# mission lifecycle session contracts (backend orchestration states)
from __future__ import annotations

import re
import uuid
from datetime import datetime
from enum import Enum
from typing import Self

from pydantic import (
    BaseModel,
    ConfigDict,
    ValidationInfo,
    field_validator,
    model_validator,
)

from app.schemas.common import StrictInt
from app.schemas.result import OutcomeStatus

_SCENARIO_ID_PATH_CHARS = re.compile(r"[/\\]|:")


# reject empty or filesystem-like scenario identifiers
def _normalize_scenario_id(value: str) -> str:
    if not isinstance(value, str):
        raise ValueError("scenario_id must be a non-empty string")
    normalized = value.strip()
    if not normalized:
        raise ValueError("scenario_id must be a non-empty string")
    if _SCENARIO_ID_PATH_CHARS.search(normalized) or ".." in normalized:
        raise ValueError("scenario_id must not be a filesystem path")
    return normalized


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


# require timezone-aware datetime
def _require_aware(value: datetime, *, field_name: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")
    return value


class MissionSessionStatus(str, Enum):
    READY = "READY"
    TRIGGERING = "TRIGGERING"
    BASELINE_READY = "BASELINE_READY"
    REPLAYING = "REPLAYING"
    COMPLETED = "COMPLETED"
    ERROR = "ERROR"


class MissionCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scenario_id: str

    @field_validator("scenario_id", mode="before")
    @classmethod
    def _validate_scenario_id(cls, value: object) -> str:
        if not isinstance(value, str):
            raise ValueError("scenario_id must be a non-empty string")
        return _normalize_scenario_id(value)


class MissionSession(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session_id: str
    scenario_id: str
    status: MissionSessionStatus
    created_at: datetime
    updated_at: datetime
    accident_triggered_at: datetime | None
    baseline_run_id: str | None
    baseline_outcome: OutcomeStatus | None
    telemetry_sample_count: StrictInt | None
    replay_started_at: datetime | None
    replay_interval_ms: StrictInt | None
    error_code: str | None

    @field_validator("session_id")
    @classmethod
    def _validate_session_id(cls, value: str) -> str:
        return _canonical_uuid_str(value, field_name="session_id")

    @field_validator("scenario_id", mode="before")
    @classmethod
    def _validate_scenario_id(cls, value: object) -> str:
        if not isinstance(value, str):
            raise ValueError("scenario_id must be a non-empty string")
        return _normalize_scenario_id(value)

    @field_validator("baseline_run_id")
    @classmethod
    def _validate_baseline_run_id(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return _canonical_uuid_str(value, field_name="baseline_run_id")

    @field_validator(
        "created_at",
        "updated_at",
        "accident_triggered_at",
        "replay_started_at",
    )
    @classmethod
    def _validate_aware_datetimes(
        cls, value: datetime | None, info: ValidationInfo
    ) -> datetime | None:
        if value is None:
            return None
        field_name = info.field_name or "timestamp"
        return _require_aware(value, field_name=field_name)

    @field_validator("error_code")
    @classmethod
    def _validate_error_code(cls, value: str | None) -> str | None:
        if value is None:
            return None
        if not isinstance(value, str) or not value.strip():
            raise ValueError("error_code must be a non-empty string when set")
        return value

    @model_validator(mode="after")
    def _validate_state_consistency(self) -> Self:
        if self.updated_at < self.created_at:
            raise ValueError("updated_at must not precede created_at")
        if (
            self.accident_triggered_at is not None
            and self.accident_triggered_at < self.created_at
        ):
            raise ValueError("accident_triggered_at must not precede created_at")
        if self.replay_started_at is not None:
            if self.accident_triggered_at is None:
                raise ValueError(
                    "replay_started_at requires accident_triggered_at"
                )
            if self.replay_started_at < self.accident_triggered_at:
                raise ValueError(
                    "replay_started_at must not precede accident_triggered_at"
                )

        status = self.status
        if status == MissionSessionStatus.READY:
            self._require_none(
                accident_triggered_at=self.accident_triggered_at,
                baseline_run_id=self.baseline_run_id,
                baseline_outcome=self.baseline_outcome,
                telemetry_sample_count=self.telemetry_sample_count,
                replay_started_at=self.replay_started_at,
                replay_interval_ms=self.replay_interval_ms,
                error_code=self.error_code,
            )
        elif status == MissionSessionStatus.TRIGGERING:
            if self.accident_triggered_at is None:
                raise ValueError("TRIGGERING requires accident_triggered_at")
            self._require_none(
                baseline_run_id=self.baseline_run_id,
                baseline_outcome=self.baseline_outcome,
                telemetry_sample_count=self.telemetry_sample_count,
                replay_started_at=self.replay_started_at,
                replay_interval_ms=self.replay_interval_ms,
                error_code=self.error_code,
            )
        elif status == MissionSessionStatus.BASELINE_READY:
            self._require_baseline_fields()
            self._require_none(
                replay_started_at=self.replay_started_at,
                replay_interval_ms=self.replay_interval_ms,
                error_code=self.error_code,
            )
        elif status in (
            MissionSessionStatus.REPLAYING,
            MissionSessionStatus.COMPLETED,
        ):
            self._require_baseline_fields()
            if self.replay_started_at is None:
                raise ValueError(f"{status.value} requires replay_started_at")
            if self.replay_interval_ms is None or self.replay_interval_ms <= 0:
                raise ValueError(
                    f"{status.value} requires positive replay_interval_ms"
                )
            if self.error_code is not None:
                raise ValueError(f"{status.value} requires error_code to be None")
        elif status == MissionSessionStatus.ERROR:
            if self.error_code is None or not self.error_code.strip():
                raise ValueError("ERROR requires a non-empty error_code")
        return self

    def _require_baseline_fields(self) -> None:
        if self.accident_triggered_at is None:
            raise ValueError(f"{self.status.value} requires accident_triggered_at")
        if self.baseline_run_id is None:
            raise ValueError(f"{self.status.value} requires baseline_run_id")
        if self.baseline_outcome is None:
            raise ValueError(f"{self.status.value} requires baseline_outcome")
        if (
            self.telemetry_sample_count is None
            or self.telemetry_sample_count <= 0
        ):
            raise ValueError(
                f"{self.status.value} requires positive telemetry_sample_count"
            )

    @staticmethod
    def _require_none(**fields: object) -> None:
        for name, value in fields.items():
            if value is not None:
                raise ValueError(f"field must be None: {name}")


class MissionCreateResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session: MissionSession


class AccidentTriggerResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session: MissionSession
    baseline_run_id: str
    baseline_outcome: OutcomeStatus
    telemetry_sample_count: StrictInt

    @field_validator("baseline_run_id")
    @classmethod
    def _validate_baseline_run_id(cls, value: str) -> str:
        return _canonical_uuid_str(value, field_name="baseline_run_id")

    @field_validator("telemetry_sample_count")
    @classmethod
    def _validate_sample_count(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("telemetry_sample_count must be a positive integer")
        return value

    @model_validator(mode="after")
    def _validate_consistency(self) -> Self:
        if self.session.status != MissionSessionStatus.BASELINE_READY:
            raise ValueError("session status must be BASELINE_READY")
        if self.baseline_run_id != self.session.baseline_run_id:
            raise ValueError("baseline_run_id must match session.baseline_run_id")
        if self.baseline_outcome != self.session.baseline_outcome:
            raise ValueError(
                "baseline_outcome must match session.baseline_outcome"
            )
        if self.telemetry_sample_count != self.session.telemetry_sample_count:
            raise ValueError(
                "telemetry_sample_count must match session.telemetry_sample_count"
            )
        return self
