import logging
import random
import re
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from functools import lru_cache
from typing import Iterator, List

import sqlalchemy
import vk_api
from sqlalchemy.engine.base import Connection, Engine
from vk_api.longpoll import Event, VkEventType, VkLongPoll
from vk_api.vk_api import VkApiMethod

from _dependencies.commons import get_app_config, sqlalchemy_get_pool

random.seed()


def main():
    vk_session = vk_api.VkApi(token=get_app_config().vk_api_key)
    vk = vk_session.get_api()
    longpoll = VkLongPoll(vk_session)
    for event in longpoll.listen():
        if event.type == VkEventType.MESSAGE_NEW:
            process_incoming_message(vk, event)


def process_incoming_message(vk: VkApiMethod, event: Event) -> None:
    # event.from_admin
    # event.message
    # event.peer_id
    # event.from_user
    # event.text
    if event.from_me:
        return

    random_id = random.randint(0, 10_000_000)
    msg = event.text.lower()
    vk_user_id = event.user_id

    if telegram_user_id := get_invite_from_message(msg):
        try:
            db().set_user_vk_id(telegram_user_id, vk_user_id)
            vk.messages.send(user_id=vk_user_id, message='got invite', random_id=random_id)
        except:
            logging.exception("can't connect VK and Telegram users")
            vk.messages.send(user_id=vk_user_id, message='something got wrong', random_id=random_id)
    else:
        vk.messages.send(user_id=vk_user_id, message='cant recognize invite', random_id=random_id)


def get_invite_from_message(message: str) -> int | None:
    """
    Pattern: telegram_id: <digits> invite_hash: <alphanumeric>
    The message may have extra text before/after, and spacing may vary.
    Use case-insensitive search (message is already lowercased in caller).
    """
    match = re.search(r'telegram_id:\s*(\d+)', message, re.IGNORECASE)
    if match:
        try:
            return int(match.group(1))
        except ValueError:
            return None
    return None


@dataclass
class DBClient:
    _pool: Engine

    @contextmanager
    def connect(self) -> Iterator[Connection]:
        with self._pool.connect() as connection:
            yield connection

    def set_user_vk_id(self, telegram_user_id: int, vk_id: str) -> None:
        """Write user's VKontakte id"""

        with self.connect() as connection:
            stmt = sqlalchemy.text("""UPDATE users SET vk_id=:vk_id where user_id=:user_id;""")
            result = connection.execute(stmt, user_id=telegram_user_id, vk_id=vk_id)
            rows = result.fetchone()
            return rows[0] if rows else None


@lru_cache
def db() -> 'DBClient':
    return DBClient(_pool=sqlalchemy_get_pool())


if __name__ == '__main__':
    main()
