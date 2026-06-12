"""DB-based state machine for user dialog state.

Provides a unified way to track what the bot is expecting from the user
(e.g., radius input, coordinates input, forum username input).
This is shared between Telegram and VK bots.
"""

import datetime
import logging
from enum import Enum
from functools import lru_cache

import sqlalchemy

from _dependencies.commons import sqlalchemy_get_pool


class DialogState(str, Enum):
    """Possible states of a user dialog with the bot."""

    radius_input = 'radius_input'
    input_of_coords_man = 'input_of_coords_man'
    input_of_forum_username = 'input_of_forum_username'
    not_defined = 'not_defined'


def set_user_state(user_id: int, state: DialogState) -> None:
    """Save the bot's expected input state for a user.

    This tells the bot what kind of input it's waiting for from the user.
    """
    pool = sqlalchemy_get_pool()
    with pool.connect() as connection:
        # First delete any existing state
        delete_stmt = sqlalchemy.text("""DELETE FROM msg_from_bot WHERE user_id=:user_id;""")
        connection.execute(delete_stmt, user_id=user_id)

        # Then insert new state
        insert_stmt = sqlalchemy.text(
            """INSERT INTO msg_from_bot (user_id, time, msg_type) values (:user_id, :time, :msg_type);"""
        )
        connection.execute(
            insert_stmt,
            user_id=user_id,
            time=datetime.datetime.now(),
            msg_type=state,
        )


def get_user_state(user_id: int) -> DialogState | None:
    """Get the bot's expected input state for a user.

    Returns None if no state is set (bot is not waiting for anything specific).
    """
    pool = sqlalchemy_get_pool()
    with pool.connect() as connection:
        stmt = sqlalchemy.text("""SELECT msg_type FROM msg_from_bot WHERE user_id=:user_id LIMIT 1;""")
        result = connection.execute(stmt, user_id=user_id)
        extract = result.fetchone()

        if not extract:
            return None

        try:
            return DialogState(extract[0])
        except Exception:
            logging.exception(f'Unknown dialog state value: {extract[0]}')
            return None


def clear_user_state(user_id: int) -> None:
    """Clear the user's dialog state (bot is no longer waiting for input)."""
    set_user_state(user_id, DialogState.not_defined)


@lru_cache
def get_db_pool():
    """Get the SQLAlchemy connection pool (cached)."""
    return sqlalchemy_get_pool()
