-- Multi-platform: YouTube accounts + generic post URLs + flexible account slots

-- Expand platform enum (Postgres)
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_enum e
    JOIN pg_type t ON e.enumtypid = t.oid
    WHERE t.typname = 'account_platform' AND e.enumlabel = 'youtube'
  ) THEN
    ALTER TYPE account_platform ADD VALUE 'youtube';
  END IF;
END $$;

-- Relax account_slot CHECK (was 1..3 for TikTok-only)
ALTER TABLE renders DROP CONSTRAINT IF EXISTS renders_account_slot_check;
ALTER TABLE renders ADD CONSTRAINT renders_account_slot_check CHECK (account_slot >= 1);

-- Generic post URL (TikTok or YouTube). Keep tiktok_url for backward compat.
ALTER TABLE posts ADD COLUMN IF NOT EXISTS post_url TEXT;
UPDATE posts SET post_url = tiktok_url WHERE post_url IS NULL AND tiktok_url IS NOT NULL;

-- Seed YouTube accounts if missing (idempotent)
INSERT INTO social_accounts (platform, handle, display_name, style, audience_geo, audience_notes, preferred_clip_length, preferred_hooks)
SELECT 'youtube', 'youtube_dramatic', 'YouTube — Dramatic', 'dramatic', ARRAY['US','CA'], 'YouTube Shorts · fast, dramatic clips', '15-25', '["drama","question"]'::jsonb
WHERE NOT EXISTS (SELECT 1 FROM social_accounts WHERE platform = 'youtube' AND handle = 'youtube_dramatic');

INSERT INTO social_accounts (platform, handle, display_name, style, audience_geo, audience_notes, preferred_clip_length, preferred_hooks)
SELECT 'youtube', 'youtube_educational', 'YouTube — Educational', 'educational', ARRAY['US','CA'], 'YouTube Shorts · educational / storytelling', '25-40', '["surprising_fact","question"]'::jsonb
WHERE NOT EXISTS (SELECT 1 FROM social_accounts WHERE platform = 'youtube' AND handle = 'youtube_educational');

INSERT INTO social_accounts (platform, handle, display_name, style, audience_geo, audience_notes, preferred_clip_length, preferred_hooks)
SELECT 'youtube', 'youtube_commentary', 'YouTube — Commentary', 'commentary', ARRAY['US','CA'], 'YouTube Shorts · commentary, captions, reactions', '15-25', '["controversy","question"]'::jsonb
WHERE NOT EXISTS (SELECT 1 FROM social_accounts WHERE platform = 'youtube' AND handle = 'youtube_commentary');
