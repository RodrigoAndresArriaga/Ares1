# Phase 3 Step 11: restart reconciliation and CWD independence
from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any

import pytest
from app.core.config import clear_settings_cache
from app.main import create_app
from app.schemas.api import ErrorCode
from app.schemas.mission import MissionSession, MissionSessionStatus
from app.schemas.result import SimulationResult
from app.services.session_store import SessionStore
from fastapi.testclient import TestClient
from tests.conftest import (
    RELEASE_SCENARIO_ID,
    RESULTS_DIR,
    make_fake_simulation_service,
    make_mission_settings,
    seed_completed_run,
)
from tests.unit.test_mission_lifecycle_service import (
    SESSION_ID,
    make_baseline_ready_session,
    make_completed_session,
    make_error_session,
    make_ready_session,
    make_replaying_session,
    make_triggering_session,
)
from tests.unit.test_telemetry_replay_service import (
    INTERVAL_MS,
    SequenceClock,
    at_ms,
)

RUN_ID = "00000000-0000-4000-8000-000000000001"


@pytest.fixture(autouse=True)
def _clear_settings_cache() -> Any:
    clear_settings_cache()
    yield
    clear_settings_cache()


class SequenceClockReusable(SequenceClock):
    def __call__(self) -> datetime:
        self.calls += 1
        if self._index >= len(self._times):
            return self._times[-1]
        value = self._times[self._index]
        self._index += 1
        return value


def _assert_safe_error(payload: dict[str, Any], tmp_path: Path) -> None:
    assert "code" in payload
    assert "message" in payload
    encoded = json.dumps(payload)
    assert str(tmp_path) not in encoded
    assert "Traceback" not in encoded
    assert 'File "' not in encoded
    assert "telemetry_history" not in encoded


def _seed_session_on_disk(sessions_dir: Path, session: MissionSession) -> None:
    SessionStore(sessions_dir).create_session(session)


def _write_session(sessions_dir: Path, session: MissionSession) -> Path:
    path = sessions_dir / session.session_id / "session.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(session.model_dump_json(), encoding="utf-8")
    return path


def test_startup_recovers_stale_triggering(
    tmp_path: Path,
    baseline_result_data: Any,
) -> None:
    settings = make_mission_settings(tmp_path)
    _seed_session_on_disk(settings.sessions_dir, make_triggering_session())

    fake = make_fake_simulation_service(baseline_result_data, run_id=RUN_ID)
    app = create_app(settings_override=settings, simulation_service_override=fake)
    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.get(f"/api/missions/{SESSION_ID}")
        assert response.status_code == 200
        body = response.json()
        assert body["status"] == MissionSessionStatus.ERROR.value
        assert body["error_code"] == ErrorCode.MISSION_TRIGGER_INTERRUPTED.value
        assert body["session_id"] == SESSION_ID
        assert body["accident_triggered_at"] is not None
        assert body["baseline_run_id"] is None
        assert str(tmp_path) not in json.dumps(body)

        conflict = client.post(f"/api/missions/{SESSION_ID}/accident")
        assert conflict.status_code == 409
        assert conflict.json()["code"] == ErrorCode.MISSION_STATE_CONFLICT.value
        _assert_safe_error(conflict.json(), tmp_path)

    fake.run_simulation.assert_not_called()


def test_ready_survives_restart(
    tmp_path: Path,
    baseline_result_data: Any,
) -> None:
    settings = make_mission_settings(tmp_path)
    session = make_ready_session()
    path = _write_session(settings.sessions_dir, session)
    before = path.read_bytes()

    fake = make_fake_simulation_service(baseline_result_data, run_id=RUN_ID)
    app = create_app(settings_override=settings, simulation_service_override=fake)
    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.get(f"/api/missions/{SESSION_ID}")
        assert response.status_code == 200
        body = response.json()
        assert body["status"] == MissionSessionStatus.READY.value
        assert body["baseline_run_id"] is None
        assert body["telemetry_sample_count"] is None
        assert "telemetry_history" not in body

    assert path.read_bytes() == before
    fake.run_simulation.assert_not_called()


