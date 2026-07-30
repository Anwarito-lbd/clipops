-- Affiliate products + schedules (MoneyPrinterV2-safe subset)

CREATE TABLE IF NOT EXISTS affiliate_products (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  product_url TEXT NOT NULL,
  affiliate_tag TEXT,
  niche TEXT,
  talking_points JSONB DEFAULT '[]',
  disclosure TEXT DEFAULT 'Ad / affiliate link',
  is_active BOOLEAN DEFAULT TRUE,
  created_at TIMESTAMPTZ DEFAULT now(),
  updated_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS affiliate_schedules (
  id TEXT PRIMARY KEY,
  product_id TEXT REFERENCES affiliate_products(id) ON DELETE CASCADE,
  platform TEXT DEFAULT 'twitter',
  times_per_day INT DEFAULT 2,
  enabled BOOLEAN DEFAULT TRUE,
  last_notified_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ DEFAULT now()
);
