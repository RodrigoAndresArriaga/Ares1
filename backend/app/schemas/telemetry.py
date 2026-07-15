# per-sample telemetry: habitat, events, active actions
from enum import Enum

from pydantic import BaseModel

from app.schemas.actions import ActionType
from app.schemas.common import CONTRACT_CONFIG, StrictBool, StrictInt
from app.schemas.crew import CrewTelemetry


class MissionStatus(str, Enum):
    NOMINAL = "NOMINAL"
    WARNING = "WARNING"
    CRITICAL = "CRITICAL"
    STABILIZED = "STABILIZED"
    FAILURE = "FAILURE"
    REJECTED = "REJECTED"


class ConstraintSeverity(str, Enum):
    INFO = "INFO"
    WARNING = "WARNING"
    CRITICAL = "CRITICAL"
    FAILURE = "FAILURE"


class ActionExecutionStatus(str, Enum):
    PENDING = "PENDING"
    ACTIVE = "ACTIVE"
    COMPLETE = "COMPLETE"
    FAILED = "FAILED"
    ABORTED = "ABORTED"


class HabitatTelemetry(BaseModel):
    model_config = CONTRACT_CONFIG

    cabin_pressure_kpa: float
    inspired_oxygen_mmhg: float
    co2_one_hour_avg_mmhg: float
    oxygen_hours_remaining: float
    battery_soc_percent: float
    solar_generation_percent: float
    power_margin_kw: float
    cabin_temperature_c: float
    temperature_margin_c: float
    eva_safe_return_margin_min: float
    mission_status: MissionStatus


class TimelineEvent(BaseModel):
    model_config = CONTRACT_CONFIG

    time_min: StrictInt
    event_type: str
    message: str
    severity: ConstraintSeverity


class ActiveActionState(BaseModel):
    model_config = CONTRACT_CONFIG

    action_index: StrictInt
    type: ActionType
    status: ActionExecutionStatus
    actual_start_min: StrictInt | None
    elapsed_min: StrictInt
    progress_fraction: float
    assigned_crew_id: str | None
    eva_crew_id: str | None
    assigned_crew_ids: list[str]
    failure_reason: str


class TelemetrySample(BaseModel):
    model_config = CONTRACT_CONFIG

    simulation_time_min: StrictInt
    habitat: HabitatTelemetry
    crew: list[CrewTelemetry]
    events: list[TimelineEvent]
    active_actions: list[ActiveActionState]
    has_warning: StrictBool
    has_critical: StrictBool
