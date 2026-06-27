"""Settings sub-menu handlers for the VK bot.

Each handler is a standalone function decorated with ``@vk_handle``.
Handlers auto-register in ``vk_registry`` at import time.

Each handler takes a ``VKHandlerContext`` and returns ``None``.
Uses ``ctx.reply()`` to send responses and ``ctx.is_consumed`` to signal handling.
"""

from __future__ import annotations

from _dependencies.bot.telegram_api_wrapper import make_invite_text_for_user
from _dependencies.models import AgePeriod, DialogState
from vk_bot._utils.services.message_formatter import (
    community_intro,
    coords_deleted,
    coords_intro,
    coords_not_set,
    first_search_intro,
    format_notif_prefs_list,
    notif_settings_current_prefs,
    notif_settings_intro,
    photos_intro,
    radius_deleted,
    radius_intro_no_radius,
    radius_intro_with_radius,
    region_selection_intro,
    vk_already_linked,
    vk_link_instructions,
)

from ..common import VKHandlerContext
from ..decorators import vk_handle
from ..keyboards import VKKeyboardButtons, VKKeyboardPresets

# ═══════════════════════════════════════════════════════════════════════
# Settings menu navigation
# ═══════════════════════════════════════════════════════════════════════


@vk_handle(text=VKKeyboardButtons.BTN_SETTINGS_REGION)
def handle_settings_region(ctx: VKHandlerContext) -> None:
    """Handle 'настроить регион поисков' button."""
    ctx.reply(
        text=region_selection_intro(),
        keyboard=VKKeyboardPresets.fed_districts_inline(),
    )


@vk_handle(text=VKKeyboardButtons.BTN_SETTINGS_COORDS)
def handle_settings_coords(ctx: VKHandlerContext) -> None:
    """Handle 'настроить домашние координаты' button."""
    coords = ctx.db.get_coordinates(ctx.user_id)
    if coords:
        ctx.reply(
            text=coords_intro(),
            keyboard=VKKeyboardPresets.coords_menu(),
        )
        return
    ctx.reply(
        text=coords_not_set(),
        keyboard=VKKeyboardPresets.coords_menu(),
    )


@vk_handle(text=VKKeyboardButtons.BTN_SETTINGS_RADIUS)
def handle_settings_radius(ctx: VKHandlerContext) -> None:
    """Handle 'настроить максимальный радиус' button."""
    radius = ctx.db.get_radius(ctx.user_id)
    if radius:
        ctx.reply(
            text=radius_intro_with_radius(radius),
            keyboard=VKKeyboardPresets.radius_settings(has_radius=True),
        )
        return
    ctx.reply(
        text=radius_intro_no_radius(),
        keyboard=VKKeyboardPresets.radius_settings(),
    )


@vk_handle(text=[VKKeyboardButtons.BTN_RADIUS_ENABLE, VKKeyboardButtons.BTN_RADIUS_EDIT])
def handle_radius_enable_edit(ctx: VKHandlerContext) -> None:
    """Handle 'включить ограничение по расстоянию' or 'изменить радиус'."""
    radius = ctx.db.get_radius(ctx.user_id)
    current = f'Текущий радиус: {radius} км. ' if radius else ''
    ctx.reply(
        text=f'{current}Введите новый радиус в километрах (только число).',
        keyboard=VKKeyboardPresets.back_to_start(),
    )
    ctx.set_state(DialogState.radius_input)


@vk_handle(text=VKKeyboardButtons.BTN_RADIUS_DISABLE)
def handle_radius_disable(ctx: VKHandlerContext) -> None:
    """Handle 'отключить ограничение по расстоянию' button."""
    ctx.db.delete_radius(ctx.user_id)
    ctx.reply(
        text=radius_deleted(),
        keyboard=VKKeyboardPresets.settings_menu(),
    )


# ═══════════════════════════════════════════════════════════════════════
# Notification preference toggles
# ═══════════════════════════════════════════════════════════════════════


# Map button text to preference names
_NOTIF_MAP: dict[str, str] = {
    VKKeyboardButtons.BTN_NOTIF_ALL_ON: 'all',
    VKKeyboardButtons.BTN_NOTIF_NEW_ON: 'new_searches',
    VKKeyboardButtons.BTN_NOTIF_STATUS_ON: 'status_changes',
    VKKeyboardButtons.BTN_NOTIF_COMMENTS_ON: 'comments_changes',
    VKKeyboardButtons.BTN_NOTIF_INFORG_ON: 'inforg_comments',
    VKKeyboardButtons.BTN_NOTIF_FIRST_POST_ON: 'first_post_changes',
    VKKeyboardButtons.BTN_NOTIF_FOLLOWED_ALL_ON: 'all_in_followed_search',
    VKKeyboardButtons.BTN_NOTIF_ALL_OFF: 'all',
    VKKeyboardButtons.BTN_NOTIF_NEW_OFF: 'new_searches',
    VKKeyboardButtons.BTN_NOTIF_STATUS_OFF: 'status_changes',
    VKKeyboardButtons.BTN_NOTIF_COMMENTS_OFF: 'comments_changes',
    VKKeyboardButtons.BTN_NOTIF_INFORG_OFF: 'inforg_comments',
    VKKeyboardButtons.BTN_NOTIF_FIRST_POST_OFF: 'first_post_changes',
    VKKeyboardButtons.BTN_NOTIF_FOLLOWED_ALL_OFF: 'all_in_followed_search',
}


