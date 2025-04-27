import ast
import json
import logging
import os
import urllib.request
from enum import Enum, IntEnum
from functools import lru_cache
from typing import Any

import google.cloud.logging
import psycopg2
import sqlalchemy
from google.cloud import pubsub_v1, secretmanager
from pydantic import BaseModel, ConfigDict, Field
from pydantic_settings import BaseSettings


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


@lru_cache
def get_secret_manager_client() -> secretmanager.SecretManagerServiceClient:
    return secretmanager.SecretManagerServiceClient()


@lru_cache
def get_project_id() -> str:
    url = 'http://metadata.google.internal/computeMetadata/v1/project/project-id'
    req = urllib.request.Request(url)
    req.add_header('Metadata-Flavor', 'Google')
    project_id = urllib.request.urlopen(req).read().decode()
    return project_id


@lru_cache  # TODO maybe cachetools/timed_lru_cache?
def get_secrets(secret_request: str) -> str:
    """Get GCP secret"""

    name = f'projects/{get_project_id()}/secrets/{secret_request}/versions/latest'
    response = get_secret_manager_client().access_secret_version(name=name)

    return response.payload.data.decode('UTF-8')


def setup_google_logging() -> None:
    logging_disabled = os.getenv('GOOGLE_LOGGING_DISABLED', False)
    if logging_disabled:
        # TODO pydantic-settings or improve parsing here.
        return

    log_client = google.cloud.logging.Client()
    log_client.setup_logging()


@lru_cache
def get_publisher() -> pubsub_v1.PublisherClient:
    return pubsub_v1.PublisherClient()


def publish_to_pubsub(topic_name: Topics, message: str | dict | list) -> None:
    """publish a new message to pub/sub"""

    topic_name_str = topic_name.value if isinstance(topic_name, Topics) else topic_name
    #  TODO find out where topic_name.value comes from as str

    topic_path = get_publisher().topic_path(get_project_id(), topic_name_str)
    data = {
        'data': {'message': message},
    }
    message_json = json.dumps(data)
    message_bytes = message_json.encode('utf-8')

    try:
        _send_topic(topic_name, topic_path, message_bytes)
        logging.info(f'Sent pub/sub message: {str(message)}')

    except Exception as e:
        logging.error('Not able to send pub/sub message: ' + repr(e))
        logging.exception(e)

    return None


def _send_topic(topic_name: Topics, topic_path: str, message_bytes: bytes) -> None:
    publish_future = get_publisher().publish(topic_path, data=message_bytes)
    publish_future.result()  # Verify the publishing succeeded


class AppConfig(BaseSettings):
    postgres_user: str
    postgres_password: str
    postgres_db: str
    postgres_host: str
    postgres_port: int = 5432
    api_clients: str = ''
    bot_api_token__prod: str = ''
    bot_api_token: str = ''
    my_telegram_id: int = 0
    web_app_url: str = ''
    web_app_url_test: str = ''
    yandex_api_key: str = ''
    osm_identifier: str = ''
    forum_bot_login: str = ''
    forum_bot_password: str = ''
    forum_proxy: str = ''


@lru_cache
def get_app_config() -> AppConfig:
    return _get_config()


@lru_cache
def get_forum_proxies() -> dict:
    proxy = get_app_config().forum_proxy
    if proxy:
        return {
            'http': f'{proxy}',
            'https': f'{proxy}',
        }
    else:
        return {}


def _get_config() -> AppConfig:
    """for patching in tests"""
    return AppConfig(
        postgres_user=get_secrets('cloud-postgres-username'),
        postgres_password=get_secrets('cloud-postgres-password'),
        postgres_db=get_secrets('cloud-postgres-db-name'),
        postgres_host='/cloudsql/' + get_secrets('cloud-postgres-connection-name'),
        postgres_port=5432,
        api_clients=get_secrets('api_clients'),
        bot_api_token__prod=get_secrets('bot_api_token__prod'),
        bot_api_token=get_secrets('bot_api_token'),
        my_telegram_id=int(get_secrets('my_telegram_id')),
        web_app_url=get_secrets('web_app_url'),
        web_app_url_test=get_secrets('web_app_url_test'),
        yandex_api_key=get_secrets('yandex_api_key'),
        osm_identifier=get_secrets('osm_identifier'),
        forum_bot_login=get_secrets('forum_bot_login'),
        forum_bot_password=get_secrets('forum_bot_password'),
        forum_proxy=get_secrets('forum_proxy'),
    )


def sql_connect_by_psycopg2() -> psycopg2.extensions.connection:
    """connect to GCP SQL via PsycoPG2"""
    # TODO pool instead of single connections
    config = get_app_config()

    conn_psy = psycopg2.connect(
        host=config.postgres_host,
        dbname=config.postgres_db,
        user=config.postgres_user,
        password=config.postgres_password,
        port=config.postgres_port,
    )
    conn_psy.autocommit = True

    return conn_psy


@lru_cache
def sqlalchemy_get_pool(pool_size: int, pool_recycle_time_seconds: int) -> sqlalchemy.engine.Engine:
    """connect to PSQL in GCP"""
    config = get_app_config()

    db_config = {
        'pool_size': pool_size,
        'max_overflow': 0,
        'pool_timeout': 0,  # seconds
        'pool_recycle': pool_recycle_time_seconds,  # seconds
    }

    pool = sqlalchemy.create_engine(
        sqlalchemy.engine.url.URL.create(
            'postgresql+psycopg2',
            username=config.postgres_user,
            host=config.postgres_host,
            port=config.postgres_port,
            password=config.postgres_password,
            database=config.postgres_db,
        ),
        **db_config,
    )

    pool.dialect.description_encoding = None

    return pool


class ChangeLogSavedValue(BaseModel):
    """value that stored in database `change_log.new_value`"""

    model_config = ConfigDict(extra='ignore')

    deletions: list[str] = Field(default_factory=list, alias='del')
    additions: list[str] = Field(default_factory=list, alias='add')
    message: str = Field(default='')

    @classmethod
    def from_db_saved_value(cls, saved_value: str) -> 'ChangeLogSavedValue':
        if not saved_value or not saved_value.startswith('{'):
            return cls(message=saved_value)

        data = ast.literal_eval(saved_value)
        return cls.model_validate(data)

    def to_db_saved_value(self) -> str:
        return str(self.model_dump(by_alias=True))


class ChangeType(IntEnum):
    """
    SQL table 'dict_notif_types'
    """

    topic_new = 0
    topic_status_change = 1
    topic_title_change = 2
    topic_comment_new = 3
    topic_inforg_comment_new = 4
    topic_field_trip_new = 5
    topic_field_trip_change = 6
    topic_coords_change = 7
    topic_first_post_change = 8
    bot_news = 20
    not_defined = 99
    all = 30


class TopicType(IntEnum):
    """
    SQL table 'dict_topic_types'
    """

    search_regular = 0
    search_reverse = 1
    search_patrol = 2
    search_training = 3
    search_info_support = 4
    search_resonance = 5
    event = 10
    info = 20
    all = 30
    unrecognized = 99


class SearchFollowingMode(str, Enum):
    # in table 'user_pref_search_whitelist'
    # TODO replace values in 'communicate' to this enum later
    ON = '👀 '
    OFF = '❌ '
