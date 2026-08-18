"""Reset user settings to registration defaults — consolidated mixin."""

import datetime

import sqlalchemy

from _dependencies.common.commons import save_default_notification_settings
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

# Onboarding step IDs at/after region selection. On reset we drop these rows
# so the bot re-prompts the user to pick a region (registration state).
_REGION_ONBOARDING_STEP_ID = 20  # moscow_replied; region_set=21, finished=80


class SettingsResetMixin(DBClientMixinBase):
    """Reset a user's settings back to registration defaults.

    Wipes all per-user preference tables and re-seeds the two that have
    non-empty defaults: notification preferences and topic types.

    Reproduces the *registration* state, not the role-aware onboarding
    state: topic types are seeded as ``default_topic_type_ids(None)``.

    Also restores subscription (``unsubscribed`` → ``unblocked``) and rolls
    onboarding back to region selection.

    Deliberately NOT touched — identity/delivery, not "settings":
    ``users.role``, ``user_roles`` (system roles), ``user_forum_attributes``
    (forum link), ``users.status='blocked'`` (admin action) and history.
    """

    def reset_user_settings(self, user_id: int) -> None:
        """Reset all settings in a single transaction.

        ``connect()`` uses ``engine.begin()``, so either every statement
        commits or none do — no partial reset state.
        """
        with self.connect() as conn:
            for table in _RESET_TABLES:
                conn.execute(
                    sqlalchemy.text(f'DELETE FROM {table} WHERE user_id=:user_id'),
                    {'user_id': user_id},
                )

            # Re-seed defaults from the same single source as registration.
            save_default_notification_settings(conn, user_id)
            self._seed_default_topic_types(conn, user_id)

            self._restore_subscription(conn, user_id)
            self._rollback_onboarding(conn, user_id)

    @staticmethod
    def _seed_default_topic_types(conn: sqlalchemy.engine.Connection, user_id: int) -> None:
        stmt = sqlalchemy.text(
            """
            INSERT INTO user_pref_topic_type (user_id, topic_type_id, timestamp)
            VALUES (:user_id, :type_id, :timestamp)
            ON CONFLICT (user_id, topic_type_id) DO NOTHING
            """
        )
        # role=None → registration default [0, 4, 5], matching VK/MAX registration.
        for type_id in default_topic_type_ids(None):
            conn.execute(
                stmt,
                {'user_id': user_id, 'type_id': type_id, 'timestamp': datetime.datetime.now()},
            )

    @staticmethod
    def _restore_subscription(conn: sqlalchemy.engine.Connection, user_id: int) -> None:
        """Re-subscribe a user who had explicitly disabled notifications.

        Only ``unsubscribed`` → ``unblocked``. ``blocked`` (admin action) is
        deliberately left untouched.
        """
        conn.execute(
            sqlalchemy.text(
                """
                UPDATE users
                SET status = 'unblocked', status_change_date = now()
                WHERE user_id = :user_id AND status = 'unsubscribed'
                """
            ),
            {'user_id': user_id},
        )

    @staticmethod
    def _rollback_onboarding(conn: sqlalchemy.engine.Connection, user_id: int) -> None:
        """Drop onboarding progress from region selection onward.

        Region subscriptions are wiped, so the bot must re-prompt the user.
        Keeps ``start`` (0) and ``role_set`` (10).
        """
        conn.execute(
            sqlalchemy.text(
                """
                DELETE FROM user_onboarding
                WHERE user_id = :user_id AND step_id >= :step_id
                """
            ),
            {'user_id': user_id, 'step_id': _REGION_ONBOARDING_STEP_ID},
        )
