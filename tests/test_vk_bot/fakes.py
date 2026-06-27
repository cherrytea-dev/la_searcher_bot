"""Fake (in-memory) implementations of VK Bot dependencies for testing.

These replace MagicMock-based fixtures with real Python objects that
record calls in-memory. Benefits:

- Type-safe: mypy can verify method signatures
- No ``.return_value`` chains: ``fake.sent_messages[0]['text']`` instead of
  ``mock.return_value.send_message.call_args[0][1]``
- Explicit state: check ``len(fake.sent_messages)`` instead of
  ``mock.send_message.assert_called_once()``
- Reusable across all test modules in ``tests/test_vk_bot/``
"""

from __future__ import annotations

from dataclasses import dataclass

# ═══════════════════════════════════════════════════════════════════════════════
# FakeVKMessageSender
# ═══════════════════════════════════════════════════════════════════════════════


@dataclass
class SentMessage:
    """Record of a single ``send_message()`` call."""

    peer_id: int
    text: str
    keyboard: dict | None = None
    attachment: str = ''
    dont_parse_links: bool = False


@dataclass
class EditedMessage:
    """Record of a single ``edit_message()`` call."""

    peer_id: int
    message_id: int | None = None
    text: str = ''
    keyboard: dict | None = None
    conversation_message_id: int | None = None


@dataclass
class CallbackAnswer:
    """Record of a single ``send_callback_answer()`` call."""

    event_id: str
    user_id: int
    peer_id: int
    event_data: dict | None = None


@dataclass
class DeletedMessage:
    """Record of a single ``delete_message()`` call."""

    peer_id: int
    message_ids: list[int]


@dataclass
class SentWithKeyboard:
    """Record of a single ``send_with_keyboard()`` call."""

    peer_id: int
    text: str
    buttons: list[str]
    color: str = 'secondary'


