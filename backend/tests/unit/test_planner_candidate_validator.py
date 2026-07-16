# Phase 5 Step 2 planner candidate grounding validator tests
from __future__ import annotations

from typing import Any

import pytest
from app.core.errors import PlannerCandidateUngroundedError
from app.services.planner_candidate_validator import PlannerCandidateValidator
from app.services.planner_prompt import PlannerPromptBuilder
from tests.conftest import (
    make_grounded_recovery_plan,
    make_multi_action_retrieval_result,
    make_planner_generation_result,
    make_planner_model_metadata,
    make_planner_prompt_input,
    make_planner_retrieval_result,
)


def _validator() -> PlannerCandidateValidator:
    return PlannerCandidateValidator()


def _generation_for_retrieval(
    baseline_result_data: Any,
    retrieval: Any,
    *,
    plan: Any | None = None,
) -> Any:
    prompt_input = make_planner_prompt_input(
        baseline_result_data,
        retrieval_overrides={"matches": retrieval.matches},
    )
    package = PlannerPromptBuilder(
        model_metadata=make_planner_model_metadata(),
        max_prompt_characters=120000,
    ).build(prompt_input)
    resolved_plan = plan if plan is not None else make_grounded_recovery_plan()
    return make_planner_generation_result(prompt_package=package, plan=resolved_plan)


def test_validator_success_grounded_plan(
    baseline_result_data: Any,
    sample_plan_data: Any,
) -> None:
    retrieval = make_multi_action_retrieval_result()
    generation = _generation_for_retrieval(
        baseline_result_data,
        retrieval,
        plan=make_grounded_recovery_plan(sample_plan_data),
    )
    preflight = _validator().validate(
        retrieval_result=retrieval,
        generation_result=generation,
    )
    assert preflight.action_count == len(generation.plan.actions)
    assert len(preflight.action_support) == preflight.action_count
    assert preflight.action_support[0].action_type.value == "isolate_module"
    assert preflight.evidence_chunk_ids == tuple(
        match.chunk_id for match in retrieval.matches
    )


def test_validator_preflight_hash_deterministic(
    baseline_result_data: Any,
    sample_plan_data: Any,
) -> None:
    retrieval = make_multi_action_retrieval_result()
    generation = _generation_for_retrieval(
        baseline_result_data,
        retrieval,
        plan=make_grounded_recovery_plan(sample_plan_data),
    )
    first = _validator().validate(
        retrieval_result=retrieval,
        generation_result=generation,
    )
    second = _validator().validate(
        retrieval_result=retrieval,
        generation_result=generation,
    )
    assert first.preflight_sha256 == second.preflight_sha256


def test_validator_rejects_zero_actions(baseline_result_data: Any) -> None:
    from app.schemas.plan import RecoveryPlan

    retrieval = make_planner_retrieval_result()
    plan = RecoveryPlan.model_validate(
        {
            "plan_id": "empty_plan",
            "summary": "No actions",
            "actions": [],
            "rationale": "test",
            "expected_risk": "test",
            "constraints_checked": [],
        },
    )
    generation = _generation_for_retrieval(baseline_result_data, retrieval, plan=plan)
    with pytest.raises(PlannerCandidateUngroundedError):
        _validator().validate(
            retrieval_result=retrieval,
            generation_result=generation,
        )


def test_validator_rejects_unsupported_action(baseline_result_data: Any) -> None:
    from app.schemas.plan import RecoveryPlan

    retrieval = make_planner_retrieval_result()
    plan = RecoveryPlan.model_validate(
        {
            "plan_id": "bad_plan",
            "summary": "Unsupported packet",
            "actions": [{"type": "send_emergency_packet", "start_min": 0}],
            "rationale": "test",
            "expected_risk": "test",
            "constraints_checked": [],
        },
    )
    generation = _generation_for_retrieval(baseline_result_data, retrieval, plan=plan)
    with pytest.raises(PlannerCandidateUngroundedError):
        _validator().validate(
            retrieval_result=retrieval,
            generation_result=generation,
        )


def test_validator_rejects_invented_chunk_id(baseline_result_data: Any) -> None:
    retrieval = make_planner_retrieval_result()
    generation = _generation_for_retrieval(baseline_result_data, retrieval)
    tampered = generation.model_copy(
        update={"evidence_chunk_ids": ("f" * 64,) + generation.evidence_chunk_ids},
    )
    with pytest.raises(PlannerCandidateUngroundedError):
        _validator().validate(
            retrieval_result=retrieval,
            generation_result=tampered,
        )


def test_validator_rejects_invented_procedure_id(baseline_result_data: Any) -> None:
    retrieval = make_planner_retrieval_result()
    generation = _generation_for_retrieval(baseline_result_data, retrieval)
    tampered = generation.model_copy(
        update={"evidence_procedure_ids": ("INVENTED",)},
    )
    with pytest.raises(PlannerCandidateUngroundedError):
        _validator().validate(
            retrieval_result=retrieval,
            generation_result=tampered,
        )


def test_validator_does_not_mutate_plan(
    baseline_result_data: Any,
    sample_plan_data: Any,
) -> None:
    retrieval = make_multi_action_retrieval_result()
    plan = make_grounded_recovery_plan(sample_plan_data)
    before = plan.model_dump(mode="json")
    generation = _generation_for_retrieval(baseline_result_data, retrieval, plan=plan)
    _validator().validate(
        retrieval_result=retrieval,
        generation_result=generation,
    )
    assert plan.model_dump(mode="json") == before
