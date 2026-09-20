from unittest.mock import patch
from uuid import uuid4

import pytest
from sqlalchemy import text

import identify_updates_of_topics._utils.forum
from _dependencies.forum import recognition_cache
from identify_updates_of_topics._utils import search_parser
from identify_updates_of_topics._utils.database import DBClient
from title_recognize.main import recognize_title


@pytest.fixture(autouse=True)
def common_patches():
    def fake_recognize_title_via_api(title: str, status_only: bool):
        reco_data = recognize_title(title, False)
        return {'status': 'ok', 'recognition': reco_data}

    with (
        patch.object(search_parser, 'recognize_title_via_api', fake_recognize_title_via_api),
    ):
        yield


@pytest.fixture(autouse=True)
def isolated_recognition_cache(monkeypatch, connection_pool):
    """Give every test its own recognition cache namespace.

    The cache lives in the shared test database (`key_value_storage`), so without this a title
    recognized in one test would be reused in another one — and a test asserting that the title
    went to the API would fail depending on the order of the run.
    """

    prefix = f'test-reco-{uuid4().hex[:12]}'
    monkeypatch.setattr(recognition_cache, 'CACHE_KEY_PREFIX', prefix)

    yield

    with connection_pool.begin() as conn:
        conn.execute(text('DELETE FROM key_value_storage WHERE key LIKE :pattern'), {'pattern': f'{prefix}-%'})


@pytest.fixture()
def mock_http_get():
    with (
        patch.object(identify_updates_of_topics._utils.forum.get_requests_session(), 'get') as mock_http,
    ):
        yield mock_http


@pytest.fixture(scope='session')
def db_client(connection_pool) -> DBClient:
    return DBClient(connection_pool)
