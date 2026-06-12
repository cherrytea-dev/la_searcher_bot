"""Tests for Phase 2A VK Bot handlers.

These tests cover:
- State-based handlers (radius input, coords input, forum username input)
- Button/command handlers (onboarding, main menu, settings, etc.)
- Region selection handlers (federal district select, region toggle)

Each handler follows the pattern:
    def handler(vk_message, state, user_id) -> VKHandlerResult | None
"""

from unittest.mock import MagicMock

import pytest

from _dependencies.services.state_machine import DialogState
from src.vk_bot._utils.common import VKHandlerResult


# ═══════════════════════════════════════════════════════════════════════════════
# 1. State Handlers
# ═══════════════════════════════════════════════════════════════════════════════


class TestHandleRadiusValue:
    """handle_radius_value — radius input state handler."""

    def test_accepts_radius_input_state(self, vk_message):
        """Handler handles when state=radius_input."""
        from src.vk_bot._utils.handlers.state_handlers import handle_radius_value

        msg = vk_message(text='50')
        result = handle_radius_value(msg, DialogState.radius_input, 12345)
        assert result is not None
        assert isinstance(result, VKHandlerResult)

    def test_ignores_other_state(self, vk_message):
        """Returns None for non-matching state."""
        from src.vk_bot._utils.handlers.state_handlers import handle_radius_value

        msg = vk_message(text='50')
        result = handle_radius_value(msg, DialogState.not_defined, 12345)
        assert result is None

    def test_parses_numeric_input(self, vk_message, mock_settings_service):
        """'50' -> saves radius, returns success text."""
        from src.vk_bot._utils.handlers.state_handlers import handle_radius_value

        msg = vk_message(text='50')
        result = handle_radius_value(msg, DialogState.radius_input, 12345)

        assert result is not None
        mock_settings_service.save_radius.assert_called_once_with(12345, 50)
        assert '50' in result.text or 'Сохранили' in result.text
        assert result.new_state == DialogState.not_defined

    def test_parses_number_in_text(self, vk_message, mock_settings_service):
        """ "хочу радиус 100 км" -> saves 100."""
        from src.vk_bot._utils.handlers.state_handlers import handle_radius_value

        msg = vk_message(text='хочу радиус 100 км')
        result = handle_radius_value(msg, DialogState.radius_input, 12345)

        assert result is not None
        mock_settings_service.save_radius.assert_called_once_with(12345, 100)

    def test_rejects_non_numeric(self, vk_message, mock_settings_service):
        """ "привет" -> returns parse error text."""
        from src.vk_bot._utils.handlers.state_handlers import handle_radius_value

        msg = vk_message(text='привет')
        result = handle_radius_value(msg, DialogState.radius_input, 12345)

        assert result is not None
        assert 'цифр' in result.text or 'Не могу' in result.text
        mock_settings_service.save_radius.assert_not_called()

    def test_saves_radius_via_settings(self, vk_message, mock_settings_service):
        """Verifies db().settings.save_radius is called."""
        from src.vk_bot._utils.handlers.state_handlers import handle_radius_value

        msg = vk_message(text='75')
        handle_radius_value(msg, DialogState.radius_input, 12345)

        mock_settings_service.save_radius.assert_called_once_with(12345, 75)

    def test_resets_state_to_not_defined(self, vk_message, mock_settings_service):
        """new_state is not_defined after save."""
        from src.vk_bot._utils.handlers.state_handlers import handle_radius_value

        msg = vk_message(text='50')
        result = handle_radius_value(msg, DialogState.radius_input, 12345)

        assert result is not None
        assert result.new_state == DialogState.not_defined


