import datetime
import logging
from typing import Any, List, Optional, Tuple

from psycopg2.extensions import cursor

from _dependencies.commons import sql_connect_by_psycopg2
from communicate._utils.common import AgePeriod, SearchFollowingMode


class DBClient:
    def __init__(self):
        self._connection = sql_connect_by_psycopg2()

    def connect(self) -> cursor:
        # TODO rename to 'cursor'?
        return self._connection.cursor()

    def save_user_message_to_bot(self, user_id: int, got_message: str) -> None:
        # TODO example method! Just for testing now.
        """save user's message to bot in psql"""

        with self.connect() as cur:
            cur.execute(
                """INSERT INTO dialogs (user_id, author, timestamp, message_text) values (%s, %s, %s, %s);""",
                (user_id, 'user', datetime.datetime.now(), got_message),
            )


def delete_last_user_inline_dialogue(cur, user_id: int) -> None:
    """Delete form DB the user's last interaction via inline buttons"""

    cur.execute("""DELETE FROM communications_last_inline_msg WHERE user_id=%s;""", (user_id,))


def get_last_user_inline_dialogue(cur, user_id: int) -> list:
    """Get from DB the user's last interaction via inline buttons"""

    cur.execute("""SELECT message_id FROM communications_last_inline_msg WHERE user_id=%s;""", (user_id,))
    message_id_lines = cur.fetchall()

    message_id_list = []
    if message_id_lines and len(message_id_lines) > 0:
        for message_id_line in message_id_lines:
            message_id_list.append(message_id_line[0])

    return message_id_list


def save_last_user_inline_dialogue(cur, user_id: int, message_id: int) -> None:
    """Save to DB the user's last interaction via inline buttons"""

    cur.execute(
        """INSERT INTO communications_last_inline_msg 
                    (user_id, timestamp, message_id) values (%s, CURRENT_TIMESTAMP AT TIME ZONE 'UTC', %s)
                    ON CONFLICT (user_id, message_id) DO 
                    UPDATE SET timestamp=CURRENT_TIMESTAMP AT TIME ZONE 'UTC';""",
        (user_id, message_id),
    )


def get_search_follow_mode(cur, user_id: int):
    cur.execute("""SELECT filter_name FROM user_pref_search_filtering WHERE user_id=%s LIMIT 1;""", (user_id,))
    result_fetched = cur.fetchone()
    result = result_fetched and 'whitelist' in result_fetched[0]
    return result


def save_user_message_to_bot(cur: cursor, user_id: int, got_message: str) -> None:
    """save user's message to bot in psql"""

    cur.execute(
        """INSERT INTO dialogs (user_id, author, timestamp, message_text) values (%s, %s, %s, %s);""",
        (user_id, 'user', datetime.datetime.now(), got_message),
    )


def get_user_sys_roles(cur, user_id):
    """Return user's roles in system"""

    user_roles = ['']

    try:
        cur.execute('SELECT role FROM user_roles WHERE user_id=%s;', (user_id,))
        lines = cur.fetchall()
        for line in lines:
            user_roles.append(line[0])
        logging.info(f'user {user_id} role has roles {user_roles=}')
    except Exception as e:
        logging.info(f'failed to get from user_roles for user {user_id}')
        logging.exception(e)

    return user_roles


def get_user_role(cur: cursor, user_id: int):
    """Return user's role"""

    user_role = None

    try:
        cur.execute('SELECT role FROM users WHERE user_id=%s LIMIT 1;', (user_id,))
        user_role = cur.fetchone()
        if user_role:
            user_role = user_role[0]

        logging.info(f'user {user_id} role is {user_role}')

    except Exception as e:
        logging.info(f'failed to get user role for user {user_id}')
        logging.exception(e)

    return user_role


def add_user_sys_role(cur, user_id, sys_role_name):
    """Saves user's role in system"""

    try:
        cur.execute(
            """INSERT INTO user_roles (user_id, role) 
                    VALUES (%s, %s) ON CONFLICT DO NOTHING;""",
            (user_id, sys_role_name),
        )

    except Exception as e:
        logging.exception(f'failed to insert into user_roles for user {user_id}')


