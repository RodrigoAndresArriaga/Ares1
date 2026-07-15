# unit tests for replay request/response and SSE event schemas
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

import pytest
from app.schemas.mission import MissionSession, MissionSessionStatus
from app.schemas.replay import (
    CurrentTelemetryResponse,
    ReplayCompleteEvent,
    ReplayStartRequest,
    ReplayStartResponse,
    ReplayTelemetryEvent,
)
from app.schemas.result import OutcomeStatus
from app.schemas.telemetry import TelemetrySample
from pydantic import ValidationError

SESSION_ID = "00000000-0000-4000-8000-000000000001"
RUN_ID = "00000000-0000-4000-8000-000000000002"
SCENARIO_ID = "mars_hab_atmosphere_solar_failure"

T0 = datetime(2026, 7, 15, 12, 0, 0, tzinfo=timezone.utc)
T1 = T0 + timedelta(seconds=1)
T2 = T0 + timedelta(seconds=2)


# build a REPLAYING MissionSession for response tests
def _replaying_session() -> MissionSession:
    return MissionSession.model_validate(
        {
            "session_id": SESSION_ID,
            "scenario_id": SCENARIO_ID,
            "status": MissionSessionStatus.REPLAYING.value,
            "created_at": T0,
            "updated_at": T2,
            "accident_triggered_at": T1,
            "baseline_run_id": RUN_ID,
            "baseline_outcome": OutcomeStatus.FAILURE.value,
            "telemetry_sample_count": 6,
            "replay_started_at": T2,
            "replay_interval_ms": 250,
            "error_code": None,
        }
    )


def test_replay_start_request_omitted_interval() -> None:
    req = ReplayStartRequest.model_validate({})
    assert req.interval_ms is None
    assert req.restart is False


def test_replay_start_request_explicit_interval() -> None:
    req = ReplayStartRequest.model_validate({"interval_ms": 100, "restart": True})
    assert req.interval_ms == 100
    assert req.restart is True


@pytest.mark.parametrize("interval", [0, -1, -250])
def test_replay_start_request_rejects_nonpositive_interval(interval: int) -> None:
    with pytest.raises(ValidationError):
        ReplayStartRequest.model_validate({"interval_ms": interval})


def test_valid_replay_start_response() -> None:
    session = _replaying_session()
    response = ReplayStartResponse(
        session=session,
        stream_path=f"/api/missions/{SESSION_ID}/stream",
        current_telemetry_path=f"/api/missions/{SESSION_ID}/telemetry",
    )
    assert response.stream_path.endswith("/stream")


def test_replay_start_response_rejects_filesystem_paths() -> None:
    session = _replaying_session()
    with pytest.raises(ValidationError):
        ReplayStartResponse(
            session=session,
            stream_path=r"C:\api\missions\stream",
            current_telemetry_path=f"/api/missions/{SESSION_ID}/telemetry",
        )


def test_replay_start_response_rejects_parent_relative_paths() -> None:
    session = _replaying_session()
    with pytest.raises(ValidationError):
        ReplayStartResponse(
            session=session,
            stream_path=f"/api/missions/{SESSION_ID}/../stream",
            current_telemetry_path=f"/api/missions/{SESSION_ID}/telemetry",
        )


def test_replay_start_response_rejects_wrong_session_id_in_paths() -> None:
    session = _replaying_session()
    other = "00000000-0000-4000-8000-000000000099"
    with pytest.raises(ValidationError):
        ReplayStartResponse(
            session=session,
            stream_path=f"/api/missions/{other}/stream",
            current_telemetry_path=f"/api/missions/{SESSION_ID}/telemetry",
        )


def test_valid_current_telemetry_response(baseline_result_data: Any) -> None:
    sample = TelemetrySample.model_validate(
        baseline_result_data["telemetry_history"][0]
    )
    response = CurrentTelemetryResponse(
        session_id=SESSION_ID,
        status=MissionSessionStatus.REPLAYING,
        sample_index=0,
        sample_count=6,
        telemetry=sample,
        baseline_run_id=RUN_ID,
    )
    assert response.telemetry.simulation_time_min == sample.simulation_time_min


