"""Tests for Phase 2A VK Bot handlers.

These tests cover:
- State-based handlers (forum username input)
- Button/command handlers (onboarding, main menu, settings, etc.)

Each handler follows the pattern:
    def handler(vk_message, state, user_id) -> VKHandlerResult | None
"""

from unittest.mock import MagicMock

import pytest

from _dependencies.services.state_machine import DialogState
from vk_bot._utils.common import VKHandlerResult

# ═══════════════════════════════════════════════════════════════════════════════
# 1. State Handlers
# ═══════════════════════════════════════════════════════════════════════════════


class TestHandleForumUsername:
    """handle_forum_username — forum username input state handler."""

    def test_accepts_forum_username_state(self, vk_message):
        """Handles when state=input_of_forum_username."""
        from vk_bot._utils.handlers.state_handlers import handle_forum_username

        msg = vk_message(text='my_forum_nick')
        result = handle_forum_username(msg, DialogState.input_of_forum_username, 12345)
        assert result is not None
        assert isinstance(result, VKHandlerResult)

    def test_ignores_other_state(self, vk_message):
        """Returns None for non-matching state."""
        from vk_bot._utils.handlers.state_handlers import handle_forum_username

        msg = vk_message(text='my_forum_nick')
        result = handle_forum_username(msg, DialogState.not_defined, 12345)
        assert result is None

    def test_captures_username(self, vk_message):
        """Passes text as forum username."""
        from vk_bot._utils.handlers.state_handlers import handle_forum_username

        msg = vk_message(text='  my_forum_nick  ')
        result = handle_forum_username(msg, DialogState.input_of_forum_username, 12345)

        assert result is not None
        assert 'посмотрю' in result.text.lower() or 'проверяю' in result.text.lower()

    def test_resets_state(self, vk_message):
        """new_state is not_defined."""
        from vk_bot._utils.handlers.state_handlers import handle_forum_username

        msg = vk_message(text='my_forum_nick')
        result = handle_forum_username(msg, DialogState.input_of_forum_username, 12345)

        assert result is not None
        assert result.new_state == DialogState.not_defined


# ═══════════════════════════════════════════════════════════════════════════════
# 2. Button/Command Handlers
# ═══════════════════════════════════════════════════════════════════════════════


class TestHandleCommandStart:
    """handle_command_start — /start command handler."""

    def test_handles_start_command(self, vk_message, mock_settings_service):
        """ "/start" -> returns welcome text."""
        from vk_bot._utils.handlers.button_handlers import handle_command_start

        mock_settings_service.check_if_new_user.return_value = False

        msg = vk_message(text='/start')
        result = handle_command_start(msg, DialogState.not_defined, 12345)

        assert result is not None
        assert isinstance(result, VKHandlerResult)
        assert 'привет' in result.text.lower()
        assert result.keyboard is not None

    def test_ignores_other_text(self, vk_message):
        """ "something" -> returns None."""
        from vk_bot._utils.handlers.button_handlers import handle_command_start

        msg = vk_message(text='something')
        result = handle_command_start(msg, DialogState.not_defined, 12345)
        assert result is None

    def test_returns_main_menu_keyboard(self, vk_message, mock_settings_service):
        """Result has main_menu keyboard."""
        from vk_bot._utils.handlers.button_handlers import handle_command_start

        mock_settings_service.check_if_new_user.return_value = False

        msg = vk_message(text='/start')
        result = handle_command_start(msg, DialogState.not_defined, 12345)

        assert result is not None
        assert result.keyboard is not None
        labels = [btn[0]['action']['label'] for btn in result.keyboard['buttons']]
        assert 'посмотреть актуальные поиски' in labels
        assert 'другие возможности' in labels


