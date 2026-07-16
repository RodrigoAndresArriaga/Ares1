# HTTP request/response envelopes (no routes)
from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.common import StrictInt
from app.schemas.plan import RecoveryPlan
from app.schemas.result import SimulationResult


class ErrorCode(str, Enum):
    SCENARIO_NOT_FOUND = "SCENARIO_NOT_FOUND"
    SIMULATOR_UNAVAILABLE = "SIMULATOR_UNAVAILABLE"
    SIMULATOR_TIMEOUT = "SIMULATOR_TIMEOUT"
    SIMULATOR_EXECUTION_FAILED = "SIMULATOR_EXECUTION_FAILED"
    SIMULATOR_OUTPUT_MISSING = "SIMULATOR_OUTPUT_MISSING"
    SIMULATOR_OUTPUT_INVALID_JSON = "SIMULATOR_OUTPUT_INVALID_JSON"
    SIMULATOR_OUTPUT_CONTRACT_ERROR = "SIMULATOR_OUTPUT_CONTRACT_ERROR"
    ARTIFACT_STORAGE_ERROR = "ARTIFACT_STORAGE_ERROR"
    MISSION_SESSION_NOT_FOUND = "MISSION_SESSION_NOT_FOUND"
    MISSION_SESSION_ALREADY_EXISTS = "MISSION_SESSION_ALREADY_EXISTS"
    MISSION_SESSION_CORRUPT = "MISSION_SESSION_CORRUPT"
    MISSION_SESSION_STORAGE_ERROR = "MISSION_SESSION_STORAGE_ERROR"
    MISSION_STATE_CONFLICT = "MISSION_STATE_CONFLICT"
    MISSION_SESSION_ID_INVALID = "MISSION_SESSION_ID_INVALID"
    BASELINE_TELEMETRY_EMPTY = "BASELINE_TELEMETRY_EMPTY"
    REPLAY_INTERVAL_INVALID = "REPLAY_INTERVAL_INVALID"
    REPLAY_NOT_STARTED = "REPLAY_NOT_STARTED"
    REPLAY_EVENT_ID_INVALID = "REPLAY_EVENT_ID_INVALID"
    REPLAY_STREAM_LIMIT = "REPLAY_STREAM_LIMIT"
    BASELINE_RESULT_UNAVAILABLE = "BASELINE_RESULT_UNAVAILABLE"
    BASELINE_RESULT_MISMATCH = "BASELINE_RESULT_MISMATCH"
    MISSION_TRIGGER_FAILED = "MISSION_TRIGGER_FAILED"
    MISSION_TRIGGER_CANCELLED = "MISSION_TRIGGER_CANCELLED"
    RUN_NOT_FOUND = "RUN_NOT_FOUND"
    RUN_ID_INVALID = "RUN_ID_INVALID"
    RUN_RESULT_NOT_FOUND = "RUN_RESULT_NOT_FOUND"
    RUN_RESULT_CORRUPT = "RUN_RESULT_CORRUPT"
    RUN_METADATA_NOT_FOUND = "RUN_METADATA_NOT_FOUND"
    RUN_METADATA_CORRUPT = "RUN_METADATA_CORRUPT"
    RUN_ARTIFACT_STORAGE_ERROR = "RUN_ARTIFACT_STORAGE_ERROR"
    INTERNAL_SERVER_ERROR = "INTERNAL_SERVER_ERROR"


class SimulationRunRequest(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "examples": [
                {"scenario_id": "mars_hab_atmosphere_solar_failure"},
                {
                    "scenario_id": "mars_hab_atmosphere_solar_failure",
                    "plan": {
                        "plan_id": "sample_plan",
                        "summary": (
                            "Isolate leaking lab module and repair "
                            "degraded solar array via EVA"
                        ),
                        "actions": [
                            {
                                "type": "isolate_module",
                                "start_min": 0,
                                "module": "lab",
                            }
                        ],
                        "rationale": "Cut leak rate below stabilize threshold",
                        "expected_risk": "EVA consumable budget",
                        "constraints_checked": ["leak_module_unoccupied"],
                    },
                },
            ]
        },
    )

    scenario_id: str
    plan: RecoveryPlan | None = None


class SimulationRunResponse(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "examples": [
                {
                    "run_id": "00000000-0000-4000-8000-000000000001",
                    "duration_ms": 120,
                    "result": {
                        "scenario_id": "mars_hab_atmosphere_solar_failure",
                        "plan_id": "",
                        "outcome": "FAILURE",
                        "valid_plan": True,
                        "metrics": {
                            "minimum_inspired_o2_mmhg": 0.0,
                            "minimum_cabin_pressure_kpa": 0.0,
                            "maximum_co2_one_hour_avg_mmhg": 0.0,
                            "minimum_battery_soc_percent": 0.0,
                            "minimum_power_margin_kw": 0.0,
                            "minimum_temperature_margin_c": 0.0,
                            "minimum_eva_safe_return_margin_min": 0.0,
                            "minimum_crew_spo2_percent": 0.0,
                            "maximum_crew_fatigue_percent": 0.0,
                            "eva_completed": False,
                            "communications_sent": False,
                            "time_to_stabilization_hr": 0.0,
                        },
                        "timeline": [],
                        "telemetry_history": [],
                        "failure_reasons": ["critical_repair_impossible"],
                    },
                }
            ]
        },
    )

    run_id: str
    duration_ms: StrictInt
    result: SimulationResult


class HealthResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["ok", "degraded"]
    simulator_ready: bool
    message: str


class ErrorResponse(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "examples": [
                {
                    "code": "SIMULATOR_UNAVAILABLE",
                    "message": "Simulator executable is not ready",
                    "run_id": None,
                }
            ]
        },
    )

    code: ErrorCode
    message: str
    run_id: str | None = Field(default=None)
