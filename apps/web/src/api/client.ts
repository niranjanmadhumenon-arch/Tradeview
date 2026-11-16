import type { BenchmarkOption, CorporateAction, TradeInput, ImportResult, InsightState, Memo, LiveSnapshot, Portfolio, SearchResponse, Settings, Trade, UpstoxState } from "./types";

declare global {
  interface Window {
    qt?: { engineUrl: string; token: string; platform: string };
  }
}

const BASE = window.qt?.engineUrl ?? import.meta.env.VITE_ENGINE_URL ?? "http://127.0.0.1:8765";
const TOKEN = window.qt?.token ?? "";

async function call<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  if (TOKEN) headers.set("X-QT-Token", TOKEN);
  let res: Response;
  try {
    res = await fetch(BASE + path, { ...init, headers });
  } catch {
    throw new Error("Engine is not reachable");
  }
  if (!res.ok) {
    const body = await res.json().catch(() => null);
    throw new Error(typeof body?.detail === "string" ? body.detail : `Engine error ${res.status}`);
  }
  return res.json() as Promise<T>;
}

export const api = {
  health: () => call<{ status: string }>("/health"),
  settings: () => call<Settings>("/api/settings"),
  saveSettings: (patch: Partial<Settings>) =>
    call<Settings>("/api/settings", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(patch),
    }),
  metrics: (refresh: boolean) => call<Portfolio>(`/api/metrics?refresh=${refresh}`),
  search: (q: string) => call<SearchResponse>(`/api/search?q=${encodeURIComponent(q)}`),
  trades: () => call<Trade[]>("/api/ledger/trades"),
  benchmarks: (q: string) =>
    call<{ results: BenchmarkOption[]; online: boolean }>(`/api/benchmarks?q=${encodeURIComponent(q)}`),
  recordTrade: (t: TradeInput) =>
    call<Trade>("/api/ledger/trades", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(t),
    }),
  amendTrade: (id: number, t: TradeInput) =>
    call<Trade>(`/api/ledger/trades/${id}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(t),
    }),
  removeTrade: (id: number) => call<{ deleted: number }>(`/api/ledger/trades/${id}`, { method: "DELETE" }),
  exportCsv: async () => {
    const headers = new Headers();
    if (TOKEN) headers.set("X-QT-Token", TOKEN);
    const res = await fetch(`${BASE}/api/ledger/export`, { headers }).catch(() => null);
    if (!res?.ok) throw new Error("Could not export the ledger");
    const d = new Date();
    const stamp = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
    return { blob: await res.blob(), name: `quant-terminal-ledger-${stamp}.csv` };
  },
  actions: () => call<CorporateAction[]>("/api/corporate-actions"),
  refreshMarket: () => call<{ warnings: string[] }>("/api/market/refresh", { method: "POST" }),
  upstox: () => call<UpstoxState>("/api/upstox"),
  saveUpstoxToken: (token: string) =>
    call<UpstoxState>("/api/upstox/token", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ token }),
    }),
  removeUpstoxToken: () => call<UpstoxState>("/api/upstox/token", { method: "DELETE" }),
  insight: () => call<InsightState>("/api/insight"),
  saveInsightKey: (key: string) =>
    call<InsightState>("/api/insight/key", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ key }),
    }),
  removeInsightKey: () => call<InsightState>("/api/insight/key", { method: "DELETE" }),
  insightPreview: () => call<Record<string, unknown>>("/api/insight/preview"),
  createMemo: () => call<Memo>("/api/insight/memo", { method: "POST" }),
  memos: () => call<Memo[]>("/api/insight/memos"),
  importCsv: (file: File) => {
    const form = new FormData();
    form.append("file", file);
    return call<ImportResult>("/api/ledger/import", { method: "POST", body: form });
  },
};

/** Opens the live tick stream and reconnects on its own if it drops. Returns a stop function. */
export function openTicks(onSnapshot: (s: LiveSnapshot) => void, onDrop: () => void): () => void {
  let ws: WebSocket | null = null;
  let timer: ReturnType<typeof setTimeout> | undefined;
  let stopped = false;
  const url = `${BASE.replace(/^http/, "ws")}/ws/ticks${TOKEN ? `?token=${encodeURIComponent(TOKEN)}` : ""}`;
  const connect = () => {
    ws = new WebSocket(url);
    ws.onmessage = (e) => {
      try {
        onSnapshot(JSON.parse(e.data) as LiveSnapshot);
      } catch {
        /* ignore a malformed frame */
      }
    };
    ws.onclose = () => {
      if (stopped) return;
      onDrop();
      timer = setTimeout(connect, 2000);
    };
  };
  connect();
  return () => {
    stopped = true;
    clearTimeout(timer);
    ws?.close();
  };
}
