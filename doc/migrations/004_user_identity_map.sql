-- Migration: Create user_identity_map table and add internal_user_id to users
--
-- Phase 1 of decoupling user registration from Telegram.
-- Introduces a canonical internal_user_id that is not tied to any messenger.
--
-- Migration steps:
-- 1. Create user_identity_map table
-- 2. Backfill identity_map for existing telegram users
-- 3. Add internal_user_id column to users table
-- 4. Backfill internal_user_id = user_id for existing users
-- 5. Add NOT NULL constraint and unique index
-- 6. Backfill identity_map for existing vk_id links
--
-- Rollback:
--   DROP TABLE user_identity_map;
--   DROP INDEX users_internal_user_id;
--   ALTER TABLE users DROP COLUMN internal_user_id;

BEGIN;

-- Step 1: Create user_identity_map table
CREATE TABLE IF NOT EXISTS user_identity_map (
    id              BIGSERIAL PRIMARY KEY,
    internal_user_id BIGINT NOT NULL,
    messenger       VARCHAR(20) NOT NULL,
    messenger_user_id VARCHAR(100) NOT NULL,
    linked_at       TIMESTAMP DEFAULT NOW(),
    UNIQUE(messenger, messenger_user_id),
    UNIQUE(internal_user_id, messenger)
);

-- Step 2: Backfill identity_map for existing telegram users
-- For existing users, internal_user_id = user_id (1:1 mapping)
INSERT INTO user_identity_map (internal_user_id, messenger, messenger_user_id)
SELECT user_id, 'telegram', user_id::text FROM users
WHERE user_id IS NOT NULL
ON CONFLICT (messenger, messenger_user_id) DO NOTHING;

-- Step 3: Add internal_user_id column to users table
ALTER TABLE users ADD COLUMN IF NOT EXISTS internal_user_id BIGINT;

-- Step 4: Backfill internal_user_id = user_id for existing users
UPDATE users SET internal_user_id = user_id WHERE internal_user_id IS NULL AND user_id IS NOT NULL;

-- Step 5: Add NOT NULL constraint and unique index
-- (only after backfill is complete)
ALTER TABLE users ALTER COLUMN internal_user_id SET NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS users_internal_user_id ON users (internal_user_id);

-- Step 6: Backfill identity_map for existing vk_id links
INSERT INTO user_identity_map (internal_user_id, messenger, messenger_user_id)
SELECT u.internal_user_id, 'vk', u.vk_id FROM users u
WHERE u.vk_id IS NOT NULL
ON CONFLICT (messenger, messenger_user_id) DO NOTHING;

COMMIT;
