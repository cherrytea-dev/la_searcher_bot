import logging
import os
import time
from functools import lru_cache
from typing import TYPE_CHECKING, Literal

from _dependencies.vk_api_client import get_default_vk_api_client

from .keyboards import VKKeyboard

if TYPE_CHECKING:
    from _dependencies.vk_api_client import VKApi


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
        Using 64-bit random value to minimize collision probability.
        """
        return int.from_bytes(os.urandom(8), 'big', signed=False)

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
                return resp.get('response', {}).get('message_id')

            except Exception as e:
                error_str = str(e)
                if '914' in error_str and attempt < 2:
                    # Per-minute flood control — retry after 1 second
                    logging.warning(f'VK flood control (914), retrying in 1s (attempt {attempt + 1})')
                    time.sleep(1)
                    continue
                if '917' in error_str:
                    # Per-day flood control — stop for this session
                    self._daily_limit_remaining = 0
                    logging.error(f'VK daily limit reached (917), stopping sends')
                    return None
                if '901' in error_str or '902' in error_str:
                    logging.warning(f'VK cannot send to user {peer_id}: {error_str}')
                    return None
                logging.exception(f'VK send_message failed to {peer_id}')
                return None

        return None

    def edit_message(
        self,
        peer_id: int,
        message_id: int,
        text: str,
        keyboard: dict | None = None,
    ) -> bool:
        """Edit a sent message. Returns True on success."""
        try:
            self._get_api().edit_message(
                peer_id=peer_id,
                message_id=message_id,
                message=text,
                keyboard=keyboard,
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
    ) -> bool:
        """Answer on a callback from inline button (show snackbar to user).

        Returns True on success.
        """
        try:
            self._get_api().send_message_event_answer(
                event_id=event_id,
                user_id=user_id,
                peer_id=peer_id,
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
        keyboard = VKKeyboard.one_column(buttons, color=color)
        return self.send_message(peer_id, text, keyboard=keyboard)
