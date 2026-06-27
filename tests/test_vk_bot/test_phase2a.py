"""Tests for Phase 2A VK Bot handlers.

These tests cover:
- State-based handlers (radius input, coords input, forum username input)
- Button/command handlers (onboarding, main menu, settings, etc.)
- Region selection handlers (federal district select, region toggle)

Each handler follows the pattern:
    def handler(ctx: VKHandlerContext) -> None
"""

import pytest

from _dependencies.models import DialogState
from src.vk_bot._utils.handlers.onboarding_handlers import (
    handle_back_to_start,
    handle_command_start,
    handle_is_moscow,
    handle_main_menu,
    handle_role_choice,
)
from src.vk_bot._utils.handlers.region_select_handlers import (
    _toggle_region_inline,
    handle_fed_district_select,
)
from src.vk_bot._utils.handlers.settings_handlers import (
    handle_age_settings,
    handle_coords_delete,
    handle_coords_enter,
    handle_coords_view,
    handle_notification_toggle,
    handle_other_feedback,
    handle_settings_coords,
    handle_settings_radius,
    handle_settings_region,
    handle_topic_type_settings,
)
from src.vk_bot._utils.handlers.state_handlers import handle_coords_text, handle_forum_username, handle_radius_value

# ═══════════════════════════════════════════════════════════════════════════════
# 1. State Handlers
# ═══════════════════════════════════════════════════════════════════════════════


class TestHandleRadiusValue:
    """handle_radius_value — radius input state handler."""

    def test_accepts_radius_input_state(self, vk_handler_context):
        """Handler handles when state=radius_input."""

        ctx = vk_handler_context(text='50', state=DialogState.radius_input)
        handle_radius_value(ctx)
        assert ctx.is_consumed

    def test_parses_numeric_input(self, vk_handler_context, mock_settings_service):
        """'50' -> saves radius, returns success text."""

        ctx = vk_handler_context(text='50', state=DialogState.radius_input)
        handle_radius_value(ctx)

        assert ctx.is_consumed
        mock_settings_service.save_radius.assert_called_once_with(12345, 50)
        ctx._sender.assert_sent_text('50')

    def test_parses_number_in_text(self, vk_handler_context, mock_settings_service):
        """ "хочу радиус 100 км" -> saves 100."""

        ctx = vk_handler_context(text='хочу радиус 100 км', state=DialogState.radius_input)
        handle_radius_value(ctx)

        assert ctx.is_consumed
        mock_settings_service.save_radius.assert_called_once_with(12345, 100)

    def test_rejects_non_numeric(self, vk_handler_context, mock_settings_service):
        """ "привет" -> returns parse error text."""

        ctx = vk_handler_context(text='привет', state=DialogState.radius_input)
        handle_radius_value(ctx)

        assert ctx.is_consumed
        ctx._sender.assert_sent_text('цифр')
        mock_settings_service.save_radius.assert_not_called()

    def test_saves_radius_via_settings(self, vk_handler_context, mock_settings_service):
        """Verifies db().settings.save_radius is called."""

        ctx = vk_handler_context(text='75', state=DialogState.radius_input)
        handle_radius_value(ctx)

        mock_settings_service.save_radius.assert_called_once_with(12345, 75)

    def test_resets_state_to_not_defined(self, vk_handler_context, mock_settings_service):
        """State is cleared after save (reply() calls clear_user_state)."""

        ctx = vk_handler_context(text='50', state=DialogState.radius_input)
        handle_radius_value(ctx)

        assert ctx.is_consumed
        mock_settings_service.clear_user_state.assert_called_once_with(12345)


