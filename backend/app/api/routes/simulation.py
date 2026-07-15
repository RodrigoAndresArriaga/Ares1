# POST /api/sim/run — thin bridge to SimulationService
from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from app.schemas.api import SimulationRunRequest, SimulationRunResponse
from app.services.simulation_service import SimulationService

router = APIRouter(prefix="/sim", tags=["simulation"])


def get_simulation_service(request: Request) -> SimulationService:
    service = request.app.state.simulation_service
    assert isinstance(service, SimulationService)
    return service


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
