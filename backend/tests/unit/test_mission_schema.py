# unit tests for mission lifecycle schemas
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta, timezone
from typing import Any

import pytest
from app.schemas.mission import (
    AccidentTriggerResponse,
    MissionCreateRequest,
    MissionCreateResponse,
    MissionSession,
    MissionSessionStatus,
)
from app.schemas.result import OutcomeStatus
from pydantic import ValidationError

SESSION_ID = "00000000-0000-4000-8000-000000000001"
RUN_ID = "00000000-0000-4000-8000-000000000002"
SCENARIO_ID = "mars_hab_atmosphere_solar_failure"

T0 = datetime(2026, 7, 15, 12, 0, 0, tzinfo=timezone.utc)
T1 = T0 + timedelta(seconds=1)
T2 = T0 + timedelta(seconds=2)
T3 = T0 + timedelta(seconds=3)


# build a MissionSession payload for a given lifecycle status
def _base_payload(status: MissionSessionStatus) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "session_id": SESSION_ID,
        "scenario_id": SCENARIO_ID,
        "status": status.value,
        "created_at": T0,
        "updated_at": T1,
        "accident_triggered_at": None,
        "baseline_run_id": None,
        "baseline_outcome": None,
        "telemetry_sample_count": None,
        "replay_started_at": None,
        "replay_interval_ms": None,
        "error_code": None,
    }
    if status == MissionSessionStatus.TRIGGERING:
        payload["accident_triggered_at"] = T1
        payload["updated_at"] = T1
    elif status == MissionSessionStatus.BASELINE_READY:
        payload["accident_triggered_at"] = T1
        payload["baseline_run_id"] = RUN_ID
        payload["baseline_outcome"] = OutcomeStatus.FAILURE.value
        payload["telemetry_sample_count"] = 6
        payload["updated_at"] = T2
    elif status == MissionSessionStatus.REPLAYING:
        payload["accident_triggered_at"] = T1
        payload["baseline_run_id"] = RUN_ID
        payload["baseline_outcome"] = OutcomeStatus.FAILURE.value
        payload["telemetry_sample_count"] = 6
        payload["replay_started_at"] = T2
        payload["replay_interval_ms"] = 250
        payload["updated_at"] = T2
    elif status == MissionSessionStatus.COMPLETED:
        payload["accident_triggered_at"] = T1
        payload["baseline_run_id"] = RUN_ID
        payload["baseline_outcome"] = OutcomeStatus.FAILURE.value
        payload["telemetry_sample_count"] = 6
        payload["replay_started_at"] = T2
        payload["replay_interval_ms"] = 250
        payload["updated_at"] = T3
    elif status == MissionSessionStatus.ERROR:
        payload["error_code"] = "SIMULATOR_UNAVAILABLE"
        payload["updated_at"] = T1
    return payload


def test_valid_ready() -> None:
    session = MissionSession.model_validate(_base_payload(MissionSessionStatus.READY))
    assert session.status == MissionSessionStatus.READY
    assert session.baseline_run_id is None
    assert session.telemetry_sample_count is None


def test_valid_triggering() -> None:
    session = MissionSession.model_validate(
        _base_payload(MissionSessionStatus.TRIGGERING)
    )
    assert session.status == MissionSessionStatus.TRIGGERING
    assert session.accident_triggered_at == T1


def test_valid_baseline_ready_failure() -> None:
    session = MissionSession.model_validate(
        _base_payload(MissionSessionStatus.BASELINE_READY)
    )
    assert session.baseline_outcome == OutcomeStatus.FAILURE
    assert session.telemetry_sample_count == 6


def test_valid_baseline_ready_other_outcome() -> None:
    payload = _base_payload(MissionSessionStatus.BASELINE_READY)
    payload["baseline_outcome"] = OutcomeStatus.STABILIZED.value
    session = MissionSession.model_validate(payload)
    assert session.baseline_outcome == OutcomeStatus.STABILIZED


def test_valid_replaying() -> None:
    session = MissionSession.model_validate(
        _base_payload(MissionSessionStatus.REPLAYING)
    )
    assert session.replay_interval_ms == 250
    assert session.replay_started_at == T2


