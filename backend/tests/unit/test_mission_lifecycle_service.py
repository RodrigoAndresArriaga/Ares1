# MissionLifecycleService unit tests (Phase 3 Step 5)
from __future__ import annotations

import asyncio
import importlib
import json
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from app.core.errors import (
    BaselineTelemetryEmptyError,
    MissionSessionConflictError,
    MissionSessionNotFoundError,
    MissionSessionStorageError,
    ReplayIntervalInvalidError,
    ScenarioNotFoundError,
    SimulatorUnavailableError,
)
from app.schemas.api import ErrorCode, SimulationRunRequest, SimulationRunResponse
from app.schemas.mission import (
    AccidentTriggerResponse,
    MissionCreateRequest,
    MissionSession,
    MissionSessionStatus,
)
from app.schemas.replay import ReplayStartRequest
from app.schemas.result import OutcomeStatus, SimulationResult
from app.services.mission_lifecycle_service import MissionLifecycleService
from app.services.scenario_registry import ScenarioRegistry
from app.services.session_store import SessionStore
from tests.conftest import RELEASE_SCENARIO_ID, install_release_scenario

SESSION_ID = "00000000-0000-4000-8000-000000000001"
OTHER_ID = "00000000-0000-4000-8000-000000000002"
RUN_ID = "00000000-0000-4000-8000-000000000003"
OTHER_RUN_ID = "00000000-0000-4000-8000-000000000004"
SCENARIO_ID = RELEASE_SCENARIO_ID

T0 = datetime(2026, 7, 15, 12, 0, 0, tzinfo=timezone.utc)
T1 = T0 + timedelta(seconds=1)
T2 = T0 + timedelta(seconds=2)
T3 = T0 + timedelta(seconds=3)
T4 = T0 + timedelta(seconds=4)
T5 = T0 + timedelta(seconds=5)

DEFAULT_INTERVAL = 250
MIN_INTERVAL = 25
MAX_INTERVAL = 60000

FORBIDDEN_SESSION_KEYS = frozenset(
    {
        "telemetry_history",
        "metrics",
        "timeline",
        "failure_reasons",
        "result",
        "plan",
        "survival_probability",
    }
)


class SequenceClock:
    def __init__(self, times: list[datetime]) -> None:
        self._times = list(times)
        self._index = 0

    def __call__(self) -> datetime:
        if self._index >= len(self._times):
            raise RuntimeError("SequenceClock exhausted")
        value = self._times[self._index]
        self._index += 1
        return value


def make_sessions_root(tmp_path: Path) -> Path:
    root = tmp_path / "sessions"
    root.mkdir(exist_ok=True)
    return root


def make_sim_response(
    *,
    run_id: str,
    result_data: Any,
    duration_ms: int = 25,
) -> SimulationRunResponse:
    return SimulationRunResponse(
        run_id=run_id,
        duration_ms=duration_ms,
        result=SimulationResult.model_validate(result_data),
    )


def make_ready_session(
    *,
    session_id: str = SESSION_ID,
    updated_at: datetime | None = None,
) -> MissionSession:
    return MissionSession.model_validate(
        {
            "session_id": session_id,
            "scenario_id": SCENARIO_ID,
            "status": MissionSessionStatus.READY.value,
            "created_at": T0,
            "updated_at": updated_at or T0,
            "accident_triggered_at": None,
            "baseline_run_id": None,
            "baseline_outcome": None,
            "telemetry_sample_count": None,
            "replay_started_at": None,
            "replay_interval_ms": None,
            "error_code": None,
        }
    )


def make_triggering_session(
    *,
    session_id: str = SESSION_ID,
    updated_at: datetime | None = None,
) -> MissionSession:
    return MissionSession.model_validate(
        {
            "session_id": session_id,
            "scenario_id": SCENARIO_ID,
            "status": MissionSessionStatus.TRIGGERING.value,
            "created_at": T0,
            "updated_at": updated_at or T1,
            "accident_triggered_at": T1,
            "baseline_run_id": None,
            "baseline_outcome": None,
            "telemetry_sample_count": None,
            "replay_started_at": None,
            "replay_interval_ms": None,
            "error_code": None,
        }
    )


def make_baseline_ready_session(
    *,
    session_id: str = SESSION_ID,
    outcome: OutcomeStatus = OutcomeStatus.FAILURE,
    sample_count: int = 6,
    updated_at: datetime | None = None,
) -> MissionSession:
    return MissionSession.model_validate(
        {
            "session_id": session_id,
            "scenario_id": SCENARIO_ID,
            "status": MissionSessionStatus.BASELINE_READY.value,
            "created_at": T0,
            "updated_at": updated_at or T2,
            "accident_triggered_at": T1,
            "baseline_run_id": RUN_ID,
            "baseline_outcome": outcome.value,
            "telemetry_sample_count": sample_count,
            "replay_started_at": None,
            "replay_interval_ms": None,
            "error_code": None,
        }
    )


