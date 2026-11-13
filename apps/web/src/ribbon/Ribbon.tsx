import { useRef, useState } from "react";
import type { Benchmark } from "../api/types";
import { feedLabel, ticker } from "../format";
import type { Holding } from "../api/types";
import { useStore } from "../state/store";

const NONE: Holding[] = [];
import { Seg } from "../ui";

export function Ribbon() {
  const status = useStore((s) => s.status);
  const busy = useStore((s) => s.busy);
  const params = useStore((s) => s.portfolio?.params);
  const holdings = useStore((s) => s.portfolio?.holdings) ?? NONE;
  const setParam = useStore((s) => s.setParam);
  const select = useStore((s) => s.select);
  const importCsv = useStore((s) => s.importCsv);
  const refreshPrices = useStore((s) => s.refreshPrices);
  const setPalette = useStore((s) => s.setPalette);
  const setUpstoxOpen = useStore((s) => s.setUpstoxOpen);
  const feed = useStore((s) => s.live?.status);
  const fileRef = useRef<HTMLInputElement>(null);
  const [query, setQuery] = useState("");

  const go = () => {
    const q = query.trim().toUpperCase();
    if (!q) return;
    const held = holdings.find((h) => ticker(h.symbol) === q || h.symbol === q);
    select(held ? held.symbol : q.includes(".") ? q : `${q}.NS`);
    setQuery("");
  };
  const mod = navigator.platform.toLowerCase().includes("mac") ? "⌘" : "Ctrl+";
  const live = feed?.state === "live";
  const dot =
    status === "down" || feed?.state === "error" ? "bg-down"
    : status === "ok" && live && feed.source === "upstox" ? "bg-up"
    : "bg-amber";
  const label =
    busy ? "CALC" : status === "down" ? "DOWN" : status !== "ok" ? "INIT" : feedLabel(feed);

  return (
    <header className="flex h-10 shrink-0 items-center gap-4 border-b border-line bg-panel px-3">
      <div className="flex items-center gap-2">
        <span className="bg-amber px-1.5 py-0.5 text-[11px] font-bold tracking-widest text-black">QT</span>
        <span className="hidden text-[10px] tracking-widest text-dim lg:inline">READ-ONLY</span>
      </div>

      <form onSubmit={(e) => { e.preventDefault(); go(); }} className="flex items-center">
        <input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="TICKER"
          aria-label="Ticker search"
          list="qt-tickers"
          spellCheck={false}
          className="w-32 border border-line bg-bg px-2 py-1 uppercase text-amber outline-none placeholder:text-dim/60 focus:border-amber"
        />
        <datalist id="qt-tickers">
          {holdings.map((h) => <option key={h.symbol} value={ticker(h.symbol)} />)}
        </datalist>
      </form>

      <Seg<Benchmark>
        label="BENCH" value={params?.benchmark}
        options={[{ value: "^NSEI", label: "NIFTY" }, { value: "^BSESN", label: "SENSEX" }]}
        onChange={(v) => setParam({ benchmark: v })}
      />
      <Seg<number>
        label="VAR" value={params?.confidence}
        options={[{ value: 0.95, label: "95%" }, { value: 0.99, label: "99%" }]}
        onChange={(v) => setParam({ confidence: v })}
      />
      <Seg<number>
        label="HORIZON" value={params?.horizon_days}
        options={[{ value: 1, label: "1D" }, { value: 10, label: "10D" }]}
        onChange={(v) => setParam({ horizon_days: v })}
      />

      <div className="ml-auto flex items-center gap-2">
        <button onClick={() => setPalette(true)}
                className="border border-line px-2 py-1 text-dim hover:border-amber hover:text-ink">
          COMMANDS <span className="text-dim/60">{mod}K</span>
        </button>
        <button onClick={() => setUpstoxOpen(true)}
                className="border border-line px-2 py-1 text-dim hover:border-amber hover:text-ink">
          UPSTOX
        </button>
        <button onClick={() => refreshPrices()} disabled={busy}
                className="border border-line px-2 py-1 text-dim hover:border-amber hover:text-ink disabled:opacity-40">
          REFRESH
        </button>
        <button onClick={() => fileRef.current?.click()}
                className="border border-amber px-2 py-1 text-amber hover:bg-amber hover:text-black">
          IMPORT CSV
        </button>
        <input
          id="qt-import" ref={fileRef} type="file" accept=".csv,text/csv" className="hidden"
          onChange={(e) => {
            const f = e.target.files?.[0];
            if (f) importCsv(f);
            e.target.value = "";
          }}
        />
        <span className="flex items-center gap-1.5 pl-1 text-[10px] tracking-widest text-dim"
              title={feed?.detail || `Engine ${status}`}>
          <span className={`h-2 w-2 rounded-full ${dot} ${busy ? "animate-pulse" : ""}`} />
          {label}
        </span>
      </div>
    </header>
  );
}
