"""VK-only user registration.

A VK user without an entry in ``user_identity_map`` is registered as an
independent user (VK-only): own row in ``users``, own preferences, own
onboarding step. There is no Telegram<->VK account linking anymore.
"""

import datetime
import logging

import sqlalchemy

from _dependencies.bot.users_management import save_onboarding_step
from _dependencies.common.commons import sqlalchemy_get_pool
from _dependencies.user_repository import UserRepository


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
                INSERT INTO users (user_id, internal_user_id, username_telegram, reg_date)
                VALUES (:user_id, :internal_user_id, :username, :reg_date)
                ON CONFLICT (user_id) DO NOTHING
            """),
            {
                'user_id': internal_user_id,
                'internal_user_id': internal_user_id,
                'username': vk_user_name,
                'reg_date': now,
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
