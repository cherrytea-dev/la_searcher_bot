import logging
from functools import lru_cache

import requests
from requests.models import Response

from _dependencies.commons import get_app_config
from _dependencies.telegram_api_wrapper import TGApiBase

from .database import db


@lru_cache
def tg_api() -> 'TGApiCommunicate':
    return TGApiCommunicate(token=get_app_config().bot_api_token__prod)


class TGApiCommunicate(TGApiBase):
    """need to extend base class with `_inline_processing` call"""

    def _make_api_call(self, method: str, params: dict, call_context: str = '') -> requests.Response | None:
        logging.info(f'_make_api_call. {method=}, {params=}, {call_context=}')
        return super()._make_api_call(method, params, call_context)

    def send_message(self, params: dict, call_context: str = '') -> str:
        response = self._make_api_call('sendMessage', params, call_context)
        user_id = params['chat_id']
        result = self._process_response_of_api_call(user_id, response)

        logging.info(f'RESPONSE {response}')
        logging.info(f'RESULT {result}')

        _inline_processing(response, params)
        return result

    def edit_message_text(self, params: dict, call_context: str = '') -> None:
        response = self._make_api_call('editMessageText', params, call_context)
        user_id = params['chat_id']
        result = self._process_response_of_api_call(user_id, response)

        logging.info(f'RESPONSE {response}')
        logging.info(f'RESULT {result}')

        _inline_processing(response, params)


def _inline_processing(response: Response | None, params: dict) -> None:
    """process the response got from inline buttons interactions"""

    if not response or 'chat_id' not in params.keys():
        return

    chat_id: int = params['chat_id']

    if 'reply_markup' in params.keys() and 'inline_keyboard' in params['reply_markup'].keys():
        sent_message_id = _get_last_bot_message_id(response)
        # prev_message_id = db().get_last_user_inline_dialogue(chat_id)
        # logging.info(f'{prev_message_id=}')
        if sent_message_id:
            db().save_last_user_inline_dialogue(chat_id, sent_message_id)


def _get_last_bot_message_id(response: requests.Response) -> int | None:
    """Get the message id of the bot's message that was just sent"""

    try:
        return response.json()['result']['message_id']
    except Exception as e:
        return None
