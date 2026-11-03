from __future__ import annotations

from datetime import date, timedelta

import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

from stocks_tracker.app_data import load_ingest_state, load_prices, load_tickers
from stocks_tracker.app_theme import COLORS, plotly_template
from stocks_tracker.indicators import bbands, ema, macd, rsi, sma

st.set_page_config(page_title="Chart — Stocks Tracker", page_icon=":material/candlestick_chart:",
                   layout="wide")
st.title("Chart")
st.caption("Candlestick with indicator overlays and a configurable lower pane.")

tickers = load_tickers()
state = load_ingest_state()
if tickers.empty:
    st.error("Universe is empty. Run `python -m stocks_tracker.universe` first.")
    st.stop()

with_prices = set(state[state["last_bar"].notna()]["symbol"]) if not state.empty else set()
options = sorted(with_prices or set(tickers["symbol"]))

st.sidebar.header("Chart options")
default_idx = options.index("AAPL") if "AAPL" in options else 0
symbol = st.sidebar.selectbox("Ticker", options, index=default_idx)

today = date.today()
start = st.sidebar.date_input("Start", today - timedelta(days=365))
end = st.sidebar.date_input("End", today)

overlays = st.sidebar.multiselect(
    "Overlays",
    ["SMA(20)", "SMA(50)", "EMA(20)", "Bollinger(20, 2)"],
    default=["SMA(50)"],
)
lower_panel = st.sidebar.radio("Lower panel", ["Volume", "RSI(14)", "MACD"], index=0)

df = load_prices(symbol, start=start, end=end)
if df.empty:
    st.warning(f"No price data for {symbol} in this window. Have you backfilled it?")
    st.stop()

fig = make_subplots(
    rows=2, cols=1, shared_xaxes=True, row_heights=[0.72, 0.28],
    vertical_spacing=0.03,
)

fig.add_trace(
    go.Candlestick(
        x=df.index, open=df["open"], high=df["high"], low=df["low"], close=df["close"],
        name=symbol, showlegend=False,
        increasing=dict(line=dict(color=COLORS["candle_up"]), fillcolor=COLORS["candle_up"]),
        decreasing=dict(line=dict(color=COLORS["candle_down"]), fillcolor=COLORS["candle_down"]),
    ),
    row=1, col=1,
)

close = df["adj_close"]
if "SMA(20)" in overlays:
    s = sma(close, 20)
    fig.add_trace(go.Scatter(x=df.index, y=s, name="SMA 20",
                             line=dict(width=1.4)), row=1, col=1)
if "SMA(50)" in overlays:
    s = sma(close, 50)
    fig.add_trace(go.Scatter(x=df.index, y=s, name="SMA 50",
                             line=dict(width=1.4)), row=1, col=1)
if "EMA(20)" in overlays:
    e = ema(close, 20)
    fig.add_trace(go.Scatter(x=df.index, y=e, name="EMA 20",
                             line=dict(width=1.4, dash="dot")), row=1, col=1)
if "Bollinger(20, 2)" in overlays:
    bb = bbands(close, 20, 2.0)
    fig.add_trace(go.Scatter(x=df.index, y=bb.upper, name="BB upper",
                             line=dict(width=1, color=COLORS["muted"])), row=1, col=1)
    fig.add_trace(go.Scatter(x=df.index, y=bb.lower, name="BB lower",
                             line=dict(width=1, color=COLORS["muted"]),
                             fill="tonexty", fillcolor="rgba(138,148,166,0.08)"), row=1, col=1)

if lower_panel == "Volume":
    volume_colors = [
        COLORS["candle_up"] if c >= o else COLORS["candle_down"]
        for o, c in zip(df["open"], df["close"], strict=False)
    ]
    fig.add_trace(go.Bar(x=df.index, y=df["volume"], name="Volume",
                         showlegend=False, marker=dict(color=volume_colors, opacity=0.6)),
                  row=2, col=1)
elif lower_panel == "RSI(14)":
    r = rsi(close, 14)
    fig.add_trace(go.Scatter(x=df.index, y=r, name="RSI(14)", showlegend=False,
                             line=dict(color=COLORS["primary"], width=1.4)),
                  row=2, col=1)
    fig.add_hline(y=70, line_dash="dash", line_color=COLORS["muted"], row=2, col=1)
    fig.add_hline(y=30, line_dash="dash", line_color=COLORS["muted"], row=2, col=1)
else:  # MACD
    m = macd(close)
    fig.add_trace(go.Scatter(x=df.index, y=m.macd, name="MACD", showlegend=False,
                             line=dict(color=COLORS["primary"], width=1.4)), row=2, col=1)
    fig.add_trace(go.Scatter(x=df.index, y=m.signal, name="Signal", showlegend=False,
                             line=dict(color=COLORS["accent"], width=1.2)), row=2, col=1)
    hist_colors = [COLORS["candle_up"] if v >= 0 else COLORS["candle_down"] for v in m.hist]
    fig.add_trace(go.Bar(x=df.index, y=m.hist, name="Hist", showlegend=False,
                         marker=dict(color=hist_colors, opacity=0.55)), row=2, col=1)

fig.update_layout(
    template=plotly_template(),
    height=720,
    xaxis_rangeslider_visible=False,
    hovermode="x unified",
    margin=dict(l=10, r=10, t=24, b=10),
)
fig.update_xaxes(showgrid=False)
st.plotly_chart(fig, use_container_width=True)

with st.expander("Recent bars"):
    st.dataframe(df.tail(10), use_container_width=True)
