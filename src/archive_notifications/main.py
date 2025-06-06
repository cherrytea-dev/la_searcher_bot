import logging

import sqlalchemy
from sqlalchemy.engine.base import Connection

from _dependencies.commons import setup_logging, sqlalchemy_get_pool
from _dependencies.pubsub import Ctx, pubsub_archive_notifications, pubsub_archive_to_bigquery

setup_logging()


def sql_connect() -> sqlalchemy.engine.Engine:
    return sqlalchemy_get_pool(20, 0)


def move_notifications_to_history_in_psql(conn: Connection) -> None:
    """move all "completed" notifications to psql table __history"""

    # checker – gives us a minimal date in notif_by_user, which is at least 2 hours older than current
    stmt = sqlalchemy.text("""
                        SELECT MIN(cl.parsed_time)
                        FROM notif_by_user AS nm
                        LEFT JOIN change_log AS cl
                        ON nm.change_log_id=cl.id
                        WHERE cl.parsed_time < NOW() - INTERVAL '2 hour' ORDER BY 1 LIMIT 1;
                        """)
    oldest_date_nbu = conn.execute(stmt).fetchone()[0]

    if oldest_date_nbu:
        logging.info(f'The oldest date in notif_by_user: {oldest_date_nbu}')

        # DEBUG 1
        stmt = sqlalchemy.text("""
                    SELECT MIN(mailing_id) FROM notif_by_user;
                    """)
        query_result = conn.execute(stmt).fetchone()
        logging.info(f'The mailing_id to be updated in nbu: {query_result[0]}')

        # migrate all records with "lowest" mailing_id from notif_by_user to notif_by_user__history
        stmt = sqlalchemy.text("""
            INSERT INTO notif_by_user__history
            SELECT * FROM notif_by_user
            WHERE mailing_id = (
                    SELECT MIN(mailing_id) FROM notif_by_user
                );
            """)
        conn.execute(stmt)

        # delete the old stuff
        stmt = sqlalchemy.text("""
                DELETE FROM notif_by_user
                WHERE mailing_id = (
                    SELECT MIN(mailing_id) FROM notif_by_user
                )
            """)
        conn.execute(stmt)

        pubsub_archive_notifications()
        return

    else:
        logging.info('nothing to migrate in notif_by_user')

        # checker – gives us a minimal date in notif_by_user_status, which is at least 2 days older than current
        stmt = sqlalchemy.text("""
                                    SELECT MIN(cl.parsed_time)
                                    FROM notif_by_user_status AS nm
                                    LEFT JOIN change_log AS cl
                                    ON nm.change_log_id=cl.id
                                    WHERE cl.parsed_time < NOW() - INTERVAL '2 hour' ORDER BY 1 LIMIT 1;
                                    """)
        oldest_date_nbus = conn.execute(stmt).fetchone()
        logging.info('The oldest date in notif_by_user_status: {}'.format(oldest_date_nbus[0]))

        if not oldest_date_nbus[0]:
            logging.info('nothing to migrate in notif_by_user_status')
            move_first_posts_to_history_in_psql(conn)
            pubsub_archive_to_bigquery()
            return

        logging.info('The oldest date in notif_by_user_status: {}'.format(oldest_date_nbus[0]))

        # DEBUG 1
        stmt = sqlalchemy.text("""
                                SELECT MIN(mailing_id) FROM notif_by_user_status;
                                """)
        query_result = conn.execute(stmt).fetchone()
        logging.info('The mailing_id to be updated in nbus: {}'.format(query_result[0]))

        # migrate all records with "lowest" mailing_id from notif_by_user_status to notif_by_user__history
        stmt = sqlalchemy.text("""
                        INSERT INTO notif_by_user_status__history
                        SELECT * FROM notif_by_user_status
                        WHERE mailing_id = (
                                SELECT MIN(mailing_id) FROM notif_by_user_status
                            );
                        """)
        conn.execute(stmt)

        # delete the old stuff
        stmt = sqlalchemy.text("""
                            DELETE FROM notif_by_user_status
                            WHERE mailing_id = (
                                SELECT MIN(mailing_id) FROM notif_by_user_status
                            )
                        """)
        conn.execute(stmt)

        pubsub_archive_notifications()
        return


def move_first_posts_to_history_in_psql(conn: Connection) -> None:
    """move all first posts for "completed" searches to psql table __history"""

    # 1. COMPLETED SEARCHES
    # take all the first_posts for "completed" searches and copy it to __history table
    stmt = sqlalchemy.text("""
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

                        ;""")
    # number_of_copied_rows = conn.execute(stmt).fetchone()
    conn.execute(stmt)

    logging.info('first_posts for completed searches are copied to __history')

    # delete all the copied info from search_first_posts table
    stmt = sqlalchemy.text("""
        DELETE FROM
            search_first_posts
        WHERE
            id in (
                SELECT
                    sfp.id
                FROM
                    search_first_posts AS sfp
                INNER JOIN
                    searches AS s
                ON
                    sfp.search_id=s.search_forum_num
                WHERE s.status = 'НЖ' or s.status = 'НП' or s.status = 'Найден'
                    OR s.status = 'Завершен'

        );""")
    # number_of_deleted_rows = conn.execute(stmt).fetchone()
    conn.execute(stmt)

    logging.info('first_posts for completed searches are deleted from search_first_posts')

    # 2. ELDER FIRST POSTS snapshots
    # take all the first_posts for "completed" searches and copy it to __history table
    stmt = sqlalchemy.text("""
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
                            ;""")
    # number_of_copied_rows = conn.execute(stmt).fetchone()
    conn.execute(stmt)

    logging.info('first_posts for elder snapshots are copied to __history')

    # delete all the copied info from search_first_posts table
    stmt = sqlalchemy.text("""
            DELETE FROM
                search_first_posts
            WHERE
                id in (
                    SELECT
                        s1.id
                    FROM (
                        SELECT
                            *, RANK() OVER (PARTITION BY search_id ORDER BY timestamp DESC) AS rank
                        FROM
                            search_first_posts
                        ORDER BY
                            1, 2 DESC) as s1
                    WHERE rank > 2
            );""")
    # number_of_deleted_rows = conn.execute(stmt).fetchone()
    conn.execute(stmt)

    logging.info('first_posts for elder snapshots are deleted from search_first_posts')


def main(event: dict[str, bytes], context: Ctx) -> None:
    """main function"""

    pool = sql_connect()
    with pool.connect() as conn:
        move_notifications_to_history_in_psql(conn)

    pool.dispose()
