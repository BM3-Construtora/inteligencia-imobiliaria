-- Widen price_history.change_pct — absurd swaps (R$1k→R$5M) overflow NUMERIC(6,2).
-- Companion to normalizer fix that also filters implausible deltas before insert.

ALTER TABLE price_history
    ALTER COLUMN change_pct TYPE NUMERIC(10, 2);
