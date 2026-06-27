"""VK-specific handler decorator and registry.

Provides the ``@vk_handle`` decorator that registers handlers into
``vk_registry`` — a :class:`HandlerRegistry` instance.

Usage::

    from vk_bot._utils.decorators import vk_handle
    from vk_bot._utils.keyboards import VKKeyboardButtons

    @vk_handle(text=VKKeyboardButtons.BTN_COORDS_ENTER)
    def handle_coords_enter(ctx: VKHandlerContext) -> None:
        ctx.reply(...)
"""

from __future__ import annotations

from typing import Callable

from _dependencies.bot.handler_registry import Handler, HandlerConditions, HandlerRegistry

vk_registry = HandlerRegistry()


def vk_handle(
    text: str | list[str] | None = None,
    text_startswith: str | None = None,
    text_regex: str | None = None,
    callback_data: str | list[str] | None = None,
    state: str | None = None,
    priority: int = 0,
) -> Callable:
    """Register a VK handler with the given matching conditions.

    Args:
        text: Exact text to match (or list of alternatives).
            The dispatcher normalizes text (``.strip().lower()``) before
            matching, so button constants are compared case-insensitively.
        text_startswith: Match if text starts with this prefix.
        text_regex: Match if ``re.search(pattern, text)`` succeeds.
        callback_data: Match callback payload ``cmd`` value.
        state: Match dialog state (string value of :class:`DialogState`).
        priority: Lower values fire first. Default ``0``.

    All specified conditions must match (AND logic).
    """
    conditions = HandlerConditions(
        text=text,
        text_startswith=text_startswith,
        text_regex=text_regex,
        callback_data=callback_data,
        state=state,
    )

    def decorator(func: Callable) -> Callable:
        handler = Handler(func=func, conditions=conditions, priority=priority)
        vk_registry.register(handler)
        return func

    return decorator
