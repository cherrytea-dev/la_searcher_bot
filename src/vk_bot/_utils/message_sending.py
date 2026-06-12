import logging
import random
import time
from functools import lru_cache

from _dependencies.vk_api_client import get_default_vk_api_client

random.seed()


@lru_cache
def vk_sender() -> 'VKMessageSender':
    return VKMessageSender()


class VKMessageSender:
    """Wrapper around VKApi for sending messages with rate limiting and error handling.

    Analogous to communicate/_utils/message_sending.py but for VK.
    """

    _daily_limit_remaining: int | None = None

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

        random_id = random.randint(0, 10_000_000)

        for attempt in range(3):
            try:
                resp = get_default_vk_api_client().send(
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
            get_default_vk_api_client().edit_message(
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
            get_default_vk_api_client().delete_message(
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
            get_default_vk_api_client().send_message_event_answer(
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
        color: str = 'secondary',
    ) -> int | None:
        """Convenience method: text + list of buttons in one column."""
        from .keyboards import VKKeyboard

        keyboard = VKKeyboard.one_column(buttons, color=color)
        return self.send_message(peer_id, text, keyboard=keyboard)
