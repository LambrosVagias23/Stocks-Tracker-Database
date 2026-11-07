"""Thin wrapper around yfinance for batched OHLCV downloads.

The public entry point is `download_history(symbols, start, end)`. It splits
`symbols` into chunks, calls `yfinance.download` once per chunk, and returns
the result as a long-format list of tuples ready for `db.upsert_prices`.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from datetime import date, datetime
from typing import NamedTuple

import pandas as pd
import yfinance as yf

from stocks_tracker.config import YFINANCE_BATCH_SIZE

log = logging.getLogger(__name__)


class PriceRow(NamedTuple):
    symbol: str
    trade_date: date
    high: float | None
    low: float | None
    close: float | None
    adj_close: float | None


def _nan_to_none_float(x) -> float | None:
    return None if x is None or pd.isna(x) else float(x)


def _flatten_download(df: pd.DataFrame, batch: Sequence[str]) -> list[PriceRow]:
    """Convert a yfinance.download result into PriceRow tuples.

    yfinance returns a wide DataFrame with MultiIndex columns ``(ticker, field)``
    for multi-symbol requests and flat columns for single-symbol requests. We
    normalise to MultiIndex, stack the ticker level into a column, then yield
    one row per (symbol, date).
    """
    if df.empty:
        return []

    # Normalise to MultiIndex columns.
    if not isinstance(df.columns, pd.MultiIndex):
        df = df.copy()
        df.columns = pd.MultiIndex.from_product([[batch[0]], df.columns])

    long = (
        df.stack(level=0, future_stack=True)
        .reset_index()
        .rename(
            columns={
                "level_1": "symbol",
                "Ticker": "symbol",
                "Date": "trade_date",
                "Datetime": "trade_date",
                "High": "high",
                "Low": "low",
                "Close": "close",
                "Adj Close": "adj_close",
            }
        )
    )

    long = long.dropna(subset=["high", "low", "close"], how="all")

    out: list[PriceRow] = []
    for row in long.itertuples(index=False):
        d = row.trade_date
        if isinstance(d, pd.Timestamp):
            d = d.date()
        elif isinstance(d, datetime):
            d = d.date()
        out.append(
            PriceRow(
                symbol=str(row.symbol),
                trade_date=d,
                high=_nan_to_none_float(row.high),
                low=_nan_to_none_float(row.low),
                close=_nan_to_none_float(row.close),
                adj_close=_nan_to_none_float(row.adj_close),
            )
        )
    return out


def download_history(
    symbols: Sequence[str],
    start: date | str | None = None,
    end: date | str | None = None,
    period: str | None = None,
    batch_size: int = YFINANCE_BATCH_SIZE,
) -> list[PriceRow]:
    """Download OHLCV for the given symbols from Yahoo Finance.

    Pass either (start, end) or (period) — forwarded to yfinance.download.
    Returns a flat list of PriceRow tuples; failed symbols are logged and
    silently skipped (yfinance may return an empty frame for delisted or
    unknown tickers).
    """
    if not symbols:
        return []
    if period is None and start is None:
        raise ValueError("Pass either period=... or start=...")

    all_rows: list[PriceRow] = []
    total = len(symbols)
    for i in range(0, total, batch_size):
        batch = list(symbols[i : i + batch_size])
        log.info("yfinance batch %d-%d of %d (%d symbols)",
                 i + 1, min(i + batch_size, total), total, len(batch))
        try:
            df = yf.download(
                batch,
                start=start,
                end=end,
                period=period,
                group_by="ticker",
                auto_adjust=False,
                threads=True,
                progress=False,
                show_errors=False,
            )
        except TypeError:
            # Older yfinance versions don't accept show_errors.
            df = yf.download(
                batch,
                start=start,
                end=end,
                period=period,
                group_by="ticker",
                auto_adjust=False,
                threads=True,
                progress=False,
            )
        rows = _flatten_download(df, batch)
        log.info("  -> %d price rows", len(rows))
        all_rows.extend(rows)

    return all_rows
