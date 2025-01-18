import asyncio

import nest_asyncio

from communicate.main import process_leaving_chat_async, process_sending_message_async

nest_asyncio.apply()
# from asgiref.sync import async_to_sync, sync_to_async


def test_1():
    asyncio.run(inner())


async def inner():
    # process_sending_message_async(1, "foo")
    # new_func = sync_to_async(process_leaving_chat_async)
    process_leaving_chat_async(2)
    pass


# async def prepare_message_for_async() -> str:
#     return "foo"

# def process_sending_message_async() -> None:
#     task = asyncio.create_task(prepare_message_for_async())
#     loop = asyncio.get_event_loop()
#     task = asyncio.ensure_future(task, loop=loop)

#     return None
