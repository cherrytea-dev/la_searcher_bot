"""Emergency read-only mode shared by the Telegram, VK and MAX bots.

Enabled with ``EMERGENCY_READONLY_MODE=true``. The bot keeps running its background pipeline
(parsing the forum, composing and sending notifications); only *user-facing* actions are
restricted: handlers on the read-only allowlist (pure "view" screens) run as usual, every other
action gets a short stub reply and nothing is written to the database.

The allowlists match handlers by name (``Handler.func.__name__`` for Telegram/VK, the callback
``cmd`` / command for MAX), so a renamed handler simply falls off the allowlist — the safe
direction: it gets the stub instead of writing. Being too strict only costs a "view" screen
(it shows the stub); being too loose would let a write through, which is the thing to avoid.
"""

from __future__ import annotations

from _dependencies.common.commons import get_app_config

#: Shown to the user on every action that is not a read-only "view" screen.
READONLY_NOTICE = (
    '⚠️ Бот временно работает в аварийном режиме «только чтение».\n\n'
    'Просматривать свои поиски и настройки можно, а сохранять изменения и подписываться — сейчас нельзя.'
)

# ── Telegram: handlers that only *show* something (search lists, settings menus, help, links) ──
READONLY_SAFE_TG = frozenset(
    {
        'handle_view_searches',
        'handle_command_start',
        'handle_back_to_main_menu',
        'handle_command_other',
        'handle_help_needed',
        'handle_main_settings',
        'handle_notification_settings_show_menu',
        'handle_coordinates_show_saved',
        'handle_show_map',
        'handle_goto_photos',
        'handle_goto_first_search',
        'handle_goto_community',
    }
)

# ── VK: the same idea — only "view" screens (search lists, main menu, help) ──
READONLY_SAFE_VK = frozenset(
    {
        'handle_command_start',
        'handle_main_menu',
        'handle_back_to_start',
        'handle_view_search_menu',
        'handle_active_searches',
        'handle_latest_searches',
        'handle_more_searches',
        'handle_follow_show',
        'handle_coords_view',
    }
)

# ── MAX: read-only callbacks (view sub-menus / saved values) and the /start command ──
READONLY_SAFE_MAX_CMDS = frozenset(
    {
        'back_to_main',
        'region',
        'radius',
        'coords',
        'radius_view',
        'coords_view',
    }
)
READONLY_SAFE_MAX_COMMANDS = frozenset({'start'})


def is_readonly() -> bool:
    """Whether the emergency read-only mode is on."""
    return bool(get_app_config().emergency_readonly_mode)
