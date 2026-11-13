"""Fallback feed: polls Yahoo Finance for delayed quotes. Used when no Upstox
access token is configured, so the live pipeline still works out of the box."""
from __future__ import annotations

import asyncio


def fetch_quotes(symbols: list[str]) -> dict[str, tuple[float, float | None]]:
    import yfinance as yf

    out: dict[str, tuple[float, float | None]] = {}
    for symbol in symbols:
        try:
            info = yf.Ticker(symbol).fast_info
            last, prev = info.last_price, info.previous_close
            if last:
                out[symbol] = (float(last), float(prev) if prev else None)
        except Exception:
            continue  # one bad symbol must not stop the rest
    return out


class YahooPollFeed:
    name = "yahoo-delayed"
    retry_seconds = 30.0

    def __init__(self, interval: float = 15.0, fetcher=fetch_quotes):
        self.interval = interval
        self.fetcher = fetcher

    async def run(self, hub) -> None:
        while True:
            symbols = await asyncio.to_thread(hub.held_symbols)
            if symbols:
                quotes = await asyncio.to_thread(self.fetcher, symbols)
                for symbol, (last, prev) in quotes.items():
                    hub.on_quote(symbol, last, prev)
                missing = [s for s in symbols if s not in quotes]
                if quotes:
                    hub.set_status("live", f"No quote for {', '.join(missing)}" if missing else "")
                else:
                    hub.set_status("error", "Yahoo returned no quotes")
            else:
                hub.set_status("live", "No holdings to price")
            await asyncio.sleep(self.interval)
