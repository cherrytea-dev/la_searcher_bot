import ast
import logging
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum, IntEnum, StrEnum
from functools import lru_cache
from typing import Any, Literal

import sqlalchemy
from bs4 import BeautifulSoup
from pydantic import BaseModel, ConfigDict, Field
from pydantic_settings import BaseSettings

from _dependencies.common.yandex_tools import setup_logging_cloud

PHONE_RE = re.compile(r'(?:\+7|7|8)\s?[\s\-(]?\s?\d{3}[\s\-)]?\s?\d{3}[\s\-]?\d{2}[\s\-]?\d{2}')


def setup_logging(package_name: str | None = None) -> None:
    setup_logging_cloud(package_name)


class AppMode(StrEnum):
    """Where the application runs — the single switch behind every mode-dependent setting.

    ``YC``  — the functions of this repository deployed one by one into Yandex Cloud: the queue
              is YMQ, titles are recognized by a separate function over HTTP, the cron jobs are
              timer triggers, the bots are called by the API gateway and each of them is a
              function of its own.

    ``K8S`` — the whole repository as one long-running container (``python -m app.main``, see
              ``doc/single-container.md``): the queue lives in PostgreSQL, the scheduler runs
              in-process, titles are recognized in-process and the bots poll.

    The two are mutually exclusive, so the settings they imply (``queue_backend``,
    ``title_recognize_local``, ``scheduler_enabled``, ``http_enabled``, ``enable_*_bot``) are
    read-only properties of :class:`AppConfig`: a half-cloud/half-container configuration is
    not a state the deployment can actually be in.
    """

    YC = 'yc'
    K8S = 'k8s'


