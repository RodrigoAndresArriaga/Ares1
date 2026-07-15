# unit tests for SimulatorClient process lifecycle (injected spawn)
from __future__ import annotations

import asyncio
import inspect
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from app.core.errors import (
    SimulatorExecutionError,
    SimulatorUnavailableError,
)
from app.schemas.result import OutcomeStatus
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


def _client(
    layout: dict[str, Path],
    spawn: Any,
    **overrides: Any,
) -> SimulatorClient:
    return SimulatorClient(
        settings_from_layout(layout, **overrides),
        _spawn=spawn,
    )


@pytest.mark.asyncio
async def test_spawn_receives_pipes_and_arg_list(
    valid_layout: dict[str, Path],
    store: RunStore,
    baseline_result_data: dict[str, Any],
) -> None:
    calls: list[tuple[tuple[Any, ...], dict[str, Any]]] = []

    async def tracking_spawn(
        *cmd: str,
        stdout: Any = None,
        stderr: Any = None,
        **kwargs: Any,
    ) -> asyncio.subprocess.Process:
        calls.append((cmd, {"stdout": stdout, "stderr": stderr, **kwargs}))
        real = make_fixture_result_spawn(baseline_result_data)
        return await real(*cmd, stdout=stdout, stderr=stderr, **kwargs)

    client = _client(valid_layout, tracking_spawn)
    workspace = store.create_workspace(
        make_baseline_request(),
        RELEASE_SCENARIO_PATH,
    )
    await client.run(workspace)
    assert len(calls) == 1
    cmd, kwargs = calls[0]
    assert cmd[0] == str(client._binary)
    assert kwargs["stdout"] is asyncio.subprocess.PIPE
    assert kwargs["stderr"] is asyncio.subprocess.PIPE


@pytest.mark.asyncio
async def test_return_code_and_bytes_preserved(
    valid_layout: dict[str, Path],
    store: RunStore,
    baseline_result_data: dict[str, Any],
) -> None:
    raw = __import__("json").dumps(baseline_result_data).encode("utf-8")
    spawn = make_exit_spawn(
        0,
        write_result=raw,
        stdout_data=b"stdout-bytes",
        stderr_data=b"stderr-bytes",
    )
    client = _client(valid_layout, spawn)
    workspace = store.create_workspace(
        make_baseline_request(),
        RELEASE_SCENARIO_PATH,
    )
    execution = await client.run(workspace)
    assert execution.process.exit_code == 0
    assert execution.process.stdout_bytes == b"stdout-bytes"
    assert execution.process.stderr_bytes == b"stderr-bytes"
    assert execution.process.duration_ms >= 0
    assert execution.process.timed_out is False


@pytest.mark.asyncio
async def test_launch_failure_maps_to_unavailable(
    valid_layout: dict[str, Path],
    store: RunStore,
) -> None:
    async def boom(
        *_args: str,
        **_kwargs: Any,
    ) -> asyncio.subprocess.Process:
        raise FileNotFoundError("missing")

    client = _client(valid_layout, boom)
    workspace = store.create_workspace(
        make_baseline_request(),
        RELEASE_SCENARIO_PATH,
    )
    with pytest.raises(SimulatorUnavailableError) as exc_info:
        await client.run(workspace)
    assert exc_info.value.run_id == workspace.run_id
    assert str(client._binary) not in exc_info.value.message


@pytest.mark.asyncio
async def test_nonzero_exit_maps_to_execution_error(
    valid_layout: dict[str, Path],
    store: RunStore,
    baseline_result_data: dict[str, Any],
) -> None:
    raw = __import__("json").dumps(baseline_result_data).encode("utf-8")
    spawn = make_exit_spawn(7, write_result=raw)
    client = _client(valid_layout, spawn)
    workspace = store.create_workspace(
        make_baseline_request(),
        RELEASE_SCENARIO_PATH,
    )
    with pytest.raises(SimulatorExecutionError) as exc_info:
        await client.run(workspace)
    assert exc_info.value.run_id == workspace.run_id
    assert exc_info.value.process_evidence is not None
    assert exc_info.value.process_evidence.exit_code == 7


