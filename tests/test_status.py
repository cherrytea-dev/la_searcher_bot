"""Tests for the runtime status registry (:mod:`app.status`)."""

from __future__ import annotations

import threading

from app.status import StatusRegistry


def test_snapshot_reports_components_and_uptime() -> None:
    registry = StatusRegistry()
    registry.set_status('http', 'running')
    registry.set_status('scheduler', 'stopped')

    snapshot = registry.snapshot()

    assert snapshot['components'] == {'http': 'running', 'scheduler': 'stopped'}
    assert snapshot['uptime_seconds'] >= 0


def test_two_registries_do_not_share_state() -> None:
    first = StatusRegistry()
    second = StatusRegistry()

    first.set_status('http', 'running')

    assert second.snapshot()['components'] == {}


def test_a_component_can_change_its_state() -> None:
    registry = StatusRegistry()
    registry.set_status('http', 'running')

    registry.set_status('http', 'stopped')

    assert registry.snapshot()['components'] == {'http': 'stopped'}


def test_concurrent_writes_are_not_lost() -> None:
    registry = StatusRegistry()

    def writer(index: int) -> None:
        registry.set_status(f'component-{index}', 'running')

    threads = [threading.Thread(target=writer, args=(index,)) for index in range(50)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert len(registry.snapshot()['components']) == 50
