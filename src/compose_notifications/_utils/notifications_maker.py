import datetime
import logging
import re
from typing import Any

import sqlalchemy
from sqlalchemy.engine.base import Connection

from _dependencies.commons import ChangeType, Topics, get_app_config
from _dependencies.pubsub import notify_admin, publish_to_pubsub

from .commons import (
    SEARCH_TOPIC_TYPES,
    LineInChangeLog,
    User,
)
from .message_composer import MessageComposer

CLEANER_RE = re.compile('<.*?>')

RE_LIST_COORDS = re.compile(r'<code>')
RE_BOTH_COORDINATES = re.compile(r'(?<=<code>).{5,100}(?=</code>)')
RE_LATITUDE = re.compile(r'^[\d.]{2,12}(?=\D)')
RE_LONGITUDE = re.compile(r'(?<=\D)[\d.]{2,12}$')


class NotificationMaker:
    def __init__(self, conn: Connection, new_record: LineInChangeLog, list_of_users: list[User]) -> None:
        self.conn = conn
        self.stat_list_of_recipients: list[int] = []  # list of users who received notification on new search
        self.new_record = new_record
        self.list_of_users = list_of_users

    def generate_notifications_for_users(self, function_id: int) -> None:
        """initiates a full cycle for all messages composition for all the users"""

        new_record = self.new_record

        # skip ignored lines which don't require a notification
        if new_record.ignore:
            new_record.processed = True
            logging.info('Iterations over all Users and Updates are done (record Ignored)')
            return

        mailing_id = self.create_new_mailing_id()

        message_for_pubsub = {'triggered_by_func_id': function_id, 'text': 'initiate notifs send out'}
        publish_to_pubsub(Topics.topic_to_send_notifications, message_for_pubsub)

        for user in self.list_of_users:
            self.generate_notification_for_user(mailing_id, user)

        # mark this line as all-processed
        new_record.processed = True
        logging.info('Iterations over all Users and Updates are done')

    def create_new_mailing_id(self) -> int:
        # record into SQL table notif_mailings

        sql_text = sqlalchemy.text("""
            INSERT INTO notif_mailings (topic_id, source_script, mailing_type, change_log_id)
            VALUES (:a, :b, :c, :d)
            RETURNING mailing_id;
                        """)
        raw_data = self.conn.execute(
            sql_text,
            a=self.new_record.forum_search_num,
            b='notifications_script',
            c=self.new_record.change_type,
            d=self.new_record.change_log_id,
        ).fetchone()

        mail_id = raw_data[0]
        logging.info(f'mailing_id = {mail_id}')

        return mail_id

    def generate_notification_for_user(
        self,
        mailing_id: int,
        user: User,
    ) -> None:
        change_type = self.new_record.change_type
        topic_type_id = self.new_record.topic_type_id

        # start composing individual messages (specific user on specific situation)
        user_message = MessageComposer(self.new_record).compose_message_for_user(user)
        if not user_message:
            return

        self._send_main_text_message(mailing_id, user, user_message)

        # save to SQL the sendLocation notification for "new search"
        if change_type == ChangeType.topic_new and topic_type_id in SEARCH_TOPIC_TYPES:
            # for user tips in "new search" notifs – to increase sent messages counter
            self.stat_list_of_recipients.append(user.user_id)
            self._send_coordinates_for_new_search(mailing_id, user)
        elif change_type == ChangeType.topic_first_post_change:
            self._send_coordinates_for_first_post_change(mailing_id, user, user_message)

    def _send_main_text_message(
        self,
        mailing_id: int,
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
            mailing_id,
            user.user_id,
            user_message,
            message_without_html,
            'text',
            message_params,
        )

    def _send_coordinates_for_new_search(
        self,
        mailing_id: int,
        user: User,
    ) -> None:
        new_record = self.new_record
        if not (new_record.search_latitude or new_record.search_longitude):
            return
        message_params = {'latitude': new_record.search_latitude, 'longitude': new_record.search_longitude}
        # record into SQL table notif_by_user (not text, but coords only)
        self._save_to_sql_notif_by_user(
            mailing_id,
            user.user_id,
            None,
            None,
            'coords',
            message_params,
        )

    def _send_coordinates_for_first_post_change(
        self,
        mailing_id: int,
        user: User,
        user_message: str,
    ) -> None:
        coords = _extract_coordinates_from_message(user_message)
        if not coords:
            return
        new_lat, new_lon = coords
        message_params = {'latitude': new_lat, 'longitude': new_lon}
        self._save_to_sql_notif_by_user(
            mailing_id,
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

        sql_text_ = sqlalchemy.text("""
            SELECT EXISTS (
                SELECT
                    message_id
                FROM
                    notif_by_user
                WHERE
                    completed IS NOT NULL AND
                    user_id=:b AND
                    message_type=:c AND
                    change_log_id=:a
            )
            /*action='get_from_sql_if_was_notified_already_new'*/
            ;
        """)

        user_was_already_notified = self.conn.execute(
            sql_text_,
            a=self.new_record.change_log_id,
            b=user_id,
            c=message_type,
        ).fetchone()[0]

        return user_was_already_notified

    def _save_to_sql_notif_by_user(
        self,
        mailing_id_: int,
        user_id: int,
        message: str | None,
        message_without_html: str | None,
        message_type: str,
        message_params: dict,
    ) -> None:
        """save to sql table notif_by_user the new message"""

        # record into SQL table notif_by_user
        sql_text_ = sqlalchemy.text("""
            INSERT INTO notif_by_user (
                mailing_id,
                user_id,
                message_content,
                message_text,
                message_type,
                message_params,
                message_group_id,
                change_log_id,
                created)
            VALUES (:a, :b, :c, :d, :e, :f, :g, :h, :i);
                            """)

        self.conn.execute(
            sql_text_,
            a=mailing_id_,
            b=user_id,
            c=message,
            d=message_without_html,
            e=message_type,
            f=str(message_params),
            g=0,
            h=self.new_record.change_log_id,
            i=datetime.datetime.now(),
        )

    def record_notification_statistics(self) -> None:
        """records +1 into users' statistics of new searches notification. needed only for usability tips"""

        dict_of_user_and_number_of_new_notifs = {
            i: self.stat_list_of_recipients.count(i) for i in self.stat_list_of_recipients
        }

        try:
            for user_id in dict_of_user_and_number_of_new_notifs:
                number_to_add = dict_of_user_and_number_of_new_notifs[user_id]

                sql_text = sqlalchemy.text("""
                    INSERT INTO user_stat (user_id, num_of_new_search_notifs)
                    VALUES(:a, :b)
                    ON CONFLICT (user_id) DO
                    UPDATE SET num_of_new_search_notifs = :b +
                    (SELECT num_of_new_search_notifs from user_stat WHERE user_id = :a)
                    WHERE user_stat.user_id = :a;
                """)
                self.conn.execute(sql_text, a=int(user_id), b=int(number_to_add))

        except Exception as e:
            logging.error('Recording statistics in notification script failed' + repr(e))
            logging.exception(e)

    def mark_new_record_as_processed(self) -> None:
        """mark all the new records in SQL as processed, to avoid processing in the next iteration"""

        if not self.new_record.processed:
            return

        sql_text = sqlalchemy.text("""
            UPDATE change_log SET notification_sent = 'y' WHERE id=:a;
                                    """)
        self.conn.execute(
            sql_text,
            a=self.new_record.change_log_id,
            sent='n' if self.new_record.ignore else 'y',
        )
        record_status = 'IGNORED' if self.new_record.ignore else 'processed'
        logging.info(f'The New Record {self.new_record.change_log_id} was marked as {record_status} in PSQL')

    def mark_new_comments_as_processed(self) -> None:
        """mark in SQL table Comments all the comments that were processed at this step, basing on search_forum_id"""

        # TODO – is it correct that we mark comments processes for any Comments for certain search? Looks
        #  like we can mark some comments which are not yet processed at all. Probably base on change_id? To be checked
        if not (self.new_record.processed and not self.new_record.ignore):
            return
        try:
            if self.new_record.change_type == ChangeType.topic_comment_new:
                sql_text = sqlalchemy.text("""
                    UPDATE comments SET notification_sent = 'y' WHERE search_forum_num=:a;
                                           """)
                self.conn.execute(sql_text, a=self.new_record.forum_search_num)

            elif self.new_record.change_type == ChangeType.topic_inforg_comment_new:
                sql_text = sqlalchemy.text("""
                    UPDATE comments SET notif_sent_inforg = 'y' WHERE search_forum_num=:a;
                                           """)
                self.conn.execute(sql_text, a=self.new_record.forum_search_num)
            # FIXME ^^^

            logging.info(f'The Update {self.new_record.change_log_id} with Comments that are processed and not ignored')
            logging.info('All Comments are marked as processed')

        except Exception as e:
            # TODO – seems a vary vague solution: to mark all
            sql_text = sqlalchemy.text("""
                UPDATE comments SET notification_sent = 'y' WHERE notification_sent is Null
                OR notification_sent = 's';
                                       """)
            self.conn.execute(sql_text)

            sql_text = sqlalchemy.text("""
                UPDATE comments SET notif_sent_inforg = 'y' WHERE notif_sent_inforg is Null;
                """)
            self.conn.execute(sql_text)

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
    except AttributeError:
        return None  # not found coordinates in the message, we should not send any message

    return new_lat, new_lon
