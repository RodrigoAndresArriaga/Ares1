# Phase 5 Step 3 MissionPlanSimulationService orchestration tests
from __future__ import annotations

import asyncio
import copy
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from app.core.errors import (
    PlanningContextMismatchError,
    PlanningInProgressError,
    PlanningSimulationIntegrityError,
    PlanningValidationStorageError,
    SimulatorTimeoutError,
)
from app.schemas.api import SimulationRunRequest, SimulationRunResponse
from app.schemas.planning_validation import PlanningValidationStatus
from app.schemas.result import OutcomeStatus, SimulationResult
from app.services.mission_plan_simulation_service import MissionPlanSimulationService
from app.services.run_store import RunStore, sha256_file
from tests.conftest import (
    PLANNING_ATTEMPT_ID,
    RELEASE_SCENARIO_PATH,
    make_baseline_request,
    make_multi_action_retrieval_result,
    make_planning_attempt_store,
    make_planning_validation_store,
)
from tests.unit.test_mission_planning_service import (
    OTHER_SESSION_ID,
    SESSION_ID,
    FakeRetrievalService,
    SequenceClock,
    _fake_generate,
    _seed_replaying,
    baseline_result_bytes,
    make_replaying_session,
    make_runs_root,
    make_service,
    seed_completed_run,
)

CANDIDATE_RUN_ID = "00000000-0000-4000-8000-000000000030"
T0 = datetime(2026, 7, 15, 12, 0, 0, tzinfo=timezone.utc)
T1 = datetime(2026, 7, 15, 12, 1, 0, tzinfo=timezone.utc)
T2 = datetime(2026, 7, 15, 12, 2, 0, tzinfo=timezone.utc)
T3 = datetime(2026, 7, 15, 12, 3, 0, tzinfo=timezone.utc)
T4 = datetime(2026, 7, 15, 12, 4, 0, tzinfo=timezone.utc)
REPLAY_START = T0 + timedelta(seconds=2)


class PersistingFakeSimulationService:
    def __init__(
        self,
        run_store: RunStore,
        *,
        result_data: dict[str, Any],
        run_id: str = CANDIDATE_RUN_ID,
        duration_ms: int = 25,
        gate: asyncio.Event | None = None,
        error: Exception | None = None,
    ) -> None:
        self.run_store = run_store
        self.result_data = result_data
        self.run_id = run_id
        self.duration_ms = duration_ms
        self.gate = gate
        self.error = error
        self.calls: list[SimulationRunRequest] = []

    async def run_simulation(self, request: SimulationRunRequest) -> SimulationRunResponse:
        self.calls.append(request)
        if self.gate is not None:
            await self.gate.wait()
        if self.error is not None:
            raise self.error
        plan_request = SimulationRunRequest(
            scenario_id=request.scenario_id,
            plan=request.plan,
        )
        workspace = self.run_store.create_workspace(plan_request, RELEASE_SCENARIO_PATH)
        result = SimulationResult.model_validate(self.result_data)
        result_bytes = json.dumps(
            result.model_dump(mode="json"),
            ensure_ascii=False,
            indent=2,
            separators=(", ", ": "),
        ).encode("utf-8") + b"\n"
        workspace.result_path.write_bytes(result_bytes)
        self.run_store.write_completed_metadata(
            workspace,
            result_sha256=sha256_file(workspace.result_path),
            process_exit_code=0,
            duration_ms=self.duration_ms,
            outcome=result.outcome.value,
        )
        return SimulationRunResponse(
            run_id=workspace.run_id,
            duration_ms=self.duration_ms,
            result=result,
        )


def _candidate_result_data(
    baseline_result_data: dict[str, Any],
    *,
    outcome: str,
    plan_id: str | None = None,
    failure_reasons: list[str] | None = None,
    valid_plan: bool = True,
) -> dict[str, Any]:
    resolved_plan_id = plan_id if plan_id is not None else "sample_plan"
    data = copy.deepcopy(baseline_result_data)
    data["outcome"] = outcome
    data["plan_id"] = resolved_plan_id
    data["valid_plan"] = valid_plan
    data["failure_reasons"] = (
        failure_reasons
        if failure_reasons is not None
        else ([] if outcome == "STABILIZED" else list(baseline_result_data["failure_reasons"]))
    )
    return data


