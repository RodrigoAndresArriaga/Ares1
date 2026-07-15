# SimulationService orchestration unit tests
from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock

import pytest
from app.core.errors import (
    ArtifactStorageError,
    ScenarioNotFoundError,
    SimulatorExecutionError,
    SimulatorOutputMissingError,
    SimulatorOutputParseError,
    SimulatorOutputValidationError,
    SimulatorTimeoutError,
    SimulatorUnavailableError,
)
from app.schemas.api import ErrorCode, SimulationRunResponse
from app.schemas.result import OutcomeStatus, SimulationResult
from app.services.run_store import RunStore, sha256_file
from app.services.scenario_registry import ScenarioRegistry
from app.services.simulation_service import SimulationService
from app.services.simulator_client import ProcessEvidence, SimulatorExecutionResult
from tests.conftest import (
    install_release_scenario,
    make_baseline_request,
    make_plan_request,
)


def _process(
    *,
    exit_code: int | None = 0,
    stdout: bytes = b"out",
    stderr: bytes = b"err",
    duration_ms: int = 17,
    timed_out: bool = False,
) -> ProcessEvidence:
    return ProcessEvidence(
        exit_code=exit_code,
        stdout_bytes=stdout,
        stderr_bytes=stderr,
        stdout_text=stdout.decode("utf-8", errors="replace"),
        stderr_text=stderr.decode("utf-8", errors="replace"),
        duration_ms=duration_ms,
        timed_out=timed_out,
    )


def _service(
    tmp_path: Path,
    client: Any,
) -> tuple[SimulationService, RunStore, ScenarioRegistry]:
    scenario_dir = tmp_path / "scenarios"
    install_release_scenario(scenario_dir)
    registry = ScenarioRegistry(scenario_dir)
    store = RunStore(tmp_path / "runs")
    service = SimulationService(registry, store, client)
    return service, store, registry


@pytest.mark.asyncio
async def test_success_baseline_persists_artifacts(
    tmp_path: Path,
    baseline_result_data: Any,
) -> None:
    result = SimulationResult.model_validate(baseline_result_data)
    process = _process(duration_ms=25)
    client = AsyncMock()

    async def _run(workspace: Any) -> SimulatorExecutionResult:
        workspace.result_path.write_text(
            json.dumps(baseline_result_data),
            encoding="utf-8",
        )
        return SimulatorExecutionResult(result=result, process=process)

    client.run = AsyncMock(side_effect=_run)
    service, store, _registry = _service(tmp_path, client)

    response = await service.run_simulation(make_baseline_request())
    assert isinstance(response, SimulationRunResponse)
    assert response.run_id
    assert response.duration_ms == 25
    assert response.result.outcome == OutcomeStatus.FAILURE
    assert client.run.await_count == 1
    workspace_arg = client.run.await_args.args[0]
    assert workspace_arg.result_path.name == "result.json"
    assert not workspace_arg.plan_path.exists() or not json.loads(
        (store._runs_root / response.run_id / "request.json").read_text(
            encoding="utf-8"
        )
    ).get("plan")

    root = store._runs_root / response.run_id
    assert (root / "stdout.log").read_bytes() == b"out"
    assert (root / "stderr.log").read_bytes() == b"err"
    result_bytes = (root / "result.json").read_bytes()
    metadata = json.loads((root / "metadata.json").read_text(encoding="utf-8"))
    assert metadata["status"] == "completed"
    assert metadata["outcome"] == "FAILURE"
    assert metadata["result_sha256"] == sha256_file(root / "result.json")
    assert metadata["error_code"] is None
    assert result_bytes == json.dumps(baseline_result_data).encode("utf-8")


@pytest.mark.asyncio
async def test_success_plan_mode_writes_plan(
    tmp_path: Path,
    valid_plan_result_data: Any,
    sample_plan_data: Any,
) -> None:
    result = SimulationResult.model_validate(valid_plan_result_data)
    process = _process()
    client = AsyncMock()

    async def _run(workspace: Any) -> SimulatorExecutionResult:
        workspace.result_path.write_text(
            json.dumps(valid_plan_result_data),
            encoding="utf-8",
        )
        return SimulatorExecutionResult(result=result, process=process)

    client.run = AsyncMock(side_effect=_run)
    service, store, _ = _service(tmp_path, client)
    response = await service.run_simulation(make_plan_request(sample_plan_data))
    assert response.result.outcome == OutcomeStatus.STABILIZED
    root = store._runs_root / response.run_id
    assert (root / "plan.json").is_file()
    metadata = json.loads((root / "metadata.json").read_text(encoding="utf-8"))
    assert metadata["mode"] == "plan"
    assert metadata["plan_id"] == "sample_plan"


@pytest.mark.asyncio
async def test_rejected_returns_normally(
    tmp_path: Path,
    invalid_plan_result_data: Any,
    invalid_plan_data: Any,
) -> None:
    result = SimulationResult.model_validate(invalid_plan_result_data)
    client = AsyncMock()

    async def _run(workspace: Any) -> SimulatorExecutionResult:
        workspace.result_path.write_text(
            json.dumps(invalid_plan_result_data),
            encoding="utf-8",
        )
        return SimulatorExecutionResult(result=result, process=_process())

    client.run = AsyncMock(side_effect=_run)
    service, _, _ = _service(tmp_path, client)
    response = await service.run_simulation(make_plan_request(invalid_plan_data))
    assert response.result.outcome == OutcomeStatus.REJECTED


