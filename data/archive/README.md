# Archive — snapshot before REAL migration

This directory holds a Parquet snapshot of the database taken on
2026-11-07, immediately before migration `005_prices_to_real.sql`
dropped and recreated the `prices` table with REAL columns (to fit
under the Supabase 500 MB free-tier ceiling).

## Contents

| File | Rows | Notes |
|---|---|---|
| `prices_2021.parquet` … `prices_2026.parquet` | 2.92M total | OHLCV, one file per calendar year |
| `tickers.parquet` | ~2,477 | Universe + market_cap as of enrichment |
| `ingest_state.parquet` | ~2,477 | Last-bar cursor and timestamps |

All files are snappy-compressed. Total ~52 MB.

## Why only 2021 onwards?

The archive was taken after an earlier emergency prune that removed
pre-2021 rows (`sql/004_prune_history_to_5y.sql`). The full 10-year
history is restored by a fresh backfill from yfinance **after** the
REAL migration runs — the Parquet files are just belt-and-braces
insurance in case yfinance revises or loses any of these bars.

## Restoring from archive

```python
import pandas as pd
import glob
from stocks_tracker.db import get_engine, upsert_prices

frames = [pd.read_parquet(p) for p in sorted(glob.glob("data/archive/prices_*.parquet"))]
df = pd.concat(frames, ignore_index=True)

rows = [
    (r.symbol, r.trade_date.date(), r.open, r.high, r.low,
     r.close, r.adj_close, r.volume)
    for r in df.itertuples(index=False)
]
upsert_prices(rows)
```

## Why not just commit the full 10y?

~5.3M rows across 10 years would be ~90 MB compressed. GitHub hard-
limits individual files at 100 MB and nudges at 50 MB; splitting by
year keeps every file comfortably under the recommendation, and the
total stays reasonable. Storing full 10y would double this; we rely
on yfinance to be the source of truth for anything the Parquets
don't cover.
