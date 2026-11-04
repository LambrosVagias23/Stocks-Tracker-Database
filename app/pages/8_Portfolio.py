"""Portfolio-level backtest: run one strategy across a universe, pick the
top N by market cap each time multiple signals fire, allocate equally.

This is the "fit the whole strategy" page — the Screener runs each ticker
independently; this one runs them as a shared cash pool so you can test
"find Connors oversold setups across the S&P 500, buy the top 2 largest
candidates, exit via SL / TP / time stop".
"""

from __future__ import annotations

from datetime import date, timedelta

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
import vectorbt as vbt

from stocks_tracker.app_data import load_ingest_state, load_prices, load_tickers
from stocks_tracker.app_theme import COLORS, plotly_template
from stocks_tracker.strategies import STRATEGIES

st.set_page_config(
    page_title="Portfolio — Stocks Tracker",
    page_icon=":material/account_balance_wallet:",
    layout="wide",
)
st.title("Portfolio backtest")
st.caption(
    "Run one strategy across a universe. On days when more candidates "
    "signal than can fit in the portfolio, keep the top N by market cap. "
    "Positions are equally-weighted via shared cash."
)

tickers = load_tickers()
state = load_ingest_state()
if tickers.empty or state.empty:
    st.error("Need both a populated universe and backfilled prices.")
    st.stop()
if "market_cap" not in tickers.columns:
    st.warning("Tickers table has no market_cap column. Run the enrich workflow.")
    st.stop()

merged = tickers.merge(state[["symbol", "last_bar"]], on="symbol", how="inner")
merged = merged[merged["last_bar"].notna()]
merged = merged[merged["market_cap"].notna()]

# --- Sidebar: universe -----------------------------------------------------

st.sidebar.header("Universe")
idx_options = ["SP500", "NDX", "R2000"]
chosen_idx = st.sidebar.multiselect("Index membership", idx_options, default=["SP500"])
pool_mask = merged["index_membership"].apply(
    lambda ms: any(m in chosen_idx for m in (ms or []))
)
pool = merged.loc[pool_mask].sort_values(
    "market_cap", ascending=False, na_position="last"
)
universe_size = st.sidebar.slider(
    "Universe size (top by market cap)", 10, max(10, len(pool)),
    min(100, len(pool)),
    help="Backtesting hundreds of tickers takes time. Start with 50-100.",
)
pool = pool.head(universe_size)
st.sidebar.caption(f"{len(pool)} tickers in pool")

# --- Sidebar: strategy -----------------------------------------------------

st.sidebar.header("Strategy")
strategy_key = st.sidebar.selectbox(
    "Strategy", list(STRATEGIES.keys()),
    format_func=lambda k: STRATEGIES[k].label,
)
spec = STRATEGIES[strategy_key]
st.sidebar.caption(spec.description)
params: dict[str, object] = {}
for p in spec.params:
    if p.kind is int:
        params[p.name] = st.sidebar.slider(p.name, int(p.min), int(p.max),
                                            int(p.default), int(p.step),
                                            key=f"pf_{p.name}")
    else:
        params[p.name] = st.sidebar.slider(p.name, float(p.min), float(p.max),
                                            float(p.default), float(p.step),
                                            key=f"pf_{p.name}")

# --- Sidebar: allocation ---------------------------------------------------

st.sidebar.header("Allocation")
top_n = st.sidebar.slider(
    "Top N positions (by market cap at signal time)", 1, 10, 2,
    help="When more tickers signal on the same bar, keep only the top N by cap. "
         "Portfolio holds up to N positions at a time; each targets 1/N of cash.",
)
initial_cash = st.sidebar.number_input("Initial cash ($)", value=100_000,
                                       step=10_000, min_value=1_000)
fees_bps = st.sidebar.number_input("Fees (bps/trade)", value=5.0, step=1.0,
                                    min_value=0.0)

# --- Sidebar: window + pre-filters ----------------------------------------

st.sidebar.header("Window")
today = date.today()
start = st.sidebar.date_input("Start", today - timedelta(days=365 * 3))
end = st.sidebar.date_input("End", today)

with st.sidebar.expander("Per-bar pre-filters (optional)"):
    st.caption(
        "Checked each bar — a ticker is eligible to enter only if its "
        "rolling return / fundamentals pass on that specific day. No "
        "lookahead bias."
    )
    min_ytd = st.number_input("Min trailing-YTD %", value=-100.0, step=5.0,
                              key="pf_min_ytd")
    min_m6 = st.number_input("Min trailing 6M %", value=-100.0, step=5.0,
                             key="pf_min_m6")
    min_m3 = st.number_input("Min trailing 3M %", value=-100.0, step=5.0,
                             key="pf_min_m3")

# --- Sidebar: risk management ---------------------------------------------

