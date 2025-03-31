import logging
from dataclasses import dataclass
from typing import Any, List, Tuple, Union

from psycopg2.extensions import cursor

from _dependencies.misc import age_writer, time_counter_since_search_start
from communicate._utils.common import SearchFollowingMode, distance_to_search


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


def compose_msg_on_user_setting_fullness(cur, user_id: int) -> Union[str, None]:
    """Create a text of message, which describes the degree on how complete user's profile is.
    More settings set – more complete profile it. It's done to motivate users to set the most tailored settings."""

    if not cur or not user_id:
        return None

    try:
        cur.execute(
            """SELECT
                            user_id 
                            , CASE WHEN role IS NOT NULL THEN TRUE ELSE FALSE END as role 
                            , CASE WHEN (SELECT TRUE FROM user_pref_age WHERE user_id=%s LIMIT 1) 
                                THEN TRUE ELSE FALSE END AS age
                            , CASE WHEN (SELECT TRUE FROM user_coordinates WHERE user_id=%s LIMIT 1) 
                                THEN TRUE ELSE FALSE END AS coords    
                            , CASE WHEN (SELECT TRUE FROM user_pref_radius WHERE user_id=%s LIMIT 1) 
                                THEN TRUE ELSE FALSE END AS radius
                            , CASE WHEN (SELECT TRUE FROM user_pref_region WHERE user_id=%s LIMIT 1) 
                                THEN TRUE ELSE FALSE END AS region
                            , CASE WHEN (SELECT TRUE FROM user_pref_topic_type WHERE user_id=%s LIMIT 1) 
                                THEN TRUE ELSE FALSE END AS topic_type
                            , CASE WHEN (SELECT TRUE FROM user_pref_urgency WHERE user_id=%s LIMIT 1) 
                                THEN TRUE ELSE FALSE END AS urgency
                            , CASE WHEN (SELECT TRUE FROM user_preferences WHERE user_id=%s 
                                AND preference!='bot_news' LIMIT 1) 
                                THEN TRUE ELSE FALSE END AS notif_type
                            , CASE WHEN (SELECT TRUE FROM user_regional_preferences WHERE user_id=%s LIMIT 1) 
                                THEN TRUE ELSE FALSE END AS region_old
                            , CASE WHEN (SELECT TRUE FROM user_forum_attributes WHERE user_id=%s
                                AND status = 'verified' LIMIT 1) 
                                THEN TRUE ELSE FALSE END AS forum
                        FROM users WHERE user_id=%s;
                        """,
            (
                user_id,
                user_id,
                user_id,
                user_id,
                user_id,
                user_id,
                user_id,
                user_id,
                user_id,
                user_id,
            ),
        )

        raw_data = cur.fetchone()

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
        logging.info('Exception in "compose_msg_on_user_setting_fullness" function')
        logging.exception(e)
        return None


def compose_user_preferences_message(cur: cursor, user_id: int) -> List[Union[List[str], str]]:
    """Compose a text for user on which types of notifications are enabled for zir"""

    cur.execute("""SELECT preference FROM user_preferences WHERE user_id=%s ORDER BY preference;""", (user_id,))
    user_prefs = cur.fetchall()

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


def compose_msg_on_all_last_searches(cur: cursor, region: int) -> str:
    """Compose a part of message on the list of recent searches"""

    pre_url = 'https://lizaalert.org/forum/viewtopic.php?t='
    text = ''

    # download the list from SEARCHES sql table
    cur.execute(
        """SELECT s2.* FROM 
            (SELECT search_forum_num, search_start_time, display_name, status, status, family_name, age 
            FROM searches 
            WHERE forum_folder_id=%s 
            ORDER BY search_start_time DESC 
            LIMIT 20) s2 
        LEFT JOIN search_health_check shc 
        ON s2.search_forum_num=shc.search_forum_num 
        WHERE (shc.status is NULL or shc.status='ok' or shc.status='regular') 
        ORDER BY s2.search_start_time DESC;""",
        (region,),
    )

    database = cur.fetchall()

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


def compose_msg_on_all_last_searches_ikb(cur: cursor, region: int, user_id: int, only_followed: bool) -> List:
    """Compose a part of message on the list of recent searches"""
    # issue#425 it is ikb variant of the above function, returns data formated for inline keyboard
    # 1st element of returned list is general info and should be popped
    # rest elements are searches to be showed as inline buttons
    # 24.03.2025: followed in whitelist searches to be showed regardless of region settings and the 60-days expiration, even in 'СТОП'

    pre_url = 'https://lizaalert.org/forum/viewtopic.php?t='
    ikb = []

    sql_text = """
        SELECT DISTINCT search_forum_num, search_start_time, display_name, status, status, family_name, age, search_following_mode
        FROM(   -- q
                SELECT s21.*, upswl.search_following_mode FROM 
                    (SELECT search_forum_num, search_start_time, display_name, s01.status as new_status, s01.status, family_name, age 
                    FROM searches s01
                    WHERE forum_folder_id=%(region)s 
                    ) s21 
                INNER JOIN user_pref_search_whitelist upswl 
                    ON upswl.search_id=s21.search_forum_num and upswl.user_id=%(user_id)s
                        and upswl.search_following_mode=%(search_follow_on)s 
                """
    if not only_followed:
        sql_text += """
            UNION
                SELECT s2.*, upswl.search_following_mode FROM 
                    (SELECT search_forum_num, search_start_time, display_name, s00.status as new_status, s00.status, family_name, age 
                    FROM searches s00
                    WHERE forum_folder_id=%(region)s 
                    ORDER BY search_start_time DESC 
                    LIMIT 20) s2 
                LEFT JOIN search_health_check shc ON s2.search_forum_num=shc.search_forum_num
                LEFT JOIN user_pref_search_whitelist upswl ON upswl.search_id=s2.search_forum_num and upswl.user_id=%(user_id)s
                WHERE (shc.status is NULL or shc.status='ok' or shc.status='regular') 
            """
    sql_text += """
            )q
        ORDER BY search_start_time DESC
        LIMIT 20
        ;"""

    cur.execute(
        sql_text,
        {'region': region, 'user_id': user_id, 'search_follow_on': SearchFollowingMode.ON},
    )

    database = cur.fetchall()

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


