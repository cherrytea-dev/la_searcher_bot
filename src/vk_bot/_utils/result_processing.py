"""Send handler results to the user and update dialog state.

This module contains the logic for taking a :class:`VKHandlerResult`
produced by a handler and delivering it to the user via the VK API.
"""

import logging

from .common import VKHandlerResult
from .database import db
from .message_sending import VKMessageSender


def process_vk_result(
    user_id: int,
    peer_id: int,
    result: VKHandlerResult,
    sender: VKMessageSender,
) -> None:
    """Send the handler result to the user and update dialog state.

    Args:
        user_id: The system user ID.
        peer_id: The VK peer ID to send responses to.
        result: The handler result to deliver.
        sender: VKMessageSender instance for sending messages.
    """
    if result.edit_message_id is not None:
        logging.info(f'process_vk_result: editing message {result.edit_message_id} for user {user_id}')
        sender.edit_message(
            peer_id=peer_id,
            message_id=result.edit_message_id,
            text=result.text,
            keyboard=result.keyboard,
        )
    else:
        logging.info(f'process_vk_result: sending NEW message for user {user_id}, text="{result.text[:50]}"')
        sender.send_message(
            peer_id=peer_id,
            text=result.text,
            keyboard=result.keyboard,
            attachment=result.attachment or '',
        )

    if result.new_state is not None:
        db().set_user_state(user_id, result.new_state)
    elif result.text:
        # Any new message resets the dialog state
        db().clear_user_state(user_id)

    try:
        db().save_bot_reply(user_id, result.text)
    except Exception:
        logging.exception(f'Failed to save bot reply to dialog history for user {user_id}')
