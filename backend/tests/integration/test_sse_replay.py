# Phase 3 Step 9: current telemetry and SSE replay integration tests
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from app.api.sse import HEARTBEAT_FRAME, generate_replay_stream
from app.core.config import clear_settings_cache
from app.main import create_app
from app.schemas.api import ErrorCode, SimulationRunResponse
from app.schemas.mission import MissionSessionStatus
from app.schemas.replay import (
    CurrentTelemetryResponse,
    ReplayCompleteEvent,
    ReplayTelemetryEvent,
)
from app.schemas.result import OutcomeStatus, SimulationResult
from app.services.run_store import sha256_file
from app.services.telemetry_replay_service import TelemetryReplayService
from fastapi.testclient import TestClient
from tests.conftest import (
    RELEASE_SCENARIO_ID,
    RELEASE_SCENARIO_PATH,
    RESULTS_DIR,
    make_baseline_request,
    make_fake_simulation_service,
    make_mission_settings,
    seed_completed_run,
)
from tests.unit.test_telemetry_replay_service import (
    INTERVAL_MS,
    REPLAY_START,
    SIX,
    SequenceClock,
    at_ms,
    make_completed_session,
    make_replaying_session,
    make_status_session,
)

RUN_ID = "00000000-0000-4000-8000-000000000001"
UNKNOWN_SESSION = "00000000-0000-4000-8000-0000000000aa"
INVALID_SESSION = "not-a-uuid"
SEVEN = 7


@pytest.fixture(autouse=True)
def _clear_settings_cache() -> Any:
    clear_settings_cache()
    yield
    clear_settings_cache()


class SequenceClockReusable(SequenceClock):
    # keep returning the last time after the sequence is exhausted
    def __call__(self) -> datetime:
        self.calls += 1
        if self._index >= len(self._times):
            return self._times[-1]
        value = self._times[self._index]
        self._index += 1
        return value


def _open_client(
    tmp_path: Path,
    *,
    result_data: Any | None = None,
    fake_service: Any | None = None,
    **settings_overrides: Any,
) -> tuple[TestClient, Any, Any]:
    settings = make_mission_settings(tmp_path, **settings_overrides)
    if fake_service is None:
        assert result_data is not None
        fake_service = make_fake_simulation_service(result_data, run_id=RUN_ID)
    app = create_app(
        settings_override=settings,
        simulation_service_override=fake_service,
    )
    client = TestClient(app, raise_server_exceptions=False)
    client.__enter__()
    return client, app, fake_service


def _close_client(client: TestClient) -> None:
    client.__exit__(None, None, None)


def _assert_safe_error(payload: dict[str, Any], tmp_path: Path) -> None:
    assert "code" in payload
    assert "message" in payload
    encoded = json.dumps(payload)
    assert str(tmp_path) not in encoded
    assert "Traceback" not in encoded
    assert 'File "' not in encoded
    assert "telemetry_history" not in encoded


def _seed_replaying(
    app: Any,
    *,
    result_path: Path | None = None,
    clock: SequenceClock | None = None,
    interval_ms: int = INTERVAL_MS,
    completed: bool = False,
    outcome: OutcomeStatus | None = None,
    sample_count: int | None = None,
) -> tuple[str, str, SimulationResult]:
    fixture = result_path or (RESULTS_DIR / "baseline_result.json")
    result_bytes = fixture.read_bytes()
    result = SimulationResult.model_validate_json(result_bytes)
    workspace = seed_completed_run(app.state.run_store, fixture)
    run_id = workspace.run_id
    resolved_outcome = outcome or result.outcome
    count = sample_count if sample_count is not None else len(result.telemetry_history)
    if completed:
        session = make_completed_session(
            baseline_run_id=run_id,
            outcome=resolved_outcome,
            sample_count=count,
            interval_ms=interval_ms,
        )
    else:
        session = make_replaying_session(
            baseline_run_id=run_id,
            outcome=resolved_outcome,
            sample_count=count,
            interval_ms=interval_ms,
        )
    app.state.session_store.create_session(session)
    if clock is not None:
        app.state.telemetry_replay_service._now_provider = clock
    return session.session_id, run_id, result


