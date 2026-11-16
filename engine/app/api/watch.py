"""Watchlist (starred stocks, shown with *), the local price cache, and the
portfolio optimiser.

Every stock you star, hold or look up gets its daily prices stored in the
local database (ledger.sqlite3 in the app's data folder). Later requests are
answered from that file and only the days since the last download are
fetched, so nothing is downloaded twice."""
from __future__ import annotations

import asyncio
import csv
import io
from datetime import date, datetime, timedelta

import numpy as np
from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import config
from app.api.routes import get_session, require_token
from app.db.models import Instrument, PriceBar, Setting, Trade, Watch
from app.ledger import ingest
from app.ledger.positions import EPS
from app.market import fx, history, symbols
from app.quant import optimizer, service

router = APIRouter(prefix="/api", dependencies=[Depends(require_token)])


def _symbol(raw: str) -> str:
    s = raw.strip().upper()
    if symbols.namespace(s) == "BOND":
        raise HTTPException(status_code=400, detail="Bonds have no market prices to track")
    if not (symbols.is_indian(s) or symbols.is_international(s) or symbols.is_namespaced(s)
            or s.startswith("^")):
        raise HTTPException(status_code=400, detail=f"'{raw}' is not a symbol the app can price")
    return s


def _cache(session: Session, symbol: str, days: int, fetcher=None) -> str | None:
    """Makes sure `days` of history are cached. Returns a warning, or None."""
    start = date.today() - timedelta(days=days)
    try:
        history.refresh_symbol(session, symbol, start, fetcher=fetcher,
                               with_actions=not symbol.startswith("^"))
        ccy = fx.currencies(session, [symbol])
        for pair in fx.fx_symbols(ccy):
            history.refresh_symbol(session, pair, start, fetcher=fetcher, with_actions=False)
        return None
    except Exception as exc:
        session.rollback()
        return f"Could not refresh {symbol}: {exc}"


# ---------------------------------------------------------------- watchlist

class WatchIn(BaseModel):
    starred: bool = True
    name: str | None = Field(default=None, max_length=120)


class ViewIn(BaseModel):
    name: str | None = Field(default=None, max_length=120)


def _watch_rows(session: Session) -> list[dict]:
    rows = session.scalars(select(Watch).order_by(Watch.starred.desc(), Watch.viewed_at.desc(),
                                                  Watch.added_at.desc())).all()
    held = {s for s, p in service.load_positions(session).items() if p.quantity > EPS}
    out = []
    for w in rows:
        inst = session.get(Instrument, w.symbol)
        bars = session.scalars(select(PriceBar).where(PriceBar.symbol == w.symbol)
                               .order_by(PriceBar.date.desc()).limit(2)).all()
        count = session.scalar(select(func.count()).where(PriceBar.symbol == w.symbol))
        last, prev = (bars[0].close if bars else None), (bars[1].close if len(bars) > 1 else None)
        out.append({
            "symbol": w.symbol, "starred": w.starred, "name": inst.name if inst else "",
            "asset_class": (inst.asset_class if inst and inst.asset_class
                            else symbols.asset_class(w.symbol, inst.name if inst else "")),
            "currency": fx.currency_of(w.symbol, {w.symbol: inst} if inst else None),
            "last": last, "as_of": bars[0].date.isoformat() if bars else None,
            "change_pct": (last / prev - 1) if last and prev else None,
            "cached_bars": count, "held": w.symbol in held,
            "viewed_at": w.viewed_at.isoformat() if w.viewed_at else None,
        })
    return out


@router.get("/watchlist")
def watchlist(session: Session = Depends(get_session)):
    return _watch_rows(session)


def _upsert(session: Session, symbol: str, name: str | None, *, star: bool | None, viewed: bool) -> Watch:
    now = datetime.now().replace(microsecond=0)
    w = session.get(Watch, symbol) or Watch(symbol=symbol, starred=False, added_at=now)
    if star is not None:
        w.starred = star
    if viewed:
        w.viewed_at = now
    session.merge(w)
    if not symbol.startswith("^"):
        ingest.remember_instrument(session, symbol, name)
    session.commit()
    return w


