"""Script takes as input the list of recently-updated forum folders. Then it parses first 20 searches (aka topics)
and saves into PSQL if there are any updates"""

import logging

from _dependencies.commons import get_app_config, setup_logging
from _dependencies.misc import generate_random_function_id
from _dependencies.pubsub import (
    Ctx,
    MessageForIdentifyUpdatesOfTopics,
    process_pubsub_message,
    pubsub_compose_notifications,
)

from ._utils.database import get_db_client
from ._utils.forum import ForumClient
from ._utils.topic_updater import SearchUpdater

setup_logging(__package__)


def main(event: dict[str, bytes], context: Ctx) -> None:  # noqa
    """main function triggered by pub/sub"""

    if get_app_config().forum_legacy_data_source:
        from ._legacy.main import main as legacy_main

        return legacy_main(event, context)

    function_id = generate_random_function_id()

    list_from_pubsub = process_pubsub_message(event)
    changed_topics = MessageForIdentifyUpdatesOfTopics.model_validate(list_from_pubsub)

    change_log_ids: list[int] = []

    search_updater = SearchUpdater(get_db_client(), ForumClient())
    for topic_id in changed_topics.root:
        logging.info(f'start checking if search {topic_id} has any updates')

        one_folder_change_log_ids = search_updater.update_search(topic_id)
        change_log_ids.extend(one_folder_change_log_ids)

    logging.info(f"Here's a list of change_log ids created: {change_log_ids}")

    if change_log_ids:
        pubsub_compose_notifications(function_id, "let's compose notifications")
