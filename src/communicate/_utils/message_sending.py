import json
import logging
import urllib.parse
from functools import lru_cache
from typing import Union

import requests
from requests.models import Response
from telegram import TelegramObject

from _dependencies.commons import Topics, get_app_config, publish_to_pubsub
from _dependencies.misc import notify_admin

from .database import db


@lru_cache
def tg_api() -> 'TGApi':
    return TGApi()


class TGApi:
    def __init__(self) -> None:
        self._token = get_app_config().bot_api_token__prod
        self._session = requests.Session()

    def leave_chat(self, user_id: int) -> None:
        self._make_api_call('leaveChat', {'chat_id': user_id})

    def send_callback_answer_to_api(self, user_id: int, callback_query_id: str, message: str) -> None:
        try:
            # NB! only 200 characters
            message = message[:200]
            message_encoded = f'&text={urllib.parse.quote(message)}'

            request_text = (
                f'https://api.telegram.org/bot{self._token}/answerCallbackQuery?callback_query_id='
                f'{callback_query_id}{message_encoded}'
            )

            response = self._session.get(request_text)
            logging.info(f'send_callback_answer_to_api..{response.json()=}')

            _process_response_of_api_call(user_id, response)
        except Exception:
            logging.exception('Error in getting response from Telegram')

    def send_message(self, params: dict, call_context: str = '') -> None:
        response = self._make_api_call('sendMessage', params, call_context)
        user_id = params['chat_id']
        result = _process_response_of_api_call(user_id, response)

        logging.info(f'RESPONSE {response}')
        logging.info(f'RESULT {result}')

        _inline_processing(response, params)

    def edit_message_text(self, params: dict, call_context: str = '') -> None:
        response = self._make_api_call('editMessageText', params, call_context)
        user_id = params['chat_id']
        result = _process_response_of_api_call(user_id, response)

        logging.info(f'RESPONSE {response}')
        logging.info(f'RESULT {result}')

        _inline_processing(response, params)

    def delete_message(self, chat_id: int, message_id: int) -> requests.Response | None:
        params = {'chat_id': chat_id, 'message_id': message_id}

        return self._make_api_call('deleteMessage', params)

    def set_my_commands(self, chat_id: int, commands: list, call_context: str = '') -> None:
        params = {'commands': commands, 'scope': {'type': 'chat', 'chat_id': chat_id}}
        response = self._make_api_call('setMyCommands', params, call_context)
        result = _process_response_of_api_call(chat_id, response)
        logging.info(f'hiding user {chat_id} menu status = {result}')

    def delete_my_commands(self, chat_id: int) -> None:
        params = {'scope': {'type': 'chat', 'chat_id': chat_id}}
        response = self._make_api_call('deleteMyCommands', params)
        _process_response_of_api_call(chat_id, response)

    def edit_message_reply_markup(self, chat_id: int, last_inline_message_id: int, call_context: str = '') -> None:
        params = {'chat_id': chat_id, 'message_id': last_inline_message_id}
        self._make_api_call('editMessageReplyMarkup', params, call_context)

    def _make_api_call(self, method: str, params: dict, call_context: str = '') -> Union[requests.Response, None]:
        """make an API call to telegram"""

        if not params or not method:
            logging.warning(f'not params or not method: {method=}; {len(params)=}')
            return None

        if 'chat_id' not in params.keys() and ('scope' not in params.keys() or 'chat_id' not in params['scope'].keys()):
            return None

        url = f'https://api.telegram.org/bot{self._token}/{method}'  # e.g. sendMessage
        headers = {'Content-Type': 'application/json'}

        if 'reply_markup' in params and isinstance(params['reply_markup'], TelegramObject):
            params['reply_markup'] = params['reply_markup'].to_dict()
        logging.info(
            f'({method=}, {call_context=})..before json_params = json.dumps(params) {params=}; {type(params)=}'
        )
        json_params = json.dumps(params)
        logging.info(f'({method=}, {call_context=})..after json.dumps(params): {json_params=}; {type(json_params)=}')

        try:
            response = self._session.post(url=url, data=json_params, headers=headers)
            logging.info(f'After session.post: {response=}; {call_context=}')
        except Exception as e:
            response = None
            logging.exception('Error in getting response from Telegram')

        logging.info(f'Before return: {response=}; {call_context=}')
        return response


def _process_response_of_api_call(user_id: int, response: Response | None, call_context: str = '') -> str:
    """process response received as a result of Telegram API call while sending message/location"""

    if response is None:
        logging.error('Response is corrupted')
        return 'failed'

    try:
        if 'ok' not in response.json():
            notify_admin(f'ALARM! "ok" is not in response: {response.json()}, user {user_id}')
            return 'failed'

        if response.ok:
            logging.info(f'message to {user_id} was successfully sent')
            return 'completed'

        elif response.status_code == 400:  # Bad Request
            logging.exception(f'Bad Request: message to {user_id} was not sent, {response.json()=}')
            return 'cancelled_bad_request'

        elif response.status_code == 403:  # FORBIDDEN
            logging.info(f'Forbidden: message to {user_id} was not sent, {response.reason=}')
            action = None
            if response.text.find('bot was blocked by the user') != -1:
                action = 'block_user'
            if response.text.find('user is deactivated') != -1:
                action = 'delete_user'
            if action:
                # TODO try to move out
                message_for_pubsub = {'action': action, 'info': {'user': user_id}}
                publish_to_pubsub(Topics.topic_for_user_management, message_for_pubsub)
                logging.info(f'Identified user id {user_id} to do {action}')
            return 'cancelled'

        elif 420 <= response.status_code <= 429:  # 'Flood Control':
            logging.exception(f'Flood Control: message to {user_id} was not sent, {response.reason=}')
            return 'failed_flood_control'

        # issue425 if not response moved here from the 1st place because it reacted even on response 400
        elif not response:
            logging.info(f'response is None for {user_id=}; {call_context=}')
            return 'failed'

        else:
            logging.exception(f'UNKNOWN ERROR: message to {user_id} was not sent, {response.reason=}')
            return 'cancelled'

    except Exception as e:
        logging.exception(f'Response is corrupted. {response.json()=}')
        return 'failed'


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
