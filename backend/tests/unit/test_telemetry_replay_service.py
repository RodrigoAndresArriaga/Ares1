# TelemetryReplayService unit tests (Phase 3 Step 8)
from __future__ import annotations

import ast
import asyncio
import hashlib
import importlib
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest
from app.core.errors import (
    BaselineResultMismatchError,
    BaselineResultUnavailableError,
    MissionSessionConflictError,
    ReplayEventIdInvalidError,
    ReplayNotStartedError,
)
from app.schemas.api import ErrorCode
from app.schemas.mission import MissionSession, MissionSessionStatus
from app.schemas.replay import (
    CurrentTelemetryResponse,
    ReplayCompleteEvent,
    ReplayTelemetryEvent,
)
from app.schemas.result import OutcomeStatus, SimulationResult
from app.services.run_store import RunStore, sha256_file
from app.services.session_store import SessionStore
from app.services.telemetry_replay_service import (
    ReplayEventBatch,
    ReplayServiceEvent,
    TelemetryReplayService,
)
from tests.conftest import (
    RELEASE_SCENARIO_ID,
    RELEASE_SCENARIO_PATH,
    RESULTS_DIR,
    make_baseline_request,
)

SESSION_ID = "00000000-0000-4000-8000-000000000001"
RUN_ID = "00000000-0000-4000-8000-000000000003"

T0 = datetime(2026, 7, 15, 12, 0, 0, tzinfo=timezone.utc)
T1 = T0 + timedelta(seconds=1)
REPLAY_START = T0 + timedelta(seconds=2)
INTERVAL_MS = 250
SIX = 6

FORBIDDEN_SESSION_KEYS = frozenset(
    {
        "telemetry_history",
        "metrics",
        "timeline",
        "failure_reasons",
        "result",
        "survival_probability",
        "last_event_id",
        "cursor",
    }
)


class SequenceClock:
    def __init__(self, times: list[datetime]) -> None:
        self._times = list(times)
        self._index = 0
        self.calls = 0

    def __call__(self) -> datetime:
        self.calls += 1
        if self._index >= len(self._times):
            raise RuntimeError("SequenceClock exhausted")
        value = self._times[self._index]
        self._index += 1
        return value


def at_ms(offset_ms: int) -> datetime:
    return REPLAY_START + timedelta(milliseconds=offset_ms)


def make_sessions_root(tmp_path: Path) -> Path:
    root = tmp_path / "sessions"
    root.mkdir(parents=True, exist_ok=True)
    return root


def make_runs_root(tmp_path: Path) -> Path:
    root = tmp_path / "runs"
    root.mkdir(parents=True, exist_ok=True)
    return root


def session_json_path(sessions_root: Path, session_id: str = SESSION_ID) -> Path:
    return sessions_root / session_id / "session.json"


def seed_completed_run(
    store: RunStore,
    result_bytes: bytes,
    *,
    outcome: str | None = None,
) -> str:
    workspace = store.create_workspace(make_baseline_request(), RELEASE_SCENARIO_PATH)
    workspace.result_path.write_bytes(result_bytes)
    resolved_outcome = outcome
    if resolved_outcome is None:
        resolved_outcome = json.loads(result_bytes.decode("utf-8"))["outcome"]
    store.write_completed_metadata(
        workspace,
        result_sha256=sha256_file(workspace.result_path),
        process_exit_code=0,
        duration_ms=1,
        outcome=resolved_outcome,
    )
    return workspace.run_id


def baseline_result_bytes() -> bytes:
    return (RESULTS_DIR / "baseline_result.json").read_bytes()


def valid_plan_result_bytes() -> bytes:
    return (RESULTS_DIR / "valid_plan_result.json").read_bytes()


def load_baseline_result() -> SimulationResult:
    return SimulationResult.model_validate_json(baseline_result_bytes())


def make_replaying_session(
    *,
    session_id: str = SESSION_ID,
    baseline_run_id: str,
    outcome: OutcomeStatus = OutcomeStatus.FAILURE,
    sample_count: int = SIX,
    replay_started_at: datetime = REPLAY_START,
    interval_ms: int = INTERVAL_MS,
    updated_at: datetime | None = None,
    scenario_id: str = RELEASE_SCENARIO_ID,
) -> MissionSession:
    return MissionSession.model_validate(
        {
            "session_id": session_id,
            "scenario_id": scenario_id,
            "status": MissionSessionStatus.REPLAYING.value,
            "created_at": T0,
            "updated_at": updated_at or replay_started_at,
            "accident_triggered_at": T1,
            "baseline_run_id": baseline_run_id,
            "baseline_outcome": outcome.value,
            "telemetry_sample_count": sample_count,
            "replay_started_at": replay_started_at,
            "replay_interval_ms": interval_ms,
            "error_code": None,
        }
    )


