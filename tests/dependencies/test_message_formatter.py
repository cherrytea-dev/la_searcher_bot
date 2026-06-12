"""Tests for the platform-independent message formatter module."""

from _dependencies.message_formatter import (
    LA_BOT_CHAT_URL,
    LA_DEV_CHAT_URL,
    LA_HOTLINE_PHONE,
    LA_PHOTOS_CHANNEL_URL,
    NOTIF_PREF_NAMES,
    SEARCH_URL_PREFIX,
    SearchDisplayItem,
    active_searches_empty,
    active_searches_header,
    active_searches_text_header,
    age_saved,
    age_settings_intro,
    ask_role,
    back_to_main_menu,
    community_intro,
    compose_settings_completeness_message,
    coords_ask_manual_input,
    coords_deleted,
    coords_intro,
    coords_not_set,
    coords_parse_error,
    coords_saved,
    first_search_intro,
    force_set_region,
    format_notif_prefs_list,
    forum_already_linked,
    forum_link_ask_retry,
    forum_link_checking,
    forum_link_intro,
    forum_link_invalid,
    forum_link_verified,
    help_no_thanks,
    help_yes_please,
    last_searches_error,
    last_searches_header,
    last_searches_text_header,
    map_intro,
    no_active_searches_found,
    notif_all_enabled,
    notif_coords_change_enabled,
    notif_field_trip_change_enabled,
    notif_field_trip_new_enabled,
    notif_first_post_change_enabled,
    notif_inforg_comments_enabled,
    notif_new_search_enabled,
    notif_settings_current_prefs,
    notif_settings_intro,
    notif_settings_no_prefs,
    notif_status_change_enabled,
    onboarding_completed_message,
    other_menu_intro,
    photos_intro,
    radius_ask_value,
    radius_deleted,
    radius_intro_no_radius,
    radius_intro_with_radius,
    radius_parse_error,
    radius_saved,
    region_selection_cant_remove_last,
    region_selection_closed,
    region_selection_help,
    region_selection_intro,
    role_other_ask_region,
    role_relative_instructions,
    role_volunteer_instructions,
    search_follow_experimental_intro,
    search_follow_intro,
    search_follow_mode_off,
    search_follow_mode_on,
    settings_menu_intro,
    topic_type_intro,
    unknown_command,
    unsupported_contact,
    unsupported_media,
    vk_already_linked,
    vk_link_instructions,
    vk_link_intro,
    welcome_back_user,
    welcome_new_user,
)


# =============================================================================
# Constants
# =============================================================================


class TestConstants:
    def test_search_url_prefix(self):
        assert SEARCH_URL_PREFIX == 'https://lizaalert.org/forum/viewtopic.php?t='

    def test_la_bot_chat_url(self):
        # Actual value from message_formatter.py
        assert LA_BOT_CHAT_URL.startswith('https://t.me/')

    def test_la_photos_channel_url(self):
        # Actual value from message_formatter.py
        assert LA_PHOTOS_CHANNEL_URL.startswith('https://t.me/')

    def test_la_dev_chat_url(self):
        # Actual value from message_formatter.py
        assert LA_DEV_CHAT_URL.startswith('https://t.me/')

    def test_la_hotline_phone(self):
        # Actual value from message_formatter.py
        assert '8' in LA_HOTLINE_PHONE
        assert '700' in LA_HOTLINE_PHONE
        assert '54-52' in LA_HOTLINE_PHONE


# =============================================================================
# SearchDisplayItem
# =============================================================================


class TestSearchDisplayItem:
    def test_minimal_item(self):
        item = SearchDisplayItem(
            topic_id=12345,
            display_name='Test Search',
            status_text='Ищем',
            distance_text='',
            following_mark='',
        )
        assert item.topic_id == 12345
        assert item.display_name == 'Test Search'
        assert item.status_text == 'Ищем'

    def test_full_item(self):
        item = SearchDisplayItem(
            topic_id=12345,
            display_name='Иван Иванов',
            status_text='Ищем 3 дня',
            distance_text='15 км ↗️',
            following_mark='👀',
        )
        assert item.display_name == 'Иван Иванов'
        assert item.distance_text == '15 км ↗️'
        assert item.following_mark == '👀'


# =============================================================================
# Welcome & Onboarding
# =============================================================================


class TestWelcomeNewUser:
    def test_returns_string(self):
        result = welcome_new_user()
        assert isinstance(result, str)
        assert len(result) > 0
        assert 'ЛизаАлерт' in result or 'поисково-спасательный' in result


class TestWelcomeBackUser:
    def test_returns_string(self):
        result = welcome_back_user()
        assert isinstance(result, str)
        assert len(result) > 0


