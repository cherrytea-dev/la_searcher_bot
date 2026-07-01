import json
import logging
import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Literal

from pydantic import BaseModel, field_validator

from _dependencies.models import DialogState

if TYPE_CHECKING:
    from .database import DBClient
    from .message_sending import VKMessageSender


class VKMessage(BaseModel):
    """Parsed incoming VK event data."""

    text: str
    user_id: int
    peer_id: int
    message_id: int | None = None
    conversation_message_id: int | None = None
    payload: str | None = None
    event_id: str | None = None

    @field_validator('payload', mode='before')
    @classmethod
    def _normalize_payload(cls, value: Any) -> str | None:
        """Normalize payload to string.

        VK Callback API may send payload as a JSON string or as a parsed dict.
        Normalize to string for consistent handling downstream.
        """
        if value is None:
            return None
        if isinstance(value, str):
            return value
        if isinstance(value, (dict, list)):
            return json.dumps(value, ensure_ascii=False)
        return str(value)

    @property
    def payload_as_dict(self) -> dict | None:
        """Parse ``payload`` JSON string into a dict.

        Returns ``None`` if payload is empty or not valid JSON.
        """
        if not self.payload:
            return None
        try:
            return json.loads(self.payload)
        except (json.JSONDecodeError, TypeError):
            return None


@dataclass
class SearchItem:
    """Formatted search for display in VK messages."""

    topic_id: int
    display_name: str
    status: str  # 'Ищем', 'НЖ', 'НП', 'СТОП', etc.
    status_emoji: str  # 🟠, ⚫, ✅, ⏹️, etc.
    time_text: str  # "3 дня", "1 неделю"
    age_text: str  # "45 лет" or ""
    distance_text: str  # "15 км ↗️" or ""
    is_followed: bool  # True if user follows this search
    is_blacklisted: bool  # True if user blacklisted this search


ButtonColor = Literal['primary', 'secondary', 'positive', 'negative']


def get_invite_from_message(message: str) -> tuple[int, str] | tuple[None, None]:
    """
    Parse invite text from a VK message.

    Pattern: telegram_id: <digits> invite_hash: <alphanumeric>
    The message may have extra text before/after, and spacing may vary.
    Use case-insensitive search.

    Returns (telegram_user_id, invite_hash) if found, or (None, None) if not.
    """
    match = re.search(r'telegram_id:\s*(\d+)\s+invite_hash:\s*(\w+)', message, re.IGNORECASE)
    if match:
        try:
            return int(match.group(1)), match.group(2)
        except ValueError:
            return None, None
    return None, None


