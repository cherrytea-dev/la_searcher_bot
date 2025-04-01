import logging
from dataclasses import dataclass
from typing import Any, List, Tuple, Union


from _dependencies.misc import age_writer, time_counter_since_search_start
from communicate._utils.common import define_dist_and_dir_to_search
from communicate._utils.database import db


@dataclass
class SearchSummary:
    # TODO can be replaced with similar classes?
    topic_type: Any = None
    topic_id: Any = None
    parsed_time: Any = None
    status: Any = None
    title: Any = None
    link: Any = None
    start_time: Any = None
    num_of_replies: Any = None
    name: Any = None
    display_name: Any = None
    age: Any = None
    searches_table_id: Any = None
    folder_id: Any = None
    age_max: Any = None
    age_min: Any = None
    num_of_persons: Any = None
    city_locations: Any = None  # city / town / place – approximate coordinates
    hq_locations: Any = None  # shtab –exact coordinates
    new_status: Any = None
    full_dict: Any = None

    def __str__(self):
        return (
            f'{self.parsed_time} – {self.folder_id} / {self.topic_id} : {self.name} - {self.age} – '
            f'{self.num_of_replies}. NEW: {self.display_name} – {self.age_min} – {self.age_max} – '
            f'{self.num_of_persons}'
        )


def compose_msg_on_user_setting_fullness(user_id: int) -> Union[str, None]:
    """Create a text of message, which describes the degree on how complete user's profile is.
    More settings set – more complete profile it. It's done to motivate users to set the most tailored settings."""

    if not user_id:
        return None

    try:
        raw_data = db().get_existing_user_settings(user_id)

        if not raw_data:
            return None

        (
            _,
            pref_role,
            pref_age,
            pref_coords,
            pref_radius,
            pref_region,
            pref_topic_type,
            pref_urgency,
            pref_notif_type,
            pref_region_old,
            pref_forum,
        ) = raw_data

        list_of_settings = [pref_notif_type, pref_region_old, pref_coords, pref_radius, pref_age, pref_forum]
        user_score = int(round(sum(list_of_settings) / len(list_of_settings) * 100, 0))

        logging.info(f'List of user settings activation: {list_of_settings=}')
        logging.info(f'User settings completeness score is {user_score}')

        if user_score == 100:
            return None

        user_score_emoji = (
            f'{user_score // 10}\U0000fe0f\U000020e3{user_score - (user_score // 10) * 10}\U0000fe0f\U000020e3'
        )
        message_text = (
            f'Вы настроили бот на {user_score_emoji}%.\n\nЧтобы сделать бот максимально эффективным '
            f'именно для вас, рекомендуем настроить следующие параметры:\n'
        )
        if not pref_notif_type:
            message_text += ' - Тип уведомлений,\n'
        if not pref_region_old:
            message_text += ' - Регион,\n'
        if not pref_coords:
            message_text += ' - Домашние координаты,\n'
        if not pref_radius:
            message_text += ' - Максимальный радиус,\n'
        if not pref_age:
            message_text += ' - Возрастные группы БВП,\n'
        if not pref_forum:
            message_text += ' - Связать бот с форумом ЛА,\n'
        message_text = message_text[:-2]

        return message_text

    except Exception as e:
        logging.exception('Exception in "compose_msg_on_user_setting_fullness" function')
        return None


def compose_user_preferences_message(user_id: int) -> List[Union[List[str], str]]:
    """Compose a text for user on which types of notifications are enabled for zir"""

    user_prefs = db().get_all_user_preferences(user_id)

    prefs_wording = ''
    prefs_list = []
    if user_prefs and len(user_prefs) > 0:
        for user_pref_line in user_prefs:
            prefs_list.append(user_pref_line[0])
            if user_pref_line[0] == 'all':
                prefs_wording += 'все сообщения'
            elif user_pref_line[0] == 'new_searches':
                prefs_wording += ' &#8226; о новых поисках\n'
            elif user_pref_line[0] == 'status_changes':
                prefs_wording += ' &#8226; об изменении статуса\n'
            elif user_pref_line[0] == 'title_changes':
                prefs_wording += ' &#8226; об изменении заголовка\n'
            elif user_pref_line[0] == 'comments_changes':
                prefs_wording += ' &#8226; о всех комментариях\n'
            elif user_pref_line[0] == 'inforg_comments':
                prefs_wording += ' &#8226; о комментариях Инфорга\n'
            elif user_pref_line[0] == 'first_post_changes':
                prefs_wording += ' &#8226; об изменениях в первом посте\n'
            elif user_pref_line[0] == 'all_in_followed_search':
                prefs_wording += ' &#8226; в отслеживаемом поиске - все уведомления\n'
            elif user_pref_line[0] == 'bot_news':
                pass
            else:
                prefs_wording += 'неизвестная настройка'
    else:
        prefs_wording += 'пока нет включенных уведомлений'

    prefs_wording_and_list = [prefs_wording, prefs_list]

    return prefs_wording_and_list


