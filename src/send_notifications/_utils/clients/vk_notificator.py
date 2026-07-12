"""VK notification client — wraps VK API calls for sending notifications."""

import logging

from _dependencies.bot.vk_api_client import VKApi
from _dependencies.common.message_params import MessageParams
from send_notifications._utils.database import MessageToSend
from send_notifications._utils.helpers import format_message_for_vk


class VKNotificator:
    """Send notifications via VK API."""

    def __init__(self, vk_api: VKApi) -> None:
        self._vk_api = vk_api

    def send_text(self, recipient: str | int, message_to_send: MessageToSend, content: str) -> str | None:
        """Send a text message via VK API."""
        try:
            logging.info(f'Sending message to VK: {recipient=} {message_to_send=}')
            self._vk_api.send(recipient, message_to_send.message_id, format_message_for_vk(content))
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
        message_params: MessageParams,
    ) -> str | None:
        """Dispatch a message exclusively via VK (messenger == VK)."""
        recipient = message_to_send.vk_id or message_to_send.user_id
        assert message_params.kind in ('text', 'coords')

        if message_params.kind == 'text':
            return self.send_text(recipient, message_to_send, content)
        else:
            return self.send_coords(
                recipient,
                message_to_send,
                message_params.latitude,  # type: ignore[arg-type]
                message_params.longitude,  # type: ignore[arg-type]
            )
