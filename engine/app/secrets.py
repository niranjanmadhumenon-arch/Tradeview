"""Where the Upstox token lives. It is kept in the operating system's
credential store (macOS Keychain, Windows Credential Manager) and never in the
database, logs or API responses. An environment variable overrides the store."""
from __future__ import annotations

import os
from typing import Protocol

SERVICE = "QuantTerminal"
ACCOUNT = "upstox-token"
ENV_NAMES = ("QT_UPSTOX_TOKEN", "QT_UPSTOX_ACCESS_TOKEN")


class TokenStore(Protocol):
    def get(self) -> str | None: ...
    def source(self) -> str | None: ...
    def set(self, token: str) -> None: ...
    def clear(self) -> None: ...


def _env_token() -> str | None:
    for name in ENV_NAMES:
        value = os.environ.get(name, "").strip()
        if value:
            return value
    return None


class KeyringStore:
    def _saved(self) -> str | None:
        try:
            import keyring

            return keyring.get_password(SERVICE, ACCOUNT) or None
        except Exception:
            return None

    def get(self) -> str | None:
        return _env_token() or self._saved()

    def source(self) -> str | None:
        if _env_token():
            return "environment"
        return "keychain" if self._saved() else None

    def set(self, token: str) -> None:
        import keyring

        try:
            keyring.set_password(SERVICE, ACCOUNT, token)
        except Exception as exc:
            raise RuntimeError(f"Could not save to the system credential store: {exc}") from exc

    def clear(self) -> None:
        import keyring

        try:
            keyring.delete_password(SERVICE, ACCOUNT)
        except Exception:
            pass  # nothing saved


class MemoryStore:
    """In-process store for tests and for running with the feed switched off."""

    def __init__(self, token: str | None = None):
        self._token = token

    def get(self) -> str | None:
        return self._token

    def source(self) -> str | None:
        return "memory" if self._token else None

    def set(self, token: str) -> None:
        self._token = token

    def clear(self) -> None:
        self._token = None
