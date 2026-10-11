"""Shared runtime state — what the ``/health`` endpoint reports.

Kept deliberately tiny: components write their state here, the HTTP server reads it. No
locking games, no metrics framework — with one container and a handful of threads a dict
behind a lock is enough.
"""

from __future__ import annotations

import threading
import time
from typing import Any

_started_at = time.monotonic()
_lock = threading.Lock()
_components: dict[str, str] = {}


def set_status(component: str, state: str) -> None:
    """Record the state of a component (``starting``, ``running``, ``stopped``, ``error``)."""
    with _lock:
        _components[component] = state


def snapshot() -> dict[str, Any]:
    """Everything ``/health`` needs in one dict."""
    with _lock:
        components = dict(_components)

    return {
        'uptime_seconds': round(time.monotonic() - _started_at, 1),
        'components': components,
    }
