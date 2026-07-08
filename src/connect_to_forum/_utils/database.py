"""DB client for connect_to_forum."""

import datetime

import sqlalchemy

from _dependencies.common.db_client import DBClientBase


class DBClient(DBClientBase):
    """DB client for connect_to_forum."""

    def delete_user_forum_attributes(self, user_id: int) -> None:
        with self.connect() as conn:
            conn.execute(
                sqlalchemy.text("""DELETE FROM user_forum_attributes WHERE user_id=:user_id"""),
                dict(user_id=user_id),
            )

    def insert_user_forum_attributes(
        self,
        user_id: int,
        forum_user_id: str,
        forum_username: str,
        forum_age: str | None,
        forum_sex: str | None,
        forum_region: str | None,
        forum_auto_num: str | None,
        forum_callsign: str | None,
        forum_phone: str | None,
        forum_reg_date: str | None,
    ) -> None:
        with self.connect() as conn:
            conn.execute(
                sqlalchemy.text("""
                INSERT INTO user_forum_attributes
                (user_id, forum_user_id, status, timestamp, forum_username, forum_age, forum_sex, forum_region,
                forum_auto_num, forum_callsign, forum_phone, forum_reg_date)
                values (:user_id, :forum_user_id, :status, :timestamp, :forum_username, :forum_age, :forum_sex,
                :forum_region, :forum_auto_num, :forum_callsign, :forum_phone, :forum_reg_date)
                """),
                dict(
                    user_id=user_id,
                    forum_user_id=forum_user_id,
                    status='non-varified',
                    timestamp=datetime.datetime.now(),
                    forum_username=forum_username,
                    forum_age=forum_age,
                    forum_sex=forum_sex,
                    forum_region=forum_region,
                    forum_auto_num=forum_auto_num,
                    forum_callsign=forum_callsign,
                    forum_phone=forum_phone,
                    forum_reg_date=forum_reg_date,
                ),
            )

    def user_has_region_set(self, user_id: int) -> bool:
        with self.connect() as conn:
            result = conn.execute(
                sqlalchemy.text("""SELECT forum_folder_num FROM user_regional_preferences WHERE user_id=:user_id"""),
                dict(user_id=user_id),
            ).fetchone()
            return result is not None

    def delete_msg_from_bot(self, user_id: int) -> None:
        with self.connect() as conn:
            conn.execute(
                sqlalchemy.text("""DELETE FROM msg_from_bot WHERE user_id=:user_id"""),
                dict(user_id=user_id),
            )

    def insert_msg_from_bot(self, user_id: int, msg_type: str) -> None:
        with self.connect() as conn:
            conn.execute(
                sqlalchemy.text("""
                INSERT INTO msg_from_bot (user_id, time, msg_type) values (:user_id, :time, :msg_type)
                """),
                dict(user_id=user_id, time=datetime.datetime.now(), msg_type=msg_type),
            )

    def insert_dialog_message(self, user_id: int, author: str, message_text: str) -> None:
        with self.connect() as conn:
            conn.execute(
                sqlalchemy.text("""
                INSERT INTO dialogs (user_id, author, timestamp, message_text)
                values (:user_id, :author, :timestamp, :message_text)
                """),
                dict(
                    user_id=user_id,
                    author=author,
                    timestamp=datetime.datetime.now(),
                    message_text=message_text,
                ),
            )
