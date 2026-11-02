"""Entry point for the Streamlit app.

Streamlit auto-discovers the files under ``pages/`` and builds a sidebar
navigation from them. This file is the landing page.
"""

from __future__ import annotations

import streamlit as st

from _data import load_ingest_state, load_tickers

st.set_page_config(
    page_title="Stocks Tracker",
    page_icon="chart_with_upwards_trend",
    layout="wide",
)

st.title("Stocks Tracker")
st.caption("Daily OHLCV for the S&P 500, NASDAQ 100, and Russell 2000 — "
           "with indicator overlays and simple strategy backtests.")

col1, col2, col3 = st.columns(3)
tickers = load_tickers()
state = load_ingest_state()

with col1:
    st.metric("Tickers in universe", f"{len(tickers):,}")
with col2:
    st.metric("Symbols with prices", f"{len(state):,}")
with col3:
    latest = state["last_bar"].max() if not state.empty else None
    st.metric("Latest bar", latest.strftime("%Y-%m-%d") if latest is not None else "—")

st.divider()

st.markdown(
    """
    ### Pages

    - **Browse** — filter and search the ticker universe.
    - **Chart** — candlestick for one ticker with SMA / EMA / Bollinger / RSI / MACD overlays.
    - **Backtest** — run a strategy on a single ticker, see metrics + equity curve.
    - **Screener** — run one strategy across the universe and rank the results.

    Use the sidebar on the left to navigate.
    """
)
