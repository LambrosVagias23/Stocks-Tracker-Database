from __future__ import annotations

from datetime import date, timedelta

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

from stocks_tracker.app_data import load_ingest_state, load_prices, load_tickers
from stocks_tracker.app_theme import COLORS, plotly_template, positive_negative
from stocks_tracker.backtest import run_from_prices
from stocks_tracker.indicators import williams_r
from stocks_tracker.strategies import STRATEGIES
from stocks_tracker.strategy_overlays import overlay_for, primary_indicator_series


def _snapshot_metrics(df: pd.DataFrame) -> dict[str, float]:
    """Latest YTD / 6M / 3M return + current Williams %R(14)."""
    last = df.index[-1]
    last_close = float(df["adj_close"].iloc[-1])
    year_start = pd.Timestamp(year=last.year, month=1, day=1)

    def pct(start_ts: pd.Timestamp) -> float:
        sub = df[df.index >= start_ts]
        if len(sub) < 2:
            return float("nan")
        base = float(sub["adj_close"].iloc[0])
        return (last_close / base - 1) * 100 if base else float("nan")

    try:
        wr = float(williams_r(df["high"], df["low"], df["close"], 14).iloc[-1])
    except Exception:
        wr = float("nan")
    return {
        "ytd": pct(year_start),
        "m6": pct(last - pd.Timedelta(days=180)),
        "m3": pct(last - pd.Timedelta(days=90)),
        "wr14": wr,
    }


def _grid(center: float, lo: float, hi: float, step: float, kind: type, n: int = 5) -> list:
    """Return n sample points centered on `center`, clamped to [lo, hi], as ints or floats."""
    half = (n - 1) / 2
    raw = [center + (i - half) * step * 2 for i in range(n)]
    if kind is int:
        pts = sorted({int(round(max(lo, min(hi, v)))) for v in raw})
    else:
        pts = sorted({round(max(lo, min(hi, v)), 4) for v in raw})
    return pts

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

# --- Ticker snapshot: show the chosen ticker's current performance / state
# so the user can see whether it's a trending / oversold / etc. candidate
# before configuring the strategy.
try:
    _snap_df = load_prices(symbol)
    if not _snap_df.empty and len(_snap_df) >= 30:
        snap = _snapshot_metrics(_snap_df)
        cap_val = tickers.loc[tickers["symbol"] == symbol, "market_cap"].iloc[0] \
            if "market_cap" in tickers.columns else None

        def _fmt_pct(v: float) -> str:
            return "—" if pd.isna(v) else f"{v:+.2f}%"

        def _fmt_cap(v) -> str:
            if v is None or pd.isna(v):
                return "—"
            v = float(v)
            if v >= 1e12:
                return f"${v / 1e12:.2f}T"
            if v >= 1e9:
                return f"${v / 1e9:.1f}B"
            if v >= 1e6:
                return f"${v / 1e6:.0f}M"
            return f"${v:,.0f}"

        with st.sidebar.container(border=True):
            st.markdown(
                f"<div style='color:{COLORS['muted']}; font-size:0.7rem; "
                f"letter-spacing:0.12em; text-transform:uppercase; font-weight:600;'>"
                f"{symbol} snapshot</div>",
                unsafe_allow_html=True,
            )
            snap_c1, snap_c2 = st.columns(2)
            snap_c1.metric("YTD", _fmt_pct(snap["ytd"]))
            snap_c2.metric("6M", _fmt_pct(snap["m6"]))
            snap_c3, snap_c4 = st.columns(2)
            snap_c3.metric("3M", _fmt_pct(snap["m3"]))
            snap_c4.metric("%R(14)",
                           "—" if pd.isna(snap["wr14"]) else f"{snap['wr14']:.1f}")
            st.caption(f"Market cap: {_fmt_cap(cap_val)}")
except Exception:
    pass

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

st.sidebar.divider()
st.sidebar.markdown("**Risk management**")
use_sl = st.sidebar.checkbox("Stop loss", value=False,
                              help="Exit if price drops this % below entry")
sl_pct = st.sidebar.slider("Stop loss %", 0.5, 25.0, 5.0, 0.5,
                           disabled=not use_sl) if use_sl else 0.0
sl_trail = st.sidebar.checkbox("Trailing stop", value=False, disabled=not use_sl,
                                help="Stop ratchets upward with new highs")
use_tp = st.sidebar.checkbox("Take profit", value=False,
                              help="Exit if price rises this % above entry")
tp_pct = st.sidebar.slider("Take profit %", 0.5, 50.0, 10.0, 0.5,
                           disabled=not use_tp) if use_tp else 0.0
use_time = st.sidebar.checkbox("Max hold days", value=False,
                                help="Force exit N bars after entry")
max_hold = st.sidebar.slider("Hold days", 1, 60, 10, 1,
                             disabled=not use_time) if use_time else 0

