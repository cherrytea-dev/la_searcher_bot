"""Reset user settings to registration defaults — consolidated mixin."""

import datetime

import sqlalchemy

from _dependencies.bot.users_management import DEFAULT_NOTIFICATION_PREFS
from _dependencies.common.db_client import DBClientMixinBase
from _dependencies.user_repository.topic_type import default_topic_type_ids

# Per-user preference tables wiped on reset. This is a compile-time constant
# tuple (never user input), so string interpolation in DELETE statements is safe.
_RESET_TABLES: tuple[str, ...] = (
    'user_preferences',
    'user_pref_topic_type',
    'user_pref_age',
    'user_pref_radius',
    'user_coordinates',
    'user_regional_preferences',
    'user_pref_region',
    'user_pref_search_filtering',
    'user_pref_search_whitelist',
    'user_pref_urgency',
)


class SettingsResetMixin(DBClientMixinBase):
    """Reset a user's settings back to registration defaults.

    Wipes all per-user preference tables and re-seeds the two that have
    non-empty defaults: notification preferences and topic types (by role).

    Deliberately NOT touched — identity/delivery, not "settings":
    ``users.role``, ``users.status``, ``user_roles`` (system roles),
    ``user_forum_attributes`` (forum link), onboarding and dialog history.
    """

    def reset_user_settings(self, user_id: int) -> None:
        """Reset all settings in a single transaction.

        ``connect()`` uses ``engine.begin()``, so either every statement
        commits or none do — no partial reset state.
        """
        with self.connect() as conn:
            role = self._get_user_role(conn, user_id)

            for table in _RESET_TABLES:
                conn.execute(
                    sqlalchemy.text(f'DELETE FROM {table} WHERE user_id=:user_id'),
                    {'user_id': user_id},
                )

            self._seed_default_notifications(conn, user_id)
            self._seed_default_topic_types(conn, user_id, role)

    @staticmethod
    def _get_user_role(conn: sqlalchemy.engine.Connection, user_id: int) -> str | None:
        stmt = sqlalchemy.text('SELECT role FROM users WHERE user_id=:user_id LIMIT 1;')
        row = conn.execute(stmt, {'user_id': user_id}).fetchone()
        return row[0] if row else None

    @staticmethod
    def _seed_default_notifications(conn: sqlalchemy.engine.Connection, user_id: int) -> None:
        stmt = sqlalchemy.text(
            """
            INSERT INTO user_preferences (user_id, preference, pref_id)
            VALUES (:user_id, :preference, :pref_id)
            ON CONFLICT (user_id, pref_id) DO NOTHING
            """
        )
        for pref_name, pref_id in DEFAULT_NOTIFICATION_PREFS:
            conn.execute(stmt, {'user_id': user_id, 'preference': pref_name, 'pref_id': pref_id})

    @staticmethod
    def _seed_default_topic_types(
        conn: sqlalchemy.engine.Connection,
        user_id: int,
        role: str | None,
    ) -> None:
        stmt = sqlalchemy.text(
            """
            INSERT INTO user_pref_topic_type (user_id, topic_type_id, timestamp)
            VALUES (:user_id, :type_id, :timestamp)
            ON CONFLICT (user_id, topic_type_id) DO NOTHING
            """
        )
        for type_id in default_topic_type_ids(role):
            conn.execute(
                stmt,
                {'user_id': user_id, 'type_id': type_id, 'timestamp': datetime.datetime.now()},
            )