class TestHandleCoordsText:
    """handle_coords_text — manual coordinate input state handler."""

    def test_accepts_coords_input_state(self, vk_handler_context):
        """Handles when state=input_of_coords_man."""

        ctx = vk_handler_context(text='55.7558, 37.6173', state=DialogState.input_of_coords_man)
        handle_coords_text(ctx)
        assert ctx.is_consumed

    def test_parses_valid_coords(self, vk_handler_context, mock_settings_service):
        """ "55.7558, 37.6173" -> saves."""

        ctx = vk_handler_context(text='55.7558, 37.6173', state=DialogState.input_of_coords_man)
        handle_coords_text(ctx)

        assert ctx.is_consumed
        mock_settings_service.save_coordinates.assert_called_once_with(12345, 55.7558, 37.6173)
        ctx._sender.assert_sent_text('сохранены')

    def test_parses_coords_with_space_delimiter(self, vk_handler_context, mock_settings_service):
        """ "55.7558 37.6173" -> saves."""

        ctx = vk_handler_context(text='55.7558 37.6173', state=DialogState.input_of_coords_man)
        handle_coords_text(ctx)

        assert ctx.is_consumed
        mock_settings_service.save_coordinates.assert_called_once_with(12345, 55.7558, 37.6173)

    def test_rejects_invalid_format(self, vk_handler_context, mock_settings_service):
        """ "abc def" -> parse error."""

        ctx = vk_handler_context(text='abc def', state=DialogState.input_of_coords_man)
        handle_coords_text(ctx)

        assert ctx.is_consumed
        ctx._sender.assert_sent_text('не распознаны')
        mock_settings_service.save_coordinates.assert_not_called()

    def test_resets_state_after_save(self, vk_handler_context, mock_settings_service):
        """State is cleared after save."""

        ctx = vk_handler_context(text='55.7558, 37.6173', state=DialogState.input_of_coords_man)
        handle_coords_text(ctx)

        assert ctx.is_consumed
        mock_settings_service.clear_user_state.assert_called_once_with(12345)


class TestHandleForumUsername:
    """handle_forum_username — forum username input state handler."""

    def test_accepts_forum_username_state(self, vk_handler_context):
        """Handles when state=input_of_forum_username."""

        ctx = vk_handler_context(text='my_forum_nick', state=DialogState.input_of_forum_username)
        handle_forum_username(ctx)
        assert ctx.is_consumed

    def test_captures_username(self, vk_handler_context):
        """Passes text as forum username."""

        ctx = vk_handler_context(text='  my_forum_nick  ', state=DialogState.input_of_forum_username)
        handle_forum_username(ctx)

        assert ctx.is_consumed
        ctx._sender.assert_sent_text('посмотрю')

    def test_resets_state(self, vk_handler_context, mock_settings_service):
        """State is cleared after save."""

        ctx = vk_handler_context(text='my_forum_nick', state=DialogState.input_of_forum_username)
        handle_forum_username(ctx)

        assert ctx.is_consumed
        mock_settings_service.clear_user_state.assert_called_once_with(12345)


# ═══════════════════════════════════════════════════════════════════════════════
# 2. Button/Command Handlers
# ═══════════════════════════════════════════════════════════════════════════════


class TestHandleCommandStart:
    """handle_command_start — /start command handler."""

    def test_handles_start_command(self, vk_handler_context, mock_settings_service):
        """ "/start" -> returns welcome text."""

        mock_settings_service.check_if_new_user.return_value = False

        ctx = vk_handler_context(text='/start')
        handle_command_start(ctx)

        assert ctx.is_consumed
        ctx._sender.assert_sent_text('привет')
        ctx._sender.assert_sent_with_keyboard()

    def test_returns_main_menu_keyboard(self, vk_handler_context, mock_settings_service):
        """Result has main_menu keyboard."""

        mock_settings_service.check_if_new_user.return_value = False

        ctx = vk_handler_context(text='/start')
        handle_command_start(ctx)

        assert ctx.is_consumed
        ctx._sender.assert_sent_with_keyboard()
        labels = ctx._sender.last_sent_keyboard_labels
        assert len(labels) == 1
        assert labels[0] == 'настроить бот'


