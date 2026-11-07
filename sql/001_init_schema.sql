-- Stocks Tracker initial schema.
-- Idempotent: safe to re-run against an existing database.

CREATE TABLE IF NOT EXISTS tickers (
    symbol            TEXT PRIMARY KEY,
    name              TEXT,
    index_membership  TEXT[] NOT NULL DEFAULT '{}',   -- subset of {'SP500','NDX','R2000'}
    first_seen        DATE,
    active            BOOLEAN NOT NULL DEFAULT TRUE,
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- NOTE: OHLC columns use REAL (float4, 4 bytes) rather than NUMERIC for
-- storage efficiency on the 500MB free tier. Real's ~7 decimal digit
-- precision is well above what stock prices need.
--
-- `open` and `volume` are intentionally omitted (migration 006): dropped to
-- stay under the free-tier ceiling. Trade-off: candlestick chart and volume
-- bars are no longer available (replaced by line chart).
--
-- No idx_prices_date: no app query filters by date alone.
CREATE TABLE IF NOT EXISTS prices (
    symbol      TEXT NOT NULL REFERENCES tickers(symbol) ON DELETE CASCADE,
    trade_date  DATE NOT NULL,
    high        REAL,
    low         REAL,
    close       REAL,
    adj_close   REAL,
    PRIMARY KEY (symbol, trade_date)
);

CREATE TABLE IF NOT EXISTS ingest_state (
    symbol       TEXT PRIMARY KEY REFERENCES tickers(symbol) ON DELETE CASCADE,
    last_bar     DATE,
    last_run_at  TIMESTAMPTZ,
    last_error   TEXT
);

-- Row-Level Security: allow the public `anon` role (used by the Streamlit app)
-- to read tickers and prices, but never write. Writes go through the pooled
-- connection string, which uses the postgres superuser and bypasses RLS.

ALTER TABLE tickers ENABLE ROW LEVEL SECURITY;
ALTER TABLE prices  ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS anon_read_tickers ON tickers;
CREATE POLICY anon_read_tickers ON tickers FOR SELECT TO anon USING (true);

DROP POLICY IF EXISTS anon_read_prices ON prices;
CREATE POLICY anon_read_prices  ON prices  FOR SELECT TO anon USING (true);
