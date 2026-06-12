"""State-based handlers for the VK bot.

These handlers check DialogState first and handle specific input states
(radius input, coordinate input, forum username input).
"""

import logging
import re

from _dependencies.services.message_formatter import (
    coords_parse_error,
    coords_saved,
    forum_link_checking,
    radius_parse_error,
    radius_saved,
)
from _dependencies.services.state_machine import DialogState

from ..common import VKHandlerResult, VKMessage
from ..database import db
from ..keyboards import VKKeyboard

logger = logging.getLogger(__name__)


def handle_radius_value(vk_message: VKMessage, state: DialogState | None, user_id: int) -> VKHandlerResult | None:
    """Handle radius input state — parse number, save radius.

    Activated when DialogState is radius_input.
    Expects a message containing a numeric value (e.g., '150' or '50 км').
    """
    if state != DialogState.radius_input:
        return None

    match = re.search(r'\d+', vk_message.text)
    if not match:
        return VKHandlerResult(
            text=radius_parse_error(),
            keyboard=VKKeyboard.radius_settings(),
        )

    radius_km = int(match.group())
    db().settings.save_radius(user_id, radius_km)
    return VKHandlerResult(
        text=radius_saved(radius_km),
        keyboard=VKKeyboard.settings_menu(),
        new_state=DialogState.not_defined,
    )


def handle_coords_text(vk_message: VKMessage, state: DialogState | None, user_id: int) -> VKHandlerResult | None:
    """Handle manual coordinate input state — parse lat, lon.

    Activated when DialogState is input_of_coords_man.
    Expects a message like '55.7558, 37.6173' or '55.7558 37.6173'.
    """
    if state != DialogState.input_of_coords_man:
        return None

    # Match patterns like "55.7558 37.6173" or "55.7558, 37.6173"
    match = re.search(r'(-?\d+\.?\d*)\s*[, ]\s*(-?\d+\.?\d*)', vk_message.text)
    if not match:
        return VKHandlerResult(
            text=coords_parse_error(),
            keyboard=VKKeyboard.coords_menu(),
        )

    lat, lon = float(match.group(1)), float(match.group(2))
    db().settings.save_coordinates(user_id, lat, lon)
    return VKHandlerResult(
        text=coords_saved(),
        keyboard=VKKeyboard.settings_menu(),
        new_state=DialogState.not_defined,
    )


def handle_forum_username(vk_message: VKMessage, state: DialogState | None, user_id: int) -> VKHandlerResult | None:
    """Handle forum username input state — trigger forum linking.

    Activated when DialogState is input_of_forum_username.
    Saves the forum username and triggers verification via pubsub.
    """
    if state != DialogState.input_of_forum_username:
        return None

    forum_username = vk_message.text.strip()
    # TODO: actually trigger forum linking via pubsub (parse_user_profile_from_forum)
    logger.info(f'Forum linking requested for user {user_id}, username: {forum_username}')

    return VKHandlerResult(
        text=forum_link_checking(),
        keyboard=VKKeyboard.settings_menu(),
        new_state=DialogState.not_defined,
    )
