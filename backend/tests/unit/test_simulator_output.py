# unit tests for SimulatorClient result.json loading and validation
from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import pytest
from app.core.errors import (
    SimulatorExecutionError,
    SimulatorOutputMissingError,
    SimulatorOutputParseError,
    SimulatorOutputValidationError,
)
from app.schemas.result import OutcomeStatus
from app.services.run_store import RunStore
from app.services.simulator_client import SimulatorClient
from tests.conftest import (
    RELEASE_SCENARIO_PATH,
    make_baseline_request,
    make_plan_request,
    settings_from_layout,
)
from tests.helpers.fake_processes import make_exit_spawn, make_fixture_result_spawn


@pytest.fixture
def store(tmp_path: Path) -> RunStore:
    return RunStore(tmp_path / "runs")


def _client(layout: dict[str, Path], spawn: Any) -> SimulatorClient:
    return SimulatorClient(settings_from_layout(layout), _spawn=spawn)


@pytest.mark.asyncio
async def test_missing_result_file(
    valid_layout: dict[str, Path],
    store: RunStore,
) -> None:
    spawn = make_exit_spawn(0)
    client = _client(valid_layout, spawn)
    workspace = store.create_workspace(
        make_baseline_request(),
        RELEASE_SCENARIO_PATH,
    )
    with pytest.raises(SimulatorOutputMissingError) as exc_info:
        await client.run(workspace)
    assert exc_info.value.run_id == workspace.run_id


@pytest.mark.asyncio
async def test_preexisting_result_directory_rejected(
    valid_layout: dict[str, Path],
    store: RunStore,
) -> None:
    client = _client(valid_layout, make_exit_spawn(0))
    workspace = store.create_workspace(
        make_baseline_request(),
        RELEASE_SCENARIO_PATH,
    )
    workspace.result_path.mkdir()
    with pytest.raises(SimulatorExecutionError):
        await client.run(workspace)


@pytest.mark.asyncio
async def test_zero_byte_result(
    valid_layout: dict[str, Path],
    store: RunStore,
) -> None:
    spawn = make_exit_spawn(0, write_result=b"")
    client = _client(valid_layout, spawn)
    workspace = store.create_workspace(
        make_baseline_request(),
        RELEASE_SCENARIO_PATH,
    )
    with pytest.raises(SimulatorOutputMissingError):
        await client.run(workspace)


@pytest.mark.asyncio
async def test_invalid_utf8_result(
    valid_layout: dict[str, Path],
    store: RunStore,
) -> None:
    spawn = make_exit_spawn(0, write_result=b"\xff\xfe invalid")
    client = _client(valid_layout, spawn)
    workspace = store.create_workspace(
        make_baseline_request(),
        RELEASE_SCENARIO_PATH,
    )
    with pytest.raises(SimulatorOutputParseError):
        await client.run(workspace)


@pytest.mark.asyncio
async def test_invalid_json_result(
    valid_layout: dict[str, Path],
    store: RunStore,
) -> None:
    spawn = make_exit_spawn(0, write_result=b"{not-json")
    client = _client(valid_layout, spawn)
    workspace = store.create_workspace(
        make_baseline_request(),
        RELEASE_SCENARIO_PATH,
    )
    with pytest.raises(SimulatorOutputParseError):
        await client.run(workspace)


@pytest.mark.asyncio
async def test_unknown_top_level_field(
    valid_layout: dict[str, Path],
    store: RunStore,
    baseline_result_data: dict[str, Any],
) -> None:
    mutated = copy.deepcopy(baseline_result_data)
    mutated["survival_probability"] = 0.5
    # remove survival_probability for this specific unknown-field case
    del mutated["survival_probability"]
    mutated["unexpected_field"] = True
    spawn = make_fixture_result_spawn(mutated)
    client = _client(valid_layout, spawn)
    workspace = store.create_workspace(
        make_baseline_request(),
        RELEASE_SCENARIO_PATH,
    )
    with pytest.raises(SimulatorOutputValidationError):
        await client.run(workspace)


@pytest.mark.asyncio
async def test_missing_required_field(
    valid_layout: dict[str, Path],
    store: RunStore,
    baseline_result_data: dict[str, Any],
) -> None:
    mutated = copy.deepcopy(baseline_result_data)
    del mutated["outcome"]
    spawn = make_fixture_result_spawn(mutated)
    client = _client(valid_layout, spawn)
    workspace = store.create_workspace(
        make_baseline_request(),
        RELEASE_SCENARIO_PATH,
    )
    with pytest.raises(SimulatorOutputValidationError):
        await client.run(workspace)


@pytest.mark.asyncio
async def test_invalid_outcome_enum(
    valid_layout: dict[str, Path],
    store: RunStore,
    baseline_result_data: dict[str, Any],
) -> None:
    mutated = copy.deepcopy(baseline_result_data)
    mutated["outcome"] = "SUCCESS"
    spawn = make_fixture_result_spawn(mutated)
    client = _client(valid_layout, spawn)
    workspace = store.create_workspace(
        make_baseline_request(),
        RELEASE_SCENARIO_PATH,
    )
    with pytest.raises(SimulatorOutputValidationError):
        await client.run(workspace)


@pytest.mark.asyncio
async def test_survival_probability_rejected(
    valid_layout: dict[str, Path],
    store: RunStore,
    baseline_result_data: dict[str, Any],
) -> None:
    mutated = copy.deepcopy(baseline_result_data)
    mutated["survival_probability"] = 0.99
    spawn = make_fixture_result_spawn(mutated)
    client = _client(valid_layout, spawn)
    workspace = store.create_workspace(
        make_baseline_request(),
        RELEASE_SCENARIO_PATH,
    )
    with pytest.raises(SimulatorOutputValidationError):
        await client.run(workspace)