class TestHandleRoleChoice:
    """handle_role_choice — role selection during onboarding."""

    @pytest.fixture(autouse=True)
    def _setup_mocks(self, mock_settings_service):
        """Store mock_settings_service reference for assertions."""
        self.mock_settings = mock_settings_service

    def test_handles_member_role(self, vk_handler_context):
        """ "я состою в лизаалерт" -> saves role with code 'member'."""

        ctx = vk_handler_context(text='я состою в ЛизаАлерт')
        handle_role_choice(ctx)

        assert ctx.is_consumed
        self.mock_settings.save_user_role.assert_called_once_with(12345, 'member')
        self.mock_settings.save_onboarding_step.assert_called_once_with(12345, 'role_set')

    def test_handles_volunteer_role(self, vk_handler_context):
        """ "я хочу помогать лизаалерт" -> saves role with code 'volunteer'."""

        ctx = vk_handler_context(text='я хочу помогать ЛизаАлерт')
        handle_role_choice(ctx)

        assert ctx.is_consumed
        self.mock_settings.save_user_role.assert_called_once_with(12345, 'volunteer')
        self.mock_settings.save_onboarding_step.assert_called_once_with(12345, 'role_set')

    def test_handles_relative_role(self, vk_handler_context):
        """ "я ищу человека" -> saves role with code 'relative', shows orders_done keyboard."""

        ctx = vk_handler_context(text='я ищу человека')
        handle_role_choice(ctx)

        assert ctx.is_consumed
        self.mock_settings.save_user_role.assert_called_once_with(12345, 'relative')
        self.mock_settings.save_onboarding_step.assert_called_once_with(12345, 'role_set')
        ctx._sender.assert_sent_with_keyboard()
        labels = ctx._sender.last_sent_keyboard_labels
        assert 'уже заказал(а)' in labels or 'закажу позже' in labels

    def test_handles_other_role(self, vk_handler_context):
        """ "у меня другая задача" -> saves role with code 'other'."""

        ctx = vk_handler_context(text='у меня другая задача')
        handle_role_choice(ctx)

        assert ctx.is_consumed
        self.mock_settings.save_user_role.assert_called_once_with(12345, 'other')
        self.mock_settings.save_onboarding_step.assert_called_once_with(12345, 'role_set')

    def test_saves_onboarding_step(self, vk_handler_context):
        """Calls save_onboarding_step with 'role_set'."""

        ctx = vk_handler_context(text='я состою в ЛизаАлерт')
        handle_role_choice(ctx)

        self.mock_settings.save_onboarding_step.assert_called_once_with(12345, 'role_set')


class TestHandleIsMoscow:
    """handle_is_moscow — Moscow region confirmation during onboarding."""

    @pytest.fixture(autouse=True)
    def _setup_mocks(self, mock_settings_service):
        """Store mock_settings_service reference for assertions."""
        self.mock_settings = mock_settings_service

    def test_handles_yes(self, vk_handler_context):
        """ "да, москва – мой регион" (em-dash) -> adds Moscow region, subscribes."""

        # Mock geo folders to include Moscow regions
        # _subscribe_moscow_regions matches 'москв' in name.lower() or 'мо:' in name.lower()
        self.mock_settings.get_geo_folders.return_value = [
            (1, 'Москва и МО'),  # 'москв' matches
            (2, 'МО: Московская обл.'),  # 'мо:' matches
            (3, 'Калужская область'),  # no match
        ]

        # Note: handler uses EN DASH (U+2013), not regular hyphen
        ctx = vk_handler_context(text='да, Москва – мой регион')
        handle_is_moscow(ctx)

        assert ctx.is_consumed
        self.mock_settings.save_onboarding_step.assert_called_once_with(12345, 'finished')
        # Verify Moscow region subscription was attempted
        self.mock_settings.add_region.assert_any_call(12345, 1)
        self.mock_settings.add_region.assert_any_call(12345, 2)
        ctx._sender.assert_sent_text('отлично')

    def test_handles_no(self, vk_handler_context):
        """ "нет, я из другого региона" -> shows fed_districts keyboard."""

        ctx = vk_handler_context(text='нет, я из другого региона')
        handle_is_moscow(ctx)

        assert ctx.is_consumed
        ctx._sender.assert_sent_with_keyboard()
        labels = ctx._sender.last_sent_keyboard_labels
        assert 'Центральный ФО' in labels


