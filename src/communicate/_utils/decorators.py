from functools import wraps
from typing import Callable

from _dependencies.bot.handler_registry import Handler, HandlerConditions, HandlerRegistry

from .common import UserInputState
from .handler_context import TGHandlerContext

# ─── New decorator-based registration ───

tg_registry = HandlerRegistry()


def tg_handle(
    text: str | list[str] | None = None,
    text_startswith: str | None = None,
    text_regex: str | None = None,
    callback_data: str | list[str] | None = None,
    state: str | None = None,
    priority: int = 0,
) -> Callable:
    """Register a Telegram handler with the given conditions.

    Args:
        text: Exact text to match (or list of texts).
        text_startswith: Prefix to match.
        text_regex: Regex pattern to search in text.
        callback_data: Callback data to match (or list of values).
        state: Dialog state to match.
        priority: Higher priority handlers are tried first.
    """
    conditions = HandlerConditions(
        text=text,
        text_startswith=text_startswith,
        text_regex=text_regex,
        callback_data=callback_data,
        state=state,
    )

    def decorator(
        func: Callable[[TGHandlerContext], None],
    ) -> Callable[[TGHandlerContext], None]:
        tg_registry.register(Handler(func=func, conditions=conditions, priority=priority))
        return func

    return decorator


# ─── Legacy decorators (backward compatibility) ───


def callback_handler(actions: list[str] = [], keyboard_name: str = '') -> Callable:
    def decorator(
        func: Callable[[TGHandlerContext], None],
    ) -> Callable[[TGHandlerContext], None]:
        @wraps(func)
        def wrapper(ctx: TGHandlerContext) -> None:
            if not ctx.update_params.got_callback:
                return

            if ctx.update_params.got_callback.action in actions:
                func(ctx)
                return

            if ctx.update_params.got_callback.keyboard_name == keyboard_name:
                func(ctx)
                return

            return

        return wrapper

    return decorator


def button_handler(buttons: list[str] = []) -> Callable:
    def decorator(
        func: Callable[[TGHandlerContext], None],
    ) -> Callable[[TGHandlerContext], None]:
        @wraps(func)
        def wrapper(ctx: TGHandlerContext) -> None:
            if not ctx.update_params.got_message:
                return

            if ctx.update_params.got_message in buttons:
                func(ctx)
                return

            return

        return wrapper

    return decorator


def state_handler(
    state: UserInputState,
) -> Callable:
    def decorator(
        func: Callable[[TGHandlerContext], None],
    ) -> Callable[[TGHandlerContext], None]:
        @wraps(func)
        def wrapper(ctx: TGHandlerContext) -> None:
            if state == ctx.extra_params.user_input_state:
                func(ctx)
                return

            return

        return wrapper

    return decorator
