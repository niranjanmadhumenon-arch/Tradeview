"""Stock search by company name or ticker.

Two sources are merged: instruments already in the local ledger (instant, works
offline) and Yahoo's symbol search, limited to NSE and BSE equities. A Yahoo
failure is not an error: the caller still gets the local matches.
"""
from __future__ import annotations

import time
from typing import Callable

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Instrument

Lookup = Callable[[str, int], list[dict]]

_SUFFIX = {".NS": "NSE", ".BO": "BSE"}
_CACHE: dict[str, tuple[float, list[dict]]] = {}
_CACHE_SECONDS = 600
_CACHE_SIZE = 256


def yahoo_lookup(query: str, limit: int) -> list[dict]:
    """Raw quote rows from Yahoo's search. Imported lazily; needs the network."""
    import yfinance as yf

    found = yf.Search(query, max_results=limit, news_count=0, enable_fuzzy_query=True, timeout=5)
    return list(found.quotes or [])


def _exchange(symbol: str) -> str | None:
    return _SUFFIX.get(symbol[-3:].upper()) if len(symbol) > 3 else None


def _normalise(rows: list[dict]) -> list[dict]:
    out = []
    for row in rows:
        symbol = str(row.get("symbol") or "").upper()
        exchange = _exchange(symbol)
        if exchange is None or str(row.get("quoteType") or "EQUITY").upper() != "EQUITY":
            continue
        name = row.get("longname") or row.get("shortname") or ""
        out.append({"symbol": symbol, "name": str(name).strip(), "exchange": exchange, "held": False})
    return out


def _remote(query: str, limit: int, lookup: Lookup) -> list[dict]:
    key = query.lower()
    hit = _CACHE.get(key)
    if hit and time.monotonic() - hit[0] < _CACHE_SECONDS:
        return hit[1]
    # Yahoo ranks global listings first, so ask for more than we show and filter.
    rows = _normalise(lookup(query, max(limit * 3, 20)))
    if len(_CACHE) >= _CACHE_SIZE:
        _CACHE.clear()
    _CACHE[key] = (time.monotonic(), rows)
    return rows


def _rank(query: str, item: dict) -> tuple:
    q = query.lower()
    ticker = item["symbol"][:-3].lower()
    name = item["name"].lower()
    if ticker == q:
        tier = 0
    elif ticker.startswith(q):
        tier = 1
    elif name.startswith(q) or any(word.startswith(q) for word in name.split()):
        tier = 2
    else:
        tier = 3
    # held first within a tier, then NSE before BSE (the app's default listing)
    return (tier, not item["held"], item["exchange"] != "NSE")


def search(session: Session, query: str, limit: int = 10, lookup: Lookup | None = None) -> dict:
    query = " ".join(query.split())
    if not query:
        return {"query": query, "results": [], "online": True}

    like = f"%{query.replace('%', '').replace('_', '')}%"
    local = session.scalars(
        select(Instrument).where(Instrument.symbol.ilike(like) | Instrument.name.ilike(like))
    ).all()
    merged: dict[str, dict] = {
        i.symbol: {"symbol": i.symbol, "name": i.name or "",
                   "exchange": _exchange(i.symbol) or i.exchange or "", "held": True}
        for i in local
    }

    online = True
    try:
        remote = _remote(query, limit, lookup or yahoo_lookup)
    except Exception:  # offline, rate-limited or a changed response: local results still stand
        remote, online = [], False
    for item in remote:
        known = merged.get(item["symbol"])
        if known is None:
            merged[item["symbol"]] = dict(item)
        elif not known["name"]:
            known["name"] = item["name"]

    # stable sort keeps Yahoo's own relevance order inside each tier
    results = sorted(merged.values(), key=lambda item: _rank(query, item))[:limit]
    return {"query": query, "results": results, "online": online}