class TestHandleCoordsText:
    """handle_coords_text — manual coordinate input state handler."""

    def test_accepts_coords_input_state(self, vk_message):
        """Handles when state=input_of_coords_man."""
        from src.vk_bot._utils.handlers.state_handlers import handle_coords_text

        msg = vk_message(text='55.7558, 37.6173')
        result = handle_coords_text(msg, DialogState.input_of_coords_man, 12345)
        assert result is not None
        assert isinstance(result, VKHandlerResult)

    def test_ignores_other_state(self, vk_message):
        """Returns None for non-matching state."""
        from src.vk_bot._utils.handlers.state_handlers import handle_coords_text

        msg = vk_message(text='55.7558, 37.6173')
        result = handle_coords_text(msg, DialogState.not_defined, 12345)
        assert result is None

    def test_parses_valid_coords(self, vk_message, mock_settings_service):
        """ "55.7558, 37.6173" -> saves."""
        from src.vk_bot._utils.handlers.state_handlers import handle_coords_text

        msg = vk_message(text='55.7558, 37.6173')
        result = handle_coords_text(msg, DialogState.input_of_coords_man, 12345)

        assert result is not None
        mock_settings_service.save_coordinates.assert_called_once_with(12345, 55.7558, 37.6173)
        assert 'сохранены' in result.text.lower()

    def test_parses_coords_with_space_delimiter(self, vk_message, mock_settings_service):
        """ "55.7558 37.6173" -> saves."""
        from src.vk_bot._utils.handlers.state_handlers import handle_coords_text

        msg = vk_message(text='55.7558 37.6173')
        result = handle_coords_text(msg, DialogState.input_of_coords_man, 12345)

        assert result is not None
        mock_settings_service.save_coordinates.assert_called_once_with(12345, 55.7558, 37.6173)

    def test_rejects_invalid_format(self, vk_message, mock_settings_service):
        """ "abc def" -> parse error."""
        from src.vk_bot._utils.handlers.state_handlers import handle_coords_text

        msg = vk_message(text='abc def')
        result = handle_coords_text(msg, DialogState.input_of_coords_man, 12345)

        assert result is not None
        assert 'не распознаны' in result.text or 'Координаты' in result.text
        mock_settings_service.save_coordinates.assert_not_called()

    def test_resets_state_after_save(self, vk_message, mock_settings_service):
        """new_state is not_defined."""
        from src.vk_bot._utils.handlers.state_handlers import handle_coords_text

        msg = vk_message(text='55.7558, 37.6173')
        result = handle_coords_text(msg, DialogState.input_of_coords_man, 12345)

        assert result is not None
        assert result.new_state == DialogState.not_defined


class TestHandleForumUsername:
    """handle_forum_username — forum username input state handler."""

    def test_accepts_forum_username_state(self, vk_message):
        """Handles when state=input_of_forum_username."""
        from src.vk_bot._utils.handlers.state_handlers import handle_forum_username

        msg = vk_message(text='my_forum_nick')
        result = handle_forum_username(msg, DialogState.input_of_forum_username, 12345)
        assert result is not None
        assert isinstance(result, VKHandlerResult)

    def test_ignores_other_state(self, vk_message):
        """Returns None for non-matching state."""
        from src.vk_bot._utils.handlers.state_handlers import handle_forum_username

        msg = vk_message(text='my_forum_nick')
        result = handle_forum_username(msg, DialogState.not_defined, 12345)
        assert result is None

    def test_captures_username(self, vk_message):
        """Passes text as forum username."""
        from src.vk_bot._utils.handlers.state_handlers import handle_forum_username

        msg = vk_message(text='  my_forum_nick  ')
        result = handle_forum_username(msg, DialogState.input_of_forum_username, 12345)

        assert result is not None
        assert 'посмотрю' in result.text.lower() or 'проверяю' in result.text.lower()

    def test_resets_state(self, vk_message):
        """new_state is not_defined."""
        from src.vk_bot._utils.handlers.state_handlers import handle_forum_username

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
        from src.vk_bot._utils.handlers.button_handlers import handle_command_start

        mock_settings_service.check_if_new_user.return_value = False

        msg = vk_message(text='/start')
        result = handle_command_start(msg, DialogState.not_defined, 12345)

        assert result is not None
        assert isinstance(result, VKHandlerResult)
        assert 'привет' in result.text.lower()
        assert result.keyboard is not None

    def test_ignores_other_text(self, vk_message):
        """ "something" -> returns None."""
        from src.vk_bot._utils.handlers.button_handlers import handle_command_start

        msg = vk_message(text='something')
        result = handle_command_start(msg, DialogState.not_defined, 12345)
        assert result is None

    def test_returns_main_menu_keyboard(self, vk_message, mock_settings_service):
        """Result has main_menu keyboard."""
        from src.vk_bot._utils.handlers.button_handlers import handle_command_start

        mock_settings_service.check_if_new_user.return_value = False

        msg = vk_message(text='/start')
        result = handle_command_start(msg, DialogState.not_defined, 12345)

        assert result is not None
        assert result.keyboard is not None
        labels = [btn[0]['action']['label'] for btn in result.keyboard['buttons']]
        assert 'настроить бот' in labels
        assert 'посмотреть актуальные поиски' in labels


