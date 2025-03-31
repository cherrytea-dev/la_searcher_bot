import datetime
import hashlib
import math
from enum import Enum
from typing import Any, Dict, Union

from _dependencies.commons import Topics, publish_to_pubsub


class Button:
    """Contains one unique button and all the associated attributes"""

    def __init__(self, data: Dict[str, Any] = None, modifier=None):
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

    def __str__(self):
        return self.text

    def temp_all_keys(self):
        return [k for k, v in self.__dict__.items()]


class GroupOfButtons:
    """Contains the set of unique buttons of the similar nature (to be shown together as alternatives)"""

    def __init__(
        self,
        button_dict,
        modifier_dict=None,
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

    def __str__(self):
        return self.any_text

    def contains(self, check: str) -> bool:
        """Check is the given text/hash is used for any button in this group"""

        if check in self.any_text:
            return True

        if check in self.any_hash:
            return True

        return False

    def temp_all_keys(self):
        return [k for k, v in self.__dict__.items()]

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

    def button_by_text(self, given_text):
        """Return a Button which correspond to the given text"""
        for key, value in self.__dict__.items():
            if not value:
                continue
            if hasattr(value, 'any_text') and given_text in value.any_text:
                return value
        return None

    def button_by_hash(self, given_hash):
        """Return a Button which correspond to the given hash"""
        for key, value in self.__dict__.items():
            if not value:
                continue
            if hasattr(value, 'hash') and given_hash == value.hash:
                return value
        return None


class AllButtons:
    def __init__(self, initial_dict):
        for key, value in initial_dict.items():
            setattr(self, key, GroupOfButtons(value))

    def temp_all_keys(self):
        return [k for k, v in self.__dict__.items()]


class SearchFollowingMode(str, Enum):
    # in table 'user_pref_search_whitelist'
    # TODO merge with the same enum in compose_notifications
    ON = '👀 '
    OFF = '❌ '


def distance_to_search(search_lat, search_lon, user_let, user_lon, coded_style=True):
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

    def calc_bearing(lat_2, lon_2, lat_1, lon_1):
        d_lon_ = lon_2 - lon_1
        x = math.cos(math.radians(lat_2)) * math.sin(math.radians(d_lon_))
        y = math.cos(math.radians(lat_1)) * math.sin(math.radians(lat_2)) - math.sin(math.radians(lat_1)) * math.cos(
            math.radians(lat_2)
        ) * math.cos(math.radians(d_lon_))
        bearing = math.atan2(x, y)
        bearing = math.degrees(bearing)

        return bearing

    def calc_nsew(lat_1, lon_1, lat_2, lon_2, coded_style=True):
        # indicators of the direction, like ↖︎
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

    direction = calc_nsew(lat1, lon1, lat2, lon2, coded_style)

    return [dist, direction]


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
    # TODO replace with direct db functions

    return None