@vk_handle(text=list(_NOTIF_MAP.keys()))
def handle_notification_toggle(ctx: VKHandlerContext) -> None:
    """Handle notification preference toggles.

    Maps VK button text to preference names and toggles them.
    """
    text = ctx.message.text.strip().lower()
    pref_name = _NOTIF_MAP[text]
    is_enable = text.startswith('включить:')

    if is_enable:
        if pref_name == 'all':
            ctx.db.delete_preferences(ctx.user_id, [])
            ctx.db.save_preference(ctx.user_id, 'all')
        else:
            ctx.db.save_preference(ctx.user_id, pref_name)
    else:
        if pref_name == 'all':
            ctx.db.delete_preferences(ctx.user_id, [])
        else:
            ctx.db.delete_preferences(ctx.user_id, [pref_name])

    prefs = ctx.db.get_all_user_preferences(ctx.user_id)
    prefs_text = ''
    if prefs:
        prefs_text = '\n' + notif_settings_current_prefs(format_notif_prefs_list(prefs))

    ctx.reply(
        text=notif_settings_intro() + prefs_text,
        keyboard=VKKeyboardPresets.notification_settings(),
    )


# ═══════════════════════════════════════════════════════════════════════
# Coordinates sub-menu actions
# ═══════════════════════════════════════════════════════════════════════


@vk_handle(text=VKKeyboardButtons.BTN_COORDS_ENTER)
def handle_coords_enter(ctx: VKHandlerContext) -> None:
    """Handle 'ввести домашние координаты вручную' button."""
    ctx.reply(
        text='Введите координаты в формате: широта, долгота (например: 55.7558, 37.6173)',
        keyboard=VKKeyboardPresets.back_to_start(),
    )
    ctx.set_state(DialogState.input_of_coords_man)


@vk_handle(text=VKKeyboardButtons.BTN_COORDS_VIEW)
def handle_coords_view(ctx: VKHandlerContext) -> None:
    """Handle 'посмотреть сохраненные координаты' button."""
    coords = ctx.db.get_coordinates(ctx.user_id)
    if coords:
        lat, lon = coords
        ctx.reply(
            text=f'Ваши координаты: {lat}, {lon}',
            keyboard=VKKeyboardPresets.coords_menu(),
        )
        return
    ctx.reply(
        text=coords_not_set(),
        keyboard=VKKeyboardPresets.coords_menu(),
    )


@vk_handle(text=VKKeyboardButtons.BTN_COORDS_DELETE)
def handle_coords_delete(ctx: VKHandlerContext) -> None:
    """Handle 'удалить домашние координаты' button."""
    ctx.db.delete_coordinates(ctx.user_id)
    ctx.reply(
        text=coords_deleted(),
        keyboard=VKKeyboardPresets.settings_menu(),
    )


# ═══════════════════════════════════════════════════════════════════════
# Age preference toggles
# ═══════════════════════════════════════════════════════════════════════


_AGE_MAP: dict[str, AgePeriod] = {
    VKKeyboardButtons.BTN_AGE_CHILDREN: AgePeriod(
        description=VKKeyboardButtons.BTN_AGE_CHILDREN,
        name='0-10',
        min_age=0,
        max_age=10,
        order=1,
    ),
    VKKeyboardButtons.BTN_AGE_TEENS: AgePeriod(
        description=VKKeyboardButtons.BTN_AGE_TEENS,
        name='11-17',
        min_age=11,
        max_age=17,
        order=2,
    ),
    VKKeyboardButtons.BTN_AGE_ADULTS: AgePeriod(
        description=VKKeyboardButtons.BTN_AGE_ADULTS,
        name='18-50',
        min_age=18,
        max_age=50,
        order=3,
    ),
    VKKeyboardButtons.BTN_AGE_ELDERLY: AgePeriod(
        description=VKKeyboardButtons.BTN_AGE_ELDERLY,
        name='51-150',
        min_age=51,
        max_age=150,
        order=4,
    ),
}


