# unit tests for RecoveryPlan
from __future__ import annotations

import copy
from typing import Any

import pytest
from app.schemas.plan import RecoveryPlan
from pydantic import ValidationError


def _round_trip(data: Any) -> None:
    model = RecoveryPlan.model_validate(data)
    dumped = model.model_dump(mode="json", exclude_unset=True)
    assert dumped == data


def test_sample_plan_round_trip(sample_plan_data: Any) -> None:
    _round_trip(sample_plan_data)


def test_invalid_plan_round_trip(invalid_plan_data: Any) -> None:
    _round_trip(invalid_plan_data)


def test_invalid_plan_must_validate(invalid_plan_data: Any) -> None:
    plan = RecoveryPlan.model_validate(invalid_plan_data)
    assert plan.plan_id == "invalid_plan"
    assert plan.actions[0].type.value == "send_emergency_packet"


def test_simulator_owned_fields_forbidden(sample_plan_data: Any) -> None:
    for forbidden in (
        "outcome",
        "valid_plan",
        "metrics",
        "timeline",
        "telemetry_history",
        "failure_reasons",
        "mission_status",
        "survival_probability",
        "success",
        "stabilized",
        "physically_feasible",
    ):
        payload = copy.deepcopy(sample_plan_data)
        payload[forbidden] = True
        with pytest.raises(ValidationError):
            RecoveryPlan.model_validate(payload)


def test_missing_required_plan_field(sample_plan_data: Any) -> None:
    payload = copy.deepcopy(sample_plan_data)
    del payload["rationale"]
    with pytest.raises(ValidationError):
        RecoveryPlan.model_validate(payload)


def test_empty_constraints_checked_allowed(sample_plan_data: Any) -> None:
    payload = copy.deepcopy(sample_plan_data)
    payload["constraints_checked"] = []
    plan = RecoveryPlan.model_validate(payload)
    assert plan.constraints_checked == []