def compose_msg_on_all_last_searches(region: int) -> str:
    """Compose a part of message on the list of recent searches"""

    pre_url = 'https://lizaalert.org/forum/viewtopic.php?t='
    text = ''

    # download the list from SEARCHES sql table
    database = db().get_all_searches_in_one_region(region)

    for line in database:
        search = SearchSummary()
        (
            search.topic_id,
            search.start_time,
            search.display_name,
            search.new_status,
            search.status,
            search.name,
            search.age,
        ) = list(line)

        if not search.display_name:
            age_string = f' {age_writer(search.age)}' if search.age and search.age != 0 else ''
            search.display_name = f'{search.name}{age_string}'

        if not search.new_status:
            search.new_status = search.status

        if search.new_status in {'Ищем', 'Возобновлен'}:
            search.new_status = f'Ищем {time_counter_since_search_start(search.start_time)[0]}'

        text += f'{search.new_status} <a href="{pre_url}{search.topic_id}">{search.display_name}</a>\n'

    return text


def compose_msg_on_all_last_searches_ikb(region: int, user_id: int, only_followed: bool) -> List:
    """Compose a part of message on the list of recent searches"""
    # issue#425 it is ikb variant of the above function, returns data formated for inline keyboard
    # 1st element of returned list is general info and should be popped
    # rest elements are searches to be showed as inline buttons
    # 24.03.2025: followed in whitelist searches to be showed regardless of region settings and the 60-days expiration, even in 'СТОП'

    pre_url = 'https://lizaalert.org/forum/viewtopic.php?t='
    ikb = []

    database = db().get_all_last_searches_in_region(region, user_id, only_followed)

    for line in database:
        search = SearchSummary()
        (
            search.topic_id,
            search.start_time,
            search.display_name,
            search.new_status,
            search.status,
            search.name,
            search.age,
            search_following_mode,
        ) = list(line)

        if not search.display_name:
            age_string = f' {age_writer(search.age)}' if search.age and search.age != 0 else ''
            search.display_name = f'{search.name}{age_string}'

        if not search.new_status:
            search.new_status = search.status

        if search.new_status in {'Ищем', 'Возобновлен'}:
            search.new_status = f'Ищем {time_counter_since_search_start(search.start_time)[0]}'

        ikb += search_button_row_ikb(
            search_following_mode,
            search.new_status,
            search.topic_id,
            search.display_name,
            f'{pre_url}{search.topic_id}',
        )
    return ikb


def compose_msg_on_active_searches_in_one_reg(region: int, user_data) -> str:
    """Compose a part of message on the list of active searches in the given region with relation to user's coords"""

    pre_url = 'https://lizaalert.org/forum/viewtopic.php?t='
    text = ''

    searches_list = db().get_active_searches_in_one_region(region)

    user_lat = None
    user_lon = None

    if user_data:
        user_lat = user_data[0]
        user_lon = user_data[1]

    for line in searches_list:
        search = SearchSummary()
        (
            search.topic_id,
            search.start_time,
            search.display_name,
            search_lat,
            search_lon,
            search.topic_type,
            search.name,
            search.age,
        ) = list(line)

        if time_counter_since_search_start(search.start_time)[1] >= 60:
            continue

        time_since_start = time_counter_since_search_start(search.start_time)[0]

        if user_lat and search_lat:
            dist = define_dist_and_dir_to_search(search_lat, search_lon, user_lat, user_lon)
            dist_and_dir = f' {dist[1]} {dist[0]} км'
        else:
            dist_and_dir = ''

        if not search.display_name:
            age_string = f' {age_writer(search.age)}' if search.age != 0 else ''
            search.display_name = f'{search.name}{age_string}'

        text += f'{time_since_start}{dist_and_dir} <a href="{pre_url}{search.topic_id}">{search.display_name}</a>\n'

    return text


def compose_msg_on_active_searches_in_one_reg_ikb(region: int, user_data: Tuple[str, str], user_id: int) -> List:
    """Compose a part of message on the list of active searches in the given region with relation to user's coords"""
    # issue#425 it is ikb variant of the above function, returns data formated for inline keyboard
    # 1st element of returned list is general info and should be popped
    # rest elements are searches to be showed as inline buttons
    # 24.03.2025: followed in whitelist searches to be showed regardless of region settings and the 60-days expiration, even in 'СТОП'

    pre_url = 'https://lizaalert.org/forum/viewtopic.php?t='
    ikb = []

    searches_list = db().get_all_active_searches_in_one_region_2(region, user_id)

    user_lat = None
    user_lon = None

    if user_data:
        user_lat = user_data[0]
        user_lon = user_data[1]

    for line in searches_list:
        search = SearchSummary()
        (
            search.topic_id,
            search.start_time,
            search.display_name,
            search_lat,
            search_lon,
            search.topic_type,
            search.name,
            search.age,
            search_following_mode,
        ) = list(line)

        if time_counter_since_search_start(search.start_time)[1] >= 60 and not search_following_mode:
            continue

        time_since_start = time_counter_since_search_start(search.start_time)[0]

        if user_lat and search_lat:
            dist = define_dist_and_dir_to_search(search_lat, search_lon, user_lat, user_lon, False)
            dist_and_dir = f' {dist[1]} {dist[0]} км'
        else:
            dist_and_dir = ''

        if not search.display_name:
            age_string = f' {age_writer(search.age)}' if search.age != 0 else ''
            search.display_name = f'{search.name}{age_string}'

        ikb += search_button_row_ikb(
            search_following_mode,
            f'{time_since_start}{dist_and_dir}',
            search.topic_id,
            search.display_name,
            f'{pre_url}{search.topic_id}',
        )
    return ikb