def make_plan_simulation_service(
    tmp_path: Path,
    *,
    retrieval: FakeRetrievalService,
    simulation: PersistingFakeSimulationService,
    planner_provider: Any | None = None,
    clock: SequenceClock | None = None,
    sample_plan_data: Any,
) -> tuple[MissionPlanSimulationService, dict[str, Any]]:
    plan_clock = clock or SequenceClock([T0, T1, T2, T3, T4])
    planning_service, deps = make_service(
        tmp_path,
        retrieval=retrieval,
        planner_provider=planner_provider,
        clock=SequenceClock([REPLAY_START]),
    )
    if planner_provider is None:
        deps["provider"].generate_plan = AsyncMock(
            side_effect=_fake_generate(sample_plan_data),
        )
    attempt_store = make_planning_attempt_store(tmp_path)
    validation_store = make_planning_validation_store(tmp_path)
    service = MissionPlanSimulationService(
        mission_planning_service=planning_service,
        planning_attempt_store=attempt_store,
        validation_store=validation_store,
        run_store=deps["run_store"],
        simulation_service=simulation,
        now_provider=plan_clock,
    )
    deps["attempt_store"] = attempt_store
    deps["validation_store"] = validation_store
    deps["plan_simulation_service"] = service
    deps["simulation"] = simulation
    return service, deps


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "outcome",
    [OutcomeStatus.STABILIZED, OutcomeStatus.FAILURE, OutcomeStatus.REJECTED],
)
async def test_successful_simulation_for_each_outcome(
    tmp_path: Path,
    baseline_result_data: Any,
    sample_plan_data: Any,
    outcome: OutcomeStatus,
) -> None:
    retrieval = FakeRetrievalService(result=make_multi_action_retrieval_result())
    run_store = RunStore(make_runs_root(tmp_path))
    candidate_data = _candidate_result_data(
        baseline_result_data,
        outcome=outcome.value,
        plan_id=sample_plan_data["plan_id"],
        valid_plan=outcome != OutcomeStatus.REJECTED,
        failure_reasons=(
            ["invalid_plan"]
            if outcome == OutcomeStatus.REJECTED
            else (
                []
                if outcome == OutcomeStatus.STABILIZED
                else baseline_result_data["failure_reasons"]
            )
        ),
    )
    simulation = PersistingFakeSimulationService(run_store, result_data=candidate_data)
    service, deps = make_plan_simulation_service(
        tmp_path,
        retrieval=retrieval,
        simulation=simulation,
        sample_plan_data=sample_plan_data,
    )
    _seed_replaying(deps)

    response = await service.generate_and_simulate(SESSION_ID)

    assert len(retrieval.calls) == 1
    assert len(simulation.calls) == 1
    assert simulation.calls[0].scenario_id == baseline_result_data["scenario_id"]
    assert simulation.calls[0].plan is not None
    assert simulation.calls[0].plan.plan_id == sample_plan_data["plan_id"]
    assert response.attempt.generation_result.plan.plan_id == sample_plan_data["plan_id"]
    assert response.validation.status == PlanningValidationStatus.SIMULATION_COMPLETE
    assert response.validation.candidate is not None
    assert response.validation.candidate.outcome == outcome
    assert response.candidate_result_path == (
        f"/api/sim/result/{response.validation.candidate.run_id}"
    )
    assert response.baseline_result_path == (
        f"/api/sim/result/{response.validation.baseline_run_id}"
    )
    assert response.validation.comparison is not None
    validation = deps["validation_store"].read_validation(PLANNING_ATTEMPT_ID)
    assert validation.status == PlanningValidationStatus.SIMULATION_COMPLETE


