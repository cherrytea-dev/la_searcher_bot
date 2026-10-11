"""PostgreSQL-backed message queue — a drop-in replacement for the Yandex Message Queue.

Why
---
The bot used to be ~18 Yandex Cloud Functions glued together by YMQ (SQS-compatible) topics.
Moving to a single container removes YMQ: the queue lives in the same PostgreSQL the rest of
the service already uses, so there is no extra broker to run and no extra dependency.

Design
------
* one table, ``pubsub_messages`` — the queue itself;
* publish = ``INSERT``; consume = ``UPDATE ... WHERE id = (SELECT ... FOR UPDATE SKIP LOCKED)``,
  which is safe with any number of workers;
* ``attempts`` grows on claim, so a message whose worker died is returned to the queue by
  :func:`requeue_stale` (visibility timeout) and can still be retried;
* failures use exponential backoff; after ``max_attempts`` the message goes to
  ``status='failed'`` (dead letter) instead of spinning forever.

The surface mirrors :mod:`_dependencies.common.yandex_tools` closely enough for
:mod:`_dependencies.common.pubsub` to switch backends by configuration
(``QUEUE_BACKEND=pg|ymq``).
"""

from __future__ import annotations

import logging
import os
import socket
from dataclasses import dataclass
from typing import Any

from pydantic_core import to_json
from sqlalchemy import text
from sqlalchemy.engine import Engine

from _dependencies.common.commons import get_app_config, sqlalchemy_get_pool

QUEUE_TABLE = 'pubsub_messages'

STATUS_PENDING = 'pending'
STATUS_PROCESSING = 'processing'
STATUS_DONE = 'done'
STATUS_FAILED = 'failed'

_DDL_STATEMENTS: tuple[str, ...] = (
    f"""
    CREATE TABLE IF NOT EXISTS {QUEUE_TABLE} (
        id            bigserial PRIMARY KEY,
        topic         text        NOT NULL,
        payload       jsonb       NOT NULL,
        status        text        NOT NULL DEFAULT '{STATUS_PENDING}',
        attempts      integer     NOT NULL DEFAULT 0,
        available_at  timestamptz NOT NULL DEFAULT now(),
        locked_at     timestamptz,
        locked_by     text,
        created_at    timestamptz NOT NULL DEFAULT now(),
        finished_at   timestamptz,
        last_error    text
    )
    """,
    f"""
    CREATE INDEX IF NOT EXISTS {QUEUE_TABLE}_poll_idx
        ON {QUEUE_TABLE} (topic, available_at, id)
        WHERE status = '{STATUS_PENDING}'
    """,
    f"""
    CREATE INDEX IF NOT EXISTS {QUEUE_TABLE}_stale_idx
        ON {QUEUE_TABLE} (locked_at)
        WHERE status = '{STATUS_PROCESSING}'
    """,
)


@dataclass(frozen=True)
class QueuedMessage:
    """A message claimed by a worker."""

    id: int
    topic: str
    payload: Any
    attempts: int


def worker_id() -> str:
    """Identify this process in ``locked_by`` (helps to find who took a stuck message)."""
    return get_app_config().worker_id or f'{socket.gethostname()}:{os.getpid()}'


def ensure_schema(engine: Engine | None = None) -> None:
    """Create the queue table and its indexes if they are not there yet (idempotent)."""
    engine = engine if engine is not None else sqlalchemy_get_pool()
    with engine.begin() as conn:
        for statement in _DDL_STATEMENTS:
            conn.execute(text(statement))
    logging.info('queue table %s is ready', QUEUE_TABLE)


def serialize(message: Any) -> str:
    """Serialize a pub/sub payload the same way the YMQ backend did."""
    return to_json(message).decode()


def enqueue(topic: str, message: Any, *, delay_seconds: float = 0.0, engine: Engine | None = None) -> int:
    """Publish ``message`` to ``topic``; returns the message id."""
    engine = engine if engine is not None else sqlalchemy_get_pool()
    stmt = text(
        f"""
        INSERT INTO {QUEUE_TABLE} (topic, payload, available_at)
        VALUES (:topic, (:payload)::jsonb, now() + make_interval(secs => :delay))
        RETURNING id
        """
    )
    with engine.begin() as conn:
        message_id = conn.execute(
            stmt,
            {'topic': topic, 'payload': serialize(message), 'delay': float(delay_seconds)},
        ).scalar()

    if message_id is None:  # INSERT ... RETURNING always yields a row; the guard is for the type checker
        raise RuntimeError(f'could not queue a message to {topic}: no id returned')

    logging.info('queued message %s to topic %s', message_id, topic)
    return int(message_id)


def claim(topic: str | None, worker: str, *, engine: Engine | None = None) -> QueuedMessage | None:
    """Take one pending message (of ``topic``, or any topic when ``topic`` is None).

    ``FOR UPDATE SKIP LOCKED`` makes concurrent workers skip each other's rows, so no
    message is handed out twice.
    """
    engine = engine if engine is not None else sqlalchemy_get_pool()
    topic_filter = 'topic = :topic AND' if topic else ''
    stmt = text(
        f"""
        UPDATE {QUEUE_TABLE}
        SET status = '{STATUS_PROCESSING}',
            locked_at = now(),
            locked_by = :worker,
            attempts = attempts + 1
        WHERE id = (
            SELECT id
            FROM {QUEUE_TABLE}
            WHERE {topic_filter} status = '{STATUS_PENDING}' AND available_at <= now()
            ORDER BY id
            LIMIT 1
            FOR UPDATE SKIP LOCKED
        )
        RETURNING id, topic, payload, attempts
        """
    )
    params: dict[str, Any] = {'worker': worker}
    if topic:
        params['topic'] = topic

    with engine.begin() as conn:
        row = conn.execute(stmt, params).first()

    if row is None:
        return None
    return QueuedMessage(id=int(row.id), topic=str(row.topic), payload=row.payload, attempts=int(row.attempts))


