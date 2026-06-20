"""VK identity mixin — user resolution by VK ID."""

import sqlalchemy


class VKIdentityMixin:
    """User resolution by VK ID.

    Methods for finding/linking users by their VKontakte ID.
    The vk_id column in the DB is varchar, so values are cast to str.
    """

    def get_user_by_vk_id(self, vk_id: int | str) -> int | None:
        """Find telegram user_id by vk_id.

        Returns None if not found (user hasn't linked VK account yet).
        The vk_id column is varchar, so we pass the value as string.
        """
        with self.connect() as connection:  # type: ignore[attr-defined]
            stmt = sqlalchemy.text("""
                SELECT user_id FROM users
                WHERE vk_id = :vk_id
                LIMIT 1;
            """)
            result = connection.execute(stmt, vk_id=str(vk_id))
            row = result.fetchone()
            return row[0] if row else None

    def get_user_vk_id(self, user_id: int) -> str | None:
        """Get the VK ID linked to a Telegram user.

        Returns None if the user hasn't linked a VK account.
        The vk_id column is varchar, so we return it as string.
        """
        with self.connect() as connection:  # type: ignore[attr-defined]
            stmt = sqlalchemy.text("""
                SELECT vk_id FROM users
                WHERE user_id = :user_id
                LIMIT 1;
            """)
            result = connection.execute(stmt, user_id=user_id)
            row = result.fetchone()
            return row[0] if row else None

    def set_user_vk_id(self, telegram_user_id: int, vk_id: int | str) -> bool:
        """Link VK ID to an existing Telegram user.

        Returns True if the user was found and updated, False if no user
        with the given telegram_user_id exists.
        """
        with self.connect() as connection:  # type: ignore[attr-defined]
            stmt = sqlalchemy.text("""
                UPDATE users
                SET vk_id = :vk_id
                WHERE user_id = :user_id;
            """)
            result = connection.execute(stmt, user_id=telegram_user_id, vk_id=str(vk_id))
            return result.rowcount > 0

    def is_user_registered_in_vk(self, vk_id: int | str) -> bool:
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
