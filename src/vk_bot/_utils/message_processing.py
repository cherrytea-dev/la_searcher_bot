"""Message and callback event processing for the VK bot.

This module contains the core logic for processing:
- ``handle_new_message`` — new user messages (text commands)
- ``handle_callback_event`` — inline keyboard callback events

Both functions delegate to the handler chain for actual command handling.
"""

import logging

from .account_linking import handle_unregistered_user, register_vk_only_user
from .common import VKHandlerContext, VKMessage, get_invite_from_message
from .database import db
from .handler_chain import HANDLER_CHAIN
from .message_sending import VKMessageSender


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

    vk_user_id = vk_message.user_id

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

            telegram_user_id, invite_hash = get_invite_from_message(vk_message.text)
            if telegram_user_id and invite_hash:
                # Let account_linking handle the invite validation
                ctx = VKHandlerContext(
                    message=vk_message,
                    user_id=-1,  # placeholder — user not yet resolved
                    state=None,
                    sender=sender,
                    db=db(),
                )
                handle_unregistered_user(ctx)
                return

            # 4. Register as VK-only user
            logging.info(f'handle_new_message: registering VK-only user {vk_user_id}')
            user_id = register_vk_only_user(vk_user_id)

    try:
        db().save_user_message(user_id, vk_message.text)
    except Exception:
        logging.exception(f'Failed to save user message to dialog history for user {user_id}')

    state = db().get_user_state(user_id)

    ctx = VKHandlerContext(
        message=vk_message,
        user_id=user_id,
        state=state,
        sender=sender,
        db=db(),
    )

    for handler in HANDLER_CHAIN:
        try:
            handler(ctx)
        except Exception:
            logging.exception(f'Handler {handler.__name__} crashed for user {user_id}')
            continue

        if ctx.is_consumed:
            logging.info(f'handle_new_message: handler {handler.__name__} matched for text="{vk_message.text}"')
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
    1. Resolve user identity
    2. Acknowledge the callback event
    3. Create a VKHandlerContext and run through the handler chain
       — pagination/district_select handlers now parse payload from
       ``ctx.message.payload_as_dict`` themselves.

    Args:
        vk_message: The incoming VK message (with payload for callbacks).
        sender: VKMessageSender instance for sending messages.
    """
    payload = vk_message.payload
    logging.info(f'handle_callback_event: user_id={vk_message.user_id}, payload="{payload}"')
    if not payload:
        return

    # Resolve identity
    vk_user_id = vk_message.user_id
    identity = db().get_identity_by_messenger_user_id(vk_user_id)
    if identity is not None:
        user_id = identity.internal_user_id
    else:
        linked_user_id = db().get_user_by_vk_id(vk_user_id)
        if linked_user_id is not None:
            user_id = linked_user_id
        else:
            logging.warning(f'handle_callback_event: unknown user {vk_user_id}, cannot process callback')
            return

    # Acknowledge the callback event
    sender.send_callback_answer(
        event_id=vk_message.event_id or '',
        user_id=vk_message.user_id,
        peer_id=vk_message.peer_id,
    )

    state = db().get_user_state(user_id)
    ctx = VKHandlerContext(
        message=vk_message,
        user_id=user_id,
        state=state,
        sender=sender,
        db=db(),
    )

    # Run through the handler chain — pagination/district_select handlers
    # will match based on ctx.message.payload_as_dict
    for handler in HANDLER_CHAIN:
        try:
            handler(ctx)
        except Exception:
            logging.exception(f'Handler {handler.__name__} crashed for user {user_id}')
            continue

        if ctx.is_consumed:
            logging.info(f'handle_callback_event: handler {handler.__name__} matched for payload="{payload}"')
            return
