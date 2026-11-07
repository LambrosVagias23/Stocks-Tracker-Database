-- Second-wave size reduction for free tier.
--
-- Changes:
--   1. Drop idx_prices_date (40 MB) — no app query filters by date alone.
--   2. Drop `open` column — breaks candlestick chart (replaced with line chart).
--   3. Drop `volume` column — breaks Volume bars in the Chart lower panel.
--
-- Postgres DROP COLUMN is logical (doesn't rewrite the heap), so just
-- ALTERing wouldn't reduce DB size until VACUUM FULL. We can't VACUUM FULL
-- at this size (needs ~2x table as temp space). So same pattern as 005:
-- DROP TABLE prices CASCADE + recreate with the trimmed schema, let the
-- next backfill repopulate. Idempotent via column-list check.

DO $$
DECLARE
    has_open bool;
    has_volume bool;
BEGIN
    SELECT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema='public' AND table_name='prices' AND column_name='open'
    ) INTO has_open;
    SELECT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema='public' AND table_name='prices' AND column_name='volume'
    ) INTO has_volume;

    IF has_open OR has_volume THEN
        RAISE NOTICE 'Rebuilding prices without open/volume...';

        DROP INDEX IF EXISTS idx_prices_date;
        DROP TABLE IF EXISTS prices CASCADE;

        CREATE TABLE prices (
            symbol      TEXT NOT NULL REFERENCES tickers(symbol) ON DELETE CASCADE,
            trade_date  DATE NOT NULL,
            high        REAL,
            low         REAL,
            close       REAL,
            adj_close   REAL,
            PRIMARY KEY (symbol, trade_date)
        );

        ALTER TABLE prices ENABLE ROW LEVEL SECURITY;
        DROP POLICY IF EXISTS anon_read_prices ON prices;
        CREATE POLICY anon_read_prices ON prices FOR SELECT TO anon USING (true);

        UPDATE ingest_state SET last_bar = NULL, last_error = NULL;

        RAISE NOTICE 'prices rebuilt (high/low/close/adj_close only). Run a full backfill.';
    ELSE
        -- Still try to drop idx_prices_date in case the previous drop failed.
        DROP INDEX IF EXISTS idx_prices_date;
        RAISE NOTICE 'prices already slim, no-op.';
    END IF;
END $$;
