"""Refresh market_cap and shares_outstanding on the tickers table.

Reads yfinance.Ticker().fast_info (markedly lighter than .info) for every
active symbol and UPDATEs the tickers row. Run weekly from GitHub Actions.

CLI::

    python -m stocks_tracker.enrich                       # all active tickers
    python -m stocks_tracker.enrich --limit 50            # smoke test
    python -m stocks_tracker.enrich --tickers AAPL,MSFT   # just these
"""

from __future__ import annotations

import argparse
import logging
from typing import Any

import yfinance as yf
from sqlalchemy import text

from stocks_tracker.db import get_active_tickers, get_engine

log = logging.getLogger(__name__)

COMMIT_EVERY = 100


def _fetch_cap(symbol: str) -> tuple[int | None, int | None]:
    """Return (market_cap, shares_outstanding). Both may be None on failure."""
    try:
        info: Any = yf.Ticker(symbol).fast_info
    except Exception as exc:  # noqa: BLE001
        log.warning("%s: fast_info failed: %s", symbol, exc)
        return (None, None)

    def _get(*keys: str) -> int | None:
        for k in keys:
            try:
                v = info[k] if hasattr(info, "__getitem__") else getattr(info, k, None)
            except (KeyError, AttributeError):
                v = None
            if v is None:
                continue
            try:
                iv = int(v)
            except (TypeError, ValueError):
                continue
            if iv > 0:
                return iv
        return None

    cap = _get("market_cap", "marketCap")
    shares = _get("shares", "shares_outstanding")
    return cap, shares


UPDATE_SQL = text(
    "UPDATE tickers SET market_cap = :cap, shares_outstanding = :shares, "
    "cap_updated_at = NOW() WHERE symbol = :symbol"
)


def enrich(symbols: list[str]) -> dict[str, int]:
    """Enrich each symbol one-by-one, committing every COMMIT_EVERY rows.

    Returns counters: {"ok": N, "null_cap": N, "errors": N}.
    """
    engine = get_engine()
    stats = {"ok": 0, "null_cap": 0, "errors": 0}
    pending = 0
    conn = engine.connect()
    trans = conn.begin()
    try:
        for i, sym in enumerate(symbols, start=1):
            try:
                cap, shares = _fetch_cap(sym)
            except Exception as exc:  # noqa: BLE001
                log.warning("%s: enrichment error: %s", sym, exc)
                stats["errors"] += 1
                cap = shares = None

            conn.execute(UPDATE_SQL, {"cap": cap, "shares": shares, "symbol": sym})
            pending += 1
            if cap is None:
                stats["null_cap"] += 1
            else:
                stats["ok"] += 1

            if pending >= COMMIT_EVERY:
                trans.commit()
                trans = conn.begin()
                pending = 0
                log.info("progress: %d/%d (ok=%d null=%d err=%d)",
                         i, len(symbols), stats["ok"], stats["null_cap"], stats["errors"])
        trans.commit()
    except Exception:
        trans.rollback()
        raise
    finally:
        conn.close()
    return stats


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--tickers", type=str, default=None,
                   help="Comma-separated list of symbols; overrides --limit")
    p.add_argument("--limit", type=int, default=None,
                   help="Enrich only the first N active tickers")
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
        raise SystemExit("No symbols to enrich. Did you run `stocks-universe`?")

    log.info("Enriching %d symbols", len(symbols))
    stats = enrich(symbols)
    print(f"Enrichment complete: ok={stats['ok']} "
          f"null_cap={stats['null_cap']} errors={stats['errors']}")


if __name__ == "__main__":
    main()
