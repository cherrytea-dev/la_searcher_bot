"""Script takes as input the list of recently-updated forum folders. Then it parses first 20 searches (aka topics)
and saves into PSQL if there are any updates"""

import logging

from _dependencies.commons import setup_logging
from _dependencies.misc import generate_random_function_id
from _dependencies.pubsub import Ctx, notify_admin, process_pubsub_message, pubsub_compose_notifications

from ._utils.database import get_db_client
from ._utils.folder_updater import FolderUpdater
from ._utils.forum import ForumClient

setup_logging(__package__)


def main(event: dict[str, bytes], context: Ctx) -> None:  # noqa
    """main function triggered by pub/sub"""

    function_id = generate_random_function_id()
    folders_list = []

    list_from_pubsub = process_pubsub_message(event)
    logging.info(f'received message from pub/sub: {list_from_pubsub}')

    db_client = get_db_client()
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
        pubsub_compose_notifications(function_id, "let's compose notifications")
