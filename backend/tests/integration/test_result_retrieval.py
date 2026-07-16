# Persisted simulator result HTTP retrieval tests (Phase 3 Step 6)
from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock

import pytest
from app.core.config import clear_settings_cache
from app.main import create_app
from app.schemas.api import ErrorCode
from app.schemas.result import OutcomeStatus, SimulationResult
from app.schemas.run import PersistedRunResultResponse
from app.services.run_store import RunStore
from app.services.simulation_service import SimulationService
from fastapi.testclient import TestClient
from tests.conftest import (
    RESULTS_DIR,
    make_fake_simulation_service,
    make_mission_settings,
    seed_completed_run,
)


@pytest.fixture(autouse=True)
def _clear_settings_cache() -> Any:
    clear_settings_cache()
    yield
    clear_settings_cache()


def _app_with_runs(tmp_path: Path) -> tuple[TestClient, Any, RunStore]:
    settings = make_mission_settings(tmp_path)
    fake = AsyncMock(spec=SimulationService)
    app = create_app(
        settings_override=settings,
        simulation_service_override=fake,
    )
    client = TestClient(app, raise_server_exceptions=False)
    client.__enter__()
    store: RunStore = app.state.run_store
    return client, app, store


def _close(client: TestClient) -> None:
    client.__exit__(None, None, None)


def _assert_safe_error(payload: dict[str, Any], tmp_path: Path) -> None:
    encoded = json.dumps(payload)
    assert str(tmp_path) not in encoded
    assert "Traceback" not in encoded
    assert "File \"" not in encoded


@pytest.mark.parametrize(
    ("fixture_file", "expected_outcome"),
    [
        ("baseline_result.json", OutcomeStatus.FAILURE),
        ("valid_plan_result.json", OutcomeStatus.STABILIZED),
        ("invalid_plan_result.json", OutcomeStatus.REJECTED),
    ],
)
def test_persisted_result_outcomes_200(
    tmp_path: Path,
    fixture_file: str,
    expected_outcome: OutcomeStatus,
) -> None:
    client, app, store = _app_with_runs(tmp_path)
    try:
        fixture = RESULTS_DIR / fixture_file
        workspace = seed_completed_run(store, fixture)
        before_result = workspace.result_path.read_bytes()
        before_meta = workspace.metadata_path.read_bytes()

        response = client.get(f"/api/sim/result/{workspace.run_id}")
        assert response.status_code == 200
        body = PersistedRunResultResponse.model_validate(response.json())
        assert body.run_id == workspace.run_id
        assert body.metadata.run_id == workspace.run_id
        assert body.result.outcome == expected_outcome
        expected = SimulationResult.model_validate_json(before_result)
        assert body.result == expected
        assert len(body.result.telemetry_history) == len(expected.telemetry_history)
        if expected_outcome == OutcomeStatus.FAILURE:
            assert body.result.plan_id == ""
            assert body.result.failure_reasons
        assert body.metadata.outcome == expected_outcome.value
        encoded = json.dumps(response.json())
        assert str(tmp_path) not in encoded
        assert str(app.state.settings.runs_dir) not in encoded
        assert workspace.result_path.read_bytes() == before_result
        assert workspace.metadata_path.read_bytes() == before_meta
    finally:
        _close(client)


def test_unknown_run_404(tmp_path: Path) -> None:
    client, _, _ = _app_with_runs(tmp_path)
    try:
        missing = "00000000-0000-4000-8000-0000000000ff"
        response = client.get(f"/api/sim/result/{missing}")
        assert response.status_code == 404
        payload = response.json()
        assert payload["code"] == ErrorCode.RUN_NOT_FOUND.value
        _assert_safe_error(payload, tmp_path)
    finally:
        _close(client)


def test_invalid_run_id_400(tmp_path: Path) -> None:
    client, _, _ = _app_with_runs(tmp_path)
    try:
        response = client.get("/api/sim/result/not-a-uuid")
        assert response.status_code == 400
        assert response.json()["code"] == ErrorCode.RUN_ID_INVALID.value
        _assert_safe_error(response.json(), tmp_path)
    finally:
        _close(client)


def test_missing_result_404(tmp_path: Path) -> None:
    client, _, store = _app_with_runs(tmp_path)
    try:
        workspace = seed_completed_run(store, RESULTS_DIR / "baseline_result.json")
        workspace.result_path.unlink()
        response = client.get(f"/api/sim/result/{workspace.run_id}")
        assert response.status_code == 404
        assert response.json()["code"] == ErrorCode.RUN_RESULT_NOT_FOUND.value
        _assert_safe_error(response.json(), tmp_path)
    finally:
        _close(client)


def test_missing_metadata_404(tmp_path: Path) -> None:
    client, _, store = _app_with_runs(tmp_path)
    try:
        workspace = seed_completed_run(store, RESULTS_DIR / "baseline_result.json")
        workspace.metadata_path.unlink()
        response = client.get(f"/api/sim/result/{workspace.run_id}")
        assert response.status_code == 404
        assert response.json()["code"] == ErrorCode.RUN_METADATA_NOT_FOUND.value
        _assert_safe_error(response.json(), tmp_path)
    finally:
        _close(client)


def test_corrupt_result_500(tmp_path: Path) -> None:
    client, _, store = _app_with_runs(tmp_path)
    try:
        workspace = seed_completed_run(store, RESULTS_DIR / "baseline_result.json")
        workspace.result_path.write_text("{not-json", encoding="utf-8")
        response = client.get(f"/api/sim/result/{workspace.run_id}")
        assert response.status_code == 500
        assert response.json()["code"] == ErrorCode.RUN_RESULT_CORRUPT.value
        _assert_safe_error(response.json(), tmp_path)
    finally:
        _close(client)


def test_corrupt_metadata_500(tmp_path: Path) -> None:
    client, _, store = _app_with_runs(tmp_path)
    try:
        workspace = seed_completed_run(store, RESULTS_DIR / "baseline_result.json")
        workspace.metadata_path.write_text("{not-json", encoding="utf-8")
        response = client.get(f"/api/sim/result/{workspace.run_id}")
        assert response.status_code == 500
        assert response.json()["code"] == ErrorCode.RUN_METADATA_CORRUPT.value
        _assert_safe_error(response.json(), tmp_path)
    finally:
        _close(client)


def test_result_route_uses_app_state_run_store(tmp_path: Path) -> None:
    client, app, store = _app_with_runs(tmp_path)
    try:
        workspace = seed_completed_run(store, RESULTS_DIR / "baseline_result.json")
        assert app.state.run_store is store
        response = client.get(f"/api/sim/result/{workspace.run_id}")
        assert response.status_code == 200
        assert app.state.run_store is store
    finally:
        _close(client)


def test_result_route_does_not_call_simulation_service(tmp_path: Path) -> None:
    settings = make_mission_settings(tmp_path)
    fake = make_fake_simulation_service(
        json.loads((RESULTS_DIR / "baseline_result.json").read_text(encoding="utf-8")),
    )
    app = create_app(
        settings_override=settings,
        simulation_service_override=fake,
    )
    with TestClient(app) as client:
        store: RunStore = app.state.run_store
        workspace = seed_completed_run(store, RESULTS_DIR / "baseline_result.json")
        response = client.get(f"/api/sim/result/{workspace.run_id}")
        assert response.status_code == 200
        fake.run_simulation.assert_not_awaited()
