"""Region (forum folder) subscription management mixin."""

import sqlalchemy


class RegionMixin:
    """User region (forum folder) subscription operations."""

    def get_user_regions(self, user_id: int) -> list[int]:
        """Get list of forum folder IDs the user is subscribed to."""
        with self.connect() as connection:  # type: ignore[attr-defined]
            stmt = sqlalchemy.text("""SELECT forum_folder_num FROM user_regional_preferences WHERE user_id=:user_id;""")
            result = connection.execute(stmt, user_id=user_id)
            return [reg[0] for reg in result.fetchall()]

    def add_region(self, user_id: int, forum_folder_num: int) -> None:
        """Subscribe user to a region (forum folder)."""
        with self.connect() as connection:  # type: ignore[attr-defined]
            stmt = sqlalchemy.text(
                """INSERT INTO user_regional_preferences (user_id, forum_folder_num)
                   VALUES (:user_id, :region);"""
            )
            connection.execute(stmt, user_id=user_id, region=forum_folder_num)

    def remove_region(self, user_id: int, forum_folder_num: int) -> None:
        """Unsubscribe user from a region (forum folder)."""
        with self.connect() as connection:  # type: ignore[attr-defined]
            stmt = sqlalchemy.text(
                """DELETE FROM user_regional_preferences
                   WHERE user_id=:user_id and forum_folder_num=:region;"""
            )
            connection.execute(stmt, user_id=user_id, region=forum_folder_num)

    def check_if_user_has_no_regions(self, user_id: int) -> bool:
        """Check if user has at least one region subscribed."""
        with self.connect() as connection:  # type: ignore[attr-defined]
            stmt = sqlalchemy.text("""SELECT user_id FROM user_regional_preferences WHERE user_id=:user_id LIMIT 1;""")
            result = connection.execute(stmt, user_id=user_id)
            return result.fetchone() is None

    def get_geo_folders(self) -> list[tuple[int, str]]:
        """Get all geographic folders from the database."""
        with self.connect() as connection:  # type: ignore[attr-defined]
            stmt = sqlalchemy.text(
                """SELECT folder_id, folder_display_name FROM geo_folders_view
                   WHERE folder_type='searches';"""
            )
            result = connection.execute(stmt)
            return result.fetchall()

    def get_geo_folders_by_district(self, federal_district_name: str) -> list[tuple[int, str]]:
        """Get geographic folders for regions in a given federal district.

        Uses geo_regions.federal_district to find all regions belonging to the
        specified federal district, then returns the corresponding folders.
        """
        with self.connect() as connection:  # type: ignore[attr-defined]
            stmt = sqlalchemy.text("""
                SELECT fv.folder_id, fv.folder_display_name
                FROM geo_folders_view fv
                JOIN geo_divisions d ON fv.division_id = d.division_id
                JOIN geo_regions r ON d.division_id = r.division_id
                WHERE fv.folder_type = 'searches'
                  AND r.federal_district = :district_name
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
