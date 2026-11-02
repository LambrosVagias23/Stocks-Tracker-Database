from __future__ import annotations

import pytest

from stocks_tracker import db


@pytest.mark.integration
def test_ping_returns_version_and_known_tables():
    info = db.ping()
    assert "PostgreSQL" in info["version"]
    public = set(info["public_tables"])
    assert {"tickers", "prices", "ingest_state"}.issubset(public), (
        f"Expected core tables; got {public}. Run `python -m stocks_tracker.db` to apply schema."
    )


@pytest.mark.integration
def test_apply_schema_is_idempotent():
    # Applying twice must not raise — the SQL uses CREATE ... IF NOT EXISTS.
    db.apply_schema()
    db.apply_schema()
