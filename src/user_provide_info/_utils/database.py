"""DB client for user_provide_info."""

from __future__ import annotations

from typing import Any

import sqlalchemy

from _dependencies.common.db_client import DBClientBase


class DBClient(DBClientBase):
    """DB client for user_provide_info."""

    def get_basic_user_params(self, user_id: int) -> dict[str, Any] | None:
        with self.connect() as conn:
            result = conn.execute(
                sqlalchemy.text("""
                SELECT u.user_id, uc.latitude, uc.longitude, ur.radius
                FROM users AS u
                LEFT JOIN user_coordinates AS uc
                ON u.user_id=uc.user_id
                LEFT JOIN user_pref_radius AS ur
                ON uc.user_id=ur.user_id
                WHERE u.user_id=:user_id;
                """),
                dict(user_id=user_id),
            ).fetchone()

            if not result:
                return None

            return {
                'curr_user': True,
                'user_id': result[0],
                'home_lat': float(result[1]) if result[1] else None,
                'home_lon': float(result[2]) if result[2] else None,
                'radius': result[3],
            }

    def get_user_regions(self, user_id: int) -> list[int]:
        with self.connect() as conn:
            result = conn.execute(
                sqlalchemy.text("""
                WITH
                    step_0 AS (
                        SELECT
                            urp.forum_folder_num,
                            f.division_id AS region_id,
                            r.polygon_id
                        FROM user_regional_preferences AS urp
                        LEFT JOIN geo_folders AS f
                        ON urp.forum_folder_num=f.folder_id
                        JOIN geo_regions AS r
                        ON f.division_id=r.division_id
                        WHERE urp.user_id=:user_id
                    )
                SELECT distinct polygon_id
                FROM step_0
                ORDER BY 1;
                """),
                dict(user_id=user_id),
            ).fetchall()
            return [line[0] for line in result]

    def get_searches_for_user(self, user_id: int, user_was_found: bool) -> list[Any]:
        filter_condition = (
            'WHERE user_id=:user_id' if user_was_found else 'WHERE forum_folder_num=276 OR forum_folder_num=41'
        )

        query = f"""
        WITH
            user_regions AS (
                SELECT forum_folder_num from user_regional_preferences
                {filter_condition}),
            user_regions_filtered AS (
                SELECT ur.*
                FROM user_regions AS ur
                LEFT JOIN geo_folders AS f
                ON ur.forum_folder_num=f.folder_id
                WHERE f.folder_type='searches'),
            s2 AS (SELECT search_forum_num, search_start_time, display_name, status, family_name,
                topic_type, topic_type_id, city_locations, age_min, age_max
                FROM searches
                WHERE forum_folder_id IN (SELECT forum_folder_num FROM user_regions_filtered)
                AND status != 'НЖ'
                AND status != 'НП'
                AND status != 'Завершен'
                AND status != 'Найден'
                AND topic_type_id != 1
                ORDER BY search_start_time DESC
                LIMIT 30),
            s3 AS (SELECT s2.*
                FROM s2
                LEFT JOIN search_health_check shc
                ON s2.search_forum_num=shc.search_forum_num
                WHERE (shc.status is NULL OR shc.status='ok' OR shc.status='regular')
                ORDER BY s2.search_start_time DESC),
            s4 AS (SELECT s3.*, sfp.content
                FROM s3
                LEFT JOIN search_first_posts AS sfp
                ON s3.search_forum_num=sfp.search_id
                WHERE sfp.actual = True),
            s5 AS (SELECT s4.*, sc.latitude, sc.longitude, sc.coord_type
                FROM s4
                LEFT JOIN search_coordinates AS sc
                ON s4.search_forum_num=sc.search_id)
            SELECT distinct s5.*, max(parsed_time) OVER (PARTITION BY cl.search_forum_num) AS last_change_time
                FROM s5
                LEFT JOIN change_log AS cl
                ON s5.search_forum_num=cl.search_forum_num;
            """
        with self.connect() as conn:
            result = conn.execute(sqlalchemy.text(query), dict(user_id=user_id))
            return list(result.fetchall())

    def save_stat_map_usage(self, user_id: int, response: str) -> None:
        with self.connect() as conn:
            conn.execute(
                sqlalchemy.text("""
                INSERT INTO stat_map_usage
                (user_id, timestamp, response)
                VALUES (:user_id, CURRENT_TIMESTAMP, :response);
                """),
                dict(user_id=user_id, response=response),
            )
