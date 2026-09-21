"""The recognition cache: a title is recognized once, not on every pass over the forum.

`title_recognize` is a pure function of the title, so its answer — including a failed one — is
stored and reused. Production logs (2026-09-20, 6 h) show why the failures matter: 209 of 239
recognition calls were repeats of titles the recognizer cannot parse at all
(`[ИНФО] Рязанскому отряду требуются!` — 170 calls, every ~2 minutes).
"""

from datetime import datetime, timedelta, timezone
from typing import Any

import pytest

from _dependencies.forum import recognition_cache
from _dependencies.forum.recognition_cache import (
    FAILURE_RETRY_DELAYS,
    SUCCESS_TTL,
    cache_key,
    recognize_title_cached,
    store,
)

NOW = datetime(2026, 9, 20, 20, 0, tzinfo=timezone.utc)
TITLE = 'Пропала Петрова Мария, Екатеринбург'
UNRECOGNIZABLE_TITLE = '[ИНФО] Рязанскому отряду требуются!'
FULL = 'full'
STATUS_ONLY = 'status_only'


class FakeStore:
    """`key_value_storage` without a database"""

    def __init__(self) -> None:
        self.items: dict[str, Any] = {}

    def get_key_value_item(self, key: str) -> Any:
        return self.items.get(key)

    def set_key_value_item(self, key: str, value: Any) -> None:
        self.items[key] = value


class BrokenStore:
    """a database that is not available"""

    def get_key_value_item(self, key: str) -> Any:
        raise RuntimeError('the database is down')

    def set_key_value_item(self, key: str, value: Any) -> None:
        raise RuntimeError('the database is down')


class FakeRecognition:
    """collects the titles sent to the API and answers with the given response"""

    def __init__(self, response: dict[str, Any] | None = None) -> None:
        self.titles: list[str] = []
        self.response = ok_response() if response is None else response

    def __call__(self, title: str, status_only: bool = False) -> dict[str, Any]:
        self.titles.append(title)
        return self.response


def ok_response(status: str = 'Ищем') -> dict[str, Any]:
    return {'status': 'ok', 'recognition': {'topic_type': 'search', 'status': status}}


def fail_response(reason: str = 'not able to recognize') -> dict[str, Any]:
    return {'status': 'fail', 'fail_reason': reason}


def entry_of(cache: FakeStore, title: str = TITLE, reco_type: str = FULL) -> dict[str, Any] | None:
    return cache.items.get(cache_key(title, reco_type))


class TestRecognizedTitleIsReused:
    def test_a_new_title_is_sent_to_the_api(self) -> None:
        cache, api = FakeStore(), FakeRecognition()

        response = recognize_title_cached(cache, TITLE, api_call=api, now=NOW)

        assert api.titles == [TITLE]
        assert response == ok_response()
        assert entry_of(cache)['status'] == 'ok'  # type:ignore [index]

    def test_the_second_call_does_not_reach_the_api(self) -> None:
        cache, api = FakeStore(), FakeRecognition()
        recognize_title_cached(cache, TITLE, api_call=api, now=NOW)

        response = recognize_title_cached(cache, TITLE, api_call=api, now=NOW + timedelta(days=1))

        assert api.titles == [TITLE]
        assert response == ok_response()

    def test_a_successful_answer_expires(self) -> None:
        cache, api = FakeStore(), FakeRecognition()
        recognize_title_cached(cache, TITLE, api_call=api, now=NOW)

        recognize_title_cached(cache, TITLE, api_call=api, now=NOW + SUCCESS_TTL + timedelta(seconds=1))

        assert api.titles == [TITLE, TITLE]

    def test_a_title_with_spaces_around_it_is_the_same_title(self) -> None:
        cache, api = FakeStore(), FakeRecognition()
        recognize_title_cached(cache, f'  {TITLE}  ', api_call=api, now=NOW)

        assert recognize_title_cached(cache, TITLE, api_call=api, now=NOW) == ok_response()
        assert api.titles == [f'  {TITLE}  ']


