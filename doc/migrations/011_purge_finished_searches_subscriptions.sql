-- Re-run of the migration 010 cleanup.
--
-- Migration 010 removed all subscriptions to "searches finished" folders, but the
-- Telegram bot kept re-adding them on every region re-subscribe: the hardcoded
-- folder map (src/communicate/_utils/regions.py) still contained those folders.
-- The map is fixed now; this cleanup removes the rows that were re-created since.
DELETE FROM user_regional_preferences urp
USING geo_folders f
WHERE urp.forum_folder_num = f.folder_id
  AND f.folder_subtype = 'searches finished';
