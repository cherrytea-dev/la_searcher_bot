"""Fixtures for VK Bot tests."""

from unittest.mock import MagicMock

import pytest

from tests.factories import db_factories, db_models


@pytest.fixture
def mock_vk_http():
    """Mock httpx.Client.post for VKApi tests.

    The global conftest patches httpx.Client entirely, so we need
    to provide a mock post method that tests can configure.
    """
    from _dependencies.vk_api_client import VKApi

    # Create a mock for the httpx.Client instance
    mock_client = MagicMock()
    mock_post = MagicMock()
    mock_client.post = mock_post

    # Patch the _session attribute on VKApi instances
    with pytest.MonkeyPatch.context() as mp:
        original_init = VKApi.__init__

        def patched_init(self, token: str):
            original_init(self, token)
            self._session = mock_client

        mp.setattr(VKApi, '__init__', patched_init)
        yield mock_post


@pytest.fixture
def user_model() -> db_models.User:
    """Create a user in the database."""
    return db_factories.UserFactory.create_sync()


@pytest.fixture
def user_id(user_model: db_models.User) -> int:
    """Return the user_id of the created user."""
    return user_model.user_id
