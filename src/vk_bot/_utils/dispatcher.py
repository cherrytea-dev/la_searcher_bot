import datetime
import logging
from typing import Callable

from _dependencies.commons import get_app_config
from _dependencies.services.message_formatter import welcome_back_user, welcome_new_user
from _dependencies.services.state_machine import DialogState, clear_user_state, get_user_state, set_user_state
from _dependencies.users_management import register_new_user

from .common import VKHandlerResult, VKMessage
from .database import db
from .keyboards import VKKeyboard
from .message_sending import vk_sender

# Type alias for handler functions
# Third parameter (int) is the resolved system user_id.
HandlerFunc = Callable[[VKMessage, DialogState | None, int], VKHandlerResult | None]


def handle_unknown(vk_message: VKMessage, state: DialogState | None, user_id: int = 0) -> VKHandlerResult | None:
    """Fallback handler — triggered when no other handler matched."""
    return VKHandlerResult(
        text='не понимаю такой команды, пожалуйста, используйте кнопки со стандартными командами ниже',
        keyboard=VKKeyboard.main_menu(),
    )


# ─── Handler chain ───────────────────────────────────────────────────

from .handlers.button_handlers import (
    handle_age_settings,
    handle_back_to_start,
    handle_command_start,
    handle_coordinates_action,
    handle_forum_linking,
    handle_help_needed,
    handle_is_moscow,
    handle_main_menu,
    handle_notification_toggle,
    handle_orders_state,
    handle_other_menu,
    handle_role_choice,
    handle_settings_menu,
    handle_topic_type_settings,
    handle_vk_linking,
)
from .handlers.region_select_handlers import (
    handle_fed_district_select,
    handle_region_toggle,
)
from .handlers.state_handlers import (
    handle_coords_text,
    handle_forum_username,
    handle_radius_value,
)
from .handlers.view_searches_handlers import (
    handle_active_searches,
    handle_follow_mode_toggle,
    handle_follow_unfollow_command,
    handle_latest_searches,
    handle_more_searches,
    handle_search_follow_menu,
    handle_view_search_menu,
)

HANDLER_CHAIN: list[HandlerFunc] = [
    # State-based handlers first (highest priority)
    handle_radius_value,
    handle_coords_text,
    handle_forum_username,
    # Onboarding
    handle_command_start,
    handle_role_choice,
    handle_orders_state,
    handle_is_moscow,
    handle_help_needed,
    # Navigation
    handle_back_to_start,
    handle_main_menu,
    # Search viewing handlers (Phase 2B) — before button_handlers to catch
    # text commands like +12345 / -12345 and search-related menu items
    handle_view_search_menu,
    handle_active_searches,
    handle_latest_searches,
    handle_search_follow_menu,
    handle_follow_mode_toggle,
    handle_follow_unfollow_command,
    handle_more_searches,
    # Region selection
    handle_fed_district_select,
    handle_region_toggle,
    # Settings
    handle_settings_menu,
    handle_notification_toggle,
    handle_coordinates_action,
    handle_age_settings,
    handle_topic_type_settings,
    handle_forum_linking,
    handle_vk_linking,
    handle_other_menu,
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
        expected_group_id = config.vk_group_id
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

    elif event_type == 'message_edit':
        # Edited messages — process same as new (user may have corrected input)
        message_data = event_object.get('message', {})
        if not message_data:
            logging.warning('message_edit event without message data')
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

    # Log user message to dialog history — wrapped in try/except to not break on DB errors
    try:
        db().settings.save_user_message(user_id, vk_message.text)
    except Exception:
        logging.exception(f'Failed to save user message to dialog history for user {user_id}')

    # Check if user is new
    if db().settings.check_if_new_user(user_id):
        _handle_new_vk_user(user_id, peer_id, vk_message)
        return

    # Get current dialog state
    state = get_user_state(user_id)

    # Run handler chain — handle_unknown is always last and always returns a result
    for handler in HANDLER_CHAIN:
        try:
            result = handler(vk_message, state, user_id)
        except Exception:
            logging.exception(f'Handler {handler.__name__} crashed for user {user_id}')
            continue

        if result is None:
            continue

        _process_vk_result(user_id, peer_id, result)
        return


def handle_callback_event(vk_message: VKMessage) -> None:
    """Process a callback event from an inline keyboard button.

    VK inline keyboards can have URL buttons (open_link) which don't
    generate callbacks, and callback buttons (callback) which generate
    message_event with a payload.

    When a callback is received:
    1. Acknowledge the event (show snackbar to user)
    2. Parse the payload to determine the action
    3. If the payload contains a command (e.g., '+12345', '-12345'),
       process it through the handler chain as if it were a text message
    """
    # Always acknowledge the event first
    vk_sender().send_callback_answer(
        event_id=vk_message.event_id or '',
        user_id=vk_message.user_id,
        peer_id=vk_message.peer_id,
    )

    # Parse payload — it may contain a command to execute
    payload = vk_message.payload
    if not payload:
        return

    # Payload can be a JSON string or a plain text command
    import json

    try:
        payload_data = json.loads(payload)
        if isinstance(payload_data, dict):
            command = payload_data.get('command', '') or payload_data.get('button', '')
        else:
            command = str(payload_data)
    except (json.JSONDecodeError, TypeError):
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
    handle_new_message(synthetic_message)


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

    # Log dialog history — wrapped in try/except to not break on DB errors
    try:
        db().settings.save_bot_reply(user_id, result.text)
    except Exception:
        logging.exception(f'Failed to save bot reply to dialog history for user {user_id}')
