"""Main button/command handlers for the VK bot.

Each handler matches by vk_message.text content and handles a specific
button click or command. Returns VKHandlerResult if it handles the message,
or None to pass to the next handler in the chain.
"""

import logging
import time

from _dependencies.services.message_formatter import (
    compose_settings_completeness_message,
    coords_deleted,
    coords_intro,
    coords_not_set,
    forum_already_linked,
    forum_link_intro,
    notif_settings_current_prefs,
    notif_settings_intro,
    onboarding_completed_message,
    radius_intro_no_radius,
    radius_intro_with_radius,
    radius_deleted,
    region_selection_intro,
    role_other_ask_region,
    role_relative_instructions,
    role_volunteer_instructions,
    settings_menu_intro,
    vk_already_linked,
    vk_link_intro,
    welcome_back_user,
    welcome_new_user,
)
from _dependencies.services.state_machine import DialogState

from ..common import VKHandlerResult, VKMessage
from ..database import db
from ..keyboards import VKKeyboard

logger = logging.getLogger(__name__)


# ── Onboarding ─────────────────────────────────────────────────────


def handle_command_start(vk_message: VKMessage, state: DialogState | None, user_id: int) -> VKHandlerResult | None:
    """Handle /start command — show welcome message and main menu."""
    if vk_message.text.strip() != '/start':
        return None

    is_new = db().settings.check_if_new_user(user_id)
    text = welcome_new_user() if is_new else welcome_back_user()
    return VKHandlerResult(
        text=text,
        keyboard=VKKeyboard.main_menu(),
        new_state=DialogState.not_defined,
    )


def handle_role_choice(vk_message: VKMessage, state: DialogState | None, user_id: int) -> VKHandlerResult | None:
    """Handle role selection during onboarding.

    Matches button text from VKKeyboard.role_choice().
    """
    text = vk_message.text.strip().lower()

    role_map = {
        'я состою в лизаалерт': 'member',
        'я хочу помогать лизаалерт': 'volunteer',
        'я ищу человека': 'relative',
        'у меня другая задача': 'other',
        'не хочу говорить': 'other',
    }

    if text not in role_map:
        return None

    role_code = role_map[text]
    db().settings.save_user_role(user_id, role_code)
    db().settings.save_onboarding_step(user_id, 'role_set')

    instructions_map = {
        'member': role_volunteer_instructions(),
        'volunteer': role_volunteer_instructions(),
        'other': role_other_ask_region(),
    }
    instructions = instructions_map.get(role_code)

    if role_code == 'relative':
        return VKHandlerResult(
            text=role_relative_instructions(),
            keyboard=VKKeyboard.orders_done(),
        )

    if role_code == 'member':
        return VKHandlerResult(
            text=instructions or 'Нужна ли вам помощь?',
            keyboard=VKKeyboard.help_needed(),
        )

    # volunteer or other → ask Moscow
    return VKHandlerResult(
        text=instructions or region_selection_intro(),
        keyboard=VKKeyboard.is_moscow(),
    )


def handle_orders_state(vk_message: VKMessage, state: DialogState | None, user_id: int) -> VKHandlerResult | None:
    """Handle orders done/TBD for relative role."""
    text = vk_message.text.strip().lower()
    if text not in ('уже заказал(а)', 'закажу позже'):
        return None

    db().settings.save_onboarding_step(user_id, 'region_set')
    return VKHandlerResult(
        text='Спасибо! Давайте настроим регион для поисков.',
        keyboard=VKKeyboard.is_moscow(),
    )


def _subscribe_moscow_regions(user_id: int) -> None:
    """Subscribe user to Moscow and Moscow Oblast regions."""
    folders = db().settings.get_geo_folders()
    for fid, name in folders:
        if 'москв' in name.lower() or 'мо:' in name.lower():
            db().settings.add_region(user_id, fid)


def handle_is_moscow(vk_message: VKMessage, state: DialogState | None, user_id: int) -> VKHandlerResult | None:
    """Handle Moscow region confirmation during onboarding."""
    text = vk_message.text.strip().lower()

    if text == 'да, москва – мой регион':
        _subscribe_moscow_regions(user_id)
        db().settings.save_onboarding_step(user_id, 'finished')
        return VKHandlerResult(
            text=onboarding_completed_message(),
            keyboard=VKKeyboard.main_menu(),
        )

    if text == 'нет, я из другого региона':
        return VKHandlerResult(
            text=region_selection_intro(),
            keyboard=VKKeyboard.fed_districts(),
        )

    return None


