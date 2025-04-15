from functools import wraps
from typing import Callable

from communicate._utils.common import HandlerResult, UpdateBasicParams, UpdateExtraParams, UserInputState


def callback_handler(actions: list[str] = [], keyboard_name: str = '') -> Callable:
    def decorator(
        func: Callable[[UpdateBasicParams, UpdateExtraParams], HandlerResult],
    ) -> Callable[[UpdateBasicParams, UpdateExtraParams], HandlerResult | None]:
        @wraps(func)
        def wrapper(update_params: UpdateBasicParams, extra_params: UpdateExtraParams) -> HandlerResult | None:
            if not update_params.got_callback:
                return None

            if update_params.got_callback['action'] in actions:
                return func(update_params, extra_params)

            if update_params.got_callback.get('keyboard') == keyboard_name:
                return func(update_params, extra_params)

            return None

        return wrapper

    return decorator


def button_handler(buttons: list[str] = []) -> Callable:
    def decorator(
        func: Callable[[UpdateBasicParams, UpdateExtraParams], HandlerResult],
    ) -> Callable[[UpdateBasicParams, UpdateExtraParams], HandlerResult | None]:
        @wraps(func)
        def wrapper(update_params: UpdateBasicParams, extra_params: UpdateExtraParams) -> HandlerResult | None:
            if not update_params.got_message:
                return None

            if update_params.got_message in buttons:
                return func(update_params, extra_params)

            return None

        return wrapper

    return decorator


def state_handler(
    state: UserInputState,
) -> Callable:
    def decorator(
        func: Callable[[UpdateBasicParams, UpdateExtraParams], HandlerResult],
    ) -> Callable[[UpdateBasicParams, UpdateExtraParams], HandlerResult | None]:
        @wraps(func)
        def wrapper(update_params: UpdateBasicParams, extra_params: UpdateExtraParams) -> HandlerResult | None:
            if state == extra_params.user_input_state:
                return func(update_params, extra_params)

            return None

        return wrapper

    return decorator
