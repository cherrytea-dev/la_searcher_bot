from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy.engine import Connection
from sqlalchemy.orm import Session
from sqlalchemy.pool import Pool

from _dependencies import pubsub
from _dependencies.commons import sqlalchemy_get_pool
from tests.common import get_test_config
from tests.factories import db_factories


@pytest.fixture(autouse=True, scope='session')
def patch_app_config():
    """Connect to local DB"""

    with patch('_dependencies.commons._get_config', get_test_config):
        yield


@pytest.fixture(autouse=True)
def patch_publish_topic():
    with patch.object(pubsub, 'publish_to_pubsub'):
        yield


@pytest.fixture(autouse=True)
def patch_http():
    with (
        patch('urllib.request'),
        patch('requests.get'),
        patch('requests.post'),
        patch('requests.session'),
        patch('requests.Session'),
        patch('google.auth.transport.requests.Request'),
        patch('google.auth.default'),
        patch('google.oauth2.id_token.fetch_id_token'),
    ):
        yield


@pytest.fixture(scope='session')
def connection_pool() -> Pool:
    return sqlalchemy_get_pool(10, 10)


@pytest.fixture()
def connection(connection_pool: Pool) -> Connection:
    with connection_pool.connect() as conn:
        yield conn


@pytest.fixture
def session() -> Session:
    with db_factories.get_session() as session:
        yield session
