import asyncio
import base64
import logging
import sys
from unittest.mock import patch

from telegram import Bot
from telegram.ext import Updater

from _dependencies.pubsub import Topics
from communicate._utils.database import db
from communicate.main import process_update
from tests.common import get_dotenv_config, topic_to_receiver_function


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
    logging.basicConfig(
        encoding='utf-8',
        stream=sys.stdout,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        level=logging.INFO,
        force=True,
    )

    def patched_send_topic(topic_name: Topics, topic_path, data: dict) -> None:
        receiver = topic_to_receiver_function(topic_name)
        receiver({'data': base64.encodebytes(data)}, 'context')

    with (
        patch('_dependencies.commons._get_config', get_dotenv_config),
        patch('_dependencies.pubsub._send_topic', patched_send_topic),
        patch('_dependencies.pubsub._get_publisher'),
        patch('_dependencies.pubsub.get_project_id'),
    ):
        # TODO add pub/sub emulation
        asyncio.run(main_bot())
