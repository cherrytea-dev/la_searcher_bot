import datetime
import logging

import sqlalchemy
from google.cloud.functions.context import Context

from _dependencies.commons import setup_google_logging, sqlalchemy_get_pool
from _dependencies.misc import generate_random_function_id, save_function_into_register
from _dependencies.pubsub import TopicManagementData, notify_admin, process_pubsub_message, pubsub_compose_notifications
from _dependencies.topic_management import save_status_for_topic, save_visibility_for_topic

setup_google_logging()


def sql_connect() -> sqlalchemy.engine.Engine:
    return sqlalchemy_get_pool(5, 5)

    # FIXME – to be added: INSERT INTO change_log
    # it requires also right execution inside compose notifications


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

        pool = sql_connect()
        with pool.connect() as conn:
            if received_dict.visibility:
                save_visibility_for_topic(conn, received_dict.topic_id, received_dict.visibility)

            if received_dict.status:
                save_status_for_topic(conn, received_dict.topic_id, received_dict.status)

    except Exception as e:
        logging.exception('Topic management script failed')
        # alarm admin
        notify_admin('ERROR in manage_topics: ' + repr(e))

    return 'ok'
