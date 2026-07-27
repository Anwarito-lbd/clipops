-- ClipOps Phase 1 schema
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

CREATE TYPE account_style AS ENUM ('dramatic', 'educational', 'commentary');
CREATE TYPE account_platform AS ENUM ('tiktok', 'content_rewards');

CREATE TYPE clip_status AS ENUM (
  'IMPORTED',
  'ANALYSED',
  'GENERATED',
  'REVIEW_REQUIRED',
  'APPROVED',
  'EXPORTED',
  'MANUALLY_POSTED',
  'SUBMITTED',
  'UNDER_REVIEW',
  'ACCEPTED',
  'VALIDATING',
  'EARNING',
  'PAYOUT_READY',
  'PAID',
  'REJECTED',
  'FAILED'
);

CREATE TYPE campaign_status AS ENUM (
  'draft',
  'scored',
  'rejected',
  'joined',
  'active',
  'closed'
);

CREATE TABLE social_accounts (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  platform account_platform NOT NULL,
  handle TEXT NOT NULL,
  display_name TEXT NOT NULL,
  style account_style,
  audience_geo TEXT[] DEFAULT '{}',
  audience_notes TEXT,
  is_active BOOLEAN NOT NULL DEFAULT TRUE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (platform, handle)
);

CREATE TABLE campaigns (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  name TEXT NOT NULL,
  brand TEXT,
  external_url TEXT,
  raw_brief TEXT NOT NULL,
  status campaign_status NOT NULL DEFAULT 'draft',
  cpm NUMERIC(12, 4),
  total_budget NUMERIC(14, 2),
  budget_utilised NUMERIC(14, 2) DEFAULT 0,
  budget_remaining NUMERIC(14, 2),
  eligibility JSONB DEFAULT '{}',
  required_geo TEXT[] DEFAULT '{}',
  has_rights BOOLEAN DEFAULT TRUE,
  footage_quality_score NUMERIC(5, 2),
  requirement_simplicity_score NUMERIC(5, 2),
  viral_potential_score NUMERIC(5, 2),
  audience_match_score NUMERIC(5, 2),
  competition_score NUMERIC(5, 2),
  approval_probability NUMERIC(5, 4) DEFAULT 0.7,
  expected_views NUMERIC(14, 2) DEFAULT 10000,
  estimated_production_cost NUMERIC(12, 2) DEFAULT 15,
  score NUMERIC(5, 2),
  expected_profit NUMERIC(14, 4),
  reject_reasons TEXT[] DEFAULT '{}',
  is_recommended BOOLEAN DEFAULT FALSE,
  joined_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE campaign_requirements (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  campaign_id UUID NOT NULL REFERENCES campaigns(id) ON DELETE CASCADE,
  required_hashtags TEXT[] DEFAULT '{}',
  required_tags TEXT[] DEFAULT '{}',
  required_disclosure TEXT,
  disclosure_placement TEXT DEFAULT 'beginning',
  min_duration_sec INT DEFAULT 15,
  max_duration_sec INT DEFAULT 60,
  aspect_ratio TEXT DEFAULT '9:16',
  forbidden_words TEXT[] DEFAULT '{}',
  forbidden_claims TEXT[] DEFAULT '{}',
  requires_logo BOOLEAN DEFAULT FALSE,
  requires_cta BOOLEAN DEFAULT FALSE,
  cta_text TEXT,
  posting_deadline TIMESTAMPTZ,
  no_external_music BOOLEAN DEFAULT TRUE,
  extra JSONB DEFAULT '{}',
  snapshot_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  is_immutable_snapshot BOOLEAN NOT NULL DEFAULT FALSE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE source_assets (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  campaign_id UUID NOT NULL REFERENCES campaigns(id) ON DELETE CASCADE,
  filename TEXT NOT NULL,
  storage_path TEXT NOT NULL,
  content_hash TEXT,
  duration_sec NUMERIC(10, 3),
  width INT,
  height INT,
  status clip_status NOT NULL DEFAULT 'IMPORTED',
  transcript_path TEXT,
  scenes_path TEXT,
  error_message TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE clip_candidates (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  source_asset_id UUID NOT NULL REFERENCES source_assets(id) ON DELETE CASCADE,
  campaign_id UUID NOT NULL REFERENCES campaigns(id) ON DELETE CASCADE,
  start_sec NUMERIC(10, 3) NOT NULL,
  end_sec NUMERIC(10, 3) NOT NULL,
  transcript_excerpt TEXT,
  scores JSONB DEFAULT '{}',
  total_score NUMERIC(8, 4) DEFAULT 0,
  rank INT,
  selected BOOLEAN DEFAULT FALSE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE clip_versions (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  candidate_id UUID NOT NULL REFERENCES clip_candidates(id) ON DELETE CASCADE,
  campaign_id UUID NOT NULL REFERENCES campaigns(id) ON DELETE CASCADE,
  social_account_id UUID NOT NULL REFERENCES social_accounts(id),
  style account_style NOT NULL,
  duration_band TEXT NOT NULL,
  hook_variant INT NOT NULL DEFAULT 1,
  subtitle_style TEXT NOT NULL DEFAULT 'bold',
  caption TEXT,
  hook_text TEXT,
  context_intro TEXT,
  status clip_status NOT NULL DEFAULT 'GENERATED',
  requirements_snapshot_id UUID REFERENCES campaign_requirements(id),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE renders (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  clip_version_id UUID NOT NULL REFERENCES clip_versions(id) ON DELETE CASCADE,
  account_slot INT NOT NULL CHECK (account_slot BETWEEN 1 AND 3),
  video_path TEXT,
  caption_path TEXT,
  cover_path TEXT,
  checklist_path TEXT,
  package_dir TEXT,
  content_hash TEXT,
  status clip_status NOT NULL DEFAULT 'GENERATED',
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE compliance_checks (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  clip_version_id UUID NOT NULL REFERENCES clip_versions(id) ON DELETE CASCADE,
  render_id UUID REFERENCES renders(id) ON DELETE SET NULL,
  passed BOOLEAN NOT NULL DEFAULT FALSE,
  checks JSONB NOT NULL DEFAULT '[]',
  override_reason TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE posts (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  clip_version_id UUID NOT NULL REFERENCES clip_versions(id) ON DELETE CASCADE,
  social_account_id UUID NOT NULL REFERENCES social_accounts(id),
  tiktok_url TEXT,
  posted_at TIMESTAMPTZ,
  status clip_status NOT NULL DEFAULT 'EXPORTED',
  notes TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE submissions (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  post_id UUID NOT NULL REFERENCES posts(id) ON DELETE CASCADE,
  campaign_id UUID NOT NULL REFERENCES campaigns(id) ON DELETE CASCADE,
  content_rewards_url TEXT,
  submitted_at TIMESTAMPTZ,
  review_started_at TIMESTAMPTZ,
  status clip_status NOT NULL DEFAULT 'SUBMITTED',
  rejection_reason TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE daily_metrics (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  post_id UUID NOT NULL REFERENCES posts(id) ON DELETE CASCADE,
  metric_date DATE NOT NULL,
  views BIGINT DEFAULT 0,
  likes BIGINT DEFAULT 0,
  comments BIGINT DEFAULT 0,
  shares BIGINT DEFAULT 0,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (post_id, metric_date)
);

CREATE TABLE earnings (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  submission_id UUID NOT NULL REFERENCES submissions(id) ON DELETE CASCADE,
  provisional_amount NUMERIC(14, 4) DEFAULT 0,
  validated_amount NUMERIC(14, 4),
  fee_amount NUMERIC(14, 4),
  net_amount NUMERIC(14, 4),
  currency TEXT DEFAULT 'USD',
  status clip_status NOT NULL DEFAULT 'EARNING',
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE payouts (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  earnings_id UUID NOT NULL REFERENCES earnings(id) ON DELETE CASCADE,
  amount NUMERIC(14, 4) NOT NULL,
  ready_at TIMESTAMPTZ,
  paid_at TIMESTAMPTZ,
  status clip_status NOT NULL DEFAULT 'PAYOUT_READY',
  notes TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_campaigns_score ON campaigns(score DESC NULLS LAST);
CREATE INDEX idx_campaigns_status ON campaigns(status);
CREATE INDEX idx_source_assets_campaign ON source_assets(campaign_id);
CREATE INDEX idx_clip_versions_status ON clip_versions(status);
CREATE INDEX idx_posts_status ON posts(status);
CREATE INDEX idx_submissions_status ON submissions(status);

-- Seed: one CR operator context + three TikTok styles
INSERT INTO social_accounts (platform, handle, display_name, style, audience_geo, audience_notes) VALUES
  ('content_rewards', 'operator', 'ClipOps CR Account', NULL, ARRAY['US','CA'], 'Single Content Rewards identity — never duplicate'),
  ('tiktok', 'tiktok_dramatic', 'TikTok 1 — Dramatic', 'dramatic', ARRAY['US','CA'], 'Fast, dramatic clips'),
  ('tiktok', 'tiktok_educational', 'TikTok 2 — Educational', 'educational', ARRAY['US','CA'], 'Educational / storytelling'),
  ('tiktok', 'tiktok_commentary', 'TikTok 3 — Commentary', 'commentary', ARRAY['US','CA'], 'Commentary, captions, reactions');
