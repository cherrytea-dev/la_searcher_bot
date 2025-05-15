import base64
import json
import logging
from functools import lru_cache

import google.auth.transport.requests
import google.oauth2.id_token
import requests
from google.cloud import pubsub_v1
from retry import retry

from _dependencies.commons import Topics, get_project_id


@lru_cache
def _get_publisher() -> pubsub_v1.PublisherClient:
    return pubsub_v1.PublisherClient()


def _send_topic(topic_name: Topics, topic_path: str, message_bytes: bytes) -> None:
    publish_future = _get_publisher().publish(topic_path, data=message_bytes)
    publish_future.result()  # Verify the publishing succeeded


def publish_to_pubsub(topic_name: Topics, message: str | dict | list) -> None:
    """publish a new message to pub/sub"""

    topic_name_str = topic_name.value if isinstance(topic_name, Topics) else topic_name
    #  TODO find out where topic_name.value comes from as str

    topic_path = _get_publisher().topic_path(get_project_id(), topic_name_str)
    data = {
        'data': {'message': message},
    }
    message_bytes = json.dumps(data).encode('utf-8')

    try:
        _send_topic(topic_name, topic_path, message_bytes)
        logging.info(f'Sent pub/sub message: {str(message)}')

    except Exception:
        logging.exception('Not able to send pub/sub message')


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
