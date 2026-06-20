"""Tests for VK Bot common module — data models and URL constants.

These tests cover:
- VKMessage Pydantic model
- VKHandlerResult dataclass
- URL constants (SEARCH_URL_PREFIX, FORUM_FOLDER_PREFIX, etc.)
- get_invite_from_message() invite text parser
"""

from vk_bot._utils.common import (
    FORUM_FOLDER_PREFIX,
    LA_HOTLINE_PHONE,
    LA_WEBSITE,
    SEARCH_URL_PREFIX,
    VKHandlerResult,
    VKMessage,
    get_invite_from_message,
)
from vk_bot._utils.database import DialogState

# ═══════════════════════════════════════════════════════════════════════════════
# VKMessage
# ═══════════════════════════════════════════════════════════════════════════════


class TestVKMessage:
    """VKMessage Pydantic model."""

    def test_create_minimal(self):
        msg = VKMessage(text='hello', user_id=123, peer_id=456)
        assert msg.text == 'hello'
        assert msg.user_id == 123
        assert msg.peer_id == 456
        assert msg.message_id is None
        assert msg.payload is None
        assert msg.event_id is None

    def test_create_full(self):
        msg = VKMessage(
            text='hello',
            user_id=123,
            peer_id=456,
            message_id=789,
            payload='{"button":"test"}',
            event_id='evt_001',
        )
        assert msg.message_id == 789
        assert msg.payload == '{"button":"test"}'
        assert msg.event_id == 'evt_001'

    def test_serialization(self):
        msg = VKMessage(text='hello', user_id=123, peer_id=456)
        data = msg.model_dump()
        assert data['text'] == 'hello'
        assert data['user_id'] == 123
        assert data['peer_id'] == 456

    def test_deserialization(self):
        data = {'text': 'hello', 'user_id': 123, 'peer_id': 456, 'message_id': 789}
        msg = VKMessage.model_validate(data)
        assert msg.text == 'hello'
        assert msg.message_id == 789


# ═══════════════════════════════════════════════════════════════════════════════
# get_invite_from_message
# ═══════════════════════════════════════════════════════════════════════════════


class TestGetInviteFromMessage:
    """get_invite_from_message() — invite text parser."""

    def test_valid_invite(self):
        result = get_invite_from_message('telegram_id: 12345 invite_hash: abcdef123456')
        assert result == (12345, 'abcdef123456')

    def test_valid_invite_with_extra_text(self):
        result = get_invite_from_message('some text before telegram_id: 999 invite_hash: xyz789 and after')
        assert result == (999, 'xyz789')

    def test_valid_invite_case_insensitive(self):
        result = get_invite_from_message('TELEGRAM_ID: 555 INVITE_HASH: ABCdef')
        assert result == (555, 'ABCdef')

    def test_invalid_no_match(self):
        result = get_invite_from_message('hello world')
        assert result == (None, None)

    def test_invalid_partial_match(self):
        result = get_invite_from_message('telegram_id: abc invite_hash: xyz')
        assert result == (None, None)

    def test_invalid_empty_string(self):
        result = get_invite_from_message('')
        assert result == (None, None)


# ═══════════════════════════════════════════════════════════════════════════════
# VKHandlerResult
# ═══════════════════════════════════════════════════════════════════════════════


class TestVKHandlerResult:
    """VKHandlerResult dataclass."""

    def test_minimal(self):
        result = VKHandlerResult(text='hello')
        assert result.text == 'hello'
        assert result.keyboard is None
        assert result.new_state is None
        assert result.edit_message_id is None
        assert result.attachment is None

    def test_full(self):
        keyboard = {'one_time': False, 'inline': False, 'buttons': []}
        result = VKHandlerResult(
            text='hello',
            keyboard=keyboard,
            new_state=DialogState.radius_input,
            edit_message_id=42,
            attachment='photo123',
        )
        assert result.keyboard == keyboard
        assert result.new_state == DialogState.radius_input
        assert result.edit_message_id == 42
        assert result.attachment == 'photo123'

    def test_default_factory(self):
        r1 = VKHandlerResult(text='a')
        r2 = VKHandlerResult(text='b')
        assert r1.keyboard is None
        assert r2.keyboard is None


# ═══════════════════════════════════════════════════════════════════════════════
# URL constants
# ═══════════════════════════════════════════════════════════════════════════════


class TestURLConstants:
    """URL constants from common.py."""

    def test_search_url_prefix(self):
        assert SEARCH_URL_PREFIX == 'https://lizaalert.org/forum/viewtopic.php?t='

    def test_forum_folder_prefix(self):
        assert FORUM_FOLDER_PREFIX == 'https://lizaalert.org/forum/viewforum.php?f='

    def test_hotline_phone(self):
        assert LA_HOTLINE_PHONE == '8 800 700-54-52'

    def test_website(self):
        assert LA_WEBSITE == 'https://lizaalert.org'