def mark_done(message_id: int, *, engine: Engine | None = None) -> None:
    """Mark a message as processed."""
    engine = engine if engine is not None else sqlalchemy_get_pool()
    with engine.begin() as conn:
        conn.execute(
            text(
                f"""
                UPDATE {QUEUE_TABLE}
                SET status = '{STATUS_DONE}', finished_at = now(), locked_at = NULL, locked_by = NULL
                WHERE id = :id
                """
            ),
            {'id': message_id},
        )


def release(message_id: int, *, delay_seconds: float = 5.0, engine: Engine | None = None) -> None:
    """Put a message back without counting it as a failed attempt.

    Used when the handler refused to run because a peer instance held the advisory lock
    (:class:`_dependencies.common.lock_manager.FunctionLockError`) — that is not an error,
    the message simply has to wait.
    """
    engine = engine if engine is not None else sqlalchemy_get_pool()
    with engine.begin() as conn:
        conn.execute(
            text(
                f"""
                UPDATE {QUEUE_TABLE}
                SET status = '{STATUS_PENDING}',
                    available_at = now() + make_interval(secs => :delay),
                    locked_at = NULL,
                    locked_by = NULL,
                    attempts = greatest(attempts - 1, 0)
                WHERE id = :id
                """
            ),
            {'id': message_id, 'delay': float(delay_seconds)},
        )


def mark_failed(
    message_id: int,
    error: str,
    *,
    max_attempts: int,
    base_secs: float,
    max_secs: float,
    engine: Engine | None = None,
) -> bool:
    """Record a failure; retry with backoff, or bury the message when attempts run out.

    Returns ``True`` when the message was buried (dead letter).
    """
    engine = engine if engine is not None else sqlalchemy_get_pool()
    stmt = text(
        f"""
        UPDATE {QUEUE_TABLE}
        SET status = CASE WHEN attempts >= :max_attempts THEN '{STATUS_FAILED}' ELSE '{STATUS_PENDING}' END,
            available_at = CASE
                WHEN attempts >= :max_attempts THEN available_at
                ELSE now() + make_interval(secs => least(:base_secs * power(2, attempts - 1), :max_secs))
            END,
            finished_at = CASE WHEN attempts >= :max_attempts THEN now() ELSE NULL END,
            locked_at = NULL,
            locked_by = NULL,
            last_error = :error
        WHERE id = :id
        RETURNING status
        """
    )
    with engine.begin() as conn:
        status = conn.execute(
            stmt,
            {
                'id': message_id,
                'error': error[:4000],
                'max_attempts': max_attempts,
                'base_secs': float(base_secs),
                'max_secs': float(max_secs),
            },
        ).scalar()

    buried = status == STATUS_FAILED
    if buried:
        logging.error('message %s buried after %s attempts: %s', message_id, max_attempts, error[:500])
    return buried


def requeue_stale(*, visibility_timeout_secs: float, engine: Engine | None = None) -> int:
    """Return messages of dead workers (``processing`` for too long) to the queue."""
    engine = engine if engine is not None else sqlalchemy_get_pool()
    stmt = text(
        f"""
        UPDATE {QUEUE_TABLE}
        SET status = '{STATUS_PENDING}',
            available_at = now(),
            locked_at = NULL,
            locked_by = NULL,
            last_error = 'visibility timeout: worker did not finish'
        WHERE status = '{STATUS_PROCESSING}'
          AND locked_at < now() - make_interval(secs => :timeout)
        RETURNING id
        """
    )
    with engine.begin() as conn:
        ids = [int(row.id) for row in conn.execute(stmt, {'timeout': float(visibility_timeout_secs)})]

    if ids:
        logging.warning('returned %d stuck message(s) to the queue: %s', len(ids), ids)
    return len(ids)


def stats(*, engine: Engine | None = None) -> list[dict[str, Any]]:
    """Counters per topic and status — for ``/health`` and for ops."""
    engine = engine if engine is not None else sqlalchemy_get_pool()
    with engine.begin() as conn:
        rows = conn.execute(
            text(
                f"""
                SELECT topic, status, count(*) AS messages, max(attempts) AS max_attempts
                FROM {QUEUE_TABLE}
                GROUP BY topic, status
                ORDER BY topic, status
                """
            )
        ).all()
    return [
        {
            'topic': str(row.topic),
            'status': str(row.status),
            'count': int(row.messages),
            'max_attempts': int(row.max_attempts),
        }
        for row in rows
    ]


def purge_finished(*, older_than_secs: float, engine: Engine | None = None) -> int:
    """Delete processed/buried messages older than the given age; returns the row count."""
    engine = engine if engine is not None else sqlalchemy_get_pool()
    stmt = text(
        f"""
        DELETE FROM {QUEUE_TABLE}
        WHERE status IN ('{STATUS_DONE}', '{STATUS_FAILED}')
          AND finished_at < now() - make_interval(secs => :age)
        """
    )
    with engine.begin() as conn:
        deleted = conn.execute(stmt, {'age': float(older_than_secs)}).rowcount
    return int(deleted or 0)
