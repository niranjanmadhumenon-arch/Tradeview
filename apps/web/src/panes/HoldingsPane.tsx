import { feedLabel, inr, num, pct, signed, signedPct, ticker, tone } from "../format";
import { useStore } from "../state/store";
import { Empty, Flash } from "../ui";

export function HoldingsPane() {
  const portfolio = useStore((s) => s.portfolio);
  const selected = useStore((s) => s.selected);
  const select = useStore((s) => s.select);
  const live = useStore((s) => s.live);
  const rows = portfolio?.holdings ?? [];
  const lp = live?.portfolio;
  // Live totals replace the close-based ones only when every holding has a live quote.
  const full = lp != null && lp.held > 0 && lp.priced === lp.held;
  const value = full ? lp.value : portfolio?.portfolio_value;
  const unrealized = full ? lp.unrealized_pnl : portfolio?.unrealized_pnl;
  if (!rows.length)
    return <Empty title="No holdings yet" hint="Import an Upstox trade-book CSV from the ribbon to build the ledger." />;

  return (
    <div className="flex h-full flex-col">
      <div className="min-h-0 flex-1 overflow-auto">
        <table className="grid-table">
          <thead>
            <tr>
              <th className="l">Symbol</th>
              <th className="r">Qty</th>
              <th className="r">Avg</th>
              <th className="r">Last</th>
              <th className="r">Day</th>
              <th className="r">Value</th>
              <th className="r">Wt</th>
              <th className="r">Unrl P&amp;L</th>
              <th className="r">Beta</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((h) => {
              const q = live?.quotes[h.symbol];
              const l = lp?.holdings[h.symbol];
              const last = q?.ltp ?? h.last;
              const val = l?.value ?? h.value;
              const unrl = l?.unrealized_pnl ?? h.unrealized_pnl;
              return (
              <tr
                key={h.symbol}
                onClick={() => select(h.symbol)}
                className={`cursor-pointer hover:bg-raise ${h.symbol === selected ? "bg-raise" : ""}`}
              >
                <td className={`l font-semibold ${h.symbol === selected ? "text-amber" : "text-cyan"}`}>
                  {ticker(h.symbol)}
                </td>
                <td className="r">{num(h.quantity, 0)}</td>
                <td className="r text-dim">{num(h.avg_cost)}</td>
                <td className="r"><Flash value={last}>{num(last)}</Flash></td>
                <td className={`r ${tone(q?.change_pct)}`}>{q?.change_pct == null ? "—" : signedPct(q.change_pct)}</td>
                <td className="r"><Flash value={val}>{num(val, 0)}</Flash></td>
                <td className="r text-dim">{pct(h.weight, 1)}</td>
                <td className={`r ${tone(unrl)}`}><Flash value={unrl}>{signed(unrl)}</Flash></td>
                <td className="r">{num(h.beta)}</td>
              </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <div className="grid grid-cols-2 gap-x-4 gap-y-1 border-t border-line bg-bg px-3 py-2 text-[10.5px]">
        <Row label="VALUE" value={inr(value)} n={value} />
        <Row label="NET DELTA" value={inr(value)} n={value} />
        <Row label="DAY P&L" value={signed(full ? lp.day_pnl : null)} n={full ? lp.day_pnl : null}
             cls={tone(full ? lp.day_pnl : null)} />
        <Row label="UNREALIZED" value={signed(unrealized)} n={unrealized} cls={tone(unrealized)} />
        <Row label="REALIZED" value={signed(portfolio?.realized_pnl)} cls={tone(portfolio?.realized_pnl)} />
        <Row label="PRICES" value={feedLabel(live?.status)} cls="text-dim" />
      </div>
    </div>
  );
}

function Row({ label, value, n, cls = "" }: {
  label: string; value: string; n?: number | null; cls?: string;
}) {
  return (
    <div className="flex justify-between">
      <span className="tracking-widest text-dim">{label}</span>
      <span className={cls}><Flash value={n}>{value}</Flash></span>
    </div>
  );
}
