# Phase 5 Step 3 planning validation contracts
# simulator-owned results persisted separately from immutable attempts
from __future__ import annotations

import hashlib
import json
import re
import uuid
from datetime import datetime
from enum import Enum
from typing import Annotated

from pydantic import BaseModel, Field, field_validator, model_validator

from app.schemas.common import CONTRACT_CONFIG, StrictBool, StrictInt
from app.schemas.plan import RecoveryPlan
from app.schemas.planning import PlanningAttempt
from app.schemas.result import OutcomeStatus, SimulationMetrics
from app.schemas.run import validate_canonical_run_id

PLANNING_VALIDATION_SCHEMA_VERSION = "1.0.0"

Sha256HexLower = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
Sha256HexUpper = Annotated[str, Field(pattern=r"^[0-9A-F]{64}$")]
NonEmptyStr = Annotated[str, Field(min_length=1)]

_FORBIDDEN_VALIDATION_KEYS = frozenset(
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
        "survival_probability",
        "filesystem_path",
        "improved",
        "safer",
        "successful",
        "recommended",
        "score",
        "confidence",
    },
)

_QUALITATIVE_COMPARISON_KEYS = frozenset(
    {
        "improved",
        "safer",
        "successful",
        "recommended",
        "score",
        "confidence",
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


def _canonical_json(value: object) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )


# SHA-256 of canonical RecoveryPlan JSON submitted to SimulationService
def canonical_plan_sha256(plan: RecoveryPlan) -> str:
    payload = _canonical_json(
        plan.model_dump(mode="json", exclude_none=True),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


class PlanningValidationStatus(str, Enum):
    SIMULATING = "SIMULATING"
    SIMULATION_COMPLETE = "SIMULATION_COMPLETE"
    ERROR = "ERROR"


class PlanningResultSummary(BaseModel):
    model_config = CONTRACT_CONFIG

    run_id: str
    result_sha256: Sha256HexUpper
    scenario_id: str
    plan_id: str
    outcome: OutcomeStatus
    valid_plan: StrictBool
    failure_reasons: list[str]
    metrics: SimulationMetrics
    telemetry_sample_count: StrictInt = Field(gt=0)

    @field_validator("run_id", mode="before")
    @classmethod
    def _validate_run_id(cls, value: object) -> str:
        return validate_canonical_run_id(value)


class PlanningResultComparison(BaseModel):
    model_config = CONTRACT_CONFIG

    baseline_outcome: OutcomeStatus
    candidate_outcome: OutcomeStatus
    outcome_changed: StrictBool
    baseline_valid_plan: StrictBool
    candidate_valid_plan: StrictBool
    baseline_failure_reasons: list[str]
    candidate_failure_reasons: list[str]
    resolved_failure_reasons: list[str]
    introduced_failure_reasons: list[str]
    baseline_metrics: SimulationMetrics
    candidate_metrics: SimulationMetrics

    @classmethod
    def reject_forbidden_payload_keys(cls, payload: dict[str, object]) -> None:
        for key in payload:
            if key in _QUALITATIVE_COMPARISON_KEYS:
                raise ValueError(f"forbidden field: {key}")


def build_planning_result_comparison(
    baseline: PlanningResultSummary,
    candidate: PlanningResultSummary,
) -> PlanningResultComparison:
    baseline_set = set(baseline.failure_reasons)
    candidate_set = set(candidate.failure_reasons)
    resolved = [reason for reason in baseline.failure_reasons if reason not in candidate_set]
    introduced = [reason for reason in candidate.failure_reasons if reason not in baseline_set]
    return PlanningResultComparison(
        baseline_outcome=baseline.outcome,
        candidate_outcome=candidate.outcome,
        outcome_changed=baseline.outcome != candidate.outcome,
        baseline_valid_plan=baseline.valid_plan,
        candidate_valid_plan=candidate.valid_plan,
        baseline_failure_reasons=list(baseline.failure_reasons),
        candidate_failure_reasons=list(candidate.failure_reasons),
        resolved_failure_reasons=resolved,
        introduced_failure_reasons=introduced,
        baseline_metrics=baseline.metrics,
        candidate_metrics=candidate.metrics,
    )


class PlanningValidationRecord(BaseModel):
    model_config = CONTRACT_CONFIG

    schema_version: NonEmptyStr
    attempt_id: str
    session_id: str
    scenario_id: str
    baseline_run_id: str
    attempt_preflight_sha256: Sha256HexLower
    candidate_plan_sha256: Sha256HexLower
    status: PlanningValidationStatus
    started_at: datetime
    completed_at: datetime | None = None
    baseline: PlanningResultSummary | None = None
    candidate: PlanningResultSummary | None = None
    comparison: PlanningResultComparison | None = None
    error_code: str | None = None

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

    @field_validator("started_at", "completed_at")
    @classmethod
    def _require_aware_timestamp(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("timestamp must be timezone-aware")
        return value

    @model_validator(mode="after")
    def _cross_field_consistency(self) -> PlanningValidationRecord:
        if self.status == PlanningValidationStatus.SIMULATING:
            if self.completed_at is not None:
                raise ValueError("SIMULATING requires completed_at to be null")
            if self.candidate is not None:
                raise ValueError("SIMULATING requires candidate to be null")
            if self.comparison is not None:
                raise ValueError("SIMULATING requires comparison to be null")
            if self.error_code is not None:
                raise ValueError("SIMULATING requires error_code to be null")
        elif self.status == PlanningValidationStatus.SIMULATION_COMPLETE:
            if self.completed_at is None:
                raise ValueError("SIMULATION_COMPLETE requires completed_at")
            if self.baseline is None or self.candidate is None or self.comparison is None:
                raise ValueError("SIMULATION_COMPLETE requires baseline, candidate, and comparison")
            if self.error_code is not None:
                raise ValueError("SIMULATION_COMPLETE requires error_code to be null")
            self._validate_summary_linkage(self.baseline, self.comparison.baseline_outcome)
            self._validate_summary_linkage(self.candidate, self.comparison.candidate_outcome)
            self._validate_comparison_matches_summaries()
        elif self.status == PlanningValidationStatus.ERROR:
            if self.completed_at is None:
                raise ValueError("ERROR requires completed_at")
            if self.error_code is None or not self.error_code.strip():
                raise ValueError("ERROR requires a nonempty error_code")

        if self.completed_at is not None and self.completed_at < self.started_at:
            raise ValueError("completed_at must be >= started_at")

        if self.baseline is not None:
            if self.baseline.run_id != self.baseline_run_id:
                raise ValueError("baseline.run_id must equal baseline_run_id")
            if self.baseline.scenario_id != self.scenario_id:
                raise ValueError("baseline.scenario_id must equal scenario_id")

        if self.candidate is not None and self.candidate.scenario_id != self.scenario_id:
            raise ValueError("candidate.scenario_id must equal scenario_id")

        return self

    def _validate_summary_linkage(
        self,
        summary: PlanningResultSummary,
        comparison_outcome: OutcomeStatus,
    ) -> None:
        if summary.outcome != comparison_outcome:
            raise ValueError("comparison outcome must match summary outcome")

    def _validate_comparison_matches_summaries(self) -> None:
        assert self.baseline is not None
        assert self.candidate is not None
        assert self.comparison is not None
        if self.comparison.baseline_outcome != self.baseline.outcome:
            raise ValueError("comparison.baseline_outcome must match baseline.outcome")
        if self.comparison.candidate_outcome != self.candidate.outcome:
            raise ValueError("comparison.candidate_outcome must match candidate.outcome")
        if self.comparison.baseline_valid_plan != self.baseline.valid_plan:
            raise ValueError("comparison.baseline_valid_plan must match baseline.valid_plan")
        if self.comparison.candidate_valid_plan != self.candidate.valid_plan:
            raise ValueError("comparison.candidate_valid_plan must match candidate.valid_plan")
        if self.comparison.baseline_failure_reasons != self.baseline.failure_reasons:
            raise ValueError("comparison.baseline_failure_reasons must match baseline")
        if self.comparison.candidate_failure_reasons != self.candidate.failure_reasons:
            raise ValueError("comparison.candidate_failure_reasons must match candidate")
        if self.comparison.baseline_metrics != self.baseline.metrics:
            raise ValueError("comparison.baseline_metrics must match baseline.metrics")
        if self.comparison.candidate_metrics != self.candidate.metrics:
            raise ValueError("comparison.candidate_metrics must match candidate.metrics")
        if self.comparison.outcome_changed != (
            self.baseline.outcome != self.candidate.outcome
        ):
            raise ValueError(
                "comparison.outcome_changed must match baseline and candidate outcomes",
            )

    @classmethod
    def reject_forbidden_payload_keys(cls, payload: dict[str, object]) -> None:
        for key in payload:
            if key in _FORBIDDEN_VALIDATION_KEYS:
                raise ValueError(f"forbidden field: {key}")


_API_RESULT_PATH = re.compile(
    r"^/api/sim/result/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
)


class PlanningSimulationResponse(BaseModel):
    model_config = CONTRACT_CONFIG

    attempt: PlanningAttempt
    validation: PlanningValidationRecord
    baseline_result_path: str
    candidate_result_path: str

    @field_validator("baseline_result_path", "candidate_result_path")
    @classmethod
    def _validate_result_path(cls, value: str) -> str:
        if not _API_RESULT_PATH.fullmatch(value):
            raise ValueError("result path must be a relative API sim result path")
        return value

    @model_validator(mode="after")
    def _validate_terminal_state(self) -> PlanningSimulationResponse:
        if self.validation.status != PlanningValidationStatus.SIMULATION_COMPLETE:
            raise ValueError("validation.status must be SIMULATION_COMPLETE")
        if self.attempt.attempt_id != self.validation.attempt_id:
            raise ValueError("attempt_id must match between attempt and validation")
        if self.attempt.session_id != self.validation.session_id:
            raise ValueError("session_id must match between attempt and validation")
        expected_baseline = f"/api/sim/result/{self.validation.baseline_run_id}"
        candidate = self.validation.candidate
        if candidate is None:
            raise ValueError("validation.candidate is required for SIMULATION_COMPLETE")
        expected_candidate = f"/api/sim/result/{candidate.run_id}"
        if self.baseline_result_path != expected_baseline:
            raise ValueError("baseline_result_path must match baseline_run_id")
        if self.candidate_result_path != expected_candidate:
            raise ValueError("candidate_result_path must match candidate run_id")
        if candidate.plan_id != self.attempt.generation_result.plan.plan_id:
            raise ValueError("candidate plan_id must match attempt RecoveryPlan.plan_id")
        return self
