import base64
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy.engine import Connection
from sqlalchemy.orm import Session

from _dependencies.commons import Topics, sql_connect_by_psycopg2, sqlalchemy_get_pool
from tests.common import get_test_config, topic_to_receiver_function
from tests.factories import db_factories


@pytest.fixture(autouse=True, scope='session')
def patch_app_config():
    """Connect to local DB"""

    with patch('_dependencies.commons._get_config', get_test_config):
        yield


@pytest.fixture()
def patch_publish_topic():
    def patched_send_topic(topic_name: Topics, topic_path, data: dict) -> None:
        receiver = topic_to_receiver_function(topic_name)
        receiver({'data': base64.encodebytes(data)}, 'context')

    with patch('_dependencies.pubsub._send_topic', patched_send_topic):
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


@pytest.fixture(autouse=True)
def patch_pubsub_client() -> MagicMock:
    with patch('google.cloud.pubsub_v1.PublisherClient', MagicMock()) as mock:
        yield mock


@pytest.fixture
def connection() -> Connection:
    pool = sqlalchemy_get_pool(10, 10)
    with pool.connect() as conn:
        yield conn


@pytest.fixture
def connection_psy() -> Connection:
    return sql_connect_by_psycopg2()


@pytest.fixture
def session() -> Session:
    with db_factories.get_session() as session:
        yield session
