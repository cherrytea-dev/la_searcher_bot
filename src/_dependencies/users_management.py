import logging
from datetime import datetime

import psycopg2

from _dependencies.commons import sql_connect_by_psycopg2
from _dependencies.pubsub import ManageUserAction


def save_updated_status_for_user(
    action: ManageUserAction, user_id: int, user_name: str | None, timestamp: datetime
) -> None:
    """block, unblock or record as new user"""

    action_to_write = action.action_to_write()

    # set PSQL connection & cursor
    with sql_connect_by_psycopg2() as conn, conn.cursor() as cur:
        if action != ManageUserAction.new:
            # compose & execute the query for USERS table
            cur.execute(
                """UPDATE users SET status =%s, status_change_date=%s WHERE user_id=%s;""",
                (action_to_write, timestamp, user_id),
            )
            conn.commit()

        # compose & execute the query for USER_STATUSES_HISTORY table
        cur.execute(
            """INSERT INTO user_statuses_history (status, date, user_id) VALUES (%s, %s, %s)
            ON CONFLICT (user_id, date) DO NOTHING
            ;""",
            (action_to_write, timestamp, user_id),
        )
        conn.commit()

        if action == ManageUserAction.new:
            # save in table users
            save_new_user(conn, user_id, user_name, timestamp)
            # save in table user_preferences
            save_default_notif_settings(conn, user_id)


def save_default_notif_settings(conn: psycopg2.extensions.connection, user_id: int) -> None:
    """if the user is new – set the default notification categories in user_preferences table"""

    # set PSQL connection & cursor
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


def save_new_user(
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
