import { useEffect, useState } from "react";
import { api } from "../api/client";
import { embedHasData, tradingViewSymbol } from "../chartSymbol";
import { num, pct, ticker, tone } from "../format";
import { useStore } from "../state/store";
import { Empty } from "../ui";

type Source = "auto" | "local";

/** Price chart for the selected symbol. TradingView where its free embed has
 *  data for the listing's exchange; otherwise (NSE-only, London, Tokyo, Hong Kong,
 *  funds...) a chart drawn from the locally cached daily prices. */
export function ChartPane() {
  const selected = useStore((s) => s.selected);
  const exchange = useStore((s) => (s.selected ? s.exchanges[s.selected] : undefined));
  const [source, setSource] = useState<Source>("auto");

  if (!selected) return <Empty title="No symbol selected" hint="Pick a holding or search a stock by name in the ribbon." />;
  if (selected.startsWith("BOND:"))
    return <Empty title="No market chart for this bond"
                  hint="Bonds tracked by hand are valued at the price you set under Add or edit bonds." />;

  const tv = tradingViewSymbol(selected, exchange);
  const canEmbed = !selected.startsWith("MF:") && embedHasData(tv);
  const embed = source === "auto" && canEmbed;

  return (
    <div className="flex h-full flex-col">
      <div className="flex items-center justify-between gap-2 border-b border-line px-3 py-1 text-[10px] tracking-widest text-dim">
        <span className="truncate">{embed ? `TRADINGVIEW · ${tv}` : `LOCAL CACHE · ${ticker(selected)}`}</span>
        {canEmbed && (
          <button onClick={() => setSource(source === "auto" ? "local" : "auto")}
                  className="shrink-0 text-dim underline hover:text-ink">
            {embed ? "use cached prices" : "use TradingView"}
          </button>
        )}
      </div>
      <div className="min-h-0 flex-1">
        {embed ? <TradingView key={tv} symbol={tv} /> : <LocalChart key={selected} symbol={selected} />}
      </div>
    </div>
  );
}

function TradingView({ symbol }: { symbol: string }) {
  const params = new URLSearchParams({
    symbol,
    interval: "D",
    theme: "dark",
    style: "1",
    timezone: "Asia/Kolkata",
    locale: "en",
    withdateranges: "1",
    hide_side_toolbar: "0",
    allow_symbol_change: "1",
    save_image: "0",
    toolbar_bg: "#0d0f13",
  });
  return (
    <iframe
      title={`${symbol} chart`}
      src={`https://s.tradingview.com/widgetembed/?${params}`}
      className="h-full w-full border-0"
      sandbox="allow-scripts allow-same-origin allow-popups"
      referrerPolicy="no-referrer"
    />
  );
}

const RANGES = [{ days: 63, label: "3M" }, { days: 126, label: "6M" }, { days: 252, label: "1Y" }, { days: 504, label: "2Y" }];

/** Daily closes from the local price cache (downloads only what is missing). */
function LocalChart({ symbol }: { symbol: string }) {
  const [bars, setBars] = useState<{ date: string; close: number }[] | null>(null);
  const [currency, setCurrency] = useState("");
  const [range, setRange] = useState(252);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setBars(null);
    setError(null);
    api.prices(symbol, 760)
      .then((r) => {
        setBars(r.bars.map((b) => ({ date: b.date, close: b.close })));
        setCurrency(r.currency);
        if (!r.bars.length) setError(r.warning ?? "No price history for this symbol");
      })
      .catch((e) => setError((e as Error).message));
  }, [symbol]);

  if (error) return <Empty title="No chart" hint={error} />;
  if (!bars) return <Empty title="Loading prices…" />;

  const shown = bars.slice(-range);
  const first = shown[0]?.close, last = shown[shown.length - 1]?.close;
  const change = first && last ? last / first - 1 : null;
  const W = 640, H = 300, L = 8, R = 56, T = 12, B = 22;
  const lo = Math.min(...shown.map((b) => b.close)), hi = Math.max(...shown.map((b) => b.close));
  const pad = (hi - lo) * 0.06 || hi * 0.02 || 1;
  const y0 = lo - pad, y1 = hi + pad;
  const sx = (i: number) => L + (i / Math.max(shown.length - 1, 1)) * (W - L - R);
  const sy = (v: number) => T + (1 - (v - y0) / (y1 - y0)) * (H - T - B);
  const line = shown.map((b, i) => `${i ? "L" : "M"}${sx(i).toFixed(1)},${sy(b.close).toFixed(1)}`).join(" ");
  const area = `${line} L${sx(shown.length - 1).toFixed(1)},${H - B} L${sx(0).toFixed(1)},${H - B} Z`;
  const color = change != null && change < 0 ? "var(--color-down)" : "var(--color-up)";
  const ticks = Array.from({ length: 5 }, (_, i) => y0 + ((y1 - y0) * i) / 4);
  const dateTicks = [0, Math.floor(shown.length / 2), shown.length - 1];

  return (
    <div className="flex h-full flex-col">
      <div className="flex flex-wrap items-baseline gap-x-3 px-3 py-2">
        <span className="font-semibold text-cyan">{ticker(symbol)}</span>
        <span className="text-lg">{num(last)}</span>
        {currency && <span className="text-[10px] text-dim">{currency}</span>}
        <span className={tone(change)}>{pct(change, 1)}</span>
        <span className="ml-auto flex">
          {RANGES.map((r) => (
            <button key={r.days} onClick={() => setRange(r.days)}
                    className={`-ml-px border px-1.5 py-0.5 text-[10px] first:ml-0 ${range === r.days ? "relative z-10 border-amber bg-amber text-black" : "border-line text-dim hover:text-ink"}`}>
              {r.label}
            </button>
          ))}
        </span>
      </div>
      <div className="min-h-0 flex-1 px-1">
        <svg viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none" className="h-full w-full" role="img"
             aria-label={`${ticker(symbol)} daily closing price`}>
          {ticks.map((v) => (
            <g key={v}>
              <line x1={L} x2={W - R} y1={sy(v)} y2={sy(v)} stroke="var(--color-line)" strokeWidth="1" vectorEffect="non-scaling-stroke" />
              <text x={W - R + 4} y={sy(v) + 3} fontSize="10" fill="var(--color-dim)">{num(v, v >= 1000 ? 0 : 2)}</text>
            </g>
          ))}
          <path d={area} fill={color} opacity="0.12" />
          <path d={line} fill="none" stroke={color} strokeWidth="1.6" vectorEffect="non-scaling-stroke" />
          {dateTicks.map((i) => shown[i] && (
            <text key={i} x={sx(i)} y={H - 6} fontSize="10" fill="var(--color-dim)"
                  textAnchor={i === 0 ? "start" : i === shown.length - 1 ? "end" : "middle"}>
              {shown[i].date}
            </text>
          ))}
        </svg>
      </div>
      <div className="border-t border-line px-3 py-1 text-[10px] text-dim">
        Daily closes from the local cache ({bars.length} days stored) · source Yahoo Finance
        {symbol.startsWith("MF:") ? " / AMFI NAV" : ""}
      </div>
    </div>
  );
}
