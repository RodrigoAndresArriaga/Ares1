# Phase 5 Step 2 planning schema contract tests
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import pytest
from app.schemas.actions import ActionType
from app.schemas.planner import PLANNER_SCHEMA_VERSION, PlannerGenerationResult
from app.schemas.planning import (
    PLANNING_SCHEMA_VERSION,
    ActionEvidenceSupport,
    PlannerCandidatePreflight,
    PlanningAttempt,
    PlanningAttemptStatus,
)
from pydantic import ValidationError
from tests.conftest import (
    PLANNER_BASELINE_RUN_ID,
    PLANNER_SESSION_ID,
    PLANNING_ATTEMPT_ID,
    make_grounded_recovery_plan,
    make_multi_action_retrieval_result,
    make_planner_generation_result,
    make_planner_mission_context,
    make_planner_model_metadata,
    make_planner_prompt_input,
    make_planner_retrieval_result,
)

T0 = datetime(2026, 7, 15, 12, 0, 0, tzinfo=timezone.utc)


def _preflight(
    *,
    action_count: int = 1,
    chunk_ids: tuple[str, ...] = ("a" * 64,),
    procedure_ids: tuple[str, ...] = ("ARES-PROC-OXY-001",),
) -> PlannerCandidatePreflight:
    return PlannerCandidatePreflight(
        schema_version=PLANNING_SCHEMA_VERSION,
        schema_parsed=True,
        evidence_grounded=True,
        action_count=action_count,
        action_support=(
            ActionEvidenceSupport(
                action_index=0,
                action_type=ActionType.ISOLATE_MODULE,
                supporting_chunk_ids=chunk_ids,
                supporting_procedure_ids=procedure_ids,
            ),
        ),
        evidence_chunk_ids=chunk_ids,
        evidence_procedure_ids=procedure_ids,
        preflight_sha256="0" * 64,
    )


def _generation(
    baseline_result_data: Any,
    *,
    retrieval: Any | None = None,
    plan: Any | None = None,
) -> PlannerGenerationResult:
    resolved_retrieval = retrieval if retrieval is not None else make_planner_retrieval_result()
    prompt_input = make_planner_prompt_input(
        baseline_result_data,
        retrieval_overrides={"matches": resolved_retrieval.matches},
    )
    from app.services.planner_prompt import PlannerPromptBuilder

    package = PlannerPromptBuilder(
        model_metadata=make_planner_model_metadata(),
        max_prompt_characters=120000,
    ).build(prompt_input)
    resolved_plan = plan if plan is not None else make_grounded_recovery_plan()
    return make_planner_generation_result(prompt_package=package, plan=resolved_plan)


def _attempt(baseline_result_data: Any, **overrides: Any) -> PlanningAttempt:
    from app.services.planner_candidate_validator import PlannerCandidateValidator

    retrieval = overrides.pop("retrieval_result", make_planner_retrieval_result())
    plan = overrides.pop("plan", None)
    if plan is None:
        from app.schemas.plan import RecoveryPlan

        plan = RecoveryPlan.model_validate(
            {
                "plan_id": "grounded_plan",
                "summary": "Isolate lab module",
                "actions": [
                    {"type": "isolate_module", "start_min": 0, "module": "lab"},
                ],
                "rationale": "Grounded by retrieval evidence",
                "expected_risk": "Temporary isolation",
                "constraints_checked": ["unit_test"],
            },
        )
    generation = _generation(baseline_result_data, retrieval=retrieval, plan=plan)
    preflight = PlannerCandidateValidator().validate(
        retrieval_result=retrieval,
        generation_result=generation,
    )
    payload = {
        "schema_version": PLANNING_SCHEMA_VERSION,
        "attempt_id": PLANNING_ATTEMPT_ID,
        "session_id": PLANNER_SESSION_ID,
        "scenario_id": baseline_result_data["scenario_id"],
        "baseline_run_id": PLANNER_BASELINE_RUN_ID,
        "created_at": T0,
        "status": PlanningAttemptStatus.CANDIDATE_READY.value,
        "mission_context": make_planner_mission_context(baseline_result_data),
        "retrieval_result": retrieval,
        "generation_result": generation,
        "preflight": preflight,
    }
    payload.update(overrides)
    return PlanningAttempt.model_validate(payload)


