import asyncio

import nest_asyncio

from communicate.main import process_leaving_chat_async, process_sending_message_async

nest_asyncio.apply()
# from asgiref.sync import async_to_sync, sync_to_async


def test_1():
    asyncio.run(inner())


def test_2():
    asyncio.run(inner_2())


async def inner():
    process_leaving_chat_async(2)
    pass


async def inner_2():
    process_sending_message_async(2, '')
    pass
