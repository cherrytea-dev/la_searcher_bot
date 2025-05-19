import datetime
from functools import lru_cache

import sqlalchemy
from sqlalchemy.engine import Connection
from sqlalchemy.engine.base import Engine

from _dependencies.commons import sqlalchemy_get_pool

from .commons import Search


class DBClient:
    def __init__(self, db: Engine) -> None:
        self._db = db

    def connect(self) -> Connection:
        return self._db.connect()

    def get_random_hidden_topic_id(self) -> int | None:
        with self.connect() as conn:
            hidden_topic = conn.execute("""
                SELECT h.search_forum_num
                FROM search_health_check AS h
                    LEFT JOIN searches AS s
                    ON h.search_forum_num=s.search_forum_num
                WHERE 
                    h.status = 'hidden'
                    and s.status in ('Ищем', 'Возобновлен')
                ORDER BY RANDOM() LIMIT 1;
                /*action='get_one_hidden_topic' */;
                                        """).fetchone()

            return int(hidden_topic[0]) if hidden_topic else None

    def delete_search_health_check(self, search_id: int) -> None:
        with self.connect() as conn:
            stmt = sqlalchemy.text("""
                DELETE FROM search_health_check WHERE search_forum_num=:a;
                                   """)
            conn.execute(stmt, a=search_id)

    def write_search_health_check(self, search_id: int, visibility: str) -> None:
        with self.connect() as conn:
            stmt = sqlalchemy.text("""
                INSERT INTO search_health_check 
                (search_forum_num, timestamp, status)
                VALUES (:a, :b, :c);
                                   """)
            conn.execute(stmt, a=search_id, b=datetime.datetime.now(), c=visibility)

    def get_list_of_topics(self) -> list[Search]:
        """get best list of searches for which first posts should be checked"""

        with self.connect() as conn:
            raw_sql_extract = conn.execute("""
                    WITH
                    s AS (SELECT search_forum_num, search_start_time, forum_folder_id FROM searches
                        WHERE status = 'Ищем'),
                    h AS (SELECT search_forum_num, status FROM search_health_check),
                    f AS (SELECT folder_id, folder_type FROM geo_folders
                        WHERE folder_type IS NULL OR folder_type = 'searches')
                    ---
                    SELECT s.search_forum_num
                    FROM s
                        LEFT JOIN h ON s.search_forum_num=h.search_forum_num
                        JOIN f ON s.forum_folder_id=f.folder_id
                    WHERE 
                        (h.status != 'deleted' AND h.status != 'hidden') 
                        OR h.status IS NULL
                    ORDER BY s.search_start_time DESC
                    /*action='get_list_of_searches_for_first_post_and_status_update 3.0' */
                    ;
                                            """).fetchall()

            # form the list-like table
            return [Search(topic_id=line[0]) for line in raw_sql_extract]

    def create_search_first_post(self, topic_id: int, act_hash: str, act_content: str) -> None:
        with self.connect() as conn:
            stmt = sqlalchemy.text("""
                INSERT INTO search_first_posts
                (search_id, timestamp, actual, content_hash, content, num_of_checks)
                VALUES (:a, :b, TRUE, :c, :d, :e);
                                    """)
            conn.execute(stmt, a=topic_id, b=datetime.datetime.now(), c=act_hash, d=act_content, e=1)

    def mark_search_first_post_as_not_actual(self, topic_id: int) -> None:
        with self.connect() as conn:
            stmt = sqlalchemy.text("""
                UPDATE search_first_posts 
                SET actual = FALSE 
                WHERE search_id = :a;
                                    """)
            conn.execute(stmt, a=topic_id)

    def get_search_first_post_actual_hash(self, topic_id: int) -> str | None:
        with self.connect() as conn:
            stmt = sqlalchemy.text("""
                SELECT content_hash, num_of_checks, content 
                FROM search_first_posts 
                WHERE
                    search_id = :a
                    AND actual = TRUE;
                            """)
            raw_data = conn.execute(stmt, a=topic_id).fetchone()
            if raw_data:
                return raw_data[0]
        return None


@lru_cache
def get_db_client() -> DBClient:
    pool = sqlalchemy_get_pool(5, 120)
    return DBClient(db=pool)
