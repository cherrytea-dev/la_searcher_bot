"""Script takes as input the list of recently-updated forum folders. Then it parses first 20 searches (aka topics)
and saves into PSQL if there are any updates"""

import logging

from _dependencies.commons import setup_logging
from _dependencies.misc import generate_random_function_id
from _dependencies.pubsub import (
    Ctx,
    MessageForIdentifyUpdatesOfTopics,
    process_pubsub_message,
    pubsub_compose_notifications,
)

from ._utils.database import get_db_client
from ._utils.folder_updater import SearchUpdater
from ._utils.forum import ForumClient

setup_logging(__package__)


def main(event: dict[str, bytes], context: Ctx) -> None:  # noqa
    """main function triggered by pub/sub"""

    function_id = generate_random_function_id()

    list_from_pubsub = process_pubsub_message(event)
    logging.info(f'received message from pub/sub: {list_from_pubsub}')
    changed_searches = MessageForIdentifyUpdatesOfTopics.model_validate(list_from_pubsub)

    change_log_ids: list[int] = []

    search_updater = SearchUpdater(get_db_client(), ForumClient())
    for search_id in changed_searches.root:
        logging.info(f'start checking if search {search_id} has any updates')

        one_folder_change_log_ids = search_updater.update_search(search_id)
        change_log_ids.extend(one_folder_change_log_ids)

    logging.info(f"Here's a list of change_log ids created: {change_log_ids}")

    if change_log_ids:
        pubsub_compose_notifications(function_id, "let's compose notifications")
