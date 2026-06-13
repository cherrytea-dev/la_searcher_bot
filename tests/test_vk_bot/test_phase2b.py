"""Tests for Phase 2B VK Bot search viewing handlers.

These tests cover:
- handle_view_search_menu — shows search view menu
- handle_active_searches — fetches and displays active searches
- handle_latest_searches — fetches and displays latest 20 searches
- handle_search_follow_menu — shows follow mode status
- handle_follow_mode_toggle — toggles follow mode on/off
- handle_follow_unfollow_command — handles +<id> / -<id> commands
- handle_more_searches — returns to search view menu

Each handler follows the pattern:
    def handler(vk_message, state, user_id) -> VKHandlerResult | None
"""

from unittest.mock import MagicMock, patch

import pytest

from _dependencies.commons import SearchFollowingMode
from _dependencies.services.state_machine import DialogState
from src.vk_bot._utils.common import VKHandlerResult

# ═══════════════════════════════════════════════════════════════════════════════
# 1. handle_view_search_menu
# ═══════════════════════════════════════════════════════════════════════════════


class TestHandleViewSearchMenu:
    """handle_view_search_menu — shows search view menu."""

    def test_handles_view_search_menu_text(self, vk_message):
        """'посмотреть актуальные поиски' -> shows search view menu."""
        from src.vk_bot._utils.handlers.view_searches_handlers import handle_view_search_menu

        msg = vk_message(text='посмотреть актуальные поиски')
        result = handle_view_search_menu(msg, DialogState.not_defined, 12345)

        assert result is not None
        assert isinstance(result, VKHandlerResult)
        assert 'режим просмотра' in result.text.lower()
        assert result.keyboard is not None

    def test_ignores_other_text(self, vk_message):
        """Returns None for non-matching text."""
        from src.vk_bot._utils.handlers.view_searches_handlers import handle_view_search_menu

        msg = vk_message(text='random text')
        result = handle_view_search_menu(msg, DialogState.not_defined, 12345)
        assert result is None

    def test_returns_search_view_keyboard(self, vk_message):
        """Result has search_view_menu keyboard with expected buttons."""
        from src.vk_bot._utils.handlers.view_searches_handlers import handle_view_search_menu

        msg = vk_message(text='посмотреть актуальные поиски')
        result = handle_view_search_menu(msg, DialogState.not_defined, 12345)

        assert result is not None
        labels = [btn[0]['action']['label'] for btn in result.keyboard['buttons']]
        assert 'активные поиски' in labels
        assert 'последние 20 поисков' in labels
        assert 'отслеживание поисков' in labels


# ═══════════════════════════════════════════════════════════════════════════════
# 2. handle_active_searches
# ═══════════════════════════════════════════════════════════════════════════════


