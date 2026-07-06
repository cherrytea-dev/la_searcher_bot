-- Migration 009: Add index for efficient batch archiving of notification history
--
-- The notif_by_user__history table had no indexes at all.
-- This composite index enables keyset pagination in archive_to_bigquery,
-- avoiding OOM when processing large daily volumes (e.g. 199k records).
--
-- See issue #7: archive_to_bigquery: OSError [Errno 28] No space left on device

BEGIN;

CREATE INDEX IF NOT EXISTS idx_notif_by_user__history_created_message_id
    ON notif_by_user__history (created, message_id);

COMMIT;
