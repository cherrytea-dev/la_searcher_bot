import json
import logging
import random
import re

import vk_api
from vk_api.longpoll import Event, VkEventType, VkLongPoll
from vk_api.vk_api import VkApiMethod

from _dependencies.commons import get_app_config

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
    user_id = event.user_id

    if invite_id := get_invite_from_message(msg):
        try:
            connect_users(user_id, invite_id)
            vk.messages.send(user_id=user_id, message='got invite', random_id=random_id)
        except:
            logging.exception("can't connect VK and Teelgram users")
            vk.messages.send(user_id=user_id, message='something got wrong', random_id=random_id)
    else:
        vk.messages.send(user_id=user_id, message='cant recognize invite', random_id=random_id)


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


def connect_users(vk_id: int, telegram_id: int) -> None:
    """
    write to sql table `users` user's id to column `vk_id'
    see examples in `src/send_notifications/main.py`, function 'fill_vk_user_ids'

    """

    return None


if __name__ == '__main__':
    main()