class TestHandleActiveSearches:
    """handle_active_searches — fetches and displays active searches."""

    @pytest.fixture(autouse=True)
    def _setup_mocks(self, mock_settings_service):
        """Store mock_settings_service reference for assertions."""
        self.mock_settings = mock_settings_service

    def test_handles_active_searches_text(self, vk_message):
        """'активные поиски' -> returns formatted search list."""
        from src.vk_bot._utils.handlers.view_searches_handlers import handle_active_searches

        # Mock user regions
        self.mock_settings.get_user_regions.return_value = [1, 2]

        # Mock DB connection for raw SQL query
        mock_conn = MagicMock()
        mock_conn.__enter__.return_value = mock_conn
        mock_conn.execute.return_value.fetchall.return_value = [
            (1001, 'Иванов Иван', 'Ищем', None, None, None, None, 1),
            (1002, 'Петров Петр', 'Возобновлен', None, None, None, None, 2),
        ]
        self.mock_settings.connect.return_value = mock_conn

        msg = vk_message(text='активные поиски')
        result = handle_active_searches(msg, DialogState.not_defined, 12345)

        assert result is not None
        assert isinstance(result, VKHandlerResult)
        assert 'Активные поиски' in result.text
        assert 'Иванов Иван' in result.text
        assert 'Петров Петр' in result.text
        assert result.keyboard is not None

    def test_handles_map_searches_text(self, vk_message):
        """'🔥карта поисков 🔥' -> also triggers active searches."""
        from src.vk_bot._utils.handlers.view_searches_handlers import handle_active_searches

        self.mock_settings.get_user_regions.return_value = [1]

        mock_conn = MagicMock()
        mock_conn.__enter__.return_value = mock_conn
        mock_conn.execute.return_value.fetchall.return_value = [
            (1001, 'Иванов Иван', 'Ищем', None, None, None, None, 1),
        ]
        self.mock_settings.connect.return_value = mock_conn

        msg = vk_message(text='🔥Карта Поисков 🔥')
        result = handle_active_searches(msg, DialogState.not_defined, 12345)

        assert result is not None
        assert 'Активные поиски' in result.text

    def test_no_regions(self, vk_message):
        """No subscribed regions -> returns 'no active searches' message."""
        from src.vk_bot._utils.handlers.view_searches_handlers import handle_active_searches

        self.mock_settings.get_user_regions.return_value = []

        msg = vk_message(text='активные поиски')
        result = handle_active_searches(msg, DialogState.not_defined, 12345)

        assert result is not None
        assert result.keyboard is not None

    def test_no_active_searches(self, vk_message):
        """No active searches found -> returns empty message."""
        from src.vk_bot._utils.handlers.view_searches_handlers import handle_active_searches

        self.mock_settings.get_user_regions.return_value = [1]

        mock_conn = MagicMock()
        mock_conn.__enter__.return_value = mock_conn
        mock_conn.execute.return_value.fetchall.return_value = []
        self.mock_settings.connect.return_value = mock_conn

        msg = vk_message(text='активные поиски')
        result = handle_active_searches(msg, DialogState.not_defined, 12345)

        assert result is not None
        assert 'не найдены' in result.text.lower() or 'активные поиски' in result.text

    def test_ignores_other_text(self, vk_message):
        """Returns None for non-matching text."""
        from src.vk_bot._utils.handlers.view_searches_handlers import handle_active_searches

        msg = vk_message(text='random text')
        result = handle_active_searches(msg, DialogState.not_defined, 12345)
        assert result is None

    def test_groups_by_folder(self, vk_message):
        """Searches are grouped by forum_folder_id."""
        from src.vk_bot._utils.handlers.view_searches_handlers import handle_active_searches

        self.mock_settings.get_user_regions.return_value = [1, 2]

        mock_conn = MagicMock()
        mock_conn.__enter__.return_value = mock_conn
        mock_conn.execute.return_value.fetchall.return_value = [
            (1001, 'Иванов Иван', 'Ищем', None, None, None, None, 1),
            (1002, 'Петров Петр', 'Возобновлен', None, None, None, None, 1),
            (1003, 'Сидоров Сидр', 'Ищем', None, None, None, None, 2),
        ]
        self.mock_settings.connect.return_value = mock_conn

        msg = vk_message(text='активные поиски')
        result = handle_active_searches(msg, DialogState.not_defined, 12345)

        assert result is not None
        # Both folder IDs should appear in the output
        assert 'Регион #1' in result.text
        assert 'Регион #2' in result.text


# ═══════════════════════════════════════════════════════════════════════════════
# 3. handle_latest_searches
# ═══════════════════════════════════════════════════════════════════════════════