def make_replaying_session(
    *,
    session_id: str = SESSION_ID,
    replay_started_at: datetime | None = None,
    interval_ms: int = DEFAULT_INTERVAL,
) -> MissionSession:
    started = replay_started_at or T2
    return MissionSession.model_validate(
        {
            "session_id": session_id,
            "scenario_id": SCENARIO_ID,
            "status": MissionSessionStatus.REPLAYING.value,
            "created_at": T0,
            "updated_at": started,
            "accident_triggered_at": T1,
            "baseline_run_id": RUN_ID,
            "baseline_outcome": OutcomeStatus.FAILURE.value,
            "telemetry_sample_count": 6,
            "replay_started_at": started,
            "replay_interval_ms": interval_ms,
            "error_code": None,
        }
    )


def make_completed_session(*, session_id: str = SESSION_ID) -> MissionSession:
    return MissionSession.model_validate(
        {
            "session_id": session_id,
            "scenario_id": SCENARIO_ID,
            "status": MissionSessionStatus.COMPLETED.value,
            "created_at": T0,
            "updated_at": T3,
            "accident_triggered_at": T1,
            "baseline_run_id": RUN_ID,
            "baseline_outcome": OutcomeStatus.FAILURE.value,
            "telemetry_sample_count": 6,
            "replay_started_at": T2,
            "replay_interval_ms": DEFAULT_INTERVAL,
            "error_code": None,
        }
    )


def make_error_session(
    *,
    session_id: str = SESSION_ID,
    error_code: str = "SIMULATOR_UNAVAILABLE",
) -> MissionSession:
    return MissionSession.model_validate(
        {
            "session_id": session_id,
            "scenario_id": SCENARIO_ID,
            "status": MissionSessionStatus.ERROR.value,
            "created_at": T0,
            "updated_at": T1,
            "accident_triggered_at": T1,
            "baseline_run_id": None,
            "baseline_outcome": None,
            "telemetry_sample_count": None,
            "replay_started_at": None,
            "replay_interval_ms": None,
            "error_code": error_code,
        }
    )


def make_service(
    tmp_path: Path,
    *,
    simulation_service: Any,
    clock: SequenceClock | None = None,
    session_store: SessionStore | None = None,
    replay_default_interval_ms: int = DEFAULT_INTERVAL,
    replay_min_interval_ms: int = MIN_INTERVAL,
    replay_max_interval_ms: int = MAX_INTERVAL,
) -> tuple[MissionLifecycleService, SessionStore, ScenarioRegistry]:
    scenario_dir = tmp_path / "scenarios"
    install_release_scenario(scenario_dir)
    registry = ScenarioRegistry(scenario_dir)
    store = session_store or SessionStore(make_sessions_root(tmp_path))
    service = MissionLifecycleService(
        scenario_registry=registry,
        session_store=store,
        simulation_service=simulation_service,
        replay_default_interval_ms=replay_default_interval_ms,
        replay_min_interval_ms=replay_min_interval_ms,
        replay_max_interval_ms=replay_max_interval_ms,
        now_provider=clock or SequenceClock([T0]),
    )
    return service, store, registry


async def _create_ready_session(
    service: MissionLifecycleService,
) -> MissionSession:
    return service.create_session(
        MissionCreateRequest(scenario_id=SCENARIO_ID),
    )


# --- A. Construction ---


def test_construction_valid_dependencies(tmp_path: Path) -> None:
    fake_sim = AsyncMock()
    service, _, _ = make_service(tmp_path, simulation_service=fake_sim)
    assert service._replay_default_interval_ms == DEFAULT_INTERVAL


@pytest.mark.parametrize(
    ("min_ms", "max_ms", "default_ms"),
    [
        (0, 100, 50),
        (100, 50, 75),
        (25, 60000, 10),
    ],
)
def test_construction_rejects_invalid_intervals(
    tmp_path: Path,
    min_ms: int,
    max_ms: int,
    default_ms: int,
) -> None:
    fake_sim = AsyncMock()
    scenario_dir = tmp_path / "scenarios"
    install_release_scenario(scenario_dir)
    registry = ScenarioRegistry(scenario_dir)
    store = SessionStore(make_sessions_root(tmp_path))
    with pytest.raises(ValueError):
        MissionLifecycleService(
            scenario_registry=registry,
            session_store=store,
            simulation_service=fake_sim,
            replay_default_interval_ms=default_ms,
            replay_min_interval_ms=min_ms,
            replay_max_interval_ms=max_ms,
        )


