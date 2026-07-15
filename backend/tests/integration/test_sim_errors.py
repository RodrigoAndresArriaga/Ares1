# HTTP error mapping integration tests via thin route
from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock

import pytest
from app.core.config import clear_settings_cache
from app.core.errors import (
    ArtifactStorageError,
    ScenarioNotFoundError,
    SimulatorTimeoutError,
    SimulatorUnavailableError,
)
from app.main import create_app
from app.schemas.api import SimulationRunResponse
from app.schemas.result import SimulationResult
from app.services.simulation_service import SimulationService
from fastapi.testclient import TestClient


@pytest.fixture(autouse=True)
def _clear_settings_cache() -> Any:
    clear_settings_cache()
    yield
    clear_settings_cache()


def _app_client(
    settings: Any,
    service: SimulationService,
    *,
    raise_server_exceptions: bool = True,
) -> TestClient:
    app = create_app(
        settings_override=settings,
        simulation_service_override=service,
    )
    return TestClient(app, raise_server_exceptions=raise_server_exceptions)


def test_route_registered_in_openapi(valid_settings: Any) -> None:
    app = create_app(settings_override=valid_settings)
    with TestClient(app) as client:
        openapi = client.get("/openapi.json").json()
    assert "/api/sim/run" in openapi["paths"]
    post = openapi["paths"]["/api/sim/run"]["post"]
    assert "FAILURE" in post["description"]
    assert "REJECTED" in post["description"]
    assert "SimulationRunResponse" in str(post)


@pytest.mark.parametrize(
    "outcome_key",
    ["baseline_result_data", "valid_plan_result_data", "invalid_plan_result_data"],
)
def test_mission_outcomes_http_200(
    valid_settings: Any,
    outcome_key: str,
    request: pytest.FixtureRequest,
) -> None:
    data = request.getfixturevalue(outcome_key)
    result = SimulationResult.model_validate(data)
    service = AsyncMock(spec=SimulationService)
    service.run_simulation = AsyncMock(
        return_value=SimulationRunResponse(
            run_id="00000000-0000-4000-8000-000000000001",
            duration_ms=5,
            result=result,
        ),
    )
    client = _app_client(valid_settings, service)
    response = client.post(
        "/api/sim/run",
        json={"scenario_id": "mars_hab_atmosphere_solar_failure"},
    )
    assert response.status_code == 200
    assert response.json()["result"]["outcome"] == result.outcome.value
    service.run_simulation.assert_awaited_once()


def test_unknown_scenario_404(valid_settings: Any) -> None:
    service = AsyncMock(spec=SimulationService)
    service.run_simulation = AsyncMock(
        side_effect=ScenarioNotFoundError(scenario_id="missing"),
    )
    client = _app_client(valid_settings, service)
    response = client.post("/api/sim/run", json={"scenario_id": "missing"})
    assert response.status_code == 404
    assert response.json()["code"] == "SCENARIO_NOT_FOUND"


def test_unavailable_503(valid_settings: Any) -> None:
    service = AsyncMock(spec=SimulationService)
    service.run_simulation = AsyncMock(side_effect=SimulatorUnavailableError())
    client = _app_client(valid_settings, service)
    response = client.post(
        "/api/sim/run",
        json={"scenario_id": "mars_hab_atmosphere_solar_failure"},
    )
    assert response.status_code == 503


def test_timeout_504(valid_settings: Any) -> None:
    service = AsyncMock(spec=SimulationService)
    service.run_simulation = AsyncMock(
        side_effect=SimulatorTimeoutError(run_id="r-timeout"),
    )
    client = _app_client(valid_settings, service)
    response = client.post(
        "/api/sim/run",
        json={"scenario_id": "mars_hab_atmosphere_solar_failure"},
    )
    assert response.status_code == 504
    assert response.json()["run_id"] == "r-timeout"


def test_artifact_500(valid_settings: Any) -> None:
    service = AsyncMock(spec=SimulationService)
    service.run_simulation = AsyncMock(
        side_effect=ArtifactStorageError(run_id="r-art"),
    )
    client = _app_client(valid_settings, service)
    response = client.post(
        "/api/sim/run",
        json={"scenario_id": "mars_hab_atmosphere_solar_failure"},
    )
    assert response.status_code == 500
    assert response.json()["code"] == "ARTIFACT_STORAGE_ERROR"


def test_malformed_body_422(valid_settings: Any) -> None:
    service = AsyncMock(spec=SimulationService)
    service.run_simulation = AsyncMock()
    client = _app_client(valid_settings, service)
    response = client.post("/api/sim/run", json={"scenario_id": 123})
    assert response.status_code == 422
    service.run_simulation.assert_not_awaited()