class TestHandleRoleChoice:
    """handle_role_choice — role selection during onboarding."""

    @pytest.fixture(autouse=True)
    def _setup_mocks(self, mock_settings_service):
        """Store mock_settings_service reference for assertions."""
        self.mock_settings = mock_settings_service

    def test_handles_member_role(self, vk_message):
        """ "я состою в лизаалерт" -> saves role with code 'member'."""
        from src.vk_bot._utils.handlers.button_handlers import handle_role_choice

        msg = vk_message(text='я состою в ЛизаАлерт')
        result = handle_role_choice(msg, DialogState.not_defined, 12345)

        assert result is not None
        self.mock_settings.save_user_role.assert_called_once_with(12345, 'member')
        self.mock_settings.save_onboarding_step.assert_called_once_with(12345, 'role_set')

    def test_handles_volunteer_role(self, vk_message):
        """ "я хочу помогать лизаалерт" -> saves role with code 'volunteer'."""
        from src.vk_bot._utils.handlers.button_handlers import handle_role_choice

        msg = vk_message(text='я хочу помогать ЛизаАлерт')
        result = handle_role_choice(msg, DialogState.not_defined, 12345)

        assert result is not None
        self.mock_settings.save_user_role.assert_called_once_with(12345, 'volunteer')
        self.mock_settings.save_onboarding_step.assert_called_once_with(12345, 'role_set')

    def test_handles_relative_role(self, vk_message):
        """ "я ищу человека" -> saves role with code 'relative', shows orders_done keyboard."""
        from src.vk_bot._utils.handlers.button_handlers import handle_role_choice

        msg = vk_message(text='я ищу человека')
        result = handle_role_choice(msg, DialogState.not_defined, 12345)

        assert result is not None
        self.mock_settings.save_user_role.assert_called_once_with(12345, 'relative')
        self.mock_settings.save_onboarding_step.assert_called_once_with(12345, 'role_set')
        labels = [btn[0]['action']['label'] for btn in result.keyboard['buttons']]
        assert 'уже заказал(а)' in labels or 'закажу позже' in labels

    def test_handles_other_role(self, vk_message):
        """ "у меня другая задача" -> saves role with code 'other'."""
        from src.vk_bot._utils.handlers.button_handlers import handle_role_choice

        msg = vk_message(text='у меня другая задача')
        result = handle_role_choice(msg, DialogState.not_defined, 12345)

        assert result is not None
        self.mock_settings.save_user_role.assert_called_once_with(12345, 'other')
        self.mock_settings.save_onboarding_step.assert_called_once_with(12345, 'role_set')

    def test_ignores_unknown_text(self, vk_message):
        """Returns None for non-matching text."""
        from src.vk_bot._utils.handlers.button_handlers import handle_role_choice

        msg = vk_message(text='random text')
        result = handle_role_choice(msg, DialogState.not_defined, 12345)
        assert result is None

    def test_saves_onboarding_step(self, vk_message):
        """Calls save_onboarding_step with 'role_set'."""
        from src.vk_bot._utils.handlers.button_handlers import handle_role_choice

        msg = vk_message(text='я состою в ЛизаАлерт')
        handle_role_choice(msg, DialogState.not_defined, 12345)

        self.mock_settings.save_onboarding_step.assert_called_once_with(12345, 'role_set')


