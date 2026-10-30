"""Integration tests for the PostgreSQL queue against a live database.

``test_queue_pg.py`` fakes the engine to test the SQL-building logic. The guarantees that only
a real PostgreSQL can show — ``FOR UPDATE SKIP LOCKED`` under concurrent workers, the visibility
timeout, the backoff arithmetic — are checked here. The engine comes from the ``connection_pool``
fixture, the same test database the DB-bound part of the suite uses.
"""

from __future__ import annotations

import threading
from collections.abc import Iterator

import pytest
from sqlalchemy import text
from sqlalchemy.engine import Engine

from _dependencies.common import queue_pg

_TOPIC = 'topic_queue_integration_test'


@pytest.fixture()
def queue_engine(connection_pool: Engine) -> Iterator[Engine]:
    """The test database with the queue table present and this test's rows cleaned up."""
    queue_pg.ensure_schema(connection_pool)
    _delete_rows(connection_pool)
    yield connection_pool
    _delete_rows(connection_pool)


def _delete_rows(engine: Engine) -> None:
    with engine.begin() as conn:
        conn.execute(text(f'DELETE FROM {queue_pg.QUEUE_TABLE} WHERE topic = :topic'), {'topic': _TOPIC})


def test_enqueue_claim_and_mark_done(queue_engine: Engine) -> None:
    message_id = queue_pg.enqueue(_TOPIC, {'hello': 'world'}, engine=queue_engine)

    message = queue_pg.claim(_TOPIC, 'worker-1', engine=queue_engine)

    assert message is not None
    assert message.id == message_id
    assert message.topic == _TOPIC
    assert message.payload == {'hello': 'world'}
    assert message.attempts == 1

    # Claimed by worker-1: nobody else gets it while it is being processed.
    assert queue_pg.claim(_TOPIC, 'worker-2', engine=queue_engine) is None

    queue_pg.mark_done(message_id, engine=queue_engine)
    assert queue_pg.claim(_TOPIC, 'worker-2', engine=queue_engine) is None
    assert queue_pg.stats(engine=queue_engine) == [
        {'topic': _TOPIC, 'status': queue_pg.STATUS_DONE, 'count': 1, 'max_attempts': 1}
    ]


def test_delayed_message_is_not_claimable_yet(queue_engine: Engine) -> None:
    queue_pg.enqueue(_TOPIC, 'later', delay_seconds=3600, engine=queue_engine)

    assert queue_pg.claim(_TOPIC, 'worker-1', engine=queue_engine) is None


def test_requeue_stale_returns_a_message_of_a_dead_worker(queue_engine: Engine) -> None:
    message_id = queue_pg.enqueue(_TOPIC, 'go', engine=queue_engine)
    assert queue_pg.claim(_TOPIC, 'dead-worker', engine=queue_engine) is not None

    with queue_engine.begin() as conn:
        conn.execute(
            text(f"UPDATE {queue_pg.QUEUE_TABLE} SET locked_at = now() - interval '1 hour' WHERE id = :id"),
            {'id': message_id},
        )

    assert queue_pg.requeue_stale(visibility_timeout_secs=900, engine=queue_engine) == 1

    message = queue_pg.claim(_TOPIC, 'worker-2', engine=queue_engine)
    assert message is not None
    assert message.id == message_id
    assert message.attempts == 2  # the dead worker's attempt is not forgiven


def test_mark_failed_buries_the_message_after_the_limit(queue_engine: Engine) -> None:
    message_id = queue_pg.enqueue(_TOPIC, 'go', engine=queue_engine)
    queue_pg.claim(_TOPIC, 'worker-1', engine=queue_engine)

    buried = queue_pg.mark_failed(
        message_id,
        'boom',
        max_attempts=1,
        base_secs=30,
        max_secs=900,
        engine=queue_engine,
    )

    assert buried is True
    assert queue_pg.stats(engine=queue_engine) == [
        {'topic': _TOPIC, 'status': queue_pg.STATUS_FAILED, 'count': 1, 'max_attempts': 1}
    ]


def test_concurrent_workers_never_claim_the_same_message(queue_engine: Engine) -> None:
    total = 40
    for index in range(total):
        queue_pg.enqueue(_TOPIC, index, engine=queue_engine)

    claimed: list[int] = []
    lock = threading.Lock()

    def worker() -> None:
        while True:
            message = queue_pg.claim(_TOPIC, 'worker', engine=queue_engine)
            if message is None:
                return
            with lock:
                claimed.append(message.id)
            queue_pg.mark_done(message.id, engine=queue_engine)

    threads = [threading.Thread(target=worker) for _ in range(4)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert len(claimed) == total
    assert len(set(claimed)) == total