def test_construction_accepts_deterministic_clock(tmp_path: Path) -> None:
    fake_sim = AsyncMock()
    service, _, _ = make_service(
        tmp_path,
        simulation_service=fake_sim,
        clock=SequenceClock([T0, T1]),
    )
    assert service._require_aware_now() == T0


def test_naive_now_provider_rejected(tmp_path: Path) -> None:
    fake_sim = AsyncMock()
    naive = datetime(2026, 1, 1, 12, 0, 0)
    service, _, _ = make_service(
        tmp_path,
        simulation_service=fake_sim,
        clock=SequenceClock([naive]),
    )
    with pytest.raises(ValueError, match="timezone-aware"):
        service.create_session(MissionCreateRequest(scenario_id=SCENARIO_ID))


# --- B. Create session ---


def test_create_session_ready(tmp_path: Path) -> None:
    fake_sim = AsyncMock()
    service, store, _ = make_service(
        tmp_path,
        simulation_service=fake_sim,
        clock=SequenceClock([T0]),
    )
    session = service.create_session(
        MissionCreateRequest(scenario_id=SCENARIO_ID),
    )
    assert session.status == MissionSessionStatus.READY
    assert session.created_at == T0
    assert session.updated_at == T0
    assert session.baseline_run_id is None
    assert session.telemetry_sample_count is None
    assert store.session_exists(session.session_id)
    fake_sim.run_simulation.assert_not_called()


def test_create_session_canonical_uuid(tmp_path: Path) -> None:
    fake_sim = AsyncMock()
    fixed = uuid.UUID("00000000-0000-4000-8000-000000000099")
    service, _, _ = make_service(
        tmp_path,
        simulation_service=fake_sim,
        clock=SequenceClock([T0, T0]),
    )
    with patch("app.services.mission_lifecycle_service.uuid.uuid4", return_value=fixed):
        session = service.create_session(
            MissionCreateRequest(scenario_id=SCENARIO_ID),
        )
    assert session.session_id == str(fixed)


def test_create_session_unknown_scenario_no_artifact(tmp_path: Path) -> None:
    fake_sim = AsyncMock()
    service, store, _ = make_service(
        tmp_path,
        simulation_service=fake_sim,
        clock=SequenceClock([T0]),
    )
    with pytest.raises(ScenarioNotFoundError):
        service.create_session(
            MissionCreateRequest(scenario_id="unknown_scenario"),
        )
    assert not any(store._sessions_root.iterdir())


def test_create_session_distinct_ids(tmp_path: Path) -> None:
    fake_sim = AsyncMock()
    service, _, _ = make_service(
        tmp_path,
        simulation_service=fake_sim,
        clock=SequenceClock([T0, T0, T0, T0]),
    )
    first = service.create_session(
        MissionCreateRequest(scenario_id=SCENARIO_ID),
    )
    second = service.create_session(
        MissionCreateRequest(scenario_id=SCENARIO_ID),
    )
    assert first.session_id != second.session_id


# --- C. Get session ---


def test_get_session_exact_persisted(tmp_path: Path) -> None:
    fake_sim = AsyncMock()
    service, store, _ = make_service(
        tmp_path,
        simulation_service=fake_sim,
        clock=SequenceClock([T0]),
    )
    created = service.create_session(
        MissionCreateRequest(scenario_id=SCENARIO_ID),
    )
    read = service.get_session(created.session_id)
    assert read == created


def test_get_session_not_found(tmp_path: Path) -> None:
    fake_sim = AsyncMock()
    service, _, _ = make_service(
        tmp_path,
        simulation_service=fake_sim,
    )
    with pytest.raises(MissionSessionNotFoundError):
        service.get_session(SESSION_ID)


def test_get_session_does_not_mutate_updated_at(tmp_path: Path) -> None:
    fake_sim = AsyncMock()
    service, store, _ = make_service(
        tmp_path,
        simulation_service=fake_sim,
        clock=SequenceClock([T0]),
    )
    created = service.create_session(
        MissionCreateRequest(scenario_id=SCENARIO_ID),
    )
    before_bytes = (
        store._sessions_root / created.session_id / "session.json"
    ).read_bytes()
    _ = service.get_session(created.session_id)
    after_bytes = (
        store._sessions_root / created.session_id / "session.json"
    ).read_bytes()
    assert before_bytes == after_bytes