def make_completed_session(
    *,
    session_id: str = SESSION_ID,
    baseline_run_id: str,
    outcome: OutcomeStatus = OutcomeStatus.FAILURE,
    sample_count: int = SIX,
    replay_started_at: datetime = REPLAY_START,
    interval_ms: int = INTERVAL_MS,
    updated_at: datetime | None = None,
) -> MissionSession:
    return MissionSession.model_validate(
        {
            "session_id": session_id,
            "scenario_id": RELEASE_SCENARIO_ID,
            "status": MissionSessionStatus.COMPLETED.value,
            "created_at": T0,
            "updated_at": updated_at or (replay_started_at + timedelta(seconds=1)),
            "accident_triggered_at": T1,
            "baseline_run_id": baseline_run_id,
            "baseline_outcome": outcome.value,
            "telemetry_sample_count": sample_count,
            "replay_started_at": replay_started_at,
            "replay_interval_ms": interval_ms,
            "error_code": None,
        }
    )


def make_status_session(
    status: MissionSessionStatus,
    *,
    baseline_run_id: str | None = None,
    error_code: str | None = None,
) -> MissionSession:
    if status == MissionSessionStatus.READY:
        return MissionSession.model_validate(
            {
                "session_id": SESSION_ID,
                "scenario_id": RELEASE_SCENARIO_ID,
                "status": status.value,
                "created_at": T0,
                "updated_at": T0,
                "accident_triggered_at": None,
                "baseline_run_id": None,
                "baseline_outcome": None,
                "telemetry_sample_count": None,
                "replay_started_at": None,
                "replay_interval_ms": None,
                "error_code": None,
            }
        )
    if status == MissionSessionStatus.TRIGGERING:
        return MissionSession.model_validate(
            {
                "session_id": SESSION_ID,
                "scenario_id": RELEASE_SCENARIO_ID,
                "status": status.value,
                "created_at": T0,
                "updated_at": T1,
                "accident_triggered_at": T1,
                "baseline_run_id": None,
                "baseline_outcome": None,
                "telemetry_sample_count": None,
                "replay_started_at": None,
                "replay_interval_ms": None,
                "error_code": None,
            }
        )
    if status == MissionSessionStatus.BASELINE_READY:
        return MissionSession.model_validate(
            {
                "session_id": SESSION_ID,
                "scenario_id": RELEASE_SCENARIO_ID,
                "status": status.value,
                "created_at": T0,
                "updated_at": T1,
                "accident_triggered_at": T1,
                "baseline_run_id": baseline_run_id or RUN_ID,
                "baseline_outcome": OutcomeStatus.FAILURE.value,
                "telemetry_sample_count": SIX,
                "replay_started_at": None,
                "replay_interval_ms": None,
                "error_code": None,
            }
        )
    if status == MissionSessionStatus.ERROR:
        return MissionSession.model_validate(
            {
                "session_id": SESSION_ID,
                "scenario_id": RELEASE_SCENARIO_ID,
                "status": status.value,
                "created_at": T0,
                "updated_at": T1,
                "accident_triggered_at": T1,
                "baseline_run_id": None,
                "baseline_outcome": None,
                "telemetry_sample_count": None,
                "replay_started_at": None,
                "replay_interval_ms": None,
                "error_code": error_code or "SIMULATOR_UNAVAILABLE",
            }
        )
    raise AssertionError(f"unsupported status fixture: {status}")


def make_service(
    tmp_path: Path,
    *,
    clock: SequenceClock,
    session: MissionSession | None = None,
    result_bytes: bytes | None = None,
) -> tuple[TelemetryReplayService, SessionStore, RunStore, str]:
    session_store = SessionStore(make_sessions_root(tmp_path))
    run_store = RunStore(make_runs_root(tmp_path))
    run_id = seed_completed_run(
        run_store,
        result_bytes if result_bytes is not None else baseline_result_bytes(),
    )
    if session is None:
        session = make_replaying_session(baseline_run_id=run_id)
    else:
        session = session.model_copy(update={"baseline_run_id": run_id})
    session_store.create_session(session)
    service = TelemetryReplayService(
        session_store=session_store,
        run_store=run_store,
        now_provider=clock,
    )
    return service, session_store, run_store, run_id


def one_sample_result_bytes() -> bytes:
    base = load_baseline_result()
    sample = base.telemetry_history[0]
    one = base.model_copy(
        update={
            "telemetry_history": [sample],
        }
    )
    return one.model_dump_json().encode("utf-8")


def rejected_with_telemetry_bytes() -> bytes:
    invalid = SimulationResult.model_validate_json(
        (RESULTS_DIR / "invalid_plan_result.json").read_bytes()
    )
    baseline = load_baseline_result()
    seeded = invalid.model_copy(
        update={
            "telemetry_history": list(baseline.telemetry_history),
            "scenario_id": RELEASE_SCENARIO_ID,
        }
    )
    return seeded.model_dump_json().encode("utf-8")


def assert_batch_equivalent(a: ReplayEventBatch, b: ReplayEventBatch) -> None:
    assert a.milliseconds_until_next_event == b.milliseconds_until_next_event
    assert a.terminal == b.terminal
    assert len(a.events) == len(b.events)
    for left, right in zip(a.events, b.events, strict=True):
        assert left.event_type == right.event_type
        assert left.sequence == right.sequence
        assert left.payload.model_dump() == right.payload.model_dump()


