"""Message and callback event processing for the VK bot.

This module contains the core logic for processing:
- ``handle_new_message`` — new user messages (text commands)
- ``handle_callback_event`` — inline keyboard callback events

Both functions delegate to the handler chain for actual command handling,
and use :func:`result_processing.process_vk_result` to send responses.
"""

import json
import logging

from .account_linking import handle_unregistered_user
from .common import VKMessage
from .database import db
from .handler_chain import HANDLER_CHAIN
from .handlers import region_select_handlers
from .message_sending import VKMessageSender
from .result_processing import process_vk_result


def handle_new_message(
    vk_message: VKMessage,
    sender: VKMessageSender,
) -> None:
    """Process a new message from a user.

    Flow:
    1. Resolve identity via ``user_identity_map`` (new path)
    2. If not found, fall back to ``users.vk_id`` column (legacy path)
    3. If still not found, try invite linking first; if that fails,
       register as a VK-only user so they can use the bot immediately
    4. Once identity is resolved → run handler chain

    Args:
        vk_message: The incoming VK message.
        sender: VKMessageSender instance for sending messages.
    """
    import datetime

    from .account_linking import handle_unregistered_user, register_vk_only_user

    vk_user_id = vk_message.user_id
    peer_id = vk_message.peer_id

    logging.info(f'handle_new_message: vk_user={vk_user_id}, text="{vk_message.text}"')

    # 1. Try new path: user_identity_map
    identity = db().get_identity_by_messenger_user_id(vk_user_id)
    if identity is not None:
        user_id = identity.internal_user_id
        logging.info(f'handle_new_message: resolved from identity_map, internal_user={user_id}')

    # 2. Fall back to legacy path: users.vk_id
    else:
        linked_user_id = db().get_user_by_vk_id(vk_user_id)
        if linked_user_id is not None:
            user_id = linked_user_id
            logging.info(f'handle_new_message: resolved from legacy vk_id, system_user={user_id}')
        else:
            # 3. Check if message is an invite attempt
            from .common import get_invite_from_message

            telegram_user_id, invite_hash = get_invite_from_message(vk_message.text)
            if telegram_user_id and invite_hash:
                # Let account_linking handle the invite validation
                handle_unregistered_user(vk_message, peer_id, sender=sender)
                return

            # 4. Register as VK-only user
            logging.info(f'handle_new_message: registering VK-only user {vk_user_id}')
            user_id = register_vk_only_user(vk_user_id)

    try:
        db().save_user_message(user_id, vk_message.text)
    except Exception:
        logging.exception(f'Failed to save user message to dialog history for user {user_id}')

    state = db().get_user_state(user_id)

    for handler in HANDLER_CHAIN:
        try:
            result = handler(vk_message, state, user_id)
        except Exception:
            logging.exception(f'Handler {handler.__name__} crashed for user {user_id}')
            continue

        if result is None:
            continue

        logging.info(f'handle_new_message: handler {handler.__name__} matched for text="{vk_message.text}"')
        process_vk_result(user_id, peer_id, result, sender=sender)
        return


def handle_callback_event(
    vk_message: VKMessage,
    sender: VKMessageSender,
) -> None:
    """Process a callback event from an inline keyboard button.

    VK inline keyboards can have URL buttons (open_link) which don't
    generate callbacks, and callback buttons (callback) which generate
    message_event with a payload.

    When a callback is received:
    1. Parse the payload to determine the action
    2. If it's a pagination command (paginate_nav/paginate_toggle/paginate_back),
       delegate to region_select_handlers.handle_inline_pagination().
    3. If it's a district_select command, delegate to
       region_select_handlers.handle_district_select().
    4. Otherwise, acknowledge the event and process through the handler chain
       as if it were a text message.

    Args:
        vk_message: The incoming VK message (with payload for callbacks).
        sender: VKMessageSender instance for sending messages.
    """
    payload = vk_message.payload
    logging.info(f'handle_callback_event: user_id={vk_message.user_id}, payload="{payload}"')
    if not payload:
        return

    try:
        payload_data = json.loads(payload)
    except (json.JSONDecodeError, TypeError):
        payload_data = None

    if isinstance(payload_data, dict):
        cmd = payload_data.get('cmd', '')

        if cmd.startswith('paginate_'):
            logging.info(
                f'handle_callback_event: routing to region_select_handlers.handle_inline_pagination, cmd="{cmd}"'
            )
            region_select_handlers.handle_inline_pagination(vk_message, payload_data, sender=sender)
            return

        if cmd == 'district_select':
            logging.info(
                f'handle_callback_event: routing to region_select_handlers.handle_district_select, '
                f'district="{payload_data.get("district")}"'
            )
            region_select_handlers.handle_district_select(vk_message, payload_data, sender=sender)
            return

    logging.info(f'handle_callback_event: non-pagination callback, processing as text command')
    sender.send_callback_answer(
        event_id=vk_message.event_id or '',
        user_id=vk_message.user_id,
        peer_id=vk_message.peer_id,
    )

    if isinstance(payload_data, dict):
        command = payload_data.get('command', '') or payload_data.get('button', '')
    elif payload_data is not None:
        command = str(payload_data)
    else:
        command = str(payload)

    if not command:
        return

    # Create a synthetic VKMessage with the command as text
    # and process it through the normal message flow
    synthetic_message = VKMessage(
        text=command,
        user_id=vk_message.user_id,
        peer_id=vk_message.peer_id,
        message_id=vk_message.message_id,
    )
    handle_new_message(synthetic_message, sender=sender)