def test_valid_completed() -> None:
    session = MissionSession.model_validate(
        _base_payload(MissionSessionStatus.COMPLETED)
    )
    assert session.status == MissionSessionStatus.COMPLETED


def test_valid_error_before_baseline() -> None:
    session = MissionSession.model_validate(_base_payload(MissionSessionStatus.ERROR))
    assert session.error_code == "SIMULATOR_UNAVAILABLE"
    assert session.baseline_run_id is None


def test_valid_error_preserving_baseline() -> None:
    payload = _base_payload(MissionSessionStatus.BASELINE_READY)
    payload["status"] = MissionSessionStatus.ERROR.value
    payload["error_code"] = "ARTIFACT_STORAGE_ERROR"
    session = MissionSession.model_validate(payload)
    assert session.baseline_run_id == RUN_ID
    assert session.baseline_outcome == OutcomeStatus.FAILURE
    assert session.telemetry_sample_count == 6
    assert session.error_code == "ARTIFACT_STORAGE_ERROR"


def test_rejects_extra_fields() -> None:
    payload = _base_payload(MissionSessionStatus.READY)
    payload["survival_probability"] = 0.9
    with pytest.raises(ValidationError):
        MissionSession.model_validate(payload)


def test_rejects_invalid_uuid_strings() -> None:
    payload = _base_payload(MissionSessionStatus.READY)
    payload["session_id"] = "not-a-uuid"
    with pytest.raises(ValidationError):
        MissionSession.model_validate(payload)

    payload = _base_payload(MissionSessionStatus.BASELINE_READY)
    payload["baseline_run_id"] = "ABCDEF00-0000-4000-8000-000000000002"
    with pytest.raises(ValidationError):
        MissionSession.model_validate(payload)


def test_rejects_naive_datetimes() -> None:
    payload = _base_payload(MissionSessionStatus.READY)
    payload["created_at"] = datetime(2026, 7, 15, 12, 0, 0)
    with pytest.raises(ValidationError):
        MissionSession.model_validate(payload)


def test_rejects_updated_at_before_created_at() -> None:
    payload = _base_payload(MissionSessionStatus.READY)
    payload["updated_at"] = T0 - timedelta(seconds=1)
    with pytest.raises(ValidationError):
        MissionSession.model_validate(payload)


def test_rejects_replay_before_accident() -> None:
    payload = _base_payload(MissionSessionStatus.REPLAYING)
    payload["replay_started_at"] = T0
    payload["accident_triggered_at"] = T1
    with pytest.raises(ValidationError):
        MissionSession.model_validate(payload)


def test_ready_rejects_baseline_data() -> None:
    payload = _base_payload(MissionSessionStatus.READY)
    payload["baseline_run_id"] = RUN_ID
    with pytest.raises(ValidationError):
        MissionSession.model_validate(payload)

    payload = _base_payload(MissionSessionStatus.READY)
    payload["telemetry_sample_count"] = 6
    with pytest.raises(ValidationError):
        MissionSession.model_validate(payload)


def test_baseline_ready_requires_run_id() -> None:
    payload = _base_payload(MissionSessionStatus.BASELINE_READY)
    payload["baseline_run_id"] = None
    with pytest.raises(ValidationError):
        MissionSession.model_validate(payload)


def test_baseline_ready_rejects_zero_sample_count() -> None:
    payload = _base_payload(MissionSessionStatus.BASELINE_READY)
    payload["telemetry_sample_count"] = 0
    with pytest.raises(ValidationError):
        MissionSession.model_validate(payload)


def test_replaying_requires_replay_start() -> None:
    payload = _base_payload(MissionSessionStatus.REPLAYING)
    payload["replay_started_at"] = None
    with pytest.raises(ValidationError):
        MissionSession.model_validate(payload)


def test_replaying_requires_interval() -> None:
    payload = _base_payload(MissionSessionStatus.REPLAYING)
    payload["replay_interval_ms"] = None
    with pytest.raises(ValidationError):
        MissionSession.model_validate(payload)


