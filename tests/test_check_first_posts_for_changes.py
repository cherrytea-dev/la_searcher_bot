from datetime import datetime
from unittest.mock import MagicMock, Mock, patch

import pytest
from faker import Faker
from sqlalchemy.orm import Session

from _dependencies.commons import sqlalchemy_get_pool
from check_first_posts_for_changes import main
from check_first_posts_for_changes._utils.database import DBClient
from tests.common import find_model
from tests.factories import db_factories, db_models

fake = Faker()


@pytest.fixture(scope='session')
def db_client(db) -> DBClient:
    return DBClient(db)


@pytest.fixture(scope='session')
def db(patch_app_config):
    return sqlalchemy_get_pool(10, 10)


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


def test_main():
    main.main(MagicMock(), 'context')
    assert True


def test_generate_list_of_topic_groups():
    res = main._generate_list_of_topic_groups()
    assert len(res) == 20


def test__define_which_topic_groups_to_be_checked():
    res = main._define_which_topic_groups_to_be_checked()
    assert res


def test_get_topics_to_check():
    cnt = 10
    geofolder = db_factories.GeoFolderFactory.create_sync(
        folder_type='searches',
    )
    for _ in range(cnt):
        search = db_factories.SearchFactory.create_sync(
            status='Ищем',
            forum_folder_id=geofolder.folder_id,
        )
        search_health_check = db_factories.SearchHealthCheckFactory.create_sync(
            search_forum_num=search.search_forum_num,
        )
    topics_to_check = main.get_topics_to_check()
    assert topics_to_check
