"""Settings sub-menu handlers for the VK bot.

Contains the `settings_router` list with handlers for:
- Settings menu navigation
- Notification preference toggles
- Coordinates sub-menu actions
- Age preference toggles
- Topic type preference toggles
- Forum linking
- VK linking
- Other options menu

Each handler matches by vk_message.text content and handles a specific
button click or command. Returns VKHandlerResult if it handles the message,
or None to pass to the next handler in the chain.
"""

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

from ..common import VKHandlerResult, VKMessage
from ..database import db
from ..keyboards import VKKeyboardButtons, VKKeyboardPresets


def handle_settings_menu(vk_message: VKMessage, state: DialogState | None, user_id: int) -> VKHandlerResult | None:
    """Handle settings menu button clicks."""
    text = vk_message.text.strip().lower()

    if text == VKKeyboardButtons.BTN_SETTINGS_REGION.lower():
        return VKHandlerResult(
            text=region_selection_intro(),
            keyboard=VKKeyboardPresets.fed_districts_inline(),
        )

    if text == VKKeyboardButtons.BTN_SETTINGS_COORDS.lower():
        coords = db().get_coordinates(user_id)
        if coords:
            return VKHandlerResult(
                text=coords_intro(),
                keyboard=VKKeyboardPresets.coords_menu(),
            )
        return VKHandlerResult(
            text=coords_not_set(),
            keyboard=VKKeyboardPresets.coords_menu(),
        )

    if text == VKKeyboardButtons.BTN_SETTINGS_RADIUS.lower():
        radius = db().get_radius(user_id)
        if radius:
            return VKHandlerResult(
                text=radius_intro_with_radius(radius),
                keyboard=VKKeyboardPresets.radius_settings(has_radius=True),
            )
        return VKHandlerResult(
            text=radius_intro_no_radius(),
            keyboard=VKKeyboardPresets.radius_settings(),
        )

    if text in (VKKeyboardButtons.BTN_RADIUS_ENABLE.lower(), VKKeyboardButtons.BTN_RADIUS_EDIT.lower()):
        radius = db().get_radius(user_id)
        current = f'Текущий радиус: {radius} км. ' if radius else ''
        return VKHandlerResult(
            text=f'{current}Введите новый радиус в километрах (только число).',
            keyboard=VKKeyboardPresets.back_to_start(),
            new_state=DialogState.radius_input,
        )

    if text == VKKeyboardButtons.BTN_RADIUS_DISABLE.lower():
        db().delete_radius(user_id)
        return VKHandlerResult(
            text=radius_deleted(),
            keyboard=VKKeyboardPresets.settings_menu(),
        )

    return None


def handle_notification_toggle(
    vk_message: VKMessage, state: DialogState | None, user_id: int
) -> VKHandlerResult | None:
    """Handle notification preference toggles.

    Maps VK button text to preference names and toggles them.
    """
    text = vk_message.text.strip().lower()

    # Map button text to preference names
    # Labels are shortened to fit VK's 40-char limit for button labels
    notif_map: dict[str, str] = {
        VKKeyboardButtons.BTN_NOTIF_ALL_ON.lower(): 'all',
        VKKeyboardButtons.BTN_NOTIF_NEW_ON.lower(): 'new_searches',
        VKKeyboardButtons.BTN_NOTIF_STATUS_ON.lower(): 'status_changes',
        VKKeyboardButtons.BTN_NOTIF_COMMENTS_ON.lower(): 'comments_changes',
        VKKeyboardButtons.BTN_NOTIF_INFORG_ON.lower(): 'inforg_comments',
        VKKeyboardButtons.BTN_NOTIF_FIRST_POST_ON.lower(): 'first_post_changes',
        VKKeyboardButtons.BTN_NOTIF_FOLLOWED_ALL_ON.lower(): 'all_in_followed_search',
        VKKeyboardButtons.BTN_NOTIF_ALL_OFF.lower(): 'all',
        VKKeyboardButtons.BTN_NOTIF_NEW_OFF.lower(): 'new_searches',
        VKKeyboardButtons.BTN_NOTIF_STATUS_OFF.lower(): 'status_changes',
        VKKeyboardButtons.BTN_NOTIF_COMMENTS_OFF.lower(): 'comments_changes',
        VKKeyboardButtons.BTN_NOTIF_INFORG_OFF.lower(): 'inforg_comments',
        VKKeyboardButtons.BTN_NOTIF_FIRST_POST_OFF.lower(): 'first_post_changes',
        VKKeyboardButtons.BTN_NOTIF_FOLLOWED_ALL_OFF.lower(): 'all_in_followed_search',
    }

    if text not in notif_map:
        return None

    pref_name = notif_map[text]
    is_enable = text.startswith('включить:')

    if is_enable:
        if pref_name == 'all':
            # Enable all — clear existing and set 'all'
            db().delete_preferences(user_id, [])
            db().save_preference(user_id, 'all')
        else:
            db().save_preference(user_id, pref_name)
    else:
        if pref_name == 'all':
            db().delete_preferences(user_id, [])
        else:
            db().delete_preferences(user_id, [pref_name])

    # Show updated preferences
    prefs = db().get_all_user_preferences(user_id)

    prefs_text = ''
    if prefs:
        prefs_text = '\n' + notif_settings_current_prefs(format_notif_prefs_list(prefs))

    return VKHandlerResult(
        text=notif_settings_intro() + prefs_text,
        keyboard=VKKeyboardPresets.notification_settings(),
    )