# --- A. Construction ---


def test_construction_valid_dependencies(tmp_path: Path) -> None:
    sessions = make_sessions_root(tmp_path)
    runs = make_runs_root(tmp_path)
    clock = SequenceClock([REPLAY_START])
    service = TelemetryReplayService(
        session_store=SessionStore(sessions),
        run_store=RunStore(runs),
        now_provider=clock,
    )
    assert service is not None
    assert list(sessions.iterdir()) == []
    assert list(runs.iterdir()) == []


@pytest.mark.asyncio
async def test_naive_now_provider_rejected(tmp_path: Path) -> None:
    naive = datetime(2026, 7, 15, 12, 0, 0)
    service, _, _, _ = make_service(tmp_path, clock=SequenceClock([naive]))
    with pytest.raises(ValueError, match="timezone-aware"):
        await service.get_current_telemetry(SESSION_ID)


# --- B. Replay preconditions ---


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("status", "exc_type", "code"),
    [
        (
            MissionSessionStatus.READY,
            ReplayNotStartedError,
            ErrorCode.REPLAY_NOT_STARTED,
        ),
        (
            MissionSessionStatus.TRIGGERING,
            ReplayNotStartedError,
            ErrorCode.REPLAY_NOT_STARTED,
        ),
        (
            MissionSessionStatus.BASELINE_READY,
            ReplayNotStartedError,
            ErrorCode.REPLAY_NOT_STARTED,
        ),
        (
            MissionSessionStatus.ERROR,
            MissionSessionConflictError,
            ErrorCode.MISSION_STATE_CONFLICT,
        ),
    ],
)
async def test_precondition_rejects_non_replay_status(
    tmp_path: Path,
    status: MissionSessionStatus,
    exc_type: type[Exception],
    code: ErrorCode,
) -> None:
    session_store = SessionStore(make_sessions_root(tmp_path))
    run_store = RunStore(make_runs_root(tmp_path))
    run_id = seed_completed_run(run_store, baseline_result_bytes())
    session_store.create_session(make_status_session(status, baseline_run_id=run_id))
    service = TelemetryReplayService(
        session_store=session_store,
        run_store=run_store,
        now_provider=SequenceClock([REPLAY_START]),
    )
    with pytest.raises(exc_type) as telemetry_exc:
        await service.get_current_telemetry(SESSION_ID)
    assert telemetry_exc.value.code == code
    with pytest.raises(exc_type) as events_exc:
        await service.get_due_events(SESSION_ID, last_event_id=None)
    assert events_exc.value.code == code


@pytest.mark.asyncio
async def test_replaying_and_completed_accepted(tmp_path: Path) -> None:
    service, _, _, _ = make_service(
        tmp_path,
        clock=SequenceClock([REPLAY_START]),
    )
    current = await service.get_current_telemetry(SESSION_ID)
    assert current.status == MissionSessionStatus.REPLAYING
    assert current.sample_index == 0

    session_store = SessionStore(make_sessions_root(tmp_path / "done"))
    run_store = RunStore(make_runs_root(tmp_path / "done"))
    run_id = seed_completed_run(run_store, baseline_result_bytes())
    session_store.create_session(make_completed_session(baseline_run_id=run_id))
    done = TelemetryReplayService(
        session_store=session_store,
        run_store=run_store,
        now_provider=SequenceClock([REPLAY_START]),
    )
    completed = await done.get_current_telemetry(SESSION_ID)
    assert completed.status == MissionSessionStatus.COMPLETED
    assert completed.sample_index == 5


# --- C. Current telemetry boundaries ---


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("offset_ms", "expected_index", "expected_status"),
    [
        (0, 0, MissionSessionStatus.REPLAYING),
        (249, 0, MissionSessionStatus.REPLAYING),
        (250, 1, MissionSessionStatus.REPLAYING),
        (500, 2, MissionSessionStatus.REPLAYING),
        (1249, 4, MissionSessionStatus.REPLAYING),
        (1250, 5, MissionSessionStatus.COMPLETED),
        (10_000, 5, MissionSessionStatus.COMPLETED),
    ],
)
async def test_current_telemetry_boundaries(
    tmp_path: Path,
    offset_ms: int,
    expected_index: int,
    expected_status: MissionSessionStatus,
) -> None:
    result = load_baseline_result()
    service, _, _, _ = make_service(
        tmp_path,
        clock=SequenceClock([at_ms(offset_ms)]),
    )
    response = await service.get_current_telemetry(SESSION_ID)
    assert response.status == expected_status
    assert response.sample_index == expected_index
    assert response.sample_count == SIX
    assert response.telemetry == result.telemetry_history[expected_index]
    assert isinstance(response, CurrentTelemetryResponse)


# --- D. One-sample replay ---


