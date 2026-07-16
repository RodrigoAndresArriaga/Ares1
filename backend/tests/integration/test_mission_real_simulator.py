# Phase 3 Step 10: real-simulator mission lifecycle and complete telemetry replay
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from app.core.config import clear_settings_cache
from app.main import create_app
from app.schemas.api import ErrorCode
from app.schemas.mission import (
    AccidentTriggerResponse,
    MissionCreateResponse,
    MissionSession,
    MissionSessionStatus,
)
from app.schemas.replay import (
    CurrentTelemetryResponse,
    ReplayCompleteEvent,
    ReplayStartResponse,
    ReplayTelemetryEvent,
)
from app.schemas.result import OutcomeStatus, SimulationResult
from app.schemas.run import PersistedRunResultResponse
from app.services.run_store import sha256_file
from fastapi.testclient import TestClient
from tests.conftest import (
    REAL_BINARY,
    RELEASE_SCENARIO_ID,
    SHARED_SIM_RESULT_PATH,
    make_real_app_settings,
    require_real_simulator,
)
from tests.integration.test_sse_replay import (
    _artifact_fingerprint,
    _parse_sse_frames,
)

# configured Settings minimum replay interval (ms)
INTERVAL_MS = 25
# current release-gate fixture behavior for mars_hab_atmosphere_solar_failure
EXPECTED_RELEASE_TELEMETRY_SAMPLES = 6

pytestmark = [
    pytest.mark.integration,
    pytest.mark.real_simulator,
]


@pytest.fixture(autouse=True)
def _require_binary() -> None:
    require_real_simulator()


@pytest.fixture(autouse=True)
def _clear_cache() -> None:
    clear_settings_cache()
    yield
    clear_settings_cache()


# list immediate child directories under runs root
def _run_dirs(runs_dir: Path) -> list[Path]:
    if not runs_dir.is_dir():
        return []
    return sorted(path for path in runs_dir.iterdir() if path.is_dir())


# assert session payload carries no numerical telemetry or result bodies
def _assert_no_numerical_payload(payload: dict[str, Any]) -> None:
    encoded = json.dumps(payload)
    for forbidden in (
        "telemetry_history",
        "cabin_pressure_kpa",
        "survival_probability",
        "timeline",
        "metrics",
    ):
        assert forbidden not in encoded


# filter SSE frames to replay events, ignoring heartbeat comments
def _replay_events(frames: list[dict[str, Any]]) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for frame in frames:
        if "comment" in frame:
            continue
        assert "event" in frame, f"malformed replay frame: {frame!r}"
        assert "id" in frame, f"malformed replay frame missing id: {frame!r}"
        assert "data" in frame, f"malformed replay frame missing data: {frame!r}"
        events.append(frame)
    return events


