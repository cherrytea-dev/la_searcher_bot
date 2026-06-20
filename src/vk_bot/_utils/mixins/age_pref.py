"""Age preference management mixin."""

import datetime

import sqlalchemy

from ..database_common import AgePeriod


class AgePrefMixin:
    """User age period preference operations."""

    def save_age_preference(self, user_id: int, period: AgePeriod) -> None:
        """Save an age period preference for a user."""
        with self.connect() as connection:  # type: ignore[attr-defined]
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
        with self.connect() as connection:  # type: ignore[attr-defined]
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
        with self.connect() as connection:  # type: ignore[attr-defined]
            stmt = sqlalchemy.text("""SELECT period_min, period_max FROM user_pref_age WHERE user_id=:user_id;""")
            result = connection.execute(stmt, user_id=user_id)
            return result.fetchall()
