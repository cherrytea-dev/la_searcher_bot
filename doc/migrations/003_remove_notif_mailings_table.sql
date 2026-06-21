-- Migration 003: Remove notif_mailings table
-- 
-- Prerequisites:
--   1. All functions (compose_notifications, send_notifications, archive_notifications)
--      must be deployed with the new code that no longer references mailing_id.
--   2. Run this migration AFTER the new code is deployed.
--
-- Why this order: the new code works with the old schema (it simply ignores mailing_id),
-- but the old code will fail if mailing_id columns are dropped first.
--
-- Changes:
--   1. Drop mailing_id FK constraint from notif_by_user
--   2. Drop mailing_id column from notif_by_user
--   3. Drop mailing_id column from notif_by_user__history
--   4. Drop notif_mailings table
--   5. Drop notif_mailings_mailing_id_seq sequence

-- Step 1: Drop FK constraint referencing notif_mailings
ALTER TABLE notif_by_user DROP CONSTRAINT IF EXISTS notif_by_user_mailing;

-- Step 2: Drop mailing_id column from notif_by_user
ALTER TABLE notif_by_user DROP COLUMN IF EXISTS mailing_id;

-- Step 3: Drop mailing_id column from notif_by_user__history
ALTER TABLE notif_by_user__history DROP COLUMN IF EXISTS mailing_id;

-- Step 4: Drop notif_mailings table
DROP TABLE IF EXISTS notif_mailings;

-- Step 5: Drop the sequence
DROP SEQUENCE IF EXISTS notif_mailings_mailing_id_seq;
