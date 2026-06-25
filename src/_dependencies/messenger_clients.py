"""Messenger client implementations — Telegram and VK.

Wraps existing low-level API clients (``TGApiBase``, ``VKApi``)
into the abstract ``MessengerClient`` interface defined in
``_dependencies.commons``.

"""

from _dependencies.commons import Messenger, MessengerClient, SendResult, UserIdentity, get_app_config
from _dependencies.telegram_api_wrapper import TGApiBase
from _dependencies.vk_api_client import VKApi, VkApiError


class TelegramClient(MessengerClient):
    """MessengerClient implementation for Telegram.

    Delegates to ``TGApiBase`` from ``telegram_api_wrapper.py``.
    Handles blocking/deleting users on 403 responses.
    """

    messenger = Messenger.TELEGRAM

    def __init__(self, tg_api: TGApiBase | None = None) -> None:
        config = get_app_config()
        prod_token = config.bot_api_token__prod or config.bot_api_token
        self._api = tg_api or TGApiBase(prod_token, config.bot_api_host)

    def send_message(self, user_identity: UserIdentity, text: str, **kwargs: object) -> SendResult:
        params: dict = {
            'chat_id': user_identity.messenger_user_id,
            'text': text,
        }
        # Pop known Telegram-specific kwargs
        disable_preview = kwargs.pop('disable_web_page_preview', None)
        if disable_preview is not None:
            params['disable_web_page_preview'] = bool(disable_preview)

        params.update(kwargs)  # type: ignore[typeddict-item]

        status = self._api.send_message(params)
        return self._to_send_result(status)

    def send_coordinates(self, user_identity: UserIdentity, lat: float, lng: float) -> SendResult:
        status = self._api.send_location(int(user_identity.messenger_user_id), str(lat), str(lng))
        return self._to_send_result(status)

    @staticmethod
    def _to_send_result(status: str) -> SendResult:
        success_map = {
            'completed': True,
            'cancelled': False,
            'cancelled_bad_request': False,
            'failed': False,
            'failed_flood_control': False,
        }
        return SendResult(success=success_map.get(status, False), status=status)


class VKClient(MessengerClient):
    """MessengerClient implementation for VKontakte.

    Delegates to ``VKApi`` from ``vk_api_client.py``.
    Uses a random message_id as random_id (VK requirement).
    """

    messenger = Messenger.VK

    def __init__(self, vk_api: VKApi | None = None) -> None:
        import random

        self._random = random
        self._api = vk_api or VKApi(get_app_config().vk_api_key)

    def send_message(self, user_identity: UserIdentity, text: str, **kwargs: object) -> SendResult:
        try:
            self._api.send(
                user_id=user_identity.messenger_user_id,
                random_id=self._random.randint(0, 2**31),
                message=text,
                keyboard=kwargs.get('keyboard'),  # type: ignore[arg-type]
                attachment=kwargs.get('attachment', ''),  # type: ignore[arg-type]
                dont_parse_links=bool(kwargs.get('dont_parse_links', False)),
            )
            return SendResult(success=True, status='completed')
        except VkApiError as e:
            if e.error_code in (VkApiError.CANNOT_SEND_TO_USER, VkApiError.CANNOT_SEND_FIRST_MESSAGE):
                return SendResult(success=False, status='cancelled', status_code=e.error_code)
            elif e.error_code == VkApiError.FLOOD_CONTROL_PER_MINUTE:
                return SendResult(success=False, status='failed_flood_control', status_code=e.error_code)
            elif e.error_code == VkApiError.FLOOD_CONTROL_PER_DAY:
                return SendResult(success=False, status='cancelled', status_code=e.error_code)
            return SendResult(success=False, status='failed', status_code=e.error_code)
        except Exception:
            return SendResult(success=False, status='failed')

    def send_coordinates(self, user_identity: UserIdentity, lat: float, lng: float) -> SendResult:
        try:
            self._api.send(
                user_id=user_identity.messenger_user_id,
                random_id=self._random.randint(0, 2**31),
                message='',
                lat=str(lat),
                long=str(lng),
            )
            return SendResult(success=True, status='completed')
        except VkApiError:
            return SendResult(success=False, status='failed')
        except Exception:
            return SendResult(success=False, status='failed')
