# Phase 5 Step 3 planning validation schema contract tests
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import pytest
from app.schemas.planning_validation import (
    PLANNING_VALIDATION_SCHEMA_VERSION,
    PlanningResultComparison,
    PlanningResultSummary,
    PlanningValidationRecord,
    PlanningValidationStatus,
    build_planning_result_comparison,
    canonical_plan_sha256,
)
from app.schemas.result import OutcomeStatus, SimulationMetrics
from pydantic import ValidationError
from tests.conftest import make_grounded_recovery_plan

T0 = datetime(2026, 7, 15, 12, 0, 0, tzinfo=timezone.utc)
T1 = datetime(2026, 7, 15, 12, 1, 0, tzinfo=timezone.utc)
RUN_ID = "00000000-0000-4000-8000-000000000001"
CANDIDATE_RUN_ID = "00000000-0000-4000-8000-000000000030"
RESULT_SHA = "A" * 64


def _metrics(**overrides: Any) -> SimulationMetrics:
    payload = {
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
    }
    payload.update(overrides)
    return SimulationMetrics.model_validate(payload)


def _summary(
    *,
    run_id: str = RUN_ID,
    outcome: OutcomeStatus = OutcomeStatus.FAILURE,
    plan_id: str = "",
    failure_reasons: list[str] | None = None,
    metrics: SimulationMetrics | None = None,
    valid_plan: bool = True,
) -> PlanningResultSummary:
    resolved_reasons = (
        ["critical_repair_impossible"]
        if failure_reasons is None
        else list(failure_reasons)
    )
    return PlanningResultSummary(
        run_id=run_id,
        result_sha256=RESULT_SHA,
        scenario_id="mars_hab_atmosphere_solar_failure",
        plan_id=plan_id,
        outcome=outcome,
        valid_plan=valid_plan,
        failure_reasons=resolved_reasons,
        metrics=metrics or _metrics(),
        telemetry_sample_count=6,
    )


def _simulating_record(**overrides: Any) -> PlanningValidationRecord:
    payload = {
        "schema_version": PLANNING_VALIDATION_SCHEMA_VERSION,
        "attempt_id": "00000000-0000-4000-8000-000000000020",
        "session_id": "00000000-0000-4000-8000-000000000001",
        "scenario_id": "mars_hab_atmosphere_solar_failure",
        "baseline_run_id": RUN_ID,
        "attempt_preflight_sha256": "a" * 64,
        "candidate_plan_sha256": "b" * 64,
        "status": PlanningValidationStatus.SIMULATING.value,
        "started_at": T0,
        "completed_at": None,
        "baseline": _summary(),
        "candidate": None,
        "comparison": None,
        "error_code": None,
    }
    payload.update(overrides)
    return PlanningValidationRecord.model_validate(payload)


def test_simulating_valid_state() -> None:
    record = _simulating_record()
    assert record.status == PlanningValidationStatus.SIMULATING
    assert record.completed_at is None


def test_simulation_complete_valid_state() -> None:
    baseline = _summary()
    candidate = _summary(
        run_id=CANDIDATE_RUN_ID,
        outcome=OutcomeStatus.STABILIZED,
        plan_id="grounded_plan",
        failure_reasons=[],
    )
    comparison = build_planning_result_comparison(baseline, candidate)
    record = PlanningValidationRecord.model_validate(
        {
            "schema_version": PLANNING_VALIDATION_SCHEMA_VERSION,
            "attempt_id": "00000000-0000-4000-8000-000000000020",
            "session_id": "00000000-0000-4000-8000-000000000001",
            "scenario_id": "mars_hab_atmosphere_solar_failure",
            "baseline_run_id": RUN_ID,
            "attempt_preflight_sha256": "a" * 64,
            "candidate_plan_sha256": "b" * 64,
            "status": PlanningValidationStatus.SIMULATION_COMPLETE.value,
            "started_at": T0,
            "completed_at": T1,
            "baseline": baseline,
            "candidate": candidate,
            "comparison": comparison,
            "error_code": None,
        }
    )
    assert record.status == PlanningValidationStatus.SIMULATION_COMPLETE


