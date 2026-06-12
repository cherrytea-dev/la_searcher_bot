"""Tests for the platform-independent message formatter module."""

import _dependencies.services.message_formatter as mf

# =============================================================================
# Constants
# =============================================================================


class TestConstants:
    def test_search_url_prefix(self):
        assert mf.SEARCH_URL_PREFIX == 'https://lizaalert.org/forum/viewtopic.php?t='

    def test_la_bot_chat_url(self):
        # Actual value from message_formatter.py
        assert mf.LA_BOT_CHAT_URL.startswith('https://t.me/')

    def test_la_photos_channel_url(self):
        # Actual value from message_formatter.py
        assert mf.LA_PHOTOS_CHANNEL_URL.startswith('https://t.me/')

    def test_la_dev_chat_url(self):
        # Actual value from message_formatter.py
        assert mf.LA_DEV_CHAT_URL.startswith('https://t.me/')

    def test_la_hotline_phone(self):
        # Actual value from message_formatter.py
        assert '8' in mf.LA_HOTLINE_PHONE
        assert '700' in mf.LA_HOTLINE_PHONE
        assert '54-52' in mf.LA_HOTLINE_PHONE


# =============================================================================
# SearchDisplayItem
# =============================================================================


class TestSearchDisplayItem:
    def test_minimal_item(self):
        item = mf.SearchDisplayItem(
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
        item = mf.SearchDisplayItem(
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
        result = mf.welcome_new_user()
        assert isinstance(result, str)
        assert len(result) > 0
        assert 'ЛизаАлерт' in result or 'поисково-спасательный' in result


class TestWelcomeBackUser:
    def test_returns_string(self):
        result = mf.welcome_back_user()
        assert isinstance(result, str)
        assert len(result) > 0


class TestOnboardingCompletedMessage:
    def test_returns_string(self):
        result = mf.onboarding_completed_message()
        assert isinstance(result, str)
        assert len(result) > 0


class TestAskRole:
    def test_returns_string(self):
        result = mf.ask_role()
        assert isinstance(result, str)
        assert len(result) > 0


class TestRoleRelativeInstructions:
    def test_returns_string(self):
        result = mf.role_relative_instructions()
        assert isinstance(result, str)
        assert len(result) > 0


class TestRoleVolunteerInstructions:
    def test_returns_string(self):
        result = mf.role_volunteer_instructions()
        assert isinstance(result, str)
        assert len(result) > 0


class TestRoleOtherAskRegion:
    def test_returns_string(self):
        result = mf.role_other_ask_region()
        assert isinstance(result, str)
        assert len(result) > 0


# =============================================================================
# Region Selection
# =============================================================================


class TestRegionSelectionIntro:
    def test_returns_string(self):
        result = mf.region_selection_intro()
        assert isinstance(result, str)
        assert len(result) > 0


class TestRegionSelectionHelp:
    def test_returns_string(self):
        result = mf.region_selection_help()
        assert isinstance(result, str)
        assert len(result) > 0


class TestForceSetRegion:
    def test_returns_string(self):
        result = mf.force_set_region()
        assert isinstance(result, str)
        assert len(result) > 0


class TestRegionSelectionClosed:
    def test_returns_string(self):
        result = mf.region_selection_closed()
        assert isinstance(result, str)
        assert len(result) > 0


class TestRegionSelectionCantRemoveLast:
    def test_returns_string(self):
        result = mf.region_selection_cant_remove_last()
        assert isinstance(result, str)
        assert len(result) > 0


# =============================================================================
# Settings Menu
# =============================================================================


class TestSettingsMenuIntro:
    def test_returns_string(self):
        result = mf.settings_menu_intro()
        assert isinstance(result, str)
        assert len(result) > 0


class TestComposeSettingsCompletenessMessage:
    def test_all_complete(self):
        result = mf.compose_settings_completeness_message(
            has_notif_type=True,
            has_region=True,
            has_coords=True,
            has_radius=True,
            has_age=True,
            has_forum=True,
        )
        assert result is None

    def test_none_complete(self):
        result = mf.compose_settings_completeness_message(
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
        result = mf.compose_settings_completeness_message(
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
        result = mf.notif_settings_intro()
        assert isinstance(result, str)
        assert len(result) > 0


class TestNotifSettingsCurrentPrefs:
    def test_with_prefs(self):
        result = mf.notif_settings_current_prefs('текст уведомлений')
        assert isinstance(result, str)
        assert len(result) > 0


class TestNotifSettingsNoPrefs:
    def test_returns_string(self):
        result = mf.notif_settings_no_prefs()
        assert isinstance(result, str)
        assert len(result) > 0


class TestNotifPrefNames:
    def test_contains_expected_keys(self):
        assert 'all' in mf.NOTIF_PREF_NAMES
        assert 'new_searches' in mf.NOTIF_PREF_NAMES
        assert 'status_changes' in mf.NOTIF_PREF_NAMES
        assert 'title_changes' in mf.NOTIF_PREF_NAMES
        assert 'comments_changes' in mf.NOTIF_PREF_NAMES
        assert 'inforg_comments' in mf.NOTIF_PREF_NAMES
        assert 'first_post_changes' in mf.NOTIF_PREF_NAMES
        assert 'all_in_followed_search' in mf.NOTIF_PREF_NAMES
        assert 'field_trips_new' in mf.NOTIF_PREF_NAMES
        assert 'field_trips_change' in mf.NOTIF_PREF_NAMES
        assert 'coords_change' in mf.NOTIF_PREF_NAMES
        assert 'bot_news' in mf.NOTIF_PREF_NAMES

    def test_values_are_strings(self):
        for key, value in mf.NOTIF_PREF_NAMES.items():
            assert isinstance(key, str)
            assert isinstance(value, str)


class TestFormatNotifPrefsList:
    def test_empty_list(self):
        result = mf.format_notif_prefs_list([])
        assert isinstance(result, str)

    def test_with_items(self):
        result = mf.format_notif_prefs_list(['new_searches', 'status_changes'])
        assert isinstance(result, str)
        assert len(result) > 0


class TestNotifFunctions:
    def test_notif_all_enabled(self):
        result = mf.notif_all_enabled()
        assert isinstance(result, str)
        assert len(result) > 0

    def test_notif_new_search_enabled(self):
        result = mf.notif_new_search_enabled()
        assert isinstance(result, str)
        assert len(result) > 0

    def test_notif_status_change_enabled(self):
        result = mf.notif_status_change_enabled()
        assert isinstance(result, str)
        assert len(result) > 0

    def test_notif_inforg_comments_enabled(self):
        result = mf.notif_inforg_comments_enabled()
        assert isinstance(result, str)
        assert len(result) > 0

    def test_notif_field_trip_new_enabled(self):
        result = mf.notif_field_trip_new_enabled()
        assert isinstance(result, str)
        assert len(result) > 0

    def test_notif_field_trip_change_enabled(self):
        result = mf.notif_field_trip_change_enabled()
        assert isinstance(result, str)
        assert len(result) > 0

    def test_notif_coords_change_enabled(self):
        result = mf.notif_coords_change_enabled()
        assert isinstance(result, str)
        assert len(result) > 0

    def test_notif_first_post_change_enabled(self):
        result = mf.notif_first_post_change_enabled()
        assert isinstance(result, str)
        assert len(result) > 0


# =============================================================================
# Topic Type
# =============================================================================


class TestTopicTypeIntro:
    def test_returns_string(self):
        result = mf.topic_type_intro()
        assert isinstance(result, str)
        assert len(result) > 0


# =============================================================================
# Age Settings
# =============================================================================


class TestAgeSettingsIntro:
    def test_first_visit(self):
        result = mf.age_settings_intro(first_visit=True)
        assert isinstance(result, str)
        assert len(result) > 0

    def test_not_first_visit(self):
        result = mf.age_settings_intro(first_visit=False)
        assert isinstance(result, str)
        assert len(result) > 0


class TestAgeSaved:
    def test_returns_string(self):
        result = mf.age_saved()
        assert isinstance(result, str)
        assert len(result) > 0


# =============================================================================
# Radius Settings
# =============================================================================


class TestRadiusIntroNoRadius:
    def test_returns_string(self):
        result = mf.radius_intro_no_radius()
        assert isinstance(result, str)
        assert len(result) > 0


class TestRadiusIntroWithRadius:
    def test_with_radius(self):
        result = mf.radius_intro_with_radius(saved_radius=50)
        assert isinstance(result, str)
        assert '50' in result


class TestRadiusAskValue:
    def test_no_saved_radius(self):
        result = mf.radius_ask_value(saved_radius=None)
        assert isinstance(result, str)
        assert len(result) > 0

    def test_with_saved_radius(self):
        result = mf.radius_ask_value(saved_radius=75)
        assert isinstance(result, str)
        assert '75' in result


class TestRadiusSaved:
    def test_returns_string(self):
        result = mf.radius_saved(radius=100)
        assert isinstance(result, str)
        assert '100' in result


class TestRadiusDeleted:
    def test_returns_string(self):
        result = mf.radius_deleted()
        assert isinstance(result, str)
        assert len(result) > 0


class TestRadiusParseError:
    def test_returns_string(self):
        result = mf.radius_parse_error()
        assert isinstance(result, str)
        assert len(result) > 0


# =============================================================================
# Coordinates
# =============================================================================


class TestCoordsIntro:
    def test_returns_string(self):
        result = mf.coords_intro()
        assert isinstance(result, str)
        assert len(result) > 0


class TestCoordsAskManualInput:
    def test_returns_string(self):
        result = mf.coords_ask_manual_input()
        assert isinstance(result, str)
        assert len(result) > 0


class TestCoordsSaved:
    def test_returns_string(self):
        result = mf.coords_saved()
        assert isinstance(result, str)
        assert len(result) > 0


class TestCoordsDeleted:
    def test_returns_string(self):
        result = mf.coords_deleted()
        assert isinstance(result, str)
        assert len(result) > 0


class TestCoordsNotSet:
    def test_returns_string(self):
        result = mf.coords_not_set()
        assert isinstance(result, str)
        assert len(result) > 0


class TestCoordsParseError:
    def test_returns_string(self):
        result = mf.coords_parse_error()
        assert isinstance(result, str)
        assert len(result) > 0


# =============================================================================
# Forum Linking
# =============================================================================


class TestForumLinkIntro:
    def test_returns_string(self):
        result = mf.forum_link_intro()
        assert isinstance(result, str)
        assert len(result) > 0


class TestForumLinkChecking:
    def test_returns_string(self):
        result = mf.forum_link_checking()
        assert isinstance(result, str)
        assert len(result) > 0


class TestForumLinkInvalid:
    def test_returns_string(self):
        result = mf.forum_link_invalid()
        assert isinstance(result, str)
        assert len(result) > 0


class TestForumLinkAskRetry:
    def test_returns_string(self):
        result = mf.forum_link_ask_retry()
        assert isinstance(result, str)
        assert len(result) > 0


class TestForumLinkVerified:
    def test_returns_string(self):
        result = mf.forum_link_verified()
        assert isinstance(result, str)
        assert len(result) > 0


class TestForumAlreadyLinked:
    def test_returns_string(self):
        result = mf.forum_already_linked(forum_username='test_user', forum_user_id=42)
        assert isinstance(result, str)
        assert 'test_user' in result


# =============================================================================
# VK Linking
# =============================================================================


class TestVkLinkIntro:
    def test_returns_string(self):
        result = mf.vk_link_intro()
        assert isinstance(result, str)
        assert len(result) > 0


class TestVkAlreadyLinked:
    def test_returns_string(self):
        result = mf.vk_already_linked()
        assert isinstance(result, str)
        assert len(result) > 0


class TestVkLinkInstructions:
    def test_returns_string(self):
        result = mf.vk_link_instructions(invite_text='test_invite_123')
        assert isinstance(result, str)
        assert 'test_invite_123' in result


# =============================================================================
# Search Following
# =============================================================================


class TestSearchFollowModeOn:
    def test_returns_string(self):
        result = mf.search_follow_mode_on()
        assert isinstance(result, str)
        assert len(result) > 0


class TestSearchFollowModeOff:
    def test_returns_string(self):
        result = mf.search_follow_mode_off()
        assert isinstance(result, str)
        assert len(result) > 0


class TestSearchFollowIntro:
    def test_returns_string(self):
        result = mf.search_follow_intro()
        assert isinstance(result, str)
        assert len(result) > 0


class TestSearchFollowExperimentalIntro:
    def test_returns_string(self):
        result = mf.search_follow_experimental_intro()
        assert isinstance(result, str)
        assert len(result) > 0


class TestNoActiveSearchesFound:
    def test_returns_string(self):
        result = mf.no_active_searches_found()
        assert isinstance(result, str)
        assert len(result) > 0


# =============================================================================
# Search Listings
# =============================================================================


class TestActiveSearchesHeader:
    def test_returns_string(self):
        result = mf.active_searches_header(region_name='Московская область')
        assert isinstance(result, str)
        assert 'Московская область' in result


class TestActiveSearchesEmpty:
    def test_returns_string(self):
        result = mf.active_searches_empty(region_name='Московская область')
        assert isinstance(result, str)
        assert len(result) > 0


class TestActiveSearchesTextHeader:
    def test_returns_string(self):
        result = mf.active_searches_text_header(region_name='Московская область')
        assert isinstance(result, str)
        assert 'Московская область' in result


class TestLastSearchesHeader:
    def test_returns_string(self):
        result = mf.last_searches_header(region_name='Московская область')
        assert isinstance(result, str)
        assert 'Московская область' in result


class TestLastSearchesTextHeader:
    def test_returns_string(self):
        result = mf.last_searches_text_header(region_name='Московская область')
        assert isinstance(result, str)
        assert 'Московская область' in result


class TestLastSearchesError:
    def test_returns_string(self):
        result = mf.last_searches_error(region_name='Московская область')
        assert isinstance(result, str)
        assert 'Московская область' in result


# =============================================================================
# Other Menu
# =============================================================================


class TestOtherMenuIntro:
    def test_returns_string(self):
        result = mf.other_menu_intro()
        assert isinstance(result, str)
        assert len(result) > 0


class TestPhotosIntro:
    def test_returns_string(self):
        result = mf.photos_intro()
        assert isinstance(result, str)
        assert len(result) > 0


class TestFirstSearchIntro:
    def test_returns_string(self):
        result = mf.first_search_intro()
        assert isinstance(result, str)
        assert len(result) > 0


class TestCommunityIntro:
    def test_returns_string(self):
        result = mf.community_intro()
        assert isinstance(result, str)
        assert len(result) > 0


class TestMapIntro:
    def test_returns_string(self):
        result = mf.map_intro()
        assert isinstance(result, str)
        assert len(result) > 0


# =============================================================================
# Help
# =============================================================================


class TestHelpNoThanks:
    def test_returns_string(self):
        result = mf.help_no_thanks()
        assert isinstance(result, str)
        assert len(result) > 0


class TestHelpYesPlease:
    def test_returns_string(self):
        result = mf.help_yes_please()
        assert isinstance(result, str)
        assert len(result) > 0


# =============================================================================
# Unsupported
# =============================================================================


class TestUnsupportedMedia:
    def test_returns_string(self):
        result = mf.unsupported_media()
        assert isinstance(result, str)
        assert len(result) > 0


class TestUnsupportedContact:
    def test_returns_string(self):
        result = mf.unsupported_contact()
        assert isinstance(result, str)
        assert len(result) > 0


# =============================================================================
# Utility
# =============================================================================


class TestBackToMainMenu:
    def test_returns_string(self):
        result = mf.back_to_main_menu()
        assert isinstance(result, str)
        assert len(result) > 0


class TestUnknownCommand:
    def test_returns_string(self):
        result = mf.unknown_command()
        assert isinstance(result, str)
        assert len(result) > 0
