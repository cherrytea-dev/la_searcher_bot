import datetime
import logging
import re
from dataclasses import dataclass
from typing import Any

from _dependencies.common.commons import ChangeType, get_app_config
from _dependencies.common.pubsub import notify_admin, pubsub_send_notifications

from .commons import (
    SEARCH_TOPIC_TYPES,
    LineInChangeLog,
    User,
)
from .database import DBClient
from .message_composer import MessageComposer


@dataclass
class NotificationRecord:
    """Dataclass representing a notification record for batch insertion."""

    user_id: int
    message: str | None
    message_without_html: str | None
    message_type: str
    message_params: str  # Already converted to string
    change_log_id: int
    created: datetime.datetime
    message_group: int = 0
    messenger: str = 'telegram'


CLEANER_RE = re.compile('<.*?>')

RE_LIST_COORDS = re.compile(r'<code>')
RE_BOTH_COORDINATES = re.compile(r'(?<=<code>).{5,100}(?=</code>)')
RE_LATITUDE = re.compile(r'^[\d.]{2,12}(?=\D)')
RE_LONGITUDE = re.compile(r'(?<=\D)[\d.]{2,12}$')


class NotificationMaker:
    def __init__(self, db: DBClient, new_record: LineInChangeLog, list_of_users: list[User]) -> None:
        self.db = db
        self.stat_list_of_recipients: list[int] = []  # list of users who received notification on new search
        self.new_record = new_record
        self.list_of_users = list_of_users
        self._batch_buffer: list[NotificationRecord] = []
        self._BATCH_SIZE = 100
        self._messenger_map: dict[int, list[str]] = {}  # user_id -> list of messengers

    def generate_notifications_for_users(self, function_id: int) -> None:
        """initiates a full cycle for all messages composition for all the users"""

        new_record = self.new_record

        # skip ignored lines which don't require a notification
        if new_record.ignore:
            new_record.processed = True
            logging.info('Iterations over all Users and Updates are done (record Ignored)')
            return

        change_log_id = new_record.change_log_id

        pubsub_send_notifications(function_id, 'initiate notifs send out')

        # Batch-resolve messengers for all users in a single query
        self._resolve_messengers_batch()

        # Defensive deduplication by user_id: duplicate entries in user_regional_preferences
        # can cause the SQL query in UsersListComposer to return the same user multiple times.
        # Without deduplication, the second pass would hit the unique index on notif_by_user.
        seen: set[int] = set()
        duplicate_ids: set[int] = set()
        unique_users: list[User] = []
        for user in self.list_of_users:
            if user.user_id not in seen:
                seen.add(user.user_id)
                unique_users.append(user)
            else:
                duplicate_ids.add(user.user_id)
        if duplicate_ids:
            logging.warning(
                f'Deduplicated user list: {len(self.list_of_users)} → {len(unique_users)} users. '
                f'Duplicate user_ids: {sorted(duplicate_ids)}'
            )
        self.list_of_users = unique_users

        for user in self.list_of_users:
            self.generate_notification_for_user(change_log_id, user)

        self.flush_batch()

        # mark this line as all-processed
        new_record.processed = True
        logging.info('Iterations over all Users and Updates are done')

    def generate_notification_for_user(
        self,
        change_log_id: int,
        user: User,
    ) -> None:
        change_type = self.new_record.change_type
        topic_type_id = self.new_record.topic_type_id

        # start composing individual messages (specific user on specific situation)
        user_message = MessageComposer(self.new_record).compose_message_for_user(user)
        if not user_message:
            return

        self._send_main_text_message(change_log_id, user, user_message)

        # save to SQL the sendLocation notification for "new search"
        if change_type == ChangeType.topic_new and topic_type_id in SEARCH_TOPIC_TYPES:
            # for user tips in "new search" notifs – to increase sent messages counter
            self.stat_list_of_recipients.append(user.user_id)
            self._send_coordinates_for_new_search(change_log_id, user)
        elif change_type == ChangeType.topic_first_post_change:
            self._send_coordinates_for_first_post_change(change_log_id, user, user_message)

    def _send_main_text_message(
        self,
        change_log_id: int,
        user: User,
        user_message: str,
    ) -> None:
        # TODO: make text more compact within 50 symbols
        message_without_html = re.sub(CLEANER_RE, '', user_message)
        message_params: dict[str, Any] = {'parse_mode': 'HTML', 'disable_web_page_preview': 'True'}

        # for the new searches we add a link to web_app map
        if self.new_record.change_type == ChangeType.topic_new:
            map_button = {'text': 'Смотреть на Карте Поисков', 'web_app': {'url': get_app_config().web_app_url}}
            message_params['reply_markup'] = {'inline_keyboard': [[map_button]]}

            # record into SQL table notif_by_user
        self._save_to_sql_notif_by_user(
            change_log_id,
            user.user_id,
            user_message,
            message_without_html,
            'text',
            message_params,
        )

    def _send_coordinates_for_new_search(
        self,
        change_log_id: int,
        user: User,
    ) -> None:
        new_record = self.new_record
        if not (new_record.search_latitude or new_record.search_longitude):
            return
        message_params = {'latitude': new_record.search_latitude, 'longitude': new_record.search_longitude}
        # record into SQL table notif_by_user (not text, but coords only)
        self._save_to_sql_notif_by_user(
            change_log_id,
            user.user_id,
            None,
            None,
            'coords',
            message_params,
        )

    def _send_coordinates_for_first_post_change(
        self,
        change_log_id: int,
        user: User,
        user_message: str,
    ) -> None:
        coords = _extract_coordinates_from_message(user_message)
        if not coords:
            return
        new_lat, new_lon = coords
        message_params = {'latitude': new_lat, 'longitude': new_lon}
        self._save_to_sql_notif_by_user(
            change_log_id,
            user.user_id,
            None,
            None,
            'coords',
            message_params,
        )

    def _get_from_sql_if_was_notified_already(self, user_id: int, message_type: str) -> bool:
        """check in sql if this user was already notified re this change_log record
        works for every user during iterations over users
        TODO not used, remove it
        """

        return self.db.check_user_notified(user_id, self.new_record.change_log_id)

    def _save_to_sql_notif_by_user(
        self,
        change_log_id: int,
        user_id: int,
        message: str | None,
        message_without_html: str | None,
        message_type: str,
        message_params: dict,
    ) -> None:
        """save to sql table notif_by_user the new message

        Creates one NotificationRecord per messenger for this user,
        so a user with both Telegram and VK gets two records.
        """

        messengers = self._messenger_map.get(user_id, [])

        for messenger in messengers:
            record = NotificationRecord(
                user_id=user_id,
                message=message,
                message_without_html=message_without_html,
                message_type=message_type,
                message_params=str(message_params),
                change_log_id=change_log_id,
                created=datetime.datetime.now(),
                messenger=messenger,
            )

            self._batch_buffer.append(record)

            if len(self._batch_buffer) >= self._BATCH_SIZE:
                self.flush_batch()

    def _resolve_messengers_batch(self) -> None:
        """Batch-resolve messengers for all users in a single query.

        Builds self._messenger_map: user_id -> list of messenger strings.
        """
        if not self.list_of_users:
            self._messenger_map = {}
            return

        user_ids = [user.user_id for user in self.list_of_users]
        rows = self.db.resolve_messengers(user_ids)

        # Build map: user_id -> set of messengers
        temp: dict[int, set[str]] = {}
        for uid, messenger in rows:
            if uid not in temp:
                temp[uid] = set()
            temp[uid].add(messenger)

        self._messenger_map = {}
        for uid in user_ids:
            messengers = temp.get(uid, set())
            self._messenger_map[uid] = list(messengers)

    def flush_batch(self) -> None:
        """Flush the batch buffer to the database"""
        if not self._batch_buffer:
            return

        # DIAG: check if any records in this batch would create duplicates
        change_log_id = self.new_record.change_log_id
        for record in self._batch_buffer:
            existing_count = self.db.check_notification_duplicate(
                change_log_id, record.user_id, record.message_type, record.messenger
            )
            if existing_count and existing_count > 0:
                logging.warning(
                    f'DOUBLING_DIAG: flush_batch would create duplicate! '
                    f'change_log_id={change_log_id} user_id={record.user_id} '
                    f'message_type={record.message_type} messenger={record.messenger} '
                    f'existing_count={existing_count}'
                )

        # Convert NotificationRecord dataclass instances to dicts with
        # column names matching the notif_by_user table.
        records = [
            {
                'user_id': r.user_id,
                'message_content': r.message,
                'message_text': r.message_without_html,
                'message_type': r.message_type,
                'message_params': r.message_params,
                'message_group_id': r.message_group,
                'change_log_id': r.change_log_id,
                'created': r.created,
                'messenger': r.messenger,
            }
            for r in self._batch_buffer
        ]
        self.db.batch_insert_notifications(records)
        logging.debug(f'Flushed {len(self._batch_buffer)} records to notif_by_user table')
        self._batch_buffer.clear()

    def record_notification_statistics(self) -> None:
        """records +1 into users' statistics of new searches notification. needed only for usability tips"""

        dict_of_user_and_number_of_new_notifs = {
            i: self.stat_list_of_recipients.count(i) for i in self.stat_list_of_recipients
        }

        try:
            for user_id in dict_of_user_and_number_of_new_notifs:
                number_to_add = dict_of_user_and_number_of_new_notifs[user_id]
                self.db.record_user_stat_notifications(int(user_id), int(number_to_add))

        except Exception as e:
            logging.error('Recording statistics in notification script failed' + repr(e))
            logging.exception(e)

    def mark_new_record_as_processed(self) -> None:
        """mark all the new records in SQL as processed, to avoid processing in the next iteration"""

        if not self.new_record.processed:
            return

        self.db.mark_change_log_processed(self.new_record.change_log_id)
        record_status = 'IGNORED' if self.new_record.ignore else 'processed'
        logging.info(f'The New Record {self.new_record.change_log_id} was marked as {record_status} in PSQL')

    def mark_new_comments_as_processed(self) -> None:
        """mark in SQL table Comments all the comments that were processed at this step, basing on search_forum_id"""

        # TODO – is it correct that we mark comments processes for any Comments for certain search? Looks
        #  like we can mark some comments which are not yet processed at all. Probably base on change_id? To be checked
        if not (self.new_record.processed and not self.new_record.ignore):
            return
        try:
            self.db.mark_comments_processed_by_change_type(
                self.new_record.forum_search_num,
                int(self.new_record.change_type),
            )

            logging.info(f'The Update {self.new_record.change_log_id} with Comments that are processed and not ignored')
            logging.info('All Comments are marked as processed')

        except Exception:
            # TODO – seems a vary vague solution: to mark all
            self.db.mark_all_comments_processed_fallback()

            logging.exception('Not able to mark Comments as Processed:')
            logging.info('Due to error, all Comments are marked as processed')
            notify_admin('ERROR: Not able to mark Comments as Processed!')


def _extract_coordinates_from_message(user_message: str) -> None | tuple[str, str]:
    list_of_coords = re.findall(RE_LIST_COORDS, user_message)
    if not list_of_coords or len(list_of_coords) != 1:
        return None
        # that would mean that there's only 1 set of new coordinates and hence we can
        # send the dedicated sendLocation message
    try:
        both_coordinates = re.search(RE_BOTH_COORDINATES, user_message).group()  # type:ignore[union-attr]
        new_lat = re.search(RE_LATITUDE, both_coordinates).group()  # type:ignore[union-attr]
        new_lon = re.search(RE_LONGITUDE, both_coordinates).group()  # type:ignore[union-attr]
        return new_lat, new_lon
    except AttributeError:
        return None  # not found coordinates in the message, we should not send any message