@router.put("/watchlist/{symbol}")
async def star(symbol: str, body: WatchIn, request: Request):
    """Stars (or unstars) a stock and caches its price history straight away."""
    symbol = _symbol(symbol)
    fetcher = getattr(request.app.state, "price_fetcher", None)

    def run() -> dict:
        with request.app.state.sessionmaker() as s:
            _upsert(s, symbol, body.name, star=body.starred, viewed=False)
            warning = _cache(s, symbol, 3 * 365, fetcher) if body.starred else None
            return {"watchlist": _watch_rows(s), "warning": warning}

    return await asyncio.to_thread(run)


@router.post("/watchlist/{symbol}/view")
async def viewed(symbol: str, body: ViewIn, request: Request):
    """Called when a stock is opened in the app: remembers it and caches its prices."""
    symbol = _symbol(symbol)
    fetcher = getattr(request.app.state, "price_fetcher", None)

    def run() -> dict:
        with request.app.state.sessionmaker() as s:
            _upsert(s, symbol, body.name, star=None, viewed=True)
            return {"symbol": symbol, "warning": _cache(s, symbol, 3 * 365, fetcher)}

    return await asyncio.to_thread(run)


@router.delete("/watchlist/{symbol}")
def forget(symbol: str, session: Session = Depends(get_session)):
    w = session.get(Watch, symbol.strip().upper())
    if w is None:
        raise HTTPException(status_code=404, detail="Not on the watchlist")
    session.delete(w)
    session.commit()
    return _watch_rows(session)


# ---------------------------------------------------------------- cached prices

@router.get("/prices/{symbol}")
async def prices(symbol: str, request: Request, days: int = Query(365, ge=5, le=3660)):
    """Daily closes from the local cache, downloading only what is missing."""
    symbol = _symbol(symbol)
    fetcher = getattr(request.app.state, "price_fetcher", None)

    def run() -> dict:
        with request.app.state.sessionmaker() as s:
            warning = _cache(s, symbol, days, fetcher)
            since = date.today() - timedelta(days=days)
            bars = s.scalars(select(PriceBar).where(PriceBar.symbol == symbol, PriceBar.date >= since)
                             .order_by(PriceBar.date)).all()
            return {"symbol": symbol, "currency": fx.currencies(s, [symbol])[symbol], "warning": warning,
                    "bars": [{"date": b.date.isoformat(), "close": b.close, "adj_close": b.adj_close}
                             for b in bars]}

    return await asyncio.to_thread(run)


@router.get("/prices/{symbol}/csv")
def prices_csv(symbol: str, session: Session = Depends(get_session)):
    """The cached history of one symbol as a CSV file (no download from Yahoo)."""
    symbol = symbol.strip().upper()
    bars = session.scalars(select(PriceBar).where(PriceBar.symbol == symbol).order_by(PriceBar.date)).all()
    if not bars:
        raise HTTPException(status_code=404, detail="Nothing cached for this symbol yet")
    out = io.StringIO()
    w = csv.writer(out, lineterminator="\n")
    w.writerow(["date", "close", "adj_close"])
    w.writerows([b.date.isoformat(), b.close, b.adj_close] for b in bars)
    safe = "".join(c if c.isalnum() or c in "-_." else "_" for c in symbol)
    return Response(content=out.getvalue(), media_type="text/csv",
                    headers={"Content-Disposition": f'attachment; filename="{safe}-prices.csv"'})


@router.get("/cache")
def cache_status(session: Session = Depends(get_session)):
    """What is stored locally, and how many downloads the cache has saved."""
    rows = session.execute(select(PriceBar.symbol, func.count(), func.min(PriceBar.date), func.max(PriceBar.date))
                           .group_by(PriceBar.symbol)).all()
    marks = {s.key.split(":", 1)[1]: s.value.partition("|")[0]
             for s in session.scalars(select(Setting).where(Setting.key.like("refreshed:%")))}
    counters = {s.key.split(":", 1)[1]: int(s.value or 0)
                for s in session.scalars(select(Setting).where(Setting.key.like("cache:%")))}
    starred = {w.symbol for w in session.scalars(select(Watch).where(Watch.starred))}
    traded = set(session.scalars(select(Trade.symbol).distinct()))
    return {
        "database": config.database_url().removeprefix("sqlite:///"),
        "symbols": [{"symbol": s, "bars": n, "first": lo.isoformat(), "last": hi.isoformat(),
                     "refreshed": marks.get(s), "starred": s in starred, "traded": s in traded}
                    for s, n, lo, hi in sorted(rows)],
        "bars": sum(n for _, n, _, _ in rows),
        "served_from_cache": counters.get("hits", 0),
        "incremental_updates": counters.get("incremental", 0),
        "full_downloads": counters.get("downloads", 0),
    }


