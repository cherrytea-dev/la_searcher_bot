import base64
import logging
from datetime import datetime
from typing import Any, Dict, Optional

from _dependencies.commons import sql_connect_by_psycopg2
from _dependencies.misc import process_pubsub_message


def save_onboarding_step(user_id: int, step_name: str, timestamp: datetime) -> None:
    """save a step of onboarding"""

    dict_steps = {
        'start': 0,
        'role_set': 10,
        'moscow_replied': 20,
        'region_set': 21,
        'urgency_set': 30,
        'finished': 80,
        'unrecognized': 99,
    }

    try:
        step_id = dict_steps[step_name]
    except:  # noqa
        step_id = 99

    # set PSQL connection & cursor
    conn = sql_connect_by_psycopg2()
    cur = conn.cursor()

    cur.execute(
        """INSERT INTO user_onboarding (user_id, step_id, step_name, timestamp) VALUES (%s, %s, %s, %s);""",
        (user_id, step_id, step_name, timestamp),
    )

    conn.commit()

    # close connection & cursor
    cur.close()
    conn.close()

    return None


def save_updated_status_for_user(action: str, user_id: int, timestamp: datetime) -> None:
    """block, unblock or record as new user"""

    action_dict = {'block_user': 'blocked', 'unblock_user': 'unblocked', 'new': 'new', 'delete_user': 'deleted'}
    action_to_write = action_dict[action]

    # set PSQL connection & cursor
    conn = sql_connect_by_psycopg2()
    cur = conn.cursor()

    if action_to_write != 'new':
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

    # close connection & cursor
    cur.close()
    conn.close()

    return None


def save_new_user(user_id: int, username: str, timestamp: datetime) -> None:
    """if the user is new – save to users table"""

    # set PSQL connection & cursor
    conn = sql_connect_by_psycopg2()
    cur = conn.cursor()

    if username == 'unknown':
        username = None

    # add the New User into table users
    cur.execute(
        """
                    WITH rows AS
                    (
                        INSERT INTO users (user_id, username_telegram, reg_date) values (%s, %s, %s)
                        ON CONFLICT (user_id) DO NOTHING
                        RETURNING 1
                    )
                    SELECT count(*) FROM rows
                    ;""",
        (user_id, username, timestamp),
    )
    conn.commit()
    num_of_updates = cur.fetchone()[0]

    if num_of_updates == 0:
        logging.info(f'New user {user_id}, username {username} HAVE NOT BEEN SAVED ' f'due to duplication')
    else:
        logging.info(f'New user with id: {user_id}, username {username} saved.')

    # save onboarding start
    cur.execute(
        """INSERT INTO user_onboarding (user_id, step_id, step_name, timestamp) VALUES (%s, %s, %s, %s);""",
        (user_id, 0, 'start', datetime.now()),
    )
    conn.commit()

    # close connection & cursor
    cur.close()
    conn.close()

    return None


def save_default_notif_settings(user_id: int) -> None:
    """if the user is new – set the default notification categories in user_preferences table"""

    # set PSQL connection & cursor
    conn = sql_connect_by_psycopg2()
    cur = conn.cursor()

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
                        SELECT count(*) FROM rows
                        ;""",
            parameters,
        )
        conn.commit()
        num_of_updates += cur.fetchone()[0]

    # close connection & cursor
    cur.close()
    conn.close()

    logging.info(f'New user with id: {user_id}, {num_of_updates} default notif categories were set.')

    return None


def main(event: Dict[str, bytes], context: str) -> str:  # noqa
    """main function"""

    try:
        received_dict = process_pubsub_message(event)
        if received_dict:
            action = received_dict['action']

            if action in {'block_user', 'unblock_user', 'new', 'delete_user'}:
                curr_user_id = received_dict['info']['user']
                try:
                    timestamp = datetime.datetime.strptime(received_dict['time'], '%Y-%m-%d %H:%M:%S.%f')

                except:  # noqa
                    timestamp = datetime.datetime.now()
                # save in table user_statuses_history and table users (for non-new users)
                save_updated_status_for_user(action, curr_user_id, timestamp)

                if action == 'new':
                    username = received_dict['info']['username']
                    # save in table users
                    save_new_user(curr_user_id, username, timestamp)
                    # save in table user_preferences
                    save_default_notif_settings(curr_user_id)

            elif action in {'update_onboarding'}:
                curr_user_id = received_dict['info']['user']
                try:
                    timestamp = datetime.datetime.strptime(received_dict['time'], '%Y-%m-%d %H:%M:%S.%f')
                except:  # noqa
                    timestamp = datetime.datetime.now()
                try:
                    step_name = received_dict['step']
                except:  # noqa
                    step_name = 'unrecognized'
                save_onboarding_step(curr_user_id, step_name, timestamp)

    except Exception as e:
        logging.error('User management script failed:' + repr(e))
        logging.exception(e)

    return 'ok'