@pytest.mark.asyncio
async def test_nonzero_exit_does_not_become_mission_result(
    valid_layout: dict[str, Path],
    store: RunStore,
    baseline_result_data: dict[str, Any],
) -> None:
    raw = __import__("json").dumps(baseline_result_data).encode("utf-8")
    spawn = make_exit_spawn(1, write_result=raw)
    client = _client(valid_layout, spawn)
    workspace = store.create_workspace(
        make_baseline_request(),
        RELEASE_SCENARIO_PATH,
    )
    with pytest.raises(SimulatorExecutionError):
        await client.run(workspace)


@pytest.mark.asyncio
async def test_semaphore_releases_after_normal_completion(
    valid_layout: dict[str, Path],
    store: RunStore,
    baseline_result_data: dict[str, Any],
) -> None:
    spawn = make_fixture_result_spawn(baseline_result_data)
    client = _client(valid_layout, spawn, max_concurrent_runs=1)
    workspace = store.create_workspace(
        make_baseline_request(),
        RELEASE_SCENARIO_PATH,
    )
    await client.run(workspace)
    assert client._semaphore._value == 1


@pytest.mark.asyncio
async def test_semaphore_releases_after_launch_failure(
    valid_layout: dict[str, Path],
    store: RunStore,
) -> None:
    async def boom(
        *_args: str,
        **_kwargs: Any,
    ) -> asyncio.subprocess.Process:
        raise OSError("launch failed")

    client = _client(valid_layout, boom, max_concurrent_runs=1)
    workspace = store.create_workspace(
        make_baseline_request(),
        RELEASE_SCENARIO_PATH,
    )
    with pytest.raises(SimulatorUnavailableError):
        await client.run(workspace)
    assert client._semaphore._value == 1


@pytest.mark.asyncio
async def test_semaphore_releases_after_nonzero_exit(
    valid_layout: dict[str, Path],
    store: RunStore,
) -> None:
    spawn = make_exit_spawn(2)
    client = _client(valid_layout, spawn, max_concurrent_runs=1)
    workspace = store.create_workspace(
        make_baseline_request(),
        RELEASE_SCENARIO_PATH,
    )
    with pytest.raises(SimulatorExecutionError):
        await client.run(workspace)
    assert client._semaphore._value == 1


@pytest.mark.asyncio
async def test_caller_cancellation_cleans_up_child(
    valid_layout: dict[str, Path],
    store: RunStore,
) -> None:
    started = asyncio.Event()
    released = asyncio.Event()

    class FakeProc:
        def __init__(self) -> None:
            self.returncode: int | None = None
            self._kill_called = False

        def kill(self) -> None:
            self._kill_called = True
            self.returncode = -9
            released.set()

        async def communicate(self) -> tuple[bytes, bytes]:
            started.set()
            await released.wait()
            return b"", b""

        async def wait(self) -> int:
            await released.wait()
            return self.returncode or 0

    fake = FakeProc()

    async def spawn_hang(
        *_args: str,
        **_kwargs: Any,
    ) -> Any:
        return fake

    client = _client(valid_layout, spawn_hang, max_concurrent_runs=1)
    workspace = store.create_workspace(
        make_baseline_request(),
        RELEASE_SCENARIO_PATH,
    )
    task = asyncio.create_task(client.run(workspace))
    await started.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert fake._kill_called is True
    assert client._semaphore._value == 1


@pytest.mark.asyncio
async def test_no_synchronous_subprocess_api_in_module() -> None:
    import app.services.simulator_client as module

    source = inspect.getsource(module)
    assert "subprocess.run" not in source
    assert "subprocess.Popen" not in source
    assert "shell=True" not in source
    assert "os.system" not in source


@pytest.mark.asyncio
async def test_mission_failure_returned_as_data(
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


@pytest.mark.asyncio
async def test_binary_missing_at_runtime(
    valid_layout: dict[str, Path],
    store: RunStore,
) -> None:
    client = _client(valid_layout, AsyncMock())
    valid_layout["sim_binary"].unlink()
    workspace = store.create_workspace(
        make_baseline_request(),
        RELEASE_SCENARIO_PATH,
    )
    with pytest.raises(SimulatorUnavailableError):
        await client.run(workspace)


@pytest.mark.asyncio
async def test_preexisting_result_rejected(
    valid_layout: dict[str, Path],
    store: RunStore,
) -> None:
    client = _client(valid_layout, MagicMock())
    workspace = store.create_workspace(
        make_baseline_request(),
        RELEASE_SCENARIO_PATH,
    )
    workspace.result_path.write_text("{}", encoding="utf-8")
    with pytest.raises(SimulatorExecutionError):
        await client.run(workspace)
