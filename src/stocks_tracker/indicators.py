"""Thin wrappers around vectorbt indicators with sensible defaults.

Call sites (the Streamlit chart overlays, the strategies module) use these
helpers rather than vectorbt directly so parameter defaults live in one
place and we can swap the underlying library later without churn.
"""

from __future__ import annotations

from typing import NamedTuple

import pandas as pd
import vectorbt as vbt


def sma(close: pd.Series, length: int = 20) -> pd.Series:
    return vbt.MA.run(close, window=length).ma.rename(f"SMA{length}")


def ema(close: pd.Series, length: int = 20) -> pd.Series:
    return vbt.MA.run(close, window=length, ewm=True).ma.rename(f"EMA{length}")


def rsi(close: pd.Series, length: int = 14) -> pd.Series:
    return vbt.RSI.run(close, window=length).rsi.rename(f"RSI{length}")


class MACDResult(NamedTuple):
    macd: pd.Series
    signal: pd.Series
    hist: pd.Series


def macd(close: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9) -> MACDResult:
    m = vbt.MACD.run(close, fast_window=fast, slow_window=slow, signal_window=signal)
    return MACDResult(
        macd=m.macd.rename("MACD"),
        signal=m.signal.rename("MACD_signal"),
        hist=m.hist.rename("MACD_hist"),
    )


class BBResult(NamedTuple):
    upper: pd.Series
    middle: pd.Series
    lower: pd.Series


def bbands(close: pd.Series, length: int = 20, std: float = 2.0) -> BBResult:
    b = vbt.BBANDS.run(close, window=length, alpha=std)
    return BBResult(
        upper=b.upper.rename(f"BB_upper({length},{std})"),
        middle=b.middle.rename(f"BB_mid({length})"),
        lower=b.lower.rename(f"BB_lower({length},{std})"),
    )


def williams_r(
    high: pd.Series, low: pd.Series, close: pd.Series, length: int = 14
) -> pd.Series:
    hh = high.rolling(length).max()
    ll = low.rolling(length).min()
    return (-100 * (hh - close) / (hh - ll)).rename(f"WR{length}")
