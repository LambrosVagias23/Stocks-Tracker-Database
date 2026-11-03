from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from stocks_tracker.app_data import load_ingest_state, load_prices, load_tickers
from stocks_tracker.app_theme import COLORS, plotly_template, positive_negative

st.set_page_config(page_title="Company — Stocks Tracker",
                   page_icon=":material/apartment:", layout="wide")

tickers = load_tickers()
state = load_ingest_state()
if tickers.empty:
    st.error("Universe is empty. Run `python -m stocks_tracker.universe` first.")
    st.stop()

merged = tickers.merge(state[["symbol", "last_bar"]], on="symbol", how="left")
merged["name"] = merged["name"].fillna("")

# --- Sidebar: search + pick ------------------------------------------------

st.sidebar.header("Search")
query = st.sidebar.text_input(
    "Symbol or company name", "",
    placeholder="e.g. AAPL, Microsoft, GME",
).strip().lower()

pool = merged
if query:
    pool = merged[
        merged["symbol"].str.lower().str.contains(query, na=False)
        | merged["name"].str.lower().str.contains(query, na=False)
    ]

st.sidebar.caption(f"{len(pool):,} match")

if pool.empty:
    st.sidebar.error("No tickers match that search.")
    st.stop()

name_by_symbol = dict(zip(pool["symbol"], pool["name"], strict=False))
options = pool["symbol"].tolist()
default_idx = options.index("AAPL") if "AAPL" in options else 0

symbol = st.sidebar.selectbox(
    "Ticker",
    options,
    index=default_idx,
    format_func=lambda s: f"{s} — {name_by_symbol.get(s, '')[:40]}" if name_by_symbol.get(s) else s,
)

row = merged.loc[merged["symbol"] == symbol].iloc[0]
indexes: list[str] = list(row.get("index_membership") or [])

# --- Hero header -----------------------------------------------------------

pills_html = "".join(
    f"<span style='display:inline-block; padding:0.15rem 0.6rem; margin-right:0.4rem; "
    f"border-radius:999px; background:{COLORS['surface_alt']}; color:{COLORS['primary']}; "
    f"font-size:0.78rem; font-weight:600; letter-spacing:0.04em;'>{idx}</span>"
    for idx in indexes
)
status_dot = COLORS["positive"] if row.get("active", True) else COLORS["negative"]

st.markdown(
    f"""
    <div style="padding:0.6rem 0 0.2rem 0;">
      <div style="color:{COLORS['muted']}; font-size:0.75rem;
                  letter-spacing:0.14em; text-transform:uppercase; font-weight:600;">
        {' · '.join(indexes) if indexes else 'US Equity'}
      </div>
      <div style="display:flex; align-items:baseline; gap:0.8rem; margin-top:0.2rem;">
        <h1 style="margin:0; font-size:2.1rem; letter-spacing:-0.02em;">{symbol}</h1>
        <span style="color:{COLORS['muted']}; font-size:1.1rem;">
          {row['name'] or '&nbsp;'}
        </span>
      </div>
      <div style="margin-top:0.6rem;">
        {pills_html}
        <span style="display:inline-block; width:0.5rem; height:0.5rem;
                     border-radius:999px; background:{status_dot}; margin-left:0.4rem;
                     margin-bottom:0.1rem; vertical-align:middle;"></span>
        <span style="color:{COLORS['muted']}; font-size:0.85rem;
                     margin-left:0.3rem; vertical-align:middle;">
          {'active' if row.get('active', True) else 'inactive'}
        </span>
      </div>
    </div>
    """,
    unsafe_allow_html=True,
)

st.write("")

# --- Price data load -------------------------------------------------------

df = load_prices(symbol)
if df.empty:
    st.warning(
        f"No price history for **{symbol}** yet. Trigger a backfill from the "
        f"**Admin** page (or run `python -m stocks_tracker.backfill "
        f"--tickers {symbol}` locally)."
    )
    st.stop()

df = df.sort_index()
last_bar = df.iloc[-1]
prev_bar = df.iloc[-2] if len(df) >= 2 else last_bar

day_change = float(last_bar["close"] - prev_bar["close"])
day_change_pct = (day_change / float(prev_bar["close"]) * 100) if prev_bar["close"] else 0.0

