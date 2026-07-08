"""Forum attribute management mixin — consolidated."""

import datetime

import sqlalchemy

from _dependencies.common.db_client import DBClientMixinBase


class ForumAttributeMixin(DBClientMixinBase):
    """User forum attribute operations (linking forum account)."""

    def get_forum_attributes(self, user_id: int) -> tuple[str, str] | None:
        """Get user's linked forum username and ID."""
        with self.connect() as connection:
            stmt = sqlalchemy.text(
                """SELECT forum_username, forum_user_id
                   FROM user_forum_attributes
                   WHERE status='verified' AND user_id=:user_id
                   ORDER BY timestamp DESC
                   LIMIT 1;"""
            )
            result = connection.execute(stmt, dict(user_id=user_id))
            return result.fetchone()

    def verify_forum_attributes(self, user_id: int) -> None:
        """Mark the latest forum attributes as verified."""
        with self.connect() as connection:
            stmt = sqlalchemy.text(
                """UPDATE user_forum_attributes SET status='verified'
                   WHERE user_id=:user_id and timestamp =
                   (SELECT MAX(timestamp) FROM user_forum_attributes WHERE user_id=:user_id);"""
            )
            connection.execute(stmt, dict(user_id=user_id))

    def replace_user_forum_attributes(
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
        """Delete old forum attributes and insert new ones in one transaction."""
        with self.connect() as connection:
            connection.execute(
                sqlalchemy.text("""DELETE FROM user_forum_attributes WHERE user_id=:user_id"""),
                dict(user_id=user_id),
            )
            connection.execute(
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
                    status='non-verified',
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
