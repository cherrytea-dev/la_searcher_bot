"""Shared infrastructure for the MAX bot handlers package.

``router``, the payload/state filters and the small helper functions live
here so that every ``handlers/*`` submodule can import them directly
(``from ..common import ...``) without circular imports.

Dialog state (FSM) is persisted in PostgreSQL via ``DialogStateMixin``
(shared with Telegram and VK bots), so state survives Yandex Cloud Function
cold starts and container instance switches.
"""

import json
import logging
from typing import Any

from maxapi import Router
from maxapi.filters.filter import BaseFilter
from maxapi.types.attachments.buttons.attachment_button import AttachmentButton
from maxapi.types.updates import UpdateUnion
from maxapi.types.updates.message_callback import MessageCallback
from maxapi.types.updates.message_created import MessageCreated

from _dependencies.common.commons import Messenger
from _dependencies.models import DialogState
from _dependencies.user_repository import UserRepository

from .keyboards import MaxKeyboardPresets

logger = logging.getLogger(__name__)

router = Router()


class PayloadCmd(BaseFilter):
    """Filter that matches ``MessageCallback`` events by parsed JSON payload ``cmd`` field.

    ``Callback.payload`` is a ``str | None`` (JSON-encoded), so the
    magic filter ``F.callback.payload.cmd`` cannot access the nested
    ``cmd`` key directly. This filter parses the JSON and checks the
    ``cmd`` value.

    Usage::

        @router.message_callback(PayloadCmd('region'))
        async def handler(event: MessageCallback) -> None: ...
    """

    def __init__(self, cmd: str) -> None:
        self._cmd = cmd

    async def __call__(self, event: UpdateUnion) -> bool:
        if not isinstance(event, MessageCallback):
            return False
        payload_str = event.callback.payload
        if not payload_str:
            return False
        try:
            data = json.loads(payload_str)
        except (json.JSONDecodeError, TypeError):
            return False
        return data.get('cmd') == self._cmd


class DBStateFilter(BaseFilter):
    """Filter that matches ``MessageCreated`` events by the user's DB-persisted dialog state.

    Checks the ``msg_from_bot`` table via ``DialogStateMixin.get_user_state()``.
    This is the DB-backed replacement for ``maxapi.filters.state.StateFilter``,
    which stores state in-memory only and does not survive Yandex Cloud Function
    cold starts.

    Usage::

        @router.message_created(F.message.body.text, DBStateFilter(DialogState.waiting_for_radius))
        async def handler(event: MessageCreated) -> None: ...
    """

    def __init__(self, state: DialogState) -> None:
        self._state = state

    async def __call__(self, event: UpdateUnion) -> bool:
        if not isinstance(event, MessageCreated):
            return False
        user_id = event.message.sender.user_id if event.message.sender else None
        if user_id is None:
            return False
        db = UserRepository()
        current_state = db.get_user_state(user_id)
        return current_state == self._state


def _get_db() -> UserRepository:
    """Get a UserRepository instance (lazy, uses AppConfig)."""
    return UserRepository()


def _get_user_id(event: MessageCreated | MessageCallback) -> int | None:
    """Extract user_id from a message or callback event."""
    if isinstance(event, MessageCreated):
        return event.message.sender.user_id if event.message.sender else None
    return event.callback.user.user_id


def _get_chat_id(event: MessageCreated | MessageCallback) -> int | None:
    """Extract chat_id from a message or callback event."""
    if isinstance(event, MessageCreated):
        return event.message.recipient.chat_id
    if event.message is not None:
        return event.message.recipient.chat_id
    return None


def _parse_payload(payload_str: str | None) -> dict[str, Any]:
    """Parse a JSON callback payload string into a dict."""
    if not payload_str:
        return {}
    try:
        return json.loads(payload_str)
    except (json.JSONDecodeError, TypeError):
        logger.warning('Failed to parse callback payload: %s', payload_str)
        return {}


def _ensure_user_registered(user_id: int) -> bool:
    """Register user if new. Returns True if freshly registered.

    Must be called at the start of every message handler that processes
    user input, not just bot_started/start. Otherwise users who skip
    /start (e.g., send arbitrary text or location right away) can save
    settings without a corresponding record in the ``users`` table.
    """
    db = _get_db()
    is_new = db.check_if_new_user(user_id)
    if is_new:
        db.register_user(user_id, Messenger.MAX)
        db.save_default_topic_types(user_id, None)
        logger.info('Registered new user %s via ensure_user_registered', user_id)
    return is_new


def _notifications_disabled(user_id: int) -> bool:
    """Return whether the user explicitly unsubscribed from notifications."""
    return _get_db().get_user_status(user_id) == 'unsubscribed'


def _main_menu_for_user(user_id: int) -> AttachmentButton:
    """Return MAX main menu with the delivery-status action matching user status."""
    return MaxKeyboardPresets.main_menu(notifications_disabled=_notifications_disabled(user_id))


def _get_regions_for_district(district: str) -> list[tuple[int, str]]:
    """Get (folder_id, display_name) list for a federal district."""
    db = _get_db()
    return db.get_geo_folders_by_district(district)


def _get_subscribed_region_names(user_id: int) -> set[str]:
    """Get set of region display names the user is subscribed to."""
    db = _get_db()
    subscribed_folder_ids = set(db.get_user_regions(user_id))
    all_folders = db.get_geo_folders()
    return {name for fid, name in all_folders if fid in subscribed_folder_ids}
