"""Message and callback event processing for the VK bot.

This module contains the core logic for processing:
- ``handle_new_message`` — new user messages (text commands)
- ``handle_callback_event`` — inline keyboard callback events

Both functions use vk_registry.match() to find the right handler
based on extracted conditions (text, state, callback_data).
"""

import logging

from .account_linking import handle_unregistered_user, register_vk_only_user
from .common import VKHandlerContext, VKMessage, get_invite_from_message
from .database import db
from .decorators import vk_registry
from .handler_chain import handle_unknown
from .handlers.region_select_handlers import handle_region_toggle
from .message_sending import VKMessageSender


def _run_registered_handlers(
    ctx: VKHandlerContext,
    *,
    text: str | None = None,
    state: str | None = None,
    callback_data: str | None = None,
) -> bool:
    """Run handlers from vk_registry that match the given conditions.

    Returns True if a handler consumed the message, False otherwise.
    """
    kwargs: dict[str, str] = {}
    if text is not None:
        kwargs['text'] = text
    if state is not None:
        kwargs['state'] = state
    if callback_data is not None:
        kwargs['callback_data'] = callback_data

    for handler in vk_registry.match(**kwargs):
        try:
            handler.func(ctx)
        except Exception:
            logging.exception(f'Handler {handler.func.__name__} crashed for user {ctx.user_id}')
            continue

        if ctx.is_consumed:
            logging.info(
                f'Handler {handler.func.__name__} matched for '
                f'text="{text}", state="{state}", callback_data="{callback_data}"'
            )
            return True

    return False


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
    4. Once identity is resolved → run registered handlers via vk_registry.match()

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

    # Normalize text for matching
    text = vk_message.text.strip().lower()

    # 1. Try registered handlers with text + state matching
    if _run_registered_handlers(ctx, text=text, state=state):
        return

    # 2. Try registered handlers with text-only matching
    if _run_registered_handlers(ctx, text=text):
        return

    # 3. Try registered handlers with state-only matching
    if state and _run_registered_handlers(ctx, state=state):
        return

    # 4. Fallback: dynamic region toggle (matches against geo folder names from DB)
    handle_region_toggle(ctx)
    if ctx.is_consumed:
        return

    # 5. Unknown command
    handle_unknown(ctx)


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
    3. Extract callback_data from payload and use vk_registry.match()

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

    # Extract callback_data from payload
    payload_dict = ctx.message.payload_as_dict
    if not payload_dict:
        return

    callback_data = payload_dict.get('cmd', '')

    # Run registered handlers matching callback_data
    if _run_registered_handlers(ctx, callback_data=callback_data):
        return

    logging.info(f'handle_callback_event: no handler matched for cmd="{callback_data}"')
