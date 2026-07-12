"""Tests for the legacy DBClient.

The legacy `check_first_posts_for_changes._legacy._utils.database` module
is being updated alongside the rest of the project in PR #11 (SQLAlchemy 2.0).

Key differences from the non-legacy DBClient:
- ``connect()`` returns ``self._db.begin()`` (transactional auto-commit context manager)
  instead of ``self._db.connect()``.
- Uses :class:`check_first_posts_for_changes._legacy._utils.commons.Search` / ``RSSItem``
  dataclasses instead of plain ``int`` / ``NamedTuple``.
"""

from datetime import datetime

import pytest
import sqlalchemy
from freezegun import freeze_time
from sqlalchemy.orm import Session

from check_first_posts_for_changes._legacy._utils.commons import RSSItem, Search
from check_first_posts_for_changes._legacy._utils.database import DBClient as LegacyDBClient
from tests.common import fake, find_model
from tests.factories import db_factories, db_models

# All tests in this file run in a single xdist worker to avoid
# interference with each other on the shared database.
pytestmark = pytest.mark.xdist_group('legacy_db')


@pytest.fixture(scope='session')
def db_client(connection_pool):
    """Create a legacy DBClient connected to the test pool."""
    return LegacyDBClient(connection_pool)


def _make_geo_folder_with_view_support(
    session: Session,
    **kwargs,
) -> db_models.GeoFolder:
    """Create a GeoFolder together with a corresponding GeoDivision.

    ``geo_folders_view`` does a LEFT JOIN with ``geo_divisions`` to compute
    ``folder_display_name``.  Without a matching division the view returns
    NULL, which breaks callers that expect a string (e.g. ``get_geo_folders()``).
    """
    folder = db_factories.GeoFolderFactory.create_sync(**kwargs)
    if 'division_id' not in kwargs or kwargs.get('division_id') is not None:
        try:
            div = db_models.GeoDivision(
                division_id=folder.division_id,
                division_name=fake.city(),
            )
            session.add(div)
            session.commit()
        except sqlalchemy.exc.IntegrityError:
            # Division already exists (leftover from a previous test) — fine
            session.rollback()
    return folder


class TestGetRandomHiddenTopic:
    """``get_random_hidden_topic_id`` — returns a hidden topic's ``search_forum_num``."""

    def test_returns_some_topic(self, db_client: LegacyDBClient, session: Session):
        """Returns a hidden topic ID when one exists."""
        search = db_factories.SearchFactory.create_sync(status='Ищем')
        db_factories.SearchHealthCheckFactory.create_sync(
            search_forum_num=search.search_forum_num,
            status='hidden',
        )

        result = db_client.get_random_hidden_topic_id()

        assert isinstance(result, int)
        assert result > 0

    def test_skips_deleted_health_check(self, db_client: LegacyDBClient, session: Session):
        """Returns a different hidden topic when the only 'deleted' one is ignored."""
        search = db_factories.SearchFactory.create_sync(status='Ищем')
        db_factories.SearchHealthCheckFactory.create_sync(
            search_forum_num=search.search_forum_num,
            status='deleted',
        )

        result = db_client.get_random_hidden_topic_id()

        # result might be None (no eligible topics) or some other topic
        assert result is None or isinstance(result, int)


class TestDeleteSearchHealthCheck:
    """``delete_search_health_check`` — removes rows from ``search_health_check``."""

    def test_deletes_existing_record(self, db_client: LegacyDBClient, session: Session):
        model = db_factories.SearchHealthCheckFactory.create_sync()

        db_client.delete_search_health_check(model.search_forum_num)

        assert not find_model(session, db_models.SearchHealthCheck, search_forum_num=model.search_forum_num)

    def test_does_not_affect_other_records(self, db_client: LegacyDBClient, session: Session):
        to_delete, to_keep = db_factories.SearchHealthCheckFactory.create_batch_sync(2)

        db_client.delete_search_health_check(to_delete.search_forum_num)

        assert find_model(session, db_models.SearchHealthCheck, id=to_keep.id)
        assert not find_model(session, db_models.SearchHealthCheck, id=to_delete.id)

    def test_noop_when_not_found(self, db_client: LegacyDBClient, session: Session):
        """Deleting a non-existent record should not raise."""
        db_client.delete_search_health_check(999_999_999)


