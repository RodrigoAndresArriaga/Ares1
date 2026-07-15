# release-gate failure-path HTTP evidence (unavailable, timeout, malformed, artifact)
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest
from app.core.config import clear_settings_cache
from app.core.errors import ArtifactStorageError
from app.main import create_app
from app.services.run_store import RunStore
from app.services.scenario_registry import ScenarioRegistry
from app.services.simulation_service import SimulationService
from app.services.simulator_client import SimulatorClient
from fastapi.testclient import TestClient
from tests.conftest import (
    RELEASE_SCENARIO_ID,
    RESULTS_DIR,
    install_release_scenario,
    make_valid_layout,
    settings_from_layout,
)
from tests.helpers.fake_processes import (
    make_exit_spawn,
    make_fixture_result_spawn,
    write_helper_scripts,
)

pytestmark = [pytest.mark.integration]


@pytest.fixture(autouse=True)
def _clear_cache() -> Any:
    clear_settings_cache()
    yield
    clear_settings_cache()


def _assert_safe_error_body(body: dict[str, Any]) -> None:
    assert set(body.keys()) <= {"code", "message", "run_id"}
    message = str(body.get("message", ""))
    assert "Traceback" not in message
    assert ":\\" not in message
    assert not message.startswith("/")
    for value in body.values():
        if isinstance(value, str):
            assert ":\\" not in value
            assert not (len(value) >= 3 and value[1] == ":" and value[2] == "\\")


def _compose_app(settings: Any, *, spawn: Any | None = None) -> Any:
    registry = ScenarioRegistry(settings.scenario_dir)
    run_store = RunStore(settings.runs_dir)
    client = SimulatorClient(settings, _spawn=spawn)
    service = SimulationService(
        scenario_registry=registry,
        run_store=run_store,
        simulator_client=client,
    )
    return create_app(
        settings_override=settings,
        simulation_service_override=service,
    )


def test_unavailable_binary_health_and_sim_503(tmp_path: Path) -> None:
    layout = make_valid_layout(tmp_path)
    install_release_scenario(layout["scenario_dir"])
    settings = settings_from_layout(layout, max_concurrent_runs=1)
    binary_path = str(settings.sim_binary)
    app = create_app(settings_override=settings)
    with TestClient(app) as client:
        assert client.get("/api/health").status_code == 200
        settings.sim_binary.unlink()
        health = client.get("/api/health")
        assert health.status_code == 503
        assert binary_path not in health.text
        assert ":\\" not in health.text

        response = client.post(
            "/api/sim/run",
            json={"scenario_id": RELEASE_SCENARIO_ID},
        )
    assert response.status_code == 503
    body = response.json()
    assert body["code"] == "SIMULATOR_UNAVAILABLE"
    _assert_safe_error_body(body)
    assert binary_path not in response.text
    run_id = body.get("run_id")
    assert run_id
    run_dir = settings.runs_dir / run_id
    assert run_dir.is_dir()
    metadata = json.loads((run_dir / "metadata.json").read_text(encoding="utf-8"))
    assert metadata["status"] == "failed"
    assert metadata["error_code"] == "SIMULATOR_UNAVAILABLE"
    assert not (run_dir / "result.json").is_file()


def test_timeout_http_504_preserves_evidence_and_semaphore(tmp_path: Path) -> None:
    layout = make_valid_layout(tmp_path)
    install_release_scenario(layout["scenario_dir"])
    scripts = write_helper_scripts(tmp_path / "scripts")
    marker = tmp_path / "hang_started.txt"
    settings = settings_from_layout(
        layout,
        sim_timeout_seconds=0.3,
        max_concurrent_runs=1,
    )

    async def spawn_hang(
        *_cmd: str,
        stdout: Any = None,
        stderr: Any = None,
        **_kwargs: Any,
    ) -> asyncio.subprocess.Process:
        return await asyncio.create_subprocess_exec(
            sys.executable,
            str(scripts["hang"]),
            str(marker),
            stdout=stdout,
            stderr=stderr,
        )

    app = _compose_app(settings, spawn=spawn_hang)
    sim_client = app.state.simulation_service._simulator_client
    with TestClient(app) as client:
        response = client.post(
            "/api/sim/run",
            json={"scenario_id": RELEASE_SCENARIO_ID},
        )
    assert response.status_code == 504
    body = response.json()
    assert body["code"] == "SIMULATOR_TIMEOUT"
    _assert_safe_error_body(body)
    assert sim_client._semaphore._value == 1
    run_dir = settings.runs_dir / body["run_id"]
    metadata = json.loads((run_dir / "metadata.json").read_text(encoding="utf-8"))
    assert metadata["status"] == "failed"
    assert metadata["error_code"] == "SIMULATOR_TIMEOUT"
    assert not (run_dir / "result.json").is_file()

    fixture = json.loads(
        (RESULTS_DIR / "baseline_result.json").read_text(encoding="utf-8"),
    )
    success_app = _compose_app(
        settings_from_layout(layout, max_concurrent_runs=1),
        spawn=make_fixture_result_spawn(fixture),
    )
    with TestClient(success_app) as client:
        ok = client.post(
            "/api/sim/run",
            json={"scenario_id": RELEASE_SCENARIO_ID},
        )
    assert ok.status_code == 200
    assert ok.json()["result"]["outcome"] == "FAILURE"


