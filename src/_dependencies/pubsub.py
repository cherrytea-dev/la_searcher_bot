import logging
from enum import Enum

from pydantic import BaseModel

from _dependencies.yandex_tools import Ctx, make_api_call_cloud, process_pubsub_message_cloud, send_topic_cloud


class Topics(Enum):
    topic_notify_admin = 'topic_notify_admin'  # send_debug_to_admin
    topic_for_first_post_processing = 'topic_for_first_post_processing'  # identify_updates_of_first_posts
    topic_for_notification = 'topic_for_notification'  # compose_notifications
    topic_to_run_parsing_script = 'topic_to_run_parsing_script'  # identify_updates_of_topics
    parse_user_profile_from_forum = 'parse_user_profile_from_forum'  # connect_to_forum
    topic_to_send_notifications = 'topic_to_send_notifications'  # send_notifications
    topic_to_archive_notifs = 'topic_to_archive_notifs'  # archive_notifications


def publish_to_pubsub(topic_name: Topics, message: str | dict | list | BaseModel) -> None:
    """publish a new message to pub/sub"""
    topic_name_str = topic_name.value if isinstance(topic_name, Topics) else topic_name
    send_topic_cloud(topic_name_str, message)


def pubsub_parse_user_profile(user_id: int, got_message: str) -> None:
    message_for_pubsub = [user_id, got_message]
    publish_to_pubsub(Topics.parse_user_profile_from_forum, message_for_pubsub)


def pubsub_parse_folders(folders_list: list) -> None:
    publish_to_pubsub(Topics.topic_to_run_parsing_script, folders_list)


def pubsub_compose_notifications(function_id: int, text: str) -> None:
    # TODO "triggered_by_func_id" - maybe we don't need it already from other functions
    message_for_pubsub = {'triggered_by_func_id': function_id, 'text': text}
    publish_to_pubsub(Topics.topic_for_notification, message_for_pubsub)


def pubsub_check_first_posts(topics_with_updated_first_posts: list[int]) -> None:
    publish_to_pubsub(Topics.topic_for_first_post_processing, topics_with_updated_first_posts)


def pubsub_send_notifications(function_id: int, text: str) -> None:
    message_for_pubsub = {'triggered_by_func_id': function_id, 'text': text}
    publish_to_pubsub(Topics.topic_to_send_notifications, message_for_pubsub)


def pubsub_archive_notifications() -> None:
    publish_to_pubsub(Topics.topic_to_archive_notifs, 'go')


def notify_admin(message: str) -> None:
    """send the pub/sub message to Debug to Admin"""

    publish_to_pubsub(Topics.topic_notify_admin, message)


def recognize_title_via_api(title: str, status_only: bool) -> dict:
    """makes an API call to another Google Cloud Function"""
    data = {'title': title}
    if status_only:
        data['reco_type'] = 'status_only'

    logging.info(f'request to title recognition: {data}')
    return make_api_call_cloud('title_recognize', data)


def process_pubsub_message(event: dict) -> str:
    """convert incoming pub/sub message into regular data"""
    return process_pubsub_message_cloud(event)
