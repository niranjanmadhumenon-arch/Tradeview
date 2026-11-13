from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import config
from app.api.routes import router
from app.db.models import make_sessionmaker
from app.market.live import Feed, LiveHub
from app.ws.routes import router as ws_router


def create_app(db_url: str | None = None, token: str | None = None, feed: Feed | None = None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        if app.state.hub:
            await app.state.hub.start()
        yield
        if app.state.hub:
            await app.state.hub.stop()

    app = FastAPI(title="Quant Terminal Engine", version="0.2.0", lifespan=lifespan)
    app.state.sessionmaker = make_sessionmaker(db_url or config.database_url())
    app.state.token = token if token is not None else config.token()
    app.state.hub = LiveHub(app.state.sessionmaker, feed) if feed else None
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
    app.include_router(ws_router)
    return app
