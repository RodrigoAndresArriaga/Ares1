# Phase 5 Step 2 MissionPlanningService orchestration tests
from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock
from uuid import UUID

import pytest
from app.core.errors import (
    MissionRetrievalQueryTooLargeError,
    PlannerCandidateUngroundedError,
    PlannerOutputInvalidError,
    PlannerPromptTooLargeError,
    PlanningContextMismatchError,
    PlanningInProgressError,
    PlanningNotAvailableError,
)
from app.schemas.mission import MissionSession, MissionSessionStatus
from app.schemas.plan import RecoveryPlan
from app.schemas.result import OutcomeStatus
from app.services.mission_planning_service import MissionPlanningService
from app.services.mission_retrieval_query import MissionRetrievalQueryBuilder
from app.services.planner_candidate_validator import PlannerCandidateValidator
from app.services.planner_prompt import PlannerPromptBuilder
from app.services.run_store import RunStore, sha256_file
from app.services.session_store import SessionStore
from app.services.telemetry_replay_service import TelemetryReplayService
from tests.conftest import (
    PLANNING_ATTEMPT_ID,
    RELEASE_SCENARIO_ID,
    RELEASE_SCENARIO_PATH,
    RESULTS_DIR,
    make_baseline_request,
    make_grounded_recovery_plan,
    make_multi_action_retrieval_result,
    make_planner_generation_result,
    make_planner_model_metadata,
    make_planning_attempt_store,
)

SESSION_ID = "00000000-0000-4000-8000-000000000001"
OTHER_SESSION_ID = "00000000-0000-4000-8000-000000000002"
T0 = datetime(2026, 7, 15, 12, 0, 0, tzinfo=timezone.utc)
T1 = T0 + timedelta(seconds=1)
REPLAY_START = T0 + timedelta(seconds=2)
INTERVAL_MS = 250
SIX = 6


def make_sessions_root(tmp_path: Path) -> Path:
    root = tmp_path / "sessions"
    root.mkdir(parents=True, exist_ok=True)
    return root


def make_runs_root(tmp_path: Path) -> Path:
    root = tmp_path / "runs"
    root.mkdir(parents=True, exist_ok=True)
    return root


FORBIDDEN_ATTEMPT_KEYS = frozenset(
    {
        "system_prompt",
        "user_prompt",
        "raw_response",
        "api_key",
        "Authorization",
        "vectors",
        "telemetry_history",
        "simulation_result",
        "candidate_run_id",
        "valid_plan",
        "survival_probability",
    },
)


class SequenceClock:
    def __init__(self, times: list[datetime]) -> None:
        self._times = list(times)
        self._index = 0

    def __call__(self) -> datetime:
        if self._index >= len(self._times):
            return self._times[-1]
        value = self._times[self._index]
        self._index += 1
        return value


def _fake_generate(sample_plan_data: Any) -> Any:
    async def _generate(prompt: Any) -> Any:
        return make_planner_generation_result(
            prompt_package=prompt,
            plan=make_grounded_recovery_plan(sample_plan_data),
        )

    return _generate


class FakeRetrievalService:
    def __init__(self, *, result: Any | None = None, error: Exception | None = None) -> None:
        self.calls: list[dict[str, object]] = []
        self._result = result
        self._error = error

    def retrieve(self, *, query: str, top_k: int | None = None) -> Any:
        self.calls.append({"query": query, "top_k": top_k})
        if self._error is not None:
            raise self._error
        assert self._result is not None
        return self._result


def baseline_result_bytes() -> bytes:
    return (RESULTS_DIR / "baseline_result.json").read_bytes()


def seed_completed_run(store: RunStore, result_bytes: bytes) -> str:
    workspace = store.create_workspace(make_baseline_request(), RELEASE_SCENARIO_PATH)
    workspace.result_path.write_bytes(result_bytes)
    outcome = json.loads(result_bytes.decode("utf-8"))["outcome"]
    store.write_completed_metadata(
        workspace,
        result_sha256=sha256_file(workspace.result_path),
        process_exit_code=0,
        duration_ms=1,
        outcome=outcome,
    )
    return workspace.run_id


