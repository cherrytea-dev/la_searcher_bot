"""Mixin: notification statistics operations (user_notification_statistics, user_stat)."""

import sqlalchemy

from _dependencies.common.db_client import DBClientMixinBase


class NotificationStatsMixin(DBClientMixinBase):
    """DB operations on user_notification_statistics and user_stat."""

    def update_notification_statistics(self, user_id: int, value: int) -> None:
        """Update or insert notification statistics count."""
        with self.connect() as conn:
            result = conn.execute(
                sqlalchemy.text("""
                    SELECT id FROM user_notification_statistics
                    WHERE user_id=:user_id
                    FOR UPDATE;
                """),
                dict(user_id=user_id),
            ).fetchone()

            if result:
                conn.execute(
                    sqlalchemy.text("""
                        UPDATE user_notification_statistics
                        SET number_of_notifications=number_of_notifications+:add_value
                        WHERE user_id=:user_id;
                    """),
                    dict(user_id=user_id, add_value=value),
                )
            else:
                conn.execute(
                    sqlalchemy.text("""
                        INSERT INTO user_notification_statistics
                        (user_id, number_of_notifications)
                        VALUES (:user_id, :num);
                    """),
                    dict(user_id=user_id, num=value),
                )

    def record_user_stat_notifications(self, user_id: int, number_to_add: int) -> None:
        """Record +1 into user_stat for new search notifications (usability tips)."""
        with self.connect() as conn:
            conn.execute(
                sqlalchemy.text("""
                    INSERT INTO user_stat (user_id, num_of_new_search_notifs)
                    VALUES(:user_id, :number_to_add)
                    ON CONFLICT (user_id) DO
                    UPDATE SET num_of_new_search_notifs = :number_to_add +
                    (SELECT num_of_new_search_notifs from user_stat WHERE user_id = :user_id)
                    WHERE user_stat.user_id = :user_id;
                """),
                dict(user_id=int(user_id), number_to_add=int(number_to_add)),
            )
