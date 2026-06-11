"""FastAPI entrypoint for the Enterprise Customer Ops Agent project."""
from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from project.backend.api import routes_legacy
from project.backend.core.config import get_app_config
from project.backend.db.postgres import init_db


PROJECT_DIR = Path(__file__).resolve().parents[1]
FRONTEND_DIR = PROJECT_DIR / "frontend"


def create_app() -> FastAPI:
    app = FastAPI(title="Enterprise Customer Ops Agent API")

    @app.on_event("startup")
    async def _startup_init_db() -> None:
        init_db()

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def _no_cache(request, call_next):
        response = await call_next(request)
        path = request.url.path or ""
        if path == "/" or path.endswith((".html", ".js", ".css")):
            response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
            response.headers["Pragma"] = "no-cache"
            response.headers["Expires"] = "0"
        return response

    app.include_router(routes_legacy.router)

    if FRONTEND_DIR.exists():
        app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="static")

    return app


app = create_app()


if __name__ == "__main__":
    import uvicorn
    app_config = get_app_config()

    uvicorn.run(
        app,
        host=app_config.host,
        port=app_config.port,
    )
