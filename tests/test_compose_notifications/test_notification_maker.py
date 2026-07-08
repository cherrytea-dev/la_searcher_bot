import random

import pytest
import sqlalchemy
from sqlalchemy import select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from _dependencies.common.commons import ChangeType, TopicType
from compose_notifications._utils.database import DBClient
from compose_notifications._utils.notifications_maker import (
    NotificationMaker,
)
from tests.factories import db_models
from tests.test_compose_notifications.factories import LineInChangeLogFactory, UserFactory


@pytest.fixture
def db_client(connection_pool: Engine) -> DBClient:
    return DBClient(db=connection_pool)


def _unique_vk_id() -> str:
    """Return a unique VK ID to avoid UNIQUE constraint collisions across test runs."""
    return str(random.randint(10_000_000, 99_999_999))


def _ensure_identity_map(
    connection_pool: Engine, internal_user_id: int, messenger: str, messenger_user_id: str
) -> None:
    """Insert into user_identity_map using a dedicated connection and commit,
    so that the data is visible to DBClient (which manages its own connections)."""
    with connection_pool.connect() as conn:
        conn.execute(
            sqlalchemy.text("""
                INSERT INTO user_identity_map (internal_user_id, messenger, messenger_user_id)
                VALUES (:internal_user_id, :messenger, :messenger_user_id)
                ON CONFLICT DO NOTHING
            """),
            {'internal_user_id': internal_user_id, 'messenger': messenger, 'messenger_user_id': messenger_user_id},
        )
        conn.commit()


