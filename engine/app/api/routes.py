"""REST surface. Strictly read-only with respect to markets: the only writes
are to the local ledger database (imports, manual corporate actions, settings)."""
from __future__ import annotations

import asyncio
import csv
import io
import json
import re
import uuid
from datetime import datetime

from datetime import date
from typing import Literal

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, Response, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import config
from app.ai import memo as memo_ai
from app.ai.gemini import InsightError
from app.db.models import CorporateAction, Instrument, Memo, Trade
from app.ledger import upstox
from app.market import search as market_search
from app.quant import service


def get_session(request: Request):
    with request.app.state.sessionmaker() as session:
        yield session


def require_token(request: Request) -> None:
    token = request.app.state.token
    if token and request.headers.get("x-qt-token") != token:
        raise HTTPException(status_code=401, detail="Invalid or missing engine token")


def _poke(request: Request) -> None:
    """Tell the live hub the ledger changed so clients get a fresh snapshot."""
    hub = request.app.state.hub
    if hub is not None:
        hub.poke()


router = APIRouter(prefix="/api", dependencies=[Depends(require_token)])


class SettingsIn(BaseModel):
    benchmark: str | None = None
    benchmark_name: str | None = None
    cov_horizon_days: int | None = None
    confidence: float | None = None
    horizon_days: int | None = None
    lookback_days: int | None = None
    risk_free_rate: float | None = None


class ActionIn(BaseModel):
    symbol: str
    ex_date: date
    kind: Literal["split", "bonus", "dividend"]
    value: float = Field(gt=0, description="Share multiplier for split/bonus; cash per share for dividend")


class TradeIn(BaseModel):
    """A trade the user made elsewhere and is recording here. Bookkeeping only:
    nothing in this engine can send it, or anything else, to a broker."""
    symbol: str = Field(min_length=1, max_length=40)
    side: Literal["BUY", "SELL"]
    quantity: float = Field(gt=0)
    price: float = Field(gt=0)
    traded_at: datetime
    name: str | None = Field(default=None, max_length=120)


_LEDGER_SYMBOL = re.compile(r"^[A-Z0-9&_-]{1,30}\.(NS|BO)$")


def _ledger_symbol(raw: str) -> str:
    symbol = raw.strip().upper()
    if "." not in symbol:
        symbol += ".NS"
    if not _LEDGER_SYMBOL.match(symbol):
        raise HTTPException(status_code=400,
                            detail="Symbol must be an NSE or BSE ticker, e.g. RELIANCE or RELIANCE.BO")
    return symbol


def _trade_json(t: Trade, names: dict[str, str]) -> dict:
    return {"id": t.id, "symbol": t.symbol, "name": names.get(t.symbol, ""), "side": t.side,
            "quantity": t.quantity, "price": t.price, "traded_at": t.traded_at.isoformat(),
            "broker": t.broker}


def _names(session: Session) -> dict[str, str]:
    return {i.symbol: i.name or "" for i in session.scalars(select(Instrument))}


def _remember_instrument(session: Session, symbol: str, name: str | None) -> None:
    known = session.get(Instrument, symbol)
    if known is None:
        scrip, _, suffix = symbol.rpartition(".")
        session.add(Instrument(symbol=symbol, name=(name or "").strip(),
                               exchange="BSE" if suffix == "BO" else "NSE", scrip_code=scrip))
        session.flush()
    elif name and not known.name:
        known.name = name.strip()


class UpstoxTokenIn(BaseModel):
    token: str = Field(min_length=20, max_length=4096)


def _upstox_state(request: Request) -> dict:
    store, hub = request.app.state.token_store, request.app.state.hub
    return {
        "configured": store.get() is not None,
        "source": store.source(),  # environment | keychain | None; the token itself is never returned
        "feed": hub.status if hub else {"source": "none", "state": "off", "detail": "Live feed is off"},
    }