def make_replaying_session(*, baseline_run_id: str, session_id: str = SESSION_ID) -> MissionSession:
    return MissionSession.model_validate(
        {
            "session_id": session_id,
            "scenario_id": RELEASE_SCENARIO_ID,
            "status": MissionSessionStatus.REPLAYING.value,
            "created_at": T0,
            "updated_at": REPLAY_START,
            "accident_triggered_at": T1,
            "baseline_run_id": baseline_run_id,
            "baseline_outcome": OutcomeStatus.FAILURE.value,
            "telemetry_sample_count": SIX,
            "replay_started_at": REPLAY_START,
            "replay_interval_ms": INTERVAL_MS,
            "error_code": None,
        }
    )


def make_completed_session(*, baseline_run_id: str, session_id: str = SESSION_ID) -> MissionSession:
    return MissionSession.model_validate(
        {
            "session_id": session_id,
            "scenario_id": RELEASE_SCENARIO_ID,
            "status": MissionSessionStatus.COMPLETED.value,
            "created_at": T0,
            "updated_at": REPLAY_START + timedelta(seconds=2),
            "accident_triggered_at": T1,
            "baseline_run_id": baseline_run_id,
            "baseline_outcome": OutcomeStatus.FAILURE.value,
            "telemetry_sample_count": SIX,
            "replay_started_at": REPLAY_START,
            "replay_interval_ms": INTERVAL_MS,
            "error_code": None,
        }
    )


def make_status_session(
    *,
    status: MissionSessionStatus,
    baseline_run_id: str | None = None,
) -> MissionSession:
    replay_fields = (
        baseline_run_id is not None
        and status in (MissionSessionStatus.REPLAYING, MissionSessionStatus.COMPLETED)
    )
    return MissionSession.model_validate(
        {
            "session_id": SESSION_ID,
            "scenario_id": RELEASE_SCENARIO_ID,
            "status": status.value,
            "created_at": T0,
            "updated_at": T1,
            "accident_triggered_at": T1 if status != MissionSessionStatus.READY else None,
            "baseline_run_id": baseline_run_id,
            "baseline_outcome": OutcomeStatus.FAILURE.value if baseline_run_id else None,
            "telemetry_sample_count": SIX if baseline_run_id else None,
            "replay_started_at": REPLAY_START if replay_fields else None,
            "replay_interval_ms": INTERVAL_MS if replay_fields else None,
            "error_code": (
                "MISSION_TRIGGER_FAILED"
                if status == MissionSessionStatus.ERROR
                else None
            ),
        }
    )


def make_service(
    tmp_path: Path,
    *,
    retrieval: FakeRetrievalService,
    planner_provider: Any | None = None,
    clock: SequenceClock | None = None,
    attempt_id_provider: Any | None = None,
    retrieval_top_k: int = 10,
    query_max_chars: int = 50000,
) -> tuple[MissionPlanningService, dict[str, Any]]:
    session_store = SessionStore(make_sessions_root(tmp_path))
    run_store = RunStore(make_runs_root(tmp_path))
    replay_service = TelemetryReplayService(
        session_store=session_store,
        run_store=run_store,
        now_provider=clock or SequenceClock([REPLAY_START]),
    )
    prompt_builder = PlannerPromptBuilder(
        model_metadata=make_planner_model_metadata(),
        max_prompt_characters=120000,
    )
    provider = planner_provider
    if provider is None:
        provider = AsyncMock()
    service = MissionPlanningService(
        session_store=session_store,
        run_store=run_store,
        telemetry_replay_service=replay_service,
        procedure_retrieval_service=retrieval,
        planner_prompt_builder=prompt_builder,
        planner_provider=provider,
        candidate_validator=PlannerCandidateValidator(),
        attempt_store=make_planning_attempt_store(tmp_path),
        retrieval_query_builder=MissionRetrievalQueryBuilder(
            max_query_characters=query_max_chars,
        ),
        retrieval_top_k=retrieval_top_k,
        now_provider=clock or SequenceClock([REPLAY_START, T0]),
        attempt_id_provider=attempt_id_provider
        or (lambda: UUID("00000000-0000-4000-8000-000000000020")),
    )
    return service, {
        "session_store": session_store,
        "run_store": run_store,
        "replay_service": replay_service,
        "retrieval": retrieval,
        "provider": provider,
    }


