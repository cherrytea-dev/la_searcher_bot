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

from _dependencies.common.geo import REGION_EMOJI_LEGEND

from ..common import VKHandlerContext
from ..decorators import vk_handle
from ..keyboards import VKKeyboardPresets
from ..services.message_formatter import (
    region_selection_intro,
    settings_menu_intro,
)

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


@vk_handle(text=_KNOWN_DISTRICTS)
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

    ctx.reply(
        text=(
            f'Выберите регион в округе "{ctx.message.text.strip()}":\n\n'
            f'{REGION_EMOJI_LEGEND}\n\n'
            'Нажмите на регион, чтобы подписаться или отписаться.'
        ),
        keyboard=VKKeyboardPresets.paginated_regions_inline(
            region_buttons, 0, district_name, selected_regions=selected_regions
        ),
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
            folder_dict[name] = folder_dict.get(name, ()) + (fid,)

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


@vk_handle(callback_data='paginate_nav')
def handle_inline_pagination_nav(ctx: VKHandlerContext) -> None:
    """Handle inline pagination navigation callback.

    Parses ``ctx.message.payload`` for the page and district parameters
    and edits the message in-place to show the requested page.
    """
    payload = ctx.message.payload_as_dict
    if not payload:
        return

    cmd = payload.get('cmd', '')
    message_id = ctx.message.message_id
    conversation_message_id = ctx.message.conversation_message_id

    logging.info(
        f'handle_inline_pagination_nav: cmd="{cmd}", user_id={ctx.user_id}, '
        f'message_id={message_id}, conversation_message_id={conversation_message_id}, '
        f'payload={payload}'
    )

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

    text = (
        f'Выберите регион в округе "{district} ФО":\n\n'
        f'{REGION_EMOJI_LEGEND}\n\n'
        'Нажмите на регион, чтобы подписаться или отписаться.'
    )
    ctx.edit(
        text=text,
        keyboard=keyboard,
        conversation_message_id=conversation_message_id,
        message_id=message_id,
    )


@vk_handle(callback_data='paginate_toggle')
def handle_inline_pagination_toggle(ctx: VKHandlerContext) -> None:
    """Handle inline pagination region toggle callback.

    Parses ``ctx.message.payload`` for the region name, toggles subscription,
    and shows a snackbar with the result.
    """
    payload = ctx.message.payload_as_dict
    if not payload:
        return

    region = payload.get('region', '')
    if not region:
        return

    snackbar_text = _toggle_region_inline(ctx, region)
    ctx.answer_callback(
        event_data={'type': 'show_snackbar', 'text': snackbar_text},
    )

    district = payload.get('district', '')
    page = payload.get('page', 0)
    message_id = ctx.message.message_id
    conversation_message_id = ctx.message.conversation_message_id

    if district:
        folders = _get_folders_for_district(ctx, district)
        if folders:
            region_buttons = [name for fid, name in folders]
            selected_regions = _get_selected_region_names(ctx)
            text = (
                f'Выберите регион в округе "{district} ФО":\n\n'
                f'{REGION_EMOJI_LEGEND}\n\n'
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


@vk_handle(callback_data='paginate_back')
def handle_inline_pagination_back(ctx: VKHandlerContext) -> None:
    """Handle inline pagination back callback — return to federal district selection."""
    payload = ctx.message.payload_as_dict
    if not payload:
        return

    message_id = ctx.message.message_id
    conversation_message_id = ctx.message.conversation_message_id

    ctx.answer_callback()
    text = region_selection_intro()
    ctx.edit(
        text=text,
        keyboard=VKKeyboardPresets.fed_districts(),
        conversation_message_id=conversation_message_id,
        message_id=message_id,
    )


@vk_handle(callback_data='paginate_finish')
def handle_inline_pagination_finish(ctx: VKHandlerContext) -> None:
    """Handle inline pagination finish callback — end region selection."""
    payload = ctx.message.payload_as_dict
    if not payload:
        return

    message_id = ctx.message.message_id
    conversation_message_id = ctx.message.conversation_message_id

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


@vk_handle(callback_data='district_select')
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
    text = (
        f'Выберите регион в округе "{district} ФО":\n\n'
        f'{REGION_EMOJI_LEGEND}\n\n'
        'Нажмите на регион, чтобы подписаться или отписаться.'
    )

    selected_regions = _get_selected_region_names(ctx)

    keyboard = VKKeyboardPresets.paginated_regions_inline(
        region_buttons, 0, district, selected_regions=selected_regions
    )

    ctx.edit(
        text=text,
        keyboard=keyboard,
        conversation_message_id=conversation_message_id,
        message_id=message_id,
    )