class TestHandleBackToStart:
    """handle_back_to_start — 'в начало' button handler."""

    def test_handles_back_to_start(self, vk_handler_context):
        """ "в начало" -> returns main_menu keyboard."""

        ctx = vk_handler_context(text='в начало')
        handle_back_to_start(ctx)

        assert ctx.is_consumed
        ctx._sender.assert_sent_with_keyboard()
        labels = ctx._sender.last_sent_keyboard_labels
        assert 'настроить бот' in labels

    def test_resets_state(self, vk_handler_context, mock_settings_service):
        """State is cleared (reply() calls clear_user_state)."""

        ctx = vk_handler_context(text='в начало', state=DialogState.radius_input)
        handle_back_to_start(ctx)

        assert ctx.is_consumed
        mock_settings_service.clear_user_state.assert_called_once_with(12345)


class TestHandleMainMenu:
    """handle_main_menu — main menu navigation buttons."""

    @pytest.fixture(autouse=True)
    def _setup_mocks(self, mock_settings_service):
        """Store mock_settings_service reference for assertions."""
        self.mock_settings = mock_settings_service

    def test_settings_button(self, vk_handler_context):
        """ "настроить бот" -> returns settings_menu keyboard."""

        ctx = vk_handler_context(text='настроить бот')
        handle_main_menu(ctx)

        assert ctx.is_consumed
        ctx._sender.assert_sent_with_keyboard()
        labels = ctx._sender.last_sent_keyboard_labels
        assert len(labels) == 4
        assert labels[0] == 'настроить регион поисков'
        assert labels[1] == 'настроить "домашние координаты"'
        assert labels[2] == 'настроить максимальный радиус'
        assert labels[3] == 'в начало'


class TestHandleSettingsRegion:
    """handle_settings_region — settings region button."""

    def test_region_settings(self, vk_handler_context):
        """ "настроить регионы" -> sends keyboard."""

        ctx = vk_handler_context(text='настроить регионы', state=DialogState.not_defined)
        handle_settings_region(ctx)

        assert ctx.is_consumed
        ctx._sender.assert_sent_with_keyboard()


class TestHandleSettingsCoords:
    """handle_settings_coords — settings coords button."""

    @pytest.fixture(autouse=True)
    def _setup_mocks(self, mock_settings_service):
        """Store mock_settings_service reference for assertions."""
        self.mock_settings = mock_settings_service

    def test_coordinates_menu(self, vk_handler_context):
        """ "настроить "домашние координаты"" -> sends coords_menu keyboard."""

        self.mock_settings.get_coordinates.return_value = None

        ctx = vk_handler_context(text='настроить "домашние координаты"', state=DialogState.not_defined)
        handle_settings_coords(ctx)

        assert ctx.is_consumed
        ctx._sender.assert_sent_with_keyboard()


class TestHandleSettingsRadius:
    """handle_settings_radius — settings radius button."""

    @pytest.fixture(autouse=True)
    def _setup_mocks(self, mock_settings_service):
        """Store mock_settings_service reference for assertions."""
        self.mock_settings = mock_settings_service

    def test_radius_settings(self, vk_handler_context):
        """ "настроить максимальный радиус" -> sends radius_settings keyboard."""

        self.mock_settings.get_radius.return_value = None

        ctx = vk_handler_context(text='настроить максимальный радиус', state=DialogState.not_defined)
        handle_settings_radius(ctx)

        assert ctx.is_consumed
        ctx._sender.assert_sent_with_keyboard()


