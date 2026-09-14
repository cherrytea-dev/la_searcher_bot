import json
import logging
import os
import sys
from functools import lru_cache
from typing import Any

import boto3
import requests
from botocore.client import BaseClient
from pydantic_core import to_json
from pythonjsonlogger.json import JsonFormatter
from retry import retry

Ctx = dict

#: Level used when LOG_LEVEL is not set (or is not understood).
DEFAULT_LOG_LEVEL = 'WARN'

_LEVEL_TO_NUMBER: dict[str, int] = {
    'CRITICAL': logging.CRITICAL,
    'ERROR': logging.ERROR,
    'WARNING': logging.WARNING,
    'WARN': logging.WARNING,
    'INFO': logging.INFO,
    'DEBUG': logging.DEBUG,
}

#: Libraries that chat on INFO (botocore: 'Found credentials in environment variables.',
#: httpx: one line per HTTP request). Their INFO/DEBUG says nothing about our business logic.
NOISY_LOGGERS: tuple[str, ...] = (
    'asyncio',
    'boto3',
    'botocore',
    'httpcore',
    'httpx',
    's3transfer',
    'urllib3',
)


def resolve_log_level(raw_level: str | None = None) -> int:
    """Return the log level number for ``raw_level`` (defaults to the ``LOG_LEVEL`` env var).

    Unset or unrecognized values fall back to :data:`DEFAULT_LOG_LEVEL` (``WARN``):
    services must opt in explicitly (``LOG_LEVEL=INFO``) to write chatter.
    """
    if raw_level is None:
        raw_level = os.environ.get('LOG_LEVEL', '')
    return _LEVEL_TO_NUMBER.get(raw_level.strip().upper(), _LEVEL_TO_NUMBER[DEFAULT_LOG_LEVEL])


def _silence_noisy_loggers() -> None:
    for logger_name in NOISY_LOGGERS:
        logging.getLogger(logger_name).setLevel(logging.WARNING)


def setup_logging_cloud(package_name: str | None = None) -> None:
    handler = logging.StreamHandler(sys.stdout)

    formatter = JsonFormatter(
        '{levelname}{message}{name}{asctime}{exc_info}',
        style='{',
        rename_fields={'levelname': 'level'},
        defaults={'stream_name': package_name},
    )
    handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.addHandler(handler)

    raw_level = os.environ.get('LOG_LEVEL', '')
    root_logger.setLevel(resolve_log_level(raw_level))  # yandex
    _silence_noisy_loggers()

    if raw_level and raw_level.strip().upper() not in _LEVEL_TO_NUMBER:
        root_logger.warning(f'Unknown LOG_LEVEL={raw_level!r}, falling back to {DEFAULT_LOG_LEVEL}')


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
    client.send_message(QueueUrl=queue_url, MessageBody=message_text)
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
    from _dependencies.common.commons import get_app_config

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
