"""Plain-English definitions of every indicator, strategy, and metric used
elsewhere in the app. Grouped so a non-technical user can skim one section
without being drowned by the rest.
"""

from __future__ import annotations

import streamlit as st

from stocks_tracker.app_theme import COLORS

st.set_page_config(
    page_title="Glossary — Stocks Tracker",
    page_icon=":material/menu_book:",
    layout="wide",
)

# --- Hero -------------------------------------------------------------------

st.markdown(
    f"""
    <div style="padding: 0.6rem 0 0.2rem 0;">
      <div style="color:{COLORS['muted']}; letter-spacing:0.12em;
                  text-transform:uppercase; font-size:0.78rem; font-weight:600;">
        Reference
      </div>
      <h1 style="margin:0.2rem 0 0 0; font-size:2.1rem; letter-spacing:-0.02em;">
        Glossary
      </h1>
      <p style="color:{COLORS['muted']}; margin:0.35rem 0 0 0; max-width:46rem;">
        What the indicators, strategies, and metrics across this app actually
        measure — in plain English, with the formula where it's short.
      </p>
    </div>
    """,
    unsafe_allow_html=True,
)
st.write("")


def term(name: str, body: str, formula: str | None = None) -> None:
    """Render one glossary entry: bold term, body, optional monospace formula."""
    st.markdown(f"**{name}** — {body}")
    if formula:
        st.markdown(
            f"<div style='color:{COLORS['muted']}; font-family:monospace; "
            f"font-size:0.88rem; margin:0.1rem 0 0.4rem 0;'>{formula}</div>",
            unsafe_allow_html=True,
        )
    else:
        st.write("")


# --- Price overlays ---------------------------------------------------------

st.subheader("Price overlays")
st.caption("Indicators drawn directly on top of the price chart to smooth or frame it.")

term(
    "SMA — Simple Moving Average",
    "The average closing price over the last N bars. Smooths out day-to-day "
    "noise so you can see the underlying trend. Longer windows (50, 200) react "
    "slowly; shorter ones (10, 20) hug recent price.",
    "SMA(N) = (close₁ + close₂ + … + closeₙ) / N",
)
term(
    "EMA — Exponential Moving Average",
    "Like SMA but weights recent bars more heavily. Reacts faster to new price "
    "moves. A common choice for crossover strategies that want earlier signals.",
    "EMAₜ = α · closeₜ + (1 − α) · EMAₜ₋₁,   α = 2 / (N + 1)",
)
term(
    "Bollinger Bands (BB)",
    "A middle line (usually SMA 20) with two outer bands plotted at ±K standard "
    "deviations of price. Bands widen in volatile periods and squeeze in calm "
    "ones. Price touching the upper band is relatively high; touching the lower "
    "is relatively low — but neither is automatically a buy or sell signal.",
    "upper = SMA(N) + K·σ,   lower = SMA(N) − K·σ   (default N=20, K=2)",
)

st.divider()

# --- Oscillators ------------------------------------------------------------

st.subheader("Oscillators")
st.caption("Momentum indicators that live in their own panel below the price chart. "
           "Bounded ranges give natural overbought / oversold reference lines.")

term(
    "RSI — Relative Strength Index",
    "Momentum oscillator bounded between 0 and 100. Compares average up-moves "
    "to average down-moves over N bars. Above 70 = overbought (crowded buyers), "
    "below 30 = oversold (crowded sellers). RSI divergence from price is a "
    "classic early-reversal signal.",
    "RSI = 100 − 100 / (1 + avg_gain / avg_loss)   (default N=14)",
)
term(
    "MACD — Moving Average Convergence Divergence",
    "Difference between a fast EMA and a slow EMA, plus a signal line (EMA of "
    "that difference) and a histogram (difference minus signal). MACD crossing "
    "above its signal line is bullish; below is bearish. The histogram shows "
    "momentum strength.",
    "MACD = EMA(12) − EMA(26),   signal = EMA(9) of MACD,   hist = MACD − signal",
)
term(
    "Williams %R",
    "Momentum oscillator bounded between −100 and 0. 0 means price closed at "
    "the period's high; −100 means it closed at the low. Below −80 = oversold, "
    "above −20 = overbought. Behaves like an inverted, faster RSI.",
    "%R = −100 · (highest_high − close) / (highest_high − lowest_low)   (over N bars, default 14)",
)

st.divider()

# --- Strategies -------------------------------------------------------------

st.subheader("Strategies")
st.caption("Rules that turn indicator values into buy / sell signals. "
           "Every strategy here is long-only (buys to open, sells to close).")

