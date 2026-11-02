from __future__ import annotations

import pytest

from stocks_tracker import universe


def test_normalise_symbol_replaces_dot_with_hyphen():
    assert universe._normalise_symbol("BRK.B") == "BRK-B"
    assert universe._normalise_symbol(" aapl ") == "AAPL"
    assert universe._normalise_symbol("goog") == "GOOG"


@pytest.mark.integration
def test_build_universe_returns_plausible_us_universe():
    rows = universe.build_universe()
    syms = {r[0] for r in rows}
    assert len(syms) > 1500, f"Expected ~2,500 symbols, got {len(syms)}"
    assert {"AAPL", "MSFT", "NVDA"}.issubset(syms), "Mega-caps missing"
