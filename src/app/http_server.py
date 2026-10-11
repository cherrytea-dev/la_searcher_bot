"""HTTP endpoints of the single container — standard library only.

In the cloud the API gateway routed HTTP requests to separate functions. Here the same
functions are called in-process: the request is wrapped into the Yandex Cloud shape
(``{'httpMethod', 'body', 'headers', ...}``) and the ``{'statusCode', 'body', 'headers'}``
answer is turned back into an HTTP response. The functions themselves are untouched.

Routes:

* ``GET /health`` — liveness: the process is up (never touches the database);
* ``GET /ready`` — readiness: the queue in PostgreSQL answers;
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
from typing import Any, Awaitable, Callable, Sequence, cast
from urllib.parse import parse_qs, urlparse

from _dependencies.common import queue_pg
from _dependencies.common.commons import get_app_config
from app.status import StatusRegistry

_HEALTH_PATHS = {'/health'}
_READY_PATHS = {'/ready'}
_JSON_HEADERS = {'Content-Type': 'application/json'}

#: Cap on concurrent request handlers: a burst (or slow clients) cannot spawn threads forever.
_MAX_HANDLER_THREADS = 32

#: Socket timeout of a connection (seconds) — a stalled client does not hold a thread forever.
_REQUEST_TIMEOUT_SECS = 30.0


def _serialize_header(value: str | Sequence[str]) -> str:
    """Render a response header value as a string; sequence values become comma-separated tokens."""
    return value if isinstance(value, str) else ', '.join(map(str, value))


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


class _AsyncRunner:
    """One event loop, in its own thread, shared by every async entry point (``max_bot``).

    ``max_bot`` builds its ``Bot``/``Dispatcher`` and the ``aiohttp`` session once at module
    level, bound to the loop that first uses them. A fresh loop per request (``asyncio.run``)
    would break the second request, so all async calls share this loop — the same way the cloud
    runtime kept one loop across warm invocations.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None

    def run(self, awaitable: Awaitable[Any]) -> Any:
        """Run ``awaitable`` on the shared loop and return its result."""
        return asyncio.run_coroutine_threadsafe(_await_result(awaitable), self._ensure_loop()).result()

    def _ensure_loop(self) -> asyncio.AbstractEventLoop:
        with self._lock:
            if self._loop is None or self._loop.is_closed():
                self._loop = asyncio.new_event_loop()
                self._thread = threading.Thread(target=self._run, args=(self._loop,), name='http-async', daemon=True)
                self._thread.start()
            return self._loop

    @staticmethod
    def _run(loop: asyncio.AbstractEventLoop) -> None:
        asyncio.set_event_loop(loop)
        loop.run_forever()

    def stop(self) -> None:
        loop = self._loop
        if loop is not None and not loop.is_closed():
            loop.call_soon_threadsafe(loop.stop)
        if self._thread is not None:
            self._thread.join(timeout=5.0)


async def _await_result(awaitable: Awaitable[Any]) -> Any:
    """Adapt any awaitable to a coroutine — ``run_coroutine_threadsafe`` accepts nothing else."""
    return await awaitable


class _RouteServer(ThreadingHTTPServer):
    """``ThreadingHTTPServer`` that carries the route table, the status registry and the cap.

    The routes live on the server (not as a class attribute of the handler) so that a test can
    build a server with its own table without mutating a shared class.
    """

    daemon_threads = True

    def __init__(self, address: tuple[str, int], routes: dict[str, str], status: StatusRegistry) -> None:
        self.routes = routes
        self.status = status
        self.async_runner = _AsyncRunner()
        self._slots = threading.BoundedSemaphore(_MAX_HANDLER_THREADS)
        super().__init__(address, _RequestHandler)

    def process_request(self, request: Any, client_address: Any) -> None:
        # Block the accept loop once saturated: the OS listen backlog holds the extra connections.
        self._slots.acquire()
        try:
            super().process_request(request, client_address)
        except Exception:
            self._slots.release()
            raise

    def process_request_thread(self, request: Any, client_address: Any) -> None:
        try:
            super().process_request_thread(request, client_address)
        finally:
            self._slots.release()

    def server_close(self) -> None:
        self.async_runner.stop()
        super().server_close()


class _RequestHandler(BaseHTTPRequestHandler):
    """Translates HTTP requests into cloud-function calls."""

    server_version = 'la-searcher-bot'
    protocol_version = 'HTTP/1.1'
    timeout = _REQUEST_TIMEOUT_SECS

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

    @property
    def _server(self) -> _RouteServer:
        return cast(_RouteServer, self.server)

    def _handle(self, method: str) -> None:
        parsed = urlparse(self.path)
        path = parsed.path.rstrip('/') or '/'

        if method in {'GET', 'HEAD'} and path in _HEALTH_PATHS:
            self._respond_liveness()
            return
        if method in {'GET', 'HEAD'} and path in _READY_PATHS:
            self._respond_readiness()
            return

        target = self._server.routes.get(path)
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
            result = _call_function(target, request_data, self._server.async_runner)
            self._respond(
                int(result.get('statusCode') or 200),
                str(result.get('body') or ''),
                {str(key): _serialize_header(value) for key, value in dict(result.get('headers') or {}).items()},
            )
        except Exception:
            logging.exception('request %s %s failed', method, parsed.path)
            self._respond(500, json.dumps({'error': 'internal error'}), _JSON_HEADERS)

    def _respond_liveness(self) -> None:
        """Liveness: the process is alive. Deliberately independent of the database."""
        payload: dict[str, Any] = {'status': 'ok', **self._server.status.snapshot()}
        self._respond(200, json.dumps(payload, ensure_ascii=False), _JSON_HEADERS)

    def _respond_readiness(self) -> None:
        """Readiness: the queue in PostgreSQL answers. A 503 keeps k8s from routing traffic here."""
        payload: dict[str, Any] = {'status': 'ok'}
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


def _call_function(target: str, request_data: dict[str, Any], async_runner: _AsyncRunner) -> dict[str, Any]:
    """Import and call a cloud function entry point; run it on the shared loop when it is async."""
    module_name, _, attribute = target.rpartition('.')
    function: Callable[..., Any] = getattr(importlib.import_module(module_name), attribute)
    result = function(request_data)

    if inspect.isawaitable(result):
        result = async_runner.run(result)

    return dict(result)


class HttpServer:
    """Threaded HTTP server running in its own thread."""

    def __init__(self, stop_event: threading.Event, status: StatusRegistry) -> None:
        self._stop_event = stop_event
        self._status = status
        config = get_app_config()
        self._host = config.http_host
        self._port = config.http_port
        self._server = _RouteServer((self._host, self._port), _build_routes(), status)
        self._thread = threading.Thread(target=self._serve, name='http-server', daemon=True)

    def start(self) -> None:
        self._status.set_status('http', 'running')
        self._thread.start()

    def stop(self) -> None:
        self._server.shutdown()
        self._server.server_close()
        self._thread.join(timeout=5.0)
        self._status.set_status('http', 'stopped')

    def _serve(self) -> None:
        logging.info('HTTP server listening on %s:%s', self._host, self._port)
        try:
            self._server.serve_forever(poll_interval=0.5)
        except Exception:
            logging.exception('HTTP server crashed')
            self._status.set_status('http', 'error')
            return
        logging.info('HTTP server stopped')
