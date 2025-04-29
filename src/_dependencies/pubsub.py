import json
import base64
from functools import lru_cache
import logging
from ast import literal_eval

import google.auth.transport.requests
from google.cloud.pubsub_v1 import PublisherClient
import google.oauth2.id_token
import requests
from retry import retry

from _dependencies.commons import Topics, get_project_id


@lru_cache
def _get_publisher() -> PublisherClient:
    return PublisherClient()


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


@retry(Exception, tries=3, delay=3)
def make_api_call(function: str, data: dict) -> dict:
    """makes an API call to another Google Cloud Function"""

    # function we're turing to "title_recognize"
    endpoint = f'https://europe-west3-lizaalert-bot-01.cloudfunctions.net/{function}'

    # required magic for Google Cloud Functions Gen2 to invoke each other
    audience = endpoint
    auth_req = google.auth.transport.requests.Request()
    id_token = google.oauth2.id_token.fetch_id_token(auth_req, audience)
    headers = {'Authorization': f'Bearer {id_token}', 'Content-Type': 'application/json'}

    response = requests.post(endpoint, json=data, headers=headers, timeout=30)
    response.raise_for_status()
    content = response.json()

    return content


def process_pubsub_message(event: dict) -> str:
    """convert incoming pub/sub message into regular data"""

    # receiving message text from pub/sub
    if 'data' in event:
        received_message_from_pubsub = base64.b64decode(event['data']).decode('utf-8')
    else:
        received_message_from_pubsub = 'I cannot read message from pub/sub'
    encoded_to_ascii = literal_eval(received_message_from_pubsub)
    data_in_ascii = encoded_to_ascii['data']
    message_in_ascii = data_in_ascii['message']

    return message_in_ascii


def process_pubsub_message_v2(event: dict) -> str:
    """get message from pub/sub notification"""

    # receiving message text from pub/sub
    try:
        if 'data' in event:
            received_message_from_pubsub = base64.b64decode(event['data']).decode('utf-8')
            encoded_to_ascii = literal_eval(received_message_from_pubsub)
            data_in_ascii = encoded_to_ascii['data']
            message_in_ascii = data_in_ascii['message']
        else:
            message_in_ascii = 'ERROR: I cannot read message from pub/sub'
    except:  # noqa
        message_in_ascii = 'ERROR: I cannot read message from pub/sub'

    logging.info(f'received message from pub/sub: {message_in_ascii}')

    return message_in_ascii


def process_pubsub_message_v3(event: dict) -> str:
    """convert incoming pub/sub message into regular data"""
    # TODO DOUBLE

    # receiving message text from pub/sub
    if 'data' in event:
        received_message_from_pubsub = base64.b64decode(event['data']).decode('utf-8')
        logging.info('received_message_from_pubsub: ' + str(received_message_from_pubsub))
    elif 'message' in event:
        received_message_from_pubsub = base64.b64decode(event['message']).decode('utf-8')
    else:
        received_message_from_pubsub = 'I cannot read message from pub/sub'
        logging.info(received_message_from_pubsub)
    encoded_to_ascii = literal_eval(received_message_from_pubsub)
    logging.info('encoded_to_ascii: ' + str(encoded_to_ascii))
    try:
        data_in_ascii = encoded_to_ascii['data']
        logging.info('data_in_ascii: ' + str(data_in_ascii))
        message_in_ascii = data_in_ascii['message']
        logging.info('message_in_ascii: ' + str(message_in_ascii))
    except Exception as es:
        message_in_ascii = None
        logging.info('exception happened: ')
        logging.exception(str(es))

    return message_in_ascii
