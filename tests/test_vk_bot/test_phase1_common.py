"""Tests for VK Bot common module — data models and URL constants.

These tests cover:
- VKMessage Pydantic model
- VKHandlerContext class
- URL constants (SEARCH_URL_PREFIX, FORUM_FOLDER_PREFIX, etc.)
- get_invite_from_message() invite text parser
"""

from unittest.mock import MagicMock

from fakes import FakeVKMessageSender

from _dependencies.models import DialogState
from vk_bot._utils.common import (
    VKHandlerContext,
    VKMessage,
    get_invite_from_message,
)
from vk_bot._utils.services.message_formatter import (
    FORUM_FOLDER_PREFIX,
    LA_HOTLINE_PHONE,
    LA_WEBSITE,
    SEARCH_URL_PREFIX,
)

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
# VKHandlerContext
# ═══════════════════════════════════════════════════════════════════════════════


class TestVKHandlerContext:
    """VKHandlerContext — context object passed to every handler."""

    def test_creates_with_minimal_args(self, vk_message):
        """Can create a context with minimal required args."""
        msg = vk_message(text='hello')
        sender = FakeVKMessageSender()
        ctx = VKHandlerContext(
            message=msg,
            user_id=12345,
            state=None,
            sender=sender,  # type: ignore[arg-type]
            db=MagicMock(),
        )
        assert ctx.message.text == 'hello'
        assert ctx.user_id == 12345
        assert ctx.state is None
        assert ctx.is_consumed is False

    def test_creates_with_state(self, vk_message):
        """Can create a context with a dialog state."""
        msg = vk_message(text='50')
        sender = FakeVKMessageSender()
        ctx = VKHandlerContext(
            message=msg,
            user_id=12345,
            state=DialogState.radius_input,
            sender=sender,  # type: ignore[arg-type]
            db=MagicMock(),
        )
        assert ctx.state == DialogState.radius_input

    def test_reply_marks_as_consumed(self, vk_message):
        """Calling .reply() sets is_consumed to True."""
        msg = vk_message(text='hello', user_id=12345, peer_id=12345)
        sender = FakeVKMessageSender()
        ctx = VKHandlerContext(
            message=msg,
            user_id=12345,
            state=None,
            sender=sender,  # type: ignore[arg-type]
            db=MagicMock(),
        )
        ctx.reply(text='Hello!')
        assert ctx.is_consumed is True
        assert len(sender.sent_messages) == 1
        assert sender.sent_messages[0].text == 'Hello!'

    def test_edit_marks_as_consumed(self, vk_message):
        """Calling .edit() sets is_consumed to True."""
        msg = vk_message(text='hello', user_id=12345, peer_id=12345)
        sender = FakeVKMessageSender()
        ctx = VKHandlerContext(
            message=msg,
            user_id=12345,
            state=None,
            sender=sender,  # type: ignore[arg-type]
            db=MagicMock(),
        )
        ctx.edit(text='Edited!', conversation_message_id=42)
        assert ctx.is_consumed is True
        assert len(sender.edited_messages) == 1
        assert sender.edited_messages[0].text == 'Edited!'

    def test_answer_callback_does_not_mark_consumed(self, vk_message):
        """Calling .answer_callback() does NOT set is_consumed."""
        msg = vk_message(text='hello', user_id=12345, peer_id=12345, event_id='evt_001')
        sender = FakeVKMessageSender()
        ctx = VKHandlerContext(
            message=msg,
            user_id=12345,
            state=None,
            sender=sender,  # type: ignore[arg-type]
            db=MagicMock(),
        )
        ctx.answer_callback(event_data={'type': 'show_snackbar', 'text': 'OK'})
        assert ctx.is_consumed is False
        assert len(sender.callback_answers) == 1

    def test_send_message_does_not_mark_consumed(self, vk_message):
        """Calling .send_message() does NOT set is_consumed."""
        msg = vk_message(text='hello', user_id=12345, peer_id=12345)
        sender = FakeVKMessageSender()
        ctx = VKHandlerContext(
            message=msg,
            user_id=12345,
            state=None,
            sender=sender,  # type: ignore[arg-type]
            db=MagicMock(),
        )
        ctx.send_message(text='Extra message')
        assert ctx.is_consumed is False
        assert len(sender.sent_messages) == 1

    def test_set_state_and_clear_state(self, vk_message):
        """Can set and clear dialog state."""
        msg = vk_message(text='hello')
        sender = FakeVKMessageSender()
        db = MagicMock()
        ctx = VKHandlerContext(
            message=msg,
            user_id=12345,
            state=None,
            sender=sender,  # type: ignore[arg-type]
            db=db,
        )
        ctx.set_state(DialogState.radius_input)
        db.set_user_state.assert_called_once_with(12345, DialogState.radius_input)
        ctx.clear_state()
        db.clear_user_state.assert_called_once_with(12345)

    def test_delete_message(self, vk_message):
        """Can delete messages."""
        msg = vk_message(text='hello', user_id=12345, peer_id=12345)
        sender = FakeVKMessageSender()
        ctx = VKHandlerContext(
            message=msg,
            user_id=12345,
            state=None,
            sender=sender,  # type: ignore[arg-type]
            db=MagicMock(),
        )
        ctx.delete_message(message_ids=[42, 43])
        assert len(sender.deleted_messages) == 1
        assert sender.deleted_messages[0].message_ids == [42, 43]

    def test_db_property(self, vk_message):
        """.db property returns the db instance."""
        msg = vk_message(text='hello')
        sender = FakeVKMessageSender()
        db = MagicMock()
        ctx = VKHandlerContext(
            message=msg,
            user_id=12345,
            state=None,
            sender=sender,  # type: ignore[arg-type]
            db=db,
        )
        assert ctx.db is db


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
