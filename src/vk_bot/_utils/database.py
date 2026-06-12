from functools import lru_cache

import sqlalchemy

from _dependencies.db_client import DBClientBase
from _dependencies.services.user_settings_service import get_user_settings_service, UserSettingsService


class DBClient(DBClientBase):
    """VK-specific DB operations.

    User settings are delegated to UserSettingsService (shared layer).
    This class only contains VK-specific methods like user resolution.
    """

    def get_user_by_vk_id(self, vk_id: int) -> int | None:
        """Find telegram user_id by vk_id.

        Returns None if not found (user hasn't linked VK account yet).
        The vk_id column is varchar, so we pass the value as string.
        """
        with self.connect() as connection:
            stmt = sqlalchemy.text("""
                SELECT user_id FROM users
                WHERE vk_id = :vk_id
                LIMIT 1;
            """)
            result = connection.execute(stmt, vk_id=str(vk_id))
            row = result.fetchone()
            return row[0] if row else None

    def set_user_vk_id(self, telegram_user_id: int, vk_id: int) -> None:
        """Link VK ID to an existing Telegram user."""
        with self.connect() as connection:
            stmt = sqlalchemy.text("""
                UPDATE users
                SET vk_id = :vk_id
                WHERE user_id = :user_id;
            """)
            connection.execute(stmt, user_id=telegram_user_id, vk_id=str(vk_id))

    def is_user_registered_in_vk(self, vk_id: int) -> bool:
        """Check if a user with this vk_id exists in the system."""
        return self.get_user_by_vk_id(vk_id) is not None

    def resolve_user_id(self, vk_user_id: int) -> int:
        """Determine system user_id for a VK user.

        Resolution logic:
        - If vk_id is already linked to a telegram_id → return telegram_id
        - If not → return -vk_user_id (negative, to avoid collision with Telegram IDs)

        This allows VK-only users to exist without a Telegram account.
        """
        telegram_id = self.get_user_by_vk_id(vk_user_id)
        if telegram_id is not None:
            return telegram_id
        return -vk_user_id

    @property
    def settings(self) -> UserSettingsService:
        """Access to shared user settings service."""
        return get_user_settings_service()


@lru_cache
def db() -> DBClient:
    return DBClient()
