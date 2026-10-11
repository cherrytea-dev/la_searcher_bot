"""Tests for the HTTP layer of the single container (:mod:`app.http_server`)."""

from __future__ import annotations

import sys
import types
from typing import Any

import pytest

from app import http_server


def _install_fake_module(monkeypatch: pytest.MonkeyPatch, name: str, main: Any) -> None:
    module = types.ModuleType(name)
    module.main = main  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, name, module)


def test_call_function_returns_the_cloud_response(monkeypatch: pytest.MonkeyPatch) -> None:
    def main(request_data: dict[str, Any]) -> dict[str, Any]:
        assert request_data['httpMethod'] == 'POST'
        return {'statusCode': 201, 'body': 'created', 'headers': {'X-Test': 'yes'}}

    _install_fake_module(monkeypatch, 'fake_sync_function', main)

    result = http_server._call_function('fake_sync_function.main', {'httpMethod': 'POST'})

    assert result == {'statusCode': 201, 'body': 'created', 'headers': {'X-Test': 'yes'}}


def test_call_function_awaits_async_entry_points(monkeypatch: pytest.MonkeyPatch) -> None:
    """``max_bot`` has an async ``main`` — the cloud runtime awaited it, so do we."""

    async def main(request_data: dict[str, Any]) -> dict[str, Any]:
        return {'statusCode': 200, 'body': 'async ok', 'headers': {}}

    _install_fake_module(monkeypatch, 'fake_async_function', main)

    result = http_server._call_function('fake_async_function.main', {'httpMethod': 'POST'})

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
