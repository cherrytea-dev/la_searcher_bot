"""System role management mixin — consolidated from communicate and VK bot."""

import sqlalchemy

from _dependencies.common.db_client import DBClientMixinBase


class SystemRoleMixin(DBClientMixinBase):
    """User system role operations (admin, tester, etc.)."""

    def get_user_sys_roles(self, user_id: int) -> list[str]:
        """Get user's system roles (admin, tester, etc.)."""
        with self.connect() as connection:
            stmt = sqlalchemy.text('SELECT role FROM user_roles WHERE user_id=:user_id;')
            result = connection.execute(stmt, user_id=user_id)
            return [row[0] for row in result.fetchall()]

    def is_user_tester(self, user_id: int) -> bool:
        """Check if user has tester role."""
        return 'tester' in self.get_user_sys_roles(user_id)

    def add_user_sys_role(self, user_id: int, role: str) -> None:
        """Add a system role to a user."""
        with self.connect() as connection:
            stmt = sqlalchemy.text(
                """INSERT INTO user_roles (user_id, role)
                   VALUES (:user_id, :role) ON CONFLICT DO NOTHING;"""
            )
            connection.execute(stmt, user_id=user_id, role=role)

    def delete_user_sys_role(self, user_id: int, role: str) -> None:
        """Remove a system role from a user."""
        with self.connect() as connection:
            stmt = sqlalchemy.text("""DELETE FROM user_roles WHERE user_id=:user_id and role=:role;""")
            connection.execute(stmt, user_id=user_id, role=role)