def _parse_sse_frames(raw: str | bytes) -> list[dict[str, Any]]:
    text = raw.decode("utf-8") if isinstance(raw, bytes) else raw
    frames: list[dict[str, Any]] = []
    for block in text.split("\n\n"):
        if not block.strip():
            continue
        if block.startswith(": "):
            frames.append({"comment": block})
            continue
        event: dict[str, Any] = {"raw": block}
        data_lines: list[str] = []
        for line in block.split("\n"):
            if line.startswith("id: "):
                event["id"] = line[4:]
            elif line.startswith("event: "):
                event["event"] = line[7:]
            elif line.startswith("data: "):
                data_lines.append(line[6:])
        if data_lines:
            event["data"] = json.loads("\n".join(data_lines))
        frames.append(event)
    return frames


def _artifact_fingerprint(app: Any, run_id: str) -> tuple[bytes, str, bytes, set[str]]:
    run_dir = app.state.settings.runs_dir / run_id
    result_path = run_dir / "result.json"
    metadata_path = run_dir / "metadata.json"
    result_bytes = result_path.read_bytes()
    digest = hashlib.sha256(result_bytes).hexdigest().upper()
    metadata_bytes = metadata_path.read_bytes()
    names = {path.name for path in run_dir.iterdir()}
    return result_bytes, digest, metadata_bytes, names


# --- A. Lifespan wiring ---


def test_lifespan_wires_replay_service_and_limiter(
    tmp_path: Path,
    baseline_result_data: Any,
) -> None:
    client, app, fake = _open_client(tmp_path, result_data=baseline_result_data)
    try:
        replay = app.state.telemetry_replay_service
        limiter = app.state.replay_stream_limiter
        assert isinstance(replay, TelemetryReplayService)
        assert replay._session_store is app.state.session_store
        assert replay._run_store is app.state.run_store
        assert limiter.capacity == app.state.settings.max_replay_streams
        assert app.state.simulation_service is fake
        assert not hasattr(app.state, "replay_background_tasks")
    finally:
        _close_client(client)


