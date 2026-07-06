"""Search following (whitelist/blacklist) management mixin — consolidated."""

import datetime

import sqlalchemy

from _dependencies.common.commons import SearchFollowingMode
from _dependencies.common.db_client import DBClientMixinBase


class SearchFollowingMixin(DBClientMixinBase):
    """Search following (whitelist/blacklist) operations."""

    def get_search_follow_mode(self, user_id: int) -> bool:
        """Check if search following mode is enabled for user."""
        with self.connect() as connection:
            stmt = sqlalchemy.text(
                """SELECT filter_name FROM user_pref_search_filtering WHERE user_id=:user_id LIMIT 1;"""
            )
            result = connection.execute(stmt, dict(user_id=user_id))
            row = result.fetchone()
            return row is not None and 'whitelist' in row[0]

    def set_search_follow_mode(self, user_id: int, enabled: bool) -> None:
        """Enable or disable search following mode."""
        filter_name = ['whitelist'] if enabled else ['']
        with self.connect() as connection:
            stmt = sqlalchemy.text(
                """INSERT INTO user_pref_search_filtering (user_id, filter_name)
                   VALUES (:user_id, :filter_name)
                   ON CONFLICT (user_id) DO UPDATE SET filter_name=:filter_name;"""
            )
            connection.execute(stmt, dict(user_id=user_id, filter_name=filter_name))

    def delete_search_follow_mode(self, user_id: int) -> None:
        """Disable search following mode."""
        with self.connect() as connection:
            stmt = sqlalchemy.text(
                """DELETE FROM user_pref_search_filtering
                   WHERE user_id=:user_id and 'whitelist' = ANY(filter_name);"""
            )
            connection.execute(stmt, dict(user_id=user_id))

    def record_search_whiteness(self, user_id: int, search_id: int, mode: SearchFollowingMode | str) -> None:
        """Save or remove a search whitelist entry."""
        with self.connect() as connection:
            if mode in [SearchFollowingMode.ON, SearchFollowingMode.OFF]:
                stmt = sqlalchemy.text(
                    """INSERT INTO user_pref_search_whitelist (user_id, search_id, timestamp, search_following_mode)
                       VALUES (:user_id, :search_id, :timestamp, :mode)
                       ON CONFLICT (user_id, search_id) DO UPDATE
                       SET timestamp=:timestamp, search_following_mode=:mode;"""
                )
                connection.execute(
                    stmt,
                    dict(
                        user_id=user_id,
                        search_id=search_id,
                        timestamp=datetime.datetime.now(),
                        mode=mode,
                    ),
                )
            else:
                stmt = sqlalchemy.text(
                    """DELETE FROM user_pref_search_whitelist
                       WHERE user_id=:user_id and search_id=:search_id;"""
                )
                connection.execute(stmt, dict(user_id=user_id, search_id=search_id))

    def delete_search_whiteness(self, user_id: int) -> None:
        """Delete all search whitelist entries for a user."""
        with self.connect() as connection:
            stmt = sqlalchemy.text("""DELETE FROM user_pref_search_whitelist WHERE user_id=:user_id;""")
            connection.execute(stmt, dict(user_id=user_id))

    def get_folders_with_followed_searches(self, user_id: int) -> list[int]:
        """Get forum folder IDs that contain searches the user is following."""
        with self.connect() as connection:
            stmt = sqlalchemy.text(
                """SELECT DISTINCT s.forum_folder_id
                   FROM searches s
                   INNER JOIN user_pref_search_whitelist upswl
                       ON upswl.search_id=s.search_forum_num
                       AND upswl.user_id=:user_id
                       AND upswl.search_following_mode=:search_follow_on
                       AND s.status not in('НЖ', 'НП', 'СТОП')
                ;"""
            )
            result = connection.execute(
                stmt,
                dict(
                    user_id=user_id,
                    search_follow_on=SearchFollowingMode.ON,
                ),
            )
            return [int(x[0]) for x in result.fetchall()]
