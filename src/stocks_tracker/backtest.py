"""Run a strategy over Supabase price history and summarise the result."""

from __future__ import annotations

from datetime import date
from typing import Any

import pandas as pd
import vectorbt as vbt
from sqlalchemy import text

from stocks_tracker.db import get_engine
from stocks_tracker.strategies import STRATEGIES, Signals


def load_prices(
    symbol: str,
    start: date | str | None = None,
    end: date | str | None = None,
) -> pd.DataFrame:
    """Return a DataFrame indexed by trade_date with OHLCV columns, adj_close default."""
    engine = get_engine()
    clauses = ["symbol = :symbol"]
    params: dict[str, Any] = {"symbol": symbol}
    if start is not None:
        clauses.append("trade_date >= :start")
        params["start"] = start
    if end is not None:
        clauses.append("trade_date <= :end")
        params["end"] = end
    sql = (
        "SELECT trade_date, open, high, low, close, adj_close, volume "
        "FROM prices WHERE " + " AND ".join(clauses) + " ORDER BY trade_date"
    )
    with engine.connect() as c:
        df = pd.read_sql(text(sql), c, params=params)
    df["trade_date"] = pd.to_datetime(df["trade_date"])
    df = df.set_index("trade_date")
    for col in ("open", "high", "low", "close", "adj_close"):
        df[col] = df[col].astype(float)
    return df


def _summary(pf: vbt.Portfolio) -> dict[str, Any]:
    """Pick the metrics most interesting to a UI user."""
    stats = pf.stats()
    trades = pf.trades.records_readable
    index = pf.wrapper.index
    total_return = float(pf.total_return())
    years = max((index[-1] - index[0]).days / 365.25, 1e-9)
    annualized_pct = ((1 + total_return) ** (1 / years) - 1) * 100
    return {
        "start": index[0].date().isoformat(),
        "end": index[-1].date().isoformat(),
        "total_return_pct": total_return * 100,
        "annualized_return_pct": annualized_pct,
        "sharpe_ratio": float(stats.get("Sharpe Ratio", float("nan"))),
        "sortino_ratio": float(stats.get("Sortino Ratio", float("nan"))),
        "calmar_ratio": float(stats.get("Calmar Ratio", float("nan"))),
        "max_drawdown_pct": float(stats.get("Max Drawdown [%]", float("nan"))),
        "win_rate_pct": float(stats.get("Win Rate [%]", float("nan"))),
        "num_trades": int(len(trades)),
        "max_exposure_pct": float(stats.get("Max Gross Exposure [%]", float("nan"))),
    }


def run_from_prices(
    symbol: str,
    df: pd.DataFrame,
    strategy_key: str,
    params: dict[str, Any] | None = None,
    initial_cash: float = 10_000.0,
    fees: float = 0.0005,  # 5 bps round-trip
) -> dict[str, Any]:
    """Run `strategy_key` on a pre-fetched price DataFrame.

    The DataFrame is expected to have a DatetimeIndex and at least an
    ``adj_close`` column (as returned by :func:`load_prices` or the
    Streamlit app's data layer).
    """
    if strategy_key not in STRATEGIES:
        raise KeyError(f"Unknown strategy {strategy_key!r}; see strategies.STRATEGIES")
    if df.empty:
        raise ValueError(f"No prices for {symbol} in the requested window")
    spec = STRATEGIES[strategy_key]

    close = df["adj_close"]
    sig: Signals = spec.fn(close, **(params or {}))

    pf = vbt.Portfolio.from_signals(
        close=close,
        entries=sig.entries,
        exits=sig.exits,
        init_cash=initial_cash,
        fees=fees,
        freq="1D",
    )

    return {
        "symbol": symbol,
        "strategy": strategy_key,
        "params": dict(params or {}),
        "metrics": _summary(pf),
        "equity_curve": pf.value(),
        "entries": sig.entries,
        "exits": sig.exits,
        "portfolio": pf,
    }


def run_backtest(
    symbol: str,
    strategy_key: str,
    params: dict[str, Any] | None = None,
    start: date | str | None = None,
    end: date | str | None = None,
    initial_cash: float = 10_000.0,
    fees: float = 0.0005,
) -> dict[str, Any]:
    """CLI/script entry point: pulls prices from Supabase via SQLAlchemy, then backtests."""
    df = load_prices(symbol, start=start, end=end)
    return run_from_prices(symbol, df, strategy_key, params, initial_cash, fees)
