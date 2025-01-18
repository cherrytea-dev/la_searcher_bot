import base64
import logging

from _dependencies.commons import setup_google_logging, sql_connect_by_psycopg2

setup_google_logging()

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)
logging.warning('it is a synthetic warning')


def process_pubsub_message(event: dict):
    """convert incoming pub/sub message into regular data"""

    # FIXME
    logging.info(f'RECEIVED EVENT {event}')
    # FIXME ^^^
    # receiving message text from pub/sub
    if 'data' in event:
        received_message_from_pubsub = base64.b64decode(event['data']).decode('utf-8')
        print(f'DECODED DATA from EVENT {received_message_from_pubsub}')
        try:
            received_message_from_pubsub.replace('null', 'None')
            encoded_to_ascii = eval(received_message_from_pubsub)
            data_in_ascii = encoded_to_ascii['data']
            message_in_ascii = data_in_ascii['message']
        except Exception as e:
            logging.exception(e)
            message_in_ascii = None

    else:
        received_message_from_pubsub = 'I cannot read message from pub/sub'
        message_in_ascii = None

    logging.info(f'received from pubsub {received_message_from_pubsub}')
    logging.info(f'message in ascii {message_in_ascii}')

    return message_in_ascii


def mark_up_onboarding_status_0(cur):
    """marks up Onboarding step_id=0 for existing old users"""

    # add the New User into table users
    cur.execute("""
                    WITH
                        onb AS (
                            select user_id, MAX(step_id) AS onb_step
                            from user_onboarding GROUP BY 1),
                        step_1 AS (
                            select u.user_id, u.reg_date, o.onb_step,
                            CASE WHEN u.reg_date<'2023-05-14 12:40:00.000000' THEN 'before' ELSE 'after' END reg_period
                            FROM users as u
                            LEFT JOIN onb AS o
                            ON u.user_id=o.user_id),
                        step_2 AS (
                            SELECT user_id
                            FROM step_1
                            WHERE reg_period='before' AND onb_step IS NULL),
                        s0 AS (
                            select user_id, timestamp, message_text, MAX(timestamp) OVER (PARTITION BY user_id),
                            CASE WHEN timestamp=(MAX(timestamp) OVER (PARTITION BY user_id)) THEN 1 ELSE 0 END AS check
                            FROM dialogs
                            WHERE author='user'),
                        only_starters AS (
                            SELECT user_id, timestamp
                            FROM s0
                            WHERE s0.check=1 AND message_text='/start')

                    SELECT u.user_id
                    FROM step_2 AS u
                    LEFT JOIN only_starters AS o
                    ON u.user_id=o.user_id
                    WHERE o.user_id IS NOT NULL
                    LIMIT 1;
                    ;""")
    user_id_to_update = cur.fetchone()

    if user_id_to_update and isinstance(user_id_to_update, tuple) and len(user_id_to_update) > 0:
        user_id_to_update = user_id_to_update[0]
        logging.info(f'User {user_id_to_update}, will be assigned with onboarding pref_id=0')

        # save onboarding start
        cur.execute(
            """
                            INSERT INTO user_onboarding
                            (user_id, step_name, step_id, timestamp)
                            VALUES (%s, 'start', 0, '2023-05-14 12:39:00.000000')
                            ;""",
            (user_id_to_update,),
        )

    else:
        logging.info('There are no users to assign onboarding pref_id=0.')

    return None


def mark_up_onboarding_status_0_2(cur):
    """marks up Onboarding step_id=0 for existing old users"""

    # add the New User into table users
    cur.execute("""
                    with
                        reg_setting AS (
                            select distinct user_id, 'yes' folder_setting
                            from user_regional_preferences),
                        onboard_step AS (
                            select user_id, MAX(step_id) AS onb_step
                            from user_onboarding GROUP BY 1)

                    SELECT u.user_id from users as u
                    LEFT JOIN reg_setting AS rs
                    ON rs.user_id=u.user_id
                    LEFT JOIN onboard_step AS o
                    ON o.user_id=u.user_id
                    WHERE o.onb_step IS NULL and rs.folder_setting IS NULL and u.role is null
                    LIMIT 1
                    ;""")
    user_id_to_update = cur.fetchone()

    if user_id_to_update and isinstance(user_id_to_update, tuple) and len(user_id_to_update) > 0:
        user_id_to_update = user_id_to_update[0]
        logging.info(f'User {user_id_to_update}, will be assigned with onboarding pref_id=0')

        # save onboarding start
        cur.execute(
            """
                            INSERT INTO user_onboarding
                            (user_id, step_name, step_id, timestamp)
                            VALUES (%s, 'start', 0, '2023-05-14 12:39:00.000000')
                            ;""",
            (user_id_to_update,),
        )

    else:
        logging.info('There are no users to assign onboarding pref_id=0.')

    return None


