"""Настройка OpenTelemetry для доставки логов приложения в сервис Логи Selectel.

Приложение пишет логи в stdout и, если задан ``OTEL_EXPORTER_OTLP_ENDPOINT``,
дополнительно отправляет их по OTLP в общий OTel Collector ядра инфраструктуры
(``http://otel-collector:4317`` в сети ``data``). Коллектор пересылает записи в
сервис Логи Selectel — ключи Selectel приложению не нужны, их знает только
коллектор.

Обе переменные (``OTEL_EXPORTER_OTLP_ENDPOINT`` и ``OTEL_SERVICE_NAME``) уже
лежат в файле секретов проекта (``/srv/infra/secrets/<app>.env``, его создаёт
``make db-create`` в репозитории infra) — приложению остаётся их прочитать.
Имя сервиса задаёт стрим событий в сервисе Логи, поэтому его ставит само
приложение, а не коллектор.

Публичная точка входа — :func:`attach_otlp_handler`: её вызывают
``setup_logging_cloud`` (облачные функции) и ``setup_logging_to_console``
(локальный/докерный запуск бота). Без ``OTEL_EXPORTER_OTLP_ENDPOINT`` ничего не
происходит: логи остаются в stdout/stderr, как раньше.
"""

from __future__ import annotations

import logging
import os

from opentelemetry._logs import set_logger_provider
from opentelemetry.exporter.otlp.proto.grpc._log_exporter import OTLPLogExporter
from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler
from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
from opentelemetry.sdk.resources import Resource

#: Имя сервиса по умолчанию (стрим в сервисе Логи, если OTEL_SERVICE_NAME пуст).
DEFAULT_SERVICE_NAME = 'la-searcher-bot'

#: Env var с адресом OTLP-приёмника коллектора; её отсутствие выключает OTLP.
ENDPOINT_ENV_VAR = 'OTEL_EXPORTER_OTLP_ENDPOINT'


def configure_telemetry(endpoint: str, *, service_name: str) -> LoggerProvider:
    """Создать и сделать глобальным ``LoggerProvider``, пишущий логи в OTLP-эндпоинт.

    Args:
        endpoint: адрес OTLP-приёмника коллектора, например
            ``http://otel-collector:4317``. Схема ``http://`` трактуется как
            небезопасное (insecure) соединение.
        service_name: значение атрибута ресурса ``service.name``; коллектор
            использует его как имя стрима в сервисе Логи.

    Returns:
        Созданный провайдер, чтобы его можно было использовать в тестах; в
        приложении функция вызывается ради побочного эффекта —
        ``set_logger_provider``.
    """
    resource = Resource.create({'service.name': service_name})
    provider = LoggerProvider(resource=resource)
    provider.add_log_record_processor(BatchLogRecordProcessor(_build_exporter(endpoint)))
    set_logger_provider(provider)
    return provider


def attach_otlp_handler(root_logger: logging.Logger, level: int) -> bool:
    """Включить отправку логов в сервис Логи Selectel, если задан эндпоинт коллектора.

    Читает из окружения ``OTEL_EXPORTER_OTLP_ENDPOINT`` и ``OTEL_SERVICE_NAME``
    (последняя — с дефолтом :data:`DEFAULT_SERVICE_NAME`), настраивает провайдер
    через :func:`configure_telemetry` и вешает на ``root_logger``
    ``opentelemetry.sdk._logs.LoggingHandler`` — он пересылает записи в OTLP,
    не мешая обычным stdout/stderr-хендлерам.

    Args:
        root_logger: логгер, к которому добавляется OTLP-хендлер.
        level: минимальный уровень записей, попадающих в OTLP.

    Returns:
        ``True``, если OTLP-хендлер был добавлен; ``False``, если переменная
        окружения не задана (поведение логирования не меняется).
    """
    endpoint = os.environ.get(ENDPOINT_ENV_VAR, '').strip()
    if not endpoint:
        return False

    service_name = os.environ.get('OTEL_SERVICE_NAME', '').strip() or DEFAULT_SERVICE_NAME

    configure_telemetry(endpoint, service_name=service_name)
    root_logger.addHandler(LoggingHandler(level=level))

    # Внутренние логи OTel (в т.ч. ошибки экспорта) не должны возвращаться в root:
    # иначе при недоступном коллекторе они через OTLP-хендлер могли бы зациклиться.
    # Без propagate они уходят только в lastResort-хендлер (stderr, WARNING+).
    logging.getLogger('opentelemetry').propagate = False
    return True


def _build_exporter(endpoint: str) -> OTLPLogExporter:
    """Собрать OTLP-экспортер по адресу ``endpoint`` (без схемы, ``insecure`` для http)."""
    host = endpoint.removeprefix('https://').removeprefix('http://')
    return OTLPLogExporter(endpoint=host, insecure=endpoint.startswith('http://'))