# ---------------------------------------------------------------- optimiser

class OptimiseIn(BaseModel):
    symbols: list[str] | None = Field(default=None, description="Default: the starred stocks")
    include_holdings: bool = False
    lookback_days: int = Field(default=504, ge=60, le=1260)
    max_weight: float = Field(default=0.35, gt=0, le=1)


@router.post("/optimizer")
async def optimise(body: OptimiseIn, request: Request):
    fetcher = getattr(request.app.state, "price_fetcher", None)

    def run() -> dict:
        with request.app.state.sessionmaker() as s:
            return run_optimiser(s, body, fetcher)

    return await asyncio.to_thread(run)


def run_optimiser(session: Session, body: OptimiseIn, fetcher=None) -> dict:
    warnings: list[str] = []
    wanted = [x.strip().upper() for x in body.symbols] if body.symbols else list(
        session.scalars(select(Watch.symbol).where(Watch.starred)))
    positions = service.load_positions(session)
    held = {sym: p for sym, p in positions.items() if p.quantity > EPS}
    if body.include_holdings:
        wanted += [h for h in held if h not in wanted and not symbols.namespace(h) == "BOND"]
    wanted = list(dict.fromkeys(w for w in wanted if not w.startswith("BOND:")))
    if len(wanted) < 2:
        raise HTTPException(status_code=400, detail="Star at least two stocks (or include your holdings)")

    calendar_days = int(body.lookback_days * 1.5) + 14
    for sym in wanted:
        w = _cache(session, sym, calendar_days, fetcher)
        if w:
            warnings.append(w)
    _, adj = history.load_prices(session, wanted)
    ccys = fx.currencies(session, wanted)
    rates = fx.Rates(session, ccys)
    usable = []
    for sym in wanted:
        if sym not in adj.columns or adj[sym].notna().sum() < 60:
            warnings.append(f"Not enough price history for {sym}; left out")
            continue
        r = rates.frame(sym, adj.index)
        if symbols.fx_pair(ccys.get(sym, "INR")) and r is None:
            warnings.append(f"No {ccys[sym]}/INR rate for {sym}; left out")
            continue
        if r is not None:
            adj[sym] = adj[sym] * r
        usable.append(sym)
    if len(usable) < 2:
        raise HTTPException(status_code=409, detail="Need price history for at least two of the stocks")
    rets = adj[usable].ffill(limit=5).pct_change(fill_method=None).dropna(how="any").tail(body.lookback_days)
    if len(rets) < 60:
        raise HTTPException(status_code=409, detail=f"Only {len(rets)} overlapping days of returns; need 60")

    rf = float(service.get_settings(session)["risk_free_rate"])
    current = None
    in_both = [sym for sym in usable if sym in held]
    if in_both:
        last = {sym: float(adj[sym].dropna().iloc[-1]) for sym in in_both}
        current = {sym: held[sym].quantity * last[sym] for sym in in_both}
        if len(in_both) < len(usable):
            warnings.append("CURRENT compares only the stocks you hold among these")
    result = optimizer.optimise(rets.to_numpy(), usable, rf, body.max_weight, current)
    names = {i.symbol: i.name for i in session.scalars(select(Instrument).where(Instrument.symbol.in_(usable)))}
    for a in result["assets"]:
        a["name"] = names.get(a["symbol"], "")
        a["held"] = a["symbol"] in held
    if result["max_weight"] > body.max_weight:
        warnings.append(f"Cap raised to {result['max_weight']:.0%}: {len(usable)} stocks cannot be fully "
                        f"invested at {body.max_weight:.0%} each")
    result.update({"symbols": usable, "observations": len(rets),
                   "from": rets.index.min().isoformat(), "to": rets.index.max().isoformat(),
                   "risk_free_rate": rf, "warnings": warnings})
    return _clean(result)


def _clean(obj):
    if isinstance(obj, dict):
        return {k: _clean(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_clean(v) for v in obj]
    if isinstance(obj, float | np.floating):
        v = float(obj)
        return v if np.isfinite(v) else None
    return obj
