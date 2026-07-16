# Mission lifecycle HTTP route integration tests (Phase 3 Step 6)
from __future__ import annotations

import asyncio
import json
import uuid
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, patch

import httpx
import pytest
from app.core.config import clear_settings_cache
from app.core.errors import MissionSessionStorageError
from app.main import create_app
from app.schemas.api import ErrorCode, SimulationRunResponse
from app.schemas.mission import (
    AccidentTriggerResponse,
    MissionCreateResponse,
    MissionSession,
    MissionSessionStatus,
)
from app.schemas.replay import ReplayStartResponse
from app.schemas.result import SimulationResult
from app.services.mission_lifecycle_service import MissionLifecycleService
from app.services.session_store import SessionStore
from app.services.simulation_service import SimulationService
from fastapi.testclient import TestClient
from tests.conftest import (
    RELEASE_SCENARIO_ID,
    make_fake_simulation_service,
    make_mission_settings,
)

FORBIDDEN_PAYLOAD_KEYS = frozenset(
    {
        "telemetry_history",
        "metrics",
        "timeline",
        "failure_reasons",
        "survival_probability",
    }
)

RUN_ID = "00000000-0000-4000-8000-000000000001"
UNKNOWN_SESSION = "00000000-0000-4000-8000-0000000000aa"


@pytest.fixture(autouse=True)
def _clear_settings_cache() -> Any:
    clear_settings_cache()
    yield
    clear_settings_cache()


