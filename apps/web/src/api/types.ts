export interface Settings {
  benchmark: string;
  benchmark_name: string;
  cov_horizon_days: number;
  confidence: number;
  horizon_days: number;
  lookback_days: number;
  risk_free_rate: number;
  display_currency: string;
  insight_frequency: "hourly" | "daily";
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
  name?: string;
  asset_class?: AssetClass;
  currency?: string;
  fx_rate?: number | null;
  total_return?: number | null;
  total_return_pct?: number | null;
  xirr?: number | null;
}

export type AssetClass = "equity" | "etf" | "mutual_fund" | "gold" | "commodity" | "bond";

export interface Returns {
  invested: number | null;
  total_return: number | null;
  total_return_pct: number | null;
  xirr: number | null;
}

export interface Allocation {
  asset_class: AssetClass;
  value: number | null;
  weight: number | null;
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
  returns?: Returns;
  allocation?: Allocation[];
  pending_reviews?: number;
  display?: { choice: string; currency: string; inr_per_unit: number; note?: string };
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
  /** "INTL" for a listing picked from international search results (price in its own currency). */
  market?: "IN" | "INTL";
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
  review?: "" | "pending" | "apply" | "skip";
}

export interface ImportResult {
  broker?: string;
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
  source: "upstox" | "zerodha" | "groww" | "bse" | "yahoo-delayed" | "none" | string;
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

export interface InsightState {
  configured: boolean;
  source: "environment" | "keychain" | "memory" | null;
  model: string;
  frequency?: "hourly" | "daily";
  last_at?: string | null;
  next_at?: string | null;
}

export interface Memo {
  id: number;
  created_at: string;
  model: string;
  text: string;
  payload: Record<string, unknown>;
  unverified_numbers: string[];
  cached?: boolean;
  next_at?: string | null;
}

export interface SearchResult {
  symbol: string;
  name: string;
  exchange: string;
  held: boolean;
  asset_class?: AssetClass;
  market?: string;
  currency?: string;
}

export interface SearchResponse {
  query: string;
  results: SearchResult[];
  online: boolean;
}

export type SourceId = "upstox" | "zerodha" | "groww" | "bse" | "yahoo";
export type PriceSource = "auto" | SourceId | "off";

export interface CredentialField {
  name: string;
  label: string;
  secret: boolean;
  required: boolean;
  help: string;
  set: boolean;
  source: "environment" | "keychain" | "memory" | null;
}

export interface Mismatch {
  broker: string;
  symbol: string;
  isin: string;
  broker_quantity: number;
  ledger_quantity: number;
}

export interface SourceState {
  id: SourceId;
  label: string;
  kind: "broker" | "data";
  capabilities: ("csv" | "holdings" | "trades" | "live" | "history")[];
  login: "none" | "redirect" | "generate";
  experimental: boolean;
  notes: string;
  live_note: string;
  configured: boolean;
  session: { needed: boolean; active: boolean; issued?: string | null };
  fields: CredentialField[];
  last_sync: string | null;
  holdings_synced: number;
  mismatches: Mismatch[];
}

export interface ConnectionsState {
  price_source: PriceSource;
  price_sources: PriceSource[];
  env_override: string | null;
  feed: FeedStatus;
  sources: SourceState[];
}

export interface SyncResult {
  imported: number;
  duplicates: number;
  holdings: number;
  mismatches: Mismatch[];
  synced_at: string;
}

export interface Bond {
  symbol: string;
  name: string;
  isin: string;
  face_value: number;
  coupon_rate: number;
  frequency: 0 | 1 | 2 | 4 | 12;
  maturity: string;
  price: number;
  coupon_per_bond: number;
}

export type BondInput = Omit<Bond, "symbol" | "coupon_per_bond">;

export interface BseSyncResult {
  added: { symbol: string; ex_date: string; kind: string; value: number; purpose: string }[];
  already_recorded: number;
  failed: string[];
  checked: number;
}

export interface ActionReview {
  id: number;
  symbol: string;
  kind: "split" | "bonus";
  value: number;
  ex_date: string;
  source: string;
  trades_before: number;
  uploaded_on: string | null;
  quantity_if_applied: number;
  quantity_if_skipped: number;
  broker_quantity: number | null;
  suggestion: { answer: "apply" | "skip" | null; reason: string };
}

export interface WatchItem {
  symbol: string;
  starred: boolean;
  name: string;
  asset_class: AssetClass;
  currency: string;
  last: number | null;
  as_of: string | null;
  change_pct: number | null;
  cached_bars: number;
  held: boolean;
  viewed_at: string | null;
}

export interface CacheStatus {
  database: string;
  symbols: { symbol: string; bars: number; first: string; last: string; refreshed: string | null; starred: boolean; traded: boolean }[];
  bars: number;
  served_from_cache: number;
  incremental_updates: number;
  full_downloads: number;
}

export interface OptPortfolio {
  return: number;
  volatility: number;
  sharpe: number | null;
  weights: Record<string, number>;
}

export interface OptimizerResult {
  symbols: string[];
  observations: number;
  from: string;
  to: string;
  risk_free_rate: number;
  max_weight: number;
  shrinkage: number;
  portfolios: { max_sharpe: OptPortfolio | null; min_variance: OptPortfolio | null; equal_weight: OptPortfolio | null; current?: OptPortfolio | null };
  frontier: { return: number; volatility: number }[];
  assets: { symbol: string; name: string; held: boolean; return: number; volatility: number; sharpe: number | null }[];
  warnings: string[];
}

export interface ImportField { field: string; label: string; required: boolean; format: string }

export interface ImportPreview {
  broker: "upstox" | "zerodha" | "groww" | "generic";
  header_row: number;
  headings: string[];
  mapping: Record<string, string | null>;
  missing: string[];
  samples: string[][];
  fields: ImportField[];
}

export interface ImportFormats {
  generic: { headings: { heading: string; required: boolean; format: string }[]; notes: string[] };
  brokers: Record<string, { label: string; file: string; required: string[]; optional: string[]; where: string }>;
}

export interface ShockRow { shock: number; pnl: number; pnl_pct: number; low: number; high: number; beta: number }

export interface StressResult {
  as_of: string;
  observations: number;
  benchmark: string;
  benchmark_name: string;
  portfolio_value: number;
  horizon_days: number;
  portfolio_beta: number;
  shocks: ShockRow[];
  custom: ShockRow & { holdings: { symbol: string; name: string; value: number; beta: number; move: number; pnl: number }[] };
  crises: { id: string; label: string; start: string; end: string; available: boolean; market_move?: number;
            pnl?: number; pnl_pct?: number; actual_share?: number;
            by_holding?: { symbol: string; move: number; pnl: number; method: "actual" | "beta" }[] }[];
  monte_carlo: {
    simulations: number; horizon_days: number;
    percentiles: Record<"p1" | "p5" | "p25" | "p50" | "p75" | "p95" | "p99", number>;
    expected_shortfall_95: number; expected_shortfall_99: number;
    prob_loss: Record<string, number>;
    histogram: { edges: number[]; counts: number[] };
  };
  correlation: { confidence: number; horizon_days: number; var_normal: number; var_stressed: number;
                 avg_correlation: number; avg_correlation_stressed: number };
  unpriced: string[];
  warnings: string[];
}
