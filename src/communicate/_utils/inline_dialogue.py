"""Inline dialogue tracking mixin — Telegram-specific.

Tracks user's last interaction via inline buttons.
VK bot does not use inline dialogues (it uses callback events instead).
"""

import sqlalchemy

from _dependencies.common.db_client import DBClientMixinBase


class InlineDialogueMixin(DBClientMixinBase):
    """Inline dialogue tracking — user's last interaction via inline buttons."""

    def delete_last_user_inline_dialogue(self, user_id: int) -> None:
        """Delete from DB the user's last interaction via inline buttons."""
        with self.connect() as connection:
            stmt = sqlalchemy.text("""DELETE FROM communications_last_inline_msg WHERE user_id=:user_id;""")
            connection.execute(stmt, user_id=user_id)

    def get_last_user_inline_dialogue(self, user_id: int) -> list[int]:
        """Get from DB the user's last interaction via inline buttons."""
        with self.connect() as connection:
            stmt = sqlalchemy.text("""SELECT message_id FROM communications_last_inline_msg WHERE user_id=:user_id;""")
            result = connection.execute(stmt, user_id=user_id)
            message_id_lines = result.fetchall()
            message_id_list = []
            if message_id_lines and len(message_id_lines) > 0:
                for message_id_line in message_id_lines:
                    message_id_list.append(message_id_line[0])
            return message_id_list

    def save_last_user_inline_dialogue(self, user_id: int, message_id: int) -> None:
        """Save to DB the user's last interaction via inline buttons."""
        with self.connect() as connection:
            stmt = sqlalchemy.text(
                """INSERT INTO communications_last_inline_msg
                            (user_id, timestamp, message_id) values (:user_id, CURRENT_TIMESTAMP AT TIME ZONE 'UTC', :message_id)
                            ON CONFLICT (user_id, message_id) DO
                            UPDATE SET timestamp=CURRENT_TIMESTAMP AT TIME ZONE 'UTC';"""
            )
            connection.execute(stmt, user_id=user_id, message_id=message_id)
