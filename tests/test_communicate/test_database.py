from unittest.mock import MagicMock, Mock

import pytest
from faker import Faker
from psycopg2.extensions import cursor

from _dependencies.commons import get_app_config, sql_connect_by_psycopg2
from communicate._utils import handlers
from communicate._utils.database import DBClient
from tests.common import find_model
from tests.factories import db_factories, db_models
from tests.factories.telegram import get_callback_query, get_reply_markup

fake = Faker()


@pytest.fixture
def cur() -> cursor:
    with sql_connect_by_psycopg2() as conn, conn.cursor() as cur:
        yield cur


@pytest.fixture(scope='session')
def db_client() -> DBClient:
    return DBClient()


def test_save_user_message_to_bot(session, db_client: DBClient):
    user_id, message = fake.pyint(), fake.text()

    db_client.save_user_message_to_bot(user_id, message)

    assert find_model(session, db_models.Dialog, user_id=user_id, author='user', message_text=message)


def test_manage_search_whiteness(cur):
    cb_query = get_callback_query()
    user_callback = {'action': 'search_follow_mode', 'hash': '123', 'text': '   '}

    res = handlers.manage_search_whiteness(cur, 1, user_callback, 1, cb_query, 'token')

    assert res[0] == 'foo'
