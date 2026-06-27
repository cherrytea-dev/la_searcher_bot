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

from ..common import VKHandlerContext
from ..keyboards import VKKeyboardButtons, VKKeyboardPresets
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


def _get_folders_for_district(ctx: VKHandlerContext, district_name: str) -> list[tuple[int, str]]:
    """Get geo folders for a given federal district name."""
    return ctx.db.get_geo_folders_by_district(district_name)


def _get_selected_region_names(ctx: VKHandlerContext) -> set[str]:
    """Get set of region display names that the user is subscribed to.

    Matches user's subscribed folder IDs against geo folder display names.
    """
    user_folder_ids = set(ctx.db.get_user_regions(ctx.user_id))
    if not user_folder_ids:
        return set()

    all_folders = ctx.db.get_geo_folders()
    selected: set[str] = set()
    for fid, name in all_folders:
        if name is not None and fid in user_folder_ids:
            selected.add(name)
    return selected


def handle_fed_district_select(ctx: VKHandlerContext) -> None:
    """Handle federal district selection — show regions in that district.

    Matches button text from VKKeyboardPresets.fed_districts().
    If the district has more than _PAGE_SIZE regions, shows inline paginated view
    (callback-based). Otherwise shows all regions as regular text buttons.

    Already-subscribed regions are highlighted with 'primary' (green) color.
    """
    district_name = _get_district_name(ctx.message.text)
    if district_name is None:
        return

    # Query folders by federal district from the database
    folders = _get_folders_for_district(ctx, district_name)
    if not folders:
        ctx.reply(
            text='В этом округе пока нет доступных регионов.',
            keyboard=VKKeyboardPresets.fed_districts(),
        )
        return

    region_buttons = [name for fid, name in folders]
    selected_regions = _get_selected_region_names(ctx)

    # Check if pagination is needed
    total_pages = (len(region_buttons) + _PAGE_SIZE - 1) // _PAGE_SIZE

    if total_pages <= 1:
        # Single page — show all regions as regular text buttons
        buttons = list(region_buttons)
        buttons.append(VKKeyboardButtons.BTN_FINISH)
        ctx.reply(
            text=f'Выберите регион в округе "{ctx.message.text.strip()}":\n\n'
            'Нажмите на регион, чтобы подписаться или отписаться.',
            keyboard=VKKeyboardPresets.two_columns(buttons, selected_regions=selected_regions),
        )
    else:
        # Multiple pages — show first page with inline callback keyboard
        ctx.reply(
            text=f'Выберите регион в округе "{ctx.message.text.strip()}":\n\n'
            'Нажмите на регион, чтобы подписаться или отписаться.',
            keyboard=VKKeyboardPresets.paginated_regions_inline(
                region_buttons, 0, district_name, selected_regions=selected_regions
            ),
        )


def handle_region_toggle(ctx: VKHandlerContext) -> None:
    """Handle region toggle (subscribe/unsubscribe).

    Matches any text that corresponds to a known geo folder name.
    Uses toggle_region_by_name which requires a folder_dict parameter.
    Checks subscription state before toggling to provide correct feedback.
    """
    text = ctx.message.text.strip()
    if not text:
        return

    # Get all geo folders
    folders = ctx.db.get_geo_folders()
    if not folders:
        return

    # Build folder_dict: {display_name: (folder_id,)}
    # Filter out None folder names (can happen if DB has NULL folder_display_name)
    folder_dict: dict[str, tuple[int, ...]] = {}
    for fid, name in folders:
        if name is not None:
            folder_dict[name] = (fid,)

    if not folder_dict:
        return

    # Case-insensitive matching
    region_name_lower = text.lower()
    matching = [name for name in folder_dict if name.lower() == region_name_lower]
    if not matching:
        return
    region_name = matching[0]
    region_folder_ids = folder_dict[region_name]

    _toggle_region(ctx, region_name, region_folder_ids, folder_dict)


