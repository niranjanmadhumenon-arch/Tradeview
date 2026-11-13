# Quant Terminal

A read-only desktop quant terminal: an Electron + React front end over a local
Python engine (FastAPI + SQLite) that computes all risk metrics itself. It has
no order routing of any kind.

Runs on macOS and Windows. All commands below are the same on both.

## Requirements

- Node.js 20 or newer
- Python 3.11 or newer (on Windows, install from python.org so the `py` launcher exists)

## Run the app

```bash
npm install            # once: UI and Electron dependencies
npm run engine:setup   # once: Python engine
npm run dev            # desktop app with hot reload
npm start              # desktop app from a production build of the UI
```

The desktop app starts the engine itself on a free local port and stops it on
quit. Use **IMPORT CSV** in the ribbon to load an Upstox trade book.

## Engine on its own

```bash
npm run engine:setup   # create engine/.venv and install dependencies
npm run engine:test    # run the test suite
npm run engine:dev     # start the engine on http://127.0.0.1:8765
```

Interactive API docs: http://127.0.0.1:8765/docs

| Variable | Purpose | Default |
| --- | --- | --- |
| `QT_PORT` | engine port | `8765` |
| `QT_TOKEN` | if set, every `/api` call must send it as `X-QT-Token` | unset |
| `QT_DATA_DIR` | where the SQLite ledger lives | per-user app data folder |
| `QT_FEED` | live prices: `auto`, `upstox`, `yahoo` or `off` | `auto` |
| `QT_UPSTOX_ACCESS_TOKEN` | Upstox access token for the live feed (expires daily) | unset |

## Live prices

The engine streams quotes and a mark-to-market snapshot over
`ws://127.0.0.1:<port>/ws/ticks`. With `QT_FEED=auto` it uses the Upstox
Market Data Feed V3 when `QT_UPSTOX_ACCESS_TOKEN` is set, and otherwise falls
back to delayed Yahoo quotes polled every 15 seconds (shown as DELAYED in the
ribbon). Set the token in the shell before `npm run dev`; it is read from the
environment only and never stored. Risk metrics stay based on daily closes.

## Status

- [x] Engine: Upstox trade-book import, positions with corporate actions,
      price history cache, risk metrics, settings
- [x] Electron shell (starts and stops the engine, sandboxed renderer)
- [x] React workspace (dockable panes, TradingView chart, risk inspector,
      command palette)
- [x] Live prices over WebSocket (Upstox feed adapter, delayed Yahoo fallback)
- [ ] In-app Upstox login (the access token is set by hand for now)
- [ ] Gemini hedging memo
- [ ] Packaging (macOS .dmg, Windows installer)

Metric formulas: [docs/metrics.md](docs/metrics.md)
