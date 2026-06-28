"""User registration and onboarding mixin — consolidated."""

import datetime
import logging

import sqlalchemy

from _dependencies.bot.users_management import register_new_user, save_onboarding_step
from _dependencies.common.commons import Messenger
from _dependencies.common.db_client import DBClientMixinBase


class UserMixin(DBClientMixinBase):
    """User registration, role, and onboarding operations."""

    def check_if_new_user(self, user_id: int) -> bool:
        """Check if user exists in the database."""
        with self.connect() as connection:
            stmt = sqlalchemy.text("""SELECT user_id FROM users WHERE user_id=:user_id LIMIT 1;""")
            result = connection.execute(stmt, user_id=user_id)
            return result.fetchone() is None

    def register_user(self, user_id: int, messenger: Messenger, username: str | None = None) -> None:
        """Register a new user with default settings.

        Args:
            user_id: Internal user ID.
            messenger: Messenger enum value for user_identity_map.
            username: Optional display name.
        """
        register_new_user(user_id, username, datetime.datetime.now(), messenger)

    def get_onboarding_step(self, user_id: int, user_is_new: bool = False) -> tuple[int, str]:
        """Get the current onboarding step for a user.

        If user_is_new is True, returns (0, 'start') immediately.
        """
        if user_is_new:
            return 0, 'start'

        with self.connect() as connection:
            try:
                stmt = sqlalchemy.text(
                    """SELECT step_id, step_name, timestamp FROM user_onboarding
                       WHERE user_id=:user_id ORDER BY step_id DESC;"""
                )
                result = connection.execute(stmt, user_id=user_id)
                raw_data = result.fetchone()
                if raw_data:
                    step_id, step_name, _time = list(raw_data)
                else:
                    step_id, step_name = 99, None
            except Exception as e:
                logging.exception(e)
                step_id, step_name = 99, None
            return step_id, step_name

    def save_onboarding_step(self, user_id: int, step: str) -> None:
        """Save onboarding step progress."""
        save_onboarding_step(user_id, step)

    def save_user_role(self, user_id: int, role: str) -> str:
        """Save user's role (member, new_member, relative, etc.).

        The caller (handler) is responsible for mapping UI button text
        to role codes. This method only stores the code in the DB.
        """
        with self.connect() as connection:
            stmt = sqlalchemy.text("""UPDATE users SET role=:role where user_id=:user_id;""")
            connection.execute(stmt, role=role, user_id=user_id)
            logging.info(f'[settings] user {user_id} selected role {role}')
            return role

    def get_user_role(self, user_id: int) -> str | None:
        """Get user's role."""
        with self.connect() as connection:
            stmt = sqlalchemy.text('SELECT role FROM users WHERE user_id=:user_id LIMIT 1;')
            result = connection.execute(stmt, user_id=user_id)
            row = result.fetchone()
            return row[0] if row else None
