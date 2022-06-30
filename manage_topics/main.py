import os
import base64

import json
import datetime
import logging

import sqlalchemy

from google.cloud import pubsub_v1
from google.cloud import secretmanager


project_id = os.environ["GCP_PROJECT"]
publisher = pubsub_v1.PublisherClient()


def process_pubsub_message(event):
    """convert incoming pub/sub message into regular data"""

    # receiving message text from pub/sub
    if 'data' in event:
        received_message_from_pubsub = base64.b64decode(event['data']).decode('utf-8')
    else:
        received_message_from_pubsub = 'I cannot read message from pub/sub'
    encoded_to_ascii = eval(received_message_from_pubsub)
    data_in_ascii = encoded_to_ascii['data']
    message_in_ascii = data_in_ascii['message']

    return message_in_ascii


def publish_to_pubsub(topic_name, message):
    """publishing a new message to pub/sub"""

    global project_id

    topic_path = publisher.topic_path(project_id, topic_name)
    message_json = json.dumps({'data': {'message': message}, })
    message_bytes = message_json.encode('utf-8')

    try:
        publish_future = publisher.publish(topic_path, data=message_bytes)
        publish_future.result()  # Verify the publishing succeeded
        logging.info('Pub/sub message published: ' + message)

    except Exception as e:
        logging.error('Publishing to pub/sub failed: ' + repr(e))
        logging.exception(e)

    return None


def notify_admin(message):
    """send the pub/sub message to Debug to Admin"""

    publish_to_pubsub('topic_notify_admin', message)

    return None


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


def save_visibility_for_topic(topic_id, visibility):
    """save in SQL if topic was deleted, hidden or unhidden"""

    try:
        pool = sql_connect()
        with pool.connect() as conn:

            # MEMO: visibility can be only:
            # 'deleted' – topic is permanently deleted
            # 'hidden' – topic is hidden from public access, can become visible in the future
            # 'ok' – regular topics with public visibility

            if 1 == 0:
                # clear the prev visibility status
                stmt = sqlalchemy.text("""DELETE FROM search_health_check WHERE search_forum_num=:a;""")
                conn.execute(stmt, a=topic_id)

                # set the new visibility status
                stmt = sqlalchemy.text("""INSERT INTO search_health_check (search_forum_num, timestamp, status) 
                                                VALUES (:a, :b, :c);""")
                conn.execute(stmt, a=topic_id, b=datetime.datetime.now(), c=visibility)

                logging.info(f'Visibility is set={visibility} for topic_id={topic_id}')
            else:
                notify_admin(f'WE FAKED VISIBILITY UPDATE: topic_id={topic_id}, visibility={visibility}')
            conn.close()
        pool.dispose()

    except Exception as e:
        logging.exception(e)

    return None


def save_status_for_topic(topic_id, status):
    """save in SQL if topic' status was updated: active search, search finished etc."""

    try:
        pool = sql_connect()
        with pool.connect() as conn:

            # MEMO: status can be:
            # 'Ищем' – active search
            # 'НЖ' – search finished, found alive
            # 'НП' – search finished, found dead
            # etc.

            # update status in change_log table
            stmt = sqlalchemy.text(
                """INSERT INTO change_log (parsed_time, search_forum_num, changed_field, new_value, parameters, 
                change_type) values (:a, :b, :c, :d, :e, :f); """)
            conn.execute(stmt, a=datetime.datetime.now(), b=topic_id, c='status_change', d=status, e='', f=1)

            # update status in searches table
            stmt = sqlalchemy.text("""UPDATE searches SET status_short=:a WHERE search_forum_num=:b;""")
            conn.execute(stmt, a=status, b=topic_id)

            logging.info(f'Status is set={status} for topic_id={topic_id}')

            conn.close()
        pool.dispose()

    except Exception as e:
        logging.exception(e)

    return None


def main(event, context): # noqa
    """main function"""

    try:
        received_dict = process_pubsub_message(event)
        if received_dict and 'topic_id' in received_dict:

            topic_id = received_dict['topic_id']

            if 'visibility' in received_dict:

                visibility = received_dict['visibility']
                save_visibility_for_topic(topic_id, visibility)

            if 'status' in received_dict:

                status = received_dict['status']
                save_status_for_topic(topic_id, status)

    except Exception as e:
        logging.error('Topic management script failed:' + repr(e))
        logging.exception(e)

        # TODO: it's only debug
        notify_admin('ERROR in manage_topics: ' + repr(e))

    return None