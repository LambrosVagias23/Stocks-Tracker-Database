"""Daily incremental update: fetch the last few bars for every active ticker.

For each ticker we read `ingest_state.last_bar` and classify it:

* ``NULL`` -> this ticker has never been loaded, so delegate to the
  :mod:`stocks_tracker.backfill` path and pull the full history window.
* Set    -> we only need recent bars. We fetch a short lookback window
  (default 7 days, which covers weekends + a holiday) for every such
  ticker in one batched yfinance call. ``ON CONFLICT`` handles the
  overlap with existing rows.

This is intentionally simple and robust: we don't try to compute a
per-ticker start date, we just rely on the primary key + upsert.
"""

from __future__ import annotations

import argparse
import logging
from datetime import date, timedelta

from sqlalchemy import text

from stocks_tracker.backfill import backfill
from stocks_tracker.config import BACKFILL_YEARS, YFINANCE_BATCH_SIZE
from stocks_tracker.db import get_engine, set_ingest_state, upsert_prices
from stocks_tracker.scrape import download_history

log = logging.getLogger(__name__)

DEFAULT_LOOKBACK_DAYS = 7


def _partition_by_ingest_state(symbols: list[str]) -> tuple[list[str], list[str]]:
    """Return (with_last_bar, without_last_bar) for the given symbols."""
    engine = get_engine()
    with engine.connect() as conn:
        known = set(
            conn.execute(
                text(
                    "SELECT symbol FROM ingest_state WHERE last_bar IS NOT NULL "
                    "AND symbol = ANY(:syms)"
                ),
                {"syms": symbols},
            ).scalars()
        )
    with_lb = [s for s in symbols if s in known]
    without_lb = [s for s in symbols if s not in known]
    return with_lb, without_lb


def update_incremental(
    symbols: list[str],
    lookback_days: int = DEFAULT_LOOKBACK_DAYS,
    batch_size: int = YFINANCE_BATCH_SIZE,
) -> int:
    """Pull the last `lookback_days` of bars for `symbols`. Returns rows written."""
    today = date.today()
    start = today - timedelta(days=lookback_days)
    end = today + timedelta(days=1)
    log.info("Incremental update: %d symbols, window %s..%s", len(symbols), start, end)

    rows = download_history(symbols, start=start, end=end, batch_size=batch_size)
    if not rows:
        log.warning("No new bars returned for any of the %d symbols", len(symbols))
        return 0

    upsert_prices(
        [
            (r.symbol, r.trade_date, r.open, r.high, r.low, r.close, r.adj_close, r.volume)
            for r in rows
        ]
    )

    # Walk once to find each symbol's new max trade_date.
    last_bar: dict[str, date] = {}
    for r in rows:
        prev = last_bar.get(r.symbol)
        if prev is None or r.trade_date > prev:
            last_bar[r.symbol] = r.trade_date
    for sym, lb in last_bar.items():
        set_ingest_state(sym, lb)

    log.info("Wrote %d rows across %d symbols", len(rows), len(last_bar))
    return len(rows)


def run(
    lookback_days: int = DEFAULT_LOOKBACK_DAYS,
    years: int = BACKFILL_YEARS,
    limit: int | None = None,
) -> dict[str, int]:
    """Run one full daily update cycle. Returns {'backfilled', 'updated'} row counts."""
    from stocks_tracker.db import get_active_tickers

    symbols = get_active_tickers()
    if limit is not None:
        symbols = symbols[:limit]
    if not symbols:
        raise SystemExit("No active tickers. Did you run `stocks-universe`?")

    with_lb, without_lb = _partition_by_ingest_state(symbols)
    log.info(
        "%d symbols total: %d need backfill, %d need incremental",
        len(symbols), len(without_lb), len(with_lb),
    )

    backfilled = 0
    if without_lb:
        backfilled = backfill(without_lb, years=years)

    updated = 0
    if with_lb:
        updated = update_incremental(with_lb, lookback_days=lookback_days)

    return {"backfilled": backfilled, "updated": updated}


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--lookback-days", type=int, default=DEFAULT_LOOKBACK_DAYS,
                   help=f"Days of history to re-fetch (default: {DEFAULT_LOOKBACK_DAYS})")
    p.add_argument("--years", type=int, default=BACKFILL_YEARS,
                   help="If any tickers need first-time backfill, how many years to pull")
    p.add_argument("--limit", type=int, default=None,
                   help="Process only the first N active tickers (for testing)")
    return p.parse_args()


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    args = _parse_args()
    counts = run(lookback_days=args.lookback_days, years=args.years, limit=args.limit)
    print(
        f"Daily update complete: {counts['backfilled']} backfilled rows + "
        f"{counts['updated']} incremental rows"
    )


if __name__ == "__main__":
    main()
