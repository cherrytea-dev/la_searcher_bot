"""Tests for the queue workers (:mod:`app.queue_worker`).

The handlers themselves are covered by the rest of the suite; here the question is what the
worker does with the outcome — mark done, retry, bury, or put back when a peer holds the lock.
"""

from __future__ import annotations

import threading
from typing import Any

import pytest

from _dependencies.common import queue_pg
from _dependencies.common.lock_manager import FunctionLockError
from app import queue_worker as worker_module
from app.queue_worker import QueueWorker
from app.status import StatusRegistry


@pytest.fixture
def worker() -> QueueWorker:
    return QueueWorker('test-worker', threading.Event(), StatusRegistry())


@pytest.fixture
def recorded(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, Any]]:
    calls: list[tuple[str, Any]] = []

    monkeypatch.setattr(worker_module.queue_pg, 'mark_done', lambda message_id: calls.append(('done', message_id)))
    monkeypatch.setattr(
        worker_module.queue_pg, 'release', lambda message_id, **kwargs: calls.append(('release', message_id))
    )
    monkeypatch.setattr(
        worker_module.queue_pg,
        'mark_failed',
        lambda message_id, error, **kwargs: calls.append(('failed', message_id, error, kwargs)),
    )
    return calls


def _message(topic: str = 'topic_notify_admin') -> queue_pg.QueuedMessage:
    return queue_pg.QueuedMessage(id=1, topic=topic, payload={'a': 1}, attempts=1)


def test_successful_handler_marks_the_message_done(
    worker: QueueWorker, recorded: list[tuple[str, Any]], monkeypatch: pytest.MonkeyPatch
) -> None:
    seen: list[tuple[str, dict[str, Any]]] = []

    def handler(event: dict[str, Any], context: dict[str, Any]) -> None:
        seen.append((event['messages'][0]['details']['message']['body'], context))

    monkeypatch.setattr(worker_module, 'resolve_handler', lambda topic: handler)

    worker._process(_message())

    assert seen and seen[0][0] == '{"a": 1}'
    assert recorded == [('done', 1)]


def test_failing_handler_is_retried_with_the_configured_policy(
    worker: QueueWorker, recorded: list[tuple[str, Any]], monkeypatch: pytest.MonkeyPatch
) -> None:
    def handler(event: dict[str, Any], context: dict[str, Any]) -> None:
        raise RuntimeError('forum is down')

    monkeypatch.setattr(worker_module, 'resolve_handler', lambda topic: handler)

    worker._process(_message())

    assert recorded[0][0] == 'failed'
    assert recorded[0][1] == 1
    assert 'forum is down' in recorded[0][2]
    assert recorded[0][3]['max_attempts'] == worker_module.get_app_config().queue_max_attempts


def test_handler_waiting_for_a_peer_lock_releases_the_message(
    worker: QueueWorker, recorded: list[tuple[str, Any]], monkeypatch: pytest.MonkeyPatch
) -> None:
    def handler(event: dict[str, Any], context: dict[str, Any]) -> None:
        raise FunctionLockError()

    monkeypatch.setattr(worker_module, 'resolve_handler', lambda topic: handler)

    worker._process(_message())

    assert recorded == [('release', 1)]


def test_unknown_topic_is_buried_immediately(
    worker: QueueWorker, recorded: list[tuple[str, Any]], monkeypatch: pytest.MonkeyPatch
) -> None:
    def resolve(topic: str) -> Any:
        raise KeyError(f'no handler for {topic}')

    monkeypatch.setattr(worker_module, 'resolve_handler', resolve)

    worker._process(_message('topic_from_the_future'))

    assert recorded[0][0] == 'failed'
    assert recorded[0][3]['max_attempts'] == 1
