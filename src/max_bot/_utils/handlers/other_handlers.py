"""Geo location handler and catch-all fallback.

``on_geo_location`` must stay above ``on_unknown_text`` in this file:
the router executes the first matching handler and stops.
"""

import logging

from maxapi import F
from maxapi.enums.attachment import AttachmentType
from maxapi.types.attachments import Location
from maxapi.types.updates.message_created import MessageCreated

from _dependencies.models import DialogState

from ..common import _get_chat_id, _get_db, _get_user_id, _main_menu_for_user, router
from ..keyboards import MaxKeyboardPresets
from ..message_formatter import (
    COORDS_INVALID_FORMAT,
    COORDS_SAVED,
    FSM_CANCELLED,
    UNKNOWN_COMMAND,
)

logger = logging.getLogger(__name__)


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
