import datetime
from unittest.mock import Mock, patch

import pytest

# from communicate._utils import compose_messages
from communicate._utils.database import DBClient
from communicate._utils.handlers import view_searches_handlers
from tests.common import fake, find_model
from tests.factories import db_factories, db_models


@pytest.fixture(autouse=True)
def patch_db(db_client: DBClient):
    with (
        patch.object(view_searches_handlers, 'db', Mock(return_value=db_client)),
    ):
        yield


def test__compose_text_message_of_all_searches(session, db_client: DBClient, user_id: int, user_model: db_models.User):
    region_id = fake.pyint()
    count = 3
    searches = db_factories.SearchFactory.create_batch_sync(
        count,
        forum_folder_id=region_id,
        search_start_time=datetime.datetime.now(),
        status='Ищем',
    )
    for search in searches:
        db_factories.SearchHealthCheckFactory.create_sync(search_forum_num=search.search_forum_num, status='ok')

    message = view_searches_handlers._compose_text_message_of_all_searches(region_id, 'name of region')

    lines = message.splitlines()
    assert len(lines) == count + 1
    for search in searches:
        assert search.display_name in message


def test__compose_text_message_on_active_searches(
    session, db_client: DBClient, user_id: int, user_model: db_models.User
):
    region_id = fake.pyint()
    count = 3
    searches = db_factories.SearchFactory.create_batch_sync(
        count,
        forum_folder_id=region_id,
        search_start_time=datetime.datetime.now(),
        status='Ищем',
    )
    for search in searches:
        db_factories.SearchHealthCheckFactory.create_sync(search_forum_num=search.search_forum_num, status='ok')

    message = view_searches_handlers._compose_text_message_on_active_searches(region_id, 'name of region', user_id)

    lines = message.splitlines()
    assert len(lines) == count + 1
    for search in searches:
        assert search.display_name in message


def test__compose_ikb_of_last_searches(session, db_client: DBClient, user_id: int, user_model: db_models.User):
    region_id = fake.pyint()
    count = 3
    searches = db_factories.SearchFactory.create_batch_sync(
        count,
        forum_folder_id=region_id,
        search_start_time=datetime.datetime.now(),
        status='Ищем',
    )
    for search in searches:
        db_factories.SearchHealthCheckFactory.create_sync(search_forum_num=search.search_forum_num, status='ok')

    ikb_data = view_searches_handlers._compose_ikb_of_last_searches(user_id, region_id, 'name of region', False)

    assert len(ikb_data.rows) == count


def test__compose_ikb_of_active_searches(session, db_client: DBClient, user_id: int, user_model: db_models.User):
    region_id = fake.pyint()
    count = 3
    searches = db_factories.SearchFactory.create_batch_sync(
        count,
        forum_folder_id=region_id,
        search_start_time=datetime.datetime.now(),
        status='Ищем',
    )
    for search in searches:
        db_factories.SearchHealthCheckFactory.create_sync(search_forum_num=search.search_forum_num, status='ok')

    ikb_data = view_searches_handlers._compose_ikb_of_active_searches(user_id, region_id, 'name of region')

    assert len(ikb_data.rows) == count
