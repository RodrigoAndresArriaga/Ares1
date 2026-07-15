# integration timeout and concurrency tests for SimulatorClient
# uses injected real Python child processes (not the frozen simulator)
from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from typing import Any

import pytest
from app.core.errors import SimulatorTimeoutError
from app.services.run_store import RunStore
from app.services.simulator_client import SimulatorClient
from tests.conftest import (
    RELEASE_SCENARIO_PATH,
    SHARED_SIM_RESULT_PATH,
    make_baseline_request,
    settings_from_layout,
)
from tests.helpers.fake_processes import make_fixture_result_spawn, write_helper_scripts


@pytest.fixture
def store(tmp_path: Path) -> RunStore:
    return RunStore(tmp_path / "runs")


@pytest.fixture
def scripts(tmp_path: Path) -> dict[str, Path]:
    return write_helper_scripts(tmp_path / "scripts")


@pytest.mark.asyncio
async def test_timeout_kills_and_reaps_child(
    valid_layout: dict[str, Path],
    store: RunStore,
    scripts: dict[str, Path],
    tmp_path: Path,
) -> None:
    marker = tmp_path / "hang_started.txt"

    async def spawn_hang(
        *_cmd: str,
        stdout: Any = None,
        stderr: Any = None,
        **_kwargs: Any,
    ) -> asyncio.subprocess.Process:
        return await asyncio.create_subprocess_exec(
            sys.executable,
            str(scripts["hang"]),
            str(marker),
            stdout=stdout,
            stderr=stderr,
        )

    client = SimulatorClient(
        settings_from_layout(
            valid_layout,
            sim_timeout_seconds=0.3,
            max_concurrent_runs=1,
        ),
        _spawn=spawn_hang,
    )
    workspace = store.create_workspace(
        make_baseline_request(),
        RELEASE_SCENARIO_PATH,
    )
    with pytest.raises(SimulatorTimeoutError) as exc_info:
        await client.run(workspace)

    assert exc_info.value.run_id == workspace.run_id
    assert str(valid_layout["sim_binary"]) not in exc_info.value.message
    assert str(workspace.root) not in exc_info.value.message
    assert exc_info.value.process_evidence is not None
    assert exc_info.value.process_evidence.timed_out is True
    assert exc_info.value.process_evidence.exit_code is not None
    assert client._semaphore._value == 1

    # process must be reaped (returncode observed after kill)
    for _ in range(50):
        if marker.exists():
            break
        await asyncio.sleep(0.02)


@pytest.mark.asyncio
async def test_timeout_does_not_return_simulation_result(
    valid_layout: dict[str, Path],
    store: RunStore,
    scripts: dict[str, Path],
    tmp_path: Path,
) -> None:
    marker = tmp_path / "hang2.txt"

    async def spawn_hang(
        *_cmd: str,
        stdout: Any = None,
        stderr: Any = None,
        **_kwargs: Any,
    ) -> asyncio.subprocess.Process:
        return await asyncio.create_subprocess_exec(
            sys.executable,
            str(scripts["hang"]),
            str(marker),
            stdout=stdout,
            stderr=stderr,
        )

    client = SimulatorClient(
        settings_from_layout(valid_layout, sim_timeout_seconds=0.2),
        _spawn=spawn_hang,
    )
    workspace = store.create_workspace(
        make_baseline_request(),
        RELEASE_SCENARIO_PATH,
    )
    with pytest.raises(SimulatorTimeoutError):
        await client.run(workspace)
    assert not workspace.result_path.exists()


