"""Mixin: search info queries (searches, activities, attributes, coordinates)."""

from typing import Any

import sqlalchemy

from _dependencies.common.db_client import DBClientMixinBase


class SearchInfoMixin(DBClientMixinBase):
    """DB operations on searches and related tables."""

    def get_search_state_by_forum_num(self, forum_search_num: int) -> Any:
        """Get search state by forum search number."""
        with self.connect() as conn:
            sql_text = sqlalchemy.text("""
                SELECT search_forum_num, parsed_time, status, forum_search_title,
                       search_start_time, num_of_replies, family_name, age,
                       id, forum_folder_id, topic_type, display_name, age_min,
                       age_max, status, city_locations, topic_type_id
                FROM searches
                WHERE search_forum_num=:forum_search_num
                ORDER BY parsed_time DESC NULLS LAST
                LIMIT 1;
            """)
            return conn.execute(sql_text, dict(forum_search_num=forum_search_num)).fetchone()

    def get_ongoing_activity_names(self, forum_search_num: int) -> list[str]:
        """Get ongoing activity display names for a search, excluding HQ closed and info."""
        with self.connect() as conn:
            query = sqlalchemy.text("""
                SELECT dsa.activity_name
                FROM search_activities sa
                LEFT JOIN dict_search_activities dsa ON sa.activity_type = dsa.activity_id
                WHERE sa.search_forum_num = :forum_search_num
                  AND sa.activity_type <> '9 - hq closed'
                  AND sa.activity_type <> '8 - info'
                  AND sa.activity_status = 'ongoing'
                ORDER BY sa.id;
            """)
            return [row[0] for row in conn.execute(query, dict(forum_search_num=forum_search_num)).fetchall()]

    def get_all_manager_entries(self, forum_search_num: int) -> list[str]:
        """Get all manager attribute entries for a search (not just the latest)."""
        with self.connect() as conn:
            query = sqlalchemy.text("""
                SELECT attribute_value
                FROM search_attributes
                WHERE attribute_name = 'managers'
                  AND search_forum_num = :forum_search_num
                ORDER BY id;
            """)
            return [row[0] for row in conn.execute(query, dict(forum_search_num=forum_search_num)).fetchall()]

    def get_enriched_search_info(self, forum_search_num: int) -> Any:
        """Get enriched search info joined with coordinates and geo folders."""
        with self.connect() as conn:
            query = sqlalchemy.text("""
                WITH
                s AS (
                    SELECT search_forum_num, forum_search_title, num_of_replies, family_name, age,
                        forum_folder_id, search_start_time, display_name, age_min, age_max, status, city_locations,
                        topic_type_id
                    FROM searches
                    WHERE search_forum_num = :forum_search_num
                ),
                ns AS (
                    SELECT s.search_forum_num, s.status, s.forum_search_title, s.num_of_replies, s.family_name,
                        s.age, s.forum_folder_id, sa.latitude, sa.longitude, s.search_start_time, s.display_name,
                        s.age_min, s.age_max, s.status, s.city_locations, s.topic_type_id
                    FROM s
                    LEFT JOIN search_coordinates as sa
                    ON s.search_forum_num=sa.search_id
                )
                SELECT ns.*, f.folder_display_name
                FROM ns
                LEFT JOIN geo_folders_view AS f
                ON ns.forum_folder_id = f.folder_id;
            """)
            return conn.execute(query, dict(forum_search_num=forum_search_num)).fetchone()