class TestHandleIsMoscow:
    """handle_is_moscow — Moscow region confirmation during onboarding."""

    @pytest.fixture(autouse=True)
    def _setup_mocks(self, mock_settings_service):
        """Store mock_settings_service reference for assertions."""
        self.mock_settings = mock_settings_service

    def test_handles_yes(self, vk_message):
        """ "да, москва – мой регион" (em-dash) -> adds Moscow region, subscribes."""
        from src.vk_bot._utils.handlers.button_handlers import handle_is_moscow

        # Mock geo folders to include Moscow regions
        # _subscribe_moscow_regions matches 'москв' in name.lower() or 'мо:' in name.lower()
        self.mock_settings.get_geo_folders.return_value = [
            (1, 'Москва и МО'),  # 'москв' matches
            (2, 'МО: Московская обл.'),  # 'мо:' matches
            (3, 'Калужская область'),  # no match
        ]

        # Note: handler uses EN DASH (U+2013), not regular hyphen
        msg = vk_message(text='да, Москва – мой регион')
        result = handle_is_moscow(msg, DialogState.not_defined, 12345)

        assert result is not None
        self.mock_settings.save_onboarding_step.assert_called_once_with(12345, 'finished')
        # Verify Moscow region subscription was attempted
        self.mock_settings.add_region.assert_any_call(12345, 1)
        self.mock_settings.add_region.assert_any_call(12345, 2)
        assert 'отлично' in result.text.lower() or 'завершили' in result.text.lower()

    def test_handles_no(self, vk_message):
        """ "нет, я из другого региона" -> shows fed_districts keyboard."""
        from src.vk_bot._utils.handlers.button_handlers import handle_is_moscow

        msg = vk_message(text='нет, я из другого региона')
        result = handle_is_moscow(msg, DialogState.not_defined, 12345)

        assert result is not None
        assert result.keyboard is not None
        labels = [btn[0]['action']['label'] for btn in result.keyboard['buttons']]
        assert 'Центральный ФО' in labels

    def test_ignores_other(self, vk_message):
        """Returns None for non-matching text."""
        from src.vk_bot._utils.handlers.button_handlers import handle_is_moscow

        msg = vk_message(text='random text')
        result = handle_is_moscow(msg, DialogState.not_defined, 12345)
        assert result is None


class TestHandleBackToStart:
    """handle_back_to_start — 'в начало' button handler."""

    def test_handles_back_to_start(self, vk_message):
        """ "в начало" -> returns main_menu keyboard."""
        from src.vk_bot._utils.handlers.button_handlers import handle_back_to_start

        msg = vk_message(text='в начало')
        result = handle_back_to_start(msg, DialogState.not_defined, 12345)

        assert result is not None
        assert isinstance(result, VKHandlerResult)
        assert result.keyboard is not None
        labels = [btn[0]['action']['label'] for btn in result.keyboard['buttons']]
        assert 'настроить бот' in labels

    def test_resets_state(self, vk_message):
        """new_state is not_defined."""
        from src.vk_bot._utils.handlers.button_handlers import handle_back_to_start

        msg = vk_message(text='в начало')
        result = handle_back_to_start(msg, DialogState.radius_input, 12345)

        assert result is not None
        assert result.new_state == DialogState.not_defined

    def test_ignores_other_text(self, vk_message):
        """Returns None."""
        from src.vk_bot._utils.handlers.button_handlers import handle_back_to_start

        msg = vk_message(text='random text')
        result = handle_back_to_start(msg, DialogState.not_defined, 12345)
        assert result is None


class TestHandleMainMenu:
    """handle_main_menu — main menu navigation buttons."""

    @pytest.fixture(autouse=True)
    def _setup_mocks(self, mock_settings_service):
        """Store mock_settings_service reference for assertions."""
        self.mock_settings = mock_settings_service

    def test_settings_button(self, vk_message):
        """ "настроить бот" -> returns settings_menu keyboard."""
        from src.vk_bot._utils.handlers.button_handlers import handle_main_menu

        msg = vk_message(text='настроить бот')
        result = handle_main_menu(msg, DialogState.not_defined, 12345)

        assert result is not None
        assert result.keyboard is not None
        labels = [btn[0]['action']['label'] for btn in result.keyboard['buttons']]
        assert 'настроить виды уведомлений' in labels

    def test_view_searches_button(self, vk_message):
        """ "посмотреть актуальные поиски" -> returns None (handled by Phase 2B handler)."""
        from src.vk_bot._utils.handlers.button_handlers import handle_main_menu

        msg = vk_message(text='посмотреть актуальные поиски')
        result = handle_main_menu(msg, DialogState.not_defined, 12345)

        assert result is None

    def test_other_menu_button(self, vk_message):
        """ "другие возможности" -> returns other_menu keyboard."""
        from src.vk_bot._utils.handlers.button_handlers import handle_main_menu

        msg = vk_message(text='другие возможности')
        result = handle_main_menu(msg, DialogState.not_defined, 12345)

        assert result is not None
        assert result.keyboard is not None
        labels = [btn[0]['action']['label'] for btn in result.keyboard['buttons']]
        assert 'посмотреть последние поиски' in labels

    def test_ignores_unknown(self, vk_message):
        """Returns None."""
        from src.vk_bot._utils.handlers.button_handlers import handle_main_menu

        msg = vk_message(text='random text')
        result = handle_main_menu(msg, DialogState.not_defined, 12345)
        assert result is None


