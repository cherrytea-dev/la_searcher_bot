"""Send the prepared notifications to users (text and location) via Telegram"""

import ast
import datetime
import logging
import time
from concurrent.futures import ThreadPoolExecutor, wait
from dataclasses import dataclass, field
from typing import Any, List

import requests
from google.cloud.functions.context import Context
from psycopg2.extensions import connection, cursor

from _dependencies.cloud_func_parallel_guard import check_and_save_event_id
from _dependencies.commons import (
    Topics,
    get_app_config,
    publish_to_pubsub,
    setup_google_logging,
    sql_connect_by_psycopg2,
)
from _dependencies.misc import (
    generate_random_function_id,
    get_change_log_update_time,
    get_triggering_function,
    notify_admin,
    process_pubsub_message_v2,
    save_sending_status_to_notif_by_user,
    tg_api_main_account,
)
from _dependencies.telegram_api_wrapper import TGApiBase

setup_google_logging()

FUNC_NAME = 'send_notifications'
# To get rid of telegram "Retrying" Warning logs, which are shown in GCP Log Explorer as Errors.
# Important – these are not errors, but just informational warnings that there were retries, that's why we exclude them
logging.getLogger('telegram.vendor.ptb_urllib3.urllib3').setLevel(logging.ERROR)
logger = logging.getLogger(__name__)

SCRIPT_SOFT_TIMEOUT_SECONDS = 60  # after which iterations should stop to prevent the whole script timeout
INTERVAL_TO_CHECK_PARALLEL_FUNCTION_SECONDS = 70  # window within which we check for started parallel function
SLEEP_TIME_FOR_NEW_NOTIFS_RECHECK_SECONDS = 5
MESSAGES_BATCH_SIZE = 100
WORKERS_COUNT = 8


@dataclass
class TimeAnalytics:
    script_start_time: datetime.datetime = field(default_factory=datetime.datetime.now)
    notif_times: list[float] = field(default_factory=list)
    delays: list[float] = field(default_factory=list)
    parsed_times: list[float] = field(default_factory=list)


@dataclass
class MessageToSend:
    message_id: int
    user_id: int
    created: datetime.datetime
    completed: datetime.datetime | None
    cancelled: datetime.datetime | None
    message_content: str
    message_type: str
    message_params: str
    message_group_id: int | None
    change_log_id: int
    mailing_id: int
    failed: datetime.datetime | None


def get_notifs_to_send(cur: cursor, select_doubling: bool) -> list[MessageToSend]:
    """return a notification which should be sent"""

    # TODO: can "doubling" calculation be done not dynamically but as a field of table?
    # TODO just use constraints on table and fix compose_notifications
    duplicated_notifications_query = """

                            SELECT
                                change_log_id, user_id, message_type
                            FROM
                                notif_by_user
                            WHERE 
                                completed IS NULL AND
                                cancelled IS null
                            group by change_log_id, user_id, message_type 
                            having count(message_id) > 1

                                    """

    notifications_query = f"""
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
                        failed 
                    FROM
                        notif_by_user
                    WHERE 
                        completed IS NULL AND
                        cancelled IS NULL AND
                        (failed IS NULL OR failed < %s) AND
                        (change_log_id, user_id, message_type) {"IN" if select_doubling else "NOT IN"} (
                            {duplicated_notifications_query}
                        )
                    ORDER BY user_id
                    LIMIT {MESSAGES_BATCH_SIZE}
                    FOR NO KEY UPDATE
 
                    /*action='check_for_notifs_to_send 3.0' */
                    ;
                    """

    delay_to_retry_send_failed_messages = datetime.timedelta(minutes=5)
    cur.execute(notifications_query, (datetime.datetime.now() - delay_to_retry_send_failed_messages,))
    notifications = cur.fetchall()
    return [MessageToSend(*notification) for notification in notifications]


def check_for_number_of_notifs_to_send(cur: cursor) -> int:
    """return a number of notifications to be sent"""

    sql_text_psy = """
                    WITH notification AS (
                    SELECT
                        DISTINCT change_log_id, user_id, message_type
                    FROM
                        notif_by_user
                    WHERE 
                        completed IS NULL AND
                        cancelled IS NULL
                    )

                    SELECT
                        count(*)
                    FROM
                        notification
                    /*action='check_for_number_of_notifs_to_send' */
                    ;
                    """

    cur.execute(sql_text_psy)
    res = cur.fetchone()
    num_of_notifs = int(res[0]) if res else 0

    return num_of_notifs


