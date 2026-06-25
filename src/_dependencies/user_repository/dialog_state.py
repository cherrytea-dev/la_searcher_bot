"""Dialog state management mixin — consolidated."""

import datetime
import logging

import sqlalchemy

from _dependencies.common.db_client import DBClientMixinBase
from _dependencies.models import DialogState


class DialogStateMixin(DBClientMixinBase):
    """Bot dialog state tracking.

    Manages what kind of input the bot expects from the user
    (e.g., radius input, coordinates input, forum username input).
    """

    def set_user_state(self, user_id: int, state: DialogState) -> None:
        """Save the bot's expected input state for a user.

        Any previous state for this user is overwritten.
        """
        with self.connect() as connection:
            delete_stmt = sqlalchemy.text("""DELETE FROM msg_from_bot WHERE user_id=:user_id;""")
            connection.execute(delete_stmt, user_id=user_id)

            insert_stmt = sqlalchemy.text(
                """INSERT INTO msg_from_bot (user_id, time, msg_type) values (:user_id, :time, :msg_type);"""
            )
            connection.execute(
                insert_stmt,
                user_id=user_id,
                time=datetime.datetime.now(),
                msg_type=state.value,
            )

    def get_user_state(self, user_id: int) -> DialogState | None:
        """Get the bot's expected input state for a user.

        Returns None if no state is set (bot is not waiting for anything specific).
        """
        with self.connect() as connection:
            stmt = sqlalchemy.text("""SELECT msg_type FROM msg_from_bot WHERE user_id=:user_id LIMIT 1;""")
            result = connection.execute(stmt, user_id=user_id)
            extract = result.fetchone()

            if not extract:
                return None

            raw_value = extract[0]

            try:
                return DialogState(raw_value)
            except ValueError:
                logging.warning(f'Unknown dialog state value: {raw_value}')
                return None

    def clear_user_state(self, user_id: int) -> None:
        """Clear the user's dialog state (bot is no longer waiting for input)."""
        self.set_user_state(user_id, DialogState.not_defined)
