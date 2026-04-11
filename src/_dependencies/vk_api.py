from functools import cache
from typing import Any

import httpx

from _dependencies.commons import get_app_config


class VKApi:
    API_VERSION = '5.199'

    def __init__(self, token: str):
        headers = {'Authorization': f'Bearer {token}'}
        self._session = httpx.Client(base_url='https://api.vk.ru/', headers=headers)

    def send(
        self,
        user_id: str,
        random_id: int,
        message: str = '',
        lat: str = '',
        long: str = '',
        keyboard: str = '',
    ) -> dict:
        # https://dev.vk.com/ru/method/messages.send
        query: dict[str, Any] = {
            'peer_id': user_id,
            'random_id': random_id,
            'v': self.API_VERSION,
            'lat': lat,
            'long': long,
            'message': message,
            # 'parse_mode': 'markdown_v2',
            # 'keyboard': '',  # https://dev.vk.com/ru/api/bots/development/keyboard
        }
        payload: dict[str, Any] = {
            # 'keyboard': keyboard,
        }
        url = '/method/messages.send'
        resp = self._session.post(url, json=payload, params=query)
        resp.raise_for_status()
        resp_data = resp.json()
        assert 'error' not in resp_data
        return resp_data

    def ge_user_id_by_login(
        self,
        login: str,
    ) -> dict:
        # https://dev.vk.com/ru/method/users.get

        query: dict[str, Any] = {
            'user_ids': login,
            'v': self.API_VERSION,
        }
        url = '/method/users.get'
        resp = self._session.get(url, params=query)
        resp.raise_for_status()
        resp_data = resp.json()
        assert 'error' not in resp_data
        return resp_data


@cache
def get_default_vk_api_client() -> VKApi:
    config = get_app_config()
    return VKApi(config.vk_api_key)
