# strict planner action contracts from Action.hpp / JsonIO parseAction
from enum import Enum
from typing import Annotated, Literal, Union

from pydantic import BaseModel, Field, model_validator

from app.schemas.common import CONTRACT_CONFIG, StrictInt


class ActionType(str, Enum):
    REDUCE_POWER_LOAD = "reduce_power_load"
    ISOLATE_MODULE = "isolate_module"
    OXYGEN_RATIONING = "oxygen_rationing"
    REPAIR_SOLAR_ARRAY = "repair_solar_array"
    DELAY_ROVER_USE = "delay_rover_use"
    SEND_EMERGENCY_PACKET = "send_emergency_packet"


class ActionBase(BaseModel):
    model_config = CONTRACT_CONFIG

    start_min: StrictInt
    percent: float | None = None
    module: str | None = None
    level: str | None = None
    duration_min: StrictInt | None = None
    hours: float | None = None
    crew_id: str | None = None
    eva_crew_id: str | None = None
    assigned_crew_ids: list[str] | None = None
    target_crew_ids: list[str] | None = None
    load_groups: list[str] | None = None


class IsolateModuleAction(ActionBase):
    type: Literal[ActionType.ISOLATE_MODULE]
    module: str


class ReducePowerLoadAction(ActionBase):
    type: Literal[ActionType.REDUCE_POWER_LOAD]
    percent: float
    load_groups: list[str]


class OxygenRationingAction(ActionBase):
    type: Literal[ActionType.OXYGEN_RATIONING]
    level: str
    target_crew_ids: list[str]


class RepairSolarArrayAction(ActionBase):
    type: Literal[ActionType.REPAIR_SOLAR_ARRAY]

    @model_validator(mode="after")
    def require_crew_identity(self) -> "RepairSolarArrayAction":
        has_eva = self.eva_crew_id is not None
        has_crew = self.crew_id is not None
        has_assigned = bool(self.assigned_crew_ids)
        if not (has_eva or has_crew or has_assigned):
            raise ValueError(
                "repair_solar_array requires eva_crew_id, crew_id, or assigned_crew_ids"
            )
        return self


class DelayRoverUseAction(ActionBase):
    type: Literal[ActionType.DELAY_ROVER_USE]
    hours: float


class SendEmergencyPacketAction(ActionBase):
    type: Literal[ActionType.SEND_EMERGENCY_PACKET]


RecoveryAction = Annotated[
    Union[
        IsolateModuleAction,
        ReducePowerLoadAction,
        OxygenRationingAction,
        RepairSolarArrayAction,
        DelayRoverUseAction,
        SendEmergencyPacketAction,
    ],
    Field(discriminator="type"),
]
