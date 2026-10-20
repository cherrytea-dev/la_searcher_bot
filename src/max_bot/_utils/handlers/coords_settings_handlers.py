"""Coordinate settings: menu callbacks and DB-state manual text input."""

import logging

from maxapi import F
from maxapi.types.updates.message_callback import MessageCallback
from maxapi.types.updates.message_created import MessageCreated

from _dependencies.models import DialogState

from ..common import DBStateFilter, PayloadCmd, _get_chat_id, _get_db, _get_user_id, router
from ..keyboards import MaxKeyboardPresets
from ..message_formatter import (
    COORDS_DELETED,
    COORDS_INVALID_FORMAT,
    COORDS_INVALID_VALUE,
    COORDS_MANUAL_PROMPT,
    COORDS_MENU_TEXT,
    COORDS_NOT_SET,
    COORDS_SAVED,
    COORDS_VIEW_TEXT,
)

logger = logging.getLogger(__name__)


@router.message_callback(PayloadCmd('coords'))
async def on_coords_menu(event: MessageCallback) -> None:
    """Show coordinate settings menu."""
    await event.ack(notification='...')
    await event.edit(
        text=COORDS_MENU_TEXT,
        attachments=[MaxKeyboardPresets.coords_menu()],
    )


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