one_year_ago = df.index[-1] - pd.Timedelta(days=365)
w52 = df[df.index >= one_year_ago]
w52_high = float(w52["high"].max()) if not w52.empty else float("nan")
w52_low = float(w52["low"].min()) if not w52.empty else float("nan")

year_start = pd.Timestamp(year=df.index[-1].year, month=1, day=1)
ytd = df[df.index >= year_start]
if len(ytd) >= 2:
    ytd_pct = (float(ytd.iloc[-1]["adj_close"]) /
               float(ytd.iloc[0]["adj_close"]) - 1) * 100
else:
    ytd_pct = 0.0

# --- Headline metrics ------------------------------------------------------

c1, c2, c3, c4 = st.columns(4)
c1.metric("Last close", f"${float(last_bar['close']):,.2f}",
          delta=f"{day_change:+.2f} ({day_change_pct:+.2f}%)",
          delta_color=positive_negative(day_change_pct))
c2.metric("52-week high", f"${w52_high:,.2f}")
c3.metric("52-week low",  f"${w52_low:,.2f}")
c4.metric("Year-to-date", f"{ytd_pct:+.2f}%",
          delta=f"{ytd_pct:+.2f}%",
          delta_color=positive_negative(ytd_pct))

st.write("")

# --- Price chart (last 1 year, line + fill) --------------------------------

one_year = df[df.index >= one_year_ago]
fig = go.Figure()
fig.add_trace(go.Scatter(
    x=one_year.index, y=one_year["adj_close"],
    name="Adj close",
    line=dict(color=COLORS["primary"], width=2),
    fill="tozeroy", fillcolor="rgba(94, 179, 255, 0.08)",
    hovertemplate="%{x|%b %d, %Y}<br>%{y:$,.2f}<extra></extra>",
))
# 52w high/low markers
if not pd.isna(w52_high):
    fig.add_hline(y=w52_high, line_dash="dot", line_color=COLORS["muted"],
                  annotation_text="52w high", annotation_position="top right",
                  annotation_font_color=COLORS["muted"])
if not pd.isna(w52_low):
    fig.add_hline(y=w52_low, line_dash="dot", line_color=COLORS["muted"],
                  annotation_text="52w low", annotation_position="bottom right",
                  annotation_font_color=COLORS["muted"])
fig.update_layout(
    template=plotly_template(),
    height=380,
    hovermode="x unified",
    yaxis=dict(tickprefix="$", tickformat=",.2f"),
    margin=dict(l=10, r=10, t=24, b=10),
    showlegend=False,
)
st.plotly_chart(fig, use_container_width=True)

# --- Data stats ------------------------------------------------------------

st.subheader("Data in the database")
s1, s2, s3, s4 = st.columns(4)
s1.metric("Bars stored", f"{len(df):,}")
s2.metric("First bar", df.index[0].strftime("%b %d, %Y"))
s3.metric("Last bar",  df.index[-1].strftime("%b %d, %Y"))
avg_vol = int(df.tail(90)["volume"].mean()) if not df.tail(90)["volume"].empty else 0
s4.metric("Avg volume (90d)", f"{avg_vol:,}")

# --- Recent bars table + CSV download --------------------------------------

st.subheader("Recent bars")
recent = df.tail(30).iloc[::-1].reset_index()
recent["trade_date"] = recent["trade_date"].dt.date
st.dataframe(
    recent,
    use_container_width=True,
    hide_index=True,
    column_config={
        "trade_date": st.column_config.DateColumn("Date"),
        "open":      st.column_config.NumberColumn("Open",  format="$%.2f"),
        "high":      st.column_config.NumberColumn("High",  format="$%.2f"),
        "low":       st.column_config.NumberColumn("Low",   format="$%.2f"),
        "close":     st.column_config.NumberColumn("Close", format="$%.2f"),
        "adj_close": st.column_config.NumberColumn("Adj close", format="$%.2f"),
        "volume":    st.column_config.NumberColumn("Volume", format="%d"),
    },
)

st.download_button(
    f"Download {symbol} full history (CSV)",
    data=df.reset_index().to_csv(index=False),
    file_name=f"{symbol}_history.csv",
    mime="text/csv",
    icon=":material/download:",
)
