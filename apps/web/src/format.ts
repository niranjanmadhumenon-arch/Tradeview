const DASH = "—";

export function num(v: number | null | undefined, digits = 2): string {
  if (v == null) return DASH;
  return v.toLocaleString("en-IN", { minimumFractionDigits: digits, maximumFractionDigits: digits });
}

export function inr(v: number | null | undefined, digits = 0): string {
  return v == null ? DASH : `₹${num(v, digits)}`;
}

export function pct(v: number | null | undefined, digits = 2): string {
  return v == null ? DASH : `${num(v * 100, digits)}%`;
}

export function signed(v: number | null | undefined, digits = 0): string {
  if (v == null) return DASH;
  return `${v > 0 ? "+" : v < 0 ? "−" : ""}${num(Math.abs(v), digits)}`;
}

export function tone(v: number | null | undefined): string {
  if (v == null || v === 0) return "text-ink";
  return v > 0 ? "text-up" : "text-down";
}

/** RELIANCE.NS -> RELIANCE */
export function ticker(symbol: string): string {
  return symbol.replace(/\.(NS|BO)$/, "");
}

export function benchmarkName(b: string): string {
  return b === "^BSESN" ? "SENSEX" : "NIFTY 50";
}

export function signedPct(v: number, digits = 2): string {
  return `${v > 0 ? "+" : v < 0 ? "−" : ""}${num(Math.abs(v) * 100, digits)}%`;
}

export function feedLabel(status: { source: string; state: string } | undefined): string {
  if (!status || status.state === "off") return "LAST CLOSE";
  if (status.state === "error") return "FEED ERROR";
  if (status.state === "connecting") return "CONNECTING";
  return status.source === "upstox" ? "UPSTOX LIVE" : "DELAYED";
}
