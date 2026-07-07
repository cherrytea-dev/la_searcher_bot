import datetime

from sqlalchemy.orm import Session

from identify_updates_of_first_posts._utils.database import DBClient
from tests.common import find_model
from tests.factories import db_factories, db_models


class TestGetSearchStatus:
    def test_returns_status_for_existing_search(self, db_client: DBClient):
        search = db_factories.SearchFactory.create_sync(status='Ищем')

        result = db_client.get_search_status(search.search_forum_num)

        assert result == 'Ищем'

    def test_returns_none_for_missing_search(self, db_client: DBClient):
        result = db_client.get_search_status(999999999)

        assert result is None

    def test_returns_status_for_finished_search(self, db_client: DBClient):
        search = db_factories.SearchFactory.create_sync(status='Завершен')

        result = db_client.get_search_status(search.search_forum_num)

        assert result == 'Завершен'


class TestIsSearchStatusActive:
    def test_true_for_active(self, db_client: DBClient):
        search = db_factories.SearchFactory.create_sync(status='Ищем')

        assert db_client.is_search_status_active(search.search_forum_num) is True

    def test_false_for_finished(self, db_client: DBClient):
        search = db_factories.SearchFactory.create_sync(status='Завершен')

        assert db_client.is_search_status_active(search.search_forum_num) is False

    def test_false_for_missing(self, db_client: DBClient):
        assert db_client.is_search_status_active(999999999) is False


class TestSaveRecordInChangeLog:
    def test_creates_record_and_returns_id(self, db_client: DBClient, session: Session):
        search_id = 123456789
        new_value = 'test_value'
        changed_field = 'test_field'
        change_type = 1

        change_log_id = db_client.save_record_in_change_log(search_id, new_value, changed_field, change_type)

        model = find_model(session, db_models.ChangeLog, id=change_log_id)
        assert model is not None
        assert model.search_forum_num == search_id
        assert model.new_value == new_value
        assert model.changed_field == changed_field
        assert model.change_type == change_type
        assert isinstance(model.parsed_time, datetime.datetime)


class TestGetActualPageContent:
    def test_returns_content_and_compact(self, db_client: DBClient):
        post = db_factories.SearchFirstPostFactory.create_sync(
            actual=True,
            content='<p>test content</p>',
            content_compact='test compact',
        )

        content, content_compact = db_client.get_actual_page_content(post.search_id)

        assert content == '<p>test content</p>'
        assert content_compact == 'test compact'

    def test_returns_none_none_when_no_row(self, db_client: DBClient):
        content, content_compact = db_client.get_actual_page_content(999999999)

        assert content is None
        assert content_compact is None

    def test_returns_only_actual_post(self, db_client: DBClient):
        db_factories.SearchFirstPostFactory.create_sync(actual=False, content='old content', search_id=42)
        db_factories.SearchFirstPostFactory.create_sync(actual=True, content='new content', search_id=42)

        content, _ = db_client.get_actual_page_content(42)

        assert content == 'new content'

    def test_returns_none_for_compact_when_null(self, db_client: DBClient):
        post = db_factories.SearchFirstPostFactory.create_sync(actual=True, content='test', content_compact=None)

        content, content_compact = db_client.get_actual_page_content(post.search_id)

        assert content == 'test'
        assert content_compact is None


class TestSaveCompactContent:
    def test_updates_content_compact(self, db_client: DBClient, session: Session):
        post = db_factories.SearchFirstPostFactory.create_sync(actual=True, content='test')

        db_client.save_compact_content(post.search_id, 'new compact value')

        model = find_model(session, db_models.SearchFirstPost, search_id=post.search_id, actual=True)
        assert model.content_compact == 'new compact value'

    def test_only_updates_actual_post(self, db_client: DBClient, session: Session):
        search_id = 555
        db_factories.SearchFirstPostFactory.create_sync(
            actual=False, content='old', search_id=search_id, content_compact=None
        )
        db_factories.SearchFirstPostFactory.create_sync(actual=True, content='new', search_id=search_id)

        db_client.save_compact_content(search_id, 'updated compact')

        old_model = find_model(session, db_models.SearchFirstPost, search_id=search_id, actual=False)
        new_model = find_model(session, db_models.SearchFirstPost, search_id=search_id, actual=True)
        assert old_model.content_compact is None
        assert new_model.content_compact == 'updated compact'


class TestGetPreviousPageContent:
    def test_returns_previous_content(self, db_client: DBClient):
        db_factories.SearchFirstPostFactory.create_sync(
            actual=False, content='previous content', search_id=123, timestamp=datetime.datetime(2024, 1, 1)
        )
        db_factories.SearchFirstPostFactory.create_sync(
            actual=True, content='current content', search_id=123, timestamp=datetime.datetime(2024, 1, 2)
        )

        result = db_client.get_previous_page_content(123)

        assert result == 'previous content'

    def test_returns_none_when_no_previous(self, db_client: DBClient):
        result = db_client.get_previous_page_content(999999999)

        assert result is None

    def test_returns_latest_previous_when_multiple(self, db_client: DBClient):
        search_id = 777
        db_factories.SearchFirstPostFactory.create_sync(
            actual=False, content='older', search_id=search_id, timestamp=datetime.datetime(2024, 1, 1)
        )
        db_factories.SearchFirstPostFactory.create_sync(
            actual=False, content='newer', search_id=search_id, timestamp=datetime.datetime(2024, 1, 3)
        )
        db_factories.SearchFirstPostFactory.create_sync(
            actual=True, content='current', search_id=search_id, timestamp=datetime.datetime(2024, 1, 4)
        )

        result = db_client.get_previous_page_content(search_id)

        assert result == 'newer'
