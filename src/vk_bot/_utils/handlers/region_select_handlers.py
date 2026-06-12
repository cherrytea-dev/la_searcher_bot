"""Region selection flow handlers for the VK bot.

Handles federal district selection and region toggle (subscribe/unsubscribe).
Uses geo_folders from the database to build the region hierarchy.
"""

import logging

from _dependencies.services.message_formatter import (
    region_selection_cant_remove_last,
    region_selection_intro,
)
from _dependencies.services.state_machine import DialogState

from ..common import VKHandlerResult, VKMessage
from ..database import db
from ..keyboards import VKKeyboard

logger = logging.getLogger(__name__)


def handle_fed_district_select(
    vk_message: VKMessage, state: DialogState | None, user_id: int
) -> VKHandlerResult | None:
    """Handle federal district selection — show regions in that district.

    Matches button text from VKKeyboard.fed_districts().
    Looks up the district in geo_folders and returns a keyboard with regions.
    """
    text = vk_message.text.strip().lower()

    # Known federal districts from VKKeyboard.fed_districts()
    known_districts = [
        'центральный фо',
        'северо-западный фо',
        'южный фо',
        'северо-кавказский фо',
        'приволжский фо',
        'уральский фо',
        'сибирский фо',
        'дальневосточный фо',
        'прочие поиски по рф',
    ]

    if text not in known_districts:
        return None

    # Get all geo folders — returns list of (folder_id, folder_display_name)
    folders = db().settings.get_geo_folders()
    if not folders:
        return VKHandlerResult(
            text='Регионы пока не загружены. Попробуйте позже.',
            keyboard=VKKeyboard.fed_districts(),
        )

    # Build a folder_id → display_name mapping
    folder_map: dict[int, str] = {fid: name for fid, name in folders}

    # Build a set of district names that contain 'фо' and match exactly
    district_names = set()
    for fid, name in folders:
        if 'фо' in name.lower():
            district_names.add(name.strip())

    matched_district = None
    for d_name in district_names:
        if d_name.lower() == text.lower():
            matched_district = d_name
            break

    if not matched_district:
        # Fallback: try to find matching regions by name similarity
        matching_regions: list[str] = []
        for fid, name in folders:
            name_lower = name.lower()
            if text.replace(' фо', '') in name_lower:
                matching_regions.append(name)

        if not matching_regions:
            return VKHandlerResult(
                text='В этом округе пока нет доступных регионов.',
                keyboard=VKKeyboard.fed_districts(),
            )

        region_buttons = list(matching_regions)
        region_buttons.append('в начало')
        return VKHandlerResult(
            text=f'Выберите регион в округе "{vk_message.text.strip()}":\n\n'
            'Нажмите на регион, чтобы подписаться или отписаться.',
            keyboard=VKKeyboard.one_column(region_buttons),
        )

    # Build region keyboard from matched district
    region_buttons = [matched_district]
    region_buttons.append('в начало')

    return VKHandlerResult(
        text=f'Выберите регион в округе "{vk_message.text.strip()}":\n\n'
        'Нажмите на регион, чтобы подписаться или отписаться.',
        keyboard=VKKeyboard.one_column(region_buttons),
    )


def handle_region_toggle(vk_message: VKMessage, state: DialogState | None, user_id: int) -> VKHandlerResult | None:
    """Handle region toggle (subscribe/unsubscribe).

    Matches any text that corresponds to a known geo folder name.
    Uses toggle_region_by_name which requires a folder_dict parameter.
    Checks subscription state before toggling to provide correct feedback.
    """
    text = vk_message.text.strip()
    if not text:
        return None

    # Get all geo folders
    folders = db().settings.get_geo_folders()
    if not folders:
        return None

    # Build folder_dict: {display_name: (folder_id,)}
    # Filter out None folder names (can happen if DB has NULL folder_display_name)
    folder_dict: dict[str, tuple[int, ...]] = {}
    for fid, name in folders:
        if name is not None:
            folder_dict[name] = (fid,)

    if not folder_dict:
        return None

    # Case-insensitive matching
    region_name_lower = text.lower()
    matching = [name for name in folder_dict if name.lower() == region_name_lower]
    if not matching:
        return None
    region_name = matching[0]
    region_folder_ids = folder_dict[region_name]

    # Check current subscription state by comparing folder IDs
    user_region_folder_ids = list(db().settings.get_user_regions(user_id))
    is_subscribed = any(fid in user_region_folder_ids for fid in region_folder_ids)

    if is_subscribed:
        try:
            result = db().settings.toggle_region_by_name(user_id, region_name, folder_dict)
        except Exception:
            logger.exception(f'Failed to toggle region for user {user_id}: {region_name}')
            return None

        if result is False:
            return VKHandlerResult(
                text=region_selection_cant_remove_last(),
                keyboard=VKKeyboard.settings_menu(),
            )
        return VKHandlerResult(
            text=f'Регион "{region_name}" удален.',
            keyboard=VKKeyboard.settings_menu(),
        )
    else:
        try:
            db().settings.toggle_region_by_name(user_id, region_name, folder_dict)
        except Exception:
            logger.exception(f'Failed to toggle region for user {user_id}: {region_name}')
            return None
        return VKHandlerResult(
            text=f'Регион "{region_name}" добавлен!',
            keyboard=VKKeyboard.settings_menu(),
        )
