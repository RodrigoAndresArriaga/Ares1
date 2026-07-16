# Phase 5 Step 2 planner candidate evidence-grounding preflight
# validates retrieval linkage only; simulator remains authoritative
from __future__ import annotations

import hashlib
import json

from app.core.errors import PlannerCandidateUngroundedError
from app.schemas.actions import ActionType
from app.schemas.planner import PlannerGenerationResult
from app.schemas.planning import (
    PLANNING_SCHEMA_VERSION,
    ActionEvidenceSupport,
    PlannerCandidatePreflight,
)
from app.schemas.retrieval_query import ProcedureRetrievalResult


def _canonical_json(value: object) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )


def _retrieval_chunk_ids(result: ProcedureRetrievalResult) -> tuple[str, ...]:
    return tuple(match.chunk_id for match in result.matches)


def _retrieval_procedure_ids(result: ProcedureRetrievalResult) -> tuple[str, ...]:
    return tuple(match.chunk.procedure_id for match in result.matches)


def _unique_procedure_ids_ordered(ids: tuple[str, ...]) -> tuple[str, ...]:
    seen: set[str] = set()
    ordered: list[str] = []
    for procedure_id in ids:
        if procedure_id not in seen:
            seen.add(procedure_id)
            ordered.append(procedure_id)
    return tuple(ordered)


def _compute_preflight_hash(
    *,
    schema_version: str,
    plan_dump: dict[str, object],
    action_support: tuple[ActionEvidenceSupport, ...],
    evidence_chunk_ids: tuple[str, ...],
    evidence_procedure_ids: tuple[str, ...],
) -> str:
    record = {
        "schema_version": schema_version,
        "plan": plan_dump,
        "action_support": [
            item.model_dump(mode="json") for item in action_support
        ],
        "evidence_chunk_ids": list(evidence_chunk_ids),
        "evidence_procedure_ids": list(evidence_procedure_ids),
    }
    payload = _canonical_json(record).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


class PlannerCandidateValidator:
    # Evidence-grounding preflight for one planner candidate RecoveryPlan.

    def validate(
        self,
        *,
        retrieval_result: ProcedureRetrievalResult,
        generation_result: PlannerGenerationResult,
    ) -> PlannerCandidatePreflight:
        plan = generation_result.plan
        actions = plan.actions
        if len(actions) < 1:
            raise PlannerCandidateUngroundedError(
                "Planner candidate must contain at least one action",
            )

        retrieval_chunk_ids = _retrieval_chunk_ids(retrieval_result)
        retrieval_procedure_ids = _retrieval_procedure_ids(retrieval_result)

        if generation_result.evidence_chunk_ids != retrieval_chunk_ids:
            raise PlannerCandidateUngroundedError(
                "Generation evidence chunk IDs do not match retrieval result order",
            )
        if generation_result.evidence_procedure_ids != retrieval_procedure_ids:
            raise PlannerCandidateUngroundedError(
                "Generation evidence procedure IDs do not match retrieval result",
            )

        action_support: list[ActionEvidenceSupport] = []
        for index, action in enumerate(actions):
            action_type = ActionType(action.type)
            supporting_chunks: list[str] = []
            supporting_procedures: list[str] = []
            seen_chunks: set[str] = set()
            seen_procedures: set[str] = set()

            for match in retrieval_result.matches:
                if action_type not in match.chunk.allowed_actions:
                    continue
                chunk_id = match.chunk_id
                if chunk_id not in seen_chunks:
                    seen_chunks.add(chunk_id)
                    supporting_chunks.append(chunk_id)
                procedure_id = match.chunk.procedure_id
                if procedure_id not in seen_procedures:
                    seen_procedures.add(procedure_id)
                    supporting_procedures.append(procedure_id)

            if not supporting_chunks:
                raise PlannerCandidateUngroundedError(
                    f"Planner candidate action at index {index} lacks evidence support",
                )

            action_support.append(
                ActionEvidenceSupport(
                    action_index=index,
                    action_type=action_type,
                    supporting_chunk_ids=tuple(supporting_chunks),
                    supporting_procedure_ids=_unique_procedure_ids_ordered(
                        tuple(supporting_procedures),
                    ),
                ),
            )

        preflight = PlannerCandidatePreflight(
            schema_version=PLANNING_SCHEMA_VERSION,
            schema_parsed=True,
            evidence_grounded=True,
            action_count=len(actions),
            action_support=tuple(action_support),
            evidence_chunk_ids=retrieval_chunk_ids,
            evidence_procedure_ids=retrieval_procedure_ids,
            preflight_sha256=_compute_preflight_hash(
                schema_version=PLANNING_SCHEMA_VERSION,
                plan_dump=plan.model_dump(mode="json"),
                action_support=tuple(action_support),
                evidence_chunk_ids=retrieval_chunk_ids,
                evidence_procedure_ids=retrieval_procedure_ids,
            ),
        )
        return preflight
