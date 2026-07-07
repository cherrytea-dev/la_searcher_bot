"""DB client for users_activate — onboarding migration SQL."""

from __future__ import annotations

import sqlalchemy

from _dependencies.common.db_client import DBClientBase


class DBClient(DBClientBase):
    """DB client for users_activate onboarding migrations."""

    # ── Shared helpers ────────────────────────────────────────────────

    def insert_onboarding_step(self, user_id: int, step_name: str, step_id: int) -> None:
        """Insert a row into user_onboarding."""
        with self.connect() as conn:
            conn.execute(
                sqlalchemy.text("""
                    INSERT INTO user_onboarding
                    (user_id, step_name, step_id, timestamp)
                    VALUES (:user_id, :step_name, :step_id, '2023-05-14 12:39:00.000000')
                """),
                dict(user_id=user_id, step_name=step_name, step_id=step_id),
            )

    def delete_temp_onboarding_user(self, user_id: int) -> None:
        """Delete a user from temp_onb_step_157."""
        with self.connect() as conn:
            conn.execute(
                sqlalchemy.text("""
                    DELETE FROM temp_onb_step_157
                    WHERE user_id = :user_id
                """),
                dict(user_id=user_id),
            )

    # ── Step-specific queries ─────────────────────────────────────────

    def get_user_for_onboarding_step_0(self) -> int | None:
        """Get next user needing onboarding step_id=0 (old users with /start)."""
        with self.connect() as conn:
            result = conn.execute(
                sqlalchemy.text("""
                    WITH
                        onb AS (
                            select user_id, MAX(step_id) AS onb_step
                            from user_onboarding GROUP BY 1),
                        step_1 AS (
                            select u.user_id, u.reg_date, o.onb_step,
                            CASE WHEN u.reg_date<'2023-05-14 12:40:00.000000' THEN 'before' ELSE 'after' END reg_period
                            FROM users as u
                            LEFT JOIN onb AS o
                            ON u.user_id=o.user_id),
                        step_2 AS (
                            SELECT user_id
                            FROM step_1
                            WHERE reg_period='before' AND onb_step IS NULL),
                        s0 AS (
                            select user_id, timestamp, message_text, MAX(timestamp) OVER (PARTITION BY user_id),
                            CASE WHEN timestamp=(MAX(timestamp) OVER (PARTITION BY user_id)) THEN 1 ELSE 0 END AS check
                            FROM dialogs
                            WHERE author='user'),
                        only_starters AS (
                            SELECT user_id, timestamp
                            FROM s0
                            WHERE s0.check=1 AND message_text='/start')

                    SELECT u.user_id
                    FROM step_2 AS u
                    LEFT JOIN only_starters AS o
                    ON u.user_id=o.user_id
                    WHERE o.user_id IS NOT NULL
                    LIMIT 1;
                """)
            ).scalar()
            return result

    def get_user_for_onboarding_step_0_2(self) -> int | None:
        """Get next user needing onboarding step_id=0 (no folder setting, no role)."""
        with self.connect() as conn:
            result = conn.execute(
                sqlalchemy.text("""
                    with
                        reg_setting AS (
                            select distinct user_id, 'yes' folder_setting
                            from user_regional_preferences),
                        onboard_step AS (
                            select user_id, MAX(step_id) AS onb_step
                            from user_onboarding GROUP BY 1)

                    SELECT u.user_id from users as u
                    LEFT JOIN reg_setting AS rs
                    ON rs.user_id=u.user_id
                    LEFT JOIN onboard_step AS o
                    ON o.user_id=u.user_id
                    WHERE o.onb_step IS NULL and rs.folder_setting IS NULL and u.role is null
                    LIMIT 1
                """)
            ).scalar()
            return result

    def get_user_for_onboarding_step_10(self) -> int | None:
        """Get next user needing onboarding step_id=10 (role_set)."""
        with self.connect() as conn:
            result = conn.execute(
                sqlalchemy.text("""
                    select user_id
                    from user_view
                    where
                        reg_period='before' and
                        last_msg_role='yes' and
                        onb_step IS NULL and
                        folder_setting IS NULL
                    limit 1
                """)
            ).scalar()
            return result

    def get_user_for_onboarding_step_10_2(self) -> int | None:
        """Get next user needing onboarding step_id=10 (no folder, has role)."""
        with self.connect() as conn:
            result = conn.execute(
                sqlalchemy.text("""
                    with
                        reg_setting AS (
                            select distinct user_id, 'yes' folder_setting
                            from user_regional_preferences),
                        onboard_step AS (
                            select user_id, MAX(step_id) AS onb_step
                            from user_onboarding GROUP BY 1)

                    SELECT u.user_id from users as u
                    LEFT JOIN reg_setting AS rs
                    ON rs.user_id=u.user_id
                    LEFT JOIN onboard_step AS o
                    ON o.user_id=u.user_id
                    WHERE o.onb_step IS NULL and rs.folder_setting IS NULL and u.role is NOT null
                    LIMIT 1
                """)
            ).scalar()
            return result

    def get_user_for_onboarding_step_20(self) -> int | None:
        """Get next user needing onboarding step_id=20 (moscow_replied)."""
        with self.connect() as conn:
            result = conn.execute(
                sqlalchemy.text("""
                    select user_id
                    from user_view
                    where
                        reg_period='before' and
                        last_msg_moscow='yes' and
                        onb_step IS NULL and
                        folder_setting IS NULL
                    limit 1
                """)
            ).scalar()
            return result

    def get_user_for_onboarding_step_21(self) -> int | None:
        """Get next user needing onboarding step_id=21 (region_set)."""
        with self.connect() as conn:
            result = conn.execute(
                sqlalchemy.text("""
                    select user_id
                    from user_view_21_new
                    limit 1
                """)
            ).scalar()
            return result

    def get_user_for_onboarding_step_80(self) -> int | None:
        """Get next user needing onboarding step_id=80 (finished, old users)."""
        with self.connect() as conn:
            result = conn.execute(
                sqlalchemy.text("""
                    select user_id
                    from user_view
                    where
                        receives_summaries='yes' and
                        notif_setting='yes' and
                        onb_step is NULL and
                        reg_period='before'
                    limit 1
                """)
            ).scalar()
            return result

    def get_user_for_onboarding_step_80_patch(self) -> int | None:
        """Get next user needing onboarding step_id=80 (patch)."""
        with self.connect() as conn:
            result = conn.execute(
                sqlalchemy.text("""
                    select user_id
                    from user_view_80
                    where receives_summaries='yes' and
                    notif_setting='yes' and
                    onb_step is NULL
                    limit 1
                """)
            ).scalar()
            return result

    def get_user_for_onboarding_step_80_wo_dialogs(self) -> int | None:
        """Get next user needing onboarding step_id=80 (no dialogs)."""
        with self.connect() as conn:
            result = conn.execute(
                sqlalchemy.text("""
                    select user_id
                    from user_view_80_wo_last_msg
                    limit 1
                """)
            ).scalar()
            return result

    def get_user_for_onboarding_step_80_just_summaries(self) -> int | None:
        """Get next user needing onboarding step_id=80 (has summaries)."""
        with self.connect() as conn:
            result = conn.execute(
                sqlalchemy.text("""
                    select user_id
                    from user_view_80
                    WHERE onb_step is NULL and receives_summaries is not null
                    limit 1
                """)
            ).scalar()
            return result

    def get_user_for_onboarding_step_80_all_settings(self) -> int | None:
        """Get next user needing onboarding step_id=80 (has all settings)."""
        with self.connect() as conn:
            result = conn.execute(
                sqlalchemy.text("""
                    select user_id
                    from user_view
                    where notif_setting='yes' and folder_setting='yes' and onb_step is null
                    limit 1
                """)
            ).scalar()
            return result

    def get_user_for_onboarding_step_80_self_deactivated(self) -> int | None:
        """Get next user needing onboarding step_id=80 (self-deactivated)."""
        with self.connect() as conn:
            result = conn.execute(
                sqlalchemy.text("""
                    WITH step_0 AS (
                        select t.user_id, CASE WHEN d.message_text LIKE 'отключ%' THEN 1 ELSE 0 END user_forced
                        from temp_onb_step_157 AS t
                        LEFT JOIN dialogs as d
                        ON t.user_id=d.user_id)
                    select user_id
                    from step_0
                    GROUP BY 1
                    HAVING max(user_forced) > 0
                    limit 1
                """)
            ).scalar()
            return result

    def get_user_for_onboarding_step_99(self) -> int | None:
        """Get next user needing onboarding step_id=99 (unrecognized)."""
        with self.connect() as conn:
            result = conn.execute(
                sqlalchemy.text("""
                    select user_id
                    from temp_onb_step_157
                    limit 1
                """)
            ).scalar()
            return result
