"""Tests for the bot poller supervisor (:mod:`app.bots`)."""

from __future__ import annotations

import threading
import types

import pytest

from app import bots
from app.status import StatusRegistry


def _config(**overrides: object) -> types.SimpleNamespace:
    base: dict[str, object] = {
        'enable_tg_bot': True,
        'enable_vk_bot': True,
        'enable_max_bot': True,
        'webhook_path_telegram': '',
        'webhook_path_vk': '',
        'webhook_path_max': '',
    }
    base.update(overrides)
    return types.SimpleNamespace(**base)


def _started_bots(monkeypatch: pytest.MonkeyPatch, config: types.SimpleNamespace) -> list[str]:
    monkeypatch.setattr(bots, 'get_app_config', lambda: config)
    started: list[str] = []
    monkeypatch.setattr(bots, '_supervise', lambda name, stop, status, runner: started.append(name))

    threads = bots.start_bots(threading.Event(), StatusRegistry())
    for thread in threads:
        thread.join(timeout=5.0)

    return sorted(started)


def test_start_bots_polls_every_enabled_bot_without_webhooks(monkeypatch: pytest.MonkeyPatch) -> None:
    assert _started_bots(monkeypatch, _config()) == ['max-bot', 'telegram-bot', 'vk-bot']


def test_start_bots_skips_a_bot_with_a_configured_webhook(monkeypatch: pytest.MonkeyPatch) -> None:
    """A served webhook must replace the poller — otherwise events are processed twice (or 409)."""
    config = _config(webhook_path_vk='/webhook/vk', webhook_path_max='/webhook/max')

    assert _started_bots(monkeypatch, config) == ['telegram-bot']


def test_start_bots_skips_disabled_bots(monkeypatch: pytest.MonkeyPatch) -> None:
    assert _started_bots(monkeypatch, _config(enable_tg_bot=False, enable_max_bot=False)) == ['vk-bot']
