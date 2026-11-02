from __future__ import annotations

import pytest

from stocks_tracker.backtest import run_backtest


@pytest.mark.integration
def test_run_backtest_on_aapl_returns_metrics():
    res = run_backtest("AAPL", "sma_crossover", params={"fast": 10, "slow": 30})
    m = res["metrics"]
    for key in (
        "total_return_pct",
        "annualized_return_pct",
        "sharpe_ratio",
        "max_drawdown_pct",
        "num_trades",
    ):
        assert key in m, f"missing metric {key}"
    assert len(res["equity_curve"]) > 0
    assert res["entries"].sum() >= 0


@pytest.mark.integration
def test_run_backtest_rejects_unknown_strategy():
    with pytest.raises(KeyError):
        run_backtest("AAPL", "nope_strategy")
