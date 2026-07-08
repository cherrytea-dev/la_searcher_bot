"""Mixin: notification record operations (notif_by_user, user_identity_map)."""

import sqlalchemy

from _dependencies.common.db_client import DBClientMixinBase


class NotificationRecordMixin(DBClientMixinBase):
    """DB operations on notif_by_user and user_identity_map."""

    def check_user_notified(self, user_id: int, change_log_id: int) -> bool:
        """Check if a user has already been notified for a change_log entry."""
        with self.connect() as conn:
            result = conn.execute(
                sqlalchemy.text("""
                    SELECT 1 FROM notif_by_user
                    WHERE user_id=:user_id AND change_log_id=:change_log_id
                    LIMIT 1;
                """),
                dict(user_id=user_id, change_log_id=change_log_id),
            ).fetchone()
            return result is not None

    def get_message_group_count(self, user_id: int, message_type: str) -> int:
        """Get max message_group_id for a user and message type."""
        with self.connect() as conn:
            result = conn.execute(
                sqlalchemy.text("""
                    SELECT MAX(message_group_id)
                    FROM notif_by_user
                    WHERE user_id=:user_id AND message_type=:message_type
                """),
                dict(user_id=user_id, message_type=message_type),
            ).fetchone()
            return result[0] if result[0] is not None else 0

    def batch_insert_notifications(self, records: list[dict]) -> None:
        """Batch insert notification records. Each dict has keys matching notif_by_user columns."""
        if not records:
            return

        with self.connect() as conn:
            columns = ', '.join(records[0].keys())
            placeholders = ', '.join(f':{k}' for k in records[0].keys())
            stmt = sqlalchemy.text(f"""
                INSERT INTO notif_by_user ({columns})
                VALUES ({placeholders})
            """)
            for rec in records:
                conn.execute(stmt, rec)

    def resolve_messengers(self, user_ids: list[int]) -> list[tuple]:
        """Batch-resolve messengers for users from user_identity_map."""
        with self.connect() as conn:
            result = conn.execute(
                sqlalchemy.text("""
                    SELECT internal_user_id, messenger
                    FROM user_identity_map
                    WHERE internal_user_id = ANY(:user_ids)
                """),
                {'user_ids': user_ids},
            )
            return list(result.fetchall())

    def check_notification_duplicate(self, change_log_id: int, user_id: int, message_type: str, messenger: str) -> int:
        """Check if a notification record already exists (DIAG)."""
        with self.connect() as conn:
            result = conn.execute(
                sqlalchemy.text("""
                    SELECT count(*) FROM notif_by_user
                    WHERE change_log_id = :cl AND user_id = :uid
                      AND message_type = :mt AND messenger = :msgr
                      AND completed IS NULL AND cancelled IS NULL
                """),
                dict(cl=change_log_id, uid=user_id, mt=message_type, msgr=messenger),
            )
            return result.scalar()

    def get_users_with_prepared_message(self, change_log_id: int) -> list[int]:
        """Get list of user_ids who already have composed messages for this change_log."""
        with self.connect() as conn:
            query = sqlalchemy.text("""
                SELECT user_id
                FROM notif_by_user
                WHERE created IS NOT NULL
                  AND change_log_id = :change_log_id
                /*action='get_from_sql_list_of_users_with_already_composed_messages 2.0'*/ ;
            """)
            raw_data = conn.execute(query, dict(change_log_id=change_log_id)).fetchall()
            return [line[0] for line in raw_data]
