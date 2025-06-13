import logging
import sqlalchemy

from _dependencies.commons import setup_logging, sqlalchemy_get_pool
from _dependencies.pubsub import process_pubsub_message

setup_logging(__package__)

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)
logging.warning('it is a synthetic warning')


def mark_up_onboarding_status_0(conn):
    """marks up Onboarding step_id=0 for existing old users"""

    # add the New User into table users
    result = conn.execute(
        sqlalchemy.text("""
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
                    """)
    )
    user_id_to_update = result.scalar()

    if user_id_to_update:
        logging.info(f'User {user_id_to_update}, will be assigned with onboarding pref_id=0')

        # save onboarding start
        conn.execute(
            sqlalchemy.text("""
                            INSERT INTO user_onboarding
                            (user_id, step_name, step_id, timestamp)
                            VALUES (:user_id, 'start', 0, '2023-05-14 12:39:00.000000')
                            """),
            {'user_id': user_id_to_update},
        )

    else:
        logging.info('There are no users to assign onboarding pref_id=0.')

    return None


def mark_up_onboarding_status_0_2(conn):
    """marks up Onboarding step_id=0 for existing old users"""

    # add the New User into table users
    result = conn.execute(
        sqlalchemy.text("""
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
                    """)
    )
    user_id_to_update = result.scalar()

    if user_id_to_update:
        logging.info(f'User {user_id_to_update}, will be assigned with onboarding pref_id=0')

        # save onboarding start
        conn.execute(
            sqlalchemy.text("""
                            INSERT INTO user_onboarding
                            (user_id, step_name, step_id, timestamp)
                            VALUES (:user_id, 'start', 0, '2023-05-14 12:39:00.000000')
                            """),
            {'user_id': user_id_to_update},
        )

    else:
        logging.info('There are no users to assign onboarding pref_id=0.')

    return None


def mark_up_onboarding_status_10(conn):
    """marks up Onboarding step_id=10 ('role_set') for existing old users"""

    # add the New User into table users
    result = conn.execute(
        sqlalchemy.text("""
                    select user_id
                    from user_view
                    where
                        reg_period='before' and
                        last_msg_role='yes' and
                        onb_step IS NULL and
                        folder_setting IS NULL
                    limit 1
                    """)
    )
    user_id_to_update = result.scalar()

    if user_id_to_update:
        logging.info(f'User {user_id_to_update}, will be assigned with onboarding pref_id=10')

        # save onboarding start
        conn.execute(
            sqlalchemy.text("""
                            INSERT INTO user_onboarding
                            (user_id, step_name, step_id, timestamp)
                            VALUES (:user_id, 'role_set', 10, '2023-05-14 12:39:00.000000')
                            """),
            {'user_id': user_id_to_update},
        )

    else:
        logging.info('There are no users to assign onboarding pref_id=10.')

    return None


def mark_up_onboarding_status_10_2(conn):
    """marks up Onboarding step_id=0 for existing old users"""

    # add the New User into table users
    result = conn.execute(
        sqlalchemy.text("""
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
                    """)
    )
    user_id_to_update = result.scalar()

    if user_id_to_update:
        logging.info(f'User {user_id_to_update}, will be assigned with onboarding pref_id=10')

        # save onboarding start
        conn.execute(
            sqlalchemy.text("""
                            INSERT INTO user_onboarding
                            (user_id, step_name, step_id, timestamp)
                            VALUES (:user_id, 'role_set', 10, '2023-05-14 12:39:00.000000')
                            """),
            {'user_id': user_id_to_update},
        )
    else:
        logging.info('There are no users to assign onboarding pref_id=10.')

    return None


def mark_up_onboarding_status_20(conn):
    """marks up Onboarding step_id=20 ('moscow_replied') for existing old users"""

    # add the New User into table users
    result = conn.execute(
        sqlalchemy.text("""
                    select user_id
                    from user_view
                    where
                        reg_period='before' and
                        last_msg_moscow='yes' and
                        onb_step IS NULL and
                        folder_setting IS NULL
                    limit 1
                    """)
    )
    user_id_to_update = result.scalar()

    if user_id_to_update:
        logging.info(f'User {user_id_to_update}, will be assigned with onboarding pref_id=20')

        # save onboarding start
        conn.execute(
            sqlalchemy.text("""
                            INSERT INTO user_onboarding
                            (user_id, step_name, step_id, timestamp)
                            VALUES (:user_id, 'moscow_replied', 20, '2023-05-14 12:39:00.000000')
                            """),
            {'user_id': user_id_to_update},
        )

    else:
        logging.info('There are no users to assign onboarding pref_id=20.')

    return None