@pytest.mark.asyncio
async def test_crew_renamed_rejected(
    valid_layout: dict[str, Path],
    store: RunStore,
    baseline_result_data: dict[str, Any],
) -> None:
    mutated = copy.deepcopy(baseline_result_data)
    sample = mutated["telemetry_history"][0]
    sample["crew_vitals"] = sample.pop("crew")
    spawn = make_fixture_result_spawn(mutated)
    client = _client(valid_layout, spawn)
    workspace = store.create_workspace(
        make_baseline_request(),
        RELEASE_SCENARIO_PATH,
    )
    with pytest.raises(SimulatorOutputValidationError):
        await client.run(workspace)


@pytest.mark.asyncio
async def test_valid_baseline_fixture(
    valid_layout: dict[str, Path],
    store: RunStore,
    baseline_result_data: dict[str, Any],
) -> None:
    client = _client(valid_layout, make_fixture_result_spawn(baseline_result_data))
    workspace = store.create_workspace(
        make_baseline_request(),
        RELEASE_SCENARIO_PATH,
    )
    execution = await client.run(workspace)
    assert execution.result.outcome == OutcomeStatus.FAILURE
    assert execution.result.plan_id == ""
    assert execution.result.valid_plan is True


@pytest.mark.asyncio
async def test_valid_plan_fixture(
    valid_layout: dict[str, Path],
    store: RunStore,
    valid_plan_result_data: dict[str, Any],
    sample_plan_data: object,
) -> None:
    client = _client(valid_layout, make_fixture_result_spawn(valid_plan_result_data))
    workspace = store.create_workspace(
        make_plan_request(sample_plan_data),
        RELEASE_SCENARIO_PATH,
    )
    execution = await client.run(workspace)
    assert execution.result.outcome == OutcomeStatus.STABILIZED


@pytest.mark.asyncio
async def test_valid_rejected_fixture(
    valid_layout: dict[str, Path],
    store: RunStore,
    invalid_plan_result_data: dict[str, Any],
    invalid_plan_data: object,
) -> None:
    client = _client(
        valid_layout,
        make_fixture_result_spawn(invalid_plan_result_data),
    )
    workspace = store.create_workspace(
        make_plan_request(invalid_plan_data),
        RELEASE_SCENARIO_PATH,
    )
    execution = await client.run(workspace)
    assert execution.result.outcome == OutcomeStatus.REJECTED
    assert execution.result.telemetry_history == []
    assert execution.result.timeline == []


@pytest.mark.asyncio
async def test_stdout_cannot_override_result(
    valid_layout: dict[str, Path],
    store: RunStore,
    baseline_result_data: dict[str, Any],
) -> None:
    raw = json.dumps(baseline_result_data).encode("utf-8")
    spawn = make_exit_spawn(
        0,
        write_result=raw,
        stdout_data=b'{"outcome":"STABILIZED"}',
    )
    client = _client(valid_layout, spawn)
    workspace = store.create_workspace(
        make_baseline_request(),
        RELEASE_SCENARIO_PATH,
    )
    execution = await client.run(workspace)
    assert execution.result.outcome == OutcomeStatus.FAILURE


@pytest.mark.asyncio
async def test_stderr_cannot_override_result(
    valid_layout: dict[str, Path],
    store: RunStore,
    valid_plan_result_data: dict[str, Any],
    sample_plan_data: object,
) -> None:
    raw = json.dumps(valid_plan_result_data).encode("utf-8")
    spawn = make_exit_spawn(
        0,
        write_result=raw,
        stderr_data=b"failure: cabin pressure critical",
    )
    client = _client(valid_layout, spawn)
    workspace = store.create_workspace(
        make_plan_request(sample_plan_data),
        RELEASE_SCENARIO_PATH,
    )
    execution = await client.run(workspace)
    assert execution.result.outcome == OutcomeStatus.STABILIZED
    assert "cabin pressure" not in " ".join(execution.result.failure_reasons)


@pytest.mark.asyncio
async def test_exit_zero_invalid_output(
    valid_layout: dict[str, Path],
    store: RunStore,
) -> None:
    spawn = make_exit_spawn(0, write_result=b'{"outcome":"FAILURE"}')
    client = _client(valid_layout, spawn)
    workspace = store.create_workspace(
        make_baseline_request(),
        RELEASE_SCENARIO_PATH,
    )
    with pytest.raises(SimulatorOutputValidationError):
        await client.run(workspace)


@pytest.mark.asyncio
async def test_nonzero_exit_plus_valid_output(
    valid_layout: dict[str, Path],
    store: RunStore,
    baseline_result_data: dict[str, Any],
) -> None:
    raw = json.dumps(baseline_result_data).encode("utf-8")
    spawn = make_exit_spawn(1, write_result=raw)
    client = _client(valid_layout, spawn)
    workspace = store.create_workspace(
        make_baseline_request(),
        RELEASE_SCENARIO_PATH,
    )
    with pytest.raises(SimulatorExecutionError) as exc_info:
        await client.run(workspace)
    assert workspace.result_path.is_file()
    assert exc_info.value.process_evidence is not None


@pytest.mark.asyncio
async def test_original_result_bytes_unchanged(
    valid_layout: dict[str, Path],
    store: RunStore,
    baseline_result_data: dict[str, Any],
) -> None:
    raw = json.dumps(baseline_result_data, indent=2).encode("utf-8") + b"\n"
    spawn = make_exit_spawn(0, write_result=raw)
    client = _client(valid_layout, spawn)
    workspace = store.create_workspace(
        make_baseline_request(),
        RELEASE_SCENARIO_PATH,
    )
    await client.run(workspace)
    assert workspace.result_path.read_bytes() == raw