def _seed_replaying(
    deps: dict[str, Any],
    *,
    session: MissionSession | None = None,
) -> str:
    run_id = seed_completed_run(deps["run_store"], baseline_result_bytes())
    replaying = session or make_replaying_session(baseline_run_id=run_id)
    deps["session_store"].create_session(replaying)
    return run_id


@pytest.mark.asyncio
async def test_generate_candidate_success(
    tmp_path: Path,
    baseline_result_data: Any,
    sample_plan_data: Any,
) -> None:
    retrieval_result = make_multi_action_retrieval_result()
    retrieval = FakeRetrievalService(result=retrieval_result)
    service, deps = make_service(tmp_path, retrieval=retrieval)
    _seed_replaying(deps)
    deps["provider"].generate_plan = AsyncMock(side_effect=_fake_generate(sample_plan_data))

    attempt = await service.generate_candidate(SESSION_ID)
    assert attempt.attempt_id == PLANNING_ATTEMPT_ID
    assert attempt.status.value == "CANDIDATE_READY"
    assert attempt.generation_result.plan.plan_id == sample_plan_data["plan_id"]
    assert len(retrieval.calls) == 1
    assert retrieval.calls[0]["top_k"] == 10
    assert "ARES-1 Mars habitat emergency procedure retrieval." in str(
        retrieval.calls[0]["query"],
    )
    deps["provider"].generate_plan.assert_awaited_once()
    on_disk = deps["session_store"].read_session(SESSION_ID)
    assert on_disk.status == MissionSessionStatus.REPLAYING


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "status",
    [
        MissionSessionStatus.READY,
        MissionSessionStatus.TRIGGERING,
        MissionSessionStatus.BASELINE_READY,
    ],
)
async def test_planning_unavailable_before_replay(
    tmp_path: Path,
    status: MissionSessionStatus,
) -> None:
    retrieval = FakeRetrievalService(result=make_multi_action_retrieval_result())
    service, deps = make_service(tmp_path, retrieval=retrieval)
    if status == MissionSessionStatus.BASELINE_READY:
        run_id = seed_completed_run(deps["run_store"], baseline_result_bytes())
        deps["session_store"].create_session(
            make_status_session(status=status, baseline_run_id=run_id),
        )
    else:
        deps["session_store"].create_session(make_status_session(status=status))
    with pytest.raises(PlanningNotAvailableError):
        await service.generate_candidate(SESSION_ID)
    assert len(retrieval.calls) == 0


@pytest.mark.asyncio
async def test_planning_unavailable_for_error_session(tmp_path: Path) -> None:
    retrieval = FakeRetrievalService(result=make_multi_action_retrieval_result())
    service, deps = make_service(tmp_path, retrieval=retrieval)
    run_id = seed_completed_run(deps["run_store"], baseline_result_bytes())
    deps["session_store"].create_session(
        make_status_session(status=MissionSessionStatus.ERROR, baseline_run_id=run_id),
    )
    with pytest.raises(PlanningNotAvailableError):
        await service.generate_candidate(SESSION_ID)


