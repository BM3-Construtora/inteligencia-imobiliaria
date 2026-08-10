-- Migration 017 — track LLM normalization to avoid re-processing
-- Saves Gemini calls by skipping already-normalized neighborhoods.

ALTER TABLE neighborhoods
    ADD COLUMN IF NOT EXISTS normalized_at TIMESTAMPTZ;

CREATE INDEX IF NOT EXISTS idx_neighborhoods_normalized_at
    ON neighborhoods (normalized_at)
    WHERE normalized_at IS NULL;
