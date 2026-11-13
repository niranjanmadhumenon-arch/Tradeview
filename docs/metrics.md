# Metric definitions

All metrics are computed locally in `engine/app/quant/metrics.py` from daily
simple returns of dividend- and split-adjusted closes. Tests in
`engine/tests/test_metrics.py` check each formula against hand-worked values.

| Symbol | Meaning |
| --- | --- |
| `r_p`, `r_b` | daily portfolio and benchmark returns |
| `r_f` | daily risk-free rate = annual rate / 252 (default 6.5%) |
| `w` | current portfolio weights by market value |
| `S` | sample covariance matrix of daily asset returns (ddof = 1) |
| `V` | portfolio market value |

**Portfolio returns.** `r_p = sum_i w_i * r_i`, using today's weights across the
whole lookback window (default 252 trading days). This answers "how risky is
the portfolio I hold now", which is what parametric VaR needs. It is not the
historical performance of the account.

| Metric | Formula |
| --- | --- |
| Beta | `cov(r_p, r_b) / var(r_b)` |
| Jensen's alpha (annualized) | `[(mean(r_p) - r_f) - beta * (mean(r_b) - r_f)] * 252` |
| Sharpe ratio | `mean(r_p - r_f) / stdev(r_p - r_f) * sqrt(252)` |
| Sortino ratio | `mean(r_p - r_f) / sqrt(mean(min(r_p - r_f, 0)^2)) * sqrt(252)` |
| Maximum drawdown | `min_t (W_t / max_{s<=t} W_s - 1)`, `W` = cumulative wealth starting at 1 |
| Parametric VaR | `V * z * sqrt(w' S w) * sqrt(h)`, `z = norm.ppf(confidence)`, `h` = horizon in days |
| Component VaR | `V * z * sqrt(h) * w_i * (S w)_i / sqrt(w' S w)`; sums to total VaR |

VaR uses the zero-mean (RiskMetrics) convention: expected return is ignored
over short horizons.

## Positions and corporate actions

Positions replay trades and corporate actions in date order
(`engine/app/ledger/positions.py`):

- Cost basis is FIFO.
- A split or bonus with multiplier `k` turns each open lot `(q, c)` into
  `(q*k, c/k)`. A 1:1 bonus and a 2-for-1 split are both `k = 2`.
- A dividend adds `quantity held before the ex-date * cash per share` to income.
- Splits and dividends come from Yahoo Finance. Bonus issues Yahoo has missed
  can be added by hand through `POST /api/corporate-actions`.
