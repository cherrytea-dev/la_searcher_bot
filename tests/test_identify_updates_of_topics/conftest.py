from unittest.mock import Mock, patch

import pytest

import identify_updates_of_topics._utils.external_api
import identify_updates_of_topics._utils.forum
from _dependencies.commons import sqlalchemy_get_pool
from identify_updates_of_topics._utils import folder_updater
from identify_updates_of_topics._utils.database import DBClient
from title_recognize.main import recognize_title


@pytest.fixture(autouse=True)
def common_patches():
    def fake_api_call(function: str, data: dict):
        reco_data = recognize_title(data['title'], None)
        return {'status': 'ok', 'recognition': reco_data}

    with (
        patch.object(folder_updater, 'make_api_call', fake_api_call),
    ):
        yield


@pytest.fixture()
def mock_http_get():
    with (
        patch.object(identify_updates_of_topics._utils.forum.get_requests_session(), 'get') as mock_http,
    ):
        yield mock_http


@pytest.fixture(scope='session')
def db(patch_app_config):
    return sqlalchemy_get_pool(10, 10)


@pytest.fixture(scope='session')
def db_client(db) -> DBClient:
    return DBClient(db)


@pytest.fixture(autouse=True)
def patch_google_cloud_storage():
    with patch('google.cloud.storage.Client'):
        yield
