import ast
import re
from enum import Enum, IntEnum
from functools import lru_cache

import psycopg2
import sqlalchemy
from bs4 import BeautifulSoup
from pydantic import BaseModel, ConfigDict, Field
from pydantic_settings import BaseSettings

from _dependencies.google_tools import get_secrets, setup_logging_cloud

PHONE_RE = re.compile(r'(?:\+7|7|8)\s?[\s\-(]?\s?\d{3}[\s\-)]?\s?\d{3}[\s\-]?\d{2}[\s\-]?\d{2}')


def setup_logging(package_name: str | None = None) -> None:
    setup_logging_cloud(package_name)


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


def add_tel_link(incoming_text: str) -> str:
    """check is text contains phone number and replaces it with clickable version, also removes [tel] tags"""

    # Modifier for all users

    outcome_text = incoming_text
    nums = re.findall(PHONE_RE, incoming_text)
    nums = list(set(nums))  # remove duplicates
    for num in nums:
        num_link = str('+7' + num[1:] if num[0] == '8' else num)
        try:
            outcome_text = outcome_text.replace(num, ' <a href="tel:' + num_link + '">' + num_link + '</a> ')

            ## move tel-tags outside of other a-tags
            soup = BeautifulSoup(outcome_text, 'html.parser')
            for outer_a in soup.find_all('a'):
                inner_a = outer_a.find('a')
                if inner_a and inner_a['href'].startswith('tel:'):
                    inner_a_text = inner_a.decode_contents()
                    inner_a_href = inner_a['href']
                    inner_a.decompose()
                    new_inner_a = soup.new_tag('a', href=inner_a_href)
                    new_inner_a.string = inner_a_text
                    outer_a.insert_after(new_inner_a)
            outcome_text = str(soup)

        except Exception as e:
            ### logging here is not needed untill we have strange behaviour
            ## logging.exception(f'add_tel_link..{e=} on {num=} in {outcome_text=}')
            outcome_text = outcome_text.replace(num, '<code>' + str(num) + '</code>')

    phpbb_tags_to_delete = {'[tel]', '[/tel]'}
    for tag in phpbb_tags_to_delete:
        outcome_text = outcome_text.replace(tag, '', 5)

    return outcome_text