class AppConfig(BaseSettings):
    postgres_user: str
    postgres_password: str
    postgres_db: str
    postgres_host: str
    postgres_port: int = 5432
    api_clients: str = ''
    bot_api_token__prod: str = ''
    bot_api_token: str = ''
    bot_api_host: str = ''
    my_telegram_id: int = 0
    web_app_url: str = ''
    web_app_url_test: str = ''
    yandex_api_key: str = ''
    osm_identifier: str = ''
    forum_bot_login: str = ''
    forum_bot_password: str = ''
    forum_proxy: str = ''
    title_recognize_url: str = ''
    aws_access_key_id: str = ''
    aws_secret_access_key: str = ''
    aws_backup_bucket_name: str = 'la-backup-notifications'
    vk_api_key: str = ''  # TODO SecretStr
    vk_confirmation_code: str = ''
    vk_group_id: int = 0
    max_bot_token: str = ''
    max_bot_webhook_secret: str = ''

    mysql_host: str = ''
    mysql_db: str = ''
    mysql_user: str = ''
    mysql_pass: str = ''

    forum_legacy_data_source: bool = False

    # ── single-container runtime (see doc/single-container.md) ─────────────────────────────
    # Everything below only matters for `python -m app.main`; the cloud functions ignore it.
    # The default is the *cloud* mode: a deploy of the cloud functions must not change behaviour
    # because the single container landed. The container switches the whole runtime with
    # APP_MODE=k8s (see .env.example); what follows from the mode are the read-only properties
    # below, not knobs of their own.
    app_mode: AppMode = AppMode.YC

    # ── queue (the PostgreSQL backend is used in the container mode only) ──────────────────
    queue_visibility_timeout_secs: int = 900
    queue_max_attempts: int = 5
    queue_retry_base_secs: float = 30.0
    queue_retry_max_secs: float = 900.0
    queue_purge_after_secs: int = 7 * 24 * 3600
    worker_threads: int = 2
    worker_poll_interval_secs: float = 1.0
    worker_id: str = ''

    # ── cron scheduler (container mode only) ───────────────────────────────────────────────
    scheduler_timezone: str = 'UTC'
    cron_check_first_posts: str = '* * * * *'
    cron_archive_to_bigquery: str = '13 11 * * *'
    cron_archive_notifications: str = '0 * * * *'

    # ── HTTP server (container mode only) ──────────────────────────────────────────────────
    http_host: str = '0.0.0.0'
    http_port: int = 8080
    api_path_active_searches: str = '/api/v1/active-searches'
    api_path_user_info: str = '/api/v1/user-info'
    webhook_path_telegram: str = ''  # empty = webhook is not served (polling is the default)
    webhook_path_vk: str = ''
    webhook_path_max: str = ''

    # Database connection pool settings
    db_pool_size: int = 2
    db_max_overflow: int = 2
    db_pool_timeout: int = 10  # seconds

    # ── derived from app_mode ──────────────────────────────────────────────────────────────
    # Read-only on purpose: they describe *how the process is deployed*, and the two modes are
    # mutually exclusive. As fields they made impossible states expressible — in-process title
    # recognition on top of the YMQ queue, or the in-process scheduler next to the Yandex timer
    # triggers doing the same job twice.
    @property
    def queue_backend(self) -> Literal['pg', 'ymq']:
        """``pg`` (table in PostgreSQL) in the container, ``ymq`` (Yandex Message Queue) in the cloud."""
        return 'pg' if self.app_mode is AppMode.K8S else 'ymq'

    @property
    def title_recognize_local(self) -> bool:
        """The container recognizes titles in-process; in the cloud a function does it over HTTP."""
        return self.app_mode is AppMode.K8S

    @property
    def scheduler_enabled(self) -> bool:
        """The cron jobs run in the container only — in the cloud the timer triggers fire them."""
        return self.app_mode is AppMode.K8S

    @property
    def http_enabled(self) -> bool:
        """The container serves HTTP itself; in the cloud the API gateway calls the functions."""
        return self.app_mode is AppMode.K8S

    @property
    def enable_tg_bot(self) -> bool:
        """The bots poll in the container only — in the cloud each of them is a function."""
        return self.app_mode is AppMode.K8S

    @property
    def enable_vk_bot(self) -> bool:
        return self.app_mode is AppMode.K8S

    @property
    def enable_max_bot(self) -> bool:
        return self.app_mode is AppMode.K8S

    def model_post_init(self, __context: Any) -> None:
        # The single container runs all functions in one process against a single shared engine
        # (queue workers, the bots, the scheduler, lock_manager and the HTTP handlers). The cloud
        # default of pool_size=2 + max_overflow=2 (4 connections) is too small there and times out
        # under load, so the container mode raises it to 10/10. Explicit env values still win.
        if self.app_mode is AppMode.K8S:
            if 'db_pool_size' not in self.model_fields_set:
                self.db_pool_size = 10
            if 'db_max_overflow' not in self.model_fields_set:
                self.db_max_overflow = 10

    @property
    def phpbb_db_url(self) -> str:
        return f'mysql+pymysql://{self.mysql_user}:{self.mysql_pass}@{self.mysql_host}:3306/{self.mysql_db}'


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
    return AppConfig()


@lru_cache
def sqlalchemy_get_pool() -> sqlalchemy.engine.Engine:
    """connect to PSQL in GCP"""
    return sqlalchemy_get_pool_inner()


