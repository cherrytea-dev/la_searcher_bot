import json
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel, field_validator

from .database import DialogState
from .services.message_formatter import (
    FORUM_FOLDER_PREFIX,
    LA_BOT_CHAT_URL,
    LA_BOT_DEV_CHAT,
    LA_DEV_CHAT_URL,
    LA_FORUM_URL,
    LA_HOTLINE_PHONE,
    LA_HOW_TO_HELP_ARTICLE,
    LA_NEWBIE_ARTICLE,
    LA_NEWBIE_FORUM_TOPIC,
    LA_PHOTOS_CHANNEL_URL,
    LA_SEARCH_REQUEST_FORM,
    LA_WEBSITE,
    SEARCH_URL_PREFIX,
)


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


@dataclass
class VKHandlerResult:
    """Result of a handler — what to send back to the user."""

    text: str
    keyboard: dict | None = None
    new_state: DialogState | None = None
    edit_message_id: int | None = None
    attachment: str | None = None


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
