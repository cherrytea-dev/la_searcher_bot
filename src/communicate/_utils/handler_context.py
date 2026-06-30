"""TGHandlerContext — context object passed to every Telegram handler.

Extracted from ``common.py`` to break a circular import chain:
``common.py`` → ``database.py`` → ``common.py``.
"""

import logging

from telegram import InlineKeyboardMarkup, Message, ReplyKeyboardMarkup, ReplyKeyboardRemove

from .common import UpdateBasicParams, UpdateExtraParams, UserInputState
from .database import DBClient
from .message_sending import TGApiCommunicate


class TGHandlerContext:
    """Context object passed to every Telegram handler.

    Provides access to incoming update data, user identity, dialog state,
    and response methods (reply, edit, answer_callback, etc.).

    Handlers receive this as their sole argument and call methods on it
    to interact with the user. The handler chain stops when a handler
    marks the context as consumed (via ``.reply()``, ``.edit()``, etc.).
    """

    def __init__(
        self,
        update_params: UpdateBasicParams,
        extra_params: UpdateExtraParams,
        tg_api: TGApiCommunicate,
        db: DBClient,
    ) -> None:
        # ── Incoming data ──────────────────────────────────────────────
        self.update_params: UpdateBasicParams = update_params
        """The parsed Telegram update parameters."""

        self.extra_params: UpdateExtraParams = extra_params
        """Extra parameters (onboarding step, user input state, etc.)."""

        self.user_id: int = update_params.user_id
        """Telegram user ID."""

        # ── Internal dependencies ──────────────────────────────────────
        self._tg_api: TGApiCommunicate = tg_api
        self._db: DBClient = db
        self._consumed: bool = False

    # ── Public properties ──────────────────────────────────────────────

    @property
    def db(self) -> DBClient:
        """Database client for user data access."""
        return self._db

    @property
    def tg_api(self) -> TGApiCommunicate:
        """Telegram Bot API client."""
        return self._tg_api

    # ── Chain control ─────────────────────────────────────────────────

    @property
    def is_consumed(self) -> bool:
        """Whether a handler has already processed this update.

        The dispatcher checks this after each handler to decide whether
        to continue iterating the chain.
        """
        return self._consumed

    # ── Response methods ───────────────────────────────────────────────

    def reply(
        self,
        text: str,
        reply_markup: ReplyKeyboardMarkup | InlineKeyboardMarkup | ReplyKeyboardRemove | None = None,
        parse_mode: str = 'HTML',
        disable_web_page_preview: bool = True,
    ) -> None:
        """Send a new message to the user (or edit if this is a callback).

        Automatically detects whether this is an inline callback response
        (edits the original message) or a regular message (sends new).

        Marks the context as consumed and clears dialog state.
        """
        self._consumed = True
        self._send_or_edit(text, reply_markup, parse_mode, disable_web_page_preview)
        self._db.set_user_input_state(self.user_id, UserInputState.not_defined)
        self._save_dialog(text)

    def edit(
        self,
        text: str,
        reply_markup: InlineKeyboardMarkup | None = None,
        message_id: int | None = None,
    ) -> None:
        """Edit an existing message (for inline keyboard updates).

        When called from a callback handler without an explicit ``message_id``,
        automatically extracts the message ID from the callback query's message.

        Marks the context as consumed.
        """
        self._consumed = True

        if message_id is None and self.update_params.callback_query is not None:
            message = self.update_params.callback_query.message
            if isinstance(message, Message):
                message_id = message.id

        params = {
            'chat_id': self.user_id,
            'text': text,
            'message_id': message_id,
            'reply_markup': reply_markup,
        }
        self._tg_api.edit_message_text(params)
        self._save_dialog(text)

    def answer_callback(self, text: str = '') -> None:
        """Answer a callback query (show a brief notification to the user).

        Does NOT mark the context as consumed — the handler may call
        both ``.answer_callback()`` and ``.reply()`` / ``.edit()``.
        """
        callback_query_id = self.update_params.callback_query_id
        if callback_query_id:
            self._tg_api.send_callback_answer_to_api(self.user_id, callback_query_id, text)

    def send_message(
        self,
        text: str,
        reply_markup: ReplyKeyboardMarkup | InlineKeyboardMarkup | ReplyKeyboardRemove | None = None,
        parse_mode: str = 'HTML',
        disable_web_page_preview: bool = True,
    ) -> None:
        """Send an additional message without consuming the context.

        Unlike ``.reply()``, this does NOT mark the context as consumed
        and does NOT clear dialog state. Use for multi-message responses
        after the primary ``.reply()``.
        """
        params = {
            'parse_mode': parse_mode,
            'disable_web_page_preview': disable_web_page_preview,
            'reply_markup': reply_markup,
            'chat_id': self.user_id,
            'text': text,
        }
        self._tg_api.send_message(params)
        self._save_dialog(text)

    def delete_inline_dialogue(self) -> None:
        """Delete the last inline dialogue message IDs for this user."""
        self._db.delete_last_user_inline_dialogue(self.user_id)

    # ── State management ──────────────────────────────────────────────

    def set_state(self, state: UserInputState) -> None:
        """Set the dialog state (what input the bot expects next)."""
        self._db.set_user_input_state(self.user_id, state)

    def clear_state(self) -> None:
        """Clear the dialog state (bot no longer expects specific input)."""
        self._db.set_user_input_state(self.user_id, UserInputState.not_defined)

    # ── Internal helpers ──────────────────────────────────────────────

    def _send_or_edit(
        self,
        text: str,
        reply_markup: ReplyKeyboardMarkup | InlineKeyboardMarkup | ReplyKeyboardRemove | None,
        parse_mode: str,
        disable_web_page_preview: bool,
    ) -> None:
        """Decide whether to send a new message or edit an existing one."""
        got_callback = self.update_params.got_callback
        callback_query = self.update_params.callback_query

        replied_with_inline_markup = got_callback and isinstance(reply_markup, InlineKeyboardMarkup)
        if replied_with_inline_markup:
            # Edit the message where the inline button was pushed
            message = callback_query.message if callback_query is not None else None
            if isinstance(message, Message):
                try:
                    if message.reply_markup == reply_markup and message.text == text:
                        # Same content — just acknowledge the callback
                        self.answer_callback('')
                        return
                except AttributeError:
                    logging.warning(f'no reply_markup or text in {callback_query=}')

                last_user_message_id = message.id
                params = {
                    'chat_id': self.user_id,
                    'text': text,
                    'message_id': last_user_message_id,
                    'reply_markup': reply_markup,
                }
                self._tg_api.edit_message_text(params)
        else:
            params = {
                'parse_mode': parse_mode,
                'disable_web_page_preview': disable_web_page_preview,
                'reply_markup': reply_markup,
                'chat_id': self.user_id,
                'text': text,
            }
            self._tg_api.send_message(params)

    def _save_dialog(self, text: str) -> None:
        """Save bot reply to dialog history."""
        if text:
            try:
                self._db.save_bot_reply_to_user(self.user_id, text)
            except Exception:
                logging.exception(f'Failed to save bot reply for user {self.user_id}')
