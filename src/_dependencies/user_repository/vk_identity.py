"""VK identity mixin — user resolution by VK ID."""

from types import SimpleNamespace

import sqlalchemy

from _dependencies.common.db_client import DBClientMixinBase


class VKIdentityMixin(DBClientMixinBase):
    """User resolution by VK ID."""

    def get_identity_by_messenger_user_id(self, messenger_user_id: int | str) -> SimpleNamespace | None:
        """Resolve ``UserIdentity`` from ``user_identity_map`` by VK user ID.

        Returns a simple namespace with ``internal_user_id``, ``messenger``,
        ``messenger_user_id`` or None if not found.
        """
        with self.connect() as connection:
            stmt = sqlalchemy.text("""
                SELECT internal_user_id, messenger, messenger_user_id
                FROM user_identity_map
                WHERE messenger = 'vk' AND messenger_user_id = :user_id
                LIMIT 1;
            """)
            result = connection.execute(stmt, dict(user_id=str(messenger_user_id)))
            row = result.fetchone()
            if row:
                return SimpleNamespace(
                    internal_user_id=row[0],
                    messenger=row[1],
                    messenger_user_id=row[2],
                )
            return None
