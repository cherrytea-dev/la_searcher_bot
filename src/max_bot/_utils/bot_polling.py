"""Long-polling runner for the MAX bot.

Creates a ``maxapi.Bot`` instance (reads ``MAX_BOT_TOKEN`` from env),
configures a ``Dispatcher`` with the shared router from ``handlers.py``,
and starts polling for updates.

Usage:
    ``uv run python -m src.max_bot.cli --polling``
"""

import asyncio
import logging

from maxapi import Bot, Dispatcher

from . import handlers

logger = logging.getLogger(__name__)


async def run_polling_async() -> None:
    """Create bot, configure dispatcher, and start long polling."""
    bot = Bot()
    dp = Dispatcher()
    dp.include_routers(handlers.router)

    # Inject the Dispatcher's FSM ContextManager into handlers.
    # Router.fsm raises RuntimeError, so handlers use this reference instead.
    handlers.set_fsm(dp.fsm)

    logger.info('Starting MAX bot in long-polling mode...')
    logger.info('Bot token configured: %s', 'yes' if bot._Bot__token else 'no')  # type: ignore[attr-defined]

    await dp.start_polling(bot)


def run_polling() -> None:
    """Synchronous entry point for ``run_max_bot.py`` and CLI."""
    asyncio.run(run_polling_async())