class TestHandleSettingsMenu:
    """handle_settings_menu — settings sub-menu navigation."""

    @pytest.fixture(autouse=True)
    def _setup_mocks(self, mock_settings_service):
        """Store mock_settings_service reference for assertions."""
        self.mock_settings = mock_settings_service

    def test_notification_settings(self, vk_message):
        """ "настроить виды уведомлений" -> returns notification_settings keyboard."""
        from src.vk_bot._utils.handlers.button_handlers import handle_settings_menu

        self.mock_settings.get_all_user_preferences.return_value = []

        msg = vk_message(text='настроить виды уведомлений')
        result = handle_settings_menu(msg, DialogState.not_defined, 12345)

        assert result is not None
        assert result.keyboard is not None
        labels = [btn[0]['action']['label'] for btn in result.keyboard['buttons']]
        assert 'включить: все уведомления' in labels

    def test_coordinates_menu(self, vk_message):
        """ "настроить "домашние координаты"" -> returns coords_menu keyboard."""
        from src.vk_bot._utils.handlers.button_handlers import handle_settings_menu

        self.mock_settings.get_coordinates.return_value = None

        msg = vk_message(text='настроить "домашние координаты"')
        result = handle_settings_menu(msg, DialogState.not_defined, 12345)

        assert result is not None
        assert result.keyboard is not None
        labels = [btn[0]['action']['label'] for btn in result.keyboard['buttons']]
        assert 'ввести "домашние координаты" вручную' in labels

    def test_radius_settings(self, vk_message):
        """ "настроить максимальный радиус" -> returns radius_settings keyboard."""
        from src.vk_bot._utils.handlers.button_handlers import handle_settings_menu

        self.mock_settings.get_radius.return_value = None

        msg = vk_message(text='настроить максимальный радиус')
        result = handle_settings_menu(msg, DialogState.not_defined, 12345)

        assert result is not None
        assert result.keyboard is not None

    def test_age_settings(self, vk_message):
        """ "настроить возрастные группы бвп" -> returns age_settings keyboard."""
        from src.vk_bot._utils.handlers.button_handlers import handle_settings_menu

        msg = vk_message(text='настроить возрастные группы БВП')
        result = handle_settings_menu(msg, DialogState.not_defined, 12345)

        assert result is not None
        assert result.keyboard is not None
        labels = [btn[0]['action']['label'] for btn in result.keyboard['buttons']]
        assert 'дети (0-10 лет)' in labels

    def test_topic_type_settings(self, vk_message):
        """ "настроить вид поисков" -> returns topic_type_settings keyboard."""
        from src.vk_bot._utils.handlers.button_handlers import handle_settings_menu

        msg = vk_message(text='настроить вид поисков')
        result = handle_settings_menu(msg, DialogState.not_defined, 12345)

        assert result is not None
        assert result.keyboard is not None
        labels = [btn[0]['action']['label'] for btn in result.keyboard['buttons']]
        assert 'поисковые работы' in labels

    def test_forum_linking(self, vk_message):
        """ "связать аккаунты бота и форума" -> returns forum_linking keyboard."""
        from src.vk_bot._utils.handlers.button_handlers import handle_settings_menu

        self.mock_settings.get_forum_attributes.return_value = None

        msg = vk_message(text='связать аккаунты бота и форума')
        result = handle_settings_menu(msg, DialogState.not_defined, 12345)

        assert result is not None
        assert result.keyboard is not None
        labels = [btn[0]['action']['label'] for btn in result.keyboard['buttons']]
        assert 'ввести ник с форума' in labels

    def test_vk_linking(self, vk_message):
        """ "связать аккаунты бота и vkontakte" -> returns vk_linking keyboard."""
        from src.vk_bot._utils.handlers.button_handlers import handle_settings_menu

        self.mock_settings.get_user_vk_id.return_value = None

        msg = vk_message(text='связать аккаунты бота и VKontakte')
        result = handle_settings_menu(msg, DialogState.not_defined, 12345)

        assert result is not None
        assert result.keyboard is not None

    def test_ignores_unknown(self, vk_message):
        """Returns None."""
        from src.vk_bot._utils.handlers.button_handlers import handle_settings_menu

        msg = vk_message(text='random text')
        result = handle_settings_menu(msg, DialogState.not_defined, 12345)
        assert result is None


