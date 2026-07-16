# Phase 5 Step 4 real planning release gate
# frozen baseline → replay → Phase 4 retrieval → Nemotron Super → simulator validation
from __future__ import annotations

import hashlib
import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest
from app.core.config import clear_settings_cache
from app.main import create_app
from app.schemas.actions import ActionType
from app.schemas.mission import (
    AccidentTriggerResponse,
    MissionCreateResponse,
    MissionSession,
    MissionSessionStatus,
)
from app.schemas.plan import RecoveryPlan
from app.schemas.planning import PlanningAttemptStatus
from app.schemas.planning_validation import (
    PlanningSimulationResponse,
    PlanningValidationStatus,
    build_planning_result_comparison,
    canonical_plan_sha256,
)
from app.schemas.replay import (
    CurrentTelemetryResponse,
    ReplayCompleteEvent,
    ReplayStartResponse,
)
from app.schemas.result import OutcomeStatus, SimulationResult
from app.schemas.run import PersistedRunResultResponse
from app.services.planning_attempt_store import PlanningAttemptStore
from app.services.planning_validation_store import PlanningValidationStore
from app.services.run_store import sha256_file
from fastapi.testclient import TestClient
from tests.conftest import (
    BACKEND_ROOT,
    BASELINE_SHA256,
    REAL_BINARY,
    RELEASE_SCENARIO_ID,
    REPO_ROOT,
    SHARED_SIM_RESULT_PATH,
    TRUSTED_EMBEDDING_INDEX_PATH,
    make_real_planning_app_settings,
    require_real_planning,
    resolve_nvidia_api_key,
    sha256_hex_upper,
)
from tests.integration.test_mission_real_simulator import (
    EXPECTED_RELEASE_TELEMETRY_SAMPLES,
    INTERVAL_MS,
    _assert_no_numerical_payload,
    _replay_events,
    _run_dirs,
)
from tests.integration.test_planning_route import FORBIDDEN_PAYLOAD_KEYS
from tests.integration.test_retrieval_real_nim import (
    DEFERRED_PROCEDURE_IDS,
    EXPECTED_RERANK_CANDIDATES,
    CountingEmbeddingProvider,
    CountingReranker,
    _assert_deferred_absent_ids,
    _assert_secrets_absent,
    _capture_manual_hashes,
)
from tests.integration.test_sse_replay import _parse_sse_frames

pytestmark = [
    pytest.mark.integration,
    pytest.mark.real_planning,
    pytest.mark.real_nim,
    pytest.mark.real_simulator,
]

_SIMULATOR_OWNED_PLAN_KEYS = frozenset(
    {
        "outcome",
        "valid_plan",
        "metrics",
        "timeline",
        "telemetry_history",
        "failure_reasons",
        "mission_status",
        "survival_probability",
    },
)
_FORBIDDEN_ATTEMPT_PERSISTENCE_KEYS = frozenset(
    {
        "system_prompt",
        "user_prompt",
        "raw_response",
        "vectors",
        "telemetry_history",
        "simulation_result",
        "simulator_result",
    },
)
_FORBIDDEN_VALIDATION_PERSISTENCE_KEYS = frozenset(
    {
        "system_prompt",
        "user_prompt",
        "raw_response",
        "vectors",
        "telemetry_history",
        "filesystem_path",
        "api_key",
        "authorization",
    },
)
_UUID_PATH_PATTERN = re.compile(
    r"^/api/sim/result/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
)


@pytest.fixture(autouse=True)
def _require_real_planning_gate() -> None:
    require_real_planning()


@pytest.fixture(autouse=True)
def _clear_settings_cache() -> Any:
    clear_settings_cache()
    yield
    clear_settings_cache()


def _require_real_planning_api_key() -> str:
    key = resolve_nvidia_api_key()
    assert key is not None
    return key


