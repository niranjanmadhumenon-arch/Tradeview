import { num, ticker } from "../format";
import { useStore } from "../state/store";
import { Empty } from "../ui";

export function TradesPane() {
  const trades = useStore((s) => s.trades);
  if (!trades.length) return <Empty title="No trades in the ledger" />;
  return (
    <table className="grid-table">
      <thead>
        <tr>
          <th className="l">Date</th>
          <th className="l">Symbol</th>
          <th className="l">Side</th>
          <th className="r">Qty</th>
          <th className="r">Price</th>
        </tr>
      </thead>
      <tbody>
        {trades.map((t) => (
          <tr key={t.id}>
            <td className="l text-dim">{t.traded_at.slice(0, 10)}</td>
            <td className="l text-cyan">{ticker(t.symbol)}</td>
            <td className={`l ${t.side === "BUY" ? "text-up" : "text-down"}`}>{t.side}</td>
            <td className="r">{num(t.quantity, 0)}</td>
            <td className="r">{num(t.price)}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