class TestOnboardingCompletedMessage:
    def test_returns_string(self):
        result = onboarding_completed_message()
        assert isinstance(result, str)
        assert len(result) > 0


class TestAskRole:
    def test_returns_string(self):
        result = ask_role()
        assert isinstance(result, str)
        assert len(result) > 0


class TestRoleRelativeInstructions:
    def test_returns_string(self):
        result = role_relative_instructions()
        assert isinstance(result, str)
        assert len(result) > 0


class TestRoleVolunteerInstructions:
    def test_returns_string(self):
        result = role_volunteer_instructions()
        assert isinstance(result, str)
        assert len(result) > 0


class TestRoleOtherAskRegion:
    def test_returns_string(self):
        result = role_other_ask_region()
        assert isinstance(result, str)
        assert len(result) > 0


# =============================================================================
# Region Selection
# =============================================================================


class TestRegionSelectionIntro:
    def test_returns_string(self):
        result = region_selection_intro()
        assert isinstance(result, str)
        assert len(result) > 0


class TestRegionSelectionHelp:
    def test_returns_string(self):
        result = region_selection_help()
        assert isinstance(result, str)
        assert len(result) > 0


class TestForceSetRegion:
    def test_returns_string(self):
        result = force_set_region()
        assert isinstance(result, str)
        assert len(result) > 0


class TestRegionSelectionClosed:
    def test_returns_string(self):
        result = region_selection_closed()
        assert isinstance(result, str)
        assert len(result) > 0


class TestRegionSelectionCantRemoveLast:
    def test_returns_string(self):
        result = region_selection_cant_remove_last()
        assert isinstance(result, str)
        assert len(result) > 0


# =============================================================================
# Settings Menu
# =============================================================================


class TestSettingsMenuIntro:
    def test_returns_string(self):
        result = settings_menu_intro()
        assert isinstance(result, str)
        assert len(result) > 0


class TestComposeSettingsCompletenessMessage:
    def test_all_complete(self):
        result = compose_settings_completeness_message(
            has_notif_type=True,
            has_region=True,
            has_coords=True,
            has_radius=True,
            has_age=True,
            has_forum=True,
        )
        assert result is None

    def test_none_complete(self):
        result = compose_settings_completeness_message(
            has_notif_type=False,
            has_region=False,
            has_coords=False,
            has_radius=False,
            has_age=False,
            has_forum=False,
        )
        assert isinstance(result, str)
        assert len(result) > 0

    def test_partial_complete(self):
        result = compose_settings_completeness_message(
            has_notif_type=True,
            has_region=False,
            has_coords=True,
            has_radius=False,
            has_age=True,
            has_forum=False,
        )
        assert isinstance(result, str)
        assert len(result) > 0


# =============================================================================
# Notification Settings
# =============================================================================


class TestNotifSettingsIntro:
    def test_returns_string(self):
        result = notif_settings_intro()
        assert isinstance(result, str)
        assert len(result) > 0


class TestNotifSettingsCurrentPrefs:
    def test_with_prefs(self):
        result = notif_settings_current_prefs('текст уведомлений')
        assert isinstance(result, str)
        assert len(result) > 0


class TestNotifSettingsNoPrefs:
    def test_returns_string(self):
        result = notif_settings_no_prefs()
        assert isinstance(result, str)
        assert len(result) > 0


class TestNotifPrefNames:
    def test_contains_expected_keys(self):
        assert 'all' in NOTIF_PREF_NAMES
        assert 'new_searches' in NOTIF_PREF_NAMES
        assert 'status_changes' in NOTIF_PREF_NAMES
        assert 'title_changes' in NOTIF_PREF_NAMES
        assert 'comments_changes' in NOTIF_PREF_NAMES
        assert 'inforg_comments' in NOTIF_PREF_NAMES
        assert 'first_post_changes' in NOTIF_PREF_NAMES
        assert 'all_in_followed_search' in NOTIF_PREF_NAMES
        assert 'field_trips_new' in NOTIF_PREF_NAMES
        assert 'field_trips_change' in NOTIF_PREF_NAMES
        assert 'coords_change' in NOTIF_PREF_NAMES
        assert 'bot_news' in NOTIF_PREF_NAMES

    def test_values_are_strings(self):
        for key, value in NOTIF_PREF_NAMES.items():
            assert isinstance(key, str)
            assert isinstance(value, str)


class TestFormatNotifPrefsList:
    def test_empty_list(self):
        result = format_notif_prefs_list([])
        assert isinstance(result, str)

    def test_with_items(self):
        result = format_notif_prefs_list(['new_searches', 'status_changes'])
        assert isinstance(result, str)
        assert len(result) > 0


