-- Migration: Drop unused tables and update views to use geo_divisions
--
-- Removes tables that are not referenced in any operational code:
--   feedback          — no DB operations in operational code
--   news              — no DB operations in operational code
--   old_dict_regions  — replaced by geo_divisions; data is identical
--
-- Views that reference old_dict_regions are recreated with geo_divisions:
--   user_view_21_new
--
-- Rollback:
--   See tests/tools/db.sql for old CREATE TABLE and view definitions.

BEGIN;

DROP TABLE IF EXISTS feedback CASCADE;
DROP TABLE IF EXISTS news CASCADE;

-- Recreate views that depend on old_dict_regions before dropping it.
-- user_view_21_new:
CREATE OR REPLACE VIEW user_view_21_new
AS WITH reg_setting AS (
         SELECT DISTINCT user_regional_preferences.user_id,
            'yes'::text AS folder_setting
           FROM user_regional_preferences
        ), onboard_step AS (
         SELECT user_onboarding.user_id,
            max(user_onboarding.step_id) AS onb_step
           FROM user_onboarding
          GROUP BY user_onboarding.user_id
        ), last_user_msg AS (
         SELECT DISTINCT ON (d.user_id) d.user_id,
            d."timestamp",
            "substring"(d.message_text::text, 1, 50) AS last_msg,
                CASE
                    WHEN d.message_text::text = '/start'::text THEN 'yes'::text
                    ELSE 'no'::text
                END AS last_msg_start,
                CASE
                    WHEN d.message_text::text = 'я состою в ЛизаАлерт'::text OR d.message_text::text = 'я хочу помогать ЛизаАлерт'::text OR d.message_text::text = 'я ищу человека'::text OR d.message_text::text = 'не хочу говорить'::text OR d.message_text::text = 'у меня другая задача'::text THEN 'yes'::text
                    ELSE 'no'::text
                END AS last_msg_role,
                CASE
                    WHEN d.message_text::text = 'нет, я из другого региона'::text THEN 'yes'::text
                    ELSE 'no'::text
                END AS last_msg_moscow,
                CASE
                    WHEN d.message_text::text = 'да, Москва – мой регион'::text OR r.division_id IS NOT NULL THEN 'yes'::text
                    ELSE 'no'::text
                END AS last_msg_reg
           FROM dialogs d
             LEFT JOIN geo_divisions r ON d.message_text::text = r.division_name::text
          WHERE d.author::text = 'user'::text
          ORDER BY d.user_id, d."timestamp" DESC
        )
 SELECT u.user_id,
    rs.folder_setting,
    o.onb_step,
    l_u_m.last_msg_reg
   FROM users u
     LEFT JOIN reg_setting rs ON u.user_id = rs.user_id
     LEFT JOIN onboard_step o ON u.user_id = o.user_id
     LEFT JOIN last_user_msg l_u_m ON u.user_id = l_u_m.user_id
  WHERE u.reg_date < '2023-05-14 12:40:00'::timestamp without time zone AND l_u_m.last_msg_reg = 'yes'::text AND o.onb_step IS NULL;


-- Now safe to drop old_dict_regions (no more dependencies)
DROP TABLE IF EXISTS old_dict_regions CASCADE;

COMMIT;
