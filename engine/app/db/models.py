from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import Date, DateTime, Float, String, UniqueConstraint, create_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker


class Base(DeclarativeBase):
    pass


class Instrument(Base):
    __tablename__ = "instruments"
    symbol: Mapped[str] = mapped_column(String, primary_key=True)  # Yahoo symbol, e.g. RELIANCE.NS
    name: Mapped[str] = mapped_column(String, default="")
    exchange: Mapped[str] = mapped_column(String, default="")
    scrip_code: Mapped[str] = mapped_column(String, default="")


class Trade(Base):
    __tablename__ = "trades"
    __table_args__ = (UniqueConstraint("broker", "trade_id", name="uq_trade"),)
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    broker: Mapped[str] = mapped_column(String)
    trade_id: Mapped[str] = mapped_column(String)
    symbol: Mapped[str] = mapped_column(String, index=True)
    side: Mapped[str] = mapped_column(String)  # BUY | SELL
    quantity: Mapped[float] = mapped_column(Float)
    price: Mapped[float] = mapped_column(Float)
    traded_at: Mapped[datetime] = mapped_column(DateTime, index=True)


class CorporateAction(Base):
    """kind = split | bonus (value is the share multiplier, e.g. 2.0 for a
    2-for-1 split or a 1:1 bonus) or dividend (value is cash per share)."""

    __tablename__ = "corporate_actions"
    __table_args__ = (UniqueConstraint("symbol", "ex_date", "kind", name="uq_action"),)
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    symbol: Mapped[str] = mapped_column(String, index=True)
    ex_date: Mapped[date] = mapped_column(Date)
    kind: Mapped[str] = mapped_column(String)
    value: Mapped[float] = mapped_column(Float)
    source: Mapped[str] = mapped_column(String, default="manual")


class PriceBar(Base):
    __tablename__ = "price_history"
    symbol: Mapped[str] = mapped_column(String, primary_key=True)
    date: Mapped[date] = mapped_column(Date, primary_key=True)
    close: Mapped[float] = mapped_column(Float)
    adj_close: Mapped[float] = mapped_column(Float)


class Setting(Base):
    __tablename__ = "settings"
    key: Mapped[str] = mapped_column(String, primary_key=True)
    value: Mapped[str] = mapped_column(String)


def make_sessionmaker(url: str) -> sessionmaker:
    engine = create_engine(url, connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    return sessionmaker(engine, expire_on_commit=False)
