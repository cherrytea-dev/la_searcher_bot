"""Tests for InlineButtonCallbackData serialization/deserialization.

Covers the compact pipe-separated format (current) and the legacy JSON
format (pre-2026-07-08, commit 9b3be36) — old inline buttons keep living
in users' chats, and tapping them sends the legacy callback_data.
Not parsing it used to fall through to the «не понимаю такой команды»
fallback (issue #961).
"""

import json

import pytest

from communicate._utils.common import InlineButtonCallbackData


class TestSerialize:
    def test_follow_mode_on_button(self):
        cb = InlineButtonCallbackData(action='search_follow_mode_on')
        assert cb.as_str() == '|search_follow_mode_on||'

    def test_follow_toggle_with_hash(self):
        cb = InlineButtonCallbackData(action='search_follow_mode', hash=12345)
        assert cb.as_str() == '|search_follow_mode|12345|'

    def test_with_keyboard_name_and_letter(self):
        cb = InlineButtonCallbackData(keyboard_name='geo', action='А', letter_to_show='А')
        assert cb.as_str() == 'geo|А||А'


class TestDeserializeCompact:
    @pytest.mark.parametrize(
        ('data', 'expected_action', 'expected_hash'),
        [
            ('|search_follow_mode_on||', 'search_follow_mode_on', None),
            ('|search_follow_mode|12345|', 'search_follow_mode', 12345),
            ('|search_follow_clear||', 'search_follow_clear', None),
        ],
    )
    def test_roundtrip(self, data, expected_action, expected_hash):
        parsed = InlineButtonCallbackData.deserialize(data)
        assert parsed.action == expected_action
        assert parsed.hash == expected_hash

    def test_numeric_action(self):
        parsed = InlineButtonCallbackData.deserialize('|5||')
        assert parsed.action == 5

    def test_keyboard_name_preserved(self):
        parsed = InlineButtonCallbackData.deserialize('geo|А||А')
        assert parsed.keyboard_name == 'geo'
        assert parsed.action == 'А'
        assert parsed.letter_to_show == 'А'


class TestDeserializeLegacyJson:
    """Legacy JSON callback_data (pre-9b3be36) must still be recognized."""

    def test_simple_action(self):
        data = json.dumps({'act': 'search_follow_mode_on'})
        parsed = InlineButtonCallbackData.deserialize(data)
        assert parsed.action == 'search_follow_mode_on'
        assert parsed.keyboard_name is None

    def test_action_with_hash(self):
        data = json.dumps({'act': 'search_follow_mode', 'hash': 12345})
        parsed = InlineButtonCallbackData.deserialize(data)
        assert parsed.action == 'search_follow_mode'
        assert parsed.hash == 12345

    def test_full_payload(self):
        data = json.dumps({'kb': 'geo', 'act': 'А', 'bs': 'А'})
        parsed = InlineButtonCallbackData.deserialize(data)
        assert parsed.keyboard_name == 'geo'
        assert parsed.action == 'А'
        assert parsed.letter_to_show == 'А'

    def test_long_form_keys(self):
        data = json.dumps({'keyboard_name': 'geo', 'action': 'close'})
        parsed = InlineButtonCallbackData.deserialize(data)
        assert parsed.keyboard_name == 'geo'
        assert parsed.action == 'close'

    def test_invalid_json_falls_back_to_none_action(self):
        parsed = InlineButtonCallbackData.deserialize('{not valid json}')
        assert parsed.action is None
