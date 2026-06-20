import logging
import random

import vk_api
from pydantic import BaseModel
from vk_api.longpoll import VkEventType, VkLongPoll

from _dependencies.commons import get_app_config

from .event_dispatcher import dispatch_event

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

            dispatch_event(event_data.model_dump())
