import ast
import time
import datetime
import os
import base64
import logging
import json
import sqlalchemy

from telegram import Bot

from google.cloud import secretmanager
from google.cloud import pubsub_v1

project_id = os.environ["GCP_PROJECT"]
client = secretmanager.SecretManagerServiceClient()
publisher = pubsub_v1.PublisherClient()

analytics_notif_times = []


def process_pubsub_message(event):
    """get message from pub/sub notification"""

    # receiving message text from pub/sub
    try:
        if 'data' in event:
            received_message_from_pubsub = base64.b64decode(event['data']).decode('utf-8')
            encoded_to_ascii = eval(received_message_from_pubsub)
            data_in_ascii = encoded_to_ascii['data']
            message_in_ascii = data_in_ascii['message']
        else:
            message_in_ascii = 'ERROR: I cannot read message from pub/sub'
    except:  # noqa
        message_in_ascii = 'ERROR: I cannot read message from pub/sub'

    return message_in_ascii


def get_secrets(secret_request):
    """get secret stored in GCP"""

    name = f"projects/{project_id}/secrets/{secret_request}/versions/latest"
    response = client.access_secret_version(name=name)

    return response.payload.data.decode("UTF-8")


def sql_connect():
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
    try:
        pool = sqlalchemy.create_engine(
            sqlalchemy.engine.url.URL(
                drivername="postgresql+pg8000",
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
        logging.info('sql connection set')

    except Exception as e:
        logging.error('sql connection was not set: ' + repr(e))
        logging.exception(e)
        pool = None

    return pool


def publish_to_pubsub(topic_name, message):
    """publish a new message to pub/sub"""

    global project_id

    topic_path = publisher.topic_path(project_id, topic_name)
    message_json = json.dumps({'data': {'message': message}, })
    message_bytes = message_json.encode('utf-8')

    try:
        publish_future = publisher.publish(topic_path, data=message_bytes)
        publish_future.result()  # Verify the publish succeeded
        logging.info('Sent pub/sub message: ' + str(message))

    except Exception as e:
        logging.error('Not able to send pub/sub message: ' + repr(e))
        logging.exception(e)

    return None


def notify_admin(message):
    """send the pub/sub message to Debug to Admin"""

    publish_to_pubsub('topic_notify_admin', message)

    return None


# TODO: temp for DEBUG
def get_list_of_admins_and_testers(conn):
    """get the list of users with admin & testers roles from PSQL"""

    list_of_admins = []
    list_of_testers = []

    try:
        user_roles = conn.execute(
            """SELECT user_id, role FROM user_roles;"""
        ).fetchall()

        for line in user_roles:
            if line[1] == 'admin':
                list_of_admins.append(line[0])
            elif line[1] == 'tester':
                list_of_testers.append(line[0])

        logging.info('Got the Lists of Admins & Testers')

    except Exception as e:
        logging.error('Not able to get the lists of Admins & Testers: ' + repr(e))
        logging.exception(e)

    return list_of_admins, list_of_testers


def write_message_sending_status(conn_, message_id_, result, mailing_id_, change_log_id_, user_id_, message_type_):
    """write to SQL table notif_by_user_status the status of individual message sent"""

    try:
        # record into SQL table notif_by_user_status
        sql_text = sqlalchemy.text("""
                    INSERT INTO notif_by_user_status (
                        message_id, 
                        event, 
                        event_timestamp,
                        mailing_id,
                        change_log_id,
                        user_id,
                        message_type,
                        context) 
                    VALUES (:a, :b, :c, :d, :e, :f, :g, :h);
                    """)

        if result in {'created', 'completed'}:
            conn_.execute(sql_text,
                          a=message_id_,
                          b=result,
                          c=datetime.datetime.now(),
                          d=mailing_id_,
                          e=change_log_id_,
                          f=user_id_,
                          g=message_type_,
                          h='send_notifs')
        else:
            # TODO: debug notify
            notify_admin('Send_notifications: message {}, sending status is {} for conn'.format(message_id_, result))
            with sql_connect().connect() as conn2:

                conn2.execute(sql_text,
                              a=message_id_,
                              b=result,
                              c=datetime.datetime.now(),
                              d=mailing_id_,
                              e=change_log_id_,
                              f=user_id_,
                              g=message_type_,
                              h='send_notifs'
                              )
            # TODO: debug notify
            notify_admin('Send_notifications: message {}, sending status is {} for conn2'.format(message_id_, result))

    except:  # noqa
        notify_admin('ERR mink write to SQL notif_by_user_status, message_id {}, status {}'.format(message_id_, result))

    return None


def check_for_notifs_to_send(conn, userid):
    """return a line with notification which was not sent"""

    sql_text = sqlalchemy.text("""
                        SELECT 
                            s2.message_id,
                            s2.user_id,
                            s2.created,
                            s2.completed,
                            s2.cancelled, 
                            nbu.message_content, 
                            nbu.message_type, 
                            nbu.message_params, 
                            nbu.message_group_id,
                            nbu.change_log_id,
                            nbu.mailing_id,
                            s2.doubling 
                        FROM
                            (SELECT DISTINCT 
                                s1.message_id, 
                                s1.user_id,
                                min(s1.event_timestamp) 
                                    FILTER (WHERE s1.event='created') 
                                    OVER (PARTITION BY message_id) AS created, 
                                max(s1.event_timestamp) 
                                    FILTER (WHERE s1.event='completed') 
                                    OVER (PARTITION BY message_id) AS completed,
                                max(s1.event_timestamp) 
                                    FILTER (WHERE s1.event='cancelled') 
                                    OVER (PARTITION BY message_id) AS cancelled, 
                                (CASE 
                                    WHEN DENSE_RANK() OVER (
                                        PARTITION BY change_log_id, user_id, message_type ORDER BY mailing_id) + 
                                        DENSE_RANK() OVER (
                                        PARTITION BY change_log_id, user_id, message_type ORDER BY mailing_id DESC) 
                                        -1 = 1 
                                    THEN 'no_doubling' 
                                    ELSE 'doubling' 
                                END) AS doubling 
                            FROM notif_by_user_status 
                            AS s1) 
                        AS s2
                        LEFT JOIN
                        notif_by_user AS nbu
                        ON s2.message_id=nbu.message_id
                        WHERE 
                            s2.completed IS NULL AND
                            s2.cancelled IS NULL AND
                            s2.user_id = :a
                        ORDER BY 1
                        LIMIT 1;
                        """)

    msg_w_o_notif = conn.execute(sql_text, a=userid).fetchone()

    # TODO: temp debug
    logging.info(str(msg_w_o_notif))
    # TODO: temp debug

    return msg_w_o_notif


def main_func(event, context):  # noqa
    """main function"""

    global analytics_notif_times

    # timer is needed to finish the script if it's already close to timeout
    script_start_time = datetime.datetime.now()

    message_from_pubsub = process_pubsub_message(event)
    logging.info(message_from_pubsub)

    bot_token = get_secrets("bot_api_token__prod")
    bot = Bot(token=bot_token)

    with sql_connect().connect() as conn:

        # TODO: only for DEBUG. for prod it's not needed
        list_of_admins, list_of_testers = get_list_of_admins_and_testers(conn)

        # TODO: DEBUG
        logging.info('list of testers:')
        logging.info(list_of_testers)

        # TODO: temp condition – to be removed after scaling
        if list_of_admins and list_of_testers:
            for user in (list_of_admins + list_of_testers):

                # analytics on sending speed - start for every user/notification
                analytics_sm_start = datetime.datetime.now()

                trigger_to_continue_iterations = True

                while trigger_to_continue_iterations:

                    # TODO: to remove admin
                    # check if there are any non-notified users
                    msg_w_o_notif = check_for_notifs_to_send(conn, user)

                    logging.info(str(msg_w_o_notif))

                    if msg_w_o_notif:

                        user_id = msg_w_o_notif[1]
                        message_id = msg_w_o_notif[0]
                        message_content = msg_w_o_notif[5]

                        if message_content:

                            # limitation to avoid telegram "message too long"
                            if len(message_content) > 3000:
                                p1 = message_content[:1500]
                                p2 = message_content[-1000:]
                                message_content = p1 + p2

                        message_type = msg_w_o_notif[6]
                        message_params = ast.literal_eval(msg_w_o_notif[7])
                        message_group_id = msg_w_o_notif[8]
                        change_log_id = msg_w_o_notif[9]
                        mailing_id = msg_w_o_notif[10]
                        doubling_trigger = msg_w_o_notif[11]

                        if doubling_trigger == 'no_doubling':

                            if 'parse_mode' in message_params:
                                parse_mode = message_params['parse_mode']
                            if 'disable_web_page_preview' in message_params:
                                disable_web_page_preview_text = message_params['disable_web_page_preview']
                                if disable_web_page_preview_text == 'no_preview':
                                    disable_web_page_preview = True
                                else:
                                    disable_web_page_preview = False

                            if 'latitude' in message_params:
                                latitude = message_params['latitude']
                            if 'longitude' in message_params:
                                longitude = message_params['longitude']

                            try:

                                if message_type == 'text':

                                    bot.sendMessage(chat_id=user_id,
                                                    text=message_content,
                                                    parse_mode=parse_mode,
                                                    disable_web_page_preview=disable_web_page_preview)

                                elif message_type == 'coords':

                                    bot.sendLocation(chat_id=user_id,
                                                     latitude=latitude,
                                                     longitude=longitude)

                                result = 'completed'

                            except Exception as e:  # when sending to telegram fails

                                result = 'failed'
                                logging.exception(repr(e))

                        else:  # it is when doubling_trigger == 'doubling'

                            result = 'cancelled'

                        try:
                            sql_text = sqlalchemy.text("""
                                            INSERT INTO notif_by_user_status (
                                                message_id, 
                                                event, 
                                                event_timestamp,
                                                mailing_id,
                                                change_log_id,
                                                user_id,
                                                message_type,
                                                context) 
                                            VALUES (:a, :b, :c, :d, :e, :f, :g, :h);
                                            """)

                            conn.execute(sql_text,
                                         a=message_id,
                                         b=result,
                                         c=datetime.datetime.now(),
                                         d=mailing_id,
                                         e=change_log_id,
                                         f=user_id,
                                         g=message_type,
                                         h='send_notif'
                                         )

                        except Exception as e:

                            notify_admin('ERROR IN SENDING NOTIFICATIONS')
                            logging.error(repr(e))

                        # check if something remained to send
                        msg_w_o_notif = check_for_notifs_to_send(conn, user)

                        if not msg_w_o_notif:

                            # wait for 10 seconds – maybe any new notification will pop up
                            time.sleep(10)

                            msg_w_o_notif = check_for_notifs_to_send(conn, user)

                            if msg_w_o_notif:
                                no_new_notifications = False
                            else:
                                no_new_notifications = True

                        else:
                            no_new_notifications = False

                    else:
                        no_new_notifications = True

                    # check if not too much time passed (not more than 500 seconds)
                    now = datetime.datetime.now()
                    if (now - script_start_time).total_seconds() > 30:
                        timeout = True
                    else:
                        timeout = False

                    # final decision if while loop should be continued
                    if not no_new_notifications and not timeout:
                        trigger_to_continue_iterations = True
                    else:
                        trigger_to_continue_iterations = False

                    if not no_new_notifications and timeout:
                        publish_to_pubsub('topic_to_send_notifications', 'next iteration')

                # analytics on sending speed - finish for every user/notification
                analytics_sm_finish = datetime.datetime.now()
                analytics_sm_duration = (analytics_sm_finish - analytics_sm_start).total_seconds()
                analytics_notif_times.append(analytics_sm_duration)

    # send statistics on number of messages and sending speed
    if analytics_notif_times:
        len_n = len(analytics_notif_times)
        average = sum(analytics_notif_times) / len_n
        message = f'[send_notifs] Analytics: num of messages {len_n}, average time {round(average, 1)} seconds, ' \
                  f'total time {round(sum(analytics_notif_times), 1)} seconds'
        notify_admin(message)
        logging.info(message)

        analytics_notif_times = []

    logging.info('script finished')

    return None
