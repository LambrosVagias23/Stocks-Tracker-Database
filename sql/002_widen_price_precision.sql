-- Widen price columns from NUMERIC(12,4) to NUMERIC(18,4).
--
-- The original pins capped values at ~$99,999,999.9999 which blows up when
-- yfinance returns a bar >= $100M (e.g. certain class-A super-highs or
-- occasional garbage from delisted tickers). Keeping scale=4 unchanged makes
-- this a metadata-only ALTER in Postgres — no row rewrite, safe on live data.
-- Idempotent: `ALTER COLUMN TYPE` is a no-op when the type already matches.

ALTER TABLE prices
    ALTER COLUMN open      TYPE NUMERIC(18,4),
    ALTER COLUMN high      TYPE NUMERIC(18,4),
    ALTER COLUMN low       TYPE NUMERIC(18,4),
    ALTER COLUMN close     TYPE NUMERIC(18,4),
    ALTER COLUMN adj_close TYPE NUMERIC(18,4);
