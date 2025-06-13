import base64
import json
import logging
import sys
from functools import lru_cache
from typing import Any, TypeVar

from dotenv import load_dotenv
from faker import Faker
from pydantic_settings import SettingsConfigDict
from sqlalchemy.orm import Session

from _dependencies.commons import AppConfig
from _dependencies.google_tools import _get_message_data
from _dependencies.pubsub import Topics

T = TypeVar('T')


class AppTestConfig(AppConfig):
    model_config = SettingsConfigDict(extra='ignore')


@lru_cache
def get_test_config() -> AppTestConfig:
    assert load_dotenv('.env.test', override=True)
    return AppTestConfig()


def get_event_with_data(message) -> dict:
    encoded_data = base64.b64encode(json.dumps({'data': {'message': message}}).encode())
    event = {'data': encoded_data}
    return event


def patched_send_topic(topic_name: Topics, topic_path, data: dict) -> None:
    receiver = topic_to_receiver_function(topic_name)
    receiver({'data': base64.encodebytes(data)}, 'context')


@lru_cache
def topic_to_receiver_function(topic_name: Topics):
    # TODO rewrite to decorator
    if topic_name == Topics.parse_user_profile_from_forum:
        from connect_to_forum.main import main

        return main
    elif topic_name == Topics.topic_for_first_post_processing:
        from identify_updates_of_first_posts.main import main

        return main
    elif topic_name == Topics.topic_for_notification:
        from compose_notifications.main import main

        return main
    elif topic_name == Topics.topic_notify_admin:
        from send_debug_to_admin.main import main

        return main
    elif topic_name == Topics.topic_to_run_parsing_script:
        from identify_updates_of_topics.main import main

        return main
    elif topic_name == Topics.topic_to_send_notifications:
        from send_notifications.main import main

        return main

    else:
        raise ValueError(f'Unknown topic {topic_name}')


def find_model(session: Session, model: type[T], **kwargs: Any) -> T | None:
    query = session.query(model)
    for key, value in kwargs.items():
        query = query.filter_by(**{key: value})
    return query.first()


@lru_cache
def get_dotenv_config() -> AppConfig:
    assert load_dotenv('.env', override=True)
    return AppConfig()


def setup_logging_to_console() -> None:
    logging.basicConfig(
        encoding='utf-8',
        stream=sys.stdout,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        level=logging.INFO,
        force=True,
    )


def patched_send_topic(topic_name_str: str, data: Any) -> None:
    topic_name = Topics(topic_name_str)
    data_bytes = _get_message_data(data)
    receiver = topic_to_receiver_function(topic_name)

    receiver({'data': base64.encodebytes(data_bytes)}, 'context')


fake = Faker()
Faker.seed()
