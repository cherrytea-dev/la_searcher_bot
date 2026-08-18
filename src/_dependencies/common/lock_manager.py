"""PostgreSQL advisory-lock based mutual exclusion for cloud functions."""

import logging
from contextlib import contextmanager
from typing import Iterator

from sqlalchemy import text
from sqlalchemy.engine import Engine

logger = logging.getLogger(__name__)


class FunctionLockError(Exception):
    """Raised when another instance of the same function is already running."""


@contextmanager
def lock_manager(engine: Engine, func_name: str) -> Iterator[None]:
    """Prevent parallel execution of the same cloud function.

    Uses a session-scoped PostgreSQL advisory lock keyed by a hash of
    ``func_name``. The lock is acquired with ``pg_try_advisory_lock``
    (non-blocking): if it is already held by another connection,
    ``FunctionLockError`` is raised immediately.

    Advisory locks are released automatically by the server when the
    connection closes — including on process crash — so there is no
    stale-lock problem and no need for a timeout, unlike the previous
    table-based ``functions_registry`` approach.
    """
    conn = engine.connect()
    acquired = conn.execute(
        text('SELECT pg_try_advisory_lock(hashtextextended(:func_name, 0))'),
        {'func_name': func_name},
    ).scalar()

    if not acquired:
        conn.close()
        logger.warning('Lock failed: another function is in progress')
        raise FunctionLockError()

    logger.info(f'Lock for function {func_name} is acquired')
    try:
        yield None
    finally:
        conn.execute(
            text('SELECT pg_advisory_unlock(hashtextextended(:func_name, 0))'),
            {'func_name': func_name},
        )
        conn.close()
        logger.info(f'Lock for function {func_name} is released')
