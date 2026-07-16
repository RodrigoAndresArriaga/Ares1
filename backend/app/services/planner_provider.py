# Phase 5 Step 1 planner provider and strict JSON parsing
# candidate RecoveryPlan only; no repair or autonomous retry on bad output
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import math
from typing import Protocol

from pydantic import ValidationError

from app.core.errors import (
    PlannerModelMismatchError,
    PlannerOutputInvalidError,
    PlannerResponseIncompleteError,
)
from app.core.logging import log_run_event
from app.integrations.nvidia_nim import NvidiaNimClient
from app.schemas.plan import RecoveryPlan
from app.schemas.planner import (
    PLANNER_SCHEMA_VERSION,
    PlannerGenerationResult,
    PlannerModelMetadata,
    PlannerPromptPackage,
)

logger = logging.getLogger("ares.planner_provider")

_SIMULATOR_OWNED_ROOT_KEYS = frozenset(
    {
        "outcome",
        "valid_plan",
        "metrics",
        "timeline",
        "telemetry_history",
        "failure_reasons",
        "mission_status",
        "survival_probability",
        "success",
        "stabilized",
        "physically_feasible",
        "simulation_result",
        "risk_score",
        "confidence",
        "citations",
        "evidence",
    },
)


def _reject_non_finite(value: object) -> None:
    if isinstance(value, bool):
        return
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("non-finite float value")
        return
    if isinstance(value, dict):
        for item in value.values():
            _reject_non_finite(item)
        return
    if isinstance(value, list):
        for item in value:
            _reject_non_finite(item)


def _no_duplicate_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    keys = [key for key, _value in pairs]
    if len(keys) != len(set(keys)):
        raise ValueError("duplicate JSON object keys")
    return dict(pairs)


def _reject_json_comments(text: str) -> None:
    for marker in ("//", "/*", "*/", "#"):
        if marker in text:
            raise ValueError("JSON comments are forbidden")


def parse_planner_response_content(content: str) -> RecoveryPlan:
    # Strict parser: no repair, no fence stripping, RecoveryPlan validation only.
    if not isinstance(content, str):
        raise PlannerOutputInvalidError("Planner response content must be a string")

    stripped = content.strip()
    if not stripped:
        raise PlannerOutputInvalidError("Planner response content is empty")
    if stripped.startswith("```") or "```" in stripped:
        raise PlannerOutputInvalidError("Planner response must not use Markdown fences")
    if not stripped.startswith("{"):
        raise PlannerOutputInvalidError("Planner response must begin with a JSON object")
    if not stripped.endswith("}"):
        raise PlannerOutputInvalidError("Planner response must end with a JSON object")

    _reject_json_comments(stripped)
    for token in ("NaN", "Infinity", "-Infinity"):
        if token in stripped:
            raise PlannerOutputInvalidError("Planner response contains non-finite values")

    try:
        parsed = json.loads(stripped, object_pairs_hook=_no_duplicate_keys)
    except json.JSONDecodeError as exc:
        raise PlannerOutputInvalidError("Planner response is not valid JSON") from exc
    except ValueError as exc:
        raise PlannerOutputInvalidError("Planner response is not valid JSON") from exc

    if parsed is None:
        raise PlannerOutputInvalidError("Planner response root must not be null")
    if isinstance(parsed, list):
        raise PlannerOutputInvalidError("Planner response root must be a JSON object")
    if not isinstance(parsed, dict):
        raise PlannerOutputInvalidError("Planner response root must be a JSON object")

    if isinstance(parsed, dict):
        for key in parsed:
            if key in _SIMULATOR_OWNED_ROOT_KEYS:
                raise PlannerOutputInvalidError(
                    "Planner response contains simulator-owned fields",
                )

    try:
        _reject_non_finite(parsed)
        return RecoveryPlan.model_validate(parsed)
    except (ValidationError, ValueError) as exc:
        raise PlannerOutputInvalidError("Planner response failed RecoveryPlan validation") from exc


class PlannerProvider(Protocol):
    async def generate_plan(
        self,
        prompt: PlannerPromptPackage,
    ) -> PlannerGenerationResult: ...


class NvidiaNimPlannerProvider:
    # One hosted Nemotron Super request per generate_plan call.
    def __init__(
        self,
        *,
        client: NvidiaNimClient,
        model_metadata: PlannerModelMetadata,
        temperature: float,
        max_tokens: int,
    ) -> None:
        self._client = client
        self._model_metadata = model_metadata
        self._temperature = temperature
        self._max_tokens = max_tokens

    async def generate_plan(
        self,
        prompt: PlannerPromptPackage,
    ) -> PlannerGenerationResult:
        messages = [
            {"role": "system", "content": prompt.system_prompt},
            {"role": "user", "content": prompt.user_prompt},
        ]
        log_run_event(
            logger,
            logging.INFO,
            "planner request started",
            event="planner_request_started",
            model_id=self._model_metadata.model_id,
            prompt_hash=prompt.prompt_sha256,
            evidence_chunk_count=len(prompt.evidence_chunk_ids),
        )
        try:
            completion = await asyncio.to_thread(
                self._client.create_chat_completion,
                model_id=self._model_metadata.model_id,
                messages=messages,
                temperature=self._temperature,
                max_tokens=self._max_tokens,
                stream=False,
            )
        except Exception as exc:
            log_run_event(
                logger,
                logging.WARNING,
                "planner provider transport failure",
                event="planner_provider_transport_failure",
                model_id=self._model_metadata.model_id,
                prompt_hash=prompt.prompt_sha256,
                error_code=getattr(exc, "code", None),
            )
            raise

        if completion.model_id != self._model_metadata.model_id:
            raise PlannerModelMismatchError(
                "Planner response model does not match configured planner model",
            )

        finish_reason = completion.finish_reason
        if finish_reason == "length":
            raise PlannerResponseIncompleteError(
                "Planner response was truncated by token limit",
            )
        if finish_reason is None:
            raise PlannerResponseIncompleteError(
                "Planner response did not finish with a documented stop reason",
            )
        if finish_reason != "stop":
            raise PlannerOutputInvalidError(
                "Planner response has unsupported finish reason",
            )

        content = completion.content
        response_sha256 = hashlib.sha256(content.encode("utf-8")).hexdigest()
        try:
            plan = parse_planner_response_content(content)
        except PlannerOutputInvalidError as exc:
            log_run_event(
                logger,
                logging.WARNING,
                "planner response rejected",
                event="planner_response_rejected",
                model_id=self._model_metadata.model_id,
                prompt_hash=prompt.prompt_sha256,
                response_hash=response_sha256,
                error_code=exc.code.value,
            )
            raise

        log_run_event(
            logger,
            logging.INFO,
            "planner request completed",
            event="planner_request_completed",
            model_id=self._model_metadata.model_id,
            prompt_hash=prompt.prompt_sha256,
            response_hash=response_sha256,
            action_count=len(plan.actions),
        )
        return PlannerGenerationResult(
            schema_version=PLANNER_SCHEMA_VERSION,
            model_metadata=self._model_metadata,
            prompt_sha256=prompt.prompt_sha256,
            response_sha256=response_sha256,
            evidence_chunk_ids=prompt.evidence_chunk_ids,
            evidence_procedure_ids=prompt.evidence_procedure_ids,
            plan=plan,
            finish_reason="stop",
        )