def mark_up_onboarding_status_10(cur):
    """marks up Onboarding step_id=10 ('role_set') for existing old users"""

    # add the New User into table users
    cur.execute("""
                    select user_id
                    from user_view
                    where
                        reg_period='before' and
                        last_msg_role='yes' and
                        onb_step IS NULL and
                        folder_setting IS NULL
                    limit 1;
                """)
    user_id_to_update = cur.fetchone()

    if user_id_to_update and isinstance(user_id_to_update, tuple) and len(user_id_to_update) > 0:
        user_id_to_update = user_id_to_update[0]
        logging.info(f'User {user_id_to_update}, will be assigned with onboarding pref_id=10')

        # save onboarding start
        cur.execute(
            """
                            INSERT INTO user_onboarding
                            (user_id, step_name, step_id, timestamp)
                            VALUES (%s, 'role_set', 10, '2023-05-14 12:39:00.000000')
                            ;""",
            (user_id_to_update,),
        )

    else:
        logging.info('There are no users to assign onboarding pref_id=10.')

    return None


def mark_up_onboarding_status_10_2(cur):
    """marks up Onboarding step_id=0 for existing old users"""

    # add the New User into table users
    cur.execute("""
                    with
                        reg_setting AS (
                            select distinct user_id, 'yes' folder_setting
                            from user_regional_preferences),
                        onboard_step AS (
                            select user_id, MAX(step_id) AS onb_step
                            from user_onboarding GROUP BY 1)

                    SELECT u.user_id from users as u
                    LEFT JOIN reg_setting AS rs
                    ON rs.user_id=u.user_id
                    LEFT JOIN onboard_step AS o
                    ON o.user_id=u.user_id
                    WHERE o.onb_step IS NULL and rs.folder_setting IS NULL and u.role is NOT null
                    LIMIT 1
                    ;""")
    user_id_to_update = cur.fetchone()

    if user_id_to_update and isinstance(user_id_to_update, tuple) and len(user_id_to_update) > 0:
        user_id_to_update = user_id_to_update[0]
        logging.info(f'User {user_id_to_update}, will be assigned with onboarding pref_id=10')

        # save onboarding start
        cur.execute(
            """
                            INSERT INTO user_onboarding
                            (user_id, step_name, step_id, timestamp)
                            VALUES (%s, 'role_set', 10, '2023-05-14 12:39:00.000000')
                            ;""",
            (user_id_to_update,),
        )
    else:
        logging.info('There are no users to assign onboarding pref_id=10.')

    return None


def mark_up_onboarding_status_20(cur):
    """marks up Onboarding step_id=20 ('moscow_replied') for existing old users"""

    # add the New User into table users
    cur.execute("""
                    select user_id
                    from user_view
                    where
                        reg_period='before' and
                        last_msg_moscow='yes' and
                        onb_step IS NULL and
                        folder_setting IS NULL
                    limit 1;
                """)
    user_id_to_update = cur.fetchone()

    if user_id_to_update and isinstance(user_id_to_update, tuple) and len(user_id_to_update) > 0:
        user_id_to_update = user_id_to_update[0]
        logging.info(f'User {user_id_to_update}, will be assigned with onboarding pref_id=20')

        # save onboarding start
        cur.execute(
            """
                            INSERT INTO user_onboarding
                            (user_id, step_name, step_id, timestamp)
                            VALUES (%s, 'moscow_replied', 20, '2023-05-14 12:39:00.000000')
                            ;""",
            (user_id_to_update,),
        )

    else:
        logging.info('There are no users to assign onboarding pref_id=20.')

    return None


def mark_up_onboarding_status_21(cur):
    """marks up Onboarding step_id=21 ('region_set') for existing old users"""

    # add the New User into table users
    cur.execute("""
                    select user_id
                    from user_view_21_new
                    limit 1;
                """)
    user_id_to_update = cur.fetchone()

    if user_id_to_update and isinstance(user_id_to_update, tuple) and len(user_id_to_update) > 0:
        user_id_to_update = user_id_to_update[0]
        logging.info(f'User {user_id_to_update}, will be assigned with onboarding pref_id=21')

        # save onboarding start
        cur.execute(
            """
                            INSERT INTO user_onboarding
                            (user_id, step_name, step_id, timestamp)
                            VALUES (%s, 'region_set', 21, '2023-05-14 12:39:00.000000')
                            ;""",
            (user_id_to_update,),
        )

    else:
        logging.info('There are no users to assign onboarding pref_id=21.')

    return None