def delete_user_sys_role(cur, user_id, sys_role_name):
    """Deletes user's role in system"""

    try:
        cur.execute(
            """DELETE FROM user_roles 
                    WHERE user_id=%s and role=%s;""",
            (user_id, sys_role_name),
        )

    except Exception as e:
        logging.exception(f'failed to delete from user_roles for user {user_id}')


def delete_user_coordinates(cur: cursor, user_id: int) -> None:
    """Delete the saved user "home" coordinates"""

    cur.execute('DELETE FROM user_coordinates WHERE user_id=%s;', (user_id,))


def show_user_coordinates(cur: cursor, user_id: int) -> Tuple[str, str]:
    """Return the saved user "home" coordinates"""

    cur.execute("""SELECT latitude, longitude FROM user_coordinates WHERE user_id=%s LIMIT 1;""", (user_id,))

    try:
        lat, lon = list(cur.fetchone())
    except:  # noqa
        lat = None
        lon = None

    return lat, lon


def get_saved_user_coordinates(cur, user_id):
    cur.execute('SELECT latitude, longitude FROM user_coordinates WHERE user_id=%s LIMIT 1;', (user_id,))

    user_data = cur.fetchone()
    return user_data


def save_user_coordinates(cur: cursor, user_id: int, input_latitude: float, input_longitude: float) -> None:
    """Save / update user "home" coordinates"""

    cur.execute('DELETE FROM user_coordinates WHERE user_id=%s;', (user_id,))

    now = datetime.datetime.now()
    cur.execute(
        """INSERT INTO user_coordinates (user_id, latitude, longitude, upd_time) values (%s, %s, %s, %s);""",
        (user_id, input_latitude, input_longitude, now),
    )


def check_if_user_has_no_regions(cur, user_id):
    """check if the user has at least one region"""

    cur.execute("""SELECT user_id FROM user_regional_preferences WHERE user_id=%s LIMIT 1;""", (user_id,))

    info_on_user_from_users = str(cur.fetchone())

    if info_on_user_from_users == 'None':
        no_regions = True
    else:
        no_regions = False

    return no_regions


def save_user_pref_role(cur, user_id, role_desc):
    """save user role"""

    role_dict = {
        'я состою в ЛизаАлерт': 'member',
        'я хочу помогать ЛизаАлерт': 'new_member',
        'я ищу человека': 'relative',
        'у меня другая задача': 'other',
        'не хочу говорить': 'no_answer',
    }

    try:
        role = role_dict[role_desc]
    except:  # noqa
        role = 'unidentified'

    cur.execute("""UPDATE users SET role=%s where user_id=%s;""", (role, user_id))

    logging.info(f'[comm]: user {user_id} selected role {role}')

    return role


def save_user_pref_topic_type(cur, user_id, pref_id, user_role) -> None:
    def save(pref_type_id):
        cur.execute(
            """INSERT INTO user_pref_topic_type (user_id, topic_type_id, timestamp) 
                                            values (%s, %s, %s) ON CONFLICT (user_id, topic_type_id) DO NOTHING;""",
            (user_id, pref_type_id, datetime.datetime.now()),
        )
        return

    if not (cur and user_id and pref_id):
        return

    if pref_id == 'default':
        if user_role in {'member', 'new_member'}:
            default_topic_type_id = [0, 3, 4, 5]  # 0=regular, 3=training, 4=info_support, 5=resonance
        else:
            default_topic_type_id = [0, 4, 5]  # 0=regular, 4=info_support, 5=resonance

        for type_id in default_topic_type_id:
            save(type_id)

    else:
        save(pref_id)


def get_user_regions_from_db(cur, user_id):
    cur.execute("""SELECT forum_folder_num from user_regional_preferences WHERE user_id=%s;""", (user_id,))

    user_curr_regs_temp = cur.fetchall()
    user_curr_regs = [reg[0] for reg in user_curr_regs_temp]
    return user_curr_regs


