import hashlib
import json
import logging

import requests
from requests.models import Response
from retry.api import retry_call
from telegram import TelegramObject
from yarl import URL

from _dependencies.bot.users_management import ManageUserAction, update_user_status
from _dependencies.common.commons import get_app_config
from _dependencies.common.telegram_message import TelegramMessage


class TelegramTransientError(Exception):
    """Raised when Telegram API returns a transient error (503, connection reset, etc.)
    that should be retried."""


class TGApiBase:
    def __init__(self, token: str, host: str = '') -> None:
        self._token = token
        self._session = requests.Session()
        self._host = host or 'https://api.telegram.org'

    @property
    def bot_api_path_start(self) -> URL:
        return URL(self._host) / f'bot{self._token}'

    def leave_chat(self, user_id: int) -> None:
        self._make_api_call('leaveChat', {'chat_id': user_id})

    def send_callback_answer_to_api(self, user_id: int, callback_query_id: str, message: str) -> None:
        try:
            # NB! only 200 characters
            message = message[:200]

            url = self.bot_api_path_start / 'answerCallbackQuery'
            query_params = {'callback_query_id': callback_query_id, 'text': message}
            url = url.with_query(query_params)

            response = self._session.get(str(url))
            self._process_response_of_api_call(user_id, response)
        except Exception:
            logging.exception('Error in getting response from Telegram')

    def send_message(self, user_id: int, message: TelegramMessage, call_context: str = '') -> str:
        params = _build_telegram_params(user_id, message)
        try:
            response = retry_call(
                self._make_api_call,
                fkwargs=dict(method='sendMessage', params=params, call_context=call_context),
                exceptions=TelegramTransientError,
                tries=3,
                delay=1,
                backoff=2,
                jitter=(0, 1),
            )
            return self._process_response_of_api_call(user_id, response)
        except TelegramTransientError:
            logging.exception(f'All retries exhausted for sendMessage to user {user_id}')
            return 'failed'

    def send_location(self, user_id: int, latitude: str, longitude: str) -> str:
        params = {'chat_id': user_id, 'latitude': latitude, 'longitude': longitude}
        response = self._make_api_call('sendLocation', params)
        return self._process_response_of_api_call(user_id, response)

    def edit_message_text(self, user_id: int, message: TelegramMessage, call_context: str = '') -> str:
        params = _build_telegram_params(user_id, message)
        if message.message_id is not None:
            params['message_id'] = message.message_id
        response = self._make_api_call('editMessageText', params, call_context)
        return self._process_response_of_api_call(user_id, response)

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

        url = self.bot_api_path_start / method  # e.g. sendMessage
        headers = {'Content-Type': 'application/json'}

        if 'reply_markup' in params and isinstance(params['reply_markup'], TelegramObject):
            params['reply_markup'] = params['reply_markup'].to_dict()

        json_params = json.dumps(params)

        json_size = len(json_params.encode('utf-8'))
        logging.info(
            f'_make_api_call: method={method}, json_body_size={json_size} bytes, '
            f'chat_id={params.get("chat_id") or params.get("scope", {}).get("chat_id", "?")}, '
            f'call_context={call_context}'
        )

        try:
            response = retry_call(
                self._session.post,
                fargs=[str(url)],
                fkwargs=dict(data=json_params, headers=headers),
                tries=3,
            )
            logging.debug(f'After session.post: {response=}; {call_context=}')
        except Exception:
            response = None
            logging.exception('Error in getting response from Telegram')

        logging.debug(f'Before return: {response=}; {call_context=}')

        # Detect transient errors (503, connection resets) for upper-level retry
        if response is not None and response.status_code == 503:
            raise TelegramTransientError(
                f'Telegram API returned 503: {response.reason}. ' f'body={response.text[:500]!r}'
            )

        return response

    def _process_response_of_api_call(self, user_id: int, response: Response | None, call_context: str = '') -> str:
        """process response received as a result of Telegram API call while sending message/location"""

        if response is None:
            logging.error('Response is corrupted')
            return 'failed'

        try:
            response_json = response.json()
        except Exception:
            # Diagnostic logging: capture response details before the JSON parse fails
            logging.exception(
                'Response JSON parse failed. '
                f'status_code={response.status_code}, '
                f'reason={response.reason!r}, '
                f'headers={dict(response.headers)!r}, '
                f'content_length={len(response.content)}, '
                f'text_preview={response.text[:500]!r}, '
                f'user_id={user_id}, '
                f'call_context={call_context}'
            )
            return 'failed'

        try:
            if 'ok' not in response_json:
                logging.error(f'ALARM! "ok" is not in response: {response_json}, user {user_id}')
                return 'failed'

            if response.ok:
                logging.info(f'message to {user_id} was successfully sent')
                return 'completed'

            elif response.status_code == 400:  # Bad Request
                description = response_json.get('description', '')
                if 'message is not modified' in description:
                    logging.info(f'message not modified for user {user_id} (no-op), {response_json=}')
                    return 'completed'
                logging.exception(f'Bad Request: message to {user_id} was not sent, {response_json=}')
                return 'cancelled_bad_request'

            elif response.status_code == 403:  # FORBIDDEN
                logging.info(f'Forbidden: message to {user_id} was not sent, {response.reason=}')
                if response.text.find('bot was blocked by the user') != -1:
                    # TODO try to move out
                    update_user_status(ManageUserAction.block_user, user_id)
                if response.text.find('user is deactivated') != -1:
                    # TODO try to move out
                    update_user_status(ManageUserAction.delete_user, user_id)
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

        except Exception:
            logging.exception(f'Response is corrupted. {response_json=}')
            return 'failed'


def _build_telegram_params(user_id: int, message: TelegramMessage) -> dict:
    """Build a Telegram API params dict from a user_id and TelegramMessage."""
    return {'chat_id': user_id, **message.to_telegram_params()}


def make_invite_text_for_user(user_id: int | str) -> str:
    invite_secret = f'{user_id}{get_app_config().bot_api_token__prod}'
    secret_hash = hashlib.sha256(invite_secret.encode()).hexdigest()
    user_invite_text = f'telegram_id: {user_id} invite_hash: {secret_hash}'
    return user_invite_text
