"""Data-access helpers for the Streamlit app.

The app runs on Streamlit Community Cloud using the Supabase anon key
(public, read-only via the RLS policies in sql/001_init_schema.sql).
That means we query over PostgREST via supabase-py rather than through
SQLAlchemy with the pooled DB URL. ``@st.cache_data`` keeps repeated
tab visits snappy without hammering the free-tier database.
"""

from __future__ import annotations

from datetime import date
from typing import Any

import pandas as pd
import streamlit as st
from supabase import Client, create_client

from stocks_tracker.config import get_supabase_client_config

_PAGE_SIZE = 1000  # PostgREST hard-caps responses at 1000 rows per request


@st.cache_resource
def get_client() -> Client:
    url, key = get_supabase_client_config()
    return create_client(url, key)


def _paginate(query_builder) -> list[dict[str, Any]]:
    """Walk PostgREST pages until a short response signals the end."""
    rows: list[dict[str, Any]] = []
    page = 0
    while True:
        resp = query_builder.range(
            page * _PAGE_SIZE, (page + 1) * _PAGE_SIZE - 1
        ).execute()
        batch = resp.data or []
        rows.extend(batch)
        if len(batch) < _PAGE_SIZE:
            break
        page += 1
    return rows


@st.cache_data(ttl=300)
def load_tickers() -> pd.DataFrame:
    sb = get_client()
    rows = _paginate(
        sb.table("tickers")
        .select("symbol, name, index_membership, active")
        .order("symbol")
    )
    return pd.DataFrame(rows)


@st.cache_data(ttl=60)
def load_ingest_state() -> pd.DataFrame:
    sb = get_client()
    rows = _paginate(sb.table("ingest_state").select("symbol, last_bar, last_run_at"))
    df = pd.DataFrame(rows)
    if not df.empty:
        df["last_bar"] = pd.to_datetime(df["last_bar"])
    return df


@st.cache_data(ttl=300)
def load_prices(
    symbol: str,
    start: date | str | None = None,
    end: date | str | None = None,
) -> pd.DataFrame:
    sb = get_client()
    q = (
        sb.table("prices")
        .select("trade_date, open, high, low, close, adj_close, volume")
        .eq("symbol", symbol)
        .order("trade_date")
    )
    if start is not None:
        q = q.gte("trade_date", str(start))
    if end is not None:
        q = q.lte("trade_date", str(end))
    rows = _paginate(q)
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    df["trade_date"] = pd.to_datetime(df["trade_date"])
    df = df.set_index("trade_date")
    for col in ("open", "high", "low", "close", "adj_close"):
        df[col] = df[col].astype(float)
    df["volume"] = df["volume"].fillna(0).astype(int)
    return df