@pytest.mark.asyncio
async def test_one_sample_replay(tmp_path: Path) -> None:
    service, session_store, _, _ = make_service(
        tmp_path,
        clock=SequenceClock([REPLAY_START, REPLAY_START, REPLAY_START, REPLAY_START]),
        session=make_replaying_session(baseline_run_id=RUN_ID, sample_count=1),
        result_bytes=one_sample_result_bytes(),
    )
    current = await service.get_current_telemetry(SESSION_ID)
    assert current.sample_index == 0
    assert current.status == MissionSessionStatus.COMPLETED
    assert session_store.read_session(SESSION_ID).status == MissionSessionStatus.COMPLETED

    batch = await service.get_due_events(SESSION_ID, last_event_id=None)
    assert [e.sequence for e in batch.events] == [0, 1]
    assert batch.events[0].event_type == "telemetry"
    assert batch.events[1].event_type == "complete"
    assert batch.terminal is True

    only_complete = await service.get_due_events(SESSION_ID, last_event_id="0")
    assert [e.sequence for e in only_complete.events] == [1]
    assert only_complete.events[0].event_type == "complete"

    empty = await service.get_due_events(SESSION_ID, last_event_id="1")
    assert empty.events == ()
    assert empty.terminal is True
    assert empty.milliseconds_until_next_event == 0


# --- E. COMPLETED persistence ---


@pytest.mark.asyncio
async def test_completed_persistence_once(tmp_path: Path) -> None:
    service, session_store, run_store, run_id = make_service(
        tmp_path,
        clock=SequenceClock([at_ms(1250), at_ms(2000)]),
    )
    result_path = run_store._resolve_run_directory(run_id) / "result.json"
    before_result = result_path.read_bytes()
    before_hash = hashlib.sha256(before_result).hexdigest()
    before_names = sorted(p.name for p in result_path.parent.iterdir())

    replace_calls = {"count": 0}
    original_replace = session_store.replace_session

    def counting_replace(*args: Any, **kwargs: Any) -> MissionSession:
        replace_calls["count"] += 1
        return original_replace(*args, **kwargs)

    with patch.object(session_store, "replace_session", side_effect=counting_replace):
        first = await service.get_current_telemetry(SESSION_ID)
        second = await service.get_current_telemetry(SESSION_ID)

    assert first.status == MissionSessionStatus.COMPLETED
    assert second.status == MissionSessionStatus.COMPLETED
    assert replace_calls["count"] == 1

    session = session_store.read_session(SESSION_ID)
    assert session.status == MissionSessionStatus.COMPLETED
    assert session.updated_at == at_ms(1250)
    assert session.replay_started_at == REPLAY_START
    assert session.replay_interval_ms == INTERVAL_MS
    assert session.baseline_run_id == run_id
    assert session.updated_at == at_ms(1250)

    assert result_path.read_bytes() == before_result
    assert hashlib.sha256(result_path.read_bytes()).hexdigest() == before_hash
    assert sorted(p.name for p in result_path.parent.iterdir()) == before_names


# --- F. Exact event ordering before completion ---


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("last_event_id", "expected_sequences"),
    [
        (None, [0, 1, 2, 3]),
        ("0", [1, 2, 3]),
        ("2", [3]),
        ("3", []),
    ],
)
async def test_event_ordering_before_completion(
    tmp_path: Path,
    last_event_id: str | None,
    expected_sequences: list[int],
) -> None:
    result = load_baseline_result()
    service, _, _, _ = make_service(
        tmp_path,
        clock=SequenceClock([at_ms(750)]),
    )
    batch = await service.get_due_events(SESSION_ID, last_event_id=last_event_id)
    assert [e.sequence for e in batch.events] == expected_sequences
    assert batch.terminal is False
    for event in batch.events:
        assert event.event_type == "telemetry"
        assert isinstance(event.payload, ReplayTelemetryEvent)
        assert event.sequence == event.payload.sequence
        assert event.payload.sample_index == event.sequence
        assert event.payload.sample_count == SIX
        assert event.payload.telemetry == result.telemetry_history[event.sequence]


# --- G. Completion ordering ---


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("last_event_id", "expected_sequences"),
    [
        (None, [0, 1, 2, 3, 4, 5, 6]),
        ("4", [5, 6]),
        ("5", [6]),
        ("6", []),
    ],
)
async def test_completion_ordering_failure(
    tmp_path: Path,
    last_event_id: str | None,
    expected_sequences: list[int],
) -> None:
    result = load_baseline_result()
    service, _, _, run_id = make_service(
        tmp_path,
        clock=SequenceClock([at_ms(1250)]),
    )
    batch = await service.get_due_events(SESSION_ID, last_event_id=last_event_id)
    assert [e.sequence for e in batch.events] == expected_sequences
    assert batch.terminal is True
    assert batch.milliseconds_until_next_event == 0
    if expected_sequences and expected_sequences[-1] == SIX:
        complete = batch.events[-1]
        assert complete.event_type == "complete"
        assert isinstance(complete.payload, ReplayCompleteEvent)
        assert complete.payload.outcome == result.outcome
        assert complete.payload.valid_plan == result.valid_plan
        assert complete.payload.failure_reasons == result.failure_reasons
        assert complete.payload.metrics == result.metrics
        assert complete.payload.baseline_run_id == run_id


