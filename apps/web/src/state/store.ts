import { create } from "zustand";
import { api, openTicks } from "../api/client";
import type { CorporateAction, LiveSnapshot, Portfolio, Settings, Trade, TradeInput } from "../api/types";

type Status = "connecting" | "ok" | "down";

interface State {
  status: Status;
  busy: boolean;
  error: string | null;
  notice: string | null;
  portfolio: Portfolio | null;
  live: LiveSnapshot | null;
  trades: Trade[];
  actions: CorporateAction[];
  selected: string | null;
  paletteOpen: boolean;
  upstoxOpen: boolean;
  layoutEpoch: number;
  init: () => Promise<void>;
  reload: (refresh?: boolean) => Promise<void>;
  setParam: (patch: Partial<Settings>) => Promise<void>;
  importCsv: (file: File) => Promise<void>;
  exportCsv: () => Promise<void>;
  saveTrade: (input: TradeInput, id?: number) => Promise<boolean>;
  removeTrade: (id: number) => Promise<void>;
  refreshPrices: () => Promise<void>;
  select: (symbol: string | null) => void;
  setPalette: (open: boolean) => void;
  setUpstoxOpen: (open: boolean) => void;
  resetLayout: () => void;
  dismiss: () => void;
}

let ticksOpen = false;
let seq = 0; // drops responses that arrive after a newer request was sent

export const useStore = create<State>((set, get) => ({
  status: "connecting",
  busy: false,
  error: null,
  notice: null,
  portfolio: null,
  live: null,
  trades: [],
  actions: [],
  selected: null,
  paletteOpen: false,
  upstoxOpen: false,
  layoutEpoch: 0,

  init: async () => {
    for (let attempt = 0; attempt < 40; attempt++) {
      try {
        await api.health();
        set({ status: "ok" });
        if (!ticksOpen) {
          ticksOpen = true;
          openTicks(
            (live) => set({ live }),
            () => set((s) => (s.live ? { live: { ...s.live, status: { ...s.live.status, state: "connecting" } } } : {})),
          );
        }
        await get().reload(true);
        return;
      } catch {
        await new Promise((r) => setTimeout(r, 500));
      }
    }
    set({ status: "down", error: "Engine is not reachable" });
  },

  reload: async (refresh = true) => {
    const mine = ++seq;
    set({ busy: true });
    try {
      const portfolio = await api.metrics(refresh);
      const [trades, actions] = await Promise.all([api.trades(), api.actions()]);
      if (mine !== seq) return;
      const selected = get().selected ?? portfolio.holdings[0]?.symbol ?? null;
      set({ portfolio, trades, actions, selected, status: "ok", error: null });
    } catch (e) {
      if (mine === seq) set({ error: (e as Error).message });
    } finally {
      if (mine === seq) set({ busy: false });
    }
  },

  setParam: async (patch) => {
    const current = get().portfolio;
    if (current) set({ portfolio: { ...current, params: { ...current.params, ...patch } } });
    try {
      await api.saveSettings(patch);
      await get().reload(true);
    } catch (e) {
      set({ error: (e as Error).message });
      await get().reload(false);
    }
  },

  importCsv: async (file) => {
    set({ busy: true, error: null });
    try {
      const r = await api.importCsv(file);
      const parts = [`${r.imported} trades imported`];
      if (r.updated) parts.push(`${r.updated} updated from the file`);
      if (r.duplicates) parts.push(`${r.duplicates} already in ledger`);
      if (r.skipped.length) parts.push(`${r.skipped.length} rows skipped`);
      set({ notice: parts.join(" · ") });
      await get().reload(true);
    } catch (e) {
      set({ error: (e as Error).message, busy: false });
    }
  },

  exportCsv: async () => {
    try {
      const { blob, name } = await api.exportCsv();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = name;
      document.body.appendChild(a);
      a.click();
      a.remove();
      setTimeout(() => URL.revokeObjectURL(url), 10_000);
      set({ notice: `Ledger exported as ${name}` });
    } catch (e) {
      set({ error: (e as Error).message });
    }
  },

  saveTrade: async (input, id) => {
    try {
      if (id == null) await api.recordTrade(input);
      else await api.amendTrade(id, input);
      set({ notice: id == null ? "Trade recorded in the ledger" : "Trade updated", error: null });
      await get().reload(true);
      return true;
    } catch (e) {
      set({ error: (e as Error).message });
      return false;
    }
  },

  removeTrade: async (id) => {
    try {
      await api.removeTrade(id);
      set({ notice: "Trade removed from the ledger", error: null });
      await get().reload(true);
    } catch (e) {
      set({ error: (e as Error).message });
    }
  },

  refreshPrices: async () => {
    set({ busy: true });
    try {
      await api.refreshMarket();
      await get().reload(false);
    } catch (e) {
      set({ error: (e as Error).message, busy: false });
    }
  },

  select: (symbol) => set({ selected: symbol }),
  setPalette: (open) => set({ paletteOpen: open }),
  setUpstoxOpen: (open) => set({ upstoxOpen: open }),
  resetLayout: () => set((s) => ({ layoutEpoch: s.layoutEpoch + 1 })),
  dismiss: () => set({ error: null, notice: null }),
}));