@dataclass
class CallCounters:
    planner_completion_calls: int = 0
    sim_with_plan: int = 0
    sim_without_plan: int = 0
    counting_embed: CountingEmbeddingProvider | None = None
    counting_rerank: CountingReranker | None = None


@dataclass
class ReleaseEvidence:
    settings: Any
    session_id: str
    baseline_run_id: str
    attempt_id: str
    candidate_run_id: str
    plan_response: PlanningSimulationResponse
    baseline_result_bytes: bytes
    baseline_metadata_bytes: bytes
    index_bytes_before: bytes
    index_hash_before: str
    manual_hashes_before: dict[str, str]
    session_json_after_replay: bytes
    api_key: str


def _attach_call_counters(app: Any) -> CallCounters:
    counters = CallCounters()
    retrieval = app.state.procedure_retrieval_service
    assert retrieval is not None
    counting_embed = CountingEmbeddingProvider(retrieval._provider)
    counting_rerank = CountingReranker(retrieval._reranker)
    retrieval._provider = counting_embed
    retrieval._reranker = counting_rerank
    counters.counting_embed = counting_embed
    counters.counting_rerank = counting_rerank

    client = app.state.nvidia_nim_client
    assert client is not None
    original_completion = client.create_chat_completion

    def counting_completion(**kwargs: Any) -> Any:
        counters.planner_completion_calls += 1
        return original_completion(**kwargs)

    client.create_chat_completion = counting_completion  # type: ignore[method-assign]

    sim_service = app.state.simulation_service
    original_run = sim_service.run_simulation

    async def counting_run(request: Any) -> Any:
        if request.plan is None:
            counters.sim_without_plan += 1
        else:
            counters.sim_with_plan += 1
        return await original_run(request)

    sim_service.run_simulation = counting_run
    return counters


def _reset_planning_counters(counters: CallCounters) -> None:
    assert counters.counting_embed is not None
    assert counters.counting_rerank is not None
    counters.counting_embed.reset_counts()
    counters.counting_rerank.reset_counts()
    counters.planner_completion_calls = 0
    counters.sim_with_plan = 0
    counters.sim_without_plan = 0


def _consume_replay_to_completion(
    client: TestClient,
    *,
    session_id: str,
    stream_path: str,
    authority: SimulationResult,
) -> None:
    stream_res = client.get(stream_path)
    assert stream_res.status_code == 200
    frames = _parse_sse_frames(stream_res.content)
    events = _replay_events(frames)
    telemetry_events = [event for event in events if event["event"] == "telemetry"]
    complete_events = [event for event in events if event["event"] == "complete"]
    assert not [event for event in events if event["event"] == "error"]
    assert len(telemetry_events) == len(authority.telemetry_history)
    assert len(complete_events) == 1
    complete = ReplayCompleteEvent.model_validate(complete_events[0]["data"])
    assert complete.outcome == authority.outcome
    assert complete.session_id == session_id


def _collect_json_keys(value: Any) -> set[str]:
    keys: set[str] = set()
    if isinstance(value, dict):
        keys.update(value.keys())
        for item in value.values():
            keys.update(_collect_json_keys(item))
    elif isinstance(value, list):
        for item in value:
            keys.update(_collect_json_keys(item))
    return keys


def _assert_forbidden_keys_absent(payload: dict[str, Any], forbidden: frozenset[str]) -> None:
    present = _collect_json_keys(payload)
    for key in forbidden:
        assert key not in present


def _assert_no_absolute_paths(text: str) -> None:
    for root in (BACKEND_ROOT, REPO_ROOT, REAL_BINARY):
        assert str(root) not in text


def _assert_planning_secrecy(text: str, api_key: str) -> None:
    _assert_secrets_absent(text, api_key)
    _assert_no_absolute_paths(text)
    for token in ("system_prompt", "user_prompt", "raw_response", "vectors"):
        assert token not in text