def test_error_requires_error_code() -> None:
    payload = _base_payload(MissionSessionStatus.ERROR)
    payload["error_code"] = None
    with pytest.raises(ValidationError):
        MissionSession.model_validate(payload)

    payload = _base_payload(MissionSessionStatus.ERROR)
    payload["error_code"] = "   "
    with pytest.raises(ValidationError):
        MissionSession.model_validate(payload)


def test_mission_create_request_accepts_scenario_id() -> None:
    req = MissionCreateRequest.model_validate({"scenario_id": SCENARIO_ID})
    assert req.scenario_id == SCENARIO_ID


def test_mission_create_request_rejects_empty_whitespace() -> None:
    for value in ("", "   ", "\t"):
        with pytest.raises(ValidationError):
            MissionCreateRequest.model_validate({"scenario_id": value})


def test_mission_create_request_rejects_paths() -> None:
    for value in (
        "../scenarios/x",
        "scenarios/x.json",
        r"C:\scenarios\x",
        "/tmp/scenario",
    ):
        with pytest.raises(ValidationError):
            MissionCreateRequest.model_validate({"scenario_id": value})


def test_mission_create_request_rejects_unknown_fields() -> None:
    with pytest.raises(ValidationError):
        MissionCreateRequest.model_validate(
            {"scenario_id": SCENARIO_ID, "plan": None}
        )


def test_mission_create_response() -> None:
    session = MissionSession.model_validate(_base_payload(MissionSessionStatus.READY))
    response = MissionCreateResponse(session=session)
    assert response.session.status == MissionSessionStatus.READY


def test_accident_trigger_response_consistency() -> None:
    session = MissionSession.model_validate(
        _base_payload(MissionSessionStatus.BASELINE_READY)
    )
    response = AccidentTriggerResponse(
        session=session,
        baseline_run_id=RUN_ID,
        baseline_outcome=OutcomeStatus.FAILURE,
        telemetry_sample_count=6,
    )
    assert response.baseline_run_id == session.baseline_run_id


def test_accident_trigger_response_rejects_mismatched_fields() -> None:
    session = MissionSession.model_validate(
        _base_payload(MissionSessionStatus.BASELINE_READY)
    )
    with pytest.raises(ValidationError):
        AccidentTriggerResponse(
            session=session,
            baseline_run_id="00000000-0000-4000-8000-000000000099",
            baseline_outcome=OutcomeStatus.FAILURE,
            telemetry_sample_count=6,
        )


def test_accident_trigger_response_rejects_non_baseline_status() -> None:
    session = MissionSession.model_validate(
        _base_payload(MissionSessionStatus.REPLAYING)
    )
    with pytest.raises(ValidationError):
        AccidentTriggerResponse(
            session=session,
            baseline_run_id=RUN_ID,
            baseline_outcome=OutcomeStatus.FAILURE,
            telemetry_sample_count=6,
        )


def test_accident_trigger_response_rejects_outcome_mismatch() -> None:
    session = MissionSession.model_validate(
        _base_payload(MissionSessionStatus.BASELINE_READY)
    )
    with pytest.raises(ValidationError):
        AccidentTriggerResponse(
            session=session,
            baseline_run_id=RUN_ID,
            baseline_outcome=OutcomeStatus.STABILIZED,
            telemetry_sample_count=6,
        )


def test_accident_trigger_response_rejects_sample_count_mismatch() -> None:
    session = MissionSession.model_validate(
        _base_payload(MissionSessionStatus.BASELINE_READY)
    )
    with pytest.raises(ValidationError):
        AccidentTriggerResponse(
            session=session,
            baseline_run_id=RUN_ID,
            baseline_outcome=OutcomeStatus.FAILURE,
            telemetry_sample_count=99,
        )


def test_payload_roundtrip_ready() -> None:
    payload = _base_payload(MissionSessionStatus.READY)
    session = MissionSession.model_validate(payload)
    dumped = session.model_dump(mode="json")
    again = MissionSession.model_validate(dumped)
    assert again.status == MissionSessionStatus.READY
    assert deepcopy(dumped)["session_id"] == SESSION_ID
