"""VK notification client — wraps VK API calls for sending notifications."""

import logging
from typing import Any

from _dependencies.bot.vk_api_client import VKApi
from send_notifications._utils.database import MessageToSend
from send_notifications._utils.helpers import format_mesage_for_vk


class VKNotificator:
    """Send notifications via VK API."""

    def __init__(self, vk_api: VKApi) -> None:
        self._vk_api = vk_api

    def send_text(self, recipient: str | int, message_to_send: MessageToSend, content: str) -> str | None:
        """Send a text message via VK API."""
        try:
            logging.info(f'Sending message to VK: {recipient=} {message_to_send=}')
            self._vk_api.send(recipient, message_to_send.message_id, format_mesage_for_vk(content))
            return 'completed'
        except Exception:
            logging.exception(f'Sending message to VK: failed {recipient=} {message_to_send=}')
            return 'failed'

    def send_coords(
        self,
        recipient: str | int,
        message_to_send: MessageToSend,
        latitude: float,
        longitude: float,
    ) -> str | None:
        """Send coordinates via VK API."""
        try:
            logging.info(f'Sending coordinates to VK: {recipient=} {message_to_send=}')
            self._vk_api.send(
                recipient,
                message_to_send.message_id,
                '',
                lat=str(latitude),
                long=str(longitude),
            )
            return 'completed'
        except Exception:
            logging.exception(f'Sending coordinates to VK: failed {recipient=} {message_to_send=}')
            return 'failed'

    def dispatch(
        self,
        message_to_send: MessageToSend,
        content: str,
        message_params: dict[str, Any],
    ) -> str | None:
        """Dispatch a message exclusively via VK (messenger == VK)."""
        recipient = message_to_send.vk_id or message_to_send.user_id

        if message_to_send.message_type == 'text':
            return self.send_text(recipient, message_to_send, content)
        elif message_to_send.message_type == 'coords':
            return self.send_coords(recipient, message_to_send, message_params['latitude'], message_params['longitude'])
        else:
            raise ValueError(f'unknown message_type for VK: {message_to_send.message_type}')
