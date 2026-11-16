export interface Settings {
  benchmark: string;
  benchmark_name: string;
  cov_horizon_days: number;
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
  covariance: Covariance | null;
  observations: number;
  holdings: Holding[];
  warnings: string[];
}

export interface Covariance {
  symbols: string[];
  horizon_days: number;
  observations: number;
  matrix: (number | null)[][];
  annualized: (number | null)[][];
  correlation: (number | null)[][];
}

export interface BenchmarkOption {
  symbol: string;
  name: string;
  kind: "INDEX" | "ETF" | "FUND" | "STOCK";
  exchange: string;
  preset: boolean;
}

/** A trade made elsewhere, as typed into the ledger. Never sent to a broker. */
export interface TradeInput {
  symbol: string;
  side: "BUY" | "SELL";
  quantity: number;
  price: number;
  traded_at: string;
  name?: string;
}

export interface Trade {
  id: number;
  symbol: string;
  name: string;
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
  updated: number;
  skipped: string[];
}

export interface Quote {
  ltp: number;
  prev_close: number | null;
  change: number | null;
  change_pct: number | null;
  ts: number;
}

export interface FeedStatus {
  source: "upstox" | "yahoo-delayed" | "none" | string;
  state: "connecting" | "live" | "error" | "off";
  detail: string;
}

export interface LiveSnapshot {
  type: "snapshot";
  status: FeedStatus;
  quotes: Record<string, Quote>;
  portfolio: {
    held: number;
    priced: number;
    value: number;
    unrealized_pnl: number;
    day_pnl: number | null;
    holdings: Record<string, { value: number; unrealized_pnl: number; day_pnl: number | null }>;
  } | null;
}

export interface UpstoxState {
  configured: boolean;
  source: "environment" | "keychain" | "memory" | null;
  feed: FeedStatus;
}

export interface InsightState {
  configured: boolean;
  source: "environment" | "keychain" | "memory" | null;
  model: string;
}

export interface Memo {
  id: number;
  created_at: string;
  model: string;
  text: string;
  payload: Record<string, unknown>;
  unverified_numbers: string[];
}

export interface SearchResult {
  symbol: string;
  name: string;
  exchange: string;
  held: boolean;
}

export interface SearchResponse {
  query: string;
  results: SearchResult[];
  online: boolean;
}
