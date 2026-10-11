"""Cron scheduler for the single container (replaces the Yandex timer triggers).

Three jobs, matching ``terraform/_func_cron_trigger.tf``:

* ``check_first_posts`` — every minute;
* ``archive_to_bigquery`` — daily at 11:13;
* ``archive_notifications`` — hourly (it just publishes to its topic, as in the cloud).

Each job runs in its own thread and is protected by the same PostgreSQL advisory lock the
cloud functions use, so a second container (or an overlapping run) skips instead of doing the
work twice. The schedule is evaluated in ``SCHEDULER_TIMEZONE`` (UTC by default — that is what
the Yandex timers used).

The scheduler is only started in ``QUEUE_BACKEND=pg`` mode (see :mod:`app.main`): with ``ymq``
the cloud cron triggers are still alive, and a second ``check_first_posts`` every minute would
duplicate the parsing. The expressions are the classic five fields (``minute hour day month
weekday``); the Quartz-style six-field form used in terraform (``* * ? * * *``) is rejected at
startup on purpose — see ``CRON_CHECK_FIRST_POSTS`` in ``.env.example``.
"""

from __future__ import annotations

import importlib
import logging
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from _dependencies.common.commons import AppConfig, get_app_config, sqlalchemy_get_pool
from _dependencies.common.cron import CronExpression
from _dependencies.common.lock_manager import FunctionLockError, lock_manager
from _dependencies.common.pubsub import Topics, publish_to_pubsub
from app.status import StatusRegistry

_TICK_SECS = 1.0


@dataclass
class CronJob:
    """A scheduled job: either a direct call or a publish to a queue topic."""

    name: str
    expression: str
    target: str  # 'call:<module.path>' | 'queue:<topic>'
    cron: CronExpression = field(init=False)
    next_run: datetime | None = field(default=None, init=False)

    def __post_init__(self) -> None:
        self.cron = CronExpression(self.expression)


def default_jobs(config: AppConfig) -> list[CronJob]:
    """The jobs of the cloud deployment, expressed as cron entries."""
    return [
        CronJob('check_first_posts', config.cron_check_first_posts, 'call:check_first_posts_for_changes.main.main'),
        CronJob('archive_to_bigquery', config.cron_archive_to_bigquery, 'call:archive_to_bigquery.main.main'),
        CronJob(
            'archive_notifications',
            config.cron_archive_notifications,
            f'queue:{Topics.topic_to_archive_notifs.value}',
        ),
    ]


class CronScheduler(threading.Thread):
    """Fires :class:`CronJob` targets when their cron expression says so."""

    def __init__(self, stop_event: threading.Event, status: StatusRegistry, jobs: list[CronJob] | None = None) -> None:
        super().__init__(name='cron-scheduler', daemon=True)
        self._stop_event = stop_event
        self._status = status
        self._timezone = ZoneInfo(get_app_config().scheduler_timezone)
        self._jobs = jobs if jobs is not None else default_jobs(get_app_config())
        self._running: dict[str, threading.Thread] = {}

    def run(self) -> None:
        self._status.set_status('scheduler', 'running')
        now = datetime.now(self._timezone)
        for job in self._jobs:
            job.next_run = job.cron.next_after(now)
            logging.info('job %s: %r, next run %s', job.name, job.expression, job.next_run.isoformat())

        while not self._stop_event.is_set():
            moment = datetime.now(self._timezone)
            for job in self._jobs:
                if job.next_run is not None and moment >= job.next_run:
                    self._trigger(job)
                    job.next_run = job.cron.next_after(moment)
            self._stop_event.wait(_TICK_SECS)

        self._status.set_status('scheduler', 'stopped')
        logging.info('scheduler stopped')

    def stop(self) -> None:
        self._stop_event.set()
        self.join(timeout=5.0)

    def _trigger(self, job: CronJob) -> None:
        previous = self._running.get(job.name)
        if previous is not None and previous.is_alive():
            logging.warning('job %s is still running since the previous tick — skipping', job.name)
            return

        thread = threading.Thread(target=self._run_job, args=(job,), name=f'cron-{job.name}', daemon=True)
        self._running[job.name] = thread
        thread.start()

    def _run_job(self, job: CronJob) -> None:
        started = time.monotonic()
        try:
            with lock_manager(sqlalchemy_get_pool(), f'cron:{job.name}'):
                self._execute(job)
        except FunctionLockError:
            logging.info('job %s is already running elsewhere — skipped', job.name)
            return
        except Exception:
            logging.exception('job %s failed', job.name)
            return

        logging.info('job %s finished in %.1fs', job.name, time.monotonic() - started)

    @staticmethod
    def _execute(job: CronJob) -> None:
        logging.info('job %s started (target=%s)', job.name, job.target)

        if job.target.startswith('queue:'):
            topic = job.target.partition(':')[2]
            # Publish through the regular routing point, so the backend is decided in one place.
            publish_to_pubsub(topic, 'go')
            return

        target = job.target.partition(':')[2]
        module_name, _, attribute = target.rpartition('.')
        handler: Any = getattr(importlib.import_module(module_name), attribute)
        handler({}, {})