def test_get_session_replaying_unchanged_despite_elapsed_wall_time(
    tmp_path: Path,
) -> None:
    fake_sim = AsyncMock()
    store = SessionStore(make_sessions_root(tmp_path))
    old_created = T0 - timedelta(hours=48)
    old_accident = T0 - timedelta(hours=47)
    old_start = T0 - timedelta(hours=24)
    store.create_session(
        MissionSession.model_validate(
            {
                "session_id": SESSION_ID,
                "scenario_id": SCENARIO_ID,
                "status": MissionSessionStatus.REPLAYING.value,
                "created_at": old_created,
                "updated_at": old_start,
                "accident_triggered_at": old_accident,
                "baseline_run_id": RUN_ID,
                "baseline_outcome": OutcomeStatus.FAILURE.value,
                "telemetry_sample_count": 6,
                "replay_started_at": old_start,
                "replay_interval_ms": DEFAULT_INTERVAL,
                "error_code": None,
            }
        )
    )
    service, _, _ = make_service(
        tmp_path,
        simulation_service=fake_sim,
        session_store=store,
        clock=SequenceClock([T4]),
    )
    read = service.get_session(SESSION_ID)
    assert read.status == MissionSessionStatus.REPLAYING
    assert read.replay_started_at == old_start


# --- D. Successful accident trigger ---


@pytest.mark.asyncio
async def test_trigger_accident_baseline_ready_failure(
    tmp_path: Path,
    baseline_result_data: Any,
) -> None:
    fake_sim = AsyncMock()
    fake_sim.run_simulation = AsyncMock(
        return_value=make_sim_response(
            run_id=RUN_ID,
            result_data=baseline_result_data,
        )
    )
    service, store, _ = make_service(
        tmp_path,
        simulation_service=fake_sim,
        clock=SequenceClock([T0, T1, T2]),
    )
    session = await _create_ready_session(service)
    response = await service.trigger_accident(session.session_id)

    assert isinstance(response, AccidentTriggerResponse)
    assert response.session.status == MissionSessionStatus.BASELINE_READY
    assert response.baseline_run_id == RUN_ID
    assert response.baseline_outcome == OutcomeStatus.FAILURE
    assert response.telemetry_sample_count == len(
        baseline_result_data["telemetry_history"]
    )
    assert response.session == store.read_session(session.session_id)
    fake_sim.run_simulation.assert_awaited_once()
    req = fake_sim.run_simulation.await_args.args[0]
    assert isinstance(req, SimulationRunRequest)
    assert req.scenario_id == SCENARIO_ID
    assert req.plan is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("fixture_name", "expected_outcome"),
    [
        ("baseline_result_data", OutcomeStatus.FAILURE),
        ("valid_plan_result_data", OutcomeStatus.STABILIZED),
        ("invalid_plan_result_data", OutcomeStatus.REJECTED),
    ],
)
async def test_trigger_preserves_all_valid_outcomes(
    tmp_path: Path,
    fixture_name: str,
    expected_outcome: OutcomeStatus,
    request: pytest.FixtureRequest,
) -> None:
    result_data = request.getfixturevalue(fixture_name)
    if not result_data["telemetry_history"]:
        pytest.skip("REJECTED fixture has empty telemetry; covered in section F")

    fake_sim = AsyncMock()
    fake_sim.run_simulation = AsyncMock(
        return_value=make_sim_response(run_id=RUN_ID, result_data=result_data)
    )
    service, _, _ = make_service(
        tmp_path,
        simulation_service=fake_sim,
        clock=SequenceClock([T0, T1, T2]),
    )
    session = await _create_ready_session(service)
    response = await service.trigger_accident(session.session_id)
    assert response.baseline_outcome == expected_outcome
    assert response.session.status == MissionSessionStatus.BASELINE_READY


@pytest.mark.asyncio
async def test_trigger_empty_plan_id_accepted(
    tmp_path: Path,
    baseline_result_data: Any,
) -> None:
    fake_sim = AsyncMock()
    fake_sim.run_simulation = AsyncMock(
        return_value=make_sim_response(
            run_id=RUN_ID,
            result_data=baseline_result_data,
        )
    )
    service, _, _ = make_service(
        tmp_path,
        simulation_service=fake_sim,
        clock=SequenceClock([T0, T1, T2]),
    )
    session = await _create_ready_session(service)
    response = await service.trigger_accident(session.session_id)
    assert response.session.status == MissionSessionStatus.BASELINE_READY
    assert baseline_result_data["plan_id"] == ""