@pytest.mark.asyncio
async def test_completion_payload_stabilized(tmp_path: Path) -> None:
    result = SimulationResult.model_validate_json(valid_plan_result_bytes())
    n = len(result.telemetry_history)
    service, _, _, run_id = make_service(
        tmp_path,
        clock=SequenceClock([at_ms((n - 1) * INTERVAL_MS)]),
        session=make_replaying_session(
            baseline_run_id=RUN_ID,
            outcome=OutcomeStatus.STABILIZED,
            sample_count=n,
        ),
        result_bytes=valid_plan_result_bytes(),
    )
    batch = await service.get_due_events(SESSION_ID, last_event_id=str(n - 1))
    assert len(batch.events) == 1
    complete = batch.events[0]
    assert complete.event_type == "complete"
    assert isinstance(complete.payload, ReplayCompleteEvent)
    assert complete.payload.outcome == OutcomeStatus.STABILIZED
    assert complete.payload.metrics == result.metrics
    assert complete.payload.baseline_run_id == run_id


@pytest.mark.asyncio
async def test_completion_payload_rejected_with_seeded_telemetry(
    tmp_path: Path,
) -> None:
    result = SimulationResult.model_validate_json(rejected_with_telemetry_bytes())
    n = len(result.telemetry_history)
    service, _, _, run_id = make_service(
        tmp_path,
        clock=SequenceClock([at_ms((n - 1) * INTERVAL_MS)]),
        session=make_replaying_session(
            baseline_run_id=RUN_ID,
            outcome=OutcomeStatus.REJECTED,
            sample_count=n,
        ),
        result_bytes=rejected_with_telemetry_bytes(),
    )
    batch = await service.get_due_events(SESSION_ID, last_event_id=None)
    assert batch.events[-1].event_type == "complete"
    payload = batch.events[-1].payload
    assert isinstance(payload, ReplayCompleteEvent)
    assert payload.outcome == OutcomeStatus.REJECTED
    assert payload.valid_plan == result.valid_plan
    assert payload.failure_reasons == result.failure_reasons
    assert payload.metrics == result.metrics


# --- H. Delay behavior ---


@pytest.mark.asyncio
async def test_delay_behavior(tmp_path: Path) -> None:
    service, _, _, _ = make_service(
        tmp_path,
        clock=SequenceClock(
            [
                at_ms(0),
                at_ms(249),
                at_ms(250),
                at_ms(1250),
                at_ms(1250),
            ]
        ),
    )
    due = await service.get_due_events(SESSION_ID, last_event_id=None)
    assert due.events
    assert due.milliseconds_until_next_event == 0

    waiting = await service.get_due_events(SESSION_ID, last_event_id="0")
    assert waiting.events == ()
    assert waiting.terminal is False
    assert waiting.milliseconds_until_next_event == 1

    boundary = await service.get_due_events(SESSION_ID, last_event_id="1")
    assert boundary.events == ()
    assert boundary.milliseconds_until_next_event == INTERVAL_MS

    terminal = await service.get_due_events(SESSION_ID, last_event_id=None)
    assert terminal.terminal is True
    assert terminal.milliseconds_until_next_event == 0

    already = await service.get_due_events(SESSION_ID, last_event_id="6")
    assert already.events == ()
    assert already.terminal is True
    assert already.milliseconds_until_next_event == 0


# --- I. Last-Event-ID validation ---


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "last_event_id",
    [None, "0", "5", "6"],
)
async def test_last_event_id_accepts_valid(
    tmp_path: Path,
    last_event_id: str | None,
) -> None:
    service, _, _, _ = make_service(
        tmp_path,
        clock=SequenceClock([at_ms(1250)]),
    )
    batch = await service.get_due_events(SESSION_ID, last_event_id=last_event_id)
    assert isinstance(batch, ReplayEventBatch)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "last_event_id",
    ["", " 1", "1 ", "+1", "-1", "01", "1.0", "0x1", "7", "abc", "00"],
)
async def test_last_event_id_rejects_invalid(
    tmp_path: Path,
    last_event_id: str,
) -> None:
    service, _, _, _ = make_service(
        tmp_path,
        clock=SequenceClock([REPLAY_START]),
    )
    with pytest.raises(ReplayEventIdInvalidError) as exc_info:
        await service.get_due_events(SESSION_ID, last_event_id=last_event_id)
    assert exc_info.value.code == ErrorCode.REPLAY_EVENT_ID_INVALID


# --- J. Catch-up ---


@pytest.mark.asyncio
async def test_catch_up_emits_missed_samples_in_order(tmp_path: Path) -> None:
    result = load_baseline_result()
    service, _, _, _ = make_service(
        tmp_path,
        clock=SequenceClock([at_ms(1000)]),
    )
    batch = await service.get_due_events(SESSION_ID, last_event_id=None)
    assert [e.sequence for e in batch.events] == [0, 1, 2, 3, 4]
    for event in batch.events:
        assert event.payload.telemetry == result.telemetry_history[event.sequence]