class TestNotifFunctions:
    def test_notif_all_enabled(self):
        result = notif_all_enabled()
        assert isinstance(result, str)
        assert len(result) > 0

    def test_notif_new_search_enabled(self):
        result = notif_new_search_enabled()
        assert isinstance(result, str)
        assert len(result) > 0

    def test_notif_status_change_enabled(self):
        result = notif_status_change_enabled()
        assert isinstance(result, str)
        assert len(result) > 0

    def test_notif_inforg_comments_enabled(self):
        result = notif_inforg_comments_enabled()
        assert isinstance(result, str)
        assert len(result) > 0

    def test_notif_field_trip_new_enabled(self):
        result = notif_field_trip_new_enabled()
        assert isinstance(result, str)
        assert len(result) > 0

    def test_notif_field_trip_change_enabled(self):
        result = notif_field_trip_change_enabled()
        assert isinstance(result, str)
        assert len(result) > 0

    def test_notif_coords_change_enabled(self):
        result = notif_coords_change_enabled()
        assert isinstance(result, str)
        assert len(result) > 0

    def test_notif_first_post_change_enabled(self):
        result = notif_first_post_change_enabled()
        assert isinstance(result, str)
        assert len(result) > 0


# =============================================================================
# Topic Type
# =============================================================================


class TestTopicTypeIntro:
    def test_returns_string(self):
        result = topic_type_intro()
        assert isinstance(result, str)
        assert len(result) > 0


# =============================================================================
# Age Settings
# =============================================================================


class TestAgeSettingsIntro:
    def test_first_visit(self):
        result = age_settings_intro(first_visit=True)
        assert isinstance(result, str)
        assert len(result) > 0

    def test_not_first_visit(self):
        result = age_settings_intro(first_visit=False)
        assert isinstance(result, str)
        assert len(result) > 0


class TestAgeSaved:
    def test_returns_string(self):
        result = age_saved()
        assert isinstance(result, str)
        assert len(result) > 0


# =============================================================================
# Radius Settings
# =============================================================================


class TestRadiusIntroNoRadius:
    def test_returns_string(self):
        result = radius_intro_no_radius()
        assert isinstance(result, str)
        assert len(result) > 0


class TestRadiusIntroWithRadius:
    def test_with_radius(self):
        result = radius_intro_with_radius(saved_radius=50)
        assert isinstance(result, str)
        assert '50' in result


class TestRadiusAskValue:
    def test_no_saved_radius(self):
        result = radius_ask_value(saved_radius=None)
        assert isinstance(result, str)
        assert len(result) > 0

    def test_with_saved_radius(self):
        result = radius_ask_value(saved_radius=75)
        assert isinstance(result, str)
        assert '75' in result


class TestRadiusSaved:
    def test_returns_string(self):
        result = radius_saved(radius=100)
        assert isinstance(result, str)
        assert '100' in result


class TestRadiusDeleted:
    def test_returns_string(self):
        result = radius_deleted()
        assert isinstance(result, str)
        assert len(result) > 0


class TestRadiusParseError:
    def test_returns_string(self):
        result = radius_parse_error()
        assert isinstance(result, str)
        assert len(result) > 0


# =============================================================================
# Coordinates
# =============================================================================


class TestCoordsIntro:
    def test_returns_string(self):
        result = coords_intro()
        assert isinstance(result, str)
        assert len(result) > 0


class TestCoordsAskManualInput:
    def test_returns_string(self):
        result = coords_ask_manual_input()
        assert isinstance(result, str)
        assert len(result) > 0


class TestCoordsSaved:
    def test_returns_string(self):
        result = coords_saved()
        assert isinstance(result, str)
        assert len(result) > 0


class TestCoordsDeleted:
    def test_returns_string(self):
        result = coords_deleted()
        assert isinstance(result, str)
        assert len(result) > 0


class TestCoordsNotSet:
    def test_returns_string(self):
        result = coords_not_set()
        assert isinstance(result, str)
        assert len(result) > 0


class TestCoordsParseError:
    def test_returns_string(self):
        result = coords_parse_error()
        assert isinstance(result, str)
        assert len(result) > 0


# =============================================================================
# Forum Linking
# =============================================================================


class TestForumLinkIntro:
    def test_returns_string(self):
        result = forum_link_intro()
        assert isinstance(result, str)
        assert len(result) > 0


class TestForumLinkChecking:
    def test_returns_string(self):
        result = forum_link_checking()
        assert isinstance(result, str)
        assert len(result) > 0


class TestForumLinkInvalid:
    def test_returns_string(self):
        result = forum_link_invalid()
        assert isinstance(result, str)
        assert len(result) > 0


class TestForumLinkAskRetry:
    def test_returns_string(self):
        result = forum_link_ask_retry()
        assert isinstance(result, str)
        assert len(result) > 0


class TestForumLinkVerified:
    def test_returns_string(self):
        result = forum_link_verified()
        assert isinstance(result, str)
        assert len(result) > 0


