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
    """connect to google cloud sql"""

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
        publish_future.result()  # Verify the publishing succeeded
        logging.info(f'Sent pub/sub message: {str(message)}')

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
        logging.error('Not able to get the lists of Admins & Testers')
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

        elif result in {'cancelled_bad_request'}:
            conn_.execute(sql_text,
                          a=message_id_,
                          b='cancelled',
                          c=datetime.datetime.now(),
                          d=mailing_id_,
                          e=change_log_id_,
                          f=user_id_,
                          g=message_type_,
                          h='send_notifs, bad request')

        elif result == 'failed_flood_control':
            conn_.execute(sql_text,
                          a=message_id_,
                          b='failed',
                          c=datetime.datetime.now(),
                          d=mailing_id_,
                          e=change_log_id_,
                          f=user_id_,
                          g=message_type_,
                          h='send_notifs, flood control')

        elif result == 'cancelled_due_to_doubling':
            conn_.execute(sql_text,
                          a=message_id_,
                          b='cancelled',
                          c=datetime.datetime.now(),
                          d=mailing_id_,
                          e=change_log_id_,
                          f=user_id_,
                          g=message_type_,
                          h='send_notifs, doubling')

        else:

            logging.info(f'[send_notif]: message {message_id_}, sending status is {result} for conn')

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

    except Exception as e:  # noqa
        notify_admin(f'[send_notif]: ERR write to SQL notif_by_user_status, message_id {message_id_}, status {result}')
        logging.exception(e)

    return None


