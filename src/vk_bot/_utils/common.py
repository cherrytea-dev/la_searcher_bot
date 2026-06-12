from dataclasses import dataclass, field
from typing import Literal

from pydantic import BaseModel

from _dependencies.services.message_formatter import (
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
from _dependencies.services.state_machine import DialogState


class VKMessage(BaseModel):
    """Parsed incoming VK event data."""

    text: str
    user_id: int
    peer_id: int
    message_id: int | None = None
    payload: str | None = None
    event_id: str | None = None


@dataclass
class VKHandlerResult:
    """Result of a handler — what to send back to the user."""

    text: str
    keyboard: dict | None = None
    new_state: DialogState | None = None
    edit_message_id: int | None = None
    attachment: str | None = None


ButtonColor = Literal['primary', 'secondary', 'positive', 'negative']
