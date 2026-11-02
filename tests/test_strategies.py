from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from stocks_tracker.indicators import bbands, ema, macd, rsi, sma
from stocks_tracker.strategies import (
    STRATEGIES,
    bollinger_breakout,
    rsi_mean_reversion,
    sma_crossover,
)


@pytest.fixture
def synth_close() -> pd.Series:
    """100 bars of noisy sinusoidal prices with a trend — produces real signals."""
    rng = np.random.default_rng(0)
    t = np.arange(300)
    trend = 100 + 0.1 * t
    cycle = 15 * np.sin(2 * np.pi * t / 60)
    noise = rng.normal(0, 1, size=t.size)
    return pd.Series(
        trend + cycle + noise,
        index=pd.date_range("2024-01-01", periods=t.size, freq="B"),
    )


def test_indicators_return_series_aligned_to_input(synth_close):
    close = synth_close
    assert sma(close, 20).shape == close.shape
    assert ema(close, 20).shape == close.shape
    assert rsi(close, 14).shape == close.shape
    m = macd(close)
    assert m.macd.shape == close.shape == m.signal.shape == m.hist.shape
    b = bbands(close)
    assert b.upper.shape == close.shape == b.middle.shape == b.lower.shape


def test_sma_crossover_fires_entries_and_exits(synth_close):
    sig = sma_crossover(synth_close, fast=10, slow=40)
    assert sig.entries.sum() >= 1, "oscillating series must trigger at least one entry"
    assert sig.exits.sum() >= 1, "oscillating series must trigger at least one exit"
    assert not (sig.entries & sig.exits).any(), "entry and exit must not coincide"


def test_rsi_mean_reversion_fires(synth_close):
    sig = rsi_mean_reversion(synth_close, period=14, oversold=35, overbought=65)
    assert sig.entries.sum() + sig.exits.sum() >= 1


def test_bollinger_breakout_fires(synth_close):
    sig = bollinger_breakout(synth_close, period=20, std=1.5)
    assert sig.entries.sum() + sig.exits.sum() >= 1


def test_strategy_registry_matches_functions():
    assert STRATEGIES["sma_crossover"].fn is sma_crossover
    assert STRATEGIES["rsi_mean_reversion"].fn is rsi_mean_reversion
    assert STRATEGIES["bollinger_breakout"].fn is bollinger_breakout
    for spec in STRATEGIES.values():
        assert spec.params, f"{spec.key} has no parameters"
