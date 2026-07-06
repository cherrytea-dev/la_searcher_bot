import datetime
import logging

import sqlalchemy

from _dependencies.common.misc import generate_random_function_id
from _dependencies.common.pubsub import notify_admin, pubsub_compose_notifications


def save_status_for_topic(conn: sqlalchemy.engine.Connection, topic_id: int, status: str) -> int | None:
    """save in SQL if topic status was updated: active search, search finished etc."""

    # check if this topic is already marked with the new status:
    stmt = sqlalchemy.text("""
        SELECT id FROM searches WHERE search_forum_num=:topic_id AND status=:status;
                        """)
    this_data_already_recorded = conn.execute(stmt, dict(topic_id=topic_id, status=status)).fetchone()

    if this_data_already_recorded:
        logging.info(f"The status {status} for search {topic_id} WAS ALREADY recorded, so It's being ignored.")
        notify_admin(f"The status {status} for search {topic_id} WAS ALREADY recorded, so It's being ignored.")
        return None

    # update status in change_log table
    stmt = sqlalchemy.text("""
            INSERT INTO change_log (parsed_time, search_forum_num, changed_field, new_value, parameters,
            change_type) values (:ts, :topic_id, :changed_field, :new_value, :params, :change_type) RETURNING id;
                            """)
    raw_data = conn.execute(stmt, dict(ts=datetime.datetime.now(), topic_id=topic_id, changed_field='status_change', new_value=status, params='', change_type=1))

    change_log_id = raw_data.scalar()
    logging.info(f'{change_log_id=}')

    # update status in searches table
    stmt = sqlalchemy.text("""UPDATE searches SET status=:status WHERE search_forum_num=:topic_id;""")
    conn.execute(stmt, dict(status=status, topic_id=topic_id))

    logging.info(f'Status is set={status} for topic_id={topic_id}')
    logging.info(f'status {status} for topic {topic_id} has been saved in change_log and searches tables.')

    function_id = generate_random_function_id()
    pubsub_compose_notifications(function_id, "let's compose notifications")
    return change_log_id


def save_visibility_for_topic(conn: sqlalchemy.engine.Connection, topic_id: int, visibility: str) -> None:
    """save in SQL if topic was deleted, hidden or unhidden"""

    notify_admin(f'WE FAKED VISIBILITY UPDATE: topic_id={topic_id}, visibility={visibility}')
    return
    # TODO for what this function is?

    # MEMO: visibility can be only:
    # 'deleted' – topic is permanently deleted
    # 'hidden' – topic is hidden from public access, can become visible in the future
    # 'ok' – regular topics with public visibility

    # clear the prev visibility status
    stmt = sqlalchemy.text("""DELETE FROM search_health_check WHERE search_forum_num=:topic_id;""")
    conn.execute(stmt, dict(topic_id=topic_id))

    # set the new visibility status
    stmt = sqlalchemy.text("""INSERT INTO search_health_check (search_forum_num, timestamp, status)
                                    VALUES (:topic_id, :ts, :visibility);""")
    conn.execute(stmt, dict(topic_id=topic_id, ts=datetime.datetime.now(), visibility=visibility))

    logging.info(f'Visibility is set={visibility} for topic_id={topic_id}')
