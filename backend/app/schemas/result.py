# complete SimulationResult and metrics contract
from enum import Enum

from pydantic import BaseModel

from app.schemas.common import CONTRACT_CONFIG, StrictBool
from app.schemas.telemetry import TelemetrySample, TimelineEvent


class OutcomeStatus(str, Enum):
    FAILURE = "FAILURE"
    STABILIZED = "STABILIZED"
    REJECTED = "REJECTED"


class SimulationMetrics(BaseModel):
    model_config = CONTRACT_CONFIG

    minimum_inspired_o2_mmhg: float
    minimum_cabin_pressure_kpa: float
    maximum_co2_one_hour_avg_mmhg: float
    minimum_battery_soc_percent: float
    minimum_power_margin_kw: float
    minimum_temperature_margin_c: float
    minimum_eva_safe_return_margin_min: float
    minimum_crew_spo2_percent: float
    maximum_crew_fatigue_percent: float
    eva_completed: StrictBool
    communications_sent: StrictBool
    time_to_stabilization_hr: float


class SimulationResult(BaseModel):
    model_config = CONTRACT_CONFIG

    scenario_id: str
    plan_id: str
    outcome: OutcomeStatus
    valid_plan: StrictBool
    metrics: SimulationMetrics
    timeline: list[TimelineEvent]
    telemetry_history: list[TelemetrySample]
    failure_reasons: list[str]
