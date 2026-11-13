export type Benchmark = "^NSEI" | "^BSESN";

export interface Settings {
  benchmark: Benchmark;
  confidence: number;
  horizon_days: number;
  lookback_days: number;
  risk_free_rate: number;
}

export interface Holding {
  symbol: string;
  quantity: number;
  avg_cost: number;
  last: number | null;
  value: number | null;
  weight: number | null;
  unrealized_pnl: number | null;
  realized_pnl: number;
  dividends: number;
  beta: number | null;
  component_var: number | null;
}

export interface Metrics {
  beta: number | null;
  jensens_alpha_annualized: number | null;
  sharpe: number | null;
  sortino: number | null;
  max_drawdown: number | null;
  volatility_annualized: number | null;
  var: number | null;
  var_pct: number | null;
  var_z: number | null;
}

export interface Portfolio {
  as_of: string | null;
  params: Settings;
  portfolio_value: number | null;
  net_delta: number | null;
  realized_pnl: number | null;
  unrealized_pnl: number | null;
  dividends: number | null;
  metrics: Metrics | null;
  covariance: { symbols: string[]; annualized: (number | null)[][] } | null;
  observations: number;
  holdings: Holding[];
  warnings: string[];
}

export interface Trade {
  id: number;
  symbol: string;
  side: "BUY" | "SELL";
  quantity: number;
  price: number;
  traded_at: string;
  broker: string;
}

export interface CorporateAction {
  id: number;
  symbol: string;
  ex_date: string;
  kind: "split" | "bonus" | "dividend";
  value: number;
  source: string;
}

export interface ImportResult {
  imported: number;
  duplicates: number;
  skipped: string[];
}