term(
    "SMA Crossover",
    "Buy when a fast SMA crosses above a slow SMA (\"golden cross\"); sell when "
    "the fast crosses back below (\"death cross\"). Simple trend-following logic "
    "that works in sustained up/down trends but gives frequent false signals "
    "in sideways markets.",
)
term(
    "RSI Mean Reversion",
    "Buy when RSI drops below the oversold line (default 30), expecting the "
    "stock to snap back. Sell when RSI rises above the overbought line "
    "(default 70). Works best on range-bound stocks; dangerous in strong "
    "trends because \"oversold\" can keep getting more oversold.",
)
term(
    "Bollinger Breakout",
    "Buy when price closes above the upper Bollinger band — a breakout move. "
    "Exit when price falls back below the middle band. Trend-following in "
    "spirit: assumes a breakout has follow-through.",
)
term(
    "Williams %R Mean Reversion",
    "Buy when %R crosses below the oversold line (default −80); exit when it "
    "crosses above the overbought line (default −20). Same mean-reversion idea "
    "as RSI but reacts faster.",
)

st.divider()

# --- Backtest metrics -------------------------------------------------------

st.subheader("Backtest metrics")
st.caption("How the Backtest and Screener pages score a strategy's historical run.")

term(
    "Total return %",
    "Final portfolio value minus starting value, as a percent of starting "
    "value. Ignores how long it took.",
)
term(
    "Annualized return (CAGR)",
    "Total return re-expressed as the equivalent constant yearly growth rate. "
    "Makes a 3-year run comparable to a 10-year one.",
    "CAGR = (end / start)^(1 / years) − 1",
)
term(
    "Sharpe ratio",
    "Average excess return divided by its standard deviation. Measures return "
    "per unit of total volatility. Rule of thumb: >1 is decent, >2 is great, "
    "<0 means you did worse than cash.",
    "Sharpe = (R̄ − R_f) / σ_R",
)
term(
    "Sortino ratio",
    "Like Sharpe but only penalises downside volatility — upside swings don't "
    "hurt the score. Usually higher than Sharpe. Preferred when returns are "
    "skewed (most trend-following strategies).",
    "Sortino = (R̄ − R_f) / σ_downside",
)
term(
    "Calmar ratio",
    "Annualized return divided by the maximum drawdown. Rewards strategies "
    "that compound steadily without a scary dip. Dollar-for-dollar one of the "
    "harshest risk-adjusted metrics.",
    "Calmar = CAGR / |max drawdown|",
)
term(
    "Max drawdown %",
    "Biggest peak-to-trough decline during the test, as a percent. A −30% "
    "drawdown means the account was ever 30% below its prior high. The "
    "psychological cost of running the strategy.",
)
term(
    "Win rate %",
    "Share of trades that closed profitably. On its own doesn't tell you much "
    "— a 40% win rate can still be very profitable if winners are big.",
)
term(
    "Number of trades",
    "How many round-trip (buy → sell) trades the strategy fired in the "
    "window. Very few trades = small sample, metrics may be noise. Hundreds "
    "of tiny trades = fees matter.",
)
term(
    "Exposure %",
    "Fraction of the backtest window the strategy was actually invested "
    "(holding the stock). 100% means always in; 20% means sitting in cash "
    "most of the time.",
)

st.divider()

# --- Performance columns ----------------------------------------------------

st.subheader("Buy-and-hold performance columns")
st.caption("Stock-level returns shown next to strategy results in the Screener, "
           "so you can see whether the strategy outperformed just owning the stock.")

term(
    "YTD %",
    "Price return from the first trading day of the current calendar year to "
    "the latest close. Buy-and-hold, dividends not reinvested beyond what "
    "adj_close already reflects.",
)
term(
    "6M %",
    "Price return from ~180 calendar days ago to the latest close.",
)
term(
    "3M %",
    "Price return from ~90 calendar days ago to the latest close.",
)

st.divider()

# --- Market cap -------------------------------------------------------------

st.subheader("Market cap")

term(
    "Market capitalisation",
    "Share price × shares outstanding — the total dollar value of the company "
    "if you bought every share at today's price. Rough buckets: large-cap "
    "> $10B, mid-cap $2–10B, small-cap $0.3–2B. In the Screener it's shown "
    "with compact units (e.g. 3.0T, 820M). Values refresh weekly.",
)

st.caption(
    "Need something that's not here? Open an issue on the repo and it goes "
    "straight into the glossary."
)