def test_mission_real_lifecycle_replay_resume(tmp_path: Path) -> None:
    shared_before = (
        SHARED_SIM_RESULT_PATH.read_bytes()
        if SHARED_SIM_RESULT_PATH.is_file()
        else None
    )
    settings = make_real_app_settings(tmp_path)
    assert settings.sim_binary == REAL_BINARY
    assert settings.replay_min_interval_ms == INTERVAL_MS
    app = create_app(settings_override=settings)

    with TestClient(app) as client:
        assert app.state.simulation_service is not None
        assert app.state.mission_lifecycle_service is not None
        assert app.state.telemetry_replay_service is not None

        # 1. create mission
        create_res = client.post(
            "/api/missions",
            json={"scenario_id": RELEASE_SCENARIO_ID},
        )
        assert create_res.status_code == 201
        created = MissionCreateResponse.model_validate(create_res.json())
        session = created.session
        session_id = session.session_id
        assert session.status == MissionSessionStatus.READY
        assert session.baseline_run_id is None
        assert session.baseline_outcome is None
        assert session.telemetry_sample_count is None
        assert session.replay_started_at is None
        assert session.replay_interval_ms is None
        assert session.accident_triggered_at is None
        _assert_no_numerical_payload(create_res.json())

        # 2. telemetry unavailable before replay
        pre_tel = client.get(f"/api/missions/{session_id}/telemetry")
        assert pre_tel.status_code == 409
        assert pre_tel.json()["code"] == ErrorCode.REPLAY_NOT_STARTED.value

        # 3. trigger accident (real simulator, plan=None)
        accident_res = client.post(f"/api/missions/{session_id}/accident")
        assert accident_res.status_code == 200
        accident = AccidentTriggerResponse.model_validate(accident_res.json())
        assert accident.session.status == MissionSessionStatus.BASELINE_READY
        assert accident.baseline_outcome == OutcomeStatus.FAILURE
        assert accident.telemetry_sample_count > 0
        # release-gate evidence: current captured release behavior has 6 samples
        assert accident.telemetry_sample_count == EXPECTED_RELEASE_TELEMETRY_SAMPLES
        baseline_run_id = accident.baseline_run_id
        assert baseline_run_id == accident.session.baseline_run_id
        run_dirs = _run_dirs(settings.runs_dir)
        assert len(run_dirs) == 1
        assert run_dirs[0].name == baseline_run_id

        # 4. inspect mission state
        get_res = client.get(f"/api/missions/{session_id}")
        assert get_res.status_code == 200
        mission = MissionSession.model_validate(get_res.json())
        assert mission.status == MissionSessionStatus.BASELINE_READY
        assert mission.baseline_run_id == baseline_run_id
        assert mission.baseline_outcome == OutcomeStatus.FAILURE
        assert mission.telemetry_sample_count == accident.telemetry_sample_count
        assert mission.replay_started_at is None
        assert mission.replay_interval_ms is None

        # 5. retrieve persisted result (comparison authority)
        result_res = client.get(f"/api/sim/result/{baseline_run_id}")
        assert result_res.status_code == 200
        persisted = PersistedRunResultResponse.model_validate(result_res.json())
        authority = persisted.result
        assert authority.outcome == OutcomeStatus.FAILURE
        assert authority.valid_plan is True
        assert authority.plan_id == ""
        assert "critical_repair_impossible" in authority.failure_reasons
        assert len(authority.telemetry_history) == accident.telemetry_sample_count
        assert persisted.metadata.run_id == baseline_run_id
        assert persisted.metadata.scenario_id == RELEASE_SCENARIO_ID
        assert persisted.run_id == baseline_run_id
        n = len(authority.telemetry_history)
        assert n == EXPECTED_RELEASE_TELEMETRY_SAMPLES

        run_dir = settings.runs_dir / baseline_run_id
        result_path = run_dir / "result.json"
        metadata = json.loads(
            (run_dir / "metadata.json").read_text(encoding="utf-8"),
        )
        assert metadata["result_sha256"] == sha256_file(result_path)
        before = _artifact_fingerprint(app, baseline_run_id)

        # 6. start replay at configured minimum interval
        replay_res = client.post(
            f"/api/missions/{session_id}/replay",
            json={"interval_ms": INTERVAL_MS, "restart": False},
        )
        assert replay_res.status_code == 200
        replay = ReplayStartResponse.model_validate(replay_res.json())
        assert replay.session.status == MissionSessionStatus.REPLAYING
        assert replay.stream_path == f"/api/missions/{session_id}/stream"
        assert (
            replay.current_telemetry_path
            == f"/api/missions/{session_id}/telemetry"
        )
        assert replay.session.baseline_run_id == baseline_run_id
        assert replay.session.baseline_outcome == OutcomeStatus.FAILURE
        assert replay.session.telemetry_sample_count == n

        # 7. current telemetry equals authority sample at service-selected index
        cur_res = client.get(replay.current_telemetry_path)
        assert cur_res.status_code == 200
        current = CurrentTelemetryResponse.model_validate(cur_res.json())
        assert current.sample_count == n
        assert current.baseline_run_id == baseline_run_id
        assert (
            current.telemetry
            == authority.telemetry_history[current.sample_index]
        )
        assert "survival_probability" not in cur_res.text

        # 8. consume full SSE stream
        stream_res = client.get(replay.stream_path)
        assert stream_res.status_code == 200
        assert "text/event-stream" in stream_res.headers["content-type"]
        frames = _parse_sse_frames(stream_res.content)
        events = _replay_events(frames)
        assert "survival_probability" not in stream_res.text

        telemetry_events = [e for e in events if e["event"] == "telemetry"]
        complete_events = [e for e in events if e["event"] == "complete"]
        error_events = [e for e in events if e["event"] == "error"]
        assert error_events == []
        assert len(telemetry_events) == n
        assert [e["id"] for e in telemetry_events] == [str(i) for i in range(n)]
        for index, frame in enumerate(telemetry_events):
            payload = ReplayTelemetryEvent.model_validate(frame["data"])
            assert payload.sequence == index
            assert payload.sample_index == index
            assert payload.sample_count == n
            assert payload.session_id == session_id
            assert payload.telemetry == authority.telemetry_history[index]

        assert len(complete_events) == 1
        assert complete_events[0]["id"] == str(n)
        complete = ReplayCompleteEvent.model_validate(complete_events[0]["data"])
        assert complete.sequence == n
        assert complete.baseline_run_id == baseline_run_id
        assert complete.outcome == authority.outcome
        assert complete.valid_plan == authority.valid_plan
        assert complete.failure_reasons == authority.failure_reasons
        assert complete.metrics == authority.metrics
        assert complete.session_id == session_id
        assert events[-1]["event"] == "complete"

        # 9. completed mission state
        done_res = client.get(f"/api/missions/{session_id}")
        assert done_res.status_code == 200
        done = MissionSession.model_validate(done_res.json())
        assert done.status == MissionSessionStatus.COMPLETED
        assert done.baseline_run_id == baseline_run_id
        assert done.baseline_outcome == OutcomeStatus.FAILURE
        assert done.telemetry_sample_count == n
        assert done.replay_started_at is not None
        assert done.replay_interval_ms == INTERVAL_MS
        _assert_no_numerical_payload(done_res.json())

        session_dir = settings.sessions_dir / session_id
        session_names = {path.name for path in session_dir.iterdir()}
        assert session_names == {"session.json"}
        session_json = json.loads(
            (session_dir / "session.json").read_text(encoding="utf-8"),
        )
        for forbidden in (
            "telemetry",
            "telemetry_history",
            "metrics",
            "timeline",
            "result",
            "cursor",
            "sample_index",
        ):
            assert forbidden not in session_json

        # 10. final current telemetry
        final_tel = client.get(f"/api/missions/{session_id}/telemetry")
        assert final_tel.status_code == 200
        final = CurrentTelemetryResponse.model_validate(final_tel.json())
        assert final.status == MissionSessionStatus.COMPLETED
        assert final.sample_index == n - 1
        assert final.sample_count == n
        assert final.telemetry == authority.telemetry_history[n - 1]

        # 11. artifact integrity after replay
        after = _artifact_fingerprint(app, baseline_run_id)
        assert after == before
        assert len(_run_dirs(settings.runs_dir)) == 1
        run_names = {path.name for path in run_dir.iterdir()}
        assert "cursor" not in run_names
        assert not any("cursor" in name for name in run_names)
        assert "result.json" in run_names
        assert "metadata.json" in run_names

        # 12. Last-Event-ID resume against completed real result
        mid_id = str(n // 2 - 1) if n >= 2 else "0"
        mid_res = client.get(
            f"/api/missions/{session_id}/stream",
            headers={"Last-Event-ID": mid_id},
        )
        assert mid_res.status_code == 200
        assert "text/event-stream" in mid_res.headers["content-type"]
        mid_events = _replay_events(_parse_sse_frames(mid_res.content))
        expected_ids = [str(i) for i in range(int(mid_id) + 1, n + 1)]
        assert [e["id"] for e in mid_events] == expected_ids
        assert mid_events[-1]["event"] == "complete"
        for frame in mid_events[:-1]:
            assert frame["event"] == "telemetry"
            payload = ReplayTelemetryEvent.model_validate(frame["data"])
            assert payload.telemetry == authority.telemetry_history[
                payload.sample_index
            ]

        after_complete = client.get(
            f"/api/missions/{session_id}/stream",
            headers={"Last-Event-ID": str(n)},
        )
        assert after_complete.status_code == 200
        assert "text/event-stream" in after_complete.headers["content-type"]
        assert after_complete.content in (b"", b"\n")
        assert _parse_sse_frames(after_complete.content) == []

        still = MissionSession.model_validate(
            client.get(f"/api/missions/{session_id}").json(),
        )
        assert still.status == MissionSessionStatus.COMPLETED
        assert still.baseline_run_id == baseline_run_id

    if shared_before is not None:
        assert SHARED_SIM_RESULT_PATH.read_bytes() == shared_before


def test_mission_real_baseline_determinism(tmp_path: Path) -> None:
    settings = make_real_app_settings(tmp_path)
    app = create_app(settings_override=settings)

    with TestClient(app) as client:
        results: list[SimulationResult] = []
        session_ids: list[str] = []
        run_ids: list[str] = []

        for _ in range(2):
            create_res = client.post(
                "/api/missions",
                json={"scenario_id": RELEASE_SCENARIO_ID},
            )
            assert create_res.status_code == 201
            session_id = MissionCreateResponse.model_validate(
                create_res.json(),
            ).session.session_id
            session_ids.append(session_id)

            accident_res = client.post(f"/api/missions/{session_id}/accident")
            assert accident_res.status_code == 200
            accident = AccidentTriggerResponse.model_validate(
                accident_res.json(),
            )
            assert accident.baseline_outcome == OutcomeStatus.FAILURE
            assert accident.telemetry_sample_count > 0
            run_ids.append(accident.baseline_run_id)

            result_res = client.get(
                f"/api/sim/result/{accident.baseline_run_id}",
            )
            assert result_res.status_code == 200
            persisted = PersistedRunResultResponse.model_validate(
                result_res.json(),
            )
            results.append(persisted.result)

        assert session_ids[0] != session_ids[1]
        assert run_ids[0] != run_ids[1]
        assert len(_run_dirs(settings.runs_dir)) == 2

        dump_a = results[0].model_dump(mode="json")
        dump_b = results[1].model_dump(mode="json")
        assert dump_a == dump_b
        assert dump_a["scenario_id"] == RELEASE_SCENARIO_ID
        assert dump_a["plan_id"] == ""
        assert dump_a["outcome"] == OutcomeStatus.FAILURE.value
        assert dump_a["valid_plan"] is True
        assert "critical_repair_impossible" in dump_a["failure_reasons"]
        assert dump_a["metrics"] == dump_b["metrics"]
        assert dump_a["timeline"] == dump_b["timeline"]
        assert dump_a["telemetry_history"] == dump_b["telemetry_history"]
        assert len(dump_a["telemetry_history"]) > 0
        # release-gate evidence: current captured release sample count
        assert len(dump_a["telemetry_history"]) == EXPECTED_RELEASE_TELEMETRY_SAMPLES