def get_geo_folders_db(cur):
    cur.execute(
        """
                    SELECT folder_id, folder_display_name FROM geo_folders_view WHERE folder_type='searches';
                    """
    )

    folders_list = cur.fetchall()
    return folders_list


def check_if_new_user(cur: cursor, user_id: int) -> bool:
    """check if the user is new or not"""

    cur.execute("""SELECT user_id FROM users WHERE user_id=%s LIMIT 1;""", (user_id,))

    info_on_user_from_users = str(cur.fetchone())

    if info_on_user_from_users == 'None':
        user_is_new = True
    else:
        user_is_new = False

    return user_is_new


def save_user_pref_urgency(
    cur, user_id, urgency_value, b_pref_urgency_highest, b_pref_urgency_high, b_pref_urgency_medium, b_pref_urgency_low
):
    """save user urgency"""

    urgency_dict = {
        b_pref_urgency_highest: {'pref_id': 0, 'pref_name': 'highest'},
        b_pref_urgency_high: {'pref_id': 1, 'pref_name': 'high'},
        b_pref_urgency_medium: {'pref_id': 2, 'pref_name': 'medium'},
        b_pref_urgency_low: {'pref_id': 3, 'pref_name': 'low'},
    }

    try:
        pref_id = urgency_dict[urgency_value]['pref_id']
        pref_name = urgency_dict[urgency_value]['pref_name']
    except:  # noqa
        pref_id = 99
        pref_name = 'unidentified'

    cur.execute("""DELETE FROM user_pref_urgency WHERE user_id=%s;""", (user_id,))
    cur.execute(
        """INSERT INTO user_pref_urgency (user_id, pref_id, pref_name, timestamp) VALUES (%s, %s, %s, %s);""",
        (user_id, pref_id, pref_name, datetime.datetime.now()),
    )

    logging.info(f'urgency set as {pref_name} for user_id {user_id}')


def get_user_reg_folders_preferences(cur: cursor, user_id: int) -> List[int]:
    """Return user's regional preferences"""

    user_prefs_list = []

    try:
        cur.execute('SELECT forum_folder_num FROM user_regional_preferences WHERE user_id=%s;', (user_id,))
        user_reg_prefs_array = cur.fetchall()

        for line in user_reg_prefs_array:
            user_prefs_list.append(line[0])

        logging.info(str(user_prefs_list))

    except Exception as e:
        logging.info(f'failed to get user regional prefs for user {user_id}')
        logging.exception(e)

    return user_prefs_list


