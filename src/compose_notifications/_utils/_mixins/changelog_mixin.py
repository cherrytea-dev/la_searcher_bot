"""Mixin: ChangeLog operations."""

from typing import Any

import sqlalchemy

from _dependencies.common.db_client import DBClientMixinBase


class ChangeLogMixin(DBClientMixinBase):
    """DB operations on the change_log table."""

    def has_uncomposed_notifications(self) -> bool:
        """Check if there are notifications remaining to be composed."""
        with self.connect() as conn:
            result = conn.execute(
                sqlalchemy.text("""
                    SELECT 1 FROM change_log
                    WHERE notification_sent IS NULL
                    OR notification_sent = 's' LIMIT 1;
                """)
            ).fetchall()
            return bool(result)

    def select_first_change_log_record(self, record_id: int | None = None) -> list[Any]:
        """Get the first unprocessed record from change_log."""
        with self.connect() as conn:
            query = sqlalchemy.text(f"""
                SELECT search_forum_num, new_value, id, change_type
                FROM change_log
                WHERE (notification_sent IS NULL OR notification_sent = 's')
                {"AND id=:record_id" if record_id is not None else ""}
                ORDER BY id ASC
                LIMIT 1;
            """)
            params = {}
            if record_id is not None:
                params['record_id'] = record_id
            return conn.execute(query, params).fetchone()

    def mark_change_log_in_progress(self, change_log_id: int) -> None:
        """Mark change_log record as 'in progress' (s)."""
        with self.connect() as conn:
            conn.execute(
                sqlalchemy.text("""
                    UPDATE change_log SET notification_sent = 's' WHERE id = :a
                """),
                dict(a=change_log_id),
            )

    def mark_change_log_processed(self, change_log_id: int) -> None:
        """Mark change_log record as processed (y)."""
        with self.connect() as conn:
            conn.execute(
                sqlalchemy.text("""
                    UPDATE change_log SET notification_sent='y'
                    WHERE id=:change_log_id;
                """),
                dict(change_log_id=change_log_id),
            )
