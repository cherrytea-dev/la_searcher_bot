"""Script does several things:
1. checks if the first posts of the searches were changed
2. FIXME - checks active searches' status (Ищем, НЖ, НП, etc.)
3. checks active searches' visibility (accessible for everyone, restricted to a certain group or permanently deleted).
Updates are either saved in PSQL or send via pub/sub to other scripts"""

import datetime
import logging
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from itertools import repeat

from _dependencies.commons import setup_logging
from _dependencies.pubsub import Ctx, pubsub_check_first_posts
from check_first_posts_for_changes._utils.database import get_phpbb_db_client

from ._utils.database import DBClient, get_db_client
from ._utils.forum import ForumUnavailable, get_first_post

setup_logging(__package__)

WORKERS_COUNT = 2
FUNCTION_TIMEOUT_SECONDS = 50
LAST_CHANGE_ID_IN_PHPBB_DB = 'LAST_CHANGE_ID_IN_PHPBB_DB'


@dataclass
class CancelToken:
    timeout_seconds: int
    start_time: datetime.datetime = field(default_factory=datetime.datetime.now)

    def expired(self) -> bool:
        return datetime.datetime.now() > (self.start_time + datetime.timedelta(seconds=self.timeout_seconds))


def update_one_topic_visibility(search_id: int, visibility: str) -> None:
    """record in psql the visibility of one topic: regular, deleted or hidden"""

    # TODO enum for visibility
    db_client = get_db_client()
    db_client.delete_search_health_check(search_id)
    db_client.write_search_health_check(search_id, visibility)
    logging.info(f'Visibility updated for {search_id} and set as {visibility}')


def update_visibility_for_one_hidden_topic() -> None:
    """check if the hidden search was unhidden"""

    hidden_topic_id = get_db_client().get_random_hidden_topic_id()
    if not hidden_topic_id:
        logging.info('No hidden topics to check')
        return

    logging.info(f'we start checking visibility for topic {hidden_topic_id}')
    post_data = get_first_post(hidden_topic_id)
    if post_data:
        update_one_topic_visibility(hidden_topic_id, post_data.topic_visibility)
    else:
        update_one_topic_visibility(hidden_topic_id, 'deleted')


def update_first_posts_in_sql(searches_list: list[int]) -> list[int]:
    """generate a list of topic_ids with updated first posts and record in it PSQL"""

    if not searches_list:
        return []

    list_of_searches_with_updated_f_posts: list[int] = []
    db_client = get_db_client()

    cancel_token = CancelToken(FUNCTION_TIMEOUT_SECONDS)

    with ThreadPoolExecutor(max_workers=WORKERS_COUNT) as executor:
        results = executor.map(
            _update_one_topic_hash,
            repeat(db_client, len(searches_list)),
            repeat(cancel_token, len(searches_list)),
            searches_list,
        )

        for i, topic_updated in enumerate(results):
            if cancel_token.expired():
                executor.shutdown(wait=False, cancel_futures=True)
                break

            if topic_updated:
                topic_id = searches_list[i]
                list_of_searches_with_updated_f_posts.append(topic_id)

    logging.info(
        (
            f'first posts checked for {len(searches_list)} searches; '
            f'updated hashes of {len(list_of_searches_with_updated_f_posts)} searches'
        )
    )

    return list_of_searches_with_updated_f_posts


def _update_one_topic_hash(db_client: DBClient, cancel_token: CancelToken, topic_id: int) -> bool:
    if cancel_token.expired():
        return False
    post_data = get_first_post(topic_id)

    if not post_data:
        update_one_topic_visibility(topic_id, 'deleted')
        return False

    last_hash = db_client.get_search_first_post_actual_hash(topic_id)

    if not last_hash:
        db_client.create_search_first_post(topic_id, post_data.hash_num, post_data.prettified_content)
        return False

    # if record for this search – outdated
    if post_data.hash_num != last_hash and post_data.topic_visibility == 'regular':
        db_client.mark_search_first_post_as_not_actual(topic_id)
        db_client.create_search_first_post(topic_id, post_data.hash_num, post_data.prettified_content)
        return True
        # if record for this search – does not exist – add a new record

    return False


def update_first_posts_and_statuses() -> None:
    """update first posts for topics"""

    active_searches = get_db_client().get_active_searches_ids()
    logging.info(f'Found {len(active_searches)} active searches')
    last_id = get_db_client().get_key_value_item(LAST_CHANGE_ID_IN_PHPBB_DB) or 0

    changed_topic_ids = get_phpbb_db_client().get_changed_post_ids_from_last_id(last_id)
    fetched_records_count = len(changed_topic_ids)
    unique_changed_topic_ids = set(changed_topic_ids)
    logging.info(f'Changed topics in forum: {unique_changed_topic_ids}')

    topic_ids_to_check = [item for item in active_searches if item in unique_changed_topic_ids]
    logging.info(f'First posts to check update: {topic_ids_to_check}')

    try:
        topics_with_updated_first_posts = update_first_posts_in_sql(topic_ids_to_check)
    except ForumUnavailable:
        logging.warning('Forum unavailable')
        return

    # Split topics_into_chunks of 10 items and send each chunk via pub/sub
    # to avoid too large lists of searches to process
    chunk_size = 10
    for i in range(0, len(topics_with_updated_first_posts), chunk_size):
        chunk = topics_with_updated_first_posts[i : i + chunk_size]
        pubsub_check_first_posts(chunk)

    get_db_client().set_key_value_item(LAST_CHANGE_ID_IN_PHPBB_DB, last_id + fetched_records_count)


def main(event: dict, context: Ctx) -> None:
    # BLOCK 1. for checking if the first posts were changed
    update_first_posts_and_statuses()

    # BLOCK 2. small bonus: check one of topics, which has visibility='hidden' to check if it was not unhidden later.
    # It is done in this script only because there's no better place. Ant these are circa 40 hidden topics at all.
    try:
        update_visibility_for_one_hidden_topic()
    except ForumUnavailable:
        pass  # nothing to do, just wait
