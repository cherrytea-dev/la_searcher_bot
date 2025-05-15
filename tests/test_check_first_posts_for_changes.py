from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

import pytest
from requests_mock.mocker import Mocker
from sqlalchemy.orm import Session

from _dependencies.commons import sqlalchemy_get_pool
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
        patch.object(forum, 'publish_to_pubsub'),
        patch.object(main, 'publish_to_pubsub'),
        patch.object(forum, '_recognize_status_with_title_recognize', Mock(return_value='Ищем')),
    ):
        yield


@pytest.fixture(scope='session')
def db_client(db) -> DBClient:
    return DBClient(db)


@pytest.fixture(scope='session')
def db(patch_app_config):
    return sqlalchemy_get_pool(10, 10)


class TestMain:
    @pytest.mark.freeze_time('2025-02-13 14:25:00')
    def test_main(self, requests_mock: Mocker, mock_topic_management):
        # TODO mock http back or remove this test
        text = Path('tests/fixtures/forum_viewtopic_first_post.html').read_text()
        requests_mock.get(f'https://lizaalert.org/forum/viewtopic.php', text=text)  # mocking any topic

        main.main(MagicMock(), 'context')

    def test_generate_list_of_topic_groups(self):
        res = main._generate_list_of_topic_groups()

        assert len(res) == 20

    def test__define_which_topic_groups_to_be_checked(self):
        res = main._define_which_topic_groups_to_be_checked()

        assert res

    @pytest.mark.freeze_time('2025-02-13 14:27:00')
    def test_get_topics_to_check(self):
        cnt = 10
        geofolder = db_factories.GeoFolderFactory.create_sync(
            folder_type='searches',
        )
        for _ in range(cnt):
            search = db_factories.SearchFactory.create_sync(
                status='Ищем',
                forum_folder_id=geofolder.folder_id,
            )
            db_factories.SearchHealthCheckFactory.create_sync(
                search_forum_num=search.search_forum_num,
            )

        assert main.get_db_client().get_list_of_topics()
        topics_to_check = main.get_topics_to_check()

        assert topics_to_check

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

        searches = db_client.get_list_of_topics()

        assert any(s.topic_id == search.search_forum_num for s in searches)

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

        res = forum.get_search_raw_content(search_num)

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
