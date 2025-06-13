import pytest

from communicate._utils.database import DBClient
from tests.factories import db_factories, db_models


@pytest.fixture(scope='session')
def db_client(connection_pool) -> DBClient:
    db = DBClient(connection_pool)
    return db


@pytest.fixture
def user_model() -> int:
    return db_factories.UserFactory.create_sync()


@pytest.fixture
def user_id(user_model: db_models.User) -> int:
    return user_model.user_id
