# real HTTP determinism: identical valid-plan requests yield equal results
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from app.core.config import clear_settings_cache
from app.main import create_app
from app.schemas.result import SimulationResult
from app.services.run_store import sha256_file
from fastapi.testclient import TestClient
from tests.conftest import (
    RELEASE_SCENARIO_ID,
    RESULTS_DIR,
    SHARED_SIM_RESULT_PATH,
    VALID_RESULT_SHA256,
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


def test_http_valid_plan_determinism(
    tmp_path: Path,
    sample_plan_data: Any,
    valid_plan_result_data: Any,
) -> None:
    shared_before = (
        SHARED_SIM_RESULT_PATH.read_bytes()
        if SHARED_SIM_RESULT_PATH.is_file()
        else None
    )
    settings = make_real_app_settings(tmp_path, max_concurrent_runs=1)
    app = create_app(settings_override=settings)
    payload = {
        "scenario_id": RELEASE_SCENARIO_ID,
        "plan": sample_plan_data,
    }
    with TestClient(app) as client:
        response_a = client.post("/api/sim/run", json=payload)
        response_b = client.post("/api/sim/run", json=payload)

    assert response_a.status_code == 200
    assert response_b.status_code == 200
    body_a = response_a.json()
    body_b = response_b.json()
    assert body_a["run_id"] != body_b["run_id"]

    result_a = SimulationResult.model_validate(body_a["result"])
    result_b = SimulationResult.model_validate(body_b["result"])
    dump_a = result_a.model_dump(mode="json")
    dump_b = result_b.model_dump(mode="json")
    assert dump_a == dump_b
    expected = SimulationResult.model_validate(valid_plan_result_data)
    assert dump_a == expected.model_dump(mode="json")

    dir_a = settings.runs_dir / body_a["run_id"]
    dir_b = settings.runs_dir / body_b["run_id"]
    assert dir_a != dir_b
    bytes_a = (dir_a / "result.json").read_bytes()
    bytes_b = (dir_b / "result.json").read_bytes()
    assert bytes_a == bytes_b
    assert bytes_a == (RESULTS_DIR / "valid_plan_result.json").read_bytes()
    hash_a = sha256_file(dir_a / "result.json")
    hash_b = sha256_file(dir_b / "result.json")
    assert hash_a == hash_b == VALID_RESULT_SHA256

    meta_a = json.loads((dir_a / "metadata.json").read_text(encoding="utf-8"))
    meta_b = json.loads((dir_b / "metadata.json").read_text(encoding="utf-8"))
    assert meta_a["result_sha256"] == hash_a
    assert meta_b["result_sha256"] == hash_b

    for raw in (bytes_a, bytes_b):
        parsed = json.loads(raw.decode("utf-8"))
        assert "run_id" not in parsed
        assert "created_at" not in parsed
        assert "completed_at" not in parsed
        assert "duration_ms" not in parsed

    if shared_before is not None:
        assert SHARED_SIM_RESULT_PATH.read_bytes() == shared_before
