import datetime
from functools import lru_cache

import sqlalchemy

from _dependencies.common.db_client import DBClientBase


class DBClient(DBClientBase):
    """DB client for identify_updates_of_first_posts."""

    def get_search_status(self, search_id: int) -> str | None:
        with self.connect() as conn:
            stmt = sqlalchemy.text("""
                SELECT display_name, status, family_name, age, status
                FROM searches WHERE search_forum_num=:search_id;
            """)
            row = conn.execute(stmt, dict(search_id=search_id)).fetchone()
            return row[1] if row else None

    def is_search_status_active(self, search_id: int) -> bool:
        status = self.get_search_status(search_id)
        return status == 'Ищем'

    def save_record_in_change_log(self, search_id: int, new_value: str, changed_field: str, change_type: int) -> int:
        with self.connect() as conn:
            stmt = sqlalchemy.text("""
                INSERT INTO change_log (parsed_time, search_forum_num, changed_field, new_value, change_type)
                values (:ts, :search_id, :changed_field, :new_value, :change_type)
                RETURNING id;
            """)
            change_log_id = conn.execute(
                stmt,
                dict(
                    ts=datetime.datetime.now(),
                    search_id=search_id,
                    changed_field=changed_field,
                    new_value=new_value,
                    change_type=change_type,
                ),
            ).scalar()
            assert change_log_id is not None, f'Failed to insert change_log for search {search_id}'
            return change_log_id

    def get_actual_page_content(self, search_id: int) -> tuple[str, str | None]:
        """Returns (content, content_compact) or ('', None)."""
        with self.connect() as conn:
            stmt = sqlalchemy.text("""
                SELECT content, content_compact
                FROM search_first_posts
                WHERE search_id=:search_id AND actual = True;
            """)
            row = conn.execute(stmt, dict(search_id=search_id)).fetchone()
            if not row:
                return '', None
            return row[0], row[1]

    def save_compact_content(self, search_id: int, content_compact: str) -> None:
        with self.connect() as conn:
            stmt = sqlalchemy.text("""
                UPDATE search_first_posts
                SET content_compact=:content_compact
                WHERE search_id=:search_id AND actual = True;
            """)
            conn.execute(stmt, dict(content_compact=content_compact, search_id=search_id))

    def get_previous_page_content(self, search_id: int) -> str | None:
        with self.connect() as conn:
            stmt = sqlalchemy.text("""
                SELECT content
                FROM search_first_posts
                WHERE search_id=:search_id AND actual=False
                ORDER BY timestamp DESC;
            """)
            row = conn.execute(stmt, dict(search_id=search_id)).fetchone()
            return row[0] if row else None


@lru_cache
def get_db_client() -> DBClient:
    return DBClient()