def _toggle_region(
    ctx: VKHandlerContext,
    region_name: str,
    region_folder_ids: tuple[int, ...] | None = None,
    folder_dict: dict[str, tuple[int, ...]] | None = None,
) -> None:
    """Toggle region subscription for a user.

    If region_folder_ids and folder_dict are provided, uses them directly.
    Otherwise, looks up the region from the database.
    """
    if region_folder_ids is None or folder_dict is None:
        # Look up from DB
        folders = ctx.db.get_geo_folders()
        if not folders:
            return
        folder_dict = {}
        for fid, name in folders:
            if name is not None:
                folder_dict[name] = (fid,)
        if region_name not in folder_dict:
            return
        region_folder_ids = folder_dict[region_name]

    # Check current subscription state by comparing folder IDs
    user_region_folder_ids = list(ctx.db.get_user_regions(ctx.user_id))
    is_subscribed = any(fid in user_region_folder_ids for fid in region_folder_ids)

    if is_subscribed:
        try:
            result = ctx.db.toggle_region_by_name(ctx.user_id, region_name, folder_dict)
        except Exception:
            logging.exception(f'Failed to toggle region for user {ctx.user_id}: {region_name}')
            return

        if result is False:
            ctx.reply(
                text=region_selection_cant_remove_last(),
                keyboard=VKKeyboardPresets.settings_menu(),
            )
            return
        ctx.reply(
            text=f'Регион "{region_name}" удален.',
            keyboard=VKKeyboardPresets.settings_menu(),
        )
    else:
        try:
            ctx.db.toggle_region_by_name(ctx.user_id, region_name, folder_dict)
        except Exception:
            logging.exception(f'Failed to toggle region for user {ctx.user_id}: {region_name}')
            return
        ctx.reply(
            text=f'Регион "{region_name}" добавлен!',
            keyboard=VKKeyboardPresets.settings_menu(),
        )


def _toggle_region_inline(ctx: VKHandlerContext, region_name: str) -> str:
    """Toggle region subscription for inline callback.

    Lightweight version used by inline pagination callbacks.
    Returns a snackbar text string to display to the user.
    """
    folders = ctx.db.get_geo_folders()
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
    user_region_folder_ids = list(ctx.db.get_user_regions(ctx.user_id))
    is_subscribed = any(fid in user_region_folder_ids for fid in region_folder_ids)

    if is_subscribed:
        try:
            result = ctx.db.toggle_region_by_name(ctx.user_id, region_name, folder_dict)
        except Exception:
            logging.exception(f'Failed to toggle region for user {ctx.user_id}: {region_name}')
            return 'Произошла ошибка. Попробуйте позже.'

        if result is False:
            return 'Нельзя удалить последний регион.'
        return f'Регион "{region_name}" удален.'
    else:
        try:
            ctx.db.toggle_region_by_name(ctx.user_id, region_name, folder_dict)
        except Exception:
            logging.exception(f'Failed to toggle region for user {ctx.user_id}: {region_name}')
            return 'Произошла ошибка. Попробуйте позже.'
        return f'Регион "{region_name}" добавлен!'


