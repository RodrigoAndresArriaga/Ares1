# Mission lifecycle HTTP routes — thin bridge to MissionLifecycleService
from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from app.schemas.mission import (
    AccidentTriggerResponse,
    MissionCreateRequest,
    MissionCreateResponse,
    MissionSession,
)
from app.schemas.replay import ReplayStartRequest, ReplayStartResponse
from app.services.mission_lifecycle_service import MissionLifecycleService

router = APIRouter(prefix="/missions", tags=["missions"])


def get_mission_lifecycle_service(request: Request) -> MissionLifecycleService:
    service = request.app.state.mission_lifecycle_service
    assert isinstance(service, MissionLifecycleService)
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
