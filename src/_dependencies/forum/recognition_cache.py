"""Cache of title recognition answers — including the failed ones.

`title_recognize` is a pure function of the title text: the same title always produces the same
answer. So an answer can be stored and reused instead of calling the cloud function again.

Failures matter as much as successes here. A title the recognizer cannot parse (e.g. `[ИНФО] …`,
`Внутренняя информация`) comes back as `status: fail`, and the callers store nothing — so the same
unchanged title is sent to the cloud function again on every pass. In production logs (2026-09-20,
6 hours) 209 of 239 recognition calls were such repeats: `[ИНФО] Рязанскому отряду требуются!` was
sent 170 times, every ~2 minutes. None of those repeats could ever succeed.

A failed title is therefore cached with a backoff (1 h → 6 h → 24 h → 7 d), so a title that becomes
recognizable after a fix is still picked up later. Successful answers are kept much longer. The whole
cache is invalidated by bumping `CACHE_VERSION` whenever recognition logic changes.

Storage is the `key_value_storage` table, one row per distinct title
(`title-reco-v<version>-<type>-<hash>`). Storage is best-effort: read/write errors are logged and the
call falls through to the API, so a broken cache can never break recognition.
"""

import hashlib
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Protocol

from _dependencies.common.pubsub import recognize_title_via_api

# Bump to invalidate the whole cache when the recognition logic changes.
CACHE_VERSION = 2

CACHE_KEY_PREFIX = 'title-reco'
SUCCESS_TTL = timedelta(days=180)
FAILURE_RETRY_DELAYS = (
    timedelta(hours=1),
    timedelta(hours=6),
    timedelta(days=1),
    timedelta(days=7),
)

FULL_RECOGNITION = 'full'
STATUS_ONLY_RECOGNITION = 'status_only'

_OK_STATUS = 'ok'
_FAIL_STATUS = 'fail'

# Titles are stored for diagnostics only, so a long one is cut instead of blowing up the row.
MAX_STORED_TITLE_LENGTH = 300

logger = logging.getLogger(__name__)


class RecognitionCacheStore(Protocol):
    """the part of a DB client the cache needs (`key_value_storage` table)"""

    def get_key_value_item(self, key: str) -> Any: ...

    def set_key_value_item(self, key: str, value: Any) -> None: ...


def cache_key(title: str, reco_type: str) -> str:
    """storage key of one title; fits `key_value_storage.key` (varchar(100))"""

    digest = hashlib.sha1(title.strip().encode('utf-8')).hexdigest()[:32]
    return f'{CACHE_KEY_PREFIX}-v{CACHE_VERSION}-{reco_type}-{digest}'


def lookup(
    cache_store: RecognitionCacheStore,
    title: str,
    reco_type: str,
    now: datetime | None = None,
) -> dict[str, Any] | None:
    """return the stored answer for the title, or None when the API has to be asked"""

    entry = _read_entry(cache_store, cache_key(title, reco_type), title)
    if not _is_fresh(entry, now or _now()):
        return None

    response = entry.get('response') if entry else None
    return response if isinstance(response, dict) else None


def store(
    cache_store: RecognitionCacheStore,
    title: str,
    reco_type: str,
    response: dict[str, Any],
    now: datetime | None = None,
) -> None:
    """remember the answer for the title; a failed one is remembered with a backoff"""

    if not isinstance(response, dict) or not title.strip():
        return

    moment = now or _now()
    key = cache_key(title, reco_type)
    previous = _read_entry(cache_store, key, title)

    if _is_ok(response):
        attempts = 0
        next_retry_at = None
    else:
        attempts = _attempts_before(previous) + 1
        next_retry_at = moment + _retry_delay(attempts)

    _write_entry(
        cache_store,
        key,
        {
            'version': CACHE_VERSION,
            'title': title.strip()[:MAX_STORED_TITLE_LENGTH],
            'reco_type': reco_type,
            'status': _OK_STATUS if _is_ok(response) else _FAIL_STATUS,
            'response': response,
            'fail_reason': response.get('fail_reason'),
            'attempts': attempts,
            'stored_at': moment.isoformat(),
            'next_retry_at': next_retry_at.isoformat() if next_retry_at else None,
        },
        title,
    )


def recognize_title_cached(
    cache_store: RecognitionCacheStore,
    title: str,
    status_only: bool = False,
    api_call: Any = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """drop-in replacement for `recognize_title_via_api` that reuses stored answers

    Args:
        cache_store: any client with `key_value_storage` access.
        title: the search title to recognize.
        status_only: ask only for the status, like `reco_type=status_only` does.
        api_call: the API function to use on a cache miss (tests pass their own).
        now: current moment, for tests.
    """

    call = api_call or recognize_title_via_api
    reco_type = STATUS_ONLY_RECOGNITION if status_only else FULL_RECOGNITION

    if not title.strip():
        return call(title, status_only)

    cached = lookup(cache_store, title, reco_type, now)
    if cached is not None:
        logger.debug(f'recognition cache hit ({reco_type}): {title[:60]}')
        return cached

    response = call(title, status_only)
    store(cache_store, title, reco_type, response, now)
    return response


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _is_ok(response: dict[str, Any]) -> bool:
    return response.get('status') == _OK_STATUS


def _attempts_before(entry: dict[str, Any] | None) -> int:
    attempts = entry.get('attempts') if entry else None
    return attempts if isinstance(attempts, int) else 0


def _retry_delay(attempts: int) -> timedelta:
    index = min(max(attempts, 1), len(FAILURE_RETRY_DELAYS)) - 1
    return FAILURE_RETRY_DELAYS[index]


def _is_fresh(entry: dict[str, Any] | None, now: datetime) -> bool:
    if not entry or entry.get('version') != CACHE_VERSION:
        return False

    if entry.get('status') == _OK_STATUS:
        stored_at = _parse_time(entry.get('stored_at'))
        return stored_at is not None and now < stored_at + SUCCESS_TTL

    next_retry_at = _parse_time(entry.get('next_retry_at'))
    return next_retry_at is not None and now < next_retry_at


def _parse_time(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None

    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None

    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _read_entry(store: RecognitionCacheStore, key: str, title: str) -> dict[str, Any] | None:
    try:
        entry = store.get_key_value_item(key)
    except Exception:
        logger.warning(f'cannot read the recognition cache for "{title[:60]}", asking the API', exc_info=True)
        return None

    return entry if isinstance(entry, dict) else None


def _write_entry(store: RecognitionCacheStore, key: str, entry: dict[str, Any], title: str) -> None:
    try:
        store.set_key_value_item(key, entry)
    except Exception:
        logger.warning(f'cannot write the recognition cache for "{title[:60]}"', exc_info=True)