st.sidebar.header("Risk management")
use_sl = st.sidebar.checkbox("Stop loss", value=True, key="pf_sl")
sl_pct = st.sidebar.slider("Stop loss %", 0.5, 25.0, 5.0, 0.5,
                           disabled=not use_sl, key="pf_sl_pct") if use_sl else 0.0
sl_trail = st.sidebar.checkbox("Trailing stop", value=False, disabled=not use_sl,
                                key="pf_sl_trail")
use_tp = st.sidebar.checkbox("Take profit", value=True, key="pf_tp")
tp_pct = st.sidebar.slider("Take profit %", 0.5, 50.0, 10.0, 0.5,
                           disabled=not use_tp, key="pf_tp_pct") if use_tp else 0.0
use_time = st.sidebar.checkbox("Max hold days", value=True, key="pf_time")
max_hold = st.sidebar.slider("Hold days", 1, 60, 10, 1, disabled=not use_time,
                             key="pf_max_hold") if use_time else 0


# --- Helpers ---------------------------------------------------------------

def _per_bar_ytd(close_df: pd.DataFrame) -> pd.DataFrame:
    """For each (date, ticker), close / close_at_year_start_of_that_year - 1."""
    year_start = close_df.groupby(close_df.index.year).transform("first")
    return (close_df / year_start - 1) * 100


def _per_bar_rolling_pct(close_df: pd.DataFrame, bars: int) -> pd.DataFrame:
    """Rolling return over `bars` trading days, in %."""
    return close_df.pct_change(periods=bars) * 100


def _enforce_top_n(entries: pd.DataFrame, caps: pd.Series, n: int) -> pd.DataFrame:
    """On rows where more than N entries are True, keep only top N by caps."""
    if n >= entries.shape[1]:
        return entries
    out = entries.copy()
    counts = entries.sum(axis=1)
    busy_days = counts[counts > n].index
    for day in busy_days:
        row = entries.loc[day]
        candidates = row[row].index.tolist()
        ranked = sorted(candidates,
                        key=lambda s: -(float(caps.get(s)) if pd.notna(caps.get(s)) else -np.inf))
        drop = set(candidates) - set(ranked[:n])
        if drop:
            out.loc[day, list(drop)] = False
    return out


# --- Run -------------------------------------------------------------------

