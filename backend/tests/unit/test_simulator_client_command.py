# unit tests for SimulatorClient command construction
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
from app.core.errors import SimulatorExecutionError
from app.services.run_store import RunStore
from app.services.simulator_client import SimulatorClient
from tests.conftest import (
    RELEASE_SCENARIO_PATH,
    make_baseline_request,
    make_plan_request,
    settings_from_layout,
)


@pytest.fixture
def client(valid_layout: dict[str, Path]) -> SimulatorClient:
    return SimulatorClient(settings_from_layout(valid_layout))


@pytest.fixture
def store(tmp_path: Path) -> RunStore:
    return RunStore(tmp_path / "runs")


def test_baseline_argument_vector(
    client: SimulatorClient,
    store: RunStore,
) -> None:
    workspace = store.create_workspace(
        make_baseline_request(),
        RELEASE_SCENARIO_PATH,
    )
    command = client._build_command(workspace)
    assert command == [
        str(client._binary),
        "--scenario",
        str(workspace.scenario_path),
        "--output",
        str(workspace.result_path),
    ]


def test_plan_argument_vector(
    client: SimulatorClient,
    store: RunStore,
    sample_plan_data: object,
) -> None:
    workspace = store.create_workspace(
        make_plan_request(sample_plan_data),
        RELEASE_SCENARIO_PATH,
    )
    command = client._build_command(workspace)
    assert command == [
        str(client._binary),
        "--scenario",
        str(workspace.scenario_path),
        "--plan",
        str(workspace.plan_path),
        "--output",
        str(workspace.result_path),
    ]


def test_executable_is_argument_zero(
    client: SimulatorClient,
    store: RunStore,
) -> None:
    workspace = store.create_workspace(
        make_baseline_request(),
        RELEASE_SCENARIO_PATH,
    )
    command = client._build_command(workspace)
    assert command[0] == str(client._binary)


def test_plan_flag_absent_in_baseline(
    client: SimulatorClient,
    store: RunStore,
) -> None:
    workspace = store.create_workspace(
        make_baseline_request(),
        RELEASE_SCENARIO_PATH,
    )
    command = client._build_command(workspace)
    assert "--plan" not in command


def test_plan_flag_present_once_in_plan_mode(
    client: SimulatorClient,
    store: RunStore,
    sample_plan_data: object,
) -> None:
    workspace = store.create_workspace(
        make_plan_request(sample_plan_data),
        RELEASE_SCENARIO_PATH,
    )
    command = client._build_command(workspace)
    assert command.count("--plan") == 1


def test_paths_are_workspace_local(
    client: SimulatorClient,
    store: RunStore,
    sample_plan_data: object,
) -> None:
    workspace = store.create_workspace(
        make_plan_request(sample_plan_data),
        RELEASE_SCENARIO_PATH,
    )
    command = client._build_command(workspace)
    root = workspace.root.resolve()
    scenario = Path(command[command.index("--scenario") + 1]).resolve()
    plan = Path(command[command.index("--plan") + 1]).resolve()
    result = Path(command[command.index("--output") + 1]).resolve()
    assert scenario.is_relative_to(root)
    assert plan.is_relative_to(root)
    assert result.is_relative_to(root)


def test_no_request_metadata_or_log_arguments(
    client: SimulatorClient,
    store: RunStore,
    sample_plan_data: object,
) -> None:
    workspace = store.create_workspace(
        make_plan_request(sample_plan_data),
        RELEASE_SCENARIO_PATH,
    )
    joined = " ".join(client._build_command(workspace))
    assert "request.json" not in joined
    assert "metadata.json" not in joined
    assert "stdout.log" not in joined
    assert "stderr.log" not in joined


def test_no_arbitrary_extra_arguments(
    client: SimulatorClient,
    store: RunStore,
) -> None:
    workspace = store.create_workspace(
        make_baseline_request(),
        RELEASE_SCENARIO_PATH,
    )
    command = client._build_command(workspace)
    assert len(command) == 5


def test_missing_declared_plan_fails_before_launch(
    client: SimulatorClient,
    store: RunStore,
    sample_plan_data: object,
) -> None:
    workspace = store.create_workspace(
        make_plan_request(sample_plan_data),
        RELEASE_SCENARIO_PATH,
    )
    workspace.plan_path.unlink()
    with pytest.raises(SimulatorExecutionError) as exc_info:
        client._build_command(workspace)
    assert exc_info.value.run_id == workspace.run_id


def test_baseline_ignores_stray_plan_file(
    client: SimulatorClient,
    store: RunStore,
) -> None:
    workspace = store.create_workspace(
        make_baseline_request(),
        RELEASE_SCENARIO_PATH,
    )
    workspace.plan_path.write_text("{}", encoding="utf-8")
    command = client._build_command(workspace)
    assert "--plan" not in command


def test_command_independent_of_cwd(
    client: SimulatorClient,
    store: RunStore,
    tmp_path: Path,
) -> None:
    workspace = store.create_workspace(
        make_baseline_request(),
        RELEASE_SCENARIO_PATH,
    )
    expected = client._build_command(workspace)
    previous = Path.cwd()
    try:
        os.chdir(tmp_path)
        actual = client._build_command(workspace)
    finally:
        os.chdir(previous)
    assert actual == expected


def test_shell_metacharacters_are_plain_arguments(
    client: SimulatorClient,
    store: RunStore,
) -> None:
    workspace = store.create_workspace(
        make_baseline_request(),
        RELEASE_SCENARIO_PATH,
    )
    command = client._build_command(workspace)
    for part in command:
        assert isinstance(part, str)
    assert not any("&&" in part or "|" in part or ";" in part for part in command)


def test_metadata_mode_required(
    client: SimulatorClient,
    store: RunStore,
) -> None:
    workspace = store.create_workspace(
        make_baseline_request(),
        RELEASE_SCENARIO_PATH,
    )
    workspace.metadata_path.write_text(
        json.dumps({"mode": "unknown"}),
        encoding="utf-8",
    )
    with pytest.raises(SimulatorExecutionError):
        client._build_command(workspace)
