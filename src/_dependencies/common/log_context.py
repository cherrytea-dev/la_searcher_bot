"""Имя выполняемой функции в каждой записи лога — поле ``stream_name``.

В облаке у каждой функции был свой процесс, поэтому ``setup_logging_cloud`` могло
повесить на root-логгер один ``defaults={'stream_name': package_name}``: имя функции
совпадало с именем процесса. В едином контейнере (``python -m app.main``) процесс
один, а функций внутри — восемнадцать, и каждый ленивый импорт ``<function>.main``
перевешивал хендлер на своё имя: ``stream_name`` становился именем последней
импортированной функции.

Здесь имя вычисляется на каждую запись, а не на процесс:

1. :func:`log_stream` — контекст выполнения: точки входа (воркер очереди, cron-джоб,
   HTTP-запрос, цикл бота) знают, какую функцию вызывают, и ставят её имя на время
   вызова. Это работает и для записей из общего кода (``_dependencies.*``), которые
   иначе не знали бы, чьи они.
2. ``default`` — имя, переданное в ``setup_logging``: в облаке это ``package_name``
   функции, в контейнере — ``'app'`` (сам контейнер).
3. Имя логгера (первый компонент) — если ни контекста, ни default нет.

ContextVar, а не глобальная переменная: значение не протекает в новые потоки (у
каждого воркера, джоба и HTTP-запроса свой контекст), поэтому параллельные задачи не
перебивают друг другу имя. Исключение — ``ThreadPoolExecutor``: его рабочие потоки
контекст не наследуют, и такие записи падают на шаг 3.

Поле нужно обоим стокам: ``JsonFormatter`` рендерит его в stdout-JSON, а
``LoggingHandler`` OTel кладёт ``record.__dict__`` в атрибуты OTLP-записи. Поэтому
фильтр проставляет именно ``record.stream_name``.
"""

from __future__ import annotations

import logging
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Iterator

#: Имя выполняемой функции на время вызова — см. :func:`log_stream`.
_STREAM: ContextVar[str | None] = ContextVar('la_log_stream', default=None)


def current_stream() -> str | None:
    """Имя функции, установленное контекстом, или ``None``."""
    return _STREAM.get()


@contextmanager
def log_stream(name: str) -> Iterator[None]:
    """Пометить записи, сделанные внутри блока, именем функции ``name``."""
    token = _STREAM.set(name)
    try:
        yield
    finally:
        _STREAM.reset(token)


def stream_from_dotted(dotted: str) -> str:
    """Имя функции из точечного пути: ``'send_notifications.main.main'`` → ``'send_notifications'``."""
    return dotted.split('.', 1)[0]


def stream_for_record(record: logging.LogRecord, default: str | None) -> str:
    """Имя функции для записи: контекст → ``default`` → имя логгера."""
    return current_stream() or default or stream_from_dotted(record.name)


class StreamNameFilter(logging.Filter):
    """Проставляет ``record.stream_name`` (и никогда не отбрасывает запись)."""

    def __init__(self, default: str | None = None) -> None:
        super().__init__()
        self._default = default

    def filter(self, record: logging.LogRecord) -> bool:
        record.stream_name = stream_for_record(record, self._default)  # type: ignore[attr-defined]
        return True
