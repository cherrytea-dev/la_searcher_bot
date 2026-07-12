import logging
from functools import lru_cache

import requests
from requests.models import Response

from _dependencies.bot.telegram_api_wrapper import TGApiBase, _build_telegram_params
from _dependencies.common.commons import get_app_config
from _dependencies.common.telegram_message import TelegramMessage

from .database import db


@lru_cache
def tg_api() -> 'TGApiCommunicate':
    config = get_app_config()
    return TGApiCommunicate(token=config.bot_api_token__prod, host=config.bot_api_host)


class TGApiCommunicate(TGApiBase):
    """need to extend base class with `_inline_processing` call"""

    def _make_api_call(self, method: str, params: dict, call_context: str = '') -> requests.Response | None:
        logging.info(f'_make_api_call. {method=}, {params=}, {call_context=}')
        return super()._make_api_call(method, params, call_context)

    def send_message(self, user_id: int, message: TelegramMessage, call_context: str = '') -> str:
        params = _build_telegram_params(user_id, message)
        response = self._make_api_call('sendMessage', params, call_context)
        result = self._process_response_of_api_call(user_id, response)

        logging.info(f'RESPONSE {response}')
        logging.info(f'RESULT {result}')

        _inline_processing(response, params)
        return result

    def edit_message_text(self, user_id: int, message: TelegramMessage, call_context: str = '') -> str:
        params = _build_telegram_params(user_id, message)
        if message.message_id is not None:
            params['message_id'] = message.message_id
        response = self._make_api_call('editMessageText', params, call_context)
        result = self._process_response_of_api_call(user_id, response)

        logging.info(f'RESPONSE {response}')
        logging.info(f'RESULT {result}')

        _inline_processing(response, params)
        return result


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
    except Exception:
        return None
