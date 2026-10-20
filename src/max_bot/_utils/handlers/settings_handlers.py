"""Main-menu navigation and settings callback handlers."""

import logging

from maxapi.types.updates.message_callback import MessageCallback

from _dependencies.bot.users_management import ManageUserAction

from ..common import PayloadCmd, _get_db, _get_user_id, _main_menu_for_user, router
from ..keyboards import MaxKeyboardPresets
from ..message_formatter import (
    MAIN_MENU_TEXT,
    NOTIFICATIONS_DISABLED,
    NOTIFICATIONS_ENABLED,
    RESET_CANCELLED,
    RESET_CONFIRM,
    RESET_DONE,
)

logger = logging.getLogger(__name__)


@router.message_callback(PayloadCmd('back_to_main'))
async def on_back_to_main(event: MessageCallback) -> None:
    """Return to main menu."""
    await event.ack(notification='...')
    await event.edit(
        text=MAIN_MENU_TEXT,
        attachments=[_main_menu_for_user(event.callback.user.user_id)],
    )


@router.message_callback(PayloadCmd('disable_notifications'))
async def on_disable_notifications(event: MessageCallback) -> None:
    """Explicitly unsubscribe from all notifications."""
    user_id = _get_user_id(event)
    if user_id is None:
        return

    db = _get_db()
    db.update_user_status(user_id, ManageUserAction.unsubscribe_user)
    await event.ack(notification='...')
    await event.edit(
        text=NOTIFICATIONS_DISABLED,
        attachments=[MaxKeyboardPresets.main_menu(notifications_disabled=True)],
    )


@router.message_callback(PayloadCmd('enable_notifications'))
async def on_enable_notifications(event: MessageCallback) -> None:
    """Re-enable notifications after explicit unsubscribe."""
    user_id = _get_user_id(event)
    if user_id is None:
        return

    db = _get_db()
    db.update_user_status(user_id, ManageUserAction.subscribe_user)
    await event.ack(notification='...')
    await event.edit(
        text=NOTIFICATIONS_ENABLED,
        attachments=[MaxKeyboardPresets.main_menu(notifications_disabled=False)],
    )


@router.message_callback(PayloadCmd('reset_settings'))
async def on_reset_settings(event: MessageCallback) -> None:
    """Show confirmation before wiping all settings to defaults."""
    await event.ack(notification='...')
    await event.edit(
        text=RESET_CONFIRM,
        attachments=[MaxKeyboardPresets.reset_confirm()],
    )


@router.message_callback(PayloadCmd('reset_confirm'))
async def on_reset_confirm(event: MessageCallback) -> None:
    """Wipe settings, restore defaults, then prompt region re-selection."""
    user_id = _get_user_id(event)
    if user_id is None:
        return

    db = _get_db()
    db.reset_user_settings(user_id)
    logger.info('User %s reset settings to defaults', user_id)

    await event.ack(notification='...')
    await event.edit(
        text=RESET_DONE,
        attachments=[MaxKeyboardPresets.fed_districts_inline()],
    )


@router.message_callback(PayloadCmd('reset_cancel'))
async def on_reset_cancel(event: MessageCallback) -> None:
    """Cancel the reset — keep settings as-is."""
    user_id = _get_user_id(event)
    await event.ack(notification='...')
    await event.edit(
        text=RESET_CANCELLED,
        attachments=[_main_menu_for_user(user_id) if user_id else MaxKeyboardPresets.main_menu()],
    )