@pytest.mark.asyncio
async def test_exact_recovery_plan_submitted(
    tmp_path: Path,
    baseline_result_data: Any,
    sample_plan_data: Any,
) -> None:
    retrieval = FakeRetrievalService(result=make_multi_action_retrieval_result())
    run_store = RunStore(make_runs_root(tmp_path))
    candidate_data = _candidate_result_data(
        baseline_result_data,
        outcome="STABILIZED",
        plan_id=sample_plan_data["plan_id"],
    )
    simulation = PersistingFakeSimulationService(run_store, result_data=candidate_data)
    service, deps = make_plan_simulation_service(
        tmp_path,
        retrieval=retrieval,
        simulation=simulation,
        sample_plan_data=sample_plan_data,
    )
    _seed_replaying(deps)
    response = await service.generate_and_simulate(SESSION_ID)
    submitted = simulation.calls[0].plan
    assert submitted is not None
    assert submitted.model_dump() == response.attempt.generation_result.plan.model_dump()


@pytest.mark.asyncio
async def test_baseline_scenario_mismatch(
    tmp_path: Path,
    baseline_result_data: Any,
    sample_plan_data: Any,
) -> None:
    retrieval = FakeRetrievalService(result=make_multi_action_retrieval_result())
    run_store = RunStore(make_runs_root(tmp_path))
    simulation = PersistingFakeSimulationService(
        run_store,
        result_data=_candidate_result_data(baseline_result_data, outcome="STABILIZED"),
    )
    service, deps = make_plan_simulation_service(
        tmp_path,
        retrieval=retrieval,
        simulation=simulation,
        sample_plan_data=sample_plan_data,
    )
    run_id = seed_completed_run(run_store, baseline_result_bytes())
    bad_bytes = json.loads(baseline_result_bytes().decode("utf-8"))
    bad_bytes["scenario_id"] = "other_scenario"
    run_dir = run_store._runs_root / run_id
    run_dir.joinpath("result.json").write_text(
        json.dumps(bad_bytes, indent=2) + "\n",
        encoding="utf-8",
    )
    deps["session_store"].create_session(make_replaying_session(baseline_run_id=run_id))
    with pytest.raises((PlanningSimulationIntegrityError, PlanningContextMismatchError)):
        await service.generate_and_simulate(SESSION_ID)
    assert len(simulation.calls) == 0


@pytest.mark.asyncio
async def test_baseline_outcome_mismatch(
    tmp_path: Path,
    baseline_result_data: Any,
    sample_plan_data: Any,
) -> None:
    retrieval = FakeRetrievalService(result=make_multi_action_retrieval_result())
    run_store = RunStore(make_runs_root(tmp_path))
    simulation = PersistingFakeSimulationService(
        run_store,
        result_data=_candidate_result_data(baseline_result_data, outcome="STABILIZED"),
    )
    service, deps = make_plan_simulation_service(
        tmp_path,
        retrieval=retrieval,
        simulation=simulation,
        sample_plan_data=sample_plan_data,
    )
    run_id = seed_completed_run(run_store, baseline_result_bytes())
    session = make_replaying_session(baseline_run_id=run_id)
    bad = session.model_copy(update={"baseline_outcome": OutcomeStatus.STABILIZED})
    deps["session_store"].create_session(bad)
    with pytest.raises((PlanningSimulationIntegrityError, PlanningContextMismatchError)):
        await service.generate_and_simulate(SESSION_ID)


@pytest.mark.asyncio
async def test_baseline_hash_mismatch(
    tmp_path: Path,
    baseline_result_data: Any,
    sample_plan_data: Any,
) -> None:
    retrieval = FakeRetrievalService(result=make_multi_action_retrieval_result())
    run_store = RunStore(make_runs_root(tmp_path))
    simulation = PersistingFakeSimulationService(
        run_store,
        result_data=_candidate_result_data(baseline_result_data, outcome="STABILIZED"),
    )
    service, deps = make_plan_simulation_service(
        tmp_path,
        retrieval=retrieval,
        simulation=simulation,
        sample_plan_data=sample_plan_data,
    )
    workspace = run_store.create_workspace(make_baseline_request(), RELEASE_SCENARIO_PATH)
    workspace.result_path.write_bytes(baseline_result_bytes())
    run_store.write_completed_metadata(
        workspace,
        result_sha256="B" * 64,
        process_exit_code=0,
        duration_ms=1,
        outcome="FAILURE",
    )
    deps["session_store"].create_session(
        make_replaying_session(baseline_run_id=workspace.run_id),
    )
    with pytest.raises(PlanningSimulationIntegrityError):
        await service.generate_and_simulate(SESSION_ID)


