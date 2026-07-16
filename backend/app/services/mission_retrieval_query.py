# Phase 5 Step 2 deterministic mission retrieval query construction
# backend-owned query text; no client input or diagnosis inference
from __future__ import annotations

import json

from app.core.errors import MissionRetrievalQueryTooLargeError
from app.schemas.planner import PlannerMissionContext


def _canonical_json(value: object) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )


class MissionRetrievalQueryBuilder:
    # Build a deterministic retrieval query from authoritative mission context.

    def __init__(self, *, max_query_characters: int) -> None:
        if max_query_characters <= 0:
            raise ValueError("max_query_characters must be positive")
        self._max_query_characters = max_query_characters

    def build(self, context: PlannerMissionContext) -> str:
        failure_reasons_json = _canonical_json(context.baseline_failure_reasons)
        metrics_json = _canonical_json(
            context.baseline_metrics.model_dump(mode="json"),
        )
        telemetry_json = _canonical_json(
            context.current_telemetry.model_dump(mode="json"),
        )
        query = (
            "ARES-1 Mars habitat emergency procedure retrieval.\n\n"
            f"Scenario ID: {context.scenario_id}\n"
            f"Baseline outcome: {context.baseline_outcome.value}\n"
            f"Baseline failure reasons: {failure_reasons_json}\n"
            f"Current telemetry sample: {context.current_sample_index} "
            f"of {context.telemetry_sample_count}\n"
            f"Baseline metrics: {metrics_json}\n"
            f"Current telemetry: {telemetry_json}\n\n"
            "Retrieve the approved procedures and action guidance relevant to the\n"
            "authoritative mission state above."
        )
        if len(query) > self._max_query_characters:
            raise MissionRetrievalQueryTooLargeError(
                "Mission retrieval query exceeds configured maximum size",
                session_id=context.session_id,
            )
        return query
