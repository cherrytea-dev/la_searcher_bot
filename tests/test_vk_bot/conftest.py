"""Fixtures for VK Bot tests."""

from unittest.mock import MagicMock, patch

import pytest
from fakes import FakeVKMessageSender

from _dependencies.bot.vk_api_client import VKApi
from _dependencies.common.commons import AppConfig
from src.vk_bot._utils.common import VKHandlerResult, VKMessage
from tests.factories import db_factories, db_models


@pytest.fixture
def mock_vk_http():
    """Mock httpx.Client.post for VKApi tests.

    The global conftest patches httpx.Client entirely, so we need
    to provide a mock post method that tests can configure.
    """
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
def mock_vk_api():
    """Create a mock VKApi client for VKMessageSender tests.

    VKMessageSender now accepts an optional `api` parameter,
    so tests can inject a mock directly: VKMessageSender(api=mock_vk_api).
    """
    api = MagicMock()
    api.send.return_value = {'response': {'message_id': 42}}
    api.edit_message.return_value = {'response': {}}
    api.delete_message.return_value = {'response': {}}
    api.send_message_event_answer.return_value = {'response': {}}
    yield api


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
    """Mock db() methods for handler tests.

    Patches db() to return a MagicMock in the database module
    AND in all handler modules that import it at module level,
    so handlers can call db().xxx() without a real DB.
    """

    mock_db = MagicMock()
    # Default return values
    mock_db.check_if_new_user.return_value = False
    mock_db.get_settings_summary.return_value = MagicMock(
        pref_notif_type=False,
        pref_region_old=False,
        pref_region=False,
        pref_coords=False,
        pref_radius=False,
        pref_age=False,
        pref_forum=False,
    )

    # Patch in the source module
    monkeypatch.setattr(
        'src.vk_bot._utils.database.db',
        lambda: mock_db,
    )
    # Also patch in all handler modules that import db at module level
    handler_modules = [
        'src.vk_bot._utils.handlers.onboarding_handlers',
        'src.vk_bot._utils.handlers.region_select_handlers',
        'src.vk_bot._utils.handlers.settings_handlers',
        'src.vk_bot._utils.handlers.state_handlers',
        'src.vk_bot._utils.handlers.view_searches_handlers',
    ]
    for mod_name in handler_modules:
        monkeypatch.setattr(f'{mod_name}.db', lambda: mock_db)
    return mock_db


@pytest.fixture
def vk_handler_result():
    """Helper to check VKHandlerResult fields."""

    return VKHandlerResult


# ═══════════════════════════════════════════════════════════════════════════════
# Dispatcher test fixtures — reduce repeated `patch()` calls in test_phase1.py
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.fixture
def fake_vk_sender():
    """Replace ``vk_sender()`` in all modules with a ``FakeVKMessageSender``.

    Uses a real ``FakeVKMessageSender`` instance instead of ``MagicMock``,
    so tests can inspect recorded calls via typed dataclasses::

        fake = fake_vk_sender  # the fixture returns the FakeVKMessageSender
        assert len(fake.sent_messages) == 1
        assert fake.sent_messages[0].text == 'expected text'
        assert fake.last_callback is not None
        fake.assert_no_calls()

    Only ``event_dispatcher`` still imports ``vk_sender`` directly (all other
    modules now receive ``VKMessageSender`` via dependency injection).

    All patches use the SAME ``FakeVKMessageSender`` instance so that tests
    can inspect calls regardless of which module's ``vk_sender`` was called.
    """
    fake = FakeVKMessageSender()
    with patch('vk_bot._utils.event_dispatcher.vk_sender', lambda: fake):
        yield fake


