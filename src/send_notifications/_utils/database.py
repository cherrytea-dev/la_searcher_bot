"""DB client for send_notifications — extracts all SQL into DBClient methods."""

import datetime
from typing import Any

import sqlalchemy

from _dependencies.common.commons import Messenger
from _dependencies.common.db_client import DBClientBase

MESSAGES_BATCH_SIZE = 100


class DBClient(DBClientBase):
    """DB client for send_notifications."""

    def get_notifs_to_send(self, select_doubling: bool) -> list:
        """Return notifications which should be sent, as MessageToSend objects."""
        # Lazy import to avoid circular dependency
        from send_notifications.main import MessageToSend

        with self.connect() as conn:
            duplicated_notifications_query = """
                SELECT
                    change_log_id, user_id, message_type, COALESCE(messenger, 'telegram')
                FROM
                    notif_by_user
                WHERE
                    completed IS NULL AND
                    cancelled IS null
                GROUP BY change_log_id, user_id, message_type, COALESCE(messenger, 'telegram')
                HAVING count(message_id) > 1
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
                    failed,
                    messenger
                FROM
                    notif_by_user
                WHERE
                    completed IS NULL AND
                    cancelled IS NULL AND
                    (failed IS NULL OR failed < :retry_delay) AND
                    (change_log_id, user_id, message_type, COALESCE(messenger, 'telegram')) {"IN" if select_doubling else "NOT IN"} (
                        {duplicated_notifications_query}
                    )
                ORDER BY user_id
                LIMIT {MESSAGES_BATCH_SIZE}
                FOR NO KEY UPDATE
                /*action='check_for_notifs_to_send 3.0' */
            """

            delay_to_retry_send_failed_messages = datetime.timedelta(minutes=5)
            stmt = sqlalchemy.text(notifications_query)
            return [MessageToSend(*row) for row in conn.execute(
                    stmt,
                    dict(
                        retry_delay=datetime.datetime.now() - delay_to_retry_send_failed_messages,
                    ),
                ).fetchall()
            ]

    def fill_max_user_ids(self, messages: list[Any]) -> None:
        """Resolve max_id from user_identity_map for MAX-destined messages."""
        max_messages = [m for m in messages if m.messenger == Messenger.MAX]
        if not max_messages:
            return

        user_ids = list(set([m.user_id for m in max_messages]))

        with self.connect() as conn:
            identity_query = """
                SELECT internal_user_id, messenger_user_id
                FROM user_identity_map
                WHERE internal_user_id = ANY(:user_ids)
                  AND messenger = 'max'
            """
            stmt = sqlalchemy.text(identity_query)
            rows = conn.execute(stmt, dict(user_ids=user_ids)).fetchall()
            user_ids_map = {internal_user_id: messenger_user_id for internal_user_id, messenger_user_id in rows}

        for message in max_messages:
            message.max_id = user_ids_map.get(message.user_id, None)

    def fill_vk_user_ids(self, messages: list[Any]) -> None:
        """Append vk_id to messages for VK-destined messages."""
        vk_messages = [m for m in messages if m.messenger == Messenger.VK]
        if not vk_messages:
            return

        user_ids = list(set([m.user_id for m in vk_messages]))

        with self.connect() as conn:
            identity_query = """
                SELECT internal_user_id, messenger_user_id
                FROM user_identity_map
                WHERE internal_user_id = ANY(:user_ids)
                  AND messenger = 'vk'
            """
            stmt = sqlalchemy.text(identity_query)
            rows = conn.execute(stmt, dict(user_ids=user_ids)).fetchall()
            user_ids_map = {internal_user_id: messenger_user_id for internal_user_id, messenger_user_id in rows}

        for message in vk_messages:
            message.vk_id = user_ids_map.get(message.user_id, None)

    def check_for_number_of_notifs_to_send(self) -> int:
        """Return a number of notifications to be sent."""
        with self.connect() as conn:
            stmt = sqlalchemy.text("""
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
            """)
            res = conn.execute(stmt).fetchone()
            return int(res[0]) if res else 0

    def save_sending_status_to_notif_by_user(self, message_id: int, result: str | None) -> None:
        """Save the sending status to notif_by_user."""
        if not result:
            result = 'failed'

        if result.startswith('cancelled'):
            result = 'cancelled'
        elif result.startswith('failed'):
            result = 'failed'

        if result not in {'completed', 'cancelled', 'failed'}:
            return

        with self.connect() as conn:
            stmt = sqlalchemy.text(f"""
                UPDATE notif_by_user
                SET {result} = :now
                WHERE message_id = :message_id;
                /*action='save_sending_status_to_notif_by_user_{result}' */
            """)
            conn.execute(stmt, dict(now=datetime.datetime.now(), message_id=message_id))

    def get_change_log_update_time(self, change_log_id: int) -> datetime.datetime | None:
        """Get the time of parsing of the change, saved in PSQL."""
        if not change_log_id:
            return None

        with self.connect() as conn:
            stmt = sqlalchemy.text("""
                SELECT parsed_time
                FROM change_log
                WHERE id = :change_log_id;
                /*action='getting_change_log_parsing_time' */
            """)
            record = conn.execute(stmt, dict(change_log_id=change_log_id)).fetchone()
            return record[0] if record else None

    def save_sending_analytics(self, num_msgs: int, speed: float, ttl_time: float) -> None:
        """Save analytics on sending speed to PSQL."""
        with self.connect() as conn:
            try:
                stmt = sqlalchemy.text("""
                    INSERT INTO notif_stat_sending_speed
                    (timestamp, num_of_msgs, speed, ttl_time)
                    VALUES
                    (:now, :num_msgs, :speed, :ttl_time);
                    /*action='notif_stat_sending_speed' */
                """)
                conn.execute(stmt, dict(now=datetime.datetime.now(), num_msgs=num_msgs, speed=speed, ttl_time=ttl_time))
            except:  # noqa
                pass