def test_malformed_output_http_502_preserves_bytes(tmp_path: Path) -> None:
    layout = make_valid_layout(tmp_path)
    install_release_scenario(layout["scenario_dir"])
    settings = settings_from_layout(layout, max_concurrent_runs=1)
    malformed = b"{"
    app = _compose_app(
        settings,
        spawn=make_exit_spawn(0, write_result=malformed, stdout_data=b"out"),
    )
    with TestClient(app) as client:
        response = client.post(
            "/api/sim/run",
            json={"scenario_id": RELEASE_SCENARIO_ID},
        )
    assert response.status_code == 502
    body = response.json()
    assert body["code"] == "SIMULATOR_OUTPUT_INVALID_JSON"
    _assert_safe_error_body(body)
    run_dir = settings.runs_dir / body["run_id"]
    assert (run_dir / "result.json").read_bytes() == malformed
    assert (run_dir / "stdout.log").is_file()
    assert (run_dir / "stderr.log").is_file()
    metadata = json.loads((run_dir / "metadata.json").read_text(encoding="utf-8"))
    assert metadata["status"] == "failed"
    assert "result" not in body


def test_artifact_failure_http_500_keeps_evidence(
    tmp_path: Path,
    baseline_result_data: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    layout = make_valid_layout(tmp_path)
    install_release_scenario(layout["scenario_dir"])
    settings = settings_from_layout(layout, max_concurrent_runs=1)
    app = _compose_app(
        settings,
        spawn=make_fixture_result_spawn(baseline_result_data),
    )
    service: SimulationService = app.state.simulation_service

    def fail_metadata(*_args: Any, **_kwargs: Any) -> None:
        raise ArtifactStorageError("Failed to write run metadata")

    monkeypatch.setattr(
        service._run_store,
        "write_completed_metadata",
        fail_metadata,
    )
    with TestClient(app) as client:
        response = client.post(
            "/api/sim/run",
            json={"scenario_id": RELEASE_SCENARIO_ID},
        )
    assert response.status_code == 500
    body = response.json()
    assert body["code"] == "ARTIFACT_STORAGE_ERROR"
    _assert_safe_error_body(body)
    run_dir = settings.runs_dir / body["run_id"]
    assert (run_dir / "result.json").is_file()
    assert (run_dir / "stdout.log").is_file()
    assert (run_dir / "request.json").is_file()
    assert (run_dir / "metadata.json").is_file()


def test_request_validation_422_before_launch(
    tmp_path: Path,
    sample_plan_data: Any,
) -> None:
    layout = make_valid_layout(tmp_path)
    install_release_scenario(layout["scenario_dir"])
    settings = settings_from_layout(layout)
    spy_spawn = MagicMock(side_effect=AssertionError("must not launch"))
    app = _compose_app(settings, spawn=spy_spawn)

    cases: list[dict[str, Any]] = [
        {"scenario_id": RELEASE_SCENARIO_ID, "extra_field": True},
        {},
        {
            "scenario_id": RELEASE_SCENARIO_ID,
            "plan": {
                **sample_plan_data,
                "actions": [{"type": "not_a_real_action", "start_min": 0}],
            },
        },
        {
            "scenario_id": RELEASE_SCENARIO_ID,
            "scenario_path": "C:/evil/scenario.json",
        },
        {
            "scenario_id": RELEASE_SCENARIO_ID,
            "executable_path": "C:/evil/sim.exe",
        },
        {
            "scenario_id": RELEASE_SCENARIO_ID,
            "output_path": "C:/evil/out.json",
        },
        {
            "scenario_id": RELEASE_SCENARIO_ID,
            "command": ["--inject"],
        },
    ]
    with TestClient(app) as client:
        for payload in cases:
            response = client.post("/api/sim/run", json=payload)
            assert response.status_code == 422, payload
            spy_spawn.assert_not_called()