class TestHandleNotificationToggle:
    """handle_notification_toggle — notification preference toggles."""

    @pytest.fixture(autouse=True)
    def _setup_mocks(self, mock_settings_service):
        """Store mock_settings_service reference for assertions."""
        self.mock_settings = mock_settings_service
        self.mock_settings.get_all_user_preferences.return_value = []

    def test_toggles_preference_on(self, vk_handler_context):
        """Toggles a preference to enabled."""

        ctx = vk_handler_context(text='включить: о новых поисках', state=DialogState.not_defined)
        handle_notification_toggle(ctx)

        assert ctx.is_consumed
        self.mock_settings.save_preference.assert_called_once_with(12345, 'new_searches')

    def test_toggles_preference_off(self, vk_handler_context):
        """Toggles a preference to disabled."""

        ctx = vk_handler_context(text='отключить: о новых поисках', state=DialogState.not_defined)
        handle_notification_toggle(ctx)

        assert ctx.is_consumed
        self.mock_settings.delete_preferences.assert_called_once_with(12345, ['new_searches'])


class TestHandleCoordsEnter:
    """handle_coords_enter — manual coordinate input."""

    def test_manual_input(self, vk_handler_context):
        """ "ввести координаты" -> sets state to input_of_coords_man."""

        ctx = vk_handler_context(text='ввести "домашние координаты" вручную', state=DialogState.not_defined)
        handle_coords_enter(ctx)

        assert ctx.is_consumed
        assert ctx.state == DialogState.input_of_coords_man


class TestHandleCoordsView:
    """handle_coords_view — view saved coordinates."""

    @pytest.fixture(autouse=True)
    def _setup_mocks(self, mock_settings_service):
        """Store mock_settings_service reference for assertions."""
        self.mock_settings = mock_settings_service

    def test_view_coordinates(self, vk_handler_context):
        """ "посмотреть сохраненные координаты" -> shows 'not set'."""

        self.mock_settings.get_coordinates.return_value = None

        ctx = vk_handler_context(text='посмотреть сохраненные координаты', state=DialogState.not_defined)
        handle_coords_view(ctx)

        assert ctx.is_consumed
        ctx._sender.assert_sent_text('не сохранены')

    def test_view_coordinates_with_data(self, vk_handler_context):
        """ "посмотреть сохраненные координаты" with existing coords."""

        self.mock_settings.get_coordinates.return_value = ('55.7558', '37.6173')

        ctx = vk_handler_context(text='посмотреть сохраненные координаты', state=DialogState.not_defined)
        handle_coords_view(ctx)

        assert ctx.is_consumed
        ctx._sender.assert_sent_text('55.7558')


class TestHandleCoordsDelete:
    """handle_coords_delete — delete saved coordinates."""

    @pytest.fixture(autouse=True)
    def _setup_mocks(self, mock_settings_service):
        """Store mock_settings_service reference for assertions."""
        self.mock_settings = mock_settings_service

    def test_delete_coordinates(self, vk_handler_context):
        """ "удалить координаты" -> deletes and returns success."""

        ctx = vk_handler_context(text='удалить "домашние координаты"', state=DialogState.not_defined)
        handle_coords_delete(ctx)

        assert ctx.is_consumed
        self.mock_settings.delete_coordinates.assert_called_once_with(12345)
        ctx._sender.assert_sent_text('удалены')