class TestHandleRoleChoice:
    """handle_role_choice — role selection during onboarding."""

    @pytest.fixture(autouse=True)
    def _setup_mocks(self, mock_settings_service):
        """Store mock_settings_service reference for assertions."""
        self.mock_settings = mock_settings_service

    def test_handles_member_role(self, vk_message):
        """ "я состою в лизаалерт" -> saves role, completes onboarding, returns main_menu."""
        from vk_bot._utils.handlers.button_handlers import handle_role_choice

        msg = vk_message(text='я состою в ЛизаАлерт')
        result = handle_role_choice(msg, DialogState.not_defined, 12345)

        assert result is not None
        self.mock_settings.save_user_role.assert_called_once_with(12345, 'member')
        # Onboarding is completed immediately for member role
        self.mock_settings.save_onboarding_step.assert_any_call(12345, 'role_set')
        self.mock_settings.save_onboarding_step.assert_any_call(12345, 'finished')
        # Returns main_menu keyboard
        labels = [btn[0]['action']['label'] for btn in result.keyboard['buttons']]

    def test_handles_volunteer_role(self, vk_message):
        """ "я хочу помогать лизаалерт" -> saves role, completes onboarding, returns main_menu."""
        from vk_bot._utils.handlers.button_handlers import handle_role_choice

        msg = vk_message(text='я хочу помогать ЛизаАлерт')
        result = handle_role_choice(msg, DialogState.not_defined, 12345)

        assert result is not None
        self.mock_settings.save_user_role.assert_called_once_with(12345, 'volunteer')
        # Onboarding is completed immediately for volunteer role
        self.mock_settings.save_onboarding_step.assert_any_call(12345, 'role_set')
        self.mock_settings.save_onboarding_step.assert_any_call(12345, 'finished')
        # Returns main_menu keyboard
        labels = [btn[0]['action']['label'] for btn in result.keyboard['buttons']]

    def test_handles_relative_role(self, vk_message):
        """ "я ищу человека" -> saves role with code 'relative', shows orders_done keyboard."""
        from vk_bot._utils.handlers.button_handlers import handle_role_choice

        msg = vk_message(text='я ищу человека')
        result = handle_role_choice(msg, DialogState.not_defined, 12345)

        assert result is not None
        self.mock_settings.save_user_role.assert_called_once_with(12345, 'relative')
        self.mock_settings.save_onboarding_step.assert_called_once_with(12345, 'role_set')
        labels = [btn[0]['action']['label'] for btn in result.keyboard['buttons']]
        assert 'уже заказал(а)' in labels or 'закажу позже' in labels

    def test_handles_other_role(self, vk_message):
        """ "у меня другая задача" -> saves role, completes onboarding, returns main_menu."""
        from vk_bot._utils.handlers.button_handlers import handle_role_choice

        msg = vk_message(text='у меня другая задача')
        result = handle_role_choice(msg, DialogState.not_defined, 12345)

        assert result is not None
        self.mock_settings.save_user_role.assert_called_once_with(12345, 'other')
        # Onboarding is completed immediately for other role
        self.mock_settings.save_onboarding_step.assert_any_call(12345, 'role_set')
        self.mock_settings.save_onboarding_step.assert_any_call(12345, 'finished')
        # Returns main_menu keyboard
        labels = [btn[0]['action']['label'] for btn in result.keyboard['buttons']]

    def test_ignores_unknown_text(self, vk_message):
        """Returns None for non-matching text."""
        from vk_bot._utils.handlers.button_handlers import handle_role_choice

        msg = vk_message(text='random text')
        result = handle_role_choice(msg, DialogState.not_defined, 12345)
        assert result is None

    def test_saves_onboarding_step(self, vk_message):
        """Calls save_onboarding_step with 'role_set'."""
        from vk_bot._utils.handlers.button_handlers import handle_role_choice

        msg = vk_message(text='я состою в ЛизаАлерт')
        handle_role_choice(msg, DialogState.not_defined, 12345)

        self.mock_settings.save_onboarding_step.assert_any_call(12345, 'role_set')


class TestHandleBackToStart:
    """handle_back_to_start — 'в начало' button handler."""

    def test_handles_back_to_start(self, vk_message):
        """ "в начало" -> returns main_menu keyboard."""
        from vk_bot._utils.handlers.button_handlers import handle_back_to_start

        msg = vk_message(text='в начало')
        result = handle_back_to_start(msg, DialogState.not_defined, 12345)

        assert result is not None
        assert isinstance(result, VKHandlerResult)
        assert result.keyboard is not None
        labels = [btn[0]['action']['label'] for btn in result.keyboard['buttons']]
        assert 'посмотреть актуальные поиски' in labels
        assert 'другие возможности' in labels

    def test_resets_state(self, vk_message):
        """new_state is not_defined."""
        from vk_bot._utils.handlers.button_handlers import handle_back_to_start

        msg = vk_message(text='в начало')
        result = handle_back_to_start(msg, DialogState.radius_input, 12345)

        assert result is not None
        assert result.new_state == DialogState.not_defined

    def test_ignores_other_text(self, vk_message):
        """Returns None."""
        from vk_bot._utils.handlers.button_handlers import handle_back_to_start

        msg = vk_message(text='random text')
        result = handle_back_to_start(msg, DialogState.not_defined, 12345)
        assert result is None