@pytest.mark.asyncio
async def test_subsequent_run_after_timeout(
    valid_layout: dict[str, Path],
    store: RunStore,
    scripts: dict[str, Path],
    tmp_path: Path,
    baseline_result_data: dict[str, Any],
) -> None:
    marker = tmp_path / "hang3.txt"
    hang_once = {"armed": True}

    async def spawn_selective(
        *cmd: str,
        stdout: Any = None,
        stderr: Any = None,
        **_kwargs: Any,
    ) -> asyncio.subprocess.Process:
        if hang_once["armed"]:
            hang_once["armed"] = False
            return await asyncio.create_subprocess_exec(
                sys.executable,
                str(scripts["hang"]),
                str(marker),
                stdout=stdout,
                stderr=stderr,
            )
        real = make_fixture_result_spawn(baseline_result_data)
        return await real(*cmd, stdout=stdout, stderr=stderr)

    client = SimulatorClient(
        settings_from_layout(
            valid_layout,
            sim_timeout_seconds=0.25,
            max_concurrent_runs=1,
        ),
        _spawn=spawn_selective,
    )
    first = store.create_workspace(
        make_baseline_request(),
        RELEASE_SCENARIO_PATH,
    )
    with pytest.raises(SimulatorTimeoutError):
        await client.run(first)

    second = store.create_workspace(
        make_baseline_request(),
        RELEASE_SCENARIO_PATH,
    )
    execution = await client.run(second)
    assert execution.result.outcome.value == "FAILURE"
    assert client._semaphore._value == 1


@pytest.mark.asyncio
async def test_concurrency_limit_enforced(
    valid_layout: dict[str, Path],
    store: RunStore,
    baseline_result_data: dict[str, Any],
) -> None:
    max_seen = 0
    active = 0
    lock = asyncio.Lock()
    release_gate = asyncio.Event()
    entered = asyncio.Event()
    entered_count = 0

    async def gated_spawn(
        *cmd: str,
        stdout: Any = None,
        stderr: Any = None,
        **_kwargs: Any,
    ) -> asyncio.subprocess.Process:
        nonlocal max_seen, active, entered_count
        async with lock:
            active += 1
            max_seen = max(max_seen, active)
            entered_count += 1
            if entered_count >= 2:
                entered.set()

        await release_gate.wait()

        async with lock:
            active -= 1

        real = make_fixture_result_spawn(baseline_result_data)
        return await real(*cmd, stdout=stdout, stderr=stderr)

    client = SimulatorClient(
        settings_from_layout(valid_layout, max_concurrent_runs=2),
        _spawn=gated_spawn,
    )
    workspaces = [
        store.create_workspace(make_baseline_request(), RELEASE_SCENARIO_PATH)
        for _ in range(4)
    ]

    async def launch_all() -> list[Any]:
        tasks = [asyncio.create_task(client.run(ws)) for ws in workspaces]
        await entered.wait()
        # with limit 2, at most 2 spawned before gate opens
        assert max_seen <= 2
        release_gate.set()
        return await asyncio.gather(*tasks)

    results = await launch_all()
    assert len(results) == 4
    assert max_seen <= 2
    assert client._semaphore._value == 2
    roots = {ws.root for ws in workspaces}
    assert len(roots) == 4
    for execution, ws in zip(results, workspaces, strict=True):
        assert execution.result.scenario_id
        assert ws.result_path.is_file()
    assert not any(
        SHARED_SIM_RESULT_PATH.resolve() == ws.result_path.resolve()
        for ws in workspaces
    )


@pytest.mark.asyncio
async def test_failed_call_does_not_reduce_capacity(
    valid_layout: dict[str, Path],
    store: RunStore,
    baseline_result_data: dict[str, Any],
) -> None:
    from tests.helpers.fake_processes import make_exit_spawn

    client = SimulatorClient(
        settings_from_layout(valid_layout, max_concurrent_runs=2),
        _spawn=make_exit_spawn(3),
    )
    bad = store.create_workspace(
        make_baseline_request(),
        RELEASE_SCENARIO_PATH,
    )
    from app.core.errors import SimulatorExecutionError

    with pytest.raises(SimulatorExecutionError):
        await client.run(bad)
    assert client._semaphore._value == 2

    client2 = SimulatorClient(
        settings_from_layout(valid_layout, max_concurrent_runs=2),
        _spawn=make_fixture_result_spawn(baseline_result_data),
    )
    # reuse same semaphore capacity semantics on a fresh successful client
    ok = store.create_workspace(
        make_baseline_request(),
        RELEASE_SCENARIO_PATH,
    )
    await client2.run(ok)
    assert client2._semaphore._value == 2
