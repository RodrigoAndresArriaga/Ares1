# crew telemetry as emitted under telemetry_history[].crew
from enum import Enum

from pydantic import BaseModel

from app.schemas.common import CONTRACT_CONFIG


class CrewActivity(str, Enum):
    SLEEP = "SLEEP"
    RESTING = "RESTING"
    NOMINAL_WORK = "NOMINAL_WORK"
    HIGH_WORKLOAD = "HIGH_WORKLOAD"
    EVA_PREP = "EVA_PREP"
    EVA_TRANSIT = "EVA_TRANSIT"
    EVA_WORK = "EVA_WORK"
    RECOVERY = "RECOVERY"
    INCAPACITATED = "INCAPACITATED"


class CrewHealthStatus(str, Enum):
    NOMINAL = "NOMINAL"
    ELEVATED_STRESS = "ELEVATED_STRESS"
    IMPAIRED = "IMPAIRED"
    CRITICAL = "CRITICAL"
    INCAPACITATED = "INCAPACITATED"


class CrewAlarmType(str, Enum):
    HYPOXIA = "HYPOXIA"
    HYPERCAPNIA = "HYPERCAPNIA"
    PRESSURE = "PRESSURE"
    TACHYCARDIA = "TACHYCARDIA"
    RESPIRATORY = "RESPIRATORY"
    THERMAL = "THERMAL"
    FATIGUE = "FATIGUE"
    PERFORMANCE = "PERFORMANCE"
    EVA_RETURN = "EVA_RETURN"


class CrewTelemetry(BaseModel):
    model_config = CONTRACT_CONFIG

    crew_id: str
    display_name: str
    activity: CrewActivity
    heart_rate_bpm: float
    respiratory_rate_bpm: float
    spo2_percent: float
    core_temperature_c: float
    fatigue_percent: float
    cognitive_performance_percent: float
    physical_performance_percent: float
    health_status: CrewHealthStatus
    alarms: list[CrewAlarmType]