def test_current_telemetry_rejects_invalid_index(baseline_result_data: Any) -> None:
    sample = TelemetrySample.model_validate(
        baseline_result_data["telemetry_history"][0]
    )
    with pytest.raises(ValidationError):
        CurrentTelemetryResponse(
            session_id=SESSION_ID,
            status=MissionSessionStatus.REPLAYING,
            sample_index=6,
            sample_count=6,
            telemetry=sample,
            baseline_run_id=RUN_ID,
        )


def test_current_telemetry_rejects_invalid_status(baseline_result_data: Any) -> None:
    sample = TelemetrySample.model_validate(
        baseline_result_data["telemetry_history"][0]
    )
    with pytest.raises(ValidationError):
        CurrentTelemetryResponse(
            session_id=SESSION_ID,
            status=MissionSessionStatus.READY,
            sample_index=0,
            sample_count=6,
            telemetry=sample,
            baseline_run_id=RUN_ID,
        )


def test_valid_replay_telemetry_event(baseline_result_data: Any) -> None:
    sample = TelemetrySample.model_validate(
        baseline_result_data["telemetry_history"][0]
    )
    event = ReplayTelemetryEvent(
        session_id=SESSION_ID,
        sequence=0,
        sample_index=0,
        sample_count=6,
        telemetry=sample,
    )
    assert event.sequence == event.sample_index


def test_replay_telemetry_rejects_sequence_index_mismatch(
    baseline_result_data: Any,
) -> None:
    sample = TelemetrySample.model_validate(
        baseline_result_data["telemetry_history"][0]
    )
    with pytest.raises(ValidationError):
        ReplayTelemetryEvent(
            session_id=SESSION_ID,
            sequence=1,
            sample_index=0,
            sample_count=6,
            telemetry=sample,
        )


def test_valid_replay_complete_event(baseline_result_data: Any) -> None:
    event = ReplayCompleteEvent.model_validate(
        {
            "session_id": SESSION_ID,
            "sequence": 5,
            "baseline_run_id": RUN_ID,
            "outcome": baseline_result_data["outcome"],
            "valid_plan": baseline_result_data["valid_plan"],
            "failure_reasons": baseline_result_data["failure_reasons"],
            "metrics": baseline_result_data["metrics"],
        }
    )
    assert event.outcome == OutcomeStatus.FAILURE
    assert event.failure_reasons == ["critical_repair_impossible"]


def test_replay_complete_rejects_survival_probability(
    baseline_result_data: Any,
) -> None:
    payload = {
        "session_id": SESSION_ID,
        "sequence": 5,
        "baseline_run_id": RUN_ID,
        "outcome": baseline_result_data["outcome"],
        "valid_plan": baseline_result_data["valid_plan"],
        "failure_reasons": baseline_result_data["failure_reasons"],
        "metrics": baseline_result_data["metrics"],
        "survival_probability": 0.42,
    }
    with pytest.raises(ValidationError):
        ReplayCompleteEvent.model_validate(payload)


def test_replay_complete_rejects_unknown_fields(baseline_result_data: Any) -> None:
    payload = {
        "session_id": SESSION_ID,
        "sequence": 5,
        "baseline_run_id": RUN_ID,
        "outcome": baseline_result_data["outcome"],
        "valid_plan": baseline_result_data["valid_plan"],
        "failure_reasons": baseline_result_data["failure_reasons"],
        "metrics": baseline_result_data["metrics"],
        "derived_risk": 1,
    }
    with pytest.raises(ValidationError):
        ReplayCompleteEvent.model_validate(payload)


def test_replay_start_request_rejects_extra_fields() -> None:
    with pytest.raises(ValidationError):
        ReplayStartRequest.model_validate({"interval_ms": 100, "speed": 2})
