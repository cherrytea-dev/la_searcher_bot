import logging
import os
import time
from functools import lru_cache
from typing import TYPE_CHECKING, Literal

from _dependencies.bot.vk_api_client import VkApiError, get_default_vk_api_client

from .keyboards import VKKeyboardLayouts

if TYPE_CHECKING:
    from _dependencies.bot.vk_api_client import VKApi


@lru_cache
def vk_sender() -> 'VKMessageSender':
    return VKMessageSender()


class VKMessageSender:
    """Wrapper around VKApi for sending messages with rate limiting and error handling.

    Analogous to communicate/_utils/message_sending.py but for VK.
    """

    _daily_limit_remaining: int | None = None

    def __init__(self, api: 'VKApi | None' = None) -> None:
        """Initialize with optional VKApi client.

        Args:
            api: VKApi client instance. If None, uses the default cached client.
                 This allows tests to inject a mock API client.
        """
        self._api = api

    def _get_api(self) -> 'VKApi':
        """Get the VKApi client, using injected one or default."""
        if self._api is not None:
            return self._api
        return get_default_vk_api_client()

    @staticmethod
    def _make_random_id() -> int:
        """Generate a unique random_id for VK API messages.send.

        VK requires unique random_id per message to prevent duplicates.
        Must be a signed 64-bit integer (int64).
        """
        raw = int.from_bytes(os.urandom(8), 'big', signed=False)
        # Mask to signed 64-bit range: [-(2^63), 2^63 - 1]
        return (raw & ((1 << 63) - 1)) * (-1 if raw & (1 << 63) else 1)

    def send_message(
        self,
        peer_id: int,
        text: str,
        keyboard: dict | None = None,
        attachment: str = '',
        dont_parse_links: bool = False,
    ) -> int | None:
        """Send a message. Returns message_id or None on failure.

        Handles per-minute flood control (914) with retry.
        Handles per-day flood control (917) by stopping.
        """
        if self._daily_limit_remaining is not None and self._daily_limit_remaining <= 0:
            logging.warning(f'VK daily message limit reached, skipping message to {peer_id}')
            return None

        random_id = self._make_random_id()
        for attempt in range(3):
            try:
                resp = self._get_api().send(
                    user_id=peer_id,
                    random_id=random_id,
                    message=text,
                    keyboard=keyboard,
                    attachment=attachment,
                    dont_parse_links=dont_parse_links,
                )
                # VK API messages.send returns {"response": <message_id_int>}
                response_data = resp.get('response')
                if isinstance(response_data, dict):
                    return response_data.get('message_id')
                return response_data

            except VkApiError as e:
                if e.error_code == VkApiError.FLOOD_CONTROL_PER_MINUTE and attempt < 2:
                    logging.warning(f'VK flood control (914), retrying in 1s (attempt {attempt + 1})')
                    time.sleep(1)
                    continue
                if e.error_code == VkApiError.FLOOD_CONTROL_PER_DAY:
                    self._daily_limit_remaining = 0
                    logging.error(f'VK daily limit reached (917), stopping sends')
                    return None
                if e.error_code in (VkApiError.CANNOT_SEND_TO_USER, VkApiError.CANNOT_SEND_FIRST_MESSAGE):
                    logging.warning(f'VK cannot send to user {peer_id}: {e.error_msg}')
                    return None
                logging.exception(f'VK send_message failed to {peer_id}: error {e.error_code}: {e.error_msg}')
                return None
            except Exception:
                logging.exception(f'VK send_message failed to {peer_id}: unexpected error')
                return None

        return None

    def edit_message(
        self,
        peer_id: int,
        message_id: int | None = None,
        text: str = '',
        keyboard: dict | None = None,
        conversation_message_id: int | None = None,
    ) -> bool:
        """Edit a sent message. Returns True on success.

        Uses conversation_message_id when provided (preferred for inline
        callback events), falls back to message_id.
        """
        try:
            self._get_api().edit_message(
                peer_id=peer_id,
                message_id=message_id,
                message=text,
                keyboard=keyboard,
                conversation_message_id=conversation_message_id,
            )
            return True
        except Exception:
            logging.exception(f'VK edit_message failed: peer_id={peer_id}, message_id={message_id}')
            return False

    def delete_message(self, peer_id: int, message_ids: list[int]) -> bool:
        """Delete messages. Returns True on success."""
        try:
            self._get_api().delete_message(
                peer_id=peer_id,
                message_ids=message_ids,
            )
            return True
        except Exception:
            logging.exception(f'VK delete_message failed: peer_id={peer_id}')
            return False

    def send_callback_answer(
        self,
        event_id: str,
        user_id: int,
        peer_id: int,
        event_data: dict | None = None,
    ) -> bool:
        """Answer on a callback from inline button (show snackbar to user).

        Args:
            event_data: Optional dict for VK callback answer.
                Use {'type': 'show_snackbar', 'text': '...'} to show a brief notification,
                or {'type': 'show_message', 'text': '...'} for a persistent popup.

        Returns True on success.
        """
        try:
            self._get_api().send_message_event_answer(
                event_id=event_id,
                user_id=user_id,
                peer_id=peer_id,
                event_data=event_data,
            )
            return True
        except Exception:
            logging.exception(f'VK send_callback_answer failed')
            return False

    def send_with_keyboard(
        self,
        peer_id: int,
        text: str,
        buttons: list[str],
        color: Literal['primary', 'secondary', 'positive', 'negative'] = 'secondary',
    ) -> int | None:
        """Convenience method: text + list of buttons in one column."""
        keyboard = VKKeyboardLayouts.one_column(buttons, color=color)
        return self.send_message(peer_id, text, keyboard=keyboard)
