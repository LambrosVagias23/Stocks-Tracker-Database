-- Rebuild `prices` with REAL (float4) columns instead of NUMERIC(18,4).
--
-- Why: NUMERIC(18,4) averages ~12 bytes/value with overhead; REAL is a fixed
-- 4 bytes. On the 500 MB Supabase free tier, 10 years of ~2,500 tickers
-- (5.3M rows) fits in ~400 MB with REAL vs ~660 MB with NUMERIC(18,4).
-- Real's ~7 significant digits is well above what OHLCV needs.
--
-- Why DROP+recreate instead of ALTER COLUMN TYPE: ALTER TYPE rewrites the
-- whole table in place, needing ~2x current size as temp space during the
-- rewrite. On a project already at the free-tier ceiling that fails.
-- DROP releases the old space immediately; the next backfill re-populates.
--
-- Trade-off: this migration DROPS all price history. Run a full backfill
-- after applying it:
--     uv run python -m stocks_tracker.backfill --years 10
--
-- Idempotent: only runs if `prices.close` is currently NUMERIC. If it's
-- already REAL, the block is a no-op.

DO $$
DECLARE
    current_type text;
BEGIN
    SELECT data_type INTO current_type
    FROM information_schema.columns
    WHERE table_schema = 'public'
      AND table_name = 'prices'
      AND column_name = 'close';

    IF current_type IS DISTINCT FROM 'real' THEN
        RAISE NOTICE 'Rebuilding prices table (was: %)...', current_type;

        DROP TABLE IF EXISTS prices CASCADE;

        CREATE TABLE prices (
            symbol      TEXT NOT NULL REFERENCES tickers(symbol) ON DELETE CASCADE,
            trade_date  DATE NOT NULL,
            open        REAL,
            high        REAL,
            low         REAL,
            close       REAL,
            adj_close   REAL,
            volume      BIGINT,
            PRIMARY KEY (symbol, trade_date)
        );
        CREATE INDEX idx_prices_date ON prices(trade_date);

        -- Re-enable RLS and the anon-read policy (dropped with the table).
        ALTER TABLE prices ENABLE ROW LEVEL SECURITY;
        DROP POLICY IF EXISTS anon_read_prices ON prices;
        CREATE POLICY anon_read_prices ON prices FOR SELECT TO anon USING (true);

        -- Clear the ingest_state cursor so the next backfill starts from
        -- scratch (otherwise it would only pull bars after the cached
        -- last_bar date, missing everything older).
        UPDATE ingest_state SET last_bar = NULL, last_error = NULL;

        RAISE NOTICE 'prices rebuilt with REAL columns. Run a full backfill now.';
    ELSE
        RAISE NOTICE 'prices already uses REAL, migration is a no-op.';
    END IF;
END $$;
