"""Topic type preference management mixin."""

import datetime

import sqlalchemy


class TopicTypeMixin:
    """User topic type preference operations."""

    def save_topic_type(self, user_id: int, topic_type_id: int) -> None:
        """Save a topic type preference for a user."""
        with self.connect() as connection:  # type: ignore[attr-defined]
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
        with self.connect() as connection:  # type: ignore[attr-defined]
            stmt = sqlalchemy.text(
                """DELETE FROM user_pref_topic_type WHERE user_id=:user_id AND topic_type_id=:type_id;"""
            )
            connection.execute(stmt, user_id=user_id, type_id=topic_type_id)

    def get_topic_types(self, user_id: int) -> list[int]:
        """Get user's saved topic type preferences."""
        with self.connect() as connection:  # type: ignore[attr-defined]
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