class TestHandleLatestSearches:
    """handle_latest_searches — fetches and displays latest 20 searches."""

    @pytest.fixture(autouse=True)
    def _setup_mocks(self, mock_settings_service):
        """Store mock_settings_service reference for assertions."""
        self.mock_settings = mock_settings_service

    def test_handles_latest_searches_text(self, vk_message):
        """'последние 20 поисков' -> returns formatted list."""
        from src.vk_bot._utils.handlers.view_searches_handlers import handle_latest_searches

        self.mock_settings.get_user_regions.return_value = [1]

        mock_conn = MagicMock()
        mock_conn.__enter__.return_value = mock_conn
        mock_conn.execute.return_value.fetchall.return_value = [
            (1001, 'Иванов Иван', 'НП', None, None, None, None, 1),
            (1002, 'Петров Петр', 'СТОП', None, None, None, None, 1),
        ]
        self.mock_settings.connect.return_value = mock_conn

        msg = vk_message(text='последние 20 поисков')
        result = handle_latest_searches(msg, DialogState.not_defined, 12345)

        assert result is not None
        assert isinstance(result, VKHandlerResult)
        assert 'Последние 20 поисков' in result.text
        assert 'Иванов Иван' in result.text
        assert 'Петров Петр' in result.text
        assert result.keyboard is not None

    def test_no_regions(self, vk_message):
        """No subscribed regions -> returns empty message."""
        from src.vk_bot._utils.handlers.view_searches_handlers import handle_latest_searches

        self.mock_settings.get_user_regions.return_value = []

        msg = vk_message(text='последние 20 поисков')
        result = handle_latest_searches(msg, DialogState.not_defined, 12345)

        assert result is not None
        assert result.keyboard is not None

    def test_no_searches(self, vk_message):
        """No searches found -> returns empty message."""
        from src.vk_bot._utils.handlers.view_searches_handlers import handle_latest_searches

        self.mock_settings.get_user_regions.return_value = [1]

        mock_conn = MagicMock()
        mock_conn.__enter__.return_value = mock_conn
        mock_conn.execute.return_value.fetchall.return_value = []
        self.mock_settings.connect.return_value = mock_conn

        msg = vk_message(text='последние 20 поисков')
        result = handle_latest_searches(msg, DialogState.not_defined, 12345)

        assert result is not None
        assert 'нет завершенных' in result.text.lower() or 'последние' in result.text.lower()

    def test_ignores_other_text(self, vk_message):
        """Returns None for non-matching text."""
        from src.vk_bot._utils.handlers.view_searches_handlers import handle_latest_searches

        msg = vk_message(text='random text')
        result = handle_latest_searches(msg, DialogState.not_defined, 12345)
        assert result is None


# ═══════════════════════════════════════════════════════════════════════════════
# 4. handle_search_follow_menu
# ═══════════════════════════════════════════════════════════════════════════════


class TestHandleSearchFollowMenu:
    """handle_search_follow_menu — shows follow mode status."""

    @pytest.fixture(autouse=True)
    def _setup_mocks(self, mock_settings_service):
        """Store mock_settings_service reference for assertions."""
        self.mock_settings = mock_settings_service

    def test_handles_follow_menu_text(self, vk_message):
        """'управление отслеживанием' -> shows follow menu."""
        from src.vk_bot._utils.handlers.view_searches_handlers import handle_search_follow_menu

        self.mock_settings.get_search_follow_mode.return_value = True

        msg = vk_message(text='управление отслеживанием')
        result = handle_search_follow_menu(msg, DialogState.not_defined, 12345)

        assert result is not None
        assert isinstance(result, VKHandlerResult)
        assert 'отслеживания' in result.text.lower()
        assert result.keyboard is not None

    def test_handles_alt_text(self, vk_message):
        """'отслеживание поисков' -> also shows follow menu."""
        from src.vk_bot._utils.handlers.view_searches_handlers import handle_search_follow_menu

        self.mock_settings.get_search_follow_mode.return_value = False

        msg = vk_message(text='отслеживание поисков')
        result = handle_search_follow_menu(msg, DialogState.not_defined, 12345)

        assert result is not None
        assert result.keyboard is not None

    def test_shows_follow_mode_on_status(self, vk_message):
        """When follow mode is on, shows enabled status."""
        from src.vk_bot._utils.handlers.view_searches_handlers import handle_search_follow_menu

        self.mock_settings.get_search_follow_mode.return_value = True

        msg = vk_message(text='управление отслеживанием')
        result = handle_search_follow_menu(msg, DialogState.not_defined, 12345)

        assert result is not None
        assert 'включен' in result.text.lower()

    def test_shows_follow_mode_off_status(self, vk_message):
        """When follow mode is off, shows disabled status."""
        from src.vk_bot._utils.handlers.view_searches_handlers import handle_search_follow_menu

        self.mock_settings.get_search_follow_mode.return_value = False

        msg = vk_message(text='управление отслеживанием')
        result = handle_search_follow_menu(msg, DialogState.not_defined, 12345)

        assert result is not None
        assert 'выключен' in result.text.lower()

    def test_ignores_other_text(self, vk_message):
        """Returns None for non-matching text."""
        from src.vk_bot._utils.handlers.view_searches_handlers import handle_search_follow_menu

        msg = vk_message(text='random text')
        result = handle_search_follow_menu(msg, DialogState.not_defined, 12345)
        assert result is None


