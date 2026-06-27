from typing import Callable

from _dependencies.bot.handler_registry import Handler, HandlerConditions, HandlerRegistry

from .handler_context import TGHandlerContext

tg_registry = HandlerRegistry()


def _normalize_text(value: str | list[str] | None) -> str | list[str] | None:
    """Lowercase text value(s) for case-insensitive matching.

    Telegram sends button text as-is, but users may type commands in any case.
    Normalizing both the expected value and the incoming text to lowercase
    ensures case-insensitive matching.
    """
    if value is None:
        return None
    if isinstance(value, list):
        return [v.strip().lower() for v in value]
    return value.strip().lower()


def tg_handle(
    text: str | list[str] | None = None,
    text_startswith: str | None = None,
    text_regex: str | None = None,
    callback_data: str | list[str] | None = None,
    callback_keyboard: str | None = None,
    state: str | None = None,
    priority: int = 0,
) -> Callable:
    """Register a Telegram handler with the given conditions.

    Args:
        text: Exact text to match (or list of texts). Normalized to lowercase.
        text_startswith: Prefix to match.
        text_regex: Regex pattern to search in text.
        callback_data: Callback data to match (or list of values).
        callback_keyboard: Callback keyboard name to match.
        state: Dialog state to match.
        priority: Higher priority handlers are tried first.
    """
    conditions = HandlerConditions(
        text=_normalize_text(text),
        text_startswith=text_startswith,
        text_regex=text_regex,
        callback_data=callback_data,
        callback_keyboard=callback_keyboard,
        state=state,
    )

    def decorator(
        func: Callable[[TGHandlerContext], None],
    ) -> Callable[[TGHandlerContext], None]:
        tg_registry.register(Handler(func=func, conditions=conditions, priority=priority))
        return func

    return decorator
