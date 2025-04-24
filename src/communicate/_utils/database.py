import datetime
import logging
from contextlib import contextmanager, suppress
from dataclasses import dataclass
from functools import lru_cache
from typing import Generator, List

from psycopg2.extensions import connection, cursor

from _dependencies.commons import SearchFollowingMode, sql_connect_by_psycopg2

from .common import PREF_DICT, AgePeriod, SearchSummary, UserInputState


@dataclass
class UserSettingsSummary:
    user_id: int
    pref_role: bool
    pref_age: bool
    pref_coords: bool
    pref_radius: bool
    pref_region: bool
    pref_topic_type: bool
    pref_urgency: bool
    pref_notif_type: bool
    pref_region_old: bool
    pref_forum: bool


@lru_cache
def db() -> 'DBClient':
    return DBClient()


class DBClient:
    _connection: connection

    @contextmanager
    def connect(self) -> Generator:
        self._connection = sql_connect_by_psycopg2()
        try:
            yield
        finally:
            with suppress(Exception):
                self._connection.close()

    def cursor(self) -> cursor:
        return self._connection.cursor()

    def save_user_message_to_bot(self, user_id: int, got_message: str) -> None:
        """save user's message to bot in psql"""

        with self.cursor() as cur:
            cur.execute(
                """INSERT INTO dialogs (user_id, author, timestamp, message_text) values (%s, %s, %s, %s);""",
                (user_id, 'user', datetime.datetime.now(), got_message),
            )

    def delete_last_user_inline_dialogue(self, user_id: int) -> None:
        """Delete form DB the user's last interaction via inline buttons"""

        with self.cursor() as cur:
            cur.execute("""DELETE FROM communications_last_inline_msg WHERE user_id=%s;""", (user_id,))

    def get_last_user_inline_dialogue(self, user_id: int) -> list[int]:
        """Get from DB the user's last interaction via inline buttons"""

        with self.cursor() as cur:
            cur.execute("""SELECT message_id FROM communications_last_inline_msg WHERE user_id=%s;""", (user_id,))
            message_id_lines = cur.fetchall()

            message_id_list = []
            if message_id_lines and len(message_id_lines) > 0:
                for message_id_line in message_id_lines:
                    message_id_list.append(message_id_line[0])

            return message_id_list

    def save_last_user_inline_dialogue(self, user_id: int, message_id: int) -> None:
        """Save to DB the user's last interaction via inline buttons"""
        with self.cursor() as cur:
            cur.execute(
                """INSERT INTO communications_last_inline_msg 
                            (user_id, timestamp, message_id) values (%s, CURRENT_TIMESTAMP AT TIME ZONE 'UTC', %s)
                            ON CONFLICT (user_id, message_id) DO 
                            UPDATE SET timestamp=CURRENT_TIMESTAMP AT TIME ZONE 'UTC';""",
                (user_id, message_id),
            )

    def get_search_follow_mode(self, user_id: int) -> bool:
        with self.cursor() as cur:
            cur.execute("""SELECT filter_name FROM user_pref_search_filtering WHERE user_id=%s LIMIT 1;""", (user_id,))
            result_fetched = cur.fetchone()
            result = result_fetched is not None and ('whitelist' in result_fetched[0])
            return result

    def get_user_sys_roles(self, user_id: int) -> list[str]:
        """Return user's roles in system"""
        with self.cursor() as cur:
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

    def get_user_role(self, user_id: int) -> str | None:
        """Return user's role"""
        with self.cursor() as cur:
            try:
                cur.execute('SELECT role FROM users WHERE user_id=%s LIMIT 1;', (user_id,))
                rows = cur.fetchone()
                if rows:
                    user_role = rows[0]
                logging.info(f'user {user_id} role is {user_role}')
                return user_role
            except Exception:
                logging.exception(f'failed to get user role for user {user_id}')
            return None

    def add_user_sys_role(self, user_id: int, sys_role_name: str) -> None:
        """Saves user's role in system"""
        with self.cursor() as cur:
            cur.execute(
                """INSERT INTO user_roles (user_id, role) 
                        VALUES (%s, %s) ON CONFLICT DO NOTHING;""",
                (user_id, sys_role_name),
            )

    def delete_user_sys_role(self, user_id: int, sys_role_name: str) -> None:
        """Deletes user's role in system"""
        with self.cursor() as cur:
            cur.execute(
                """DELETE FROM user_roles 
                        WHERE user_id=%s and role=%s;""",
                (user_id, sys_role_name),
            )

    def delete_user_coordinates(self, user_id: int) -> None:
        """Delete the saved user "home" coordinates"""
        with self.cursor() as cur:
            cur.execute('DELETE FROM user_coordinates WHERE user_id=%s;', (user_id,))

    def get_user_coordinates_or_none(self, user_id: int) -> tuple[str, str] | tuple[None, None]:
        """Return the saved user "home" coordinates or None,None"""
        saved_coords = self.get_saved_user_coordinates(user_id)
        return saved_coords or (None, None)

    def get_saved_user_coordinates(self, user_id: int) -> tuple[str, str] | None:
        with self.cursor() as cur:
            cur.execute('SELECT latitude, longitude FROM user_coordinates WHERE user_id=%s LIMIT 1;', (user_id,))

            user_data = cur.fetchone()
            return user_data

    def save_user_coordinates(self, user_id: int, input_latitude: float, input_longitude: float) -> None:
        """Save / update user "home" coordinates"""

        with self.cursor() as cur:
            cur.execute('DELETE FROM user_coordinates WHERE user_id=%s;', (user_id,))

            now = datetime.datetime.now()
            cur.execute(
                """INSERT INTO user_coordinates (user_id, latitude, longitude, upd_time) values (%s, %s, %s, %s);""",
                (user_id, input_latitude, input_longitude, now),
            )

    def check_if_user_has_no_regions(self, user_id: int) -> bool:
        """check if the user has at least one region"""

        with self.cursor() as cur:
            cur.execute("""SELECT user_id FROM user_regional_preferences WHERE user_id=%s LIMIT 1;""", (user_id,))

            info_on_user_from_users = str(cur.fetchone())

            return info_on_user_from_users == 'None'

    def save_user_pref_role(self, user_id: int, role_desc: str) -> str:
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

        with self.cursor() as cur:
            cur.execute("""UPDATE users SET role=%s where user_id=%s;""", (role, user_id))

            logging.info(f'[comm]: user {user_id} selected role {role}')

            return role

    def _save_user_pref_topic_type(self, user_id: int, pref_type_id: int) -> None:
        with self.cursor() as cur:
            cur.execute(
                """INSERT INTO user_pref_topic_type (user_id, topic_type_id, timestamp) 
                                                        values (%s, %s, %s) ON CONFLICT (user_id, topic_type_id) DO NOTHING;""",
                (user_id, pref_type_id, datetime.datetime.now()),
            )
            return

    def save_user_pref_topic_type(self, user_id: int, user_role: str | None) -> None:
        if not user_id:
            return

        if user_role in {'member', 'new_member'}:
            default_topic_type_id = [0, 3, 4, 5]  # 0=regular, 3=training, 4=info_support, 5=resonance
        else:
            default_topic_type_id = [0, 4, 5]  # 0=regular, 4=info_support, 5=resonance

        for type_id in default_topic_type_id:
            self._save_user_pref_topic_type(user_id, type_id)

    def get_user_regions_from_db(self, user_id: int) -> list[int]:
        with self.cursor() as cur:
            cur.execute("""SELECT forum_folder_num from user_regional_preferences WHERE user_id=%s;""", (user_id,))

            user_curr_regs_temp = cur.fetchall()
            return [reg[0] for reg in user_curr_regs_temp]

    def get_geo_folders_db(self) -> list[tuple[int, str]]:
        with self.cursor() as cur:
            cur.execute(
                """
                   SELECT folder_id, folder_display_name FROM geo_folders_view WHERE folder_type='searches';
                   """
            )

            folders_list = cur.fetchall()
            return folders_list

    def check_if_new_user(self, user_id: int) -> bool:
        """check if the user is new or not"""
        with self.cursor() as cur:
            cur.execute("""SELECT user_id FROM users WHERE user_id=%s LIMIT 1;""", (user_id,))

            info_on_user_from_users = str(cur.fetchone())

            if info_on_user_from_users == 'None':
                user_is_new = True
            else:
                user_is_new = False

            return user_is_new

    def get_user_reg_folders_preferences(self, user_id: int) -> list[int]:
        """Return user's regional preferences"""

        user_prefs_list = []

        with self.cursor() as cur:
            cur.execute('SELECT forum_folder_num FROM user_regional_preferences WHERE user_id=%s;', (user_id,))
            user_reg_prefs_array = cur.fetchall()

        for line in user_reg_prefs_array:
            user_prefs_list.append(line[0])

        logging.info(str(user_prefs_list))

        return user_prefs_list

    def user_preference_save(self, user: int, preference_name: str) -> None:
        """execute SQL INSERT command"""

        preference_id = PREF_DICT[preference_name]
        with self.cursor() as cur:
            cur.execute(
                """INSERT INTO user_preferences 
                            (user_id, preference, pref_id) 
                            VALUES (%s, %s, %s) 
                            ON CONFLICT DO NOTHING;""",
                (user, preference_name, preference_id),
            )

    def user_preference_delete(self, user: int, list_of_prefs: List[str]) -> None:
        """execute SQL DELETE command"""

        with self.cursor() as cur:
            if list_of_prefs:
                for line in list_of_prefs:
                    line_id = PREF_DICT[line]
                    cur.execute("""DELETE FROM user_preferences WHERE user_id=%s AND pref_id=%s;""", (user, line_id))
            else:
                cur.execute("""DELETE FROM user_preferences WHERE user_id=%s;""", (user,))

    def user_preference_is_exists(self, user_id: int, pref_list: list[str]) -> bool:
        """execute SQL SELECT command and returns TRUE / FALSE if something found"""

        with self.cursor() as cur:
            for line in pref_list:
                cur.execute(
                    """SELECT id FROM user_preferences WHERE user_id=%s AND preference=%s LIMIT 1;""", (user_id, line)
                )

                if cur.fetchone():
                    return True

        return False

    def get_user_input_state(self, user_id: int) -> UserInputState | None:
        """Get the last bot message to user to define if user is expected to give exact answer"""

        with self.cursor() as cur:
            cur.execute(
                """
                SELECT msg_type FROM msg_from_bot WHERE user_id=%s LIMIT 1;
                """,
                (user_id,),
            )

            extract = cur.fetchone()
        logging.info('get the last bot message to user to define if user is expected to give exact answer')
        logging.info(str(extract))

        # msg_type=UserInputState.
        msg_type = None
        if extract:
            try:
                msg_type = UserInputState(extract[0])
            except Exception:
                msg_type = None

        if msg_type:
            logging.info(f'before this message bot was waiting for {msg_type} from user {user_id}')
        else:
            logging.info(f'before this message bot was NOT waiting anything from user {user_id}')

        return msg_type

    def set_user_input_state(self, user_id: int, message_type: UserInputState) -> None:
        # TODO the same in connect_to_forum
        with self.cursor() as cur:
            cur.execute("""DELETE FROM msg_from_bot WHERE user_id=%s;""", (user_id,))

            cur.execute(
                """INSERT INTO msg_from_bot (user_id, time, msg_type) values (%s, %s, %s);""",
                (user_id, datetime.datetime.now(), message_type),
            )

    def get_user_forum_attributes_db(self, user_id: int) -> tuple[str, str] | None:
        with self.cursor() as cur:
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

    def write_user_forum_attributes_db(self, user_id: int) -> None:
        with self.cursor() as cur:
            cur.execute(
                """UPDATE user_forum_attributes SET status='verified'
                        WHERE user_id=%s and timestamp =
                        (SELECT MAX(timestamp) FROM user_forum_attributes WHERE user_id=%s);""",
                (user_id, user_id),
            )

    def get_onboarding_step(self, user_id: int, user_is_new: bool) -> tuple[int, str]:
        """checks the latest step of onboarding"""
        with self.cursor() as cur:
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

    def save_bot_reply_to_user(self, user_id: int, bot_message: str) -> None:
        """save bot's reply to user in psql"""

        if len(bot_message) > 27 and bot_message[28] in {
            'Актуальные поиски за 60 дней',
            'Последние 20 поисков в разде',
        }:
            bot_message = bot_message[28]
        with self.cursor() as cur:
            cur.execute(
                """INSERT INTO dialogs (user_id, author, timestamp, message_text) values (%s, %s, %s, %s);""",
                (user_id, 'bot', datetime.datetime.now(), bot_message),
            )

    def set_search_follow_mode(self, user_id: int, new_value: bool) -> None:
        filter_name_value = ['whitelist'] if new_value else ['']
        logging.info(f'{filter_name_value=}')
        with self.cursor() as cur:
            cur.execute(
                """INSERT INTO user_pref_search_filtering (user_id, filter_name) values (%s, %s)
                            ON CONFLICT (user_id) DO UPDATE SET filter_name=%s;""",
                (user_id, filter_name_value, filter_name_value),
            )

    def delete_folder_from_user_regional_preference(self, user_id: int, region: int) -> None:
        with self.cursor() as cur:
            cur.execute(
                """DELETE FROM user_regional_preferences WHERE user_id=%s and forum_folder_num=%s;""",
                (user_id, region),
            )

    def get_folders_with_followed_searches(self, user_id: int) -> list[int]:
        with self.cursor() as cur:
            cur.execute(
                """SELECT DISTINCT s.forum_folder_id 
                    FROM searches s 
                    INNER JOIN user_pref_search_whitelist upswl 
                        ON upswl.search_id=s.search_forum_num
                        AND upswl.user_id=%(user_id)s
                        AND upswl.search_following_mode=%(search_follow_on)s
                        AND s.status not in('НЖ', 'НП', 'СТОП')
                ;""",
                {'user_id': user_id, 'search_follow_on': SearchFollowingMode.ON},
            )
            lines = cur.fetchall()
            return [int(x[0]) for x in lines]

    def add_folder_to_user_regional_preference(self, user_id: int, region: int) -> None:
        with self.cursor() as cur:
            cur.execute(
                """INSERT INTO user_regional_preferences (user_id, forum_folder_num) values (%s, %s);""",
                (user_id, region),
            )

    def get_user_regions(self, user_id: int) -> list[int]:
        with self.cursor() as cur:
            cur.execute("""SELECT forum_folder_num from user_regional_preferences WHERE user_id=%s;""", (user_id,))

            user_curr_regs = cur.fetchall()
            return [reg[0] for reg in user_curr_regs]

    def check_saved_radius(self, user: int) -> int | None:
        """check if user already has a radius preference"""
        with self.cursor() as cur:
            cur.execute("""SELECT radius FROM user_pref_radius WHERE user_id=%s;""", (user,))
            raw_radius = cur.fetchone()
            if raw_radius and str(raw_radius) != 'None':
                return int(raw_radius[0])
            return None

    def delete_user_saved_radius(self, user_id: int) -> None:
        with self.cursor() as cur:
            cur.execute("""DELETE FROM user_pref_radius WHERE user_id=%s;""", (user_id,))

    def save_user_radius(self, user_id: int, number: int) -> None:
        with self.cursor() as cur:
            cur.execute(
                """INSERT INTO user_pref_radius (user_id, radius) 
                                    VALUES (%s, %s) ON CONFLICT (user_id) DO
                                    UPDATE SET radius=%s;""",
                (user_id, number, number),
            )

    def delete_user_saved_topic_type(self, user: int, type_id: int) -> None:
        """Delete a certain topic_type for a certain user_id from the DB"""
        with self.cursor() as cur:
            cur.execute("""DELETE FROM user_pref_topic_type WHERE user_id=%s AND topic_type_id=%s;""", (user, type_id))

    def record_topic_type(self, user: int, type_id: int) -> None:
        """Insert a certain topic_type for a certain user_id into the DB"""

        with self.cursor() as cur:
            cur.execute(
                """INSERT INTO user_pref_topic_type (user_id, topic_type_id, timestamp) 
                            VALUES (%s, %s, %s) ON CONFLICT (user_id, topic_type_id) DO NOTHING;""",
                (user, type_id, datetime.datetime.now()),
            )

    def check_saved_topic_types(self, user: int) -> list[int]:
        """check if user already has any preference"""
        with self.cursor() as cur:
            cur.execute("""SELECT topic_type_id FROM user_pref_topic_type WHERE user_id=%s ORDER BY 1;""", (user,))
            raw_data = cur.fetchall()
            return [line[0] for line in raw_data]

    def record_search_whiteness(self, user: int, search_id: int, new_mark_value: SearchFollowingMode | str) -> None:
        """Save a certain user_pref_search_whitelist for a certain user_id into the DB"""
        with self.cursor() as cur:
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

    def add_region_to_user_settings(self, user_id: int, region_id: int) -> None:
        with self.cursor() as cur:
            cur.execute(
                """INSERT INTO user_pref_region (user_id, region_id) values
                        (%s, %s);""",
                (user_id, region_id),
            )

    def save_user_age_prefs(self, user_id: int, chosen_setting: AgePeriod) -> None:
        with self.cursor() as cur:
            cur.execute(
                """INSERT INTO user_pref_age (user_id, period_name, period_set_date, period_min, period_max) 
                                values (%s, %s, %s, %s, %s) ON CONFLICT (user_id, period_min, period_max) DO NOTHING;""",
                (user_id, chosen_setting.name, datetime.datetime.now(), chosen_setting.min_age, chosen_setting.max_age),
            )

    def delete_user_age_pref(self, user_id: int, chosen_setting: AgePeriod) -> None:
        with self.cursor() as cur:
            cur.execute(
                """DELETE FROM user_pref_age WHERE user_id=%s AND period_min=%s AND period_max=%s;""",
                (user_id, chosen_setting.min_age, chosen_setting.max_age),
            )

    def get_age_prefs(self, user_id: int) -> list[tuple]:
        with self.cursor() as cur:
            cur.execute("""SELECT period_min, period_max FROM user_pref_age WHERE user_id=%s;""", (user_id,))
            raw_list_of_periods = cur.fetchall()
            return raw_list_of_periods

    def get_user_settings_summary(self, user_id: int) -> UserSettingsSummary | None:
        with self.cursor() as cur:
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
            return UserSettingsSummary(*raw_data) if raw_data else None

    def get_all_user_preferences(self, user_id: int) -> list[str]:
        with self.cursor() as cur:
            cur.execute("""SELECT preference FROM user_preferences WHERE user_id=%s ORDER BY preference;""", (user_id,))
            user_prefs = cur.fetchall()
            return [x[0] for x in user_prefs]

    def get_active_searches_in_region_limit_20(self, region: int, user_id: int) -> list[SearchSummary]:
        with self.cursor() as cur:
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
            return [
                SearchSummary(
                    topic_id=row[0],
                    start_time=row[1],
                    display_name=row[2],
                    search_lat=row[3],
                    search_lon=row[4],
                    topic_type=row[5],
                    name=row[6],
                    age=row[7],
                    following_mode=row[8],
                )
                for row in searches_list
            ]

    def get_all_last_searches_in_region_limit_20(
        self, region: int, user_id: int, only_followed: bool
    ) -> list[SearchSummary]:
        with self.cursor() as cur:
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
            return [
                (
                    SearchSummary(
                        topic_id=row[0],
                        start_time=row[1],
                        display_name=row[2],
                        new_status=row[3],
                        status=row[4],
                        name=row[5],
                        age=row[6],
                        following_mode=row[7],
                    )
                )
                for row in database
            ]

    def get_active_searches_in_one_region(self, region: int) -> list[SearchSummary]:
        with self.cursor() as cur:
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

            return [
                (
                    SearchSummary(
                        topic_id=row[0],
                        start_time=row[1],
                        display_name=row[2],
                        search_lat=row[3],
                        search_lon=row[4],
                        topic_type=row[5],
                        name=row[6],
                        age=row[7],
                    )
                )
                for row in searches_list
            ]

    def get_all_searches_in_one_region_limit_20(self, region: int) -> list[SearchSummary]:
        with self.cursor() as cur:
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

            rows = cur.fetchall()
            return [
                SearchSummary(
                    topic_id=row[0],
                    start_time=row[1],
                    display_name=row[2],
                    new_status=row[3],
                    status=row[4],
                    name=row[5],
                    age=row[6],
                )
                for row in rows
            ]