# ═══════════════════════════════════════════════════════════════════════════════
# 5. handle_follow_mode_toggle
# ═══════════════════════════════════════════════════════════════════════════════


class TestHandleFollowModeToggle:
    """handle_follow_mode_toggle — toggles follow mode on/off."""

    @pytest.fixture(autouse=True)
    def _setup_mocks(self, mock_settings_service):
        """Store mock_settings_service reference for assertions."""
        self.mock_settings = mock_settings_service

    def test_enables_follow_mode(self, vk_message):
        """'включить режим отслеживания' -> enables follow mode."""
        from src.vk_bot._utils.handlers.view_searches_handlers import handle_follow_mode_toggle

        msg = vk_message(text='включить режим отслеживания')
        result = handle_follow_mode_toggle(msg, DialogState.not_defined, 12345)

        assert result is not None
        self.mock_settings.set_search_follow_mode.assert_called_once_with(12345, True)
        assert result.keyboard is not None

    def test_disables_follow_mode(self, vk_message):
        """'выключить режим отслеживания' -> disables follow mode."""
        from src.vk_bot._utils.handlers.view_searches_handlers import handle_follow_mode_toggle

        msg = vk_message(text='выключить режим отслеживания')
        result = handle_follow_mode_toggle(msg, DialogState.not_defined, 12345)

        assert result is not None
        self.mock_settings.set_search_follow_mode.assert_called_once_with(12345, False)
        assert result.keyboard is not None

    def test_shows_followed_searches(self, vk_message):
        """'показать отслеживаемые поиски' -> shows list of followed searches."""
        from src.vk_bot._utils.handlers.view_searches_handlers import handle_follow_mode_toggle

        # _get_user_followed_ids iterates over execute() result directly (not fetchall)
        # It checks row[1] in (SearchFollowingMode.ON, SearchFollowingMode.OFF)
        # First execute call: fetch from user_pref_search_whitelist
        mock_result_whitelist = MagicMock()
        mock_result_whitelist.__iter__.return_value = iter(
            [
                (1001, SearchFollowingMode.ON),
                (1002, SearchFollowingMode.OFF),
            ]
        )

        # Second execute call: fetch search details from searches table
        mock_result_searches = MagicMock()
        mock_result_searches.fetchall.return_value = [
            (1001, 'Иванов Иван', 'Ищем'),
            (1002, 'Петров Петр', 'НП'),
        ]

        mock_conn = MagicMock()
        mock_conn.__enter__.return_value = mock_conn
        mock_conn.execute.side_effect = [
            mock_result_whitelist,
            mock_result_searches,
        ]
        self.mock_settings.connect.return_value = mock_conn

        msg = vk_message(text='показать отслеживаемые поиски')
        result = handle_follow_mode_toggle(msg, DialogState.not_defined, 12345)

        assert result is not None
        assert 'Отслеживаемые поиски' in result.text
        assert 'Иванов Иван' in result.text
        assert 'Петров Петр' in result.text
        assert result.keyboard is not None

    def test_shows_followed_searches_empty(self, vk_message):
        """No followed searches -> shows empty message with instructions."""
        from src.vk_bot._utils.handlers.view_searches_handlers import handle_follow_mode_toggle

        # _get_user_followed_ids iterates over execute() result directly
        mock_result = MagicMock()
        mock_result.__iter__.return_value = iter([])

        mock_conn = MagicMock()
        mock_conn.__enter__.return_value = mock_conn
        mock_conn.execute.return_value = mock_result
        self.mock_settings.connect.return_value = mock_conn

        msg = vk_message(text='показать отслеживаемые поиски')
        result = handle_follow_mode_toggle(msg, DialogState.not_defined, 12345)

        assert result is not None
        assert 'нет отслеживаемых' in result.text.lower()
        assert '+12345' in result.text or '+' in result.text

    def test_ignores_other_text(self, vk_message):
        """Returns None for non-matching text."""
        from src.vk_bot._utils.handlers.view_searches_handlers import handle_follow_mode_toggle

        msg = vk_message(text='random text')
        result = handle_follow_mode_toggle(msg, DialogState.not_defined, 12345)
        assert result is None