def _assert_recovery_plan_contract(plan: RecoveryPlan) -> None:
    assert len(plan.actions) >= 1
    dumped = plan.model_dump(mode="json")
    for key in _SIMULATOR_OWNED_PLAN_KEYS:
        assert key not in dumped
    for action in plan.actions:
        assert action.type in ActionType
        action_dump = action.model_dump(mode="json")
        for key in _SIMULATOR_OWNED_PLAN_KEYS:
            assert key not in action_dump


def _quality_failure_diagnostic(response: PlanningSimulationResponse) -> str:
    attempt = response.attempt
    plan = attempt.generation_result.plan
    action_lines = [
        f"  action[{index}] type={action.type.value} start_min={action.start_min}"
        for index, action in enumerate(plan.actions)
    ]
    procedure_lines: list[str] = []
    for match in attempt.retrieval_result.matches:
        section = "/".join(match.chunk.section_path)
        procedure_lines.append(
            f"  {match.chunk.procedure_id} section={section} rank={match.rank}",
        )
    candidate = response.validation.candidate
    outcome = candidate.outcome.value if candidate is not None else "missing"
    failure_reasons = candidate.failure_reasons if candidate is not None else []
    return (
        "Real planner candidate did not STABILIZE.\n"
        f"simulator_outcome={outcome}\n"
        f"failure_reasons={failure_reasons}\n"
        "generated_actions:\n"
        + "\n".join(action_lines)
        + "\nretrieved_procedures:\n"
        + "\n".join(procedure_lines)
    )


def _run_release_lifecycle(
    client: TestClient,
    app: Any,
    settings: Any,
    api_key: str,
) -> tuple[str, str, SimulationResult, bytes, bytes, bytes]:
    create_res = client.post(
        "/api/missions",
        json={"scenario_id": RELEASE_SCENARIO_ID},
    )
    assert create_res.status_code == 201
    created = MissionCreateResponse.model_validate(create_res.json())
    session_id = created.session.session_id
    assert created.session.status == MissionSessionStatus.READY
    assert created.session.baseline_run_id is None
    assert created.session.replay_started_at is None
    _assert_no_numerical_payload(create_res.json())
    _assert_planning_secrecy(create_res.text, api_key)

    accident_res = client.post(f"/api/missions/{session_id}/accident")
    assert accident_res.status_code == 200
    accident = AccidentTriggerResponse.model_validate(accident_res.json())
    assert accident.session.status == MissionSessionStatus.BASELINE_READY
    assert accident.baseline_outcome == OutcomeStatus.FAILURE
    assert accident.telemetry_sample_count == EXPECTED_RELEASE_TELEMETRY_SAMPLES
    baseline_run_id = accident.baseline_run_id
    assert len(_run_dirs(settings.runs_dir)) == 1

    result_res = client.get(f"/api/sim/result/{baseline_run_id}")
    assert result_res.status_code == 200
    persisted = PersistedRunResultResponse.model_validate(result_res.json())
    authority = persisted.result
    assert authority.outcome == OutcomeStatus.FAILURE
    assert authority.valid_plan is True
    assert authority.plan_id == ""
    assert "critical_repair_impossible" in authority.failure_reasons
    assert len(authority.telemetry_history) == EXPECTED_RELEASE_TELEMETRY_SAMPLES
    assert sha256_hex_upper(settings.runs_dir / baseline_run_id / "result.json") == (
        BASELINE_SHA256
    )

    baseline_result_bytes = (
        settings.runs_dir / baseline_run_id / "result.json"
    ).read_bytes()
    baseline_metadata_bytes = (
        settings.runs_dir / baseline_run_id / "metadata.json"
    ).read_bytes()

    replay_res = client.post(
        f"/api/missions/{session_id}/replay",
        json={"interval_ms": INTERVAL_MS, "restart": False},
    )
    assert replay_res.status_code == 200
    replay = ReplayStartResponse.model_validate(replay_res.json())
    assert replay.session.status == MissionSessionStatus.REPLAYING
    _consume_replay_to_completion(
        client,
        session_id=session_id,
        stream_path=replay.stream_path,
        authority=authority,
    )

    final_tel = client.get(replay.current_telemetry_path)
    assert final_tel.status_code == 200
    final = CurrentTelemetryResponse.model_validate(final_tel.json())
    assert final.status == MissionSessionStatus.COMPLETED
    assert final.telemetry == authority.telemetry_history[-1]
    assert len(_run_dirs(settings.runs_dir)) == 1

    session_json_after_replay = (
        settings.sessions_dir / session_id / "session.json"
    ).read_bytes()
    return (
        session_id,
        baseline_run_id,
        authority,
        baseline_result_bytes,
        baseline_metadata_bytes,
        session_json_after_replay,
    )


