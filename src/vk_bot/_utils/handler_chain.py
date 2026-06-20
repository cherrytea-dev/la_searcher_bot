"""Handler chain definition for the VK bot.

Defines the ordered list of handler routers (HANDLER_CHAIN) that
process incoming user messages, and the fallback handler (handle_unknown)
that is invoked when no other handler matches.
"""

from typing import Callable

from .common import VKHandlerResult, VKMessage
from .database import DialogState
from .handlers import (
    onboarding_handlers,
    region_select_handlers,
    settings_handlers,
    state_handlers,
    view_searches_handlers,
)
from .keyboards import VKKeyboardPresets

HandlerFunc = Callable[[VKMessage, DialogState | None, int], VKHandlerResult | None]


def handle_unknown(vk_message: VKMessage, state: DialogState | None, user_id: int = 0) -> VKHandlerResult | None:
    """Fallback handler — triggered when no other handler matched."""
    return VKHandlerResult(
        text='не понимаю такой команды, пожалуйста, используйте кнопки со стандартными командами ниже',
        keyboard=VKKeyboardPresets.main_menu(),
    )


HANDLER_CHAIN: list[HandlerFunc] = [
    *state_handlers.router,
    *onboarding_handlers.router,
    *view_searches_handlers.router,
    *region_select_handlers.router,
    *settings_handlers.settings_router,
    handle_unknown,
]