def check_for_notifs_to_send(conn):
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
                            s2.doubling,
                            s2.failed 
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
                                max(s1.event_timestamp) 
                                    FILTER (WHERE s1.event='failed') 
                                    OVER (PARTITION BY message_id) AS failed, 
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
                            s2.cancelled IS NULL
                        ORDER BY 1
                        LIMIT 1;
                        """)

    msg_w_o_notif = conn.execute(sql_text).fetchone()

    # TODO: temp debug
    logging.info(str(msg_w_o_notif))
    # TODO: temp debug

    return msg_w_o_notif


def send_single_message(bot, user_id, message_content, message_params, message_type):
    """send one message to telegram"""

    analytics_send_start = datetime.datetime.now()

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

            analytics_only_sendmessage_start = datetime.datetime.now()
            analytics_only_sendmessage_st_st = round((analytics_only_sendmessage_start -
                                                         analytics_send_start).total_seconds(), 2)
            logging.info(f'time: sendMessage: st-st duration: {analytics_only_sendmessage_st_st}')

            bot.sendMessage(chat_id=user_id,
                            text=message_content,
                            parse_mode=parse_mode, # noqa
                            disable_web_page_preview=disable_web_page_preview) # noqa

            analytics_only_sendmessage_finish = datetime.datetime.now()
            analytics_only_sendmessage_duration = round((analytics_only_sendmessage_finish -
                                             analytics_only_sendmessage_start).total_seconds(), 2)
            logging.info(f'time: sendMessage duration: {analytics_only_sendmessage_duration}')

        elif message_type == 'coords':

            bot.sendLocation(chat_id=user_id,
                             latitude=latitude, # noqa
                             longitude=longitude) # noqa

        result = 'completed'

        # TODO: temp for debug
        logging.info(f'success sending to telegram user={user_id}, message={message_content}')
        # TODO: temp for debug

    except Exception as e:  # when sending to telegram fails

        error_description = str(e)

        if error_description.find('BadRequest()') > -1:
            result = 'cancelled_bad_request'

            logging.info(f'failed sending to telegram due to Bad Request user={user_id}, message={message_content}')
            logging.error(error_description)

        elif error_description.find('Flood control exceeded') > -1:
            result = 'failed_flood_control'

            logging.info(f'"flood control": failed sending to telegram user={user_id}, message={message_content}')
            time.sleep(5)  # TODO: temp placeholder to wait 5 seconds

        # if user blocked the bot OR user is deactivated (deleted telegram account)
        elif error_description.find('bot was blocked by the user') != -1 \
                or error_description.find('user is deactivated') != -1:
            if error_description.find('bot was blocked by the user') != -1:
                action = 'block_user'
            else:
                action = 'delete_user'
            message_for_pubsub = {'action': action, 'info': {'user': user_id}}
            publish_to_pubsub('topic_for_user_management', message_for_pubsub)

            logging.info('Identified user id={} to do {}'.format(user_id, action))
            result = 'cancelled'

        else:
            result = 'failed'

            logging.info(f'failed sending to telegram user={user_id}, message={message_content}')
            logging.exception(error_description)

    analytics_send_finish = datetime.datetime.now()
    analytics_send_duration = round((analytics_send_finish -
                                    analytics_send_start).total_seconds(), 2)
    logging.info(f'time: {analytics_send_duration} – msg send script duration')

    return result


def iterate_over_notifications(bot, script_start_time):
    """iterate over all available notifications, finishes if timeout is met or no new notifications"""

    # TODO: to increase 30 seconds to 500 seconds once script will work with mani ids
    custom_timeout = 30  # seconds, after which iterations should stop to prevent the whole script timeout

    with sql_connect().connect() as conn:

        analytics_get_admins_and_testers_start = datetime.datetime.now()

        # TODO: only for DEBUG. for prod it's not needed
        list_of_admins, list_of_testers = get_list_of_admins_and_testers(conn)

        analytics_get_admins_and_testers_finish = datetime.datetime.now()

        analytics_get_admins = round((analytics_get_admins_and_testers_finish -
                                          analytics_get_admins_and_testers_start).total_seconds(), 2)
        logging.info(f'time: {analytics_get_admins} – get admins')

        # TODO: temp DEBUG
        logging.info('list of testers:')
        logging.info(list_of_testers)

        trigger_to_continue_iterations = True

        while trigger_to_continue_iterations:

            # analytics on sending speed - start for every user/notification
            analytics_sm_start = datetime.datetime.now()
            analytics_iteration_start = datetime.datetime.now()
            logging.info('time: -------------- loop start -------------')

            # TODO: to remove admin
            # check if there are any non-notified users
            msg_w_o_notif = check_for_notifs_to_send(conn)

            analytics_check_time = datetime.datetime.now()
            analytics_time_for_check = round((analytics_check_time - analytics_iteration_start).total_seconds(), 2)

            logging.info(str(msg_w_o_notif))
            logging.info(f'time: iter start -> check: {analytics_time_for_check}')

            if msg_w_o_notif:

                user_id = msg_w_o_notif[1]
                message_id = msg_w_o_notif[0]
                message_content = msg_w_o_notif[5]
                message_failed = msg_w_o_notif[12]
                message_type = msg_w_o_notif[6]
                created_time = msg_w_o_notif[2]
                how_old_is_notif = (datetime.datetime.now() - created_time).total_seconds()

                # TODO: temp condition for Admins and Testers OR the prev message delivery was FAILED
                if (message_content or message_type == 'coords') and \
                        (user_id in (list_of_admins + list_of_testers) or
                         message_failed or
                         user_id <= 367905643
                         or how_old_is_notif > 900):

                    # limitation to avoid telegram "message too long"
                    if message_content:
                        if len(message_content) > 3000:
                            p1 = message_content[:1500]
                            p2 = message_content[-1000:]
                            message_content = p1 + '...' + p2

                    message_params = ast.literal_eval(msg_w_o_notif[7])
                    # message_group_id = msg_w_o_notif[8]
                    change_log_id = msg_w_o_notif[9]
                    mailing_id = msg_w_o_notif[10]
                    doubling_trigger = msg_w_o_notif[11]

                    analytics_pre_sending_msg = datetime.datetime.now()
                    analytics_check_send = round((analytics_pre_sending_msg -
                                                  analytics_check_time).total_seconds(), 2)
                    # logging.info(f'time: {analytics_check_send} – check -> pre-sending msg')

                    # send the message to telegram if it is not a clone-message
                    if doubling_trigger == 'no_doubling':

                        result = send_single_message(bot, user_id, message_content, message_params, message_type)

                        analytics_send_finish = datetime.datetime.now()
                        analytics_send_start_finish = round((analytics_send_finish -
                                                             analytics_pre_sending_msg).total_seconds(), 2)
                        logging.info(f'time: {analytics_send_start_finish} – outer sending msg')

                    else:
                        result = 'cancelled_due_to_doubling'


                    analytics_save_sql_strart = datetime.datetime.now()

                    # save result of sending telegram notification into SQL
                    write_message_sending_status(conn, message_id, result, mailing_id,
                                                 change_log_id, user_id, message_type)

                    analytics_after_double_saved_in_sql = datetime.datetime.now()

                    analytics_save_sql_duration = round((analytics_after_double_saved_in_sql -
                                                         analytics_save_sql_strart).total_seconds(), 2)
                    logging.info(f'time: {analytics_save_sql_duration} – saving to sql')

                    analytics_doubling_checked_saved_to_sql = round((analytics_after_double_saved_in_sql -
                                                                     analytics_pre_sending_msg).total_seconds(), 2)
                    logging.info(f'time: check -> save to sql: {analytics_doubling_checked_saved_to_sql}')

                    analytics_before_send_to_admin = datetime.datetime.now()

                    # TODO: temp
                    if user_id in list_of_admins and message_content:
                        notify_admin(f'[send_notif]: user {user_id}, length ib bytes: '
                                     f'{len(message_content.encode("utf-8"))}, message:\n{message_content[0:100]}')
                    # TODO: temp

                    analytics_after_send_to_admin = datetime.datetime.now()
                    analytics_send_bytes_to_admin = round((analytics_after_send_to_admin -
                                                          analytics_before_send_to_admin).total_seconds(), 2)
                    # logging.info(f'time: send bytes to admin: {analytics_send_bytes_to_admin}')

                    # analytics on sending speed - finish for every user/notification
                    analytics_sm_finish = datetime.datetime.now()
                    analytics_sm_duration = (analytics_sm_finish - analytics_sm_start).total_seconds()
                    analytics_notif_times.append(analytics_sm_duration)

                    no_new_notifications = False

            else:
                # wait for 10 seconds – maybe any new notification will pop up
                time.sleep(10)

                msg_w_o_notif = check_for_notifs_to_send(conn)

                if msg_w_o_notif:
                    no_new_notifications = False
                else:
                    no_new_notifications = True

            # check if not too much time passed (not more than 500 seconds)
            now = datetime.datetime.now()

            if (now - script_start_time).total_seconds() > custom_timeout:
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

            analytics_end_of_iteration = datetime.datetime.now()
            analytics_iteration_duration = round((analytics_end_of_iteration -
                                                 analytics_iteration_start).total_seconds(), 2)
            logging.info(f'time: iteration duration: {analytics_iteration_duration}')

    return None


def main_func(event, context):  # noqa
    """main function"""

    global analytics_notif_times

    # timer is needed to finish the script if it's already close to timeout
    script_start_time = datetime.datetime.now()

    message_from_pubsub = process_pubsub_message(event)
    logging.info(message_from_pubsub)

    bot_token = get_secrets("bot_api_token__prod")
    bot = Bot(token=bot_token)

    iterate_over_notifications(bot, script_start_time)

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
