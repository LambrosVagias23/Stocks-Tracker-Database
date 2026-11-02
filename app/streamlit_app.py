"""Entry point for the Streamlit app.

Streamlit auto-discovers the files under ``pages/`` and builds a sidebar
navigation from them. This file is the landing page.
"""

from __future__ import annotations

import streamlit as st

from _data import load_ingest_state, load_tickers
from _theme import COLORS

st.set_page_config(
    page_title="Stocks Tracker",
    page_icon=":material/show_chart:",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Load Material Symbols font so <span class="material-symbols-outlined"> renders.
st.markdown(
    """
    <link rel="stylesheet"
          href="https://fonts.googleapis.com/css2?family=Material+Symbols+Outlined:opsz,wght,FILL,GRAD@24,400,0,0" />
    <style>
      .material-symbols-outlined {
        font-family: 'Material Symbols Outlined';
        font-weight: normal; font-style: normal;
        font-size: 1.35rem; line-height: 1;
        letter-spacing: normal; text-transform: none; display: inline-block;
        white-space: nowrap; word-wrap: normal; direction: ltr;
        -webkit-font-feature-settings: 'liga'; -webkit-font-smoothing: antialiased;
      }
    </style>
    """,
    unsafe_allow_html=True,
)

# --- Hero -------------------------------------------------------------------

st.markdown(
    f"""
    <div style="padding: 1.2rem 0 0.4rem 0;">
      <div style="color: {COLORS['muted']}; letter-spacing: 0.12em;
                  text-transform: uppercase; font-size: 0.78rem;
                  font-weight: 600;">
        Equities · US · Daily OHLCV
      </div>
      <h1 style="margin: 0.2rem 0 0 0; font-size: 2.2rem; letter-spacing: -0.02em;">
        Stocks Tracker
      </h1>
      <p style="color: {COLORS['muted']}; margin: 0.35rem 0 0 0; max-width: 46rem;">
        Daily history for S&amp;P&nbsp;500, NASDAQ&nbsp;100, and Russell&nbsp;2000.
        Chart it, overlay indicators, and backtest strategies against the full universe.
      </p>
    </div>
    """,
    unsafe_allow_html=True,
)

st.write("")  # breathing room

# --- Snapshot metrics -------------------------------------------------------

tickers = load_tickers()
state = load_ingest_state()

c1, c2, c3 = st.columns(3, gap="medium")
with c1:
    with st.container(border=True):
        st.markdown(f"<span style='color:{COLORS['muted']}'>Universe</span>",
                    unsafe_allow_html=True)
        st.markdown(f"<h2 style='margin:0.1rem 0 0 0'>{len(tickers):,}</h2>",
                    unsafe_allow_html=True)
        st.caption("tickers across SP500 · NDX · R2000")
with c2:
    with st.container(border=True):
        st.markdown(f"<span style='color:{COLORS['muted']}'>With prices</span>",
                    unsafe_allow_html=True)
        st.markdown(f"<h2 style='margin:0.1rem 0 0 0'>{len(state):,}</h2>",
                    unsafe_allow_html=True)
        coverage = (len(state) / max(len(tickers), 1)) * 100
        st.caption(f"{coverage:.1f}% backfilled")
with c3:
    with st.container(border=True):
        st.markdown(f"<span style='color:{COLORS['muted']}'>Latest bar</span>",
                    unsafe_allow_html=True)
        latest = state["last_bar"].max() if not state.empty else None
        latest_str = latest.strftime("%b %d, %Y") if latest is not None else "—"
        st.markdown(
            f"<h2 style='margin:0.1rem 0 0 0; white-space:nowrap;'>{latest_str}</h2>",
            unsafe_allow_html=True,
        )
        st.caption("daily update at 22:30 UTC")

st.write("")

# --- Page tiles -------------------------------------------------------------

PAGES = [
    ("Browse",   "Browse", "search",       "Filter and search 2,500 tickers by index, name, or data coverage."),
    ("Chart",    "Chart",  "candlestick_chart", "Candlestick with SMA / EMA / Bollinger overlays and an RSI or MACD lower pane."),
    ("Backtest", "Backtest", "insights",   "Run a strategy on one ticker. Metrics, equity curve, and trade log."),
    ("Screener", "Screener", "filter_list","Run one strategy across a slice of the universe and rank the results."),
    ("Admin",    "Admin",  "settings",     "Refresh universe, run daily updates, or trigger a full backfill (local-only)."),
]

st.subheader("Explore")

cols = st.columns(2, gap="medium")
for i, (page, label, icon, desc) in enumerate(PAGES):
    with cols[i % 2]:
        with st.container(border=True):
            st.markdown(
                f"""
                <div style="display:flex; align-items:center; gap:0.6rem;">
                  <span class="material-symbols-outlined"
                        style="font-family:'Material Symbols Outlined';
                               color:{COLORS['primary']}; font-size:1.4rem;">
                    {icon}
                  </span>
                  <span style="font-weight:600; font-size:1.05rem;">{label}</span>
                </div>
                <p style="color:{COLORS['muted']}; margin:0.4rem 0 0.6rem 0; font-size:0.92rem;">
                  {desc}
                </p>
                """,
                unsafe_allow_html=True,
            )
            st.page_link(f"pages/{i + 1}_{page}.py", label=f"Open {label}",
                         icon=":material/arrow_forward:")

st.caption(
    "Data: yfinance · Database: Supabase Postgres · "
    "Analytics: vectorbt · UI: Streamlit"
)
