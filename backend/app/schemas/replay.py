# replay HTTP and SSE payload contracts
from __future__ import annotations

import uuid
from typing import Self

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

from app.schemas.common import StrictBool, StrictInt
from app.schemas.mission import MissionSession, MissionSessionStatus
from app.schemas.result import OutcomeStatus, SimulationMetrics
from app.schemas.telemetry import TelemetrySample


# require canonical UUID string form used by RunStore
def _canonical_uuid_str(value: str, *, field_name: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{field_name} must be a canonical UUID string")
    try:
        parsed = uuid.UUID(value)
    except (ValueError, AttributeError, TypeError) as exc:
        raise ValueError(f"{field_name} must be a canonical UUID string") from exc
    canonical = str(parsed)
    if value != canonical:
        raise ValueError(f"{field_name} must be a canonical UUID string")
    return canonical


# reject filesystem and traversal paths; require /api/ prefix and session id
def _validate_api_session_path(path: str, *, session_id: str, field_name: str) -> str:
    if not isinstance(path, str) or not path.startswith("/api/"):
        raise ValueError(f"{field_name} must begin with /api/")
    if path.startswith("//") or "\\" in path:
        raise ValueError(f"{field_name} must not be a filesystem path")
    if ".." in path:
        raise ValueError(f"{field_name} must not contain parent-relative segments")
    if session_id not in path:
        raise ValueError(f"{field_name} must contain the session_id")
    return path


class ReplayStartRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    interval_ms: StrictInt | None = None
    restart: StrictBool = False

    @field_validator("interval_ms")
    @classmethod
    def _validate_interval_ms(cls, value: int | None) -> int | None:
        if value is None:
            return None
        if value <= 0:
            raise ValueError("interval_ms must be a positive integer when provided")
        return value


class ReplayStartResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session: MissionSession
    stream_path: str
    current_telemetry_path: str

    @model_validator(mode="after")
    def _validate_response(self) -> Self:
        if self.session.status != MissionSessionStatus.REPLAYING:
            raise ValueError("session status must be REPLAYING")
        _validate_api_session_path(
            self.stream_path,
            session_id=self.session.session_id,
            field_name="stream_path",
        )
        _validate_api_session_path(
            self.current_telemetry_path,
            session_id=self.session.session_id,
            field_name="current_telemetry_path",
        )
        return self


class CurrentTelemetryResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session_id: str
    status: MissionSessionStatus
    sample_index: StrictInt
    sample_count: StrictInt
    telemetry: TelemetrySample
    baseline_run_id: str

    @field_validator("session_id")
    @classmethod
    def _validate_session_id(cls, value: str) -> str:
        return _canonical_uuid_str(value, field_name="session_id")

    @field_validator("baseline_run_id")
    @classmethod
    def _validate_baseline_run_id(cls, value: str) -> str:
        return _canonical_uuid_str(value, field_name="baseline_run_id")

    @model_validator(mode="after")
    def _validate_bounds_and_status(self) -> Self:
        if self.status not in (
            MissionSessionStatus.REPLAYING,
            MissionSessionStatus.COMPLETED,
        ):
            raise ValueError("status must be REPLAYING or COMPLETED")
        if self.sample_count <= 0:
            raise ValueError("sample_count must be greater than 0")
        if not (0 <= self.sample_index < self.sample_count):
            raise ValueError("sample_index must satisfy 0 <= sample_index < sample_count")
        return self


class ReplayTelemetryEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session_id: str
    sequence: StrictInt
    sample_index: StrictInt
    sample_count: StrictInt
    telemetry: TelemetrySample

    @field_validator("session_id")
    @classmethod
    def _validate_session_id(cls, value: str) -> str:
        return _canonical_uuid_str(value, field_name="session_id")

    @model_validator(mode="after")
    def _validate_sequence_and_bounds(self) -> Self:
        if self.sequence < 0:
            raise ValueError("sequence must be >= 0")
        if self.sequence != self.sample_index:
            raise ValueError("sequence must equal sample_index")
        if self.sample_count <= 0:
            raise ValueError("sample_count must be greater than 0")
        if not (0 <= self.sample_index < self.sample_count):
            raise ValueError("sample_index must satisfy 0 <= sample_index < sample_count")
        return self


class ReplayCompleteEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session_id: str
    sequence: StrictInt
    baseline_run_id: str
    outcome: OutcomeStatus
    valid_plan: StrictBool
    failure_reasons: list[str]
    metrics: SimulationMetrics

    @field_validator("session_id")
    @classmethod
    def _validate_session_id(cls, value: str) -> str:
        return _canonical_uuid_str(value, field_name="session_id")

    @field_validator("baseline_run_id")
    @classmethod
    def _validate_baseline_run_id(cls, value: str) -> str:
        return _canonical_uuid_str(value, field_name="baseline_run_id")

    @field_validator("sequence")
    @classmethod
    def _validate_sequence(cls, value: int) -> int:
        if value < 0:
            raise ValueError("sequence must be >= 0")
        return value
