"""Entry point: `python -m app.server`. Also the target for PyInstaller later."""
from __future__ import annotations

import uvicorn

from app import config
from app.main import create_app

app = create_app()


def main() -> None:
    uvicorn.run(app, host=config.host(), port=config.port(), log_level="info")


if __name__ == "__main__":
    main()
