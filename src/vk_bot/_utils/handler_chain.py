"""Handler chain definition for the VK bot.

Imports all handler modules to trigger @vk_handle registration,
then provides the fallback handler (handle_unknown) for unmatched messages.

The actual handler matching is done by vk_registry.match() in message_processing.py.
"""

from .common import VKHandlerContext
from .handlers import (  # noqa: F401 — import to trigger @vk_handle registration
    onboarding_handlers,
    region_select_handlers,
    settings_handlers,
    state_handlers,
    view_searches_handlers,
)
from .keyboards import VKKeyboardPresets


def handle_unknown(ctx: VKHandlerContext) -> None:
    """Fallback handler — triggered when no other handler matched."""
    ctx.reply(
        text='не понимаю такой команды, пожалуйста, используйте кнопки со стандартными командами ниже',
        keyboard=VKKeyboardPresets.main_menu(),
    )
