"""Dialog history mixin."""

import datetime

import sqlalchemy


class DialogHistoryMixin:
    """User-bot dialog history operations."""

    def save_user_message(self, user_id: int, text: str) -> None:
        """Save user's message to dialog history."""
        with self.connect() as connection:  # type: ignore[attr-defined]
            stmt = sqlalchemy.text(
                """INSERT INTO dialogs (user_id, author, timestamp, message_text)
                   values (:user_id, :author, :timestamp, :message_text);"""
            )
            connection.execute(
                stmt,
                user_id=user_id,
                author='user',
                timestamp=datetime.datetime.now(),
                message_text=text,
            )

    def save_bot_reply(self, user_id: int, text: str) -> None:
        """Save bot's reply to dialog history."""
        with self.connect() as connection:  # type: ignore[attr-defined]
            stmt = sqlalchemy.text(
                """INSERT INTO dialogs (user_id, author, timestamp, message_text)
                   values (:user_id, :author, :timestamp, :message_text);"""
            )
            connection.execute(
                stmt,
                user_id=user_id,
                author='bot',
                timestamp=datetime.datetime.now(),
                message_text=text,
            )
