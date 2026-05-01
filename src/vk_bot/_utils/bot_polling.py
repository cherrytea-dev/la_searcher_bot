import logging
import random
import re
from functools import lru_cache

import sqlalchemy
import vk_api
from pydantic import BaseModel
from vk_api.longpoll import Event, VkEventType, VkLongPoll

from _dependencies.commons import get_app_config, sqlalchemy_get_pool
from _dependencies.db_client import DBClientBase
from _dependencies.telegram_api_wrapper import make_invite_text_for_user
from _dependencies.vk_api_client import get_default_vk_api_client

random.seed()


class EventMessage(BaseModel):
    text: str
    from_id: int
    peer_id: int


class EventObject(BaseModel):
    client_info: dict | None = None
    message: EventMessage | None = None


class UpdateEvent(BaseModel):
    type: str
    object: EventObject | None


class DBClient(DBClientBase):
    def set_user_vk_id(self, telegram_user_id: int, vk_id: int) -> None:
        """Write user's VKontakte id"""

        with self.connect() as connection:
            stmt = sqlalchemy.text("""
                UPDATE users 
                SET vk_id=:vk_id 
                where user_id=:user_id;
                                   """)
            connection.execute(stmt, user_id=telegram_user_id, vk_id=vk_id)


@lru_cache
def db() -> 'DBClient':
    return DBClient(db=sqlalchemy_get_pool())


def process_incoming_message(event: UpdateEvent) -> None:
    logging.info('processing event %s', event)
    if not event.object:
        return

    if event.type != 'message_new':
        return

    if not event.object.message:
        return

    msg = event.object.message.text.lower()

    telegram_user_id, secret = get_invite_from_message(msg)
    logging.info('got invite from user %s', telegram_user_id)
    # vk.messages.mark_as_read(peer_id=event.peer_id)
    if not telegram_user_id:
        return

    if make_invite_text_for_user(telegram_user_id).lower() != msg:
        logging.warning(f'invite hash wrong for telegram user {telegram_user_id}')
        return

    random_id = random.randint(0, 10_000_000)
    vk_user_id = event.object.message.from_id
    try:
        logging.info('connecting user %s', telegram_user_id)
        db().set_user_vk_id(telegram_user_id, vk_user_id)
        message = (
            'Ваш акаунт связан с аккаунтом в Телеграм. \n'
            'Вы будете получать здесь уведомления о поисках с теми же настройками, которые заданы в Телеграм'
        )
        get_default_vk_api_client().send(user_id=vk_user_id, message=message, random_id=random_id)

    except:
        logging.exception("can't connect VK and Telegram users")
        get_default_vk_api_client().send(
            user_id=vk_user_id, message='не удалось привязать пользователя Телеграм', random_id=random_id
        )


def get_invite_from_message(message: str) -> tuple[int, str] | tuple[None, None]:
    """
    Pattern: telegram_id: <digits> invite_hash: <alphanumeric>
    The message may have extra text before/after, and spacing may vary.
    Use case-insensitive search (message is already lowercased in caller).
    """
    match = re.search(r'telegram_id:\s*(\d+) invite_hash:\s*(\w+)', message, re.IGNORECASE)
    if match:
        try:
            return int(match.group(1)), match.group(2)
        except ValueError:
            return None, None
    return None, None


def run_polling() -> None:
    vk_session = vk_api.VkApi(token=get_app_config().vk_api_key)
    longpoll = VkLongPoll(vk_session)
    for event in longpoll.listen():
        if event.type == VkEventType.MESSAGE_NEW and not event.from_me:
            json_ = {
                'type': 'message_new',
                'object': {
                    'message': {
                        'from_id': event.from_user,
                        'text': event.text,
                        'peer_id': event.from_user,
                    },
                },
            }
            event_data = UpdateEvent.model_validate(json_)

            process_incoming_message(event_data)
