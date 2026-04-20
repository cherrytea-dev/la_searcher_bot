import logging
import random
from contextlib import suppress
from functools import lru_cache
from typing import Any

import vk_api
from pydantic import BaseModel
from sqlalchemy.engine.base import Connection, Engine
from vk_api.longpoll import Event, VkEventType, VkLongPoll
from vk_api.vk_api import VkApiMethod

from _dependencies.commons import get_app_config, setup_logging, sqlalchemy_get_pool
from _dependencies.misc import (
    RequestWrapper,
    ResponseWrapper,
    request_response_converter,
)
from _dependencies.telegram_api_wrapper import make_invite_text_for_user

from ._utils.bot_polling import process_incoming_message

setup_logging(__package__)
random.seed()


@lru_cache
def _get_vk_session() -> vk_api.VkApi:
    vk_session = vk_api.VkApi(token=get_app_config().vk_api_key)
    return vk_session


@lru_cache
def _get_longpoll() -> VkLongPoll:
    vk_session = _get_vk_session()
    longpoll = VkLongPoll(vk_session)
    return longpoll


@request_response_converter
def main(request: RequestWrapper, *args: Any, **kwargs: Any) -> ResponseWrapper:
    return ResponseWrapper(data=main_raw(request.json_))  # type:ignore[arg-type]


def main_raw(request: dict) -> str:
    logging.info(request)

    with suppress(Exception):
        if request['type'] == 'confirmation' and request['group_id'] == 237036024:
            # confirmation, run once
            return get_app_config().vk_confirmation_code

    # Cannot convert Flask request to Event. So we'll use endpoint just as trigger to run polling.
    vk_session = _get_vk_session()
    vk = vk_session.get_api()

    for event in _get_longpoll().check():
        if event.type == VkEventType.MESSAGE_NEW:
            process_incoming_message(vk, event)

    return 'ok'
