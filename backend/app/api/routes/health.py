# GET /api/health — liveness vs simulator readiness
from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from app.core.config import Settings
from app.schemas.api import HealthResponse

logger = logging.getLogger("ares.health")

RELEASE_SCENARIO_FILENAME = "mars_hab_atmosphere_solar_failure.json"

router = APIRouter()


@dataclass(frozen=True, slots=True)
class ReadinessResult:
    ready: bool
    reason_code: str
    detail: str


# probe runs directory writability without leaving residual files
def _runs_dir_writable(path: Path) -> bool:
    if not path.exists() or not path.is_dir():
        return False
    probe = path / f".ares_health_probe_{uuid.uuid4().hex}"
    try:
        probe.write_text("ok", encoding="utf-8")
    except OSError:
        return False
    finally:
        probe.unlink(missing_ok=True)
    return True


# cheap filesystem readiness checks (no subprocess, no scenario parse)
def evaluate_readiness(settings: Settings) -> ReadinessResult:
    if not settings.sim_binary.exists() or not settings.sim_binary.is_file():
        return ReadinessResult(
            ready=False,
            reason_code="SIM_BINARY_MISSING",
            detail=f"simulator binary missing or not a file: {settings.sim_binary}",
        )

    if not settings.scenario_dir.exists() or not settings.scenario_dir.is_dir():
        return ReadinessResult(
            ready=False,
            reason_code="SCENARIO_DIR_MISSING",
            detail=f"scenario directory missing: {settings.scenario_dir}",
        )

    release_scenario = settings.scenario_dir / RELEASE_SCENARIO_FILENAME
    if not release_scenario.exists() or not release_scenario.is_file():
        return ReadinessResult(
            ready=False,
            reason_code="SCENARIO_MISSING",
            detail=f"release scenario missing: {release_scenario}",
        )

    if not _runs_dir_writable(settings.runs_dir):
        return ReadinessResult(
            ready=False,
            reason_code="RUNS_NOT_WRITABLE",
            detail=f"runs directory missing or not writable: {settings.runs_dir}",
        )

    return ReadinessResult(
        ready=True,
        reason_code="READY",
        detail="all Phase 1 simulator prerequisites available",
    )


def readiness_to_health_response(
    result: ReadinessResult,
) -> tuple[int, HealthResponse]:
    if result.ready:
        return 200, HealthResponse(
            status="ok",
            simulator_ready=True,
            message="ready",
        )
    return 503, HealthResponse(
        status="degraded",
        simulator_ready=False,
        message="simulator prerequisites unavailable",
    )


@router.get("/health", response_model=HealthResponse)
def get_health(request: Request) -> HealthResponse | JSONResponse:
    settings: Settings = request.app.state.settings
    result = evaluate_readiness(settings)
    status_code, body = readiness_to_health_response(result)
    if not result.ready:
        logger.warning(
            "health not ready reason_code=%s detail=%s",
            result.reason_code,
            result.detail,
        )
    if status_code == 200:
        return body
    return JSONResponse(status_code=status_code, content=body.model_dump(mode="json"))
