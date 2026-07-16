# Phase 5 Step 2 deterministic mission retrieval query tests
from __future__ import annotations

import json
from typing import Any

import pytest
from app.core.errors import MissionRetrievalQueryTooLargeError
from app.services.mission_retrieval_query import MissionRetrievalQueryBuilder
from tests.conftest import make_planner_mission_context


def _builder(*, max_chars: int = 50000) -> MissionRetrievalQueryBuilder:
    return MissionRetrievalQueryBuilder(max_query_characters=max_chars)


def test_query_determinism(baseline_result_data: Any) -> None:
    context = make_planner_mission_context(baseline_result_data)
    first = _builder().build(context)
    second = _builder().build(context)
    assert first == second


def test_query_contains_exact_mission_values(baseline_result_data: Any) -> None:
    context = make_planner_mission_context(baseline_result_data, sample_index=2)
    query = _builder().build(context)
    assert f"Scenario ID: {context.scenario_id}" in query
    assert f"Baseline outcome: {context.baseline_outcome.value}" in query
    assert "Current telemetry sample: 2 of" in query
    assert json.dumps(
        context.baseline_failure_reasons,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ) in query
    assert json.dumps(
        context.baseline_metrics.model_dump(mode="json"),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ) in query
    assert json.dumps(
        context.current_telemetry.model_dump(mode="json"),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ) in query


def test_query_preserves_failure_reasons_and_metrics(baseline_result_data: Any) -> None:
    context = make_planner_mission_context(baseline_result_data)
    query = _builder().build(context)
    for reason in context.baseline_failure_reasons:
        assert reason in query


def test_query_has_no_diagnosis_inference_or_paths(baseline_result_data: Any) -> None:
    context = make_planner_mission_context(baseline_result_data)
    query = _builder().build(context)
    assert "telemetry_history" not in query
    assert "vector" not in query.lower()
    assert "docs/procedures" not in query
    assert "Bearer" not in query
    assert "Oxygen Leak Response" not in query


def test_query_exact_maximum_accepted(baseline_result_data: Any) -> None:
    context = make_planner_mission_context(baseline_result_data)
    query = _builder().build(context)
    exact = MissionRetrievalQueryBuilder(max_query_characters=len(query))
    assert exact.build(context) == query


def test_query_above_maximum_rejected_without_truncation(
    baseline_result_data: Any,
) -> None:
    context = make_planner_mission_context(baseline_result_data)
    full = _builder().build(context)
    with pytest.raises(MissionRetrievalQueryTooLargeError):
        MissionRetrievalQueryBuilder(max_query_characters=len(full) - 1).build(context)