@pytest.mark.asyncio
async def test_simulator_infrastructure_failure_persists_error(
    tmp_path: Path,
    baseline_result_data: Any,
    sample_plan_data: Any,
) -> None:
    retrieval = FakeRetrievalService(result=make_multi_action_retrieval_result())
    run_store = RunStore(make_runs_root(tmp_path))
    simulation = PersistingFakeSimulationService(
        run_store,
        result_data=_candidate_result_data(baseline_result_data, outcome="STABILIZED"),
        error=SimulatorTimeoutError("timeout", run_id="pending"),
    )
    service, deps = make_plan_simulation_service(
        tmp_path,
        retrieval=retrieval,
        simulation=simulation,
        sample_plan_data=sample_plan_data,
    )
    _seed_replaying(deps)
    with pytest.raises(SimulatorTimeoutError):
        await service.generate_and_simulate(SESSION_ID)
    record = deps["validation_store"].read_validation(PLANNING_ATTEMPT_ID)
    assert record.status == PlanningValidationStatus.ERROR
    assert record.error_code == "SIMULATOR_TIMEOUT"
    assert record.comparison is None


@pytest.mark.asyncio
async def test_cancellation_after_simulating(
    tmp_path: Path,
    baseline_result_data: Any,
    sample_plan_data: Any,
) -> None:
    retrieval = FakeRetrievalService(result=make_multi_action_retrieval_result())
    run_store = RunStore(make_runs_root(tmp_path))
    gate = asyncio.Event()
    simulation = PersistingFakeSimulationService(
        run_store,
        result_data=_candidate_result_data(baseline_result_data, outcome="STABILIZED"),
        gate=gate,
    )
    service, deps = make_plan_simulation_service(
        tmp_path,
        retrieval=retrieval,
        simulation=simulation,
        sample_plan_data=sample_plan_data,
    )
    _seed_replaying(deps)
    task = asyncio.create_task(service.generate_and_simulate(SESSION_ID))
    await asyncio.sleep(0.05)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    record = deps["validation_store"].read_validation(PLANNING_ATTEMPT_ID)
    assert record.status == PlanningValidationStatus.ERROR
    assert record.error_code == "PLANNING_SIMULATION_CANCELLED"


@pytest.mark.asyncio
async def test_final_persistence_failure_leaves_simulating(
    tmp_path: Path,
    baseline_result_data: Any,
    sample_plan_data: Any,
) -> None:
    retrieval = FakeRetrievalService(result=make_multi_action_retrieval_result())
    run_store = RunStore(make_runs_root(tmp_path))
    simulation = PersistingFakeSimulationService(
        run_store,
        result_data=_candidate_result_data(baseline_result_data, outcome="STABILIZED"),
    )
    service, deps = make_plan_simulation_service(
        tmp_path,
        retrieval=retrieval,
        simulation=simulation,
        sample_plan_data=sample_plan_data,
    )
    _seed_replaying(deps)
    with patch.object(
        deps["validation_store"],
        "replace_validation",
        side_effect=PlanningValidationStorageError("replace failed"),
    ):
        with pytest.raises(PlanningValidationStorageError):
            await service.generate_and_simulate(SESSION_ID)
    record = deps["validation_store"].read_validation(PLANNING_ATTEMPT_ID)
    assert record.status == PlanningValidationStatus.SIMULATING
    assert len(simulation.calls) == 1


