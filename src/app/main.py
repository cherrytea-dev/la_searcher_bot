"""Single-container entry point: HTTP + cron scheduler + queue workers + bot pollers.

    python -m app.main                 # run everything
    python -m app.main --check-config  # validate the configuration and exit

Startup order matters: the queue table is created first, then the HTTP server (so that
``/health`` answers while the rest warms up), then the scheduler, the workers and the bots.
On ``SIGTERM`` (what k8s sends) the container stops in the reverse order and gives the worker
threads a moment to finish the message they hold.
"""

from __future__ import annotations

import argparse
import logging
import signal
import threading
import time
from types import FrameType
from typing import Any

from _dependencies.common import queue_pg
from _dependencies.common.commons import AppConfig, get_app_config, setup_logging
from app import bots, status
from app.http_server import HttpServer
from app.queue_worker import start_workers
from app.scheduler import CronScheduler, default_jobs

setup_logging('app')

#: Grace period for the components during shutdown (seconds).
_SHUTDOWN_GRACE_SECS = 30.0


def _log_startup(config: AppConfig) -> None:
    logging.info(
        'single container starting: queue_backend=%s workers=%s scheduler=%s http=%s:%s bots(tg/vk/max)=%s/%s/%s '
        'title_recognize_local=%s',
        config.queue_backend,
        config.worker_threads,
        config.scheduler_enabled,
        config.http_host,
        config.http_port,
        config.enable_tg_bot,
        config.enable_vk_bot,
        config.enable_max_bot,
        config.title_recognize_local,
    )


def _install_signal_handlers(stop_event: threading.Event) -> None:
    def _handle(signum: int, _frame: FrameType | None) -> None:
        logging.info('signal %s received: shutting down', signum)
        stop_event.set()

    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, _handle)


def main() -> int:
    parser = argparse.ArgumentParser(prog='app.main', description='la_searcher_bot in a single container')
    parser.add_argument('--check-config', action='store_true', help='validate the configuration and exit')
    args = parser.parse_args()

    config = get_app_config()
    _log_startup(config)

    if args.check_config:
        jobs = ', '.join(f'{job.name}={job.expression}' for job in default_jobs(config))
        logging.info('configuration is valid; jobs: %s', jobs)
        return 0

    stop_event = threading.Event()
    _install_signal_handlers(stop_event)

    components: list[Any] = []

    if config.queue_backend == 'pg':
        queue_pg.ensure_schema()
    else:
        logging.warning(
            'QUEUE_BACKEND=%s: queue workers are not started — messages arrive through the YMQ triggers',
            config.queue_backend,
        )

    if config.http_enabled:
        http = HttpServer(stop_event)
        http.start()
        components.append(http)

    if config.scheduler_enabled:
        scheduler = CronScheduler(stop_event)
        scheduler.start()
        components.append(scheduler)

    if config.queue_backend == 'pg':
        components.extend(start_workers(stop_event))

    components.extend(bots.start_bots(stop_event))

    status.set_status('container', 'running')
    logging.info('single container is up (%d components)', len(components))

    try:
        while not stop_event.is_set():
            time.sleep(0.5)
    except KeyboardInterrupt:
        stop_event.set()

    return _shutdown(components)


def _shutdown(components: list[Any]) -> int:
    status.set_status('container', 'stopping')
    logging.info('shutting down %d components', len(components))

    deadline = time.monotonic() + _SHUTDOWN_GRACE_SECS
    for component in reversed(components):
        try:
            if hasattr(component, 'stop'):
                component.stop()
            elif isinstance(component, threading.Thread):
                component.join(timeout=max(0.0, deadline - time.monotonic()))
        except Exception:
            logging.exception('stopping %s failed', component)

    status.set_status('container', 'stopped')
    logging.info('single container stopped')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
