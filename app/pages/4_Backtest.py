from __future__ import annotations

from datetime import date, timedelta

import plotly.graph_objects as go
import streamlit as st

from stocks_tracker.app_data import load_ingest_state, load_prices, load_tickers
from stocks_tracker.app_theme import COLORS, plotly_template, positive_negative
from stocks_tracker.backtest import run_from_prices
from stocks_tracker.strategies import STRATEGIES

st.set_page_config(page_title="Backtest — Stocks Tracker",
                   page_icon=":material/insights:", layout="wide")
st.title("Backtest")
st.caption("Run a strategy on one ticker and compare it to buy & hold.")

tickers = load_tickers()
state = load_ingest_state()
if tickers.empty:
    st.error("Universe is empty.")
    st.stop()

with_prices = sorted(set(state[state["last_bar"].notna()]["symbol"])) if not state.empty else []
if not with_prices:
    st.warning("No tickers have price history yet. Run `python -m stocks_tracker.backfill` first.")
    st.stop()

st.sidebar.header("Backtest setup")
symbol = st.sidebar.selectbox(
    "Ticker", with_prices,
    index=with_prices.index("AAPL") if "AAPL" in with_prices else 0,
)

strategy_keys = list(STRATEGIES.keys())
strategy_labels = {k: STRATEGIES[k].label for k in strategy_keys}
strategy_key = st.sidebar.selectbox(
    "Strategy", strategy_keys,
    format_func=lambda k: strategy_labels[k],
)

spec = STRATEGIES[strategy_key]
st.sidebar.caption(spec.description)

params: dict[str, object] = {}
for p in spec.params:
    if p.kind is int:
        params[p.name] = st.sidebar.slider(
            p.name, int(p.min), int(p.max), int(p.default), int(p.step),
        )
    else:
        params[p.name] = st.sidebar.slider(
            p.name, float(p.min), float(p.max), float(p.default), float(p.step),
        )

today = date.today()
start = st.sidebar.date_input("Start", today - timedelta(days=365 * 3))
end = st.sidebar.date_input("End", today)

st.sidebar.divider()
initial_cash = st.sidebar.number_input("Initial cash ($)", value=10_000,
                                        step=1_000, min_value=100)
fees_bps = st.sidebar.number_input("Fees (bps per trade)", value=5.0,
                                    step=1.0, min_value=0.0)

if st.sidebar.button("Run backtest", type="primary", use_container_width=True):
    df = load_prices(symbol, start=start, end=end)
    if df.empty:
        st.error(f"No prices for {symbol} in {start}..{end}")
        st.stop()
    with st.spinner(f"Backtesting {symbol} · {spec.label}..."):
        res = run_from_prices(
            symbol, df, strategy_key, params=params,
            initial_cash=float(initial_cash), fees=fees_bps / 10_000,
        )
    m = res["metrics"]

    # --- Headline metrics ---------------------------------------------------
    st.markdown(
        f"<div style='color:{COLORS['muted']}; letter-spacing:0.1em; "
        f"text-transform:uppercase; font-size:0.75rem; font-weight:600; "
        f"margin-top:0.3rem;'>"
        f"{spec.label} · {symbol} · {m['start']} → {m['end']}"
        f"</div>",
        unsafe_allow_html=True,
    )

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Total return", f"{m['total_return_pct']:.2f}%",
              delta=f"{m['total_return_pct']:.2f}%",
              delta_color=positive_negative(m["total_return_pct"]))
    c2.metric("Annualized", f"{m['annualized_return_pct']:.2f}%",
              delta=f"{m['annualized_return_pct']:.2f}%",
              delta_color=positive_negative(m["annualized_return_pct"]))
    c3.metric("Sharpe", f"{m['sharpe_ratio']:.2f}")
    c4.metric("Max drawdown", f"{m['max_drawdown_pct']:.2f}%",
              delta=f"{-abs(m['max_drawdown_pct']):.2f}%",
              delta_color="inverse")

    c5, c6, c7, c8 = st.columns(4)
    c5.metric("Sortino", f"{m['sortino_ratio']:.2f}")
    c6.metric("Calmar",  f"{m['calmar_ratio']:.2f}")
    c7.metric("Win rate", f"{m['win_rate_pct']:.1f}%")
    c8.metric("Trades",  f"{m['num_trades']}")

    st.write("")

    # --- Equity curve -------------------------------------------------------
    eq = res["equity_curve"]
    buy_hold = df["adj_close"] / df["adj_close"].iloc[0] * float(initial_cash)
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=buy_hold.index, y=buy_hold, name="Buy & hold",
        line=dict(width=1.3, color=COLORS["muted"], dash="dot"),
        hovertemplate="%{y:$,.0f}<extra>Buy & hold</extra>",
    ))
    fig.add_trace(go.Scatter(
        x=eq.index, y=eq, name="Strategy",
        line=dict(width=2.2, color=COLORS["primary"]),
        fill="tozeroy", fillcolor="rgba(94, 179, 255, 0.08)",
        hovertemplate="%{y:$,.0f}<extra>Strategy</extra>",
    ))
    entries = res["entries"][res["entries"]]
    exits = res["exits"][res["exits"]]
    fig.add_trace(go.Scatter(
        x=entries.index, y=eq.reindex(entries.index), mode="markers",
        marker=dict(color=COLORS["positive"], symbol="triangle-up", size=10,
                    line=dict(color=COLORS["bg"], width=1)),
        name="Entry",
        hovertemplate="Entry · %{x|%b %d, %Y}<extra></extra>",
    ))
    fig.add_trace(go.Scatter(
        x=exits.index, y=eq.reindex(exits.index), mode="markers",
        marker=dict(color=COLORS["negative"], symbol="triangle-down", size=10,
                    line=dict(color=COLORS["bg"], width=1)),
        name="Exit",
        hovertemplate="Exit · %{x|%b %d, %Y}<extra></extra>",
    ))
    fig.update_layout(
        template=plotly_template(),
        height=460,
        hovermode="x unified",
        yaxis=dict(tickprefix="$", tickformat=",.0f"),
    )
    st.plotly_chart(fig, use_container_width=True)

    # --- Trade log ----------------------------------------------------------
    with st.expander("Trade log"):
        pf = res["portfolio"]
        st.dataframe(pf.trades.records_readable, use_container_width=True, hide_index=True)
else:
    st.info(
        "Pick a ticker, strategy, and parameters in the sidebar, then press "
        "**Run backtest**.",
        icon=":material/arrow_back:",
    )