class TestNotificationMaker:
    def test_generate_notifications_for_users(self, db_client: DBClient, dict_notif_type_status_change):
        record = LineInChangeLogFactory.build(ignore=False, change_type=ChangeType.topic_status_change, processed=False)
        user = UserFactory.build()
        composer = NotificationMaker(db_client, record, [user])

        assert not record.processed
        composer.generate_notifications_for_users(1)
        assert record.processed

    def test_generate_notifications_for_user_text(
        self, connection_pool: Engine, db_client: DBClient, dict_notif_type_status_change, session: Session
    ):
        record = LineInChangeLogFactory.build(ignore=False, change_type=ChangeType.topic_status_change, processed=False)
        user = UserFactory.build()
        _ensure_identity_map(connection_pool, user.user_id, 'telegram', str(user.user_id))
        db = db_client
        composer = NotificationMaker(db, record, [user])
        composer._resolve_messengers_batch()

        composer.generate_notification_for_user(record.change_log_id, user)
        composer.flush_batch()

        stmt = select(db_models.NotifByUser).filter(
            db_models.NotifByUser.change_log_id == record.change_log_id,
            db_models.NotifByUser.user_id == user.user_id,
        )
        notifs = list(session.execute(stmt).scalars().all())

        assert len(notifs) == 1
        notification: db_models.NotifByUser = notifs[0]
        assert notification.created
        assert notification.message_type == 'text'

    def test_generate_notifications_for_user_text_with_coords_1(
        self, connection_pool: Engine, db_client: DBClient, dict_notif_type_new, session: Session
    ):
        record = LineInChangeLogFactory.build(
            ignore=False,
            change_type=ChangeType.topic_new,
            topic_type_id=TopicType.search_regular,
            processed=False,
            search_latitude='60.0000',
            search_longitude='60.0000',
        )
        user = UserFactory.build(
            user_latitude='55.0000',
            user_longitude='55.0000',
        )
        _ensure_identity_map(connection_pool, user.user_id, 'telegram', str(user.user_id))
        db = db_client
        composer = NotificationMaker(db, record, [user])
        composer._resolve_messengers_batch()

        composer.generate_notification_for_user(record.change_log_id, user)
        composer.flush_batch()

        stmt = select(db_models.NotifByUser).filter(
            db_models.NotifByUser.change_log_id == record.change_log_id,
            db_models.NotifByUser.user_id == user.user_id,
        )
        notifs = list(session.execute(stmt).scalars().all())

        assert len(notifs) == 2
        assert len([n for n in notifs if n.message_type == 'text']) == 1
        assert len([n for n in notifs if n.message_type == 'coords']) == 1

    def test_generate_notifications_for_user_text_with_coords_2(
        self, connection_pool: Engine, db_client: DBClient, dict_notif_type_first_post_change, session: Session
    ):
        record = LineInChangeLogFactory.build(
            ignore=False,
            change_type=ChangeType.topic_first_post_change,
            topic_type_id=TopicType.search_regular,
            processed=False,
            search_latitude='60.0000',
            search_longitude='60.0000',
            new_value="{'add':['56.1234 60.1234']}",
        )
        user = UserFactory.build(
            user_latitude='55.0000',
            user_longitude='55.0000',
        )
        _ensure_identity_map(connection_pool, user.user_id, 'telegram', str(user.user_id))
        db = db_client
        composer = NotificationMaker(db, record, [user])
        composer._resolve_messengers_batch()

        composer.generate_notification_for_user(record.change_log_id, user)
        composer.flush_batch()

        stmt = select(db_models.NotifByUser).filter(
            db_models.NotifByUser.change_log_id == record.change_log_id,
            db_models.NotifByUser.user_id == user.user_id,
        )
        notifs = list(session.execute(stmt).scalars().all())

        assert len(notifs) == 2
        assert len([n for n in notifs if n.message_type == 'text']) == 1
        assert len([n for n in notifs if n.message_type == 'coords']) == 1

    # ─── Tests for _resolve_messengers_batch() ───────────────────────────────

    def test_resolve_messengers_batch_telegram_only(
        self, connection_pool: Engine, db_client: DBClient, dict_notif_type_status_change
    ):
        """User with only telegram in user_identity_map → ['telegram']."""
        user = UserFactory.build(user_id=999999002)
        _ensure_identity_map(connection_pool, user.user_id, 'telegram', str(user.user_id))

        composer = NotificationMaker(db_client, LineInChangeLogFactory.build(), [user])
        composer._resolve_messengers_batch()
        assert composer._messenger_map == {user.user_id: ['telegram']}

    def test_resolve_messengers_batch_vk_only(
        self, connection_pool: Engine, db_client: DBClient, dict_notif_type_status_change
    ):
        """User with only vk in user_identity_map → ['vk']."""
        user = UserFactory.build(user_id=999999003)
        _ensure_identity_map(connection_pool, user.user_id, 'vk', _unique_vk_id())

        composer = NotificationMaker(db_client, LineInChangeLogFactory.build(), [user])
        composer._resolve_messengers_batch()
        assert composer._messenger_map == {user.user_id: ['vk']}

    def test_resolve_messengers_batch_telegram_and_vk(
        self, connection_pool: Engine, db_client: DBClient, dict_notif_type_status_change
    ):
        """User with both telegram and vk → ['telegram', 'vk']."""
        user = UserFactory.build(user_id=999999004)
        _ensure_identity_map(connection_pool, user.user_id, 'telegram', str(user.user_id))
        _ensure_identity_map(connection_pool, user.user_id, 'vk', _unique_vk_id())

        composer = NotificationMaker(db_client, LineInChangeLogFactory.build(), [user])
        composer._resolve_messengers_batch()
        assert set(composer._messenger_map[user.user_id]) == {'telegram', 'vk'}

    def test_resolve_messengers_batch_multiple_users(
        self, connection_pool: Engine, db_client: DBClient, dict_notif_type_status_change
    ):
        """Multiple users with different messenger combinations."""
        user_tg = UserFactory.build(user_id=999999005)
        user_vk = UserFactory.build(user_id=999999006)
        user_both = UserFactory.build(user_id=999999007)
        user_none = UserFactory.build(user_id=999999008)

        _ensure_identity_map(connection_pool, user_tg.user_id, 'telegram', str(user_tg.user_id))
        _ensure_identity_map(connection_pool, user_vk.user_id, 'vk', _unique_vk_id())
        _ensure_identity_map(connection_pool, user_both.user_id, 'telegram', str(user_both.user_id))
        _ensure_identity_map(connection_pool, user_both.user_id, 'vk', _unique_vk_id())

        composer = NotificationMaker(
            db_client, LineInChangeLogFactory.build(), [user_tg, user_vk, user_both, user_none]
        )
        composer._resolve_messengers_batch()

        assert composer._messenger_map[user_tg.user_id] == ['telegram']
        assert composer._messenger_map[user_vk.user_id] == ['vk']
        assert set(composer._messenger_map[user_both.user_id]) == {'telegram', 'vk'}
        assert composer._messenger_map[user_none.user_id] == []

    def test_resolve_messengers_batch_empty_users(self, db_client: DBClient, dict_notif_type_status_change):
        """Empty list_of_users → empty _messenger_map."""
        composer = NotificationMaker(db_client, LineInChangeLogFactory.build(), [])
        composer._resolve_messengers_batch()
        assert composer._messenger_map == {}

    # ─── Tests for _save_to_sql_notif_by_user() ──────────────────────────────

    def test_save_to_sql_notif_by_user_telegram_only(
        self, connection_pool: Engine, db_client: DBClient, dict_notif_type_status_change, session: Session
    ):
        """User with only telegram → 1 record with messenger='telegram'."""
        user = UserFactory.build(user_id=999999010)
        _ensure_identity_map(connection_pool, user.user_id, 'telegram', str(user.user_id))

        record = LineInChangeLogFactory.build(ignore=False, change_type=ChangeType.topic_status_change, processed=False)
        db = db_client
        composer = NotificationMaker(db, record, [user])
        composer._resolve_messengers_batch()
        composer._save_to_sql_notif_by_user(record.change_log_id, user.user_id, 'test msg', 'test msg', 'text', {})
        composer.flush_batch()

        notifs = list(
            session.execute(
                select(db_models.NotifByUser).filter(
                    db_models.NotifByUser.change_log_id == record.change_log_id,
                    db_models.NotifByUser.user_id == user.user_id,
                )
            )
            .scalars()
            .all()
        )
        assert len(notifs) == 1
        assert notifs[0].messenger == 'telegram'

    def test_save_to_sql_notif_by_user_vk_only(
        self, connection_pool: Engine, db_client: DBClient, dict_notif_type_status_change, session: Session
    ):
        """User with only vk → 1 record with messenger='vk'."""
        user = UserFactory.build(user_id=999999011)
        _ensure_identity_map(connection_pool, user.user_id, 'vk', _unique_vk_id())

        record = LineInChangeLogFactory.build(ignore=False, change_type=ChangeType.topic_status_change, processed=False)
        db = db_client
        composer = NotificationMaker(db, record, [user])
        composer._resolve_messengers_batch()
        composer._save_to_sql_notif_by_user(record.change_log_id, user.user_id, 'test msg', 'test msg', 'text', {})
        composer.flush_batch()

        notifs = list(
            session.execute(
                select(db_models.NotifByUser).filter(
                    db_models.NotifByUser.change_log_id == record.change_log_id,
                    db_models.NotifByUser.user_id == user.user_id,
                )
            )
            .scalars()
            .all()
        )
        assert len(notifs) == 1
        assert notifs[0].messenger == 'vk'

    def test_save_to_sql_notif_by_user_telegram_and_vk(
        self, connection_pool: Engine, db_client: DBClient, dict_notif_type_status_change, session: Session
    ):
        """User with telegram + vk → 2 records: one 'telegram', one 'vk'."""
        user = UserFactory.build(user_id=999999012)
        _ensure_identity_map(connection_pool, user.user_id, 'telegram', str(user.user_id))
        _ensure_identity_map(connection_pool, user.user_id, 'vk', _unique_vk_id())

        record = LineInChangeLogFactory.build(ignore=False, change_type=ChangeType.topic_status_change, processed=False)
        db = db_client
        composer = NotificationMaker(db, record, [user])
        composer._resolve_messengers_batch()
        composer._save_to_sql_notif_by_user(record.change_log_id, user.user_id, 'test msg', 'test msg', 'text', {})
        composer.flush_batch()

        notifs = list(
            session.execute(
                select(db_models.NotifByUser).filter(
                    db_models.NotifByUser.change_log_id == record.change_log_id,
                    db_models.NotifByUser.user_id == user.user_id,
                )
            )
            .scalars()
            .all()
        )
        assert len(notifs) == 2
        messengers = {n.messenger for n in notifs}
        assert messengers == {'telegram', 'vk'}

    def test_save_to_sql_notif_by_user_multiple_users(
        self, connection_pool: Engine, db_client: DBClient, dict_notif_type_status_change, session: Session
    ):
        """Two users: one TG+VK, one TG-only → total 3 records with correct messengers."""
        user_both = UserFactory.build(user_id=999999014)
        user_tg = UserFactory.build(user_id=999999015)
        _ensure_identity_map(connection_pool, user_both.user_id, 'telegram', str(user_both.user_id))
        _ensure_identity_map(connection_pool, user_both.user_id, 'vk', _unique_vk_id())
        _ensure_identity_map(connection_pool, user_tg.user_id, 'telegram', str(user_tg.user_id))

        record = LineInChangeLogFactory.build(ignore=False, change_type=ChangeType.topic_status_change, processed=False)
        db = DBClient(db=connection_pool)
        composer = NotificationMaker(db, record, [user_both, user_tg])
        composer._resolve_messengers_batch()

        composer._save_to_sql_notif_by_user(record.change_log_id, user_both.user_id, 'msg', 'msg', 'text', {})
        composer._save_to_sql_notif_by_user(record.change_log_id, user_tg.user_id, 'msg', 'msg', 'text', {})
        composer.flush_batch()

        notifs = list(
            session.execute(
                select(db_models.NotifByUser).filter(
                    db_models.NotifByUser.change_log_id == record.change_log_id,
                )
            )
            .scalars()
            .all()
        )
        assert len(notifs) == 3

        both_notifs = [n for n in notifs if n.user_id == user_both.user_id]
        assert len(both_notifs) == 2
        assert {n.messenger for n in both_notifs} == {'telegram', 'vk'}

        tg_notifs = [n for n in notifs if n.user_id == user_tg.user_id]
        assert len(tg_notifs) == 1
        assert tg_notifs[0].messenger == 'telegram'

    # ─── Integration tests: full cycle with user_identity_map ─────────────────

    def test_generate_notifications_for_user_text_with_vk(
        self, connection_pool: Engine, db_client: DBClient, dict_notif_type_status_change, session: Session
    ):
        """User with TG+VK, topic_status_change → 2 notif records (telegram + vk)."""
        user = UserFactory.build(user_id=999999020)
        _ensure_identity_map(connection_pool, user.user_id, 'telegram', str(user.user_id))
        _ensure_identity_map(connection_pool, user.user_id, 'vk', _unique_vk_id())

        record = LineInChangeLogFactory.build(ignore=False, change_type=ChangeType.topic_status_change, processed=False)
        composer = NotificationMaker(db_client, record, [user])
        composer.generate_notifications_for_users(1)

        notifs = list(
            session.execute(
                select(db_models.NotifByUser).filter(
                    db_models.NotifByUser.change_log_id == record.change_log_id,
                    db_models.NotifByUser.user_id == user.user_id,
                )
            )
            .scalars()
            .all()
        )
        assert len(notifs) == 2
        assert {n.messenger for n in notifs} == {'telegram', 'vk'}
        assert all(n.message_type == 'text' for n in notifs)

    def test_generate_notifications_for_user_text_and_coords_with_vk(
        self, connection_pool: Engine, db_client: DBClient, dict_notif_type_new, session: Session
    ):
        """User with TG+VK, topic_new with coords → 4 notif records (2 text + 2 coords)."""
        user = UserFactory.build(user_id=999999021, user_latitude='55.0000', user_longitude='55.0000')
        _ensure_identity_map(connection_pool, user.user_id, 'telegram', str(user.user_id))
        _ensure_identity_map(connection_pool, user.user_id, 'vk', _unique_vk_id())

        record = LineInChangeLogFactory.build(
            ignore=False,
            change_type=ChangeType.topic_new,
            topic_type_id=TopicType.search_regular,
            processed=False,
            search_latitude='60.0000',
            search_longitude='60.0000',
        )
        composer = NotificationMaker(db_client, record, [user])
        composer.generate_notifications_for_users(1)

        notifs = list(
            session.execute(
                select(db_models.NotifByUser).filter(
                    db_models.NotifByUser.change_log_id == record.change_log_id,
                    db_models.NotifByUser.user_id == user.user_id,
                )
            )
            .scalars()
            .all()
        )
        # 2 messengers × (1 text + 1 coords) = 4
        assert len(notifs) == 4
        assert len([n for n in notifs if n.messenger == 'telegram']) == 2
        assert len([n for n in notifs if n.messenger == 'vk']) == 2
        assert len([n for n in notifs if n.message_type == 'text']) == 2
        assert len([n for n in notifs if n.message_type == 'coords']) == 2

    def test_generate_notifications_for_users_mixed_messengers(
        self, connection_pool: Engine, db_client: DBClient, dict_notif_type_status_change, session: Session
    ):
        """Two users: TG-only and VK-only → correct messenger per user."""
        user_tg = UserFactory.build(user_id=999999022)
        user_vk = UserFactory.build(user_id=999999023)
        _ensure_identity_map(connection_pool, user_tg.user_id, 'telegram', str(user_tg.user_id))
        _ensure_identity_map(connection_pool, user_vk.user_id, 'vk', _unique_vk_id())

        record = LineInChangeLogFactory.build(ignore=False, change_type=ChangeType.topic_status_change, processed=False)
        composer = NotificationMaker(db_client, record, [user_tg, user_vk])
        composer.generate_notifications_for_users(1)

        notifs = list(
            session.execute(
                select(db_models.NotifByUser).filter(
                    db_models.NotifByUser.change_log_id == record.change_log_id,
                )
            )
            .scalars()
            .all()
        )
        assert len(notifs) == 2

        tg_notifs = [n for n in notifs if n.user_id == user_tg.user_id]
        assert len(tg_notifs) == 1
        assert tg_notifs[0].messenger == 'telegram'

        vk_notifs = [n for n in notifs if n.user_id == user_vk.user_id]
        assert len(vk_notifs) == 1
        assert vk_notifs[0].messenger == 'vk'
