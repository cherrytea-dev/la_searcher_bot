"""Message and callback handlers for the MAX bot.

Uses the ``maxapi`` library's ``Router`` + ``Dispatcher`` pattern with
magic filters (``F``) and command filters (``Command``).

Dialog state (FSM) is persisted in PostgreSQL via ``DialogStateMixin``
(shared with Telegram and VK bots), so state survives Yandex Cloud Function
cold starts and container instance switches.

Flow:
    1. ``bot_started`` / ``/start`` → register user → show main menu
    2. Main menu buttons → region / radius / coords sub-menus
    3. Region: federal districts → paginated regions → toggle subscribe
    4. Radius: DB state ``waiting_for_radius`` → save to DB
    5. Coords: DB state ``waiting_for_coords`` or geo location → save to DB
"""

import json
import logging
from typing import Any

from maxapi import F, Router
from maxapi.enums.attachment import AttachmentType
from maxapi.filters.command import Command
from maxapi.filters.filter import BaseFilter
from maxapi.types.attachments import Location
from maxapi.types.attachments.buttons.attachment_button import AttachmentButton
from maxapi.types.updates import UpdateUnion
from maxapi.types.updates.bot_started import BotStarted
from maxapi.types.updates.message_callback import MessageCallback
from maxapi.types.updates.message_created import MessageCreated

from _dependencies.bot.users_management import ManageUserAction
from _dependencies.common.commons import Messenger
from _dependencies.common.geo import (
    CMD_DISTRICT_SELECT,
    CMD_PAGINATE_FINISH,
    CMD_PAGINATE_NAV,
    CMD_PAGINATE_TOGGLE,
)
from _dependencies.models import DialogState
from _dependencies.user_repository import UserRepository

from .keyboards import MaxKeyboardPresets
from .message_formatter import (
    COORDS_DELETED,
    COORDS_INVALID_FORMAT,
    COORDS_INVALID_VALUE,
    COORDS_MANUAL_PROMPT,
    COORDS_MENU_TEXT,
    COORDS_NOT_SET,
    COORDS_SAVED,
    COORDS_VIEW_TEXT,
    FED_DISTRICTS_PROMPT,
    FSM_CANCELLED,
    INTERNAL_ERROR,
    MAIN_MENU_TEXT,
    NOTIFICATIONS_DISABLED,
    NOTIFICATIONS_ENABLED,
    RADIUS_DELETED,
    RADIUS_INVALID,
    RADIUS_MENU_TEXT,
    RADIUS_NOT_SET,
    RADIUS_PROMPT,
    RADIUS_SAVED,
    RADIUS_VIEW_TEXT,
    REGION_CANNOT_REMOVE_LAST,
    REGION_LIST_PROMPT,
    REGION_SELECTION_DONE,
    REGION_TOGGLED_OFF,
    REGION_TOGGLED_ON,
    UNKNOWN_COMMAND,
    WELCOME_TEXT,
)

logger = logging.getLogger(__name__)

router = Router()


class PayloadCmd(BaseFilter):
    """Filter that matches ``MessageCallback`` events by parsed JSON payload ``cmd`` field.

    ``Callback.payload`` is a ``str | None`` (JSON-encoded), so the
    magic filter ``F.callback.payload.cmd`` cannot access the nested
    ``cmd`` key directly. This filter parses the JSON and checks the
    ``cmd`` value.

    Usage::

        @router.message_callback(PayloadCmd('region'))
        async def handler(event: MessageCallback) -> None: ...
    """

    def __init__(self, cmd: str) -> None:
        self._cmd = cmd

    async def __call__(self, event: UpdateUnion) -> bool:
        if not isinstance(event, MessageCallback):
            return False
        payload_str = event.callback.payload
        if not payload_str:
            return False
        try:
            data = json.loads(payload_str)
        except (json.JSONDecodeError, TypeError):
            return False
        return data.get('cmd') == self._cmd