def mark_up_onboarding_status_80(cur):
    """marks up Onboarding step_id=80 for existing old users"""

    # add the New User into table users
    cur.execute("""
                    select user_id
                    from user_view
                    where
                        receives_summaries='yes' and
                        notif_setting='yes' and
                        onb_step is NULL and
                        reg_period='before'
                    limit 1;
                """)
    user_id_to_update = cur.fetchone()

    if user_id_to_update and isinstance(user_id_to_update, tuple) and len(user_id_to_update) > 0:
        user_id_to_update = user_id_to_update[0]
        logging.info(f'User {user_id_to_update}, will be assigned with onboarding pref_id=80')

        # save onboarding start
        cur.execute(
            """
                            INSERT INTO user_onboarding
                            (user_id, step_name, step_id, timestamp)
                            VALUES (%s, 'finished', 80, '2023-05-14 12:39:00.000000')
                            ;""",
            (user_id_to_update,),
        )

    else:
        logging.info('There are no users to assign onboarding pref_id=80.')

    return None


def mark_up_onboarding_status_80_patch(cur):
    """marks up Onboarding step_id=80 for existing old users"""

    # add the New User into table users
    cur.execute("""
                    select user_id
                    from user_view_80
                    where receives_summaries='yes' and
                    notif_setting='yes' and
                    onb_step is NULL
                    limit 1;
                """)
    user_id_to_update = cur.fetchone()

    if user_id_to_update and isinstance(user_id_to_update, tuple) and len(user_id_to_update) > 0:
        user_id_to_update = user_id_to_update[0]
        logging.info(f'User {user_id_to_update}, will be assigned with onboarding pref_id=80')

        # save onboarding start
        cur.execute(
            """
                            INSERT INTO user_onboarding
                            (user_id, step_name, step_id, timestamp)
                            VALUES (%s, 'finished', 80, '2023-05-14 12:39:00.000000')
                            ;""",
            (user_id_to_update,),
        )

    else:
        logging.info('There are no users to assign onboarding pref_id=80.')

    return None


def mark_up_onboarding_status_80_wo_dialogs(cur):
    """marks up Onboarding step_id=80 for existing old users w/o dialogs at all"""

    # add the New User into table users
    cur.execute("""
                    select user_id
                    from user_view_80_wo_last_msg
                    limit 1;
                """)
    user_id_to_update = cur.fetchone()

    if user_id_to_update and isinstance(user_id_to_update, tuple) and len(user_id_to_update) > 0:
        user_id_to_update = user_id_to_update[0]
        logging.info(f'User {user_id_to_update}, will be assigned with onboarding pref_id=80')

        # save onboarding start
        cur.execute(
            """
                            INSERT INTO user_onboarding
                            (user_id, step_name, step_id, timestamp)
                            VALUES (%s, 'finished', 80, '2023-05-14 12:39:00.000000')
                            ;""",
            (user_id_to_update,),
        )

    else:
        logging.info('There are no users to assign onboarding pref_id=80.')

    return None


def mark_up_onboarding_status_80_just_got_summaries(cur):
    """marks up Onboarding step_id=80 for existing old users"""

    # add the New User into table users
    cur.execute("""
                    select *
                    from user_view_80
                    WHERE onb_step is NULL and receives_summaries is not null
                    limit 1;
                """)
    user_id_to_update = cur.fetchone()

    if user_id_to_update and isinstance(user_id_to_update, tuple) and len(user_id_to_update) > 0:
        user_id_to_update = user_id_to_update[0]
        logging.info(f'User {user_id_to_update}, will be assigned with onboarding pref_id=80')

        # save onboarding start
        cur.execute(
            """
                            INSERT INTO user_onboarding
                            (user_id, step_name, step_id, timestamp)
                            VALUES (%s, 'finished', 80, '2023-05-14 12:39:00.000000')
                            ;""",
            (user_id_to_update,),
        )

    else:
        logging.info('There are no users to assign onboarding pref_id=80.')

    return None


