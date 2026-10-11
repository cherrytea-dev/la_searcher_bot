"""HTTP endpoints of the single container — standard library only.

In the cloud the API gateway routed HTTP requests to separate functions. Here the same
functions are called in-process: the request is wrapped into the Yandex Cloud shape
(``{'httpMethod', 'body', 'headers', ...}``) and the ``{'statusCode', 'body', 'headers'}``
answer is turned back into an HTTP response. The functions themselves are untouched.

Routes:

* ``GET /health`` (alias ``/ready``) — probes for k8s, plus queue counters;
* ``POST <API_PATH_ACTIVE_SEARCHES>`` — ``api_get_active_searches`` (web app "Map");
* ``POST <API_PATH_USER_INFO>`` — ``user_provide_info`` (web app "Map");
* webhook paths for the bots — only if ``WEBHOOK_PATH_*`` is set (polling is the default).
"""

from __future__ import annotations

import asyncio
import importlib
import inspect
import json
import logging
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Awaitable, Callable
from urllib.parse import parse_qs, urlparse

from _dependencies.common import queue_pg
from _dependencies.common.commons import get_app_config
from app import status

_HEALTH_PATHS = {'/health', '/ready'}
_JSON_HEADERS = {'Content-Type': 'application/json'}


def _build_routes() -> dict[str, str]:
    """URL path → dotted path of the HTTP-shaped function's ``main``."""
    config = get_app_config()
    routes = {
        config.api_path_active_searches: 'api_get_active_searches.main.main',
        config.api_path_user_info: 'user_provide_info.main.main',
    }
    if config.webhook_path_telegram:
        routes[config.webhook_path_telegram] = 'communicate.main.main'
    if config.webhook_path_vk:
        routes[config.webhook_path_vk] = 'vk_bot.main.main'
    if config.webhook_path_max:
        routes[config.webhook_path_max] = 'max_bot.main.main'

    return {path.rstrip('/') or '/': target for path, target in routes.items() if path}


class _RequestHandler(BaseHTTPRequestHandler):
    """Translates HTTP requests into cloud-function calls."""

    server_version = 'la-searcher-bot'
    protocol_version = 'HTTP/1.1'
    routes: dict[str, str] = {}

    def do_GET(self) -> None:  # noqa: N802 - name required by BaseHTTPRequestHandler
        self._handle('GET')

    def do_HEAD(self) -> None:  # noqa: N802
        self._handle('HEAD')

    def do_POST(self) -> None:  # noqa: N802
        self._handle('POST')

    def do_OPTIONS(self) -> None:  # noqa: N802
        self._handle('OPTIONS')

    def log_message(self, fmt: str, *args: Any) -> None:
        logging.debug('%s %s', self.address_string(), fmt % args)

    def _handle(self, method: str) -> None:
        parsed = urlparse(self.path)
        path = parsed.path.rstrip('/') or '/'

        if path in _HEALTH_PATHS and method in {'GET', 'HEAD'}:
            self._respond_health()
            return

        target = self.routes.get(path)
        if target is None:
            self._respond(404, json.dumps({'error': 'not found', 'path': parsed.path}), _JSON_HEADERS)
            return

        try:
            request_data = {
                'httpMethod': method,
                'body': self._read_body(),
                'headers': dict(self.headers.items()),
                'queryStringParameters': {key: values[0] for key, values in parse_qs(parsed.query).items()},
                'path': parsed.path,
            }
            result = _call_function(target, request_data)
            self._respond(
                int(result.get('statusCode') or 200),
                str(result.get('body') or ''),
                {str(key): str(value) for key, value in dict(result.get('headers') or {}).items()},
            )
        except Exception:
            logging.exception('request %s %s failed', method, parsed.path)
            self._respond(500, json.dumps({'error': 'internal error'}), _JSON_HEADERS)

    def _respond_health(self) -> None:
        payload: dict[str, Any] = {'status': 'ok', **status.snapshot()}
        try:
            payload['queue'] = queue_pg.stats()
        except Exception as exc:
            payload['status'] = 'degraded'
            payload['queue_error'] = f'{type(exc).__name__}: {exc}'

        self._respond(200 if payload['status'] == 'ok' else 503, json.dumps(payload, ensure_ascii=False), _JSON_HEADERS)

    def _read_body(self) -> str:
        length = int(self.headers.get('Content-Length') or 0)
        if not length:
            return ''
        return self.rfile.read(length).decode('utf-8', errors='replace')

    def _respond(self, status_code: int, body: str, headers: dict[str, str]) -> None:
        payload = body.encode('utf-8')
        self.send_response(status_code)
        for key, value in headers.items():
            if key.lower() in {'content-length', 'transfer-encoding', 'connection'}:
                continue
            self.send_header(key, value)
        self.send_header('Content-Length', str(len(payload)))
        self.end_headers()
        if self.command != 'HEAD':
            self.wfile.write(payload)


def _call_function(target: str, request_data: dict[str, Any]) -> dict[str, Any]:
    """Import and call a cloud function entry point; await it when it is async."""
    module_name, _, attribute = target.rpartition('.')
    function: Callable[..., Any] = getattr(importlib.import_module(module_name), attribute)
    result = function(request_data)

    if inspect.isawaitable(result):
        # ``max_bot`` has an async entry point: the cloud runtime awaited it, we do the same.
        result = asyncio.run(_await_result(result))

    return dict(result)


async def _await_result(awaitable: Awaitable[Any]) -> Any:
    """Adapt any awaitable to a coroutine — ``asyncio.run`` accepts nothing else."""
    return await awaitable


def _handler_factory(routes: dict[str, str]) -> type[BaseHTTPRequestHandler]:
    class _BoundHandler(_RequestHandler):
        pass

    _BoundHandler.routes = routes
    return _BoundHandler


class HttpServer:
    """Threaded HTTP server running in its own thread."""

    def __init__(self, stop_event: threading.Event) -> None:
        self._stop_event = stop_event
        config = get_app_config()
        self._host = config.http_host
        self._port = config.http_port
        self._server = ThreadingHTTPServer((self._host, self._port), _handler_factory(_build_routes()))
        self._server.daemon_threads = True
        self._thread = threading.Thread(target=self._serve, name='http-server', daemon=True)

    def start(self) -> None:
        status.set_status('http', 'running')
        self._thread.start()

    def stop(self) -> None:
        self._server.shutdown()
        self._server.server_close()
        self._thread.join(timeout=5.0)
        status.set_status('http', 'stopped')

    def _serve(self) -> None:
        logging.info('HTTP server listening on %s:%s', self._host, self._port)
        try:
            self._server.serve_forever(poll_interval=0.5)
        except Exception:
            logging.exception('HTTP server crashed')
            status.set_status('http', 'error')
            return
        logging.info('HTTP server stopped')