class VKHandlerContext:
    """Context object passed to every handler.

    Provides access to incoming message data, dialog state, user identity,
    and response methods (reply, edit, delete, etc.).

    Handlers receive this as their sole argument and call methods on it
    to interact with the user. The handler chain stops when a handler
    marks the context as consumed (via ``.reply()``, ``.edit()``, etc.).
    """

    def __init__(
        self,
        message: VKMessage,
        user_id: int,
        state: DialogState | None,
        sender: 'VKMessageSender',
        db: 'DBClient',
    ) -> None:
        # ── Incoming data ──────────────────────────────────────────────
        self.message: VKMessage = message
        """The incoming VK message (text, user_id, peer_id, payload, etc.)."""

        self.user_id: int = user_id
        """Resolved internal user ID (not VK user ID)."""

        self.state: DialogState | None = state
        """Current dialog state (what input the bot expects), or None."""

        # ── Internal dependencies ──────────────────────────────────────
        self._sender: VKMessageSender = sender
        self._db: DBClient = db
        self._consumed: bool = False

    # ── Public properties ─────────────────────────────────────────────

    @property
    def db(self) -> 'DBClient':
        """Access the database client for querying user data."""
        return self._db

    # ── Chain control ─────────────────────────────────────────────────

    @property
    def is_consumed(self) -> bool:
        """Whether a handler has already processed this message.

        The dispatcher checks this after each handler to decide whether
        to continue iterating the chain.
        """
        return self._consumed

    # ── Response methods ───────────────────────────────────────────────

    def reply(
        self,
        text: str,
        keyboard: dict | None = None,
        attachment: str = '',
        dont_parse_links: bool = False,
    ) -> int | None:
        """Send a new message to the user and clear dialog state.

        This is the primary response method. It:
        1. Sends the message via VK API
        2. Clears the dialog state (``not_defined``)
        3. Saves the bot reply to dialog history
        4. Marks the context as consumed

        If the handler needs a different state, call ``.set_state()``
        *before* ``.reply()``.

        Returns the sent message ID, or None on failure.
        """
        self._consumed = True
        message_id = self._sender.send_message(
            peer_id=self.message.peer_id,
            text=text,
            keyboard=keyboard,
            attachment=attachment,
            dont_parse_links=dont_parse_links,
        )
        self._db.clear_user_state(self.user_id)
        self._save_dialog(text)
        return message_id

    def edit(
        self,
        text: str,
        keyboard: dict | None = None,
        message_id: int | None = None,
        conversation_message_id: int | None = None,
    ) -> bool:
        """Edit an existing message (for inline keyboard updates).

        Marks the context as consumed.
        Returns True on success.
        """
        self._consumed = True
        result = self._sender.edit_message(
            peer_id=self.message.peer_id,
            message_id=message_id,
            text=text,
            keyboard=keyboard,
            conversation_message_id=conversation_message_id,
        )
        self._save_dialog(text)
        return result

    def delete_message(self, message_ids: list[int]) -> bool:
        """Delete messages. Marks the context as consumed."""
        self._consumed = True
        return self._sender.delete_message(
            peer_id=self.message.peer_id,
            message_ids=message_ids,
        )

    def answer_callback(
        self,
        event_data: dict | None = None,
    ) -> bool:
        """Answer an inline keyboard callback (show snackbar/popup).

        Does NOT mark the context as consumed — the handler may call
        both ``.answer_callback()`` and ``.reply()`` / ``.edit()``.

        If the VK event has no ``event_id`` (edge case), the callback
        ack is silently skipped — VK API would reject an empty event_id
        with error 100.
        """
        if not self.message.event_id:
            logging.warning(
                f'answer_callback: VK event without event_id '
                f'(user_id={self.message.user_id}, peer_id={self.message.peer_id}) '
                f'— skipping callback ack'
            )
            return False
        return self._sender.send_callback_answer(
            event_id=self.message.event_id,
            user_id=self.message.user_id,
            peer_id=self.message.peer_id,
            event_data=event_data,
        )

    def send_message(
        self,
        text: str,
        keyboard: dict | None = None,
        attachment: str = '',
        dont_parse_links: bool = False,
    ) -> int | None:
        """Send an additional message without consuming the context.

        Unlike ``.reply()``, this does NOT mark the context as consumed
        and does NOT clear dialog state. Use for multi-message responses
        after the primary ``.reply()``.
        """
        message_id = self._sender.send_message(
            peer_id=self.message.peer_id,
            text=text,
            keyboard=keyboard,
            attachment=attachment,
            dont_parse_links=dont_parse_links,
        )
        self._save_dialog(text)
        return message_id

    # ── State management ──────────────────────────────────────────────

    def set_state(self, state: DialogState) -> None:
        """Set the dialog state (what input the bot expects next)."""
        self._db.set_user_state(self.user_id, state)
        self.state = state

    def clear_state(self) -> None:
        """Clear the dialog state (bot no longer expects specific input)."""
        self._db.clear_user_state(self.user_id)
        self.state = DialogState.not_defined

    # ── Internal helpers ──────────────────────────────────────────────

    def _save_dialog(self, text: str) -> None:
        """Save bot reply to dialog history."""
        try:
            self._db.save_bot_reply(self.user_id, text)
        except Exception:
            logging.exception(f'Failed to save bot reply to dialog history for user {self.user_id}')
