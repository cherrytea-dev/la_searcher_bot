"""Account linking logic for unregistered VK users.

Handles the flow where a VK user who is not yet linked to a Telegram account
sends an invite code to the VK bot. The invite code is validated via SHA256
hash of {telegram_user_id}{bot_api_token__prod}.

This module was extracted from dispatcher.py to reduce its size and separate
concerns — account linking is a distinct domain from event dispatching.
"""

import datetime
import hashlib
import logging

import sqlalchemy

from _dependencies.bot.users_management import save_onboarding_step
from _dependencies.common.commons import get_app_config, sqlalchemy_get_pool
from _dependencies.user_repository import UserRepository

from .common import VKHandlerContext, get_invite_from_message
from .keyboards import VKKeyboardPresets


def register_vk_only_user(vk_user_id: int, vk_user_name: str | None = None) -> int:
    """Register a new user without a Telegram account.

    This is the key function for VK-only registration.
    It creates:
    1. A new record in ``users`` table (with ``internal_user_id`` as ``user_id`` placeholder)
    2. A record in ``user_identity_map`` (messenger='vk', messenger_user_id=vk_user_id)
    3. Onboarding step
    4. Default notification preferences
    5. Default topic type preferences

    Args:
        vk_user_id: VK user ID.
        vk_user_name: Optional VK user display name.

    Returns:
        The new ``internal_user_id``.
    """

    pool = sqlalchemy_get_pool()
    with pool.begin() as conn:
        # 1. Generate a new internal_user_id from the users sequence
        result = conn.execute(sqlalchemy.text("SELECT nextval('users_id_seq'::regclass)"))
        internal_user_id = result.scalar()
        assert internal_user_id is not None, 'Failed to generate next user ID from sequence'

        # 2. Create record in users table
        #    Use internal_user_id as user_id (no telegram id available)

        now = datetime.datetime.now()
        conn.execute(
            sqlalchemy.text("""
                INSERT INTO users (user_id, internal_user_id, username_telegram, reg_date, status)
                VALUES (:user_id, :internal_user_id, :username, :reg_date, :status)
                ON CONFLICT (user_id) DO NOTHING
            """),
            {
                'user_id': internal_user_id,
                'internal_user_id': internal_user_id,
                'username': vk_user_name,
                'reg_date': now,
                'status': 'new',
            },
        )

        # 3. Create identity_map entry for VK
        conn.execute(
            sqlalchemy.text("""
                INSERT INTO user_identity_map (internal_user_id, messenger, messenger_user_id)
                VALUES (:internal_user_id, 'vk', :vk_user_id)
                ON CONFLICT (messenger, messenger_user_id) DO NOTHING
            """),
            {'internal_user_id': internal_user_id, 'vk_user_id': str(vk_user_id)},
        )

        # 4. Save onboarding start
        save_onboarding_step(internal_user_id, 'start')

        # 5. Create default notification preferences
        _save_default_preferences(conn, internal_user_id)

        # 6. Create default topic type preferences (required for compose_notifications SQL filter)
        UserRepository().save_default_topic_types(internal_user_id, None)

        logging.info(f'VK-only user registered: internal_user_id={internal_user_id}, vk_user_id={vk_user_id}')
        return internal_user_id


def _save_default_preferences(conn: sqlalchemy.engine.Connection, user_id: int) -> None:
    """Save default notification preferences for a new user."""
    default_prefs = [
        (user_id, 'new_searches', 0),
        (user_id, 'status_changes', 1),
        (user_id, 'inforg_comments', 4),
        (user_id, 'first_post_changes', 8),
        (user_id, 'bot_news', 20),
    ]
    stmt = sqlalchemy.text("""
        INSERT INTO user_preferences (user_id, preference, pref_id)
        VALUES (:user_id, :preference, :pref_id)
        ON CONFLICT (user_id, pref_id) DO NOTHING
    """)
    for params in default_prefs:
        conn.execute(stmt, {'user_id': params[0], 'preference': params[1], 'pref_id': params[2]})


def handle_unregistered_user(ctx: VKHandlerContext) -> None:
    """Handle a message from an unregistered (unlinked) VK user.

    The only allowed action is to link via invite text.
    Any other message gets instructions on how to get the invite.
    No phantom user is created in the database.

    Args:
        ctx: VKHandlerContext with message, sender, and db access.
    """
    vk_user_id = ctx.message.user_id
    message_text = ctx.message.text

    logging.info(f'handle_unregistered_user: vk_user={vk_user_id}, text="{message_text}"')

    telegram_user_id, invite_hash = get_invite_from_message(message_text)

    if not telegram_user_id or not invite_hash:
        text = _get_invite_instructions_text()
        ctx.send_message(text=text)
        return

    if not _validate_invite_hash(telegram_user_id, invite_hash):
        text = 'Неверный код приглашения. Попробуйте еще раз или получите новый код в Telegram боте.'
        ctx.send_message(text=text)
        return

    updated = ctx.db.set_user_vk_id(telegram_user_id, vk_user_id)
    if updated:
        logging.info(f'VK user {vk_user_id} linked to Telegram user {telegram_user_id}')

        ctx.send_message(
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
        ctx.send_message(text=text)
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
