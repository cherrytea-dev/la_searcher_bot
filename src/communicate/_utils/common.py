import datetime
import hashlib
import math
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, Union

from _dependencies.commons import Topics, publish_to_pubsub
from compose_notifications._utils.commons import calc_bearing  # TODO common code


@dataclass
class AgePeriod:
    description: str
    name: str
    min_age: int
    max_age: int
    order: int
    current: bool = False  # TODO don't need


class Button:
    """Contains one unique button and all the associated attributes"""

    def __init__(self, data: Dict[str, Any], modifier=None):
        if modifier is None:
            modifier = {'on': '✅ ', 'off': '☐ '}  # standard modifier

        self.modifier = modifier
        self.data = data
        self.text = None
        for key, value in self.data.items():
            setattr(self, key, value)
        self.hash = hashlib.shake_128(self.text.encode('utf-8')).hexdigest(4)  # noqa

        self.any_text = [self.text]
        for key, value in modifier.items():
            new_value = f'{value}{self.text}'
            setattr(self, key, new_value)
            self.any_text.append(new_value)

        self.all = [v for k, v in self.__dict__.items() if v != modifier]

    def __str__(self) -> str:
        return self.text


class GroupOfButtons:
    """Contains the set of unique buttons of the similar nature (to be shown together as alternatives)"""

    def __init__(
        self,
        button_dict: dict,
        modifier_dict: Any = None,
    ):
        self.modifier_dict = modifier_dict

        all_button_texts = []
        all_button_hashes = []
        for key, value in button_dict.items():
            setattr(self, key, Button(value, modifier_dict))
            all_button_texts += self.__getattribute__(key).any_text
            all_button_hashes.append(self.__getattribute__(key).hash)
        self.any_text = all_button_texts
        self.any_hash = all_button_hashes

    def __str__(self) -> str:
        return self.any_text

    def contains(self, check: str) -> bool:
        """Check is the given text/hash is used for any button in this group"""

        if check in self.any_text:
            return True

        if check in self.any_hash:
            return True

        return False

    def id(self, given_id):
        """Return a Button which correspond to the given id"""
        for key, value in self.__dict__.items():
            if not value:
                continue
            if hasattr(value, 'id') and value.id == given_id:
                return value
        return None

    def keyboard(self, act_list, change_list):
        """Generate a list of telegram buttons (2D array) basing on existing setting list and one that should change"""

        keyboard = []
        for key, value in self.__dict__.items():
            curr_button = self.__getattribute__(key)
            if key in {'modifier_dict', 'any_text', 'any_hash'}:
                continue
            if hasattr(value, 'hide') and value.hide:
                continue
            curr_button_is_in_existing_id_list = False
            curr_button_is_asked_to_change = False
            for id_item in act_list:
                if curr_button.id == id_item:
                    curr_button_is_in_existing_id_list = True
                    break
            for id_item in change_list:
                if curr_button.id == id_item:
                    curr_button_is_asked_to_change = True
                    break

            if curr_button_is_in_existing_id_list and key not in {'about'}:
                if not curr_button_is_asked_to_change:
                    keyboard += [
                        {'text': curr_button.on, 'callback_data': f'{{"action":"off","hash": "{curr_button.hash}"}}'}
                    ]
                else:
                    keyboard += [
                        {'text': curr_button.off, 'callback_data': f'{{"action":"on","hash": "{curr_button.hash}"}}'}
                    ]
            elif key not in {'about'}:
                if not curr_button_is_asked_to_change:
                    keyboard += [
                        {'text': curr_button.off, 'callback_data': f'{{"action":"on","hash": "{curr_button.hash}"}}'}
                    ]
                else:
                    keyboard += [
                        {'text': curr_button.on, 'callback_data': f'{{"action":"off","hash": "{curr_button.hash}"}}'}
                    ]
            else:  # case for 'about' button
                keyboard += [
                    {'text': curr_button.text, 'callback_data': f'{{"action":"about","hash": "{curr_button.hash}"}}'}
                ]

        keyboard = [[k] for k in keyboard]

        return keyboard

    def button_by_text(self, given_text: str) -> Button | None:
        """Return a Button which correspond to the given text"""
        for key, value in self.__dict__.items():
            if not value:
                continue
            if hasattr(value, 'any_text') and given_text in value.any_text:
                return value
        return None

    def button_by_hash(self, given_hash: str) -> Button | None:
        """Return a Button which correspond to the given hash"""
        for key, value in self.__dict__.items():
            if not value:
                continue
            if hasattr(value, 'hash') and given_hash == value.hash:
                return value
        return None


class AllButtons:
    def __init__(self, initial_dict: dict) -> None:
        for key, value in initial_dict.items():
            setattr(self, key, GroupOfButtons(value))


class SearchFollowingMode(str, Enum):
    # in table 'user_pref_search_whitelist'
    # TODO merge with the same enum in compose_notifications
    ON = '👀 '
    OFF = '❌ '


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


def if_user_enables(callback: Dict) -> Union[None, bool]:
    """check if user wants to enable or disable a feature"""
    user_wants_to_enable = None

    if callback['action'] == 'on':
        user_wants_to_enable = True
    elif callback['action'] == 'off':
        user_wants_to_enable = False

    return user_wants_to_enable


def save_onboarding_step(user_id: str, username: str, step: str) -> None:
    """save the certain step in onboarding"""
    # TODO replace with direct db functions

    # to avoid eval errors in recipient script
    if not username:
        username = 'unknown'

    message_for_pubsub = {
        'action': 'update_onboarding',
        'info': {'user': user_id, 'username': username},
        'time': str(datetime.datetime.now()),
        'step': step,
    }
    publish_to_pubsub(Topics.topic_for_user_management, message_for_pubsub)


pref_dict = {
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
