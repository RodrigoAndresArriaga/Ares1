# unit tests for RecoveryAction structural contracts
from __future__ import annotations

import copy
from typing import Any

import pytest
from app.schemas.actions import (
    ActionType,
    DelayRoverUseAction,
    IsolateModuleAction,
    OxygenRationingAction,
    RecoveryAction,
    ReducePowerLoadAction,
    RepairSolarArrayAction,
    SendEmergencyPacketAction,
)
from pydantic import TypeAdapter, ValidationError

adapter = TypeAdapter(RecoveryAction)


def test_every_action_type_constructible() -> None:
    cases: list[dict[str, Any]] = [
        {"type": "isolate_module", "start_min": 0, "module": "lab"},
        {
            "type": "reduce_power_load",
            "start_min": 0,
            "percent": 50.0,
            "load_groups": ["discretionary"],
        },
        {
            "type": "oxygen_rationing",
            "start_min": 0,
            "level": "moderate",
            "target_crew_ids": ["crew_01"],
        },
        {"type": "repair_solar_array", "start_min": 1, "eva_crew_id": "crew_01"},
        {"type": "delay_rover_use", "start_min": 10, "hours": 2.0},
        {"type": "send_emergency_packet", "start_min": 2000},
    ]
    for payload in cases:
        model = adapter.validate_python(payload)
        assert model.type in ActionType


def test_sample_plan_actions_round_trip(sample_plan_data: Any) -> None:
    for action in sample_plan_data["actions"]:
        model = adapter.validate_python(action)
        dumped = model.model_dump(mode="json", exclude_unset=True)
        assert dumped == action


def test_invalid_plan_action_accepted(invalid_plan_data: Any) -> None:
    action = invalid_plan_data["actions"][0]
    model = adapter.validate_python(action)
    assert isinstance(model, SendEmergencyPacketAction)
    assert model.start_min == 2000


def test_unknown_action_type_rejected() -> None:
    with pytest.raises(ValidationError):
        adapter.validate_python({"type": "fly_to_orbit", "start_min": 0})


def test_unknown_field_rejected() -> None:
    with pytest.raises(ValidationError):
        adapter.validate_python(
            {"type": "send_emergency_packet", "start_min": 0, "unexpected": True}
        )


def test_missing_type_specific_field_rejected() -> None:
    with pytest.raises(ValidationError):
        adapter.validate_python({"type": "isolate_module", "start_min": 0})
    with pytest.raises(ValidationError):
        adapter.validate_python({"type": "reduce_power_load", "start_min": 0, "percent": 10.0})
    with pytest.raises(ValidationError):
        adapter.validate_python({"type": "repair_solar_array", "start_min": 1})


def test_invalid_field_type_rejected() -> None:
    with pytest.raises(ValidationError):
        adapter.validate_python({"type": "send_emergency_packet", "start_min": 1.5})
    with pytest.raises(ValidationError):
        adapter.validate_python(
            {"type": "isolate_module", "start_min": 0, "module": ["lab"]}
        )


def test_infeasible_packet_still_structurally_valid() -> None:
    # simulator rejects closed comms window; schema must accept
    model = adapter.validate_python({"type": "send_emergency_packet", "start_min": 2000})
    assert model.type == ActionType.SEND_EMERGENCY_PACKET


def test_repair_with_crew_id_identity() -> None:
    model = adapter.validate_python(
        {"type": "repair_solar_array", "start_min": 1, "crew_id": "crew_02"}
    )
    assert isinstance(model, RepairSolarArrayAction)


def test_typed_model_classes() -> None:
    assert IsolateModuleAction.model_validate(
        {"type": "isolate_module", "start_min": 0, "module": "lab"}
    )
    assert ReducePowerLoadAction.model_validate(
        {
            "type": "reduce_power_load",
            "start_min": 0,
            "percent": 10.0,
            "load_groups": [],
        }
    )
    assert OxygenRationingAction.model_validate(
        {
            "type": "oxygen_rationing",
            "start_min": 0,
            "level": "low",
            "target_crew_ids": [],
        }
    )
    assert DelayRoverUseAction.model_validate(
        {"type": "delay_rover_use", "start_min": 0, "hours": 1.0}
    )


def test_mutated_copy_does_not_affect_original(sample_plan_data: Any) -> None:
    original = sample_plan_data["actions"][0]
    mutated = copy.deepcopy(original)
    mutated["module"] = "habitat"
    model = adapter.validate_python(mutated)
    assert model.module == "habitat"
    assert original["module"] == "lab"
