"""Notification preference management mixin — consolidated."""

import sqlalchemy

from _dependencies.common.commons import PREF_DICT
from _dependencies.common.db_client import DBClientMixinBase


class NotificationPrefMixin(DBClientMixinBase):
    """User notification preference operations."""

    def get_all_user_preferences(self, user_id: int) -> list[str]:
        """Get all notification preferences for a user."""
        with self.connect() as connection:
            stmt = sqlalchemy.text(
                """SELECT preference FROM user_preferences WHERE user_id=:user_id ORDER BY preference;"""
            )
            result = connection.execute(stmt, user_id=user_id)
            return [x[0] for x in result.fetchall()]

    def save_preference(self, user_id: int, preference_name: str) -> None:
        """Enable a notification preference for a user."""
        preference_id = PREF_DICT[preference_name]
        with self.connect() as connection:
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
        with self.connect() as connection:
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
        with self.connect() as connection:
            for pref in preferences:
                stmt = sqlalchemy.text(
                    """SELECT id FROM user_preferences
                       WHERE user_id=:user_id AND preference=:preference LIMIT 1;"""
                )
                result = connection.execute(stmt, user_id=user_id, preference=pref)
                if result.fetchone():
                    return True
            return False