def test_error_valid_state() -> None:
    record = PlanningValidationRecord.model_validate(
        {
            "schema_version": PLANNING_VALIDATION_SCHEMA_VERSION,
            "attempt_id": "00000000-0000-4000-8000-000000000020",
            "session_id": "00000000-0000-4000-8000-000000000001",
            "scenario_id": "mars_hab_atmosphere_solar_failure",
            "baseline_run_id": RUN_ID,
            "attempt_preflight_sha256": "a" * 64,
            "candidate_plan_sha256": "b" * 64,
            "status": PlanningValidationStatus.ERROR.value,
            "started_at": T0,
            "completed_at": T1,
            "baseline": _summary(),
            "candidate": None,
            "comparison": None,
            "error_code": "SIMULATOR_TIMEOUT",
        }
    )
    assert record.error_code == "SIMULATOR_TIMEOUT"


def test_simulating_rejects_completed_at() -> None:
    with pytest.raises(ValidationError):
        _simulating_record(completed_at=T1)


def test_complete_requires_terminal_fields() -> None:
    with pytest.raises(ValidationError):
        _simulating_record(
            status=PlanningValidationStatus.SIMULATION_COMPLETE.value,
            completed_at=T1,
        )


def test_error_requires_error_code() -> None:
    with pytest.raises(ValidationError):
        PlanningValidationRecord.model_validate(
            {
                "schema_version": PLANNING_VALIDATION_SCHEMA_VERSION,
                "attempt_id": "00000000-0000-4000-8000-000000000020",
                "session_id": "00000000-0000-4000-8000-000000000001",
                "scenario_id": "mars_hab_atmosphere_solar_failure",
                "baseline_run_id": RUN_ID,
                "attempt_preflight_sha256": "a" * 64,
                "candidate_plan_sha256": "b" * 64,
                "status": PlanningValidationStatus.ERROR.value,
                "started_at": T0,
                "completed_at": T1,
                "baseline": _summary(),
                "error_code": None,
            }
        )


def test_timestamps_must_be_timezone_aware() -> None:
    with pytest.raises(ValidationError):
        _simulating_record(started_at=datetime(2026, 7, 15, 12, 0, 0))


def test_result_summary_rejects_lowercase_hash() -> None:
    with pytest.raises(ValidationError):
        PlanningResultSummary.model_validate(
            {
                "run_id": RUN_ID,
                "result_sha256": "a" * 64,
                "scenario_id": "mars_hab_atmosphere_solar_failure",
                "plan_id": "",
                "outcome": "FAILURE",
                "valid_plan": True,
                "failure_reasons": [],
                "metrics": _metrics().model_dump(mode="json"),
                "telemetry_sample_count": 6,
            }
        )


def test_empty_baseline_plan_id_preserved() -> None:
    summary = _summary(plan_id="")
    assert summary.plan_id == ""


@pytest.mark.parametrize(
    "outcome",
    [OutcomeStatus.FAILURE, OutcomeStatus.STABILIZED, OutcomeStatus.REJECTED],
)
def test_summary_accepts_simulator_outcomes(outcome: OutcomeStatus) -> None:
    summary = _summary(outcome=outcome)
    assert summary.outcome == outcome


def test_unknown_fields_rejected() -> None:
    with pytest.raises(ValidationError):
        PlanningResultSummary.model_validate(
            {
                "run_id": RUN_ID,
                "result_sha256": RESULT_SHA,
                "scenario_id": "mars_hab_atmosphere_solar_failure",
                "plan_id": "",
                "outcome": "FAILURE",
                "valid_plan": True,
                "failure_reasons": [],
                "metrics": _metrics().model_dump(mode="json"),
                "telemetry_sample_count": 6,
                "survival_probability": 0.5,
            }
        )


