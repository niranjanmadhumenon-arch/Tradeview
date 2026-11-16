import { useEffect, useRef, useState } from "react";
import { api } from "../api/client";
import type { SearchResult } from "../api/types";
import { ticker } from "../format";
import { useStore } from "../state/store";

/** Stock search by company name or ticker, with a keyboard-driven result list. */
export function SearchBox() {
  const select = useStore((s) => s.select);
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<SearchResult[]>([]);
  const [online, setOnline] = useState(true);
  const [loading, setLoading] = useState(false);
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);
  const listRef = useRef<HTMLUListElement>(null);
  const seq = useRef(0);

  const q = query.trim();

  useEffect(() => {
    const mine = ++seq.current;
    if (!q) {
      setResults([]);
      setLoading(false);
      return;
    }
    setLoading(true);
    const timer = setTimeout(async () => {
      try {
        const r = await api.search(q);
        if (mine !== seq.current) return;
        setResults(r.results);
        setOnline(r.online);
        setActive(0);
      } catch {
        if (mine !== seq.current) return;
        setResults([]);
        setOnline(false);
      } finally {
        if (mine === seq.current) setLoading(false);
      }
    }, 200);
    return () => clearTimeout(timer);
  }, [q]);

  // "/" focuses the search from anywhere outside a text field
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const el = e.target as HTMLElement | null;
      const typing = el?.tagName === "INPUT" || el?.tagName === "TEXTAREA" || el?.isContentEditable;
      if (e.key === "/" && !typing && !e.metaKey && !e.ctrlKey && !e.altKey) {
        e.preventDefault();
        inputRef.current?.focus();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  useEffect(() => {
    listRef.current?.children[active]?.scrollIntoView({ block: "nearest" });
  }, [active]);

  const pick = (symbol: string) => {
    select(symbol);
    setQuery("");
    setResults([]);
    setOpen(false);
    inputRef.current?.blur();
  };

  const submit = () => {
    if (!q) return;
    const chosen = results[active];
    if (chosen) return pick(chosen.symbol);
    // Still loading or nothing found: a single word is taken as a ticker, as before.
    if (!/\s/.test(q)) {
      const t = q.toUpperCase();
      pick(/\.(NS|BO)$/.test(t) ? t : `${t}.NS`);
    }
  };

  const onKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "ArrowDown" || e.key === "ArrowUp") {
      e.preventDefault();
      setOpen(true);
      if (results.length) {
        const step = e.key === "ArrowDown" ? 1 : -1;
        setActive((a) => (a + step + results.length) % results.length);
      }
    } else if (e.key === "Enter") {
      e.preventDefault();
      submit();
    } else if (e.key === "Escape") {
      if (open && q) setOpen(false);
      else inputRef.current?.blur();
    }
  };

  const show = open && q.length > 0;
  const status = loading && !results.length ? "Searching…"
    : !results.length ? (online ? "No matching stock on NSE or BSE." : "No match in your ledger. Market search is offline.")
    : null;

  return (
    <div className="relative min-w-40 max-w-72 flex-1">
      <div className="flex items-center border border-line bg-bg focus-within:border-amber">
        <svg viewBox="0 0 16 16" aria-hidden="true" className="ml-2 h-3 w-3 shrink-0 text-dim">
          <circle cx="7" cy="7" r="4.5" fill="none" stroke="currentColor" strokeWidth="1.5" />
          <path d="M10.5 10.5 14 14" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
        </svg>
        <input
          ref={inputRef}
          value={query}
          onChange={(e) => { setQuery(e.target.value); setOpen(true); }}
          onFocus={() => setOpen(true)}
          onBlur={() => setOpen(false)}
          onKeyDown={onKeyDown}
          placeholder="Search stocks by name or ticker"
          aria-label="Search stocks by name or ticker"
          role="combobox"
          aria-expanded={show}
          aria-controls="qt-search-list"
          aria-autocomplete="list"
          aria-activedescendant={show && results[active] ? `qt-search-${active}` : undefined}
          spellCheck={false}
          autoComplete="off"
          className="min-w-0 flex-1 bg-transparent px-2 py-1 text-amber outline-none placeholder:text-dim/60"
        />
        {!q && <kbd className="mr-1.5 border border-line px-1 text-[10px] text-dim/70">/</kbd>}
      </div>

      {show && (
        <div className="absolute left-0 top-full z-30 mt-1 w-[26rem] max-w-[90vw] border border-amber bg-panel shadow-2xl">
          {status ? (
            <div className="px-3 py-2 text-dim">{status}</div>
          ) : (
            <ul id="qt-search-list" ref={listRef} role="listbox" className="max-h-80 overflow-auto py-1">
              {results.map((r, i) => (
                <li
                  key={r.symbol}
                  id={`qt-search-${i}`}
                  role="option"
                  aria-selected={i === active}
                  onMouseDown={(e) => { e.preventDefault(); pick(r.symbol); }}
                  onMouseMove={() => setActive(i)}
                  className={`flex cursor-pointer items-center gap-3 px-3 py-1.5 ${i === active ? "bg-amber text-black" : ""}`}
                >
                  <span className="min-w-0 flex-1 truncate">{r.name || ticker(r.symbol)}</span>
                  {r.held && (
                    <span className={`text-[10px] tracking-widest ${i === active ? "text-black/70" : "text-up"}`}>HELD</span>
                  )}
                  <span className={`shrink-0 ${i === active ? "text-black" : "text-amber"}`}>{ticker(r.symbol)}</span>
                  <span className={`w-7 shrink-0 text-right text-[10px] tracking-widest ${i === active ? "text-black/70" : "text-dim"}`}>
                    {r.exchange}
                  </span>
                </li>
              ))}
            </ul>
          )}
          {!status && !online && (
            <div className="border-t border-line px-3 py-1 text-[10px] text-dim">
              Market search is offline. Showing stocks from your ledger only.
            </div>
          )}
        </div>
      )}
    </div>
  );
}
