# integration malformed-output bridge tests for SimulatorClient
from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

import pytest
from app.core.errors import (
    SimulatorOutputMissingError,
    SimulatorOutputParseError,
    SimulatorOutputValidationError,
)
from app.services.run_store import RunStore
from app.services.simulator_client import SimulatorClient
from tests.conftest import (
    RELEASE_SCENARIO_PATH,
    make_baseline_request,
    settings_from_layout,
)
from tests.helpers.fake_processes import make_exit_spawn, make_fixture_result_spawn


@pytest.fixture
def store(tmp_path: Path) -> RunStore:
    return RunStore(tmp_path / "runs")


@pytest.mark.asyncio
async def test_malformed_json_bridge(
    valid_layout: dict[str, Path],
    store: RunStore,
) -> None:
    client = SimulatorClient(
        settings_from_layout(valid_layout),
        _spawn=make_exit_spawn(0, write_result=b"{" ),
    )
    workspace = store.create_workspace(
        make_baseline_request(),
        RELEASE_SCENARIO_PATH,
    )
    with pytest.raises(SimulatorOutputParseError) as exc_info:
        await client.run(workspace)
    assert exc_info.value.run_id == workspace.run_id
    assert exc_info.value.__cause__ is not None


@pytest.mark.asyncio
async def test_contract_invalid_bridge(
    valid_layout: dict[str, Path],
    store: RunStore,
    baseline_result_data: dict[str, Any],
) -> None:
    mutated = copy.deepcopy(baseline_result_data)
    mutated["extra_top"] = 1
    client = SimulatorClient(
        settings_from_layout(valid_layout),
        _spawn=make_fixture_result_spawn(mutated),
    )
    workspace = store.create_workspace(
        make_baseline_request(),
        RELEASE_SCENARIO_PATH,
    )
    with pytest.raises(SimulatorOutputValidationError) as exc_info:
        await client.run(workspace)
    assert str(workspace.result_path) not in exc_info.value.message


@pytest.mark.asyncio
async def test_empty_output_bridge(
    valid_layout: dict[str, Path],
    store: RunStore,
) -> None:
    client = SimulatorClient(
        settings_from_layout(valid_layout),
        _spawn=make_exit_spawn(0, write_result=b""),
    )
    workspace = store.create_workspace(
        make_baseline_request(),
        RELEASE_SCENARIO_PATH,
    )
    with pytest.raises(SimulatorOutputMissingError):
        await client.run(workspace)


@pytest.mark.asyncio
async def test_invalid_utf8_bridge(
    valid_layout: dict[str, Path],
    store: RunStore,
) -> None:
    client = SimulatorClient(
        settings_from_layout(valid_layout),
        _spawn=make_exit_spawn(0, write_result=b"\x80\x81"),
    )
    workspace = store.create_workspace(
        make_baseline_request(),
        RELEASE_SCENARIO_PATH,
    )
    with pytest.raises(SimulatorOutputParseError):
        await client.run(workspace)
