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

CREATE TABLE IF NOT EXISTS prices (
    symbol      TEXT NOT NULL REFERENCES tickers(symbol) ON DELETE CASCADE,
    trade_date  DATE NOT NULL,
    open        NUMERIC(18,4),
    high        NUMERIC(18,4),
    low         NUMERIC(18,4),
    close       NUMERIC(18,4),
    adj_close   NUMERIC(18,4),
    volume      BIGINT,
    PRIMARY KEY (symbol, trade_date)
);
CREATE INDEX IF NOT EXISTS idx_prices_date ON prices(trade_date);

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
