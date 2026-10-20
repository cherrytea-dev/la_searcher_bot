"""Registration handlers: ``bot_started`` and ``/start``."""

import logging

from maxapi.filters.command import Command
from maxapi.types.updates.bot_started import BotStarted
from maxapi.types.updates.message_created import MessageCreated

from ..common import _get_chat_id, _get_user_id, _main_menu_for_user, router
from ..message_formatter import INTERNAL_ERROR, WELCOME_TEXT

logger = logging.getLogger(__name__)


@router.bot_started()
async def on_bot_started(event: BotStarted) -> None:
    """Handle ``bot_started`` — user first opens a chat with the bot.

    Registers the user if new, then shows the main menu.
    """
    user_id = event.user.user_id
    chat_id = event.chat_id
    logger.info('Bot started by user %s in chat %s', user_id, chat_id)

    bot = event.bot
    if bot is None:
        logger.error('Bot instance is None in bot_started handler')
        return

    try:
        await bot.send_message(
            chat_id=chat_id,
            text=WELCOME_TEXT,
            attachments=[_main_menu_for_user(user_id)],  # type: ignore[arg-type]
        )
    except Exception:
        logger.exception('Error in bot_started for user %s', user_id)
        await bot.send_message(chat_id=chat_id, text=INTERNAL_ERROR)


@router.message_created(Command('start'))
async def on_start(event: MessageCreated) -> None:
    """Handle ``/start`` command — register user and show main menu."""
    user_id = _get_user_id(event)
    chat_id = _get_chat_id(event)
    logger.info('Start command from user %s', user_id)

    if user_id is None or chat_id is None:
        return

    try:
        await event.message.answer(
            text=WELCOME_TEXT,
            attachments=[_main_menu_for_user(user_id)],
        )
    except Exception:
        logger.exception('Error in /start for user %s', user_id)
        await event.message.answer(text=INTERNAL_ERROR)