class DBStateFilter(BaseFilter):
    """Filter that matches ``MessageCreated`` events by the user's DB-persisted dialog state.

    Checks the ``msg_from_bot`` table via ``DialogStateMixin.get_user_state()``.
    This is the DB-backed replacement for ``maxapi.filters.state.StateFilter``,
    which stores state in-memory only and does not survive Yandex Cloud Function
    cold starts.

    Usage::

        @router.message_created(F.message.body.text, DBStateFilter(DialogState.waiting_for_radius))
        async def handler(event: MessageCreated) -> None: ...
    """

    def __init__(self, state: DialogState) -> None:
        self._state = state

    async def __call__(self, event: UpdateUnion) -> bool:
        if not isinstance(event, MessageCreated):
            return False
        user_id = event.message.sender.user_id if event.message.sender else None
        if user_id is None:
            return False
        db = UserRepository()
        current_state = db.get_user_state(user_id)
        return current_state == self._state


# ─── Helpers ──────────────────────────────────────────────────────────────


def _get_db() -> UserRepository:
    """Get a UserRepository instance (lazy, uses AppConfig)."""
    return UserRepository()


def _get_user_id(event: MessageCreated | MessageCallback) -> int | None:
    """Extract user_id from a message or callback event."""
    if isinstance(event, MessageCreated):
        return event.message.sender.user_id if event.message.sender else None
    return event.callback.user.user_id


def _get_chat_id(event: MessageCreated | MessageCallback) -> int | None:
    """Extract chat_id from a message or callback event."""
    if isinstance(event, MessageCreated):
        return event.message.recipient.chat_id
    if event.message is not None:
        return event.message.recipient.chat_id
    return None


def _parse_payload(payload_str: str | None) -> dict[str, Any]:
    """Parse a JSON callback payload string into a dict."""
    if not payload_str:
        return {}
    try:
        return json.loads(payload_str)
    except (json.JSONDecodeError, TypeError):
        logger.warning('Failed to parse callback payload: %s', payload_str)
        return {}


def _ensure_user_registered(user_id: int) -> bool:
    """Register user if new. Returns True if freshly registered.

    Must be called at the start of every message handler that processes
    user input, not just bot_started/start. Otherwise users who skip
    /start (e.g., send arbitrary text or location right away) can save
    settings without a corresponding record in the ``users`` table.
    """
    db = _get_db()
    is_new = db.check_if_new_user(user_id)
    if is_new:
        db.register_user(user_id, Messenger.MAX)
        db.save_default_topic_types(user_id, None)
        logger.info('Registered new user %s via ensure_user_registered', user_id)
    return is_new


def _notifications_disabled(user_id: int) -> bool:
    """Return whether the user explicitly unsubscribed from notifications."""
    return _get_db().get_user_status(user_id) == 'unsubscribed'


def _main_menu_for_user(user_id: int) -> AttachmentButton:
    """Return MAX main menu with the delivery-status action matching user status."""
    return MaxKeyboardPresets.main_menu(notifications_disabled=_notifications_disabled(user_id))


def _get_regions_for_district(district: str) -> list[tuple[int, str]]:
    """Get (folder_id, display_name) list for a federal district."""
    db = _get_db()
    return db.get_geo_folders_by_district(district)


def _get_subscribed_region_names(user_id: int) -> set[str]:
    """Get set of region display names the user is subscribed to."""
    db = _get_db()
    subscribed_folder_ids = set(db.get_user_regions(user_id))
    all_folders = db.get_geo_folders()
    return {name for fid, name in all_folders if fid in subscribed_folder_ids}


# ─── Registration & Main Menu ────────────────────────────────────────────


@router.bot_started()
async def on_bot_started(event: BotStarted) -> None:
    """Handle ``bot_started`` — user first opens a chat with the bot.

    Registers the user if new, then shows the main menu.
    """
    user_id = event.user.user_id
    chat_id = event.chat_id
    logger.info('Bot started by user %s in chat %s', user_id, chat_id)

    bot = event.bot
    if bot is None:
        logger.error('Bot instance is None in bot_started handler')
        return

    try:
        await bot.send_message(
            chat_id=chat_id,
            text=WELCOME_TEXT,
            attachments=[_main_menu_for_user(user_id)],  # type: ignore[arg-type]
        )
    except Exception:
        logger.exception('Error in bot_started for user %s', user_id)
        await bot.send_message(chat_id=chat_id, text=INTERNAL_ERROR)


