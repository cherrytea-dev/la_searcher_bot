import asyncio

import nest_asyncio

from _dependencies.misc import process_sending_message_async

nest_asyncio.apply()


def test_nested_async():
    asyncio.run(inner())


async def inner():
    process_sending_message_async(2, '')
    pass
