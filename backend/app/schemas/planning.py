# Phase 5 Step 2 planning attempt contracts
# persisted candidates are evidence-grounded only; simulator remains authoritative
from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum
from typing import Annotated, Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from app.schemas.actions import ActionType
from app.schemas.common import CONTRACT_CONFIG, StrictInt
from app.schemas.planner import (
    PlannerGenerationResult,
    PlannerMissionContext,
)
from app.schemas.retrieval_query import ProcedureRetrievalResult

PLANNING_SCHEMA_VERSION = "1.0.0"

Sha256HexLower = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
NonEmptyStr = Annotated[str, Field(min_length=1)]

_FORBIDDEN_ATTEMPT_KEYS = frozenset(
    {
        "system_prompt",
        "user_prompt",
        "raw_response",
        "api_key",
        "authorization",
        "vectors",
        "telemetry_history",
        "simulation_result",
        "simulator_result",
        "candidate_run_id",
        "valid_plan",
        "survival_probability",
        "filesystem_path",
    },
)


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


class PlanningAttemptStatus(str, Enum):
    CANDIDATE_READY = "CANDIDATE_READY"


class ActionEvidenceSupport(BaseModel):
    model_config = CONTRACT_CONFIG

    action_index: StrictInt = Field(ge=0)
    action_type: ActionType
    supporting_chunk_ids: tuple[NonEmptyStr, ...]
    supporting_procedure_ids: tuple[NonEmptyStr, ...]

    @field_validator("supporting_chunk_ids", "supporting_procedure_ids")
    @classmethod
    def _nonempty_unique_tuple(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if len(value) < 1:
            raise ValueError("tuple must contain at least one entry")
        if len(value) != len(set(value)):
            raise ValueError("tuple entries must be unique")
        return value


class PlannerCandidatePreflight(BaseModel):
    model_config = CONTRACT_CONFIG

    schema_version: NonEmptyStr
    schema_parsed: Literal[True]
    evidence_grounded: Literal[True]
    action_count: StrictInt = Field(gt=0)
    action_support: tuple[ActionEvidenceSupport, ...]
    evidence_chunk_ids: tuple[NonEmptyStr, ...]
    evidence_procedure_ids: tuple[NonEmptyStr, ...]
    preflight_sha256: Sha256HexLower

    @model_validator(mode="after")
    def _validate_support_shape(self) -> PlannerCandidatePreflight:
        if len(self.action_support) < 1:
            raise ValueError("action_support must contain at least one entry")
        if self.action_count != len(self.action_support):
            raise ValueError("action_count must match action_support length")
        expected_indexes = list(range(len(self.action_support)))
        actual_indexes = [item.action_index for item in self.action_support]
        if actual_indexes != expected_indexes:
            raise ValueError("action indexes must be contiguous from 0")
        if len(self.evidence_chunk_ids) < 1:
            raise ValueError("evidence_chunk_ids must be nonempty")
        if len(self.evidence_procedure_ids) < 1:
            raise ValueError("evidence_procedure_ids must be nonempty")
        return self


class PlanningAttempt(BaseModel):
    # Immutable persisted candidate; not simulator-approved.
    model_config = CONTRACT_CONFIG

    schema_version: NonEmptyStr
    attempt_id: str
    session_id: str
    scenario_id: str
    baseline_run_id: str
    created_at: datetime
    status: PlanningAttemptStatus
    mission_context: PlannerMissionContext
    retrieval_result: ProcedureRetrievalResult
    generation_result: PlannerGenerationResult
    preflight: PlannerCandidatePreflight

    @field_validator("attempt_id")
    @classmethod
    def _validate_attempt_id(cls, value: str) -> str:
        return _canonical_uuid_str(value, field_name="attempt_id")

    @field_validator("session_id")
    @classmethod
    def _validate_session_id(cls, value: str) -> str:
        return _canonical_uuid_str(value, field_name="session_id")

    @field_validator("baseline_run_id")
    @classmethod
    def _validate_baseline_run_id(cls, value: str) -> str:
        return _canonical_uuid_str(value, field_name="baseline_run_id")

    @field_validator("created_at")
    @classmethod
    def _require_aware_timestamp(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("created_at must be timezone-aware")
        return value

    @model_validator(mode="after")
    def _cross_field_consistency(self) -> PlanningAttempt:
        if self.status != PlanningAttemptStatus.CANDIDATE_READY:
            raise ValueError("status must be CANDIDATE_READY for Step 2")
        if self.session_id != self.mission_context.session_id:
            raise ValueError("session_id must match mission_context.session_id")
        if self.baseline_run_id != self.mission_context.baseline_run_id:
            raise ValueError("baseline_run_id must match mission_context.baseline_run_id")
        if self.scenario_id != self.mission_context.scenario_id:
            raise ValueError("scenario_id must match mission_context.scenario_id")

        retrieval_chunk_ids = tuple(match.chunk_id for match in self.retrieval_result.matches)
        if self.generation_result.evidence_chunk_ids != retrieval_chunk_ids:
            raise ValueError(
                "generation_result evidence_chunk_ids must match retrieval matches",
            )
        if self.preflight.evidence_chunk_ids != retrieval_chunk_ids:
            raise ValueError("preflight evidence_chunk_ids must match retrieval matches")
        if self.preflight.evidence_procedure_ids != self.generation_result.evidence_procedure_ids:
            raise ValueError(
                "preflight evidence_procedure_ids must match generation_result",
            )
        if len(self.generation_result.plan.actions) != self.preflight.action_count:
            raise ValueError("plan action count must match preflight action_count")
        return self

    @classmethod
    def reject_forbidden_payload_keys(cls, payload: dict[str, object]) -> None:
        for key in payload:
            if key in _FORBIDDEN_ATTEMPT_KEYS:
                raise ValueError(f"forbidden field: {key}")


# transport-neutral service result; same shape as persisted attempt
PlanningGenerationResponse = PlanningAttempt
