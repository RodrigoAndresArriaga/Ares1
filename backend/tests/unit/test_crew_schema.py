# unit tests for CrewTelemetry against every fixture crew record
from __future__ import annotations

import copy
from typing import Any

import pytest
from app.schemas.crew import CrewTelemetry
from pydantic import ValidationError


def test_every_crew_record_in_all_fixtures(all_result_data: list[Any]) -> None:
    count = 0
    for result in all_result_data:
        for sample in result["telemetry_history"]:
            for crew in sample["crew"]:
                model = CrewTelemetry.model_validate(crew)
                dumped = model.model_dump(mode="json")
                assert dumped == crew
                count += 1
    assert count == (6 * 2) + (43 * 2)


def test_missing_required_vital_fails(baseline_result_data: Any) -> None:
    crew = copy.deepcopy(baseline_result_data["telemetry_history"][0]["crew"][0])
    del crew["spo2_percent"]
    with pytest.raises(ValidationError):
        CrewTelemetry.model_validate(crew)


def test_unknown_crew_field_fails(baseline_result_data: Any) -> None:
    crew = copy.deepcopy(baseline_result_data["telemetry_history"][0]["crew"][0])
    crew["metabolism_fake"] = 1.0
    with pytest.raises(ValidationError):
        CrewTelemetry.model_validate(crew)


def test_empty_alarms_preserved(baseline_result_data: Any) -> None:
    crew = baseline_result_data["telemetry_history"][0]["crew"][0]
    model = CrewTelemetry.model_validate(crew)
    assert model.alarms == []


def test_invalid_activity_rejected(baseline_result_data: Any) -> None:
    crew = copy.deepcopy(baseline_result_data["telemetry_history"][0]["crew"][0])
    crew["activity"] = "JOGGING"
    with pytest.raises(ValidationError):
        CrewTelemetry.model_validate(crew)
