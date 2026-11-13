import { useEffect, useRef, useState } from "react";
import { api } from "../api/client";
import type { UpstoxState } from "../api/types";
import { feedLabel } from "../format";
import { useStore } from "../state/store";

/** One-time setup for live Upstox prices. The token goes straight to the
 *  engine, which keeps it in the system credential store; it is never shown again. */
export function UpstoxDialog() {
  const open = useStore((s) => s.upstoxOpen);
  const setOpen = useStore((s) => s.setUpstoxOpen);
  const liveStatus = useStore((s) => s.live?.status);
  const [state, setState] = useState<UpstoxState | null>(null);
  const [token, setToken] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const input = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (!open) return;
    setToken("");
    setError(null);
    api.upstox().then(setState).catch((e) => setError((e as Error).message));
    input.current?.focus();
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setOpen(false);
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, setOpen]);

  if (!open) return null;

  const act = async (fn: () => Promise<UpstoxState>) => {
    setBusy(true);
    setError(null);
    try {
      setState(await fn());
      setToken("");
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };
  const feed = liveStatus ?? state?.feed;
  const fromEnv = state?.source === "environment";

  return (
    <div className="fixed inset-0 z-40 flex items-start justify-center bg-black/60 pt-24"
         onMouseDown={(e) => e.target === e.currentTarget && setOpen(false)}>
      <div role="dialog" aria-modal="true" aria-labelledby="upstox-title"
           className="w-[480px] max-w-[92vw] border border-amber bg-panel shadow-2xl">
        <div className="flex items-center justify-between border-b border-line px-4 py-2.5">
          <h2 id="upstox-title" className="tracking-widest text-amber">UPSTOX LIVE PRICES</h2>
          <button onClick={() => setOpen(false)} aria-label="Close" className="text-dim hover:text-ink">✕</button>
        </div>

        <div className="space-y-3 px-4 py-4">
          <div className="grid grid-cols-[90px_1fr] gap-y-1">
            <span className="text-dim">TOKEN</span>
            <span>
              {state == null ? "…" : !state.configured ? "Not set"
                : fromEnv ? "Set by environment variable" : "Saved in system keychain"}
            </span>
            <span className="text-dim">FEED</span>
            <span className={feed?.state === "error" ? "text-down" : feed?.state === "live" && feed.source === "upstox" ? "text-up" : "text-amber"}>
              {feedLabel(feed)}
              {feed?.detail ? <span className="text-dim"> · {feed.detail}</span> : null}
            </span>
          </div>

          <p className="text-[11px] leading-relaxed text-dim">
            Paste an Upstox <span className="text-ink">Analytics Token</span>: read-only, valid for one year,
            and unable to place or change orders. Create it in the Upstox Developer Apps page under the
            Analytics tab. Without a token, prices come from Yahoo with a delay.
          </p>

          <form
            className="flex gap-2"
            onSubmit={(e) => {
              e.preventDefault();
              if (token.trim()) act(() => api.saveUpstoxToken(token.trim()));
            }}
          >
            <input
              ref={input}
              type="password"
              value={token}
              onChange={(e) => setToken(e.target.value)}
              placeholder={fromEnv ? "Managed by environment variable" : "Analytics token"}
              aria-label="Upstox analytics token"
              autoComplete="off"
              spellCheck={false}
              disabled={busy || fromEnv}
              className="min-w-0 flex-1 border border-line bg-bg px-2 py-1.5 text-ink outline-none placeholder:text-dim/60 focus:border-amber disabled:opacity-50"
            />
            <button type="submit" disabled={busy || fromEnv || token.trim().length < 20}
                    className="border border-amber px-3 py-1.5 text-amber hover:bg-amber hover:text-black disabled:opacity-40 disabled:hover:bg-transparent disabled:hover:text-amber">
              SAVE
            </button>
          </form>

          {state?.source === "keychain" && (
            <button onClick={() => act(api.removeUpstoxToken)} disabled={busy}
                    className="text-[11px] text-dim underline hover:text-down disabled:opacity-40">
              Remove saved token and go back to delayed prices
            </button>
          )}
          {error && <div role="alert" className="text-down">{error}</div>}
        </div>
      </div>
    </div>
  );
}
