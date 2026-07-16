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
from app.core.errors import (
    RetrievalIndexCorruptError,
    RetrievalIndexNotFoundError,
    RetrievalIndexStaleError,
    RetrievalIndexUnavailableError,
    register_exception_handlers,
)
from app.core.logging import configure_logging
from app.integrations.nvidia_nim import NvidiaNimClient
from app.schemas.embedding import EmbeddingModelDescriptor, RerankerModelDescriptor
from app.services.mission_lifecycle_service import MissionLifecycleService
from app.services.procedure_embedding_index_store import ProcedureEmbeddingIndexStore
from app.services.procedure_retrieval import ProcedureRetrievalService
from app.services.run_store import RunStore
from app.services.scenario_registry import ScenarioRegistry
from app.services.session_store import SessionStore
from app.services.simulation_service import SimulationService
from app.services.simulator_client import SimulatorClient
from app.services.telemetry_replay_service import TelemetryReplayService

logger = logging.getLogger("ares.main")


def _build_retrieval_resources(
    settings: Settings,
) -> tuple[
    NvidiaNimClient | None,
    ProcedureEmbeddingIndexStore,
    ProcedureRetrievalService | None,
]:
    store = ProcedureEmbeddingIndexStore(
        index_path=settings.procedure_embedding_index_path,
    )
    if settings.nvidia_api_key is None:
        logger.warning(
            "retrieval unavailable: ARES_NVIDIA_API_KEY not configured",
        )
        return None, store, None

    embed_model = EmbeddingModelDescriptor(
        provider="nvidia",
        model_id=settings.nvidia_embed_model_id,
        model_revision=settings.nvidia_embed_model_revision,
        dimensions=settings.nvidia_embed_dimensions,
    )
    rerank_model = RerankerModelDescriptor(
        provider="nvidia",
        model_id=settings.nvidia_rerank_model_id,
        model_revision=settings.nvidia_rerank_model_revision,
    )
    client = NvidiaNimClient(
        api_key=settings.nvidia_api_key.get_secret_value(),
        embed_base_url=settings.nvidia_embed_base_url,
        rerank_base_url=settings.nvidia_rerank_base_url,
        embed_model=embed_model,
        rerank_model=rerank_model,
        timeout_seconds=settings.nvidia_request_timeout_seconds,
        max_retries=settings.nvidia_max_retries,
        retry_backoff_seconds=settings.nvidia_retry_backoff_seconds,
    )
    try:
        index = store.load_compatible(expected_model=embed_model)
    except (
        RetrievalIndexNotFoundError,
        RetrievalIndexCorruptError,
        RetrievalIndexStaleError,
        RetrievalIndexUnavailableError,
    ) as exc:
        logger.warning(
            "retrieval unavailable: %s",
            exc.message,
        )
        client.close()
        return None, store, None

    service = ProcedureRetrievalService(
        index=index,
        provider=client.embedding_provider,
        reranker=client.reranker,
        rerank_candidate_count=settings.retrieval_rerank_candidate_count,
        max_top_k=settings.retrieval_max_top_k,
    )
    return client, store, service


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

    if getattr(app.state, "procedure_retrieval_service", None) is None:
        nim_client, index_store, retrieval_service = _build_retrieval_resources(
            settings,
        )
        app.state.nvidia_nim_client = nim_client
        app.state.procedure_embedding_index_store = index_store
        app.state.procedure_retrieval_service = retrieval_service
    elif getattr(app.state, "procedure_embedding_index_store", None) is None:
        app.state.procedure_embedding_index_store = ProcedureEmbeddingIndexStore(
            index_path=settings.procedure_embedding_index_path,
        )

    summary = await app.state.mission_lifecycle_service.reconcile_interrupted_sessions()
    logger.info(
        "startup reconciliation complete sessions_seen=%s "
        "triggering_recovered=%s unchanged=%s corrupt=%s conflicts=%s",
        summary.sessions_seen,
        summary.triggering_recovered,
        summary.unchanged,
        summary.corrupt,
        summary.conflicts,
    )

    if readiness.ready:
        logger.info("startup readiness ok reason_code=%s", readiness.reason_code)
    else:
        logger.warning(
            "startup readiness degraded reason_code=%s detail=%s",
            readiness.reason_code,
            readiness.detail,
        )
    try:
        yield
    finally:
        nim_client = getattr(app.state, "nvidia_nim_client", None)
        if nim_client is not None:
            nim_client.close()


def create_app(
    settings_override: Settings | None = None,
    *,
    simulation_service_override: SimulationService | None = None,
    procedure_retrieval_service_override: ProcedureRetrievalService | None = None,
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
    if procedure_retrieval_service_override is not None:
        app.state.procedure_retrieval_service = procedure_retrieval_service_override
    register_exception_handlers(app)
    app.include_router(api_router, prefix="/api")
    return app