class FakeVKMessageSender:
    """In-memory fake that records all calls instead of sending to VK API.

    Usage in tests::

        fake = FakeVKMessageSender()
        # Inject into the module under test
        with patch('vk_bot._utils.account_linking.vk_sender', lambda: fake):
            ...

    Assertions::

        assert len(fake.sent_messages) == 1
        assert fake.sent_messages[0].text == 'expected text'
        assert fake.sent_messages[0].keyboard is not None

        assert len(fake.edited_messages) == 0
        assert len(fake.callback_answers) == 1
        assert fake.callback_answers[0].event_id == 'evt_001'
    """

    def __init__(self) -> None:
        self.sent_messages: list[SentMessage] = []
        self.edited_messages: list[EditedMessage] = []
        self.callback_answers: list[CallbackAnswer] = []
        self.deleted_messages: list[DeletedMessage] = []
        self.sent_with_keyboard: list[SentWithKeyboard] = []

        # Configurable return values
        self._next_message_id: int = 42
        self._edit_ok: bool = True
        self._callback_ok: bool = True
        self._delete_ok: bool = True

    # ── Configuration helpers ──────────────────────────────────────────────

    def set_next_message_id(self, message_id: int) -> None:
        """Override the fake message_id returned by ``send_message()``."""
        self._next_message_id = message_id

    def set_edit_result(self, ok: bool) -> None:
        """Override whether ``edit_message()`` returns True or False."""
        self._edit_ok = ok

    def set_callback_result(self, ok: bool) -> None:
        """Override whether ``send_callback_answer()`` returns True or False."""
        self._callback_ok = ok

    # ── Public methods matching VKMessageSender interface ──────────────────

    def send_message(
        self,
        peer_id: int,
        text: str,
        keyboard: dict | None = None,
        attachment: str = '',
        dont_parse_links: bool = False,
    ) -> int | None:
        """Record a sent message and return a fake message_id."""
        self.sent_messages.append(
            SentMessage(
                peer_id=peer_id,
                text=text,
                keyboard=keyboard,
                attachment=attachment,
                dont_parse_links=dont_parse_links,
            )
        )
        return self._next_message_id

    def edit_message(
        self,
        peer_id: int,
        message_id: int | None = None,
        text: str = '',
        keyboard: dict | None = None,
        conversation_message_id: int | None = None,
    ) -> bool:
        """Record an edited message."""
        self.edited_messages.append(
            EditedMessage(
                peer_id=peer_id,
                message_id=message_id,
                text=text,
                keyboard=keyboard,
                conversation_message_id=conversation_message_id,
            )
        )
        return self._edit_ok

    def delete_message(self, peer_id: int, message_ids: list[int]) -> bool:
        """Record a deleted message."""
        self.deleted_messages.append(
            DeletedMessage(
                peer_id=peer_id,
                message_ids=message_ids,
            )
        )
        return self._delete_ok

    def send_callback_answer(
        self,
        event_id: str,
        user_id: int,
        peer_id: int,
        event_data: dict | None = None,
    ) -> bool:
        """Record a callback answer."""
        self.callback_answers.append(
            CallbackAnswer(
                event_id=event_id,
                user_id=user_id,
                peer_id=peer_id,
                event_data=event_data,
            )
        )
        return self._callback_ok

    def send_with_keyboard(
        self,
        peer_id: int,
        text: str,
        buttons: list[str],
        color: str = 'secondary',
    ) -> int | None:
        """Record a message sent with a keyboard."""
        self.sent_with_keyboard.append(
            SentWithKeyboard(
                peer_id=peer_id,
                text=text,
                buttons=buttons,
                color=color,
            )
        )
        return self._next_message_id

    # ── Convenience assertions ─────────────────────────────────────────────

    @property
    def last_sent(self) -> SentMessage | None:
        """Last sent message, or None if no messages were sent."""
        return self.sent_messages[-1] if self.sent_messages else None

    @property
    def last_edited(self) -> EditedMessage | None:
        """Last edited message, or None if no messages were edited."""
        return self.edited_messages[-1] if self.edited_messages else None

    @property
    def last_callback(self) -> CallbackAnswer | None:
        """Last callback answer, or None if no callbacks were answered."""
        return self.callback_answers[-1] if self.callback_answers else None

    @property
    def last_sent_keyboard_labels(self) -> list[str]:
        """Extract button labels from the last sent message's keyboard.

        Handles both VK API keyboard dict format and SentWithKeyboard format.
        Returns an empty list if no keyboard was sent.
        """
        # Check send_with_keyboard first (legacy path)
        if self.sent_with_keyboard:
            return list(self.sent_with_keyboard[-1].buttons)
        # Check send_message with keyboard dict
        if self.last_sent is not None and self.last_sent.keyboard is not None:
            labels: list[str] = []
            for row in self.last_sent.keyboard.get('buttons', []):
                for btn in row:
                    label = btn.get('action', {}).get('label', '')
                    if label:
                        labels.append(label)
            return labels
        return []

    def assert_sent(self, count: int = 1) -> None:
        """Assert that exactly ``count`` messages were sent."""
        assert len(self.sent_messages) == count, f'Expected {count} sent message(s), got {len(self.sent_messages)}'

    def assert_edited(self, count: int = 1) -> None:
        """Assert that exactly ``count`` messages were edited."""
        assert (
            len(self.edited_messages) == count
        ), f'Expected {count} edited message(s), got {len(self.edited_messages)}'

    def assert_callback_answered(self, count: int = 1) -> None:
        """Assert that exactly ``count`` callback answers were sent."""
        assert (
            len(self.callback_answers) == count
        ), f'Expected {count} callback answer(s), got {len(self.callback_answers)}'

    def assert_sent_text(self, text: str) -> None:
        """Assert that the last sent message contains ``text`` (case-insensitive)."""
        assert self.last_sent is not None, 'No messages were sent'
        assert (
            text.lower() in self.last_sent.text.lower()
        ), f'Expected text "{text}" in last sent message, got "{self.last_sent.text}"'

    def assert_sent_with_keyboard(self) -> None:
        """Assert that the last sent message had a keyboard."""
        assert self.last_sent is not None, 'No messages were sent'
        assert self.last_sent.keyboard is not None, 'Last sent message has no keyboard'

    def assert_edited_text(self, text: str) -> None:
        """Assert that the last edited message contains ``text``."""
        assert self.last_edited is not None, 'No messages were edited'
        assert (
            text in self.last_edited.text
        ), f'Expected text "{text}" in last edited message, got "{self.last_edited.text}"'

    def assert_callback_snackbar(self, text: str) -> None:
        """Assert that the last callback answer was a snackbar with ``text``."""
        assert self.last_callback is not None, 'No callback answers were sent'
        assert self.last_callback.event_data is not None, 'Last callback has no event_data'
        assert (
            self.last_callback.event_data.get('type') == 'show_snackbar'
        ), f'Expected show_snackbar, got {self.last_callback.event_data.get("type")}'
        assert text in self.last_callback.event_data.get(
            'text', ''
        ), f'Expected snackbar text "{text}", got "{self.last_callback.event_data.get("text")}"'

    def assert_no_calls(self) -> None:
        """Assert that no VK API calls were made at all."""
        assert not self.sent_messages, f'Expected no sent messages, got {len(self.sent_messages)}'
        assert not self.edited_messages, f'Expected no edited messages, got {len(self.edited_messages)}'
        assert not self.callback_answers, f'Expected no callback answers, got {len(self.callback_answers)}'
        assert not self.deleted_messages, f'Expected no deleted messages, got {len(self.deleted_messages)}'

    def reset(self) -> None:
        """Clear all recorded calls."""
        self.sent_messages.clear()
        self.edited_messages.clear()
        self.callback_answers.clear()
        self.deleted_messages.clear()
        self.sent_with_keyboard.clear()
