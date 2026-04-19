"""Send the prepared notifications to users (text and location) via Telegram"""

import ast
import datetime
import logging
import re
import time
from concurrent.futures import ThreadPoolExecutor, wait
from contextlib import contextmanager
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any, Iterator, List

import sqlalchemy
from sqlalchemy.engine.base import Connection, Engine

from _dependencies.commons import setup_logging, sqlalchemy_get_pool
from _dependencies.lock_manager import FunctionLockError, lock_manager
from _dependencies.misc import generate_random_function_id, tg_api_main_account
from _dependencies.pubsub import Ctx, notify_admin, pubsub_send_notifications
from _dependencies.telegram_api_wrapper import TGApiBase
from _dependencies.vk_api_client import VKApi, get_default_vk_api_client

setup_logging(__package__)


FUNC_NAME = 'send_notifications'

SCRIPT_SOFT_TIMEOUT_SECONDS = 40  # after which iterations should stop to prevent the whole script timeout
INTERVAL_TO_CHECK_PARALLEL_FUNCTION_SECONDS = 50  # window within which we check for started parallel function
SLEEP_TIME_FOR_NEW_NOTIFS_RECHECK_SECONDS = 5
MESSAGES_BATCH_SIZE = 100
WORKERS_COUNT = 2

USE_VK_API = True  # feature-flag


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
    vk_id: str | None = None


@lru_cache
def db() -> 'DBClient':
    return DBClient(_pool=sqlalchemy_get_pool())


@dataclass
class DBClient:
    _pool: Engine

    @contextmanager
    def connect(self) -> Iterator[Connection]:
        with self._pool.connect() as connection:
            yield connection

    def get_notifs_to_send(self, select_doubling: bool) -> list['MessageToSend']:
        """return notifications which should be sent"""
        with self.connect() as conn:
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
                    (failed IS NULL OR failed < :retry_delay) AND
                    (change_log_id, user_id, message_type) {"IN" if select_doubling else "NOT IN"} (
                        {duplicated_notifications_query}
                    )
                ORDER BY user_id
                LIMIT {MESSAGES_BATCH_SIZE}
                FOR NO KEY UPDATE
                /*action='check_for_notifs_to_send 3.0' */
            """

            delay_to_retry_send_failed_messages = datetime.timedelta(minutes=5)
            stmt = sqlalchemy.text(notifications_query)
            notifications = conn.execute(
                stmt,
                retry_delay=datetime.datetime.now() - delay_to_retry_send_failed_messages,
            ).fetchall()
            return [MessageToSend(*notification) for notification in notifications]

    def fill_vk_user_ids(self, messages: list['MessageToSend']) -> None:
        """temporarily: append vk_id to MessageToSten"""
        with self.connect() as conn:
            user_ids = list(set([x.user_id for x in messages]))
            if not user_ids:
                return

            notifications_query = """
                SELECT
                    user_id, vk_id 
                FROM
                    users
                WHERE 
                    users.user_id = ANY( :user_ids)
                    AND vk_id is not null
            """

            stmt = sqlalchemy.text(notifications_query)
            rows = conn.execute(
                stmt,
                user_ids=user_ids,
            ).fetchall()
            user_ids_map = {user_id: vk_id for user_id, vk_id in rows}

            for message in messages:
                message.vk_id = user_ids_map.get(message.user_id, None)

    def check_for_number_of_notifs_to_send(self) -> int:
        """return a number of notifications to be sent"""
        with self.connect() as conn:
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
            """

            stmt = sqlalchemy.text(sql_text_psy)
            res = conn.execute(stmt).fetchone()
            return int(res[0]) if res else 0

    def save_sending_status_to_notif_by_user(self, message_id: int, result: str | None) -> None:
        """save the telegram sending status to sql table notif_by_user"""
        if not result:
            result = 'failed'

        if result.startswith('cancelled'):
            result = 'cancelled'
        elif result.startswith('failed'):
            result = 'failed'

        if result not in {'completed', 'cancelled', 'failed'}:
            return

        with self.connect() as conn:
            sql_text_psy = f"""
                UPDATE notif_by_user
                SET {result} = :now
                WHERE message_id = :message_id;
                /*action='save_sending_status_to_notif_by_user_{result}' */
            """
            stmt = sqlalchemy.text(sql_text_psy)
            conn.execute(stmt, now=datetime.datetime.now(), message_id=message_id)

    def get_change_log_update_time(self, change_log_id: int) -> datetime.datetime | None:
        """get the time of parsing of the change, saved in PSQL"""
        if not change_log_id:
            return None

        with self.connect() as conn:
            sql_text_psy = """
                SELECT parsed_time 
                FROM change_log 
                WHERE id = :change_log_id;
                /*action='getting_change_log_parsing_time' */
            """
            stmt = sqlalchemy.text(sql_text_psy)
            record = conn.execute(stmt, change_log_id=change_log_id).fetchone()
            return record[0] if record else None

    def save_sending_analytics(self, num_msgs: int, speed: float, ttl_time: float) -> None:
        """save analytics on sending speed to PSQL"""
        with self.connect() as conn:
            try:
                sql_text = """
                    INSERT INTO notif_stat_sending_speed
                    (timestamp, num_of_msgs, speed, ttl_time)
                    VALUES
                    (:now, :num_msgs, :speed, :ttl_time);
                    /*action='notif_stat_sending_speed' */
                """
                stmt = sqlalchemy.text(sql_text)
                conn.execute(stmt, now=datetime.datetime.now(), num_msgs=num_msgs, speed=speed, ttl_time=ttl_time)
            except:  # noqa
                pass


