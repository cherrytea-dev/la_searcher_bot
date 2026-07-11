"""NotificationSender — orchestrates reading, sending, and tracking notifications."""

import datetime
import logging
import time
from concurrent.futures import ThreadPoolExecutor, wait

from _dependencies.common.commons import Messenger
from _dependencies.common.pubsub import notify_admin, pubsub_send_notifications
from send_notifications._utils.clients.max_notificator import MaxNotificator
from send_notifications._utils.clients.telegram_notificator import TelegramNotificator
from send_notifications._utils.clients.vk_notificator import VKNotificator
from send_notifications._utils.database import DBClient, MessageToSend
from send_notifications._utils.helpers import (
    SLEEP_TIME_FOR_NEW_NOTIFS_RECHECK_SECONDS,
    USE_VK_API,
    WORKERS_COUNT,
    _prepare_message,
    seconds_between,
    seconds_between_round_2,
    time_is_out,
)
from send_notifications._utils.models import TimeAnalytics


class NotificationSender:
    """Orchestrates the full notification sending pipeline."""

    def __init__(
        self,
        db_client: DBClient,
        vk_notificator: VKNotificator,
        tg_notificator: TelegramNotificator,
        max_notificator: MaxNotificator,
    ) -> None:
        self._db_client = db_client
        self._vk_notificator = vk_notificator
        self._tg_notificator = tg_notificator
        self._max_notificator = max_notificator

    # ── public API ──────────────────────────────────────────────────

    def send_all(self, function_id: int, time_analytics: TimeAnalytics) -> list[int]:
        """Main loop: read notifications, send, handle timeouts and recursion."""
        set_of_change_ids: set[int] = set()

        with ThreadPoolExecutor(max_workers=WORKERS_COUNT) as executor:
            is_first_wait = True
            while True:
                # analytics on sending speed - start for every user/notification
                self._process_doubling_messages()

                analytics_sql_start = datetime.datetime.now()

                # check if there are any non-notified users
                messages = self._db_client.get_notifs_to_send(select_doubling=False)
                if USE_VK_API:
                    self._db_client.fill_vk_user_ids(messages)
                self._db_client.fill_max_user_ids(messages)

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
                        self._process_message_sending,
                        time_analytics,
                        set_of_change_ids,
                        message_to_send,
                    )
                    for message_to_send in messages
                ]
                wait(futures)
                for future in futures:
                    try:
                        future.result()
                    except Exception:
                        logging.exception("can't send message")

                if time_is_out(time_analytics.script_start_time):
                    if self._db_client.get_notifs_to_send(select_doubling=False):
                        pubsub_send_notifications(function_id, 'next iteration')
                    break

        return list(set_of_change_ids)

    def finish_analytics(self, time_analytics: TimeAnalytics, change_ids: list[int]) -> None:
        """Finalize: record metrics to DB, notify admin."""
        notif_times = time_analytics.notif_times
        delays = time_analytics.delays
        parsed_times = time_analytics.parsed_times
        if not notif_times:
            return

        full_script_run_time = seconds_between(time_analytics.script_start_time)

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
            f'| {min_delay}–{max_delay} | {min_parse_time}–{max_parse_time} | {change_ids}'
        )
        if max_parse_time and max_parse_time >= 2:
            notify_admin(message)
        logging.info(message)

        self._db_client.save_sending_analytics(len_n, average, ttl_time)

    # ── private helpers ─────────────────────────────────────────────

    def _send_one(self, message_to_send: MessageToSend) -> str | None:
        """Select client by messenger and dispatch."""
        content, message_params = _prepare_message(message_to_send)

        if message_to_send.messenger == Messenger.VK:
            return self._vk_notificator.dispatch(message_to_send, content, message_params)

        if message_to_send.messenger == Messenger.MAX:
            return self._max_notificator.dispatch(message_to_send, content, message_params)

        return self._tg_notificator.dispatch(message_to_send, content, message_params)

    def _process_message_sending(
        self,
        time_analytics: TimeAnalytics,
        set_of_change_ids: set[int],
        message_to_send: MessageToSend,
    ) -> None:
        """Log + DB update + metrics for one message."""
        logging.debug('time: -------------- loop start -------------')
        logging.info(f'{message_to_send}')
        analytics_sm_start = datetime.datetime.now()

        change_log_upd_time = self._db_client.get_change_log_update_time(message_to_send.change_log_id)

        analytics_pre_sending_msg = datetime.datetime.now()

        result = self._send_one(message_to_send)

        analytics_send_start_finish = seconds_between_round_2(analytics_pre_sending_msg)
        logging.debug(f'time: {analytics_send_start_finish:.2f} – sending msg')

        self._db_client.save_sending_status_to_notif_by_user(message_to_send.message_id, result)

        if result == 'completed':
            self._process_logs_with_completed_sending(time_analytics, message_to_send, change_log_upd_time)
            set_of_change_ids.add(message_to_send.change_log_id)

        analytics_sm_duration = seconds_between(analytics_sm_start)
        time_analytics.notif_times.append(analytics_sm_duration)

    def _process_doubling_messages(self) -> None:
        """Search and cancel duplicate notifications."""
        messages = self._db_client.get_notifs_to_send(select_doubling=True)
        if messages:
            groups: dict[tuple, list[int]] = {}
            for m in messages:
                key = (m.change_log_id, m.message_type, m.user_id, m.messenger)
                groups.setdefault(key, []).append(m.message_id)
            logging.warning(
                f'DOUBLING_DIAG: {len(messages)} total doubling messages. '
                f'Groups: {len(groups)}. Details: '
                + '; '.join(f'cl={k[0]} type={k[1]} uid={k[2]} msgr={k[3]} → ids={v}' for k, v in groups.items())
            )
            notify_admin(f'cancelled_due_to_doubling! {len(messages)} messages are doubling')

        seen_keys: set[tuple] = set()
        for message in messages:
            key = (message.change_log_id, message.message_type, message.user_id, message.messenger)
            if key in seen_keys:
                logging.info(
                    f'DOUBLING_DIAG: cancelling duplicate msg_id={message.message_id} '
                    f'for key cl={message.change_log_id} type={message.message_type} '
                    f'uid={message.user_id} msgr={message.messenger}'
                )
                self._db_client.save_sending_status_to_notif_by_user(message.message_id, 'cancelled_due_to_doubling')
            else:
                seen_keys.add(key)
                logging.info(
                    f'DOUBLING_DIAG: keeping first msg_id={message.message_id} '
                    f'for key cl={message.change_log_id} type={message.message_type} '
                    f'uid={message.user_id} msgr={message.messenger}'
                )

    def _process_logs_with_completed_sending(
        self,
        time_analytics: TimeAnalytics,
        message_to_send: MessageToSend,
        change_log_upd_time: datetime.datetime | None,
    ) -> None:
        """Log metrics for a completed send."""
        creation_time = message_to_send.created

        duration_complete_vs_create_minutes = seconds_between_round_2(creation_time)
        logging.debug(f'metric: creation to completion time – {duration_complete_vs_create_minutes} min')
        time_analytics.delays.append(duration_complete_vs_create_minutes)

        duration_complete_vs_parsed_time_minutes = seconds_between_round_2(
            change_log_upd_time or datetime.datetime.now()
        )
        logging.debug(f'metric: parsing to completion time – {duration_complete_vs_parsed_time_minutes} min')
        time_analytics.parsed_times.append(duration_complete_vs_parsed_time_minutes)