@router.message_created(Command('start'))
async def on_start(event: MessageCreated) -> None:
    """Handle ``/start`` command — register user and show main menu."""
    user_id = _get_user_id(event)
    chat_id = _get_chat_id(event)
    logger.info('Start command from user %s', user_id)

    if user_id is None or chat_id is None:
        return

    try:
        await event.message.answer(
            text=WELCOME_TEXT,
            attachments=[_main_menu_for_user(user_id)],
        )
    except Exception:
        logger.exception('Error in /start for user %s', user_id)
        await event.message.answer(text=INTERNAL_ERROR)


# ─── Callback: Main Menu Navigation ──────────────────────────────────────


@router.message_callback(PayloadCmd('back_to_main'))
async def on_back_to_main(event: MessageCallback) -> None:
    """Return to main menu."""
    await event.ack(notification='...')
    await event.edit(
        text=MAIN_MENU_TEXT,
        attachments=[_main_menu_for_user(event.callback.user.user_id)],
    )


@router.message_callback(PayloadCmd('region'))
async def on_region_menu(event: MessageCallback) -> None:
    """Show federal districts for region selection."""
    await event.ack(notification='...')
    await event.edit(
        text=FED_DISTRICTS_PROMPT,
        attachments=[MaxKeyboardPresets.fed_districts_inline()],
    )


@router.message_callback(PayloadCmd('radius'))
async def on_radius_menu(event: MessageCallback) -> None:
    """Show radius settings menu."""
    await event.ack(notification='...')
    await event.edit(
        text=RADIUS_MENU_TEXT,
        attachments=[MaxKeyboardPresets.radius_menu()],
    )


@router.message_callback(PayloadCmd('coords'))
async def on_coords_menu(event: MessageCallback) -> None:
    """Show coordinate settings menu."""
    await event.ack(notification='...')
    await event.edit(
        text=COORDS_MENU_TEXT,
        attachments=[MaxKeyboardPresets.coords_menu()],
    )


@router.message_callback(PayloadCmd('disable_notifications'))
async def on_disable_notifications(event: MessageCallback) -> None:
    """Explicitly unsubscribe from all notifications."""
    user_id = _get_user_id(event)
    if user_id is None:
        return

    db = _get_db()
    db.update_user_status(user_id, ManageUserAction.unsubscribe_user)
    await event.ack(notification='...')
    await event.edit(
        text=NOTIFICATIONS_DISABLED,
        attachments=[MaxKeyboardPresets.main_menu(notifications_disabled=True)],
    )


@router.message_callback(PayloadCmd('enable_notifications'))
async def on_enable_notifications(event: MessageCallback) -> None:
    """Re-enable notifications after explicit unsubscribe."""
    user_id = _get_user_id(event)
    if user_id is None:
        return

    db = _get_db()
    db.update_user_status(user_id, ManageUserAction.subscribe_user)
    await event.ack(notification='...')
    await event.edit(
        text=NOTIFICATIONS_ENABLED,
        attachments=[MaxKeyboardPresets.main_menu(notifications_disabled=False)],
    )


# ─── Region Selection: Federal Districts ─────────────────────────────────


@router.message_callback(PayloadCmd(CMD_DISTRICT_SELECT))
async def on_district_select(event: MessageCallback) -> None:
    """Show paginated regions for the selected federal district."""
    payload = _parse_payload(event.callback.payload)
    district = payload.get('district', '')
    logger.info('District selected: %s', district)

    regions = _get_regions_for_district(district)
    if not regions:
        await event.ack(notification='В этом округе пока нет доступных регионов.')
        return

    user_id = _get_user_id(event)
    subscribed_names = _get_subscribed_region_names(user_id) if user_id else set()

    region_names = [name for _fid, name in regions]

    await event.ack(notification='...')
    await event.edit(
        text=REGION_LIST_PROMPT,
        attachments=[
            MaxKeyboardPresets.paginated_regions_inline(
                region_buttons=region_names,
                page=0,
                district=district,
                subscribed_ids=subscribed_names,
            )
        ],
    )


# ─── Region Selection: Pagination ────────────────────────────────────────


