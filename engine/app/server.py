"""Entry point: `python -m app.server`. Also the target for PyInstaller later."""
from __future__ import annotations

import uvicorn

from app import config
from app.main import create_app
from app.secrets import KeyringStore


def make_feed(store):
    """QT_FEED = auto (default) | upstox | yahoo | off. With `auto`, Upstox is
    used when a token is saved, otherwise delayed Yahoo quotes."""
    choice = config.feed_choice()
    token = store.get()
    if choice == "off":
        return None
    if choice == "upstox" or (choice == "auto" and token):
        from app.market.feeds.upstox import UpstoxFeed

        return UpstoxFeed(token or "", config.data_dir())
    from app.market.feeds.yahoo_poll import YahooPollFeed

    return YahooPollFeed()


app = create_app(token_store=KeyringStore(), feed_factory=make_feed)


def main() -> None:
    uvicorn.run(app, host=config.host(), port=config.port(), log_level="info")


if __name__ == "__main__":
    main()
