# HTTP status mapping and safe ErrorResponse tests
from __future__ import annotations

import logging
from typing import Any
from unittest.mock import AsyncMock

import pytest
from app.core.config import clear_settings_cache
from app.core.errors import (
    ArtifactStorageError,
    ScenarioNotFoundError,
    SimulatorExecutionError,
    SimulatorOutputMissingError,
    SimulatorOutputParseError,
    SimulatorOutputValidationError,
    SimulatorTimeoutError,
    SimulatorUnavailableError,
)
from app.main import create_app
from app.schemas.api import ErrorCode, SimulationRunResponse
from app.schemas.result import SimulationResult
from app.services.simulation_service import SimulationService
from fastapi.testclient import TestClient


@pytest.fixture(autouse=True)
def _clear_settings_cache() -> Any:
    clear_settings_cache()
    yield
    clear_settings_cache()


def _client_with_service(service: SimulationService, settings: Any) -> TestClient:
    app = create_app(
        settings_override=settings,
        simulation_service_override=service,
    )
    return TestClient(app, raise_server_exceptions=False)


@pytest.mark.parametrize(
    "exc,status,code",
    [
        (ScenarioNotFoundError(scenario_id="x"), 404, "SCENARIO_NOT_FOUND"),
        (SimulatorUnavailableError(), 503, "SIMULATOR_UNAVAILABLE"),
        (SimulatorTimeoutError(run_id="r1"), 504, "SIMULATOR_TIMEOUT"),
        (SimulatorExecutionError(run_id="r1"), 502, "SIMULATOR_EXECUTION_FAILED"),
        (SimulatorOutputMissingError(run_id="r1"), 502, "SIMULATOR_OUTPUT_MISSING"),
        (
            SimulatorOutputParseError(run_id="r1"),
            502,
            "SIMULATOR_OUTPUT_INVALID_JSON",
        ),
        (
            SimulatorOutputValidationError(run_id="r1"),
            502,
            "SIMULATOR_OUTPUT_CONTRACT_ERROR",
        ),
        (ArtifactStorageError(run_id="r1"), 500, "ARTIFACT_STORAGE_ERROR"),
    ],
)
def test_typed_error_http_mapping(
    valid_settings: Any,
    exc: Exception,
    status: int,
    code: str,
) -> None:
    service = AsyncMock(spec=SimulationService)
    service.run_simulation = AsyncMock(side_effect=exc)
    client = _client_with_service(service, valid_settings)
    response = client.post(
        "/api/sim/run",
        json={"scenario_id": "mars_hab_atmosphere_solar_failure"},
    )
    assert response.status_code == status
    body = response.json()
    assert body["code"] == code
    assert isinstance(body["message"], str)
    assert "C:\\" not in response.text
    assert "/Users/" not in response.text
    assert "Traceback" not in response.text
    assert "process_evidence" not in body
    if getattr(exc, "run_id", None) is not None:
        assert body["run_id"] == exc.run_id
    else:
        assert body["run_id"] is None


def test_unexpected_exception_safe_500(
    valid_settings: Any,
    caplog: pytest.LogCaptureFixture,
) -> None:
    service = AsyncMock(spec=SimulationService)
    service.run_simulation = AsyncMock(
        side_effect=RuntimeError("secret boom path C:\\secret\\x"),
    )
    app = create_app(
        settings_override=valid_settings,
        simulation_service_override=service,
    )
    with caplog.at_level(logging.ERROR):
        client = TestClient(app, raise_server_exceptions=False)
        response = client.post(
            "/api/sim/run",
            json={"scenario_id": "mars_hab_atmosphere_solar_failure"},
        )
    assert response.status_code == 500
    body = response.json()
    assert body["code"] == ErrorCode.INTERNAL_SERVER_ERROR.value
    assert body["run_id"] is None
    assert "secret boom" not in response.text
    assert "C:\\secret" not in response.text
    assert "Traceback" not in response.text
    assert any("unexpected_error" in r.getMessage() for r in caplog.records)


def test_malformed_request_still_422(valid_settings: Any) -> None:
    service = AsyncMock(spec=SimulationService)
    service.run_simulation = AsyncMock(
        side_effect=AssertionError("should not be called"),
    )
    client = _client_with_service(service, valid_settings)
    response = client.post("/api/sim/run", json={"plan": {}})
    assert response.status_code == 422


def test_mission_failure_returns_200(
    valid_settings: Any,
    baseline_result_data: Any,
) -> None:
    result = SimulationResult.model_validate(baseline_result_data)
    service = AsyncMock(spec=SimulationService)
    service.run_simulation = AsyncMock(
        return_value=SimulationRunResponse(
            run_id="00000000-0000-4000-8000-000000000099",
            duration_ms=10,
            result=result,
        ),
    )
    client = _client_with_service(service, valid_settings)
    response = client.post(
        "/api/sim/run",
        json={"scenario_id": "mars_hab_atmosphere_solar_failure"},
    )
    assert response.status_code == 200
    assert response.json()["result"]["outcome"] == "FAILURE"