# --- K. Linked-result integrity ---


@pytest.mark.asyncio
async def test_missing_result_unavailable(tmp_path: Path) -> None:
    session_store = SessionStore(make_sessions_root(tmp_path))
    run_store = RunStore(make_runs_root(tmp_path))
    session_store.create_session(make_replaying_session(baseline_run_id=RUN_ID))
    before = session_json_path(tmp_path / "sessions").read_bytes()
    service = TelemetryReplayService(
        session_store=session_store,
        run_store=run_store,
        now_provider=SequenceClock([REPLAY_START]),
    )
    with pytest.raises(BaselineResultUnavailableError) as exc_info:
        await service.get_current_telemetry(SESSION_ID)
    assert exc_info.value.code == ErrorCode.BASELINE_RESULT_UNAVAILABLE
    assert exc_info.value.__cause__ is not None
    assert session_json_path(tmp_path / "sessions").read_bytes() == before
    assert session_store.read_session(SESSION_ID).status == MissionSessionStatus.REPLAYING


@pytest.mark.asyncio
async def test_corrupt_result_unavailable(tmp_path: Path) -> None:
    session_store = SessionStore(make_sessions_root(tmp_path))
    run_store = RunStore(make_runs_root(tmp_path))
    run_id = seed_completed_run(run_store, baseline_result_bytes())
    run_dir = run_store._resolve_run_directory(run_id)
    (run_dir / "result.json").write_text("{not-json", encoding="utf-8")
    session_store.create_session(make_replaying_session(baseline_run_id=run_id))
    before = session_json_path(tmp_path / "sessions").read_bytes()
    service = TelemetryReplayService(
        session_store=session_store,
        run_store=run_store,
        now_provider=SequenceClock([at_ms(1250)]),
    )
    with pytest.raises(BaselineResultUnavailableError) as exc_info:
        await service.get_due_events(SESSION_ID, last_event_id=None)
    assert exc_info.value.code == ErrorCode.BASELINE_RESULT_UNAVAILABLE
    assert exc_info.value.__cause__ is not None
    assert session_json_path(tmp_path / "sessions").read_bytes() == before
    assert session_store.read_session(SESSION_ID).status == MissionSessionStatus.REPLAYING


@pytest.mark.asyncio
async def test_scenario_mismatch(tmp_path: Path) -> None:
    result = load_baseline_result()
    mismatched = result.model_copy(update={"scenario_id": "other_scenario_id"})
    service, session_store, _, _ = make_service(
        tmp_path,
        clock=SequenceClock([at_ms(1250)]),
        result_bytes=mismatched.model_dump_json().encode("utf-8"),
    )
    before = session_json_path(tmp_path / "sessions").read_bytes()
    with pytest.raises(BaselineResultMismatchError) as exc_info:
        await service.get_current_telemetry(SESSION_ID)
    assert exc_info.value.code == ErrorCode.BASELINE_RESULT_MISMATCH
    assert session_json_path(tmp_path / "sessions").read_bytes() == before
    assert session_store.read_session(SESSION_ID).status == MissionSessionStatus.REPLAYING


@pytest.mark.asyncio
async def test_outcome_mismatch(tmp_path: Path) -> None:
    service, session_store, _, run_id = make_service(
        tmp_path,
        clock=SequenceClock([REPLAY_START]),
    )
    # rewrite session outcome without touching result
    session = session_store.read_session(SESSION_ID)
    session_store.replace_session(
        session.model_copy(update={"baseline_outcome": OutcomeStatus.STABILIZED}),
        expected_status=MissionSessionStatus.REPLAYING,
        expected_updated_at=session.updated_at,
    )
    before = session_json_path(tmp_path / "sessions").read_bytes()
    with pytest.raises(BaselineResultMismatchError):
        await service.get_current_telemetry(SESSION_ID)
    assert session_json_path(tmp_path / "sessions").read_bytes() == before


@pytest.mark.asyncio
async def test_sample_count_mismatch(tmp_path: Path) -> None:
    service, session_store, _, _ = make_service(
        tmp_path,
        clock=SequenceClock([REPLAY_START]),
    )
    session = session_store.read_session(SESSION_ID)
    session_store.replace_session(
        session.model_copy(update={"telemetry_sample_count": 3}),
        expected_status=MissionSessionStatus.REPLAYING,
        expected_updated_at=session.updated_at,
    )
    with pytest.raises(BaselineResultMismatchError):
        await service.get_current_telemetry(SESSION_ID)
    assert session_store.read_session(SESSION_ID).status == MissionSessionStatus.REPLAYING


