-- Add nullable market_cap + shares_outstanding + cap_updated_at columns
-- to the tickers table. Populated weekly by `python -m stocks_tracker.enrich`.
-- Idempotent: safe to re-run.

ALTER TABLE tickers
    ADD COLUMN IF NOT EXISTS market_cap         BIGINT,
    ADD COLUMN IF NOT EXISTS shares_outstanding BIGINT,
    ADD COLUMN IF NOT EXISTS cap_updated_at     TIMESTAMPTZ;
