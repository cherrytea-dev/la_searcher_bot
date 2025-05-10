from contextlib import suppress
from enum import Enum
from typing import Any, Dict

from telegram import InlineKeyboardButton, KeyboardButton, ReplyKeyboardMarkup

from _dependencies.commons import TopicType


class ExtendedEnum(Enum):
    @classmethod
    def list(cls) -> list[str]:
        return list(map(lambda c: c.value, cls))


c_start = '/start'

b_back_to_start = 'в начало'
b_fed_dist_other_r = 'Прочие поиски по РФ'
b_fed_dist_pick_other = 'выбрать другой Федеральный Округ'

b_act_titles = 'названия'  # these are "Title update notification" button

# admin and experimental options
b_admin_menu = 'admin'
b_test_menu = 'test'
b_test_search_follow_mode_on = 'test search follow mode on'  # noqa
b_test_search_follow_mode_off = 'test search follow mode off'


# Settings - Fed Dist - Regions
b_menu_set_region = 'настроить регион поисков'
b_region_select_var_2 = 'Выбор региона: вариант 2'

# Settings - coordinates
b_coords_auto_def = KeyboardButton(text='автоматически определить "домашние координаты"', request_location=True)


class IsMoscow(str, ExtendedEnum):
    b_reg_moscow = 'да, Москва – мой регион'
    b_reg_not_moscow = 'нет, я из другого региона'


class OrdersState(str, ExtendedEnum):
    b_orders_done = 'да, заявки поданы'
    b_orders_tbd = 'нет, но я хочу продолжить'


class Commands(str, ExtendedEnum):
    c_view_act_searches = '/view_act_searches'
    c_view_latest_searches = '/view_latest_searches'
    c_settings = '/settings'
    c_other = '/other'
    c_map = '/map'


class RoleChoice(str, ExtendedEnum):
    b_role_iam_la = 'я состою в ЛизаАлерт'
    b_role_want_to_be_la = 'я хочу помогать ЛизаАлерт'
    b_role_looking_for_person = 'я ищу человека'
    b_role_other = 'у меня другая задача'
    b_role_secret = 'не хочу говорить'


class DistanceSettings(str, ExtendedEnum):
    b_pref_radius_act = 'включить ограничение по расстоянию'
    b_pref_radius_deact = 'отключить ограничение по расстоянию'
    b_pref_radius_change = 'изменить ограничение по расстоянию'


class ItsMe(str, ExtendedEnum):
    b_yes_its_me = 'да, это я'
    b_no_its_not_me = 'нет, это не я'


class MainMenu(str, ExtendedEnum):
    b_view_act_searches = 'посмотреть актуальные поиски'
    b_settings = 'настроить бот'
    b_other = 'другие возможности'
    b_map = '🔥Карта Поисков 🔥'


class HelpNeeded(str, ExtendedEnum):
    b_help_yes = 'да, помогите мне настроить бот'
    b_help_no = 'нет, помощь не требуется'


class MainSettingsMenu(str, ExtendedEnum):
    # Settings menu
    b_set_pref_notif_type = 'настроить виды уведомлений'
    b_set_pref_coords = 'настроить "домашние координаты"'
    b_set_pref_radius = 'настроить максимальный радиус'
    b_set_pref_age = 'настроить возрастные группы БВП'
    b_set_forum_nick = 'связать аккаунты бота и форума'
    b_change_forum_nick = 'изменить аккаунт форума'  # noqa
    b_set_topic_type = 'настроить вид поисков'


class NotificationSettingsMenu(str, ExtendedEnum):
    # Settings - notifications
    b_act_all = 'включить: все уведомления'
    b_act_new_search = 'включить: о новых поисках'
    b_act_stat_change = 'включить: об изменениях статусов'
    b_act_all_comments = 'включить: о всех новых комментариях'
    b_act_inforg_com = 'включить: о комментариях Инфорга'
    b_act_field_trips_new = 'включить: о новых выездах'  # TODO not used
    b_act_field_trips_change = 'включить: об изменениях в выездах'  # TODO not used
    b_act_coords_change = 'включить: о смене места штаба'  # TODO not used
    b_act_first_post_change = 'включить: об изменениях в первом посте'
    b_act_all_in_followed_search = 'включить: в отслеживаемых поисках - все уведомления'
    ###
    b_deact_all = 'настроить более гибко'
    b_deact_new_search = 'отключить: о новых поисках'
    b_deact_stat_change = 'отключить: об изменениях статусов'
    b_deact_all_comments = 'отключить: о всех новых комментариях'
    b_deact_inforg_com = 'отключить: о комментариях Инфорга'
    b_deact_field_trips_new = 'отключить: о новых выездах'  # TODO not used
    b_deact_field_trips_change = 'отключить: об изменениях в выездах'  # TODO not used
    b_deact_coords_change = 'отключить: о смене места штаба'  # TODO not used
    b_deact_first_post_change = 'отключить: об изменениях в первом посте'
    b_deact_all_in_followed_search = 'отключить: в отслеживаемых поисках - все уведомления'