def mark_up_onboarding_status_21(conn):
    """marks up Onboarding step_id=21 ('region_set') for existing old users"""

    # add the New User into table users
    result = conn.execute(
        sqlalchemy.text("""
                    select user_id
                    from user_view_21_new
                    limit 1
                    """)
    )
    user_id_to_update = result.scalar()

    if user_id_to_update:
        logging.info(f'User {user_id_to_update}, will be assigned with onboarding pref_id=21')

        # save onboarding start
        conn.execute(
            sqlalchemy.text("""
                            INSERT INTO user_onboarding
                            (user_id, step_name, step_id, timestamp)
                            VALUES (:user_id, 'region_set', 21, '2023-05-14 12:39:00.000000')
                            """),
            {'user_id': user_id_to_update},
        )

    else:
        logging.info('There are no users to assign onboarding pref_id=21.')

    return None


def mark_up_onboarding_status_80(conn):
    """marks up Onboarding step_id=80 for existing old users"""

    # add the New User into table users
    result = conn.execute(
        sqlalchemy.text("""
                    select user_id
                    from user_view
                    where
                        receives_summaries='yes' and
                        notif_setting='yes' and
                        onb_step is NULL and
                        reg_period='before'
                    limit 1
                    """)
    )
    user_id_to_update = result.scalar()

    if user_id_to_update:
        logging.info(f'User {user_id_to_update}, will be assigned with onboarding pref_id=80')

        # save onboarding start
        conn.execute(
            sqlalchemy.text("""
                            INSERT INTO user_onboarding
                            (user_id, step_name, step_id, timestamp)
                            VALUES (:user_id, 'finished', 80, '2023-05-14 12:39:00.000000')
                            """),
            {'user_id': user_id_to_update},
        )

    else:
        logging.info('There are no users to assign onboarding pref_id=80.')

    return None


def mark_up_onboarding_status_80_patch(conn):
    """marks up Onboarding step_id=80 for existing old users"""

    # add the New User into table users
    result = conn.execute(
        sqlalchemy.text("""
                    select user_id
                    from user_view_80
                    where receives_summaries='yes' and
                    notif_setting='yes' and
                    onb_step is NULL
                    limit 1
                    """)
    )
    user_id_to_update = result.scalar()

    if user_id_to_update:
        logging.info(f'User {user_id_to_update}, will be assigned with onboarding pref_id=80')

        # save onboarding start
        conn.execute(
            sqlalchemy.text("""
                            INSERT INTO user_onboarding
                            (user_id, step_name, step_id, timestamp)
                            VALUES (:user_id, 'finished', 80, '2023-05-14 12:39:00.000000')
                            """),
            {'user_id': user_id_to_update},
        )

    else:
        logging.info('There are no users to assign onboarding pref_id=80.')

    return None


def mark_up_onboarding_status_80_wo_dialogs(conn):
    """marks up Onboarding step_id=80 for existing old users w/o dialogs at all"""

    # add the New User into table users
    result = conn.execute(
        sqlalchemy.text("""
                    select user_id
                    from user_view_80_wo_last_msg
                    limit 1
                    """)
    )
    user_id_to_update = result.scalar()

    if user_id_to_update:
        logging.info(f'User {user_id_to_update}, will be assigned with onboarding pref_id=80')

        # save onboarding start
        conn.execute(
            sqlalchemy.text("""
                            INSERT INTO user_onboarding
                            (user_id, step_name, step_id, timestamp)
                            VALUES (:user_id, 'finished', 80, '2023-05-14 12:39:00.000000')
                            """),
            {'user_id': user_id_to_update},
        )

    else:
        logging.info('There are no users to assign onboarding pref_id=80.')

    return None


def mark_up_onboarding_status_80_just_got_summaries(conn):
    """marks up Onboarding step_id=80 for existing old users"""

    # add the New User into table users
    result = conn.execute(
        sqlalchemy.text("""
                    select user_id
                    from user_view_80
                    WHERE onb_step is NULL and receives_summaries is not null
                    limit 1
                    """)
    )
    user_id_to_update = result.scalar()

    if user_id_to_update:
        logging.info(f'User {user_id_to_update}, will be assigned with onboarding pref_id=80')

        # save onboarding start
        conn.execute(
            sqlalchemy.text("""
                            INSERT INTO user_onboarding
                            (user_id, step_name, step_id, timestamp)
                            VALUES (:user_id, 'finished', 80, '2023-05-14 12:39:00.000000')
                            """),
            {'user_id': user_id_to_update},
        )

    else:
        logging.info('There are no users to assign onboarding pref_id=80.')

    return None


