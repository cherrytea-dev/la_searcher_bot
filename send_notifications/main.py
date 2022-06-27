import ast
import time
import datetime
import os
import base64
import logging
import json
import psycopg2

from telegram import Bot, error

from google.cloud import secretmanager
from google.cloud import pubsub_v1

project_id = os.environ["GCP_PROJECT"]
client = secretmanager.SecretManagerServiceClient()
publisher = pubsub_v1.PublisherClient()

# To get rid of telegram "Retrying" Warning logs, which are shown in GCP Log Explorer as Errors.
# Important – these are not errors, but jest informational warnings that there were retries, that's why we exclude them
logging.getLogger("telegram.vendor.ptb_urllib3.urllib3").setLevel(logging.ERROR)
logger = logging.getLogger(__name__)

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


def sql_connect_by_psycopg2():
    """connect to GCP SLQ via PsycoPG2"""

    try:
        db_user = get_secrets("cloud-postgres-username")
        db_pass = get_secrets("cloud-postgres-password")
        db_name = get_secrets("cloud-postgres-db-name")
        db_conn = get_secrets("cloud-postgres-connection-name")
        db_host = '/cloudsql/' + db_conn

        conn_psy = psycopg2.connect(host=db_host, dbname=db_name, user=db_user, password=db_pass)
        conn_psy.autocommit = True

        logging.info('sql connection set via psycopg2')

    except Exception as e:
        logging.error('failed to set sql connection by psycopg2')
        logging.exception(e)
        conn_psy = None

    return conn_psy


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


def check_for_notifs_to_send(cur):
    """return a notification which should be sent"""

    # TODO: can "doubling" be done not dynamically but as a field of table?
    sql_text_psy = """
                    SELECT 
                        message_id,
                        user_id,
                        created,
                        completed,
                        cancelled, 
                        message_content, 
                        message_type, 
                        message_params, 
                        message_group_id,
                        change_log_id,
                        mailing_id,
                        (CASE 
                            WHEN DENSE_RANK() OVER (
                                PARTITION BY change_log_id, user_id, message_type ORDER BY mailing_id) + 
                                DENSE_RANK() OVER (
                                PARTITION BY change_log_id, user_id, message_type ORDER BY mailing_id DESC) 
                                -1 = 1 
                            THEN 'no_doubling' 
                            ELSE 'doubling' 
                        END) AS doubling, 
                        failed 
                    FROM
                    notif_by_user
                    WHERE 
                        completed IS NULL AND
                        cancelled IS NULL
                    ORDER BY 1
                    LIMIT 1 
                    /*action='check_for_notifs_to_send 2.0' */
                    ;
                    """

    cur.execute(sql_text_psy)
    notification = cur.fetchone()

    return notification


def send_single_message(bot, user_id, message_content, message_params, message_type):
    """send one message to telegram"""

    if message_params:
        # convert string to bool
        if 'disable_web_page_preview' in message_params:
            message_params['disable_web_page_preview'] = (message_params['disable_web_page_preview'] == 'True')

    try:

        if message_type == 'text':
            bot.sendMessage(chat_id=user_id, text=message_content, **message_params)

        elif message_type == 'coords':
            bot.sendLocation(chat_id=user_id, **message_params)

        result = 'completed'

        logging.info(f'success sending a msg to telegram user={user_id}')

    except error.BadRequest as e:

        result = 'cancelled_bad_request'

        logging.info(f'failed sending to telegram due to Bad Request user={user_id}, message={message_content}')
        logging.error(e)

    except error.RetryAfter as e:

        result = 'failed_flood_control'

        logging.info(f'"flood control": failed sending to telegram user={user_id}, message={message_content}')
        logging.error(e)
        time.sleep(5)  # TODO: temp placeholder to wait 5 seconds

    except Exception as e:  # when sending to telegram fails by other reasons

        error_description = str(e)

        # if user blocked the bot OR user is deactivated (deleted telegram account)
        if error_description.find('bot was blocked by the user') != -1 \
                or error_description.find('user is deactivated') != -1:
            if error_description.find('bot was blocked by the user') != -1:
                action = 'block_user'
            else:
                action = 'delete_user'
            message_for_pubsub = {'action': action, 'info': {'user': user_id}}
            publish_to_pubsub('topic_for_user_management', message_for_pubsub)

            logging.info(f'Identified user id {user_id} to do {action}')
            result = 'cancelled'

        else:
            result = 'failed'

            logging.info(f'failed sending to telegram user={user_id}, message={message_content}')
            logging.exception(error_description)

    return result


