"""Radius settings: menu callbacks and DB-state text input."""

import logging

from maxapi import F
from maxapi.types.updates.message_callback import MessageCallback
from maxapi.types.updates.message_created import MessageCreated

from _dependencies.models import DialogState

from ..common import DBStateFilter, PayloadCmd, _get_chat_id, _get_db, _get_user_id, router
from ..keyboards import MaxKeyboardPresets
from ..message_formatter import (
    RADIUS_DELETED,
    RADIUS_INVALID,
    RADIUS_MENU_TEXT,
    RADIUS_NOT_SET,
    RADIUS_PROMPT,
    RADIUS_SAVED,
    RADIUS_VIEW_TEXT,
)

logger = logging.getLogger(__name__)


@router.message_callback(PayloadCmd('radius'))
async def on_radius_menu(event: MessageCallback) -> None:
    """Show radius settings menu."""
    await event.ack(notification='...')
    await event.edit(
        text=RADIUS_MENU_TEXT,
        attachments=[MaxKeyboardPresets.radius_menu()],
    )


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
        text = RADIUS_VIEW_TEXT.format(radius) if radius else RADIUS_NOT_SET
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
