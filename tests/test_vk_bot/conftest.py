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


@pytest.fixture
def vk_message():
    """Helper to create VKMessage instances."""
    from src.vk_bot._utils.common import VKMessage

    def _create(
        text: str = '/start',
        user_id: int = 12345,
        peer_id: int = 12345,
        message_id: int = 42,
        payload: str | None = None,
        event_id: str | None = None,
    ) -> VKMessage:
        return VKMessage(
            text=text,
            user_id=user_id,
            peer_id=peer_id,
            message_id=message_id,
            payload=payload,
            event_id=event_id,
        )

    return _create


@pytest.fixture
def mock_settings_service(monkeypatch):
    """Mock UserSettingsService methods for handler tests.

    Patches get_user_settings_service() to return a MagicMock,
    so handlers can call db().settings.xxx() without a real DB.
    """
    from _dependencies.services.user_settings_service import get_user_settings_service

    mock_settings = MagicMock()
    # Default return values
    mock_settings.check_if_new_user.return_value = False
    mock_settings.get_settings_summary.return_value = MagicMock(
        pref_notif_type=False,
        pref_region_old=False,
        pref_region=False,
        pref_coords=False,
        pref_radius=False,
        pref_age=False,
        pref_forum=False,
    )

    monkeypatch.setattr(
        'src.vk_bot._utils.database.get_user_settings_service',
        lambda: mock_settings,
    )
    return mock_settings


@pytest.fixture
def vk_handler_result():
    """Helper to check VKHandlerResult fields."""
    from src.vk_bot._utils.common import VKHandlerResult

    return VKHandlerResult
