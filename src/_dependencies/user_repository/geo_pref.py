"""Geographic preferences (coordinates, radius) mixin — consolidated."""

import datetime

import sqlalchemy

from _dependencies.common.db_client import DBClientMixinBase


class GeoPrefMixin(DBClientMixinBase):
    """User geographic preference operations — coordinates and radius."""

    def save_coordinates(self, user_id: int, latitude: float, longitude: float) -> None:
        """Save user's home coordinates."""
        with self.connect() as connection:
            delete_stmt = sqlalchemy.text('DELETE FROM user_coordinates WHERE user_id=:user_id;')
            connection.execute(delete_stmt, user_id=user_id)

            now = datetime.datetime.now()
            insert_stmt = sqlalchemy.text(
                """INSERT INTO user_coordinates (user_id, latitude, longitude, upd_time)
                   VALUES (:user_id, :latitude, :longitude, :upd_time);"""
            )
            connection.execute(
                insert_stmt,
                user_id=user_id,
                latitude=latitude,
                longitude=longitude,
                upd_time=now,
            )

    def get_coordinates(self, user_id: int) -> tuple[str, str] | None:
        """Get user's saved home coordinates, or None."""
        with self.connect() as connection:
            stmt = sqlalchemy.text('SELECT latitude, longitude FROM user_coordinates WHERE user_id=:user_id LIMIT 1;')
            result = connection.execute(stmt, user_id=user_id)
            return result.fetchone()

    def delete_coordinates(self, user_id: int) -> None:
        """Delete user's saved home coordinates."""
        with self.connect() as connection:
            stmt = sqlalchemy.text('DELETE FROM user_coordinates WHERE user_id=:user_id;')
            connection.execute(stmt, user_id=user_id)

    def save_radius(self, user_id: int, radius_km: int) -> None:
        """Save user's notification radius preference."""
        with self.connect() as connection:
            stmt = sqlalchemy.text(
                """INSERT INTO user_pref_radius (user_id, radius)
                   VALUES (:user_id, :radius) ON CONFLICT (user_id) DO
                   UPDATE SET radius=:radius;"""
            )
            connection.execute(stmt, user_id=user_id, radius=radius_km)

    def get_radius(self, user_id: int) -> int | None:
        """Get user's saved radius, or None."""
        with self.connect() as connection:
            stmt = sqlalchemy.text("""SELECT radius FROM user_pref_radius WHERE user_id=:user_id;""")
            result = connection.execute(stmt, user_id=user_id)
            raw = result.fetchone()
            if raw and str(raw[0]) != 'None':
                return int(raw[0])
            return None

    def delete_radius(self, user_id: int) -> None:
        """Delete user's radius preference."""
        with self.connect() as connection:
            stmt = sqlalchemy.text("""DELETE FROM user_pref_radius WHERE user_id=:user_id;""")
            connection.execute(stmt, user_id=user_id)
