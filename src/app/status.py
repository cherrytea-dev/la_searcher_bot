"""Shared runtime state — what the probes report.

The registry is created once in :func:`app.main.main` and handed to every component, so the
state belongs to the process that owns it instead of living in module-level globals (which a
test, or a second instance in the same interpreter, would share by accident).

Kept deliberately tiny: components write their state here, the HTTP server reads it. No locking
games, no metrics framework — with one container and a handful of threads a dict behind a lock
is enough.
"""

from __future__ import annotations

import threading
import time
from typing import Any


class StatusRegistry:
    """States of the running components, plus process uptime."""

    def __init__(self) -> None:
        self._started_at = time.monotonic()
        self._lock = threading.Lock()
        self._components: dict[str, str] = {}

    def set_status(self, component: str, state: str) -> None:
        """Record the state of a component (``starting``, ``running``, ``stopped``, ``error``)."""
        with self._lock:
            self._components[component] = state

    def snapshot(self) -> dict[str, Any]:
        """Everything the liveness probe needs in one dict."""
        with self._lock:
            components = dict(self._components)

        return {
            'uptime_seconds': round(time.monotonic() - self._started_at, 1),
            'components': components,
        }