class CoordinateSettingsMenu(str, ExtendedEnum):
    b_coords_man_def = 'ввести "домашние координаты" вручную'
    b_coords_check = 'посмотреть сохраненные "домашние координаты"'
    b_coords_del = 'удалить "домашние координаты"'


# Other menu
class OtherOptionsMenu(str, ExtendedEnum):
    b_view_latest_searches = 'посмотреть последние поиски'
    b_goto_community = 'написать разработчику бота'
    b_goto_first_search = 'ознакомиться с информацией для новичка'
    b_goto_photos = 'посмотреть красивые фото с поисков'


class TopicTypeInlineKeyboardBuilder:
    keyboard_code = 'topic_type_select'
    modifier = {True: '✅ ', False: '☐ ', None: ''}
    _topic_buttons_data = [
        ('regular', 'стандартные активные поиски', TopicType.search_regular, False),
        ('resonance', 'резонансные поиски', TopicType.search_resonance, False),
        ('info_support', 'информационная поддержка', TopicType.search_info_support, False),
        ('reverse', 'обратные поиски', TopicType.search_reverse, False),
        ('training', 'учебные поиски', TopicType.search_training, False),
        ('patrol', 'ночной патруль', TopicType.search_patrol, False),
        ('event', 'мероприятия', TopicType.event, False),
        # ('info', 'полезная информация', TopicType.info, False),
        ('about', '💡 справка по типам поисков 💡', None, False),
    ]

    @classmethod
    def manual_callback_handling(cls, cb_data: dict[str, Any]) -> bool:
        with suppress(Exception):
            if cb_data['keyboard'] == cls.keyboard_code and cb_data['action'] == 'about':
                return True
        return False

    @classmethod
    def get_topic_id_by_button(cls, callback_data: dict) -> TopicType | None:
        topic_id = callback_data['action'].split()[0]
        return None if topic_id == 'None' else TopicType(int(topic_id))

    @classmethod
    def get_keyboard(cls, current_options: list, changed_options: list) -> list[list[InlineKeyboardButton]]:
        keyboard = []
        all_options = set(current_options)
        for option in changed_options:
            if option in all_options:
                all_options.remove(option)
            else:
                all_options.add(option)
        for code, name, topic_type, hidden_ in cls._topic_buttons_data:
            button = cls._create_button(all_options, code, name, topic_type)
            keyboard.append([button])
        return keyboard

    @classmethod
    def _create_button(
        cls, all_options: set[int], code: str, name: str, topic_type: TopicType | None
    ) -> InlineKeyboardButton:
        option_selected = None if topic_type is None else topic_type in all_options

        if topic_type is None:
            action = code
        else:
            action = f'{topic_type} {"off" if option_selected else "on"}'

        cb_data = {
            'keyboard': cls.keyboard_code,
            'action': action,
        }

        button_text = cls.modifier[option_selected] + name
        button = InlineKeyboardButton(text=button_text, callback_data=str(cb_data))
        assert len(str(cb_data)) <= InlineKeyboardButton.MAX_CALLBACK_DATA
        return button

    @classmethod
    def if_user_enables(cls, callback: Dict) -> bool | None:
        """check if user wants to enable or disable a feature"""

        if callback['action'].endswith('on'):
            return True
        if callback['action'].endswith('off'):
            return False
        return None


# basic markup which will be substituted for all specific cases
_keyboard_main = [[MainMenu.b_map], [MainMenu.b_view_act_searches], [MainMenu.b_settings], [MainMenu.b_other]]
reply_markup_main = ReplyKeyboardMarkup(_keyboard_main, resize_keyboard=True)
