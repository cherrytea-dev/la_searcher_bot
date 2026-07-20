import datetime
from functools import lru_cache

import sqlalchemy

from _dependencies.common.db_client import DBClientBase

from .commons import RSSItem, Search


class DBClient(DBClientBase):
    """Legacy DBClient — now inherits from DBClientBase."""

    def get_random_hidden_topic_id(self) -> int | None:
        with self.connect() as conn:
            hidden_topic = conn.execute(
                sqlalchemy.text("""
                SELECT h.search_forum_num
                FROM search_health_check AS h
                    LEFT JOIN searches AS s
                    ON h.search_forum_num=s.search_forum_num
                WHERE 
                    h.status = 'hidden'
                    and s.status in ('Ищем', 'Возобновлен')
                ORDER BY RANDOM() LIMIT 1;
                /*action='get_one_hidden_topic' */;
                                        """)
            ).fetchone()

            return int(hidden_topic[0]) if hidden_topic else None

    def delete_search_health_check(self, search_id: int) -> None:
        with self.connect() as conn:
            stmt = sqlalchemy.text("""
                DELETE FROM search_health_check WHERE search_forum_num=:search_id;
                                   """)
            conn.execute(stmt, dict(search_id=search_id))

    def write_search_health_check(self, search_id: int, visibility: str) -> None:
        with self.connect() as conn:
            stmt = sqlalchemy.text("""
                INSERT INTO search_health_check 
                (search_forum_num, timestamp, status)
                VALUES (:search_id, :ts, :visibility);
                                   """)
            conn.execute(stmt, dict(search_id=search_id, ts=datetime.datetime.now(), visibility=visibility))

    def get_list_of_topics(self) -> list[Search]:
        """get best list of searches for which first posts should be checked"""

        with self.connect() as conn:
            raw_sql_extract = conn.execute(
                sqlalchemy.text("""
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
                                            """)
            ).fetchall()

            # form the list-like table
            return [Search(topic_id=line[0]) for line in raw_sql_extract]

    def create_search_first_post(self, topic_id: int, act_hash: str, act_content: str) -> None:
        with self.connect() as conn:
            stmt = sqlalchemy.text("""
                INSERT INTO search_first_posts
                (search_id, timestamp, actual, content_hash, content, num_of_checks)
                VALUES (:topic_id, :ts, TRUE, :hash_val, :content, :num_checks);
                                    """)
            conn.execute(
                stmt,
                dict(
                    topic_id=topic_id,
                    ts=datetime.datetime.now(),
                    hash_val=act_hash,
                    content=act_content,
                    num_checks=1,
                ),
            )

    def mark_search_first_post_as_not_actual(self, topic_id: int) -> None:
        with self.connect() as conn:
            stmt = sqlalchemy.text("""
                UPDATE search_first_posts 
                SET actual = FALSE 
                WHERE search_id = :topic_id;
                                    """)
            conn.execute(stmt, dict(topic_id=topic_id))

    def get_search_first_post_actual_hash(self, topic_id: int) -> str | None:
        with self.connect() as conn:
            stmt = sqlalchemy.text("""
                SELECT content_hash, num_of_checks, content
                FROM search_first_posts
                WHERE
                    search_id = :topic_id
                    AND actual = TRUE;
                            """)
            raw_data = conn.execute(stmt, dict(topic_id=topic_id)).fetchone()
            if raw_data:
                return raw_data[0]
        return None

    def get_search_title(self, topic_id: int) -> str | None:
        """get the current search title from the searches table"""
        with self.connect() as conn:
            stmt = sqlalchemy.text("""
                SELECT forum_search_title FROM searches WHERE search_forum_num=:topic_id;
            """)
            result = conn.execute(stmt, dict(topic_id=topic_id)).fetchone()
            return result[0] if result else None

    def save_rss_item(self, item: RSSItem) -> None:
        with self.connect() as conn:
            stmt = sqlalchemy.text("""
                INSERT INTO rss_items 
                (search_forum_num, published_at, updated_at, url, content)
                VALUES (:topic_id, :published_at, :updated_at, :url, :content);
                                   """)
            conn.execute(
                stmt,
                dict(
                    topic_id=item.topic_id,
                    published_at=item.published_at,
                    updated_at=item.updated_at,
                    url=item.item_id,
                    content=item.content,
                ),
            )

    def get_rss_item(self, item_id: str) -> RSSItem | None:
        with self.connect() as conn:
            stmt = sqlalchemy.text("""
                SELECT id, url, search_forum_num, published_at, updated_at, content 
                FROM rss_items 
                WHERE
                    url = :item_id;
                            """)
            raw_data = conn.execute(stmt, dict(item_id=item_id)).fetchone()
            if raw_data:
                return RSSItem(
                    id=raw_data[0],
                    item_id=raw_data[1],
                    topic_id=raw_data[2],
                    published_at=raw_data[3],
                    updated_at=raw_data[4],
                    content=raw_data[5],
                )
        return None


@lru_cache
def get_db_client() -> DBClient:
    return DBClient()