@pytest.mark.asyncio
async def test_completed_session_uses_final_sample(
    tmp_path: Path,
    sample_plan_data: Any,
) -> None:
    retrieval_result = make_multi_action_retrieval_result()
    retrieval = FakeRetrievalService(result=retrieval_result)
    service, deps = make_service(
        tmp_path,
        retrieval=retrieval,
        clock=SequenceClock([REPLAY_START + timedelta(seconds=30)]),
    )
    run_id = seed_completed_run(deps["run_store"], baseline_result_bytes())
    deps["session_store"].create_session(make_completed_session(baseline_run_id=run_id))
    deps["provider"].generate_plan = AsyncMock(side_effect=_fake_generate(sample_plan_data))

    attempt = await service.generate_candidate(SESSION_ID)
    assert attempt.mission_context.current_sample_index == SIX - 1


@pytest.mark.asyncio
async def test_context_mismatch_rejects_outcome(tmp_path: Path) -> None:
    retrieval = FakeRetrievalService(result=make_multi_action_retrieval_result())
    service, deps = make_service(tmp_path, retrieval=retrieval)
    run_id = seed_completed_run(deps["run_store"], baseline_result_bytes())
    session = make_replaying_session(baseline_run_id=run_id)
    bad = session.model_copy(update={"baseline_outcome": OutcomeStatus.STABILIZED})
    deps["session_store"].create_session(bad)
    with pytest.raises(PlanningContextMismatchError):
        await service.generate_candidate(SESSION_ID)


@pytest.mark.asyncio
async def test_ungrounded_candidate_not_persisted(
    tmp_path: Path,
    baseline_result_data: Any,
) -> None:
    retrieval_result = make_multi_action_retrieval_result()
    retrieval = FakeRetrievalService(result=retrieval_result)
    service, deps = make_service(tmp_path, retrieval=retrieval)
    _seed_replaying(deps)

    async def ungrounded_generate(prompt: Any) -> Any:
        bad_plan = RecoveryPlan.model_validate(
            {
                "plan_id": "bad_plan",
                "summary": "Unsupported packet",
                "actions": [{"type": "send_emergency_packet", "start_min": 0}],
                "rationale": "test",
                "expected_risk": "test",
                "constraints_checked": [],
            },
        )
        return make_planner_generation_result(prompt_package=prompt, plan=bad_plan)

    deps["provider"].generate_plan = ungrounded_generate

    with pytest.raises(PlannerCandidateUngroundedError):
        await service.generate_candidate(SESSION_ID)
    assert not make_planning_attempt_store(tmp_path).attempt_exists(PLANNING_ATTEMPT_ID)


@pytest.mark.asyncio
async def test_concurrent_same_session_rejected(
    tmp_path: Path,
    sample_plan_data: Any,
) -> None:
    retrieval_result = make_multi_action_retrieval_result()
    retrieval = FakeRetrievalService(result=retrieval_result)
    gate = asyncio.Event()
    service, deps = make_service(tmp_path, retrieval=retrieval)
    _seed_replaying(deps)

    async def slow_generate(prompt: Any) -> Any:
        await gate.wait()
        return await _fake_generate(sample_plan_data)(prompt)

    deps["provider"].generate_plan = slow_generate

    first = asyncio.create_task(service.generate_candidate(SESSION_ID))
    await asyncio.sleep(0.01)
    with pytest.raises(PlanningInProgressError):
        await service.generate_candidate(SESSION_ID)
    gate.set()
    await first
    assert len(retrieval.calls) == 1


