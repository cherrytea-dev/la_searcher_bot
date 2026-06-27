-- Migration 007: Purge search_first_posts__history
--
-- Context: The search_first_posts__history table accumulated ~6 GB / 2M rows
-- on production. The data is never read by any code — it's a dead-letter store.
-- This migration:
--   1. Deletes all records older than 30 days (TTL matching the code in archive_notifications)
--   2. Optionally truncates the entire table if you want a clean slate
--   3. Adds an index on timestamp to make future TTL purges efficient
--
-- Run this AFTER deploying the updated archive_notifications function
-- (which now purges old records after each archivation cycle).

-- Step 1: Check current size before cleanup
SELECT
    pg_size_pretty(pg_total_relation_size('search_first_posts__history')) AS total_size,
    pg_size_pretty(pg_relation_size('search_first_posts__history')) AS table_size,
    count(*) AS row_count
FROM search_first_posts__history;

-- Step 2: Delete records older than 30 days
-- This may take a while on 2M rows. Run during low-traffic hours.
-- If you want to keep absolutely nothing, use TRUNCATE instead (Step 2b).
DELETE FROM search_first_posts__history
WHERE timestamp < NOW() - INTERVAL '30 days';

-- Step 2b (alternative): Truncate everything — no TTL, just wipe it clean.
-- Uncomment if you want a completely fresh start:
-- TRUNCATE search_first_posts__history;

-- Step 3: Add an index on timestamp to make future TTL purges fast
-- (the table has no indexes at all, which makes DELETE slow)
CREATE INDEX IF NOT EXISTS idx_search_first_posts__history_timestamp
    ON search_first_posts__history (timestamp);

-- Step 4: Verify the result
SELECT
    pg_size_pretty(pg_total_relation_size('search_first_posts__history')) AS total_size,
    count(*) AS row_count
FROM search_first_posts__history;

-- Step 5: Optionally run VACUUM to reclaim disk space to the OS
-- (PostgreSQL does not automatically return freed space to the OS)
-- VACUUM FULL search_first_posts__history;
-- Or for the whole database:
-- VACUUM FULL;