def compose_full_message_on_list_of_searches(list_type: str, user_id: int, region: int, region_name: str) -> str:
    """Compose a Final message on the list of searches in the given region"""

    msg = ''

    user_data = db().get_saved_user_coordinates(user_id)

    # combine the list of last 20 searches
    if list_type == 'all':
        msg += compose_msg_on_all_last_searches(region)

        if msg:
            msg = (
                'Последние 20 поисков в разделе <a href="https://lizaalert.org/forum/viewforum.php?f='
                + str(region)
                + '">'
                + region_name
                + '</a>:\n'
                + msg
            )

        else:
            msg = (
                'Не получается отобразить последние поиски в разделе '
                '<a href="https://lizaalert.org/forum/viewforum.php?f='
                + str(region)
                + '">'
                + region_name
                + '</a>, что-то пошло не так, простите. Напишите об этом разработчику '
                'в <a href="https://t.me/joinchat/2J-kV0GaCgwxY2Ni">Специальном Чате '
                'в телеграм</a>, пожалуйста.'
            )

    # Combine the list of the latest active searches
    else:
        msg += compose_msg_on_active_searches_in_one_reg(region, user_data)

        if msg:
            msg = (
                'Актуальные поиски за 60 дней в разделе <a href="https://lizaalert.org/forum/viewforum.php?f='
                + str(region)
                + '">'
                + region_name
                + '</a>:\n'
                + msg
            )

        else:
            msg = (
                'В разделе <a href="https://lizaalert.org/forum/viewforum.php?f='
                + str(region)
                + '">'
                + region_name
                + '</a> все поиски за последние 60 дней завершены.'
            )

    return msg


def compose_full_message_on_list_of_searches_ikb(
    list_type: str, user_id: int, region: int, region_name: str, only_followed: bool
):  # issue#425
    """Compose a Final message on the list of searches in the given region"""
    # issue#425 This variant of the above function returns data in format used to compose inline keyboard
    # 1st element is caption
    # rest elements are searches in format to be showed as inline buttons

    ikb = []

    user_data = db().get_saved_user_coordinates(user_id)

    url = f'https://lizaalert.org/forum/viewforum.php?f={region}'
    # combine the list of last 20 searches
    if list_type == 'all':
        ikb += compose_msg_on_all_last_searches_ikb(region, user_id, only_followed)
        logging.info('ikb += compose_msg_on_all_last_searches_ikb == ' + str(ikb))

        if len(ikb) > 0:
            msg = f'Посл. 20 поисков в {region_name}'
            ikb.insert(0, [{'text': msg, 'url': url}])
        else:
            msg = (
                'Не получается отобразить последние поиски в разделе '
                '<a href="https://lizaalert.org/forum/viewforum.php?f='
                + str(region)
                + '">'
                + region_name
                + '</a>, что-то пошло не так, простите. Напишите об этом разработчику '
                'в <a href="https://t.me/joinchat/2J-kV0GaCgwxY2Ni">Специальном Чате '
                'в телеграм</a>, пожалуйста.'
            )
            ikb = [[{'text': msg, 'url': url}]]

    # Combine the list of the latest active searches
    else:
        ikb += compose_msg_on_active_searches_in_one_reg_ikb(region, user_data, user_id)
        logging.info(f'ikb += compose_msg_on_active_searches_in_one_reg_ikb == {ikb}; ({region=})')

        if len(ikb) > 0:
            msg = f'Акт. поиски за 60 дней в {region_name}'
            ikb.insert(0, [{'text': msg, 'url': url}])
        else:
            msg = f'Нет акт. поисков за 60 дней в {region_name}'
            ikb = [[{'text': msg, 'url': url}]]

    return ikb


def search_button_row_ikb(search_following_mode, search_status, search_id, search_display_name, url):
    search_following_mark = search_following_mode if search_following_mode else '  '
    ikb_row = [
        [
            {
                'text': f'{search_following_mark} {search_status}',
                'callback_data': f'{{"action":"search_follow_mode", "hash":"{search_id}"}}',
            },  ##left button to on/off follow
            {'text': search_display_name, 'url': url},  ##right button - link to the search on the forum
        ]
    ]
    return ikb_row
