# FastAPI application factory and lifespan readiness
from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.router import api_router
from app.api.routes.health import evaluate_readiness
from app.core.config import Settings, get_settings

logger = logging.getLogger("ares.main")


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings: Settings = app.state.settings
    readiness = evaluate_readiness(settings)
    app.state.startup_readiness = readiness
    if readiness.ready:
        logger.info("startup readiness ok reason_code=%s", readiness.reason_code)
    else:
        logger.warning(
            "startup readiness degraded reason_code=%s detail=%s",
            readiness.reason_code,
            readiness.detail,
        )
    yield


def create_app(settings_override: Settings | None = None) -> FastAPI:
    settings = settings_override if settings_override is not None else get_settings()
    app = FastAPI(
        title="ARES-1 Phase 1 Backend",
        version="0.1.0",
        description=(
            "Phase 1 FastAPI bridge for the frozen C++ simulator. "
            "Provides configuration validation and health readiness only."
        ),
        lifespan=_lifespan,
    )
    app.state.settings = settings
    app.include_router(api_router, prefix="/api")
    return app
