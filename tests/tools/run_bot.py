import asyncio
import logging
from unittest.mock import patch

from telegram import Bot
from telegram.ext import Updater

from communicate._utils.database import db
from communicate.main import process_update
from tests.common import get_dotenv_config, patched_send_topic, setup_logging_to_console


async def main_bot() -> None:
    bot = Bot(get_dotenv_config().bot_api_token__prod)
    update_queue = asyncio.Queue()
    updater = Updater(bot, update_queue)
    async with updater:
        with db().connect():
            queue = await updater.start_polling(timeout=60)
            while True:
                update = await queue.get()
                print(update)
                process_update(update)


if __name__ == '__main__':
    setup_logging_to_console()
    logging.info('hello')

    with (
        patch('_dependencies.commons._get_config', get_dotenv_config),
        # patch('_dependencies.pubsub.send_topic_google', patched_send_topic),
    ):
        # TODO add pub/sub emulation
        asyncio.run(main_bot())