def send_single_message(tg_api: TGApiBase, vk_api: VKApi, message_to_send: MessageToSend) -> str | None:
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

        if USE_VK_API and message_to_send.vk_id:
            try:
                logging.info(f'Sending message to VK: {message_to_send.vk_id=} {message_to_send=}')
                vk_api.send(
                    message_to_send.vk_id,
                    message_to_send.message_id,
                    format_mesage_for_vk(message_content),
                )
            except Exception:
                logging.exception(f'Sending message to VK: failed {message_to_send.vk_id=} {message_to_send=}')

        # return 'completed'  # TODO
        return tg_api.send_message(message_params)

    elif message_to_send.message_type == 'coords':
        if USE_VK_API and message_to_send.vk_id:
            try:
                logging.info(f'Sending message to VK: {message_to_send.vk_id=} {message_to_send=}')
                vk_api.send(
                    message_to_send.vk_id,
                    message_to_send.message_id,
                    '',
                    lat=message_params['latitude'],
                    long=message_params['longitude'],
                )
            except Exception:
                logging.exception(f'Sending message to VK: failed {message_to_send.vk_id=} {message_to_send=}')

        # return 'completed'  # TODO
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
    function_id: int,
    time_analytics: TimeAnalytics,
) -> list[int]:
    """iterate over all available notifications, finishes if timeout is met or no new notifications"""

    set_of_change_ids: set[int] = set()
    tg_api = tg_api_main_account()
    vk_api = get_default_vk_api_client()
    db_client = db()

    with ThreadPoolExecutor(max_workers=WORKERS_COUNT) as executor:
        is_first_wait = True
        while True:
            # analytics on sending speed - start for every user/notification
            _process_doubling_messages()

            analytics_sql_start = datetime.datetime.now()

            # check if there are any non-notified users
            messages = db_client.get_notifs_to_send(select_doubling=False)
            if USE_VK_API:
                db_client.fill_vk_user_ids(messages)

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
                    vk_api,
                    time_analytics,
                    set_of_change_ids,
                    message_to_send,
                )
                for message_to_send in messages
            ]
            wait(futures)
            for future in futures:
                try:
                    res = future.result()
                except:
                    logging.exception("can't send message")

            if time_is_out(time_analytics.script_start_time):
                if db_client.get_notifs_to_send(select_doubling=False):
                    pubsub_send_notifications(function_id, 'next iteration')
                break

    return list(set_of_change_ids)