def _mission_client(
    tmp_path: Path,
    *,
    result_data: Any | None = None,
    fake_service: Any | None = None,
    raise_server_exceptions: bool = False,
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
    client = TestClient(app, raise_server_exceptions=raise_server_exceptions)
    client.__enter__()
    return client, app, fake_service


def _close_client(client: TestClient) -> None:
    client.__exit__(None, None, None)


def _create_session(client: TestClient) -> dict[str, Any]:
    response = client.post(
        "/api/missions",
        json={"scenario_id": RELEASE_SCENARIO_ID},
    )
    assert response.status_code == 201
    return response.json()


def _assert_safe_error(payload: dict[str, Any], tmp_path: Path) -> None:
    assert "code" in payload
    assert "message" in payload
    encoded = json.dumps(payload)
    assert str(tmp_path) not in encoded
    assert "Traceback" not in encoded
    assert "File \"" not in encoded


# --- A. Lifespan wiring ---


def test_lifespan_wires_session_store_and_lifecycle_once(
    tmp_path: Path,
    baseline_result_data: Any,
) -> None:
    client, app, fake = _mission_client(tmp_path, result_data=baseline_result_data)
    try:
        store = app.state.session_store
        lifecycle = app.state.mission_lifecycle_service
        assert isinstance(store, SessionStore)
        assert isinstance(lifecycle, MissionLifecycleService)
        assert app.state.scenario_registry is lifecycle._scenario_registry
        assert app.state.simulation_service is fake
        assert lifecycle._simulation_service is fake
        assert store._sessions_root == app.state.settings.sessions_dir.resolve()

        _create_session(client)
        _create_session(client)
        assert app.state.session_store is store
        assert app.state.mission_lifecycle_service is lifecycle
    finally:
        _close_client(client)


def test_lifespan_fails_when_session_store_construction_fails(
    tmp_path: Path,
    baseline_result_data: Any,
) -> None:
    settings = make_mission_settings(tmp_path)
    fake = make_fake_simulation_service(baseline_result_data, run_id=RUN_ID)
    app = create_app(
        settings_override=settings,
        simulation_service_override=fake,
    )
    with patch(
        "app.main.SessionStore",
        side_effect=MissionSessionStorageError("Sessions root is missing"),
    ):
        with pytest.raises(MissionSessionStorageError):
            with TestClient(app):
                pass


def test_shutdown_has_no_background_mission_tasks(
    tmp_path: Path,
    baseline_result_data: Any,
) -> None:
    client, app, _ = _mission_client(tmp_path, result_data=baseline_result_data)
    try:
        _create_session(client)
    finally:
        _close_client(client)
    assert not hasattr(app.state, "replay_stream_semaphore")


# --- B. POST /api/missions ---


def test_create_mission_201_ready(
    tmp_path: Path,
    baseline_result_data: Any,
) -> None:
    client, app, fake = _mission_client(tmp_path, result_data=baseline_result_data)
    try:
        response = client.post(
            "/api/missions",
            json={"scenario_id": RELEASE_SCENARIO_ID},
        )
        assert response.status_code == 201
        body = MissionCreateResponse.model_validate(response.json())
        session = body.session
        assert session.status == MissionSessionStatus.READY
        uuid.UUID(session.session_id)
        assert session.session_id == str(uuid.UUID(session.session_id))
        assert session.scenario_id == RELEASE_SCENARIO_ID
        assert session.baseline_run_id is None
        assert session.baseline_outcome is None
        assert session.telemetry_sample_count is None
        assert session.replay_started_at is None
        assert session.replay_interval_ms is None
        encoded = json.dumps(response.json())
        for key in FORBIDDEN_PAYLOAD_KEYS:
            assert key not in encoded
        session_path = (
            app.state.settings.sessions_dir / session.session_id / "session.json"
        )
        assert session_path.is_file()
        fake.run_simulation.assert_not_awaited()
    finally:
        _close_client(client)


def test_create_mission_unknown_scenario(
    tmp_path: Path,
    baseline_result_data: Any,
) -> None:
    client, _, fake = _mission_client(tmp_path, result_data=baseline_result_data)
    try:
        response = client.post(
            "/api/missions",
            json={"scenario_id": "unknown_scenario"},
        )
        assert response.status_code == 404
        payload = response.json()
        assert payload["code"] == ErrorCode.SCENARIO_NOT_FOUND.value
        _assert_safe_error(payload, tmp_path)
        fake.run_simulation.assert_not_awaited()
    finally:
        _close_client(client)


def test_create_mission_unknown_fields_422(
    tmp_path: Path,
    baseline_result_data: Any,
) -> None:
    client, _, _ = _mission_client(tmp_path, result_data=baseline_result_data)
    try:
        response = client.post(
            "/api/missions",
            json={"scenario_id": RELEASE_SCENARIO_ID, "extra": True},
        )
        assert response.status_code == 422
    finally:
        _close_client(client)


def test_create_mission_empty_scenario_id_422(
    tmp_path: Path,
    baseline_result_data: Any,
) -> None:
    client, _, _ = _mission_client(tmp_path, result_data=baseline_result_data)
    try:
        response = client.post("/api/missions", json={"scenario_id": ""})
        assert response.status_code == 422
    finally:
        _close_client(client)


# --- C. GET /api/missions/{session_id} ---


def test_get_mission_exact_persisted(
    tmp_path: Path,
    baseline_result_data: Any,
) -> None:
    client, app, _ = _mission_client(tmp_path, result_data=baseline_result_data)
    try:
        created = _create_session(client)
        session_id = created["session"]["session_id"]
        session_path = (
            app.state.settings.sessions_dir / session_id / "session.json"
        )
        before_bytes = session_path.read_bytes()
        before_updated = created["session"]["updated_at"]

        response = client.get(f"/api/missions/{session_id}")
        assert response.status_code == 200
        body = MissionSession.model_validate(response.json())
        assert body.session_id == session_id
        assert body.status == MissionSessionStatus.READY
        assert body.updated_at.isoformat().replace("+00:00", "Z") in (
            before_updated,
            body.updated_at.isoformat(),
        )
        assert response.json()["updated_at"] == before_updated
        assert session_path.read_bytes() == before_bytes
    finally:
        _close_client(client)


def test_get_mission_unknown_404(
    tmp_path: Path,
    baseline_result_data: Any,
) -> None:
    client, _, _ = _mission_client(tmp_path, result_data=baseline_result_data)
    try:
        response = client.get(f"/api/missions/{UNKNOWN_SESSION}")
        assert response.status_code == 404
        payload = response.json()
        assert payload["code"] == ErrorCode.MISSION_SESSION_NOT_FOUND.value
        _assert_safe_error(payload, tmp_path)
    finally:
        _close_client(client)


def test_get_mission_invalid_id_400(
    tmp_path: Path,
    baseline_result_data: Any,
) -> None:
    client, _, _ = _mission_client(tmp_path, result_data=baseline_result_data)
    try:
        response = client.get("/api/missions/not-a-uuid")
        assert response.status_code == 400
        assert response.json()["code"] == ErrorCode.MISSION_SESSION_ID_INVALID.value
    finally:
        _close_client(client)


# --- D. POST accident ---


@pytest.mark.parametrize(
    "fixture_name",
    [
        "baseline_result_data",
        "valid_plan_result_data",
        "invalid_plan_result_data",
    ],
)
def test_accident_outcomes_http_200(
    tmp_path: Path,
    fixture_name: str,
    request: pytest.FixtureRequest,
    baseline_result_data: Any,
) -> None:
    result_data = dict(request.getfixturevalue(fixture_name))
    # REJECTED release fixture has empty telemetry; seed samples for BASELINE_READY
    if not result_data["telemetry_history"]:
        result_data["telemetry_history"] = baseline_result_data["telemetry_history"]
        result_data["timeline"] = baseline_result_data["timeline"]
        result_data["metrics"] = baseline_result_data["metrics"]
    expected = SimulationResult.model_validate(result_data)
    client, _, fake = _mission_client(tmp_path, result_data=result_data)
    try:
        created = _create_session(client)
        session_id = created["session"]["session_id"]
        response = client.post(f"/api/missions/{session_id}/accident")
        assert response.status_code == 200
        body = AccidentTriggerResponse.model_validate(response.json())
        assert body.session.status == MissionSessionStatus.BASELINE_READY
        assert body.baseline_run_id == RUN_ID
        assert body.baseline_outcome == expected.outcome
        assert body.telemetry_sample_count == len(expected.telemetry_history)
        encoded = json.dumps(response.json())
        assert "telemetry_history" not in encoded
        fake.run_simulation.assert_awaited_once()
    finally:
        _close_client(client)


def test_accident_duplicate_409(
    tmp_path: Path,
    baseline_result_data: Any,
) -> None:
    client, _, fake = _mission_client(tmp_path, result_data=baseline_result_data)
    try:
        created = _create_session(client)
        session_id = created["session"]["session_id"]
        first = client.post(f"/api/missions/{session_id}/accident")
        assert first.status_code == 200
        second = client.post(f"/api/missions/{session_id}/accident")
        assert second.status_code == 409
        payload = second.json()
        assert payload["code"] == ErrorCode.MISSION_STATE_CONFLICT.value
        _assert_safe_error(payload, tmp_path)
        assert fake.run_simulation.await_count == 1
    finally:
        _close_client(client)


@pytest.mark.parametrize(
    "status",
    [
        MissionSessionStatus.ERROR,
        MissionSessionStatus.REPLAYING,
        MissionSessionStatus.COMPLETED,
    ],
)
def test_accident_invalid_status_409(
    tmp_path: Path,
    baseline_result_data: Any,
    status: MissionSessionStatus,
) -> None:
    client, app, _ = _mission_client(tmp_path, result_data=baseline_result_data)
    try:
        created = _create_session(client)
        session_id = created["session"]["session_id"]
        store: SessionStore = app.state.session_store
        session = store.read_session(session_id)

        if status == MissionSessionStatus.ERROR:
            updated = session.model_copy(
                update={
                    "status": status,
                    "error_code": "SIMULATOR_UNAVAILABLE",
                    "accident_triggered_at": session.created_at,
                    "updated_at": session.created_at,
                }
            )
            store.replace_session(
                updated,
                expected_status=MissionSessionStatus.READY,
                expected_updated_at=session.updated_at,
            )
        else:
            accident = client.post(f"/api/missions/{session_id}/accident")
            assert accident.status_code == 200
            replay = client.post(
                f"/api/missions/{session_id}/replay",
                json={},
            )
            assert replay.status_code == 200
            if status == MissionSessionStatus.COMPLETED:
                session = store.read_session(session_id)
                completed = session.model_copy(
                    update={"status": MissionSessionStatus.COMPLETED},
                )
                store.replace_session(
                    completed,
                    expected_status=MissionSessionStatus.REPLAYING,
                    expected_updated_at=session.updated_at,
                )

        response = client.post(f"/api/missions/{session_id}/accident")
        assert response.status_code == 409
        assert response.json()["code"] == ErrorCode.MISSION_STATE_CONFLICT.value
    finally:
        _close_client(client)


def test_accident_unknown_and_invalid_ids(
    tmp_path: Path,
    baseline_result_data: Any,
) -> None:
    client, _, _ = _mission_client(tmp_path, result_data=baseline_result_data)
    try:
        missing = client.post(f"/api/missions/{UNKNOWN_SESSION}/accident")
        assert missing.status_code == 404
        invalid = client.post("/api/missions/not-a-uuid/accident")
        assert invalid.status_code == 400
    finally:
        _close_client(client)


def test_accident_arbitrary_json_body_is_ignored(
    tmp_path: Path,
    baseline_result_data: Any,
) -> None:
    # FastAPI ignores undeclared request bodies for this route by design.
    client, _, fake = _mission_client(tmp_path, result_data=baseline_result_data)
    try:
        created = _create_session(client)
        session_id = created["session"]["session_id"]
        response = client.post(
            f"/api/missions/{session_id}/accident",
            json={"fault": "ignored", "accident_type": "x"},
        )
        assert response.status_code == 200
        fake.run_simulation.assert_awaited_once()
    finally:
        _close_client(client)


# --- E. POST replay ---


def test_replay_start_baseline_ready(
    tmp_path: Path,
    baseline_result_data: Any,
) -> None:
    client, _, fake = _mission_client(tmp_path, result_data=baseline_result_data)
    try:
        created = _create_session(client)
        session_id = created["session"]["session_id"]
        accident = client.post(f"/api/missions/{session_id}/accident")
        assert accident.status_code == 200
        fake.run_simulation.reset_mock()

        response = client.post(f"/api/missions/{session_id}/replay", json={})
        assert response.status_code == 200
        body = ReplayStartResponse.model_validate(response.json())
        assert body.session.status == MissionSessionStatus.REPLAYING
        assert body.session.replay_interval_ms == 250
        assert body.stream_path == f"/api/missions/{session_id}/stream"
        assert body.current_telemetry_path == (
            f"/api/missions/{session_id}/telemetry"
        )
        assert "\\" not in body.stream_path
        assert ":" not in body.stream_path[4:]
        assert body.session.baseline_run_id == RUN_ID
        fake.run_simulation.assert_not_awaited()
    finally:
        _close_client(client)


def test_replay_explicit_interval(
    tmp_path: Path,
    baseline_result_data: Any,
) -> None:
    client, _, _ = _mission_client(tmp_path, result_data=baseline_result_data)
    try:
        created = _create_session(client)
        session_id = created["session"]["session_id"]
        assert client.post(f"/api/missions/{session_id}/accident").status_code == 200
        response = client.post(
            f"/api/missions/{session_id}/replay",
            json={"interval_ms": 100, "restart": False},
        )
        assert response.status_code == 200
        assert response.json()["session"]["replay_interval_ms"] == 100
    finally:
        _close_client(client)


def test_replay_before_baseline_409(
    tmp_path: Path,
    baseline_result_data: Any,
) -> None:
    client, _, fake = _mission_client(tmp_path, result_data=baseline_result_data)
    try:
        created = _create_session(client)
        session_id = created["session"]["session_id"]
        response = client.post(f"/api/missions/{session_id}/replay", json={})
        assert response.status_code == 409
        assert response.json()["code"] == ErrorCode.MISSION_STATE_CONFLICT.value
        fake.run_simulation.assert_not_awaited()
    finally:
        _close_client(client)


def test_replay_while_replaying_409(
    tmp_path: Path,
    baseline_result_data: Any,
) -> None:
    client, _, _ = _mission_client(tmp_path, result_data=baseline_result_data)
    try:
        created = _create_session(client)
        session_id = created["session"]["session_id"]
        assert client.post(f"/api/missions/{session_id}/accident").status_code == 200
        assert (
            client.post(f"/api/missions/{session_id}/replay", json={}).status_code
            == 200
        )
        second = client.post(f"/api/missions/{session_id}/replay", json={})
        assert second.status_code == 409
    finally:
        _close_client(client)


def test_replay_completed_without_restart_409(
    tmp_path: Path,
    baseline_result_data: Any,
) -> None:
    client, app, _ = _mission_client(tmp_path, result_data=baseline_result_data)
    try:
        created = _create_session(client)
        session_id = created["session"]["session_id"]
        assert client.post(f"/api/missions/{session_id}/accident").status_code == 200
        assert (
            client.post(f"/api/missions/{session_id}/replay", json={}).status_code
            == 200
        )
        store: SessionStore = app.state.session_store
        session = store.read_session(session_id)
        completed = session.model_copy(
            update={"status": MissionSessionStatus.COMPLETED},
        )
        store.replace_session(
            completed,
            expected_status=MissionSessionStatus.REPLAYING,
            expected_updated_at=session.updated_at,
        )
        response = client.post(
            f"/api/missions/{session_id}/replay",
            json={"restart": False},
        )
        assert response.status_code == 409
    finally:
        _close_client(client)


def test_replay_completed_with_restart_succeeds(
    tmp_path: Path,
    baseline_result_data: Any,
) -> None:
    client, app, _ = _mission_client(tmp_path, result_data=baseline_result_data)
    try:
        created = _create_session(client)
        session_id = created["session"]["session_id"]
        assert client.post(f"/api/missions/{session_id}/accident").status_code == 200
        assert (
            client.post(f"/api/missions/{session_id}/replay", json={}).status_code
            == 200
        )
        store: SessionStore = app.state.session_store
        session = store.read_session(session_id)
        completed = session.model_copy(
            update={"status": MissionSessionStatus.COMPLETED},
        )
        store.replace_session(
            completed,
            expected_status=MissionSessionStatus.REPLAYING,
            expected_updated_at=session.updated_at,
        )
        response = client.post(
            f"/api/missions/{session_id}/replay",
            json={"restart": True},
        )
        assert response.status_code == 200
        assert response.json()["session"]["status"] == "REPLAYING"
    finally:
        _close_client(client)


def test_replay_interval_below_min_422(
    tmp_path: Path,
    baseline_result_data: Any,
) -> None:
    client, _, _ = _mission_client(tmp_path, result_data=baseline_result_data)
    try:
        created = _create_session(client)
        session_id = created["session"]["session_id"]
        assert client.post(f"/api/missions/{session_id}/accident").status_code == 200
        response = client.post(
            f"/api/missions/{session_id}/replay",
            json={"interval_ms": 10},
        )
        assert response.status_code == 422
        assert response.json()["code"] == ErrorCode.REPLAY_INTERVAL_INVALID.value
    finally:
        _close_client(client)


def test_replay_interval_above_max_422(
    tmp_path: Path,
    baseline_result_data: Any,
) -> None:
    client, _, _ = _mission_client(tmp_path, result_data=baseline_result_data)
    try:
        created = _create_session(client)
        session_id = created["session"]["session_id"]
        assert client.post(f"/api/missions/{session_id}/accident").status_code == 200
        response = client.post(
            f"/api/missions/{session_id}/replay",
            json={"interval_ms": 60001},
        )
        assert response.status_code == 422
        assert response.json()["code"] == ErrorCode.REPLAY_INTERVAL_INVALID.value
    finally:
        _close_client(client)


def test_replay_schema_rejects_nonpositive_and_unknown(
    tmp_path: Path,
    baseline_result_data: Any,
) -> None:
    client, _, _ = _mission_client(tmp_path, result_data=baseline_result_data)
    try:
        created = _create_session(client)
        session_id = created["session"]["session_id"]
        assert client.post(f"/api/missions/{session_id}/accident").status_code == 200
        assert (
            client.post(
                f"/api/missions/{session_id}/replay",
                json={"interval_ms": 0},
            ).status_code
            == 422
        )
        assert (
            client.post(
                f"/api/missions/{session_id}/replay",
                json={"interval_ms": -1},
            ).status_code
            == 422
        )
        assert (
            client.post(
                f"/api/missions/{session_id}/replay",
                json={"unknown": True},
            ).status_code
            == 422
        )
    finally:
        _close_client(client)


def test_replay_invalid_unknown_session_ids(
    tmp_path: Path,
    baseline_result_data: Any,
) -> None:
    client, _, _ = _mission_client(tmp_path, result_data=baseline_result_data)
    try:
        missing = client.post(
            f"/api/missions/{UNKNOWN_SESSION}/replay",
            json={},
        )
        assert missing.status_code == 404
        invalid = client.post("/api/missions/not-a-uuid/replay", json={})
        assert invalid.status_code == 400
    finally:
        _close_client(client)


# --- H. Dependency reuse ---


def test_mission_routes_reuse_app_state_services(
    tmp_path: Path,
    baseline_result_data: Any,
) -> None:
    client, app, fake = _mission_client(tmp_path, result_data=baseline_result_data)
    try:
        lifecycle = app.state.mission_lifecycle_service
        store = app.state.session_store
        first = _create_session(client)
        second = _create_session(client)
        assert first["session"]["session_id"] != second["session"]["session_id"]
        assert app.state.mission_lifecycle_service is lifecycle
        assert app.state.session_store is store
        assert app.state.simulation_service is fake
        assert not isinstance(lifecycle, AsyncMock)
    finally:
        _close_client(client)


# --- I. Concurrent accident ---


@pytest.mark.asyncio
async def test_concurrent_accident_one_wins(
    tmp_path: Path,
    baseline_result_data: Any,
) -> None:
    settings = make_mission_settings(tmp_path)
    started = asyncio.Event()
    release = asyncio.Event()
    call_count = 0

    async def gated_run(_request: Any) -> SimulationRunResponse:
        nonlocal call_count
        call_count += 1
        started.set()
        await release.wait()
        return SimulationRunResponse(
            run_id=RUN_ID,
            duration_ms=25,
            result=SimulationResult.model_validate(baseline_result_data),
        )

    fake = AsyncMock(spec=SimulationService)
    fake.run_simulation = AsyncMock(side_effect=gated_run)
    app = create_app(
        settings_override=settings,
        simulation_service_override=fake,
    )

    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://test",
        ) as http:
            create = await http.post(
                "/api/missions",
                json={"scenario_id": RELEASE_SCENARIO_ID},
            )
            assert create.status_code == 201
            session_id = create.json()["session"]["session_id"]

            task1 = asyncio.create_task(
                http.post(f"/api/missions/{session_id}/accident"),
            )
            await started.wait()
            task2 = asyncio.create_task(
                http.post(f"/api/missions/{session_id}/accident"),
            )
            await asyncio.sleep(0.05)
            release.set()
            results = await asyncio.gather(task1, task2)

        statuses = sorted(r.status_code for r in results)
        assert statuses == [200, 409]
        assert call_count == 1
        session = app.state.session_store.read_session(session_id)
        assert session.status == MissionSessionStatus.BASELINE_READY


