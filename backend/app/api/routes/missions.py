# Mission lifecycle HTTP routes — thin bridge to MissionLifecycleService
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Header, Request
from fastapi.responses import StreamingResponse

from app.api.sse import ReplayStreamLimiter, generate_replay_stream
from app.core.errors import PlanningServiceUnavailableError, ReplayStreamLimitError
from app.schemas.mission import (
    AccidentTriggerResponse,
    MissionCreateRequest,
    MissionCreateResponse,
    MissionSession,
)
from app.schemas.planning_validation import PlanningSimulationResponse
from app.schemas.replay import (
    CurrentTelemetryResponse,
    ReplayStartRequest,
    ReplayStartResponse,
)
from app.services.mission_lifecycle_service import MissionLifecycleService
from app.services.mission_plan_simulation_service import MissionPlanSimulationService
from app.services.telemetry_replay_service import TelemetryReplayService

logger = logging.getLogger("ares.missions")

router = APIRouter(prefix="/missions", tags=["missions"])


def get_mission_lifecycle_service(request: Request) -> MissionLifecycleService:
    service = request.app.state.mission_lifecycle_service
    assert isinstance(service, MissionLifecycleService)
    return service


def get_telemetry_replay_service(request: Request) -> TelemetryReplayService:
    service = request.app.state.telemetry_replay_service
    assert isinstance(service, TelemetryReplayService)
    return service


def get_replay_stream_limiter(request: Request) -> ReplayStreamLimiter:
    limiter = request.app.state.replay_stream_limiter
    assert isinstance(limiter, ReplayStreamLimiter)
    return limiter


def get_mission_plan_simulation_service(
    request: Request,
) -> MissionPlanSimulationService:
    service = getattr(request.app.state, "mission_plan_simulation_service", None)
    if service is None:
        raise PlanningServiceUnavailableError(
            "Mission planning service is unavailable",
        )
    assert isinstance(service, MissionPlanSimulationService)
    return service


@router.post(
    "",
    response_model=MissionCreateResponse,
    status_code=201,
    summary="Create a mission session",
    description=(
        "Validate a registered scenario and create a READY mission session. "
        "Does not run the simulator or expose numerical telemetry."
    ),
)
def create_mission(
    body: MissionCreateRequest,
    service: MissionLifecycleService = Depends(get_mission_lifecycle_service),
) -> MissionCreateResponse:
    session = service.create_session(body)
    return MissionCreateResponse(session=session)


@router.get(
    "/{session_id}",
    response_model=MissionSession,
    status_code=200,
    summary="Read a mission session",
    description=(
        "Return the exact persisted mission session without mutating state "
        "or calculating replay position."
    ),
)
def get_mission(
    session_id: str,
    service: MissionLifecycleService = Depends(get_mission_lifecycle_service),
) -> MissionSession:
    return service.get_session(session_id)


@router.post(
    "/{session_id}/accident",
    response_model=AccidentTriggerResponse,
    status_code=200,
    summary="Trigger the registered accident",
    description=(
        "Require READY, run one baseline simulation through the lifecycle "
        "service, and persist BASELINE_READY. Simulator FAILURE and REJECTED "
        "remain HTTP 200."
    ),
)
async def trigger_accident(
    session_id: str,
    service: MissionLifecycleService = Depends(get_mission_lifecycle_service),
) -> AccidentTriggerResponse:
    return await service.trigger_accident(session_id)


@router.post(
    "/{session_id}/replay",
    response_model=ReplayStartResponse,
    status_code=200,
    summary="Start or restart telemetry replay",
    description=(
        "Start replay from BASELINE_READY, or restart from COMPLETED when "
        "restart=true. Returns future stream and telemetry paths without "
        "reading telemetry or running the simulator."
    ),
)
async def start_replay(
    session_id: str,
    body: ReplayStartRequest,
    service: MissionLifecycleService = Depends(get_mission_lifecycle_service),
) -> ReplayStartResponse:
    session = await service.start_replay(session_id, body)
    return ReplayStartResponse(
        session=session,
        stream_path=f"/api/missions/{session.session_id}/stream",
        current_telemetry_path=f"/api/missions/{session.session_id}/telemetry",
    )


@router.get(
    "/{session_id}/telemetry",
    response_model=CurrentTelemetryResponse,
    status_code=200,
    summary="Read current replay telemetry",
    description=(
        "Return the exact currently due telemetry sample for a REPLAYING or "
        "COMPLETED mission. Does not interpolate or alter nested samples."
    ),
)
async def get_current_telemetry(
    session_id: str,
    service: TelemetryReplayService = Depends(get_telemetry_replay_service),
) -> CurrentTelemetryResponse:
    return await service.get_current_telemetry(session_id)


@router.post(
    "/{session_id}/plan",
    response_model=PlanningSimulationResponse,
    status_code=200,
    summary="Generate grounded candidate and simulate",
    description=(
        "Require REPLAYING or COMPLETED, generate one evidence-grounded "
        "candidate through MissionPlanningService, simulate it once through "
        "SimulationService, and persist validation artifacts. No request body. "
        "STABILIZED, FAILURE, and REJECTED are valid HTTP 200 results."
    ),
)
async def plan_mission(
    session_id: str,
    service: MissionPlanSimulationService = Depends(get_mission_plan_simulation_service),
) -> PlanningSimulationResponse:
    return await service.generate_and_simulate(session_id)


@router.get(
    "/{session_id}/stream",
    status_code=200,
    summary="Stream telemetry replay as Server-Sent Events",
    description=(
        "Ordered text/event-stream of exact telemetry samples and a final "
        "complete event. Supports Last-Event-ID resume without persisting a "
        "client cursor."
    ),
    responses={
        200: {
            "content": {
                "text/event-stream": {
                    "schema": {"type": "string"},
                },
            },
        },
    },
)
async def stream_replay(
    request: Request,
    session_id: str,
    last_event_id: str | None = Header(None, alias="Last-Event-ID"),
    service: TelemetryReplayService = Depends(get_telemetry_replay_service),
    limiter: ReplayStreamLimiter = Depends(get_replay_stream_limiter),
) -> StreamingResponse:
    lease = await limiter.try_acquire()
    if lease is None:
        logger.warning(
            "replay_stream_rejected session_id=%s code=REPLAY_STREAM_LIMIT active=%s",
            session_id,
            limiter.active_count,
        )
        raise ReplayStreamLimitError(session_id=session_id)

    logger.info(
        "replay_stream_accepted session_id=%s last_event_id=%s active=%s",
        session_id,
        last_event_id,
        limiter.active_count,
    )

    try:
        initial_batch = await service.get_due_events(
            session_id,
            last_event_id=last_event_id,
        )
    except Exception:
        await lease.release()
        raise

    settings = request.app.state.settings
    try:
        return StreamingResponse(
            generate_replay_stream(
                request=request,
                service=service,
                lease=lease,
                session_id=session_id,
                initial_batch=initial_batch,
                initial_last_event_id=last_event_id,
                heartbeat_seconds=settings.sse_heartbeat_seconds,
            ),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "X-Accel-Buffering": "no",
                "Connection": "keep-alive",
            },
        )
    except Exception:
        await lease.release()
        raise
