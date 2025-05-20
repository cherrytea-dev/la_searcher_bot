import logging
from datetime import datetime
from enum import Enum

import psycopg2

from _dependencies.commons import sql_connect_by_psycopg2


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


def register_new_user(user_id: int, user_name: str | None, timestamp: datetime) -> None:
    """block, unblock or record as new user"""

    with sql_connect_by_psycopg2() as conn:
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

    # set PSQL connection & cursor
    with sql_connect_by_psycopg2() as conn:
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

    # set PSQL connection & cursor
    with sql_connect_by_psycopg2() as conn, conn.cursor() as cur:
        cur.execute(
            """
                INSERT INTO user_onboarding (user_id, step_id, step_name, timestamp) VALUES (%s, %s, %s, %s);
            """,
            (user_id, step_id, step, datetime.now()),
        )
        conn.commit()


def _change_status_in_table_users(
    conn: psycopg2.extensions.connection, user_id: int, timestamp: datetime, action_to_write: str
) -> None:
    # compose & execute the query for USERS table
    with conn.cursor() as cur:
        cur.execute(
            """UPDATE users SET status =%s, status_change_date=%s WHERE user_id=%s;""",
            (action_to_write, timestamp, user_id),
        )
        conn.commit()


def _write_new_user_status(
    conn: psycopg2.extensions.connection,
    action: ManageUserAction,
    user_id: int,
    timestamp: datetime,
) -> None:
    # compose & execute the query for USER_STATUSES_HISTORY table

    action_to_write = action.action_to_write()

    with conn.cursor() as cur:
        # compose & execute the query for USER_STATUSES_HISTORY table
        cur.execute(
            """INSERT INTO user_statuses_history (status, date, user_id) VALUES (%s, %s, %s)
            ON CONFLICT (user_id, date) DO NOTHING
            ;""",
            (action_to_write, timestamp, user_id),
        )
        conn.commit()


def _save_default_notif_settings(conn: psycopg2.extensions.connection, user_id: int) -> None:
    """if the user is new – set the default notification categories in user_preferences table"""

    with conn.cursor() as cur:
        num_of_updates = 0

        # default notification settings
        list_of_parameters = [
            (user_id, 'new_searches', 0),
            (user_id, 'status_changes', 1),
            (user_id, 'inforg_comments', 4),
            (user_id, 'first_post_changes', 8),
            (user_id, 'bot_news', 20),
        ]

        # apply default notification settings – write to PSQL in not exist (due to repetitions of pub/sub messages)
        for parameters in list_of_parameters:
            cur.execute(
                """
                    WITH rows AS
                    (
                        INSERT INTO user_preferences (user_id, preference, pref_id) values (%s, %s, %s)
                        ON CONFLICT (user_id, pref_id) DO NOTHING
                        RETURNING 1
                    )
                    SELECT count(*) FROM rows;
                """,
                parameters,
            )
            conn.commit()
            num_of_updates += cur.fetchone()[0]  # type:ignore[index]

    logging.info(f'New user with id: {user_id}, {num_of_updates} default notif categories were set.')


def _save_new_user(
    conn: psycopg2.extensions.connection, user_id: int, username: str | None, timestamp: datetime
) -> None:
    """if the user is new – save to users table"""

    with conn.cursor() as cur:
        # add the New User into table users
        cur.execute(
            """
                WITH rows AS
                (
                    INSERT INTO users (user_id, username_telegram, reg_date) values (%s, %s, %s)
                    ON CONFLICT (user_id) DO NOTHING
                    RETURNING 1
                )
                SELECT count(*) FROM rows;
            """,
            (user_id, username, timestamp),
        )
        conn.commit()
        num_of_updates = cur.fetchone()[0]  # type:ignore[index]

        if num_of_updates == 0:
            logging.info(f'New user {user_id}, username {username} HAVE NOT BEEN SAVED ' f'due to duplication')
        else:
            logging.info(f'New user with id: {user_id}, username {username} saved.')

        # save onboarding start
        cur.execute(
            """
            INSERT INTO user_onboarding (user_id, step_id, step_name, timestamp) VALUES (%s, %s, %s, %s);
            """,
            (user_id, 0, 'start', datetime.now()),
        )
        conn.commit()
