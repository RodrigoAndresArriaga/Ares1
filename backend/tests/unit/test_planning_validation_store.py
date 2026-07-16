# PlanningValidationStore: atomic persistence, containment, and strict parse
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import pytest
from app.core.errors import (
    PlanningValidationAlreadyExistsError,
    PlanningValidationConflictError,
    PlanningValidationCorruptError,
    PlanningValidationNotFoundError,
    PlanningValidationStorageError,
)
from app.schemas.planning_validation import (
    PLANNING_VALIDATION_SCHEMA_VERSION,
    PlanningValidationRecord,
    PlanningValidationStatus,
)
from app.services.planning_attempt_store import PlanningAttemptStore
from app.services.planning_validation_store import PlanningValidationStore
from tests.conftest import (
    PLANNING_ATTEMPT_ID,
    make_planning_attempt_store,
    make_planning_root,
    make_planning_validation_store,
)
from tests.unit.test_planning_schema import _attempt

T0 = datetime(2026, 7, 15, 12, 0, 0, tzinfo=timezone.utc)
T1 = datetime(2026, 7, 15, 12, 1, 0, tzinfo=timezone.utc)
RESULT_SHA = "A" * 64


def _try_symlink(link: Path, target: Path) -> bool:
    try:
        link.symlink_to(target)
        return True
    except OSError:
        return False


def _baseline_summary() -> dict[str, object]:
    return {
        "run_id": "00000000-0000-4000-8000-000000000001",
        "result_sha256": RESULT_SHA,
        "scenario_id": "mars_hab_atmosphere_solar_failure",
        "plan_id": "",
        "outcome": "FAILURE",
        "valid_plan": True,
        "failure_reasons": ["critical_repair_impossible"],
        "metrics": {
            "minimum_inspired_o2_mmhg": 1.0,
            "minimum_cabin_pressure_kpa": 2.0,
            "maximum_co2_one_hour_avg_mmhg": 3.0,
            "minimum_battery_soc_percent": 4.0,
            "minimum_power_margin_kw": 5.0,
            "minimum_temperature_margin_c": 6.0,
            "minimum_eva_safe_return_margin_min": 7.0,
            "minimum_crew_spo2_percent": 8.0,
            "maximum_crew_fatigue_percent": 9.0,
            "eva_completed": False,
            "communications_sent": False,
            "time_to_stabilization_hr": 0.0,
        },
        "telemetry_sample_count": 6,
    }


def _simulating_record() -> PlanningValidationRecord:
    return PlanningValidationRecord.model_validate(
        {
            "schema_version": PLANNING_VALIDATION_SCHEMA_VERSION,
            "attempt_id": PLANNING_ATTEMPT_ID,
            "session_id": "00000000-0000-4000-8000-000000000001",
            "scenario_id": "mars_hab_atmosphere_solar_failure",
            "baseline_run_id": "00000000-0000-4000-8000-000000000001",
            "attempt_preflight_sha256": "a" * 64,
            "candidate_plan_sha256": "b" * 64,
            "status": PlanningValidationStatus.SIMULATING.value,
            "started_at": T0,
            "completed_at": None,
            "baseline": _baseline_summary(),
            "candidate": None,
            "comparison": None,
            "error_code": None,
        }
    )


def _seed_attempt(
    tmp_path: Path,
    baseline_result_data: object,
) -> tuple[PlanningAttemptStore, PlanningValidationStore]:
    attempt_store = make_planning_attempt_store(tmp_path)
    validation_store = make_planning_validation_store(tmp_path)
    attempt_store.create_attempt(_attempt(baseline_result_data))
    return attempt_store, validation_store


def test_create_read_simulating(
    tmp_path: Path,
    baseline_result_data: object,
) -> None:
    _, store = _seed_attempt(tmp_path, baseline_result_data)
    record = _simulating_record()
    created = store.create_validation(record)
    read = store.read_validation(PLANNING_ATTEMPT_ID)
    assert created == read == record