def mark_up_onboarding_status_80_have_all_settings(cur):
    """marks up Onboarding step_id=80 for existing old users"""

    # add the New User into table users
    cur.execute("""
                    select user_id
                    from user_view
                    where notif_setting='yes' and folder_setting='yes' and onb_step is null
                    limit 1;
                """)
    user_id_to_update = cur.fetchone()

    if user_id_to_update and isinstance(user_id_to_update, tuple) and len(user_id_to_update) > 0:
        user_id_to_update = user_id_to_update[0]
        logging.info(f'User {user_id_to_update}, will be assigned with onboarding pref_id=80')

        # save onboarding start
        cur.execute(
            """
                            INSERT INTO user_onboarding
                            (user_id, step_name, step_id, timestamp)
                            VALUES (%s, 'finished', 80, '2023-05-14 12:39:00.000000')
                            ;""",
            (user_id_to_update,),
        )

    else:
        logging.info('There are no users to assign onboarding pref_id=80.')

    return None


def mark_up_onboarding_status_80_self_deactivated(cur):
    """marks up Onboarding step_id=80 for existing old users"""

    # add the New User into table users
    cur.execute("""
                    WITH step_0 AS (
                        select t.user_id, CASE WHEN d.message_text LIKE 'отключ%' THEN 1 ELSE 0 END user_forced
                        from temp_onb_step_157 AS t
                        LEFT JOIN dialogs as d
                        ON t.user_id=d.user_id)
                    select user_id
                    from step_0
                    GROUP BY 1
                    HAVING max(user_forced) > 0
                    limit 1;
                """)
    user_id_to_update = cur.fetchone()

    if user_id_to_update and isinstance(user_id_to_update, tuple) and len(user_id_to_update) > 0:
        user_id_to_update = user_id_to_update[0]
        logging.info(f'User {user_id_to_update}, will be assigned with onboarding pref_id=80')

        # save onboarding start
        cur.execute(
            """
                            INSERT INTO user_onboarding
                            (user_id, step_name, step_id, timestamp)
                            VALUES (%s, 'finished', 80, '2023-05-14 12:39:00.000000')
                            ;""",
            (user_id_to_update,),
        )
        # save onboarding start
        cur.execute(
            """
                            DELETE FROM temp_onb_step_157
                            WHERE user_id=%s
                                    ;""",
            (user_id_to_update,),
        )

    else:
        logging.info('There are no users to assign onboarding pref_id=80.')

    return None


def mark_up_onboarding_status_99(cur):
    """marks up Onboarding step_id=99 for existing old users"""

    # add the New User into table users
    cur.execute("""
                    select user_id
                    from temp_onb_step_157
                    limit 1;
                """)
    user_id_to_update = cur.fetchone()

    if user_id_to_update and isinstance(user_id_to_update, tuple) and len(user_id_to_update) > 0:
        user_id_to_update = user_id_to_update[0]
        logging.info(f'User {user_id_to_update}, will be assigned with onboarding pref_id=80')

        # save onboarding start
        cur.execute(
            """
                            INSERT INTO user_onboarding
                            (user_id, step_name, step_id, timestamp)
                            VALUES (%s, 'unrecognized', 99, '2023-05-14 12:39:00.000000')
                            ;""",
            (user_id_to_update,),
        )
        # save onboarding start
        cur.execute(
            """
                            DELETE FROM temp_onb_step_157
                            WHERE user_id=%s
                                    ;""",
            (user_id_to_update,),
        )

    else:
        logging.info('There are no users to assign onboarding pref_id=80.')

    return None


def main(event, context):  # noqa
    """main function"""

    # FIXME –testing logging, which, seems, disappeared
    logging.info('this is 1st logging line')
    print('this is 1st print line')
    # FIXME ^^^

    # set PSQL connection & cursor
    conn = sql_connect_by_psycopg2()
    cur = conn.cursor()

    try:
        # mark_up_onboarding_status_0(cur)
        # mark_up_onboarding_status_10(cur)
        # mark_up_onboarding_status_20(cur)
        # mark_up_onboarding_status_21(cur)
        # mark_up_onboarding_status_80(cur)
        # mark_up_onboarding_status_80_patch(cur)
        # mark_up_onboarding_status_80_wo_dialogs(cur)

        for i in range(20):
            # mark_up_onboarding_status_0_2(cur)
            # mark_up_onboarding_status_10_2(cur)
            # mark_up_onboarding_status_80_just_got_summaries(cur)
            # mark_up_onboarding_status_80_have_all_settings(cur)
            # mark_up_onboarding_status_80_self_deactivated(cur)
            # mark_up_onboarding_status_99(cur)
            pass

    except Exception as e:
        logging.error('User activation script failed')
        logging.exception(e)

    # close connection & cursor
    cur.close()
    conn.close()

    return 'ok'
