"""MAX notification client — wraps MAX API calls for sending notifications."""

import logging
from typing import Any

from _dependencies.bot.messenger_clients import MaxClient
from _dependencies.common.commons import Messenger, UserIdentity
from send_notifications._utils.database import MessageToSend


class MaxNotificator:
    """Send notifications via MAX API."""

    def __init__(self, max_client: MaxClient) -> None:
        self._max_client = max_client

    def _build_identity(self, message_to_send: MessageToSend, recipient: str) -> UserIdentity:
        return UserIdentity(
            internal_user_id=message_to_send.user_id,
            messenger=Messenger.MAX,
            messenger_user_id=recipient,
        )

    def send_text(self, message_to_send: MessageToSend, content: str) -> str | None:
        """Send a text message via MAX API."""
        recipient = message_to_send.max_id or str(message_to_send.user_id)
        try:
            logging.info(f'Sending message to MAX: {recipient=} {message_to_send=}')
            user_identity = self._build_identity(message_to_send, recipient)
            result = self._max_client.send_message(user_identity, content, parse_mode='html')
            return result.status
        except Exception:
            logging.exception(f'Sending message to MAX: failed {recipient=} {message_to_send=}')
            return 'failed'

    def send_coords(self, message_to_send: MessageToSend, latitude: float, longitude: float) -> str | None:
        """Send coordinates via MAX API."""
        recipient = message_to_send.max_id or str(message_to_send.user_id)
        try:
            logging.info(f'Sending coordinates to MAX: {recipient=} {message_to_send=}')
            user_identity = self._build_identity(message_to_send, recipient)
            result = self._max_client.send_coordinates(
                user_identity,
                lat=latitude,
                lng=longitude,
            )
            return result.status
        except Exception:
            logging.exception(f'Sending coordinates to MAX: failed {recipient=} {message_to_send=}')
            return 'failed'

    def dispatch(
        self,
        message_to_send: MessageToSend,
        content: str,
        message_params: dict[str, Any],
    ) -> str | None:
        """Dispatch a message exclusively via MAX (messenger == MAX)."""
        if message_to_send.message_type == 'text':
            return self.send_text(message_to_send, content)
        elif message_to_send.message_type == 'coords':
            return self.send_coords(message_to_send, message_params['latitude'], message_params['longitude'])
        else:
            raise ValueError(f'unknown message_type for MAX: {message_to_send.message_type}')
