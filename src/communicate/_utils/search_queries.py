"""Telegram-specific search query functions.

These are not mixin methods — they are module-level functions that take
a DB connection as a parameter. This avoids coupling to the DBClient class
hierarchy and makes the queries easier to test and reuse.

VK bot uses a completely different approach for search viewing
(through services/user_settings_service.py), so these are Telegram-only.
"""

import sqlalchemy

from _dependencies.common.commons import SearchFollowingMode

from .common import SearchSummary


def get_active_searches_in_region_limit_20(
    connection: sqlalchemy.engine.Connection, region: int, user_id: int
) -> list[SearchSummary]:
    """Get active searches in a region with follow status, limited to 20."""
    stmt = sqlalchemy.text("""
        SELECT s.search_forum_num, s.search_start_time, s.display_name, sa.latitude, sa.longitude, 
        s.topic_type, s.family_name, s.age, upswl.search_following_mode
        FROM searches s 
        LEFT JOIN search_coordinates sa ON s.search_forum_num = sa.search_id 
        LEFT JOIN search_health_check shc ON s.search_forum_num=shc.search_forum_num
        LEFT JOIN user_pref_search_whitelist upswl ON upswl.search_id=s.search_forum_num and upswl.user_id=:user_id
        WHERE s.forum_folder_id=:region
        AND (
                (
                    (s.status='Ищем' OR s.status='Возобновлен')
                and (shc.status is NULL or shc.status='ok' or shc.status='regular')
                )
            or (upswl.search_following_mode=:search_follow_on
                and s.status in('Ищем', 'Возобновлен', 'СТОП')
                )
            )
        ORDER BY s.search_start_time DESC
        LIMIT 20;""")

    result = connection.execute(
        stmt,
        dict(
            region=region,
            user_id=user_id,
            search_follow_on=SearchFollowingMode.ON,
        ),
    )
    return [
        SearchSummary(
            topic_id=row[0],
            start_time=row[1],
            display_name=row[2],
            search_lat=row[3],
            search_lon=row[4],
            topic_type=row[5],
            name=row[6],
            age=row[7],
            following_mode=row[8],
        )
        for row in result.fetchall()
    ]


def get_all_last_searches_in_region_limit_20(
    connection: sqlalchemy.engine.Connection, region: int, user_id: int, only_followed: bool
) -> list[SearchSummary]:
    """Get all (or followed-only) searches in a region, limited to 20."""
    sql_text = """
        SELECT DISTINCT search_forum_num, search_start_time, display_name, status, status, family_name, age, search_following_mode
        FROM(   -- q
                SELECT s21.*, upswl.search_following_mode FROM 
                    (SELECT search_forum_num, search_start_time, display_name, s01.status as new_status, s01.status, family_name, age 
                    FROM searches s01
                    WHERE forum_folder_id=:region 
                    ) s21 
                INNER JOIN user_pref_search_whitelist upswl 
                    ON upswl.search_id=s21.search_forum_num and upswl.user_id=:user_id
                        and upswl.search_following_mode=:search_follow_on 
                """
    if not only_followed:
        sql_text += """
            UNION
                SELECT s2.*, upswl.search_following_mode FROM 
                    (SELECT search_forum_num, search_start_time, display_name, s00.status as new_status, s00.status, family_name, age 
                    FROM searches s00
                    WHERE forum_folder_id=:region 
                    ORDER BY search_start_time DESC 
                    LIMIT 20) s2 
                LEFT JOIN search_health_check shc ON s2.search_forum_num=shc.search_forum_num
                LEFT JOIN user_pref_search_whitelist upswl ON upswl.search_id=s2.search_forum_num and upswl.user_id=:user_id
                WHERE (shc.status is NULL or shc.status='ok' or shc.status='regular') 
            """
    sql_text += """
            )q
        ORDER BY search_start_time DESC
        LIMIT 20
        ;"""

    stmt = sqlalchemy.text(sql_text)
    result = connection.execute(
        stmt,
        dict(
            region=region,
            user_id=user_id,
            search_follow_on=SearchFollowingMode.ON,
        ),
    )
    return [
        SearchSummary(
            topic_id=row[0],
            start_time=row[1],
            display_name=row[2],
            new_status=row[3],
            status=row[4],
            name=row[5],
            age=row[6],
            following_mode=row[7],
        )
        for row in result.fetchall()
    ]


def get_active_searches_in_one_region(connection: sqlalchemy.engine.Connection, region: int) -> list[SearchSummary]:
    """Get active searches in a region (no follow status)."""
    stmt = sqlalchemy.text("""
        SELECT s2.* FROM 
            (SELECT s.search_forum_num, s.search_start_time, s.display_name, sa.latitude, sa.longitude, 
            s.topic_type, s.family_name, s.age 
            FROM searches s 
            LEFT JOIN search_coordinates sa ON s.search_forum_num = sa.search_id 
            WHERE (s.status='Ищем' OR s.status='Возобновлен') 
                AND s.forum_folder_id=:region ORDER BY s.search_start_time DESC) s2 
        LEFT JOIN search_health_check shc ON s2.search_forum_num=shc.search_forum_num
        WHERE (shc.status is NULL or shc.status='ok' or shc.status='regular') 
        ORDER BY s2.search_start_time DESC;""")

    result = connection.execute(stmt, dict(region=region))
    return [
        SearchSummary(
            topic_id=row[0],
            start_time=row[1],
            display_name=row[2],
            search_lat=row[3],
            search_lon=row[4],
            topic_type=row[5],
            name=row[6],
            age=row[7],
        )
        for row in result.fetchall()
    ]


def get_all_searches_in_one_region_limit_20(
    connection: sqlalchemy.engine.Connection, region: int
) -> list[SearchSummary]:
    """Get all searches in a region (including completed), limited to 20."""
    stmt = sqlalchemy.text("""
        SELECT s2.* FROM 
            (SELECT search_forum_num, search_start_time, display_name, status, status, family_name, age 
            FROM searches 
            WHERE forum_folder_id=:region 
            ORDER BY search_start_time DESC 
            LIMIT 20) s2 
        LEFT JOIN search_health_check shc 
        ON s2.search_forum_num=shc.search_forum_num 
        WHERE (shc.status is NULL or shc.status='ok' or shc.status='regular') 
        ORDER BY s2.search_start_time DESC;""")

    result = connection.execute(stmt, dict(region=region))
    return [
        SearchSummary(
            topic_id=row[0],
            start_time=row[1],
            display_name=row[2],
            new_status=row[3],
            status=row[4],
            name=row[5],
            age=row[6],
        )
        for row in result.fetchall()
    ]
