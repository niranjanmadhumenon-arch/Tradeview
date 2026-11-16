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
quit. Use **IMPORT CSV** in the ribbon to load an Upstox trade book. The search
bar in the ribbon finds any NSE or BSE stock by company name or ticker (press
`/` to focus it); without a network it still searches the stocks in your ledger.

## Build an installer

```bash
npm run package        # .dmg on macOS, .exe installer on Windows, in release/
```

Each installer has to be built on its own system, because the Python engine is
frozen into a native binary (with PyInstaller) and bundled into the app. The
installed app needs neither Python nor Node. `.github/workflows/release.yml`
builds both on GitHub (run it from the Actions tab or push a `v*` tag).

The builds are not code-signed. On macOS, open the app the first time with
right-click > Open; on Windows, choose "More info" > "Run anyway" on the
SmartScreen prompt. Signing needs an Apple Developer ID and a Windows
code-signing certificate. The first launch after installing can take up to a
minute while the system checks the engine; later launches take a second or two.

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
| `QT_UPSTOX_TOKEN` | Upstox token; overrides the one saved in the app | unset |
| `QT_GEMINI_API_KEY` | Gemini API key; overrides the one saved in the app | unset |
| `QT_GEMINI_MODEL` | Gemini model used for memos | `gemini-3.8-flash` |

## Live prices

The engine streams quotes and a mark-to-market snapshot over
`ws://127.0.0.1:<port>/ws/ticks`. Risk metrics stay based on daily closes.

**Upstox (real time).** Click **UPSTOX** in the ribbon and paste an Upstox
*Analytics Token*. It is read-only, valid for one year, and cannot place or
change orders, which matches this app's no-execution rule. Create it in the
Upstox Developer Apps page under the Analytics tab. The token is saved in the
system credential store (macOS Keychain, Windows Credential Manager), never in
the database, and the feed switches to Upstox straight away. A daily OAuth
access token also works but has to be replaced every day.

**Yahoo (delayed).** With no token, quotes are polled from Yahoo every 15
seconds and the ribbon shows DELAYED. `QT_FEED=upstox` disables this fallback.

The engine only ever sends GET requests to Upstox: the feed authorize call and
the public instrument list.

## AI insight

The **AI INSIGHT** tab writes a short hedging memo with Google Gemini. Paste a
Gemini API key from Google AI Studio once; it is saved in the system keychain.

- Gemini receives only a small JSON of figures the engine already computed and
  rounded (weights, beta, VaR, ratios, drawdown). No trades, quantities or
  costs. "Show data sent to Gemini" in the pane shows the exact content.
- The prompt forbids calculations, hedge sizes and order instructions. After the
  memo returns, every number in it is checked against the figures sent, and any
  that do not match are flagged in the pane as unverified.
- Memos are stored locally with the data that produced them.

## Status

- [x] Engine: Upstox trade-book import, positions with corporate actions,
      price history cache, risk metrics, settings
- [x] Electron shell (starts and stops the engine, sandboxed renderer)
- [x] React workspace (dockable panes, TradingView chart, risk inspector,
      command palette)
- [x] Live prices over WebSocket (Upstox feed adapter, delayed Yahoo fallback)
- [x] Upstox token setup in the app, stored in the system keychain
- [x] Gemini hedging memo with a check on every number it quotes
- [x] Packaging: macOS .dmg built and tested; Windows installer configured but
      not yet built or tested

Metric formulas: [docs/metrics.md](docs/metrics.md)
