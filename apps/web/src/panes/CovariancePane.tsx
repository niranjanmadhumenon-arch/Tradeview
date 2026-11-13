import { num, ticker } from "../format";
import { useStore } from "../state/store";
import { Empty } from "../ui";

export function CovariancePane() {
  const cov = useStore((s) => s.portfolio?.covariance);
  if (!cov) return <Empty title="Covariance matrix unavailable" hint="Needs at least 30 days of price history for the holdings." />;
  const flat = cov.annualized.flat().filter((v): v is number => v != null);
  const max = Math.max(...flat.map(Math.abs), 1e-12);
  return (
    <div className="p-3">
      <div className="mb-2 text-[10px] tracking-widest text-dim">ANNUALIZED COVARIANCE OF DAILY RETURNS</div>
      <table className="grid-table w-auto">
        <thead>
          <tr>
            <th className="l" />
            {cov.symbols.map((s) => <th key={s} className="r">{ticker(s)}</th>)}
          </tr>
        </thead>
        <tbody>
          {cov.annualized.map((row, i) => (
            <tr key={cov.symbols[i]}>
              <td className="l text-cyan">{ticker(cov.symbols[i])}</td>
              {row.map((v, j) => (
                <td key={j} className="r"
                    style={{ background: v == null ? undefined : `rgb(255 176 0 / ${(Math.abs(v) / max) * 0.45})` }}>
                  {num(v, 4)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
