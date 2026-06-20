"""Region selection flow handlers for the VK bot.

Handles federal district selection and region toggle (subscribe/unsubscribe).
Uses geo_folders from the database to build the region hierarchy.

Pagination (inline callback-based):
- Districts with many regions (e.g., Цетральный ФО has 35 folders)
  are split across multiple pages using inline callback buttons.
- Navigation and region toggle happen via VK message_event callbacks
  with JSON payloads, handled by handle_inline_pagination() and
  handle_district_select() in this module.
- No dialog state is stored for pagination — the keyboard IS the state.
"""

import logging

from ..common import VKHandlerResult, VKMessage
from ..database import DialogState, db
from ..keyboards import VKKeyboardButtons, VKKeyboardPresets
from ..message_sending import VKMessageSender
from ..services.message_formatter import (
    region_selection_cant_remove_last,
    region_selection_intro,
    settings_menu_intro,
)

# Number of region buttons per page (6 items = 3 rows in two_columns layout).
# Kept at 6 to stay under VK's 10-button limit for messages.edit inline keyboards.
_PAGE_SIZE = 6

# Known federal districts from VKKeyboardPresets.fed_districts()
_KNOWN_DISTRICTS = [
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


def _get_district_name(text: str) -> str | None:
    """Extract normalized district name from button text, or None if not a district."""
    text_lower = text.strip().lower()
    if text_lower not in _KNOWN_DISTRICTS:
        return None
    # 'уральский фо' → 'Уральский', 'северо-западный фо' → 'Северо-Западный'
    return text_lower.replace(' фо', '').strip().title()


def _get_folders_for_district(district_name: str) -> list[tuple[int, str]]:
    """Get geo folders for a given federal district name."""
    return db().get_geo_folders_by_district(district_name)


def _get_selected_region_names(user_id: int) -> set[str]:
    """Get set of region display names that the user is subscribed to.

    Matches user's subscribed folder IDs against geo folder display names.
    """
    user_folder_ids = set(db().get_user_regions(user_id))
    if not user_folder_ids:
        return set()

    all_folders = db().get_geo_folders()
    selected: set[str] = set()
    for fid, name in all_folders:
        if name is not None and fid in user_folder_ids:
            selected.add(name)
    return selected


def handle_fed_district_select(
    vk_message: VKMessage, state: DialogState | None, user_id: int
) -> VKHandlerResult | None:
    """Handle federal district selection — show regions in that district.

    Matches button text from VKKeyboardPresets.fed_districts().
    If the district has more than _PAGE_SIZE regions, shows inline paginated view
    (callback-based). Otherwise shows all regions as regular text buttons.

    Already-subscribed regions are highlighted with 'primary' (green) color.
    """
    district_name = _get_district_name(vk_message.text)
    if district_name is None:
        return None

    # Query folders by federal district from the database
    folders = _get_folders_for_district(district_name)
    if not folders:
        return VKHandlerResult(
            text='В этом округе пока нет доступных регионов.',
            keyboard=VKKeyboardPresets.fed_districts(),
        )

    region_buttons = [name for fid, name in folders]
    selected_regions = _get_selected_region_names(user_id)

    # Check if pagination is needed
    total_pages = (len(region_buttons) + _PAGE_SIZE - 1) // _PAGE_SIZE

    if total_pages <= 1:
        # Single page — show all regions as regular text buttons
        buttons = list(region_buttons)
        buttons.append(VKKeyboardButtons.BTN_FINISH)
        return VKHandlerResult(
            text=f'Выберите регион в округе "{vk_message.text.strip()}":\n\n'
            'Нажмите на регион, чтобы подписаться или отписаться.',
            keyboard=VKKeyboardPresets.two_columns(buttons, selected_regions=selected_regions),
        )
    else:
        # Multiple pages — show first page with inline callback keyboard
        return VKHandlerResult(
            text=f'Выберите регион в округе "{vk_message.text.strip()}":\n\n'
            'Нажмите на регион, чтобы подписаться или отписаться.',
            keyboard=VKKeyboardPresets.paginated_regions_inline(
                region_buttons, 0, district_name, selected_regions=selected_regions
            ),
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
    folders = db().get_geo_folders()
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

    return _toggle_region(user_id, region_name, region_folder_ids, folder_dict)


def _toggle_region(
    user_id: int,
    region_name: str,
    region_folder_ids: tuple[int, ...] | None = None,
    folder_dict: dict[str, tuple[int, ...]] | None = None,
) -> VKHandlerResult | None:
    """Toggle region subscription for a user.

    If region_folder_ids and folder_dict are provided, uses them directly.
    Otherwise, looks up the region from the database.
    """
    if region_folder_ids is None or folder_dict is None:
        # Look up from DB
        folders = db().get_geo_folders()
        if not folders:
            return None
        folder_dict = {}
        for fid, name in folders:
            if name is not None:
                folder_dict[name] = (fid,)
        if region_name not in folder_dict:
            return None
        region_folder_ids = folder_dict[region_name]

    # Check current subscription state by comparing folder IDs
    user_region_folder_ids = list(db().get_user_regions(user_id))
    is_subscribed = any(fid in user_region_folder_ids for fid in region_folder_ids)

    if is_subscribed:
        try:
            result = db().toggle_region_by_name(user_id, region_name, folder_dict)
        except Exception:
            logging.exception(f'Failed to toggle region for user {user_id}: {region_name}')
            return None

        if result is False:
            return VKHandlerResult(
                text=region_selection_cant_remove_last(),
                keyboard=VKKeyboardPresets.settings_menu(),
            )
        return VKHandlerResult(
            text=f'Регион "{region_name}" удален.',
            keyboard=VKKeyboardPresets.settings_menu(),
        )
    else:
        try:
            db().toggle_region_by_name(user_id, region_name, folder_dict)
        except Exception:
            logging.exception(f'Failed to toggle region for user {user_id}: {region_name}')
            return None
        return VKHandlerResult(
            text=f'Регион "{region_name}" добавлен!',
            keyboard=VKKeyboardPresets.settings_menu(),
        )


def _toggle_region_inline(user_id: int, region_name: str) -> str:
    """Toggle region subscription for inline callback.

    Lightweight version used by inline pagination callbacks.
    Returns a snackbar text string to display to the user (no VKHandlerResult).
    """
    folders = db().get_geo_folders()
    if not folders:
        return 'Произошла ошибка. Попробуйте позже.'

    folder_dict: dict[str, tuple[int, ...]] = {}
    for fid, name in folders:
        if name is not None:
            folder_dict[name] = (fid,)

    if region_name not in folder_dict:
        return 'Регион не найден.'

    # Check current subscription state
    region_folder_ids = folder_dict[region_name]
    user_region_folder_ids = list(db().get_user_regions(user_id))
    is_subscribed = any(fid in user_region_folder_ids for fid in region_folder_ids)

    if is_subscribed:
        try:
            result = db().toggle_region_by_name(user_id, region_name, folder_dict)
        except Exception:
            logging.exception(f'Failed to toggle region for user {user_id}: {region_name}')
            return 'Произошла ошибка. Попробуйте позже.'

        if result is False:
            return 'Нельзя удалить последний регион.'
        return f'Регион "{region_name}" удален.'
    else:
        try:
            db().toggle_region_by_name(user_id, region_name, folder_dict)
        except Exception:
            logging.exception(f'Failed to toggle region for user {user_id}: {region_name}')
            return 'Произошла ошибка. Попробуйте позже.'
        return f'Регион "{region_name}" добавлен!'


def _edit_message(
    peer_id: int,
    text: str,
    sender: VKMessageSender,
    keyboard: dict | None = None,
    conversation_message_id: int | None = None,
    message_id: int | None = None,
) -> None:
    """Edit an existing message in-place.

    Uses conversation_message_id first (preferred for inline callback events),
    falls back to message_id. At least one of the two must be provided.

    Args:
        sender: VKMessageSender instance for sending messages.
    """
    if conversation_message_id:
        sender.edit_message(
            peer_id=peer_id,
            text=text,
            keyboard=keyboard,
            conversation_message_id=conversation_message_id,
        )
    elif message_id:
        sender.edit_message(
            peer_id=peer_id,
            text=text,
            keyboard=keyboard,
            message_id=message_id,
        )


def handle_inline_pagination(
    vk_message: VKMessage,
    payload: dict,
    sender: VKMessageSender,
) -> None:
    """Handle inline pagination callbacks for region selection.

    Processes four command types:
    - paginate_nav: Navigate to a different page (edit message in-place)
    - paginate_toggle: Toggle region subscription (show snackbar)
    - paginate_back: Return to federal district selection (edit message in-place)
    - paginate_finish: Finish region selection — remove inline keyboard
      and send a new message with the settings menu keyboard.

    Uses conversation_message_id for messages.edit (matching VK Callback API
    best practice — the demo at inline_keyboard_demo.py uses this pattern).
    Falls back to send_message if no message identifier is available.

    Args:
        vk_message: The incoming VK message with callback data.
        payload: Parsed JSON payload dict.
        sender: VKMessageSender instance for sending messages.
    """
    cmd = payload.get('cmd', '')
    user_id = db().resolve_user_id(vk_message.user_id)
    peer_id = vk_message.peer_id
    message_id = vk_message.message_id
    conversation_message_id = vk_message.conversation_message_id

    logging.info(
        f'handle_inline_pagination: cmd="{cmd}", user_id={user_id}, '
        f'message_id={message_id}, conversation_message_id={conversation_message_id}, '
        f'payload={payload}'
    )

    if cmd == 'paginate_nav':
        district = payload.get('district', '')
        page = payload.get('page', 0)
        folders = _get_folders_for_district(district)
        if not folders:
            sender.send_callback_answer(
                event_id=vk_message.event_id or '',
                user_id=vk_message.user_id,
                peer_id=peer_id,
                event_data={'type': 'show_snackbar', 'text': 'В этом округе пока нет доступных регионов.'},
            )
            return

        region_buttons = [name for fid, name in folders]
        selected_regions = _get_selected_region_names(user_id)
        keyboard = VKKeyboardPresets.paginated_regions_inline(
            region_buttons, page, district, selected_regions=selected_regions
        )

        callback_ok = sender.send_callback_answer(
            event_id=vk_message.event_id or '',
            user_id=vk_message.user_id,
            peer_id=peer_id,
        )
        logging.info(f'handle_inline_pagination: send_callback_answer returned {callback_ok}')

        text = f'Выберите регион в округе "{district} ФО":\n\n' 'Нажмите на регион, чтобы подписаться или отписаться.'
        _edit_message(
            peer_id=peer_id,
            text=text,
            keyboard=keyboard,
            conversation_message_id=conversation_message_id,
            message_id=message_id,
            sender=sender,
        )

    elif cmd == 'paginate_toggle':
        region = payload.get('region', '')
        if not region:
            return

        snackbar_text = _toggle_region_inline(user_id, region)
        sender.send_callback_answer(
            event_id=vk_message.event_id or '',
            user_id=vk_message.user_id,
            peer_id=peer_id,
            event_data={'type': 'show_snackbar', 'text': snackbar_text},
        )

        district = payload.get('district', '')
        page = payload.get('page', 0)
        if district:
            folders = _get_folders_for_district(district)
            if folders:
                region_buttons = [name for fid, name in folders]
                selected_regions = _get_selected_region_names(user_id)
                text = (
                    f'Выберите регион в округе "{district} ФО":\n\n'
                    'Нажмите на регион, чтобы подписаться или отписаться.'
                )
                keyboard = VKKeyboardPresets.paginated_regions_inline(
                    region_buttons, page, district, selected_regions=selected_regions
                )
                _edit_message(
                    peer_id=peer_id,
                    text=text,
                    keyboard=keyboard,
                    conversation_message_id=conversation_message_id,
                    message_id=message_id,
                    sender=sender,
                )

    elif cmd == 'paginate_back':
        sender.send_callback_answer(
            event_id=vk_message.event_id or '',
            user_id=vk_message.user_id,
            peer_id=peer_id,
        )
        text = region_selection_intro()
        _edit_message(
            peer_id=peer_id,
            text=text,
            keyboard=VKKeyboardPresets.fed_districts(),
            conversation_message_id=conversation_message_id,
            message_id=message_id,
            sender=sender,
        )

    elif cmd == 'paginate_finish':
        sender.send_callback_answer(
            event_id=vk_message.event_id or '',
            user_id=vk_message.user_id,
            peer_id=peer_id,
        )
        empty_keyboard = {'inline': True, 'buttons': []}
        _edit_message(
            peer_id=peer_id,
            text='✅ Выбор региона завершён.',
            keyboard=empty_keyboard,
            conversation_message_id=conversation_message_id,
            message_id=message_id,
            sender=sender,
        )
        sender.send_message(
            peer_id=peer_id,
            text=settings_menu_intro(),
            keyboard=VKKeyboardPresets.settings_menu(),
        )


def handle_district_select(
    vk_message: VKMessage,
    payload: dict,
    sender: VKMessageSender,
) -> None:
    """Handle federal district selection via inline callback.

    When a user clicks a district inline button (e.g., 'Центральный ФО'),
    this function:
    1. Acknowledges the callback event
    2. Queries the database for regions in that district
    3. Edits the message in-place to show region buttons
       (inline paginated if many regions, or regular text if few)

    Already-subscribed regions are highlighted with 'primary' (green) color.

    Uses conversation_message_id for messages.edit (matching the pattern
    used by handle_inline_pagination).

    Args:
        vk_message: The incoming VK message with callback data.
        payload: Parsed JSON payload dict.
        sender: VKMessageSender instance for sending messages.
    """
    district = payload.get('district', '')
    if not district:
        return

    user_id = db().resolve_user_id(vk_message.user_id)
    peer_id = vk_message.peer_id
    conversation_message_id = vk_message.conversation_message_id
    message_id = vk_message.message_id

    logging.info(
        f'handle_district_select: district="{district}", user_id={user_id}, '
        f'conversation_message_id={conversation_message_id}'
    )

    sender.send_callback_answer(
        event_id=vk_message.event_id or '',
        user_id=vk_message.user_id,
        peer_id=peer_id,
    )

    folders = _get_folders_for_district(district)
    if not folders:
        sender.send_callback_answer(
            event_id=vk_message.event_id or '',
            user_id=vk_message.user_id,
            peer_id=peer_id,
            event_data={'type': 'show_snackbar', 'text': 'В этом округе пока нет доступных регионов.'},
        )
        return

    region_buttons = [name for fid, name in folders]
    text = f'Выберите регион в округе "{district} ФО":\n\n' 'Нажмите на регион, чтобы подписаться или отписаться.'

    selected_regions = _get_selected_region_names(user_id)

    total_pages = (len(region_buttons) + _PAGE_SIZE - 1) // _PAGE_SIZE

    if total_pages <= 1:
        buttons = list(region_buttons)
        buttons.append('Завершить')
        keyboard = VKKeyboardPresets.two_columns(buttons, selected_regions=selected_regions)
    else:
        keyboard = VKKeyboardPresets.paginated_regions_inline(
            region_buttons, 0, district, selected_regions=selected_regions
        )

    _edit_message(
        peer_id=peer_id,
        text=text,
        keyboard=keyboard,
        conversation_message_id=conversation_message_id,
        message_id=message_id,
        sender=sender,
    )


router: list = [
    handle_fed_district_select,
    handle_region_toggle,
]
