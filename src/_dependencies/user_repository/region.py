"""Region (forum folder) subscription management mixin — consolidated."""

import datetime

import sqlalchemy

from _dependencies.common.db_client import DBClientMixinBase


class RegionMixin(DBClientMixinBase):
    """User region (forum folder) subscription operations."""

    def get_user_regions(self, user_id: int) -> list[int]:
        """Get list of forum folder IDs the user is subscribed to."""
        with self.connect() as connection:
            stmt = sqlalchemy.text("""SELECT forum_folder_num FROM user_regional_preferences WHERE user_id=:user_id;""")
            result = connection.execute(stmt, dict(user_id=user_id))
            return [reg[0] for reg in result.fetchall()]

    def add_region(self, user_id: int, forum_folder_num: int) -> None:
        """Subscribe user to a region (forum folder)."""
        with self.connect() as connection:
            stmt = sqlalchemy.text(
                """INSERT INTO user_regional_preferences (user_id, forum_folder_num)
                   VALUES (:user_id, :region);"""
            )
            connection.execute(stmt, dict(user_id=user_id, region=forum_folder_num))

    def remove_region(self, user_id: int, forum_folder_num: int) -> None:
        """Unsubscribe user from a region (forum folder)."""
        with self.connect() as connection:
            stmt = sqlalchemy.text(
                """DELETE FROM user_regional_preferences
                   WHERE user_id=:user_id and forum_folder_num=:region;"""
            )
            connection.execute(stmt, dict(user_id=user_id, region=forum_folder_num))

    def check_if_user_has_no_regions(self, user_id: int) -> bool:
        """Check if user has at least one region subscribed."""
        with self.connect() as connection:
            stmt = sqlalchemy.text("""SELECT user_id FROM user_regional_preferences WHERE user_id=:user_id LIMIT 1;""")
            result = connection.execute(stmt, dict(user_id=user_id))
            return result.fetchone() is None

    def add_user_region_setting(self, user_id: int, region_id: int) -> None:
        """Record that the user has configured a region setting.

        Writes to ``user_pref_region`` — a flag table used by
        ``settings_summary`` to determine if the user has set up regions.
        """
        with self.connect() as connection:
            stmt = sqlalchemy.text(
                """INSERT INTO user_pref_region (user_id, region_id, timestamp)
                   VALUES (:user_id, :region_id, :timestamp);"""
            )
            connection.execute(
                stmt,
                dict(
                    user_id=user_id,
                    region_id=region_id,
                    timestamp=datetime.datetime.now(),
                ),
            )

    def get_geo_folders(self) -> list[tuple[int, str]]:
        """Get all geographic folders from the database."""
        with self.connect() as connection:
            stmt = sqlalchemy.text(
                """SELECT folder_id, folder_display_name FROM geo_folders_view
                   WHERE folder_type='searches';"""
            )
            result = connection.execute(stmt)
            return result.fetchall()

    def get_geo_folders_by_district(self, federal_district_name: str) -> list[tuple[int, str]]:
        """Get geographic folders for regions in a given federal district.

        Returns a list of ``(folder_id, folder_display_name)`` tuples.
        When multiple folders share the same display name (e.g., multiple
        forum subforums for the same division+subtype), only the first
        folder_id is returned — the keyboard shows each display name once.
        """
        with self.connect() as connection:
            stmt = sqlalchemy.text("""
                SELECT MIN(fv.folder_id) AS folder_id, fv.folder_display_name
                FROM geo_folders_view fv
                JOIN geo_divisions d ON fv.division_id = d.division_id
                JOIN geo_regions r ON d.division_id = r.division_id
                WHERE fv.folder_type = 'searches'
                  AND r.federal_district = :district_name
                GROUP BY fv.folder_display_name
                ORDER BY fv.folder_display_name;
            """)
            result = connection.execute(stmt, {'district_name': federal_district_name})
            return result.fetchall()

    def toggle_region_by_name(self, user_id: int, region_name: str, folder_dict: dict[str, tuple[int, ...]]) -> bool:
        """Toggle a region subscription by its display name.

        Returns False if user tries to remove the last remaining region.
        """
        folder_ids = folder_dict.get(region_name)
        if not folder_ids:
            return False

        user_curr_regs = self.get_user_regions(user_id)
        region_was_in_db = any(folder_ids[0] == reg for reg in user_curr_regs)
        region_is_the_only = region_was_in_db and len(user_curr_regs) - len(folder_ids) < 1

        if region_is_the_only:
            return False

        if region_was_in_db:
            for folder_id in folder_ids:
                self.remove_region(user_id, folder_id)
        else:
            for folder_id in folder_ids:
                self.add_region(user_id, folder_id)

        return True
