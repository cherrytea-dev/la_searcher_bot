from unittest.mock import patch

import pytest

import identify_updates_of_topics._utils.forum
from _dependencies.commons import sqlalchemy_get_pool
from identify_updates_of_topics._utils import folder_updater
from identify_updates_of_topics._utils.database import DBClient
from title_recognize.main import recognize_title


@pytest.fixture(autouse=True)
def common_patches():
    def fake_recognize_title_via_api(title: str, status_only: bool):
        reco_data = recognize_title(title, False)
        return {'status': 'ok', 'recognition': reco_data}

    with (
        patch.object(folder_updater, 'recognize_title_via_api', fake_recognize_title_via_api),
    ):
        yield


@pytest.fixture()
def mock_http_get():
    with (
        patch.object(identify_updates_of_topics._utils.forum.get_requests_session(), 'get') as mock_http,
    ):
        yield mock_http


@pytest.fixture(scope='session')
def db_client(connection_pool) -> DBClient:
    return DBClient(connection_pool)