def test_replace_with_simulation_complete(
    tmp_path: Path,
    baseline_result_data: object,
) -> None:
    _, store = _seed_attempt(tmp_path, baseline_result_data)
    store.create_validation(_simulating_record())
    candidate = {
        **_baseline_summary(),
        "run_id": "00000000-0000-4000-8000-000000000030",
        "plan_id": "grounded_plan",
        "outcome": "STABILIZED",
        "failure_reasons": [],
    }
    comparison = {
        "baseline_outcome": "FAILURE",
        "candidate_outcome": "STABILIZED",
        "outcome_changed": True,
        "baseline_valid_plan": True,
        "candidate_valid_plan": True,
        "baseline_failure_reasons": ["critical_repair_impossible"],
        "candidate_failure_reasons": [],
        "resolved_failure_reasons": ["critical_repair_impossible"],
        "introduced_failure_reasons": [],
        "baseline_metrics": _baseline_summary()["metrics"],
        "candidate_metrics": candidate["metrics"],
    }
    complete = PlanningValidationRecord.model_validate(
        {
            "schema_version": PLANNING_VALIDATION_SCHEMA_VERSION,
            "attempt_id": PLANNING_ATTEMPT_ID,
            "session_id": "00000000-0000-4000-8000-000000000001",
            "scenario_id": "mars_hab_atmosphere_solar_failure",
            "baseline_run_id": "00000000-0000-4000-8000-000000000001",
            "attempt_preflight_sha256": "a" * 64,
            "candidate_plan_sha256": "b" * 64,
            "status": PlanningValidationStatus.SIMULATION_COMPLETE.value,
            "started_at": T0,
            "completed_at": T1,
            "baseline": _baseline_summary(),
            "candidate": candidate,
            "comparison": comparison,
            "error_code": None,
        }
    )
    replaced = store.replace_validation(
        complete,
        expected_status=PlanningValidationStatus.SIMULATING,
    )
    assert replaced.status == PlanningValidationStatus.SIMULATION_COMPLETE


def test_replace_with_error(
    tmp_path: Path,
    baseline_result_data: object,
) -> None:
    _, store = _seed_attempt(tmp_path, baseline_result_data)
    store.create_validation(_simulating_record())
    error_record = PlanningValidationRecord.model_validate(
        {
            **_simulating_record().model_dump(mode="json"),
            "status": PlanningValidationStatus.ERROR.value,
            "completed_at": T1,
            "error_code": "SIMULATOR_TIMEOUT",
        }
    )
    replaced = store.replace_validation(
        error_record,
        expected_status=PlanningValidationStatus.SIMULATING,
    )
    assert replaced.status == PlanningValidationStatus.ERROR


def test_duplicate_create_rejected(
    tmp_path: Path,
    baseline_result_data: object,
) -> None:
    _, store = _seed_attempt(tmp_path, baseline_result_data)
    store.create_validation(_simulating_record())
    with pytest.raises(PlanningValidationAlreadyExistsError):
        store.create_validation(_simulating_record())


def test_terminal_overwrite_rejected(
    tmp_path: Path,
    baseline_result_data: object,
) -> None:
    _, store = _seed_attempt(tmp_path, baseline_result_data)
    store.create_validation(_simulating_record())
    error_record = PlanningValidationRecord.model_validate(
        {
            **_simulating_record().model_dump(mode="json"),
            "status": PlanningValidationStatus.ERROR.value,
            "completed_at": T1,
            "error_code": "SIMULATOR_TIMEOUT",
        }
    )
    store.replace_validation(error_record, expected_status=PlanningValidationStatus.SIMULATING)
    with pytest.raises(PlanningValidationConflictError):
        store.replace_validation(error_record)


def test_wrong_expected_status_conflict(
    tmp_path: Path,
    baseline_result_data: object,
) -> None:
    _, store = _seed_attempt(tmp_path, baseline_result_data)
    store.create_validation(_simulating_record())
    error_record = PlanningValidationRecord.model_validate(
        {
            **_simulating_record().model_dump(mode="json"),
            "status": PlanningValidationStatus.ERROR.value,
            "completed_at": T1,
            "error_code": "SIMULATOR_TIMEOUT",
        }
    )
    with pytest.raises(PlanningValidationConflictError):
        store.replace_validation(
            error_record,
            expected_status=PlanningValidationStatus.SIMULATION_COMPLETE,
        )


def test_missing_record(tmp_path: Path) -> None:
    store = make_planning_validation_store(tmp_path)
    with pytest.raises(PlanningValidationNotFoundError):
        store.read_validation(PLANNING_ATTEMPT_ID)


def test_missing_attempt_dir(tmp_path: Path) -> None:
    store = make_planning_validation_store(tmp_path)
    with pytest.raises(PlanningValidationNotFoundError):
        store.create_validation(_simulating_record())


