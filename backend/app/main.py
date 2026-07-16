# FastAPI application factory and lifespan readiness
from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.router import api_router
from app.api.routes.health import evaluate_readiness
from app.api.sse import ReplayStreamLimiter
from app.core.config import Settings, get_settings
from app.core.errors import register_exception_handlers
from app.core.logging import configure_logging
from app.services.mission_lifecycle_service import MissionLifecycleService
from app.services.run_store import RunStore
from app.services.scenario_registry import ScenarioRegistry
from app.services.session_store import SessionStore
from app.services.simulation_service import SimulationService
from app.services.simulator_client import SimulatorClient
from app.services.telemetry_replay_service import TelemetryReplayService

logger = logging.getLogger("ares.main")


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings: Settings = app.state.settings
    readiness = evaluate_readiness(settings)
    app.state.startup_readiness = readiness

    if getattr(app.state, "simulation_service", None) is None:
        registry = ScenarioRegistry(settings.scenario_dir)
        run_store = RunStore(settings.runs_dir)
        simulator_client = SimulatorClient(settings)
        app.state.scenario_registry = registry
        app.state.run_store = run_store
        app.state.simulator_client = simulator_client
        app.state.simulation_service = SimulationService(
            scenario_registry=registry,
            run_store=run_store,
            simulator_client=simulator_client,
        )

    if getattr(app.state, "scenario_registry", None) is None:
        app.state.scenario_registry = ScenarioRegistry(settings.scenario_dir)
    if getattr(app.state, "run_store", None) is None:
        app.state.run_store = RunStore(settings.runs_dir)

    session_store = SessionStore(settings.sessions_dir)
    app.state.session_store = session_store
    app.state.mission_lifecycle_service = MissionLifecycleService(
        scenario_registry=app.state.scenario_registry,
        session_store=session_store,
        simulation_service=app.state.simulation_service,
        replay_default_interval_ms=settings.replay_default_interval_ms,
        replay_min_interval_ms=settings.replay_min_interval_ms,
        replay_max_interval_ms=settings.replay_max_interval_ms,
    )
    app.state.telemetry_replay_service = TelemetryReplayService(
        session_store=session_store,
        run_store=app.state.run_store,
    )
    app.state.replay_stream_limiter = ReplayStreamLimiter(
        capacity=settings.max_replay_streams,
    )

    if readiness.ready:
        logger.info("startup readiness ok reason_code=%s", readiness.reason_code)
    else:
        logger.warning(
            "startup readiness degraded reason_code=%s detail=%s",
            readiness.reason_code,
            readiness.detail,
        )
    yield


def create_app(
    settings_override: Settings | None = None,
    *,
    simulation_service_override: SimulationService | None = None,
) -> FastAPI:
    settings = settings_override if settings_override is not None else get_settings()
    configure_logging(settings)
    app = FastAPI(
        title="ARES-1 Phase 1 Backend",
        version="0.1.0",
        description=(
            "Phase 1 FastAPI bridge for the frozen C++ simulator. "
            "Provides configuration validation, health readiness, and "
            "POST /api/sim/run. Mission FAILURE and REJECTED are valid "
            "HTTP 200 results."
        ),
        lifespan=_lifespan,
    )
    app.state.settings = settings
    if simulation_service_override is not None:
        app.state.simulation_service = simulation_service_override
    register_exception_handlers(app)
    app.include_router(api_router, prefix="/api")
    return app
