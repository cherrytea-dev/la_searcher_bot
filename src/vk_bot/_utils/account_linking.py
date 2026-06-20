"""Account linking logic for unregistered VK users.

Handles the flow where a VK user who is not yet linked to a Telegram account
sends an invite code to the VK bot. The invite code is validated via SHA256
hash of {telegram_user_id}{bot_api_token__prod}.

This module was extracted from dispatcher.py to reduce its size and separate
concerns — account linking is a distinct domain from event dispatching.
"""

import hashlib
import logging

from _dependencies.commons import get_app_config

from .common import VKMessage, get_invite_from_message
from .database import db
from .keyboards import VKKeyboardPresets
from .message_sending import VKMessageSender


def handle_unregistered_user(
    vk_message: VKMessage,
    peer_id: int,
    sender: VKMessageSender,
) -> None:
    """Handle a message from an unregistered (unlinked) VK user.

    The only allowed action is to link via invite text.
    Any other message gets instructions on how to get the invite.
    No phantom user is created in the database.

    Args:
        vk_message: The incoming VK message.
        peer_id: The peer ID to send responses to.
        sender: VKMessageSender instance for sending messages.
    """
    _sender = sender
    vk_user_id = vk_message.user_id
    message_text = vk_message.text

    logging.info(f'handle_unregistered_user: vk_user={vk_user_id}, text="{message_text}"')

    telegram_user_id, invite_hash = get_invite_from_message(message_text)

    if not telegram_user_id or not invite_hash:
        text = _get_invite_instructions_text()
        _sender.send_message(peer_id=peer_id, text=text)
        return

    if not _validate_invite_hash(telegram_user_id, invite_hash):
        text = 'Неверный код приглашения. Попробуйте еще раз или получите новый код в Telegram боте.'
        _sender.send_message(peer_id=peer_id, text=text)
        return

    updated = db().set_user_vk_id(telegram_user_id, vk_user_id)
    if updated:
        logging.info(f'VK user {vk_user_id} linked to Telegram user {telegram_user_id}')

        _sender.send_message(
            peer_id=peer_id,
            text='Теперь вы можете изменять настройки бота здесь',
            keyboard=VKKeyboardPresets.main_menu(),
        )
        return
    else:
        # Telegram user not found in DB — invite is stale or user was deleted
        logging.warning(
            f'Failed to link VK user {vk_user_id} to Telegram user {telegram_user_id}: '
            f'Telegram user not found in database'
        )
        text = (
            'Не удалось привязать аккаунт. Возможно, вы удалили бота в Telegram. '
            'Пожалуйста, откройте Telegram бота заново и получите новый код приглашения.'
        )
        _sender.send_message(peer_id=peer_id, text=text)
        return


def _validate_invite_hash(telegram_user_id: int, provided_hash: str) -> bool:
    """Validate invite hash against the expected value.

    The hash is computed as: sha256(f'{telegram_user_id}{bot_api_token__prod}')
    This matches make_invite_text_for_user() in telegram_api_wrapper.py.
    """
    config = get_app_config()
    invite_secret = f'{telegram_user_id}{config.bot_api_token__prod}'
    expected_hash = hashlib.sha256(invite_secret.encode()).hexdigest()
    return provided_hash == expected_hash


def _get_invite_instructions_text() -> str:
    """Return instructions text for unregistered VK users."""
    return (
        '👋 Добро пожаловать в бота поискового отряда ЛизаАлерт!\n\n'
        'Чтобы начать пользоваться ботом, вам нужно привязать свой аккаунт VK '
        'к аккаунту Telegram.\n\n'
        '📱 Как это сделать:\n'
        '1. Откройте бота в Telegram: @LizaAlert_Searcher_Bot\n'
        '2. Перейдите в "Настройки" → "Связать аккаунты бота и Вконтакте"\n'
        '3. Скопируйте полученный код приглашения\n'
        '4. Отправьте этот код сюда, в этот чат\n\n'
        'После привязки вы сможете получать уведомления о поисках '
        'и управлять настройками прямо здесь.'
    )