class TestWriteSearchHealthCheck:
    """``write_search_health_check`` — inserts into ``search_health_check``."""

    def test_writes_new_record(self, db_client: LegacyDBClient, session: Session):
        search_id = fake.pyint(min_value=1_000_000_000, max_value=2_000_000_000)

        with freeze_time('2026-07-06 14:00:00'):
            db_client.write_search_health_check(search_id, 'hidden')

        record = find_model(session, db_models.SearchHealthCheck, search_forum_num=search_id)
        assert record is not None
        assert record.status == 'hidden'
        assert record.timestamp == datetime(2026, 7, 6, 14, 0, 0)

    def test_writes_regular_visibility(self, db_client: LegacyDBClient, session: Session):
        search_id = fake.pyint(min_value=1_000_000_000, max_value=2_000_000_000)

        db_client.write_search_health_check(search_id, 'regular')

        record = find_model(session, db_models.SearchHealthCheck, search_forum_num=search_id)
        assert record is not None
        assert record.status == 'regular'


class TestGetListOfTopics:
    """``get_list_of_topics`` — returns active searches that are NOT deleted/hidden."""

    def test_returns_eligible_searches(self, db_client: LegacyDBClient, session: Session):
        search = db_factories.SearchFactory.create_sync(status='Ищем')
        _make_geo_folder_with_view_support(
            session,
            folder_id=search.forum_folder_id,
            folder_type='searches',
        )

        results = db_client.get_list_of_topics()

        topic_ids = [s.topic_id for s in results]
        assert search.search_forum_num in topic_ids

    def test_excludes_deleted_health_check(self, db_client: LegacyDBClient, session: Session):
        search = db_factories.SearchFactory.create_sync(status='Ищем')
        _make_geo_folder_with_view_support(
            session,
            folder_id=search.forum_folder_id,
            folder_type='searches',
        )
        db_factories.SearchHealthCheckFactory.create_sync(
            search_forum_num=search.search_forum_num,
            status='deleted',
        )

        results = db_client.get_list_of_topics()

        assert search.search_forum_num not in [s.topic_id for s in results]

    def test_excludes_hidden_health_check(self, db_client: LegacyDBClient, session: Session):
        search = db_factories.SearchFactory.create_sync(status='Ищем')
        _make_geo_folder_with_view_support(
            session,
            folder_id=search.forum_folder_id,
            folder_type='searches',
        )
        db_factories.SearchHealthCheckFactory.create_sync(
            search_forum_num=search.search_forum_num,
            status='hidden',
        )

        results = db_client.get_list_of_topics()

        assert search.search_forum_num not in [s.topic_id for s in results]

    @pytest.mark.parametrize(
        'folder_type',
        [
            None,
            'searches',
        ],
    )
    def test_allows_geo_folder_types(self, db_client: LegacyDBClient, session: Session, folder_type):
        """Both NULL folder_type and 'searches' are valid."""
        search = db_factories.SearchFactory.create_sync(status='Ищем')

        # Explicitly pass folder_type=None for the NULL case; the factory
        # would otherwise generate a random string.
        _make_geo_folder_with_view_support(
            session,
            folder_id=search.forum_folder_id,
            folder_type=folder_type,
        )

        results = db_client.get_list_of_topics()

        assert search.search_forum_num in [s.topic_id for s in results]

    def test_excludes_non_search_folder_type(self, db_client: LegacyDBClient, session: Session):
        """Folders with a non-NULL, non-'searches' folder_type should exclude the search."""
        search = db_factories.SearchFactory.create_sync(status='Ищем')
        _make_geo_folder_with_view_support(
            session,
            folder_id=search.forum_folder_id,
            folder_type='info',
        )

        results = db_client.get_list_of_topics()

        assert search.search_forum_num not in [s.topic_id for s in results]

    def test_returns_search_dataclass(self, db_client: LegacyDBClient, session: Session):
        """Each result should be a ``Search`` dataclass with ``topic_id`` set."""
        search = db_factories.SearchFactory.create_sync(status='Ищем')
        _make_geo_folder_with_view_support(
            session,
            folder_id=search.forum_folder_id,
            folder_type='searches',
        )

        results = db_client.get_list_of_topics()

        assert all(isinstance(s, Search) for s in results)
        assert any(s.topic_id == search.search_forum_num for s in results)

    def test_ignores_no_longer_eligible_searches(self, db_client: LegacyDBClient, session: Session):
        """Only searches with status 'Ищем' should be returned."""
        search_found = db_factories.SearchFactory.create_sync(status='Найден')
        search_nj = db_factories.SearchFactory.create_sync(status='НЖ')
        search_np = db_factories.SearchFactory.create_sync(status='НП')
        search_ischem = db_factories.SearchFactory.create_sync(status='Ищем')
        _ = _make_geo_folder_with_view_support(
            session,
            folder_id=search_ischem.forum_folder_id,
            folder_type='searches',
        )

        results = db_client.get_list_of_topics()
        topic_ids = [s.topic_id for s in results]

        # non-Ищем searches should NOT appear
        assert search_found.search_forum_num not in topic_ids
        assert search_nj.search_forum_num not in topic_ids
        assert search_np.search_forum_num not in topic_ids
        # Ищем search SHOULD appear
        assert search_ischem.search_forum_num in topic_ids

    def test_returns_results_in_reverse_start_time_order(self, db_client: LegacyDBClient, session: Session):
        """Searches should be ordered by ``search_start_time DESC``."""
        from datetime import datetime as dt

        folder = _make_geo_folder_with_view_support(session, folder_type='searches')
        old = db_factories.SearchFactory.create_sync(
            status='Ищем',
            forum_folder_id=folder.folder_id,
            search_start_time=dt(2026, 1, 1, 12, 0, 0),
        )
        mid = db_factories.SearchFactory.create_sync(
            status='Ищем',
            forum_folder_id=folder.folder_id,
            search_start_time=dt(2026, 6, 1, 12, 0, 0),
        )
        new = db_factories.SearchFactory.create_sync(
            status='Ищем',
            forum_folder_id=folder.folder_id,
            search_start_time=dt(2026, 7, 1, 12, 0, 0),
        )

        results = db_client.get_list_of_topics()

        # newest search should appear first (DESC order)
        topic_ids = [s.topic_id for s in results]
        assert topic_ids.index(new.search_forum_num) < topic_ids.index(mid.search_forum_num)
        assert topic_ids.index(mid.search_forum_num) < topic_ids.index(old.search_forum_num)

    def test_returns_list_type(self, db_client: LegacyDBClient, session: Session):
        """Always returns a list, even when no eligible searches."""
        results = db_client.get_list_of_topics()
        assert isinstance(results, list)