def handle_coordinates_action(vk_message: VKMessage, state: DialogState | None, user_id: int) -> VKHandlerResult | None:
    """Handle coordinates sub-menu actions."""
    text = vk_message.text.strip().lower()

    if text == VKKeyboardButtons.BTN_COORDS_ENTER.lower():
        return VKHandlerResult(
            text='Введите координаты в формате: широта, долгота (например: 55.7558, 37.6173)',
            keyboard=VKKeyboardPresets.back_to_start(),
            new_state=DialogState.input_of_coords_man,
        )

    if text == VKKeyboardButtons.BTN_COORDS_VIEW.lower():
        coords = db().get_coordinates(user_id)
        if coords:
            lat, lon = coords
            return VKHandlerResult(
                text=f'Ваши координаты: {lat}, {lon}',
                keyboard=VKKeyboardPresets.coords_menu(),
            )
        return VKHandlerResult(
            text=coords_not_set(),
            keyboard=VKKeyboardPresets.coords_menu(),
        )

    if text == VKKeyboardButtons.BTN_COORDS_DELETE.lower():
        db().delete_coordinates(user_id)
        return VKHandlerResult(
            text=coords_deleted(),
            keyboard=VKKeyboardPresets.settings_menu(),
        )

    return None


def handle_age_settings(vk_message: VKMessage, state: DialogState | None, user_id: int) -> VKHandlerResult | None:
    """Handle age preference toggles.

    Maps button text to AgePeriod objects and toggles them.
    """
    text = vk_message.text.strip().lower()

    age_map: dict[str, AgePeriod] = {
        VKKeyboardButtons.BTN_AGE_CHILDREN.lower(): AgePeriod(
            description=VKKeyboardButtons.BTN_AGE_CHILDREN,
            name='0-10',
            min_age=0,
            max_age=10,
            order=1,
        ),
        VKKeyboardButtons.BTN_AGE_TEENS.lower(): AgePeriod(
            description=VKKeyboardButtons.BTN_AGE_TEENS,
            name='11-17',
            min_age=11,
            max_age=17,
            order=2,
        ),
        VKKeyboardButtons.BTN_AGE_ADULTS.lower(): AgePeriod(
            description=VKKeyboardButtons.BTN_AGE_ADULTS,
            name='18-50',
            min_age=18,
            max_age=50,
            order=3,
        ),
        VKKeyboardButtons.BTN_AGE_ELDERLY.lower(): AgePeriod(
            description=VKKeyboardButtons.BTN_AGE_ELDERLY,
            name='51-150',
            min_age=51,
            max_age=150,
            order=4,
        ),
    }

    if text not in age_map:
        return None

    period = age_map[text]
    current_prefs = db().get_age_preferences(user_id)

    # Check if this period is already set
    period_active = any(p_min == period.min_age and p_max == period.max_age for p_min, p_max in current_prefs)

    if period_active:
        db().delete_age_preference(user_id, period)
    else:
        db().save_age_preference(user_id, period)

    updated = db().get_age_preferences(user_id)
    # Build readable list of active age groups
    age_names = []
    for p_min, p_max in updated:
        for btn_text, ap in age_map.items():
            if ap.min_age == p_min and ap.max_age == p_max:
                age_names.append(ap.description)
                break

    prefs_text = ', '.join(age_names) if age_names else 'не выбрано'
    return VKHandlerResult(
        text=f'Возрастные группы: {prefs_text}',
        keyboard=VKKeyboardPresets.age_settings(),
    )


