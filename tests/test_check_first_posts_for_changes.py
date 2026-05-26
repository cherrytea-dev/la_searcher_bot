from pathlib import Path
from unittest.mock import MagicMock, Mock, patch
from uuid import uuid4

import pytest
from requests_mock.mocker import Mocker
from sqlalchemy.orm import Session

import check_first_posts_for_changes._utils.database
from check_first_posts_for_changes import main
from check_first_posts_for_changes._utils import forum
from check_first_posts_for_changes._utils.database import DBClient
from tests.common import fake, find_model
from tests.factories import db_factories, db_models


@pytest.fixture(autouse=True)
def patch_http():
    pass  # disable http mocking


@pytest.fixture
def mock_topic_management():
    with (
        patch.object(forum, '_recognize_status_with_title_recognize', Mock(return_value='Ищем')),
    ):
        yield


@pytest.fixture(scope='session')
def db_client(connection_pool) -> DBClient:
    return DBClient(connection_pool)


class TestMain:
    @pytest.mark.freeze_time('2025-02-13 14:25:00')
    def test_main(self, requests_mock: Mocker, mock_topic_management):
        # TODO mock http back or remove this test
        text = Path('tests/fixtures/forum_viewtopic_first_post.html').read_text()
        requests_mock.get(f'https://lizaalert.org/forum/viewtopic.php', text=text)  # mocking any topic

        main.main(MagicMock(), 'context')

    def test_update_one_topic_visibility(self, session):
        search_health_check = db_factories.SearchHealthCheckFactory.create_sync()
        old_status = search_health_check.status
        topic_id = search_health_check.search_forum_num

        main.update_one_topic_visibility(topic_id, 'hidden')

        assert not find_model(session, db_models.SearchHealthCheck, search_forum_num=topic_id, status=old_status)
        assert find_model(session, db_models.SearchHealthCheck, search_forum_num=topic_id, status='hidden')

    def test__update_one_topic_hash(self):
        pass


class TestDBClient:
    def test_get_random_hidden_topic(self, db_client: DBClient, session: Session):
        search = db_factories.SearchFactory.create_sync(status='Ищем')
        search_health_check = db_factories.SearchHealthCheckFactory.create_sync(
            search_forum_num=search.search_forum_num, status='hidden'
        )
        assert db_client.get_random_hidden_topic_id()

    def test_delete_search_health_check(self, db_client: DBClient, session: Session):
        model = db_factories.SearchHealthCheckFactory.create_sync()

        db_client.delete_search_health_check(model.search_forum_num)

        assert not find_model(session, db_models.SearchHealthCheck, search_forum_num=model.search_forum_num)

    def test_write_search_health_check(self, db_client: DBClient, session: Session):
        search_id = fake.pyint()

        db_client.write_search_health_check(search_id, 'hidden')

        assert find_model(session, db_models.SearchHealthCheck, search_forum_num=search_id, status='hidden')

    def test_get_list_of_topics(self, db_client: DBClient, session: Session):
        search = db_factories.SearchFactory.create_sync(status='Ищем')
        geofolder = db_factories.GeoFolderFactory.create_sync(
            folder_type='searches',
            folder_id=search.forum_folder_id,
        )
        search_health_check = db_factories.SearchHealthCheckFactory.create_sync(
            search_forum_num=search.search_forum_num,
        )

        active_searches_ids = db_client.get_active_searches_ids()

        assert search.search_forum_num in active_searches_ids

    def test_create_search_first_post(self, db_client: DBClient, session: Session):
        search_id = fake.pyint()

        db_client.create_search_first_post(search_id, 'foo', 'bar')

        assert find_model(session, db_models.SearchFirstPost, search_id=search_id, content_hash='foo')

    def test_mark_search_first_post_as_not_actual(self, db_client: DBClient, session: Session):
        sfp = db_factories.SearchFirstPostFactory.create_sync(actual=True)

        db_client.mark_search_first_post_as_not_actual(sfp.search_id)

        assert find_model(session, db_models.SearchFirstPost, search_id=sfp.search_id, actual=False)

    def test_get_search_first_post_actual_hash(self, db_client: DBClient, session: Session):
        sfp = db_factories.SearchFirstPostFactory.create_sync(actual=True)

        hash = db_client.get_search_first_post_actual_hash(sfp.search_id)

        assert hash == sfp.content_hash


class TestForum:
    def test_get_search_raw_content(self, requests_mock: Mocker):
        search_num = 1
        text = Path('tests/fixtures/forum_viewtopic_first_post.html').read_text()
        requests_mock.get(
            f'https://lizaalert.org/forum/viewtopic.php?t={search_num}',
            text=text,
        )

        res = forum._get_search_raw_content(search_num)

        assert res

    def test_get_first_post(self, requests_mock: Mocker, mock_topic_management):
        search_num = 1
        text = Path('tests/fixtures/forum_viewtopic_first_post.html').read_text()
        requests_mock.get(
            f'https://lizaalert.org/forum/viewtopic.php?t={search_num}',
            text=text,
        )

        res = forum.get_first_post(search_num)

        assert res.topic_visibility == 'regular'
        assert res.hash_num == '30439b2156a1c8050154c142dda4d04c'


class TestParseDatabaseTables:
    """New way to identify updates: parse table `phpbb_posts_history` in mysql"""

    def test_fetch_changes_from_last_time(self):
        db_cln_2 = check_first_posts_for_changes._utils.database.get_phpbb_db_client()
        assert db_cln_2
        last_change_id = 1
        changes = db_cln_2.get_changed_post_ids_from_last_id(last_change_id)
        assert changes

    def test_key_value_settings(self, db_client: DBClient):
        key = str(uuid4())
        value = '123'

        db_client.set_key_value_item(key, value)
        saved = db_client.get_key_value_item(key)

        assert saved == value
