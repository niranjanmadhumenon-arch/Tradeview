from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import config
from app.api.routes import router
from app.db.models import make_sessionmaker


def create_app(db_url: str | None = None, token: str | None = None) -> FastAPI:
    app = FastAPI(title="Quant Terminal Engine", version="0.1.0")
    app.state.sessionmaker = make_sessionmaker(db_url or config.database_url())
    app.state.token = token if token is not None else config.token()
    app.add_middleware(
        CORSMiddleware,
        allow_origin_regex=r"^(http://(localhost|127\.0\.0\.1)(:\d+)?|file://|null)$",
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/health")
    def health():
        return {"status": "ok", "version": app.version}

    app.include_router(router)
    return app