def handle_topic_type_settings(
    vk_message: VKMessage, state: DialogState | None, user_id: int
) -> VKHandlerResult | None:
    """Handle topic type preference toggles.

    Maps button text to topic_type_id integers and toggles them.
    """
    text = vk_message.text.strip().lower()

    type_map: dict[str, int] = {
        VKKeyboardButtons.BTN_TYPE_SEARCH.lower(): 0,
        VKKeyboardButtons.BTN_TYPE_INFO.lower(): 4,
    }

    if text not in type_map:
        return None

    topic_type_id = type_map[text]
    current_types = db().get_topic_types(user_id)

    if topic_type_id in current_types:
        db().delete_topic_type(user_id, topic_type_id)
    else:
        db().save_topic_type(user_id, topic_type_id)

    updated = db().get_topic_types(user_id)
    # Map IDs back to names
    id_to_name = {v: k for k, v in type_map.items()}
    types_text = ', '.join(id_to_name.get(tid, f'тип {tid}') for tid in updated) or 'не выбрано'

    return VKHandlerResult(
        text=f'Виды поисков: {types_text}',
        keyboard=VKKeyboardPresets.topic_type_settings(),
    )


def handle_other_menu(vk_message: VKMessage, state: DialogState | None, user_id: int) -> VKHandlerResult | None:
    """Handle other options menu buttons."""
    text = vk_message.text.strip().lower()

    if text == VKKeyboardButtons.BTN_OTHER_LAST_SEARCHES.lower():
        # Delegate to the latest searches handler in view_searches_handlers
        # by returning None to let it pass through the handler chain
        return None

    if text == VKKeyboardButtons.BTN_OTHER_FEEDBACK.lower():
        return VKHandlerResult(
            text=community_intro(),
            keyboard=VKKeyboardPresets.other_menu(),
        )

    if text == VKKeyboardButtons.BTN_OTHER_NEWBIE_INFO.lower():
        return VKHandlerResult(
            text=first_search_intro(),
            keyboard=VKKeyboardPresets.other_menu(),
        )

    if text == VKKeyboardButtons.BTN_OTHER_PHOTOS.lower():
        return VKHandlerResult(
            text=photos_intro(),
            keyboard=VKKeyboardPresets.other_menu(),
        )

    return None


def handle_forum_linking(vk_message: VKMessage, state: DialogState | None, user_id: int) -> VKHandlerResult | None:
    """Handle forum linking — set state to input forum username."""
    text = vk_message.text.strip().lower()
    if text != VKKeyboardButtons.BTN_FORUM_ENTER_NICK.lower():
        return None

    return VKHandlerResult(
        text='Введите ваш логин (ник) на форуме lizaalert.org:',
        keyboard=VKKeyboardPresets.back_to_start(),
        new_state=DialogState.input_of_forum_username,
    )


def handle_vk_linking(vk_message: VKMessage, state: DialogState | None, user_id: int) -> VKHandlerResult | None:
    """Handle VK linking button.

    Generates a proper invite text using make_invite_text_for_user() which
    creates a SHA256 hash of {telegram_user_id}{bot_api_token__prod}.
    The user copies this text and sends it to the VK bot to link accounts.
    """
    text = vk_message.text.strip().lower()
    if text != VKKeyboardButtons.BTN_VK_LINK.lower():
        return None

    vk_id = db().get_user_vk_id(user_id)
    if vk_id:
        return VKHandlerResult(
            text=vk_already_linked(),
            keyboard=VKKeyboardPresets.settings_menu(),
        )

    invite_text = make_invite_text_for_user(user_id)
    return VKHandlerResult(
        text=vk_link_instructions(invite_text),
        keyboard=VKKeyboardPresets.settings_menu(),
    )


settings_router: list = [
    handle_settings_menu,
    handle_notification_toggle,
    handle_coordinates_action,
    handle_age_settings,
    handle_topic_type_settings,
    handle_forum_linking,
    handle_vk_linking,
    handle_other_menu,
]
