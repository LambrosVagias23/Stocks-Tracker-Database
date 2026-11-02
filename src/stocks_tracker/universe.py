"""Build the universe of US tickers to track.

Sources
-------
S&P 500   : Wikipedia (list of constituents).
NASDAQ 100: Wikipedia (list of constituents).
Russell 2000: iShares IWM ETF holdings CSV. Wikipedia doesn't list all 2,000
    names; IWM publishes its full holdings daily and is the de-facto reference
    used by data vendors.

Symbols are normalised to the form yfinance expects: dots are replaced with
hyphens (BRK.B -> BRK-B), whitespace is stripped, and any non-equity rows
(cash, pending settlements) are dropped.
"""

from __future__ import annotations

import io
import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

import pandas as pd
import requests

from stocks_tracker.config import (
    INDEX_NDX,
    INDEX_R2000,
    INDEX_SP500,
    NDX_SLICKCHARTS_URL,
    SP500_WIKI_URL,
)
from stocks_tracker.db import upsert_tickers

if TYPE_CHECKING:
    pass

log = logging.getLogger(__name__)

R2000_SOURCE_URL = "https://stockanalysis.com/list/russell-2000-stocks/"
R2000_MAX_PAGES = 6  # safety cap; R2000 has ~2,000 names, 500/page = 4 pages

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
)


@dataclass(frozen=True)
class TickerEntry:
    symbol: str
    name: str | None
    index: str  # one of INDEX_SP500 / INDEX_NDX / INDEX_R2000


def _normalise_symbol(sym: str) -> str:
    """Yahoo Finance uses hyphens where Wikipedia / vendors use dots."""
    return sym.strip().upper().replace(".", "-")


def _fetch_html(url: str) -> str:
    r = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=30)
    r.raise_for_status()
    return r.text


def fetch_sp500() -> list[TickerEntry]:
    html = _fetch_html(SP500_WIKI_URL)
    tables = pd.read_html(io.StringIO(html), attrs={"id": "constituents"})
    df = tables[0]
    out: list[TickerEntry] = []
    for _, row in df.iterrows():
        sym = _normalise_symbol(str(row["Symbol"]))
        name = str(row.get("Security") or row.get("Company") or "").strip() or None
        if sym:
            out.append(TickerEntry(sym, name, INDEX_SP500))
    log.info("S&P 500: %d symbols", len(out))
    return out


def fetch_ndx() -> list[TickerEntry]:
    html = _fetch_html(NDX_SLICKCHARTS_URL)
    df = pd.read_html(io.StringIO(html))[0]
    out = [
        TickerEntry(
            _normalise_symbol(str(r["Symbol"])),
            str(r["Company"]).strip() or None,
            INDEX_NDX,
        )
        for _, r in df.iterrows()
        if str(r["Symbol"]).strip()
    ]
    log.info("NASDAQ 100: %d symbols", len(out))
    return out


def fetch_r2000() -> list[TickerEntry]:
    """Pull Russell 2000 constituents from stockanalysis.com (paginated).

    iShares' IWM holdings CSV endpoint is behind a WAF that returns the
    product-page HTML to non-browser clients, so we use stockanalysis.com's
    public Russell 2000 list, which paginates at 500 rows/page.
    """
    seen: dict[str, str | None] = {}
    for page in range(1, R2000_MAX_PAGES + 1):
        url = R2000_SOURCE_URL + (f"?page={page}" if page > 1 else "")
        resp = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=30)
        if resp.status_code == 404:
            break  # pagination exhausted
        resp.raise_for_status()
        try:
            df = pd.read_html(io.StringIO(resp.text), flavor="lxml")[0]
        except ValueError:
            break  # no table — reached the end
        if "Symbol" not in df.columns or df.empty:
            break
        before = len(seen)
        for _, r in df.iterrows():
            sym = _normalise_symbol(str(r["Symbol"]))
            if not sym or sym == "NAN":
                continue
            name = str(r.get("Company Name") or "").strip() or None
            seen.setdefault(sym, name)
        if len(seen) == before:
            break  # page returned only duplicates — done

    out = [TickerEntry(sym, name, INDEX_R2000) for sym, name in sorted(seen.items())]
    log.info("Russell 2000 (stockanalysis.com): %d symbols", len(out))
    return out


def build_universe() -> list[tuple[str, str | None, list[str], None]]:
    """Fetch all three sources and merge into (symbol, name, memberships, first_seen=None)."""
    entries: list[TickerEntry] = []
    for fetcher in (fetch_sp500, fetch_ndx, fetch_r2000):
        try:
            entries.extend(fetcher())
        except Exception as exc:  # noqa: BLE001
            log.error("%s failed: %s", fetcher.__name__, exc)

    # Merge: symbol -> (name, {indexes})
    merged: dict[str, dict] = {}
    for e in entries:
        slot = merged.setdefault(e.symbol, {"name": e.name, "indexes": set()})
        slot["indexes"].add(e.index)
        if not slot["name"] and e.name:
            slot["name"] = e.name

    rows = [
        (sym, info["name"], sorted(info["indexes"]), None)
        for sym, info in sorted(merged.items())
    ]
    log.info("Universe: %d unique symbols across SP500/NDX/R2000", len(rows))
    return rows


def main() -> None:
    """CLI: refresh the universe and upsert into the tickers table."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    rows = build_universe()
    n = upsert_tickers(rows)
    print(f"Upserted {n} tickers")


if __name__ == "__main__":
    main()
