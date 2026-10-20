"""Unit tests for the per-record ``stream_name`` (``_dependencies.common.log_context``).

In the cloud each function had its own process, so one ``stream_name`` default per process
was enough. The single container runs all the functions in one process: the name has to be
decided per record — see the module docstring of ``log_context``.
"""

from __future__ import annotations

import io
import json
import logging
import os
import sys
import threading
from contextlib import contextmanager
from typing import Iterator
from unittest.mock import patch

from _dependencies.common.log_context import (
    StreamNameFilter,
    current_stream,
    log_stream,
    stream_for_record,
    stream_from_dotted,
)
from _dependencies.common.pubsub import Topics
from _dependencies.common.yandex_tools import setup_logging_cloud
from app.dispatch import stream_for_topic


def _record(logger_name: str = 'send_notifications.main') -> logging.LogRecord:
    return logging.LogRecord(
        name=logger_name, level=logging.INFO, pathname=__file__, lineno=1, msg='hello', args=(), exc_info=None
    )


@contextmanager
def _fresh_root_logging() -> Iterator[None]:
    """Configure the root logger from scratch and restore its state afterwards."""
    root = logging.getLogger()
    saved_handlers = root.handlers[:]
    saved_level = root.level
    saved_flag = root.__dict__.pop('_la_logging_configured', None)
    try:
        with patch.dict(os.environ, {'OTEL_EXPORTER_OTLP_ENDPOINT': ''}):
            yield
    finally:
        root.handlers[:] = saved_handlers
        root.setLevel(saved_level)
        root.__dict__.pop('_la_logging_configured', None)
        if saved_flag is not None:
            root.__dict__['_la_logging_configured'] = saved_flag


def test_context_wins_over_default_and_logger_name() -> None:
    record = _record('_dependencies.common.db_client')

    assert stream_for_record(record, 'app') == 'app'
    with log_stream('send_notifications'):
        assert stream_for_record(record, 'app') == 'send_notifications'


def test_default_wins_over_logger_name() -> None:
    record = _record('_dependencies.common.db_client')

    assert stream_for_record(record, None) == '_dependencies'


def test_nested_stream_restores_the_outer_one() -> None:
    with log_stream('app'):
        with log_stream('send_notifications'):
            assert current_stream() == 'send_notifications'
        assert current_stream() == 'app'


def test_context_does_not_leak_into_another_thread() -> None:
    seen: list[str | None] = []

    with log_stream('send_notifications'):
        thread = threading.Thread(target=lambda: seen.append(current_stream()))
        thread.start()
        thread.join()

    assert seen == [None]


def test_stream_from_dotted_takes_the_package() -> None:
    assert stream_from_dotted('send_notifications.main.main') == 'send_notifications'
    assert stream_from_dotted('communicate') == 'communicate'


def test_filter_stamps_the_record_and_never_drops_it() -> None:
    record = _record()

    assert StreamNameFilter('app').filter(record) is True
    assert record.stream_name == 'app'


def test_json_log_gets_the_stream_name_of_the_running_function() -> None:
    buffer = io.StringIO()

    with _fresh_root_logging(), patch.object(sys, 'stdout', buffer):
        setup_logging_cloud('app')
        logging.getLogger().setLevel(logging.INFO)
        with log_stream('send_notifications'):
            logging.getLogger('_dependencies.common.db_client').info('hello')

    payload = json.loads(buffer.getvalue().strip())
    assert payload['stream_name'] == 'send_notifications'
    assert payload['name'] == '_dependencies.common.db_client'
    assert payload['message'] == 'hello'


def test_setup_logging_cloud_keeps_the_first_configuration() -> None:
    """A lazily imported function must not re-hang the root handler (see ``log_context``)."""
    with _fresh_root_logging():
        setup_logging_cloud('app')
        handlers = logging.getLogger().handlers[:]

        setup_logging_cloud('send_notifications')

        assert logging.getLogger().handlers == handlers


def test_stream_for_topic_maps_a_topic_to_its_function() -> None:
    assert stream_for_topic(Topics.topic_to_send_notifications.value) == 'send_notifications'
    assert stream_for_topic('no-such-topic') == 'unknown'
