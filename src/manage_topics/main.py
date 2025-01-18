import datetime
import json
import logging
import random
from typing import Any, Dict, Optional

import sqlalchemy

from _dependencies.commons import Topics, publish_to_pubsub, setup_google_logging, sqlalchemy_get_pool
from _dependencies.misc import notify_admin, process_pubsub_message

setup_google_logging()


def sql_connect() -> sqlalchemy.engine.Engine:
    return sqlalchemy_get_pool(5, 5)


def save_visibility_for_topic(topic_id: int, visibility: bool):
    """save in SQL if topic was deleted, hidden or unhidden"""

    try:
        pool = sql_connect()
        with pool.connect() as conn:
            # MEMO: visibility can be only:
            # 'deleted' – topic is permanently deleted
            # 'hidden' – topic is hidden from public access, can become visible in the future
            # 'ok' – regular topics with public visibility

            if 1 == 0:
                # clear the prev visibility status
                stmt = sqlalchemy.text("""DELETE FROM search_health_check WHERE search_forum_num=:a;""")
                conn.execute(stmt, a=topic_id)

                # set the new visibility status
                stmt = sqlalchemy.text("""INSERT INTO search_health_check (search_forum_num, timestamp, status)
                                                VALUES (:a, :b, :c);""")
                conn.execute(stmt, a=topic_id, b=datetime.datetime.now(), c=visibility)

                logging.info(f'Visibility is set={visibility} for topic_id={topic_id}')

                # FIXME – to be added: INSERT INTO change_log
                # it requires also right execution inside compose notifications

            else:
                notify_admin(f'WE FAKED VISIBILITY UPDATE: topic_id={topic_id}, visibility={visibility}')
            conn.close()
        pool.dispose()

    except Exception as e:
        logging.exception(e)

    return None


def save_status_for_topic(topic_id: int, status: str) -> int:
    """save in SQL if topic status was updated: active search, search finished etc."""

    change_log_id = None
    try:
        pool = sql_connect()
        conn = pool.connect()

        # check if this topic is already marked with the new status:
        stmt = sqlalchemy.text("""SELECT id FROM searches WHERE search_forum_num=:a AND status=:b;""")
        this_data_already_recorded = conn.execute(stmt, a=topic_id, b=status).fetchone()

        if this_data_already_recorded:
            logging.info(f"The status {status} for search {topic_id} WAS ALREADY recorded, so It's being ignored.")
            notify_admin(f"The status {status} for search {topic_id} WAS ALREADY recorded, so It's being ignored.")
            conn.close()
            pool.dispose()
            return None

        # update status in change_log table
        stmt = sqlalchemy.text(
            """INSERT INTO change_log (parsed_time, search_forum_num, changed_field, new_value, parameters,
            change_type) values (:a, :b, :c, :d, :e, :f) RETURNING id;"""
        )
        raw_data = conn.execute(
            stmt, a=datetime.datetime.now(), b=topic_id, c='status_change', d=status, e='', f=1
        ).fetchone()

        change_log_id = raw_data[0]
        logging.info(f'{change_log_id=}')

        # update status in searches table
        stmt = sqlalchemy.text("""UPDATE searches SET status=:a WHERE search_forum_num=:b;""")
        conn.execute(stmt, a=status, b=topic_id)

        conn.close()
        pool.dispose()

        logging.info(f'Status is set={status} for topic_id={topic_id}')
        logging.info(f'status {status} for topic {topic_id} has been saved in change_log and searches tables.')

    except Exception as e:
        logging.exception(e)

    return change_log_id


def save_function_into_register(context: str, start_time: datetime.datetime, function_id: int, change_log_id: int):
    """save current function into functions_registry"""

    try:
        event_id = context.event_id

        json_of_params = json.dumps({'ch_id': [change_log_id]})

        pool = sql_connect()
        with pool.connect() as conn:
            sql_text = sqlalchemy.text("""INSERT INTO functions_registry
                                                      (event_id, time_start, cloud_function_name, function_id,
                                                      time_finish, params)
                                                      VALUES (:a, :b, :c, :d, :e, :f)
                                                      /*action='save_manage_topics_function' */;""")
            conn.execute(
                sql_text,
                a=event_id,
                b=start_time,
                c='manage_topics',
                d=function_id,
                e=datetime.datetime.now(),
                f=json_of_params,
            )

            logging.info(f'function {function_id} was saved in functions_registry')

    except Exception as e:
        logging.info(f'function {function_id} was NOT ABLE to be saved in functions_registry')
        logging.exception(e)

    return None


def generate_random_function_id() -> int:
    """generates a random ID for every function – to track all function dependencies (no built-in ID in GCF)"""

    random_id = random.randint(100000000000, 999999999999)

    return random_id


def main(event, context):  # noqa
    """main function"""

    analytics_func_start = datetime.datetime.now()
    function_id = generate_random_function_id()

    try:
        received_dict = process_pubsub_message(event)
        logging.info(f'Script received pub/sub message {received_dict} by event_id {event}')

        if received_dict and 'topic_id' in received_dict:
            topic_id = received_dict['topic_id']

            if 'visibility' in received_dict:
                visibility = received_dict['visibility']
                save_visibility_for_topic(topic_id, visibility)

            if 'status' in received_dict:
                status = received_dict['status']
                change_log_id = save_status_for_topic(topic_id, status)
                save_function_into_register(context, analytics_func_start, function_id, change_log_id)
                if change_log_id:
                    message_for_pubsub = {'triggered_by_func_id': function_id, 'text': "let's compose notifications"}
                    publish_to_pubsub(Topics.topic_for_notification, message_for_pubsub)

    except Exception as e:
        logging.error('Topic management script failed:' + repr(e))
        logging.exception(e)

        # alarm admin
        notify_admin('ERROR in manage_topics: ' + repr(e))

    return 'ok'
