# unit tests for HTTP envelope schemas
from __future__ import annotations

import copy
from typing import Any

import pytest
from app.schemas.api import (
    ErrorCode,
    ErrorResponse,
    HealthResponse,
    SimulationRunRequest,
    SimulationRunResponse,
)
from app.schemas.result import SimulationResult
from pydantic import ValidationError


def test_baseline_request() -> None:
    req = SimulationRunRequest.model_validate(
        {"scenario_id": "mars_hab_atmosphere_solar_failure"}
    )
    assert req.plan is None


def test_request_with_inline_plan(sample_plan_data: Any) -> None:
    req = SimulationRunRequest.model_validate(
        {
            "scenario_id": "mars_hab_atmosphere_solar_failure",
            "plan": sample_plan_data,
        }
    )
    assert req.plan is not None
    assert req.plan.plan_id == "sample_plan"


def test_request_rejects_path_fields() -> None:
    for field in ("scenario_path", "plan_path", "output_path", "simulator_path", "command"):
        with pytest.raises(ValidationError):
            SimulationRunRequest.model_validate(
                {"scenario_id": "mars_hab_atmosphere_solar_failure", field: "/tmp/x"}
            )


def test_response_wraps_strict_result(baseline_result_data: Any) -> None:
    result = SimulationResult.model_validate(baseline_result_data)
    response = SimulationRunResponse(
        run_id="run-1",
        duration_ms=10,
        result=result,
    )
    dumped = response.model_dump(mode="json")
    assert dumped["run_id"] == "run-1"
    assert dumped["result"] == baseline_result_data
    assert "scenario_path" not in dumped


def test_health_response() -> None:
    ok = HealthResponse(status="ok", simulator_ready=True, message="ready")
    degraded = HealthResponse(
        status="degraded", simulator_ready=False, message="simulator binary missing"
    )
    assert ok.simulator_ready is True
    assert degraded.status == "degraded"


def test_error_response_optional_run_id() -> None:
    err = ErrorResponse(
        code=ErrorCode.SIMULATOR_UNAVAILABLE,
        message="Simulator executable is not ready",
    )
    assert err.run_id is None
    with_run = ErrorResponse(
        code=ErrorCode.SIMULATOR_TIMEOUT,
        message="Timed out",
        run_id="run-9",
    )
    assert with_run.run_id == "run-9"


def test_error_response_forbids_extra() -> None:
    with pytest.raises(ValidationError):
        ErrorResponse.model_validate(
            {
                "code": "SIMULATOR_UNAVAILABLE",
                "message": "x",
                "stack_trace": "nope",
            }
        )


def test_request_with_invalid_plan_inline(invalid_plan_data: Any) -> None:
    req = SimulationRunRequest.model_validate(
        {
            "scenario_id": "mars_hab_atmosphere_solar_failure",
            "plan": copy.deepcopy(invalid_plan_data),
        }
    )
    assert req.plan is not None
    assert req.plan.plan_id == "invalid_plan"
