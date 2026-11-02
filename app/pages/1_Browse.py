from __future__ import annotations

import streamlit as st

from stocks_tracker.app_data import load_ingest_state, load_tickers

st.set_page_config(page_title="Browse — Stocks Tracker", layout="wide")
st.title("Browse the universe")

tickers = load_tickers()
state = load_ingest_state()

if tickers.empty:
    st.error("No tickers found. Run `python -m stocks_tracker.universe` to populate.")
    st.stop()

merged = tickers.merge(
    state[["symbol", "last_bar"]], on="symbol", how="left"
)

st.sidebar.header("Filters")
options = ["SP500", "NDX", "R2000"]
chosen = st.sidebar.multiselect("Index membership", options, default=options)
query = st.sidebar.text_input("Search (symbol or name)", "").strip().lower()
show_only_with_prices = st.sidebar.checkbox("Only tickers with price history", value=False)

mask = merged["index_membership"].apply(lambda ms: any(m in chosen for m in (ms or [])))
if query:
    mask &= (
        merged["symbol"].str.lower().str.contains(query, na=False)
        | merged["name"].fillna("").str.lower().str.contains(query, na=False)
    )
if show_only_with_prices:
    mask &= merged["last_bar"].notna()

filtered = merged[mask].reset_index(drop=True)
st.caption(f"{len(filtered):,} of {len(tickers):,} symbols match")

st.dataframe(
    filtered,
    column_config={
        "symbol": "Symbol",
        "name": "Name",
        "index_membership": "Indexes",
        "active": "Active",
        "last_bar": st.column_config.DateColumn("Last bar"),
    },
    use_container_width=True,
    hide_index=True,
)