async def _restart_feed(request: Request) -> None:
    app = request.app
    feed = await asyncio.to_thread(app.state.feed_factory, app.state.token_store)
    if app.state.hub is not None and feed is not None:
        await app.state.hub.set_feed(feed)


@router.get("/upstox")
async def upstox_status(request: Request):
    return await asyncio.to_thread(_upstox_state, request)


@router.put("/upstox/token")
async def save_upstox_token(body: UpstoxTokenIn, request: Request):
    """Saves an Upstox Analytics Token to the system credential store and
    switches the live feed to Upstox."""
    token = body.token.strip()
    if any(c.isspace() for c in token):
        raise HTTPException(status_code=400, detail="That does not look like a token (it contains spaces)")
    try:
        await asyncio.to_thread(request.app.state.token_store.set, token)
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    await _restart_feed(request)
    return await asyncio.to_thread(_upstox_state, request)


@router.delete("/upstox/token")
async def remove_upstox_token(request: Request):
    await asyncio.to_thread(request.app.state.token_store.clear)
    await _restart_feed(request)
    return await asyncio.to_thread(_upstox_state, request)


@router.post("/ledger/import")
async def import_ledger(request: Request, file: UploadFile = File(...),
                        session: Session = Depends(get_session)):
    try:
        parsed = upstox.parse(await file.read())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    existing = {t.trade_id: t for t in session.scalars(select(Trade))}
    imported = duplicates = updated = 0
    for t in parsed.trades:
        known = existing.get(t.trade_id)
        if known is not None:
            # Rows from this app's own export carry their ledger id: apply edits made in the file.
            new = (t.symbol, t.side, t.quantity, t.price, t.traded_at)
            old = (known.symbol, known.side, known.quantity, known.price, known.traded_at)
            if t.from_export and new != old:
                known.symbol, known.side, known.quantity, known.price, known.traded_at = new
                _remember_instrument(session, t.symbol, t.name)
                updated += 1
            else:
                duplicates += 1
            continue
        row = Trade(broker="manual" if t.trade_id.startswith("m:") else upstox.BROKER,
                    trade_id=t.trade_id, symbol=t.symbol, side=t.side,
                    quantity=t.quantity, price=t.price, traded_at=t.traded_at)
        session.add(row)
        existing[t.trade_id] = row
        _remember_instrument(session, t.symbol, t.name)
        imported += 1
    session.commit()
    _poke(request)
    return {"imported": imported, "duplicates": duplicates, "updated": updated,
            "skipped": parsed.skipped}


@router.get("/ledger/trades")
def list_trades(session: Session = Depends(get_session)):
    names = _names(session)
    rows = session.scalars(select(Trade).order_by(Trade.traded_at.desc(), Trade.id.desc())).all()
    return [_trade_json(t, names) for t in rows]


@router.post("/ledger/trades", status_code=201)
def record_trade(body: TradeIn, request: Request, session: Session = Depends(get_session)):
    """Records a trade that already happened at a broker. Local bookkeeping only."""
    symbol = _ledger_symbol(body.symbol)
    trade = Trade(broker="manual", trade_id=f"m:{uuid.uuid4().hex}", symbol=symbol, side=body.side,
                  quantity=body.quantity, price=body.price,
                  traded_at=body.traded_at.replace(tzinfo=None))
    session.add(trade)
    _remember_instrument(session, symbol, body.name)
    session.commit()
    _poke(request)
    return _trade_json(trade, _names(session))


@router.put("/ledger/trades/{trade_id}")
def amend_trade(trade_id: int, body: TradeIn, request: Request,
                session: Session = Depends(get_session)):
    """Corrects a ledger entry. The row keeps its identity, so a later import does not duplicate it."""
    trade = session.get(Trade, trade_id)
    if trade is None:
        raise HTTPException(status_code=404, detail="No such trade in the ledger")
    trade.symbol = _ledger_symbol(body.symbol)
    trade.side, trade.quantity, trade.price = body.side, body.quantity, body.price
    trade.traded_at = body.traded_at.replace(tzinfo=None)
    _remember_instrument(session, trade.symbol, body.name)
    session.commit()
    _poke(request)
    return _trade_json(trade, _names(session))


