import os
import logging
import sqlalchemy
import json

from google.cloud import secretmanager
from google.cloud import pubsub_v1

project_id = os.environ["GCP_PROJECT"]
client = secretmanager.SecretManagerServiceClient()
publisher = pubsub_v1.PublisherClient()


def get_secrets(secret_request):
    """get GCP secret"""

    name = f"projects/{project_id}/secrets/{secret_request}/versions/latest"
    response = client.access_secret_version(name=name)

    return response.payload.data.decode("UTF-8")


def sql_connect():
    """connect to GCP PSQL"""

    db_user = get_secrets("cloud-postgres-username")
    db_pass = get_secrets("cloud-postgres-password")
    db_name = get_secrets("cloud-postgres-db-name")
    db_conn = get_secrets("cloud-postgres-connection-name")
    db_socket_dir = "/cloudsql"

    db_config = {
        "pool_size": 20,
        "max_overflow": 0,
        "pool_timeout": 0,  # seconds
        "pool_recycle": 0,  # seconds
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


def publish_to_pubsub(topic_name, message):
    """publish a new message to pub/sub"""

    # global project_id

    topic_path = publisher.topic_path(project_id, topic_name)
    message_json = json.dumps({'data': {'message': message}, })
    message_bytes = message_json.encode('utf-8')

    try:
        publish_future = publisher.publish(topic_path, data=message_bytes)
        publish_future.result()  # Verify the publishing succeeded
        logging.info('Sent pub/sub message: ' + str(message))

    except Exception as e:
        logging.error('Not able to send pub/sub message: ' + repr(e))
        logging.exception(e)

    return None


def main(event, context):  # noqa
    """main function"""

    pool = sql_connect()
    with pool.connect() as conn:

        # checker – gives us a minimal date in notif_by_user, which is at least 2 hours older than current
        stmt = sqlalchemy.text("""
                        SELECT MIN(cl.parsed_time) 
                        FROM notif_by_user AS nm 
                        LEFT JOIN change_log AS cl 
                        ON nm.change_log_id=cl.id 
                        WHERE cl.parsed_time < NOW() - INTERVAL '2 hour' ORDER BY 1 LIMIT 1;
                        """)
        oldest_date_nbu = conn.execute(stmt).fetchone()

        if oldest_date_nbu[0]:

            logging.info('The oldest date in notif_by_user: {}'.format(oldest_date_nbu[0]))

            # DEBUG 1
            stmt = sqlalchemy.text("""
                    SELECT MIN(mailing_id) FROM notif_by_user;
                    """)
            result = conn.execute(stmt).fetchone()
            logging.info('The mailing_id to be updated in nbu: {}'.format(result[0]))

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

            publish_to_pubsub('topic_to_archive_notifs', 'go')

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

            if oldest_date_nbus[0]:

                logging.info('The oldest date in notif_by_user_status: {}'.format(oldest_date_nbus[0]))

                # DEBUG 1
                stmt = sqlalchemy.text("""
                                    SELECT MIN(mailing_id) FROM notif_by_user_status;
                                    """)
                result = conn.execute(stmt).fetchone()
                logging.info('The mailing_id to be updated in nbus: {}'.format(result[0]))

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

                publish_to_pubsub('topic_to_archive_notifs', 'go')

            else:

                publish_to_pubsub('topic_to_archive_to_bigquery', 'go')

                logging.info('nothing to migrate in notif_by_user_status')

        conn.close()
    pool.dispose()

    return None
