"""State-based handlers for the VK bot.

These handlers check DialogState first and handle specific input states
(forum username input). Radius and coordinate input have been moved
to the web admin panel.
"""

import logging

from _dependencies.pubsub import pubsub_parse_user_profile
from _dependencies.services.message_formatter import (
    forum_link_checking,
)
from _dependencies.services.state_machine import DialogState

from ..common import VKHandlerResult, VKMessage
from ..database import db
from ..keyboards import VKKeyboard

logger = logging.getLogger(__name__)


def handle_forum_username(vk_message: VKMessage, state: DialogState | None, user_id: int) -> VKHandlerResult | None:
    """Handle forum username input state — trigger forum linking.

    Activated when DialogState is input_of_forum_username.
    Saves the forum username and triggers verification via pubsub.
    """
    if state != DialogState.input_of_forum_username:
        return None

    forum_username = vk_message.text.strip()
    logger.info(f'Forum linking requested for user {user_id}, username: {forum_username}')

    # Trigger forum profile parsing via pubsub
    # The connect_to_forum function will log into the forum,
    # scrape the user's profile, and save it to user_forum_attributes
    try:
        pubsub_parse_user_profile(user_id, forum_username)
        logger.info(f'Published forum linking request for user {user_id}, username: {forum_username}')
    except Exception:
        logger.exception(f'Failed to publish forum linking request for user {user_id}')

    return VKHandlerResult(
        text=forum_link_checking(),
        keyboard=VKKeyboard.settings_menu(),
        new_state=DialogState.not_defined,
    )
