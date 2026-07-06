import logging

import sqlalchemy

from _dependencies.common.commons import setup_logging
from _dependencies.common.db_client import DBClientBase
from _dependencies.common.pubsub import Ctx, pubsub_archive_notifications

setup_logging(__package__)

# How long to keep records in search_first_posts__history before purging them.
# Data older than this is deleted after each archivation cycle.
SEARCH_FIRST_POSTS_HISTORY_TTL_DAYS = 30


class DBClient(DBClientBase):
    """DB client for archive_notifications."""

    def move_notifications_to_history(self) -> None:
        """move all "completed" notifications to psql table __history"""
        with self.connect() as conn:
            # checker – gives us a minimal date in notif_by_user, which is at least 2 hours older than current
            stmt = sqlalchemy.text("""
                SELECT MIN(cl.parsed_time)
                FROM notif_by_user AS nm
                LEFT JOIN change_log AS cl
                ON nm.change_log_id=cl.id
                WHERE cl.parsed_time < NOW() - INTERVAL '2 hour' ORDER BY 1 LIMIT 1;
            """)
            oldest_date_nbu = conn.execute(stmt).scalar()
            if oldest_date_nbu is None:
                return

            logging.info(f'The oldest date in notif_by_user: {oldest_date_nbu}')

            # DEBUG 1
            stmt = sqlalchemy.text("""
                SELECT MIN(change_log_id) FROM notif_by_user;
            """)
            change_log_id = conn.execute(stmt).scalar()
            if change_log_id is None:
                return

            logging.info(f'The change_log_id to be updated in nbu: {change_log_id}')

            # migrate all records with "lowest" change_log_id from notif_by_user to notif_by_user__history
            stmt = sqlalchemy.text("""
                INSERT INTO notif_by_user__history
                    SELECT  * FROM notif_by_user
                    WHERE change_log_id = :change_log_id
                    FOR UPDATE;
                --
                DELETE FROM notif_by_user
                    WHERE change_log_id = :change_log_id
            """)
            conn.execute(stmt, dict(change_log_id=change_log_id))

        pubsub_archive_notifications()

    def move_first_posts_to_history(self) -> None:
        """move first posts for completed searches to __history, then purge old history records"""
        with self.connect() as conn:
            # 1. COMPLETED SEARCHES
            stmt = sqlalchemy.text("""
                WITH moved_rows AS (
                    INSERT INTO
                        search_first_posts__history
                    (
                        SELECT
                            sfp.*
                        FROM
                            search_first_posts AS sfp
                        INNER JOIN
                            searches AS s
                        ON sfp.search_id=s.search_forum_num
                        WHERE s.status = 'НЖ' or s.status = 'НП' or s.status = 'Найден'
                            OR s.status = 'Завершен'
                    )
                    RETURNING id
                )
                DELETE FROM
                    search_first_posts
                WHERE
                    id IN (SELECT id FROM moved_rows);
            """)
            conn.execute(stmt)

            logging.info(
                'first_posts for completed searches are copied to __history and deleted from search_first_posts'
            )

            # 2. ELDER FIRST POSTS snapshots
            stmt = sqlalchemy.text("""
                WITH moved_rows AS (
                    INSERT INTO
                        search_first_posts__history
                    (
                        SELECT
                            s1.id, s1.search_id, s1.timestamp, s1.actual, s1.content_hash, s1.content,
                            s1.num_of_checks, s1.coords, s1.field_trip, s1.content_compact
                        FROM (
                            SELECT
                                *, RANK() OVER (PARTITION BY search_id ORDER BY timestamp DESC) AS rank
                            FROM
                                search_first_posts
                            ORDER BY
                                1, 2 DESC) as s1
                        WHERE rank > 2
                    )
                    RETURNING id
                )
                DELETE FROM
                    search_first_posts
                WHERE
                    id IN (SELECT id FROM moved_rows);
            """)
            conn.execute(stmt)

            logging.info(
                'first_posts for elder snapshots are copied to __history and deleted from search_first_posts'
            )

            # 3. TTL PURGE
            stmt = sqlalchemy.text("""
                DELETE FROM search_first_posts__history
                WHERE timestamp < NOW() - make_interval(days => :ttl_days)
            """)
            conn.execute(stmt, dict(ttl_days=SEARCH_FIRST_POSTS_HISTORY_TTL_DAYS))

            logging.info(
                'purged records older than %d days from search_first_posts__history',
                SEARCH_FIRST_POSTS_HISTORY_TTL_DAYS,
            )


def main(event: dict[str, bytes], context: Ctx) -> None:
    """main function"""

    db = DBClient()
    db.move_notifications_to_history()
    db.move_first_posts_to_history()