@pytest.fixture
def mock_vk_sender():
    """Patch vk_sender() in all modules that import it directly.

    Provides a pre-configured mock with default return values for
    send_message and send_callback_answer. Tests can override by
    accessing the returned mock directly.

    Only ``event_dispatcher`` still imports ``vk_sender`` directly (all other
    modules now receive ``VKMessageSender`` via dependency injection).

    .. deprecated::
        Use :func:`fake_vk_sender` instead — it provides typed dataclass
        records and convenience assertion helpers.
    """
    sender_mock = MagicMock()
    sender_mock.return_value.send_message.return_value = 1
    sender_mock.return_value.send_callback_answer.return_value = True
    with patch('vk_bot._utils.event_dispatcher.vk_sender', sender_mock):
        yield sender_mock


@pytest.fixture
def mock_dispatcher_db():
    """Patch db() in all modules that import it directly.

    Provides a pre-configured mock with resolve_user_id returning 42.
    Tests can override by accessing mock_db().xxx.return_value = ...

    Since account_linking, region_select_handlers, message_processing,
    and result_processing all do ``from .database import db``
    (creating local references), we must patch each module's namespace
    individually.

    All patches use the SAME MagicMock instance so that tests
    can check ``mock_dispatcher_db().xxx`` regardless of which module's
    ``db`` was actually called.
    """
    db_mock = MagicMock()
    db_mock().resolve_user_id.return_value = 42
    with (
        patch('vk_bot._utils.account_linking.db', db_mock),
        patch('vk_bot._utils.handlers.region_select_handlers.db', db_mock),
        patch('vk_bot._utils.message_processing.db', db_mock),
        patch('vk_bot._utils.result_processing.db', db_mock),
    ):
        yield db_mock


@pytest.fixture
def mock_app_config():
    """Patch get_app_config() in modules that import it directly.

    Provides a pre-configured AppConfig with test values for
    vk_group_id, vk_confirmation_code, and bot_api_token__prod.

    Patches account_linking and event_dispatcher since both import
    get_app_config from _dependencies.common.commons directly.
    (dispatcher.py is now a re-export module and no longer imports it.)
    """
    config = AppConfig(
        postgres_user='test',
        postgres_password='test',
        postgres_db='test',
        postgres_host='localhost',
        vk_group_id=237036024,
        vk_confirmation_code='test_code',
        bot_api_token__prod='test_secret',
    )
    with (
        patch('vk_bot._utils.account_linking.get_app_config', return_value=config),
        patch('vk_bot._utils.event_dispatcher.get_app_config', return_value=config),
    ):
        yield config


@pytest.fixture
def dispatcher_mocks():
    """Patch all dependencies for inline pagination tests.

    Provides a dict with pre-configured mocks:
    - db: mock_db (resolve_user_id returns 42)
    - sender: FakeVKMessageSender instance (inject via ``sender=fake_sender``)
    - folders: _get_folders_for_district
    - selected: _get_selected_region_names
    - keyboard: VKKeyboardPresets (paginated_regions_inline, fed_districts, settings_menu)

    Tests should inject the sender via DI::

        handle_inline_pagination(msg, payload, sender=fake_sender)
    """
    fake_sender = FakeVKMessageSender()
    with (
        patch('vk_bot._utils.handlers.region_select_handlers.db') as mock_db,
        patch('vk_bot._utils.handlers.region_select_handlers._get_folders_for_district') as mock_get_folders,
        patch('vk_bot._utils.handlers.region_select_handlers._get_selected_region_names') as mock_get_selected,
        patch('vk_bot._utils.handlers.region_select_handlers.VKKeyboardPresets') as mock_keyboard,
    ):
        mock_db().resolve_user_id.return_value = 42
        mock_keyboard.paginated_regions_inline.return_value = {'inline': True, 'buttons': []}
        mock_keyboard.fed_districts.return_value = {'inline': True, 'buttons': []}
        mock_keyboard.settings_menu.return_value = {'buttons': []}

        yield {
            'db': mock_db,
            'sender': fake_sender,
            'folders': mock_get_folders,
            'selected': mock_get_selected,
            'keyboard': mock_keyboard,
        }