# ═══════════════════════════════════════════════════════════════════════════════
# 6. handle_follow_unfollow_command
# ═══════════════════════════════════════════════════════════════════════════════


class TestHandleFollowUnfollowCommand:
    """handle_follow_unfollow_command — +<id> / -<id> commands."""

    @pytest.fixture(autouse=True)
    def _setup_mocks(self, mock_settings_service):
        """Store mock_settings_service reference for assertions."""
        self.mock_settings = mock_settings_service

    def _setup_mock_conn(self, exists: bool = True, current_mode=None):
        """Helper to set up mock DB connection with configurable responses.

        The handler calls execute() twice:
        1. First: check if search exists (SELECT search_forum_num FROM searches ...)
        2. Second: check current follow state (SELECT search_following_mode ...)

        _get_user_followed_ids is NOT called here (only in follow_mode_toggle).
        """
        mock_conn = MagicMock()
        mock_conn.__enter__.return_value = mock_conn

        # First execute call: check if search exists
        mock_result_exists = MagicMock()
        mock_result_exists.fetchone.return_value = (1001,) if exists else None

        # Second execute call: check current follow state
        mock_result_follow = MagicMock()
        mock_result_follow.fetchone.return_value = (current_mode,) if current_mode else None

        mock_conn.execute.side_effect = [
            mock_result_exists,
            mock_result_follow,
        ]
        self.mock_settings.connect.return_value = mock_conn
        return mock_conn

    def test_follow_command(self, vk_message):
        """'+12345' -> follows search."""
        from src.vk_bot._utils.handlers.view_searches_handlers import handle_follow_unfollow_command

        self._setup_mock_conn(exists=True, current_mode=None)

        msg = vk_message(text='+12345')
        result = handle_follow_unfollow_command(msg, DialogState.not_defined, 12345)

        assert result is not None
        assert isinstance(result, VKHandlerResult)
        self.mock_settings.record_search_whiteness.assert_called_once_with(12345, 12345, SearchFollowingMode.ON)
        assert 'следите' in result.text.lower()

    def test_unfollow_command(self, vk_message):
        """'-12345' when currently followed -> blacklists."""
        from src.vk_bot._utils.handlers.view_searches_handlers import handle_follow_unfollow_command

        self._setup_mock_conn(exists=True, current_mode=SearchFollowingMode.ON)

        msg = vk_message(text='-12345')
        result = handle_follow_unfollow_command(msg, DialogState.not_defined, 12345)

        assert result is not None
        self.mock_settings.record_search_whiteness.assert_called_once_with(12345, 12345, SearchFollowingMode.OFF)
        assert 'не будете' in result.text.lower()

    def test_blacklist_command(self, vk_message):
        """'-12345' when not followed -> blacklists."""
        from src.vk_bot._utils.handlers.view_searches_handlers import handle_follow_unfollow_command

        self._setup_mock_conn(exists=True, current_mode=None)

        msg = vk_message(text='-12345')
        result = handle_follow_unfollow_command(msg, DialogState.not_defined, 12345)

        assert result is not None
        self.mock_settings.record_search_whiteness.assert_called_once_with(12345, 12345, SearchFollowingMode.OFF)
        assert 'игнорируемые' in result.text.lower() or 'добавлен' in result.text.lower()

    def test_blacklist_to_neutral_cycle(self, vk_message):
        """'-12345' when already blacklisted -> removes from whitelist (neutral)."""
        from src.vk_bot._utils.handlers.view_searches_handlers import handle_follow_unfollow_command

        self._setup_mock_conn(exists=True, current_mode=SearchFollowingMode.OFF)

        msg = vk_message(text='-12345')
        result = handle_follow_unfollow_command(msg, DialogState.not_defined, 12345)

        assert result is not None
        self.mock_settings.record_search_whiteness.assert_called_once_with(12345, 12345, '  ')
        assert 'сброшено' in result.text.lower()

    def test_already_following(self, vk_message):
        """'+12345' when already followed -> shows already following message."""
        from src.vk_bot._utils.handlers.view_searches_handlers import handle_follow_unfollow_command

        self._setup_mock_conn(exists=True, current_mode=SearchFollowingMode.ON)

        msg = vk_message(text='+12345')
        result = handle_follow_unfollow_command(msg, DialogState.not_defined, 12345)

        assert result is not None
        assert 'уже следите' in result.text.lower()
        self.mock_settings.record_search_whiteness.assert_not_called()

    def test_search_not_found(self, vk_message):
        """'+99999' when search doesn't exist -> shows not found message."""
        from src.vk_bot._utils.handlers.view_searches_handlers import handle_follow_unfollow_command

        self._setup_mock_conn(exists=False)

        msg = vk_message(text='+99999')
        result = handle_follow_unfollow_command(msg, DialogState.not_defined, 12345)

        assert result is not None
        assert 'не найден' in result.text.lower()
        self.mock_settings.record_search_whiteness.assert_not_called()

    def test_ignores_non_command_text(self, vk_message):
        """Returns None for non-command text."""
        from src.vk_bot._utils.handlers.view_searches_handlers import handle_follow_unfollow_command

        msg = vk_message(text='random text')
        result = handle_follow_unfollow_command(msg, DialogState.not_defined, 12345)
        assert result is None

    def test_ignores_text_without_plus_minus(self, vk_message):
        """Returns None for text that doesn't start with + or -."""
        from src.vk_bot._utils.handlers.view_searches_handlers import handle_follow_unfollow_command

        msg = vk_message(text='12345')
        result = handle_follow_unfollow_command(msg, DialogState.not_defined, 12345)
        assert result is None

    def test_ignores_plus_without_digits(self, vk_message):
        """Returns None for '+' without digits."""
        from src.vk_bot._utils.handlers.view_searches_handlers import handle_follow_unfollow_command

        msg = vk_message(text='+abc')
        result = handle_follow_unfollow_command(msg, DialogState.not_defined, 12345)
        assert result is None


