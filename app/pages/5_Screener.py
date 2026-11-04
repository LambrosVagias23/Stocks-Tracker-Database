from __future__ import annotations

from datetime import date, timedelta

import pandas as pd
import streamlit as st

from stocks_tracker.app_data import load_ingest_state, load_prices, load_tickers
from stocks_tracker.backtest import run_from_prices
from stocks_tracker.indicators import williams_r
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


def _current_wr(df: pd.DataFrame, period: int = 14) -> float:
    """Latest Williams %R value, or NaN if not enough bars."""
    if len(df) < period + 1:
        return float("nan")
    try:
        return float(williams_r(df["high"], df["low"], df["close"], period).iloc[-1])
    except Exception:
        return float("nan")


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

cap_by_symbol: dict[str, float | None] = (
    dict(zip(tickers["symbol"], tickers["market_cap"], strict=False))
    if "market_cap" in tickers.columns
    else {}
)

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
st.sidebar.caption(f"Backtesting up to {len(pool)} symbols (before pre-filters)")

# --- Pre-filters: skip tickers that don't match these criteria before the
# heavy backtest step. Defaults are permissive — nothing is filtered until
# the user tightens a knob.
with st.sidebar.expander("Pre-filters (optional)"):
    st.caption("Skip tickers that fail these before backtesting.")
    min_ytd = st.number_input("Min YTD %", value=-100.0, step=5.0, format="%.1f",
                              help="Exclude tickers below this year-to-date return")
    min_m6 = st.number_input("Min 6M %", value=-100.0, step=5.0, format="%.1f")
    min_m3 = st.number_input("Min 3M %", value=-100.0, step=5.0, format="%.1f")
    wr_lo, wr_hi = st.slider(
        "Current Williams %R range",
        -100.0, 0.0, (-100.0, 0.0), 1.0,
        help="Keep tickers whose latest %R(14) falls in this band. "
             "e.g. (-100, -80) = currently oversold; (-20, 0) = currently overbought.",
    )
    cap_available = any(v for v in cap_by_symbol.values())
    if cap_available:
        min_cap_b = st.number_input("Min market cap ($B)", value=0.0, step=1.0,
                                    min_value=0.0,
                                    help="0 = don't filter. 10 = large-caps only.")
        max_cap_b = st.number_input("Max market cap ($B)", value=0.0, step=10.0,
                                    min_value=0.0,
                                    help="0 = no upper cap.")
    else:
        min_cap_b = max_cap_b = 0.0

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
        "ytd_pct", "m6_pct", "m3_pct", "market_cap", "current_wr",
    ],
    index=0,
)

st.sidebar.divider()
st.sidebar.markdown("**Risk management**")
use_sl = st.sidebar.checkbox("Stop loss", value=False, key="scr_sl")
sl_pct = st.sidebar.slider("Stop loss %", 0.5, 25.0, 5.0, 0.5,
                           disabled=not use_sl, key="scr_sl_pct") if use_sl else 0.0
sl_trail = st.sidebar.checkbox("Trailing stop", value=False,
                                disabled=not use_sl, key="scr_sl_trail")
use_tp = st.sidebar.checkbox("Take profit", value=False, key="scr_tp")
tp_pct = st.sidebar.slider("Take profit %", 0.5, 50.0, 10.0, 0.5,
                           disabled=not use_tp, key="scr_tp_pct") if use_tp else 0.0
use_time = st.sidebar.checkbox("Max hold days", value=False, key="scr_time")
max_hold = st.sidebar.slider("Hold days", 1, 60, 10, 1,
                             disabled=not use_time, key="scr_max_hold") if use_time else 0

if st.sidebar.button("Run screener", type="primary"):
    rows = []
    filtered_out = 0
    progress = st.progress(0.0, text="Starting...")
    for i, symbol in enumerate(pool):
        progress.progress((i + 1) / len(pool), text=f"[{i + 1}/{len(pool)}] {symbol}")
        try:
            df = load_prices(symbol, start=start, end=end)
            if df.empty or len(df) < 60:
                continue

            # --- Apply pre-filters -----------------------------------------
            pr = _period_returns(df)
            curr_wr = _current_wr(df, 14)
            cap = cap_by_symbol.get(symbol)

            if min_ytd > -100 and (pd.isna(pr["ytd_pct"]) or pr["ytd_pct"] < min_ytd):
                filtered_out += 1
                continue
            if min_m6 > -100 and (pd.isna(pr["m6_pct"]) or pr["m6_pct"] < min_m6):
                filtered_out += 1
                continue
            if min_m3 > -100 and (pd.isna(pr["m3_pct"]) or pr["m3_pct"] < min_m3):
                filtered_out += 1
                continue
            if (wr_lo > -100 or wr_hi < 0) and (
                pd.isna(curr_wr) or not (wr_lo <= curr_wr <= wr_hi)
            ):
                filtered_out += 1
                continue
            if min_cap_b > 0 and (cap is None or cap < min_cap_b * 1e9):
                filtered_out += 1
                continue
            if max_cap_b > 0 and cap is not None and cap > max_cap_b * 1e9:
                filtered_out += 1
                continue

            # --- Passed filters: run the backtest --------------------------
            res = run_from_prices(
                symbol, df, strategy_key, params=params,
                sl_stop=(sl_pct / 100) if use_sl else None,
                tp_stop=(tp_pct / 100) if use_tp else None,
                sl_trail=sl_trail if use_sl else False,
                max_hold_days=max_hold if use_time else None,
            )
            m = res["metrics"]
            rows.append({
                "symbol": symbol,
                **m,
                **pr,
                "current_wr": curr_wr,
                "market_cap": cap,
            })
        except Exception as exc:  # noqa: BLE001
            st.warning(f"{symbol}: {exc}")
    progress.empty()

    if not rows:
        st.info(f"No tickers passed the filters ({filtered_out} filtered out).")
        st.stop()

    results = pd.DataFrame(rows).sort_values(rank_by, ascending=False).reset_index(drop=True)
    filter_summary = f" · {filtered_out} filtered out" if filtered_out else ""
    st.success(f"Backtested {len(results)} / {len(pool)} symbols{filter_summary}")

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
            "current_wr": st.column_config.NumberColumn("%R(14)", format="%.1f"),
            "market_cap": st.column_config.NumberColumn("Market cap", format="compact"),
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