def _execute_plan_and_collect_evidence(
    client: TestClient,
    app: Any,
    settings: Any,
    *,
    session_id: str,
    baseline_run_id: str,
    baseline_result_bytes: bytes,
    baseline_metadata_bytes: bytes,
    index_bytes_before: bytes,
    index_hash_before: str,
    manual_hashes_before: dict[str, str],
    session_json_after_replay: bytes,
    api_key: str,
) -> ReleaseEvidence:
    counters = _attach_call_counters(app)
    _reset_planning_counters(counters)
    runs_before_plan = len(_run_dirs(settings.runs_dir))
    planning_dirs_before = (
        sorted(path.name for path in settings.planning_attempts_dir.iterdir())
        if settings.planning_attempts_dir.is_dir()
        else []
    )

    plan_res = client.post(f"/api/missions/{session_id}/plan")
    assert plan_res.status_code == 200, plan_res.text
    _assert_planning_secrecy(plan_res.text, api_key)

    try:
        payload = PlanningSimulationResponse.model_validate(plan_res.json())
    except Exception as exc:
        pytest.fail(f"plan response failed schema validation: {exc}\n{plan_res.text}")

    candidate = payload.validation.candidate
    assert candidate is not None
    if candidate.outcome != OutcomeStatus.STABILIZED:
        pytest.fail(_quality_failure_diagnostic(payload))

    assert payload.attempt.status == PlanningAttemptStatus.CANDIDATE_READY
    assert payload.validation.status == PlanningValidationStatus.SIMULATION_COMPLETE
    assert candidate.valid_plan is True
    assert candidate.run_id != baseline_run_id
    assert payload.validation.baseline is not None
    assert payload.validation.baseline.outcome == OutcomeStatus.FAILURE
    assert payload.validation.comparison is not None
    expected_comparison = build_planning_result_comparison(
        payload.validation.baseline,
        candidate,
    )
    assert payload.validation.comparison.model_dump() == expected_comparison.model_dump()
    assert _UUID_PATH_PATTERN.fullmatch(payload.baseline_result_path)
    assert _UUID_PATH_PATTERN.fullmatch(payload.candidate_result_path)
    assert payload.baseline_result_path == f"/api/sim/result/{baseline_run_id}"
    assert payload.candidate_result_path == f"/api/sim/result/{candidate.run_id}"

    _assert_forbidden_keys_absent(plan_res.json(), FORBIDDEN_PAYLOAD_KEYS)
    plan = payload.attempt.generation_result.plan
    _assert_recovery_plan_contract(plan)
    assert payload.validation.candidate_plan_sha256 == canonical_plan_sha256(plan)

    retrieval_matches = {
        match.chunk_id: match.chunk
        for match in payload.attempt.retrieval_result.matches
    }
    _assert_deferred_absent_ids(
        {match.chunk.procedure_id for match in payload.attempt.retrieval_result.matches},
    )
    for support in payload.attempt.preflight.action_support:
        action = plan.actions[support.action_index]
        assert support.action_type == action.type
        for chunk_id in support.supporting_chunk_ids:
            assert chunk_id in retrieval_matches
            chunk = retrieval_matches[chunk_id]
            assert action.type in chunk.allowed_actions
        for procedure_id in support.supporting_procedure_ids:
            assert procedure_id not in DEFERRED_PROCEDURE_IDS
            assert any(
                chunk.procedure_id == procedure_id
                for chunk_id in support.supporting_chunk_ids
                for chunk in (retrieval_matches[chunk_id],)
            )

    assert counters.counting_embed is not None
    assert counters.counting_rerank is not None
    assert counters.counting_embed.document_embed_calls == 0
    assert counters.counting_embed.query_embed_calls == 1
    assert counters.counting_rerank.rerank_calls == 1
    assert counters.counting_rerank.last_document_count == EXPECTED_RERANK_CANDIDATES
    assert counters.planner_completion_calls == 1
    assert counters.sim_with_plan == 1
    assert counters.sim_without_plan == 0
    assert payload.attempt.retrieval_result.returned_count <= (
        payload.attempt.retrieval_result.requested_top_k
    )

    candidate_run_id = candidate.run_id
    candidate_res = client.get(f"/api/sim/result/{candidate_run_id}")
    assert candidate_res.status_code == 200
    candidate_persisted = PersistedRunResultResponse.model_validate(candidate_res.json())
    assert candidate_persisted.result.outcome == OutcomeStatus.STABILIZED
    assert candidate_persisted.result.valid_plan is True
    assert candidate_persisted.result.plan_id == plan.plan_id
    assert candidate_persisted.metadata.result_sha256 == candidate.result_sha256
    assert candidate_persisted.metadata.result_sha256 == sha256_file(
        settings.runs_dir / candidate_run_id / "result.json",
    )
    assert "telemetry_history" not in _collect_json_keys(plan_res.json())

    candidate_run_dir = settings.runs_dir / candidate_run_id
    plan_path = candidate_run_dir / "plan.json"
    assert plan_path.is_file()
    metadata = json.loads(
        (candidate_run_dir / "metadata.json").read_text(encoding="utf-8"),
    )
    assert metadata["plan_sha256"] == sha256_file(plan_path)
    assert metadata["plan_id"] == plan.plan_id

    attempt_id = payload.attempt.attempt_id
    attempt_store = PlanningAttemptStore(settings.planning_attempts_dir)
    validation_store = PlanningValidationStore(settings.planning_attempts_dir)
    stored_attempt = attempt_store.read_attempt(attempt_id)
    stored_validation = validation_store.read_validation(attempt_id)
    assert stored_attempt.model_dump() == payload.attempt.model_dump()
    assert stored_validation.model_dump() == payload.validation.model_dump()
    _assert_forbidden_keys_absent(
        json.loads(
            (settings.planning_attempts_dir / attempt_id / "attempt.json").read_text(
                encoding="utf-8",
            ),
        ),
        _FORBIDDEN_ATTEMPT_PERSISTENCE_KEYS,
    )
    _assert_forbidden_keys_absent(
        json.loads(
            (settings.planning_attempts_dir / attempt_id / "validation.json").read_text(
                encoding="utf-8",
            ),
        ),
        _FORBIDDEN_VALIDATION_PERSISTENCE_KEYS,
    )

    assert len(_run_dirs(settings.runs_dir)) == runs_before_plan + 1
    planning_dirs_after = sorted(
        path.name for path in settings.planning_attempts_dir.iterdir()
    )
    assert len(planning_dirs_after) == len(planning_dirs_before) + 1
    attempt_dir = settings.planning_attempts_dir / attempt_id
    assert {path.name for path in attempt_dir.iterdir()} == {
        "attempt.json",
        "validation.json",
    }

    baseline_run_dir = settings.runs_dir / baseline_run_id
    assert (baseline_run_dir / "result.json").read_bytes() == baseline_result_bytes
    assert (baseline_run_dir / "metadata.json").read_bytes() == baseline_metadata_bytes
    assert TRUSTED_EMBEDDING_INDEX_PATH.read_bytes() == index_bytes_before
    assert hashlib.sha256(TRUSTED_EMBEDDING_INDEX_PATH.read_bytes()).hexdigest().lower() == (
        index_hash_before
    )
    assert _capture_manual_hashes() == manual_hashes_before
    assert (
        settings.sessions_dir / session_id / "session.json"
    ).read_bytes() == session_json_after_replay

    index_parent = TRUSTED_EMBEDDING_INDEX_PATH.parent
    assert not (index_parent / "query_cache.json").exists()
    assert not (index_parent / "rerank_cache.json").exists()
    assert not list(index_parent.glob("*cursor*"))

    baseline_result_res = client.get(f"/api/sim/result/{baseline_run_id}")
    assert baseline_result_res.status_code == 200

    combined_secrecy = "\n".join(
        [
            plan_res.text,
            candidate_res.text,
            baseline_result_res.text,
            (settings.planning_attempts_dir / attempt_id / "attempt.json").read_text(
                encoding="utf-8",
            ),
            (settings.planning_attempts_dir / attempt_id / "validation.json").read_text(
                encoding="utf-8",
            ),
        ],
    )
    _assert_planning_secrecy(combined_secrecy, api_key)

    return ReleaseEvidence(
        settings=settings,
        session_id=session_id,
        baseline_run_id=baseline_run_id,
        attempt_id=attempt_id,
        candidate_run_id=candidate_run_id,
        plan_response=payload,
        baseline_result_bytes=baseline_result_bytes,
        baseline_metadata_bytes=baseline_metadata_bytes,
        index_bytes_before=index_bytes_before,
        index_hash_before=index_hash_before,
        manual_hashes_before=manual_hashes_before,
        session_json_after_replay=session_json_after_replay,
        api_key=api_key,
    )


