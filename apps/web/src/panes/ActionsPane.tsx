import { num, ticker } from "../format";
import { useStore } from "../state/store";
import { Empty } from "../ui";

export function ActionsPane() {
  const actions = useStore((s) => s.actions);
  if (!actions.length)
    return <Empty title="No corporate actions" hint="Splits and dividends appear here after prices are refreshed." />;
  return (
    <table className="grid-table">
      <thead>
        <tr>
          <th className="l">Ex-date</th>
          <th className="l">Symbol</th>
          <th className="l">Type</th>
          <th className="r">Value</th>
          <th className="l">Source</th>
        </tr>
      </thead>
      <tbody>
        {actions.map((a) => (
          <tr key={a.id}>
            <td className="l text-dim">{a.ex_date}</td>
            <td className="l text-cyan">{ticker(a.symbol)}</td>
            <td className={`l ${a.kind === "dividend" ? "text-ink" : "text-amber"}`}>{a.kind.toUpperCase()}</td>
            <td className="r">{a.kind === "dividend" ? `₹${num(a.value)}` : `×${num(a.value)}`}</td>
            <td className="l text-dim">{a.source}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
