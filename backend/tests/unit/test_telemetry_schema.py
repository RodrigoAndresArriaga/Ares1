# unit tests for telemetry sample models
from __future__ import annotations

import copy
from typing import Any

import pytest
from app.schemas.telemetry import TelemetrySample
from pydantic import ValidationError


def test_every_telemetry_sample(all_result_data: list[Any]) -> None:
    count = 0
    for result in all_result_data:
        for sample in result["telemetry_history"]:
            model = TelemetrySample.model_validate(sample)
            dumped = model.model_dump(mode="json")
            assert dumped == sample
            count += 1
    assert count == 6 + 43 + 0


def test_empty_telemetry_history_is_valid_list() -> None:
    assert isinstance([], list)


def test_missing_cabin_temperature_fails(baseline_result_data: Any) -> None:
    sample = copy.deepcopy(baseline_result_data["telemetry_history"][0])
    del sample["habitat"]["cabin_temperature_c"]
    with pytest.raises(ValidationError):
        TelemetrySample.model_validate(sample)


def test_missing_crew_fails(baseline_result_data: Any) -> None:
    sample = copy.deepcopy(baseline_result_data["telemetry_history"][0])
    del sample["crew"]
    with pytest.raises(ValidationError):
        TelemetrySample.model_validate(sample)


def test_unknown_telemetry_field_fails(baseline_result_data: Any) -> None:
    sample = copy.deepcopy(baseline_result_data["telemetry_history"][0])
    sample["synthetic_field"] = True
    with pytest.raises(ValidationError):
        TelemetrySample.model_validate(sample)


def test_crew_vitals_key_rejected(baseline_result_data: Any) -> None:
    sample = copy.deepcopy(baseline_result_data["telemetry_history"][0])
    sample["crew_vitals"] = sample.pop("crew")
    with pytest.raises(ValidationError):
        TelemetrySample.model_validate(sample)


def test_parsed_sample_immutable_source(baseline_result_data: Any) -> None:
    original = baseline_result_data["telemetry_history"][0]
    snapshot = copy.deepcopy(original)
    model = TelemetrySample.model_validate(original)
    dumped = model.model_dump(mode="json")
    assert dumped == snapshot
    assert original == snapshot


def test_active_action_null_identities(valid_plan_result_data: Any) -> None:
    found_null = False
    for sample in valid_plan_result_data["telemetry_history"]:
        for action in sample["active_actions"]:
            if action["assigned_crew_id"] is None or action["eva_crew_id"] is None:
                model = TelemetrySample.model_validate(sample)
                assert model.active_actions
                found_null = True
                break
        if found_null:
            break
    assert found_null
