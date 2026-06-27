"""Platform-agnostic handler registration infrastructure.

Provides the core building blocks for decorator-based handler registration
used by both the VK bot and Telegram bot:

- :class:`HandlerConditions` — pure data model describing what conditions
  a handler matches on (text, callback_data, state, etc.)
- :class:`Handler` — a registered handler with its conditions and priority
- :class:`HandlerRegistry` — a priority-ordered registry of handlers
- :func:`match_conditions` — pure matching function that checks conditions
  against a dict of extracted values

This module contains **no platform-specific logic**, no context type references,
and no decorators. Platform-specific decorators (``@vk_handle``, ``@tg_handle``)
live in their respective bot packages and use this infrastructure.
"""

import re
from dataclasses import dataclass
from typing import Any, Callable, Generator

from pydantic import BaseModel


class HandlerConditions(BaseModel):
    """Conditions that determine whether a handler should fire.

    All fields are optional (``None`` means "don't check this condition").
    When multiple fields are set, **all** must match (AND logic).

    .. note::

       This model is platform-agnostic. It does not reference
       ``VKHandlerContext``, ``TGHandlerContext``, or any messenger-specific
       types. The decorator layer is responsible for extracting values from
       the context and passing them to :func:`match_conditions`.
    """

    text: str | list[str] | None = None
    """Exact text match. A string or list of strings (any of which matches)."""

    text_startswith: str | None = None
    """Text prefix match (``str.startswith``)."""

    text_regex: str | None = None
    """Text regex match (``re.search``)."""

    callback_data: str | list[str] | None = None
    """Callback data match (e.g. VK ``payload.cmd`` or TG ``callback_query.data``)."""

    state: str | None = None
    """Dialog state match. Uses the string value of :class:`DialogState`."""


@dataclass
class Handler:
    """A registered handler with its matching conditions and priority.

    Attributes:
        func: The handler callable. Receives a platform-specific context
            object as its sole argument.
        conditions: The conditions that determine when this handler fires.
        priority: Lower values fire first. Default ``0``.
    """

    func: Callable[..., Any]
    conditions: HandlerConditions
    priority: int = 0


def match_conditions(conditions: HandlerConditions, **values: Any) -> bool:
    """Check whether *conditions* match the given keyword *values*.

    For each non-``None`` field in *conditions*, the corresponding keyword
    argument is checked. Returns ``True`` only if **all** conditions match
    (AND logic).

    Examples::

        match_conditions(
            HandlerConditions(text='hello', state='radius_input'),
            text='hello',
            state='radius_input',
        )  # → True

        match_conditions(
            HandlerConditions(text='hello'),
            text='world',
        )  # → False

        match_conditions(
            HandlerConditions(text_regex=r'^[+-]\\d+$'),
            text='+12345',
        )  # → True
    """
    # ── Text exact match ──────────────────────────────────────────────
    if conditions.text is not None:
        user_text = values.get('text')
        if user_text is None:
            return False
        expected = conditions.text if isinstance(conditions.text, list) else [conditions.text]
        if user_text not in expected:
            return False

    # ── Text prefix match (startswith) ────────────────────────────────
    if conditions.text_startswith is not None:
        user_text = values.get('text')
        if user_text is None:
            return False
        if not user_text.startswith(conditions.text_startswith):
            return False

    # ── Text regex match ──────────────────────────────────────────────
    if conditions.text_regex is not None:
        user_text = values.get('text')
        if user_text is None:
            return False
        if not re.search(conditions.text_regex, user_text):
            return False

    # ── Callback data match ──────────────────────────────────────────
    if conditions.callback_data is not None:
        incoming = values.get('callback_data')
        if incoming is None:
            return False
        expected = (
            conditions.callback_data if isinstance(conditions.callback_data, list) else [conditions.callback_data]
        )
        if incoming not in expected:
            return False

    # ── State match ──────────────────────────────────────────────────
    if conditions.state is not None:
        if values.get('state') != conditions.state:
            return False

    return True  # all conditions matched


class HandlerRegistry:
    """Priority-ordered registry of handlers.

    Handlers are registered at import time via platform-specific decorators
    (``@vk_handle``, ``@tg_handle``). At dispatch time, the dispatcher
    extracts values from the context and calls :meth:`match` to find
    matching handlers in priority order.

    The registry is **read-only at runtime** — all registration happens
    during module import.
    """

    def __init__(self) -> None:
        self._handlers: list[Handler] = []

    def register(self, handler: Handler) -> None:
        """Register a handler.

        Called by platform-specific decorators at import time.
        """
        self._handlers.append(handler)

    def match(self, **kwargs: Any) -> Generator[Handler, None, None]:
        """Yield handlers whose conditions match *kwargs*, in priority order.

        Args:
            **kwargs: Extracted values to match against. Typical keys:
                ``text``, ``callback_data``, ``state``.

        Yields:
            :class:`Handler` instances in ascending priority order.
        """
        for handler in sorted(self._handlers, key=lambda h: h.priority):
            if match_conditions(handler.conditions, **kwargs):
                yield handler

    def all(self) -> list[Handler]:
        """Return all registered handlers (for testing/inspection)."""
        return list(self._handlers)

    def clear(self) -> None:
        """Remove all registered handlers (for testing)."""
        self._handlers.clear()
