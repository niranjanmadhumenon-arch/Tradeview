import { useEffect, useState } from "react";
import { api } from "../api/client";
import type { InsightState, Memo } from "../api/types";
import { useStore } from "../state/store";

const HEADINGS = ["RISK POSTURE", "KEY EXPOSURES", "HEDGING CONSIDERATIONS", "WHAT TO WATCH"];

/** AI-written hedging memo. The model only receives the figures shown under
 *  "Data sent"; the engine does all the maths. */
export function InsightPane() {
  const hasMetrics = useStore((s) => s.portfolio?.metrics != null);
  const paramsKey = useStore((s) => JSON.stringify(s.portfolio?.params ?? null));
  const [state, setState] = useState<InsightState | null>(null);
  const [memos, setMemos] = useState<Memo[]>([]);
  const [shown, setShown] = useState<number | null>(null);
  const [preview, setPreview] = useState<Record<string, unknown> | null>(null);
  const [showData, setShowData] = useState(false);
  const [key, setKey] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.insight().then(setState).catch((e) => setError((e as Error).message));
    api.memos().then(setMemos).catch(() => {});
  }, []);

  // Keep the "data that will be sent" preview in step with the risk parameters.
  useEffect(() => {
    if (!hasMetrics) return setPreview(null);
    api.insightPreview().then(setPreview).catch(() => setPreview(null));
  }, [hasMetrics, paramsKey]);

  const run = async (fn: () => Promise<void>) => {
    setBusy(true);
    setError(null);
    try {
      await fn();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };
  const generate = () =>
    run(async () => {
      const memo = await api.createMemo();
      setMemos((m) => [memo, ...m]);
      setShown(memo.id);
    });

  const memo = memos.find((m) => m.id === shown) ?? memos[0] ?? null;
  const data = showData ? (memo && shown != null ? memo.payload : preview ?? memo?.payload) : null;

  if (state && !state.configured) {
    return (
      <div className="space-y-3 p-3">
        <div className="text-[10px] tracking-widest text-dim">AI INSIGHT · GOOGLE GEMINI</div>
        <p className="text-[11px] leading-relaxed text-dim">
          Generates a short hedging memo from the risk figures this terminal has already computed. Gemini
          receives only those summary figures (weights, beta, VaR, ratios), never your trades, quantities or
          costs, and it does no calculations. Paste a Gemini API key from Google AI Studio; it is saved in
          the system keychain.
        </p>
        <form className="flex gap-2"
              onSubmit={(e) => {
                e.preventDefault();
                run(async () => {
                  setState(await api.saveInsightKey(key.trim()));
                  setKey("");
                });
              }}>
          <input type="password" value={key} onChange={(e) => setKey(e.target.value)}
                 placeholder="Gemini API key" aria-label="Gemini API key" autoComplete="off" spellCheck={false}
                 disabled={busy}
                 className="min-w-0 flex-1 border border-line bg-bg px-2 py-1.5 text-ink outline-none placeholder:text-dim/60 focus:border-amber" />
          <button type="submit" disabled={busy || key.trim().length < 20}
                  className="border border-amber px-3 py-1.5 text-amber hover:bg-amber hover:text-black disabled:opacity-40 disabled:hover:bg-transparent disabled:hover:text-amber">
            SAVE
          </button>
        </form>
        {error && <div role="alert" className="text-down">{error}</div>}
      </div>
    );
  }

  return (
    <div className="flex h-full flex-col">
      <div className="flex items-center justify-between gap-2 border-b border-line px-3 py-2">
        <div className="min-w-0 truncate text-[10px] tracking-widest text-dim">
          AI INSIGHT{state ? ` · ${state.model.toUpperCase()}` : ""}
        </div>
        <button onClick={generate} disabled={busy || !hasMetrics || !state}
                title={hasMetrics ? "" : "Needs risk metrics first"}
                className="shrink-0 border border-amber px-2 py-1 text-amber hover:bg-amber hover:text-black disabled:opacity-40 disabled:hover:bg-transparent disabled:hover:text-amber">
          {busy ? "WRITING…" : memo ? "NEW MEMO" : "GENERATE MEMO"}
        </button>
      </div>

      <div className="min-h-0 flex-1 overflow-auto px-3 py-3">
        {error && <div role="alert" className="mb-3 text-down">{error}</div>}

        {!memo && !error && (
          <p className="text-[11px] leading-relaxed text-dim">
            {hasMetrics
              ? "No memo yet. Generate one from the current risk figures."
              : "Import trades and refresh prices first; the memo is written from the risk metrics."}
          </p>
        )}

        {memo && (
          <>
            <div className="mb-2 text-[10px] text-dim">
              {memo.created_at.slice(0, 16).replace("T", " ")} · {memo.model}
            </div>
            {memo.unverified_numbers.length > 0 && (
              <div className="mb-3 border border-amber/50 bg-amber/10 px-2 py-1.5 text-[11px] text-amber">
                ⚠ This memo contains figures the engine did not supply: {memo.unverified_numbers.join(", ")}.
                Treat them as unverified.
              </div>
            )}
            <MemoText text={memo.text} />
            <p className="mt-4 border-t border-line pt-2 text-[10px] leading-relaxed text-dim">
              AI-written commentary on locally computed figures. Not investment advice. This terminal cannot
              place orders.
            </p>
          </>
        )}

        <button onClick={() => setShowData((v) => !v)}
                className="mt-3 text-[10.5px] text-dim underline hover:text-ink">
          {showData ? "Hide" : "Show"} data sent to Gemini
        </button>
        {showData && (
          <pre className="mt-2 overflow-auto border border-line bg-bg p-2 text-[10.5px] leading-snug text-dim">
            {data ? JSON.stringify(data, null, 1) : "Nothing to send yet."}
          </pre>
        )}

        {memos.length > 1 && (
          <div className="mt-4">
            <div className="mb-1 text-[10px] tracking-widest text-dim">HISTORY</div>
            {memos.map((m) => (
              <button key={m.id} onClick={() => setShown(m.id)}
                      className={`block w-full px-1 py-1 text-left hover:bg-raise ${
                        m.id === memo?.id ? "text-amber" : "text-dim"
                      }`}>
                {m.created_at.slice(0, 16).replace("T", " ")}
                {m.unverified_numbers.length > 0 ? " · ⚠" : ""}
              </button>
            ))}
          </div>
        )}

        {state?.source === "keychain" && (
          <button onClick={() => run(async () => setState(await api.removeInsightKey()))} disabled={busy}
                  className="mt-4 block text-[10.5px] text-dim underline hover:text-down">
            Remove saved Gemini key
          </button>
        )}
      </div>
    </div>
  );
}

function MemoText({ text }: { text: string }) {
  return (
    <div className="space-y-1.5 text-[12px] leading-relaxed">
      {text.split("\n").map((line, i) => {
        const clean = line.replace(/^[#*\s]+|[*:\s]+$/g, "");
        if (!clean) return null;
        if (HEADINGS.includes(clean.toUpperCase()))
          return <h3 key={i} className="pt-2 text-[10px] tracking-widest text-amber first:pt-0">{clean.toUpperCase()}</h3>;
        return <p key={i} className="whitespace-pre-wrap">{line.replace(/\*\*/g, "")}</p>;
      })}
    </div>
  );
}