def save_preference(cur: cursor, user_id: int, preference: str):
    """Save user preference on types of notifications to be sent by bot"""

    # the master-table is dict_notif_types:

    pref_dict = {
        'topic_new': 0,
        'topic_status_change': 1,
        'topic_title_change': 2,
        'topic_comment_new': 3,
        'topic_inforg_comment_new': 4,
        'topic_field_trip_new': 5,
        'topic_field_trip_change': 6,
        'topic_coords_change': 7,
        'topic_first_post_change': 8,
        'topic_all_in_followed_search': 9,
        'bot_news': 20,
        'all': 30,
        'not_defined': 99,
        'new_searches': 0,
        'status_changes': 1,
        'title_changes': 2,
        'comments_changes': 3,
        'inforg_comments': 4,
        'field_trips_new': 5,
        'field_trips_change': 6,
        'coords_change': 7,
        'first_post_changes': 8,
        'all_in_followed_search': 9,
    }

    def execute_insert(user: int, preference_name: str):
        """execute SQL INSERT command"""

        preference_id = pref_dict[preference_name]
        cur.execute(
            """INSERT INTO user_preferences 
                        (user_id, preference, pref_id) 
                        VALUES (%s, %s, %s) 
                        ON CONFLICT DO NOTHING;""",
            (user, preference_name, preference_id),
        )

    def execute_delete(user: int, list_of_prefs: List[str]):
        """execute SQL DELETE command"""

        if list_of_prefs:
            for line in list_of_prefs:
                line_id = pref_dict[line]
                cur.execute("""DELETE FROM user_preferences WHERE user_id=%s AND pref_id=%s;""", (user, line_id))
        else:
            cur.execute("""DELETE FROM user_preferences WHERE user_id=%s;""", (user,))

    def execute_check(user, pref_list):
        """execute SQL SELECT command and returns TRUE / FALSE if something found"""

        result = False

        for line in pref_list:
            cur.execute("""SELECT id FROM user_preferences WHERE user_id=%s AND preference=%s LIMIT 1;""", (user, line))

            if str(cur.fetchone()) != 'None':
                result = True
                break

        return result

    if preference == 'all':
        execute_delete(user_id, [])
        execute_insert(user_id, preference)

    elif preference in {
        'new_searches',
        'status_changes',
        'title_changes',
        'comments_changes',
        'first_post_changes',
        'all_in_followed_search',
    }:
        if execute_check(user_id, ['all']):
            execute_insert(user_id, 'bot_news')
        execute_delete(user_id, ['all'])

        execute_insert(user_id, preference)

        if preference == 'comments_changes':
            execute_delete(user_id, ['inforg_comments'])

    elif preference == 'inforg_comments':
        if not execute_check(user_id, ['all', 'comments_changes']):
            execute_insert(user_id, preference)

    elif preference in {'field_trips_new', 'field_trips_change', 'coords_change'}:
        # FIXME – temp deactivation unlit feature will be ready for prod
        # FIXME – to be added to "new_searches" etc group
        # if not execute_check(user_id, ['all']):
        execute_insert(user_id, preference)

    elif preference in {
        '-new_searches',
        '-status_changes',
        '-comments_changes',
        '-inforg_comments',
        '-title_changes',
        '-all',
        '-field_trips_new',
        '-field_trips_change',
        '-coords_change',
        '-first_post_changes',
        '-all_in_followed_search',
    }:
        if preference == '-all':
            execute_insert(user_id, 'bot_news')
            execute_insert(user_id, 'new_searches')
            execute_insert(user_id, 'status_changes')
            execute_insert(user_id, 'inforg_comments')
            execute_insert(user_id, 'first_post_changes')
        elif preference == '-comments_changes':
            execute_insert(user_id, 'inforg_comments')

        preference = preference[1:]
        execute_delete(user_id, [preference])


def get_last_bot_msg(cur: cursor, user_id: int) -> str:
    """Get the last bot message to user to define if user is expected to give exact answer"""

    cur.execute(
        """
        SELECT msg_type FROM msg_from_bot WHERE user_id=%s LIMIT 1;
        """,
        (user_id,),
    )

    extract = cur.fetchone()
    logging.info('get the last bot message to user to define if user is expected to give exact answer')
    logging.info(str(extract))

    if extract and extract != 'None':
        msg_type = extract[0]
    else:
        msg_type = None

    if msg_type:
        logging.info(f'before this message bot was waiting for {msg_type} from user {user_id}')
    else:
        logging.info(f'before this message bot was NOT waiting anything from user {user_id}')

    return msg_type


def get_user_forum_attributes_db(cur, user_id):
    cur.execute(
        """SELECT forum_username, forum_user_id 
                       FROM user_forum_attributes 
                       WHERE status='verified' AND user_id=%s 
                       ORDER BY timestamp DESC 
                       LIMIT 1;""",
        (user_id,),
    )
    saved_forum_user = cur.fetchone()
    return saved_forum_user


def write_user_forum_attributes_db(cur, user_id):
    cur.execute(
        """UPDATE user_forum_attributes SET status='verified'
                WHERE user_id=%s and timestamp =
                (SELECT MAX(timestamp) FROM user_forum_attributes WHERE user_id=%s);""",
        (user_id, user_id),
    )