def test_malformed_json(
    tmp_path: Path,
    baseline_result_data: object,
) -> None:
    _seed_attempt(tmp_path, baseline_result_data)
    path = tmp_path / "planning" / PLANNING_ATTEMPT_ID / "validation.json"
    path.write_text("{not json", encoding="utf-8")
    store = make_planning_validation_store(tmp_path)
    with pytest.raises(PlanningValidationCorruptError):
        store.read_validation(PLANNING_ATTEMPT_ID)


def test_schema_invalid_json(
    tmp_path: Path,
    baseline_result_data: object,
) -> None:
    _seed_attempt(tmp_path, baseline_result_data)
    path = tmp_path / "planning" / PLANNING_ATTEMPT_ID / "validation.json"
    path.write_text(json.dumps({"status": "SIMULATING"}), encoding="utf-8")
    store = make_planning_validation_store(tmp_path)
    with pytest.raises(PlanningValidationCorruptError):
        store.read_validation(PLANNING_ATTEMPT_ID)


def test_attempt_id_mismatch(
    tmp_path: Path,
    baseline_result_data: object,
) -> None:
    _seed_attempt(tmp_path, baseline_result_data)
    path = tmp_path / "planning" / PLANNING_ATTEMPT_ID / "validation.json"
    payload = _simulating_record().model_dump(mode="json")
    payload["attempt_id"] = "00000000-0000-4000-8000-000000000099"
    path.write_text(json.dumps(payload), encoding="utf-8")
    store = make_planning_validation_store(tmp_path)
    with pytest.raises(PlanningValidationCorruptError):
        store.read_validation(PLANNING_ATTEMPT_ID)


def test_invalid_utf8(
    tmp_path: Path,
    baseline_result_data: object,
) -> None:
    _seed_attempt(tmp_path, baseline_result_data)
    path = tmp_path / "planning" / PLANNING_ATTEMPT_ID / "validation.json"
    path.write_bytes(b"\xff\xfe")
    store = make_planning_validation_store(tmp_path)
    with pytest.raises(PlanningValidationCorruptError):
        store.read_validation(PLANNING_ATTEMPT_ID)


def test_artifact_is_directory(
    tmp_path: Path,
    baseline_result_data: object,
) -> None:
    _seed_attempt(tmp_path, baseline_result_data)
    path = tmp_path / "planning" / PLANNING_ATTEMPT_ID / "validation.json"
    path.mkdir()
    store = make_planning_validation_store(tmp_path)
    with pytest.raises(PlanningValidationCorruptError):
        store.read_validation(PLANNING_ATTEMPT_ID)


def test_atomic_write_failure(
    tmp_path: Path,
    baseline_result_data: object,
) -> None:
    _, store = _seed_attempt(tmp_path, baseline_result_data)
    with patch(
        "app.services.planning_validation_store.write_json_atomic",
        side_effect=OSError("disk full"),
    ):
        with pytest.raises(PlanningValidationStorageError):
            store.create_validation(_simulating_record())


def test_attempt_json_unchanged(
    tmp_path: Path,
    baseline_result_data: object,
) -> None:
    attempt_store, store = _seed_attempt(tmp_path, baseline_result_data)
    before = attempt_store.read_attempt(PLANNING_ATTEMPT_ID)
    store.create_validation(_simulating_record())
    after = attempt_store.read_attempt(PLANNING_ATTEMPT_ID)
    assert before == after


def test_cwd_independence(
    tmp_path: Path,
    baseline_result_data: object,
) -> None:
    root = make_planning_root(tmp_path)
    attempt_store = PlanningAttemptStore(root)
    attempt_store.create_attempt(_attempt(baseline_result_data))
    store = PlanningValidationStore(root)
    store.create_validation(_simulating_record())
    original = os.getcwd()
    try:
        os.chdir(tmp_path)
        read = PlanningValidationStore(root).read_validation(PLANNING_ATTEMPT_ID)
    finally:
        os.chdir(original)
    assert read.status == PlanningValidationStatus.SIMULATING


@pytest.mark.skipif(os.name == "nt", reason="symlink escape requires POSIX")
def test_symlink_escape_rejected(
    tmp_path: Path,
    baseline_result_data: object,
) -> None:
    _seed_attempt(tmp_path, baseline_result_data)
    outside = tmp_path / "outside.json"
    outside.write_text("{}", encoding="utf-8")
    link = tmp_path / "planning" / PLANNING_ATTEMPT_ID / "validation.json"
    if link.exists():
        link.unlink()
    assert _try_symlink(link, outside)
    store = make_planning_validation_store(tmp_path)
    with pytest.raises(PlanningValidationCorruptError):
        store.read_validation(PLANNING_ATTEMPT_ID)
