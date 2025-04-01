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


@pytest.fixture(scope='session')
def db_client() -> DBClient:
    db = DBClient()
    with db.connect():
        yield db


@pytest.fixture
def user_id() -> int:
    return fake.pyint()


def test_save_user_message_to_bot(session, db_client: DBClient, user_id: int):
    message = fake.text()

    db_client.save_user_message_to_bot(user_id, message)

    assert find_model(session, db_models.Dialog, user_id=user_id, author='user', message_text=message)


def test_add_user_sys_role(session, db_client: DBClient, user_id: int):
    role = fake.pystr(1, 5)

    db_client.add_user_sys_role(user_id, role)

    assert find_model(session, db_models.UserRole, user_id=user_id, role=role)
