-- Migration: Add messenger column to notification tables
--
-- Phase 2 of decoupling user registration from Telegram.
-- Adds a `messenger` column to notif_by_user and notif_by_user__history
-- to track which messenger a notification targets.
--
-- Migration steps:
-- 1. Add messenger column to notif_by_user (default 'telegram')
-- 2. Add messenger column to notif_by_user__history (default 'telegram')
--
-- Rollback:
--   ALTER TABLE notif_by_user DROP COLUMN messenger;
--   ALTER TABLE notif_by_user__history DROP COLUMN messenger;

BEGIN;

ALTER TABLE notif_by_user ADD COLUMN IF NOT EXISTS messenger VARCHAR(20) NOT NULL DEFAULT 'telegram';
ALTER TABLE notif_by_user__history ADD COLUMN IF NOT EXISTS messenger VARCHAR(20) NOT NULL DEFAULT 'telegram';

COMMIT;