# --- E. Duplicate and invalid trigger states ---


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "session_factory",
    [
        make_triggering_session,
        make_baseline_ready_session,
        make_replaying_session,
        make_completed_session,
        make_error_session,
    ],
)
async def test_trigger_rejected_from_invalid_states(
    tmp_path: Path,
    session_factory: Any,
    baseline_result_data: Any,
) -> None:
    fake_sim = AsyncMock()
    fake_sim.run_simulation = AsyncMock(
        return_value=make_sim_response(
            run_id=RUN_ID,
            result_data=baseline_result_data,
        )
    )
    store = SessionStore(make_sessions_root(tmp_path))
    store.create_session(session_factory())
    service, _, _ = make_service(
        tmp_path,
        simulation_service=fake_sim,
        session_store=store,
        clock=SequenceClock([T0]),
    )
    with pytest.raises(MissionSessionConflictError):
        await service.trigger_accident(SESSION_ID)
    fake_sim.run_simulation.assert_not_awaited()


# --- F. Empty telemetry ---


@pytest.mark.asyncio
async def test_trigger_empty_telemetry_persists_error(
    tmp_path: Path,
    invalid_plan_result_data: Any,
) -> None:
    fake_sim = AsyncMock()
    fake_sim.run_simulation = AsyncMock(
        return_value=make_sim_response(
            run_id=RUN_ID,
            result_data=invalid_plan_result_data,
        )
    )
    service, store, _ = make_service(
        tmp_path,
        simulation_service=fake_sim,
        clock=SequenceClock([T0, T1, T2]),
    )
    session = await _create_ready_session(service)
    with pytest.raises(BaselineTelemetryEmptyError) as exc_info:
        await service.trigger_accident(session.session_id)
    assert exc_info.value.code == ErrorCode.BASELINE_TELEMETRY_EMPTY

    persisted = store.read_session(session.session_id)
    assert persisted.status == MissionSessionStatus.ERROR
    assert persisted.error_code == ErrorCode.BASELINE_TELEMETRY_EMPTY.value
    assert persisted.baseline_run_id == RUN_ID
    assert persisted.baseline_outcome == OutcomeStatus.REJECTED
    assert persisted.telemetry_sample_count is None


# --- G. Infrastructure failure ---


@pytest.mark.asyncio
async def test_trigger_infrastructure_failure_persists_error(
    tmp_path: Path,
) -> None:
    sim_error = SimulatorUnavailableError()
    fake_sim = AsyncMock()
    fake_sim.run_simulation = AsyncMock(side_effect=sim_error)
    service, store, _ = make_service(
        tmp_path,
        simulation_service=fake_sim,
        clock=SequenceClock([T0, T1, T2]),
    )
    session = await _create_ready_session(service)
    with pytest.raises(SimulatorUnavailableError):
        await service.trigger_accident(session.session_id)

    persisted = store.read_session(session.session_id)
    assert persisted.status == MissionSessionStatus.ERROR
    assert persisted.error_code == ErrorCode.SIMULATOR_UNAVAILABLE.value
    assert persisted.baseline_run_id is None
    assert persisted.baseline_outcome is None
    fake_sim.run_simulation.assert_awaited_once()


# --- H. ERROR persistence failure ---


@pytest.mark.asyncio
async def test_trigger_error_persist_failure_precedence(
    tmp_path: Path,
) -> None:
    sim_error = SimulatorUnavailableError()
    fake_sim = AsyncMock()
    fake_sim.run_simulation = AsyncMock(side_effect=sim_error)
    service, store, _ = make_service(
        tmp_path,
        simulation_service=fake_sim,
        clock=SequenceClock([T0, T1, T2]),
    )
    session = await _create_ready_session(service)

    original_replace = store.replace_session
    call_count = 0

    def failing_replace(*args: Any, **kwargs: Any) -> MissionSession:
        nonlocal call_count
        call_count += 1
        if call_count == 2:
            raise MissionSessionStorageError(
                "Failed to replace mission session",
                session_id=session.session_id,
            )
        return original_replace(*args, **kwargs)

    with patch.object(store, "replace_session", side_effect=failing_replace):
        with pytest.raises(MissionSessionStorageError) as exc_info:
            await service.trigger_accident(session.session_id)
        assert exc_info.value.__cause__ is sim_error

    persisted = store.read_session(session.session_id)
    assert persisted.status == MissionSessionStatus.TRIGGERING


# --- I. Cancellation ---