def test_baseline_ready_survives_restart(
    tmp_path: Path,
    baseline_result_data: Any,
) -> None:
    settings = make_mission_settings(tmp_path)
    fake = make_fake_simulation_service(baseline_result_data, run_id=RUN_ID)
    app = create_app(settings_override=settings, simulation_service_override=fake)
    with TestClient(app, raise_server_exceptions=False):
        workspace = seed_completed_run(
            app.state.run_store,
            RESULTS_DIR / "baseline_result.json",
        )
        result = SimulationResult.model_validate(baseline_result_data)
        session = make_baseline_ready_session(
            sample_count=len(result.telemetry_history),
        ).model_copy(update={"baseline_run_id": workspace.run_id})
        path = _write_session(settings.sessions_dir, session)
        before = path.read_bytes()

    fake2 = make_fake_simulation_service(baseline_result_data, run_id=RUN_ID)
    app2 = create_app(settings_override=settings, simulation_service_override=fake2)
    with TestClient(app2, raise_server_exceptions=False) as client2:
        response = client2.get(f"/api/missions/{SESSION_ID}")
        assert response.status_code == 200
        assert response.json()["status"] == MissionSessionStatus.BASELINE_READY.value
        assert response.json()["baseline_run_id"] == workspace.run_id
        assert path.read_bytes() == before

        start = client2.post(
            f"/api/missions/{SESSION_ID}/replay",
            json={"interval_ms": INTERVAL_MS},
        )
        assert start.status_code == 200
        assert start.json()["session"]["status"] == MissionSessionStatus.REPLAYING.value

    fake2.run_simulation.assert_not_called()


def test_replaying_survives_restart_and_may_complete(
    tmp_path: Path,
    baseline_result_data: Any,
) -> None:
    settings = make_mission_settings(tmp_path)
    fake = make_fake_simulation_service(baseline_result_data, run_id=RUN_ID)
    app = create_app(settings_override=settings, simulation_service_override=fake)
    with TestClient(app, raise_server_exceptions=False):
        workspace = seed_completed_run(
            app.state.run_store,
            RESULTS_DIR / "baseline_result.json",
        )
        result = SimulationResult.model_validate(baseline_result_data)
        session = make_replaying_session().model_copy(
            update={
                "baseline_run_id": workspace.run_id,
                "telemetry_sample_count": len(result.telemetry_history),
            }
        )
        _write_session(settings.sessions_dir, session)
        result_before = (
            settings.runs_dir / workspace.run_id / "result.json"
        ).read_bytes()

    fake2 = make_fake_simulation_service(baseline_result_data, run_id=RUN_ID)
    app2 = create_app(settings_override=settings, simulation_service_override=fake2)
    with TestClient(app2, raise_server_exceptions=False) as client2:
        get_session = client2.get(f"/api/missions/{SESSION_ID}")
        assert get_session.status_code == 200
        assert get_session.json()["status"] == MissionSessionStatus.REPLAYING.value

        app2.state.telemetry_replay_service._now_provider = SequenceClockReusable(
            [at_ms(1250)]
        )
        telemetry = client2.get(f"/api/missions/{SESSION_ID}/telemetry")
        assert telemetry.status_code == 200
        body = telemetry.json()
        assert body["status"] == MissionSessionStatus.COMPLETED.value
        assert body["sample_index"] == len(result.telemetry_history) - 1

        # Last-Event-ID at completion sequence is terminal with empty body
        resume = client2.get(
            f"/api/missions/{SESSION_ID}/stream",
            headers={"Last-Event-ID": str(len(result.telemetry_history))},
        )
        assert resume.status_code == 200
        assert app2.state.replay_stream_limiter.active_count == 0
        session_after = app2.state.session_store.read_session(SESSION_ID)
        assert session_after.status == MissionSessionStatus.COMPLETED

    fake2.run_simulation.assert_not_called()
    assert (
        settings.runs_dir / workspace.run_id / "result.json"
    ).read_bytes() == result_before


