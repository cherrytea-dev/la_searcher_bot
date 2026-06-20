"""Shared data models for VK bot database layer.

These types are used by multiple mixins and by external consumers (handlers, tests).
They were previously defined in database.py and user_settings_service.py.
"""

from dataclasses import dataclass
from enum import Enum


class DialogState(str, Enum):
    """Possible states of a user dialog with the bot.

    Tells the bot what kind of input it's waiting for from the user
    (e.g., radius input, coordinates input, forum username input).
    """

    radius_input = 'radius_input'
    input_of_coords_man = 'input_of_coords_man'
    input_of_forum_username = 'input_of_forum_username'
    not_defined = 'not_defined'


@dataclass
class AgePeriod:
    """Age period for filtering searches by missing person's age."""

    description: str
    name: str
    min_age: int
    max_age: int
    order: int
    active: bool = False


@dataclass
class UserSettingsSummary:
    """Aggregated view of user's settings completeness."""

    user_id: int
    pref_role: bool
    pref_age: bool
    pref_coords: bool
    pref_radius: bool
    pref_region: bool
    pref_topic_type: bool
    pref_urgency: bool
    pref_notif_type: bool
    pref_region_old: bool
    pref_forum: bool
