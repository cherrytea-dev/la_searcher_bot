"""Queue workers: claim a message from the queue and run the matching handler.

One thread per worker. Handlers are the untouched cloud functions, called with the same
``(event, context)`` signature they had in Yandex Cloud — see :mod:`app.dispatch`.
"""

from __future__ import annotations

import logging
import threading
import time

from _dependencies.common import queue_pg
from _dependencies.common.commons import get_app_config
from _dependencies.common.lock_manager import FunctionLockError
from app import status
from app.dispatch import build_event, resolve_handler

#: Sleep after a failed poll (the database may be restarting).
_POLL_ERROR_SLEEP_SECS = 5.0

#: How often the designated worker sweeps for messages left behind by a dead process.
_STALE_SWEEP_INTERVAL_SECS = 60.0

#: How long a worker is given to finish the message it is holding during shutdown.
_JOIN_TIMEOUT_SECS = 30.0


class QueueWorker(threading.Thread):
    """Pulls messages from ``pubsub_messages`` and calls the topic's handler."""

    def __init__(self, name: str, stop_event: threading.Event, *, sweep_stale: bool = False) -> None:
        super().__init__(name=name, daemon=True)
        self._stop_event = stop_event
        self._worker_id = f'{queue_pg.worker_id()}#{name}'
        self._sweep_stale = sweep_stale
        self._next_sweep = 0.0

    def run(self) -> None:
        status.set_status(self.name, 'running')
        logging.info('worker %s started (id=%s)', self.name, self._worker_id)

        while not self._stop_event.is_set():
            try:
                self._sweep_if_due()
                message = queue_pg.claim(None, self._worker_id)
            except Exception:
                logging.exception('worker %s: polling the queue failed', self.name)
                self._stop_event.wait(_POLL_ERROR_SLEEP_SECS)
                continue

            if message is None:
                self._stop_event.wait(get_app_config().worker_poll_interval_secs)
                continue

            self._process(message)

        status.set_status(self.name, 'stopped')
        logging.info('worker %s stopped', self.name)

    def stop(self) -> None:
        """Ask the worker to stop and wait for the message in flight (shutdown path)."""
        self._stop_event.set()
        self.join(timeout=_JOIN_TIMEOUT_SECS)

    def _process(self, message: queue_pg.QueuedMessage) -> None:
        config = get_app_config()
        started = time.monotonic()
        logging.info(
            'worker %s: message %s from %s (attempt %s)',
            self.name,
            message.id,
            message.topic,
            message.attempts,
        )

        try:
            handler = resolve_handler(message.topic)
        except KeyError as exc:
            logging.error('worker %s: %s', self.name, exc)
            queue_pg.mark_failed(
                message.id,
                str(exc),
                max_attempts=1,
                base_secs=config.queue_retry_base_secs,
                max_secs=config.queue_retry_max_secs,
            )
            return

        try:
            handler(build_event(message.payload), {})
        except FunctionLockError:
            # Not an error: another container instance is already running this function.
            # Put the message back without burning an attempt.
            logging.info('worker %s: message %s waits for the lock', self.name, message.id)
            queue_pg.release(message.id, delay_seconds=max(config.worker_poll_interval_secs * 5, 5.0))
            return
        except Exception as exc:
            logging.exception('worker %s: handler for topic %s failed', self.name, message.topic)
            queue_pg.mark_failed(
                message.id,
                f'{type(exc).__name__}: {exc}',
                max_attempts=config.queue_max_attempts,
                base_secs=config.queue_retry_base_secs,
                max_secs=config.queue_retry_max_secs,
            )
            return

        queue_pg.mark_done(message.id)
        logging.info(
            'worker %s: message %s (%s) done in %.1fs',
            self.name,
            message.id,
            message.topic,
            time.monotonic() - started,
        )

    def _sweep_if_due(self) -> None:
        if not self._sweep_stale:
            return

        now = time.monotonic()
        if now < self._next_sweep:
            return
        self._next_sweep = now + _STALE_SWEEP_INTERVAL_SECS

        config = get_app_config()
        queue_pg.requeue_stale(visibility_timeout_secs=config.queue_visibility_timeout_secs)
        purged = queue_pg.purge_finished(older_than_secs=config.queue_purge_after_secs)
        if purged:
            logging.info('housekeeping: removed %d finished message(s)', purged)


def start_workers(stop_event: threading.Event) -> list[QueueWorker]:
    """Start the configured number of workers (the first one also does housekeeping)."""
    count = max(1, get_app_config().worker_threads)
    workers = [QueueWorker(f'queue-worker-{index}', stop_event, sweep_stale=index == 0) for index in range(count)]
    for worker in workers:
        worker.start()
    return workers
