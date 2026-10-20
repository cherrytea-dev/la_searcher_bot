"""Guard against silently losing handlers when handler modules are moved or split.

Handler registration happens as a side effect of importing the handler modules
in ``communicate.main``. If a module is accidentally removed from that import
list, its handlers disappear without any error — this test catches that.
"""

from communicate import main  # noqa: F401 — import to trigger @tg_handle registration
from communicate._utils.decorators import tg_registry

EXPECTED_HANDLER_NAMES = {
    'handle_admin_experimental_settings',
    'handle_age_settings',
    'handle_back_to_main_menu',
    'handle_command_other',
    'handle_command_start',
    'handle_coordinates_delete',
    'handle_coordinates_menu_manual_input',
    'handle_coordinates_show_menu',
    'handle_coordinates_show_saved',
    'handle_disable_notifications',
    'handle_enable_notifications',
    'handle_goto_community',
    'handle_goto_first_search',
    'handle_goto_photos',
    'handle_help_needed',
    'handle_if_moscow',
    'handle_linking_to_forum_its_me',
    'handle_linking_to_forum_not_me',
    'handle_linking_to_forum_show_menu',
    'handle_linking_to_forum_user_input',
    'handle_main_settings',
    'handle_notification_settings',
    'handle_notification_settings_show_menu',
    'handle_radius_menu',
    'handle_radius_menu_show',
    'handle_radius_value',
    'handle_region_selection_callback',
    'handle_reset_settings_cancel',
    'handle_reset_settings_confirm',
    'handle_reset_settings_confirm_prompt',
    'handle_search_follow_clear',
    'handle_set_region',
    'handle_show_map',
    'handle_test_admin_check',
    'handle_topic_type_show_menu',
    'handle_topic_type_user_changed',
    'handle_user_coordinates_from_text',
    'handle_user_role',
    'handle_view_searches',
    'manage_search_whiteness',
}


def test_registry_contains_all_expected_handlers():
    actual_names = {handler.func.__name__ for handler in tg_registry.all()}
    assert actual_names == EXPECTED_HANDLER_NAMES