class TestForumAlreadyLinked:
    def test_returns_string(self):
        result = forum_already_linked(forum_username='test_user', forum_user_id=42)
        assert isinstance(result, str)
        assert 'test_user' in result


# =============================================================================
# VK Linking
# =============================================================================


class TestVkLinkIntro:
    def test_returns_string(self):
        result = vk_link_intro()
        assert isinstance(result, str)
        assert len(result) > 0


class TestVkAlreadyLinked:
    def test_returns_string(self):
        result = vk_already_linked()
        assert isinstance(result, str)
        assert len(result) > 0


class TestVkLinkInstructions:
    def test_returns_string(self):
        result = vk_link_instructions(invite_text='test_invite_123')
        assert isinstance(result, str)
        assert 'test_invite_123' in result


# =============================================================================
# Search Following
# =============================================================================


class TestSearchFollowModeOn:
    def test_returns_string(self):
        result = search_follow_mode_on()
        assert isinstance(result, str)
        assert len(result) > 0


class TestSearchFollowModeOff:
    def test_returns_string(self):
        result = search_follow_mode_off()
        assert isinstance(result, str)
        assert len(result) > 0


class TestSearchFollowIntro:
    def test_returns_string(self):
        result = search_follow_intro()
        assert isinstance(result, str)
        assert len(result) > 0


class TestSearchFollowExperimentalIntro:
    def test_returns_string(self):
        result = search_follow_experimental_intro()
        assert isinstance(result, str)
        assert len(result) > 0


class TestNoActiveSearchesFound:
    def test_returns_string(self):
        result = no_active_searches_found()
        assert isinstance(result, str)
        assert len(result) > 0


# =============================================================================
# Search Listings
# =============================================================================


class TestActiveSearchesHeader:
    def test_returns_string(self):
        result = active_searches_header(region_name='Московская область')
        assert isinstance(result, str)
        assert 'Московская область' in result


class TestActiveSearchesEmpty:
    def test_returns_string(self):
        result = active_searches_empty(region_name='Московская область')
        assert isinstance(result, str)
        assert len(result) > 0


class TestActiveSearchesTextHeader:
    def test_returns_string(self):
        result = active_searches_text_header(region_name='Московская область')
        assert isinstance(result, str)
        assert 'Московская область' in result


class TestLastSearchesHeader:
    def test_returns_string(self):
        result = last_searches_header(region_name='Московская область')
        assert isinstance(result, str)
        assert 'Московская область' in result


class TestLastSearchesTextHeader:
    def test_returns_string(self):
        result = last_searches_text_header(region_name='Московская область')
        assert isinstance(result, str)
        assert 'Московская область' in result


class TestLastSearchesError:
    def test_returns_string(self):
        result = last_searches_error(region_name='Московская область')
        assert isinstance(result, str)
        assert 'Московская область' in result


# =============================================================================
# Other Menu
# =============================================================================


class TestOtherMenuIntro:
    def test_returns_string(self):
        result = other_menu_intro()
        assert isinstance(result, str)
        assert len(result) > 0


class TestPhotosIntro:
    def test_returns_string(self):
        result = photos_intro()
        assert isinstance(result, str)
        assert len(result) > 0


class TestFirstSearchIntro:
    def test_returns_string(self):
        result = first_search_intro()
        assert isinstance(result, str)
        assert len(result) > 0


class TestCommunityIntro:
    def test_returns_string(self):
        result = community_intro()
        assert isinstance(result, str)
        assert len(result) > 0


class TestMapIntro:
    def test_returns_string(self):
        result = map_intro()
        assert isinstance(result, str)
        assert len(result) > 0


# =============================================================================
# Help
# =============================================================================


class TestHelpNoThanks:
    def test_returns_string(self):
        result = help_no_thanks()
        assert isinstance(result, str)
        assert len(result) > 0


class TestHelpYesPlease:
    def test_returns_string(self):
        result = help_yes_please()
        assert isinstance(result, str)
        assert len(result) > 0


# =============================================================================
# Unsupported
# =============================================================================


class TestUnsupportedMedia:
    def test_returns_string(self):
        result = unsupported_media()
        assert isinstance(result, str)
        assert len(result) > 0


class TestUnsupportedContact:
    def test_returns_string(self):
        result = unsupported_contact()
        assert isinstance(result, str)
        assert len(result) > 0


# =============================================================================
# Utility
# =============================================================================


class TestBackToMainMenu:
    def test_returns_string(self):
        result = back_to_main_menu()
        assert isinstance(result, str)
        assert len(result) > 0


class TestUnknownCommand:
    def test_returns_string(self):
        result = unknown_command()
        assert isinstance(result, str)
        assert len(result) > 0