@pytest.mark.asyncio
async def test_empty_telemetry_mismatch(tmp_path: Path) -> None:
    # constructible empty telemetry cannot satisfy REPLAYING schema sample_count>0
    # with matching empty history; force mismatch via corrupt empty file vs count
    empty = load_baseline_result().model_copy(update={"telemetry_history": []})
    session_store = SessionStore(make_sessions_root(tmp_path))
    run_store = RunStore(make_runs_root(tmp_path))
    run_id = seed_completed_run(
        run_store,
        empty.model_dump_json().encode("utf-8"),
        outcome=OutcomeStatus.FAILURE.value,
    )
    session_store.create_session(
        make_replaying_session(baseline_run_id=run_id, sample_count=6)
    )
    service = TelemetryReplayService(
        session_store=session_store,
        run_store=run_store,
        now_provider=SequenceClock([REPLAY_START]),
    )
    with pytest.raises(BaselineResultMismatchError):
        await service.get_current_telemetry(SESSION_ID)


# --- L. Artifact immutability ---


@pytest.mark.asyncio
async def test_artifact_immutability_incomplete(tmp_path: Path) -> None:
    service, session_store, run_store, run_id = make_service(
        tmp_path,
        clock=SequenceClock([at_ms(100), at_ms(100)]),
    )
    result_path = run_store._resolve_run_directory(run_id) / "result.json"
    before_result = result_path.read_bytes()
    before_hash = hashlib.sha256(before_result).hexdigest()
    before_dir = sorted(p.name for p in result_path.parent.iterdir())
    before_session = session_json_path(tmp_path / "sessions").read_bytes()

    await service.get_current_telemetry(SESSION_ID)
    await service.get_due_events(SESSION_ID, last_event_id=None)

    assert result_path.read_bytes() == before_result
    assert hashlib.sha256(result_path.read_bytes()).hexdigest() == before_hash
    assert sorted(p.name for p in result_path.parent.iterdir()) == before_dir
    assert session_json_path(tmp_path / "sessions").read_bytes() == before_session


@pytest.mark.asyncio
async def test_artifact_immutability_on_completion(tmp_path: Path) -> None:
    service, session_store, run_store, run_id = make_service(
        tmp_path,
        clock=SequenceClock([at_ms(1250)]),
    )
    result_path = run_store._resolve_run_directory(run_id) / "result.json"
    before_result = result_path.read_bytes()
    before_hash = hashlib.sha256(before_result).hexdigest()

    await service.get_current_telemetry(SESSION_ID)

    assert result_path.read_bytes() == before_result
    assert hashlib.sha256(result_path.read_bytes()).hexdigest() == before_hash
    session = session_store.read_session(SESSION_ID)
    assert session.status == MissionSessionStatus.COMPLETED
    payload = json.loads(session_json_path(tmp_path / "sessions").read_text("utf-8"))
    for key in FORBIDDEN_SESSION_KEYS:
        assert key not in payload
    assert "path" not in payload
    assert "\\" not in json.dumps(payload)


# --- M. Multiple clients ---


@pytest.mark.asyncio
async def test_multiple_clients_equivalent_batches(tmp_path: Path) -> None:
    session_store = SessionStore(make_sessions_root(tmp_path))
    run_store = RunStore(make_runs_root(tmp_path))
    run_id = seed_completed_run(run_store, baseline_result_bytes())
    session_store.create_session(make_replaying_session(baseline_run_id=run_id))

    replace_calls = {"count": 0}
    original_replace = session_store.replace_session

    def counting_replace(*args: Any, **kwargs: Any) -> MissionSession:
        replace_calls["count"] += 1
        return original_replace(*args, **kwargs)

    clock_a = SequenceClock([at_ms(1250)])
    clock_b = SequenceClock([at_ms(1250)])
    service_a = TelemetryReplayService(
        session_store=session_store,
        run_store=run_store,
        now_provider=clock_a,
    )
    service_b = TelemetryReplayService(
        session_store=session_store,
        run_store=run_store,
        now_provider=clock_b,
    )

    with patch.object(session_store, "replace_session", side_effect=counting_replace):
        batch_a, batch_b = await asyncio.gather(
            service_a.get_due_events(SESSION_ID, last_event_id=None),
            service_b.get_due_events(SESSION_ID, last_event_id=None),
        )

    assert_batch_equivalent(batch_a, batch_b)
    assert replace_calls["count"] == 1
    assert batch_a.events[-1].event_type == "complete"

    service_c = TelemetryReplayService(
        session_store=session_store,
        run_store=run_store,
        now_provider=SequenceClock([at_ms(1250)]),
    )
    slice_batch = await service_c.get_due_events(SESSION_ID, last_event_id="5")
    assert [e.sequence for e in slice_batch.events] == [6]


# --- N. Restart safety ---


