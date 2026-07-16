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
from app.schemas.planner import PlannerModelMetadata
from app.services.mission_lifecycle_service import MissionLifecycleService
from app.services.mission_plan_simulation_service import MissionPlanSimulationService
from app.services.mission_planning_service import MissionPlanningService
from app.services.mission_retrieval_query import MissionRetrievalQueryBuilder
from app.services.planner_candidate_validator import PlannerCandidateValidator
from app.services.planner_prompt import PlannerPromptBuilder
from app.services.planner_provider import NvidiaNimPlannerProvider, PlannerProvider
from app.services.planning_attempt_store import PlanningAttemptStore
from app.services.planning_validation_store import PlanningValidationStore
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


def _build_planning_resources(
    settings: Settings,
    *,
    session_store: SessionStore,
    run_store: RunStore,
    telemetry_replay_service: TelemetryReplayService,
    procedure_retrieval_service: ProcedureRetrievalService | None,
    nvidia_nim_client: NvidiaNimClient | None,
    planner_provider_override: PlannerProvider | None,
    simulation_service: SimulationService,
) -> tuple[
    PlanningAttemptStore,
    PlanningValidationStore,
    MissionPlanningService,
    MissionPlanSimulationService,
] | None:
    if settings.nvidia_api_key is None and planner_provider_override is None:
        logger.warning(
            "planning unavailable: ARES_NVIDIA_API_KEY not configured",
        )
        return None
    if procedure_retrieval_service is None:
        logger.warning(
            "planning unavailable: procedure retrieval service is unavailable",
        )
        return None
    if planner_provider_override is None and nvidia_nim_client is None:
        logger.warning(
            "planning unavailable: NVIDIA NIM client is unavailable",
        )
        return None

    attempt_store = PlanningAttemptStore(settings.planning_attempts_dir)
    validation_store = PlanningValidationStore(settings.planning_attempts_dir)
    retrieval_query_builder = MissionRetrievalQueryBuilder(
        max_query_characters=settings.planner_retrieval_query_max_characters,
    )
    model_metadata = PlannerModelMetadata(
        provider="nvidia",
        model_id=settings.nvidia_planner_model_id,
        model_revision=settings.nvidia_planner_model_revision,
    )
    prompt_builder = PlannerPromptBuilder(
        model_metadata=model_metadata,
        max_prompt_characters=settings.planner_max_prompt_characters,
    )
    if planner_provider_override is not None:
        planner_provider = planner_provider_override
    else:
        assert nvidia_nim_client is not None
        planner_provider = NvidiaNimPlannerProvider(
            client=nvidia_nim_client,
            model_metadata=model_metadata,
            temperature=settings.nvidia_planner_temperature,
            max_tokens=settings.nvidia_planner_max_tokens,
        )
    candidate_validator = PlannerCandidateValidator()
    mission_planning_service = MissionPlanningService(
        session_store=session_store,
        run_store=run_store,
        telemetry_replay_service=telemetry_replay_service,
        procedure_retrieval_service=procedure_retrieval_service,
        planner_prompt_builder=prompt_builder,
        planner_provider=planner_provider,
        candidate_validator=candidate_validator,
        attempt_store=attempt_store,
        retrieval_query_builder=retrieval_query_builder,
        retrieval_top_k=settings.planner_retrieval_top_k,
    )
    mission_plan_simulation_service = MissionPlanSimulationService(
        mission_planning_service=mission_planning_service,
        planning_attempt_store=attempt_store,
        validation_store=validation_store,
        run_store=run_store,
        simulation_service=simulation_service,
    )
    return (
        attempt_store,
        validation_store,
        mission_planning_service,
        mission_plan_simulation_service,
    )


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

    planner_provider_override = getattr(app.state, "planner_provider_override", None)
    if getattr(app.state, "mission_plan_simulation_service", None) is None:
        planning_bundle = _build_planning_resources(
            settings,
            session_store=session_store,
            run_store=app.state.run_store,
            telemetry_replay_service=app.state.telemetry_replay_service,
            procedure_retrieval_service=app.state.procedure_retrieval_service,
            nvidia_nim_client=getattr(app.state, "nvidia_nim_client", None),
            planner_provider_override=planner_provider_override,
            simulation_service=app.state.simulation_service,
        )
        if planning_bundle is None:
            app.state.planning_attempt_store = None
            app.state.planning_validation_store = None
            app.state.mission_planning_service = None
            app.state.mission_plan_simulation_service = None
        else:
            (
                app.state.planning_attempt_store,
                app.state.planning_validation_store,
                app.state.mission_planning_service,
                app.state.mission_plan_simulation_service,
            ) = planning_bundle

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
    planner_provider_override: PlannerProvider | None = None,
    mission_plan_simulation_service_override: MissionPlanSimulationService | None = None,
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
    if planner_provider_override is not None:
        app.state.planner_provider_override = planner_provider_override
    if mission_plan_simulation_service_override is not None:
        app.state.mission_plan_simulation_service = mission_plan_simulation_service_override
    register_exception_handlers(app)
    app.include_router(api_router, prefix="/api")
    return app
