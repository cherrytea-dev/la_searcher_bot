"""Telegram-specific role and topic type mixin.

Contains role selection logic and default topic type assignment
that is specific to the Telegram bot's onboarding flow.
VK bot uses different button texts and a different flow.
"""

import datetime
import logging

import sqlalchemy

from _dependencies.common.db_client import DBClientMixinBase


class TelegramRoleMixin(DBClientMixinBase):
    """Telegram-specific role and topic type operations."""

    def save_user_pref_role(self, user_id: int, role_desc: str) -> str:
        """Save user role based on Telegram button text."""
        role_dict = {
            'я состою в ЛизаАлерт': 'member',
            'я хочу помогать ЛизаАлерт': 'new_member',
            'я ищу человека': 'relative',
            'у меня другая задача': 'other',
            'не хочу говорить': 'no_answer',
        }
        try:
            role = role_dict[role_desc]
        except:  # noqa
            role = 'unidentified'

        with self.connect() as connection:
            stmt = sqlalchemy.text("""UPDATE users SET role=:role where user_id=:user_id;""")
            connection.execute(stmt, dict(role=role, user_id=user_id))
            logging.info(f'[comm]: user {user_id} selected role {role}')
            return role

    def _save_user_pref_topic_type(self, user_id: int, pref_type_id: int) -> None:
        """Save a single topic type preference."""
        with self.connect() as connection:
            stmt = sqlalchemy.text(
                """INSERT INTO user_pref_topic_type (user_id, topic_type_id, timestamp)
                   VALUES (:user_id, :type_id, :timestamp)
                   ON CONFLICT (user_id, topic_type_id) DO NOTHING;"""
            )
            connection.execute(
                stmt,
                dict(
                    user_id=user_id,
                    type_id=pref_type_id,
                    timestamp=datetime.datetime.now(),
                ),
            )

    def save_user_pref_topic_type(self, user_id: int, user_role: str | None) -> None:
        """Save default topic type preferences based on user role."""
        if not user_id:
            return
        if user_role in {'member', 'new_member'}:
            default_topic_type_id = [0, 3, 4, 5]
        else:
            default_topic_type_id = [0, 4, 5]
        for type_id in default_topic_type_id:
            self._save_user_pref_topic_type(user_id, type_id)