@pytest.mark.asyncio
async def test_trigger_cancellation_persists_error_and_reraises(
    tmp_path: Path,
) -> None:
    gate = asyncio.Event()

    async def slow_sim(_request: SimulationRunRequest) -> SimulationRunResponse:
        await gate.wait()
        raise AssertionError("should not complete")

    fake_sim = AsyncMock()
    fake_sim.run_simulation = AsyncMock(side_effect=slow_sim)
    service, store, _ = make_service(
        tmp_path,
        simulation_service=fake_sim,
        clock=SequenceClock([T0, T1, T2, T3]),
    )
    session = await _create_ready_session(service)

    task = asyncio.create_task(service.trigger_accident(session.session_id))
    await asyncio.sleep(0.01)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    persisted = store.read_session(session.session_id)
    assert persisted.status == MissionSessionStatus.ERROR
    assert persisted.error_code == ErrorCode.MISSION_TRIGGER_CANCELLED.value


# --- J. Concurrent trigger ---


@pytest.mark.asyncio
async def test_concurrent_trigger_one_sim_call(
    tmp_path: Path,
    baseline_result_data: Any,
) -> None:
    entered = asyncio.Event()
    release = asyncio.Event()

    async def gated_sim(
        _request: SimulationRunRequest,
    ) -> SimulationRunResponse:
        entered.set()
        await release.wait()
        return make_sim_response(
            run_id=RUN_ID,
            result_data=baseline_result_data,
        )

    fake_sim = AsyncMock()
    fake_sim.run_simulation = AsyncMock(side_effect=gated_sim)
    service, store, _ = make_service(
        tmp_path,
        simulation_service=fake_sim,
        clock=SequenceClock([T0, T1, T2, T3, T4, T5]),
    )
    session = await _create_ready_session(service)

    first = asyncio.create_task(service.trigger_accident(session.session_id))
    await entered.wait()
    second = asyncio.create_task(service.trigger_accident(session.session_id))
    release.set()

    results = await asyncio.gather(first, second, return_exceptions=True)
    successes = [r for r in results if isinstance(r, AccidentTriggerResponse)]
    conflicts = [r for r in results if isinstance(r, MissionSessionConflictError)]
    assert len(successes) == 1
    assert len(conflicts) == 1
    assert fake_sim.run_simulation.await_count == 1

    final = store.read_session(session.session_id)
    assert final.status == MissionSessionStatus.BASELINE_READY


@pytest.mark.asyncio
async def test_concurrent_trigger_different_sessions_independent(
    tmp_path: Path,
    baseline_result_data: Any,
) -> None:
    fake_sim = AsyncMock()
    fake_sim.run_simulation = AsyncMock(
        side_effect=[
            make_sim_response(run_id=RUN_ID, result_data=baseline_result_data),
            make_sim_response(
                run_id=OTHER_RUN_ID,
                result_data=baseline_result_data,
            ),
        ]
    )
    service, store, _ = make_service(
        tmp_path,
        simulation_service=fake_sim,
        clock=SequenceClock([T0, T0, T1, T2, T1, T2]),
    )
    first = await _create_ready_session(service)
    second = await _create_ready_session(service)

    await asyncio.gather(
        service.trigger_accident(first.session_id),
        service.trigger_accident(second.session_id),
    )
    assert fake_sim.run_simulation.await_count == 2
    assert (
        store.read_session(first.session_id).status
        == MissionSessionStatus.BASELINE_READY
    )
    assert (
        store.read_session(second.session_id).status
        == MissionSessionStatus.BASELINE_READY
    )


# --- K. Start replay ---


@pytest.mark.asyncio
async def test_start_replay_default_interval(
    tmp_path: Path,
    baseline_result_data: Any,
) -> None:
    fake_sim = AsyncMock()
    fake_sim.run_simulation = AsyncMock(
        return_value=make_sim_response(
            run_id=RUN_ID,
            result_data=baseline_result_data,
        )
    )
    service, store, _ = make_service(
        tmp_path,
        simulation_service=fake_sim,
        clock=SequenceClock([T0, T1, T2, T3]),
    )
    session = await _create_ready_session(service)
    await service.trigger_accident(session.session_id)
    replaying = await service.start_replay(
        session.session_id,
        ReplayStartRequest.model_validate({}),
    )
    assert replaying.status == MissionSessionStatus.REPLAYING
    assert replaying.replay_interval_ms == DEFAULT_INTERVAL
    assert replaying.replay_started_at == T3
    assert replaying.baseline_run_id == RUN_ID
    fake_sim.run_simulation.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize("interval", [MIN_INTERVAL, MAX_INTERVAL])
