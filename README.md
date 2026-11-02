# Stocks Tracker Database

Daily OHLCV for ~2,500 US tickers (S&P 500 + NASDAQ 100 + Russell 2000)
loaded incrementally into Supabase, with a Streamlit app for charting
and strategy backtesting.

> Live app: _not yet deployed — follow the "Deploy" section below._

## Stack

| Layer         | Choice |
| ------------- | ----------------------------------------------- |
| Data source   | [yfinance](https://pypi.org/project/yfinance/) |
| Universe      | Wikipedia (S&P 500) + Slickcharts (NDX) + stockanalysis.com (R2000) |
| Database      | [Supabase](https://supabase.com) Postgres (free tier) |
| Scheduler     | GitHub Actions cron (22:30 UTC Mon–Fri)       |
| Backtesting   | [vectorbt](https://vectorbt.dev)              |
| UI            | [Streamlit](https://streamlit.io) → Community Cloud |

## Project layout

```
sql/                 schema (apply once in Supabase SQL editor OR via `python -m stocks_tracker.db`)
src/stocks_tracker/  python package: universe, scrape, backfill, update, backtest...
app/                 streamlit app (streamlit_app.py + pages/)
.github/workflows/   daily update cron
```

## Local development

Prerequisites: Python 3.11 or 3.12, [uv](https://docs.astral.sh/uv/).

```powershell
# 1. Fill .env — copy from .env.example and paste Supabase credentials
cp .env.example .env

# 2. Install deps (core only is enough for scraping + backfill)
uv sync

# 3. Apply the schema (idempotent)
uv run python -m stocks_tracker.db

# 4. Scrape the universe into the tickers table (~2,500 rows)
uv run python -m stocks_tracker.universe

# 5. Backfill ten years of OHLCV. First full run is slow (~45–60 min).
uv run python -m stocks_tracker.backfill

# 6. Launch the Streamlit app (requires the `app` extras)
uv sync --extra app
uv run streamlit run app/streamlit_app.py
```

Daily deltas after the initial backfill: `uv run python -m stocks_tracker.update`.

## Deploy

### GitHub Actions (daily update cron)

1. Push this repo to GitHub.
2. In **Settings → Secrets and variables → Actions**, add
   `SUPABASE_DB_URL_POOLED` with the Transaction-pooler connection
   string (port 6543, `aws-0-<region>.pooler.supabase.com`). Pooled is
   required because the direct host is IPv6-only on the Supabase free
   tier and GitHub-hosted runners are IPv4.
3. Trigger the workflow once from the **Actions** tab (**Run workflow**)
   to confirm it works. From then on it runs 22:30 UTC on weekdays.

### Streamlit Community Cloud (public UI)

1. Push the repo (same as above).
2. Sign in to [share.streamlit.io](https://share.streamlit.io) with
   GitHub, click **New app**, pick this repo and branch.
3. Set **Main file path** to `app/streamlit_app.py`.
4. Under **Advanced settings → Secrets**, paste:

   ```toml
   SUPABASE_URL = "https://<your-project-ref>.supabase.co"
   SUPABASE_ANON_KEY = "sb_publishable_..."
   ```

   The app connects over PostgREST using the anon key, which only has
   read access thanks to the RLS policies in `sql/001_init_schema.sql`.
5. Deploy. Replace the "Live app" link at the top of this README with
   the resulting URL.

## Tests

```powershell
uv sync --extra dev
uv run pytest
```

Integration tests marked `@pytest.mark.integration` hit the real
Supabase pooler and need `.env` populated.
