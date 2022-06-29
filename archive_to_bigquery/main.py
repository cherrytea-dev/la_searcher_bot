"""move data from Cloud SQL to BigQuery for long-term storage & analysis"""

import logging
from google.cloud import bigquery


def main(event, context): # noqa
    """main function"""

    client = bigquery.Client()

    # 1. Get the initial row count of bq table
    query = """
        SELECT
            count(*) AS count
        FROM 
            notif_archive.notif_by_user__archive
        """

    query_initial_rows_bq = client.query(query)
    for row in query_initial_rows_bq:
        logging.info(f'initial rows in BQ: {row.count}')

    # 2. Get the initial row count of cloud sql table
    query = '''
            SELECT
                *
            FROM
                EXTERNAL_QUERY("projects/lizaalert-bot-01/locations/europe-west3/connections/bq_to_cloud_sql",
            """SELECT count(*) AS count FROM notif_by_user__history;""")
            '''

    query_initial_rows_psql = client.query(query)
    for row in query_initial_rows_psql:
        logging.info(f'initial rows in psql: {row.count}')

    # 3. Copy all the new rows from psql to bq
    query = '''
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

    query_move = client.query(query)
    result = query_move.result()  # noqa

    affected_rows = 0
    for child_job in client.list_jobs(parent_job=query_move.job_id):
        if child_job.num_dml_affected_rows is not None:
            affected_rows += child_job.num_dml_affected_rows

    logging.info("Affected rows: {}".format(affected_rows))

    logging.info(f'move from cloud sql to bq: {query_move.num_dml_affected_rows}')

    # 4. Validate that there are no doubling message_ids in the final bq table
    query = """
        SELECT
            message_id, count(*) AS count
        FROM 
            notif_archive.notif_by_user__archive
        GROUP BY 1
        HAVING count(*) > 1
        """

    query_job_final_check = client.query(query)
    for row in query_job_final_check:
        logging.info(f'final check says: {row.count}')

    # 5. Get the resulting row count of bq table
    query = """
        SELECT
            count(*) AS count
        FROM 
            notif_archive.notif_by_user__archive
        """

    query_resulting_rows_bq = client.query(query)
    for row in query_resulting_rows_bq:
        logging.info(f'resulting rows in BQ: {row.count}')

    # 6. Delete data from cloud sql
    # query = """ """

    # query_delete = client.query(query)
    # print(f'move from cloud sql to bq: {query_move}')

    return None
