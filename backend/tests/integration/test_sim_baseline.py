# real FastAPI baseline smoke: FAILURE via frozen sim_core.exe
from __future__ import annotations

from pathlib import Path

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


def test_http_baseline_failure(real_app_settings: Settings) -> None:
    shared_before = (
        SHARED_SIM_RESULT_PATH.read_bytes()
        if SHARED_SIM_RESULT_PATH.is_file()
        else None
    )
    app = create_app(settings_override=real_app_settings)
    with TestClient(app) as client:
        response = client.post(
            "/api/sim/run",
            json={"scenario_id": RELEASE_SCENARIO_ID},
        )
    assert response.status_code == 200
    body = response.json()
    assert body["result"]["outcome"] == "FAILURE"
    assert body["result"]["plan_id"] == ""
    assert "valid_plan" in body["result"]
    assert isinstance(body["result"]["failure_reasons"], list)
    assert isinstance(body["result"]["telemetry_history"], list)
    assert body["run_id"]
    run_dir = real_app_settings.runs_dir / body["run_id"]
    assert run_dir.is_dir()
    assert (run_dir / "result.json").is_file()
    assert (run_dir / "metadata.json").is_file()
    if shared_before is not None:
        assert SHARED_SIM_RESULT_PATH.read_bytes() == shared_before
