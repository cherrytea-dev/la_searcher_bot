import base64
import inspect
import json
from dataclasses import is_dataclass
from datetime import date, datetime
from functools import lru_cache
from typing import Any, Callable, TypeVar
from unittest.mock import MagicMock

import psycopg2
import sqlalchemy
from dotenv import load_dotenv
from faker import Faker
from polyfactory.factories import dataclass_factory
from pydantic_settings import SettingsConfigDict
from sqlalchemy.orm import Session

from _dependencies.commons import AppConfig, sql_connect_by_psycopg2, sqlalchemy_get_pool
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


def _get_default_arg_value(param):
    if param._annotation is str:
        return 'foo'
    elif param._annotation is int:
        return 1
    elif param._annotation is list:
        return []
    elif param._annotation is dict:
        return {}
    elif param._annotation is bool:
        return False
    elif param._annotation is datetime:
        return datetime.now()
    elif param._annotation is date:
        return date.today()
    elif param._annotation is float:
        return 1.1

    # specific
    elif param._annotation is sqlalchemy.engine.Engine:
        return sqlalchemy_get_pool(1, 1)
    elif param._annotation is sqlalchemy.engine.Connection:
        pool = sqlalchemy_get_pool(1, 1)
        return pool.connect()
    elif param._annotation is psycopg2.extensions.connection:
        return sql_connect_by_psycopg2()
    elif param._annotation is psycopg2.extensions.cursor:
        return sql_connect_by_psycopg2().cursor()
    elif is_dataclass(param._annotation):
        factory = _get_dataclass_factory(param._annotation)
        return factory.build()

    # suggestions
    elif param.name == 'conn':
        pool = sqlalchemy_get_pool(1, 1)
        return pool.connect()
    elif param.name == 'db':
        return sql_connect_by_psycopg2()
    # elif param.name == 'cur':
    #     return sql_connect_by_psycopg2().cursor()
    # elif param.name == 'change_log_id':
    #     return 1
    # elif param.name == 'user_id':
    #     return 1

    # ok, just mock it
    else:
        return MagicMock()


@lru_cache
def _get_dataclass_factory(dataclass_) -> dataclass_factory.DataclassFactory:
    return dataclass_factory.DataclassFactory.create_factory(model=dataclass_)


def generate_args_for_function(func: Callable) -> dict[str, Any]:
    signature = inspect.signature(func)

    return {param_name: _get_default_arg_value(signature.parameters[param_name]) for param_name in signature.parameters}


def run_smoke(func: Callable):
    """runs fumction with default args"""
    args = generate_args_for_function(func)
    try:
        return func(**args)
    except Exception as e:
        raise e
    finally:
        for arg in args:
            if False:
                pass
            elif isinstance(args[arg], psycopg2.extensions.cursor):
                args[arg].close()
            elif isinstance(args[arg], psycopg2.extensions.connection):
                args[arg].close()
            elif isinstance(args[arg], sqlalchemy.engine.Connection):
                args[arg].close()


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
    elif topic_name == Topics.topic_for_user_management:
        from manage_users.main import main

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


fake = Faker()
Faker.seed()


@lru_cache
def get_dotenv_config() -> AppConfig:
    assert load_dotenv('.env', override=True)
    return AppConfig()