class TestHandleNotificationToggle:
    """handle_notification_toggle — notification preference toggles."""

    @pytest.fixture(autouse=True)
    def _setup_mocks(self, mock_settings_service):
        """Store mock_settings_service reference for assertions."""
        self.mock_settings = mock_settings_service
        self.mock_settings.get_all_user_preferences.return_value = []

    def test_toggles_preference_on(self, vk_message):
        """Toggles a preference to enabled."""
        from src.vk_bot._utils.handlers.button_handlers import handle_notification_toggle

        msg = vk_message(text='включить: о новых поисках')
        result = handle_notification_toggle(msg, DialogState.not_defined, 12345)

        assert result is not None
        self.mock_settings.save_preference.assert_called_once_with(12345, 'new_searches')

    def test_toggles_preference_off(self, vk_message):
        """Toggles a preference to disabled."""
        from src.vk_bot._utils.handlers.button_handlers import handle_notification_toggle

        msg = vk_message(text='отключить: о новых поисках')
        result = handle_notification_toggle(msg, DialogState.not_defined, 12345)

        assert result is not None
        self.mock_settings.delete_preferences.assert_called_once_with(12345, ['new_searches'])

    def test_ignores_unknown_text(self, vk_message):
        """Returns None."""
        from src.vk_bot._utils.handlers.button_handlers import handle_notification_toggle

        msg = vk_message(text='random text')
        result = handle_notification_toggle(msg, DialogState.not_defined, 12345)
        assert result is None


class TestHandleCoordinatesAction:
    """handle_coordinates_action — coordinates sub-menu actions."""

    @pytest.fixture(autouse=True)
    def _setup_mocks(self, mock_settings_service):
        """Store mock_settings_service reference for assertions."""
        self.mock_settings = mock_settings_service

    def test_manual_input(self, vk_message):
        """ "ввести координаты" -> sets state to input_of_coords_man."""
        from src.vk_bot._utils.handlers.button_handlers import handle_coordinates_action

        msg = vk_message(text='ввести "домашние координаты" вручную')
        result = handle_coordinates_action(msg, DialogState.not_defined, 12345)

        assert result is not None
        assert result.new_state == DialogState.input_of_coords_man

    def test_view_coordinates(self, vk_message):
        """ "посмотреть сохраненные координаты" -> shows 'not set'."""
        from src.vk_bot._utils.handlers.button_handlers import handle_coordinates_action

        self.mock_settings.get_coordinates.return_value = None

        msg = vk_message(text='посмотреть сохраненные "домашние координаты"')
        result = handle_coordinates_action(msg, DialogState.not_defined, 12345)

        assert result is not None
        assert 'не сохранены' in result.text.lower()

    def test_view_coordinates_with_data(self, vk_message):
        """ "посмотреть сохраненные координаты" with existing coords."""
        from src.vk_bot._utils.handlers.button_handlers import handle_coordinates_action

        self.mock_settings.get_coordinates.return_value = ('55.7558', '37.6173')

        msg = vk_message(text='посмотреть сохраненные "домашние координаты"')
        result = handle_coordinates_action(msg, DialogState.not_defined, 12345)

        assert result is not None
        assert '55.7558' in result.text

    def test_delete_coordinates(self, vk_message):
        """ "удалить координаты" -> deletes and returns success."""
        from src.vk_bot._utils.handlers.button_handlers import handle_coordinates_action

        msg = vk_message(text='удалить "домашние координаты"')
        result = handle_coordinates_action(msg, DialogState.not_defined, 12345)

        assert result is not None
        self.mock_settings.delete_coordinates.assert_called_once_with(12345)
        assert 'удалены' in result.text.lower()

    def test_ignores_unknown(self, vk_message):
        """Returns None."""
        from src.vk_bot._utils.handlers.button_handlers import handle_coordinates_action

        msg = vk_message(text='random text')
        result = handle_coordinates_action(msg, DialogState.not_defined, 12345)
        assert result is None


