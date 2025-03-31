import datetime
from typing import Tuple

from psycopg2.extensions import cursor


def delete_last_user_inline_dialogue(cur, user_id: int) -> None:
    """Delete form DB the user's last interaction via inline buttons"""

    cur.execute("""DELETE FROM communications_last_inline_msg WHERE user_id=%s;""", (user_id,))
    return None


def get_last_user_inline_dialogue(cur, user_id: int) -> list:
    """Get from DB the user's last interaction via inline buttons"""

    cur.execute("""SELECT message_id FROM communications_last_inline_msg WHERE user_id=%s;""", (user_id,))
    message_id_lines = cur.fetchall()

    message_id_list = []
    if message_id_lines and len(message_id_lines) > 0:
        for message_id_line in message_id_lines:
            message_id_list.append(message_id_line[0])

    return message_id_list


def save_last_user_inline_dialogue(cur, user_id: int, message_id: int) -> None:
    """Save to DB the user's last interaction via inline buttons"""

    cur.execute(
        """INSERT INTO communications_last_inline_msg 
                    (user_id, timestamp, message_id) values (%s, CURRENT_TIMESTAMP AT TIME ZONE 'UTC', %s)
                    ON CONFLICT (user_id, message_id) DO 
                    UPDATE SET timestamp=CURRENT_TIMESTAMP AT TIME ZONE 'UTC';""",
        (user_id, message_id),
    )
    return None


def get_search_follow_mode(cur, user_id: int):
    cur.execute("""SELECT filter_name FROM user_pref_search_filtering WHERE user_id=%s LIMIT 1;""", (user_id,))
    result_fetched = cur.fetchone()
    result = result_fetched and 'whitelist' in result_fetched[0]
    return result


def save_user_message_to_bot(cur: cursor, user_id: int, got_message: str) -> None:
    """save user's message to bot in psql"""

    cur.execute(
        """INSERT INTO dialogs (user_id, author, timestamp, message_text) values (%s, %s, %s, %s);""",
        (user_id, 'user', datetime.datetime.now(), got_message),
    )

    return None


def get_user_sys_roles(cur, user_id):
    """Return user's roles in system"""

    user_roles = ['']

    try:
        cur.execute('SELECT role FROM user_roles WHERE user_id=%s;', (user_id,))
        lines = cur.fetchall()
        for line in lines:
            user_roles.append(line[0])
        logging.info(f'user {user_id} role has roles {user_roles=}')
    except Exception as e:
        logging.info(f'failed to get from user_roles for user {user_id}')
        logging.exception(e)

    return user_roles


def get_user_role(cur: cursor, user_id: int):
    """Return user's role"""

    user_role = None

    try:
        cur.execute('SELECT role FROM users WHERE user_id=%s LIMIT 1;', (user_id,))
        user_role = cur.fetchone()
        if user_role:
            user_role = user_role[0]

        logging.info(f'user {user_id} role is {user_role}')

    except Exception as e:
        logging.info(f'failed to get user role for user {user_id}')
        logging.exception(e)

    return user_role


def add_user_sys_role(cur, user_id, sys_role_name):
    """Saves user's role in system"""

    try:
        cur.execute(
            """INSERT INTO user_roles (user_id, role) 
                    VALUES (%s, %s) ON CONFLICT DO NOTHING;""",
            (user_id, sys_role_name),
        )

    except Exception as e:
        logging.info(f'failed to insert into user_roles for user {user_id}')
        logging.exception(e)

    return None


def delete_user_sys_role(cur, user_id, sys_role_name):
    """Deletes user's role in system"""

    try:
        cur.execute(
            """DELETE FROM user_roles 
                    WHERE user_id=%s and role=%s;""",
            (user_id, sys_role_name),
        )

    except Exception as e:
        logging.info(f'failed to delete from user_roles for user {user_id}')
        logging.exception(e)

    return None


def delete_user_coordinates(cur: cursor, user_id: int) -> None:
    """Delete the saved user "home" coordinates"""

    cur.execute('DELETE FROM user_coordinates WHERE user_id=%s;', (user_id,))

    return None


def show_user_coordinates(cur: cursor, user_id: int) -> Tuple[str, str]:
    """Return the saved user "home" coordinates"""

    cur.execute("""SELECT latitude, longitude FROM user_coordinates WHERE user_id=%s LIMIT 1;""", (user_id,))

    try:
        lat, lon = list(cur.fetchone())
    except:  # noqa
        lat = None
        lon = None

    return lat, lon


def save_user_coordinates(cur: cursor, user_id: int, input_latitude: float, input_longitude: float) -> None:
    """Save / update user "home" coordinates"""

    cur.execute('DELETE FROM user_coordinates WHERE user_id=%s;', (user_id,))

    now = datetime.datetime.now()
    cur.execute(
        """INSERT INTO user_coordinates (user_id, latitude, longitude, upd_time) values (%s, %s, %s, %s);""",
        (user_id, input_latitude, input_longitude, now),
    )

    return None
