-- Sync operator-mode tables with SQLAlchemy models (Postgres)
-- Apply after 20260727100000_init.sql when using Docker Postgres

ALTER TABLE social_accounts ADD COLUMN IF NOT EXISTS preferred_clip_length TEXT;
ALTER TABLE social_accounts ADD COLUMN IF NOT EXISTS preferred_hooks JSONB DEFAULT '[]';

CREATE TABLE IF NOT EXISTS discovered_campaigns (
  id TEXT PRIMARY KEY,
  external_id TEXT,
  external_url TEXT,
  name TEXT NOT NULL,
  brand TEXT,
  raw_payload JSONB DEFAULT '{}',
  cpm NUMERIC(12,4),
  budget_remaining_pct NUMERIC(6,2),
  difficulty TEXT,
  required_clips INT DEFAULT 3,
  min_duration_sec INT DEFAULT 15,
  max_duration_sec INT DEFAULT 60,
  opportunity_score NUMERIC(5,2),
  expected_profit NUMERIC(14,4),
  is_eligible BOOLEAN DEFAULT FALSE,
  reject_reasons JSONB DEFAULT '[]',
  operator_status TEXT DEFAULT 'discovered',
  campaign_id TEXT,
  brief_text TEXT,
  asset_urls JSONB DEFAULT '[]',
  created_at TIMESTAMPTZ DEFAULT now(),
  updated_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS operator_notifications (
  id TEXT PRIMARY KEY,
  kind TEXT NOT NULL,
  title TEXT NOT NULL,
  body TEXT DEFAULT '',
  action_url TEXT,
  action_label TEXT,
  related_id TEXT,
  read BOOLEAN DEFAULT FALSE,
  created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS clip_performance (
  id TEXT PRIMARY KEY,
  campaign_id TEXT,
  account_id TEXT,
  clip_version_id TEXT,
  post_id TEXT,
  hook_type TEXT,
  clip_length_band TEXT,
  topic TEXT,
  editing_style TEXT,
  caption_style TEXT,
  posting_time TIMESTAMPTZ,
  views INT DEFAULT 0,
  likes INT DEFAULT 0,
  comments INT DEFAULT 0,
  shares INT DEFAULT 0,
  approval_status TEXT,
  verified_views INT DEFAULT 0,
  earnings NUMERIC(14,4) DEFAULT 0,
  created_at TIMESTAMPTZ DEFAULT now(),
  updated_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS production_events (
  id TEXT PRIMARY KEY,
  campaign_id TEXT,
  source_asset_id TEXT,
  title TEXT NOT NULL,
  status TEXT DEFAULT 'done',
  created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS operator_settings (
  id TEXT PRIMARY KEY,
  monthly_target NUMERIC(14,2) DEFAULT 1000,
  currency TEXT DEFAULT 'GBP',
  updated_at TIMESTAMPTZ DEFAULT now()
);
