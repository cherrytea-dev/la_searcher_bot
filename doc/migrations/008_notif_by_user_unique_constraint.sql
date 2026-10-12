-- Add a unique constraint on notif_by_user to prevent duplicate notification records.
-- Duplicates can arise from race conditions in compose_notifications when two
-- instances process the same change_log_id concurrently.
--
-- The constraint covers (change_log_id, user_id, message_type, messenger) —
-- the same tuple used by send_notifications to detect doubling.
--
-- Before adding the constraint, clean up any existing duplicates by keeping
-- only the earliest message_id per group.

-- Step 1: Remove duplicates — keep only the earliest message_id per group.
-- (Autocommit: the two steps cannot share a transaction — see step 2.)
DELETE FROM notif_by_user nbu
WHERE nbu.message_id NOT IN (
    SELECT MIN(message_id)
    FROM notif_by_user
    WHERE completed IS NULL AND cancelled IS NULL
    GROUP BY change_log_id, user_id, message_type, COALESCE(messenger, 'telegram')
    HAVING COUNT(*) > 1
)
AND (nbu.completed IS NULL AND nbu.cancelled IS NULL)
AND EXISTS (
    SELECT 1
    FROM notif_by_user nbu2
    WHERE nbu2.change_log_id = nbu.change_log_id
      AND nbu2.user_id = nbu.user_id
      AND nbu2.message_type = nbu.message_type
      AND COALESCE(nbu2.messenger, 'telegram') = COALESCE(nbu.messenger, 'telegram')
      AND nbu2.message_id < nbu.message_id
      AND nbu2.completed IS NULL AND nbu2.cancelled IS NULL
);

-- Step 2: Add the unique constraint (partially, only for unsent notifications).
-- Deliberately NOT wrapped in BEGIN/COMMIT: CREATE INDEX CONCURRENTLY cannot run inside a
-- transaction block, and wrapping it there made this whole migration fail.
CREATE UNIQUE INDEX CONCURRENTLY IF NOT EXISTS
    notif_by_user_unique_unsent_idx
    ON notif_by_user (change_log_id, user_id, message_type, COALESCE(messenger, 'telegram'))
    WHERE completed IS NULL AND cancelled IS NULL;