@pytest.mark.asyncio
async def test_different_sessions_may_plan_concurrently(
    tmp_path: Path,
    sample_plan_data: Any,
) -> None:
    retrieval_result = make_multi_action_retrieval_result()
    retrieval = FakeRetrievalService(result=retrieval_result)
    gate = asyncio.Event()
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

    run_a = seed_completed_run(deps["run_store"], baseline_result_bytes())
    run_b = seed_completed_run(deps["run_store"], baseline_result_bytes())
    deps["session_store"].create_session(
        make_replaying_session(baseline_run_id=run_a, session_id=SESSION_ID),
    )
    deps["session_store"].create_session(
        make_replaying_session(baseline_run_id=run_b, session_id=OTHER_SESSION_ID),
    )

    async def slow_generate(prompt: Any) -> Any:
        await gate.wait()
        return await _fake_generate(sample_plan_data)(prompt)

    deps["provider"].generate_plan = slow_generate
    first = asyncio.create_task(service.generate_candidate(SESSION_ID))
    second = asyncio.create_task(service.generate_candidate(OTHER_SESSION_ID))
    await asyncio.sleep(0.01)
    gate.set()
    await asyncio.gather(first, second)
    assert len(retrieval.calls) == 2


@pytest.mark.asyncio
async def test_restart_safe_read(tmp_path: Path, sample_plan_data: Any) -> None:
    retrieval_result = make_multi_action_retrieval_result()
    retrieval = FakeRetrievalService(result=retrieval_result)
    service, deps = make_service(tmp_path, retrieval=retrieval)
    _seed_replaying(deps)
    deps["provider"].generate_plan = AsyncMock(side_effect=_fake_generate(sample_plan_data))

    created = await service.generate_candidate(SESSION_ID)
    fresh_store = make_planning_attempt_store(tmp_path)
    read = fresh_store.read_attempt(PLANNING_ATTEMPT_ID)
    assert read == created


@pytest.mark.asyncio
async def test_attempt_artifact_forbidden_keys(
    tmp_path: Path,
    sample_plan_data: Any,
) -> None:
    retrieval_result = make_multi_action_retrieval_result()
    retrieval = FakeRetrievalService(result=retrieval_result)
    service, deps = make_service(tmp_path, retrieval=retrieval)
    _seed_replaying(deps)
    deps["provider"].generate_plan = AsyncMock(side_effect=_fake_generate(sample_plan_data))
    await service.generate_candidate(SESSION_ID)

    path = tmp_path / "planning" / PLANNING_ATTEMPT_ID / "attempt.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    flattened = json.dumps(payload)
    for key in FORBIDDEN_ATTEMPT_KEYS:
        assert key not in flattened


@pytest.mark.asyncio
async def test_query_too_large_not_persisted(tmp_path: Path) -> None:
    retrieval = FakeRetrievalService(result=make_multi_action_retrieval_result())
    service, deps = make_service(tmp_path, retrieval=retrieval, query_max_chars=10)
    _seed_replaying(deps)
    with pytest.raises(MissionRetrievalQueryTooLargeError):
        await service.generate_candidate(SESSION_ID)
    assert len(retrieval.calls) == 0


@pytest.mark.asyncio
async def test_prompt_too_large_not_persisted(tmp_path: Path) -> None:
    retrieval = FakeRetrievalService(result=make_multi_action_retrieval_result())
    service, deps = make_service(tmp_path, retrieval=retrieval)
    _seed_replaying(deps)
    service._planner_prompt_builder = PlannerPromptBuilder(
        model_metadata=make_planner_model_metadata(),
        max_prompt_characters=1,
    )
    with pytest.raises(PlannerPromptTooLargeError):
        await service.generate_candidate(SESSION_ID)


@pytest.mark.asyncio
async def test_provider_failure_not_persisted(
    tmp_path: Path,
    baseline_result_data: Any,
) -> None:
    retrieval_result = make_multi_action_retrieval_result()
    retrieval = FakeRetrievalService(result=retrieval_result)
    service, deps = make_service(tmp_path, retrieval=retrieval)
    _seed_replaying(deps)
    deps["provider"].generate_plan = AsyncMock(
        side_effect=PlannerOutputInvalidError("bad output"),
    )
    with pytest.raises(PlannerOutputInvalidError):
        await service.generate_candidate(SESSION_ID)
    assert len(retrieval.calls) == 1
    deps["provider"].generate_plan.assert_awaited_once()
