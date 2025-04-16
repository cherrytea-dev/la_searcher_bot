import asyncio
import base64
import logging
import sys
from functools import lru_cache
from unittest.mock import patch

import nest_asyncio
from dotenv import load_dotenv
from pyannotate_runtime import collect_types
from telegram import Bot
from telegram.ext import Updater

from _dependencies.commons import AppConfig, Topics
from communicate._utils.database import db
from communicate.main import process_update
from tests.common import topic_to_receiver_function

nest_asyncio.apply()


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


@lru_cache
def get_dotenv_config() -> AppConfig:
    assert load_dotenv('.env', override=True)
    return AppConfig()


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
        patch('_dependencies.commons.get_publisher'),
        patch('_dependencies.commons.get_project_id'),
        patch('_dependencies.commons._send_topic', patched_send_topic),
    ):
        # TODO add pub/sub emulation
        collect_types.init_types_collection()
        with collect_types.collect():
            try:
                asyncio.run(main_bot())
            except Exception as exc:
                pass  # let the pyannotate to save collected types
        collect_types.dump_stats('type_info.json')
