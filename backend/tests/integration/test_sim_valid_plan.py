# real FastAPI valid-plan smoke: STABILIZED via frozen sim_core.exe
from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from app.core.config import Settings, clear_settings_cache
from app.main import create_app
from fastapi.testclient import TestClient
from tests.conftest import (
    RELEASE_SCENARIO_ID,
    REPO_ROOT,
    SHARED_SIM_RESULT_PATH,
    install_release_scenario,
)

REAL_BINARY = REPO_ROOT / "Simulator" / "build" / "sim_core.exe"


def _real_binary_available() -> bool:
    return REAL_BINARY.is_file() and REAL_BINARY.stat().st_size > 0


pytestmark = pytest.mark.skipif(
    not _real_binary_available(),
    reason="frozen simulator executable not present",
)


@pytest.fixture(autouse=True)
def _clear_cache() -> None:
    clear_settings_cache()
    yield
    clear_settings_cache()


@pytest.fixture
def real_app_settings(tmp_path: Path) -> Settings:
    project_root = tmp_path / "project"
    scenario_dir = project_root / "scenarios"
    install_release_scenario(scenario_dir)
    runs_dir = tmp_path / "runs"
    runs_dir.mkdir()
    return Settings(
        _env_file=None,
        project_root=project_root,
        sim_binary=REAL_BINARY,
        scenario_dir=scenario_dir,
        runs_dir=runs_dir,
        sim_timeout_seconds=120.0,
        max_concurrent_runs=1,
        log_level="INFO",
    )


def test_http_valid_plan_stabilized(
    real_app_settings: Settings,
    sample_plan_data: Any,
) -> None:
    shared_before = (
        SHARED_SIM_RESULT_PATH.read_bytes()
        if SHARED_SIM_RESULT_PATH.is_file()
        else None
    )
    app = create_app(settings_override=real_app_settings)
    with TestClient(app) as client:
        response = client.post(
            "/api/sim/run",
            json={
                "scenario_id": RELEASE_SCENARIO_ID,
                "plan": sample_plan_data,
            },
        )
    assert response.status_code == 200
    body = response.json()
    assert body["result"]["outcome"] == "STABILIZED"
    assert body["result"]["plan_id"] == "sample_plan"
    assert isinstance(body["result"]["telemetry_history"], list)
    assert len(body["result"]["telemetry_history"]) > 0
    sample = body["result"]["telemetry_history"][0]
    assert "crew" in sample
    if shared_before is not None:
        assert SHARED_SIM_RESULT_PATH.read_bytes() == shared_before