@router.message_callback(PayloadCmd(CMD_PAGINATE_NAV))
async def on_paginate_nav(event: MessageCallback) -> None:
    """Navigate between pages of regions."""
    payload = _parse_payload(event.callback.payload)
    district = payload.get('district', '')
    page = payload.get('page', 0)

    user_id = _get_user_id(event)

    regions = _get_regions_for_district(district)
    region_names = [name for _fid, name in regions]

    subscribed_names = _get_subscribed_region_names(user_id) if user_id else set()

    await event.ack(notification='...')
    await event.edit(
        text=REGION_LIST_PROMPT,
        attachments=[
            MaxKeyboardPresets.paginated_regions_inline(
                region_buttons=region_names,
                page=page,
                district=district,
                subscribed_ids=subscribed_names,
            )
        ],
    )


# ─── Region Selection: Toggle Subscribe ──────────────────────────────────


@router.message_callback(PayloadCmd(CMD_PAGINATE_TOGGLE))
async def on_paginate_toggle(event: MessageCallback) -> None:
    """Toggle subscription for a region."""
    payload = _parse_payload(event.callback.payload)
    region_name = payload.get('region', '')
    district = payload.get('district', '')
    page = payload.get('page', 0)
    user_id = _get_user_id(event)

    if not user_id or not region_name:
        await event.ack(notification='Ошибка: не удалось определить регион.')
        return

    db = _get_db()

    # Build folder_dict: region_name -> (folder_id, ...).
    # Use ALL geo folders (not the grouped district list) because a display
    # name can map to multiple folder IDs (e.g., Москва и МО – Завершенные
    # поиски has folder_ids 411, 412, 415).  Toggling MUST cover all of
    # them to avoid stale checkmarks.
    all_folders = db.get_geo_folders()
    folder_dict: dict[str, tuple[int, ...]] = {}
    for fid, name in all_folders:
        if name:
            folder_dict[name] = folder_dict.get(name, ()) + (fid,)

    # Keep the district-scoped list for keyboard building
    regions = _get_regions_for_district(district)

    try:
        success = db.toggle_region_by_name(user_id, region_name, folder_dict)
    except Exception:
        logger.exception('Error toggling region for user %s', user_id)
        await event.ack(notification=INTERNAL_ERROR)
        return

    if not success:
        await event.ack(notification=REGION_CANNOT_REMOVE_LAST)
    else:
        # Determine if subscribed or unsubscribed
        subscribed_names = _get_subscribed_region_names(user_id)
        if region_name in subscribed_names:
            await event.ack(notification=REGION_TOGGLED_ON)
        else:
            await event.ack(notification=REGION_TOGGLED_OFF)

    # Refresh the keyboard
    region_names = [name for _fid, name in regions]
    subscribed_names = _get_subscribed_region_names(user_id)

    await event.edit(
        text=REGION_LIST_PROMPT,
        attachments=[
            MaxKeyboardPresets.paginated_regions_inline(
                region_buttons=region_names,
                page=page,
                district=district,
                subscribed_ids=subscribed_names,
            )
        ],
    )


@router.message_callback(PayloadCmd(CMD_PAGINATE_FINISH))
async def on_paginate_finish(event: MessageCallback) -> None:
    """Finish region selection and return to main menu."""
    await event.ack(notification=REGION_SELECTION_DONE)
    user_id = _get_user_id(event)
    if user_id is None:
        return
    await event.edit(
        text=MAIN_MENU_TEXT,
        attachments=[_main_menu_for_user(user_id)],
    )


# ─── Radius Settings ─────────────────────────────────────────────────────


@router.message_callback(PayloadCmd('radius_set'))
async def on_radius_set(event: MessageCallback) -> None:
    """Start DB-backed dialog state for radius input."""
    user_id = _get_user_id(event)

    await event.ack(notification='...')

    # Set DB-persisted dialog state (reuses existing radius_input state)
    if user_id is not None:
        db = _get_db()
        db.set_user_state(user_id, DialogState.radius_input)
        logger.info('Set DB state radius_input for user %s', user_id)

    await event.edit(
        text=RADIUS_PROMPT,
        attachments=[MaxKeyboardPresets.back_to_main()],
    )


