import json
import logging
from enum import Enum
from typing import Any

from pydantic import BaseModel, RootModel

from _dependencies.common.commons import get_app_config
from _dependencies.common.queue_pg import enqueue as queue_pg_enqueue
from _dependencies.common.yandex_tools import (
    Ctx as YandexCtx,
)
from _dependencies.common.yandex_tools import (
    make_api_call_cloud,
    process_pubsub_message_cloud,
    send_topic_cloud,
)

Ctx = YandexCtx


class Topics(Enum):
    topic_notify_admin = 'topic_notify_admin'  # send_debug_to_admin
    topic_for_first_post_processing = 'topic_for_first_post_processing'  # identify_updates_of_first_posts
    topic_for_notification = 'topic_for_notification'  # compose_notifications
    topic_to_run_parsing_script = 'topic_to_run_parsing_script'  # identify_updates_of_topics
    parse_user_profile_from_forum = 'parse_user_profile_from_forum'  # connect_to_forum
    topic_to_send_notifications = 'topic_to_send_notifications'  # send_notifications
    topic_to_archive_notifs = 'topic_to_archive_notifs'  # archive_notifications


class MessageForIdentifyUpdatesOfTopics(RootModel):
    """Message contract for topic_to_run_parsing_script.
    Published by check_first_posts_for_changes, consumed by identify_updates_of_topics.
    """

    root: list[int]  # ids of topic (search)


class MessageForParseUserProfile(RootModel):
    """Message contract for parse_user_profile_from_forum.
    Published by communicate/vk_bot scripts, consumed by connect_to_forum.
    """

    root: tuple[int, str]  # (user_id: telegram user id, forum_username: str)


class MessageForParseFolders(RootModel):
    """Message contract for topic_to_run_parsing_script (legacy path).
    Published by check_topics_by_upd_time / identify_updates_of_first_posts (legacy),
    consumed by identify_updates_of_topics (legacy).
    Each item is [folder_num, ...extra_data].
    """

    root: list[list]  # [[folder_num, ...], ...]


class MessageForComposeNotifications(BaseModel):
    """Message contract for topic_for_notification.
    Published by various scripts, consumed by compose_notifications.
    """

    triggered_by_func_id: int
    text: str


class MessageForCheckFirstPosts(RootModel):
    """Message contract for topic_for_first_post_processing.
    Published by check_first_posts_for_changes, consumed by identify_updates_of_first_posts.
    """

    root: list[int]  # search/forum topic ids


class MessageForSendNotifications(BaseModel):
    """Message contract for topic_to_send_notifications.
    Published by compose_notifications, consumed by send_notifications.
    """

    triggered_by_func_id: int
    text: str


def _send_to_queue(topic_name: str, message: str | dict | list | BaseModel) -> None:
    """Publish to the configured backend.

    ``pg`` (default in the single container) writes the message into the ``pubsub_messages``
    table; ``ymq`` keeps the legacy Yandex Message Queue for as long as both run side by side.
    """
    if get_app_config().queue_backend == 'ymq':
        send_topic_cloud(topic_name, message)
        return

    try:
        queue_pg_enqueue(topic_name, message)
    except Exception:
        # Mirrors the old behaviour: a broken publish must not take the handler down.
        logging.exception(f'Not able to send pub/sub message to topic {topic_name}')


def publish_to_pubsub(topic_name: Topics | str, message: str | dict | list | BaseModel) -> None:
    """publish a new message to pub/sub"""
    topic_name_str = topic_name.value if isinstance(topic_name, Topics) else topic_name
    _send_to_queue(topic_name_str, message)


def pubsub_parse_user_profile(user_id: int, got_message: str) -> None:
    message = MessageForParseUserProfile(root=(user_id, got_message))
    publish_to_pubsub(Topics.parse_user_profile_from_forum, message)


def pubsub_parse_folders(folders_list: list) -> None:
    # Legacy: publishes list of [folder_num, ...extra_data] entries
    message = MessageForParseFolders(root=folders_list)
    publish_to_pubsub(Topics.topic_to_run_parsing_script, message)


def pubsub_parse_searches(topic_ids: MessageForIdentifyUpdatesOfTopics) -> None:
    publish_to_pubsub(Topics.topic_to_run_parsing_script, topic_ids)


def pubsub_compose_notifications(function_id: int, text: str) -> None:
    message = MessageForComposeNotifications(triggered_by_func_id=function_id, text=text)
    publish_to_pubsub(Topics.topic_for_notification, message)


def pubsub_check_first_posts(topics_with_updated_first_posts: list[int]) -> None:
    message = MessageForCheckFirstPosts(root=topics_with_updated_first_posts)
    publish_to_pubsub(Topics.topic_for_first_post_processing, message)


def pubsub_send_notifications(function_id: int, text: str) -> None:
    message = MessageForSendNotifications(triggered_by_func_id=function_id, text=text)
    publish_to_pubsub(Topics.topic_to_send_notifications, message)


def pubsub_archive_notifications() -> None:
    publish_to_pubsub(Topics.topic_to_archive_notifs, 'go')


def notify_admin(message: str) -> None:
    """send the pub/sub message to Debug to Admin"""

    publish_to_pubsub(Topics.topic_notify_admin, message)


def recognize_title_via_api(title: str, status_only: bool) -> dict:
    """Recognize a title — in-process in the single container, over HTTP in the cloud.

    The function used to be a separate cloud function called through the API gateway; inside
    one container that hop is pointless (and it was the 1 GB-memory function). The flag
    ``TITLE_RECOGNIZE_LOCAL`` keeps the old path available.
    """
    data = {'title': title}
    if status_only:
        data['reco_type'] = 'status_only'

    logging.info(f'request to title recognition: {data}')
    if get_app_config().title_recognize_local:
        return _recognize_title_locally(data)

    return make_api_call_cloud('title_recognize', data)


def _recognize_title_locally(data: dict) -> dict:
    """Call ``title_recognize`` in this process through its regular HTTP-shaped entry point."""
    # Imported lazily: pymorphy3 and its dictionaries must stay out of the import graph of
    # every other function (they are only needed once recognition is actually requested).
    from title_recognize.main import main as title_recognize_main

    response: dict[str, Any] = title_recognize_main({'httpMethod': 'POST', 'body': json.dumps(data), 'headers': {}})

    status_code = int(response.get('statusCode') or 200)
    body = response.get('body') or '{}'
    if status_code >= 400:
        raise RuntimeError(f'title_recognize failed with {status_code}: {body}')

    return dict(json.loads(body))


def process_pubsub_message(event: dict) -> str:
    """convert incoming pub/sub message into regular data"""
    return process_pubsub_message_cloud(event)
