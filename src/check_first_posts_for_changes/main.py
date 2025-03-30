"""Script does several things:
1. checks if the first posts of the searches were changed
2. FIXME - checks active searches' status (Ищем, НЖ, НП, etc.)
3. checks active searches' visibility (accessible for everyone, restricted to a certain group or permanently deleted).
Updates are either saved in PSQL or send via pub/sub to other scripts"""

import datetime
import logging
from functools import lru_cache

from google.cloud.functions.context import Context

from _dependencies.commons import Topics, publish_to_pubsub, setup_google_logging, sqlalchemy_get_pool

from ._utils.commons import PercentGroup, Search
from ._utils.database import DBClient
from ._utils.forum import (
    define_topic_visibility_by_content,
    get_first_post,
    get_search_raw_content,
)

setup_google_logging()


@lru_cache
def get_db_client() -> DBClient:
    pool = sqlalchemy_get_pool(5, 120)
    return DBClient(db=pool)


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
    post_content = get_search_raw_content(hidden_topic_id)
    visibility = define_topic_visibility_by_content(post_content)
    if visibility:
        update_one_topic_visibility(hidden_topic_id, visibility)


def _generate_list_of_topic_groups() -> list[PercentGroup]:
    """generate N search groups, groups needed to define which part of all searches will be checked now"""

    percent_step = 5
    list_of_groups: list[PercentGroup] = []
    current_percent = 0

    while current_percent < 100:
        n = int(current_percent / percent_step)
        new_group = PercentGroup(
            n=n,
            start_percent=current_percent,
            finish_percent=min(100, current_percent + percent_step - 1),
            frequency=2**n,
            first_delay=2 ** (n - 1) - 1 if n != 0 else 0,
        )
        list_of_groups.append(new_group)
        current_percent += percent_step

    return list_of_groups


def _define_which_topic_groups_to_be_checked() -> list[PercentGroup]:
    """gives an output of 2 groups that should be checked for this time"""
    list_of_groups = _generate_list_of_topic_groups()

    start_time = datetime.datetime(2023, 1, 1, 0, 0, 0)
    curr_minute = int(((datetime.datetime.now() - start_time).total_seconds() / 60) // 1)

    curr_minute_list: list[PercentGroup] = []
    for group_2 in list_of_groups:
        if not ((curr_minute - group_2.first_delay) % group_2.frequency):
            curr_minute_list.append(group_2)
            logging.debug(f'Group to be checked {group_2}')

    return curr_minute_list


def get_topics_to_check() -> list[Search]:
    """add searches to the chosen groups"""
    topics_to_check: list[Search] = []

    # TODO maybe there is better method of randomizing?
    searches = get_db_client().get_list_of_topics()
    list_of_groups = _define_which_topic_groups_to_be_checked()

    num_of_searches = len(searches)

    for group_2 in list_of_groups:
        group_2.start_num = int((group_2.start_percent * num_of_searches / 100) // 1)
        group_2.finish_num = min(int(((group_2.finish_percent + 1) * num_of_searches / 100) // 1 - 1), len(searches))

    for j, search in enumerate(searches):
        for group_2 in list_of_groups:
            if group_2.start_num <= j <= group_2.finish_num:
                topics_to_check.append(search)

    return topics_to_check


def update_first_posts_in_sql(searches_list: list[Search]) -> list[int]:
    """generate a list of topic_ids with updated first posts and record in it PSQL"""

    num_of_searches_counter = 0
    list_of_searches_with_updated_f_posts: list[int] = []
    db_client = get_db_client()
    try:
        for line in searches_list:
            num_of_searches_counter += 1
            topic_id = line.topic_id
            hash_updated = _update_one_topic_hash(db_client, topic_id)
            if hash_updated:
                list_of_searches_with_updated_f_posts.append(topic_id)

    except Exception as e:
        logging.exception('exception in update_first_posts_and_statuses')

    logging.info(f'first posts checked for {num_of_searches_counter} searches')

    return list_of_searches_with_updated_f_posts


def _update_one_topic_hash(db_client: DBClient, topic_id: int) -> bool:
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

    topics_to_check = get_topics_to_check()

    if not topics_to_check:
        return

    topics_with_updated_first_posts = update_first_posts_in_sql(topics_to_check)

    if not topics_with_updated_first_posts:
        return

    publish_to_pubsub(Topics.topic_for_first_post_processing, topics_with_updated_first_posts)


def main(event: dict, context: Context) -> None:
    # to avoid function invocation except when it was initiated by scheduler (and pub/sub message was not doubled)
    if datetime.datetime.now().second > 5:
        return

    # BLOCK 1. for checking if the first posts were changed
    update_first_posts_and_statuses()

    # BLOCK 2. small bonus: check one of topics, which has visibility='hidden' to check if it was not unhidden later.
    # It is done in this script only because there's no better place. Ant these are circa 40 hidden topics at all.
    update_visibility_for_one_hidden_topic()

    # if bad_gateway_counter > 3:
    #     notify_admin(f'[che_posts]: Bad Gateway {bad_gateway_counter} times')
