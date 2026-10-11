"""Tests for the HTTP layer of the single container (:mod:`app.http_server`)."""

from __future__ import annotations

import http.client
import json
import sys
import threading
import types
from typing import Any

import pytest

from app import http_server
from app.status import StatusRegistry


def _install_fake_module(monkeypatch: pytest.MonkeyPatch, name: str, main: Any) -> None:
    module = types.ModuleType(name)
    module.main = main  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, name, module)


def test_call_function_returns_the_cloud_response(monkeypatch: pytest.MonkeyPatch) -> None:
    def main(request_data: dict[str, Any]) -> dict[str, Any]:
        assert request_data['httpMethod'] == 'POST'
        return {'statusCode': 201, 'body': 'created', 'headers': {'X-Test': 'yes'}}

    _install_fake_module(monkeypatch, 'fake_sync_function', main)

    result = http_server._call_function('fake_sync_function.main', {'httpMethod': 'POST'}, http_server._AsyncRunner())

    assert result == {'statusCode': 201, 'body': 'created', 'headers': {'X-Test': 'yes'}}


def test_call_function_runs_async_entry_points_on_the_shared_loop(monkeypatch: pytest.MonkeyPatch) -> None:
    """``max_bot`` has an async ``main`` and its module state is bound to one loop — so we keep one."""

    async def main(request_data: dict[str, Any]) -> dict[str, Any]:
        return {'statusCode': 200, 'body': 'async ok', 'headers': {}}

    _install_fake_module(monkeypatch, 'fake_async_function', main)
    runner = http_server._AsyncRunner()
    try:
        result = http_server._call_function('fake_async_function.main', {'httpMethod': 'POST'}, runner)
    finally:
        runner.stop()

    assert result['body'] == 'async ok'


def test_routes_cover_the_web_app_and_only_configured_webhooks(monkeypatch: pytest.MonkeyPatch) -> None:
    config = types.SimpleNamespace(
        api_path_active_searches='/api/v1/active-searches',
        api_path_user_info='/api/v1/user-info',
        webhook_path_telegram='',
        webhook_path_vk='/webhook/vk',
        webhook_path_max='',
    )
    monkeypatch.setattr(http_server, 'get_app_config', lambda: config)

    routes = http_server._build_routes()

    assert routes == {
        '/api/v1/active-searches': 'api_get_active_searches.main.main',
        '/api/v1/user-info': 'user_provide_info.main.main',
        '/webhook/vk': 'vk_bot.main.main',
    }


def test_routes_normalize_trailing_slashes(monkeypatch: pytest.MonkeyPatch) -> None:
    config = types.SimpleNamespace(
        api_path_active_searches='/api/v1/active-searches/',
        api_path_user_info='',
        webhook_path_telegram='',
        webhook_path_vk='',
        webhook_path_max='',
    )
    monkeypatch.setattr(http_server, 'get_app_config', lambda: config)

    assert http_server._build_routes() == {'/api/v1/active-searches': 'api_get_active_searches.main.main'}


@pytest.fixture()
def running_server() -> Any:
    """A real server on a random port — the probes are checked end to end."""
    server = http_server._RouteServer(('127.0.0.1', 0), {}, StatusRegistry())
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5.0)


def _get(server: Any, path: str) -> tuple[int, dict[str, Any]]:
    connection = http.client.HTTPConnection(*server.server_address, timeout=5)
    try:
        connection.request('GET', path)
        response = connection.getresponse()
        return response.status, json.loads(response.read())
    finally:
        connection.close()


def test_health_is_liveness_and_ready_checks_the_queue(running_server: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(http_server.queue_pg, 'stats', lambda: [])

    status_code, body = _get(running_server, '/health')
    assert status_code == 200
    assert body['status'] == 'ok'
    assert 'uptime_seconds' in body
    assert 'queue' not in body  # liveness never touches the database

    status_code, body = _get(running_server, '/ready')
    assert status_code == 200
    assert body['queue'] == []


def test_readiness_reports_a_broken_database_while_liveness_stays_up(
    running_server: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    def broken() -> list[dict[str, Any]]:
        raise RuntimeError('database is down')

    monkeypatch.setattr(http_server.queue_pg, 'stats', broken)

    ready_code, ready_body = _get(running_server, '/ready')
    assert ready_code == 503
    assert ready_body['status'] == 'degraded'
    assert 'database is down' in ready_body['queue_error']

    health_code, health_body = _get(running_server, '/health')
    assert health_code == 200
    assert health_body['status'] == 'ok'
