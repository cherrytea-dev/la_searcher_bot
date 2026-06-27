"""State-based handlers for the VK bot.

These handlers check DialogState first and handle specific input states
(radius input, coordinate input, forum username input).
"""

import logging
import re

from _dependencies.common.pubsub import pubsub_parse_user_profile
from _dependencies.models import DialogState

from ..common import VKHandlerContext
from ..keyboards import VKKeyboardPresets
from ..services.message_formatter import (
    coords_parse_error,
    coords_saved,
    forum_link_checking,
    radius_parse_error,
    radius_saved,
)


def handle_radius_value(ctx: VKHandlerContext) -> None:
    """Handle radius input state — parse number, save radius.

    Activated when DialogState is radius_input.
    Expects a message containing a numeric value (e.g., '150' or '50 км').
    """
    if ctx.state != DialogState.radius_input:
        return

    match = re.search(r'\d+', ctx.message.text)
    if not match:
        ctx.reply(
            text=radius_parse_error(),
            keyboard=VKKeyboardPresets.radius_settings(),
        )
        return

    radius_km = int(match.group())
    ctx.db.save_radius(ctx.user_id, radius_km)
    ctx.reply(
        text=radius_saved(radius_km),
        keyboard=VKKeyboardPresets.settings_menu(),
    )


def handle_coords_text(ctx: VKHandlerContext) -> None:
    """Handle manual coordinate input state — parse lat, lon.

    Activated when DialogState is input_of_coords_man.
    Expects a message like '55.7558, 37.6173' or '55.7558 37.6173'.
    """
    if ctx.state != DialogState.input_of_coords_man:
        return

    # Match patterns like "55.7558 37.6173" or "55.7558, 37.6173"
    match = re.search(r'(-?\d+\.?\d*)\s*[, ]\s*(-?\d+\.?\d*)', ctx.message.text)
    if not match:
        ctx.reply(
            text=coords_parse_error(),
            keyboard=VKKeyboardPresets.coords_menu(),
        )
        return

    lat, lon = float(match.group(1)), float(match.group(2))
    ctx.db.save_coordinates(ctx.user_id, lat, lon)
    ctx.reply(
        text=coords_saved(),
        keyboard=VKKeyboardPresets.settings_menu(),
    )


def handle_forum_username(ctx: VKHandlerContext) -> None:
    """Handle forum username input state — trigger forum linking.

    Activated when DialogState is input_of_forum_username.
    Saves the forum username and triggers verification via pubsub.
    """
    if ctx.state != DialogState.input_of_forum_username:
        return

    forum_username = ctx.message.text.strip()
    logging.info(f'Forum linking requested for user {ctx.user_id}, username: {forum_username}')

    # Trigger forum profile parsing via pubsub
    # The connect_to_forum function will log into the forum,
    # scrape the user's profile, and save it to user_forum_attributes
    try:
        pubsub_parse_user_profile(ctx.user_id, forum_username)
        logging.info(f'Published forum linking request for user {ctx.user_id}, username: {forum_username}')
    except Exception:
        logging.exception(f'Failed to publish forum linking request for user {ctx.user_id}')

    ctx.reply(
        text=forum_link_checking(),
        keyboard=VKKeyboardPresets.settings_menu(),
    )


router: list = [
    handle_radius_value,
    handle_coords_text,
    handle_forum_username,
]
