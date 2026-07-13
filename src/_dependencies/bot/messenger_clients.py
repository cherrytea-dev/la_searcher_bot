"""Messenger client implementations — Telegram, VK, and MAX.

Wraps existing low-level API clients (``TGApiBase``, ``VKApi``, ``maxapi.Bot``)
into the abstract ``MessengerClient`` interface defined in
``_dependencies.commons``.

"""

import asyncio
import random
from collections.abc import Coroutine
from typing import Any, cast

from maxapi import Bot as MaxBot
from maxapi.enums import ParseMode

from _dependencies.bot.telegram_api_wrapper import TGApiBase
from _dependencies.bot.vk_api_client import VKApi, VkApiError
from _dependencies.common.commons import Messenger, MessengerClient, SendResult, UserIdentity, get_app_config
from _dependencies.common.telegram_message import TelegramMessage


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
        message = TelegramMessage(
            text=text,
            parse_mode=cast('str | None', kwargs.get('parse_mode')),
            disable_web_page_preview=cast('bool | None', kwargs.get('disable_web_page_preview')),
            reply_markup=kwargs.get('reply_markup'),
        )
        user_id = int(user_identity.messenger_user_id)
        status = self._api.send_message(user_id, message)
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

    Can be used as a context manager to ensure the underlying aiohttp
    session is properly closed::

        with MaxClient() as client:
            client.send_message(...)

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

    def __enter__(self) -> 'MaxClient':
        """Create a persistent event loop and ensure the aiohttp session.

        The event loop is reused across all ``send_message`` / ``send_coordinates``
        calls within the ``with`` block. The session is created once and closed
        once in ``__exit__``, preventing ``Unclosed client session`` warnings.
        """
        self._loop = asyncio.new_event_loop()
        self._loop.run_until_complete(self._bot.ensure_session())
        return self

    def __exit__(self, *args: object) -> None:
        """Close the underlying aiohttp session and event loop."""
        try:
            session = self._bot.session
            if session is not None and not session.closed:
                self._loop.run_until_complete(self._bot.close_session())
        finally:
            self._loop.close()

    def _run_and_close(self, coro: Coroutine[Any, Any, Any]) -> None:
        """Run an async coroutine, using the context manager's event loop if available.

        When used inside a ``with MaxClient() as client:`` block, the persistent
        event loop from ``__enter__`` is reused — the session stays alive across
        calls and is only closed once in ``__exit__``.

        Fallback (no context manager): creates a fresh session, runs the coroutine,
        and closes the session within its own ``asyncio.run()``.
        """
        loop = getattr(self, '_loop', None)
        if loop is not None and not loop.is_closed():
            # Inside a ``with`` block — session already exists from __enter__
            loop.run_until_complete(coro)
        else:
            # Standalone usage — one-shot: create, run, close
            async def _wrapped() -> None:
                await self._bot.ensure_session()
                try:
                    await coro
                finally:
                    await self._bot.close_session()

            asyncio.run(_wrapped())

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

            parse_mode: ParseMode | None = None
            if parse_mode_str:
                parse_mode = ParseMode(parse_mode_str)

            self._run_and_close(
                self._bot.send_message(
                    user_id=user_id,
                    text=text,
                    parse_mode=parse_mode,
                )
            )
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

            self._run_and_close(
                self._bot.send_message(
                    user_id=user_id,
                    text=text,
                )
            )
            return SendResult(success=True, status='completed')
        except ValueError:
            return SendResult(success=False, status='cancelled_bad_request')
        except Exception:
            return SendResult(success=False, status='failed')