def test_planning_real_e2e_release_gate(
    tmp_path: Path,
) -> None:
    api_key = _require_real_planning_api_key()
    shared_before = (
        SHARED_SIM_RESULT_PATH.read_bytes()
        if SHARED_SIM_RESULT_PATH.is_file()
        else None
    )
    settings = make_real_planning_app_settings(
        tmp_path,
        api_key=api_key,
    )
    assert settings.sim_binary == REAL_BINARY
    assert settings.procedure_embedding_index_path == TRUSTED_EMBEDDING_INDEX_PATH.resolve()

    index_bytes_before = TRUSTED_EMBEDDING_INDEX_PATH.read_bytes()
    index_hash_before = hashlib.sha256(index_bytes_before).hexdigest().lower()
    manual_hashes_before = _capture_manual_hashes()

    app = create_app(settings_override=settings)
    with TestClient(app) as client:
        assert app.state.mission_planning_service is not None
        assert app.state.mission_plan_simulation_service is not None
        assert app.state.procedure_retrieval_service is not None

        (
            session_id,
            baseline_run_id,
            _authority,
            baseline_result_bytes,
            baseline_metadata_bytes,
            session_json_after_replay,
        ) = _run_release_lifecycle(
            client,
            app,
            settings,
            api_key,
        )

        evidence = _execute_plan_and_collect_evidence(
            client,
            app,
            settings,
            session_id=session_id,
            baseline_run_id=baseline_run_id,
            baseline_result_bytes=baseline_result_bytes,
            baseline_metadata_bytes=baseline_metadata_bytes,
            index_bytes_before=index_bytes_before,
            index_hash_before=index_hash_before,
            manual_hashes_before=manual_hashes_before,
            session_json_after_replay=session_json_after_replay,
            api_key=api_key,
        )

    if shared_before is not None:
        assert SHARED_SIM_RESULT_PATH.read_bytes() == shared_before

    # restart persistence proof without invoking POST /plan again
    restart_app = create_app(settings_override=settings)
    with TestClient(restart_app) as restart_client:
        restart_counters = _attach_call_counters(restart_app)
        _reset_planning_counters(restart_counters)

        mission_res = restart_client.get(f"/api/missions/{evidence.session_id}")
        assert mission_res.status_code == 200
        mission = MissionSession.model_validate(mission_res.json())
        assert mission.baseline_run_id == evidence.baseline_run_id

        baseline_res = restart_client.get(
            f"/api/sim/result/{evidence.baseline_run_id}",
        )
        assert baseline_res.status_code == 200
        baseline_persisted = PersistedRunResultResponse.model_validate(
            baseline_res.json(),
        )
        assert baseline_persisted.result.outcome == OutcomeStatus.FAILURE
        assert baseline_persisted.metadata.result_sha256 == sha256_hex_upper(
            settings.runs_dir / evidence.baseline_run_id / "result.json",
        )
        assert (
            settings.runs_dir / evidence.baseline_run_id / "result.json"
        ).read_bytes() == evidence.baseline_result_bytes

        candidate_res = restart_client.get(
            f"/api/sim/result/{evidence.candidate_run_id}",
        )
        assert candidate_res.status_code == 200
        candidate_persisted = PersistedRunResultResponse.model_validate(
            candidate_res.json(),
        )
        assert candidate_persisted.result.outcome == OutcomeStatus.STABILIZED
        assert candidate_persisted.result.plan_id == (
            evidence.plan_response.attempt.generation_result.plan.plan_id
        )

        fresh_attempt = PlanningAttemptStore(
            settings.planning_attempts_dir,
        ).read_attempt(evidence.attempt_id)
        fresh_validation = PlanningValidationStore(
            settings.planning_attempts_dir,
        ).read_validation(evidence.attempt_id)
        assert fresh_attempt.model_dump() == evidence.plan_response.attempt.model_dump()
        assert fresh_validation.model_dump() == evidence.plan_response.validation.model_dump()

        assert restart_counters.counting_embed is not None
        assert restart_counters.counting_rerank is not None
        assert restart_counters.counting_embed.document_embed_calls == 0
        assert restart_counters.counting_embed.query_embed_calls == 0
        assert restart_counters.counting_rerank.rerank_calls == 0
        assert restart_counters.planner_completion_calls == 0
        assert restart_counters.sim_with_plan == 0
        assert restart_counters.sim_without_plan == 0

        _assert_planning_secrecy(
            "\n".join(
                [
                    mission_res.text,
                    baseline_res.text,
                    candidate_res.text,
                ],
            ),
            evidence.api_key,
        )


