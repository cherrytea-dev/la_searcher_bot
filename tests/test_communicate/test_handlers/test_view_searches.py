import datetime

import sqlalchemy

# from communicate._utils import compose_messages
from communicate._utils.database import DBClient
from communicate._utils.handlers import view_searches_handlers
from tests.common import fake
from tests.factories import db_factories


@pytest.fixture
def region_id(session):
    _region_id = fake.pyint(min_value=1_000_000_000, max_value=2_000_000_000)
    yield _region_id
    session.execute(
        sqlalchemy.text('DELETE FROM searches WHERE forum_folder_id = :region_id'),
        {'region_id': _region_id},
    )
    session.commit()


@pytest.fixture(autouse=True)
def patch_db(db_client: DBClient):
    with (
        patch.object(view_searches_handlers, 'db', Mock(return_value=db_client)),
    ):
        yield


def test__compose_text_message_of_all_searches(db_client: DBClient, user_id: int, region_id: int):
    count = 3
    searches = db_factories.SearchFactory.create_batch_sync(
        count,
        forum_folder_id=region_id,
        search_start_time=datetime.datetime.now(),
        status='Ищем',
    )
    for search in searches:
        db_factories.SearchHealthCheckFactory.create_sync(search_forum_num=search.search_forum_num, status='ok')

    message = view_searches_handlers._compose_text_message_of_all_searches(db_client, region_id, 'name of region')

    lines = message.splitlines()
    assert len(lines) == count + 1
    for search in searches:
        assert search.display_name in message


def test__compose_text_message_on_active_searches(db_client: DBClient, user_id: int, region_id: int):
    count = 3
    searches = db_factories.SearchFactory.create_batch_sync(
        count,
        forum_folder_id=region_id,
        search_start_time=datetime.datetime.now(),
        status='Ищем',
    )
    for search in searches:
        db_factories.SearchHealthCheckFactory.create_sync(search_forum_num=search.search_forum_num, status='ok')

    message = view_searches_handlers._compose_text_message_on_active_searches(
        db_client, region_id, 'name of region', user_id
    )

    lines = message.splitlines()
    assert len(lines) == count + 1
    for search in searches:
        assert search.display_name in message


def test__compose_ikb_of_last_searches(db_client: DBClient, user_id: int, region_id: int):
    count = 3
    searches = db_factories.SearchFactory.create_batch_sync(
        count,
        forum_folder_id=region_id,
        search_start_time=datetime.datetime.now(),
        status='Ищем',
    )
    for search in searches:
        db_factories.SearchHealthCheckFactory.create_sync(search_forum_num=search.search_forum_num, status='ok')

    ikb_data = view_searches_handlers._compose_ikb_of_last_searches(
        db_client, user_id, region_id, 'name of region', False
    )

    assert len(ikb_data.rows) == count


def test__compose_ikb_of_active_searches(db_client: DBClient, user_id: int, region_id: int):
    count = 3
    searches = db_factories.SearchFactory.create_batch_sync(
        count,
        forum_folder_id=region_id,
        search_start_time=datetime.datetime.now(),
        status='Ищем',
    )
    for search in searches:
        db_factories.SearchHealthCheckFactory.create_sync(search_forum_num=search.search_forum_num, status='ok')

    ikb_data = view_searches_handlers._compose_ikb_of_active_searches(db_client, user_id, region_id, 'name of region')

    assert len(ikb_data.rows) == count
