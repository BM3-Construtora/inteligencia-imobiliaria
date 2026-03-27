-- 007_deal_velocity.sql — Deal velocity metric

ALTER TABLE neighborhoods ADD COLUMN IF NOT EXISTS avg_days_on_market INT;
