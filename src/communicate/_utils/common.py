import math
from dataclasses import dataclass
from enum import Enum
from typing import Any, Sequence, Union

from pydantic import BaseModel, ConfigDict, Field
from telegram import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
)

from _dependencies.commons import SearchFollowingMode
from _dependencies.misc import calc_bearing

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


@dataclass
class AgePeriod:
    description: str
    name: str
    min_age: int
    max_age: int
    order: int
    active: bool = False  # TODO don't need


class UserInputState(str, Enum):
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


HandlerResult = tuple[str, ReplyKeyboardMarkup | InlineKeyboardMarkup | ReplyKeyboardRemove | None]
HandlerResultWithState = tuple[
    str, ReplyKeyboardMarkup | InlineKeyboardMarkup | ReplyKeyboardRemove | None, UserInputState
]