@lru_cache
def sqlalchemy_get_pool_inner() -> sqlalchemy.engine.Engine:
    """connect to PSQL in GCP"""
    config = get_app_config()

    db_config = {
        'pool_size': config.db_pool_size,
        'max_overflow': config.db_max_overflow,
        'pool_timeout': config.db_pool_timeout,  # seconds
        'pool_recycle': 3600,  # seconds (1 hour)
        'pool_pre_ping': True,
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


# Notification preference IDs — shared between Telegram and VK bots.
# Maps preference name (used in code) to its integer ID in the DB.
# NOTE: Both snake_case (topic_new) and legacy (new_searches) keys are
# included for backward compatibility. When both are present, they must
# map to the same ID.
PREF_DICT: dict[str, int] = {
    'topic_new': 0,
    'topic_status_change': 1,
    'topic_title_change': 2,
    'topic_comment_new': 3,
    'topic_inforg_comment_new': 4,
    'topic_field_trip_new': 5,
    'topic_field_trip_change': 6,
    'topic_coords_change': 7,
    'topic_first_post_change': 8,
    'topic_all_in_followed_search': 9,
    'bot_news': 20,
    'all': 30,
    'not_defined': 99,
    # Legacy keys (used by communicate bot)
    'new_searches': 0,
    'status_changes': 1,
    'title_changes': 2,
    'comments_changes': 3,
    'inforg_comments': 4,
    'field_trips_new': 5,
    'field_trips_change': 6,
    'coords_change': 7,
    'first_post_changes': 8,
    'all_in_followed_search': 9,
}


# Default notification preferences assigned on registration and restored on
# reset. Single source of truth — values are pref_ids from PREF_DICT above.
DEFAULT_NOTIFICATION_PREFS: tuple[tuple[str, int], ...] = (
    ('new_searches', 0),
    ('status_changes', 1),
    ('inforg_comments', 4),
    ('first_post_changes', 8),
    ('bot_news', 20),
)


def save_default_notification_settings(conn: sqlalchemy.engine.Connection, user_id: int) -> None:
    """Insert the default notification categories into user_preferences.

    Idempotent: ``ON CONFLICT DO NOTHING`` makes a second call harmless.
    """
    stmt = sqlalchemy.text("""
        INSERT INTO user_preferences (user_id, preference, pref_id)
        VALUES (:user_id, :preference, :pref_id)
        ON CONFLICT (user_id, pref_id) DO NOTHING
    """)
    for pref_name, pref_id in DEFAULT_NOTIFICATION_PREFS:
        conn.execute(stmt, {'user_id': user_id, 'preference': pref_name, 'pref_id': pref_id})
    logging.info(f'Default notification categories set for user {user_id}.')


def add_tel_link(incoming_text: str) -> str:
    """check is text contains phone number and replaces it with clickable version, also removes [tel] tags"""

    outcome_text = unify_phone_format(incoming_text)
    phones = re.findall(PHONE_RE, outcome_text)
    for num in set(phones):
        normalized_phone = _normalize_phone(num)
        try:
            outcome_text = outcome_text.replace(num, _make_phone_link(normalized_phone))
            outcome_text = _move_phone_links_outside_href_tags(outcome_text)
        except Exception:
            ### logging here is not needed untill we have strange behaviour
            ## logging.exception(f'add_tel_link..{e=} on {num=} in {outcome_text=}')
            outcome_text = outcome_text.replace(num, '<code>' + str(num) + '</code>')

    phpbb_tags_to_delete = {'[tel]', '[/tel]'}
    for tag in phpbb_tags_to_delete:
        outcome_text = outcome_text.replace(tag, '', 5)

    return outcome_text


def _make_phone_link(phone: str) -> str:
    return f' <a href="tel:{phone}"> ☎️{phone}</a> '


def _normalize_phone(phone: str) -> str:
    return '+7' + phone[1:] if phone[0] == '8' else phone


def unify_phone_format(text: str) -> str:
    phones = re.findall(PHONE_RE, text)
    for phone in set(phones):
        text = text.replace(phone, _normalize_phone(phone))
    return text


def _move_phone_links_outside_href_tags(outcome_text: str) -> str:
    # move tel-tags outside of other a-tags
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
    return str(soup)


# ═══════════════════════════════════════════════════════════════════════════════
# Messenger abstraction layer (Phase 2)
# ═══════════════════════════════════════════════════════════════════════════════


class Messenger(StrEnum):
    """Supported messengers."""

    TELEGRAM = 'telegram'
    VK = 'vk'
    MAX = 'max'


@dataclass(frozen=True)
class UserIdentity:
    """Identifies a user within a specific messenger."""

    internal_user_id: int
    messenger: Messenger
    messenger_user_id: str


@dataclass(frozen=True)
class SendResult:
    """Result of sending a message."""

    success: bool
    status: str  # 'completed', 'cancelled', 'failed', 'cancelled_bad_request', 'failed_flood_control'
    status_code: int | None = None


class MessengerClient(ABC):
    """Abstract interface for sending messages via any messenger."""

    messenger: Messenger

    @abstractmethod
    def send_message(self, user_identity: UserIdentity, text: str, **kwargs: object) -> SendResult: ...

    @abstractmethod
    def send_coordinates(self, user_identity: UserIdentity, lat: float, lng: float) -> SendResult: ...
