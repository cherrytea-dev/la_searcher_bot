import os

import dotenv
from telethon import TelegramClient

dotenv.load_dotenv(override=True)
api_id = int(os.getenv('TELETHON_APP_ID'))
api_hash = os.getenv('TELETHON_API_HASH')

# visit https://my.telegram.org/apps to know secrets

channel_username = 'budet_poisk'


client = TelegramClient('build/new_session', api_id, api_hash)


async def main():
    async for message in client.iter_messages(channel_username, limit=10):  # limit to last 10 messages
        print(message.sender.username if message.sender else 'Unknown', message.date.isoformat(), message.text)


with client:
    client.loop.run_until_complete(main())
