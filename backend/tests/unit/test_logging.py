# structured logging event trail tests
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock

import pytest
from app.core.config import clear_settings_cache
from app.core.errors import SimulatorTimeoutError
from app.core.logging import configure_logging
from app.main import create_app
from app.schemas.result import SimulationResult
from app.services.run_store import RunStore
from app.services.scenario_registry import ScenarioRegistry
from app.services.simulation_service import SimulationService
from app.services.simulator_client import ProcessEvidence, SimulatorExecutionResult
from tests.conftest import (
    install_release_scenario,
    make_baseline_request,
    make_plan_request,
    make_valid_layout,
    settings_from_layout,
)


@pytest.fixture(autouse=True)
def _clear_settings_cache() -> Any:
    clear_settings_cache()
    yield
    clear_settings_cache()


def _process() -> ProcessEvidence:
    return ProcessEvidence(
        exit_code=0,
        stdout_bytes=b"",
        stderr_bytes=b"",
        stdout_text="",
        stderr_text="",
        duration_ms=11,
        timed_out=False,
    )


def _events(caplog: pytest.LogCaptureFixture) -> list[str]:
    return [
        getattr(r, "event")
        for r in caplog.records
        if getattr(r, "event", None) is not None
    ]


@pytest.mark.asyncio
async def test_success_event_order(
    tmp_path: Path,
    baseline_result_data: Any,
    caplog: pytest.LogCaptureFixture,
) -> None:
    result = SimulationResult.model_validate(baseline_result_data)
    client = AsyncMock()

    async def _run(workspace: Any) -> SimulatorExecutionResult:
        workspace.result_path.write_text(
            __import__("json").dumps(baseline_result_data),
            encoding="utf-8",
        )
        return SimulatorExecutionResult(result=result, process=_process())

    client.run = AsyncMock(side_effect=_run)
    scenario_dir = tmp_path / "scenarios"
    install_release_scenario(scenario_dir)
    service = SimulationService(
        ScenarioRegistry(scenario_dir),
        RunStore(tmp_path / "runs"),
        client,
    )
    with caplog.at_level(logging.INFO, logger="ares.simulation"):
        response = await service.run_simulation(make_baseline_request())
    events = _events(caplog)
    assert events == [
        "simulation_run_created",
        "simulator_process_started",
        "simulator_process_completed",
        "simulator_output_validated",
        "simulation_run_completed",
    ]
    run_ids = {
        getattr(r, "run_id")
        for r in caplog.records
        if getattr(r, "event", None) is not None
    }
    assert run_ids == {response.run_id}
    assert any(
        getattr(r, "outcome", None) == "FAILURE"
        for r in caplog.records
        if getattr(r, "event", None) == "simulation_run_completed"
    )
    assert "simulation_run_failed" not in events
    joined = " ".join(r.getMessage() for r in caplog.records)
    assert "telemetry_history" not in joined
    assert str(tmp_path) not in joined or "event=" in joined
    # absolute workspace paths must not appear as structured context values
    for record in caplog.records:
        for key in ("run_id", "scenario_id", "plan_id", "mode", "outcome"):
            value = getattr(record, key, None)
            if isinstance(value, str):
                assert ":\\" not in value
                assert not value.startswith("/")


@pytest.mark.asyncio
async def test_rejected_logs_completed_not_failed(
    tmp_path: Path,
    invalid_plan_result_data: Any,
    invalid_plan_data: Any,
    caplog: pytest.LogCaptureFixture,
) -> None:
    result = SimulationResult.model_validate(invalid_plan_result_data)
    client = AsyncMock()

    async def _run(workspace: Any) -> SimulatorExecutionResult:
        workspace.result_path.write_text(
            __import__("json").dumps(invalid_plan_result_data),
            encoding="utf-8",
        )
        return SimulatorExecutionResult(result=result, process=_process())

    client.run = AsyncMock(side_effect=_run)
    scenario_dir = tmp_path / "scenarios"
    install_release_scenario(scenario_dir)
    service = SimulationService(
        ScenarioRegistry(scenario_dir),
        RunStore(tmp_path / "runs"),
        client,
    )
    with caplog.at_level(logging.INFO, logger="ares.simulation"):
        await service.run_simulation(make_plan_request(invalid_plan_data))
    events = _events(caplog)
    assert "simulation_run_completed" in events
    assert "simulation_run_failed" not in events
    assert any(
        getattr(r, "outcome", None) == "REJECTED" for r in caplog.records
    )


@pytest.mark.asyncio
async def test_timeout_logs_failed(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    client = AsyncMock()
    client.run = AsyncMock(
        side_effect=SimulatorTimeoutError(
            process_evidence=_process(),
        ),
    )
    scenario_dir = tmp_path / "scenarios"
    install_release_scenario(scenario_dir)
    service = SimulationService(
        ScenarioRegistry(scenario_dir),
        RunStore(tmp_path / "runs"),
        client,
    )
    with caplog.at_level(logging.INFO, logger="ares.simulation"):
        with pytest.raises(SimulatorTimeoutError):
            await service.run_simulation(make_baseline_request())
    events = _events(caplog)
    assert events[0] == "simulation_run_created"
    assert "simulator_process_started" in events
    assert "simulation_run_failed" in events
    assert "simulation_run_completed" not in events


def test_configure_logging_no_duplicate_handlers(tmp_path: Path) -> None:
    layout = make_valid_layout(tmp_path)
    settings = settings_from_layout(layout)
    configure_logging(settings)
    configure_logging(settings)
    root = logging.getLogger("ares")
    marked = [
        h for h in root.handlers if getattr(h, "ares_structured_handler", False)
    ]
    assert len(marked) == 1
    create_app(settings_override=settings)
    create_app(settings_override=settings)
    marked = [
        h for h in root.handlers if getattr(h, "ares_structured_handler", False)
    ]
    assert len(marked) == 1


def test_log_level_respected(tmp_path: Path) -> None:
    layout = make_valid_layout(tmp_path)
    settings = settings_from_layout(layout, log_level="ERROR")
    configure_logging(settings)
    assert logging.getLogger("ares").level == logging.ERROR
