"""move data from Cloud SQL to BigQuery for long-term storage & analysis"""

import os
import logging

import sqlalchemy

from google.cloud import bigquery
from google.cloud import secretmanager

project_id = os.environ["GCP_PROJECT"]


def get_secrets(secret_request):
    """get secret from GCP Secret Manager"""

    name = f"projects/{project_id}/secrets/{secret_request}/versions/latest"
    client = secretmanager.SecretManagerServiceClient()

    response = client.access_secret_version(name=name)

    return response.payload.data.decode("UTF-8")


def sql_connect():
    """connect to PSQL in GCP"""

    db_user = get_secrets("cloud-postgres-username")
    db_pass = get_secrets("cloud-postgres-password")
    db_name = get_secrets("cloud-postgres-db-name")
    db_conn = get_secrets("cloud-postgres-connection-name")
    db_socket_dir = "/cloudsql"

    db_config = {
        "pool_size": 5,
        "max_overflow": 0,
        "pool_timeout": 0,  # seconds
        "pool_recycle": 5,  # seconds
    }

    pool = sqlalchemy.create_engine(
        sqlalchemy.engine.url.URL(
            "postgresql+pg8000",
            username=db_user,
            password=db_pass,
            database=db_name,
            query={
                "unix_sock": "{}/{}/.s.PGSQL.5432".format(
                    db_socket_dir,
                    db_conn)
            }
        ),
        **db_config
    )
    pool.dialect.description_encoding = None

    return pool

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
    init_bq_count = None
    for row in query_initial_rows_bq:
        init_bq_count = row.count
        logging.info(f'initial rows in BQ: {init_bq_count}')

    # 2. Get the initial row count of cloud sql table
    query = '''
            SELECT
                *
            FROM
                EXTERNAL_QUERY("projects/lizaalert-bot-01/locations/europe-west3/connections/bq_to_cloud_sql",
            """SELECT count(*) AS count FROM notif_by_user__history;""")
            '''

    query_initial_rows_psql = client.query(query)
    init_psql_count = None
    for row in query_initial_rows_psql:
        init_psql_count = row.count
        logging.info(f'initial rows in psql: {init_psql_count}')

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
    moved_lines = query_move.num_dml_affected_rows
    logging.info(f'move from cloud sql to bq: {moved_lines}')

    # 4. Get the resulting row count of bq table
    query = """
        SELECT
            count(*) AS count
        FROM 
            notif_archive.notif_by_user__archive
        """

    query_resulting_rows_bq = client.query(query)
    new_bq_count = None
    for row in query_resulting_rows_bq:
        new_bq_count = row.count
        logging.info(f'resulting rows in BQ: {new_bq_count}')

    # 5. Run checkers
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

    # 5.2 should be zero
    validation_on_bq_lines = new_bq_count - moved_lines - init_bq_count

    # 5.3 should be zero
    validation_on_psql_lines = init_psql_count - moved_lines

    # 6. Delete data from cloud sql
    if validation_on_doubles == 0 and validation_on_bq_lines == 0:  # and validation_on_psql_lines:
        logging.info('validations for deletion passed')

        pool = sql_connect()
        conn = pool.connect()

        stmt = sqlalchemy.text("""DELETE FROM notif_by_user__history WHERE message_id > 0 LIMIT 100;""")
        conn.execute(stmt)

        conn.close()
        pool.dispose()

        logging.info(f'deletion from cloud sql executed')
    else:
        logging.info('validations for deletion failed')

    # 7. Get the resulting row count of cloud sql table
    query = '''
            SELECT
                *
            FROM
                EXTERNAL_QUERY("projects/lizaalert-bot-01/locations/europe-west3/connections/bq_to_cloud_sql",
            """SELECT count(*) AS count FROM notif_by_user__history;""")
            '''

    query_resulting_rows_psql = client.query(query)
    new_psql_count = 0 # noqa
    for row in query_resulting_rows_psql:
        new_psql_count = row.count
        logging.info(f'resulting rows in psql: {new_psql_count}')

    return None
