"""Forum attribute management mixin."""

import sqlalchemy


class ForumAttributeMixin:
    """User forum attribute operations (linking forum account)."""

    def get_forum_attributes(self, user_id: int) -> tuple[str, str] | None:
        """Get user's linked forum username and ID."""
        with self.connect() as connection:  # type: ignore[attr-defined]
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
        with self.connect() as connection:  # type: ignore[attr-defined]
            stmt = sqlalchemy.text(
                """UPDATE user_forum_attributes SET status='verified'
                   WHERE user_id=:user_id and timestamp =
                   (SELECT MAX(timestamp) FROM user_forum_attributes WHERE user_id=:user_id);"""
            )
            connection.execute(stmt, user_id=user_id)
