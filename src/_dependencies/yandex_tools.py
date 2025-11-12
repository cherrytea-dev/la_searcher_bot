import json
import logging
import sys
from functools import lru_cache
from typing import Any

import boto3
import requests
from botocore.client import BaseClient
from pydantic_core import to_json
from pythonjsonlogger import jsonlogger
from retry import retry

Ctx = dict


def setup_logging_cloud(package_name: str | None = None) -> None:
    handler = logging.StreamHandler(sys.stdout)

    formatter = jsonlogger.JsonFormatter(
        '{levelname}{message}{name}{asctime}{exc_info}',
        style='{',
        rename_fields={'levelname': 'level'},
        defaults={'stream_name': package_name},
    )
    handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.addHandler(handler)

    logging.getLogger().setLevel(logging.INFO)  # yandex


@lru_cache
def _get_boto3_client() -> BaseClient:
    return boto3.client(
        service_name='sqs',
        endpoint_url='https://message-queue.api.cloud.yandex.net',
        region_name='ru-central1',
    )


@lru_cache
def _get_queue_url(client: BaseClient, topic_name: str) -> str:
    test_queue_url_data = client.get_queue_url(QueueName=topic_name)
    return test_queue_url_data['QueueUrl']


def _send_serialized_message(topic_name: str, message_text: str) -> None:
    # Create client

    client = _get_boto3_client()

    queue_url = _get_queue_url(client, topic_name)
    resp = client.send_message(QueueUrl=queue_url, MessageBody=message_text)
    pass


def _send_topic(topic_name: str, serialized_message: str) -> None:
    _send_serialized_message(topic_name, serialized_message)


def send_topic_cloud(topic_name: str, message: Any) -> None:
    serialized_message = to_json(message).decode()

    try:
        _send_topic(topic_name, serialized_message)
        logging.info(f'Sent pub/sub message to topic {topic_name}: {str(message)}')

    except Exception:
        logging.exception(f'Not able to send pub/sub message to topic {topic_name}')


@retry(Exception, tries=3, delay=3)
def make_api_call_cloud(function: str, data: dict) -> dict:
    # TODO make more clear
    from _dependencies.commons import get_app_config

    headers = {
        'Content-Type': 'application/json',
    }

    response = requests.post(get_app_config().title_recognize_url, json=data, headers=headers, timeout=30)
    response.raise_for_status()
    return response.json()


def process_pubsub_message_cloud(event: dict) -> str:
    raw_message = event['messages'][0]['details']['message']['body']
    message = json.loads(raw_message)
    logging.info(f'received message from pub/sub: {message}')
    return message