@router.delete("/ledger/trades/{trade_id}")
def remove_trade(trade_id: int, request: Request, session: Session = Depends(get_session)):
    trade = session.get(Trade, trade_id)
    if trade is None:
        raise HTTPException(status_code=404, detail="No such trade in the ledger")
    session.delete(trade)
    session.commit()
    _poke(request)
    return {"deleted": trade_id}


@router.get("/ledger/export")
def export_ledger(session: Session = Depends(get_session)):
    """The whole ledger as a CSV that IMPORT CSV reads back."""
    trades = session.scalars(select(Trade).order_by(Trade.traded_at, Trade.id)).all()
    out = io.StringIO()
    writer = csv.DictWriter(out, fieldnames=upstox.EXPORT_COLUMNS, lineterminator="\n")
    writer.writeheader()
    writer.writerows(upstox.export_rows(trades, _names(session)))
    name = f"quant-terminal-ledger-{datetime.now():%Y-%m-%d}.csv"
    return Response(content=out.getvalue(), media_type="text/csv",
                    headers={"Content-Disposition": f'attachment; filename="{name}"'})


@router.get("/benchmarks")
def list_benchmarks(q: str = Query("", max_length=64), limit: int = Query(40, ge=1, le=60)):
    """Benchmark choices: built-in indices and ETFs, plus a live lookup for anything else."""
    return market_search.search_benchmarks(q, limit)


@router.get("/portfolio/holdings")
def holdings(session: Session = Depends(get_session)):
    """Holdings from cached prices only: fast, and never touches the network."""
    data = service.compute(session, refresh=False)
    keys = ("as_of", "portfolio_value", "net_delta", "realized_pnl", "unrealized_pnl",
            "dividends", "holdings", "warnings")
    return {k: data[k] for k in keys}


@router.get("/search")
def search_stocks(q: str = Query("", max_length=64), limit: int = Query(10, ge=1, le=25),
                  session: Session = Depends(get_session)):
    """Find a stock by company name or ticker: ledger instruments plus NSE/BSE listings."""
    return market_search.search(session, q, limit)


@router.get("/metrics")
def metrics(
    benchmark: str | None = None,
    cov_horizon_days: int | None = None,
    confidence: float | None = None,
    horizon_days: int | None = None,
    lookback_days: int | None = None,
    risk_free_rate: float | None = None,
    refresh: bool = Query(True, description="Refresh prices from Yahoo (at most once a day)"),
    session: Session = Depends(get_session),
):
    overrides = {"benchmark": benchmark, "cov_horizon_days": cov_horizon_days, "confidence": confidence, "horizon_days": horizon_days,
                 "lookback_days": lookback_days, "risk_free_rate": risk_free_rate}
    try:
        return service.compute(session, overrides, refresh=refresh)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/settings")
def read_settings(session: Session = Depends(get_session)):
    return service.get_settings(session)


