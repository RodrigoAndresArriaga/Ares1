# real frozen-executable smoke tests through SimulatorClient
# no FastAPI or SimulationService
from __future__ import annotations

from pathlib import Path

import pytest
from app.core.config import Settings
from app.schemas.result import OutcomeStatus
from app.services.run_store import RunStore
from app.services.simulator_client import SimulatorClient
from tests.conftest import (
    RELEASE_SCENARIO_PATH,
    REPO_ROOT,
    SHARED_SIM_RESULT_PATH,
    make_baseline_request,
    make_plan_request,
)

REAL_BINARY = REPO_ROOT / "Simulator" / "build" / "sim_core.exe"


def _real_binary_available() -> bool:
    return REAL_BINARY.is_file() and REAL_BINARY.stat().st_size > 0


pytestmark = pytest.mark.skipif(
    not _real_binary_available(),
    reason="frozen simulator executable not present",
)


@pytest.fixture
def real_settings(tmp_path: Path) -> Settings:
    project_root = tmp_path / "project"
    scenario_dir = project_root / "scenarios"
    scenario_dir.mkdir(parents=True)
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


@pytest.fixture
def store(tmp_path: Path) -> RunStore:
    return RunStore(tmp_path / "runs")


@pytest.mark.asyncio
async def test_real_cli_baseline_failure(
    real_settings: Settings,
    store: RunStore,
) -> None:
    shared_before = (
        SHARED_SIM_RESULT_PATH.read_bytes()
        if SHARED_SIM_RESULT_PATH.is_file()
        else None
    )
    client = SimulatorClient(real_settings)
    workspace = store.create_workspace(
        make_baseline_request(),
        RELEASE_SCENARIO_PATH,
    )
    execution = await client.run(workspace)
    assert execution.process.exit_code == 0
    assert execution.result.outcome == OutcomeStatus.FAILURE
    assert execution.result.plan_id == ""
    assert workspace.result_path.is_file()
    if shared_before is not None:
        assert SHARED_SIM_RESULT_PATH.read_bytes() == shared_before


@pytest.mark.asyncio
async def test_real_cli_valid_plan_stabilized(
    real_settings: Settings,
    store: RunStore,
    sample_plan_data: object,
) -> None:
    client = SimulatorClient(real_settings)
    workspace = store.create_workspace(
        make_plan_request(sample_plan_data),
        RELEASE_SCENARIO_PATH,
    )
    execution = await client.run(workspace)
    assert execution.process.exit_code == 0
    assert execution.result.outcome == OutcomeStatus.STABILIZED


@pytest.mark.asyncio
async def test_real_cli_invalid_plan_rejected(
    real_settings: Settings,
    store: RunStore,
    invalid_plan_data: object,
) -> None:
    client = SimulatorClient(real_settings)
    workspace = store.create_workspace(
        make_plan_request(invalid_plan_data),
        RELEASE_SCENARIO_PATH,
    )
    execution = await client.run(workspace)
    assert execution.process.exit_code == 0
    assert execution.result.outcome == OutcomeStatus.REJECTED
    assert execution.result.telemetry_history == []
    assert execution.result.timeline == []
