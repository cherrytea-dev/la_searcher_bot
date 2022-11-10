import os
import base64

import json
import datetime
import logging

import psycopg2

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

    # Preparing to turn to the existing pub/sub topic
    # topic_name = 'topic_notify_admin'
    topic_path = publisher.topic_path(project_id, topic_name)
    # Preparing the message
    message_json = json.dumps({'data': {'message': message}, })
    message_bytes = message_json.encode('utf-8')
    # Publishes a message
    try:
        publish_future = publisher.publish(topic_path, data=message_bytes)
        publish_future.result()  # Verify the publishing succeeded
        logging.info('Pub/sub message published from User Management: ' + message)

    except Exception as e:
        logging.error('Publish to pub/sub from User Management failed: ' + repr(e))
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


def sql_connect_by_psycopg2():
    """set the connection to psql via psycopg2"""

    db_user = get_secrets("cloud-postgres-username")
    db_pass = get_secrets("cloud-postgres-password")
    db_name = get_secrets("cloud-postgres-db-name")
    db_conn = get_secrets("cloud-postgres-connection-name")
    db_host = '/cloudsql/' + db_conn

    conn_psy = psycopg2.connect(host=db_host, dbname=db_name, user=db_user, password=db_pass)

    return conn_psy


def save_updated_status_for_user(action, user_id):
    """block, unblock or record as new user"""

    action_dict = {'block_user': 'blocked', 'unblock_user': 'unblocked', 'new': 'new', 'delete_user': 'deleted'}
    action_to_write = action_dict[action]

    # set PSQL connection & cursor
    conn = sql_connect_by_psycopg2()
    cur = conn.cursor()

    if action_to_write != 'new':
        # compose & execute the query for USERS table
        cur.execute(
            """UPDATE users SET status =%s, status_change_date=%s WHERE user_id=%s;""",
            (action_to_write, datetime.datetime.now(), user_id)
        )
        conn.commit()

    # compose & execute the query for USER_STATUSES_HISTORY table
    cur.execute(
        """INSERT INTO user_statuses_history (status, date, user_id) VALUES (%s, %s, %s);""",
        (action_to_write, datetime.datetime.now(), user_id)
    )
    conn.commit()

    # close connection & cursor
    cur.close()
    conn.close()

    return None


def save_new_user(user_id, username):
    """if the user is new – save to users table"""

    # set PSQL connection & cursor
    conn = sql_connect_by_psycopg2()
    cur = conn.cursor()

    if username == 'unknown':
        username = None

    # add the New User into table users
    cur.execute("""INSERT INTO users (user_id, username_telegram, reg_date) values (%s, %s, %s);""",
                (user_id, username, datetime.datetime.now()))
    conn.commit()

    # close connection & cursor
    cur.close()
    conn.close()

    logging.info(f'New user with id: {user_id}, username {username} saved.')

    return None


def save_default_notif_settings(user_id):
    """if the user is new – set the default notification categories in user_preferences table"""

    # set PSQL connection & cursor
    conn = sql_connect_by_psycopg2()
    cur = conn.cursor()

    # default setting is set as notifications on new searches & status changes
    cur.execute("""INSERT INTO user_preferences (user_id, preference, pref_id) values (%s, %s, %s);""",
                (user_id, 'new_searches', 0))
    conn.commit()

    cur.execute("""INSERT INTO user_preferences (user_id, preference, pref_id) values (%s, %s, %s);""",
                (user_id, 'status_changes', 1))
    conn.commit()

    cur.execute("""INSERT INTO user_preferences (user_id, preference, pref_id) values (%s, %s, %s);""",
                (user_id, 'bot_news', 20))
    conn.commit()

    # close connection & cursor
    cur.close()
    conn.close()

    logging.info(f'New user with id: {user_id}, default notif categories are set.')

    return None


def main(event, context): # noqa
    """main function"""

    try:
        received_dict = process_pubsub_message(event)
        if received_dict:

            action = received_dict['action']

            if action in {'block_user', 'unblock_user', 'new', 'delete_user'}:

                curr_user_id = received_dict['info']['user']
                save_updated_status_for_user(action, curr_user_id)

                if action == 'new':

                    username = received_dict['info']['username']
                    # save in table users
                    save_new_user(curr_user_id, username)
                    # save in table user_preferences
                    save_default_notif_settings(curr_user_id)

    except Exception as e:
        logging.error('User management script failed:' + repr(e))
        logging.exception(e)

        # TODO: it's only debug
        message_to_admin = 'ERROR in user_management: ' + repr(e)
        notify_admin(message_to_admin)

    return None
