"""Engine configuration. Everything is driven by environment variables so the
Electron shell can configure the engine the same way on macOS and Windows."""
from __future__ import annotations

import os
from pathlib import Path

from platformdirs import user_data_dir

APP_NAME = "QuantTerminal"

DEFAULT_SETTINGS: dict[str, float | int | str] = {
    "benchmark": "^NSEI",
    "confidence": 0.95,
    "horizon_days": 1,
    "lookback_days": 252,
    "risk_free_rate": 0.065,
}

ALLOWED_BENCHMARKS = ("^NSEI", "^BSESN")


def data_dir() -> Path:
    """Per-user data folder: ~/Library/Application Support on macOS,
    %LOCALAPPDATA% on Windows. Override with QT_DATA_DIR."""
    override = os.environ.get("QT_DATA_DIR")
    path = Path(override) if override else Path(user_data_dir(APP_NAME, appauthor=False))
    path.mkdir(parents=True, exist_ok=True)
    return path


def database_url() -> str:
    return f"sqlite:///{(data_dir() / 'ledger.sqlite3').as_posix()}"


def host() -> str:
    return "127.0.0.1"  # never exposed beyond the local machine


def port() -> int:
    return int(os.environ.get("QT_PORT", "8765"))


def token() -> str | None:
    """Optional per-session token set by the Electron shell."""
    return os.environ.get("QT_TOKEN") or None


def feed_choice() -> str:
    return os.environ.get("QT_FEED", "auto").strip().lower()


def upstox_access_token() -> str | None:
    """Daily Upstox access token for the market data feed. Read from the
    environment only; it is never written to the database or logged."""
    return os.environ.get("QT_UPSTOX_ACCESS_TOKEN") or None
