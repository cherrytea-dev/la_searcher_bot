"""DB client for compose_notifications — extracts all SQL into DBClient methods."""

from typing import Any

import sqlalchemy

from _dependencies.common.db_client import DBClientBase


class DBClient(DBClientBase):
    """DB client for compose_notifications."""

    # ── main.py methods ──────────────────────────────────────────────

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

    def has_uncomposed_notifications(self) -> bool:
        """Check if there are notifications remaining to be composed."""
        with self.connect() as conn:
            result = conn.execute(
                sqlalchemy.text("""
                    SELECT 1 FROM change_log
                    WHERE notification_sent IS NULL
                    OR notification_sent = 's' LIMIT 1;
                """)
            ).fetchall()
            return bool(result)

    def mark_change_log_in_progress(self, change_log_id: int) -> None:
        """Mark change_log record as 'in progress' (s)."""
        with self.connect() as conn:
            conn.execute(
                sqlalchemy.text("""
                    UPDATE change_log SET notification_sent = 's' WHERE id = :a
                """),
                dict(a=change_log_id),
            )

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

    # ── LogRecordComposer methods ────────────────────────────────────

    def select_first_change_log_record(self, record_id: int | None = None) -> list[Any]:
        """Get the first unprocessed record from change_log."""
        with self.connect() as conn:
            query = sqlalchemy.text(f"""
                SELECT search_forum_num, new_value, id, change_type
                FROM change_log
                WHERE (notification_sent IS NULL OR notification_sent = 's')
                {"AND id=:record_id" if record_id is not None else ""}
                ORDER BY id ASC
                LIMIT 1;
            """)
            params = {}
            if record_id is not None:
                params['record_id'] = record_id
            return conn.execute(query, params).fetchone()

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

    def get_unprocessed_comments_for_search(self, forum_search_num: int) -> list[Any]:
        """Get all unprocessed comments for a search with full column set."""
        with self.connect() as conn:
            query = sqlalchemy.text("""
                SELECT comment_url, comment_text, comment_author_nickname,
                       comment_author_link, search_forum_num, comment_num, comment_global_num
                FROM comments
                WHERE notification_sent IS NULL
                  AND search_forum_num = :forum_search_num;
            """)
            return conn.execute(query, dict(forum_search_num=forum_search_num)).fetchall()

    def get_unprocessed_inforg_comments_for_search(self, forum_search_num: int) -> list[Any]:
        """Get unprocessed inforg comments for a search with full column set."""
        with self.connect() as conn:
            query = sqlalchemy.text("""
                SELECT comment_url, comment_text, comment_author_nickname,
                       comment_author_link, search_forum_num, comment_num, comment_global_num
                FROM comments
                WHERE notif_sent_inforg IS NULL
                  AND LOWER(LEFT(comment_author_nickname, 6)) = 'инфорг'
                  AND comment_author_nickname != 'Инфорг кинологов'
                  AND search_forum_num = :forum_search_num;
            """)
            return conn.execute(query, dict(forum_search_num=forum_search_num)).fetchall()

    # ── UsersListComposer methods ────────────────────────────────────

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

    # ── UserListFilter methods ───────────────────────────────────────

    def get_topic_type_preferences(self, user_id: int) -> list[int]:
        with self.connect() as conn:
            result = conn.execute(
                sqlalchemy.text("""
                    SELECT topic_type_id FROM user_topic_type_preferences
                    WHERE user_id = :user_id
                """),
                dict(user_id=user_id),
            ).fetchall()
            return [r[0] for r in result]

    # ── NotificationMaker methods ────────────────────────────────────

    def check_user_notified(self, user_id: int, change_log_id: int) -> bool:
        with self.connect() as conn:
            result = conn.execute(
                sqlalchemy.text("""
                    SELECT 1 FROM notif_by_user
                    WHERE user_id=:user_id AND change_log_id=:change_log_id
                    LIMIT 1;
                """),
                dict(user_id=user_id, change_log_id=change_log_id),
            ).fetchone()
            return result is not None

    def get_message_group_count(self, user_id: int, message_type: str) -> int:
        with self.connect() as conn:
            result = conn.execute(
                sqlalchemy.text("""
                    SELECT MAX(message_group_id)
                    FROM notif_by_user
                    WHERE user_id=:user_id AND message_type=:message_type
                """),
                dict(user_id=user_id, message_type=message_type),
            ).fetchone()
            return result[0] if result[0] is not None else 0

    def batch_insert_notifications(self, records: list[dict]) -> None:
        """Batch insert notification records. Each dict has keys matching notif_by_user columns."""
        if not records:
            return

        with self.connect() as conn:
            columns = ', '.join(records[0].keys())
            placeholders = ', '.join(f':{k}' for k in records[0].keys())
            stmt = sqlalchemy.text(f"""
                INSERT INTO notif_by_user ({columns})
                VALUES ({placeholders})
            """)
            for rec in records:
                conn.execute(stmt, rec)

    def update_notification_statistics(self, user_id: int, value: int) -> None:
        """Update or insert notification statistics count."""
        with self.connect() as conn:
            result = conn.execute(
                sqlalchemy.text("""
                    SELECT id FROM user_notification_statistics
                    WHERE user_id=:user_id
                    FOR UPDATE;
                """),
                dict(user_id=user_id),
            ).fetchone()

            if result:
                conn.execute(
                    sqlalchemy.text("""
                        UPDATE user_notification_statistics
                        SET number_of_notifications=number_of_notifications+:add_value
                        WHERE user_id=:user_id;
                    """),
                    dict(user_id=user_id, add_value=value),
                )
            else:
                conn.execute(
                    sqlalchemy.text("""
                        INSERT INTO user_notification_statistics
                        (user_id, number_of_notifications)
                        VALUES (:user_id, :num);
                    """),
                    dict(user_id=user_id, num=value),
                )

    def mark_comments_processed(self, search_forum_num: int) -> None:
        with self.connect() as conn:
            conn.execute(
                sqlalchemy.text("""
                    UPDATE comments
                    SET notification_sent='y'
                    WHERE search_forum_num=:forum_search_num
                      AND notification_sent IS NULL;
                """),
                dict(forum_search_num=search_forum_num),
            )

    def mark_events_comments_processed(self, search_forum_num: int) -> None:
        with self.connect() as conn:
            conn.execute(
                sqlalchemy.text("""
                    UPDATE comments
                    SET notification_sent='y'
                    WHERE search_forum_num=:forum_search_num
                      AND notification_sent IS NULL
                      AND (comment_text ILIKE '%ДСЛ%' OR comment_text ILIKE '%в работе%');
                """),
                dict(forum_search_num=search_forum_num),
            )

    def mark_change_log_processed(self, change_log_id: int) -> None:
        with self.connect() as conn:
            conn.execute(
                sqlalchemy.text("""
                    UPDATE change_log SET notification_sent='y'
                    WHERE id=:change_log_id;
                """),
                dict(change_log_id=change_log_id),
            )

    # ── NotificationMaker methods (continued) ────────────────────────────

    def resolve_messengers(self, user_ids: list[int]) -> list[tuple]:
        """Batch-resolve messengers for users from user_identity_map."""
        with self.connect() as conn:
            result = conn.execute(
                sqlalchemy.text("""
                    SELECT internal_user_id, messenger
                    FROM user_identity_map
                    WHERE internal_user_id = ANY(:user_ids)
                """),
                {'user_ids': user_ids},
            )
            return list(result.fetchall())

    def check_notification_duplicate(self, change_log_id: int, user_id: int, message_type: str, messenger: str) -> int:
        """Check if a notification record already exists (DIAG)."""
        with self.connect() as conn:
            result = conn.execute(
                sqlalchemy.text("""
                    SELECT count(*) FROM notif_by_user
                    WHERE change_log_id = :cl AND user_id = :uid
                      AND message_type = :mt AND messenger = :msgr
                      AND completed IS NULL AND cancelled IS NULL
                """),
                dict(cl=change_log_id, uid=user_id, mt=message_type, msgr=messenger),
            )
            return result.scalar()

    def record_user_stat_notifications(self, user_id: int, number_to_add: int) -> None:
        """Record +1 into user_stat for new search notifications (usability tips)."""
        with self.connect() as conn:
            conn.execute(
                sqlalchemy.text("""
                    INSERT INTO user_stat (user_id, num_of_new_search_notifs)
                    VALUES(:user_id, :number_to_add)
                    ON CONFLICT (user_id) DO
                    UPDATE SET num_of_new_search_notifs = :number_to_add +
                    (SELECT num_of_new_search_notifs from user_stat WHERE user_id = :user_id)
                    WHERE user_stat.user_id = :user_id;
                """),
                dict(user_id=int(user_id), number_to_add=int(number_to_add)),
            )

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

    def get_users_with_prepared_message(self, change_log_id: int) -> list[int]:
        """Get list of user_ids who already have composed messages for this change_log."""
        with self.connect() as conn:
            query = sqlalchemy.text("""
                SELECT user_id
                FROM notif_by_user
                WHERE created IS NOT NULL
                  AND change_log_id = :change_log_id
                /*action='get_from_sql_list_of_users_with_already_composed_messages 2.0'*/ ;
            """)
            raw_data = conn.execute(query, dict(change_log_id=change_log_id)).fetchall()
            return [line[0] for line in raw_data]

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

    def mark_comments_processed_by_change_type(self, forum_search_num: int, change_type: int) -> None:
        """Mark comments as processed based on change type (3=comment, 4=inforg comment)."""
        with self.connect() as conn:
            if change_type == 3:  # ChangeType.topic_comment_new
                conn.execute(
                    sqlalchemy.text("""
                        UPDATE comments SET notification_sent = 'y'
                        WHERE search_forum_num=:forum_search_num;
                    """),
                    dict(forum_search_num=forum_search_num),
                )
            elif change_type == 4:  # ChangeType.topic_inforg_comment_new
                conn.execute(
                    sqlalchemy.text("""
                        UPDATE comments SET notif_sent_inforg = 'y'
                        WHERE search_forum_num=:forum_search_num;
                    """),
                    dict(forum_search_num=forum_search_num),
                )
            else:
                # Fallback: mark all
                conn.execute(
                    sqlalchemy.text("""
                        UPDATE comments SET notification_sent = 'y'
                        WHERE notification_sent is Null OR notification_sent = 's';
                    """),
                )
                conn.execute(
                    sqlalchemy.text("""
                        UPDATE comments SET notif_sent_inforg = 'y'
                        WHERE notif_sent_inforg is Null;
                    """),
                )

    def mark_all_comments_processed_fallback(self) -> None:
        """Fallback: mark ALL comments as processed (used in except block)."""
        with self.connect() as conn:
            conn.execute(
                sqlalchemy.text("""
                    UPDATE comments SET notification_sent = 'y'
                    WHERE notification_sent is Null OR notification_sent = 's';
                """)
            )
            conn.execute(
                sqlalchemy.text("""
                    UPDATE comments SET notif_sent_inforg = 'y'
                    WHERE notif_sent_inforg is Null;
                """)
            )