@pytest.mark.asyncio
async def test_concurrent_accident_different_sessions(
    tmp_path: Path,
    baseline_result_data: Any,
) -> None:
    settings = make_mission_settings(tmp_path)
    call_count = 0
    lock = asyncio.Lock()

    async def counting_run(_request: Any) -> SimulationRunResponse:
        nonlocal call_count
        async with lock:
            call_count += 1
            run_id = f"00000000-0000-4000-8000-{call_count:012d}"
        return SimulationRunResponse(
            run_id=run_id,
            duration_ms=25,
            result=SimulationResult.model_validate(baseline_result_data),
        )

    fake = AsyncMock(spec=SimulationService)
    fake.run_simulation = AsyncMock(side_effect=counting_run)
    app = create_app(
        settings_override=settings,
        simulation_service_override=fake,
    )

    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://test",
        ) as http:
            ids: list[str] = []
            for _ in range(2):
                create = await http.post(
                    "/api/missions",
                    json={"scenario_id": RELEASE_SCENARIO_ID},
                )
                assert create.status_code == 201
                ids.append(create.json()["session"]["session_id"])

            results = await asyncio.gather(
                http.post(f"/api/missions/{ids[0]}/accident"),
                http.post(f"/api/missions/{ids[1]}/accident"),
            )
        assert [r.status_code for r in results] == [200, 200]
        assert call_count == 2


# --- J. OpenAPI ---


def test_openapi_step6_routes(tmp_path: Path) -> None:
    settings = make_mission_settings(tmp_path)
    app = create_app(settings_override=settings)
    with TestClient(app) as client:
        payload = client.get("/openapi.json").json()
    paths = payload["paths"]
    assert "/api/missions" in paths
    assert "/api/missions/{session_id}" in paths
    assert "/api/missions/{session_id}/accident" in paths
    assert "/api/missions/{session_id}/replay" in paths
    assert "/api/sim/result/{run_id}" in paths
    assert "/api/missions/{session_id}/telemetry" not in paths
    assert "/api/missions/{session_id}/stream" not in paths

    create = paths["/api/missions"]["post"]
    assert "201" in create["responses"]
    accident = paths["/api/missions/{session_id}/accident"]["post"]
    assert "requestBody" not in accident
