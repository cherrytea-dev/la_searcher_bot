import datetime
from functools import lru_cache

import sqlalchemy

from _dependencies.common.db_client import DBClientBase
from _dependencies.models import AgePeriod, UserSettingsSummary
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

from .common import SearchSummary, UserInputState
from .inline_dialogue import InlineDialogueMixin
from .role_mixin import TelegramRoleMixin
from .search_queries import (
    get_active_searches_in_one_region,
    get_active_searches_in_region_limit_20,
    get_all_last_searches_in_region_limit_20,
    get_all_searches_in_one_region_limit_20,
)


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
    InlineDialogueMixin,
    TelegramRoleMixin,
):
    """Telegram bot DB client.

    Inherits shared methods from consolidated mixins in ``_dependencies.user_repository``,
    plus Telegram-specific mixins (InlineDialogueMixin, TelegramRoleMixin).
    Search queries are delegated to module-level functions in ``search_queries.py``.
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
            connection.execute(delete_stmt, dict(user_id=user_id))
            insert_stmt = sqlalchemy.text(
                """INSERT INTO msg_from_bot (user_id, time, msg_type) values (:user_id, :time, :msg_type);"""
            )
            connection.execute(
                insert_stmt,
                dict(
                    user_id=user_id,
                    time=datetime.datetime.now(),
                    msg_type=state_value,
                ),
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

    # ═══════════════════════════════════════════════════════════════════════
    # Search-related queries — delegate to module-level functions
    # ═══════════════════════════════════════════════════════════════════════

    def get_active_searches_in_region_limit_20(self, region: int, user_id: int) -> list[SearchSummary]:
        with self.connect() as connection:
            return get_active_searches_in_region_limit_20(connection, region, user_id)

    def get_all_last_searches_in_region_limit_20(
        self, region: int, user_id: int, only_followed: bool
    ) -> list[SearchSummary]:
        with self.connect() as connection:
            return get_all_last_searches_in_region_limit_20(connection, region, user_id, only_followed)

    def get_active_searches_in_one_region(self, region: int) -> list[SearchSummary]:
        with self.connect() as connection:
            return get_active_searches_in_one_region(connection, region)

    def get_all_searches_in_one_region_limit_20(self, region: int) -> list[SearchSummary]:
        with self.connect() as connection:
            return get_all_searches_in_one_region_limit_20(connection, region)


@lru_cache
def db() -> DBClient:
    return DBClient()
