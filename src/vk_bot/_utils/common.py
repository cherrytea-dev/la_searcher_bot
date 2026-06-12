from dataclasses import dataclass, field
from typing import Literal

from pydantic import BaseModel

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


# URL constants (mirrored from communicate/_utils/common.py)
SEARCH_URL_PREFIX = 'https://lizaalert.org/forum/viewtopic.php?t='
FORUM_FOLDER_PREFIX = 'https://lizaalert.org/forum/viewforum.php?f='
LA_BOT_CHAT_URL = 'https://t.me/la_search_bot'
LA_PHOTOS_CHANNEL_URL = 'https://t.me/lizaalert_photo'
LA_DEV_CHAT_URL = 'https://t.me/la_search_chat'
LA_HOTLINE_PHONE = '8-800-700-54-52'
LA_WEBSITE = 'https://lizaalert.org'
LA_FORUM_URL = 'https://lizaalert.org/forum'
LA_NEWBIE_ARTICLE = 'https://lizaalert.org/help/'
LA_HOW_TO_HELP_ARTICLE = 'https://lizaalert.org/help/'
LA_SEARCH_REQUEST_FORM = 'https://lizaalert.org/request/'
LA_NEWBIE_FORUM_TOPIC = 'https://lizaalert.org/forum/viewtopic.php?t=2'
LA_BOT_DEV_CHAT = 'https://t.me/la_search_chat'


ButtonColor = Literal['primary', 'secondary', 'positive', 'negative']
