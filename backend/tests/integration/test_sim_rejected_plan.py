# real FastAPI invalid-plan smoke: REJECTED via frozen sim_core.exe
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from app.core.config import clear_settings_cache
from app.main import create_app
from app.schemas.plan import RecoveryPlan
from app.schemas.result import SimulationResult
from app.services.run_store import sha256_file
from fastapi.testclient import TestClient
from tests.conftest import (
    RELEASE_SCENARIO_ID,
    RESULTS_DIR,
    SHARED_SIM_RESULT_PATH,
    make_real_app_settings,
    require_real_simulator,
)

pytestmark = [
    pytest.mark.integration,
    pytest.mark.real_simulator,
]


@pytest.fixture(autouse=True)
def _require_binary() -> None:
    require_real_simulator()


@pytest.fixture(autouse=True)
def _clear_cache() -> None:
    clear_settings_cache()
    yield
    clear_settings_cache()


@pytest.fixture
def real_app_settings(tmp_path: Path) -> Any:
    return make_real_app_settings(tmp_path)


def test_http_invalid_plan_rejected(
    real_app_settings: Any,
    invalid_plan_data: Any,
    invalid_plan_result_data: Any,
    release_scenario_bytes: bytes,
) -> None:
    shared_before = (
        SHARED_SIM_RESULT_PATH.read_bytes()
        if SHARED_SIM_RESULT_PATH.is_file()
        else None
    )
    expected = SimulationResult.model_validate(invalid_plan_result_data)
    expected_dump = expected.model_dump(mode="json")
    app = create_app(settings_override=real_app_settings)
    with TestClient(app) as client:
        response = client.post(
            "/api/sim/run",
            json={
                "scenario_id": RELEASE_SCENARIO_ID,
                "plan": invalid_plan_data,
            },
        )
    assert response.status_code == 200
    assert response.status_code not in (400, 422, 500)
    body = response.json()
    result = body["result"]
    assert result["outcome"] == "REJECTED"
    assert result["plan_id"] == "invalid_plan"
    assert result["valid_plan"] is False
    assert result["timeline"] == []
    assert result["telemetry_history"] == []
    assert result["failure_reasons"] == expected_dump["failure_reasons"]
    assert len(result["failure_reasons"]) > 0
    assert result["metrics"] == expected_dump["metrics"]
    assert SimulationResult.model_validate(result).model_dump(
        mode="json",
    ) == expected_dump

    run_id = body["run_id"]
    run_dir = real_app_settings.runs_dir / run_id
    for name in (
        "request.json",
        "scenario.json",
        "plan.json",
        "result.json",
        "stdout.log",
        "stderr.log",
        "metadata.json",
    ):
        assert (run_dir / name).is_file()
    assert (run_dir / "scenario.json").read_bytes() == release_scenario_bytes
    plan_on_disk = json.loads((run_dir / "plan.json").read_text(encoding="utf-8"))
    assert RecoveryPlan.model_validate(plan_on_disk).model_dump(
        mode="json",
    ) == RecoveryPlan.model_validate(invalid_plan_data).model_dump(mode="json")
    result_bytes = (run_dir / "result.json").read_bytes()
    metadata = json.loads((run_dir / "metadata.json").read_text(encoding="utf-8"))
    assert metadata["outcome"] == "REJECTED"
    assert metadata["status"] == "completed"
    assert metadata["error_code"] is None
    assert metadata["result_sha256"] == sha256_file(run_dir / "result.json")
    assert result_bytes == (RESULTS_DIR / "invalid_plan_result.json").read_bytes()
    if shared_before is not None:
        assert SHARED_SIM_RESULT_PATH.read_bytes() == shared_before
