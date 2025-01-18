import asyncio
from unittest.mock import patch

import nest_asyncio
from pyannotate_runtime import collect_types
from telegram import Bot
from telegram.ext import Updater

from communicate.main import process_update
from tests.common import get_test_config

nest_asyncio.apply()


async def main_bot() -> None:
    bot = Bot(get_test_config().bot_api_token__prod)
    update_queue = asyncio.Queue()
    updater = Updater(bot, update_queue)
    async with updater:
        queue = await updater.start_polling(timeout=60)
        while True:
            update = await queue.get()
            print(update)
            process_update(update)


if __name__ == '__main__':
    with (
        patch('_dependencies.commons._get_config', get_test_config),
        patch('_dependencies.commons.get_publisher'),
        patch('_dependencies.commons.get_project_id'),
    ):
        # TODO add pub/sub emulation
        collect_types.init_types_collection()
        with collect_types.collect():
            try:
                asyncio.run(main_bot())
            except:
                pass  # let the pyannotate to save collected types
        collect_types.dump_stats('type_info.json')
