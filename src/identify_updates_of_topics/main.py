"""Script takes as input the list of recently-updated forum folders. Then it parses first 20 searches (aka topics)
and saves into PSQL if there are any updates"""

import ast
import logging
from datetime import datetime

import sqlalchemy
from google.cloud.functions.context import Context

from _dependencies.commons import (
    Topics,
    publish_to_pubsub,
    setup_google_logging,
    sqlalchemy_get_pool,
)
from _dependencies.misc import generate_random_function_id, notify_admin, process_pubsub_message_v3

from ._utils.database import DBClient
from ._utils.folder_updater import FolderUpdater
from ._utils.forum import ForumClient

setup_google_logging()


def sql_connect() -> sqlalchemy.engine.Engine:
    return sqlalchemy_get_pool(5, 120)


def main(event: dict[str, bytes], context: Context) -> None:  # noqa
    """main function triggered by pub/sub"""

    function_id = generate_random_function_id()
    folders_list = []

    analytics_func_start = datetime.now()

    message_from_pubsub = process_pubsub_message_v3(event)
    list_from_pubsub = ast.literal_eval(message_from_pubsub) if message_from_pubsub else None
    logging.info(f'received message from pub/sub: {message_from_pubsub}')

    db_conn_pool = sql_connect()
    db_client = DBClient(db_conn_pool)
    forum_client = ForumClient()
    list_of_ignored_folders = db_client.get_the_list_of_ignored_folders()

    if list_from_pubsub:
        folders_list = [int(line[0]) for line in list_from_pubsub if int(line[0]) not in list_of_ignored_folders]
        logging.info(f'list of folders, received from pubsub but filtered by ignored folders: {folders_list}')

    if not folders_list:
        notify_admin(f'NB! [Ide_topics] resulted in empty folders list. Initial, but filtered {list_from_pubsub}')
        folders_list = [276, 41]

    list_of_folders_with_updates = []
    change_log_ids = []

    for folder in folders_list:
        logging.info(f'start checking if folder {folder} has any updates')

        update_trigger, one_folder_change_log_ids = FolderUpdater(db_client, forum_client, folder).run()

        if update_trigger:
            list_of_folders_with_updates.append(folder)
            change_log_ids += one_folder_change_log_ids

    logging.info(f"Here's a list of folders with updates: {list_of_folders_with_updates}")
    logging.info(f"Here's a list of change_log ids created: {change_log_ids}")

    if list_of_folders_with_updates:
        db_client.save_function_into_register(context, analytics_func_start, function_id, change_log_ids)

        message_for_pubsub = {'triggered_by_func_id': function_id, 'text': "let's compose notifications"}
        publish_to_pubsub(Topics.topic_for_notification, message_for_pubsub)

    db_conn_pool.dispose()