def test_action_evidence_support_valid() -> None:
    item = ActionEvidenceSupport(
        action_index=0,
        action_type=ActionType.ISOLATE_MODULE,
        supporting_chunk_ids=("a" * 64, "b" * 64),
        supporting_procedure_ids=("ARES-PROC-001",),
    )
    assert item.supporting_chunk_ids == ("a" * 64, "b" * 64)


def test_action_evidence_support_rejects_duplicate_chunk_ids() -> None:
    with pytest.raises(ValidationError):
        ActionEvidenceSupport(
            action_index=0,
            action_type=ActionType.ISOLATE_MODULE,
            supporting_chunk_ids=("a" * 64, "a" * 64),
            supporting_procedure_ids=("ARES-PROC-001",),
        )


def test_preflight_requires_contiguous_action_indexes() -> None:
    with pytest.raises(ValidationError):
        PlannerCandidatePreflight(
            schema_version=PLANNING_SCHEMA_VERSION,
            schema_parsed=True,
            evidence_grounded=True,
            action_count=2,
            action_support=(
                ActionEvidenceSupport(
                    action_index=0,
                    action_type=ActionType.ISOLATE_MODULE,
                    supporting_chunk_ids=("a" * 64,),
                    supporting_procedure_ids=("ARES-PROC-001",),
                ),
                ActionEvidenceSupport(
                    action_index=2,
                    action_type=ActionType.REDUCE_POWER_LOAD,
                    supporting_chunk_ids=("b" * 64,),
                    supporting_procedure_ids=("ARES-PROC-002",),
                ),
            ),
            evidence_chunk_ids=("a" * 64, "b" * 64),
            evidence_procedure_ids=("ARES-PROC-001", "ARES-PROC-002"),
            preflight_sha256="0" * 64,
        )


def test_planning_attempt_valid_cross_field_consistency(
    baseline_result_data: Any,
) -> None:
    attempt = _attempt(baseline_result_data)
    assert attempt.status == PlanningAttemptStatus.CANDIDATE_READY
    assert attempt.session_id == attempt.mission_context.session_id


def test_planning_attempt_rejects_unknown_fields(
    baseline_result_data: Any,
) -> None:
    with pytest.raises(ValidationError):
        _attempt(baseline_result_data, valid_plan=True)


def test_planning_attempt_rejects_forbidden_payload_keys() -> None:
    with pytest.raises(ValueError, match="forbidden field"):
        PlanningAttempt.reject_forbidden_payload_keys({"system_prompt": "secret"})


def test_planning_attempt_rejects_naive_timestamp(
    baseline_result_data: Any,
) -> None:
    with pytest.raises(ValidationError):
        _attempt(
            baseline_result_data,
            created_at=datetime(2026, 7, 15, 12, 0, 0),
        )


def test_planning_attempt_rejects_noncanonical_uuid(
    baseline_result_data: Any,
) -> None:
    with pytest.raises(ValidationError):
        _attempt(
            baseline_result_data,
            attempt_id="not-a-uuid",
        )


def test_planning_attempt_rejects_evidence_mismatch(
    baseline_result_data: Any,
) -> None:
    from app.services.planner_candidate_validator import PlannerCandidateValidator

    retrieval = make_multi_action_retrieval_result()
    generation = _generation(
        baseline_result_data,
        retrieval=retrieval,
        plan=make_grounded_recovery_plan(),
    )
    preflight = PlannerCandidateValidator().validate(
        retrieval_result=retrieval,
        generation_result=generation,
    )
    with pytest.raises(ValidationError):
        PlanningAttempt.model_validate(
            {
                "schema_version": PLANNING_SCHEMA_VERSION,
                "attempt_id": PLANNING_ATTEMPT_ID,
                "session_id": PLANNER_SESSION_ID,
                "scenario_id": baseline_result_data["scenario_id"],
                "baseline_run_id": PLANNER_BASELINE_RUN_ID,
                "created_at": T0,
                "status": PlanningAttemptStatus.CANDIDATE_READY.value,
                "mission_context": make_planner_mission_context(baseline_result_data),
                "retrieval_result": make_planner_retrieval_result(),
                "generation_result": generation,
                "preflight": preflight,
            },
        )


def test_generation_result_schema_version_required(
    baseline_result_data: Any,
) -> None:
    generation = _generation(baseline_result_data)
    assert generation.schema_version == PLANNER_SCHEMA_VERSION