class TestHandleAgeSettings:
    """handle_age_settings — age preference toggles."""

    @pytest.fixture(autouse=True)
    def _setup_mocks(self, mock_settings_service):
        """Store mock_settings_service reference for assertions."""
        self.mock_settings = mock_settings_service
        self.mock_settings.get_age_preferences.return_value = []

    def test_toggles_age_on(self, vk_handler_context):
        """ "дети (0-10 лет)" -> adds age preference."""

        ctx = vk_handler_context(text='дети (0-10 лет)', state=DialogState.not_defined)
        handle_age_settings(ctx)

        assert ctx.is_consumed
        self.mock_settings.save_age_preference.assert_called_once()

    def test_toggles_age_off(self, vk_handler_context):
        """Toggles existing age preference off."""

        self.mock_settings.get_age_preferences.return_value = [(0, 10)]

        ctx = vk_handler_context(text='дети (0-10 лет)', state=DialogState.not_defined)
        handle_age_settings(ctx)

        assert ctx.is_consumed
        self.mock_settings.delete_age_preference.assert_called_once()


class TestHandleTopicTypeSettings:
    """handle_topic_type_settings — topic type preference toggles."""

    @pytest.fixture(autouse=True)
    def _setup_mocks(self, mock_settings_service):
        """Store mock_settings_service reference for assertions."""
        self.mock_settings = mock_settings_service
        self.mock_settings.get_topic_types.return_value = []

    def test_toggles_search_type(self, vk_handler_context):
        """ "поисковые работы" -> toggles search type."""

        ctx = vk_handler_context(text='поисковые работы', state=DialogState.not_defined)
        handle_topic_type_settings(ctx)

        assert ctx.is_consumed
        self.mock_settings.save_topic_type.assert_called_once_with(12345, 0)

    def test_toggles_search_type_off(self, vk_handler_context):
        """Toggles existing topic type off."""

        self.mock_settings.get_topic_types.return_value = [0]

        ctx = vk_handler_context(text='поисковые работы', state=DialogState.not_defined)
        handle_topic_type_settings(ctx)

        assert ctx.is_consumed
        self.mock_settings.delete_topic_type.assert_called_once_with(12345, 0)


class TestHandleOtherFeedback:
    """handle_other_feedback — 'write to developer' button."""

    def test_community(self, vk_handler_context):
        """ "написать разработчику бота" -> sends info text."""

        ctx = vk_handler_context(text='написать разработчику бота', state=DialogState.not_defined)
        handle_other_feedback(ctx)

        assert ctx.is_consumed
        ctx._sender.assert_sent_with_keyboard()


# ═══════════════════════════════════════════════════════════════════════════════
# 3. Region Selection Handlers
# ═══════════════════════════════════════════════════════════════════════════════


class TestHandleFedDistrictSelect:
    """handle_fed_district_select — federal district selection."""

    @pytest.fixture(autouse=True)
    def _setup_mocks(self, mock_settings_service):
        """Store mock_settings_service reference for assertions."""
        self.mock_settings = mock_settings_service

    def test_matches_district_name(self, vk_handler_context):
        """Matches federal district button text."""

        self.mock_settings.get_geo_folders_by_district.return_value = [
            (1, 'Москва и МО'),
            (2, 'Московская область'),
        ]

        ctx = vk_handler_context(text='Центральный ФО', state=DialogState.not_defined)
        handle_fed_district_select(ctx)

        assert ctx.is_consumed

    def test_shows_regions(self, vk_handler_context):
        """Returns regions within the district."""

        self.mock_settings.get_geo_folders_by_district.return_value = [
            (1, 'Москва и МО'),
            (2, 'Московская область'),
        ]

        ctx = vk_handler_context(text='Центральный ФО', state=DialogState.not_defined)
        handle_fed_district_select(ctx)

        assert ctx.is_consumed
        # Check that sent message has region names in keyboard
        ctx._sender.assert_sent_with_keyboard()
        labels = ctx._sender.last_sent_keyboard_labels
        assert 'Москва и МО' in labels
        assert 'Московская область' in labels

    def test_triggers_pagination_for_many_regions(self, vk_handler_context):
        """District with >6 regions triggers inline pagination."""

        # 15 regions = 3 pages (6 + 6 + 3)
        self.mock_settings.get_geo_folders_by_district.return_value = [(i, f'Регион {i}') for i in range(1, 16)]

        ctx = vk_handler_context(text='Центральный ФО', state=DialogState.not_defined)
        handle_fed_district_select(ctx)

        assert ctx.is_consumed
        # Should be inline keyboard (paginated)
        ctx._sender.assert_sent_with_keyboard()

    def test_no_pagination_for_few_regions(self, vk_handler_context):
        """District with <=6 regions shows all without pagination."""

        # 4 regions = 1 page
        self.mock_settings.get_geo_folders_by_district.return_value = [
            (1, 'Москва и МО'),
            (2, 'Московская область'),
            (3, 'Тверская обл.'),
            (4, 'Калужская обл.'),
        ]

        ctx = vk_handler_context(text='Центральный ФО', state=DialogState.not_defined)
        handle_fed_district_select(ctx)

        assert ctx.is_consumed
        ctx._sender.assert_sent_with_keyboard()
        labels = ctx._sender.last_sent_keyboard_labels
        assert 'Москва и МО' in labels
        assert 'Калужская обл.' in labels


