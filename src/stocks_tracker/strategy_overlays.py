"""Per-strategy indicator overlays for the Backtest page.

Given a strategy key, its live params, and the price DataFrame, return the
series that visualise what the strategy is actually watching. Kept in one
module so the Backtest UI stays dumb (just loops over the returned list).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd

from stocks_tracker.indicators import bbands, rsi, sma, williams_r


@dataclass(frozen=True)
class IndicatorLine:
    label: str
    series: pd.Series
    # Where to draw: "price" overlays the price chart, "panel" uses a dedicated
    # lower pane with its own y-axis. Dash and style are plotly line kwargs.
    where: str = "panel"
    dash: str | None = None


@dataclass(frozen=True)
class StrategyOverlay:
    """What to render under / over the equity curve for a strategy."""
    lines: list[IndicatorLine]
    # Horizontal reference lines on the indicator panel, e.g. [-80, -20] for %R.
    hlines: list[float]
    # Human-readable name for the indicator panel y-axis.
    panel_title: str


def overlay_for(strategy_key: str, params: dict[str, Any], df: pd.DataFrame) -> StrategyOverlay:
    close = df["adj_close"]
    if strategy_key == "sma_crossover":
        fast = int(params.get("fast", 20))
        slow = int(params.get("slow", 50))
        return StrategyOverlay(
            lines=[
                IndicatorLine(f"SMA {fast}", sma(close, fast), where="price"),
                IndicatorLine(f"SMA {slow}", sma(close, slow), where="price", dash="dot"),
            ],
            hlines=[],
            panel_title="Price",
        )
    if strategy_key == "rsi_mean_reversion":
        period = int(params.get("period", 14))
        oversold = float(params.get("oversold", 30))
        overbought = float(params.get("overbought", 70))
        return StrategyOverlay(
            lines=[IndicatorLine(f"RSI({period})", rsi(close, period))],
            hlines=[oversold, overbought],
            panel_title="RSI",
        )
    if strategy_key == "bollinger_breakout":
        period = int(params.get("period", 20))
        std = float(params.get("std", 2.0))
        bb = bbands(close, period, std)
        return StrategyOverlay(
            lines=[
                IndicatorLine(f"BB upper({period},{std})", bb.upper, where="price"),
                IndicatorLine(f"BB mid({period})", bb.middle, where="price", dash="dot"),
                IndicatorLine(f"BB lower({period},{std})", bb.lower, where="price"),
            ],
            hlines=[],
            panel_title="Price",
        )
    if strategy_key == "williams_r_mean_reversion":
        period = int(params.get("period", 14))
        oversold = float(params.get("oversold", -80))
        overbought = float(params.get("overbought", -20))
        wr = williams_r(df["high"], df["low"], df["close"], period)
        return StrategyOverlay(
            lines=[IndicatorLine(f"%R({period})", wr)],
            hlines=[oversold, overbought],
            panel_title="Williams %R",
        )
    return StrategyOverlay(lines=[], hlines=[], panel_title="")


def primary_indicator_series(
    strategy_key: str, params: dict[str, Any], df: pd.DataFrame
) -> pd.Series | None:
    """Return the single Series that best represents 'the indicator value' for
    trade-log annotation (e.g. %R or RSI). For strategies that watch two
    overlays simultaneously (SMA cross), return the fast-minus-slow spread.
    """
    close = df["adj_close"]
    if strategy_key == "sma_crossover":
        fast = int(params.get("fast", 20))
        slow = int(params.get("slow", 50))
        return (sma(close, fast) - sma(close, slow)).rename("fast - slow")
    if strategy_key == "rsi_mean_reversion":
        return rsi(close, int(params.get("period", 14))).rename("RSI")
    if strategy_key == "bollinger_breakout":
        bb = bbands(close, int(params.get("period", 20)),
                    float(params.get("std", 2.0)))
        return ((close - bb.middle) / (bb.upper - bb.middle)).rename("band position")
    if strategy_key == "williams_r_mean_reversion":
        return williams_r(df["high"], df["low"], df["close"],
                          int(params.get("period", 14))).rename("%R")
    return None
