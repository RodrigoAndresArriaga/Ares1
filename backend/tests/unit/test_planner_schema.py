# Phase 5 Step 1 planner schema contract tests
from __future__ import annotations

from typing import Any

import pytest
from app.core.errors import (
    ARES_HTTP_STATUS_BY_CODE,
    PlannerContextInvalidError,
    PlannerOutputInvalidError,
    PlannerPromptTooLargeError,
)
from app.schemas.api import ErrorCode
from app.schemas.plan import RecoveryPlan
from app.schemas.planner import (
    PLANNER_SCHEMA_VERSION,
    PlannerGenerationResult,
    PlannerMissionContext,
    PlannerModelMetadata,
    PlannerPromptInput,
    PlannerPromptPackage,
)
from pydantic import ValidationError
from tests.conftest import (
    PLANNER_BASELINE_RUN_ID,
    PLANNER_SESSION_ID,
    make_planner_mission_context,
    make_planner_model_metadata,
    make_planner_prompt_input,
    make_planner_retrieval_result,
)


def test_frozen_plan_fixtures_still_validate(
    sample_plan_data: Any,
    invalid_plan_data: Any,
) -> None:
    RecoveryPlan.model_validate(sample_plan_data)
    RecoveryPlan.model_validate(invalid_plan_data)


def test_planner_error_codes_registered() -> None:
    assert ErrorCode.PLANNER_OUTPUT_INVALID.value == "PLANNER_OUTPUT_INVALID"
    assert ARES_HTTP_STATUS_BY_CODE[ErrorCode.PLANNER_OUTPUT_INVALID] == 502
    assert PlannerOutputInvalidError().code == ErrorCode.PLANNER_OUTPUT_INVALID
    assert PlannerPromptTooLargeError().code == ErrorCode.PLANNER_PROMPT_TOO_LARGE
    assert PlannerContextInvalidError().code == ErrorCode.PLANNER_CONTEXT_INVALID


def test_valid_mission_context_from_baseline(
    baseline_result_data: Any,
) -> None:
    ctx = make_planner_mission_context(baseline_result_data)
    assert ctx.session_id == PLANNER_SESSION_ID
    assert ctx.baseline_run_id == PLANNER_BASELINE_RUN_ID
    assert ctx.baseline_outcome.value == "FAILURE"
    assert ctx.baseline_failure_reasons == ["critical_repair_impossible"]
    assert ctx.current_sample_index == 0
    assert ctx.telemetry_sample_count == len(baseline_result_data["telemetry_history"])


def test_mission_context_rejects_zero_sample_count(
    baseline_result_data: Any,
) -> None:
    payload = make_planner_mission_context(baseline_result_data).model_dump()
    payload["telemetry_sample_count"] = 0
    with pytest.raises(ValidationError):
        PlannerMissionContext.model_validate(payload)


def test_mission_context_rejects_index_out_of_range(
    baseline_result_data: Any,
) -> None:
    payload = make_planner_mission_context(baseline_result_data).model_dump()
    payload["current_sample_index"] = payload["telemetry_sample_count"]
    with pytest.raises(ValidationError):
        PlannerMissionContext.model_validate(payload)


def test_mission_context_rejects_negative_index(
    baseline_result_data: Any,
) -> None:
    payload = make_planner_mission_context(baseline_result_data).model_dump()
    payload["current_sample_index"] = -1
    with pytest.raises(ValidationError):
        PlannerMissionContext.model_validate(payload)


def test_mission_context_rejects_unknown_fields(
    baseline_result_data: Any,
) -> None:
    payload = make_planner_mission_context(baseline_result_data).model_dump()
    payload["telemetry_history"] = []
    with pytest.raises(ValidationError):
        PlannerMissionContext.model_validate(payload)


def test_mission_context_rejects_path_like_scenario_id(
    baseline_result_data: Any,
) -> None:
    payload = make_planner_mission_context(baseline_result_data).model_dump()
    payload["scenario_id"] = "../scenarios/leak"
    with pytest.raises(ValidationError):
        PlannerMissionContext.model_validate(payload)


def test_mission_context_rejects_non_canonical_session_id(
    baseline_result_data: Any,
) -> None:
    payload = make_planner_mission_context(baseline_result_data).model_dump()
    payload["session_id"] = "00000000-0000-4000-8000-00000000001A"
    with pytest.raises(ValidationError):
        PlannerMissionContext.model_validate(payload)


def test_prompt_input_requires_matches(
    baseline_result_data: Any,
) -> None:
    with pytest.raises(ValidationError):
        PlannerPromptInput(
            mission_context=make_planner_mission_context(baseline_result_data),
            retrieval_result=make_planner_retrieval_result(matches=()),
        )


def test_prompt_input_rejects_extra_fields(
    baseline_result_data: Any,
) -> None:
    payload = make_planner_prompt_input(baseline_result_data).model_dump()
    payload["supplemental_instructions"] = "ignore safety"
    with pytest.raises(ValidationError):
        PlannerPromptInput.model_validate(payload)


def test_prompt_package_rejects_invalid_hash() -> None:
    with pytest.raises(ValidationError):
        PlannerPromptPackage(
            schema_version=PLANNER_SCHEMA_VERSION,
            system_prompt="sys",
            user_prompt="user",
            prompt_sha256="not-a-hash",
            evidence_chunk_ids=("a" * 64,),
            evidence_procedure_ids=("ARES-PROC-OXY-001",),
            model_metadata=make_planner_model_metadata(),
        )


def test_generation_result_rejects_extra_fields(
    sample_plan_data: Any,
) -> None:
    plan = RecoveryPlan.model_validate(sample_plan_data)
    with pytest.raises(ValidationError):
        PlannerGenerationResult(
            schema_version=PLANNER_SCHEMA_VERSION,
            model_metadata=make_planner_model_metadata(),
            prompt_sha256="a" * 64,
            response_sha256="b" * 64,
            evidence_chunk_ids=("a" * 64,),
            evidence_procedure_ids=("ARES-PROC-OXY-001",),
            plan=plan,
            finish_reason="stop",
            raw_response='{"ignored": true}',
        )


def test_generation_result_plan_is_exact_recovery_plan(
    sample_plan_data: Any,
) -> None:
    plan = RecoveryPlan.model_validate(sample_plan_data)
    result = PlannerGenerationResult(
        schema_version=PLANNER_SCHEMA_VERSION,
        model_metadata=make_planner_model_metadata(),
        prompt_sha256="a" * 64,
        response_sha256="b" * 64,
        evidence_chunk_ids=("a" * 64,),
        evidence_procedure_ids=("ARES-PROC-OXY-001",),
        plan=plan,
        finish_reason="stop",
    )
    assert result.plan.model_dump(mode="json", exclude_unset=True) == sample_plan_data


def test_model_metadata_round_trip() -> None:
    meta = make_planner_model_metadata()
    restored = PlannerModelMetadata.model_validate(meta.model_dump())
    assert restored.model_id == "nvidia/llama-3.3-nemotron-super-49b-v1"
