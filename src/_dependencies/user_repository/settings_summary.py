"""Settings summary mixin — consolidated."""

import sqlalchemy

from _dependencies.common.db_client import DBClientMixinBase
from _dependencies.models import UserSettingsSummary


class SettingsSummaryMixin(DBClientMixinBase):
    """User settings summary operations."""

    def get_settings_summary(self, user_id: int) -> UserSettingsSummary | None:
        """Get a summary of which settings the user has configured."""
        with self.connect() as connection:
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
            result = connection.execute(stmt, dict(user_id=user_id))
            raw_data = result.fetchone()
            return UserSettingsSummary(*raw_data) if raw_data else None