@vk_handle(text=list(_AGE_MAP.keys()))
def handle_age_settings(ctx: VKHandlerContext) -> None:
    """Handle age preference toggles.

    Maps button text to AgePeriod objects and toggles them.
    """
    text = ctx.message.text.strip().lower()
    period = _AGE_MAP[text]
    current_prefs = ctx.db.get_age_preferences(ctx.user_id)

    period_active = any(p_min == period.min_age and p_max == period.max_age for p_min, p_max in current_prefs)

    if period_active:
        ctx.db.delete_age_preference(ctx.user_id, period)
    else:
        ctx.db.save_age_preference(ctx.user_id, period)

    updated = ctx.db.get_age_preferences(ctx.user_id)
    age_names = []
    for p_min, p_max in updated:
        for btn_text, ap in _AGE_MAP.items():
            if ap.min_age == p_min and ap.max_age == p_max:
                age_names.append(ap.description)
                break

    prefs_text = ', '.join(age_names) if age_names else 'не выбрано'
    ctx.reply(
        text=f'Возрастные группы: {prefs_text}',
        keyboard=VKKeyboardPresets.age_settings(),
    )


# ═══════════════════════════════════════════════════════════════════════
# Topic type preference toggles
# ═══════════════════════════════════════════════════════════════════════


_TYPE_MAP: dict[str, int] = {
    VKKeyboardButtons.BTN_TYPE_SEARCH: 0,
    VKKeyboardButtons.BTN_TYPE_INFO: 4,
}


@vk_handle(text=list(_TYPE_MAP.keys()))
def handle_topic_type_settings(ctx: VKHandlerContext) -> None:
    """Handle topic type preference toggles.

    Maps button text to topic_type_id integers and toggles them.
    """
    text = ctx.message.text.strip().lower()
    topic_type_id = _TYPE_MAP[text]
    current_types = ctx.db.get_topic_types(ctx.user_id)

    if topic_type_id in current_types:
        ctx.db.delete_topic_type(ctx.user_id, topic_type_id)
    else:
        ctx.db.save_topic_type(ctx.user_id, topic_type_id)

    updated = ctx.db.get_topic_types(ctx.user_id)
    id_to_name = {v: k for k, v in _TYPE_MAP.items()}
    types_text = ', '.join(id_to_name.get(tid, f'тип {tid}') for tid in updated) or 'не выбрано'

    ctx.reply(
        text=f'Виды поисков: {types_text}',
        keyboard=VKKeyboardPresets.topic_type_settings(),
    )


# ═══════════════════════════════════════════════════════════════════════
# Other menu
# ═══════════════════════════════════════════════════════════════════════


@vk_handle(text=VKKeyboardButtons.BTN_OTHER_LAST_SEARCHES)
def handle_other_last_searches(ctx: VKHandlerContext) -> None:
    """Handle 'посмотреть последние поиски' — pass through to view_searches.

    Returns without consuming, letting it pass through the handler chain
    to the view_searches_handlers.
    """
    return


@vk_handle(text=VKKeyboardButtons.BTN_OTHER_FEEDBACK)
def handle_other_feedback(ctx: VKHandlerContext) -> None:
    """Handle 'написать разработчику бота' button."""
    ctx.reply(
        text=community_intro(),
        keyboard=VKKeyboardPresets.other_menu(),
    )


@vk_handle(text=VKKeyboardButtons.BTN_OTHER_NEWBIE_INFO)
def handle_other_newbie_info(ctx: VKHandlerContext) -> None:
    """Handle 'ознакомиться с информацией для новичка' button."""
    ctx.reply(
        text=first_search_intro(),
        keyboard=VKKeyboardPresets.other_menu(),
    )


@vk_handle(text=VKKeyboardButtons.BTN_OTHER_PHOTOS)
def handle_other_photos(ctx: VKHandlerContext) -> None:
    """Handle 'посмотреть красивые фото с поисков' button."""
    ctx.reply(
        text=photos_intro(),
        keyboard=VKKeyboardPresets.other_menu(),
    )


# ═══════════════════════════════════════════════════════════════════════
# Forum linking
# ═══════════════════════════════════════════════════════════════════════


@vk_handle(text=VKKeyboardButtons.BTN_FORUM_ENTER_NICK)
def handle_forum_linking(ctx: VKHandlerContext) -> None:
    """Handle forum linking — set state to input forum username."""
    ctx.reply(
        text='Введите ваш логин (ник) на форуме lizaalert.org:',
        keyboard=VKKeyboardPresets.back_to_start(),
    )
    ctx.set_state(DialogState.input_of_forum_username)


# ═══════════════════════════════════════════════════════════════════════
# VK linking
# ═══════════════════════════════════════════════════════════════════════


@vk_handle(text=VKKeyboardButtons.BTN_VK_LINK)
def handle_vk_linking(ctx: VKHandlerContext) -> None:
    """Handle VK linking button.

    Generates a proper invite text using make_invite_text_for_user() which
    creates a SHA256 hash of {telegram_user_id}{bot_api_token__prod}.
    The user copies this text and sends it to the VK bot to link accounts.
    """
    vk_id = ctx.db.get_user_vk_id(ctx.user_id)
    if vk_id:
        ctx.reply(
            text=vk_already_linked(),
            keyboard=VKKeyboardPresets.settings_menu(),
        )
        return

    invite_text = make_invite_text_for_user(ctx.user_id)
    ctx.reply(
        text=vk_link_instructions(invite_text),
        keyboard=VKKeyboardPresets.settings_menu(),
    )