def compose_msg_on_active_searches_in_one_reg(cur: cursor, region: int, user_data) -> str:
    """Compose a part of message on the list of active searches in the given region with relation to user's coords"""

    pre_url = 'https://lizaalert.org/forum/viewtopic.php?t='
    text = ''

    cur.execute(
        """SELECT s2.* FROM 
            (SELECT s.search_forum_num, s.search_start_time, s.display_name, sa.latitude, sa.longitude, 
            s.topic_type, s.family_name, s.age 
            FROM searches s 
            LEFT JOIN search_coordinates sa ON s.search_forum_num = sa.search_id 
            WHERE (s.status='Ищем' OR s.status='Возобновлен') 
                AND s.forum_folder_id=%s ORDER BY s.search_start_time DESC) s2 
        LEFT JOIN search_health_check shc ON s2.search_forum_num=shc.search_forum_num
        WHERE (shc.status is NULL or shc.status='ok' or shc.status='regular') 
        ORDER BY s2.search_start_time DESC;""",
        (region,),
    )
    searches_list = cur.fetchall()

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
            dist = distance_to_search(search_lat, search_lon, user_lat, user_lon)
            dist_and_dir = f' {dist[1]} {dist[0]} км'
        else:
            dist_and_dir = ''

        if not search.display_name:
            age_string = f' {age_writer(search.age)}' if search.age != 0 else ''
            search.display_name = f'{search.name}{age_string}'

        text += f'{time_since_start}{dist_and_dir} <a href="{pre_url}{search.topic_id}">{search.display_name}</a>\n'

    return text


def compose_msg_on_active_searches_in_one_reg_ikb(
    cur: cursor, region: int, user_data: Tuple[str, str], user_id: int
) -> List:
    """Compose a part of message on the list of active searches in the given region with relation to user's coords"""
    # issue#425 it is ikb variant of the above function, returns data formated for inline keyboard
    # 1st element of returned list is general info and should be popped
    # rest elements are searches to be showed as inline buttons
    # 24.03.2025: followed in whitelist searches to be showed regardless of region settings and the 60-days expiration, even in 'СТОП'

    pre_url = 'https://lizaalert.org/forum/viewtopic.php?t='
    ikb = []

    sql_text = """
        SELECT s.search_forum_num, s.search_start_time, s.display_name, sa.latitude, sa.longitude, 
        s.topic_type, s.family_name, s.age, upswl.search_following_mode
        FROM searches s 
        LEFT JOIN search_coordinates sa ON s.search_forum_num = sa.search_id 
        LEFT JOIN search_health_check shc ON s.search_forum_num=shc.search_forum_num
        LEFT JOIN user_pref_search_whitelist upswl ON upswl.search_id=s.search_forum_num and upswl.user_id=%(user_id)s
        WHERE s.forum_folder_id=%(region)s
        AND (
                (s.status='Ищем' OR s.status='Возобновлен'
                and (shc.status is NULL or shc.status='ok' or shc.status='regular')
                )
            or (upswl.search_following_mode=%(search_follow_on)s
                and s.status in('Ищем', 'Возобновлен', 'СТОП')
                )
            )
        ORDER BY s.search_start_time DESC
        LIMIT 20;"""

    cur.execute(
        sql_text,
        {
            'region': region,
            'user_id': user_id,
            'search_follow_on': SearchFollowingMode.ON,
        },
    )
    searches_list = cur.fetchall()

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
            dist = distance_to_search(search_lat, search_lon, user_lat, user_lon, False)
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


def compose_full_message_on_list_of_searches(
    cur: cursor, list_type: str, user_id: int, region: int, region_name: str
) -> str:
    """Compose a Final message on the list of searches in the given region"""

    msg = ''

    cur.execute('SELECT latitude, longitude FROM user_coordinates WHERE user_id=%s LIMIT 1;', (user_id,))

    user_data = cur.fetchone()

    # combine the list of last 20 searches
    if list_type == 'all':
        msg += compose_msg_on_all_last_searches(cur, region)

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
        msg += compose_msg_on_active_searches_in_one_reg(cur, region, user_data)

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
    cur: cursor, list_type: str, user_id: int, region: int, region_name: str, only_followed: bool
):  # issue#425
    """Compose a Final message on the list of searches in the given region"""
    # issue#425 This variant of the above function returns data in format used to compose inline keyboard
    # 1st element is caption
    # rest elements are searches in format to be showed as inline buttons

    ikb = []

    cur.execute('SELECT latitude, longitude FROM user_coordinates WHERE user_id=%s LIMIT 1;', (user_id,))

    user_data = cur.fetchone()

    url = f'https://lizaalert.org/forum/viewforum.php?f={region}'
    # combine the list of last 20 searches
    if list_type == 'all':
        ikb += compose_msg_on_all_last_searches_ikb(cur, region, user_id, only_followed)
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
        ikb += compose_msg_on_active_searches_in_one_reg_ikb(cur, region, user_data, user_id)
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
