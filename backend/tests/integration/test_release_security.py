# release-gate security regressions for HTTP bridge controls
from __future__ import annotations

import inspect
import re
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock

import pytest
from app.core.config import clear_settings_cache
from app.core.logging import log_run_event
from app.main import create_app
from app.schemas.api import SimulationRunResponse
from app.schemas.result import SimulationResult
from app.services import simulator_client as simulator_client_module
from app.services.simulation_service import SimulationService
from fastapi.testclient import TestClient
from tests.conftest import (
    RELEASE_SCENARIO_ID,
    SHARED_SIM_RESULT_PATH,
    make_real_app_settings,
    require_real_simulator,
)

pytestmark = [pytest.mark.integration]


@pytest.fixture(autouse=True)
def _clear_cache() -> Any:
    clear_settings_cache()
    yield
    clear_settings_cache()


def test_no_shell_subprocess_apis_in_client_source() -> None:
    source = inspect.getsource(simulator_client_module)
    assert "shell=True" not in source
    assert "os.system" not in source
    assert "subprocess.run" not in source
    assert "subprocess.Popen" not in source
    assert "create_subprocess_shell" not in source
    assert "create_subprocess_exec" in source


def test_openapi_request_has_no_path_or_exec_fields(valid_settings: Any) -> None:
    app = create_app(settings_override=valid_settings)
    with TestClient(app) as client:
        openapi = client.get("/openapi.json").json()
    schema = openapi["components"]["schemas"]["SimulationRunRequest"]
    props = schema.get("properties", {})
    forbidden = {
        "scenario_path",
        "plan_path",
        "output_path",
        "executable",
        "executable_path",
        "simulator_path",
        "command",
        "args",
        "argv",
    }
    assert forbidden.isdisjoint(props.keys())
    assert "scenario_id" in props


def test_http_rejects_arbitrary_control_fields(valid_settings: Any) -> None:
    service = AsyncMock(spec=SimulationService)
    service.run_simulation = AsyncMock()
    app = create_app(
        settings_override=valid_settings,
        simulation_service_override=service,
    )
    with TestClient(app) as client:
        for field, value in (
            ("scenario_path", "../evil.json"),
            ("output_path", "C:/tmp/out.json"),
            ("executable_path", "C:/tmp/sim.exe"),
            ("command", ["rm", "-rf", "/"]),
        ):
            response = client.post(
                "/api/sim/run",
                json={"scenario_id": RELEASE_SCENARIO_ID, field: value},
            )
            assert response.status_code == 422
    service.run_simulation.assert_not_awaited()


def test_error_bodies_exclude_paths_and_tracebacks(valid_settings: Any) -> None:
    from app.core.errors import SimulatorUnavailableError

    service = AsyncMock(spec=SimulationService)
    service.run_simulation = AsyncMock(
        side_effect=SimulatorUnavailableError(
            run_id="aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
        ),
    )
    app = create_app(
        settings_override=valid_settings,
        simulation_service_override=service,
    )
    with TestClient(app) as client:
        response = client.post(
            "/api/sim/run",
            json={"scenario_id": RELEASE_SCENARIO_ID},
        )
    assert response.status_code == 503
    text = response.text
    assert "Traceback" not in text
    assert re.search(r"[A-Za-z]:\\\\", text) is None
    assert "/Users/" not in text
    assert "C:\\" not in text
    body = response.json()
    assert set(body.keys()) <= {"code", "message", "run_id"}


def test_structured_logs_exclude_telemetry_and_plans(
    caplog: pytest.LogCaptureFixture,
) -> None:
    import logging

    logger = logging.getLogger("ares.security_test")
    with caplog.at_level(logging.INFO, logger="ares.security_test"):
        log_run_event(
            logger,
            logging.INFO,
            "simulation run completed",
            event="simulation_run_completed",
            run_id="run-1",
            scenario_id=RELEASE_SCENARIO_ID,
            plan_id="sample_plan",
            mode="plan",
            duration_ms=12,
            process_exit_code=0,
            outcome="STABILIZED",
        )
    assert "telemetry_history" not in caplog.text
    assert "actions" not in caplog.text
    assert "API_KEY" not in caplog.text


@pytest.mark.real_simulator
def test_http_run_never_writes_shared_results(
    tmp_path: Path,
) -> None:
    require_real_simulator()
    shared_before = (
        SHARED_SIM_RESULT_PATH.read_bytes()
        if SHARED_SIM_RESULT_PATH.is_file()
        else None
    )
    settings = make_real_app_settings(tmp_path)
    app = create_app(settings_override=settings)
    with TestClient(app) as client:
        response = client.post(
            "/api/sim/run",
            json={"scenario_id": RELEASE_SCENARIO_ID},
        )
    assert response.status_code == 200
    run_dir = settings.runs_dir / response.json()["run_id"]
    result_path = run_dir / "result.json"
    assert result_path.is_file()
    assert result_path.resolve() != SHARED_SIM_RESULT_PATH.resolve()
    if shared_before is not None:
        assert SHARED_SIM_RESULT_PATH.read_bytes() == shared_before


def test_mission_outcomes_not_mapped_to_infrastructure_errors(
    valid_settings: Any,
    baseline_result_data: Any,
    valid_plan_result_data: Any,
    invalid_plan_result_data: Any,
) -> None:
    for data in (
        baseline_result_data,
        valid_plan_result_data,
        invalid_plan_result_data,
    ):
        result = SimulationResult.model_validate(data)
        service = AsyncMock(spec=SimulationService)
        service.run_simulation = AsyncMock(
            return_value=SimulationRunResponse(
                run_id="00000000-0000-4000-8000-000000000099",
                duration_ms=1,
                result=result,
            ),
        )
        app = create_app(
            settings_override=valid_settings,
            simulation_service_override=service,
        )
        with TestClient(app) as client:
            response = client.post(
                "/api/sim/run",
                json={"scenario_id": RELEASE_SCENARIO_ID},
            )
        assert response.status_code == 200
        assert response.json()["result"]["outcome"] == result.outcome.value