def handle_help_needed(vk_message: VKMessage, state: DialogState | None, user_id: int) -> VKHandlerResult | None:
    """Handle help needed question for member role."""
    text = vk_message.text.strip().lower()
    if text not in ('да, помогите мне настроить бот', 'нет, помощь не требуется'):
        return None

    db().settings.save_onboarding_step(user_id, 'region_set')
    return VKHandlerResult(
        text=region_selection_intro(),
        keyboard=VKKeyboard.fed_districts(),
    )


# ── Main Menu ──────────────────────────────────────────────────────


def handle_main_menu(vk_message: VKMessage, state: DialogState | None, user_id: int) -> VKHandlerResult | None:
    """Handle main menu navigation buttons."""
    text = vk_message.text.strip().lower()

    if text == 'настроить бот':
        summary = db().settings.get_settings_summary(user_id)
        if summary:
            completeness = compose_settings_completeness_message(
                has_notif_type=summary.pref_notif_type,
                has_region=summary.pref_region_old or summary.pref_region,
                has_coords=summary.pref_coords,
                has_radius=summary.pref_radius,
                has_age=summary.pref_age,
                has_forum=summary.pref_forum,
            )
            settings_text = settings_menu_intro()
            if completeness:
                settings_text += '\n\n' + completeness
        else:
            settings_text = settings_menu_intro()

        return VKHandlerResult(
            text=settings_text,
            keyboard=VKKeyboard.settings_menu(),
        )

    if text == 'посмотреть актуальные поиски':
        return VKHandlerResult(
            text='Функция просмотра поисков будет доступна в следующей версии.',
            keyboard=VKKeyboard.main_menu(),
        )

    if text in ('другие возможности', '🔥карта поисков 🔥'):
        return VKHandlerResult(
            text='Выберите раздел:',
            keyboard=VKKeyboard.other_menu(),
        )

    return None


def handle_back_to_start(vk_message: VKMessage, state: DialogState | None, user_id: int) -> VKHandlerResult | None:
    """Handle 'в начало' button — return to main menu."""
    if vk_message.text.strip().lower() != 'в начало':
        return None

    return VKHandlerResult(
        text=welcome_back_user(),
        keyboard=VKKeyboard.main_menu(),
        new_state=DialogState.not_defined,
    )


# ── Settings Sub-menus ─────────────────────────────────────────────