def _process_message_sending(
    tg_api: TGApiBase,
    vk_api: VKApi,
    time_analytics: TimeAnalytics,
    set_of_change_ids: set[int],
    message_to_send: MessageToSend,
) -> None:
    logging.debug('time: -------------- loop start -------------')
    logging.info(f'{message_to_send}')
    analytics_sm_start = datetime.datetime.now()

    change_log_upd_time = db().get_change_log_update_time(message_to_send.change_log_id)

    analytics_pre_sending_msg = datetime.datetime.now()

    result = send_single_message(tg_api, vk_api, message_to_send)

    analytics_send_start_finish = seconds_between_round_2(analytics_pre_sending_msg)
    logging.debug(f'time: {analytics_send_start_finish:.2f} – sending msg')

    # save result of sending telegram notification into SQL notif_by_user
    db().save_sending_status_to_notif_by_user(message_to_send.message_id, result)

    # save metric: how long does it took from creation to completion
    if result == 'completed':
        _process_logs_with_completed_sending(time_analytics, message_to_send, change_log_upd_time)
        set_of_change_ids.add(message_to_send.change_log_id)

    # analytics on sending speed - finish for every user/notification
    analytics_sm_duration = seconds_between(analytics_sm_start)
    time_analytics.notif_times.append(analytics_sm_duration)


def _process_doubling_messages() -> None:
    db_client = db()
    messages = db_client.get_notifs_to_send(select_doubling=True)
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
        db_client.save_sending_status_to_notif_by_user(message.message_id, result)


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
    db().save_sending_analytics(len_n, average, ttl_time)

    return None


def main(event: dict, context: Ctx) -> str | None:
    """Main function that is triggered by pub/sub"""

    time_analytics = TimeAnalytics(script_start_time=datetime.datetime.now())

    # timer is needed to finish the script if it's already close to timeout

    function_id = generate_random_function_id()

    try:
        pool = sqlalchemy_get_pool()
        connection = pool.connect()
        with lock_manager(connection, FUNC_NAME, INTERVAL_TO_CHECK_PARALLEL_FUNCTION_SECONDS):
            changed_ids = iterate_over_notifications(function_id, time_analytics)

    except FunctionLockError:
        logging.info('script cancelled')
        return None

    finish_time_analytics(time_analytics, changed_ids)

    logging.info('script finished')

    return 'ok'


def format_mesage_for_vk(message: str) -> str:
    # Handle different types of <a> tags based on their href
    # Pattern to match <a href="URL">text</a>
    a_tag_pattern = re.compile(r'<a\s+href="([^"]+)"[^>]*>([^<]+)</a>')

    def replace_a_tag(match: re.Match) -> str:
        url = match.group(1)
        text = match.group(2)

        # Rule 1: For links starting with https://lizaalert.org/forum/memberlist.php
        # Remove the link but keep the text
        if url.startswith('https://lizaalert.org/forum/memberlist.php'):
            return text

        # Rule 2: For links starting with https://lizaalert.org/forum/viewtopic.php and containing "start" in query
        # Remove the link but keep the text
        if url.startswith('https://lizaalert.org/forum/viewtopic.php') and 'start=' in url:
            return text

        # Rule 3: For phone number links (tel:)
        # Remove the link but keep the text
        if url.startswith('tel:'):
            return text

        # Rule 4: For other links (including lizaalert.org/forum/viewtopic.php without start),
        # unfold the link: show URL followed by text
        return f'{url} {text}'

    # Replace all <a> tags
    result = a_tag_pattern.sub(replace_a_tag, message)

    # Remove any remaining HTML tags (including self-closing tags)
    # Pattern matches < followed by any characters (non-greedy) up to >
    html_tag_pattern = re.compile(r'<[^>]+>')
    result = html_tag_pattern.sub('', result)

    return result