@pytest.mark.asyncio
async def test_unknown_scenario_creates_no_workspace(tmp_path: Path) -> None:
    client = AsyncMock()
    service, store, _ = _service(tmp_path, client)
    with pytest.raises(ScenarioNotFoundError):
        await service.run_simulation(
            make_baseline_request().model_copy(
                update={"scenario_id": "does_not_exist"},
            )
        )
    client.run.assert_not_awaited()
    runs_root = tmp_path / "runs"
    assert not runs_root.exists() or list(runs_root.iterdir()) == []


@pytest.mark.asyncio
async def test_artifact_create_failure_skips_client(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = AsyncMock()
    service, store, _ = _service(tmp_path, client)

    def _boom(*_a: Any, **_k: Any) -> Any:
        raise ArtifactStorageError("boom")

    monkeypatch.setattr(store, "create_workspace", _boom)
    with pytest.raises(ArtifactStorageError):
        await service.run_simulation(make_baseline_request())
    client.run.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "error_cls,code",
    [
        (SimulatorUnavailableError, ErrorCode.SIMULATOR_UNAVAILABLE),
        (SimulatorTimeoutError, ErrorCode.SIMULATOR_TIMEOUT),
        (SimulatorExecutionError, ErrorCode.SIMULATOR_EXECUTION_FAILED),
        (SimulatorOutputMissingError, ErrorCode.SIMULATOR_OUTPUT_MISSING),
        (SimulatorOutputParseError, ErrorCode.SIMULATOR_OUTPUT_INVALID_JSON),
        (
            SimulatorOutputValidationError,
            ErrorCode.SIMULATOR_OUTPUT_CONTRACT_ERROR,
        ),
    ],
)
async def test_simulator_errors_attach_run_id_and_fail_metadata(
    tmp_path: Path,
    error_cls: type,
    code: ErrorCode,
) -> None:
    evidence = _process(exit_code=None, duration_ms=9, timed_out=True)
    client = AsyncMock()
    client.run = AsyncMock(
        side_effect=error_cls(process_evidence=evidence),
    )
    service, store, _ = _service(tmp_path, client)
    with pytest.raises(error_cls) as exc_info:
        await service.run_simulation(make_baseline_request())
    assert exc_info.value.run_id is not None
    assert exc_info.value.code == code
    root = store._runs_root / exc_info.value.run_id
    assert (root / "stdout.log").read_bytes() == b"out"
    assert (root / "stderr.log").read_bytes() == b"err"
    metadata = json.loads((root / "metadata.json").read_text(encoding="utf-8"))
    assert metadata["status"] == "failed"
    assert metadata["error_code"] == code.value
    assert metadata["duration_ms"] == 9


@pytest.mark.asyncio
async def test_parse_error_preserves_malformed_result(tmp_path: Path) -> None:
    client = AsyncMock()

    async def _run(workspace: Any) -> Any:
        workspace.result_path.write_bytes(b"{not-json")
        raise SimulatorOutputParseError(
            process_evidence=_process(),
            run_id=workspace.run_id,
        )

    client.run = AsyncMock(side_effect=_run)
    service, store, _ = _service(tmp_path, client)
    with pytest.raises(SimulatorOutputParseError) as exc_info:
        await service.run_simulation(make_baseline_request())
    root = store._runs_root / exc_info.value.run_id
    assert (root / "result.json").read_bytes() == b"{not-json"
    metadata = json.loads((root / "metadata.json").read_text(encoding="utf-8"))
    assert metadata["result_sha256"] == sha256_file(root / "result.json")


@pytest.mark.asyncio
async def test_missing_output_keeps_result_absent(tmp_path: Path) -> None:
    client = AsyncMock()
    client.run = AsyncMock(
        side_effect=SimulatorOutputMissingError(process_evidence=_process()),
    )
    service, store, _ = _service(tmp_path, client)
    with pytest.raises(SimulatorOutputMissingError) as exc_info:
        await service.run_simulation(make_baseline_request())
    root = store._runs_root / exc_info.value.run_id
    assert not (root / "result.json").exists()
    metadata = json.loads((root / "metadata.json").read_text(encoding="utf-8"))
    assert metadata["result_sha256"] is None


@pytest.mark.asyncio
async def test_failure_finalization_artifact_error_precedence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = AsyncMock()
    client.run = AsyncMock(
        side_effect=SimulatorTimeoutError(process_evidence=_process()),
    )
    service, store, _ = _service(tmp_path, client)

    def _fail_meta(*_a: Any, **_k: Any) -> None:
        raise ArtifactStorageError("meta failed")

    monkeypatch.setattr(store, "write_failed_metadata", _fail_meta)
    with pytest.raises(ArtifactStorageError) as exc_info:
        await service.run_simulation(make_baseline_request())
    assert exc_info.value.run_id is not None
    assert isinstance(exc_info.value.__cause__, SimulatorTimeoutError)


@pytest.mark.asyncio
async def test_cancellation_is_reraised(tmp_path: Path) -> None:
    import asyncio

    client = AsyncMock()
    client.run = AsyncMock(side_effect=asyncio.CancelledError())
    service, store, _ = _service(tmp_path, client)
    with pytest.raises(asyncio.CancelledError):
        await service.run_simulation(make_baseline_request())
    runs = list(store._runs_root.iterdir())
    assert len(runs) == 1
    metadata = json.loads((runs[0] / "metadata.json").read_text(encoding="utf-8"))
    assert metadata["status"] == "created"


@pytest.mark.asyncio
async def test_service_does_not_know_http_status(tmp_path: Path) -> None:
    import inspect

    source = inspect.getsource(SimulationService)
    assert "404" not in source
    assert "502" not in source
    assert "503" not in source
    assert "504" not in source
    assert "HTTP" not in source