def handle_settings_menu(vk_message: VKMessage, state: DialogState | None, user_id: int) -> VKHandlerResult | None:
    """Handle settings menu button clicks."""
    text = vk_message.text.strip().lower()

    if text == 'настроить виды уведомлений':
        prefs = db().settings.get_all_user_preferences(user_id)
        prefs_text = ''
        if prefs:
            from _dependencies.services.message_formatter import format_notif_prefs_list

            prefs_text = '\n' + notif_settings_current_prefs(format_notif_prefs_list(prefs))
        return VKHandlerResult(
            text=notif_settings_intro() + prefs_text,
            keyboard=VKKeyboard.notification_settings(),
        )

    if text == 'настроить "домашние координаты"':
        coords = db().settings.get_coordinates(user_id)
        if coords:
            return VKHandlerResult(
                text=coords_intro(),
                keyboard=VKKeyboard.coords_menu(),
            )
        return VKHandlerResult(
            text=coords_not_set(),
            keyboard=VKKeyboard.coords_menu(),
        )

    if text in ('настроить максимальный радиус', 'включить ограничение по расстоянию'):
        radius = db().settings.get_radius(user_id)
        if radius:
            return VKHandlerResult(
                text=radius_intro_with_radius(radius),
                keyboard=VKKeyboard.radius_settings(has_radius=True),
            )
        return VKHandlerResult(
            text=radius_intro_no_radius(),
            keyboard=VKKeyboard.radius_settings(),
        )

    if text == 'изменить радиус':
        radius = db().settings.get_radius(user_id)
        current = f'Текущий радиус: {radius} км. ' if radius else ''
        return VKHandlerResult(
            text=f'{current}Введите новый радиус в километрах (только число).',
            keyboard=VKKeyboard.back_to_start(),
            new_state=DialogState.radius_input,
        )

    if text == 'отключить ограничение по расстоянию':
        db().settings.delete_radius(user_id)
        return VKHandlerResult(
            text=radius_deleted(),
            keyboard=VKKeyboard.settings_menu(),
        )

    if text == 'настроить возрастные группы бвп':
        return VKHandlerResult(
            text='Выберите возрастные группы:',
            keyboard=VKKeyboard.age_settings(),
        )

    if text == 'настроить вид поисков':
        return VKHandlerResult(
            text='Выберите виды поисков, которые хотите отслеживать:',
            keyboard=VKKeyboard.topic_type_settings(),
        )

    if text == 'связать аккаунты бота и форума':
        forum_data = db().settings.get_forum_attributes(user_id)
        if forum_data:
            forum_username, forum_user_id = forum_data
            return VKHandlerResult(
                text=forum_already_linked(forum_username, int(forum_user_id)),
                keyboard=VKKeyboard.settings_menu(),
            )
        return VKHandlerResult(
            text=forum_link_intro(),
            keyboard=VKKeyboard.forum_linking(),
        )

    if text == 'связать аккаунты бота и vkontakte':
        vk_id = db().settings.get_user_vk_id(user_id)
        if vk_id:
            return VKHandlerResult(
                text=vk_already_linked(),
                keyboard=VKKeyboard.settings_menu(),
            )
        return VKHandlerResult(
            text=vk_link_intro(),
            keyboard=VKKeyboard.vk_linking(),
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
    notif_map: dict[str, str] = {
        'включить: все уведомления': 'all',
        'включить: о новых поисках': 'new_searches',
        'включить: об изменениях статусов': 'status_changes',
        'включить: о всех новых комментариях': 'comments_changes',
        'включить: о комментариях инфорга': 'inforg_comments',
        'включить: об изменениях в первом посте': 'first_post_changes',
        'включить: в отслеживаемых поисках - все уведомления': 'all_in_followed_search',
        'отключить: о новых поисках': 'new_searches',
        'отключить: об изменениях статусов': 'status_changes',
        'отключить: о всех новых комментариях': 'comments_changes',
        'отключить: о комментариях инфорга': 'inforg_comments',
        'отключить: об изменениях в первом посте': 'first_post_changes',
        'отключить: в отслеживаемых поисках - все уведомления': 'all_in_followed_search',
    }

    if text not in notif_map:
        return None

    pref_name = notif_map[text]
    is_enable = text.startswith('включить:')

    if is_enable:
        if pref_name == 'all':
            # Enable all — clear existing and set 'all'
            db().settings.delete_preferences(user_id, [])
            db().settings.save_preference(user_id, 'all')
        else:
            db().settings.save_preference(user_id, pref_name)
    else:
        if pref_name == 'all':
            db().settings.delete_preferences(user_id, [])
        else:
            db().settings.delete_preferences(user_id, [pref_name])

    # Show updated preferences
    prefs = db().settings.get_all_user_preferences(user_id)
    from _dependencies.services.message_formatter import format_notif_prefs_list

    prefs_text = ''
    if prefs:
        prefs_text = '\n' + notif_settings_current_prefs(format_notif_prefs_list(prefs))

    return VKHandlerResult(
        text=notif_settings_intro() + prefs_text,
        keyboard=VKKeyboard.notification_settings(),
    )


def handle_coordinates_action(vk_message: VKMessage, state: DialogState | None, user_id: int) -> VKHandlerResult | None:
    """Handle coordinates sub-menu actions."""
    text = vk_message.text.strip().lower()

    if text == 'ввести "домашние координаты" вручную':
        return VKHandlerResult(
            text='Введите координаты в формате: широта, долгота (например: 55.7558, 37.6173)',
            keyboard=VKKeyboard.back_to_start(),
            new_state=DialogState.input_of_coords_man,
        )

    if text == 'посмотреть сохраненные "домашние координаты"':
        coords = db().settings.get_coordinates(user_id)
        if coords:
            lat, lon = coords
            return VKHandlerResult(
                text=f'Ваши координаты: {lat}, {lon}',
                keyboard=VKKeyboard.coords_menu(),
            )
        return VKHandlerResult(
            text=coords_not_set(),
            keyboard=VKKeyboard.coords_menu(),
        )

    if text == 'удалить "домашние координаты"':
        db().settings.delete_coordinates(user_id)
        return VKHandlerResult(
            text=coords_deleted(),
            keyboard=VKKeyboard.settings_menu(),
        )

    return None


def handle_age_settings(vk_message: VKMessage, state: DialogState | None, user_id: int) -> VKHandlerResult | None:
    """Handle age preference toggles.

    Maps button text to AgePeriod objects and toggles them.
    """
    text = vk_message.text.strip().lower()

    from _dependencies.services.user_settings_service import AgePeriod

    age_map: dict[str, AgePeriod] = {
        'дети (0-10 лет)': AgePeriod(
            description='дети (0-10 лет)',
            name='0-10',
            min_age=0,
            max_age=10,
            order=1,
        ),
        'подростки (11-17 лет)': AgePeriod(
            description='подростки (11-17 лет)',
            name='11-17',
            min_age=11,
            max_age=17,
            order=2,
        ),
        'взрослые (18-50 лет)': AgePeriod(
            description='взрослые (18-50 лет)',
            name='18-50',
            min_age=18,
            max_age=50,
            order=3,
        ),
        'пожилые (51+ лет)': AgePeriod(
            description='пожилые (51+ лет)',
            name='51-150',
            min_age=51,
            max_age=150,
            order=4,
        ),
    }

    if text not in age_map:
        return None

    period = age_map[text]
    current_prefs = db().settings.get_age_preferences(user_id)

    # Check if this period is already set
    period_active = any(p_min == period.min_age and p_max == period.max_age for p_min, p_max in current_prefs)

    if period_active:
        db().settings.delete_age_preference(user_id, period)
    else:
        db().settings.save_age_preference(user_id, period)

    updated = db().settings.get_age_preferences(user_id)
    # Build readable list of active age groups
    age_names = []
    for p_min, p_max in updated:
        for btn_text, ap in age_map.items():
            if ap.min_age == p_min and ap.max_age == p_max:
                age_names.append(btn_text)
                break

    prefs_text = ', '.join(age_names) if age_names else 'не выбрано'
    return VKHandlerResult(
        text=f'Возрастные группы: {prefs_text}',
        keyboard=VKKeyboard.age_settings(),
    )


def handle_topic_type_settings(
    vk_message: VKMessage, state: DialogState | None, user_id: int
) -> VKHandlerResult | None:
    """Handle topic type preference toggles.

    Maps button text to topic_type_id integers and toggles them.
    """
    text = vk_message.text.strip().lower()

    type_map: dict[str, int] = {
        'поисковые работы': 0,
        'информационный поиск': 4,
    }

    if text not in type_map:
        return None

    topic_type_id = type_map[text]
    current_types = db().settings.get_topic_types(user_id)

    if topic_type_id in current_types:
        db().settings.delete_topic_type(user_id, topic_type_id)
    else:
        db().settings.save_topic_type(user_id, topic_type_id)

    updated = db().settings.get_topic_types(user_id)
    # Map IDs back to names
    id_to_name = {v: k for k, v in type_map.items()}
    types_text = ', '.join(id_to_name.get(tid, f'тип {tid}') for tid in updated) or 'не выбрано'

    return VKHandlerResult(
        text=f'Виды поисков: {types_text}',
        keyboard=VKKeyboard.topic_type_settings(),
    )


def handle_other_menu(vk_message: VKMessage, state: DialogState | None, user_id: int) -> VKHandlerResult | None:
    """Handle other options menu buttons."""
    text = vk_message.text.strip().lower()

    if text == 'посмотреть последние поиски':
        return VKHandlerResult(
            text='Функция будет доступна в следующей версии.',
            keyboard=VKKeyboard.other_menu(),
        )

    if text == 'написать разработчику бота':
        return VKHandlerResult(
            text='Связаться с разработчиком можно в чате бота.',
            keyboard=VKKeyboard.other_menu(),
        )

    if text == 'ознакомиться с информацией для новичка':
        return VKHandlerResult(
            text='Информация для новичка доступна на сайте lizaalert.org',
            keyboard=VKKeyboard.other_menu(),
        )

    if text == 'посмотреть красивые фото с поисков':
        return VKHandlerResult(
            text='Функция будет доступна в следующей версии.',
            keyboard=VKKeyboard.other_menu(),
        )

    return None


def handle_forum_linking(vk_message: VKMessage, state: DialogState | None, user_id: int) -> VKHandlerResult | None:
    """Handle forum linking — set state to input forum username."""
    text = vk_message.text.strip().lower()
    if text != 'ввести ник с форума':
        return None

    return VKHandlerResult(
        text='Введите ваш логин (ник) на форуме lizaalert.org:',
        keyboard=VKKeyboard.back_to_start(),
        new_state=DialogState.input_of_forum_username,
    )


def handle_vk_linking(vk_message: VKMessage, state: DialogState | None, user_id: int) -> VKHandlerResult | None:
    """Handle VK linking button."""
    text = vk_message.text.strip().lower()
    if text != 'связать аккаунты':
        return None

    vk_id = db().settings.get_user_vk_id(user_id)
    if vk_id:
        return VKHandlerResult(
            text=vk_already_linked(),
            keyboard=VKKeyboard.settings_menu(),
        )

    from _dependencies.services.message_formatter import vk_link_instructions

    import time

    invite_text = f'la_link_{user_id}_{int(time.time())}'
    return VKHandlerResult(
        text=vk_link_instructions(invite_text),
        keyboard=VKKeyboard.settings_menu(),
    )