def handle_inline_pagination(ctx: VKHandlerContext) -> None:
    """Handle inline pagination callbacks for region selection.

    Parses ``ctx.message.payload`` for the command and parameters.
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
        ctx: Handler context with message data and response methods.
    """
    payload = ctx.message.payload_as_dict
    if not payload:
        return

    cmd = payload.get('cmd', '')
    message_id = ctx.message.message_id
    conversation_message_id = ctx.message.conversation_message_id

    logging.info(
        f'handle_inline_pagination: cmd="{cmd}", user_id={ctx.user_id}, '
        f'message_id={message_id}, conversation_message_id={conversation_message_id}, '
        f'payload={payload}'
    )

    if cmd == 'paginate_nav':
        district = payload.get('district', '')
        page = payload.get('page', 0)
        folders = _get_folders_for_district(ctx, district)
        if not folders:
            ctx.answer_callback(
                event_data={'type': 'show_snackbar', 'text': 'В этом округе пока нет доступных регионов.'},
            )
            return

        region_buttons = [name for fid, name in folders]
        selected_regions = _get_selected_region_names(ctx)
        keyboard = VKKeyboardPresets.paginated_regions_inline(
            region_buttons, page, district, selected_regions=selected_regions
        )

        ctx.answer_callback()

        text = f'Выберите регион в округе "{district} ФО":\n\n' 'Нажмите на регион, чтобы подписаться или отписаться.'
        ctx.edit(
            text=text,
            keyboard=keyboard,
            conversation_message_id=conversation_message_id,
            message_id=message_id,
        )

    elif cmd == 'paginate_toggle':
        region = payload.get('region', '')
        if not region:
            return

        snackbar_text = _toggle_region_inline(ctx, region)
        ctx.answer_callback(
            event_data={'type': 'show_snackbar', 'text': snackbar_text},
        )

        district = payload.get('district', '')
        page = payload.get('page', 0)
        if district:
            folders = _get_folders_for_district(ctx, district)
            if folders:
                region_buttons = [name for fid, name in folders]
                selected_regions = _get_selected_region_names(ctx)
                text = (
                    f'Выберите регион в округе "{district} ФО":\n\n'
                    'Нажмите на регион, чтобы подписаться или отписаться.'
                )
                keyboard = VKKeyboardPresets.paginated_regions_inline(
                    region_buttons, page, district, selected_regions=selected_regions
                )
                ctx.edit(
                    text=text,
                    keyboard=keyboard,
                    conversation_message_id=conversation_message_id,
                    message_id=message_id,
                )

    elif cmd == 'paginate_back':
        ctx.answer_callback()
        text = region_selection_intro()
        ctx.edit(
            text=text,
            keyboard=VKKeyboardPresets.fed_districts(),
            conversation_message_id=conversation_message_id,
            message_id=message_id,
        )

    elif cmd == 'paginate_finish':
        ctx.answer_callback()
        empty_keyboard = {'inline': True, 'buttons': []}
        ctx.edit(
            text='✅ Выбор региона завершён.',
            keyboard=empty_keyboard,
            conversation_message_id=conversation_message_id,
            message_id=message_id,
        )
        ctx.send_message(
            text=settings_menu_intro(),
            keyboard=VKKeyboardPresets.settings_menu(),
        )


def handle_district_select(ctx: VKHandlerContext) -> None:
    """Handle federal district selection via inline callback.

    Parses ``ctx.message.payload_as_dict`` for the district name.
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
        ctx: Handler context with message data and response methods.
    """
    payload = ctx.message.payload_as_dict
    if not payload:
        return
    district = payload.get('district', '')
    if not district:
        return

    conversation_message_id = ctx.message.conversation_message_id
    message_id = ctx.message.message_id

    logging.info(
        f'handle_district_select: district="{district}", user_id={ctx.user_id}, '
        f'conversation_message_id={conversation_message_id}'
    )

    ctx.answer_callback()

    folders = _get_folders_for_district(ctx, district)
    if not folders:
        ctx.answer_callback(
            event_data={'type': 'show_snackbar', 'text': 'В этом округе пока нет доступных регионов.'},
        )
        return

    region_buttons = [name for fid, name in folders]
    text = f'Выберите регион в округе "{district} ФО":\n\n' 'Нажмите на регион, чтобы подписаться или отписаться.'

    selected_regions = _get_selected_region_names(ctx)

    total_pages = (len(region_buttons) + _PAGE_SIZE - 1) // _PAGE_SIZE

    if total_pages <= 1:
        buttons = list(region_buttons)
        buttons.append('Завершить')
        keyboard = VKKeyboardPresets.two_columns(buttons, selected_regions=selected_regions)
    else:
        keyboard = VKKeyboardPresets.paginated_regions_inline(
            region_buttons, 0, district, selected_regions=selected_regions
        )

    ctx.edit(
        text=text,
        keyboard=keyboard,
        conversation_message_id=conversation_message_id,
        message_id=message_id,
    )


router: list = [
    handle_inline_pagination,
    handle_district_select,
    handle_fed_district_select,
    handle_region_toggle,
]
