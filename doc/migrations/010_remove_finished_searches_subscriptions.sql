-- Remove all existing subscriptions to "searches finished" folders.
-- These are now hidden from the UI in both MAX and VK bots because
-- users should only subscribe to active searches and info support.
DELETE FROM user_regional_preferences urp
USING geo_folders f
WHERE urp.forum_folder_num = f.folder_id
  AND f.folder_subtype = 'searches finished';