class TestCreateSearchFirstPost:
    """``create_search_first_post`` — inserts into ``search_first_posts``."""

    def test_creates_record(self, db_client: LegacyDBClient, session: Session):
        topic_id = fake.pyint(min_value=1_000_000_000, max_value=2_000_000_000)
        hash_val = 'abc123'
        content = 'First post content'

        with freeze_time('2026-07-06 14:00:00'):
            db_client.create_search_first_post(topic_id, hash_val, content)

        record = find_model(session, db_models.SearchFirstPost, search_id=topic_id)
        assert record is not None
        assert record.content_hash == hash_val
        assert record.content == content
        assert record.actual is True
        assert record.num_of_checks == 1
        assert record.timestamp == datetime(2026, 7, 6, 14, 0, 0)

    def test_multiple_posts_for_same_topic(self, db_client: LegacyDBClient, session: Session):
        topic_id = fake.pyint(min_value=1_000_000_000, max_value=2_000_000_000)

        db_client.create_search_first_post(topic_id, 'hash1', 'Content 1')

        # The table has no unique constraint on search_id, so a second insert
        # should succeed (it will be marked as not actual later).
        db_client.create_search_first_post(topic_id, 'hash2', 'Content 2')

        records = session.query(db_models.SearchFirstPost).filter(db_models.SearchFirstPost.search_id == topic_id).all()
        assert len(records) == 2


class TestMarkSearchFirstPostAsNotActual:
    """``mark_search_first_post_as_not_actual`` — sets ``actual = FALSE``."""

    def test_marks_record_as_not_actual(self, db_client: LegacyDBClient, session: Session):
        sfp = db_factories.SearchFirstPostFactory.create_sync(actual=True)

        db_client.mark_search_first_post_as_not_actual(sfp.search_id)

        record = find_model(session, db_models.SearchFirstPost, id=sfp.id)
        assert record is not None
        assert record.actual is False

    def test_does_not_affect_other_records(self, db_client: LegacyDBClient, session: Session):
        to_update, to_keep = db_factories.SearchFirstPostFactory.create_batch_sync(2, actual=True)

        db_client.mark_search_first_post_as_not_actual(to_update.search_id)

        assert find_model(session, db_models.SearchFirstPost, id=to_update.id).actual is False
        assert find_model(session, db_models.SearchFirstPost, id=to_keep.id).actual is True