if st.sidebar.button("Run portfolio backtest", type="primary"):
    pool_symbols = pool["symbol"].tolist()
    cap_series = pool.set_index("symbol")["market_cap"]

    # 1) Load prices into aligned wide DataFrames
    closes: dict[str, pd.Series] = {}
    highs: dict[str, pd.Series] = {}
    lows: dict[str, pd.Series] = {}
    load_prog = st.progress(0.0, text="Loading prices...")
    for i, sym in enumerate(pool_symbols):
        load_prog.progress((i + 1) / len(pool_symbols),
                           text=f"[{i + 1}/{len(pool_symbols)}] loading {sym}")
        try:
            df = load_prices(sym, start=start, end=end)
            if df.empty or len(df) < 60:
                continue
            closes[sym] = df["adj_close"]
            highs[sym] = df["high"]
            lows[sym] = df["low"]
        except Exception:  # noqa: BLE001
            continue
    load_prog.empty()

    if not closes:
        st.error("No price data loaded for the pool. Check the date window.")
        st.stop()

    close_df = pd.DataFrame(closes).sort_index()
    high_df = pd.DataFrame(highs).reindex_like(close_df)
    low_df = pd.DataFrame(lows).reindex_like(close_df)

    # 2) Compute strategy signals per column
    sig_prog = st.progress(0.0, text="Computing signals...")
    entries_df = pd.DataFrame(False, index=close_df.index, columns=close_df.columns)
    exits_df = pd.DataFrame(False, index=close_df.index, columns=close_df.columns)
    cols = list(close_df.columns)
    for i, sym in enumerate(cols):
        sig_prog.progress((i + 1) / len(cols), text=f"[{i + 1}/{len(cols)}] {sym}")
        close_s = close_df[sym].dropna()
        if len(close_s) < 30:
            continue
        try:
            if spec.inputs == "ohlc":
                sig = spec.fn(high_df[sym].reindex_like(close_s),
                              low_df[sym].reindex_like(close_s),
                              close_s, **params)
            else:
                sig = spec.fn(close_s, **params)
            entries_df.loc[sig.entries.index, sym] = sig.entries.values
            exits_df.loc[sig.exits.index, sym] = sig.exits.values
        except Exception:  # noqa: BLE001
            continue
    sig_prog.empty()

    # 3) Apply per-bar filters to entries (never to exits — we always want to be
    # able to leave a position no matter what).
    if min_ytd > -100:
        ytd_df = _per_bar_ytd(close_df)
        entries_df = entries_df & (ytd_df >= min_ytd)
    if min_m6 > -100:
        m6_df = _per_bar_rolling_pct(close_df, 126)
        entries_df = entries_df & (m6_df >= min_m6)
    if min_m3 > -100:
        m3_df = _per_bar_rolling_pct(close_df, 63)
        entries_df = entries_df & (m3_df >= min_m3)
    entries_df = entries_df.fillna(False).astype(bool)

    # 4) Cap-weighted top-N selection per bar
    entries_df = _enforce_top_n(entries_df, cap_series, top_n)

    # 5) Time-based exits (force exit N bars after each entry)
    if use_time and max_hold > 0:
        forced = entries_df.shift(max_hold, fill_value=False)
        exits_df = (exits_df.astype(bool) | forced.astype(bool))

    # 6) vectorbt portfolio with shared cash
    stop_kwargs: dict = {}
    if use_sl:
        stop_kwargs["sl_stop"] = sl_pct / 100
        stop_kwargs["sl_trail"] = sl_trail
    if use_tp:
        stop_kwargs["tp_stop"] = tp_pct / 100

    with st.spinner("Simulating portfolio..."):
        pf = vbt.Portfolio.from_signals(
            close=close_df,
            entries=entries_df,
            exits=exits_df,
            size=1 / top_n,
            size_type="percent",
            cash_sharing=True,
            group_by=True,
            init_cash=float(initial_cash),
            fees=fees_bps / 10_000,
            freq="1D",
            **stop_kwargs,
        )

    value = pf.value()
    trades = pf.trades.records_readable
    total_return = (value.iloc[-1] / float(initial_cash) - 1) * 100
    years = max((value.index[-1] - value.index[0]).days / 365.25, 1e-9)
    cagr = ((1 + total_return / 100) ** (1 / years) - 1) * 100
    bh = close_df.mean(axis=1)  # equal-weight buy-hold benchmark
    bh = bh / bh.iloc[0] * float(initial_cash)

    # --- Headline metrics -------------------------------------------------
    st.subheader("Results")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Total return", f"{total_return:+.2f}%")
    c2.metric("CAGR", f"{cagr:+.2f}%")
    try:
        sharpe = float(pf.sharpe_ratio())
    except Exception:
        sharpe = float("nan")
    c3.metric("Sharpe", f"{sharpe:.2f}")
    c4.metric("Closed trades", f"{len(trades)}")
    st.caption(
        f"Portfolio vs equal-weight buy & hold of the {len(close_df.columns)}-ticker pool. "
        f"Window: {value.index[0].date()} → {value.index[-1].date()}. "
        f"Entries fired: {int(entries_df.sum().sum())}."
    )

    # --- Equity curve -----------------------------------------------------
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=bh.index, y=bh, name="Buy & hold (equal-weight pool)",
        line=dict(color=COLORS["muted"], width=1.3, dash="dot"),
    ))
    fig.add_trace(go.Scatter(
        x=value.index, y=value, name="Portfolio",
        line=dict(color=COLORS["primary"], width=2.2),
        fill="tozeroy", fillcolor="rgba(94, 179, 255, 0.08)",
    ))
    fig.update_layout(
        template=plotly_template(),
        height=420, hovermode="x unified",
        yaxis=dict(tickprefix="$", tickformat=",.0f"),
    )
    st.plotly_chart(fig, use_container_width=True)

    # --- Trade log --------------------------------------------------------
    with st.expander(f"Trade log ({len(trades)} trades)"):
        if trades.empty:
            st.info("No trades were placed in this window.")
        else:
            st.dataframe(trades, use_container_width=True, hide_index=True)
            st.download_button(
                "Download trades CSV",
                data=trades.to_csv(index=False),
                file_name=f"portfolio_{strategy_key}_trades.csv",
                mime="text/csv",
            )

    # --- Per-ticker contribution -----------------------------------------
    if not trades.empty and "Column" in trades.columns:
        contrib = trades.groupby("Column")["PnL"].sum().sort_values(ascending=False)
        with st.expander(f"Per-ticker contribution ({len(contrib)} tickers traded)"):
            contrib_df = contrib.reset_index()
            contrib_df.columns = ["symbol", "net_pnl"]
            contrib_df["market_cap"] = contrib_df["symbol"].map(cap_series)
            st.dataframe(
                contrib_df,
                use_container_width=True,
                hide_index=True,
                column_config={
                    "symbol": "Symbol",
                    "net_pnl": st.column_config.NumberColumn("Net P&L", format="$%.2f"),
                    "market_cap": st.column_config.NumberColumn("Market cap",
                                                                format="compact"),
                },
            )
else:
    st.info(
        "Configure universe, strategy, allocation, and risk management in the "
        "sidebar, then press **Run portfolio backtest**. For the Connors setup "
        "mentioned in Greek: Index = SP500, Strategy = RSI + %R Double Oversold, "
        "Top N = 2, Min YTD = 0, Min 6M = 0, SL 5% / TP 10% / Hold 10d.",
        icon=":material/lightbulb:",
    )
