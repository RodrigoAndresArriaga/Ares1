# POST /api/sim/run and GET /api/sim/result — thin bridges to services
from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from app.schemas.api import SimulationRunRequest, SimulationRunResponse
from app.schemas.run import PersistedRunResultResponse
from app.services.run_store import RunStore
from app.services.simulation_service import SimulationService

router = APIRouter(prefix="/sim", tags=["simulation"])


def get_simulation_service(request: Request) -> SimulationService:
    service = request.app.state.simulation_service
    assert isinstance(service, SimulationService)
    return service


def get_run_store(request: Request) -> RunStore:
    store = request.app.state.run_store
    assert isinstance(store, RunStore)
    return store


@router.post(
    "/run",
    response_model=SimulationRunResponse,
    status_code=200,
    summary="Run a registered scenario simulation",
    description=(
        "Execute one registered scenario with an optional recovery plan. "
        "Mission outcomes FAILURE, STABILIZED, and REJECTED are valid "
        "simulation results and always return HTTP 200. Only infrastructure "
        "failures use non-200 status codes."
    ),
)
async def run_simulation(
    body: SimulationRunRequest,
    service: SimulationService = Depends(get_simulation_service),
) -> SimulationRunResponse:
    return await service.run_simulation(body)


@router.get(
    "/result/{run_id}",
    response_model=PersistedRunResultResponse,
    status_code=200,
    summary="Retrieve a persisted simulator result",
    description=(
        "Read an existing run's metadata and result.json without executing "
        "the simulator. Outcomes FAILURE, STABILIZED, and REJECTED remain "
        "HTTP 200 when artifacts are valid."
    ),
)
def get_persisted_result(
    run_id: str,
    run_store: RunStore = Depends(get_run_store),
) -> PersistedRunResultResponse:
    metadata = run_store.read_metadata(run_id)
    result = run_store.read_result(run_id)
    return PersistedRunResultResponse(
        run_id=run_id,
        metadata=metadata,
        result=result,
    )