def check_onboarding_step(cur: cursor, user_id: int, user_is_new: bool) -> Tuple[int, str]:
    """checks the latest step of onboarding"""

    if user_is_new:
        return 0, 'start'

    try:
        cur.execute(
            """SELECT step_id, step_name, timestamp FROM user_onboarding 
                               WHERE user_id=%s ORDER BY step_id DESC;""",
            (user_id,),
        )
        raw_data = cur.fetchone()
        if raw_data:
            step_id, step_name, time = list(raw_data)
        else:
            step_id, step_name = 99, None

    except Exception as e:
        logging.exception(e)
        step_id, step_name = 99, None

    return step_id, step_name


def save_bot_reply_to_user(cur: cursor, user_id: int, bot_message: str) -> None:
    """save bot's reply to user in psql"""

    if len(bot_message) > 27 and bot_message[28] in {'Актуальные поиски за 60 дней', 'Последние 20 поисков в разде'}:
        bot_message = bot_message[28]

    cur.execute(
        """INSERT INTO dialogs (user_id, author, timestamp, message_text) values (%s, %s, %s, %s);""",
        (user_id, 'bot', datetime.datetime.now(), bot_message),
    )


def save_last_user_message_in_db(cur, user_id, message_type):
    # TODO the same in connect_to_forum
    cur.execute("""DELETE FROM msg_from_bot WHERE user_id=%s;""", (user_id,))

    cur.execute(
        """INSERT INTO msg_from_bot (user_id, time, msg_type) values (%s, %s, %s);""",
        (user_id, datetime.datetime.now(), message_type),
    )


def set_search_follow_mode(cur: cursor, user_id: int, new_value: bool) -> None:
    filter_name_value = ['whitelist'] if new_value else ['']
    logging.info(f'{filter_name_value=}')
    cur.execute(
        """INSERT INTO user_pref_search_filtering (user_id, filter_name) values (%s, %s)
                    ON CONFLICT (user_id) DO UPDATE SET filter_name=%s;""",
        (user_id, filter_name_value, filter_name_value),
    )


def delete_folder_from_user_regional_preference(cur, user_id, region):
    cur.execute(
        """DELETE FROM user_regional_preferences WHERE user_id=%s and forum_folder_num=%s;""",
        (user_id, region),
    )


def get_folders_with_followed_searches(cur, user_id):
    cur.execute(
        """SELECT DISTINCT s.forum_folder_id 
                            FROM searches s 
                            INNER JOIN user_pref_search_whitelist upswl 
                                ON upswl.search_id=s.search_forum_num
                                AND upswl.user_id=%(user_id)s
                                AND upswl.search_following_mode=%(search_follow_on)s
                        ;""",
        {'user_id': user_id, 'search_follow_on': SearchFollowingMode.ON},
    )
    lines = cur.fetchall()
    return lines


def add_folder_to_user_regional_preference(cur, user_id, region):
    cur.execute(
        """INSERT INTO user_regional_preferences (user_id, forum_folder_num) values (%s, %s);""",
        (user_id, region),
    )


def get_user_regions(cur, user_id):
    cur.execute("""SELECT forum_folder_num from user_regional_preferences WHERE user_id=%s;""", (user_id,))

    user_curr_regs = cur.fetchall()
    user_curr_regs_list = [reg[0] for reg in user_curr_regs]
    return user_curr_regs_list


def check_saved_radius(cur, user: int) -> Optional[Any]:
    """check if user already has a radius preference"""

    saved_rad = None
    cur.execute("""SELECT radius FROM user_pref_radius WHERE user_id=%s;""", (user,))
    raw_radius = cur.fetchone()
    if raw_radius and str(raw_radius) != 'None':
        saved_rad = int(raw_radius[0])
    return saved_rad


def delete_user_saved_radius(cur, user_id):
    cur.execute("""DELETE FROM user_pref_radius WHERE user_id=%s;""", (user_id,))


def save_user_radius(cur, user_id, number):
    cur.execute(
        """INSERT INTO user_pref_radius (user_id, radius) 
                               VALUES (%s, %s) ON CONFLICT (user_id) DO
                               UPDATE SET radius=%s;""",
        (user_id, number, number),
    )


