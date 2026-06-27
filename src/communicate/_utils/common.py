import logging
import math
from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING, Any, Sequence, Union

from pydantic import BaseModel, ConfigDict, Field
from telegram import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    Message,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
)

from _dependencies.common.commons import SearchFollowingMode
from _dependencies.common.misc import calc_bearing

if TYPE_CHECKING:
    from .database import DBClient
    from .message_sending import TGApiCommunicate

SEARCH_URL_PREFIX = 'https://lizaalert.org/forum/viewtopic.php?t='
FORUM_FOLDER_PREFIX = 'https://lizaalert.org/forum/viewforum.php?f='
LA_BOT_CHAT_URL = 'https://t.me/joinchat/2J-kV0GaCgwxY2Ni'
NOT_FOLLOWING_MARK = '  '  # 'third state' of SearchFollowingMode


class InlineButtonCallbackData(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    keyboard_name: str | None = Field(default=None, alias='kb')
    action: str | int | None = Field(default=None, alias='act')
    hash: int | None = Field(default=None)
    letter_to_show: str = Field(default='', alias='bs')

    def as_str(self) -> str:
        res = self.model_dump_json(by_alias=True, exclude_none=True, exclude_unset=True)
        assert len(res) <= InlineKeyboardButton.MAX_CALLBACK_DATA
        return res


class UserInputState(str, Enum):
    """User input state — alias for DialogState for backward compatibility.

    ``AgePeriod`` is now imported from ``_dependencies.models``.
    """

    radius_input = 'radius_input'
    input_of_coords_man = 'input_of_coords_man'
    input_of_forum_username = 'input_of_forum_username'
    not_defined = 'not_defined'


PREF_DICT = {
    # TODO enum
    'topic_new': 0,
    'topic_status_change': 1,
    'topic_title_change': 2,
    'topic_comment_new': 3,
    'topic_inforg_comment_new': 4,
    'topic_field_trip_new': 5,
    'topic_field_trip_change': 6,
    'topic_coords_change': 7,
    'topic_first_post_change': 8,
    'topic_all_in_followed_search': 9,
    'bot_news': 20,
    'all': 30,
    'not_defined': 99,
    'new_searches': 0,
    'status_changes': 1,
    'title_changes': 2,
    'comments_changes': 3,
    'inforg_comments': 4,
    'field_trips_new': 5,
    'field_trips_change': 6,
    'coords_change': 7,
    'first_post_changes': 8,
    'all_in_followed_search': 9,
}


@dataclass
class SearchSummary:
    topic_type: Any = None
    topic_id: Any = None
    status: Any = None
    start_time: Any = None
    name: Any = None
    display_name: Any = None
    age: Any = None
    new_status: Any = None
    search_lat: str = ''
    search_lon: str = ''
    following_mode: SearchFollowingMode | None = None


@dataclass
class UpdateExtraParams:
    user_is_new: bool
    onboarding_step_id: int
    user_input_state: UserInputState | None


@dataclass
class UpdateBasicParams:
    user_new_status: str
    timer_changed: str
    photo: str
    document: str
    voice: str
    contact: str
    inline_query: str
    sticker: str
    user_latitude: float
    user_longitude: float
    got_message: str
    channel_type: str
    username: str
    user_id: int
    got_callback: InlineButtonCallbackData | None
    callback_query_id: str
    callback_query: CallbackQuery | None


def generate_yandex_maps_place_link(lat: Union[float, str], lon: Union[float, str], param: str) -> str:
    """Compose a link to yandex map with the given coordinates"""

    coordinates_format = '{0:.5f}'

    if param == 'coords':
        display = str(coordinates_format.format(float(lat))) + ', ' + str(coordinates_format.format(float(lon)))
    else:
        display = 'Карта'

    msg = f'<a href="https://yandex.ru/maps/?pt={lon},{lat}&z=11&l=map">{display}</a>'

    return msg


def calc_direction(lat_1: float, lon_1: float, lat_2: float, lon_2: float, coded_style: bool = True) -> str:
    # indicators of the direction, like ↖︎
    # TODO merge with `calc_direction`

    if coded_style:
        points = [
            '&#8593;&#xFE0E;',
            '&#8599;&#xFE0F;',
            '&#8594;&#xFE0E;',
            '&#8600;&#xFE0E;',
            '&#8595;&#xFE0E;',
            '&#8601;&#xFE0E;',
            '&#8592;&#xFE0E;',
            '&#8598;&#xFE0E;',
        ]
    else:
        points = ['⬆️', '↗️', '➡️', '↘️', '⬇️', '↙️', '⬅️', '↖️']

    bearing = calc_bearing(lat_1, lon_1, lat_2, lon_2)
    bearing += 22.5
    bearing = bearing % 360
    bearing = int(bearing / 45)  # values 0 to 7
    nsew = points[bearing]

    return nsew


def define_dist_and_dir_to_search(
    search_lat: str, search_lon: str, user_let: str, user_lon: str, coded_style: bool = True
) -> tuple[float, str]:
    # TODO merge with `define_dist_and_dir_to_search`
    """Return the distance and direction from user "home" coordinates to the search coordinates"""

    r = 6373.0  # radius of the Earth

    # coordinates in radians
    lat1 = math.radians(float(search_lat))
    lon1 = math.radians(float(search_lon))
    lat2 = math.radians(float(user_let))
    lon2 = math.radians(float(user_lon))

    # change in coordinates
    d_lon = lon2 - lon1

    d_lat = lat2 - lat1

    # Haversine formula
    a = math.sin(d_lat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(d_lon / 2) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

    distance = r * c
    dist = round(distance)

    # define direction

    direction = calc_direction(lat1, lon1, lat2, lon2, coded_style)

    return (dist, direction)


def create_one_column_reply_markup(buttons: Sequence[str | KeyboardButton]) -> ReplyKeyboardMarkup:
    """Creates keyboard with buttons in one column"""
    return ReplyKeyboardMarkup([[x] for x in buttons], resize_keyboard=True)


class TGHandlerContext:
    """Context object passed to every Telegram handler.

    Provides access to incoming update data, user identity, dialog state,
    and response methods (reply, edit, answer_callback, etc.).

    Handlers receive this as their sole argument and call methods on it
    to interact with the user. The handler chain stops when a handler
    marks the context as consumed (via ``.reply()``, ``.edit()``, etc.).
    """

    def __init__(
        self,
        update_params: 'UpdateBasicParams',
        extra_params: 'UpdateExtraParams',
        tg_api: 'TGApiCommunicate',
        db: 'DBClient',
    ) -> None:
        # ── Incoming data ──────────────────────────────────────────────
        self.update_params: UpdateBasicParams = update_params
        """The parsed Telegram update parameters."""

        self.extra_params: UpdateExtraParams = extra_params
        """Extra parameters (onboarding step, user input state, etc.)."""

        self.user_id: int = update_params.user_id
        """Telegram user ID."""

        # ── Internal dependencies ──────────────────────────────────────
        self._tg_api: TGApiCommunicate = tg_api
        self._db: DBClient = db
        self._consumed: bool = False

    # ── Public properties ──────────────────────────────────────────────

    @property
    def db(self) -> 'DBClient':
        """Database client for user data access."""
        return self._db

    @property
    def tg_api(self) -> 'TGApiCommunicate':
        """Telegram Bot API client."""
        return self._tg_api

    # ── Chain control ─────────────────────────────────────────────────

    @property
    def is_consumed(self) -> bool:
        """Whether a handler has already processed this update.

        The dispatcher checks this after each handler to decide whether
        to continue iterating the chain.
        """
        return self._consumed

    # ── Response methods ───────────────────────────────────────────────

    def reply(
        self,
        text: str,
        reply_markup: ReplyKeyboardMarkup | InlineKeyboardMarkup | ReplyKeyboardRemove | None = None,
        parse_mode: str = 'HTML',
        disable_web_page_preview: bool = True,
    ) -> None:
        """Send a new message to the user (or edit if this is a callback).

        Automatically detects whether this is an inline callback response
        (edits the original message) or a regular message (sends new).

        Marks the context as consumed and clears dialog state.
        """
        self._consumed = True
        self._send_or_edit(text, reply_markup, parse_mode, disable_web_page_preview)
        self._db.set_user_input_state(self.user_id, UserInputState.not_defined)
        self._save_dialog(text)

    def edit(
        self,
        text: str,
        reply_markup: InlineKeyboardMarkup | None = None,
        message_id: int | None = None,
    ) -> None:
        """Edit an existing message (for inline keyboard updates).

        Marks the context as consumed.
        """
        self._consumed = True
        params = {
            'chat_id': self.user_id,
            'text': text,
            'message_id': message_id,
            'reply_markup': reply_markup,
        }
        self._tg_api.edit_message_text(params)
        self._save_dialog(text)

    def answer_callback(self, text: str = '') -> None:
        """Answer a callback query (show a brief notification to the user).

        Does NOT mark the context as consumed — the handler may call
        both ``.answer_callback()`` and ``.reply()`` / ``.edit()``.
        """
        callback_query_id = self.update_params.callback_query_id
        if callback_query_id:
            self._tg_api.send_callback_answer_to_api(self.user_id, callback_query_id, text)

    def send_message(
        self,
        text: str,
        reply_markup: ReplyKeyboardMarkup | InlineKeyboardMarkup | ReplyKeyboardRemove | None = None,
        parse_mode: str = 'HTML',
        disable_web_page_preview: bool = True,
    ) -> None:
        """Send an additional message without consuming the context.

        Unlike ``.reply()``, this does NOT mark the context as consumed
        and does NOT clear dialog state. Use for multi-message responses
        after the primary ``.reply()``.
        """
        params = {
            'parse_mode': parse_mode,
            'disable_web_page_preview': disable_web_page_preview,
            'reply_markup': reply_markup,
            'chat_id': self.user_id,
            'text': text,
        }
        self._tg_api.send_message(params)
        self._save_dialog(text)

    def delete_inline_dialogue(self) -> None:
        """Delete the last inline dialogue message IDs for this user."""
        self._db.delete_last_user_inline_dialogue(self.user_id)

    # ── State management ──────────────────────────────────────────────

    def set_state(self, state: UserInputState) -> None:
        """Set the dialog state (what input the bot expects next)."""
        self._db.set_user_input_state(self.user_id, state)

    def clear_state(self) -> None:
        """Clear the dialog state (bot no longer expects specific input)."""
        self._db.set_user_input_state(self.user_id, UserInputState.not_defined)

    # ── Internal helpers ──────────────────────────────────────────────

    def _send_or_edit(
        self,
        text: str,
        reply_markup: ReplyKeyboardMarkup | InlineKeyboardMarkup | ReplyKeyboardRemove | None,
        parse_mode: str,
        disable_web_page_preview: bool,
    ) -> None:
        """Decide whether to send a new message or edit an existing one."""
        got_callback = self.update_params.got_callback
        callback_query = self.update_params.callback_query

        replied_with_inline_markup = got_callback and isinstance(reply_markup, InlineKeyboardMarkup)
        if replied_with_inline_markup:
            # Edit the message where the inline button was pushed
            message = callback_query.message if callback_query is not None else None
            if isinstance(message, Message):
                try:
                    if message.reply_markup == reply_markup and message.text == text:
                        # Same content — just acknowledge the callback
                        self.answer_callback('')
                        return
                except AttributeError:
                    logging.warning(f'no reply_markup or text in {callback_query=}')

                last_user_message_id = message.id
                params = {
                    'chat_id': self.user_id,
                    'text': text,
                    'message_id': last_user_message_id,
                    'reply_markup': reply_markup,
                }
                self._tg_api.edit_message_text(params)
        else:
            params = {
                'parse_mode': parse_mode,
                'disable_web_page_preview': disable_web_page_preview,
                'reply_markup': reply_markup,
                'chat_id': self.user_id,
                'text': text,
            }
            self._tg_api.send_message(params)

    def _save_dialog(self, text: str) -> None:
        """Save bot reply to dialog history."""
        if text:
            try:
                self._db.save_bot_reply_to_user(self.user_id, text)
            except Exception:
                logging.exception(f'Failed to save bot reply for user {self.user_id}')
