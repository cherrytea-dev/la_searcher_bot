import datetime
import logging
from typing import Callable

from _dependencies.commons import get_app_config
from _dependencies.services.state_machine import DialogState, clear_user_state, get_user_state, set_user_state
from _dependencies.services.message_formatter import welcome_new_user, welcome_back_user
from _dependencies.users_management import register_new_user

from .common import VKHandlerResult, VKMessage
from .database import db
from .keyboards import VKKeyboard
from .message_sending import vk_sender

# Type alias for handler functions
HandlerFunc = Callable[[VKMessage, DialogState | None], VKHandlerResult | None]


def handle_unknown(vk_message: VKMessage, state: DialogState | None) -> VKHandlerResult | None:
    """Fallback handler — triggered when no other handler matched."""
    return VKHandlerResult(
        text='не понимаю такой команды, пожалуйста, используйте кнопки со стандартными командами ниже',
        keyboard=VKKeyboard.main_menu(),
    )


# ─── Handler chain ───────────────────────────────────────────────────
# Phase 2 will populate this with actual handlers.
# For now, it contains only the fallback handler.

HANDLER_CHAIN: list[HandlerFunc] = [
    # Phase 2: state handlers will go here
    # Phase 2: command handlers will go here
    # Phase 2: button handlers will go here
    # Fallback
    handle_unknown,
]


def dispatch_event(raw_event: dict) -> str:
    """Main entry point for VK event processing.

    Called from:
    - main.py (VK Callback API HTTP endpoint)
    - bot_polling.py (LongPoll adapter)

    Returns 'ok' for VK Callback API confirmation.
    """
    event_type = raw_event.get('type', '')

    # VK Callback API confirmation handshake
    if event_type == 'confirmation':
        config = get_app_config()
        expected_group_id = 237036024
        if raw_event.get('group_id') == expected_group_id:
            return config.vk_confirmation_code
        logging.warning(f'Unexpected group_id in confirmation: {raw_event.get("group_id")}')
        return 'ok'

    # Parse event
    event_object = raw_event.get('object', {})
    if not event_object:
        logging.warning(f'VK event without object: {raw_event}')
        return 'ok'

    if event_type == 'message_new':
        message_data = event_object.get('message', {})
        if not message_data:
            logging.warning('message_new event without message data')
            return 'ok'

        vk_message = VKMessage(
            text=message_data.get('text', ''),
            user_id=message_data.get('from_id', 0),
            peer_id=message_data.get('peer_id', 0),
            message_id=message_data.get('id'),
        )
        handle_new_message(vk_message)

    elif event_type == 'message_event':
        # Callback from inline keyboard (VK Callback API Events)
        vk_message = VKMessage(
            text='',
            user_id=event_object.get('user_id', 0),
            peer_id=event_object.get('peer_id', 0),
            message_id=event_object.get('message_id'),
            payload=event_object.get('payload'),
            event_id=event_object.get('event_id'),
        )
        handle_callback_event(vk_message)

    else:
        logging.debug(f'Unhandled VK event type: {event_type}')

    return 'ok'


def handle_new_message(vk_message: VKMessage) -> None:
    """Process a new message from a user.

    Flow:
    1. Resolve user_id (vk_id → system user_id)
    2. Check if new user → register + onboarding
    3. Get current dialog state
    4. Run handler chain
    5. Send response
    """
    user_id = db().resolve_user_id(vk_message.user_id)
    peer_id = vk_message.peer_id

    logging.info(f'VK message from vk_user={vk_message.user_id}, system_user={user_id}: {vk_message.text}')

    # Check if user is new
    if db().settings.check_if_new_user(user_id):
        _handle_new_vk_user(user_id, peer_id, vk_message)
        return

    # Get current dialog state
    state = get_user_state(user_id)

    # Run handler chain
    for handler in HANDLER_CHAIN:
        try:
            result = handler(vk_message, state)
        except Exception:
            logging.exception(f'Handler {handler.__name__} crashed for user {user_id}')
            continue

        if result is None:
            continue

        _process_vk_result(user_id, peer_id, result)
        return

    # Fallback — unknown command
    _process_vk_result(
        user_id,
        peer_id,
        VKHandlerResult(
            text='не понимаю такой команды, пожалуйста, используйте кнопки со стандартными командами ниже',
            keyboard=VKKeyboard.main_menu(),
        ),
    )


def handle_callback_event(vk_message: VKMessage) -> None:
    """Process a callback event from an inline keyboard button.

    VK inline keyboards are limited (URL only), but message_event
    can be used for interactive elements.
    """
    # For now, just acknowledge the event
    vk_sender().send_callback_answer(
        event_id=vk_message.event_id or '',
        user_id=vk_message.user_id,
        peer_id=vk_message.peer_id,
    )


def _handle_new_vk_user(user_id: int, peer_id: int, vk_message: VKMessage) -> None:
    """Register a new VK user and start onboarding."""
    logging.info(f'New VK user registered: system_user={user_id}, vk_user={vk_message.user_id}')

    register_new_user(user_id, None, datetime.datetime.now())

    welcome_text = welcome_new_user()
    vk_sender().send_message(
        peer_id=peer_id,
        text=welcome_text,
        keyboard=VKKeyboard.role_choice(),
    )


def _process_vk_result(user_id: int, peer_id: int, result: VKHandlerResult) -> None:
    """Send the handler result to the user and update dialog state."""
    if result.edit_message_id is not None:
        # Edit existing message
        vk_sender().edit_message(
            peer_id=peer_id,
            message_id=result.edit_message_id,
            text=result.text,
            keyboard=result.keyboard,
        )
    else:
        # Send new message
        vk_sender().send_message(
            peer_id=peer_id,
            text=result.text,
            keyboard=result.keyboard,
            attachment=result.attachment or '',
        )

    # Update dialog state
    if result.new_state is not None:
        set_user_state(user_id, result.new_state)
    elif result.text:
        # Any new message resets the dialog state
        clear_user_state(user_id)
