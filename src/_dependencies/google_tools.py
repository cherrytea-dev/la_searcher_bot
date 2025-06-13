import base64
import json
import logging
import os
import urllib.request
from functools import lru_cache
from typing import Any, TypeAlias

import google.auth.transport.requests
import google.cloud.logging
import google.oauth2.id_token
import requests
from google.cloud import pubsub_v1, secretmanager
from google.cloud.functions.context import Context
from pydantic import BaseModel
from retry import retry

Ctx: TypeAlias = Context


@lru_cache
def _get_secret_manager_client() -> secretmanager.SecretManagerServiceClient:
    return secretmanager.SecretManagerServiceClient()


@lru_cache
def _get_project_id() -> str:
    url = 'http://metadata.google.internal/computeMetadata/v1/project/project-id'
    req = urllib.request.Request(url)
    req.add_header('Metadata-Flavor', 'Google')
    project_id = urllib.request.urlopen(req).read().decode()
    return project_id


@lru_cache  # TODO maybe cachetools/timed_lru_cache?
def get_secrets(secret_request: str) -> str:
    """Get GCP secret"""

    name = f'projects/{_get_project_id()}/secrets/{secret_request}/versions/latest'
    response = _get_secret_manager_client().access_secret_version(name=name)

    return response.payload.data.decode('UTF-8')


@lru_cache
def _get_publisher() -> pubsub_v1.PublisherClient:
    return pubsub_v1.PublisherClient()


@retry(Exception, tries=3, delay=3)
def make_api_call_cloud(function: str, data: dict) -> dict:
    endpoint = f'https://europe-west3-lizaalert-bot-01.cloudfunctions.net/{function}'

    # required magic for Google Cloud Functions Gen2 to invoke each other
    audience = endpoint
    auth_req = google.auth.transport.requests.Request()
    id_token = google.oauth2.id_token.fetch_id_token(auth_req, audience)
    headers = {'Authorization': f'Bearer {id_token}', 'Content-Type': 'application/json'}

    response = requests.post(endpoint, json=data, headers=headers, timeout=30)
    response.raise_for_status()
    return response.json()


class PubSubMessage(BaseModel):
    message: Any


class PubSubData(BaseModel):
    data: PubSubMessage


def _get_message_data(message: Any) -> bytes:
    data = PubSubData(data=PubSubMessage(message=message))
    message_bytes = data.model_dump_json().encode('utf-8')
    return message_bytes


def send_topic_cloud(topic_name_str: str, message: Any) -> None:
    topic_path = _get_publisher().topic_path(_get_project_id(), topic_name_str)
    message_bytes = _get_message_data(message)

    try:
        publish_future = _get_publisher().publish(topic_path, data=message_bytes)
        publish_future.result()  # Verify the publishing succeeded
        logging.info(f'Sent pub/sub message: {str(message)}')

    except Exception:
        logging.exception('Not able to send pub/sub message')


def process_pubsub_message_cloud(event: dict) -> str:
    """convert incoming pub/sub message into regular data"""

    # receiving message text from pub/sub
    raw_message = base64.b64decode(event['data']).decode('utf-8')
    json_data = json.loads(raw_message)
    message = json_data['data']['message']
    logging.info(f'received message from pub/sub: {message}')
    return message


def setup_logging_cloud(package_name: str | None = None) -> None:
    logging_disabled = os.getenv('GOOGLE_LOGGING_DISABLED', False)
    if logging_disabled:
        # TODO pydantic-settings or improve parsing here.
        return

    log_client = google.cloud.logging.Client()
    log_client.setup_logging()
