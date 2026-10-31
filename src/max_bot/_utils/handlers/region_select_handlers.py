"""Region selection: federal district choice, pagination and subscribe toggle."""

import logging

from maxapi.types.updates.message_callback import MessageCallback

from _dependencies.common.geo import (
    CMD_DISTRICT_SELECT,
    CMD_PAGINATE_FINISH,
    CMD_PAGINATE_NAV,
    CMD_PAGINATE_TOGGLE,
)

from ..common import (
    PayloadCmd,
    _get_db,
    _get_regions_for_district,
    _get_subscribed_region_names,
    _get_user_id,
    _main_menu_for_user,
    _parse_payload,
    router,
)
from ..keyboards import MaxKeyboardPresets
from ..message_formatter import (
    FED_DISTRICTS_PROMPT,
    INTERNAL_ERROR,
    MAIN_MENU_TEXT,
    REGION_CANNOT_REMOVE_LAST,
    REGION_LIST_PROMPT,
    REGION_SELECTION_DONE,
    REGION_TOGGLED_OFF,
    REGION_TOGGLED_ON,
)

logger = logging.getLogger(__name__)


@router.message_callback(PayloadCmd('region'))
async def on_region_menu(event: MessageCallback) -> None:
    """Show federal districts for region selection."""
    await event.ack(notification='...')
    await event.edit(
        text=FED_DISTRICTS_PROMPT,
        attachments=[MaxKeyboardPresets.fed_districts_inline()],
    )


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
            folder_dict[name] = (*folder_dict.get(name, ()), fid)

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