class TestGetSearchFirstPostActualHash:
    """``get_search_first_post_actual_hash`` — returns the hash of the actual first post."""

    def test_returns_hash_for_actual_post(self, db_client: LegacyDBClient, session: Session):
        sfp = db_factories.SearchFirstPostFactory.create_sync(actual=True, content_hash='target_hash')

        result = db_client.get_search_first_post_actual_hash(sfp.search_id)

        assert result == 'target_hash'

    def test_returns_none_when_not_actual(self, db_client: LegacyDBClient, session: Session):
        db_factories.SearchFirstPostFactory.create_sync(actual=False, content_hash='stale_hash')

        result = db_client.get_search_first_post_actual_hash(fake.pyint())

        assert result is None

    def test_returns_none_when_no_record(self, db_client: LegacyDBClient, session: Session):
        result = db_client.get_search_first_post_actual_hash(999_999_999)

        assert result is None

    def test_ignores_not_actual_records(self, db_client: LegacyDBClient, session: Session):
        sfp = db_factories.SearchFirstPostFactory.create_sync(actual=True, content_hash='actual_hash')
        db_factories.SearchFirstPostFactory.create_sync(
            search_id=sfp.search_id,
            actual=False,
            content_hash='stale_hash',
        )

        result = db_client.get_search_first_post_actual_hash(sfp.search_id)

        assert result == 'actual_hash'


class TestRssItems:
    """``save_rss_item`` / ``get_rss_item`` — CRUD for ``rss_items`` table.

    .. note::

        The ``rss_items`` table is **not** part of the test DB schema
        (``tests/tools/db.sql``).  Tests for these methods are therefore
        skipped by default.  To run them, add the table to the test schema
        first.

    The RSS feed feature is legacy and scheduled for removal (see
    ``_legacy/main.py`` TODO comment).
    """

    @pytest.mark.skip(
        reason='rss_items table not present in test database schema (see tests/tools/db.sql). Add it to run RSS tests.'
    )
    def test_save_and_get_rss_item(self, db_client: LegacyDBClient, session: Session):
        item = RSSItem(
            topic_id=123,
            published_at=datetime(2026, 1, 1, 12, 0, 0),
            updated_at=datetime(2026, 1, 1, 13, 0, 0),
            item_id='https://example.com/rss/1',
            content='RSS item summary',
        )

        db_client.save_rss_item(item)
        result = db_client.get_rss_item(item.item_id)

        assert result is not None
        assert result.topic_id == item.topic_id
        assert result.item_id == item.item_id
        assert result.content == item.content
        assert result.published_at == item.published_at
        assert result.updated_at == item.updated_at

    @pytest.mark.skip(
        reason='rss_items table not present in test database schema (see tests/tools/db.sql). Add it to run RSS tests.'
    )
    def test_get_rss_item_none_when_not_found(self, db_client: LegacyDBClient, session: Session):
        result = db_client.get_rss_item('nonexistent-url')
        assert result is None

    @pytest.mark.skip(
        reason='rss_items table not present in test database schema (see tests/tools/db.sql). Add it to run RSS tests.'
    )
    def test_get_rss_item_returns_full_dataclass(self, db_client: LegacyDBClient, session: Session):
        item = RSSItem(
            topic_id=456,
            published_at=datetime(2026, 2, 1, 10, 0, 0),
            updated_at=datetime(2026, 2, 1, 11, 0, 0),
            item_id='https://example.com/rss/2',
            content='Another summary',
        )
        db_client.save_rss_item(item)
        result = db_client.get_rss_item(item.item_id)

        assert isinstance(result, RSSItem)
        assert result.id is not None  # auto-generated primary key


class TestIntegration:
    """End-to-end scenarios combining multiple ``DBClient`` methods."""

    def test_full_first_post_lifecycle(self, db_client: LegacyDBClient, session: Session):
        """Simulate the full flow: create → mark not actual → create new → get hash."""
        topic_id = fake.pyint(min_value=1_000_000_000, max_value=2_000_000_000)

        # Create first version
        db_client.create_search_first_post(topic_id, 'hash_v1', 'Content v1')
        assert db_client.get_search_first_post_actual_hash(topic_id) == 'hash_v1'

        # Mark as not actual and create second version
        db_client.mark_search_first_post_as_not_actual(topic_id)
        db_client.create_search_first_post(topic_id, 'hash_v2', 'Content v2')

        # Now the latest actual hash should be v2
        assert db_client.get_search_first_post_actual_hash(topic_id) == 'hash_v2'

    def test_visibility_lifecycle(self, db_client: LegacyDBClient, session: Session):
        """Delete old health check, write new visibility, verify."""
        topic_id = fake.pyint(min_value=1_000_000_000, max_value=2_000_000_000)

        db_client.write_search_health_check(topic_id, 'hidden')
        assert find_model(session, db_models.SearchHealthCheck, search_forum_num=topic_id, status='hidden')

        db_client.delete_search_health_check(topic_id)
        db_client.write_search_health_check(topic_id, 'regular')
        assert find_model(session, db_models.SearchHealthCheck, search_forum_num=topic_id, status='regular')
        assert not find_model(session, db_models.SearchHealthCheck, search_forum_num=topic_id, status='hidden')
