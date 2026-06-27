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
    def handler(ctx: VKHandlerContext) -> None
"""

from unittest.mock import MagicMock

import pytest

from _dependencies.common.commons import SearchFollowingMode
from _dependencies.models import DialogState
from src.vk_bot._utils.handlers.view_searches_handlers import (
    handle_active_searches,
    handle_follow_disable,
    handle_follow_enable,
    handle_follow_show,
    handle_follow_unfollow_command,
    handle_latest_searches,
    handle_more_searches,
    handle_search_follow_menu,
    handle_view_search_menu,
)

# ═══════════════════════════════════════════════════════════════════════════════
# 1. handle_view_search_menu
# ═══════════════════════════════════════════════════════════════════════════════


class TestHandleViewSearchMenu:
    """handle_view_search_menu — shows search view menu."""

    def test_handles_view_search_menu_text(self, vk_handler_context):
        """'посмотреть актуальные поиски' -> shows search view menu."""

        ctx = vk_handler_context(text='посмотреть актуальные поиски', state=DialogState.not_defined)
        handle_view_search_menu(ctx)

        assert ctx.is_consumed
        ctx._sender.assert_sent_text('режим просмотра')
        ctx._sender.assert_sent_with_keyboard()

    def test_returns_search_view_keyboard(self, vk_handler_context):
        """Result has search_view_menu keyboard with expected buttons."""

        ctx = vk_handler_context(text='посмотреть актуальные поиски', state=DialogState.not_defined)
        handle_view_search_menu(ctx)

        assert ctx.is_consumed
        ctx._sender.assert_sent_with_keyboard()
        labels = ctx._sender.last_sent_keyboard_labels
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

    def test_handles_active_searches_text(self, vk_handler_context):
        """'активные поиски' -> returns formatted search list."""

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

        ctx = vk_handler_context(text='активные поиски', state=DialogState.not_defined)
        handle_active_searches(ctx)

        assert ctx.is_consumed
        ctx._sender.assert_sent_text('Активные поиски')
        ctx._sender.assert_sent_text('Иванов Иван')
        ctx._sender.assert_sent_text('Петров Петр')
        ctx._sender.assert_sent_with_keyboard()

    def test_handles_map_searches_text(self, vk_handler_context):
        """'🔥карта поисков 🔥' -> also triggers active searches."""

        self.mock_settings.get_user_regions.return_value = [1]

        mock_conn = MagicMock()
        mock_conn.__enter__.return_value = mock_conn
        mock_conn.execute.return_value.fetchall.return_value = [
            (1001, 'Иванов Иван', 'Ищем', None, None, None, None, 1),
        ]
        self.mock_settings.connect.return_value = mock_conn

        ctx = vk_handler_context(text='🔥Карта Поисков 🔥', state=DialogState.not_defined)
        handle_active_searches(ctx)

        assert ctx.is_consumed
        ctx._sender.assert_sent_text('Активные поиски')

    def test_no_regions(self, vk_handler_context):
        """No subscribed regions -> returns 'no active searches' message."""

        self.mock_settings.get_user_regions.return_value = []

        ctx = vk_handler_context(text='активные поиски', state=DialogState.not_defined)
        handle_active_searches(ctx)

        assert ctx.is_consumed
        ctx._sender.assert_sent_with_keyboard()

    def test_no_active_searches(self, vk_handler_context):
        """No active searches found -> returns empty message."""

        self.mock_settings.get_user_regions.return_value = [1]

        mock_conn = MagicMock()
        mock_conn.__enter__.return_value = mock_conn
        mock_conn.execute.return_value.fetchall.return_value = []
        self.mock_settings.connect.return_value = mock_conn

        ctx = vk_handler_context(text='активные поиски', state=DialogState.not_defined)
        handle_active_searches(ctx)

        assert ctx.is_consumed
        ctx._sender.assert_sent_text('не найдены')

    def test_groups_by_folder(self, vk_handler_context):
        """Searches are grouped by forum_folder_id."""

        self.mock_settings.get_user_regions.return_value = [1, 2]

        mock_conn = MagicMock()
        mock_conn.__enter__.return_value = mock_conn
        mock_conn.execute.return_value.fetchall.return_value = [
            (1001, 'Иванов Иван', 'Ищем', None, None, None, None, 1),
            (1002, 'Петров Петр', 'Возобновлен', None, None, None, None, 1),
            (1003, 'Сидоров Сидр', 'Ищем', None, None, None, None, 2),
        ]
        self.mock_settings.connect.return_value = mock_conn

        ctx = vk_handler_context(text='активные поиски', state=DialogState.not_defined)
        handle_active_searches(ctx)

        assert ctx.is_consumed
        # Both folder IDs should appear in the output
        ctx._sender.assert_sent_text('Регион #1')
        ctx._sender.assert_sent_text('Регион #2')


# ═══════════════════════════════════════════════════════════════════════════════
# 3. handle_latest_searches
# ═══════════════════════════════════════════════════════════════════════════════


class TestHandleLatestSearches:
    """handle_latest_searches — fetches and displays latest 20 searches."""

    @pytest.fixture(autouse=True)
    def _setup_mocks(self, mock_settings_service):
        """Store mock_settings_service reference for assertions."""
        self.mock_settings = mock_settings_service

    def test_handles_latest_searches_text(self, vk_handler_context):
        """'последние 20 поисков' -> returns formatted list."""

        self.mock_settings.get_user_regions.return_value = [1]

        mock_conn = MagicMock()
        mock_conn.__enter__.return_value = mock_conn
        mock_conn.execute.return_value.fetchall.return_value = [
            (1001, 'Иванов Иван', 'НП', None, None, None, None, 1),
            (1002, 'Петров Петр', 'СТОП', None, None, None, None, 1),
        ]
        self.mock_settings.connect.return_value = mock_conn

        ctx = vk_handler_context(text='последние 20 поисков', state=DialogState.not_defined)
        handle_latest_searches(ctx)

        assert ctx.is_consumed
        ctx._sender.assert_sent_text('Последние 20 поисков')
        ctx._sender.assert_sent_text('Иванов Иван')
        ctx._sender.assert_sent_text('Петров Петр')
        ctx._sender.assert_sent_with_keyboard()

    def test_no_regions(self, vk_handler_context):
        """No subscribed regions -> returns empty message."""

        self.mock_settings.get_user_regions.return_value = []

        ctx = vk_handler_context(text='последние 20 поисков', state=DialogState.not_defined)
        handle_latest_searches(ctx)

        assert ctx.is_consumed
        ctx._sender.assert_sent_with_keyboard()

    def test_no_searches(self, vk_handler_context):
        """No searches found -> returns empty message."""

        self.mock_settings.get_user_regions.return_value = [1]

        mock_conn = MagicMock()
        mock_conn.__enter__.return_value = mock_conn
        mock_conn.execute.return_value.fetchall.return_value = []
        self.mock_settings.connect.return_value = mock_conn

        ctx = vk_handler_context(text='последние 20 поисков', state=DialogState.not_defined)
        handle_latest_searches(ctx)

        assert ctx.is_consumed
        ctx._sender.assert_sent_text('нет завершенных')


# ═══════════════════════════════════════════════════════════════════════════════
# 4. handle_search_follow_menu
# ═══════════════════════════════════════════════════════════════════════════════


class TestHandleSearchFollowMenu:
    """handle_search_follow_menu — shows follow mode status."""

    @pytest.fixture(autouse=True)
    def _setup_mocks(self, mock_settings_service):
        """Store mock_settings_service reference for assertions."""
        self.mock_settings = mock_settings_service

    def test_handles_follow_menu_text(self, vk_handler_context):
        """'управление отслеживанием' -> shows follow menu."""

        self.mock_settings.get_search_follow_mode.return_value = True

        ctx = vk_handler_context(text='управление отслеживанием', state=DialogState.not_defined)
        handle_search_follow_menu(ctx)

        assert ctx.is_consumed
        ctx._sender.assert_sent_text('отслеживания')
        ctx._sender.assert_sent_with_keyboard()

    def test_handles_alt_text(self, vk_handler_context):
        """'отслеживание поисков' -> also shows follow menu."""

        self.mock_settings.get_search_follow_mode.return_value = False

        ctx = vk_handler_context(text='отслеживание поисков', state=DialogState.not_defined)
        handle_search_follow_menu(ctx)

        assert ctx.is_consumed
        ctx._sender.assert_sent_with_keyboard()

    def test_shows_follow_mode_on_status(self, vk_handler_context):
        """When follow mode is on, shows enabled status."""

        self.mock_settings.get_search_follow_mode.return_value = True

        ctx = vk_handler_context(text='управление отслеживанием', state=DialogState.not_defined)
        handle_search_follow_menu(ctx)

        assert ctx.is_consumed
        ctx._sender.assert_sent_text('включен')

    def test_shows_follow_mode_off_status(self, vk_handler_context):
        """When follow mode is off, shows disabled status."""

        self.mock_settings.get_search_follow_mode.return_value = False

        ctx = vk_handler_context(text='управление отслеживанием', state=DialogState.not_defined)
        handle_search_follow_menu(ctx)

        assert ctx.is_consumed
        ctx._sender.assert_sent_text('выключен')


# ═══════════════════════════════════════════════════════════════════════════════
# 5. handle_follow_mode_toggle
# ═══════════════════════════════════════════════════════════════════════════════


class TestHandleFollowEnable:
    """handle_follow_enable — enables follow mode."""

    @pytest.fixture(autouse=True)
    def _setup_mocks(self, mock_settings_service):
        """Store mock_settings_service reference for assertions."""
        self.mock_settings = mock_settings_service

    def test_enables_follow_mode(self, vk_handler_context):
        """'включить режим отслеживания' -> enables follow mode."""

        ctx = vk_handler_context(text='включить режим отслеживания', state=DialogState.not_defined)
        handle_follow_enable(ctx)

        assert ctx.is_consumed
        self.mock_settings.set_search_follow_mode.assert_called_once_with(12345, True)
        ctx._sender.assert_sent_with_keyboard()


class TestHandleFollowDisable:
    """handle_follow_disable — disables follow mode."""

    @pytest.fixture(autouse=True)
    def _setup_mocks(self, mock_settings_service):
        """Store mock_settings_service reference for assertions."""
        self.mock_settings = mock_settings_service

    def test_disables_follow_mode(self, vk_handler_context):
        """'выключить режим отслеживания' -> disables follow mode."""

        ctx = vk_handler_context(text='выключить режим отслеживания', state=DialogState.not_defined)
        handle_follow_disable(ctx)

        assert ctx.is_consumed
        self.mock_settings.set_search_follow_mode.assert_called_once_with(12345, False)
        ctx._sender.assert_sent_with_keyboard()


class TestHandleFollowShow:
    """handle_follow_show — shows followed searches list."""

    @pytest.fixture(autouse=True)
    def _setup_mocks(self, mock_settings_service):
        """Store mock_settings_service reference for assertions."""
        self.mock_settings = mock_settings_service

    def test_shows_followed_searches(self, vk_handler_context):
        """'показать отслеживаемые поиски' -> shows list of followed searches."""

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

        ctx = vk_handler_context(text='показать отслеживаемые поиски', state=DialogState.not_defined)
        handle_follow_show(ctx)

        assert ctx.is_consumed
        ctx._sender.assert_sent_text('Отслеживаемые поиски')
        ctx._sender.assert_sent_text('Иванов Иван')
        ctx._sender.assert_sent_text('Петров Петр')
        ctx._sender.assert_sent_with_keyboard()

    def test_shows_followed_searches_empty(self, vk_handler_context):
        """No followed searches -> shows empty message with instructions."""

        # _get_user_followed_ids iterates over execute() result directly
        mock_result = MagicMock()
        mock_result.__iter__.return_value = iter([])

        mock_conn = MagicMock()
        mock_conn.__enter__.return_value = mock_conn
        mock_conn.execute.return_value = mock_result
        self.mock_settings.connect.return_value = mock_conn

        ctx = vk_handler_context(text='показать отслеживаемые поиски', state=DialogState.not_defined)
        handle_follow_show(ctx)

        assert ctx.is_consumed
        ctx._sender.assert_sent_text('нет отслеживаемых')


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

    def test_follow_command(self, vk_handler_context):
        """'+12345' -> follows search."""

        self._setup_mock_conn(exists=True, current_mode=None)

        ctx = vk_handler_context(text='+12345', state=DialogState.not_defined)
        handle_follow_unfollow_command(ctx)

        assert ctx.is_consumed
        self.mock_settings.record_search_whiteness.assert_called_once_with(12345, 12345, SearchFollowingMode.ON)
        ctx._sender.assert_sent_text('следите')

    def test_unfollow_command(self, vk_handler_context):
        """'-12345' when currently followed -> blacklists."""

        self._setup_mock_conn(exists=True, current_mode=SearchFollowingMode.ON)

        ctx = vk_handler_context(text='-12345', state=DialogState.not_defined)
        handle_follow_unfollow_command(ctx)

        assert ctx.is_consumed
        self.mock_settings.record_search_whiteness.assert_called_once_with(12345, 12345, SearchFollowingMode.OFF)
        ctx._sender.assert_sent_text('не будете')

    def test_blacklist_command(self, vk_handler_context):
        """'-12345' when not followed -> blacklists."""

        self._setup_mock_conn(exists=True, current_mode=None)

        ctx = vk_handler_context(text='-12345', state=DialogState.not_defined)
        handle_follow_unfollow_command(ctx)

        assert ctx.is_consumed
        self.mock_settings.record_search_whiteness.assert_called_once_with(12345, 12345, SearchFollowingMode.OFF)
        ctx._sender.assert_sent_text('игнорируемые')

    def test_blacklist_to_neutral_cycle(self, vk_handler_context):
        """'-12345' when already blacklisted -> removes from whitelist (neutral)."""

        self._setup_mock_conn(exists=True, current_mode=SearchFollowingMode.OFF)

        ctx = vk_handler_context(text='-12345', state=DialogState.not_defined)
        handle_follow_unfollow_command(ctx)

        assert ctx.is_consumed
        self.mock_settings.record_search_whiteness.assert_called_once_with(12345, 12345, '  ')
        ctx._sender.assert_sent_text('сброшено')

    def test_already_following(self, vk_handler_context):
        """'+12345' when already followed -> shows already following message."""

        self._setup_mock_conn(exists=True, current_mode=SearchFollowingMode.ON)

        ctx = vk_handler_context(text='+12345', state=DialogState.not_defined)
        handle_follow_unfollow_command(ctx)

        assert ctx.is_consumed
        ctx._sender.assert_sent_text('уже следите')
        self.mock_settings.record_search_whiteness.assert_not_called()

    def test_search_not_found(self, vk_handler_context):
        """'+99999' when search doesn't exist -> shows not found message."""

        self._setup_mock_conn(exists=False)

        ctx = vk_handler_context(text='+99999', state=DialogState.not_defined)
        handle_follow_unfollow_command(ctx)

        assert ctx.is_consumed
        ctx._sender.assert_sent_text('не найден')
        self.mock_settings.record_search_whiteness.assert_not_called()

    def test_ignores_non_command_text(self, vk_handler_context):
        """Does not consume for non-command text."""

        ctx = vk_handler_context(text='random text', state=DialogState.not_defined)
        handle_follow_unfollow_command(ctx)
        assert not ctx.is_consumed

    def test_ignores_text_without_plus_minus(self, vk_handler_context):
        """Does not consume for text that doesn't start with + or -."""

        ctx = vk_handler_context(text='12345', state=DialogState.not_defined)
        handle_follow_unfollow_command(ctx)
        assert not ctx.is_consumed

    def test_ignores_plus_without_digits(self, vk_handler_context):
        """Does not consume for '+' without digits."""

        ctx = vk_handler_context(text='+abc', state=DialogState.not_defined)
        handle_follow_unfollow_command(ctx)
        assert not ctx.is_consumed


# ═══════════════════════════════════════════════════════════════════════════════
# 7. handle_more_searches
# ═══════════════════════════════════════════════════════════════════════════════


class TestHandleMoreSearches:
    """handle_more_searches — returns to search view menu."""

    def test_handles_more_searches_text(self, vk_handler_context):
        """'еще поиски' -> returns search view menu."""

        ctx = vk_handler_context(text='еще поиски', state=DialogState.not_defined)
        handle_more_searches(ctx)

        assert ctx.is_consumed
        ctx._sender.assert_sent_text('режим просмотра')
        ctx._sender.assert_sent_with_keyboard()

    def test_returns_search_view_keyboard(self, vk_handler_context):
        """Result has search_view_menu keyboard."""

        ctx = vk_handler_context(text='еще поиски', state=DialogState.not_defined)
        handle_more_searches(ctx)

        assert ctx.is_consumed
        ctx._sender.assert_sent_with_keyboard()
        labels = ctx._sender.last_sent_keyboard_labels
        assert 'активные поиски' in labels
        assert 'последние 20 поисков' in labels
