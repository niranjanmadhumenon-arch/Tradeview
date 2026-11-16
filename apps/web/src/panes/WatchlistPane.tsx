import { useEffect, useState } from "react";
import { api } from "../api/client";
import type { CacheStatus } from "../api/types";
import { ASSET_TAG, num, signedPct, ticker, tone } from "../format";
import { useStore } from "../state/store";
import { Empty } from "../ui";

/** Starred stocks (*) and recently viewed ones. All of their daily prices live in
 *  the local database, so looking at them again costs no download. */
export function WatchlistPane() {
  const watch = useStore((s) => s.watch);
  const load = useStore((s) => s.loadWatchlist);
  const toggleStar = useStore((s) => s.toggleStar);
  const openSymbol = useStore((s) => s.openSymbol);
  const selected = useStore((s) => s.selected);
  const [cache, setCache] = useState<CacheStatus | null>(null);

  useEffect(() => {
    load();
    api.cache().then(setCache).catch(() => {});
  }, [load, watch.length]);

  const exportCsv = async (symbol: string) => {
    try {
      const blob = await api.pricesCsv(symbol);
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `${symbol.replace(/[^A-Za-z0-9._-]/g, "_")}-prices.csv`;
      a.click();
      URL.revokeObjectURL(url);
    } catch (e) {
      useStore.setState({ error: (e as Error).message });
    }
  };

  return (
    <div className="flex h-full flex-col">
      <div className="min-h-0 flex-1 overflow-auto">
        {!watch.length ? (
          <Empty title="No stocks starred yet"
                 hint="Search a stock in the ribbon and press ☆ to star it. Starred stocks keep their prices cached and feed the OPTIMIZER." />
        ) : (
          <table className="grid-table">
            <thead>
              <tr>
                <th className="l" aria-label="Starred" />
                <th className="l">Symbol</th>
                <th className="r">Last</th>
                <th className="r">Day</th>
                <th className="r" title="Daily bars stored locally">Cached</th>
                <th className="l" />
              </tr>
            </thead>
            <tbody>
              {watch.map((w) => (
                <tr key={w.symbol} className={`hover:bg-raise ${w.symbol === selected ? "bg-raise" : ""}`}>
                  <td className="l">
                    <button onClick={() => toggleStar(w.symbol, w.name)}
                            aria-label={w.starred ? `Unstar ${w.symbol}` : `Star ${w.symbol}`}
                            aria-pressed={w.starred}
                            className={w.starred ? "text-amber" : "text-dim hover:text-amber"}>
                      {w.starred ? "★" : "☆"}
                    </button>
                  </td>
                  <td className="l cursor-pointer" onClick={() => openSymbol(w.symbol, w.name)} title={w.name || undefined}>
                    <span className="font-semibold text-cyan">{ticker(w.symbol)}</span>
                    {w.asset_class !== "equity" && (
                      <span className={`ml-1.5 text-[9px] tracking-widest ${ASSET_TAG[w.asset_class]?.cls ?? "text-dim"}`}>
                        {ASSET_TAG[w.asset_class]?.label}
                      </span>
                    )}
                    {w.held && <span className="ml-1.5 text-[9px] tracking-widest text-up">HELD</span>}
                    <div className="max-w-[180px] truncate text-[10px] text-dim">{w.name}</div>
                  </td>
                  <td className="r tabular-nums">
                    {num(w.last)}{w.currency !== "INR" && <span className="ml-1 text-[9px] text-dim">{w.currency}</span>}
                  </td>
                  <td className={`r ${tone(w.change_pct)}`}>{w.change_pct == null ? "—" : signedPct(w.change_pct)}</td>
                  <td className="r text-dim tabular-nums" title={w.as_of ? `Latest bar ${w.as_of}` : undefined}>{w.cached_bars}</td>
                  <td className="l">
                    {w.cached_bars > 0 && (
                      <button onClick={() => exportCsv(w.symbol)} className="text-[10px] text-dim underline hover:text-ink">
                        csv
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
      {cache && (
        <div className="border-t border-line bg-bg px-3 py-2 text-[10.5px] text-dim">
          <div className="flex flex-wrap gap-x-4 gap-y-0.5">
            <span><span className="tracking-widest">CACHE</span> {cache.symbols.length} symbols · {cache.bars.toLocaleString("en-IN")} bars</span>
            <span title="Requests answered locally with no download">served locally {cache.served_from_cache}</span>
            <span title="Only the days since the last download were fetched">top-ups {cache.incremental_updates}</span>
            <span title="Whole history fetched: first time, or after a new split or dividend">full {cache.full_downloads}</span>
          </div>
          <div className="mt-0.5 truncate" title={cache.database}>{cache.database}</div>
        </div>
      )}
    </div>
  );
}
