"""Mixin: user filtering queries (users, preferences, whitelists, roles)."""

from typing import Any

import sqlalchemy

from _dependencies.common.db_client import DBClientMixinBase


class UserFilterMixin(DBClientMixinBase):
    """DB operations for filtering and resolving users."""

    def get_admins_and_testers(self) -> tuple[list[int], list[int]]:
        """Get lists of admin and tester user IDs."""
        list_of_admins: list[int] = []
        list_of_testers: list[int] = []

        try:
            with self.connect() as conn:
                user_roles = conn.execute(
                    sqlalchemy.text("""
                        SELECT user_id, role FROM user_roles;
                    """)
                ).fetchall()

                for line in user_roles:
                    if line[1] == 'admin':
                        list_of_admins.append(line[0])
                    elif line[1] == 'tester':
                        list_of_testers.append(line[0])
        except Exception:
            pass

        return list_of_admins, list_of_testers

    def delete_ended_search_following(self, forum_search_num: int, new_status: str) -> None:
        """Delete from user_pref_search_whitelist if search goes to ending status."""
        finished_statuses = ['Завершен', 'НЖ', 'НП', 'Найден']
        if new_status in finished_statuses:
            with self.connect() as conn:
                conn.execute(
                    sqlalchemy.text("""
                        DELETE FROM user_pref_search_whitelist upswl
                        WHERE upswl.search_id=:forum_search_num
                    """),
                    dict(forum_search_num=forum_search_num),
                )

    def compose_users_list_for_change_log(
        self,
        change_type: int,
        forum_folder: int,
        topic_type_id: int,
        forum_search_num: int,
        following_mode_on: str,
    ) -> list[Any]:
        """Get users who should receive notifications for a given change_log line."""
        with self.connect() as conn:
            sql_text_psy = sqlalchemy.text("""
                WITH
                    user_list AS (
                        SELECT user_id, username_telegram, role
                        FROM users WHERE status IS NULL or status='unblocked'),
                    ---
                    user_notif_pref_prep AS (
                        SELECT user_id, array_agg(pref_id) AS agg
                        FROM user_preferences GROUP BY user_id),
                    ---
                    user_notif_type_pref AS
                    (
                        SELECT ulist.user_id, CASE WHEN 30 = ANY(agg) THEN True ELSE False END AS all_notifs
                        FROM user_notif_pref_prep unpp
                        JOIN user_list ulist ON ulist.user_id=unpp.user_id
                        WHERE
                            (30 = ANY(agg) OR :change_type = ANY(agg)
                                OR
                                (/* 'all types in a followed search' mode is on*/
                                    (
                                        exists(select 1 from user_preferences up
                                            where up.user_id=ulist.user_id and up.pref_id=9
                                            /*it is equal to up.preference='all_in_followed_search'*/
                                            )
                                        or :change_type = 1  -- status_changes
                                    )
                                    and /*following mode is on*/
                                        exists (select 1 from user_pref_search_filtering upsf
                                                    where upsf.user_id=ulist.user_id and 'whitelist' = ANY(upsf.filter_name)
                                        )
                                    and  /*this is followed search*/
                                        exists(
                                            select 1 FROM user_pref_search_whitelist upswls
                                            where
                                                upswls.user_id=ulist.user_id
                                                and upswls.search_id = :forum_search_num
                                                and upswls.search_following_mode=:following_mode_on
                                        )
                                )
                            )
                            AND NOT
                            (
                                4 = ANY(agg)  /* 4 is topic_inforg_comment_new */
                                AND :change_type = 2 /* 2 is topic_title_change */ /*AK20240409:issue13*/
                            )
                        ),
                    ---
                    user_folders_prep AS (
                        SELECT user_id, forum_folder_num,
                            CASE WHEN count(forum_folder_num) OVER (PARTITION BY user_id) > 1
                                THEN TRUE ELSE FALSE END as multi_folder
                        FROM user_regional_preferences),
                    ---
                    user_folders AS (
                        SELECT user_id, forum_folder_num, multi_folder
                        FROM user_folders_prep WHERE forum_folder_num= :forum_folder),
                    ---
                    user_topic_pref_prep AS (
                        SELECT user_id, array_agg(topic_type_id) aS agg
                        FROM user_pref_topic_type GROUP BY user_id),
                    ---
                    user_topic_type_pref AS (
                        SELECT user_id, agg AS all_types
                        FROM user_topic_pref_prep
                        WHERE 30 = ANY(agg) OR :topic_type_id = ANY(agg)),
                    ---
                    user_short_list AS (
                        SELECT ul.user_id, ul.username_telegram, ul.role , uf.multi_folder, up.all_notifs
                        FROM user_list as ul
                        LEFT JOIN user_notif_type_pref AS up
                        ON ul.user_id=up.user_id
                        LEFT JOIN user_folders AS uf
                        ON ul.user_id=uf.user_id
                        LEFT JOIN user_topic_type_pref AS ut
                        ON ul.user_id=ut.user_id
                        WHERE
                            uf.forum_folder_num IS NOT NULL AND
                            up.all_notifs IS NOT NULL AND
                            ut.all_types IS NOT NULL),
                    ---
                    user_with_loc AS (
                        SELECT u.user_id, u.username_telegram, uc.latitude, uc.longitude,
                            u.role, u.multi_folder, u.all_notifs
                        FROM user_short_list AS u
                        LEFT JOIN user_coordinates as uc
                        ON u.user_id=uc.user_id),
                    ---
                    user_age_prefs AS (
                        SELECT user_id, array_agg(array[period_min, period_max]) as age_prefs
                        FROM user_pref_age
                        GROUP BY user_id)
                ----------------------------------------------------------------
                SELECT DISTINCT  ns.user_id, ns.username_telegram, ns.latitude, ns.longitude, ns.role,
                        st.num_of_new_search_notifs, ns.multi_folder, ns.all_notifs,
                        upr.radius, uap.age_prefs
                FROM user_with_loc AS ns
                LEFT JOIN user_stat st
                    ON ns.user_id=st.user_id
                LEFT JOIN user_pref_radius upr
                    ON ns.user_id=upr.user_id
                LEFT JOIN user_age_prefs AS uap
                    ON ns.user_id=uap.user_id
                -----
                /*action='get_user_list_filtered_by_folder_and_notif_type' */;
            """)
            return conn.execute(
                sql_text_psy,
                dict(
                    change_type=change_type,
                    forum_folder=forum_folder,
                    topic_type_id=topic_type_id,
                    forum_search_num=forum_search_num,
                    following_mode_on=following_mode_on,
                ),
            ).fetchall()

    def get_debug_users(self) -> list[Any]:
        """Get user_pref_search_whitelist for debug."""
        with self.connect() as conn:
            sql_text = sqlalchemy.text("""
                SELECT user_id, search_id, "status"
                FROM user_pref_search_whitelist
                ORDER BY user_id, search_id;
            """)
            return conn.execute(sql_text).fetchall()

    def get_topic_type_preferences(self, user_id: int) -> list[int]:
        """Get topic type preferences for a user."""
        with self.connect() as conn:
            result = conn.execute(
                sqlalchemy.text("""
                    SELECT topic_type_id FROM user_topic_type_preferences
                    WHERE user_id = :user_id
                """),
                dict(user_id=user_id),
            ).fetchall()
            return [r[0] for r in result]

    def get_users_passing_following_filter(
        self,
        forum_search_num: int,
        search_new_status: str,
        change_type: int,
        following_mode_on: str,
        following_mode_off: str,
    ) -> list[int]:
        """Get user_ids that pass the 'following search' filter."""
        with self.connect() as conn:
            query = sqlalchemy.text("""
                SELECT u.user_id FROM users u
                LEFT JOIN user_pref_search_filtering upsf
                    ON upsf.user_id=u.user_id and 'whitelist' = ANY(upsf.filter_name)
                WHERE upsf.filter_name is not null /* user has activated following mode */
                    AND
                    (
                        (
                            NOT /* 1st condition to suppress notifications */
                                (   /* the user is not following this search */
                                    (   not exists
                                        (
                                            select 1 from user_pref_search_whitelist upswls
                                            WHERE
                                                upswls.user_id=u.user_id
                                                and upswls.search_id = :forum_search_num
                                                and upswls.search_following_mode=:following_mode_on
                                        )
                                        and exists /*another followed search in active status*/
                                        (
                                            select 1 from user_pref_search_whitelist upswls
                                            join searches s on s.search_forum_num=upswls.search_id and s.search_forum_num != :forum_search_num
                                            WHERE
                                                upswls.user_id=u.user_id
                                                and upswls.search_following_mode=:following_mode_on
                                                and s.status not in ('СТОП', 'Завершен', 'НЖ', 'НП', 'Найден')
                                        )
                                    )
                                ) /* end of 1st condition to suppress notifications */
                        OR  /* condition to process the message */
                            ( /*this search is followed*/
                                exists
                                (
                                    select 1 from user_pref_search_whitelist upswls
                                    WHERE
                                        upswls.user_id=u.user_id
                                        and upswls.search_id = :forum_search_num
                                        and upswls.search_following_mode=:following_mode_on
                                )
                                AND
                                ( /*and this search is active*/
                                    :search_new_status NOT in ('СТОП', 'Завершен', 'НЖ', 'НП', 'Найден')
                                    or      /* or not active but the message has change_type=1(status_change) */
                                        (   /* which we should send even for non-active search */
                                            :search_new_status in ('СТОП', 'Завершен', 'НЖ', 'НП', 'Найден')
                                            AND :change_type = 1
                                        )
                                )
                            )
                        )
                        AND NOT exists -- 2nd suppressing condition: the search is in blacklist for this user
                            (
                                select 1 from user_pref_search_whitelist upswls
                                WHERE
                                    upswls.user_id=u.user_id
                                    and upswls.search_id = :forum_search_num
                                    and upswls.search_following_mode=:following_mode_off
                            )
                    )
                    OR upsf.filter_name is null
                    ;
            """)
            rows = conn.execute(
                query,
                dict(
                    forum_search_num=forum_search_num,
                    search_new_status=search_new_status,
                    change_type=change_type,
                    following_mode_on=following_mode_on,
                    following_mode_off=following_mode_off,
                ),
            ).fetchall()
            return [row[0] for row in rows]
