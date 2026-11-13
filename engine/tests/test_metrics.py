"""Golden-value tests: expected numbers are worked out by hand."""
import math

import numpy as np
import pandas as pd
import pytest

from app.quant import metrics as qm


def test_max_drawdown_hand_value():
    # wealth: 1.00 -> 1.10 -> 0.55 -> 0.66 ; worst fall is 1.10 -> 0.55 = -50%
    assert qm.max_drawdown(pd.Series([0.10, -0.50, 0.20])) == pytest.approx(-0.5)


def test_max_drawdown_counts_initial_capital_as_peak():
    assert qm.max_drawdown(pd.Series([-0.10, 0.05])) == pytest.approx(-0.10)


def test_beta_and_alpha_of_levered_benchmark():
    rb = pd.Series([0.01, -0.02, 0.015, 0.003, -0.007])
    rp = 2 * rb + 0.001  # beta 2, constant daily excess 0.001
    assert qm.beta(rp, rb) == pytest.approx(2.0)
    # with rf = 0: alpha_daily = mean(rp) - 2*mean(rb) = 0.001 ; annualized x252
    assert qm.jensens_alpha_annualized(rp, rb, 0.0) == pytest.approx(0.252)


def test_alpha_accounts_for_risk_free_rate():
    rb = pd.Series([0.01, -0.02, 0.015, 0.003, -0.007])
    rp = 2 * rb
    # alpha_daily = (mean(rp)-rf) - 2*(mean(rb)-rf) = rf ; annualized = rf_annual
    assert qm.jensens_alpha_annualized(rp, rb, 0.0504) == pytest.approx(0.0504)


def test_sharpe_hand_value():
    r = pd.Series([0.01, 0.03])  # mean 0.02, sample sd = 0.0141421356
    assert qm.sharpe_ratio(r, 0.0) == pytest.approx(0.02 / 0.0141421356 * math.sqrt(252), rel=1e-6)


def test_sortino_hand_value():
    r = pd.Series([0.02, -0.01, 0.01, -0.02])  # mean 0; use rf 0 -> ratio 0
    assert qm.sortino_ratio(r, 0.0) == pytest.approx(0.0, abs=1e-12)
    r = pd.Series([0.03, -0.01])  # mean 0.01 ; downside dev = sqrt((0 + 0.0001)/2) = 0.00707107
    assert qm.sortino_ratio(r, 0.0) == pytest.approx(0.01 / 0.0070710678 * math.sqrt(252), rel=1e-6)


def test_parametric_var_hand_value():
    # two uncorrelated assets, daily variances 0.0001 and 0.0004, equal weights
    # sigma_p = sqrt(0.25*0.0001 + 0.25*0.0004) = 0.0111803399 ; z(95%) = 1.6448536
    out = qm.parametric_var(np.array([0.5, 0.5]), np.diag([0.0001, 0.0004]), 1_000_000, 0.95)
    assert out["var"] == pytest.approx(18390.02, abs=0.5)
    assert out["component"].sum() == pytest.approx(out["var"])
    # component split follows variance contribution: 20% / 80%
    assert out["component"][0] / out["var"] == pytest.approx(0.2)


def test_var_scales_with_confidence_and_horizon():
    w, cov = np.array([1.0]), np.array([[0.0004]])  # sigma 2% a day
    v95 = qm.parametric_var(w, cov, 100_000, 0.95)["var"]
    v99 = qm.parametric_var(w, cov, 100_000, 0.99)["var"]
    v99_10d = qm.parametric_var(w, cov, 100_000, 0.99, horizon_days=10)["var"]
    assert v95 == pytest.approx(3289.71, abs=0.5)   # 100000 * 1.6448536 * 0.02
    assert v99 == pytest.approx(4652.70, abs=0.5)   # 100000 * 2.3263479 * 0.02
    assert v99_10d == pytest.approx(v99 * math.sqrt(10))