def test_planning_real_e2e_cwd_independence(
    tmp_path: Path,
) -> None:
    api_key = _require_real_planning_api_key()
    settings = make_real_planning_app_settings(
        tmp_path,
        api_key=api_key,
    )
    alt_cwd = tmp_path / "alt_cwd"
    alt_cwd.mkdir()
    before_listing = set(alt_cwd.rglob("*"))
    previous = Path.cwd()
    try:
        os.chdir(alt_cwd)
        app = create_app(settings_override=settings)
        with TestClient(app) as client:
            index_bytes_before = TRUSTED_EMBEDDING_INDEX_PATH.read_bytes()
            index_hash_before = hashlib.sha256(index_bytes_before).hexdigest().lower()
            manual_hashes_before = _capture_manual_hashes()
            _run_release_lifecycle(
                client,
                app,
                settings,
                api_key,
            )
            assert settings.runs_dir.is_dir()
            assert settings.sessions_dir.is_dir()
            assert TRUSTED_EMBEDDING_INDEX_PATH.read_bytes() == index_bytes_before
            index_hash_after = hashlib.sha256(
                TRUSTED_EMBEDDING_INDEX_PATH.read_bytes(),
            ).hexdigest().lower()
            assert index_hash_after == index_hash_before
            assert _capture_manual_hashes() == manual_hashes_before
        after_listing = set(alt_cwd.rglob("*"))
        assert after_listing == before_listing
    finally:
        os.chdir(previous)
