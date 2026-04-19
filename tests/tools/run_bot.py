import asyncio
import logging
from unittest.mock import patch

from telegram import Bot
from telegram.ext import Updater

from communicate._utils.database import db
from communicate._utils.message_sending import tg_api
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

    # bot_message = (
    #     'Откройте чат в VK по кнопке ниже \n'
    #     f'и вставьте туда следующий текст: `user_id: {196282174}`'
    # )
    # # keyboard = [b_back_to_start]
    # # reply_markup = create_one_column_reply_markup(keyboard)

    # from telegram import ReplyKeyboardMarkup, InlineKeyboardMarkup, InlineKeyboardButton
    # btn = InlineKeyboardButton(text="Чат в VK", url="https://m.vk.com/write-237036024")
    # markup = InlineKeyboardMarkup([[btn]])
    # params = {
    #     'chat_id': 196282174,
    #     'text': bot_message,
    #     'parse_mode': 'markdown',
    #     'disable_web_page_preview': True,
    #     'reply_markup': markup,
    # }
    # tg_api().send_message(params)

    with (
        patch('_dependencies.commons._get_config', get_dotenv_config),
        # patch('_dependencies.pubsub.send_topic_google', patched_send_topic),
    ):
        # TODO add pub/sub emulation
        asyncio.run(main_bot())
