"""Unit tests for the PostgreSQL queue (:mod:`_dependencies.common.queue_pg`).

There is no live database here on purpose: the statements are PostgreSQL-specific
(``FOR UPDATE SKIP LOCKED``, ``make_interval``) and the DB-bound suite covers the rest of the
project. The engine is faked, so what is tested is the logic around the SQL — parameter
building, row mapping, and the retry/dead-letter decisions.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from pydantic import BaseModel

from _dependencies.common import queue_pg


class _Row:
    def __init__(self, **values: Any) -> None:
        self.__dict__.update(values)


class _FakeResult:
    def __init__(
        self,
        *,
        row: _Row | None = None,
        rows: tuple[_Row, ...] = (),
        scalar: Any = None,
        rowcount: int = 0,
    ) -> None:
        self._row = row
        self._rows = rows
        self._scalar = scalar
        self._rowcount = rowcount

    def first(self) -> _Row | None:
        return self._row

    def all(self) -> list[_Row]:
        return list(self._rows)

    def scalar(self) -> Any:
        return self._scalar

    def __iter__(self) -> Iterator[_Row]:
        return iter(self._rows)

    @property
    def rowcount(self) -> int:
        return self._rowcount


class _FakeConnection:
    def __init__(self, results: list[_FakeResult]) -> None:
        self.executed: list[tuple[str, dict[str, Any]]] = []
        self._results = list(results)

    def execute(self, statement: Any, params: dict[str, Any] | None = None) -> _FakeResult:
        self.executed.append((str(statement), params or {}))
        if self._results:
            return self._results.pop(0)
        return _FakeResult()


class _FakeEngine:
    def __init__(self, results: list[_FakeResult] | None = None) -> None:
        self.connection = _FakeConnection(results or [])

    @contextmanager
    def begin(self) -> Iterator[_FakeConnection]:
        yield self.connection


class _Payload(BaseModel):
    text: str
    triggered_by_func_id: int


def test_ensure_schema_creates_table_and_indexes() -> None:
    engine = _FakeEngine()

    queue_pg.ensure_schema(engine)  # type: ignore[arg-type]

    statements = [sql for sql, _ in engine.connection.executed]
    assert len(statements) == len(queue_pg._DDL_STATEMENTS)
    assert 'CREATE TABLE IF NOT EXISTS pubsub_messages' in statements[0]
    assert all('CREATE INDEX IF NOT EXISTS' in sql for sql in statements[1:])


def test_enqueue_serializes_the_payload_and_returns_the_id() -> None:
    engine = _FakeEngine([_FakeResult(scalar=42)])

    message_id = queue_pg.enqueue('topic_for_notification', {'a': 1}, engine=engine)  # type: ignore[arg-type]

    assert message_id == 42
    sql, params = engine.connection.executed[0]
    assert 'INSERT INTO pubsub_messages' in sql
    assert params['topic'] == 'topic_for_notification'
    assert json.loads(params['payload']) == {'a': 1}
    assert params['delay'] == 0.0


def test_enqueue_accepts_pydantic_payloads() -> None:
    engine = _FakeEngine([_FakeResult(scalar=7)])

    queue_pg.enqueue(
        'topic_to_send_notifications',
        _Payload(text='hello', triggered_by_func_id=1),
        engine=engine,  # type: ignore[arg-type]
    )

    _, params = engine.connection.executed[0]
    assert json.loads(params['payload']) == {'text': 'hello', 'triggered_by_func_id': 1}


def test_claim_maps_the_row() -> None:
    engine = _FakeEngine([_FakeResult(row=_Row(id=5, topic='topic_notify_admin', payload={'x': 1}, attempts=3))])

    message = queue_pg.claim(None, 'worker-1', engine=engine)  # type: ignore[arg-type]

    assert message == queue_pg.QueuedMessage(id=5, topic='topic_notify_admin', payload={'x': 1}, attempts=3)
    sql, params = engine.connection.executed[0]
    assert 'FOR UPDATE SKIP LOCKED' in sql
    assert params['worker'] == 'worker-1'
    assert 'topic = :topic' not in sql


def test_claim_with_topic_filters_by_it() -> None:
    engine = _FakeEngine([_FakeResult()])

    assert queue_pg.claim('topic_for_notification', 'worker-1', engine=engine) is None  # type: ignore[arg-type]

    sql, params = engine.connection.executed[0]
    assert 'topic = :topic AND' in sql
    assert params['topic'] == 'topic_for_notification'


def test_mark_failed_retries_before_the_limit() -> None:
    engine = _FakeEngine([_FakeResult(scalar=queue_pg.STATUS_PENDING)])

    buried = queue_pg.mark_failed(
        5,
        'boom',
        max_attempts=5,
        base_secs=30,
        max_secs=900,
        engine=engine,  # type: ignore[arg-type]
    )

    assert buried is False
    _, params = engine.connection.executed[0]
    assert params['max_attempts'] == 5
    assert params['base_secs'] == 30.0


def test_mark_failed_buries_after_the_limit() -> None:
    engine = _FakeEngine([_FakeResult(scalar=queue_pg.STATUS_FAILED)])

    buried = queue_pg.mark_failed(
        5,
        'boom',
        max_attempts=5,
        base_secs=30,
        max_secs=900,
        engine=engine,  # type: ignore[arg-type]
    )

    assert buried is True


def test_mark_done_and_release_keep_the_message_traceable() -> None:
    engine = _FakeEngine()

    queue_pg.mark_done(5, engine=engine)  # type: ignore[arg-type]
    queue_pg.release(6, delay_seconds=15, engine=engine)  # type: ignore[arg-type]

    done_sql, done_params = engine.connection.executed[0]
    release_sql, release_params = engine.connection.executed[1]

    assert f"status = '{queue_pg.STATUS_DONE}'" in done_sql
    assert done_params == {'id': 5}
    assert f"status = '{queue_pg.STATUS_PENDING}'" in release_sql
    assert 'attempts = greatest(attempts - 1, 0)' in release_sql
    assert release_params == {'id': 6, 'delay': 15.0}


def test_requeue_stale_counts_the_returned_messages() -> None:
    engine = _FakeEngine([_FakeResult(rows=(_Row(id=1), _Row(id=2)))])

    returned = queue_pg.requeue_stale(visibility_timeout_secs=900, engine=engine)  # type: ignore[arg-type]

    assert returned == 2
    sql, params = engine.connection.executed[0]
    assert 'visibility timeout' in sql
    assert params['timeout'] == 900.0


def test_stats_maps_rows_to_dicts() -> None:
    engine = _FakeEngine([_FakeResult(rows=(_Row(topic='t', status='pending', messages=3, max_attempts=1),))])

    assert queue_pg.stats(engine=engine) == [  # type: ignore[arg-type]
        {'topic': 't', 'status': 'pending', 'count': 3, 'max_attempts': 1}
    ]


def test_purge_finished_reports_the_deleted_rows() -> None:
    engine = _FakeEngine([_FakeResult(rowcount=4)])

    assert queue_pg.purge_finished(older_than_secs=3600, engine=engine) == 4  # type: ignore[arg-type]


def test_serialize_matches_the_legacy_json_format() -> None:
    assert json.loads(queue_pg.serialize(_Payload(text='hi', triggered_by_func_id=2))) == {
        'text': 'hi',
        'triggered_by_func_id': 2,
    }
