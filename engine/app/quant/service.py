"""Glue between the database and the pure maths: loads the ledger, refreshes
prices, and assembles the JSON payload the UI consumes."""
from __future__ import annotations

import math
from datetime import date, timedelta

import numpy as np
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import ALLOWED_BENCHMARKS, DEFAULT_SETTINGS
from app.db.models import CorporateAction, Setting, Trade
from app.ledger.positions import EPS, Position, build_positions
from app.market import history
from app.quant import metrics as qm

MIN_OBSERVATIONS = 30


def _f(x) -> float | None:
    x = float(x)
    return x if math.isfinite(x) else None


def get_settings(session: Session) -> dict:
    out = dict(DEFAULT_SETTINGS)
    for key, default in DEFAULT_SETTINGS.items():
        row = session.get(Setting, key)
        if row is not None:
            out[key] = type(default)(row.value)
    return out


def validate_settings(values: dict) -> dict:
    clean: dict = {}
    for key, value in values.items():
        if key not in DEFAULT_SETTINGS or value is None:
            continue
        value = type(DEFAULT_SETTINGS[key])(value)
        if key == "benchmark" and value not in ALLOWED_BENCHMARKS:
            raise ValueError(f"benchmark must be one of {', '.join(ALLOWED_BENCHMARKS)}")
        if key == "confidence" and not 0.5 < value < 1:
            raise ValueError("confidence must be between 0.5 and 1 (e.g. 0.95 or 0.99)")
        if key == "horizon_days" and value < 1:
            raise ValueError("horizon_days must be at least 1")
        if key == "lookback_days" and value < MIN_OBSERVATIONS:
            raise ValueError(f"lookback_days must be at least {MIN_OBSERVATIONS}")
        if key == "risk_free_rate" and not 0 <= value < 1:
            raise ValueError("risk_free_rate is an annual fraction, e.g. 0.065")
        clean[key] = value
    return clean


def save_settings(session: Session, values: dict) -> dict:
    for key, value in validate_settings(values).items():
        row = session.get(Setting, key)
        if row:
            row.value = str(value)
        else:
            session.add(Setting(key=key, value=str(value)))
    session.commit()
    return get_settings(session)


def load_positions(session: Session) -> dict[str, Position]:
    trades = session.scalars(select(Trade)).all()
    actions = session.scalars(select(CorporateAction)).all()
    return build_positions(trades, actions)


def history_start(session: Session) -> date:
    first = session.scalar(select(Trade.traded_at).order_by(Trade.traded_at).limit(1))
    floor = date.today() - timedelta(days=3 * 365)
    return min(first.date() - timedelta(days=7), floor) if first else floor


def refresh_market(session: Session, benchmark: str, fetcher=None, force: bool = False) -> list[str]:
    """Refreshes every traded symbol plus the benchmark. Failures become warnings
    so the terminal keeps working offline from the cache."""
    warnings: list[str] = []
    start = history_start(session)
    symbols = list(session.scalars(select(Trade.symbol).distinct()))
    for symbol, is_index in [(s, False) for s in symbols] + [(benchmark, True)]:
        try:
            history.refresh_symbol(session, symbol, start, fetcher=fetcher,
                                   with_actions=not is_index, force=force)
        except Exception as exc:
            session.rollback()
            warnings.append(f"Could not refresh {symbol}: {exc}")
    return warnings


def compute(session: Session, overrides: dict | None = None, *, refresh: bool = True,
            fetcher=None) -> dict:
    params = {**get_settings(session), **validate_settings(overrides or {})}
    benchmark = params["benchmark"]
    warnings = refresh_market(session, benchmark, fetcher) if refresh else []

    positions = load_positions(session)
    for p in positions.values():
        warnings.extend(p.warnings)
    held = sorted(s for s, p in positions.items() if p.quantity > EPS)
    close, adj = history.load_prices(session, held + [benchmark])

    priced = [s for s in held if s in close.columns and close[s].notna().any()]
    for s in held:
        if s not in priced:
            warnings.append(f"No price history for {s}; excluded from value and risk")

    last = {s: float(close[s].dropna().iloc[-1]) for s in priced}
    value = {s: positions[s].quantity * last[s] for s in priced}
    total = sum(value.values())
    weight = {s: value[s] / total for s in priced} if total > 0 else {}

    result = {
        "as_of": close.index.max().isoformat() if len(close) else None,
        "params": params,
        "portfolio_value": _f(total),
        "net_delta": _f(total),  # cash equity: delta 1, so exposure equals market value
        "realized_pnl": _f(sum(p.realized_pnl for p in positions.values())),
        "dividends": _f(sum(p.dividends for p in positions.values())),
        "unrealized_pnl": _f(sum(value[s] - positions[s].cost_value for s in priced)),
        "metrics": None,
        "covariance": None,
        "observations": 0,
        "warnings": warnings,
    }
    holdings = {
        s: {
            "symbol": s,
            "quantity": _f(positions[s].quantity),
            "avg_cost": _f(positions[s].avg_cost),
            "last": _f(last[s]) if s in last else None,
            "value": _f(value[s]) if s in value else None,
            "weight": _f(weight[s]) if s in weight else None,
            "unrealized_pnl": _f(value[s] - positions[s].cost_value) if s in value else None,
            "realized_pnl": _f(positions[s].realized_pnl),
            "dividends": _f(positions[s].dividends),
            "beta": None,
            "component_var": None,
        }
        for s in held
    }
    result["holdings"] = list(holdings.values())
    if not priced:
        return result

    has_bench = benchmark in adj.columns and adj[benchmark].notna().any()
    if not has_bench:
        warnings.append(f"No history for benchmark {benchmark}; beta and alpha unavailable")
    cols = priced + ([benchmark] if has_bench else [])
    rets = adj[cols].pct_change(fill_method=None).dropna(how="any").tail(int(params["lookback_days"]))
    result["observations"] = len(rets)
    if len(rets) < MIN_OBSERVATIONS:
        warnings.append(
            f"Only {len(rets)} overlapping daily returns; need {MIN_OBSERVATIONS} for risk metrics"
        )
        return result

    w = np.array([weight[s] for s in priced])
    asset_rets = rets[priced]
    rp = asset_rets.to_numpy() @ w
    cov = np.atleast_2d(np.cov(asset_rets.to_numpy(), rowvar=False, ddof=1))
    var = qm.parametric_var(w, cov, total, params["confidence"], int(params["horizon_days"]))
    rf = params["risk_free_rate"]

    m = {
        "beta": None,
        "jensens_alpha_annualized": None,
        "sharpe": _f(qm.sharpe_ratio(rp, rf)),
        "sortino": _f(qm.sortino_ratio(rp, rf)),
        "max_drawdown": _f(qm.max_drawdown(rp)),
        "volatility_annualized": _f(qm.annualized_volatility(rp)),
        "var": _f(var["var"]),
        "var_pct": _f(var["var"] / total),
        "var_z": _f(var["z"]),
    }
    if has_bench:
        rb = rets[benchmark].to_numpy()
        m["beta"] = _f(qm.beta(rp, rb))
        m["jensens_alpha_annualized"] = _f(qm.jensens_alpha_annualized(rp, rb, rf))
        for s in priced:
            holdings[s]["beta"] = _f(qm.beta(asset_rets[s].to_numpy(), rb))
    for s, c in zip(priced, var["component"]):
        holdings[s]["component_var"] = _f(c)

    result["metrics"] = m
    result["covariance"] = {
        "symbols": priced,
        "annualized": [[_f(v) for v in row] for row in cov * qm.TRADING_DAYS],
    }
    return result