def send_single_message(tg_api: TGApiBase, message_to_send: MessageToSend) -> str | None:
    """send one message to telegram"""

    message_content = message_to_send.message_content
    message_params_str = message_to_send.message_params
    user_id = message_to_send.user_id

    # limitation to avoid telegram "message too long"
    if message_content and len(message_content) > 3000:
        message_content = f'{message_content[:1500]}...{message_content[-1000:]}'

    message_params: dict[str, Any] = ast.literal_eval(message_params_str) if message_params_str else {}
    if message_params:
        # convert string to bool
        if 'disable_web_page_preview' in message_params:
            message_params['disable_web_page_preview'] = message_params['disable_web_page_preview'] == 'True'

    if message_to_send.message_type == 'text':
        message_params['chat_id'] = user_id
        message_params['text'] = message_content
        return tg_api.send_message(message_params)

    elif message_to_send.message_type == 'coords':
        return tg_api.send_location(user_id, message_params['latitude'], message_params['longitude'])
    else:
        raise ValueError(f'unknown message_type: {message_to_send.message_type}')


def seconds_between(datetime1: datetime.datetime, datetime2: datetime.datetime | None = None) -> float:
    delta = datetime1 - (datetime2 or datetime.datetime.now())
    return abs(delta.total_seconds())


def seconds_between_round_2(datetime1: datetime.datetime, datetime2: datetime.datetime | None = None) -> float:
    return round(seconds_between(datetime1, datetime2), 2)


def time_is_out(start: datetime.datetime) -> bool:
    # check if not too much time passed from start to now
    delta = datetime.datetime.now() - start
    return delta.total_seconds() > SCRIPT_SOFT_TIMEOUT_SECONDS


def iterate_over_notifications(
    session: requests.Session,
    function_id: int,
    time_analytics: TimeAnalytics,
) -> list[int]:
    """iterate over all available notifications, finishes if timeout is met or no new notifications"""

    set_of_change_ids: set[int] = set()

    tg_api = tg_api_main_account()
    with (
        sql_connect_by_psycopg2() as conn_psy,
        conn_psy.cursor() as cur,
        ThreadPoolExecutor(max_workers=WORKERS_COUNT) as executor,
    ):
        is_first_wait = True
        while True:
            # analytics on sending speed - start for every user/notification
            _process_doubling_messages(cur)

            analytics_sql_start = datetime.datetime.now()

            # check if there are any non-notified users
            messages = get_notifs_to_send(cur, select_doubling=False)
            analytics_sql_duration = seconds_between_round_2(analytics_sql_start)
            logging.debug(f'time: {analytics_sql_duration:.2f} – reading sql')

            if not messages:
                if not is_first_wait:
                    break
                time.sleep(SLEEP_TIME_FOR_NEW_NOTIFS_RECHECK_SECONDS)
                is_first_wait = False
                continue

            futures = [
                executor.submit(
                    _process_message_sending,
                    tg_api,
                    time_analytics,
                    set_of_change_ids,
                    conn_psy,
                    message_to_send,
                )
                for message_to_send in messages
            ]
            wait(futures)

            if time_is_out(time_analytics.script_start_time):
                if get_notifs_to_send(cur, select_doubling=False):
                    message_for_pubsub = {'triggered_by_func_id': function_id, 'text': 'next iteration'}
                    publish_to_pubsub(Topics.topic_to_send_notifications, message_for_pubsub)
                break

    return list(set_of_change_ids)


def _process_message_sending(
    tg_api: TGApiBase,
    time_analytics: TimeAnalytics,
    set_of_change_ids: set[int],
    conn: connection,
    message_to_send: MessageToSend,
) -> None:
    logging.debug('time: -------------- loop start -------------')
    logging.info(f'{message_to_send}')
    analytics_sm_start = datetime.datetime.now()

    with conn.cursor() as cur:
        change_log_upd_time = get_change_log_update_time(cur, message_to_send.change_log_id)

    analytics_pre_sending_msg = datetime.datetime.now()

    result = send_single_message(tg_api, message_to_send)

    analytics_send_start_finish = seconds_between_round_2(analytics_pre_sending_msg)
    logging.debug(f'time: {analytics_send_start_finish:.2f} – sending msg')

    # save result of sending telegram notification into SQL notif_by_user
    with conn.cursor() as cur:
        save_sending_status_to_notif_by_user(cur, message_to_send.message_id, result)

    # save metric: how long does it took from creation to completion
    if result == 'completed':
        _process_logs_with_completed_sending(time_analytics, message_to_send, change_log_upd_time)
        set_of_change_ids.add(message_to_send.change_log_id)

    # analytics on sending speed - finish for every user/notification
    analytics_sm_duration = seconds_between(analytics_sm_start)
    time_analytics.notif_times.append(analytics_sm_duration)