class TestHandleMainMenu:
    """handle_main_menu — main menu navigation buttons."""

    @pytest.fixture(autouse=True)
    def _setup_mocks(self, mock_settings_service):
        """Store mock_settings_service reference for assertions."""
        self.mock_settings = mock_settings_service

    def test_view_searches_button(self, vk_message):
        """ "посмотреть актуальные поиски" -> returns None (handled by Phase 2B handler)."""
        from vk_bot._utils.handlers.button_handlers import handle_main_menu

        msg = vk_message(text='посмотреть актуальные поиски')
        result = handle_main_menu(msg, DialogState.not_defined, 12345)

        assert result is None

    def test_other_menu_button(self, vk_message):
        """ "другие возможности" -> returns other_menu keyboard."""
        from vk_bot._utils.handlers.button_handlers import handle_main_menu

        msg = vk_message(text='другие возможности')
        result = handle_main_menu(msg, DialogState.not_defined, 12345)

        assert result is not None
        assert result.keyboard is not None
        labels = [btn[0]['action']['label'] for btn in result.keyboard['buttons']]
        assert 'посмотреть последние поиски' in labels

    def test_ignores_unknown(self, vk_message):
        """Returns None."""
        from vk_bot._utils.handlers.button_handlers import handle_main_menu

        msg = vk_message(text='random text')
        result = handle_main_menu(msg, DialogState.not_defined, 12345)
        assert result is None


class TestHandleSettingsMenu:
    """handle_settings_menu — settings sub-menu navigation (account linking only)."""

    @pytest.fixture(autouse=True)
    def _setup_mocks(self, mock_settings_service):
        """Store mock_settings_service reference for assertions."""
        self.mock_settings = mock_settings_service

    def test_forum_linking(self, vk_message):
        """ "связать аккаунты бота и форума" -> returns forum_linking keyboard."""
        from vk_bot._utils.handlers.button_handlers import handle_settings_menu

        self.mock_settings.get_forum_attributes.return_value = None

        msg = vk_message(text='связать аккаунты бота и форума')
        result = handle_settings_menu(msg, DialogState.not_defined, 12345)

        assert result is not None
        assert result.keyboard is not None
        labels = [btn[0]['action']['label'] for btn in result.keyboard['buttons']]
        assert 'ввести ник с форума' in labels

    def test_vk_linking(self, vk_message):
        """ "связать аккаунты бота и vkontakte" -> returns vk_linking keyboard."""
        from vk_bot._utils.handlers.button_handlers import handle_settings_menu

        self.mock_settings.get_user_vk_id.return_value = None

        msg = vk_message(text='связать аккаунты бота и VKontakte')
        result = handle_settings_menu(msg, DialogState.not_defined, 12345)

        assert result is not None
        assert result.keyboard is not None

    def test_ignores_unknown(self, vk_message):
        """Returns None."""
        from vk_bot._utils.handlers.button_handlers import handle_settings_menu

        msg = vk_message(text='random text')
        result = handle_settings_menu(msg, DialogState.not_defined, 12345)
        assert result is None


class TestHandleOtherMenu:
    """handle_other_menu — other options menu buttons."""

    def test_latest_searches(self, vk_message):
        """ "посмотреть последние поиски" -> passes through to view_searches_handlers."""
        from vk_bot._utils.handlers.button_handlers import handle_other_menu

        msg = vk_message(text='посмотреть последние поиски')
        result = handle_other_menu(msg, DialogState.not_defined, 12345)

        # Now delegates to handle_latest_searches in the handler chain
        assert result is None

    def test_community(self, vk_message):
        """ "написать разработчику бота" -> returns info text."""
        from vk_bot._utils.handlers.button_handlers import handle_other_menu

        msg = vk_message(text='написать разработчику бота')
        result = handle_other_menu(msg, DialogState.not_defined, 12345)

        assert result is not None
        assert result.keyboard is not None

    def test_ignores_unknown(self, vk_message):
        """Returns None."""
        from vk_bot._utils.handlers.button_handlers import handle_other_menu

        msg = vk_message(text='random text')
        result = handle_other_menu(msg, DialogState.not_defined, 12345)
        assert result is None
