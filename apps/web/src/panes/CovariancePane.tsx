import { useState } from "react";
import { num, ticker } from "../format";
import { useStore } from "../state/store";
import { Empty, Seg } from "../ui";

type View = "matrix" | "annualized" | "correlation";

const HORIZONS = [1, 2, 3, 5, 10].map((d) => ({ value: d, label: `${d}D` }));
const VIEWS: { value: View; label: string }[] = [
  { value: "matrix", label: "PERIOD" },
  { value: "annualized", label: "ANNUAL" },
  { value: "correlation", label: "CORR" },
];

export function CovariancePane() {
  const cov = useStore((s) => s.portfolio?.covariance);
  const horizon = useStore((s) => s.portfolio?.params.cov_horizon_days);
  const setParam = useStore((s) => s.setParam);
  const [view, setView] = useState<View>("matrix");

  const controls = (
    <div className="mb-3 flex flex-wrap items-center gap-4">
      <Seg<number> label="HORIZON" value={horizon} options={HORIZONS}
                   onChange={(v) => setParam({ cov_horizon_days: v })} />
      <Seg<View> label="SHOW" value={view} options={VIEWS} onChange={setView} />
    </div>
  );

  if (!cov) {
    return (
      <div className="flex h-full flex-col p-3">
        {controls}
        <Empty title="Covariance matrix unavailable"
               hint="Needs at least 30 returns of price history for the holdings at this horizon." />
      </div>
    );
  }

  const data = cov[view];
  const h = cov.horizon_days;
  const unit = h === 1 ? "DAILY" : `${h}-DAY`;
  const title =
    view === "matrix" ? `COVARIANCE OF ${unit} RETURNS`
    : view === "annualized" ? `COVARIANCE OF ${unit} RETURNS, ANNUALIZED`
    : `CORRELATION OF ${unit} RETURNS`;
  const flat = data.flat().filter((v): v is number => v != null);
  const max = view === "correlation" ? 1 : Math.max(...flat.map(Math.abs), 1e-12);
  const digits = view === "matrix" ? 6 : view === "annualized" ? 4 : 2;

  return (
    <div className="p-3">
      {controls}
      <div className="mb-2 text-[10px] tracking-widest text-dim">
        {title} · {cov.observations} {h > 1 ? "OVERLAPPING " : ""}OBSERVATIONS
      </div>
      <table className="grid-table w-auto">
        <thead>
          <tr>
            <th className="l" />
            {cov.symbols.map((s) => <th key={s} className="r">{ticker(s)}</th>)}
          </tr>
        </thead>
        <tbody>
          {data.map((row, i) => (
            <tr key={cov.symbols[i]}>
              <td className="l text-cyan">{ticker(cov.symbols[i])}</td>
              {row.map((v, j) => (
                <td key={j} className="r"
                    style={{
                      background: v == null ? undefined
                        : `rgb(${v < 0 ? "64 156 255" : "255 176 0"} / ${(Math.abs(v) / max) * 0.45})`,
                    }}>
                  {num(v, digits)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