if st.sidebar.button("Run backtest", type="primary", use_container_width=True):
    df = load_prices(symbol, start=start, end=end)
    if df.empty:
        st.error(f"No prices for {symbol} in {start}..{end}")
        st.stop()
    with st.spinner(f"Backtesting {symbol} · {spec.label}..."):
        res = run_from_prices(
            symbol, df, strategy_key, params=params,
            initial_cash=float(initial_cash), fees=fees_bps / 10_000,
            sl_stop=(sl_pct / 100) if use_sl else None,
            tp_stop=(tp_pct / 100) if use_tp else None,
            sl_trail=sl_trail if use_sl else False,
            max_hold_days=max_hold if use_time else None,
        )
    m = res["metrics"]

    # --- Headline metrics ---------------------------------------------------
    stop_bits = []
    if use_sl:
        stop_bits.append(f"SL {sl_pct:g}%{' (trail)' if sl_trail else ''}")
    if use_tp:
        stop_bits.append(f"TP {tp_pct:g}%")
    if use_time:
        stop_bits.append(f"max hold {max_hold}d")
    stop_suffix = f" · {' · '.join(stop_bits)}" if stop_bits else ""
    st.markdown(
        f"<div style='color:{COLORS['muted']}; letter-spacing:0.1em; "
        f"text-transform:uppercase; font-size:0.75rem; font-weight:600; "
        f"margin-top:0.3rem;'>"
        f"{spec.label} · {symbol} · {m['start']} → {m['end']}{stop_suffix}"
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

    # --- Equity curve + indicator panel ------------------------------------
    eq = res["equity_curve"]
    buy_hold = df["adj_close"] / df["adj_close"].iloc[0] * float(initial_cash)
    overlay = overlay_for(strategy_key, params, df)

    fig = make_subplots(
        rows=2, cols=1, shared_xaxes=True, row_heights=[0.65, 0.35],
        vertical_spacing=0.04,
        subplot_titles=("Equity curve", overlay.panel_title or ""),
    )

    fig.add_trace(go.Scatter(
        x=buy_hold.index, y=buy_hold, name="Buy & hold",
        line=dict(width=1.3, color=COLORS["muted"], dash="dot"),
        hovertemplate="%{y:$,.0f}<extra>Buy & hold</extra>",
    ), row=1, col=1)
    fig.add_trace(go.Scatter(
        x=eq.index, y=eq, name="Strategy",
        line=dict(width=2.2, color=COLORS["primary"]),
        fill="tozeroy", fillcolor="rgba(94, 179, 255, 0.08)",
        hovertemplate="%{y:$,.0f}<extra>Strategy</extra>",
    ), row=1, col=1)

    entries = res["entries"][res["entries"]]
    exits = res["exits"][res["exits"]]
    fig.add_trace(go.Scatter(
        x=entries.index, y=eq.reindex(entries.index), mode="markers",
        marker=dict(color=COLORS["positive"], symbol="triangle-up", size=10,
                    line=dict(color=COLORS["bg"], width=1)),
        name="Entry",
        hovertemplate="Entry · %{x|%b %d, %Y}<extra></extra>",
    ), row=1, col=1)
    fig.add_trace(go.Scatter(
        x=exits.index, y=eq.reindex(exits.index), mode="markers",
        marker=dict(color=COLORS["negative"], symbol="triangle-down", size=10,
                    line=dict(color=COLORS["bg"], width=1)),
        name="Exit",
        hovertemplate="Exit · %{x|%b %d, %Y}<extra></extra>",
    ), row=1, col=1)

    # Indicator panel: either dedicated oscillator pane (RSI, %R) or
    # price-chart overlays repeated (SMA cross, Bollinger).
    price_overlays = [ln for ln in overlay.lines if ln.where == "price"]
    panel_lines = [ln for ln in overlay.lines if ln.where == "panel"]
    if price_overlays:
        fig.add_trace(go.Scatter(
            x=df.index, y=df["adj_close"], name="Price",
            line=dict(width=1.4, color=COLORS["text"]),
            hovertemplate="%{y:$,.2f}<extra>Price</extra>",
        ), row=2, col=1)
        for ln in price_overlays:
            fig.add_trace(go.Scatter(
                x=ln.series.index, y=ln.series, name=ln.label,
                line=dict(width=1.3, dash=ln.dash or "solid"),
            ), row=2, col=1)
    for ln in panel_lines:
        fig.add_trace(go.Scatter(
            x=ln.series.index, y=ln.series, name=ln.label,
            line=dict(width=1.6, color=COLORS["primary"], dash=ln.dash or "solid"),
        ), row=2, col=1)
    for y in overlay.hlines:
        fig.add_hline(y=y, line_dash="dash", line_color=COLORS["muted"], row=2, col=1)
    # Entry/exit markers mirrored on the indicator panel to make timing obvious.
    indicator = primary_indicator_series(strategy_key, params, df)
    if indicator is not None:
        fig.add_trace(go.Scatter(
            x=entries.index, y=indicator.reindex(entries.index), mode="markers",
            marker=dict(color=COLORS["positive"], symbol="triangle-up", size=9,
                        line=dict(color=COLORS["bg"], width=1)),
            showlegend=False,
            hovertemplate=f"Entry · %{{x|%b %d, %Y}}<br>{indicator.name}=%{{y:.2f}}<extra></extra>",
        ), row=2, col=1)
        fig.add_trace(go.Scatter(
            x=exits.index, y=indicator.reindex(exits.index), mode="markers",
            marker=dict(color=COLORS["negative"], symbol="triangle-down", size=9,
                        line=dict(color=COLORS["bg"], width=1)),
            showlegend=False,
            hovertemplate=f"Exit · %{{x|%b %d, %Y}}<br>{indicator.name}=%{{y:.2f}}<extra></extra>",
        ), row=2, col=1)

    fig.update_layout(
        template=plotly_template(),
        height=640,
        hovermode="x unified",
        margin=dict(l=10, r=10, t=40, b=10),
    )
    fig.update_yaxes(tickprefix="$", tickformat=",.0f", row=1, col=1)
    st.plotly_chart(fig, use_container_width=True)

    # --- Trade log with indicator-at-entry/exit ----------------------------
    with st.expander("Trade log"):
        pf = res["portfolio"]
        trades = pf.trades.records_readable.copy()
        if indicator is not None and not trades.empty:
            if "Entry Timestamp" in trades.columns:
                trades[f"{indicator.name} @ entry"] = (
                    indicator.reindex(pd.to_datetime(trades["Entry Timestamp"])).to_numpy()
                )
            if "Exit Timestamp" in trades.columns:
                trades[f"{indicator.name} @ exit"] = (
                    indicator.reindex(pd.to_datetime(trades["Exit Timestamp"])).to_numpy()
                )
        st.dataframe(trades, use_container_width=True, hide_index=True)

    # --- Parameter sensitivity heatmap -------------------------------------
    #
    # Vary the first two numeric params across a 5-point grid centred on the
    # user's current selection. 25 backtests on a cached DataFrame; keep the
    # other params fixed to the current values so the grid is interpretable.
    numeric_params = [p for p in spec.params if p.kind in (int, float)]
    if len(numeric_params) >= 2:
        p1, p2 = numeric_params[0], numeric_params[1]
        with st.expander(
            f"Parameter sensitivity · {p1.name} × {p2.name}",
            expanded=False,
        ):
            st.caption(
                f"Re-runs the backtest across a 5×5 grid around your "
                f"current `{p1.name}={params[p1.name]}` and "
                f"`{p2.name}={params[p2.name]}`. Other params stay fixed."
            )
            run_grid = st.button(
                "Run grid (25 backtests)", key="run_sensitivity",
                use_container_width=True,
            )
            if run_grid:
                p1_values = _grid(params[p1.name], p1.min, p1.max, p1.step, p1.kind)
                p2_values = _grid(params[p2.name], p2.min, p2.max, p2.step, p2.kind)
                metric_name = "Sharpe"
                sharpe = np.full((len(p2_values), len(p1_values)), np.nan)
                ret = np.full_like(sharpe, np.nan)
                progress = st.progress(0.0, text="Running grid...")
                total = len(p1_values) * len(p2_values)
                k = 0
                for i, v2 in enumerate(p2_values):
                    for j, v1 in enumerate(p1_values):
                        k += 1
                        progress.progress(k / total, text=f"[{k}/{total}]")
                        trial = dict(params)
                        trial[p1.name] = v1
                        trial[p2.name] = v2
                        try:
                            r = run_from_prices(
                                symbol, df, strategy_key, params=trial,
                                initial_cash=float(initial_cash),
                                fees=fees_bps / 10_000,
                                sl_stop=(sl_pct / 100) if use_sl else None,
                                tp_stop=(tp_pct / 100) if use_tp else None,
                                sl_trail=sl_trail if use_sl else False,
                                max_hold_days=max_hold if use_time else None,
                            )
                            sharpe[i, j] = r["metrics"]["sharpe_ratio"]
                            ret[i, j] = r["metrics"]["total_return_pct"]
                        except Exception:  # noqa: BLE001
                            pass
                progress.empty()

                g1, g2 = st.columns(2)
                for col, data, title, fmt in [
                    (g1, sharpe, f"Sharpe ({metric_name})", ".2f"),
                    (g2, ret, "Total return %", ".1f"),
                ]:
                    hm = go.Figure(go.Heatmap(
                        z=data, x=p1_values, y=p2_values,
                        colorscale="RdBu", zmid=0,
                        text=data, texttemplate="%{text:" + fmt + "}",
                        hovertemplate=(
                            f"{p1.name}=%{{x}}<br>{p2.name}=%{{y}}"
                            f"<br>{title}=%{{z:{fmt}}}<extra></extra>"
                        ),
                        colorbar=dict(thickness=12),
                    ))
                    hm.update_layout(
                        template=plotly_template(),
                        height=360,
                        title=dict(text=title, font=dict(size=14)),
                        xaxis=dict(title=p1.name, type="category"),
                        yaxis=dict(title=p2.name, type="category"),
                        margin=dict(l=10, r=10, t=40, b=10),
                    )
                    col.plotly_chart(hm, use_container_width=True)
else:
    st.info(
        "Pick a ticker, strategy, and parameters in the sidebar, then press "
        "**Run backtest**.",
        icon=":material/arrow_back:",
    )
