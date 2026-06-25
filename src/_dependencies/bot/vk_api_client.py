import json
import logging
from functools import cache
from typing import Any

import httpx

from _dependencies.common.commons import get_app_config


class VkApiError(Exception):
    """Raised when VK API returns an error response.

    Attributes:
        error_code: VK API error code (e.g., 901, 914, 917)
        error_msg: Human-readable error message from VK API
    """

    # VK API error codes — defined here so all consumers use named constants
    UNKNOWN_ERROR = 1
    PARAM_ERROR = 100
    ACCESS_DENIED = 200
    CANNOT_SEND_TO_USER = 901
    CANNOT_SEND_FIRST_MESSAGE = 902
    FLOOD_CONTROL_PER_MINUTE = 914
    FLOOD_CONTROL_PER_DAY = 917

    def __init__(self, error_code: int, error_msg: str) -> None:
        self.error_code = error_code
        self.error_msg = error_msg
        super().__init__(f'VK API error {error_code}: {error_msg}')


class VKApi:
    API_VERSION = '5.199'

    def __init__(self, token: str):
        headers = {'Authorization': f'Bearer {token}'}
        self._session = httpx.Client(base_url='https://api.vk.ru/', headers=headers)

    def send(
        self,
        user_id: int | str,
        random_id: int,
        message: str = '',
        lat: str = '',
        long: str = '',
        keyboard: dict | None = None,
        attachment: str = '',
        dont_parse_links: bool = False,
    ) -> dict:
        """Send a message to a user or chat.

        https://dev.vk.com/ru/method/messages.send
        """
        params: dict[str, Any] = {
            'peer_id': user_id,
            'random_id': random_id,
            'v': self.API_VERSION,
            'message': message,
        }

        if keyboard is not None:
            params['keyboard'] = json.dumps(keyboard, ensure_ascii=False)

        if lat and long:
            params['lat'] = lat
            params['long'] = long

        if attachment:
            params['attachment'] = attachment

        if dont_parse_links:
            params['dont_parse_links'] = 1

        url = '/method/messages.send'
        resp = self._session.post(url, data=params)
        resp.raise_for_status()
        resp_data = resp.json()
        _handle_vk_error(resp_data)
        return resp_data

    def edit_message(
        self,
        peer_id: int,
        message_id: int | None = None,
        message: str = '',
        keyboard: dict | None = None,
        conversation_message_id: int | None = None,
    ) -> dict:
        """Edit a sent message.

        Uses conversation_message_id when available (preferred for inline
        callback events), falls back to message_id.

        https://dev.vk.com/ru/method/messages.edit
        """
        params: dict[str, Any] = {
            'peer_id': peer_id,
            'message': message,
            'v': self.API_VERSION,
        }

        if conversation_message_id is not None:
            params['conversation_message_id'] = conversation_message_id
        elif message_id is not None:
            params['message_id'] = message_id

        if keyboard is not None:
            params['keyboard'] = json.dumps(keyboard, ensure_ascii=False)

        url = '/method/messages.edit'
        resp = self._session.post(url, data=params)
        resp.raise_for_status()
        resp_data = resp.json()
        _handle_vk_error(resp_data)
        return resp_data

    def delete_message(self, peer_id: int, message_ids: list[int]) -> dict:
        """Delete messages.

        https://dev.vk.com/ru/method/messages.delete
        """
        query: dict[str, Any] = {
            'peer_id': peer_id,
            'message_ids': ','.join(str(mid) for mid in message_ids),
            'delete_for_all': 1,
            'v': self.API_VERSION,
        }
        url = '/method/messages.delete'
        resp = self._session.post(url, params=query)
        resp.raise_for_status()
        resp_data = resp.json()
        _handle_vk_error(resp_data)
        return resp_data

    def send_message_event_answer(
        self,
        event_id: str,
        user_id: int,
        peer_id: int,
        event_data: dict | None = None,
    ) -> dict:
        """Answer on a message event (callback from inline keyboard).

        https://dev.vk.com/ru/method/messages.sendMessageEventAnswer
        """
        query: dict[str, Any] = {
            'event_id': event_id,
            'user_id': user_id,
            'peer_id': peer_id,
            'v': self.API_VERSION,
        }
        payload: dict[str, Any] = {}

        if event_data is not None:
            payload['event_data'] = json.dumps(event_data, ensure_ascii=False)

        url = '/method/messages.sendMessageEventAnswer'
        resp = self._session.post(url, json=payload, params=query)
        resp.raise_for_status()
        resp_data = resp.json()
        _handle_vk_error(resp_data)
        return resp_data

    def get_user_id_by_login(
        self,
        login: str,
    ) -> dict:
        """Get user info by login.

        https://dev.vk.com/ru/method/users.get
        """
        query: dict[str, Any] = {
            'user_ids': login,
            'v': self.API_VERSION,
        }
        url = '/method/users.get'
        resp = self._session.get(url, params=query)
        resp.raise_for_status()
        resp_data = resp.json()
        _handle_vk_error(resp_data)
        return resp_data


def _handle_vk_error(resp_data: dict) -> None:
    """Check VK API response for errors and raise VkApiError if found.

    Raises:
        VkApiError: If the response contains an error block.
    """
    if 'error' not in resp_data:
        return

    error = resp_data['error']
    error_code = error.get('error_code')
    error_msg = error.get('error_msg', '')

    if error_code == VkApiError.UNKNOWN_ERROR:
        logging.error(f'VK API unknown error: {error_msg}')
    elif error_code == VkApiError.PARAM_ERROR:
        logging.error(f'VK API param error: {error_msg}')
    elif error_code == VkApiError.ACCESS_DENIED:
        logging.warning(f'VK API access denied (user blocked bot?): {error_msg}')
    elif error_code == VkApiError.CANNOT_SEND_TO_USER:
        logging.warning(f'VK API cannot send messages to user: {error_msg}')
    elif error_code == VkApiError.CANNOT_SEND_FIRST_MESSAGE:
        logging.warning(f'VK API cannot send first message to user: {error_msg}')
    elif error_code == VkApiError.FLOOD_CONTROL_PER_MINUTE:
        logging.warning(f'VK API flood control (per-minute): {error_msg}')
    elif error_code == VkApiError.FLOOD_CONTROL_PER_DAY:
        logging.warning(f'VK API flood control (per-day limit): {error_msg}')
    else:
        logging.error(f'VK API error {error_code}: {error_msg}')

    raise VkApiError(error_code=error_code, error_msg=error_msg)


@cache
def get_default_vk_api_client() -> VKApi:
    config = get_app_config()
    return VKApi(config.vk_api_key)