class TestHandleAgeSettings:
    """handle_age_settings — age preference toggles."""

    @pytest.fixture(autouse=True)
    def _setup_mocks(self, mock_settings_service):
        """Store mock_settings_service reference for assertions."""
        self.mock_settings = mock_settings_service
        self.mock_settings.get_age_preferences.return_value = []

    def test_toggles_age_on(self, vk_message):
        """ "дети (0-10 лет)" -> adds age preference."""
        from src.vk_bot._utils.handlers.button_handlers import handle_age_settings

        msg = vk_message(text='дети (0-10 лет)')
        result = handle_age_settings(msg, DialogState.not_defined, 12345)

        assert result is not None
        self.mock_settings.save_age_preference.assert_called_once()

    def test_toggles_age_off(self, vk_message):
        """Toggles existing age preference off."""
        from src.vk_bot._utils.handlers.button_handlers import handle_age_settings

        self.mock_settings.get_age_preferences.return_value = [(0, 10)]

        msg = vk_message(text='дети (0-10 лет)')
        result = handle_age_settings(msg, DialogState.not_defined, 12345)

        assert result is not None
        self.mock_settings.delete_age_preference.assert_called_once()

    def test_ignores_unknown(self, vk_message):
        """Returns None."""
        from src.vk_bot._utils.handlers.button_handlers import handle_age_settings

        msg = vk_message(text='random text')
        result = handle_age_settings(msg, DialogState.not_defined, 12345)
        assert result is None


class TestHandleTopicTypeSettings:
    """handle_topic_type_settings — topic type preference toggles."""

    @pytest.fixture(autouse=True)
    def _setup_mocks(self, mock_settings_service):
        """Store mock_settings_service reference for assertions."""
        self.mock_settings = mock_settings_service
        self.mock_settings.get_topic_types.return_value = []

    def test_toggles_search_type(self, vk_message):
        """ "поисковые работы" -> toggles search type."""
        from src.vk_bot._utils.handlers.button_handlers import handle_topic_type_settings

        msg = vk_message(text='поисковые работы')
        result = handle_topic_type_settings(msg, DialogState.not_defined, 12345)

        assert result is not None
        self.mock_settings.save_topic_type.assert_called_once_with(12345, 0)

    def test_toggles_search_type_off(self, vk_message):
        """Toggles existing topic type off."""
        from src.vk_bot._utils.handlers.button_handlers import handle_topic_type_settings

        self.mock_settings.get_topic_types.return_value = [0]

        msg = vk_message(text='поисковые работы')
        result = handle_topic_type_settings(msg, DialogState.not_defined, 12345)

        assert result is not None
        self.mock_settings.delete_topic_type.assert_called_once_with(12345, 0)

    def test_ignores_unknown(self, vk_message):
        """Returns None."""
        from src.vk_bot._utils.handlers.button_handlers import handle_topic_type_settings

        msg = vk_message(text='random text')
        result = handle_topic_type_settings(msg, DialogState.not_defined, 12345)
        assert result is None


class TestHandleOtherMenu:
    """handle_other_menu — other options menu buttons."""

    def test_latest_searches(self, vk_message):
        """ "посмотреть последние поиски" -> returns placeholder."""
        from src.vk_bot._utils.handlers.button_handlers import handle_other_menu

        msg = vk_message(text='посмотреть последние поиски')
        result = handle_other_menu(msg, DialogState.not_defined, 12345)

        assert result is not None
        assert 'будет доступна' in result.text.lower()

    def test_community(self, vk_message):
        """ "написать разработчику бота" -> returns info text."""
        from src.vk_bot._utils.handlers.button_handlers import handle_other_menu

        msg = vk_message(text='написать разработчику бота')
        result = handle_other_menu(msg, DialogState.not_defined, 12345)

        assert result is not None
        assert result.keyboard is not None

    def test_ignores_unknown(self, vk_message):
        """Returns None."""
        from src.vk_bot._utils.handlers.button_handlers import handle_other_menu

        msg = vk_message(text='random text')
        result = handle_other_menu(msg, DialogState.not_defined, 12345)
        assert result is None


# ═══════════════════════════════════════════════════════════════════════════════
# 3. Region Selection Handlers
# ═══════════════════════════════════════════════════════════════════════════════


