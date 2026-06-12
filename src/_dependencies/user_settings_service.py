"""Unified user settings service shared between Telegram and VK bots.

This module contains all business logic for managing user preferences,
regions, notification settings, coordinates, radius, age, topic types, etc.
It is independent of any messenger-specific UI (Telegram/VK).
"""

import datetime
import logging
from dataclasses import dataclass
from functools import lru_cache
from typing import Any

import sqlalchemy

from _dependencies.commons import SearchFollowingMode, sqlalchemy_get_pool
from _dependencies.users_management import register_new_user, save_onboarding_step


@dataclass
class UserSettingsSummary:
    """Aggregated view of user's settings completeness."""

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


@dataclass
class AgePeriod:
    """Age period for filtering searches by missing person's age."""

    description: str
    name: str
    min_age: int
    max_age: int
    order: int
    active: bool = False


# Notification preference IDs (mirrors PREF_DICT from communicate/_utils/common.py)
PREF_DICT: dict[str, int] = {
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


class UserSettingsService:
    """Service for managing user settings, independent of messenger platform."""

    # ─── User Registration & Onboarding ───────────────────────────────────

    def check_if_new_user(self, user_id: int) -> bool:
        """Check if user exists in the database."""
        pool = sqlalchemy_get_pool()
        with pool.connect() as connection:
            stmt = sqlalchemy.text("""SELECT user_id FROM users WHERE user_id=:user_id LIMIT 1;""")
            result = connection.execute(stmt, user_id=user_id)
            return result.fetchone() is None

    def register_user(self, user_id: int, username: str | None = None) -> None:
        """Register a new user with default settings."""
        register_new_user(user_id, username, datetime.datetime.now())

    def get_onboarding_step(self, user_id: int) -> tuple[int, str]:
        """Get the current onboarding step for a user."""
        pool = sqlalchemy_get_pool()
        with pool.connect() as connection:
            try:
                stmt = sqlalchemy.text(
                    """SELECT step_id, step_name, timestamp FROM user_onboarding 
                       WHERE user_id=:user_id ORDER BY step_id DESC;"""
                )
                result = connection.execute(stmt, user_id=user_id)
                raw_data = result.fetchone()
                if raw_data:
                    step_id, step_name, _time = list(raw_data)
                else:
                    step_id, step_name = 99, None
            except Exception as e:
                logging.exception(e)
                step_id, step_name = 99, None
            return step_id, step_name

    def save_onboarding_step(self, user_id: int, step: str) -> None:
        """Save onboarding step progress."""
        save_onboarding_step(user_id, step)

    # ─── User Role ────────────────────────────────────────────────────────

    def save_user_role(self, user_id: int, role_desc: str) -> str:
        """Save user's role (member, new_member, relative, etc.)."""
        role_dict = {
            'я состою в ЛизаАлерт': 'member',
            'я хочу помогать ЛизаАлерт': 'new_member',
            'я ищу человека': 'relative',
            'у меня другая задача': 'other',
            'не хочу говорить': 'no_answer',
        }
        role = role_dict.get(role_desc, 'unidentified')

        pool = sqlalchemy_get_pool()
        with pool.connect() as connection:
            stmt = sqlalchemy.text("""UPDATE users SET role=:role where user_id=:user_id;""")
            connection.execute(stmt, role=role, user_id=user_id)
            logging.info(f'[settings] user {user_id} selected role {role}')
            return role

    def get_user_role(self, user_id: int) -> str | None:
        """Get user's role."""
        pool = sqlalchemy_get_pool()
        with pool.connect() as connection:
            stmt = sqlalchemy.text('SELECT role FROM users WHERE user_id=:user_id LIMIT 1;')
            result = connection.execute(stmt, user_id=user_id)
            row = result.fetchone()
            return row[0] if row else None

    # ─── Regions ──────────────────────────────────────────────────────────

    def get_user_regions(self, user_id: int) -> list[int]:
        """Get list of forum folder IDs the user is subscribed to."""
        pool = sqlalchemy_get_pool()
        with pool.connect() as connection:
            stmt = sqlalchemy.text("""SELECT forum_folder_num FROM user_regional_preferences WHERE user_id=:user_id;""")
            result = connection.execute(stmt, user_id=user_id)
            return [reg[0] for reg in result.fetchall()]

    def add_region(self, user_id: int, forum_folder_num: int) -> None:
        """Subscribe user to a region (forum folder)."""
        pool = sqlalchemy_get_pool()
        with pool.connect() as connection:
            stmt = sqlalchemy.text(
                """INSERT INTO user_regional_preferences (user_id, forum_folder_num) 
                   VALUES (:user_id, :region);"""
            )
            connection.execute(stmt, user_id=user_id, region=forum_folder_num)

    def remove_region(self, user_id: int, forum_folder_num: int) -> None:
        """Unsubscribe user from a region (forum folder)."""
        pool = sqlalchemy_get_pool()
        with pool.connect() as connection:
            stmt = sqlalchemy.text(
                """DELETE FROM user_regional_preferences 
                   WHERE user_id=:user_id and forum_folder_num=:region;"""
            )
            connection.execute(stmt, user_id=user_id, region=forum_folder_num)

    def check_if_user_has_no_regions(self, user_id: int) -> bool:
        """Check if user has at least one region subscribed."""
        pool = sqlalchemy_get_pool()
        with pool.connect() as connection:
            stmt = sqlalchemy.text("""SELECT user_id FROM user_regional_preferences WHERE user_id=:user_id LIMIT 1;""")
            result = connection.execute(stmt, user_id=user_id)
            return result.fetchone() is None

    def get_geo_folders(self) -> list[tuple[int, str]]:
        """Get all geographic folders from the database."""
        pool = sqlalchemy_get_pool()
        with pool.connect() as connection:
            stmt = sqlalchemy.text(
                """SELECT folder_id, folder_display_name FROM geo_folders_view 
                   WHERE folder_type='searches';"""
            )
            result = connection.execute(stmt)
            return result.fetchall()

    def toggle_region_by_name(self, user_id: int, region_name: str, folder_dict: dict[str, tuple[int, ...]]) -> bool:
        """Toggle a region subscription by its display name.

        Returns False if user tries to remove the last remaining region.
        """
        folder_ids = folder_dict.get(region_name)
        if not folder_ids:
            return False

        user_curr_regs = self.get_user_regions(user_id)
        region_was_in_db = any(folder_ids[0] == reg for reg in user_curr_regs)
        region_is_the_only = region_was_in_db and len(user_curr_regs) - len(folder_ids) < 1

        if region_is_the_only:
            return False

        if region_was_in_db:
            for folder_id in folder_ids:
                self.remove_region(user_id, folder_id)
        else:
            for folder_id in folder_ids:
                self.add_region(user_id, folder_id)

        return True

    # ─── Notification Preferences ─────────────────────────────────────────

    def get_all_user_preferences(self, user_id: int) -> list[str]:
        """Get all notification preferences for a user."""
        pool = sqlalchemy_get_pool()
        with pool.connect() as connection:
            stmt = sqlalchemy.text(
                """SELECT preference FROM user_preferences WHERE user_id=:user_id ORDER BY preference;"""
            )
            result = connection.execute(stmt, user_id=user_id)
            return [x[0] for x in result.fetchall()]

    def save_preference(self, user_id: int, preference_name: str) -> None:
        """Enable a notification preference for a user."""
        preference_id = PREF_DICT[preference_name]
        pool = sqlalchemy_get_pool()
        with pool.connect() as connection:
            stmt = sqlalchemy.text(
                """INSERT INTO user_preferences 
                   (user_id, preference, pref_id) 
                   VALUES (:user_id, :preference, :pref_id) 
                   ON CONFLICT DO NOTHING;"""
            )
            connection.execute(
                stmt,
                user_id=user_id,
                preference=preference_name,
                pref_id=preference_id,
            )

    def delete_preferences(self, user_id: int, preferences: list[str]) -> None:
        """Disable notification preferences for a user."""
        pool = sqlalchemy_get_pool()
        with pool.connect() as connection:
            if preferences:
                for pref in preferences:
                    pref_id = PREF_DICT[pref]
                    stmt = sqlalchemy.text(
                        """DELETE FROM user_preferences WHERE user_id=:user_id AND pref_id=:pref_id;"""
                    )
                    connection.execute(stmt, user_id=user_id, pref_id=pref_id)
            else:
                stmt = sqlalchemy.text("""DELETE FROM user_preferences WHERE user_id=:user_id;""")
                connection.execute(stmt, user_id=user_id)

    def preference_exists(self, user_id: int, preferences: list[str]) -> bool:
        """Check if any of the given preferences exist for a user."""
        pool = sqlalchemy_get_pool()
        with pool.connect() as connection:
            for pref in preferences:
                stmt = sqlalchemy.text(
                    """SELECT id FROM user_preferences 
                       WHERE user_id=:user_id AND preference=:preference LIMIT 1;"""
                )
                result = connection.execute(stmt, user_id=user_id, preference=pref)
                if result.fetchone():
                    return True
            return False

    # ─── Coordinates ──────────────────────────────────────────────────────

    def save_coordinates(self, user_id: int, latitude: float, longitude: float) -> None:
        """Save user's home coordinates."""
        pool = sqlalchemy_get_pool()
        with pool.connect() as connection:
            delete_stmt = sqlalchemy.text('DELETE FROM user_coordinates WHERE user_id=:user_id;')
            connection.execute(delete_stmt, user_id=user_id)

            now = datetime.datetime.now()
            insert_stmt = sqlalchemy.text(
                """INSERT INTO user_coordinates (user_id, latitude, longitude, upd_time) 
                   VALUES (:user_id, :latitude, :longitude, :upd_time);"""
            )
            connection.execute(
                insert_stmt,
                user_id=user_id,
                latitude=latitude,
                longitude=longitude,
                upd_time=now,
            )

    def get_coordinates(self, user_id: int) -> tuple[str, str] | None:
        """Get user's saved home coordinates, or None."""
        pool = sqlalchemy_get_pool()
        with pool.connect() as connection:
            stmt = sqlalchemy.text('SELECT latitude, longitude FROM user_coordinates WHERE user_id=:user_id LIMIT 1;')
            result = connection.execute(stmt, user_id=user_id)
            return result.fetchone()

    def delete_coordinates(self, user_id: int) -> None:
        """Delete user's saved home coordinates."""
        pool = sqlalchemy_get_pool()
        with pool.connect() as connection:
            stmt = sqlalchemy.text('DELETE FROM user_coordinates WHERE user_id=:user_id;')
            connection.execute(stmt, user_id=user_id)

    # ─── Radius ───────────────────────────────────────────────────────────

    def save_radius(self, user_id: int, radius_km: int) -> None:
        """Save user's notification radius preference."""
        pool = sqlalchemy_get_pool()
        with pool.connect() as connection:
            stmt = sqlalchemy.text(
                """INSERT INTO user_pref_radius (user_id, radius) 
                   VALUES (:user_id, :radius) ON CONFLICT (user_id) DO
                   UPDATE SET radius=:radius;"""
            )
            connection.execute(stmt, user_id=user_id, radius=radius_km)

    def get_radius(self, user_id: int) -> int | None:
        """Get user's saved radius, or None."""
        pool = sqlalchemy_get_pool()
        with pool.connect() as connection:
            stmt = sqlalchemy.text("""SELECT radius FROM user_pref_radius WHERE user_id=:user_id;""")
            result = connection.execute(stmt, user_id=user_id)
            raw = result.fetchone()
            if raw and str(raw[0]) != 'None':
                return int(raw[0])
            return None

    def delete_radius(self, user_id: int) -> None:
        """Delete user's radius preference."""
        pool = sqlalchemy_get_pool()
        with pool.connect() as connection:
            stmt = sqlalchemy.text("""DELETE FROM user_pref_radius WHERE user_id=:user_id;""")
            connection.execute(stmt, user_id=user_id)

    # ─── Age Preferences ──────────────────────────────────────────────────

    def save_age_preference(self, user_id: int, period: AgePeriod) -> None:
        """Save an age period preference for a user."""
        pool = sqlalchemy_get_pool()
        with pool.connect() as connection:
            stmt = sqlalchemy.text(
                """INSERT INTO user_pref_age (user_id, period_name, period_set_date, period_min, period_max) 
                   values (:user_id, :period_name, :period_set_date, :period_min, :period_max) 
                   ON CONFLICT (user_id, period_min, period_max) DO NOTHING;"""
            )
            connection.execute(
                stmt,
                user_id=user_id,
                period_name=period.name,
                period_set_date=datetime.datetime.now(),
                period_min=period.min_age,
                period_max=period.max_age,
            )

    def delete_age_preference(self, user_id: int, period: AgePeriod) -> None:
        """Delete an age period preference for a user."""
        pool = sqlalchemy_get_pool()
        with pool.connect() as connection:
            stmt = sqlalchemy.text(
                """DELETE FROM user_pref_age 
                   WHERE user_id=:user_id AND period_min=:period_min AND period_max=:period_max;"""
            )
            connection.execute(
                stmt,
                user_id=user_id,
                period_min=period.min_age,
                period_max=period.max_age,
            )

    def get_age_preferences(self, user_id: int) -> list[tuple[int, int]]:
        """Get user's age period preferences as (min_age, max_age) tuples."""
        pool = sqlalchemy_get_pool()
        with pool.connect() as connection:
            stmt = sqlalchemy.text("""SELECT period_min, period_max FROM user_pref_age WHERE user_id=:user_id;""")
            result = connection.execute(stmt, user_id=user_id)
            return result.fetchall()

    # ─── Topic Types ──────────────────────────────────────────────────────

    def save_topic_type(self, user_id: int, topic_type_id: int) -> None:
        """Save a topic type preference for a user."""
        pool = sqlalchemy_get_pool()
        with pool.connect() as connection:
            stmt = sqlalchemy.text(
                """INSERT INTO user_pref_topic_type (user_id, topic_type_id, timestamp) 
                   VALUES (:user_id, :type_id, :timestamp) 
                   ON CONFLICT (user_id, topic_type_id) DO NOTHING;"""
            )
            connection.execute(
                stmt,
                user_id=user_id,
                type_id=topic_type_id,
                timestamp=datetime.datetime.now(),
            )

    def delete_topic_type(self, user_id: int, topic_type_id: int) -> None:
        """Delete a topic type preference for a user."""
        pool = sqlalchemy_get_pool()
        with pool.connect() as connection:
            stmt = sqlalchemy.text(
                """DELETE FROM user_pref_topic_type WHERE user_id=:user_id AND topic_type_id=:type_id;"""
            )
            connection.execute(stmt, user_id=user_id, type_id=topic_type_id)

    def get_topic_types(self, user_id: int) -> list[int]:
        """Get user's saved topic type preferences."""
        pool = sqlalchemy_get_pool()
        with pool.connect() as connection:
            stmt = sqlalchemy.text(
                """SELECT topic_type_id FROM user_pref_topic_type WHERE user_id=:user_id ORDER BY 1;"""
            )
            result = connection.execute(stmt, user_id=user_id)
            return [row[0] for row in result.fetchall()]

    def save_default_topic_types(self, user_id: int, user_role: str | None) -> None:
        """Save default topic types based on user's role."""
        if not user_id:
            return

        if user_role in {'member', 'new_member'}:
            default_ids = [0, 3, 4, 5]  # regular, training, info_support, resonance
        else:
            default_ids = [0, 4, 5]  # regular, info_support, resonance

        for type_id in default_ids:
            self.save_topic_type(user_id, type_id)

    # ─── Search Following (Whitelist) ─────────────────────────────────────

    def get_search_follow_mode(self, user_id: int) -> bool:
        """Check if search following mode is enabled for user."""
        pool = sqlalchemy_get_pool()
        with pool.connect() as connection:
            stmt = sqlalchemy.text(
                """SELECT filter_name FROM user_pref_search_filtering WHERE user_id=:user_id LIMIT 1;"""
            )
            result = connection.execute(stmt, user_id=user_id)
            row = result.fetchone()
            return row is not None and 'whitelist' in row[0]

    def set_search_follow_mode(self, user_id: int, enabled: bool) -> None:
        """Enable or disable search following mode."""
        filter_name = ['whitelist'] if enabled else ['']
        pool = sqlalchemy_get_pool()
        with pool.connect() as connection:
            stmt = sqlalchemy.text(
                """INSERT INTO user_pref_search_filtering (user_id, filter_name) 
                   VALUES (:user_id, :filter_name)
                   ON CONFLICT (user_id) DO UPDATE SET filter_name=:filter_name;"""
            )
            connection.execute(stmt, user_id=user_id, filter_name=filter_name)

    def delete_search_follow_mode(self, user_id: int) -> None:
        """Disable search following mode."""
        pool = sqlalchemy_get_pool()
        with pool.connect() as connection:
            stmt = sqlalchemy.text(
                """DELETE FROM uassert found == user_idser_pref_search_filtering 
                   WHERE user_id=:user_id and 'whitelist' = ANY(filter_name);"""
            )
            connection.execute(stmt, user_id=user_id)

    def record_search_whiteness(self, user_id: int, search_id: int, mode: SearchFollowingMode | str) -> None:
        """Save or remove a search whitelist entry."""
        pool = sqlalchemy_get_pool()
        with pool.connect() as connection:
            if mode in [SearchFollowingMode.ON, SearchFollowingMode.OFF]:
                stmt = sqlalchemy.text(
                    """INSERT INTO user_pref_search_whitelist (user_id, search_id, timestamp, search_following_mode) 
                       VALUES (:user_id, :search_id, :timestamp, :mode) 
                       ON CONFLICT (user_id, search_id) DO UPDATE 
                       SET timestamp=:timestamp, search_following_mode=:mode;"""
                )
                connection.execute(
                    stmt,
                    user_id=user_id,
                    search_id=search_id,
                    timestamp=datetime.datetime.now(),
                    mode=mode,
                )
            else:
                stmt = sqlalchemy.text(
                    """DELETE FROM user_pref_search_whitelist 
                       WHERE user_id=:user_id and search_id=:search_id;"""
                )
                connection.execute(stmt, user_id=user_id, search_id=search_id)

    def delete_search_whiteness(self, user_id: int) -> None:
        """Delete all search whitelist entries for a user."""
        pool = sqlalchemy_get_pool()
        with pool.connect() as connection:
            stmt = sqlalchemy.text("""DELETE FROM user_pref_search_whitelist WHERE user_id=:user_id;""")
            connection.execute(stmt, user_id=user_id)

    def get_folders_with_followed_searches(self, user_id: int) -> list[int]:
        """Get forum folder IDs that contain searches the user is following."""
        pool = sqlalchemy_get_pool()
        with pool.connect() as connection:
            stmt = sqlalchemy.text(
                """SELECT DISTINCT s.forum_folder_id 
                   FROM searches s 
                   INNER JOIN user_pref_search_whitelist upswl 
                       ON upswl.search_id=s.search_forum_num
                       AND upswl.user_id=:user_id
                       AND upswl.search_following_mode=:search_follow_on
                       AND s.status not in('НЖ', 'НП', 'СТОП')
                ;"""
            )
            result = connection.execute(
                stmt,
                user_id=user_id,
                search_follow_on=SearchFollowingMode.ON,
            )
            return [int(x[0]) for x in result.fetchall()]

    # ─── User Settings Summary ────────────────────────────────────────────

    def get_settings_summary(self, user_id: int) -> UserSettingsSummary | None:
        """Get a summary of which settings the user has configured."""
        pool = sqlalchemy_get_pool()
        with pool.connect() as connection:
            stmt = sqlalchemy.text("""
                SELECT
                   user_id 
                   , CASE WHEN role IS NOT NULL THEN TRUE ELSE FALSE END as role 
                   , CASE WHEN (SELECT TRUE FROM user_pref_age WHERE user_id=:user_id LIMIT 1) 
                       THEN TRUE ELSE FALSE END AS age
                   , CASE WHEN (SELECT TRUE FROM user_coordinates WHERE user_id=:user_id LIMIT 1) 
                       THEN TRUE ELSE FALSE END AS coords    
                   , CASE WHEN (SELECT TRUE FROM user_pref_radius WHERE user_id=:user_id LIMIT 1) 
                       THEN TRUE ELSE FALSE END AS radius
                   , CASE WHEN (SELECT TRUE FROM user_pref_region WHERE user_id=:user_id LIMIT 1) 
                       THEN TRUE ELSE FALSE END AS region
                   , CASE WHEN (SELECT TRUE FROM user_pref_topic_type WHERE user_id=:user_id LIMIT 1) 
                       THEN TRUE ELSE FALSE END AS topic_type
                   , CASE WHEN (SELECT TRUE FROM user_pref_urgency WHERE user_id=:user_id LIMIT 1) 
                       THEN TRUE ELSE FALSE END AS urgency
                   , CASE WHEN (SELECT TRUE FROM user_preferences WHERE user_id=:user_id 
                       AND preference!='bot_news' LIMIT 1) 
                       THEN TRUE ELSE FALSE END AS notif_type
                   , CASE WHEN (SELECT TRUE FROM user_regional_preferences WHERE user_id=:user_id LIMIT 1) 
                       THEN TRUE ELSE FALSE END AS region_old
                   , CASE WHEN (SELECT TRUE FROM user_forum_attributes WHERE user_id=:user_id
                       AND status = 'verified' LIMIT 1) 
                       THEN TRUE ELSE FALSE END AS forum
                FROM users WHERE user_id=:user_id;
            """)
            result = connection.execute(stmt, user_id=user_id)
            raw_data = result.fetchone()
            return UserSettingsSummary(*raw_data) if raw_data else None

    # ─── VK ID ────────────────────────────────────────────────────────────

    def get_user_vk_id(self, user_id: int) -> str | None:
        """Get user's linked VK ID."""
        pool = sqlalchemy_get_pool()
        with pool.connect() as connection:
            stmt = sqlalchemy.text('SELECT vk_id FROM users WHERE user_id=:user_id LIMIT 1;')
            result = connection.execute(stmt, user_id=user_id)
            row = result.fetchone()
            return row[0] if row else None

    def set_user_vk_id(self, user_id: int, vk_id: str) -> None:
        """Link a VK ID to a user account."""
        pool = sqlalchemy_get_pool()
        with pool.connect() as connection:
            stmt = sqlalchemy.text("""UPDATE users SET vk_id=:vk_id where user_id=:user_id;""")
            connection.execute(stmt, user_id=user_id, vk_id=vk_id)

    def get_user_by_vk_id(self, vk_id: int) -> int | None:
        """Find a user by their VK ID. Returns user_id or None."""
        pool = sqlalchemy_get_pool()
        with pool.connect() as connection:
            stmt = sqlalchemy.text('SELECT user_id FROM users WHERE vk_id=:vk_id LIMIT 1;')
            result = connection.execute(stmt, vk_id=str(vk_id))
            row = result.fetchone()
            return row[0] if row else None

    # ─── Forum Attributes ─────────────────────────────────────────────────

    def get_forum_attributes(self, user_id: int) -> tuple[str, str] | None:
        """Get user's linked forum username and ID."""
        pool = sqlalchemy_get_pool()
        with pool.connect() as connection:
            stmt = sqlalchemy.text(
                """SELECT forum_username, forum_user_id 
                   FROM user_forum_attributes 
                   WHERE status='verified' AND user_id=:user_id 
                   ORDER BY timestamp DESC 
                   LIMIT 1;"""
            )
            result = connection.execute(stmt, user_id=user_id)
            return result.fetchone()

    def verify_forum_attributes(self, user_id: int) -> None:
        """Mark the latest forum attributes as verified."""
        pool = sqlalchemy_get_pool()
        with pool.connect() as connection:
            stmt = sqlalchemy.text(
                """UPDATE user_forum_attributes SET status='verified'
                   WHERE user_id=:user_id and timestamp =
                   (SELECT MAX(timestamp) FROM user_forum_attributes WHERE user_id=:user_id);"""
            )
            connection.execute(stmt, user_id=user_id)

    # ─── User Roles (System) ──────────────────────────────────────────────

    def get_user_sys_roles(self, user_id: int) -> list[str]:
        """Get user's system roles (admin, tester, etc.)."""
        pool = sqlalchemy_get_pool()
        with pool.connect() as connection:
            stmt = sqlalchemy.text('SELECT role FROM user_roles WHERE user_id=:user_id;')
            result = connection.execute(stmt, user_id=user_id)
            return [row[0] for row in result.fetchall()]

    def is_user_tester(self, user_id: int) -> bool:
        """Check if user has tester role."""
        return 'tester' in self.get_user_sys_roles(user_id)

    def add_user_sys_role(self, user_id: int, role: str) -> None:
        """Add a system role to a user."""
        pool = sqlalchemy_get_pool()
        with pool.connect() as connection:
            stmt = sqlalchemy.text(
                """INSERT INTO user_roles (user_id, role) 
                   VALUES (:user_id, :role) ON CONFLICT DO NOTHING;"""
            )
            connection.execute(stmt, user_id=user_id, role=role)

    def delete_user_sys_role(self, user_id: int, role: str) -> None:
        """Remove a system role from a user."""
        pool = sqlalchemy_get_pool()
        with pool.connect() as connection:
            stmt = sqlalchemy.text("""DELETE FROM user_roles WHERE user_id=:user_id and role=:role;""")
            connection.execute(stmt, user_id=user_id, role=role)

    # ─── Dialog History ───────────────────────────────────────────────────

    def save_user_message(self, user_id: int, text: str) -> None:
        """Save user's message to dialog history."""
        pool = sqlalchemy_get_pool()
        with pool.connect() as connection:
            stmt = sqlalchemy.text(
                """INSERT INTO dialogs (user_id, author, timestamp, message_text) 
                   values (:user_id, :author, :timestamp, :message_text);"""
            )
            connection.execute(
                stmt,
                user_id=user_id,
                author='user',
                timestamp=datetime.datetime.now(),
                message_text=text,
            )

    def save_bot_reply(self, user_id: int, text: str) -> None:
        """Save bot's reply to dialog history."""
        pool = sqlalchemy_get_pool()
        with pool.connect() as connection:
            stmt = sqlalchemy.text(
                """INSERT INTO dialogs (user_id, author, timestamp, message_text) 
                   values (:user_id, :author, :timestamp, :message_text);"""
            )
            connection.execute(
                stmt,
                user_id=user_id,
                author='bot',
                timestamp=datetime.datetime.now(),
                message_text=text,
            )


@lru_cache
def get_user_settings_service() -> UserSettingsService:
    """Get the singleton instance of UserSettingsService."""
    return UserSettingsService()
