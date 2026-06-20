"""Tests for the platform-independent message formatter module."""

import vk_bot._utils.services.message_formatter as mf

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
# Settings Menu
# =============================================================================


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