def save_sending_status_to_notif_by_user(cur, message_id, result):
    """save the telegram sending status to sql table notif_by_user"""

    if result[0:10] == 'cancelled':
        result = result[0:10]
    elif result[0:7] == 'failed':
        result = result[0:7]

    if result in {'completed', 'cancelled', 'failed'}:


        sql_text_psy = f"""
                    UPDATE notif_by_user
                    SET {result} = %s
                    WHERE message_id = %s;
                    /*action='save_sending_status_to_notif_by_user_{result}' */
                    ;"""

        cur.execute(sql_text_psy, (datetime.datetime.now(), message_id))

    return None


def iterate_over_notifications(bot, script_start_time):
    """iterate over all available notifications, finishes if timeout is met or no new notifications"""

    # TODO: to think to increase 30 seconds to 500 seconds - if helpful
    custom_timeout = 120  # seconds, after which iterations should stop to prevent the whole script timeout

    with sql_connect_by_psycopg2() as conn_psy, conn_psy.cursor() as cur:

        trigger_to_continue_iterations = True
        while trigger_to_continue_iterations:

            # analytics on sending speed - start for every user/notification
            analytics_sm_start = datetime.datetime.now()
            analytics_iteration_start = datetime.datetime.now()
            logging.info('time: -------------- loop start -------------')
            analytics_sql_start = datetime.datetime.now()

            # check if there are any non-notified users
            message_to_send = check_for_notifs_to_send(cur)

            analytics_sql_finish = datetime.datetime.now()
            analytics_sql_duration = round((analytics_sql_finish -
                                            analytics_sql_start).total_seconds(), 2)
            logging.info('time: reading sql=' + str(analytics_sql_duration))
            logging.info(str(message_to_send))

            if message_to_send:
                doubling_trigger = message_to_send[11]

                if doubling_trigger == 'no_doubling':

                    user_id = message_to_send[1]
                    message_id = message_to_send[0]
                    message_type = message_to_send[6]
                    message_params = ast.literal_eval(message_to_send[7]) if message_to_send[7] else {}

                    message_content = message_to_send[5]
                    # limitation to avoid telegram "message too long"
                    if message_content and len(message_content) > 3000:
                        message_content = f'{message_content[:1500]}...{message_content[-1000:]}'

                    analytics_pre_sending_msg = datetime.datetime.now()

                    # TODO: to introduce check of the status for the Coord_change and field_trip:
                    #  if status != 'Ищем': do not send, result = 'cancelled'
                    result = send_single_message(bot, user_id, message_content, message_params, message_type)

                    analytics_send_finish = datetime.datetime.now()
                    analytics_send_start_finish = round((analytics_send_finish -
                                                         analytics_pre_sending_msg).total_seconds(), 2)
                    logging.info(f'time: {analytics_send_start_finish} – outer sending msg')

                else:
                    result = 'cancelled_due_to_doubling'

                analytics_save_sql_start = datetime.datetime.now()

                # save result of sending telegram notification into SQL notif_by_user
                save_sending_status_to_notif_by_user(cur, message_id, result)

                analytics_after_double_saved_in_sql = datetime.datetime.now()

                analytics_save_sql_duration = round((analytics_after_double_saved_in_sql -
                                                     analytics_save_sql_start).total_seconds(), 2)
                logging.info(f'time: {analytics_save_sql_duration} – saving to sql')

                analytics_doubling_checked_saved_to_sql = round((analytics_after_double_saved_in_sql -
                                                                 analytics_pre_sending_msg).total_seconds(), 2)
                logging.info(f'time: check -> save to sql: {analytics_doubling_checked_saved_to_sql}')

                # analytics on sending speed - finish for every user/notification
                analytics_sm_finish = datetime.datetime.now()
                analytics_sm_duration = (analytics_sm_finish - analytics_sm_start).total_seconds()
                analytics_notif_times.append(analytics_sm_duration)

                no_new_notifications = False

            else:
                # wait for 10 seconds – maybe any new notification will pop up
                time.sleep(10)

                message_to_send = check_for_notifs_to_send(cur)

                no_new_notifications = False if message_to_send else True

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

        cur.close()
    conn_psy.close()

    return None


def main_func(event, context):  # noqa
    """main function"""

    global analytics_notif_times

    # timer is needed to finish the script if it's already close to timeout
    script_start_time = datetime.datetime.now()

    message_from_pubsub = process_pubsub_message(event)
    logging.info(f'received message from pub/sub: {message_from_pubsub}')

    bot_token = get_secrets("bot_api_token__prod")
    bot = Bot(token=bot_token)

    iterate_over_notifications(bot, script_start_time)

    # send statistics on number of messages and sending speed
    if analytics_notif_times:
        len_n = len(analytics_notif_times)
        average = sum(analytics_notif_times) / len_n
        message = f'[send_notifs] Analytics: num of messages {len_n}, average time {round(average, 2)} seconds, ' \
                  f'total time {round(sum(analytics_notif_times), 1)} seconds'
        notify_admin(message)
        logging.info(message)

        analytics_notif_times = []

    logging.info('script finished')

    return None
