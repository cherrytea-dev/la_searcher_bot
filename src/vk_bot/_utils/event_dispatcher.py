"""VK event dispatcher — routes incoming VK Callback API events to handlers.

The dispatcher handles three stages:
1. Extract event_type and event_object from the raw VK event
2. Deduplicate (VK may resend events on timeout)
3. Route to the appropriate handler based on event_type

Event types:
- ``confirmation`` — VK server handshake (synchronous, returns confirmation code)
- ``message_new`` — new user message → :func:`message_processing.handle_new_message`
- ``message_event`` — inline keyboard callback → :func:`message_processing.handle_callback_event`
- ``message_edit`` / ``message_reply`` — ignored (bot's own echo)
"""

import logging
import time
from collections import OrderedDict
from typing import Callable

from _dependencies.common.commons import get_app_config

from .common import VKMessage
from .handler_chain import handle_unknown  # noqa: F401 — re-exported via dispatcher
from .message_processing import handle_callback_event, handle_new_message
from .message_sending import vk_sender


class VKEventDispatcher:
    """Диспетчер событий VK Callback API.

    Разделяет обработку входящего события на три стадии:
    1. Извлечение event_type и event_object
    2. Дедупликация (VK может пересылать события при таймауте)
    3. Маршрутизация к профильному обработчику через словарь _handlers

    Исключение: confirmation-рукопожатие обрабатывается синхронно
    и возвращает код подтверждения, а не 'ok'.
    """

    _EVENT_CACHE_MAX_SIZE = 1000

    def __init__(self) -> None:
        self._event_cache: OrderedDict[str, float] = OrderedDict()
        self._handlers: dict[str, Callable[[dict], str]] = {
            'message_new': self._handle_message_new,
            'message_edit': self._handle_message_edit,
            'message_event': self._handle_message_event,
            'message_reply': self._handle_message_reply,
        }

    def dispatch(self, raw_event: dict) -> str:
        event_type = raw_event.get('type', '')
        logging.info(f'dispatch_event: received event type={event_type}')

        if event_type == 'confirmation':
            return self._handle_confirmation(raw_event)

        event_object = raw_event.get('object', {})
        if not event_object:
            logging.warning(f'VK event without object: {raw_event}')
            return 'ok'

        if self._is_duplicate(event_type, event_object):
            return 'ok'

        handler = self._handlers.get(event_type)
        if handler is not None:
            return handler(event_object)

        logging.debug(f'Unhandled VK event type: {event_type}')
        return 'ok'

    def _handle_confirmation(self, raw_event: dict) -> str:
        """Handle VK Callback API confirmation handshake.

        This is the only handler that returns a non-'ok' value:
        the server must return the confirmation code synchronously
        within the HTTP response, or VK won't complete the handshake.
        """
        config = get_app_config()
        expected_group_id = config.vk_group_id
        if raw_event.get('group_id') == expected_group_id:
            return config.vk_confirmation_code
        logging.warning(f'Unexpected group_id in confirmation: {raw_event.get("group_id")}')
        return 'ok'

    def _is_duplicate(self, event_type: str, event_object: dict) -> bool:
        """Check if an event has already been processed (deduplication).

        VK may resend events if the server doesn't respond within 8 seconds,
        or due to network issues. This cache prevents processing the same
        event twice.

        Uses OrderedDict for LRU-style eviction when the cache exceeds the
        max size — oldest entries are removed first, preserving the most
        recent entries for deduplication.
        """
        event_id = event_object.get('event_id') or ''
        if event_type == 'message_new':
            message_data = event_object.get('message', {}) or {}
            event_id = str(message_data.get('conversation_message_id', ''))
        if not event_id:
            return False
        if event_id in self._event_cache:
            return True
        self._event_cache[event_id] = time.time()
        # LRU-style eviction: remove oldest entries when over limit
        while len(self._event_cache) > self._EVENT_CACHE_MAX_SIZE:
            self._event_cache.popitem(last=False)
        return False

    def _handle_message_new(self, event_object: dict) -> str:
        """Process a new message event.

        Extracts message data, wraps in VKMessage, and delegates
        to handle_new_message() for handler chain processing.
        """
        message_data = event_object.get('message', {})
        if not message_data:
            logging.warning('message_new event without message data')
            return 'ok'

        msg_text = message_data.get('text', '')
        msg_from_id = message_data.get('from_id', 0)
        msg_id = message_data.get('id')
        logging.info(f'dispatch_event: message_new from_id={msg_from_id}, msg_id={msg_id}, text="{msg_text}"')

        vk_message = VKMessage(
            text=msg_text,
            user_id=msg_from_id,
            peer_id=message_data.get('peer_id', 0),
            message_id=msg_id,
        )

        handle_new_message(vk_message, sender=vk_sender())
        return 'ok'

    def _handle_message_edit(self, event_object: dict) -> str:
        """Handle message_edit — ignore, since the bot only edits messages
        programmatically (e.g., updating inline keyboards). Processing
        message_edit would re-trigger the handler chain and could cause
        duplicate messages (e.g., re-sending the district selection).
        """
        logging.debug('Ignoring message_edit event (bot-edited message)')
        return 'ok'

    def _handle_message_event(self, event_object: dict) -> str:
        """Process an inline keyboard callback event.

        Extracts payload and message identifiers, wraps in VKMessage,
        and delegates to handle_callback_event().
        """
        raw_payload = event_object.get('payload')
        logging.info(
            f'dispatch_event: message_event user_id={event_object.get("user_id")}, '
            f'message_id={event_object.get("message_id")}, '
            f'conversation_message_id={event_object.get("conversation_message_id")}, '
            f'payload={raw_payload}'
        )
        vk_message = VKMessage(
            text='',
            user_id=event_object.get('user_id', 0),
            peer_id=event_object.get('peer_id', 0),
            message_id=event_object.get('message_id'),
            conversation_message_id=event_object.get('conversation_message_id'),
            payload=raw_payload,
            event_id=event_object.get('event_id'),
        )

        handle_callback_event(vk_message, sender=vk_sender())
        return 'ok'

    def _handle_message_reply(self, event_object: dict) -> str:
        """Handle message_reply — VK sends this when the bot sends a message (echo).

        from_id is the negative group ID for bot's own messages.
        We must NOT process this as a user message — just ignore it.
        """
        msg_from_id = event_object.get('from_id', 0)
        msg_text = event_object.get('text', '')[:80]
        logging.info(f'dispatch_event: message_reply from_id={msg_from_id}, text="{msg_text}" — ignoring (bot echo)')
        return 'ok'


dispatcher = VKEventDispatcher()
dispatch_event = dispatcher.dispatch
