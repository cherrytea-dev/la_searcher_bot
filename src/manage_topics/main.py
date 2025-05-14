import datetime
import logging

import sqlalchemy
from google.cloud.functions.context import Context

from _dependencies.commons import setup_google_logging, sqlalchemy_get_pool
from _dependencies.misc import generate_random_function_id, save_function_into_register
from _dependencies.pubsub import TopicManagementData, notify_admin, process_pubsub_message, pubsub_compose_notifications

setup_google_logging()


def sql_connect() -> sqlalchemy.engine.Engine:
    return sqlalchemy_get_pool(5, 5)


def save_visibility_for_topic(topic_id: int, visibility: str) -> None:
    """save in SQL if topic was deleted, hidden or unhidden"""

    pool = sql_connect()
    with pool.connect() as conn:
        notify_admin(f'WE FAKED VISIBILITY UPDATE: topic_id={topic_id}, visibility={visibility}')
        return
        # TODO for what this function is?

        # MEMO: visibility can be only:
        # 'deleted' – topic is permanently deleted
        # 'hidden' – topic is hidden from public access, can become visible in the future
        # 'ok' – regular topics with public visibility

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


def save_status_for_topic(topic_id: int, status: str) -> int | None:
    """save in SQL if topic status was updated: active search, search finished etc."""

    change_log_id = None
    pool = sql_connect()
    with pool.connect() as conn:
        # check if this topic is already marked with the new status:
        stmt = sqlalchemy.text("""
            SELECT id FROM searches WHERE search_forum_num=:a AND status=:b;
                            """)
        this_data_already_recorded = conn.execute(stmt, a=topic_id, b=status).fetchone()

        if this_data_already_recorded:
            logging.info(f"The status {status} for search {topic_id} WAS ALREADY recorded, so It's being ignored.")
            notify_admin(f"The status {status} for search {topic_id} WAS ALREADY recorded, so It's being ignored.")
            return None

        # update status in change_log table
        stmt = sqlalchemy.text("""
                INSERT INTO change_log (parsed_time, search_forum_num, changed_field, new_value, parameters,
                change_type) values (:a, :b, :c, :d, :e, :f) RETURNING id;
                                """)
        raw_data = conn.execute(
            stmt, a=datetime.datetime.now(), b=topic_id, c='status_change', d=status, e='', f=1
        ).fetchone()

        change_log_id = raw_data[0]
        logging.info(f'{change_log_id=}')

        # update status in searches table
        stmt = sqlalchemy.text("""UPDATE searches SET status=:a WHERE search_forum_num=:b;""")
        conn.execute(stmt, a=status, b=topic_id)

    logging.info(f'Status is set={status} for topic_id={topic_id}')
    logging.info(f'status {status} for topic {topic_id} has been saved in change_log and searches tables.')

    return change_log_id


def main(event: dict[str, bytes], context: Context) -> str:  # noqa
    """main function"""

    analytics_func_start = datetime.datetime.now()
    function_id = generate_random_function_id()

    try:
        received_dict_raw = process_pubsub_message(event)
        logging.info(f'Script received pub/sub message {received_dict_raw} by event_id {event}')
        received_dict = TopicManagementData.model_validate(received_dict_raw)

        if not received_dict.topic_id:
            return 'no topic id'

        if received_dict.visibility:
            save_visibility_for_topic(received_dict.topic_id, received_dict.visibility)

        if received_dict.status:
            change_log_id = save_status_for_topic(received_dict.topic_id, received_dict.status)

            if change_log_id:
                pool = sql_connect()
                with pool.connect() as conn:
                    save_function_into_register(
                        conn, context.event_id, analytics_func_start, function_id, [change_log_id], 'manage_topics'
                    )

                    pubsub_compose_notifications(function_id, "let's compose notifications")

    except Exception as e:
        logging.exception('Topic management script failed')
        # alarm admin
        notify_admin('ERROR in manage_topics: ' + repr(e))

    return 'ok'
