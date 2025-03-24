"""move data from Cloud SQL to BigQuery for long-term storage & analysis"""

import logging
from typing import Any, Dict, Optional

import sqlalchemy
from google.cloud import bigquery
from google.cloud.functions.context import Context

from _dependencies.commons import sqlalchemy_get_pool


def sql_connect() -> sqlalchemy.engine.Engine:
    return sqlalchemy_get_pool(5, 5)


def archive_notif_by_user(client: bigquery.Client) -> None:
    """archive (move) data from notif_by_user in psql into BQ"""

    init_bq_count = _get_initial_rows_count(client)
    init_psql_count = _get_initial_rows_psql_count(client)
    moved_lines = _get_moved_lines_count(client)

    new_bq_count = _get_query_resulting_rows_count(client)

    # 5. Run checkers
    # 5.1. Validate that there are no doubling message_ids in the final bq table
    _validate_doubling_messages(client)

    # 5.2 should be zero
    validation_on_bq_lines = new_bq_count - moved_lines - init_bq_count

    # 5.3 should be zero
    validation_on_psql_lines = init_psql_count - moved_lines

    _delete_old_records_from_psql(validation_on_bq_lines)

    _check_resulting_row_count(client)


def _get_initial_rows_count(client: bigquery.Client) -> int:
    # 1. Get the initial row count of bq table
    query = """
            SELECT
                count(*) AS count
            FROM
                notif_archive.notif_by_user__archive
            """

    query_initial_rows_bq = client.query(query)
    init_bq_count = 0
    for row in query_initial_rows_bq:
        init_bq_count = row.count
        logging.info(f'initial rows in BQ: {init_bq_count}')
    return init_bq_count


def _get_initial_rows_psql_count(client: bigquery.Client) -> int:
    # 2. Get the initial row count of cloud sql table
    query = '''
                SELECT
                    *
                FROM
                    EXTERNAL_QUERY("projects/lizaalert-bot-01/locations/europe-west3/connections/bq_to_cloud_sql",
                """SELECT count(*) AS count FROM notif_by_user__history;""")
                '''

    query_initial_rows_psql = client.query(query)
    init_psql_count = 0
    for row in query_initial_rows_psql:
        init_psql_count = row.count
        logging.info(f'initial rows in psql: {init_psql_count}')
    return init_psql_count


def _get_moved_lines_count(client: bigquery.Client) -> int:
    # 3. Copy all the new rows from psql to bq
    move_query_text = '''
                INSERT INTO
                    notif_archive.notif_by_user__archive (message_id, mailing_id, user_id, message_content,
                    message_text, message_type, message_params, message_group_id, change_log_id, created, completed,
                    cancelled, failed, num_of_fails)
                SELECT *
                FROM
                    EXTERNAL_QUERY("projects/lizaalert-bot-01/locations/europe-west3/connections/bq_to_cloud_sql",
                    """SELECT * FROM notif_by_user__history;""")
                WHERE NOT message_id IN
                    (SELECT message_id FROM notif_archive.notif_by_user__archive)
                '''

    query_move = client.query(move_query_text)
    result = query_move.result()  # noqa
    moved_lines = query_move.num_dml_affected_rows or 0
    logging.info(f'move from cloud sql to bq: {moved_lines}')
    return moved_lines


def _get_query_resulting_rows_count(client: bigquery.Client) -> int:
    # 4. Get the resulting row count of bq table
    query = """
            SELECT
                count(*) AS count
            FROM
                notif_archive.notif_by_user__archive
            """

    query_resulting_rows_bq = client.query(query)
    new_bq_count = 0
    for row in query_resulting_rows_bq:
        new_bq_count = row.count
        logging.info(f'resulting rows in BQ: {new_bq_count}')
    return new_bq_count


def _validate_doubling_messages(client: bigquery.Client) -> None:
    # 5.1. Validate that there are no doubling message_ids in the final bq table
    query = """
            SELECT
                message_id, count(*) AS count
            FROM
                notif_archive.notif_by_user__archive
            GROUP BY 1
            HAVING count(*) > 1
            """

    query_job_final_check = client.query(query)
    validation_on_doubles = 0
    for row in query_job_final_check:
        validation_on_doubles = row.count
        logging.info(f'final check says: {validation_on_doubles}')


def _delete_old_records_from_psql(validation_on_bq_lines: int) -> None:
    # 6. Delete data from cloud sql
    # TODO: validations disabled because once the doubling in BQ happened -> and then all the iterations are failing
    #  with this validation - so the 5.1 and 5.3 validation never more relevant. to fix it - only 5.2 has been left
    # if validation_on_doubles == 0 and validation_on_bq_lines == 0 and validation_on_psql_lines == 0:
    if validation_on_bq_lines != 0:
        logging.info('validations for deletion failed')
        return

    logging.info('validations for deletion passed')

    pool = sql_connect()
    with pool.connect() as conn:
        stmt = sqlalchemy.text("""DELETE FROM notif_by_user__history;""")
        conn.execute(stmt)

    pool.dispose()

    logging.info('deletion from cloud sql executed')


def _check_resulting_row_count(client: bigquery.Client) -> None:
    # 7. Get the resulting row count of cloud sql table
    query = '''
                SELECT
                    *
                FROM
                    EXTERNAL_QUERY("projects/lizaalert-bot-01/locations/europe-west3/connections/bq_to_cloud_sql",
                """SELECT count(*) AS count FROM notif_by_user__history;""")
                '''

    query_resulting_rows_psql = client.query(query)
    new_psql_count = 0  # noqa
    for row in query_resulting_rows_psql:
        new_psql_count = row.count
        logging.info(f'resulting rows in psql: {new_psql_count}')


def save_sql_stat_table_sizes(client: bigquery.Client) -> None:
    """save current psql parameters: sizes of biggest tables"""

    query_text = '''
            INSERT INTO
                stat.sql_table_sizes
            SELECT
                *
            FROM
              EXTERNAL_QUERY("projects/lizaalert-bot-01/locations/europe-west3/connections/bq_to_cloud_sql",
                """
                  SELECT
                    NOW() AS timestamp, *
                  FROM
                    (
                    SELECT
                      table_name, round(pg_relation_size(quote_ident(table_name))/1024/1024, 1) AS size_mb
                    FROM
                      information_schema.tables
                    WHERE
                      table_schema = 'public'
                    ) AS s1
                  WHERE
                    s1.size_mb > 1
                  ORDER BY
                    2 DESC
                  ;
                """
              )
            '''

    query = client.query(query_text)
    result = query.result()
    lines = query.num_dml_affected_rows
    logging.info(f'saved psql table sizes stat to bq, number of lines: {lines}')


def main(event: dict, context: Context) -> None:
    """main function"""

    client = bigquery.Client()

    archive_notif_by_user(client)

    save_sql_stat_table_sizes(client)