async def test_start_replay_boundary_intervals(
    tmp_path: Path,
    interval: int,
) -> None:
    fake_sim = AsyncMock()
    store = SessionStore(make_sessions_root(tmp_path))
    store.create_session(make_baseline_ready_session())
    service, _, _ = make_service(
        tmp_path,
        simulation_service=fake_sim,
        session_store=store,
        clock=SequenceClock([T3]),
    )
    replaying = await service.start_replay(
        SESSION_ID,
        ReplayStartRequest(interval_ms=interval, restart=False),
    )
    assert replaying.replay_interval_ms == interval


@pytest.mark.asyncio
@pytest.mark.parametrize("interval", [MIN_INTERVAL - 1, MAX_INTERVAL + 1])
async def test_start_replay_interval_out_of_bounds(
    tmp_path: Path,
    interval: int,
) -> None:
    fake_sim = AsyncMock()
    store = SessionStore(make_sessions_root(tmp_path))
    store.create_session(make_baseline_ready_session())
    service, _, _ = make_service(
        tmp_path,
        simulation_service=fake_sim,
        session_store=store,
        clock=SequenceClock([T3]),
    )
    with pytest.raises(ReplayIntervalInvalidError) as exc_info:
        await service.start_replay(
            SESSION_ID,
            ReplayStartRequest(interval_ms=interval, restart=False),
        )
    err = exc_info.value
    assert err.provided_interval_ms == interval
    assert err.min_interval_ms == MIN_INTERVAL
    assert err.max_interval_ms == MAX_INTERVAL


@pytest.mark.asyncio
async def test_start_replay_from_baseline_ready_restart_flags(
    tmp_path: Path,
) -> None:
    fake_sim = AsyncMock()
    store = SessionStore(make_sessions_root(tmp_path))
    store.create_session(make_baseline_ready_session())
    service, _, _ = make_service(
        tmp_path,
        simulation_service=fake_sim,
        session_store=store,
        clock=SequenceClock([T3, T4]),
    )
    for restart in (False, True):
        replaying = await service.start_replay(
            SESSION_ID,
            ReplayStartRequest(restart=restart),
        )
        assert replaying.status == MissionSessionStatus.REPLAYING
        store.replace_session(
            make_baseline_ready_session(updated_at=replaying.updated_at),
            expected_status=MissionSessionStatus.REPLAYING,
            expected_updated_at=replaying.updated_at,
        )


# --- L. Replay state conflicts ---


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "session_factory",
    [
        make_ready_session,
        make_triggering_session,
        make_replaying_session,
        make_error_session,
    ],
)
async def test_start_replay_rejected_invalid_states(
    tmp_path: Path,
    session_factory: Any,
) -> None:
    fake_sim = AsyncMock()
    store = SessionStore(make_sessions_root(tmp_path))
    store.create_session(session_factory())
    service, _, _ = make_service(
        tmp_path,
        simulation_service=fake_sim,
        session_store=store,
        clock=SequenceClock([T3]),
    )
    with pytest.raises(MissionSessionConflictError):
        await service.start_replay(
            SESSION_ID,
            ReplayStartRequest.model_validate({}),
        )


@pytest.mark.asyncio
async def test_start_replay_completed_without_restart_rejected(
    tmp_path: Path,
) -> None:
    fake_sim = AsyncMock()
    store = SessionStore(make_sessions_root(tmp_path))
    store.create_session(make_completed_session())
    service, _, _ = make_service(
        tmp_path,
        simulation_service=fake_sim,
        session_store=store,
        clock=SequenceClock([T4]),
    )
    with pytest.raises(MissionSessionConflictError):
        await service.start_replay(
            SESSION_ID,
            ReplayStartRequest(restart=False),
        )


@pytest.mark.asyncio
async def test_start_replay_completed_with_restart(
    tmp_path: Path,
) -> None:
    fake_sim = AsyncMock()
    store = SessionStore(make_sessions_root(tmp_path))
    store.create_session(make_completed_session())
    service, _, _ = make_service(
        tmp_path,
        simulation_service=fake_sim,
        session_store=store,
        clock=SequenceClock([T4]),
    )
    replaying = await service.start_replay(
        SESSION_ID,
        ReplayStartRequest(restart=True, interval_ms=100),
    )
    assert replaying.status == MissionSessionStatus.REPLAYING
    assert replaying.baseline_run_id == RUN_ID
    assert replaying.baseline_outcome == OutcomeStatus.FAILURE
    assert replaying.telemetry_sample_count == 6
    assert replaying.replay_started_at == T4
    assert replaying.replay_interval_ms == 100
    assert replaying.accident_triggered_at == T1


# --- M. Persistence and restart safety ---


