"""Reusable long-only strategy functions.

Each strategy accepts a ``close`` Series (and parameters) and returns a
``Signals`` named-tuple of boolean entry/exit Series aligned to ``close``.
The ``STRATEGIES`` registry at the bottom makes the set introspectable
from the Streamlit UI so new strategies auto-appear in the dropdown.
"""

from __future__ import annotations

from typing import Callable, NamedTuple

import pandas as pd

from stocks_tracker.indicators import bbands, rsi, sma, williams_r


class Signals(NamedTuple):
    entries: pd.Series
    exits: pd.Series


class Param(NamedTuple):
    name: str
    default: int | float
    min: int | float
    max: int | float
    step: int | float
    kind: type  # int or float


class StrategySpec(NamedTuple):
    key: str
    label: str
    fn: Callable[..., Signals]
    params: list[Param]
    description: str
    # "close" (default) → fn is called as fn(close, **params).
    # "ohlc"            → fn is called as fn(high, low, close, **params).
    inputs: str = "close"


# ---- strategies -------------------------------------------------------------


def sma_crossover(close: pd.Series, fast: int = 20, slow: int = 50) -> Signals:
    """Classic golden-cross: enter long when fast SMA crosses above slow SMA."""
    f = sma(close, int(fast))
    s = sma(close, int(slow))
    diff = f - s
    prev = diff.shift(1)
    entries = (prev <= 0) & (diff > 0)
    exits = (prev >= 0) & (diff < 0)
    return Signals(entries.fillna(False), exits.fillna(False))


def rsi_mean_reversion(
    close: pd.Series,
    period: int = 14,
    oversold: float = 30,
    overbought: float = 70,
) -> Signals:
    """Enter long when RSI drops below `oversold`; exit when it rises above `overbought`."""
    r = rsi(close, int(period))
    entries = (r.shift(1) >= oversold) & (r < oversold)
    exits = (r.shift(1) <= overbought) & (r > overbought)
    return Signals(entries.fillna(False), exits.fillna(False))


def bollinger_breakout(
    close: pd.Series,
    period: int = 20,
    std: float = 2.0,
) -> Signals:
    """Enter long on a close above the upper Bollinger band; exit on cross below middle."""
    bb = bbands(close, int(period), float(std))
    entries = (close.shift(1) <= bb.upper.shift(1)) & (close > bb.upper)
    exits = (close.shift(1) >= bb.middle.shift(1)) & (close < bb.middle)
    return Signals(entries.fillna(False), exits.fillna(False))


def williams_r_mean_reversion(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    period: int = 14,
    oversold: float = -80,
    overbought: float = -20,
) -> Signals:
    """Enter long when %R crosses below `oversold`; exit when it crosses above `overbought`.

    Williams %R is bounded in [-100, 0]: 0 = at period high, -100 = at period low.
    Standard thresholds: < -80 is oversold, > -20 is overbought.
    """
    wr = williams_r(high, low, close, int(period))
    entries = (wr.shift(1) >= oversold) & (wr < oversold)
    exits = (wr.shift(1) <= overbought) & (wr > overbought)
    return Signals(entries.fillna(False), exits.fillna(False))


# ---- registry ---------------------------------------------------------------

STRATEGIES: dict[str, StrategySpec] = {
    "sma_crossover": StrategySpec(
        key="sma_crossover",
        label="SMA Crossover",
        fn=sma_crossover,
        params=[
            Param("fast", 20, 2, 100, 1, int),
            Param("slow", 50, 5, 300, 1, int),
        ],
        description="Enter long when the fast SMA crosses above the slow SMA.",
    ),
    "rsi_mean_reversion": StrategySpec(
        key="rsi_mean_reversion",
        label="RSI Mean Reversion",
        fn=rsi_mean_reversion,
        params=[
            Param("period", 14, 2, 50, 1, int),
            Param("oversold", 30, 5, 50, 1, float),
            Param("overbought", 70, 50, 95, 1, float),
        ],
        description="Buy oversold (RSI < threshold), sell overbought (RSI > threshold).",
    ),
    "bollinger_breakout": StrategySpec(
        key="bollinger_breakout",
        label="Bollinger Breakout",
        fn=bollinger_breakout,
        params=[
            Param("period", 20, 5, 100, 1, int),
            Param("std", 2.0, 1.0, 4.0, 0.1, float),
        ],
        description="Buy when price breaks above the upper band; exit on cross below the middle.",
    ),
    "williams_r_mean_reversion": StrategySpec(
        key="williams_r_mean_reversion",
        label="Williams %R Mean Reversion",
        fn=williams_r_mean_reversion,
        params=[
            Param("period", 14, 2, 50, 1, int),
            Param("oversold", -80, -99, -50, 1, float),
            Param("overbought", -20, -50, -1, 1, float),
        ],
        description="Buy when %R crosses below the oversold line (-80); exit when it crosses above the overbought line (-20).",
        inputs="ohlc",
    ),
}