def test_lifespan_fails_when_replay_service_construction_fails(
    tmp_path: Path,
    baseline_result_data: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = make_mission_settings(tmp_path)
    fake = make_fake_simulation_service(baseline_result_data, run_id=RUN_ID)
    app = create_app(settings_override=settings, simulation_service_override=fake)

    def boom(**kwargs: Any) -> Any:
        raise RuntimeError("replay service failed")

    monkeypatch.setattr("app.main.TelemetryReplayService", boom)
    with pytest.raises(RuntimeError, match="replay service failed"):
        with TestClient(app):
            pass


# --- B. OpenAPI ---


def test_openapi_includes_telemetry_and_stream(tmp_path: Path) -> None:
    settings = make_mission_settings(tmp_path)
    app = create_app(settings_override=settings)
    with TestClient(app) as client:
        payload = client.get("/openapi.json").json()
    paths = payload["paths"]
    assert "/api/missions/{session_id}/telemetry" in paths
    assert "/api/missions/{session_id}/stream" in paths
    assert "/api/missions/{session_id}/replay" in paths
    telemetry = paths["/api/missions/{session_id}/telemetry"]["get"]
    assert "CurrentTelemetryResponse" in json.dumps(telemetry)
    stream = paths["/api/missions/{session_id}/stream"]["get"]
    assert "text/event-stream" in stream["responses"]["200"]["content"]
    assert not any("websocket" in path.lower() for path in paths)


# --- C. Current telemetry ---


@pytest.mark.parametrize(
    "status",
    [
        MissionSessionStatus.READY,
        MissionSessionStatus.TRIGGERING,
        MissionSessionStatus.BASELINE_READY,
    ],
)
def test_current_telemetry_replay_not_started(
    tmp_path: Path,
    baseline_result_data: Any,
    status: MissionSessionStatus,
) -> None:
    client, app, _ = _open_client(tmp_path, result_data=baseline_result_data)
    try:
        session = make_status_session(status)
        app.state.session_store.create_session(session)
        response = client.get(f"/api/missions/{session.session_id}/telemetry")
        assert response.status_code == 409
        assert response.json()["code"] == ErrorCode.REPLAY_NOT_STARTED.value
        assert "text/event-stream" not in response.headers.get("content-type", "")
        _assert_safe_error(response.json(), tmp_path)
    finally:
        _close_client(client)


def test_current_telemetry_error_conflict(
    tmp_path: Path,
    baseline_result_data: Any,
) -> None:
    client, app, _ = _open_client(tmp_path, result_data=baseline_result_data)
    try:
        session = make_status_session(MissionSessionStatus.ERROR)
        app.state.session_store.create_session(session)
        response = client.get(f"/api/missions/{session.session_id}/telemetry")
        assert response.status_code == 409
        assert response.json()["code"] == ErrorCode.MISSION_STATE_CONFLICT.value
        _assert_safe_error(response.json(), tmp_path)
    finally:
        _close_client(client)


def test_current_telemetry_invalid_and_unknown_session(
    tmp_path: Path,
    baseline_result_data: Any,
) -> None:
    client, _, _ = _open_client(tmp_path, result_data=baseline_result_data)
    try:
        invalid = client.get(f"/api/missions/{INVALID_SESSION}/telemetry")
        assert invalid.status_code == 400
        assert invalid.json()["code"] == ErrorCode.MISSION_SESSION_ID_INVALID.value
        unknown = client.get(f"/api/missions/{UNKNOWN_SESSION}/telemetry")
        assert unknown.status_code == 404
        assert unknown.json()["code"] == ErrorCode.MISSION_SESSION_NOT_FOUND.value
        _assert_safe_error(invalid.json(), tmp_path)
        _assert_safe_error(unknown.json(), tmp_path)
    finally:
        _close_client(client)


def test_current_telemetry_replaying_and_completed_exact(
    tmp_path: Path,
    baseline_result_data: Any,
) -> None:
    client, app, _ = _open_client(tmp_path, result_data=baseline_result_data)
    try:
        session_id, run_id, result = _seed_replaying(
            app,
            clock=SequenceClockReusable([REPLAY_START]),
        )
        before = _artifact_fingerprint(app, run_id)
        response = client.get(f"/api/missions/{session_id}/telemetry")
        assert response.status_code == 200
        body = CurrentTelemetryResponse.model_validate(response.json())
        assert body.status == MissionSessionStatus.REPLAYING
        assert body.sample_index == 0
        assert body.sample_count == SIX
        assert body.telemetry == result.telemetry_history[0]
        assert set(response.json()) == {
            "session_id",
            "status",
            "sample_index",
            "sample_count",
            "telemetry",
            "baseline_run_id",
        }

        app.state.telemetry_replay_service._now_provider = SequenceClockReusable(
            [at_ms(750)]
        )
        later = client.get(f"/api/missions/{session_id}/telemetry")
        later_body = CurrentTelemetryResponse.model_validate(later.json())
        assert later_body.sample_index == 3
        assert later_body.telemetry == result.telemetry_history[3]

        app.state.telemetry_replay_service._now_provider = SequenceClockReusable(
            [at_ms(1250)]
        )
        final = client.get(f"/api/missions/{session_id}/telemetry")
        final_body = CurrentTelemetryResponse.model_validate(final.json())
        assert final_body.status == MissionSessionStatus.COMPLETED
        assert final_body.sample_index == 5
        assert final_body.telemetry == result.telemetry_history[5]

        already = client.get(f"/api/missions/{session_id}/telemetry")
        already_body = CurrentTelemetryResponse.model_validate(already.json())
        assert already_body.status == MissionSessionStatus.COMPLETED
        assert already_body.telemetry == result.telemetry_history[5]

        after = _artifact_fingerprint(app, run_id)
        assert after == before
        session_path = (
            app.state.settings.sessions_dir / session_id / "session.json"
        )
        session_json = json.loads(session_path.read_text(encoding="utf-8"))
        assert "telemetry_history" not in session_json
        assert not (app.state.settings.sessions_dir / session_id / "cursor.json").exists()
    finally:
        _close_client(client)


# --- D/E. Basic SSE and exact payload integrity ---


def test_sse_stream_ordered_exact_and_complete(
    tmp_path: Path,
    baseline_result_data: Any,
) -> None:
    client, app, _ = _open_client(tmp_path, result_data=baseline_result_data)
    try:
        session_id, run_id, result = _seed_replaying(
            app,
            clock=SequenceClockReusable([at_ms(1250)]),
        )
        before = _artifact_fingerprint(app, run_id)
        response = client.get(f"/api/missions/{session_id}/stream")
        assert response.status_code == 200
        content_type = response.headers["content-type"]
        assert content_type.startswith("text/event-stream")
        assert response.headers.get("cache-control") == "no-cache"
        assert response.headers.get("x-accel-buffering") == "no"
        assert "content-length" not in {k.lower() for k in response.headers.keys()}

        frames = _parse_sse_frames(response.content)
        telemetry_frames = [f for f in frames if f.get("event") == "telemetry"]
        complete_frames = [f for f in frames if f.get("event") == "complete"]
        assert len(telemetry_frames) == SIX
        assert len(complete_frames) == 1
        for index, frame in enumerate(telemetry_frames):
            assert frame["id"] == str(index)
            payload = ReplayTelemetryEvent.model_validate(frame["data"])
            assert payload.sequence == index
            assert payload.sample_index == index
            assert payload.sample_count == SIX
            assert payload.telemetry == result.telemetry_history[index]
        complete = ReplayCompleteEvent.model_validate(complete_frames[0]["data"])
        assert complete_frames[0]["id"] == str(SIX)
        assert complete.sequence == SIX
        assert complete.baseline_run_id == run_id
        assert complete.outcome == result.outcome
        assert complete.valid_plan == result.valid_plan
        assert complete.failure_reasons == list(result.failure_reasons)
        assert complete.metrics == result.metrics
        assert "survival_probability" not in complete_frames[0]["data"]
        assert frames[-1]["event"] == "complete"
        after = _artifact_fingerprint(app, run_id)
        assert after == before
        session = app.state.session_store.read_session(session_id)
        assert session.status == MissionSessionStatus.COMPLETED
    finally:
        _close_client(client)


# --- F. FAILURE / REJECTED / STABILIZED ---


def _make_seeding_fake(app_holder: dict[str, Any], result_data: Any) -> Any:
    from unittest.mock import AsyncMock

    from app.services.simulation_service import SimulationService

    service = AsyncMock(spec=SimulationService)
    result = SimulationResult.model_validate(result_data)

    async def _run(request: Any) -> SimulationRunResponse:
        workspace = app_holder["app"].state.run_store.create_workspace(
            make_baseline_request(),
            RELEASE_SCENARIO_PATH,
        )
        workspace.result_path.write_text(
            result.model_dump_json(),
            encoding="utf-8",
        )
        app_holder["app"].state.run_store.write_completed_metadata(
            workspace,
            result_sha256=sha256_file(workspace.result_path),
            process_exit_code=0,
            duration_ms=1,
            outcome=result.outcome.value,
        )
        return SimulationRunResponse(
            run_id=workspace.run_id,
            duration_ms=25,
            result=result,
        )

    service.run_simulation = AsyncMock(side_effect=_run)
    return service


@pytest.mark.parametrize(
    ("fixture_name", "expected_outcome"),
    [
        ("baseline_result_data", OutcomeStatus.FAILURE),
        ("valid_plan_result_data", OutcomeStatus.STABILIZED),
        ("invalid_plan_result_data", OutcomeStatus.REJECTED),
    ],
)
def test_sse_outcome_payloads_are_normal_complete(
    tmp_path: Path,
    fixture_name: str,
    expected_outcome: OutcomeStatus,
    request: pytest.FixtureRequest,
    baseline_result_data: Any,
) -> None:
    result_data = dict(request.getfixturevalue(fixture_name))
    if not result_data["telemetry_history"]:
        result_data["telemetry_history"] = baseline_result_data["telemetry_history"]
        result_data["timeline"] = baseline_result_data["timeline"]
        result_data["metrics"] = baseline_result_data["metrics"]
    app_holder: dict[str, Any] = {}
    fake = _make_seeding_fake(app_holder, result_data)
    client, app, _ = _open_client(tmp_path, fake_service=fake)
    app_holder["app"] = app
    try:
        created = client.post(
            "/api/missions",
            json={"scenario_id": RELEASE_SCENARIO_ID},
        )
        session_id = created.json()["session"]["session_id"]
        accident = client.post(f"/api/missions/{session_id}/accident")
        assert accident.status_code == 200
        replay = client.post(f"/api/missions/{session_id}/replay", json={})
        assert replay.status_code == 200
        result = SimulationResult.model_validate(result_data)
        session = app.state.session_store.read_session(session_id)
        assert session.replay_started_at is not None
        assert session.replay_interval_ms is not None
        due_at = session.replay_started_at + timedelta(
            milliseconds=len(result.telemetry_history) * session.replay_interval_ms,
        )
        app.state.telemetry_replay_service._now_provider = SequenceClockReusable([due_at])
        response = client.get(f"/api/missions/{session_id}/stream")
        assert response.status_code == 200
        frames = _parse_sse_frames(response.content)
        assert not any(f.get("event") == "error" for f in frames)
        complete = next(f for f in frames if f.get("event") == "complete")
        payload = ReplayCompleteEvent.model_validate(complete["data"])
        assert payload.outcome == expected_outcome
        assert "survival_probability" not in complete["data"]
    finally:
        _close_client(client)


# --- G/H. Resume and invalid Last-Event-ID ---


def test_sse_resume_semantics(
    tmp_path: Path,
    baseline_result_data: Any,
) -> None:
    client, app, _ = _open_client(tmp_path, result_data=baseline_result_data)
    try:
        session_id, _, result = _seed_replaying(
            app,
            clock=SequenceClockReusable([at_ms(1250)]),
            completed=True,
        )
        full = _parse_sse_frames(client.get(f"/api/missions/{session_id}/stream").content)
        assert [f["id"] for f in full if "id" in f] == [str(i) for i in range(SEVEN)]

        mid = _parse_sse_frames(
            client.get(
                f"/api/missions/{session_id}/stream",
                headers={"Last-Event-ID": "2"},
            ).content
        )
        assert [f["id"] for f in mid if "id" in f] == ["3", "4", "5", "6"]

        after_final_telemetry = _parse_sse_frames(
            client.get(
                f"/api/missions/{session_id}/stream",
                headers={"Last-Event-ID": "5"},
            ).content
        )
        assert [f["id"] for f in after_final_telemetry if "id" in f] == ["6"]
        assert after_final_telemetry[0]["event"] == "complete"

        after_complete = client.get(
            f"/api/missions/{session_id}/stream",
            headers={"Last-Event-ID": "6"},
        )
        assert after_complete.status_code == 200
        assert after_complete.content in (b"", b"\n")
        assert _parse_sse_frames(after_complete.content) == []

        from_zero = _parse_sse_frames(
            client.get(
                f"/api/missions/{session_id}/stream",
                headers={"Last-Event-ID": "0"},
            ).content
        )
        assert [f["id"] for f in from_zero if "id" in f] == [str(i) for i in range(1, 7)]
        assert result.telemetry_history[3] == ReplayTelemetryEvent.model_validate(
            mid[0]["data"]
        ).telemetry
    finally:
        _close_client(client)


@pytest.mark.parametrize(
    "bad_id",
    ["", " ", "+1", "-1", "1.5", "0x1", "01", "abc", "7"],
)
def test_invalid_last_event_id_json_400(
    tmp_path: Path,
    baseline_result_data: Any,
    bad_id: str,
) -> None:
    client, app, _ = _open_client(
        tmp_path,
        result_data=baseline_result_data,
        max_replay_streams=1,
    )
    try:
        session_id, _, _ = _seed_replaying(
            app,
            clock=SequenceClockReusable([at_ms(1250)]),
            completed=True,
        )
        response = client.get(
            f"/api/missions/{session_id}/stream",
            headers={"Last-Event-ID": bad_id},
        )
        assert response.status_code == 400
        assert response.json()["code"] == ErrorCode.REPLAY_EVENT_ID_INVALID.value
        assert "text/event-stream" not in response.headers.get("content-type", "")
        _assert_safe_error(response.json(), tmp_path)
        assert app.state.replay_stream_limiter.active_count == 0
        session = app.state.session_store.read_session(session_id)
        assert session.status == MissionSessionStatus.COMPLETED
    finally:
        _close_client(client)


# --- I. Replay not started stream ---


@pytest.mark.parametrize(
    "status",
    [
        MissionSessionStatus.READY,
        MissionSessionStatus.TRIGGERING,
        MissionSessionStatus.BASELINE_READY,
    ],
)
def test_stream_replay_not_started_json(
    tmp_path: Path,
    baseline_result_data: Any,
    status: MissionSessionStatus,
) -> None:
    client, app, _ = _open_client(
        tmp_path,
        result_data=baseline_result_data,
        max_replay_streams=1,
    )
    try:
        session = make_status_session(status)
        app.state.session_store.create_session(session)
        response = client.get(f"/api/missions/{session.session_id}/stream")
        assert response.status_code == 409
        assert response.json()["code"] == ErrorCode.REPLAY_NOT_STARTED.value
        assert "text/event-stream" not in response.headers.get("content-type", "")
        assert app.state.replay_stream_limiter.active_count == 0
        _assert_safe_error(response.json(), tmp_path)
    finally:
        _close_client(client)


def test_stream_error_status_conflict(
    tmp_path: Path,
    baseline_result_data: Any,
) -> None:
    client, app, _ = _open_client(tmp_path, result_data=baseline_result_data)
    try:
        session = make_status_session(MissionSessionStatus.ERROR)
        app.state.session_store.create_session(session)
        response = client.get(f"/api/missions/{session.session_id}/stream")
        assert response.status_code == 409
        assert response.json()["code"] == ErrorCode.MISSION_STATE_CONFLICT.value
        _assert_safe_error(response.json(), tmp_path)
    finally:
        _close_client(client)


# --- J. Heartbeats ---


@pytest.mark.asyncio
async def test_heartbeat_while_waiting(
    tmp_path: Path,
    baseline_result_data: Any,
) -> None:
    settings = make_mission_settings(
        tmp_path,
        sse_heartbeat_seconds=0.05,
        replay_default_interval_ms=250,
    )
    fake = make_fake_simulation_service(baseline_result_data, run_id=RUN_ID)
    app = create_app(settings_override=settings, simulation_service_override=fake)
    async with app.router.lifespan_context(app):
        session_id, _, _ = _seed_replaying(
            app,
            clock=SequenceClockReusable([REPLAY_START]),
            interval_ms=250,
        )
        sleep_calls: list[float] = []

        async def fake_sleep(delay: float) -> None:
            sleep_calls.append(delay)
            if len(sleep_calls) == 1:
                app.state.telemetry_replay_service._now_provider = SequenceClockReusable(
                    [at_ms(250)]
                )

        class FakeRequest:
            def __init__(self) -> None:
                self._disconnected = False

            async def is_disconnected(self) -> bool:
                return self._disconnected

        lease = await app.state.replay_stream_limiter.try_acquire()
        assert lease is not None
        initial = await app.state.telemetry_replay_service.get_due_events(
            session_id,
            last_event_id=None,
        )
        assert len(initial.events) == 1
        # service returns delay 0 with events; empty follow-up batch carries wait
        assert initial.milliseconds_until_next_event == 0

        gen = generate_replay_stream(
            request=FakeRequest(),  # type: ignore[arg-type]
            service=app.state.telemetry_replay_service,
            lease=lease,
            session_id=session_id,
            initial_batch=initial,
            initial_last_event_id=None,
            heartbeat_seconds=0.05,
            sleep=fake_sleep,
        )
        chunks: list[bytes] = []
        try:
            async for chunk in gen:
                chunks.append(chunk)
                if any(c == HEARTBEAT_FRAME for c in chunks) and any(
                    b"id: 1\n" in c for c in chunks
                ):
                    break
        finally:
            await gen.aclose()

        assert any(chunk == HEARTBEAT_FRAME for chunk in chunks)
        assert any(b"id: 0\n" in chunk for chunk in chunks)
        assert any(b"id: 1\n" in chunk for chunk in chunks)
        assert app.state.replay_stream_limiter.active_count == 0
        assert sleep_calls
        assert sleep_calls[0] == pytest.approx(0.05)


# --- K. Stream limit ---


def test_stream_limit_503_and_release(
    tmp_path: Path,
    baseline_result_data: Any,
) -> None:
    client, app, _ = _open_client(
        tmp_path,
        result_data=baseline_result_data,
        max_replay_streams=1,
    )
    try:
        session_id, _, _ = _seed_replaying(
            app,
            clock=SequenceClockReusable([at_ms(1250)]),
            completed=True,
        )

        async def deny_acquire() -> None:
            return None

        original = app.state.replay_stream_limiter.try_acquire
        app.state.replay_stream_limiter.try_acquire = deny_acquire  # type: ignore[method-assign]
        try:
            limited = client.get(f"/api/missions/{session_id}/stream")
        finally:
            app.state.replay_stream_limiter.try_acquire = original  # type: ignore[method-assign]

        assert limited.status_code == 503
        assert limited.json()["code"] == ErrorCode.REPLAY_STREAM_LIMIT.value
        assert "text/event-stream" not in limited.headers.get("content-type", "")
        _assert_safe_error(limited.json(), tmp_path)
        assert app.state.replay_stream_limiter.active_count == 0

        ok = client.get(f"/api/missions/{session_id}/stream")
        assert ok.status_code == 200
        assert ok.headers["content-type"].startswith("text/event-stream")
        frames = _parse_sse_frames(ok.content)
        assert frames[-1]["event"] == "complete"
        assert app.state.replay_stream_limiter.active_count == 0
    finally:
        _close_client(client)


def test_stream_limit_released_after_preflight_error(
    tmp_path: Path,
    baseline_result_data: Any,
) -> None:
    client, app, _ = _open_client(
        tmp_path,
        result_data=baseline_result_data,
        max_replay_streams=1,
    )
    try:
        session = make_status_session(MissionSessionStatus.READY)
        app.state.session_store.create_session(session)
        response = client.get(f"/api/missions/{session.session_id}/stream")
        assert response.status_code == 409
        assert response.json()["code"] == ErrorCode.REPLAY_NOT_STARTED.value
        assert app.state.replay_stream_limiter.active_count == 0
    finally:
        _close_client(client)

    client2, app2, _ = _open_client(
        tmp_path / "slot",
        result_data=baseline_result_data,
        max_replay_streams=1,
    )
    try:
        session_id, _, _ = _seed_replaying(
            app2,
            clock=SequenceClockReusable([at_ms(1250)]),
            completed=True,
        )
        ok = client2.get(f"/api/missions/{session_id}/stream")
        assert ok.status_code == 200
        assert app2.state.replay_stream_limiter.active_count == 0
    finally:
        _close_client(client2)


# --- L. Client disconnect ---


@pytest.mark.asyncio
async def test_disconnect_releases_slot_without_error_transition(
    tmp_path: Path,
    baseline_result_data: Any,
) -> None:
    settings = make_mission_settings(tmp_path, max_replay_streams=1)
    fake = make_fake_simulation_service(baseline_result_data, run_id=RUN_ID)
    app = create_app(settings_override=settings, simulation_service_override=fake)

    class DisconnectRequest:
        def __init__(self) -> None:
            self.calls = 0

        async def is_disconnected(self) -> bool:
            self.calls += 1
            return self.calls > 2

    async with app.router.lifespan_context(app):
        session_id, _, _ = _seed_replaying(
            app,
            clock=SequenceClockReusable([REPLAY_START]),
            interval_ms=60_000,
        )
        lease = await app.state.replay_stream_limiter.try_acquire()
        assert lease is not None
        initial = await app.state.telemetry_replay_service.get_due_events(
            session_id,
            last_event_id=None,
        )

        async def sleeper(_delay: float) -> None:
            return None

        chunks: list[bytes] = []
        async for chunk in generate_replay_stream(
            request=DisconnectRequest(),  # type: ignore[arg-type]
            service=app.state.telemetry_replay_service,
            lease=lease,
            session_id=session_id,
            initial_batch=initial,
            initial_last_event_id=None,
            heartbeat_seconds=15.0,
            sleep=sleeper,
        ):
            chunks.append(chunk)

        assert app.state.replay_stream_limiter.active_count == 0
        session = app.state.session_store.read_session(session_id)
        assert session.status == MissionSessionStatus.REPLAYING
        assert not (app.state.settings.sessions_dir / session_id / "cursor.json").exists()

        app.state.telemetry_replay_service._now_provider = SequenceClockReusable(
            [at_ms(1250)]
        )
        with TestClient(app) as client:
            resumed = client.get(
                f"/api/missions/{session_id}/stream",
                headers={"Last-Event-ID": "0"},
            )
        frames = _parse_sse_frames(resumed.content)
        assert frames[0]["id"] == "1"


def test_multiple_clients_equivalent_and_independent_cursors(
    tmp_path: Path,
    baseline_result_data: Any,
) -> None:
    client, app, _ = _open_client(
        tmp_path,
        result_data=baseline_result_data,
        max_replay_streams=4,
    )
    try:
        session_id, _, _ = _seed_replaying(
            app,
            clock=SequenceClockReusable([at_ms(1250)]),
            completed=True,
        )
        a = client.get(
            f"/api/missions/{session_id}/stream",
            headers={"Last-Event-ID": "2"},
        )
        b = client.get(
            f"/api/missions/{session_id}/stream",
            headers={"Last-Event-ID": "2"},
        )
        c = client.get(
            f"/api/missions/{session_id}/stream",
            headers={"Last-Event-ID": "4"},
        )
        assert a.content == b.content
        ids_a = [f["id"] for f in _parse_sse_frames(a.content) if "id" in f]
        ids_c = [f["id"] for f in _parse_sse_frames(c.content) if "id" in f]
        assert ids_a == ["3", "4", "5", "6"]
        assert ids_c == ["5", "6"]
    finally:
        _close_client(client)


def test_completion_race_persists_completed_once(
    tmp_path: Path,
    baseline_result_data: Any,
) -> None:
    client, app, _ = _open_client(
        tmp_path,
        result_data=baseline_result_data,
        max_replay_streams=4,
    )
    try:
        session_id, _, _ = _seed_replaying(
            app,
            clock=SequenceClockReusable([at_ms(1250)]),
        )
        first = client.get(f"/api/missions/{session_id}/stream")
        second = client.get(f"/api/missions/{session_id}/stream")
        assert first.status_code == 200
        assert second.status_code == 200
        assert _parse_sse_frames(first.content)[-1]["event"] == "complete"
        assert _parse_sse_frames(second.content)[-1]["event"] == "complete"
        session = app.state.session_store.read_session(session_id)
        assert session.status == MissionSessionStatus.COMPLETED
    finally:
        _close_client(client)


# --- O/P/Q. Dependency reuse, errors, artifacts ---


def test_routes_reuse_app_state_dependencies(
    tmp_path: Path,
    baseline_result_data: Any,
) -> None:
    client, app, _ = _open_client(tmp_path, result_data=baseline_result_data)
    try:
        session_id, _, _ = _seed_replaying(
            app,
            clock=SequenceClockReusable([REPLAY_START]),
        )
        replay = app.state.telemetry_replay_service
        limiter = app.state.replay_stream_limiter
        client.get(f"/api/missions/{session_id}/telemetry")
        assert app.state.telemetry_replay_service is replay
        assert app.state.replay_stream_limiter is limiter
        assert app.state.session_store is replay._session_store
    finally:
        _close_client(client)


def test_baseline_mismatch_safe_envelope(
    tmp_path: Path,
    baseline_result_data: Any,
) -> None:
    client, app, _ = _open_client(tmp_path, result_data=baseline_result_data)
    try:
        workspace = seed_completed_run(
            app.state.run_store,
            RESULTS_DIR / "baseline_result.json",
        )
        session = make_replaying_session(
            baseline_run_id=workspace.run_id,
            sample_count=99,
        )
        app.state.session_store.create_session(session)
        app.state.telemetry_replay_service._now_provider = SequenceClockReusable(
            [REPLAY_START]
        )
        response = client.get(f"/api/missions/{session.session_id}/telemetry")
        assert response.status_code == 500
        assert response.json()["code"] == ErrorCode.BASELINE_RESULT_MISMATCH.value
        _assert_safe_error(response.json(), tmp_path)
    finally:
        _close_client(client)
