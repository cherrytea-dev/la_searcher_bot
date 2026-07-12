"""MAX notification client — wraps MAX API calls for sending notifications."""

import logging

from _dependencies.bot.messenger_clients import MaxClient
from _dependencies.common.commons import Messenger, UserIdentity
from send_notifications._utils.database import MessageToSend
from send_notifications._utils.models import MessageParams


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
        message_params: MessageParams,
    ) -> str | None:
        """Dispatch a message exclusively via MAX (messenger == MAX)."""
        assert message_params.kind in ('text', 'coords')

        if message_params.kind == 'text':
            return self.send_text(message_to_send, content)
        else:
            return self.send_coords(
                message_to_send,
                message_params.latitude,  # type: ignore[arg-type]
                message_params.longitude,  # type: ignore[arg-type]
            )
