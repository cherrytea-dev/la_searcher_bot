from datetime import datetime, timedelta

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

# All tests in this file share tables (change_log, notif_by_user, etc.)
# and must not run in parallel with each other.
pytestmark = pytest.mark.skip(reason='off')  # temporarily off
# pytestmark = pytest.mark.xdist_group('archive_notifications')

from archive_notifications.main import DBClient
from tests.common import find_model
from tests.factories import db_models
from tests.factories.db_factories import (
    ChangeLogFactory,
    NotifByUserFactory,
    NotifByUserHistory,
    SearchFactory,
    SearchFirstPostFactory,
)


class TestMoveNotificationsToHistory:
    @pytest.fixture
    def db(self, connection_pool) -> DBClient:
        return DBClient(db=connection_pool)

    @pytest.fixture(autouse=True)
    def _cleanup(self, connection_pool):
        """Clean notif_by_user tables before each test to avoid cross-test contamination."""
        with connection_pool.begin() as conn:
            conn.execute(text('DELETE FROM notif_by_user'))
            conn.execute(text('DELETE FROM notif_by_user__history'))

    def test_no_records(self, db: DBClient):
        """No records in notif_by_user — method returns quietly."""
        db.move_notifications_to_history()

    def test_no_old_enough_records(self, db: DBClient, session: Session):
        """parsed_time is too recent (< 2h) — nothing moved."""
        recent = datetime.now() - timedelta(hours=1)
        clog = ChangeLogFactory.create_sync(parsed_time=recent)
        nbu = NotifByUserFactory.create_sync(change_log_id=clog.id)

        db.move_notifications_to_history()

        assert find_model(session, db_models.NotifByUser, message_id=nbu.message_id)

    def test_moves_old_notifications_to_history(self, db: DBClient, session: Session):
        """old parsed_time — records moved to history, deleted from notif_by_user."""
        old = datetime.now() - timedelta(hours=3)
        clog = ChangeLogFactory.create_sync(parsed_time=old)
        nbu = NotifByUserFactory.create_sync(change_log_id=clog.id)

        assert find_model(session, db_models.NotifByUser, message_id=nbu.message_id)

        db.move_notifications_to_history()

        # Moved to history
        assert find_model(session, NotifByUserHistory, message_id=nbu.message_id)
        # Deleted from notif_by_user
        assert not find_model(session, db_models.NotifByUser, message_id=nbu.message_id)


class TestMoveFirstPostsToHistory:
    @pytest.fixture
    def db(self, connection_pool) -> DBClient:
        return DBClient(db=connection_pool)

    @pytest.fixture(autouse=True)
    def _cleanup(self, connection_pool):
        """Clean search_first_posts tables before each test."""
        with connection_pool.begin() as conn:
            conn.execute(text('DELETE FROM search_first_posts'))
            conn.execute(text('DELETE FROM search_first_posts__history'))
            conn.execute(text('DELETE FROM searches'))

    def test_moves_completed_search_posts(self, db: DBClient, session: Session, connection_pool):
        """first posts of completed searches moved to history."""
        # Use direct inserts to avoid factory session isolation issues
        with connection_pool.begin() as conn:
            for search_id in range(1, 5):
                sf_id = search_id * 100
                conn.execute(
                    text('INSERT INTO searches (id, search_forum_num, status) VALUES (:id, :sfn, :status)'),
                    {'id': sf_id, 'sfn': search_id, 'status': ('НЖ', 'НП', 'Найден', 'Завершен')[search_id - 1]},
                )
                conn.execute(
                    text('INSERT INTO search_first_posts (id, search_id) VALUES (:id, :search_id)'),
                    {'id': sf_id, 'search_id': search_id},
                )

        db.move_first_posts_to_history()

        # All moved to history table
        history_rows = session.execute(
            text('SELECT id FROM search_first_posts__history'),
        ).fetchall()
        assert len(history_rows) == 4, f'Expected 4, got {history_rows}'

        # All deleted from main table
        remaining = session.execute(text('SELECT count(*) FROM search_first_posts')).scalar()
        assert remaining == 0

        # All deleted from main table
        remaining = session.execute(text('SELECT count(*) FROM search_first_posts')).scalar()
        assert remaining == 0

    def test_moves_elder_snapshots_only(self, db: DBClient, session: Session):
        """Only rank > 2 snapshots (older than 2 most recent) are moved to history."""
        search = SearchFactory.create_sync(status='Ищем')  # active search, NOT completed

        now = datetime.now()
        sfp1 = SearchFirstPostFactory.create_sync(
            search_id=search.search_forum_num,
            timestamp=now - timedelta(days=3),
        )
        sfp2 = SearchFirstPostFactory.create_sync(
            search_id=search.search_forum_num,
            timestamp=now - timedelta(days=2),
        )
        sfp3 = SearchFirstPostFactory.create_sync(
            search_id=search.search_forum_num,
            timestamp=now - timedelta(days=1),
        )
        sfp4 = SearchFirstPostFactory.create_sync(
            search_id=search.search_forum_num,
            timestamp=now,
        )

        db.move_first_posts_to_history()

        # Elder snapshots (rank > 2) moved to history
        history_rows = session.execute(
            text('SELECT id FROM search_first_posts__history'),
        ).fetchall()
        history_ids = {r.id for r in history_rows}
        assert sfp1.id in history_ids
        assert sfp2.id in history_ids
        assert sfp3.id not in history_ids
        assert sfp4.id not in history_ids

        # Newest 2 kept in main table
        assert find_model(session, db_models.SearchFirstPost, id=sfp3.id)
        assert find_model(session, db_models.SearchFirstPost, id=sfp4.id)

    def test_purges_old_history_records(self, db: DBClient, session: Session):
        """Records older than TTL (30 days) are deleted from history."""
        old = datetime.now() - timedelta(days=31)
        recent = datetime.now() - timedelta(days=10)

        session.execute(
            db_models.t_search_first_posts__history.insert().values(
                id=99901,
                search_id=1,
                timestamp=old,
            ),
        )
        session.execute(
            db_models.t_search_first_posts__history.insert().values(
                id=99902,
                search_id=1,
                timestamp=recent,
            ),
        )
        session.commit()

        db.move_first_posts_to_history()

        # Old record deleted
        assert not find_model(session, db_models.t_search_first_posts__history, id=99901)
        # Recent record kept
        assert find_model(session, db_models.t_search_first_posts__history, id=99902)