def test_completed_survives_restart(
    tmp_path: Path,
    baseline_result_data: Any,
) -> None:
    settings = make_mission_settings(tmp_path)
    fake = make_fake_simulation_service(baseline_result_data, run_id=RUN_ID)
    app = create_app(settings_override=settings, simulation_service_override=fake)
    with TestClient(app, raise_server_exceptions=False):
        workspace = seed_completed_run(
            app.state.run_store,
            RESULTS_DIR / "baseline_result.json",
        )
        result = SimulationResult.model_validate(baseline_result_data)
        session = make_completed_session().model_copy(
            update={
                "baseline_run_id": workspace.run_id,
                "telemetry_sample_count": len(result.telemetry_history),
            }
        )
        path = _write_session(settings.sessions_dir, session)
        before = path.read_bytes()
        result_before = (
            settings.runs_dir / workspace.run_id / "result.json"
        ).read_bytes()

    fake2 = make_fake_simulation_service(baseline_result_data, run_id=RUN_ID)
    app2 = create_app(settings_override=settings, simulation_service_override=fake2)
    with TestClient(app2, raise_server_exceptions=False) as client2:
        response = client2.get(f"/api/missions/{SESSION_ID}")
        assert response.status_code == 200
        assert response.json()["status"] == MissionSessionStatus.COMPLETED.value

        app2.state.telemetry_replay_service._now_provider = SequenceClockReusable(
            [at_ms(1250)]
        )
        telemetry = client2.get(f"/api/missions/{SESSION_ID}/telemetry")
        assert telemetry.status_code == 200
        assert telemetry.json()["status"] == MissionSessionStatus.COMPLETED.value
        assert telemetry.json()["sample_index"] == len(result.telemetry_history) - 1

    assert path.read_bytes() == before
    assert (
        settings.runs_dir / workspace.run_id / "result.json"
    ).read_bytes() == result_before
    fake2.run_simulation.assert_not_called()


def test_error_survives_restart(
    tmp_path: Path,
    baseline_result_data: Any,
) -> None:
    settings = make_mission_settings(tmp_path)
    session = make_error_session(error_code=ErrorCode.SIMULATOR_UNAVAILABLE.value)
    path = _write_session(settings.sessions_dir, session)
    before = path.read_bytes()

    fake = make_fake_simulation_service(baseline_result_data, run_id=RUN_ID)
    app = create_app(settings_override=settings, simulation_service_override=fake)
    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.get(f"/api/missions/{SESSION_ID}")
        assert response.status_code == 200
        assert response.json()["status"] == MissionSessionStatus.ERROR.value
        assert response.json()["error_code"] == ErrorCode.SIMULATOR_UNAVAILABLE.value

        trigger = client.post(f"/api/missions/{SESSION_ID}/accident")
        assert trigger.status_code == 409
        replay = client.post(
            f"/api/missions/{SESSION_ID}/replay",
            json={"interval_ms": INTERVAL_MS},
        )
        assert replay.status_code == 409

    assert path.read_bytes() == before
    fake.run_simulation.assert_not_called()


def test_cwd_independence_with_relative_roots_and_reconcile(
    tmp_path: Path,
    baseline_result_data: Any,
) -> None:
    # settings resolve absolute roots at construction; prove CWD changes are ignored
    settings = make_mission_settings(tmp_path)
    _seed_session_on_disk(settings.sessions_dir, make_triggering_session())
    fake = make_fake_simulation_service(baseline_result_data, run_id=RUN_ID)

    original = Path.cwd()
    other_cwd = tmp_path / "other_cwd"
    other_cwd.mkdir()
    try:
        os.chdir(other_cwd)
        before_other = {p.relative_to(other_cwd) for p in other_cwd.rglob("*")}

        app = create_app(
            settings_override=settings,
            simulation_service_override=fake,
        )
        with TestClient(app, raise_server_exceptions=False) as client:
            response = client.get(f"/api/missions/{SESSION_ID}")
            assert response.status_code == 200
            assert response.json()["status"] == MissionSessionStatus.ERROR.value
            assert (
                response.json()["error_code"]
                == ErrorCode.MISSION_TRIGGER_INTERRUPTED.value
            )

            created = client.post(
                "/api/missions",
                json={"scenario_id": RELEASE_SCENARIO_ID},
            )
            assert created.status_code == 201
            new_id = created.json()["session"]["session_id"]
            assert (settings.sessions_dir / new_id / "session.json").is_file()

        after_other = {p.relative_to(other_cwd) for p in other_cwd.rglob("*")}
        assert after_other == before_other
        fake.run_simulation.assert_not_called()
        assert (settings.sessions_dir / SESSION_ID / "session.json").is_file()
    finally:
        os.chdir(original)
