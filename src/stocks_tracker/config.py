from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(PROJECT_ROOT / ".env")

INDEX_SP500 = "SP500"
INDEX_NDX = "NDX"
INDEX_R2000 = "R2000"

SP500_WIKI_URL = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
# Wikipedia's Nasdaq-100 page no longer lists its constituents inline; Slickcharts
# publishes a stable HTML table.
NDX_SLICKCHARTS_URL = "https://www.slickcharts.com/nasdaq100"

BACKFILL_YEARS = 10
YFINANCE_BATCH_SIZE = 100
DB_UPSERT_BATCH_SIZE = 5000


def get_db_url() -> str:
    """Return the DB URL for scripts.

    Prefers the pooled (IPv4) URL so the same code path works locally and in
    GitHub Actions. Falls back to the direct URL when the pooled one is unset.
    """
    url = os.getenv("SUPABASE_DB_URL_POOLED") or os.getenv("SUPABASE_DB_URL")
    if not url:
        raise RuntimeError(
            "No database URL configured. Set SUPABASE_DB_URL_POOLED (preferred) "
            "or SUPABASE_DB_URL in .env — see .env.example."
        )
    return url


def get_supabase_client_config() -> tuple[str, str]:
    """Return (project_url, anon_key) for the Streamlit app's supabase-py client."""
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_ANON_KEY")
    if not url or not key:
        raise RuntimeError(
            "SUPABASE_URL and SUPABASE_ANON_KEY must be set — see .env.example."
        )
    return url, key
