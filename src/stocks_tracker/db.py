from __future__ import annotations

import logging
from collections.abc import Iterable, Sequence
from datetime import date
from functools import lru_cache
from pathlib import Path
from typing import Any

from psycopg2.extras import execute_values
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

from stocks_tracker.config import DB_UPSERT_BATCH_SIZE, PROJECT_ROOT, get_db_url

log = logging.getLogger(__name__)

SQL_DIR = PROJECT_ROOT / "sql"


@lru_cache(maxsize=1)
def get_engine() -> Engine:
    url = get_db_url()
    # SQLAlchemy 2.1+ picks psycopg (v3) for the bare `postgresql://` scheme;
    # we ship psycopg2-binary (and use psycopg2.extras.execute_values), so pin
    # the driver explicitly.
    if url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+psycopg2://", 1)
    return create_engine(url, pool_pre_ping=True, future=True)


def apply_schema(sql_dir: Path = SQL_DIR) -> None:
    """Apply every ``*.sql`` file in sql_dir in sorted order.

    Each file is wrapped in its own transaction. All files are written to be
    idempotent (``CREATE TABLE IF NOT EXISTS``, ``ALTER COLUMN TYPE`` noop when
    the type already matches) so re-running is safe.
    """
    engine = get_engine()
    for path in sorted(sql_dir.glob("*.sql")):
        sql = path.read_text(encoding="utf-8")
        with engine.begin() as conn:
            conn.exec_driver_sql(sql)
        log.info("Applied %s", path.name)


def ping() -> dict[str, Any]:
    """Smoke test: SELECT version() and count the known tables."""
    engine = get_engine()
    with engine.connect() as conn:
        version = conn.execute(text("SELECT version()")).scalar_one()
        tables = conn.execute(
            text(
                "SELECT tablename FROM pg_tables "
                "WHERE schemaname = 'public' ORDER BY tablename"
            )
        ).scalars().all()
    return {"version": version, "public_tables": tables}


def _execute_values_upsert(
    sql: str,
    rows: Sequence[tuple],
    page_size: int = DB_UPSERT_BATCH_SIZE,
) -> int:
    """Run a batched INSERT ... ON CONFLICT via psycopg2.execute_values.

    Returns the number of rows sent (not necessarily the number affected,
    since ON CONFLICT DO UPDATE touches already-existing rows too).
    """
    if not rows:
        return 0
    engine = get_engine()
    raw = engine.raw_connection()
    try:
        with raw.cursor() as cur:
            execute_values(cur, sql, rows, page_size=page_size)
        raw.commit()
    finally:
        raw.close()
    return len(rows)


def upsert_tickers(rows: Iterable[tuple[str, str | None, list[str], date | None]]) -> int:
    """Upsert (symbol, name, index_membership, first_seen) rows into `tickers`.

    index_membership is merged (union) with the existing array on conflict so
    a ticker appearing in multiple index refreshes keeps all memberships.
    """
    rows = list(rows)
    sql = """
        INSERT INTO tickers (symbol, name, index_membership, first_seen, updated_at)
        VALUES %s
        ON CONFLICT (symbol) DO UPDATE SET
            name = COALESCE(EXCLUDED.name, tickers.name),
            index_membership = ARRAY(
                SELECT DISTINCT unnest(tickers.index_membership || EXCLUDED.index_membership)
            ),
            first_seen = LEAST(tickers.first_seen, EXCLUDED.first_seen),
            updated_at = NOW()
    """
    # execute_values wants the row-template parameter; the VALUES clause
    # structure matches our tuple order.
    template = "(%s, %s, %s::text[], %s, NOW())"
    engine = get_engine()
    raw = engine.raw_connection()
    try:
        with raw.cursor() as cur:
            execute_values(cur, sql, rows, template=template,
                           page_size=DB_UPSERT_BATCH_SIZE)
        raw.commit()
    finally:
        raw.close()
    return len(rows)


PRICES_UPSERT_SQL = """
    INSERT INTO prices
        (symbol, trade_date, open, high, low, close, adj_close, volume)
    VALUES %s
    ON CONFLICT (symbol, trade_date) DO UPDATE SET
        open      = EXCLUDED.open,
        high      = EXCLUDED.high,
        low       = EXCLUDED.low,
        close     = EXCLUDED.close,
        adj_close = EXCLUDED.adj_close,
        volume    = EXCLUDED.volume
"""


def upsert_prices(rows: Sequence[tuple]) -> int:
    """Bulk upsert OHLCV rows. Each tuple is (symbol, trade_date, o, h, l, c, adj, vol)."""
    return _execute_values_upsert(PRICES_UPSERT_SQL, rows)


def set_ingest_state(symbol: str, last_bar: date | None, error: str | None = None) -> None:
    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO ingest_state (symbol, last_bar, last_run_at, last_error) "
                "VALUES (:symbol, :last_bar, NOW(), :error) "
                "ON CONFLICT (symbol) DO UPDATE SET "
                "  last_bar    = COALESCE(EXCLUDED.last_bar, ingest_state.last_bar), "
                "  last_run_at = NOW(), "
                "  last_error  = EXCLUDED.last_error"
            ),
            {"symbol": symbol, "last_bar": last_bar, "error": error},
        )


def get_last_bar(symbol: str) -> date | None:
    engine = get_engine()
    with engine.connect() as conn:
        return conn.execute(
            text("SELECT last_bar FROM ingest_state WHERE symbol = :s"),
            {"s": symbol},
        ).scalar_one_or_none()


def get_active_tickers() -> list[str]:
    engine = get_engine()
    with engine.connect() as conn:
        return list(
            conn.execute(
                text("SELECT symbol FROM tickers WHERE active ORDER BY symbol")
            ).scalars()
        )


def main() -> None:
    """CLI: `python -m stocks_tracker.db` applies the schema then pings."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    apply_schema()
    info = ping()
    print(f"Postgres: {info['version']}")
    print(f"Public tables: {info['public_tables']}")


if __name__ == "__main__":
    main()
