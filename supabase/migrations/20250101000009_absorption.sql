-- 009_absorption.sql — Absorption metrics + deactivation tracking

-- Track when listings are removed from portals
ALTER TABLE listings ADD COLUMN IF NOT EXISTS deactivated_at TIMESTAMPTZ;

-- Absorption metrics per neighborhood
ALTER TABLE neighborhoods ADD COLUMN IF NOT EXISTS absorption_rate NUMERIC(5,2);
ALTER TABLE neighborhoods ADD COLUMN IF NOT EXISTS months_of_inventory NUMERIC(5,1);
ALTER TABLE neighborhoods ADD COLUMN IF NOT EXISTS removed_last_30d INT DEFAULT 0;
ALTER TABLE neighborhoods ADD COLUMN IF NOT EXISTS new_last_30d INT DEFAULT 0;
