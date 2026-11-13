"""Daily price history and corporate actions from Yahoo Finance, cached in SQLite.

Adjusted closes change retroactively whenever a new dividend or split lands,
so a refresh replaces the whole window for a symbol instead of appending."""
from __future__ import annotations

from datetime import date
from typing import Callable

import pandas as pd
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.db.models import CorporateAction, PriceBar, Setting

Fetcher = Callable[[str, date], pd.DataFrame]


def fetch(symbol: str, start: date) -> pd.DataFrame:
    """Returns a frame indexed by date with columns close, adj_close, dividend, split."""
    import yfinance as yf

    raw = yf.Ticker(symbol).history(start=start.isoformat(), auto_adjust=False, actions=True)
    if raw.empty:
        return pd.DataFrame(columns=["close", "adj_close", "dividend", "split"])
    idx = pd.to_datetime(raw.index)
    if idx.tz is not None:
        idx = idx.tz_localize(None)
    out = pd.DataFrame(index=idx.date)
    out["close"] = raw["Close"].to_numpy()
    out["adj_close"] = raw["Adj Close"].to_numpy() if "Adj Close" in raw else raw["Close"].to_numpy()
    out["dividend"] = raw["Dividends"].to_numpy() if "Dividends" in raw else 0.0
    out["split"] = raw["Stock Splits"].to_numpy() if "Stock Splits" in raw else 0.0
    return out.dropna(subset=["close"])


def refresh_symbol(
    session: Session,
    symbol: str,
    start: date,
    *,
    fetcher: Fetcher | None = None,
    with_actions: bool = True,
    force: bool = False,
) -> int:
    """Refreshes one symbol at most once per day. Returns bars stored (0 if skipped)."""
    key = f"refreshed:{symbol}"
    stamp = f"{date.today().isoformat()}|{start.isoformat()}"
    marker = session.get(Setting, key)
    if marker and marker.value == stamp and not force:
        return 0

    frame = (fetcher or fetch)(symbol, start)
    if frame.empty:
        raise ValueError(f"No price data returned for {symbol}")

    session.execute(delete(PriceBar).where(PriceBar.symbol == symbol))
    session.add_all(
        PriceBar(symbol=symbol, date=d, close=float(r.close), adj_close=float(r.adj_close))
        for d, r in frame.iterrows()
    )
    if with_actions:
        session.execute(
            delete(CorporateAction).where(
                CorporateAction.symbol == symbol, CorporateAction.source == "yfinance"
            )
        )
        manual = {
            (a.ex_date, "factor" if a.kind in ("split", "bonus") else a.kind)
            for a in session.scalars(select(CorporateAction).where(CorporateAction.symbol == symbol))
        }
        for d, r in frame.iterrows():
            if r.split and r.split > 0 and (d, "factor") not in manual:
                session.add(CorporateAction(symbol=symbol, ex_date=d, kind="split",
                                            value=float(r.split), source="yfinance"))
            if r.dividend and r.dividend > 0 and (d, "dividend") not in manual:
                session.add(CorporateAction(symbol=symbol, ex_date=d, kind="dividend",
                                            value=float(r.dividend), source="yfinance"))
    if marker:
        marker.value = stamp
    else:
        session.add(Setting(key=key, value=stamp))
    session.commit()
    return len(frame)


def load_prices(session: Session, symbols: list[str]) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Returns (close, adj_close) frames: one column per symbol, indexed by date."""
    rows = session.execute(
        select(PriceBar.symbol, PriceBar.date, PriceBar.close, PriceBar.adj_close).where(
            PriceBar.symbol.in_(symbols)
        )
    ).all()
    if not rows:
        empty = pd.DataFrame()
        return empty, empty
    df = pd.DataFrame(rows, columns=["symbol", "date", "close", "adj_close"])
    close = df.pivot(index="date", columns="symbol", values="close").sort_index()
    adj = df.pivot(index="date", columns="symbol", values="adj_close").sort_index()
    return close, adj
