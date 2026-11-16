"""Pure risk and performance maths. No I/O: inputs are pandas/numpy objects of
daily simple returns. Formulas are documented in docs/metrics.md."""
from __future__ import annotations

import math

import numpy as np
import pandas as pd
from scipy.stats import norm

TRADING_DAYS = 252


def portfolio_returns(asset_returns: pd.DataFrame, weights: pd.Series) -> pd.Series:
    w = weights.reindex(asset_returns.columns).fillna(0.0)
    return asset_returns.mul(w, axis=1).sum(axis=1)


def beta(r: pd.Series, benchmark: pd.Series) -> float:
    c = np.cov(np.asarray(r, dtype=float), np.asarray(benchmark, dtype=float), ddof=1)
    return float(c[0, 1] / c[1, 1]) if c[1, 1] > 0 else math.nan


def jensens_alpha_annualized(r: pd.Series, benchmark: pd.Series, rf_annual: float) -> float:
    rf = rf_annual / TRADING_DAYS
    b = beta(r, benchmark)
    daily = (float(np.mean(r)) - rf) - b * (float(np.mean(benchmark)) - rf)
    return daily * TRADING_DAYS


def sharpe_ratio(r: pd.Series, rf_annual: float) -> float:
    excess = np.asarray(r, dtype=float) - rf_annual / TRADING_DAYS
    sd = excess.std(ddof=1)
    return float(excess.mean() / sd * math.sqrt(TRADING_DAYS)) if sd > 0 else math.nan


def sortino_ratio(r: pd.Series, rf_annual: float) -> float:
    excess = np.asarray(r, dtype=float) - rf_annual / TRADING_DAYS
    downside = math.sqrt(float(np.mean(np.minimum(excess, 0.0) ** 2)))
    return float(excess.mean() / downside * math.sqrt(TRADING_DAYS)) if downside > 0 else math.nan


def max_drawdown(r: pd.Series) -> float:
    """Largest peak-to-trough fall of cumulative wealth, as a negative fraction."""
    wealth = np.concatenate([[1.0], np.cumprod(1.0 + np.asarray(r, dtype=float))])
    peaks = np.maximum.accumulate(wealth)
    return float((wealth / peaks - 1.0).min())


def annualized_volatility(r: pd.Series) -> float:
    return float(np.asarray(r, dtype=float).std(ddof=1) * math.sqrt(TRADING_DAYS))


def parametric_var(
    weights: np.ndarray,
    cov_daily: np.ndarray,
    portfolio_value: float,
    confidence: float,
    horizon_days: int = 1,
) -> dict:
    """Variance-covariance VaR with zero mean (RiskMetrics convention):
    VaR = V * z * sqrt(w' S w) * sqrt(h). Component VaRs sum to the total."""
    w = np.asarray(weights, dtype=float)
    cov = np.asarray(cov_daily, dtype=float)
    sigma = math.sqrt(float(w @ cov @ w))
    z = float(norm.ppf(confidence))
    scale = portfolio_value * z * math.sqrt(horizon_days)
    component = scale * w * (cov @ w) / sigma if sigma > 0 else np.zeros_like(w)
    return {"var": scale * sigma, "sigma_daily": sigma, "z": z, "component": component}


def horizon_returns(returns: np.ndarray, days: int) -> np.ndarray:
    """Compounded returns over every overlapping window of `days` rows.
    Input is (T,) or (T, N) daily simple returns; output has T - days + 1 rows."""
    r = np.asarray(returns, dtype=float)
    if days <= 1:
        return r
    if len(r) < days:
        return r[:0]
    growth = np.cumsum(np.log1p(r), axis=0)
    growth = np.concatenate([np.zeros_like(growth[:1]), growth], axis=0)
    return np.expm1(growth[days:] - growth[:-days])


def correlation(cov: np.ndarray) -> np.ndarray:
    sd = np.sqrt(np.diag(cov))
    with np.errstate(divide="ignore", invalid="ignore"):
        return cov / np.outer(sd, sd)
