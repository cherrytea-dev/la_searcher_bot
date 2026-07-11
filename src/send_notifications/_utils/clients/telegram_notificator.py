"""Telegram notification client — wraps Telegram API calls for sending notifications."""

from typing import Any

from _dependencies.bot.telegram_api_wrapper import TGApiBase
from send_notifications._utils.database import MessageToSend


class TelegramNotificator:
    """Send notifications via Telegram API."""

    def __init__(self, tg_api: TGApiBase) -> None:
        self._tg_api = tg_api

    def send_text(self, user_id: int, content: str, message_params: dict[str, Any]) -> str | None:
        """Send a text message via Telegram API."""
        message_params['chat_id'] = user_id
        message_params['text'] = content
        return self._tg_api.send_message(message_params)

    def send_location(self, user_id: int, latitude: float, longitude: float) -> str | None:
        """Send coordinates via Telegram API."""
        return self._tg_api.send_location(user_id, str(latitude), str(longitude))

    def dispatch(
        self,
        message_to_send: MessageToSend,
        content: str,
        message_params: dict[str, Any],
    ) -> str | None:
        """Dispatch a message via Telegram."""
        user_id = message_to_send.user_id

        if message_to_send.message_type == 'text':
            return self.send_text(user_id, content, message_params)
        elif message_to_send.message_type == 'coords':
            return self.send_location(user_id, message_params['latitude'], message_params['longitude'])
        else:
            raise ValueError(f'unknown message_type: {message_to_send.message_type}')