@pytest.mark.asyncio
async def test_restart_safety(tmp_path: Path) -> None:
    sessions = make_sessions_root(tmp_path)
    runs = make_runs_root(tmp_path)
    session_store = SessionStore(sessions)
    run_store = RunStore(runs)
    run_id = seed_completed_run(run_store, baseline_result_bytes())
    session_store.create_session(make_replaying_session(baseline_run_id=run_id))

    fresh_sessions = SessionStore(sessions)
    fresh_runs = RunStore(runs)
    service = TelemetryReplayService(
        session_store=fresh_sessions,
        run_store=fresh_runs,
        now_provider=SequenceClock([at_ms(1250)]),
    )
    current = await service.get_current_telemetry(SESSION_ID)
    assert current.sample_index == 5
    assert current.status == MissionSessionStatus.COMPLETED
    batch = await TelemetryReplayService(
        session_store=SessionStore(sessions),
        run_store=RunStore(runs),
        now_provider=SequenceClock([at_ms(1250)]),
    ).get_due_events(SESSION_ID, last_event_id=None)
    assert [e.sequence for e in batch.events] == [0, 1, 2, 3, 4, 5, 6]


# --- O. No sleeps or transport logic ---


def test_no_sleeps_or_transport_imports() -> None:
    module = importlib.import_module("app.services.telemetry_replay_service")
    module_path = Path(module.__file__)
    tree = ast.parse(module_path.read_text(encoding="utf-8"))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imported.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])
        elif isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
            if node.value.id in {"asyncio", "time"} and node.attr == "sleep":
                pytest.fail("sleep usage found")
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            if (
                isinstance(node.func.value, ast.Name)
                and node.func.value.id in {"asyncio", "time"}
                and node.func.attr == "sleep"
            ):
                pytest.fail("sleep call found")
    assert "fastapi" not in imported
    assert "starlette" not in imported


# --- P. No result interpretation ---


@pytest.mark.asyncio
async def test_failure_and_rejected_replay_normally(tmp_path: Path) -> None:
    failure_service, _, _, _ = make_service(
        tmp_path / "failure",
        clock=SequenceClock([at_ms(1250)]),
    )
    failure_batch = await failure_service.get_due_events(
        SESSION_ID, last_event_id=None
    )
    assert failure_batch.events[-1].event_type == "complete"
    assert failure_batch.events[-1].payload.outcome == OutcomeStatus.FAILURE

    rejected_service, _, _, _ = make_service(
        tmp_path / "rejected",
        clock=SequenceClock([at_ms(1250)]),
        session=make_replaying_session(
            baseline_run_id=RUN_ID,
            outcome=OutcomeStatus.REJECTED,
            sample_count=SIX,
        ),
        result_bytes=rejected_with_telemetry_bytes(),
    )
    rejected_batch = await rejected_service.get_due_events(
        SESSION_ID, last_event_id=None
    )
    assert rejected_batch.events[-1].event_type == "complete"
    assert rejected_batch.events[-1].payload.outcome == OutcomeStatus.REJECTED
    assert all(
        e.event_type in {"telemetry", "complete"} for e in rejected_batch.events
    )


# --- Q. Strict response models ---


@pytest.mark.asyncio
async def test_strict_response_models(tmp_path: Path) -> None:
    service, _, _, _ = make_service(
        tmp_path,
        clock=SequenceClock([REPLAY_START, at_ms(1250)]),
    )
    current = await service.get_current_telemetry(SESSION_ID)
    dumped = current.model_dump()
    assert "survival_probability" not in dumped
    CurrentTelemetryResponse.model_validate(dumped)

    batch = await service.get_due_events(SESSION_ID, last_event_id=None)
    for event in batch.events:
        if event.event_type == "telemetry":
            assert isinstance(event, ReplayServiceEvent)
            ReplayTelemetryEvent.model_validate(event.payload.model_dump())
            assert "survival_probability" not in event.payload.model_dump()
        else:
            ReplayCompleteEvent.model_validate(event.payload.model_dump())
            assert "survival_probability" not in event.payload.model_dump()


# --- R. Timestamp discipline ---


@pytest.mark.asyncio
async def test_timestamp_discipline(tmp_path: Path) -> None:
    clock = SequenceClock([at_ms(100)])
    service, session_store, _, _ = make_service(tmp_path, clock=clock)
    before = session_store.read_session(SESSION_ID).updated_at
    await service.get_current_telemetry(SESSION_ID)
    assert clock.calls == 1
    assert session_store.read_session(SESSION_ID).updated_at == before

    clock2 = SequenceClock([at_ms(1250)])
    service2 = TelemetryReplayService(
        session_store=session_store,
        run_store=RunStore(tmp_path / "runs"),
        now_provider=clock2,
    )
    await service2.get_current_telemetry(SESSION_ID)
    assert clock2.calls == 1
    session = session_store.read_session(SESSION_ID)
    assert session.updated_at == at_ms(1250)
    assert session.updated_at >= session.replay_started_at  # type: ignore[operator]


# --- S. Session content constraints ---


@pytest.mark.asyncio
async def test_session_content_constraints_after_completion(tmp_path: Path) -> None:
    service, _, _, _ = make_service(
        tmp_path,
        clock=SequenceClock([at_ms(1250)]),
    )
    await service.get_current_telemetry(SESSION_ID)
    payload = json.loads(session_json_path(tmp_path / "sessions").read_text("utf-8"))
    for key in FORBIDDEN_SESSION_KEYS:
        assert key not in payload
    assert payload["status"] == MissionSessionStatus.COMPLETED.value