def test_forbidden_validation_keys_rejected() -> None:
    with pytest.raises(ValueError, match="forbidden field"):
        PlanningValidationRecord.reject_forbidden_payload_keys(
            {"telemetry_history": []},
        )


def test_comparison_failure_to_stabilized() -> None:
    baseline = _summary(outcome=OutcomeStatus.FAILURE)
    candidate = _summary(
        run_id=CANDIDATE_RUN_ID,
        outcome=OutcomeStatus.STABILIZED,
        plan_id="grounded_plan",
        failure_reasons=[],
    )
    comparison = build_planning_result_comparison(baseline, candidate)
    assert comparison.outcome_changed is True
    assert comparison.resolved_failure_reasons == ["critical_repair_impossible"]
    assert comparison.introduced_failure_reasons == []


def test_comparison_failure_to_rejected() -> None:
    baseline = _summary(outcome=OutcomeStatus.FAILURE)
    candidate = _summary(
        run_id=CANDIDATE_RUN_ID,
        outcome=OutcomeStatus.REJECTED,
        plan_id="grounded_plan",
        failure_reasons=["invalid_plan"],
        valid_plan=False,
    )
    comparison = build_planning_result_comparison(baseline, candidate)
    assert comparison.candidate_outcome == OutcomeStatus.REJECTED
    assert "invalid_plan" in comparison.introduced_failure_reasons


def test_comparison_preserves_reason_ordering() -> None:
    baseline = _summary(failure_reasons=["a", "b", "c"])
    candidate = _summary(
        run_id=CANDIDATE_RUN_ID,
        failure_reasons=["b", "d"],
        plan_id="grounded_plan",
    )
    comparison = build_planning_result_comparison(baseline, candidate)
    assert comparison.resolved_failure_reasons == ["a", "c"]
    assert comparison.introduced_failure_reasons == ["d"]


def test_comparison_repeated_construction_equal() -> None:
    baseline = _summary()
    candidate = _summary(run_id=CANDIDATE_RUN_ID, plan_id="grounded_plan")
    first = build_planning_result_comparison(baseline, candidate)
    second = build_planning_result_comparison(baseline, candidate)
    assert first == second


def test_comparison_no_qualitative_fields() -> None:
    with pytest.raises(ValueError, match="forbidden field"):
        PlanningResultComparison.reject_forbidden_payload_keys({"improved": True})


def test_canonical_plan_hash_deterministic(sample_plan_data: Any) -> None:
    plan = make_grounded_recovery_plan(sample_plan_data)
    first = canonical_plan_sha256(plan)
    second = canonical_plan_sha256(plan)
    assert first == second
    assert len(first) == 64


def test_complete_record_rejects_comparison_mismatch() -> None:
    baseline = _summary()
    candidate = _summary(run_id=CANDIDATE_RUN_ID, plan_id="grounded_plan")
    comparison = build_planning_result_comparison(baseline, candidate)
    bad = comparison.model_copy(update={"outcome_changed": not comparison.outcome_changed})
    with pytest.raises(ValidationError):
        PlanningValidationRecord.model_validate(
            {
                "schema_version": PLANNING_VALIDATION_SCHEMA_VERSION,
                "attempt_id": "00000000-0000-4000-8000-000000000020",
                "session_id": "00000000-0000-4000-8000-000000000001",
                "scenario_id": "mars_hab_atmosphere_solar_failure",
                "baseline_run_id": RUN_ID,
                "attempt_preflight_sha256": "a" * 64,
                "candidate_plan_sha256": "b" * 64,
                "status": PlanningValidationStatus.SIMULATION_COMPLETE.value,
                "started_at": T0,
                "completed_at": T1,
                "baseline": baseline,
                "candidate": candidate,
                "comparison": bad,
                "error_code": None,
            }
        )
