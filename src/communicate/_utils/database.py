import datetime
import logging
from dataclasses import dataclass
from functools import lru_cache

import sqlalchemy

from _dependencies.common.commons import SearchFollowingMode
from _dependencies.common.db_client import DBClientBase
from _dependencies.models import AgePeriod, DialogState, UserSettingsSummary
from _dependencies.user_repository import (
    AgePrefMixin,
    DialogHistoryMixin,
    DialogStateMixin,
    ForumAttributeMixin,
    GeoPrefMixin,
    NotificationPrefMixin,
    RegionMixin,
    SearchFollowingMixin,
    SettingsSummaryMixin,
    SystemRoleMixin,
    TopicTypeMixin,
    UserMixin,
    VKIdentityMixin,
)

from .common import PREF_DICT, SearchSummary, UserInputState


class DBClient(
    DBClientBase,
    VKIdentityMixin,
    DialogStateMixin,
    UserMixin,
    RegionMixin,
    NotificationPrefMixin,
    GeoPrefMixin,
    AgePrefMixin,
    TopicTypeMixin,
    SearchFollowingMixin,
    ForumAttributeMixin,
    SystemRoleMixin,
    DialogHistoryMixin,
    SettingsSummaryMixin,
):
    """Telegram bot DB client.

    Inherits shared methods from consolidated mixins in ``_dependencies.user_repository``.
    Telegram-specific methods (search queries, inline dialogue tracking) remain here.
    """

    # ═══════════════════════════════════════════════════════════════════════
    # Adapter methods — map communicate's method names to mixin names
    # ═══════════════════════════════════════════════════════════════════════

    def save_user_message_to_bot(self, user_id: int, got_message: str) -> None:
        """Save user's message to bot in psql"""
        self.save_user_message(user_id, got_message)

    def save_bot_reply_to_user(self, user_id: int, bot_message: str) -> None:
        """save bot's reply to user in psql"""
        if len(bot_message) > 27 and bot_message[28] in {
            'Актуальные поиски за 60 дней',
            'Последние 20 поисков в разде',
        }:
            bot_message = bot_message[28]

        self.save_bot_reply(user_id, bot_message)

    def get_saved_user_coordinates(self, user_id: int) -> tuple[str, str] | None:
        return self.get_coordinates(user_id)

    def get_user_coordinates_or_none(self, user_id: int) -> tuple[str, str] | tuple[None, None]:
        saved_coords = self.get_coordinates(user_id)
        return saved_coords or (None, None)

    def save_user_coordinates(self, user_id: int, input_latitude: float, input_longitude: float) -> None:
        self.save_coordinates(user_id, input_latitude, input_longitude)

    def delete_user_coordinates(self, user_id: int) -> None:
        self.delete_coordinates(user_id)

    def check_saved_radius(self, user: int) -> int | None:
        return self.get_radius(user)

    def save_user_radius(self, user_id: int, number: int) -> None:
        self.save_radius(user_id, number)

    def delete_user_saved_radius(self, user_id: int) -> None:
        self.delete_radius(user_id)

    def get_user_regions_from_db(self, user_id: int) -> list[int]:
        return self.get_user_regions(user_id)

    def get_user_reg_folders_preferences(self, user_id: int) -> list[int]:
        return self.get_user_regions(user_id)

    def get_geo_folders_db(self) -> list[tuple[int, str]]:
        return self.get_geo_folders()

    def add_folder_to_user_regional_preference(self, user_id: int, region: int) -> None:
        self.add_region(user_id, region)

    def delete_folder_from_user_regional_preference(self, user_id: int, region: int) -> None:
        self.remove_region(user_id, region)

    def get_user_forum_attributes_db(self, user_id: int) -> tuple[str, str] | None:
        return self.get_forum_attributes(user_id)

    def write_user_forum_attributes_db(self, user_id: int) -> None:
        self.verify_forum_attributes(user_id)

    def get_user_input_state(self, user_id: int) -> UserInputState | None:
        """Get the last bot message to user to define if user is expected to give exact answer"""
        state = self.get_user_state(user_id)
        if state is None:
            return None
        try:
            return UserInputState(state.value)
        except ValueError:
            return None

    def set_user_input_state(self, user_id: int, message_type: UserInputState) -> None:
        """Set the user's input state (what kind of input bot expects).

        Accepts both UserInputState enum and plain string (for backward compatibility
        with tests that pass strings directly).
        """
        if isinstance(message_type, UserInputState):
            state_value = message_type.value
        else:
            state_value = str(message_type)
        # Write directly to DB to preserve backward compatibility with raw string values
        with self.connect() as connection:
            delete_stmt = sqlalchemy.text("""DELETE FROM msg_from_bot WHERE user_id=:user_id;""")
            connection.execute(delete_stmt, user_id=user_id)
            insert_stmt = sqlalchemy.text(
                """INSERT INTO msg_from_bot (user_id, time, msg_type) values (:user_id, :time, :msg_type);"""
            )
            connection.execute(
                insert_stmt,
                user_id=user_id,
                time=datetime.datetime.now(),
                msg_type=state_value,
            )

    def user_preference_save(self, user: int, preference_name: str) -> None:
        self.save_preference(user, preference_name)

    def user_preference_delete(self, user: int, list_of_prefs: list[str]) -> None:
        self.delete_preferences(user, list_of_prefs)

    def user_preference_is_exists(self, user_id: int, pref_list: list[str]) -> bool:
        return self.preference_exists(user_id, pref_list)

    def save_user_age_prefs(self, user_id: int, chosen_setting: AgePeriod) -> None:
        self.save_age_preference(user_id, chosen_setting)

    def delete_user_age_pref(self, user_id: int, chosen_setting: AgePeriod) -> None:
        self.delete_age_preference(user_id, chosen_setting)

    def get_age_prefs(self, user_id: int) -> list[tuple]:
        return self.get_age_preferences(user_id)

    def check_saved_topic_types(self, user: int) -> list[int]:
        return self.get_topic_types(user)

    def record_topic_type(self, user: int, type_id: int) -> None:
        self.save_topic_type(user, type_id)

    def delete_user_saved_topic_type(self, user: int, type_id: int) -> None:
        self.delete_topic_type(user, type_id)

    def get_user_settings_summary(self, user_id: int) -> UserSettingsSummary | None:
        return self.get_settings_summary(user_id)

    def get_user_sys_roles(self, user_id: int) -> list[str]:
        """Return user's roles in system (with leading empty string for backward compatibility)."""
        roles = super().get_user_sys_roles(user_id)
        return [''] + roles

    # ═══════════════════════════════════════════════════════════════════════
    # Communicate-specific methods (not in shared mixins)
    # ═══════════════════════════════════════════════════════════════════════

    def delete_last_user_inline_dialogue(self, user_id: int) -> None:
        """Delete form DB the user's last interaction via inline buttons"""
        with self.connect() as connection:
            stmt = sqlalchemy.text("""DELETE FROM communications_last_inline_msg WHERE user_id=:user_id;""")
            connection.execute(stmt, user_id=user_id)

    def get_last_user_inline_dialogue(self, user_id: int) -> list[int]:
        """Get from DB the user's last interaction via inline buttons"""
        with self.connect() as connection:
            stmt = sqlalchemy.text("""SELECT message_id FROM communications_last_inline_msg WHERE user_id=:user_id;""")
            result = connection.execute(stmt, user_id=user_id)
            message_id_lines = result.fetchall()
            message_id_list = []
            if message_id_lines and len(message_id_lines) > 0:
                for message_id_line in message_id_lines:
                    message_id_list.append(message_id_line[0])
            return message_id_list

    def save_last_user_inline_dialogue(self, user_id: int, message_id: int) -> None:
        """Save to DB the user's last interaction via inline buttons"""
        with self.connect() as connection:
            stmt = sqlalchemy.text(
                """INSERT INTO communications_last_inline_msg 
                            (user_id, timestamp, message_id) values (:user_id, CURRENT_TIMESTAMP AT TIME ZONE 'UTC', :message_id)
                            ON CONFLICT (user_id, message_id) DO 
                            UPDATE SET timestamp=CURRENT_TIMESTAMP AT TIME ZONE 'UTC';"""
            )
            connection.execute(stmt, user_id=user_id, message_id=message_id)

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

        with self.connect() as connection:
            stmt = sqlalchemy.text("""UPDATE users SET role=:role where user_id=:user_id;""")
            connection.execute(stmt, role=role, user_id=user_id)
            logging.info(f'[comm]: user {user_id} selected role {role}')
            return role

    def _save_user_pref_topic_type(self, user_id: int, pref_type_id: int) -> None:
        self.save_topic_type(user_id, pref_type_id)

    def save_user_pref_topic_type(self, user_id: int, user_role: str | None) -> None:
        if not user_id:
            return
        if user_role in {'member', 'new_member'}:
            default_topic_type_id = [0, 3, 4, 5]
        else:
            default_topic_type_id = [0, 4, 5]
        for type_id in default_topic_type_id:
            self._save_user_pref_topic_type(user_id, type_id)

    def delete_search_follow_marks(self, user_id: int) -> None:
        with self.connect() as connection:
            stmt = sqlalchemy.text(
                """DELETE FROM user_pref_search_whitelist 
                   WHERE user_id=:user_id;"""
            )
            connection.execute(stmt, user_id=user_id)

    def add_region_to_user_settings(self, user_id: int, region_id: int) -> None:
        with self.connect() as connection:
            stmt = sqlalchemy.text(
                """INSERT INTO user_pref_region (user_id, region_id) values
                   (:user_id, :region_id);"""
            )
            connection.execute(stmt, user_id=user_id, region_id=region_id)

    # ═══════════════════════════════════════════════════════════════════════
    # Search-related queries (Telegram-specific, not shared with VK bot)
    # ═══════════════════════════════════════════════════════════════════════

    def get_active_searches_in_region_limit_20(self, region: int, user_id: int) -> list[SearchSummary]:
        with self.connect() as connection:
            stmt = sqlalchemy.text("""
                SELECT s.search_forum_num, s.search_start_time, s.display_name, sa.latitude, sa.longitude, 
                s.topic_type, s.family_name, s.age, upswl.search_following_mode
                FROM searches s 
                LEFT JOIN search_coordinates sa ON s.search_forum_num = sa.search_id 
                LEFT JOIN search_health_check shc ON s.search_forum_num=shc.search_forum_num
                LEFT JOIN user_pref_search_whitelist upswl ON upswl.search_id=s.search_forum_num and upswl.user_id=:user_id
                WHERE s.forum_folder_id=:region
                AND (
                        (
                            (s.status='Ищем' OR s.status='Возобновлен')
                        and (shc.status is NULL or shc.status='ok' or shc.status='regular')
                        )
                    or (upswl.search_following_mode=:search_follow_on
                        and s.status in('Ищем', 'Возобновлен', 'СТОП')
                        )
                    )
                ORDER BY s.search_start_time DESC
                LIMIT 20;""")

            result = connection.execute(
                stmt,
                region=region,
                user_id=user_id,
                search_follow_on=SearchFollowingMode.ON,
            )
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
                for row in result.fetchall()
            ]

    def get_all_last_searches_in_region_limit_20(
        self, region: int, user_id: int, only_followed: bool
    ) -> list[SearchSummary]:
        with self.connect() as connection:
            sql_text = """
                SELECT DISTINCT search_forum_num, search_start_time, display_name, status, status, family_name, age, search_following_mode
                FROM(   -- q
                        SELECT s21.*, upswl.search_following_mode FROM 
                            (SELECT search_forum_num, search_start_time, display_name, s01.status as new_status, s01.status, family_name, age 
                            FROM searches s01
                            WHERE forum_folder_id=:region 
                            ) s21 
                        INNER JOIN user_pref_search_whitelist upswl 
                            ON upswl.search_id=s21.search_forum_num and upswl.user_id=:user_id
                                and upswl.search_following_mode=:search_follow_on 
                        """
            if not only_followed:
                sql_text += """
                    UNION
                        SELECT s2.*, upswl.search_following_mode FROM 
                            (SELECT search_forum_num, search_start_time, display_name, s00.status as new_status, s00.status, family_name, age 
                            FROM searches s00
                            WHERE forum_folder_id=:region 
                            ORDER BY search_start_time DESC 
                            LIMIT 20) s2 
                        LEFT JOIN search_health_check shc ON s2.search_forum_num=shc.search_forum_num
                        LEFT JOIN user_pref_search_whitelist upswl ON upswl.search_id=s2.search_forum_num and upswl.user_id=:user_id
                        WHERE (shc.status is NULL or shc.status='ok' or shc.status='regular') 
                    """
            sql_text += """
                    )q
                ORDER BY search_start_time DESC
                LIMIT 20
                ;"""

            stmt = sqlalchemy.text(sql_text)
            result = connection.execute(
                stmt,
                region=region,
                user_id=user_id,
                search_follow_on=SearchFollowingMode.ON,
            )
            return [
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
                for row in result.fetchall()
            ]

    def get_active_searches_in_one_region(self, region: int) -> list[SearchSummary]:
        with self.connect() as connection:
            stmt = sqlalchemy.text("""
                SELECT s2.* FROM 
                    (SELECT s.search_forum_num, s.search_start_time, s.display_name, sa.latitude, sa.longitude, 
                    s.topic_type, s.family_name, s.age 
                    FROM searches s 
                    LEFT JOIN search_coordinates sa ON s.search_forum_num = sa.search_id 
                    WHERE (s.status='Ищем' OR s.status='Возобновлен') 
                        AND s.forum_folder_id=:region ORDER BY s.search_start_time DESC) s2 
                LEFT JOIN search_health_check shc ON s2.search_forum_num=shc.search_forum_num
                WHERE (shc.status is NULL or shc.status='ok' or shc.status='regular') 
                ORDER BY s2.search_start_time DESC;""")

            result = connection.execute(stmt, region=region)
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
                )
                for row in result.fetchall()
            ]

    def get_all_searches_in_one_region_limit_20(self, region: int) -> list[SearchSummary]:
        with self.connect() as connection:
            stmt = sqlalchemy.text("""
                SELECT s2.* FROM 
                    (SELECT search_forum_num, search_start_time, display_name, status, status, family_name, age 
                    FROM searches 
                    WHERE forum_folder_id=:region 
                    ORDER BY search_start_time DESC 
                    LIMIT 20) s2 
                LEFT JOIN search_health_check shc 
                ON s2.search_forum_num=shc.search_forum_num 
                WHERE (shc.status is NULL or shc.status='ok' or shc.status='regular') 
                ORDER BY s2.search_start_time DESC;""")

            result = connection.execute(stmt, region=region)
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
                for row in result.fetchall()
            ]


@lru_cache
def db() -> DBClient:
    return DBClient()