def mark_up_onboarding_status_80_have_all_settings(conn):
    """marks up Onboarding step_id=80 for existing old users"""

    # add the New User into table users
    result = conn.execute(
        sqlalchemy.text("""
                    select user_id
                    from user_view
                    where notif_setting='yes' and folder_setting='yes' and onb_step is null
                    limit 1
                    """)
    )
    user_id_to_update = result.scalar()

    if user_id_to_update:
        logging.info(f'User {user_id_to_update}, will be assigned with onboarding pref_id=80')

        # save onboarding start
        conn.execute(
            sqlalchemy.text("""
                            INSERT INTO user_onboarding
                            (user_id, step_name, step_id, timestamp)
                            VALUES (:user_id, 'finished', 80, '2023-05-14 12:39:00.000000')
                            """),
            {'user_id': user_id_to_update},
        )

    else:
        logging.info('There are no users to assign onboarding pref_id=80.')

    return None


def mark_up_onboarding_status_80_self_deactivated(conn):
    """marks up Onboarding step_id=80 for existing old users"""

    # add the New User into table users
    result = conn.execute(
        sqlalchemy.text("""
                    WITH step_0 AS (
                        select t.user_id, CASE WHEN d.message_text LIKE 'отключ%' THEN 1 ELSE 0 END user_forced
                        from temp_onb_step_157 AS t
                        LEFT JOIN dialogs as d
                        ON t.user_id=d.user_id)
                    select user_id
                    from step_0
                    GROUP BY 1
                    HAVING max(user_forced) > 0
                    limit 1
                    """)
    )
    user_id_to_update = result.scalar()

    if user_id_to_update:
        logging.info(f'User {user_id_to_update}, will be assigned with onboarding pref_id=80')

        # save onboarding start
        conn.execute(
            sqlalchemy.text("""
                            INSERT INTO user_onboarding
                            (user_id, step_name, step_id, timestamp)
                            VALUES (:user_id, 'finished', 80, '2023-05-14 12:39:00.000000')
                            """),
            {'user_id': user_id_to_update},
        )
        # delete from temp table
        conn.execute(
            sqlalchemy.text("""
                            DELETE FROM temp_onb_step_157
                            WHERE user_id=:user_id
                            """),
            {'user_id': user_id_to_update},
        )

    else:
        logging.info('There are no users to assign onboarding pref_id=80.')

    return None


def mark_up_onboarding_status_99(conn):
    """marks up Onboarding step_id=99 for existing old users"""

    # add the New User into table users
    result = conn.execute(
        sqlalchemy.text("""
                    select user_id
                    from temp_onb_step_157
                    limit 1
                    """)
    )
    user_id_to_update = result.scalar()

    if user_id_to_update:
        logging.info(f'User {user_id_to_update}, will be assigned with onboarding pref_id=80')

        # save onboarding start
        conn.execute(
            sqlalchemy.text("""
                            INSERT INTO user_onboarding
                            (user_id, step_name, step_id, timestamp)
                            VALUES (:user_id, 'unrecognized', 99, '2023-05-14 12:39:00.000000')
                            """),
            {'user_id': user_id_to_update},
        )
        # delete from temp table
        conn.execute(
            sqlalchemy.text("""
                            DELETE FROM temp_onb_step_157
                            WHERE user_id=:user_id
                            """),
            {'user_id': user_id_to_update},
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

    pool = sqlalchemy_get_pool(5, 60)
    with pool.connect() as conn:
        try:
            # mark_up_onboarding_status_0(conn)
            # mark_up_onboarding_status_10(conn)
            # mark_up_onboarding_status_20(conn)
            # mark_up_onboarding_status_21(conn)
            # mark_up_onboarding_status_80(conn)
            # mark_up_onboarding_status_80_patch(conn)
            # mark_up_onboarding_status_80_wo_dialogs(conn)

            for i in range(20):
                # mark_up_onboarding_status_0_2(conn)
                # mark_up_onboarding_status_10_2(conn)
                # mark_up_onboarding_status_80_just_got_summaries(conn)
                # mark_up_onboarding_status_80_have_all_settings(conn)
                # mark_up_onboarding_status_80_self_deactivated(conn)
                # mark_up_onboarding_status_99(conn)
                pass

        except Exception as e:
            logging.error('User activation script failed')
            logging.exception(e)

    return 'ok'
