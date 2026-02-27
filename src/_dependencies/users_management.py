import logging
from datetime import datetime
from enum import Enum

import sqlalchemy

from _dependencies.commons import sqlalchemy_get_pool


class ManageUserAction(str, Enum):
    block_user = 'block_user'
    unblock_user = 'unblock_user'
    new = 'new'
    delete_user = 'delete_user'

    def action_to_write(self) -> str:
        return {
            self.block_user: 'blocked',
            self.unblock_user: 'unblocked',
            self.new: 'new',
            self.delete_user: 'deleted',
        }[self]


def sql_connect() -> sqlalchemy.engine.Engine:
    return sqlalchemy_get_pool(5, 60)


def register_new_user(user_id: int, user_name: str | None, timestamp: datetime) -> None:
    """block, unblock or record as new user"""

    pool = sql_connect()
    with pool.connect() as conn:
        # compose & execute the query for USER_STATUSES_HISTORY table
        _write_new_user_status(conn, ManageUserAction.new, user_id, timestamp)

        # save in table users
        _save_new_user(conn, user_id, user_name, timestamp)
        # save in table user_preferences
        _save_default_notif_settings(conn, user_id)


def update_user_status(action: ManageUserAction, user_id: int) -> None:
    """block, unblock or record as new user"""

    timestamp = datetime.now()
    action_to_write = action.action_to_write()

    pool = sql_connect()
    with pool.connect() as conn:
        _change_status_in_table_users(conn, user_id, timestamp, action_to_write)
        _write_new_user_status(conn, action, user_id, timestamp)


def save_onboarding_step(user_id: int, step: str) -> None:
    """save the certain step in onboarding"""

    dict_steps = {
        'start': 0,
        'role_set': 10,
        'moscow_replied': 20,
        'region_set': 21,
        'urgency_set': 30,
        'finished': 80,
        'unrecognized': 99,
    }

    step_id = dict_steps.get(step, 99)

    pool = sql_connect()
    with pool.connect() as conn:
        conn.execute(
            sqlalchemy.text("""
                INSERT INTO user_onboarding (user_id, step_id, step_name, timestamp) 
                VALUES (:user_id, :step_id, :step_name, :timestamp)
            """),
            {'user_id': user_id, 'step_id': step_id, 'step_name': step, 'timestamp': datetime.now()},
        )


def _change_status_in_table_users(
    conn: sqlalchemy.engine.Connection, user_id: int, timestamp: datetime, action_to_write: str
) -> None:
    # compose & execute the query for USERS table
    conn.execute(
        sqlalchemy.text("""
            UPDATE users SET status =:status, status_change_date=:change_date 
            WHERE user_id=:user_id
        """),
        {'status': action_to_write, 'change_date': timestamp, 'user_id': user_id},
    )


def _write_new_user_status(
    conn: sqlalchemy.engine.Connection,
    action: ManageUserAction,
    user_id: int,
    timestamp: datetime,
) -> None:
    # compose & execute the query for USER_STATUSES_HISTORY table

    action_to_write = action.action_to_write()

    conn.execute(
        sqlalchemy.text("""
            INSERT INTO user_statuses_history (status, date, user_id) 
            VALUES (:status, :date, :user_id)
            ON CONFLICT (user_id, date) DO NOTHING
        """),
        {'status': action_to_write, 'date': timestamp, 'user_id': user_id},
    )


def _save_default_notif_settings(conn: sqlalchemy.engine.Connection, user_id: int) -> None:
    """if the user is new – set the default notification categories in user_preferences table"""

    stmt = sqlalchemy.text("""
                INSERT INTO user_preferences (user_id, preference, pref_id)
                VALUES (:user_id, :preference, :pref_id)
                ON CONFLICT (user_id, pref_id) DO NOTHING
        """)

    # default notification settings
    list_of_parameters = [
        (user_id, 'new_searches', 0),
        (user_id, 'status_changes', 1),
        (user_id, 'inforg_comments', 4),
        (user_id, 'first_post_changes', 8),
        (user_id, 'bot_news', 20),
    ]
    # apply default notification settings – write to PSQL in not exist (due to repetitions of pub/sub messages)
    for params in list_of_parameters:
        params_dict = {'user_id': params[0], 'preference': params[1], 'pref_id': params[2]}
        conn.execute(stmt, params_dict)

    logging.info(f'New user with id: {user_id}, default notif categories were set.')


def _save_new_user(conn: sqlalchemy.engine.Connection, user_id: int, username: str | None, timestamp: datetime) -> None:
    """if the user is new – save to users table"""

    # add the New User into table users
    result = conn.execute(
        sqlalchemy.text("""
            WITH rows AS
            (
                INSERT INTO users (user_id, username_telegram, reg_date) 
                VALUES (:user_id, :username, :reg_date)
                ON CONFLICT (user_id) DO NOTHING
                RETURNING 1
            )
            SELECT count(*) FROM rows;
        """),
        {'user_id': user_id, 'username': username, 'reg_date': timestamp},
    )
    num_of_updates = result.scalar()

    if num_of_updates == 0:
        logging.info(f'New user {user_id}, username {username} HAVE NOT BEEN SAVED due to duplication')
    else:
        logging.info(f'New user with id: {user_id}, username {username} saved.')

    # save onboarding start
    conn.execute(
        sqlalchemy.text("""
            INSERT INTO user_onboarding (user_id, step_id, step_name, timestamp) 
            VALUES (:user_id, :step_id, :step_name, :timestamp)
        """),
        {'user_id': user_id, 'step_id': 0, 'step_name': 'start', 'timestamp': datetime.now()},
    )