@router.message_callback(PayloadCmd('radius_view'))
async def on_radius_view(event: MessageCallback) -> None:
    """Show current radius."""
    user_id = _get_user_id(event)
    if user_id:
        db = _get_db()
        radius = db.get_radius(user_id)
        if radius:
            text = RADIUS_VIEW_TEXT.format(radius)
        else:
            text = RADIUS_NOT_SET
    else:
        text = RADIUS_NOT_SET

    await event.ack(notification='...')
    await event.edit(
        text=text,
        attachments=[MaxKeyboardPresets.radius_menu()],
    )


@router.message_callback(PayloadCmd('radius_delete'))
async def on_radius_delete(event: MessageCallback) -> None:
    """Delete current radius."""
    user_id = _get_user_id(event)
    if user_id:
        db = _get_db()
        db.delete_radius(user_id)

    await event.ack(notification=RADIUS_DELETED)
    await event.edit(
        text=RADIUS_MENU_TEXT,
        attachments=[MaxKeyboardPresets.radius_menu()],
    )


# ─── Coordinates Settings ────────────────────────────────────────────────


@router.message_callback(PayloadCmd('coords_enter'))
async def on_coords_enter(event: MessageCallback) -> None:
    """Start DB-backed dialog state for manual coordinate input."""
    user_id = _get_user_id(event)

    await event.ack(notification='...')

    if user_id is not None:
        db = _get_db()
        db.set_user_state(user_id, DialogState.input_of_coords_man)
        logger.info('Set DB state input_of_coords_man for user %s', user_id)

    await event.edit(
        text=COORDS_MANUAL_PROMPT,
        attachments=[MaxKeyboardPresets.back_to_main()],
    )


@router.message_callback(PayloadCmd('coords_view'))
async def on_coords_view(event: MessageCallback) -> None:
    """Show current coordinates."""
    user_id = _get_user_id(event)
    if user_id:
        db = _get_db()
        coords = db.get_coordinates(user_id)
        if coords:
            lat, lng = coords
            text = COORDS_VIEW_TEXT.format(lat, lng)
        else:
            text = COORDS_NOT_SET
    else:
        text = COORDS_NOT_SET

    await event.ack(notification='...')
    await event.edit(
        text=text,
        attachments=[MaxKeyboardPresets.coords_menu()],
    )


@router.message_callback(PayloadCmd('coords_delete'))
async def on_coords_delete(event: MessageCallback) -> None:
    """Delete current coordinates."""
    user_id = _get_user_id(event)
    if user_id:
        db = _get_db()
        db.delete_coordinates(user_id)

    await event.ack(notification=COORDS_DELETED)
    await event.edit(
        text=COORDS_MENU_TEXT,
        attachments=[MaxKeyboardPresets.coords_menu()],
    )


# ─── DB State: Waiting for Radius ────────────────────────────────────────


@router.message_created(
    F.message.body.text,
    DBStateFilter(DialogState.radius_input),
)
async def on_radius_text(event: MessageCreated) -> None:
    """Handle radius input during DB-backed dialog state."""
    user_id = _get_user_id(event)
    chat_id = _get_chat_id(event)

    if user_id is None or chat_id is None:
        return

    body = event.message.body
    if body is None or body.text is None:
        return

    text = body.text.strip()

    # Clear DB state
    db = _get_db()
    db.clear_user_state(user_id)

    # Validate: must be integer 1-1000
    try:
        radius = int(text)
        if radius < 1 or radius > 1000:
            raise ValueError
    except (ValueError, TypeError):
        await event.message.answer(
            text=RADIUS_INVALID,
            attachments=[MaxKeyboardPresets.radius_menu()],
        )
        return

    db.save_radius(user_id, radius)
    logger.info('User %s set radius to %s km', user_id, radius)

    await event.message.answer(
        text=RADIUS_SAVED.format(radius),
        attachments=[MaxKeyboardPresets.radius_menu()],
    )


# ─── DB State: Waiting for Coordinates (manual text input) ────────────────


