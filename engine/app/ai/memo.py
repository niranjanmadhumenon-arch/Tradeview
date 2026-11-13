"""AI insight layer. The model writes prose only.

What it receives: a small JSON document of risk figures the engine has already
computed and rounded. What it must not do: calculate anything. After the memo
comes back, every number in it is checked against the figures that were sent,
and any that do not match are reported so the UI can flag them."""
from __future__ import annotations

import re

BENCHMARK_NAMES = {"^NSEI": "NIFTY 50", "^BSESN": "SENSEX"}

SYSTEM_INSTRUCTION = """You are a risk strategist writing a short tactical hedging memo for the user of a \
read-only portfolio analytics terminal covering Indian equities.

Hard rules:
- Use only the figures in the JSON you are given. Quote them exactly as written.
- Do not calculate, derive, estimate, round, annualize, convert or combine numbers. If a figure you want is \
not in the JSON, say it is not available.
- Do not give position sizes, quantities, strike prices, price targets or rupee amounts for any hedge.
- Do not tell the user to place, buy or sell anything. The terminal cannot trade. Describe hedging approaches \
as considerations for the user to evaluate.
- Do not use outside market data, news or forecasts.

Write plain text with exactly these four headings on their own lines:
RISK POSTURE
KEY EXPOSURES
HEDGING CONSIDERATIONS
WHAT TO WATCH

Under 300 words. Short paragraphs or dash bullets. No markdown symbols other than dashes."""


def _r(value, digits=2):
    return None if value is None else round(float(value), digits)


def _pct(value, digits=2):
    return None if value is None else round(float(value) * 100, digits)


def build_payload(data: dict) -> dict:
    """Turns the engine's metrics payload into the only thing the model sees.
    Percentages are converted and rounded here, locally, so the model has
    nothing left to compute."""
    m, params = data["metrics"], data["params"]
    total_var = m["var"] or 0.0
    value = data["portfolio_value"] or 0.0
    holdings = []
    for h in data["holdings"]:
        if h["weight"] is None:
            continue
        cost = (h["value"] or 0.0) - (h["unrealized_pnl"] or 0.0)
        holdings.append({
            "symbol": re.sub(r"\.(NS|BO)$", "", h["symbol"]),
            "weight_pct": _pct(h["weight"]),
            "beta": _r(h["beta"]),
            "share_of_var_pct": _pct(h["component_var"] / total_var) if total_var and h["component_var"] is not None else None,
            "unrealized_return_pct": _pct(h["unrealized_pnl"] / cost) if cost > 0 and h["unrealized_pnl"] is not None else None,
        })
    holdings.sort(key=lambda h: -(h["weight_pct"] or 0))
    cost_total = value - (data["unrealized_pnl"] or 0.0)
    return {
        "as_of": data["as_of"],
        "benchmark": BENCHMARK_NAMES.get(params["benchmark"], params["benchmark"]),
        "var_confidence_pct": _r(params["confidence"] * 100, 1),
        "var_horizon_days": int(params["horizon_days"]),
        "lookback_trading_days": int(data["observations"]),
        "portfolio": {
            "net_delta_inr": _r(data["net_delta"], 0),
            "value_at_risk_inr": _r(m["var"], 0),
            "value_at_risk_pct_of_value": _pct(m["var_pct"]),
            "beta": _r(m["beta"]),
            "jensens_alpha_annualized_pct": _pct(m["jensens_alpha_annualized"]),
            "sharpe_ratio": _r(m["sharpe"]),
            "sortino_ratio": _r(m["sortino"]),
            "max_drawdown_pct": _pct(m["max_drawdown"]),
            "volatility_annualized_pct": _pct(m["volatility_annualized"]),
            "unrealized_return_pct": _pct(data["unrealized_pnl"] / cost_total) if cost_total > 0 and data["unrealized_pnl"] is not None else None,
            "holdings_count": len(holdings),
        },
        "holdings": holdings,
    }


_NUMBER = re.compile(r"(?<![A-Za-z])\d[\d,]*(?:\.\d+)?")
_ALWAYS_OK = {50.0, 100.0}  # "NIFTY 50", "100%"


def _numbers_in(obj) -> set[float]:
    found: set[float] = set()
    if isinstance(obj, bool) or obj is None:
        return found
    if isinstance(obj, (int, float)):
        value = abs(float(obj))
        found.update({value, round(value, 1), float(round(value))})
    elif isinstance(obj, str):
        for token in _NUMBER.findall(obj):
            found.add(float(token.replace(",", "")))
    elif isinstance(obj, dict):
        for v in obj.values():
            found |= _numbers_in(v)
    elif isinstance(obj, (list, tuple)):
        for v in obj:
            found |= _numbers_in(v)
    return found


def unverified_numbers(memo: str, payload: dict) -> list[str]:
    """Numbers in the memo that are not figures the engine supplied (allowing
    the same figure rounded to one or zero decimals). Small counts such as
    'two holdings' written as digits are allowed up to 10."""
    allowed = _numbers_in(payload) | _ALWAYS_OK
    flagged: list[str] = []
    for token in _NUMBER.findall(memo):
        value = float(token.replace(",", ""))
        if value <= 10 and value == int(value):
            continue
        if not any(abs(value - ok) < 1e-9 for ok in allowed) and token not in flagged:
            flagged.append(token)
    return flagged