@pytest.mark.asyncio
async def test_same_session_concurrent_rejected(
    tmp_path: Path,
    baseline_result_data: Any,
    sample_plan_data: Any,
) -> None:
    retrieval = FakeRetrievalService(result=make_multi_action_retrieval_result())
    run_store = RunStore(make_runs_root(tmp_path))
    gate = asyncio.Event()
    simulation = PersistingFakeSimulationService(
        run_store,
        result_data=_candidate_result_data(baseline_result_data, outcome="STABILIZED"),
        gate=gate,
    )
    service, deps = make_plan_simulation_service(
        tmp_path,
        retrieval=retrieval,
        simulation=simulation,
        sample_plan_data=sample_plan_data,
    )
    _seed_replaying(deps)
    first = asyncio.create_task(service.generate_and_simulate(SESSION_ID))
    await asyncio.sleep(0.05)
    with pytest.raises(PlanningInProgressError):
        await service.generate_and_simulate(SESSION_ID)
    gate.set()
    await first
    assert len(retrieval.calls) == 1
    assert len(simulation.calls) == 1


@pytest.mark.asyncio
async def test_different_sessions_concurrent_isolated(
    tmp_path: Path,
    baseline_result_data: Any,
    sample_plan_data: Any,
) -> None:
    retrieval = FakeRetrievalService(result=make_multi_action_retrieval_result())
    run_store = RunStore(make_runs_root(tmp_path))
    gate = asyncio.Event()
    simulation = PersistingFakeSimulationService(
        run_store,
        result_data=_candidate_result_data(baseline_result_data, outcome="STABILIZED"),
        gate=gate,
    )
    from uuid import UUID

    attempt_ids = iter(
        [
            UUID("00000000-0000-4000-8000-000000000020"),
            UUID("00000000-0000-4000-8000-000000000021"),
        ],
    )
    service, deps = make_service(
        tmp_path,
        retrieval=retrieval,
        attempt_id_provider=lambda: next(attempt_ids),
    )
    deps["provider"].generate_plan = AsyncMock(side_effect=_fake_generate(sample_plan_data))
    validation_store = make_planning_validation_store(tmp_path)
    attempt_store = make_planning_attempt_store(tmp_path)
    plan_sim = MissionPlanSimulationService(
        mission_planning_service=service,
        planning_attempt_store=attempt_store,
        validation_store=validation_store,
        run_store=deps["run_store"],
        simulation_service=simulation,
        now_provider=SequenceClock([T0, T1, T2, T3, T4, T0, T1, T2, T3, T4]),
    )
    run_a = seed_completed_run(deps["run_store"], baseline_result_bytes())
    run_b = seed_completed_run(deps["run_store"], baseline_result_bytes())
    deps["session_store"].create_session(
        make_replaying_session(baseline_run_id=run_a, session_id=SESSION_ID),
    )
    deps["session_store"].create_session(
        make_replaying_session(baseline_run_id=run_b, session_id=OTHER_SESSION_ID),
    )
    first = asyncio.create_task(plan_sim.generate_and_simulate(SESSION_ID))
    second = asyncio.create_task(plan_sim.generate_and_simulate(OTHER_SESSION_ID))
    await asyncio.sleep(0.05)
    gate.set()
    await asyncio.gather(first, second)
    assert len(retrieval.calls) == 2
    assert len(simulation.calls) == 2


@pytest.mark.asyncio
async def test_restart_safe_reads(
    tmp_path: Path,
    baseline_result_data: Any,
    sample_plan_data: Any,
) -> None:
    retrieval = FakeRetrievalService(result=make_multi_action_retrieval_result())
    run_store = RunStore(make_runs_root(tmp_path))
    simulation = PersistingFakeSimulationService(
        run_store,
        result_data=_candidate_result_data(baseline_result_data, outcome="STABILIZED"),
    )
    service, deps = make_plan_simulation_service(
        tmp_path,
        retrieval=retrieval,
        simulation=simulation,
        sample_plan_data=sample_plan_data,
    )
    _seed_replaying(deps)
    created = await service.generate_and_simulate(SESSION_ID)
    fresh_attempt_store = make_planning_attempt_store(tmp_path)
    fresh_validation_store = make_planning_validation_store(tmp_path)
    read_attempt = fresh_attempt_store.read_attempt(PLANNING_ATTEMPT_ID)
    read_validation = fresh_validation_store.read_validation(PLANNING_ATTEMPT_ID)
    assert read_attempt == created.attempt
    assert read_validation == created.validation
