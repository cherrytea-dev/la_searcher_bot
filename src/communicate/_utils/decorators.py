from functools import wraps
from typing import Callable

from .common import TGHandlerContext, UserInputState


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