class TestToggleRegionInline:
    """_toggle_region_inline — lightweight toggle for inline callbacks."""

    @pytest.fixture(autouse=True)
    def _setup_mocks(self, mock_settings_service):
        """Store mock_settings_service reference for assertions."""
        self.mock_settings = mock_settings_service

    def test_subscribes_to_region(self, vk_handler_context):
        """Returns snackbar text for subscription."""

        self.mock_settings.get_geo_folders.return_value = [(1, 'Москва и МО')]
        self.mock_settings.get_user_regions.return_value = []

        ctx = vk_handler_context(text='Москва и МО', user_id=12345)
        result = _toggle_region_inline(ctx, 'Москва и МО')

        assert 'добавлен' in result
        self.mock_settings.toggle_region_by_name.assert_called_once()

    def test_unsubscribes_from_region(self, vk_handler_context):
        """Returns snackbar text for unsubscription."""

        self.mock_settings.get_geo_folders.return_value = [(1, 'Москва и МО')]
        self.mock_settings.get_user_regions.return_value = [1]
        self.mock_settings.toggle_region_by_name.return_value = True

        ctx = vk_handler_context(text='Москва и МО', user_id=12345)
        result = _toggle_region_inline(ctx, 'Москва и МО')

        assert 'удален' in result

    def test_cant_remove_last_region(self, vk_handler_context):
        """Returns error text when can't remove last region."""

        self.mock_settings.get_geo_folders.return_value = [(1, 'Москва и МО')]
        self.mock_settings.get_user_regions.return_value = [1]
        self.mock_settings.toggle_region_by_name.return_value = False

        ctx = vk_handler_context(text='Москва и МО', user_id=12345)
        result = _toggle_region_inline(ctx, 'Москва и МО')

        assert 'последний регион' in result

    def test_region_not_found(self, vk_handler_context):
        """Returns error text when region doesn't exist."""

        self.mock_settings.get_geo_folders.return_value = [(1, 'Москва и МО')]

        ctx = vk_handler_context(text='Москва и МО', user_id=12345)
        result = _toggle_region_inline(ctx, 'Неизвестный регион')

        assert 'не найден' in result

    def test_db_error_returns_error_text(self, vk_handler_context):
        """Returns error text when DB operation fails."""

        self.mock_settings.get_geo_folders.return_value = [(1, 'Москва и МО')]
        self.mock_settings.get_user_regions.return_value = []
        self.mock_settings.toggle_region_by_name.side_effect = Exception('DB error')

        ctx = vk_handler_context(text='Москва и МО', user_id=12345)
        result = _toggle_region_inline(ctx, 'Москва и МО')

        assert 'ошибка' in result.lower() or 'позже' in result.lower()
