"""TelegramMessage — typed contract for Telegram outgoing messages.

Replaces raw ``dict`` usage across the codebase: all ``send_message``
and ``edit_message_text`` calls now accept a typed model instead of
assembling and disassembling a loose dictionary.

The model deliberately excludes ``chat_id`` — the recipient is always
passed as a separate parameter at the call site (``user_id`` / ``chat_id``),
which makes the contract explicit and removes the need to extract it
from inside the dict.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class TelegramMessage(BaseModel):
    """Outgoing Telegram message (text variant, ``sendMessage``).

    Designed for both ``sendMessage`` and ``editMessageText`` calls:

    - **``send_message``** — ``message_id`` is ignored
    - **``edit_message_text``** — ``message_id`` **must** be set

    ``reply_markup`` accepts a ``TelegramObject`` instance (e.g.
    ``InlineKeyboardMarkup``, ``ReplyKeyboardMarkup``) directly.
    Serialisation to ``dict`` is handled by ``TGApiBase._make_api_call``
    just before the JSON call to the Telegram API.
    """

    text: str
    """Message text (plain text or HTML/Markdown)."""

    parse_mode: str | None = 'HTML'
    """Telegram parse mode (``'HTML'``, ``'MarkdownV2'``, or ``None``)."""

    disable_web_page_preview: bool | None = True
    """Disable link previews in the message."""

    reply_markup: Any = None
    """Reply markup (inline keyboard, reply keyboard, etc.).

    Accepts ``TelegramObject`` (from python-telegram-bot) or a raw
    ``dict``.  ``TelegramObject`` instances are converted to ``dict``
    via ``.to_dict()`` inside ``TGApiBase._make_api_call``.
    """

    message_id: int | None = None
    """Message ID to edit (only used by ``edit_message_text``).

    Must be set when calling ``edit_message_text``; ignored by
    ``send_message``.
    """

    def to_telegram_params(self) -> dict[str, Any]:
        """Convert message content to a Telegram API ``params`` slice (without ``chat_id``).

        ``None`` fields are excluded so the Telegram API uses its
        own defaults.  ``reply_markup`` values that are
        ``TelegramObject`` instances will be serialised just before
        the HTTP call in ``_make_api_call``.
        """
        return self.model_dump(exclude_none=True)
