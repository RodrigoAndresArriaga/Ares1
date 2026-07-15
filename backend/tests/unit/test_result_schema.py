# unit tests for SimulationResult
from __future__ import annotations

import copy
from typing import Any

import pytest
from app.schemas.result import OutcomeStatus, SimulationResult
from pydantic import ValidationError


def test_baseline_result(baseline_result_data: Any) -> None:
    model = SimulationResult.model_validate(baseline_result_data)
    assert model.outcome == OutcomeStatus.FAILURE
    assert model.plan_id == ""
    assert model.valid_plan is True
    assert model.model_dump(mode="json") == baseline_result_data


def test_valid_plan_result(valid_plan_result_data: Any) -> None:
    model = SimulationResult.model_validate(valid_plan_result_data)
    assert model.outcome == OutcomeStatus.STABILIZED
    assert model.model_dump(mode="json") == valid_plan_result_data


def test_invalid_plan_result(invalid_plan_result_data: Any) -> None:
    model = SimulationResult.model_validate(invalid_plan_result_data)
    assert model.outcome == OutcomeStatus.REJECTED
    assert model.telemetry_history == []
    assert model.timeline == []
    assert model.failure_reasons
    assert model.model_dump(mode="json") == invalid_plan_result_data


def test_missing_telemetry_history(baseline_result_data: Any) -> None:
    payload = copy.deepcopy(baseline_result_data)
    del payload["telemetry_history"]
    with pytest.raises(ValidationError):
        SimulationResult.model_validate(payload)


def test_missing_timeline(baseline_result_data: Any) -> None:
    payload = copy.deepcopy(baseline_result_data)
    del payload["timeline"]
    with pytest.raises(ValidationError):
        SimulationResult.model_validate(payload)


def test_missing_failure_reasons(baseline_result_data: Any) -> None:
    payload = copy.deepcopy(baseline_result_data)
    del payload["failure_reasons"]
    with pytest.raises(ValidationError):
        SimulationResult.model_validate(payload)


def test_unknown_top_level_field(baseline_result_data: Any) -> None:
    payload = copy.deepcopy(baseline_result_data)
    payload["extra_field"] = 1
    with pytest.raises(ValidationError):
        SimulationResult.model_validate(payload)


def test_invalid_outcome_string(baseline_result_data: Any) -> None:
    payload = copy.deepcopy(baseline_result_data)
    payload["outcome"] = "SUCCESS"
    with pytest.raises(ValidationError):
        SimulationResult.model_validate(payload)


def test_incorrect_plan_id_type(baseline_result_data: Any) -> None:
    payload = copy.deepcopy(baseline_result_data)
    payload["plan_id"] = None
    with pytest.raises(ValidationError):
        SimulationResult.model_validate(payload)


def test_incorrect_valid_plan_type(baseline_result_data: Any) -> None:
    payload = copy.deepcopy(baseline_result_data)
    payload["valid_plan"] = "true"
    with pytest.raises(ValidationError):
        SimulationResult.model_validate(payload)


def test_survival_probability_rejected(baseline_result_data: Any) -> None:
    payload = copy.deepcopy(baseline_result_data)
    payload["survival_probability"] = 0.9
    with pytest.raises(ValidationError):
        SimulationResult.model_validate(payload)


def test_null_replacing_required_empty_array(invalid_plan_result_data: Any) -> None:
    payload = copy.deepcopy(invalid_plan_result_data)
    payload["telemetry_history"] = None
    with pytest.raises(ValidationError):
        SimulationResult.model_validate(payload)


def test_crew_vitals_inside_sample_rejected(valid_plan_result_data: Any) -> None:
    payload = copy.deepcopy(valid_plan_result_data)
    sample = payload["telemetry_history"][0]
    sample["crew_vitals"] = sample.pop("crew")
    with pytest.raises(ValidationError):
        SimulationResult.model_validate(payload)
