from __future__ import annotations

from datetime import date, timedelta

import pandas as pd
import streamlit as st

from stocks_tracker.app_data import load_ingest_state, load_prices, load_tickers
from stocks_tracker.backtest import run_from_prices
from stocks_tracker.strategies import STRATEGIES


def _period_returns(df: pd.DataFrame) -> dict[str, float]:
    """YTD / 6-month / 3-month buy-and-hold return on adj_close, in %."""
    last = df.index[-1]
    last_close = float(df["adj_close"].iloc[-1])
    year_start = pd.Timestamp(year=last.year, month=1, day=1)

    def pct(start_ts: pd.Timestamp) -> float:
        sub = df[df.index >= start_ts]
        if len(sub) < 2:
            return float("nan")
        base = float(sub["adj_close"].iloc[0])
        return (last_close / base - 1) * 100 if base else float("nan")

    return {
        "ytd_pct": pct(year_start),
        "m6_pct": pct(last - pd.Timedelta(days=180)),
        "m3_pct": pct(last - pd.Timedelta(days=90)),
    }


st.set_page_config(page_title="Screener — Stocks Tracker", layout="wide")
st.title("Strategy screener")
st.caption(
    "Run one strategy across a slice of the universe and rank the results. "
    "Backtesting many tickers is slow — stick to a filtered subset the first time."
)

tickers = load_tickers()
state = load_ingest_state()
if tickers.empty or state.empty:
    st.error("Need both a populated universe and backfilled prices before screening.")
    st.stop()

merged = tickers.merge(state[["symbol", "last_bar"]], on="symbol", how="inner")
merged = merged[merged["last_bar"].notna()]
if merged.empty:
    st.warning("No tickers have price history yet. Run `python -m stocks_tracker.backfill`.")
    st.stop()

st.sidebar.header("Screener setup")

idx_options = ["SP500", "NDX", "R2000"]
chosen_idx = st.sidebar.multiselect("Index membership", idx_options, default=["SP500"])
pool_mask = merged["index_membership"].apply(lambda ms: any(m in chosen_idx for m in (ms or [])))
pool = sorted(set(merged.loc[pool_mask, "symbol"]))

max_universe = st.sidebar.slider("Max symbols to backtest", 5, max(5, len(pool)),
                                 min(50, len(pool)))
pool = pool[:max_universe]
st.sidebar.caption(f"Backtesting {len(pool)} symbols")

strategy_key = st.sidebar.selectbox(
    "Strategy", list(STRATEGIES.keys()),
    format_func=lambda k: STRATEGIES[k].label,
)
spec = STRATEGIES[strategy_key]
params: dict[str, object] = {}
for p in spec.params:
    if p.kind is int:
        params[p.name] = st.sidebar.slider(p.name, int(p.min), int(p.max), int(p.default), int(p.step))
    else:
        params[p.name] = st.sidebar.slider(p.name, float(p.min), float(p.max), float(p.default), float(p.step))

today = date.today()
start = st.sidebar.date_input("Start", today - timedelta(days=365 * 3))
end = st.sidebar.date_input("End", today)
rank_by = st.sidebar.selectbox(
    "Rank by",
    [
        "sharpe_ratio", "annualized_return_pct", "calmar_ratio", "total_return_pct",
        "ytd_pct", "m6_pct", "m3_pct",
    ],
    index=0,
)

if st.sidebar.button("Run screener", type="primary"):
    rows = []
    progress = st.progress(0.0, text="Starting...")
    for i, symbol in enumerate(pool):
        progress.progress((i + 1) / len(pool), text=f"[{i + 1}/{len(pool)}] {symbol}")
        try:
            df = load_prices(symbol, start=start, end=end)
            if df.empty or len(df) < 60:
                continue
            res = run_from_prices(symbol, df, strategy_key, params=params)
            m = res["metrics"]
            rows.append({"symbol": symbol, **m, **_period_returns(df)})
        except Exception as exc:  # noqa: BLE001
            st.warning(f"{symbol}: {exc}")
    progress.empty()

    if not rows:
        st.info("No successful backtests.")
        st.stop()

    results = pd.DataFrame(rows).sort_values(rank_by, ascending=False).reset_index(drop=True)
    st.success(f"Backtested {len(results)} / {len(pool)} symbols")

    st.dataframe(
        results,
        use_container_width=True,
        hide_index=True,
        column_config={
            "symbol": "Symbol",
            "total_return_pct": st.column_config.NumberColumn("Total %", format="%.2f"),
            "annualized_return_pct": st.column_config.NumberColumn("Annualized %", format="%.2f"),
            "sharpe_ratio": st.column_config.NumberColumn("Sharpe", format="%.2f"),
            "sortino_ratio": st.column_config.NumberColumn("Sortino", format="%.2f"),
            "calmar_ratio": st.column_config.NumberColumn("Calmar", format="%.2f"),
            "max_drawdown_pct": st.column_config.NumberColumn("Max DD %", format="%.2f"),
            "win_rate_pct": st.column_config.NumberColumn("Win %", format="%.1f"),
            "num_trades": "Trades",
            "max_exposure_pct": st.column_config.NumberColumn("Exposure %", format="%.1f"),
            "ytd_pct": st.column_config.NumberColumn("YTD %", format="%+.2f"),
            "m6_pct": st.column_config.NumberColumn("6M %", format="%+.2f"),
            "m3_pct": st.column_config.NumberColumn("3M %", format="%+.2f"),
        },
    )
    st.download_button(
        "Download CSV",
        data=results.to_csv(index=False),
        file_name=f"screener_{strategy_key}.csv",
        mime="text/csv",
    )
else:
    st.info("Configure in the sidebar, then press **Run screener**.")
