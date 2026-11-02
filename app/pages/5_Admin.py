"""Admin actions: refresh universe / incremental update / full backfill.

The actions here write to Supabase, so they require the superuser pooled
connection string in ``SUPABASE_DB_URL_POOLED``. On a public deploy
(Streamlit Community Cloud) only the anon key is configured, so this
page shows a disabled state. Running the app locally with ``.env``
populated unlocks the actions.
"""

from __future__ import annotations

import logging
import os

import streamlit as st

# Importing config has a side effect of loading .env, which is what
# populates SUPABASE_DB_URL_POOLED when running locally.
import stocks_tracker.config  # noqa: F401

st.set_page_config(page_title="Admin — Stocks Tracker", layout="wide")
st.title("Admin")
st.caption(
    "Trigger universe refresh, daily update, or full backfill. "
    "Writes to Supabase, so only enabled when the pooled DB URL is configured."
)

HAS_DB_WRITE = bool(os.getenv("SUPABASE_DB_URL_POOLED") or os.getenv("SUPABASE_DB_URL"))

if not HAS_DB_WRITE:
    st.warning(
        "**Read-only mode.** This instance only has the Supabase anon key, "
        "which cannot write to the database. Admin actions are disabled.\n\n"
        "To use this page, run the app locally with `.env` populated:\n"
        "```powershell\n"
        "uv run streamlit run app/streamlit_app.py\n"
        "```"
    )
    st.stop()

st.success("Write access to Supabase is available on this instance.")


class _StreamlitLogHandler(logging.Handler):
    """Push log records from the stocks_tracker.* loggers to a Streamlit container."""

    def __init__(self, container) -> None:
        super().__init__()
        self.container = container

    def emit(self, record: logging.LogRecord) -> None:
        try:
            self.container.write(f"`{record.levelname[0]}` {record.getMessage()}")
        except Exception:  # noqa: BLE001
            # Streamlit may complain if called outside a script run — swallow it.
            pass


def _with_live_logs(status, fn, *args, **kwargs):
    handler = _StreamlitLogHandler(status)
    handler.setLevel(logging.INFO)
    pkg_logger = logging.getLogger("stocks_tracker")
    main_logger = logging.getLogger("__main__")
    for lg in (pkg_logger, main_logger):
        lg.addHandler(handler)
        lg.setLevel(logging.INFO)
    try:
        return fn(*args, **kwargs)
    finally:
        for lg in (pkg_logger, main_logger):
            lg.removeHandler(handler)


# ----- Action 1: refresh universe --------------------------------------------

with st.container(border=True):
    st.subheader("Refresh universe")
    st.caption(
        "Re-scrape S&P 500 (Wikipedia), NASDAQ 100 (Slickcharts), and "
        "Russell 2000 (stockanalysis.com) and upsert into `tickers`. "
        "Takes about 10 seconds. Safe to run anytime."
    )
    if st.button("Refresh universe", key="univ_btn", type="primary"):
        with st.status("Scraping sources...", expanded=True) as status:
            from stocks_tracker.db import upsert_tickers
            from stocks_tracker.universe import build_universe

            rows = _with_live_logs(status, build_universe)
            status.write(f"Upserting {len(rows)} rows...")
            upsert_tickers(rows)
            status.update(label=f"Refreshed {len(rows)} tickers", state="complete")


# ----- Action 2: daily incremental update ------------------------------------

with st.container(border=True):
    st.subheader("Daily incremental update")
    st.caption(
        "For every ticker with existing history, pull the last few trading "
        "days of bars. For any ticker that has never been loaded, this runs "
        "the full backfill path for that ticker. Typically 1–5 minutes."
    )
    col1, col2 = st.columns(2)
    with col1:
        upd_lookback = st.number_input(
            "Lookback (days)", min_value=1, max_value=30, value=7,
            help="Days of history to re-fetch for already-loaded tickers.",
        )
    with col2:
        upd_limit = st.number_input(
            "Limit (0 = all)", min_value=0, max_value=5000, value=0, step=100,
            help="Cap on active tickers to process (for testing).",
        )
    if st.button("Run update", key="upd_btn", type="primary"):
        with st.status("Running incremental update...", expanded=True) as status:
            from stocks_tracker.update import run

            counts = _with_live_logs(
                status, run,
                lookback_days=int(upd_lookback),
                limit=int(upd_limit) if upd_limit > 0 else None,
            )
            status.write(f"Backfilled rows: `{counts['backfilled']}`")
            status.write(f"Incremental rows: `{counts['updated']}`")
            status.update(
                label=f"Update complete: {counts['backfilled'] + counts['updated']} rows",
                state="complete",
            )


# ----- Action 3: full backfill -----------------------------------------------

with st.container(border=True):
    st.subheader("Full backfill")
    st.caption(
        "Pull N years of OHLCV for every active ticker from scratch. "
        "**The full 2,500-symbol × 10-year run takes 45–60 minutes** and "
        "writes ~300 MB to Supabase. You usually only need this once; "
        "after the first run, use **Daily incremental update** instead."
    )
    col1, col2 = st.columns(2)
    with col1:
        bf_years = st.slider("Years of history", 1, 20, 10, key="bf_years")
    with col2:
        bf_limit = st.number_input(
            "Limit (0 = all tickers)", min_value=0, max_value=5000,
            value=0, step=100, key="bf_limit",
        )
    bf_confirm = st.checkbox(
        "I understand this blocks the Streamlit session for the entire run "
        "and may take 45–60 minutes for the full universe.",
        key="bf_confirm",
    )
    if st.button("Run backfill", key="bf_btn", type="primary", disabled=not bf_confirm):
        with st.status(f"Backfilling {bf_years}y of history...", expanded=True) as status:
            from stocks_tracker.backfill import backfill
            from stocks_tracker.db import get_active_tickers

            symbols = get_active_tickers()
            if bf_limit > 0:
                symbols = symbols[: int(bf_limit)]
            status.write(f"Backfilling **{len(symbols)}** symbols over **{bf_years}** years")
            total = _with_live_logs(status, backfill, symbols, years=int(bf_years))
            status.update(
                label=f"Backfill complete: {total:,} rows across {len(symbols)} symbols",
                state="complete",
            )