# ═══════════════════════════════════════════════════════════════════════════════
# 7. handle_more_searches
# ═══════════════════════════════════════════════════════════════════════════════


class TestHandleMoreSearches:
    """handle_more_searches — returns to search view menu."""

    def test_handles_more_searches_text(self, vk_message):
        """'еще поиски' -> returns search view menu."""
        from src.vk_bot._utils.handlers.view_searches_handlers import handle_more_searches

        msg = vk_message(text='еще поиски')
        result = handle_more_searches(msg, DialogState.not_defined, 12345)

        assert result is not None
        assert isinstance(result, VKHandlerResult)
        assert 'режим просмотра' in result.text.lower()
        assert result.keyboard is not None

    def test_ignores_other_text(self, vk_message):
        """Returns None for non-matching text."""
        from src.vk_bot._utils.handlers.view_searches_handlers import handle_more_searches

        msg = vk_message(text='random text')
        result = handle_more_searches(msg, DialogState.not_defined, 12345)
        assert result is None

    def test_returns_search_view_keyboard(self, vk_message):
        """Result has search_view_menu keyboard."""
        from src.vk_bot._utils.handlers.view_searches_handlers import handle_more_searches

        msg = vk_message(text='еще поиски')
        result = handle_more_searches(msg, DialogState.not_defined, 12345)

        assert result is not None
        labels = [btn[0]['action']['label'] for btn in result.keyboard['buttons']]
        assert 'активные поиски' in labels
        assert 'последние 20 поисков' in labels
