# strict persisted run metadata contract (metadata.json)
from __future__ import annotations

import re
import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, field_validator

from app.schemas.common import CONTRACT_CONFIG, StrictInt

_SHA256_UPPER = re.compile(r"^[0-9A-F]{64}$")


# accept only canonical lowercase hyphenated UUID strings
def validate_canonical_run_id(value: object) -> str:
    if not isinstance(value, str):
        raise ValueError("run_id must be a canonical UUID string")
    if not value or value != value.strip():
        raise ValueError("run_id must be a canonical UUID string")
    if any(ch in value for ch in ("/", "\\", "%")):
        raise ValueError("run_id must be a canonical UUID string")
    if value in (".", "..") or ".." in value:
        raise ValueError("run_id must be a canonical UUID string")
    try:
        parsed = uuid.UUID(value)
    except (ValueError, AttributeError, TypeError) as exc:
        raise ValueError("run_id must be a canonical UUID string") from exc
    canonical = str(parsed)
    if value != canonical:
        raise ValueError("run_id must be a canonical UUID string")
    return canonical


# require uppercase 64-char SHA-256 hex when present
def _validate_sha256_field(value: str | None) -> str | None:
    if value is None:
        return None
    if not _SHA256_UPPER.fullmatch(value):
        raise ValueError("hash must be 64-character uppercase SHA-256 hex")
    return value


class RunArtifactMetadata(BaseModel):
    model_config = CONTRACT_CONFIG

    run_id: str
    created_at: str
    mode: Literal["baseline", "plan"]
    scenario_id: str
    plan_id: str | None
    scenario_sha256: str
    plan_sha256: str | None
    result_sha256: str | None
    process_exit_code: StrictInt | None
    duration_ms: StrictInt | None
    outcome: str | None
    status: Literal["created", "completed", "failed"]
    error_code: str | None

    @field_validator("run_id", mode="before")
    @classmethod
    def _validate_run_id(cls, value: object) -> str:
        return validate_canonical_run_id(value)

    @field_validator("created_at")
    @classmethod
    def _validate_created_at(cls, value: str) -> str:
        try:
            parsed = datetime.fromisoformat(value)
        except ValueError as exc:
            raise ValueError("created_at must be a timezone-aware ISO-8601 timestamp") from exc
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            raise ValueError("created_at must be a timezone-aware ISO-8601 timestamp")
        return value

    @field_validator("scenario_sha256")
    @classmethod
    def _validate_scenario_sha256(cls, value: str) -> str:
        result = _validate_sha256_field(value)
        assert result is not None
        return result

    @field_validator("plan_sha256", "result_sha256")
    @classmethod
    def _validate_optional_sha256(cls, value: str | None) -> str | None:
        return _validate_sha256_field(value)
