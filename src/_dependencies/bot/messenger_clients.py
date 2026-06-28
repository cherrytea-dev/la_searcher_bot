"""Messenger client implementations — Telegram, VK, and MAX.

Wraps existing low-level API clients (``TGApiBase``, ``VKApi``, ``maxapi.Bot``)
into the abstract ``MessengerClient`` interface defined in
``_dependencies.commons``.

"""

import asyncio
import random
from typing import cast

from maxapi import Bot as MaxBot

from _dependencies.bot.telegram_api_wrapper import TGApiBase
from _dependencies.bot.vk_api_client import VKApi, VkApiError
from _dependencies.common.commons import Messenger, MessengerClient, SendResult, UserIdentity, get_app_config


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
        params: dict[str, object] = {
            'chat_id': user_identity.messenger_user_id,
            'text': text,
        }
        # Pop known Telegram-specific kwargs
        disable_preview = kwargs.pop('disable_web_page_preview', None)
        if disable_preview is not None:
            params['disable_web_page_preview'] = bool(disable_preview)

        params.update(kwargs)

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
        self._random = random
        self._api = vk_api or VKApi(get_app_config().vk_api_key)

    def send_message(self, user_identity: UserIdentity, text: str, **kwargs: object) -> SendResult:
        try:
            keyboard = cast('dict | None', kwargs.get('keyboard'))
            attachment = cast('str', kwargs.get('attachment', ''))
            self._api.send(
                user_id=user_identity.messenger_user_id,
                random_id=self._random.randint(0, 2**31),
                message=text,
                keyboard=keyboard,
                attachment=attachment,
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


class MaxClient(MessengerClient):
    """MessengerClient implementation for MAX messenger.

    Wraps ``maxapi.Bot`` from the ``maxapi`` library.
    The maxapi library is fully async, so synchronous ``send_message``
    and ``send_coordinates`` calls are bridged via ``asyncio.run()``.

    NOTE: This is a minimal integration for sending notifications.
    Full interactive bot features (Dispatcher, webhooks, FSM) will
    be added separately in a dedicated MAX bot module.
    """

    messenger = Messenger.MAX

    def __init__(self, bot_instance: MaxBot | None = None) -> None:
        """Initialize with an optional pre-configured maxapi.Bot.

        If no bot is provided, creates one using ``MAX_BOT_TOKEN``
        from the app config (reads ``MAX_BOT_TOKEN`` env var).
        """
        if bot_instance is not None:
            self._bot: MaxBot = bot_instance
        else:
            self._bot = MaxBot()

    def send_message(self, user_identity: UserIdentity, text: str, **kwargs: object) -> SendResult:
        """Send a text message to a MAX user.

        The ``user_identity.messenger_user_id`` is the MAX user ID
        (integer as string).

        Supported kwargs:
            - ``parse_mode``: ``'markdown'`` or ``'html'`` (passed to maxapi)
        """
        try:
            user_id = int(user_identity.messenger_user_id)
            parse_mode_str = cast('str | None', kwargs.get('parse_mode'))

            from maxapi.enums import ParseMode

            parse_mode: ParseMode | None = None
            if parse_mode_str:
                parse_mode = ParseMode(parse_mode_str)

            async def _send() -> None:
                await self._bot.send_message(
                    user_id=user_id,
                    text=text,
                    parse_mode=parse_mode,
                )

            asyncio.run(_send())
            return SendResult(success=True, status='completed')
        except ValueError:
            return SendResult(success=False, status='cancelled_bad_request')
        except Exception:
            return SendResult(success=False, status='failed')

    def send_coordinates(self, user_identity: UserIdentity, lat: float, lng: float) -> SendResult:
        """Send location coordinates to a MAX user.

        MAX API does not have a dedicated location message type,
        so coordinates are sent as a text message with a link to
        the location.
        """
        try:
            user_id = int(user_identity.messenger_user_id)
            maps_url = f'https://yandex.ru/maps/?pt={lng},{lat}&z=15&l=map'
            text = f'📍 Координаты: {lat}, {lng}\n{maps_url}'

            async def _send() -> None:
                await self._bot.send_message(
                    user_id=user_id,
                    text=text,
                )

            asyncio.run(_send())
            return SendResult(success=True, status='completed')
        except ValueError:
            return SendResult(success=False, status='cancelled_bad_request')
        except Exception:
            return SendResult(success=False, status='failed')
