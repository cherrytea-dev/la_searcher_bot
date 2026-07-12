"""Telegram notification client — wraps Telegram API calls for sending notifications."""

from _dependencies.bot.telegram_api_wrapper import TGApiBase
from _dependencies.common.message_params import MessageParams
from _dependencies.common.telegram_message import TelegramMessage
from send_notifications._utils.database import MessageToSend


class TelegramNotificator:
    """Send notifications via Telegram API."""

    def __init__(self, tg_api: TGApiBase) -> None:
        self._tg_api = tg_api

    def send_text(self, user_id: int, content: str, message_params: MessageParams) -> str | None:
        """Send a text message via Telegram API."""
        message = TelegramMessage(
            text=content,
            parse_mode=message_params.parse_mode,
            disable_web_page_preview=message_params.disable_web_page_preview,
            reply_markup=message_params.reply_markup,
        )
        return self._tg_api.send_message(user_id, message)

    def send_location(self, user_id: int, latitude: float, longitude: float) -> str | None:
        """Send coordinates via Telegram API."""
        return self._tg_api.send_location(user_id, str(latitude), str(longitude))

    def dispatch(
        self,
        message_to_send: MessageToSend,
        content: str,
        message_params: MessageParams,
    ) -> str | None:
        """Dispatch a message via Telegram."""
        user_id = message_to_send.user_id
        assert message_params.kind in ('text', 'coords')

        if message_params.kind == 'text':
            return self.send_text(user_id, content, message_params)
        else:
            return self.send_location(user_id, message_params.latitude, message_params.longitude)  # type: ignore[arg-type]
