import base64
import json
import logging
from datetime import datetime
from enum import Enum
from functools import lru_cache
from typing import Any

import google.auth.transport.requests
import google.oauth2.id_token
import requests
from google.cloud import pubsub_v1
from pydantic import BaseModel, Field
from retry import retry

from _dependencies.commons import get_project_id


class Topics(Enum):
    topic_notify_admin = 'topic_notify_admin'
    topic_for_topic_management = 'topic_for_topic_management'
    topic_for_first_post_processing = 'topic_for_first_post_processing'
    topic_for_notification = 'topic_for_notification'
    topic_to_run_parsing_script = 'topic_to_run_parsing_script'
    topic_for_user_management = 'topic_for_user_management'
    parse_user_profile_from_forum = 'parse_user_profile_from_forum'
    topic_to_send_notifications = 'topic_to_send_notifications'
    topic_to_archive_notifs = 'topic_to_archive_notifs'
    topic_to_archive_to_bigquery = 'topic_to_archive_to_bigquery'


class TopicManagementData(BaseModel):
    topic_id: int
    status: str | None = None
    visibility: str | None = None


class ManageUsersDataUserInfo(BaseModel):
    user: int  # id
    username: str | None = None


class ManageUserAction(str, Enum):
    block_user = 'block_user'
    unblock_user = 'unblock_user'
    new = 'new'
    delete_user = 'delete_user'
    update_onboarding = 'update_onboarding'

    def action_to_write(self) -> str:
        return {
            self.block_user: 'blocked',
            self.unblock_user: 'unblocked',
            self.new: 'new',
            self.delete_user: 'deleted',
        }[self]


class ManageUsersData(BaseModel):
    action: ManageUserAction
    time: datetime = Field(default_factory=datetime.now)
    info: ManageUsersDataUserInfo
    step: str = 'unrecognized'


@lru_cache
def _get_publisher() -> pubsub_v1.PublisherClient:
    return pubsub_v1.PublisherClient()


def _send_topic(topic_name: Topics, topic_path: str, message_bytes: bytes) -> None:
    publish_future = _get_publisher().publish(topic_path, data=message_bytes)
    publish_future.result()  # Verify the publishing succeeded


class PubSubMessage(BaseModel):
    message: Any


class PubSubData(BaseModel):
    data: PubSubMessage


def publish_to_pubsub(topic_name: Topics, message: str | dict | list | BaseModel) -> None:
    """publish a new message to pub/sub"""

    topic_name_str = topic_name.value if isinstance(topic_name, Topics) else topic_name
    #  TODO find out where topic_name.value comes from as str

    topic_path = _get_publisher().topic_path(get_project_id(), topic_name_str)
    data = PubSubData(data=PubSubMessage(message=message))
    message_bytes = data.model_dump_json().encode('utf-8')

    try:
        _send_topic(topic_name, topic_path, message_bytes)
        logging.info(f'Sent pub/sub message: {str(message)}')

    except Exception:
        logging.exception('Not able to send pub/sub message')


def pubsub_parse_user_profile(user_id: int, got_message: str) -> None:
    message_for_pubsub = [user_id, got_message]
    publish_to_pubsub(Topics.parse_user_profile_from_forum, message_for_pubsub)


def pubsub_parse_folders(folders_list: list) -> None:
    publish_to_pubsub(Topics.topic_to_run_parsing_script, str(folders_list))


def pubsub_compose_notifications(function_id: int, text: str) -> None:
    # TODO "triggered_by_func_id" - maybe we don't need it already from other functions
    message_for_pubsub = {'triggered_by_func_id': function_id, 'text': text}
    publish_to_pubsub(Topics.topic_for_notification, message_for_pubsub)


def pubsub_check_first_posts(topics_with_updated_first_posts: list[int]) -> None:
    publish_to_pubsub(Topics.topic_for_first_post_processing, topics_with_updated_first_posts)


def pubsub_send_notifications(function_id: int, text: str) -> None:
    message_for_pubsub = {'triggered_by_func_id': function_id, 'text': text}
    publish_to_pubsub(Topics.topic_to_send_notifications, message_for_pubsub)


def pubsub_topic_management(topic_id: int, status: str | None = None, visibility: str | None = None) -> None:
    # TODO change status right here

    pubsub_message = TopicManagementData(topic_id=topic_id, status=status, visibility=visibility)
    publish_to_pubsub(Topics.topic_for_topic_management, pubsub_message.model_dump())


def pubsub_user_management(
    user_id: int,
    action: ManageUserAction,
    username: str | None = None,
    time: datetime | None = None,
    step: str | None = None,
) -> None:
    logging.info(f'Identified user id {user_id} to do {action}')

    message_for_pubsub = ManageUsersData(
        action=action,
        info=ManageUsersDataUserInfo(user=user_id, username=username),
        step=step or 'unrecognized',
        time=time or datetime.now(),
    )

    publish_to_pubsub(Topics.topic_for_user_management, message_for_pubsub.model_dump())


def pubsub_archive_notifications() -> None:
    publish_to_pubsub(Topics.topic_to_archive_notifs, 'go')


def pubsub_archive_to_bigquery() -> None:
    publish_to_pubsub(Topics.topic_to_archive_to_bigquery, 'go')


def notify_admin(message: str) -> None:
    """send the pub/sub message to Debug to Admin"""

    publish_to_pubsub(Topics.topic_notify_admin, message)


def recognize_title_via_api(title: str, status_only: bool) -> dict:
    """makes an API call to another Google Cloud Function"""
    data = {'title': title}
    if status_only:
        data['reco_type'] = 'status_only'

    # function we're turing to "title_recognize"
    return _make_api_call('title_recognize', data)


@retry(Exception, tries=3, delay=3)
def _make_api_call(function: str, data: dict) -> dict:
    endpoint = f'https://europe-west3-lizaalert-bot-01.cloudfunctions.net/{function}'

    # required magic for Google Cloud Functions Gen2 to invoke each other
    audience = endpoint
    auth_req = google.auth.transport.requests.Request()
    id_token = google.oauth2.id_token.fetch_id_token(auth_req, audience)
    headers = {'Authorization': f'Bearer {id_token}', 'Content-Type': 'application/json'}

    response = requests.post(endpoint, json=data, headers=headers, timeout=30)
    response.raise_for_status()
    return response.json()


def process_pubsub_message(event: dict) -> str:
    """convert incoming pub/sub message into regular data"""

    # receiving message text from pub/sub
    raw_message = base64.b64decode(event['data']).decode('utf-8')
    json_data = json.loads(raw_message)
    message = json_data['data']['message']
    logging.info(f'received message from pub/sub: {message}')
    return message


def save_onboarding_step(user_id: int, username: str, step: str) -> None:
    """save the certain step in onboarding"""

    pubsub_user_management(
        user_id, ManageUserAction.update_onboarding, username=username, time=datetime.now(), step=step
    )
