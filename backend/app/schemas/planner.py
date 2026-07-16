# Phase 5 Step 1 planner input/output contracts
# candidate RecoveryPlan only; simulator remains authoritative
from __future__ import annotations

import re
import uuid
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.schemas.common import CONTRACT_CONFIG, StrictInt
from app.schemas.plan import RecoveryPlan
from app.schemas.result import OutcomeStatus, SimulationMetrics
from app.schemas.retrieval_query import ProcedureRetrievalResult
from app.schemas.telemetry import TelemetrySample

PLANNER_SCHEMA_VERSION = "1.0.0"

Sha256HexLower = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
NonEmptyStr = Annotated[str, Field(min_length=1)]

_SCENARIO_ID_PATH_CHARS = re.compile(r"[/\\]|:")


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


def _normalize_scenario_id(value: str) -> str:
    if not isinstance(value, str):
        raise ValueError("scenario_id must be a non-empty string")
    normalized = value.strip()
    if not normalized:
        raise ValueError("scenario_id must be a non-empty string")
    if _SCENARIO_ID_PATH_CHARS.search(normalized) or ".." in normalized:
        raise ValueError("scenario_id must not be a filesystem path")
    return normalized


class PlannerModelMetadata(BaseModel):
    model_config = CONTRACT_CONFIG

    provider: NonEmptyStr
    model_id: NonEmptyStr
    model_revision: str | None = None


class PlannerMissionContext(BaseModel):
    model_config = CONTRACT_CONFIG

    session_id: str
    scenario_id: str
    baseline_run_id: str
    baseline_outcome: OutcomeStatus
    baseline_failure_reasons: list[str]
    baseline_metrics: SimulationMetrics
    current_sample_index: StrictInt = Field(ge=0)
    telemetry_sample_count: StrictInt = Field(gt=0)
    current_telemetry: TelemetrySample

    @field_validator("session_id")
    @classmethod
    def _validate_session_id(cls, value: str) -> str:
        return _canonical_uuid_str(value, field_name="session_id")

    @field_validator("baseline_run_id")
    @classmethod
    def _validate_baseline_run_id(cls, value: str) -> str:
        return _canonical_uuid_str(value, field_name="baseline_run_id")

    @field_validator("scenario_id")
    @classmethod
    def _validate_scenario_id(cls, value: str) -> str:
        return _normalize_scenario_id(value)

    @model_validator(mode="after")
    def _index_within_bounds(self) -> PlannerMissionContext:
        if self.current_sample_index >= self.telemetry_sample_count:
            raise ValueError(
                "current_sample_index must be less than telemetry_sample_count",
            )
        return self


class PlannerPromptInput(BaseModel):
    model_config = CONTRACT_CONFIG

    mission_context: PlannerMissionContext
    retrieval_result: ProcedureRetrievalResult

    @model_validator(mode="after")
    def _require_matches(self) -> PlannerPromptInput:
        if len(self.retrieval_result.matches) < 1:
            raise ValueError("retrieval_result must contain at least one match")
        return self


class PlannerPromptPackage(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: NonEmptyStr
    system_prompt: str
    user_prompt: str
    prompt_sha256: Sha256HexLower
    evidence_chunk_ids: tuple[str, ...]
    evidence_procedure_ids: tuple[str, ...]
    model_metadata: PlannerModelMetadata


class PlannerGenerationResult(BaseModel):
    model_config = CONTRACT_CONFIG

    schema_version: NonEmptyStr
    model_metadata: PlannerModelMetadata
    prompt_sha256: Sha256HexLower
    response_sha256: Sha256HexLower
    evidence_chunk_ids: tuple[str, ...]
    evidence_procedure_ids: tuple[str, ...]
    plan: RecoveryPlan
    finish_reason: Literal["stop"] | None = None
