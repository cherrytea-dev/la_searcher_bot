import json
import logging
import urllib.parse

import requests
from requests.models import Response
from retry.api import retry_call
from telegram import TelegramObject

from _dependencies.pubsub import pubsub_user_management


class TGApiBase:
    def __init__(self, token: str) -> None:
        self._token = token
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

            self._process_response_of_api_call(user_id, response)
        except Exception:
            logging.exception('Error in getting response from Telegram')

    def send_message(self, params: dict, call_context: str = '') -> str:
        response = self._make_api_call('sendMessage', params, call_context)
        user_id = params['chat_id']
        return self._process_response_of_api_call(user_id, response)

    def send_location(self, user_id: int, latitude: str, longitude: str) -> str:
        # request_text = f'https://api.telegram.org/bot{bot_token}/sendLocation?chat_id={user_id}{latitude}{longitude}'

        params = {'chat_id': user_id, 'latitude': latitude, 'longitude': longitude}
        response = self._make_api_call('sendLocation', params)
        return self._process_response_of_api_call(user_id, response)

    def edit_message_text(self, params: dict, call_context: str = '') -> None:
        response = self._make_api_call('editMessageText', params, call_context)
        user_id = params['chat_id']
        self._process_response_of_api_call(user_id, response)

    def delete_message(self, chat_id: int, message_id: int) -> requests.Response | None:
        params = {'chat_id': chat_id, 'message_id': message_id}

        return self._make_api_call('deleteMessage', params)

    def set_my_commands(self, chat_id: int, commands: list, call_context: str = '') -> None:
        params = {'commands': commands, 'scope': {'type': 'chat', 'chat_id': chat_id}}
        response = self._make_api_call('setMyCommands', params, call_context)
        result = self._process_response_of_api_call(chat_id, response)
        logging.info(f'hiding user {chat_id} menu status = {result}')

    def delete_my_commands(self, chat_id: int) -> None:
        params = {'scope': {'type': 'chat', 'chat_id': chat_id}}
        response = self._make_api_call('deleteMyCommands', params)
        self._process_response_of_api_call(chat_id, response)

    def edit_message_reply_markup(self, chat_id: int, last_inline_message_id: int, call_context: str = '') -> None:
        params = {'chat_id': chat_id, 'message_id': last_inline_message_id}
        self._make_api_call('editMessageReplyMarkup', params, call_context)

    def _make_api_call(self, method: str, params: dict, call_context: str = '') -> requests.Response | None:
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

        json_params = json.dumps(params)

        try:
            response = retry_call(
                self._session.post,
                fargs=[url],
                fkwargs=dict(data=json_params, headers=headers),
                tries=3,
            )
            logging.debug(f'After session.post: {response=}; {call_context=}')
        except Exception as e:
            response = None
            logging.exception('Error in getting response from Telegram')

        logging.debug(f'Before return: {response=}; {call_context=}')
        return response

    def _process_response_of_api_call(self, user_id: int, response: Response | None, call_context: str = '') -> str:
        """process response received as a result of Telegram API call while sending message/location"""

        if response is None:
            logging.error('Response is corrupted')
            return 'failed'

        try:
            if 'ok' not in response.json():
                logging.error(f'ALARM! "ok" is not in response: {response.json()}, user {user_id}')
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
                    pubsub_user_management(user_id, action)
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
