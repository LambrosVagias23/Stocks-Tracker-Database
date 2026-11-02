"""One-shot backfill of N years of OHLCV history for every active ticker.

CLI::

    python -m stocks_tracker.backfill                       # all active tickers, 10y
    python -m stocks_tracker.backfill --tickers AAPL,MSFT   # just these
    python -m stocks_tracker.backfill --years 2 --limit 50  # 2y of first 50 tickers

Run this once after `python -m stocks_tracker.universe`. For subsequent daily
runs use `stocks_tracker.update` which only pulls bars after `ingest_state.last_bar`.
"""

from __future__ import annotations

import argparse
import logging
from collections import defaultdict
from datetime import date, timedelta

from stocks_tracker.config import BACKFILL_YEARS, YFINANCE_BATCH_SIZE
from stocks_tracker.db import get_active_tickers, set_ingest_state, upsert_prices
from stocks_tracker.scrape import PriceRow, download_history

log = logging.getLogger(__name__)


def _write_batch(rows: list[PriceRow]) -> dict[str, date]:
    """Upsert prices and return each symbol's max trade_date in this batch."""
    if not rows:
        return {}
    tuples = [
        (r.symbol, r.trade_date, r.open, r.high, r.low, r.close, r.adj_close, r.volume)
        for r in rows
    ]
    upsert_prices(tuples)
    last_bar: dict[str, date] = {}
    for r in rows:
        prev = last_bar.get(r.symbol)
        if prev is None or r.trade_date > prev:
            last_bar[r.symbol] = r.trade_date
    return last_bar


def backfill(
    symbols: list[str],
    years: int = BACKFILL_YEARS,
    batch_size: int = YFINANCE_BATCH_SIZE,
) -> int:
    """Backfill `symbols` and return the total rows inserted."""
    today = date.today()
    start = today - timedelta(days=years * 366 + 5)
    log.info(
        "Backfilling %d symbols over ~%d years (from %s)", len(symbols), years, start
    )

    total_rows = 0
    attempted: set[str] = set()
    returned: set[str] = set()
    symbols_with_counts: dict[str, int] = defaultdict(int)

    for i in range(0, len(symbols), batch_size):
        batch = symbols[i : i + batch_size]
        attempted.update(batch)
        rows = download_history(batch, start=start, end=today + timedelta(days=1))

        last_bar = _write_batch(rows)
        for sym, lb in last_bar.items():
            set_ingest_state(sym, lb)
            returned.add(sym)
        for r in rows:
            symbols_with_counts[r.symbol] += 1
        total_rows += len(rows)
        log.info(
            "progress: %d/%d symbols attempted, %d rows written so far",
            min(i + batch_size, len(symbols)),
            len(symbols),
            total_rows,
        )

    missing = attempted - returned
    if missing:
        log.warning("No data for %d symbols (sample: %s)",
                    len(missing), sorted(missing)[:10])
        for sym in missing:
            set_ingest_state(sym, None, error="no data returned")

    return total_rows


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--tickers", type=str, default=None,
                   help="Comma-separated list of symbols; overrides --limit")
    p.add_argument("--years", type=int, default=BACKFILL_YEARS,
                   help=f"Years of history (default: {BACKFILL_YEARS})")
    p.add_argument("--limit", type=int, default=None,
                   help="Backfill only the first N active tickers")
    p.add_argument("--batch-size", type=int, default=YFINANCE_BATCH_SIZE,
                   help=f"Symbols per yfinance call (default: {YFINANCE_BATCH_SIZE})")
    return p.parse_args()


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    args = _parse_args()
    if args.tickers:
        symbols = [s.strip().upper() for s in args.tickers.split(",") if s.strip()]
    else:
        symbols = get_active_tickers()
        if args.limit:
            symbols = symbols[: args.limit]
    if not symbols:
        raise SystemExit("No symbols to backfill. Did you run `stocks-universe`?")
    total = backfill(symbols, years=args.years, batch_size=args.batch_size)
    print(f"Backfill complete: {total} price rows written across {len(symbols)} symbols")


if __name__ == "__main__":
    main()
