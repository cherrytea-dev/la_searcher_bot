-- Migration: Add index on comments table to speed up duplicate check
-- 
-- Root cause: Sequential comment_number values are used as phpBB pagination offsets (start=),
-- so multiple values can map to the same forum page. get_comment_data() always gets the first
-- post on the page, and write_comment() did a blind INSERT without duplicate checking.
--
-- Fix: 
-- 1. Add a non-unique index on (comment_global_num, search_forum_num) for fast SELECT
-- 2. write_comment() now checks for existing records before INSERT

-- Add a non-unique index for fast duplicate lookups
CREATE INDEX IF NOT EXISTS idx_comments_global_num_search_forum_num
ON comments (comment_global_num, search_forum_num);