class TestHandleFedDistrictSelect:
    """handle_fed_district_select — federal district selection."""

    @pytest.fixture(autouse=True)
    def _setup_mocks(self, mock_settings_service):
        """Store mock_settings_service reference for assertions."""
        self.mock_settings = mock_settings_service

    def test_matches_district_name(self, vk_message):
        """Matches federal district button text."""
        from src.vk_bot._utils.handlers.region_select_handlers import handle_fed_district_select

        self.mock_settings.get_geo_folders.return_value = [
            (1, 'Москва и МО'),
            (2, 'Московская область'),
        ]

        msg = vk_message(text='Центральный ФО')
        result = handle_fed_district_select(msg, DialogState.not_defined, 12345)

        assert result is not None
        assert isinstance(result, VKHandlerResult)

    def test_shows_regions(self, vk_message):
        """Returns regions within the district."""
        from src.vk_bot._utils.handlers.region_select_handlers import handle_fed_district_select

        # The handler matches by checking if district name (without " фо")
        # is contained in the region name (lowercased).
        # "центральный фо" -> "центральный" -> check if in region name
        self.mock_settings.get_geo_folders.return_value = [
            (1, 'Центральный регион'),
            (2, 'Центрально-Черноземный район'),
            (3, 'Калужская область'),
        ]

        msg = vk_message(text='Центральный ФО')
        result = handle_fed_district_select(msg, DialogState.not_defined, 12345)

        assert result is not None
        labels = [btn[0]['action']['label'] for btn in result.keyboard['buttons']]
        assert 'Центральный регион' in labels

    def test_ignores_unknown(self, vk_message):
        """Returns None."""
        from src.vk_bot._utils.handlers.region_select_handlers import handle_fed_district_select

        msg = vk_message(text='random text')
        result = handle_fed_district_select(msg, DialogState.not_defined, 12345)
        assert result is None


class TestHandleRegionToggle:
    """handle_region_toggle — region subscribe/unsubscribe."""

    @pytest.fixture(autouse=True)
    def _setup_mocks(self, mock_settings_service):
        """Store mock_settings_service reference for assertions."""
        self.mock_settings = mock_settings_service

    def test_subscribes_to_region(self, vk_message):
        """Subscribes to a new region."""
        from src.vk_bot._utils.handlers.region_select_handlers import handle_region_toggle

        self.mock_settings.get_geo_folders.return_value = [
            (1, 'Москва и МО'),
        ]
        self.mock_settings.get_user_regions.return_value = []  # not subscribed yet

        msg = vk_message(text='Москва и МО')
        result = handle_region_toggle(msg, DialogState.not_defined, 12345)

        assert result is not None
        assert 'добавлен' in result.text
        self.mock_settings.toggle_region_by_name.assert_called_once()

    def test_unsubscribes_from_region(self, vk_message):
        """Unsubscribes from an existing region."""
        from src.vk_bot._utils.handlers.region_select_handlers import handle_region_toggle

        self.mock_settings.get_geo_folders.return_value = [
            (1, 'Москва и МО'),
        ]
        self.mock_settings.get_user_regions.return_value = [1]  # already subscribed
        self.mock_settings.toggle_region_by_name.return_value = True

        msg = vk_message(text='Москва и МО')
        result = handle_region_toggle(msg, DialogState.not_defined, 12345)

        assert result is not None
        assert 'удален' in result.text
        self.mock_settings.toggle_region_by_name.assert_called_once()

    def test_cant_remove_last_region(self, vk_message):
        """Can't remove the last remaining region."""
        from src.vk_bot._utils.handlers.region_select_handlers import handle_region_toggle

        self.mock_settings.get_geo_folders.return_value = [
            (1, 'Москва и МО'),
        ]
        self.mock_settings.get_user_regions.return_value = [1]  # already subscribed
        self.mock_settings.toggle_region_by_name.return_value = False

        msg = vk_message(text='Москва и МО')
        result = handle_region_toggle(msg, DialogState.not_defined, 12345)

        assert result is not None
        assert 'регион' in result.text.lower()

    def test_ignores_unknown(self, vk_message):
        """Returns None."""
        from src.vk_bot._utils.handlers.region_select_handlers import handle_region_toggle

        self.mock_settings.get_geo_folders.return_value = [
            (1, 'Москва и МО'),
        ]

        msg = vk_message(text='random text')
        result = handle_region_toggle(msg, DialogState.not_defined, 12345)
        assert result is None