def delete_user_saved_topic_type(cur, user: int, type_id: int) -> None:
    """Delete a certain topic_type for a certain user_id from the DB"""

    cur.execute("""DELETE FROM user_pref_topic_type WHERE user_id=%s AND topic_type_id=%s;""", (user, type_id))


def record_topic_type(cur, user: int, type_id: int) -> None:
    """Insert a certain topic_type for a certain user_id into the DB"""

    cur.execute(
        """INSERT INTO user_pref_topic_type (user_id, topic_type_id, timestamp) 
                    VALUES (%s, %s, %s) ON CONFLICT (user_id, topic_type_id) DO NOTHING;""",
        (user, type_id, datetime.datetime.now()),
    )


def check_saved_topic_types(cur, user: int) -> list:
    """check if user already has any preference"""

    saved_pref = []
    cur.execute("""SELECT topic_type_id FROM user_pref_topic_type WHERE user_id=%s ORDER BY 1;""", (user,))
    raw_data = cur.fetchall()
    if raw_data and str(raw_data) != 'None':
        for line in raw_data:
            saved_pref.append(line[0])

    logging.info(f'{saved_pref=}')

    return saved_pref


def record_search_whiteness(cur, user: int, search_id: int, new_mark_value) -> None:
    """Save a certain user_pref_search_whitelist for a certain user_id into the DB"""
    if new_mark_value in [SearchFollowingMode.ON, SearchFollowingMode.OFF]:
        cur.execute(
            """INSERT INTO user_pref_search_whitelist (user_id, search_id, timestamp, search_following_mode) 
                        VALUES (%s, %s, %s, %s) ON CONFLICT (user_id, search_id) DO UPDATE SET timestamp=%s, search_following_mode=%s;""",
            (user, search_id, datetime.datetime.now(), new_mark_value, datetime.datetime.now(), new_mark_value),
        )
    else:
        cur.execute(
            """DELETE FROM user_pref_search_whitelist WHERE user_id=%(user)s and search_id=%(search_id)s;""",
            {'user': user, 'search_id': search_id},
        )


def add_region_to_user_settings(cur, user_id, region_id):
    cur.execute(
        """INSERT INTO user_pref_region (user_id, region_id) values
                (%s, %s);""",
        (user_id, region_id),
    )


def save_user_age_prefs(cur, user_id, chosen_setting: AgePeriod):
    cur.execute(
        """INSERT INTO user_pref_age (user_id, period_name, period_set_date, period_min, period_max) 
                        values (%s, %s, %s, %s, %s) ON CONFLICT (user_id, period_min, period_max) DO NOTHING;""",
        (user_id, chosen_setting.name, datetime.datetime.now(), chosen_setting.min_age, chosen_setting.max_age),
    )


def delete_user_age_pref(cur, user_id, chosen_setting: AgePeriod) -> None:
    cur.execute(
        """DELETE FROM user_pref_age WHERE user_id=%s AND period_min=%s AND period_max=%s;""",
        (user_id, chosen_setting.min_age, chosen_setting.max_age),
    )


def get_age_prefs(cur, user_id):
    cur.execute("""SELECT period_min, period_max FROM user_pref_age WHERE user_id=%s;""", (user_id,))
    raw_list_of_periods = cur.fetchall()
    return raw_list_of_periods


def get_existing_user_settings(cur, user_id):
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
    return raw_data


def get_all_user_preferences(cur, user_id):
    cur.execute("""SELECT preference FROM user_preferences WHERE user_id=%s ORDER BY preference;""", (user_id,))
    user_prefs = cur.fetchall()
    return user_prefs


def get_all_active_searches_in_one_region_2(cur, region, user_id):
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
    return searches_list


def get_all_searches_in_one_region(cur, region):
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
    return database


def get_all_last_searches_in_region(cur, region, user_id, only_followed):
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
    return database


def get_active_searches_in_one_region(cur, region):
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
    return searches_list