def _process_doubling_messages(cur: cursor) -> None:
    messages = get_notifs_to_send(cur, select_doubling=True)
    if messages:
        notify_admin(f'cancelled_due_to_doubling! {len(messages)} messages are doubling')

    already_marked = set()
    for message in messages:
        # TODO mark only first message in tuple
        key = (message.change_log_id, message.message_type, message.user_id)
        if key in already_marked:
            continue
        already_marked.add(key)
        result = 'cancelled_due_to_doubling'
        save_sending_status_to_notif_by_user(cur, message.message_id, result)


def _process_logs_with_completed_sending(
    time_analytics: TimeAnalytics, message_to_send: MessageToSend, change_log_upd_time: datetime.datetime | None
) -> None:
    creation_time = message_to_send.created

    duration_complete_vs_create_minutes = seconds_between_round_2(creation_time)
    logging.debug(f'metric: creation to completion time – {duration_complete_vs_create_minutes} min')
    time_analytics.delays.append(duration_complete_vs_create_minutes)

    duration_complete_vs_parsed_time_minutes = seconds_between_round_2(change_log_upd_time or datetime.datetime.now())
    logging.debug(f'metric: parsing to completion time – {duration_complete_vs_parsed_time_minutes} min')
    time_analytics.parsed_times.append(duration_complete_vs_parsed_time_minutes)


def finish_time_analytics(
    time_analytics: TimeAnalytics,
    list_of_change_ids: List,
) -> None:
    """Make final steps for time analytics: inform admin, log, record statistics into PSQL"""

    notif_times = time_analytics.notif_times
    delays = time_analytics.delays
    parsed_times = time_analytics.parsed_times
    if not notif_times:
        return None

    full_script_run_time = seconds_between(time_analytics.script_start_time)

    # send statistics on number of messages and sending speed

    len_n = len(notif_times)
    average = full_script_run_time / len_n
    ttl_time = round(full_script_run_time, 1)
    if not delays:
        min_delay, max_delay = None, None
    else:
        min_delay = round(min(delays), 1)
        max_delay = round(max(delays), 1)

    if not parsed_times:
        min_parse_time, max_parse_time = None, None
    else:
        min_parse_time = int(min(parsed_times))
        max_parse_time = int(max(parsed_times))

    message = (
        f'[s0] {len_n} x {round(average, 2)} = {int(ttl_time)} '
        f'| {min_delay}–{max_delay} | {min_parse_time}–{max_parse_time} | {list_of_change_ids}'
    )
    if max_parse_time and max_parse_time >= 2:  # only for cases when delay is >2 mins from parsing time
        notify_admin(message)
    logging.info(message)

    # save to psql the analytics on sending speed
    conn_psy = sql_connect_by_psycopg2()
    cur = conn_psy.cursor()

    try:
        sql_text_psy = """
                        INSERT INTO notif_stat_sending_speed
                        (timestamp, num_of_msgs, speed, ttl_time)
                        VALUES
                        (%s, %s, %s, %s);
                        /*action='notif_stat_sending_speed' */
                        ;"""

        cur.execute(sql_text_psy, (datetime.datetime.now(), len_n, average, ttl_time))
    except:  # noqa
        pass

    cur.close()
    conn_psy.close()

    return None


def main(event: dict, context: Context) -> str | None:
    """Main function that is triggered by pub/sub"""

    time_analytics = TimeAnalytics(script_start_time=datetime.datetime.now())

    # timer is needed to finish the script if it's already close to timeout

    function_id = generate_random_function_id()

    message_from_pubsub = process_pubsub_message_v2(event)
    triggered_by_func_id = get_triggering_function(message_from_pubsub)  # type:ignore[arg-type]
    # TODO maybe it not works

    # TODO remove after speeding up this function
    there_is_function_working_in_parallel = check_and_save_event_id(
        context,
        'start',
        function_id,
        None,
        triggered_by_func_id,
        FUNC_NAME,
        INTERVAL_TO_CHECK_PARALLEL_FUNCTION_SECONDS,
    )
    if there_is_function_working_in_parallel:
        logging.info('function execution stopped due to parallel run with another function')
        check_and_save_event_id(
            context,
            'finish',
            function_id,
            None,
            None,
            FUNC_NAME,
            INTERVAL_TO_CHECK_PARALLEL_FUNCTION_SECONDS,
        )
        logging.info('script finished')
        return None

    with requests.Session() as session:
        changed_ids = iterate_over_notifications(session, function_id, time_analytics)

    finish_time_analytics(time_analytics, changed_ids)

    check_and_save_event_id(
        context,
        'finish',
        function_id,
        changed_ids,
        None,
        FUNC_NAME,
        INTERVAL_TO_CHECK_PARALLEL_FUNCTION_SECONDS,
    )
    logging.info('script finished')

    return 'ok'
