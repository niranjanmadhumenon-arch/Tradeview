import { inr, num, pct, signed, ticker, tone } from "../format";
import { useStore } from "../state/store";
import { Empty, Flash } from "../ui";

export function HoldingsPane() {
  const portfolio = useStore((s) => s.portfolio);
  const selected = useStore((s) => s.selected);
  const select = useStore((s) => s.select);
  const rows = portfolio?.holdings ?? [];
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
              <th className="r">Value</th>
              <th className="r">Wt</th>
              <th className="r">Unrl P&amp;L</th>
              <th className="r">Beta</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((h) => (
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
                <td className="r"><Flash value={h.last}>{num(h.last)}</Flash></td>
                <td className="r"><Flash value={h.value}>{num(h.value, 0)}</Flash></td>
                <td className="r text-dim">{pct(h.weight, 1)}</td>
                <td className={`r ${tone(h.unrealized_pnl)}`}>{signed(h.unrealized_pnl)}</td>
                <td className="r">{num(h.beta)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="grid grid-cols-2 gap-x-4 gap-y-1 border-t border-line bg-bg px-3 py-2 text-[10.5px]">
        <Row label="VALUE" value={inr(portfolio?.portfolio_value)} />
        <Row label="NET DELTA" value={inr(portfolio?.net_delta)} />
        <Row label="UNREALIZED" value={signed(portfolio?.unrealized_pnl)} cls={tone(portfolio?.unrealized_pnl)} />
        <Row label="REALIZED" value={signed(portfolio?.realized_pnl)} cls={tone(portfolio?.realized_pnl)} />
      </div>
    </div>
  );
}

function Row({ label, value, cls = "" }: { label: string; value: string; cls?: string }) {
  return (
    <div className="flex justify-between">
      <span className="tracking-widest text-dim">{label}</span>
      <span className={cls}>{value}</span>
    </div>
  );
}
