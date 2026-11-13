import { Command } from "cmdk";
import { useEffect } from "react";
import { ticker } from "../format";
import type { Holding } from "../api/types";
import { useStore } from "../state/store";

const NONE: Holding[] = [];

export function Palette() {
  const open = useStore((s) => s.paletteOpen);
  const setOpen = useStore((s) => s.setPalette);
  const holdings = useStore((s) => s.portfolio?.holdings) ?? NONE;
  const { select, setParam, refreshPrices, resetLayout } = useStore.getState();

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setOpen(!useStore.getState().paletteOpen);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [setOpen]);

  const run = (fn: () => void) => () => {
    setOpen(false);
    fn();
  };
  const item =
    "flex cursor-pointer items-center justify-between px-3 py-1.5 data-[selected=true]:bg-amber data-[selected=true]:text-black";
  const group = "[&_[cmdk-group-heading]]:px-3 [&_[cmdk-group-heading]]:py-1 [&_[cmdk-group-heading]]:text-[10px] [&_[cmdk-group-heading]]:tracking-widest [&_[cmdk-group-heading]]:text-dim";

  return (
    <Command.Dialog
      open={open}
      onOpenChange={setOpen}
      label="Command palette"
      overlayClassName="fixed inset-0 z-40 bg-black/60"
      contentClassName="fixed left-1/2 top-24 z-50 w-[460px] max-w-[92vw] -translate-x-1/2 border border-amber bg-panel shadow-2xl"
    >
      <Command.Input
        placeholder="Type a command or ticker…"
        className="w-full border-b border-line bg-transparent px-3 py-2.5 text-amber outline-none placeholder:text-dim"
      />
      <Command.List className="max-h-80 overflow-auto py-1">
        <Command.Empty className="px-3 py-3 text-dim">No matching command.</Command.Empty>
        {holdings.length > 0 && (
          <Command.Group heading="HOLDINGS" className={group}>
            {holdings.map((h) => (
              <Command.Item key={h.symbol} value={`chart ${ticker(h.symbol)}`} className={item}
                            onSelect={run(() => select(h.symbol))}>
                <span>Chart {ticker(h.symbol)}</span>
              </Command.Item>
            ))}
          </Command.Group>
        )}
        <Command.Group heading="RISK PARAMETERS" className={group}>
          <Command.Item className={item} onSelect={run(() => setParam({ benchmark: "^NSEI" }))}>Benchmark: NIFTY 50</Command.Item>
          <Command.Item className={item} onSelect={run(() => setParam({ benchmark: "^BSESN" }))}>Benchmark: SENSEX</Command.Item>
          <Command.Item className={item} onSelect={run(() => setParam({ confidence: 0.95 }))}>VaR confidence: 95%</Command.Item>
          <Command.Item className={item} onSelect={run(() => setParam({ confidence: 0.99 }))}>VaR confidence: 99%</Command.Item>
          <Command.Item className={item} onSelect={run(() => setParam({ horizon_days: 1 }))}>VaR horizon: 1 day</Command.Item>
          <Command.Item className={item} onSelect={run(() => setParam({ horizon_days: 10 }))}>VaR horizon: 10 days</Command.Item>
        </Command.Group>
        <Command.Group heading="WORKSPACE" className={group}>
          <Command.Item className={item}
                        onSelect={run(() => document.getElementById("qt-import")?.click())}>
            Import Upstox trade-book CSV
          </Command.Item>
          <Command.Item className={item}
                        onSelect={run(() => useStore.getState().setUpstoxOpen(true))}>
            Connect Upstox live prices
          </Command.Item>
          <Command.Item className={item} onSelect={run(() => refreshPrices())}>Refresh prices</Command.Item>
          <Command.Item className={item} onSelect={run(() => resetLayout())}>Reset layout</Command.Item>
        </Command.Group>
      </Command.List>
    </Command.Dialog>
  );
}