class TestUnrecognizableTitleIsNotAskedAgain:
    def test_a_failed_answer_is_remembered(self) -> None:
        cache, api = FakeStore(), FakeRecognition(fail_response())

        recognize_title_cached(cache, UNRECOGNIZABLE_TITLE, api_call=api, now=NOW)

        entry = entry_of(cache, UNRECOGNIZABLE_TITLE)
        assert entry is not None
        assert entry['status'] == 'fail'
        assert entry['fail_reason'] == 'not able to recognize'

    def test_the_second_call_does_not_reach_the_api(self) -> None:
        cache, api = FakeStore(), FakeRecognition(fail_response())
        first = recognize_title_cached(cache, UNRECOGNIZABLE_TITLE, api_call=api, now=NOW)

        second = recognize_title_cached(cache, UNRECOGNIZABLE_TITLE, api_call=api, now=NOW + timedelta(minutes=2))

        assert api.titles == [UNRECOGNIZABLE_TITLE]
        assert first == second == fail_response()

    def test_the_title_is_asked_again_once_the_backoff_is_over(self) -> None:
        cache, api = FakeStore(), FakeRecognition(fail_response())
        recognize_title_cached(cache, UNRECOGNIZABLE_TITLE, api_call=api, now=NOW)

        recognize_title_cached(
            cache,
            UNRECOGNIZABLE_TITLE,
            api_call=api,
            now=NOW + FAILURE_RETRY_DELAYS[0] + timedelta(seconds=1),
        )

        assert api.titles == [UNRECOGNIZABLE_TITLE, UNRECOGNIZABLE_TITLE]

    def test_every_failed_attempt_delays_the_next_one_more(self) -> None:
        cache = FakeStore()
        moment = NOW

        expected_delays = [*FAILURE_RETRY_DELAYS, FAILURE_RETRY_DELAYS[-1]]

        for attempt, delay in enumerate(expected_delays, start=1):
            api = FakeRecognition(fail_response())
            recognize_title_cached(cache, UNRECOGNIZABLE_TITLE, api_call=api, now=moment)

            assert api.titles == [UNRECOGNIZABLE_TITLE]
            entry = entry_of(cache, UNRECOGNIZABLE_TITLE)
            assert entry is not None
            assert entry['attempts'] == attempt
            assert datetime.fromisoformat(entry['next_retry_at']) == moment + delay

            moment += delay + timedelta(seconds=1)

    def test_a_successful_answer_resets_the_attempts(self) -> None:
        cache = FakeStore()
        recognize_title_cached(cache, TITLE, api_call=FakeRecognition(fail_response()), now=NOW)
        recognize_title_cached(
            cache,
            TITLE,
            api_call=FakeRecognition(),
            now=NOW + FAILURE_RETRY_DELAYS[0] + timedelta(seconds=1),
        )

        entry = entry_of(cache)
        assert entry is not None
        assert entry['attempts'] == 0
        assert entry['next_retry_at'] is None


class TestCacheNeverBreaksRecognition:
    @pytest.mark.parametrize('response', [ok_response(), fail_response()])
    def test_a_broken_storage_does_not_block_the_call(self, response: dict[str, Any]) -> None:
        api = FakeRecognition(response)

        assert recognize_title_cached(BrokenStore(), TITLE, api_call=api, now=NOW) == response
        assert api.titles == [TITLE]

    def test_a_broken_api_is_not_remembered_as_a_failure(self) -> None:
        cache = FakeStore()

        def broken_api(title: str, status_only: bool = False) -> dict[str, Any]:
            raise RuntimeError('title_recognize is not available')

        with pytest.raises(RuntimeError):
            recognize_title_cached(cache, TITLE, api_call=broken_api, now=NOW)

        assert cache.items == {}

    def test_an_empty_title_is_not_stored(self) -> None:
        cache, api = FakeStore(), FakeRecognition()

        recognize_title_cached(cache, '   ', api_call=api, now=NOW)

        assert api.titles == ['   ']
        assert cache.items == {}


class TestCacheKeys:
    def test_the_status_only_answer_is_cached_separately(self) -> None:
        cache = FakeStore()
        recognize_title_cached(cache, TITLE, status_only=True, api_call=FakeRecognition(ok_response('НЖ')), now=NOW)

        full = FakeRecognition()
        assert recognize_title_cached(cache, TITLE, api_call=full, now=NOW) == ok_response()

        assert full.titles == [TITLE]
        assert entry_of(cache, TITLE, STATUS_ONLY) is not None

    def test_a_new_cache_version_forgets_the_stored_answers(self, monkeypatch) -> None:
        cache, api = FakeStore(), FakeRecognition()
        recognize_title_cached(cache, TITLE, api_call=api, now=NOW)

        monkeypatch.setattr(recognition_cache, 'CACHE_VERSION', recognition_cache.CACHE_VERSION + 1)
        recognize_title_cached(cache, TITLE, api_call=api, now=NOW)

        assert api.titles == [TITLE, TITLE]

    def test_an_entry_of_another_version_is_ignored(self) -> None:
        cache = FakeStore()
        cache.set_key_value_item(
            cache_key(TITLE, FULL),
            {
                'version': recognition_cache.CACHE_VERSION - 1,
                'status': 'ok',
                'response': ok_response(),
                'stored_at': NOW.isoformat(),
            },
        )

        assert recognition_cache.lookup(cache, TITLE, FULL, NOW) is None

    def test_storing_the_same_title_twice_keeps_one_row(self) -> None:
        cache = FakeStore()
        response = ok_response()
        store(cache, TITLE, FULL, response, now=NOW)
        store(cache, TITLE, FULL, response, now=NOW + timedelta(minutes=1))

        assert len(cache.items) == 1
