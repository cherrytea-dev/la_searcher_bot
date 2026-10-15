"""Long-polling bot runners — one supervised thread per messenger.

The cloud deployment received Telegram/VK/MAX events through webhooks, which needs a public
ingress. In a container it is cheaper to poll: Telegram through ``Updater.start_polling``,
VK through ``VkLongPoll``, MAX through ``Dispatcher.start_polling``. Each runner is wrapped in
a supervisor that restarts it with a delay if it crashes.

A bot that has a configured webhook path is served over HTTP by :mod:`app.http_server` instead
of being polled: its runner is skipped here, so events are never processed twice.
"""

from __future__ import annotations

import asyncio
import logging
import threading
from typing import Any, Callable

from _dependencies.common.commons import get_app_config
from _dependencies.common.log_context import log_stream
from app.status import StatusRegistry

_RESTART_DELAY_SECS = 15.0
_TELEGRAM_POLL_TIMEOUT_SECS = 60

#: Which function each poller runs — its name goes into ``stream_name`` (see log_context).
_BOT_STREAMS: dict[str, str] = {
    'telegram-bot': 'communicate',
    'vk-bot': 'vk_bot',
    'max-bot': 'max_bot',
}

#: Update types the bot asks Telegram for. The cloud functions never set ``allowed_updates``,
#: so they received everything; the polling container has to ask for the same set explicitly,
#: otherwise ``my_chat_member`` (the only thing that lifts a block), inline queries and channel
#: posts are dropped without a trace. Shared with ``tests/tools/run_bot.py`` so the two lists
#: cannot drift apart again.
TELEGRAM_ALLOWED_UPDATES: tuple[str, ...] = (
    'message',
    'callback_query',
    'my_chat_member',
    'inline_query',
    'channel_post',
    'edited_channel_post',
)


def start_bots(stop_event: threading.Event, status: StatusRegistry) -> list[threading.Thread]:
    """Start the enabled bots; returns their threads."""
    config = get_app_config()
    runners: list[tuple[str, Callable[[threading.Event], None]]] = []
    if config.enable_tg_bot and not config.webhook_path_telegram:
        runners.append(('telegram-bot', run_telegram))
    if config.enable_vk_bot and not config.webhook_path_vk:
        runners.append(('vk-bot', run_vk))
    if config.enable_max_bot and not config.webhook_path_max:
        runners.append(('max-bot', run_max))

    threads = []
    for name, runner in runners:
        thread = threading.Thread(target=_supervise, args=(name, stop_event, status, runner), name=name, daemon=True)
        thread.start()
        threads.append(thread)
    return threads


def _supervise(
    name: str, stop_event: threading.Event, status: StatusRegistry, runner: Callable[[threading.Event], None]
) -> None:
    status.set_status(name, 'starting')
    while not stop_event.is_set():
        try:
            status.set_status(name, 'running')
            with log_stream(_BOT_STREAMS.get(name, name)):
                runner(stop_event)
        except Exception:
            logging.exception('%s crashed; restarting in %.0fs', name, _RESTART_DELAY_SECS)
            status.set_status(name, 'error')
            stop_event.wait(_RESTART_DELAY_SECS)
        else:
            break
    status.set_status(name, 'stopped')


def run_telegram(stop_event: threading.Event) -> None:
    """Poll Telegram updates and hand them to ``communicate`` in the same process."""
    asyncio.run(_telegram_loop(stop_event))


async def _telegram_loop(stop_event: threading.Event) -> None:
    from telegram import Bot
    from telegram.ext import Updater

    from communicate.main import process_update

    bot = Bot(get_app_config().bot_api_token__prod)
    updater = Updater(bot, asyncio.Queue())
    async with updater:
        update_queue = await updater.start_polling(
            timeout=_TELEGRAM_POLL_TIMEOUT_SECS,
            allowed_updates=TELEGRAM_ALLOWED_UPDATES,
        )
        logging.info('telegram bot: polling started')
        while not stop_event.is_set():
            try:
                update: Any = await asyncio.wait_for(update_queue.get(), timeout=5)
            except TimeoutError:
                continue
            # process_update talks to Telegram and PostgreSQL: keep the event loop free.
            await asyncio.to_thread(process_update, update)


def run_vk(stop_event: threading.Event) -> None:
    """Poll VK (``VkLongPoll``) — the loop is blocking, the thread is a daemon."""
    from vk_bot._utils.bot_polling import run_polling

    logging.info('vk bot: polling started')
    run_polling()


def run_max(stop_event: threading.Event) -> None:
    """Poll MAX through ``maxapi``."""
    from max_bot._utils.bot_polling import run_polling

    logging.info('max bot: polling started')
    run_polling()