@router.put("/settings")
def write_settings(body: SettingsIn, session: Session = Depends(get_session)):
    try:
        return service.save_settings(session, body.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/market/refresh")
def refresh_market(session: Session = Depends(get_session)):
    settings = service.get_settings(session)
    return {"warnings": service.refresh_market(session, settings["benchmark"], force=True,
                                               lookback_days=int(settings["lookback_days"]))}


@router.get("/corporate-actions")
def list_actions(symbol: str | None = None, session: Session = Depends(get_session)):
    query = select(CorporateAction).order_by(CorporateAction.ex_date.desc())
    if symbol:
        query = query.where(CorporateAction.symbol == symbol)
    return [
        {"id": a.id, "symbol": a.symbol, "ex_date": a.ex_date.isoformat(), "kind": a.kind,
         "value": a.value, "source": a.source}
        for a in session.scalars(query)
    ]


@router.post("/corporate-actions", status_code=201)
def add_action(body: ActionIn, request: Request, session: Session = Depends(get_session)):
    """Manual entry, mainly for bonus issues Yahoo has not recorded."""
    family = ("split", "bonus") if body.kind in ("split", "bonus") else ("dividend",)
    clash = session.scalar(
        select(CorporateAction).where(
            CorporateAction.symbol == body.symbol,
            CorporateAction.ex_date == body.ex_date,
            CorporateAction.kind.in_(family),
        )
    )
    if clash:
        raise HTTPException(
            status_code=409,
            detail=f"A {clash.kind} for {body.symbol} on {body.ex_date} already exists "
                   f"(source: {clash.source}); adding another would double-count it",
        )
    action = CorporateAction(symbol=body.symbol, ex_date=body.ex_date, kind=body.kind,
                             value=body.value, source="manual")
    session.add(action)
    session.commit()
    _poke(request)
    return {"id": action.id}


# ---------------------------------------------------------------- AI insight

class ApiKeyIn(BaseModel):
    key: str = Field(min_length=20, max_length=512)


def _insight_state(request: Request) -> dict:
    store = request.app.state.gemini_store
    return {"configured": store.get() is not None, "source": store.source(),
            "model": config.gemini_model()}


def _memo_json(m: Memo) -> dict:
    return {"id": m.id, "created_at": m.created_at.isoformat(), "model": m.model, "text": m.text,
            "payload": json.loads(m.payload), "unverified_numbers": json.loads(m.unverified)}


@router.get("/insight")
def insight_status(request: Request):
    return _insight_state(request)


@router.put("/insight/key")
def save_insight_key(body: ApiKeyIn, request: Request):
    key = body.key.strip()
    if any(c.isspace() for c in key):
        raise HTTPException(status_code=400, detail="That does not look like an API key (it contains spaces)")
    try:
        request.app.state.gemini_store.set(key)
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return _insight_state(request)


@router.delete("/insight/key")
def remove_insight_key(request: Request):
    request.app.state.gemini_store.clear()
    return _insight_state(request)


@router.get("/insight/preview")
def insight_preview(session: Session = Depends(get_session)):
    """Exactly what would be sent to the model, so the user can inspect it first."""
    data = service.compute(session, refresh=False)
    if not data["metrics"]:
        raise HTTPException(status_code=409, detail="No risk metrics yet. Import trades and refresh prices first.")
    return memo_ai.build_payload(data)


@router.post("/insight/memo")
def create_memo(request: Request, session: Session = Depends(get_session)):
    """Sends the locally computed risk figures to Gemini and stores the memo it writes."""
    api_key = request.app.state.gemini_store.get()
    if not api_key:
        raise HTTPException(status_code=409, detail="No Gemini API key saved.")
    data = service.compute(session, refresh=False)
    if not data["metrics"]:
        raise HTTPException(status_code=409, detail="No risk metrics yet. Import trades and refresh prices first.")
    payload = memo_ai.build_payload(data)
    model = config.gemini_model()
    try:
        text = request.app.state.memo_generator(api_key, model, memo_ai.SYSTEM_INSTRUCTION, payload)
    except InsightError as exc:
        raise HTTPException(status_code=exc.status, detail=str(exc)) from exc
    row = Memo(created_at=datetime.now(), model=model, payload=json.dumps(payload), text=text,
               unverified=json.dumps(memo_ai.unverified_numbers(text, payload)))
    session.add(row)
    session.commit()
    return _memo_json(row)


@router.get("/insight/memos")
def list_memos(limit: int = Query(20, ge=1, le=100), session: Session = Depends(get_session)):
    rows = session.scalars(select(Memo).order_by(Memo.id.desc()).limit(limit)).all()
    return [_memo_json(m) for m in rows]