@pytest.mark.asyncio
async def test_persisted_state_survives_new_service_instance(
    tmp_path: Path,
    baseline_result_data: Any,
) -> None:
    fake_sim = AsyncMock()
    fake_sim.run_simulation = AsyncMock(
        return_value=make_sim_response(
            run_id=RUN_ID,
            result_data=baseline_result_data,
        )
    )
    service1, store1, _ = make_service(
        tmp_path,
        simulation_service=fake_sim,
        clock=SequenceClock([T0, T1, T2, T3]),
    )
    session = await _create_ready_session(service1)
    await service1.trigger_accident(session.session_id)

    sessions_root = store1._sessions_root
    service2 = MissionLifecycleService(
        scenario_registry=ScenarioRegistry(tmp_path / "scenarios"),
        session_store=SessionStore(sessions_root),
        simulation_service=fake_sim,
        replay_default_interval_ms=DEFAULT_INTERVAL,
        replay_min_interval_ms=MIN_INTERVAL,
        replay_max_interval_ms=MAX_INTERVAL,
        now_provider=SequenceClock([T3]),
    )
    read = service2.get_session(session.session_id)
    assert read.status == MissionSessionStatus.BASELINE_READY
    replaying = await service2.start_replay(
        session.session_id,
        ReplayStartRequest.model_validate({}),
    )
    assert replaying.status == MissionSessionStatus.REPLAYING


# --- N. Timestamp ordering ---


@pytest.mark.asyncio
async def test_timestamp_ordering_create_trigger_baseline_replay(
    tmp_path: Path,
    baseline_result_data: Any,
) -> None:
    fake_sim = AsyncMock()
    fake_sim.run_simulation = AsyncMock(
        return_value=make_sim_response(
            run_id=RUN_ID,
            result_data=baseline_result_data,
        )
    )
    service, _, _ = make_service(
        tmp_path,
        simulation_service=fake_sim,
        clock=SequenceClock([T0, T1, T2, T3]),
    )
    created = await _create_ready_session(service)
    assert created.created_at == created.updated_at == T0

    triggered = await service.trigger_accident(created.session_id)
    session = triggered.session
    assert session.created_at == T0
    assert session.accident_triggered_at == T1
    assert session.updated_at == T2
    assert session.created_at <= session.accident_triggered_at <= session.updated_at

    replaying = await service.start_replay(
        created.session_id,
        ReplayStartRequest.model_validate({}),
    )
    assert replaying.replay_started_at == T3
    assert replaying.accident_triggered_at <= replaying.replay_started_at


# --- O. Content integrity ---


@pytest.mark.asyncio
async def test_session_artifact_lifecycle_fields_only(
    tmp_path: Path,
    baseline_result_data: Any,
) -> None:
    fake_sim = AsyncMock()
    fake_sim.run_simulation = AsyncMock(
        return_value=make_sim_response(
            run_id=RUN_ID,
            result_data=baseline_result_data,
        )
    )
    service, store, _ = make_service(
        tmp_path,
        simulation_service=fake_sim,
        clock=SequenceClock([T0, T1, T2]),
    )
    session = await _create_ready_session(service)
    await service.trigger_accident(session.session_id)

    payload = json.loads(
        (store._sessions_root / session.session_id / "session.json").read_text(
            encoding="utf-8"
        )
    )
    assert FORBIDDEN_SESSION_KEYS.isdisjoint(payload.keys())
    assert "telemetry_history" not in json.dumps(payload)


# --- P. No replay implementation ---


def test_no_current_sample_method() -> None:
    assert not hasattr(MissionLifecycleService, "get_current_telemetry")
    assert not hasattr(MissionLifecycleService, "get_current_sample")


def test_no_replay_clock_import() -> None:
    module_name = "app.services.mission_lifecycle_service"
    mod = sys.modules.get(module_name) or importlib.import_module(module_name)
    assert "replay_clock" not in mod.__dict__
    source_path = Path(mod.__file__ or "")
    source = source_path.read_text(encoding="utf-8")
    assert "from app.services.replay_clock" not in source
    assert "import replay_clock" not in source


@pytest.mark.asyncio
async def test_get_session_never_transitions_replaying_to_completed(
    tmp_path: Path,
) -> None:
    fake_sim = AsyncMock()
    store = SessionStore(make_sessions_root(tmp_path))
    store.create_session(make_replaying_session())
    service, _, _ = make_service(
        tmp_path,
        simulation_service=fake_sim,
        session_store=store,
        clock=SequenceClock([T4]),
    )
    read = service.get_session(SESSION_ID)
    assert read.status == MissionSessionStatus.REPLAYING