@router.message_created(
    F.message.body.text,
    DBStateFilter(DialogState.input_of_coords_man),
)
async def on_coords_text(event: MessageCreated) -> None:
    """Handle manual coordinate input during DB-backed dialog state.

    Expected format: ``latitude, longitude`` (e.g., ``55.7558, 37.6173``).
    """
    user_id = _get_user_id(event)
    chat_id = _get_chat_id(event)

    if user_id is None or chat_id is None:
        return

    body = event.message.body
    if body is None or body.text is None:
        return

    text = body.text.strip()

    # Clear DB state
    db = _get_db()
    db.clear_user_state(user_id)

    # Parse "lat, lng" format
    parts = text.replace(';', ',').split(',')
    if len(parts) != 2:
        await event.message.answer(
            text=COORDS_INVALID_FORMAT,
            attachments=[MaxKeyboardPresets.coords_menu()],
        )
        return

    try:
        lat = float(parts[0].strip())
        lng = float(parts[1].strip())
    except (ValueError, TypeError):
        await event.message.answer(
            text=COORDS_INVALID_FORMAT,
            attachments=[MaxKeyboardPresets.coords_menu()],
        )
        return

    # Validate ranges
    if not (-90 <= lat <= 90) or not (-180 <= lng <= 180):
        await event.message.answer(
            text=COORDS_INVALID_VALUE,
            attachments=[MaxKeyboardPresets.coords_menu()],
        )
        return

    db.save_coordinates(user_id, lat, lng)
    logger.info('User %s set coordinates: %s, %s', user_id, lat, lng)

    await event.message.answer(
        text=COORDS_SAVED.format(lat, lng),
        attachments=[MaxKeyboardPresets.coords_menu()],
    )


# ─── Geo Location (from native geo button) ────────────────────────────────


@router.message_created(F.message.body.attachments)
async def on_geo_location(event: MessageCreated) -> None:
    """Handle messages with attachments — specifically geo location.

    When a user sends their location via the ``RequestGeoLocationButton``,
    the message contains a ``Location`` attachment.
    """
    user_id = _get_user_id(event)
    chat_id = _get_chat_id(event)
    attachments = event.message.body.attachments if event.message.body else None

    if user_id is None or chat_id is None:
        return

    if not attachments:
        return

    # Look for a Location attachment
    location: Location | None = None
    for att in attachments:
        if isinstance(att, Location) or (hasattr(att, 'type') and att.type == AttachmentType.LOCATION):
            location = att  # type: ignore[assignment]
            break

    if location is None:
        # Has attachments but not a location — could be an image, etc.
        # If user is in a DB dialog state, clear it and show menu
        db = _get_db()
        current_state = db.get_user_state(user_id)
        if current_state is not None and current_state != DialogState.not_defined:
            db.clear_user_state(user_id)
            await event.message.answer(
                text=FSM_CANCELLED,
                attachments=[_main_menu_for_user(user_id)],
            )
        return

    lat = location.latitude
    lng = location.longitude

    if lat is None or lng is None:
        await event.message.answer(
            text=COORDS_INVALID_FORMAT,
            attachments=[MaxKeyboardPresets.coords_menu()],
        )
        return

    # Clear any DB dialog state
    db = _get_db()
    db.clear_user_state(user_id)

    db.save_coordinates(user_id, lat, lng)
    logger.info('User %s set coordinates via geo: %s, %s', user_id, lat, lng)

    await event.message.answer(
        text=COORDS_SAVED.format(lat, lng),
        attachments=[MaxKeyboardPresets.coords_menu()],
    )


# ─── Fallback ─────────────────────────────────────────────────────────────


@router.message_created(F.message.body.text)
async def on_unknown_text(event: MessageCreated) -> None:
    """Fallback handler for any unrecognized text message.

    If the user is in a DB dialog state, clear it and show the main menu.
    Otherwise, show the main menu.
    """
    user_id = _get_user_id(event)
    chat_id = _get_chat_id(event)

    if user_id is None or chat_id is None:
        return

    # Check if user is in a DB dialog state
    db = _get_db()
    current_state = db.get_user_state(user_id)
    if current_state is not None and current_state != DialogState.not_defined:
        db.clear_user_state(user_id)
        await event.message.answer(
            text=FSM_CANCELLED,
            attachments=[_main_menu_for_user(user_id)],
        )
        return

    await event.message.answer(
        text=UNKNOWN_COMMAND,
        attachments=[_main_menu_for_user(user_id)],
    )
