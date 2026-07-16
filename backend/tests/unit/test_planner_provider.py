# Phase 5 Step 1 planner provider and strict JSON parser tests
from __future__ import annotations

import json
from typing import Any

import httpx
import pytest
from app.core.errors import (
    NvidiaNimAuthError,
    NvidiaNimResponseInvalidError,
    NvidiaNimUnavailableError,
    PlannerModelMismatchError,
    PlannerOutputInvalidError,
    PlannerResponseIncompleteError,
)
from app.integrations.nvidia_nim import NvidiaNimClient
from app.schemas.embedding import EmbeddingModelDescriptor, RerankerModelDescriptor
from app.services.planner_prompt import PlannerPromptBuilder
from app.services.planner_provider import (
    NvidiaNimPlannerProvider,
    parse_planner_response_content,
)
from tests.conftest import (
    make_planner_model_metadata,
    make_planner_prompt_input,
)

CHAT_URL = "https://integrate.api.nvidia.com/v1/chat/completions"
API_KEY = "test-secret-key-do-not-leak"
MODEL_ID = "nvidia/llama-3.3-nemotron-super-49b-v1"


def _embed_model() -> EmbeddingModelDescriptor:
    return EmbeddingModelDescriptor(
        provider="nvidia",
        model_id="nvidia/llama-nemotron-embed-1b-v2",
        model_revision=None,
        dimensions=4,
    )


def _rerank_model() -> RerankerModelDescriptor:
    return RerankerModelDescriptor(
        provider="nvidia",
        model_id="nvidia/llama-nemotron-rerank-1b-v2",
        model_revision=None,
    )


def _client(handler: httpx.MockTransport) -> NvidiaNimClient:
    return NvidiaNimClient(
        api_key=API_KEY,
        embed_base_url="https://integrate.api.nvidia.com/v1",
        rerank_base_url="https://ai.api.nvidia.com/v1",
        embed_model=_embed_model(),
        rerank_model=_rerank_model(),
        timeout_seconds=5.0,
        max_retries=2,
        retry_backoff_seconds=0.01,
        transport=handler,
    )


def _chat_response(
    *,
    content: str,
    finish_reason: str | None = "stop",
    model: str = MODEL_ID,
) -> dict[str, object]:
    return {
        "id": "chatcmpl-test",
        "object": "chat.completion",
        "created": 1,
        "model": model,
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": content},
                "finish_reason": finish_reason,
            },
        ],
        "usage": {
            "prompt_tokens": 10,
            "completion_tokens": 20,
            "total_tokens": 30,
        },
    }


def _prompt_package(baseline_result_data: Any) -> Any:
    builder = PlannerPromptBuilder(
        model_metadata=make_planner_model_metadata(),
        max_prompt_characters=120000,
    )
    return builder.build(make_planner_prompt_input(baseline_result_data))


def test_parser_accepts_sample_plan_json(sample_plan_data: Any) -> None:
    text = json.dumps(sample_plan_data, separators=(",", ":"))
    plan = parse_planner_response_content(text)
    assert plan.plan_id == "sample_plan"


def test_parser_accepts_invalid_plan_json(invalid_plan_data: Any) -> None:
    text = json.dumps(invalid_plan_data)
    plan = parse_planner_response_content(text)
    assert plan.actions[0].type.value == "send_emergency_packet"


def test_parser_rejects_markdown_fences(sample_plan_data: Any) -> None:
    text = "```json\n" + json.dumps(sample_plan_data) + "\n```"
    with pytest.raises(PlannerOutputInvalidError):
        parse_planner_response_content(text)


def test_parser_rejects_prefix_prose(sample_plan_data: Any) -> None:
    text = "Here is the plan:\n" + json.dumps(sample_plan_data)
    with pytest.raises(PlannerOutputInvalidError):
        parse_planner_response_content(text)


def test_parser_rejects_array_root() -> None:
    with pytest.raises(PlannerOutputInvalidError):
        parse_planner_response_content("[]")


def test_parser_rejects_null_root() -> None:
    with pytest.raises(PlannerOutputInvalidError):
        parse_planner_response_content("null")


def test_parser_rejects_simulator_owned_field(sample_plan_data: Any) -> None:
    payload = dict(sample_plan_data)
    payload["outcome"] = "STABILIZED"
    with pytest.raises(PlannerOutputInvalidError):
        parse_planner_response_content(json.dumps(payload))


def test_parser_rejects_unknown_action() -> None:
    payload = {
        "plan_id": "x",
        "summary": "s",
        "actions": [{"type": "unsupported_action", "start_min": 0}],
        "rationale": "r",
        "expected_risk": "e",
        "constraints_checked": [],
    }
    with pytest.raises(PlannerOutputInvalidError):
        parse_planner_response_content(json.dumps(payload))


def test_parser_rejects_duplicate_keys(sample_plan_data: Any) -> None:
    text = (
        '{"plan_id":"sample_plan","plan_id":"dup","summary":"s","actions":[],'
        '"rationale":"r","expected_risk":"e","constraints_checked":[]}'
    )
    with pytest.raises(PlannerOutputInvalidError):
        parse_planner_response_content(text)


def test_parser_rejects_non_finite_values(sample_plan_data: Any) -> None:
    broken = dict(sample_plan_data)
    broken["actions"] = [
        {
            "type": "reduce_power_load",
            "start_min": 0,
            "percent": float("nan"),
            "load_groups": ["discretionary"],
        },
    ]
    with pytest.raises(PlannerOutputInvalidError):
        parse_planner_response_content(json.dumps(broken))


@pytest.mark.asyncio
async def test_provider_success_contract(
    baseline_result_data: Any,
    sample_plan_data: Any,
) -> None:
    content = json.dumps(sample_plan_data)
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        assert request.url == CHAT_URL
        assert request.headers["Authorization"] == f"Bearer {API_KEY}"
        body = json.loads(request.content.decode("utf-8"))
        assert body["model"] == MODEL_ID
        assert body["stream"] is False
        assert "response_format" not in body
        assert len(body["messages"]) == 2
        return httpx.Response(200, json=_chat_response(content=content))

    provider = NvidiaNimPlannerProvider(
        client=_client(httpx.MockTransport(handler)),
        model_metadata=make_planner_model_metadata(),
        temperature=0.0,
        max_tokens=4096,
    )
    package = _prompt_package(baseline_result_data)
    result = await provider.generate_plan(package)
    assert len(calls) == 1
    assert result.plan.plan_id == "sample_plan"
    assert result.prompt_sha256 == package.prompt_sha256
    assert result.evidence_chunk_ids == package.evidence_chunk_ids
    assert result.finish_reason == "stop"
    assert len(result.response_sha256) == 64


@pytest.mark.asyncio
async def test_provider_rejects_length_finish_reason(
    baseline_result_data: Any,
    sample_plan_data: Any,
) -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json=_chat_response(
                content=json.dumps(sample_plan_data),
                finish_reason="length",
            ),
        )

    provider = NvidiaNimPlannerProvider(
        client=_client(httpx.MockTransport(handler)),
        model_metadata=make_planner_model_metadata(),
        temperature=0.0,
        max_tokens=4096,
    )
    with pytest.raises(PlannerResponseIncompleteError):
        await provider.generate_plan(_prompt_package(baseline_result_data))


@pytest.mark.asyncio
async def test_provider_rejects_model_mismatch(
    baseline_result_data: Any,
    sample_plan_data: Any,
) -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json=_chat_response(
                content=json.dumps(sample_plan_data),
                model="other/model",
            ),
        )

    provider = NvidiaNimPlannerProvider(
        client=_client(httpx.MockTransport(handler)),
        model_metadata=make_planner_model_metadata(),
        temperature=0.0,
        max_tokens=4096,
    )
    with pytest.raises(PlannerModelMismatchError):
        await provider.generate_plan(_prompt_package(baseline_result_data))


@pytest.mark.asyncio
async def test_provider_invalid_json_no_retry(
    baseline_result_data: Any,
) -> None:
    call_count = 0

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        return httpx.Response(
            200,
            json=_chat_response(content="not json at all"),
        )

    provider = NvidiaNimPlannerProvider(
        client=_client(httpx.MockTransport(handler)),
        model_metadata=make_planner_model_metadata(),
        temperature=0.0,
        max_tokens=4096,
    )
    with pytest.raises(PlannerOutputInvalidError):
        await provider.generate_plan(_prompt_package(baseline_result_data))
    assert call_count == 1


@pytest.mark.asyncio
async def test_provider_retries_429(
    baseline_result_data: Any,
    sample_plan_data: Any,
) -> None:
    attempts = {"count": 0}

    def handler(_request: httpx.Request) -> httpx.Response:
        attempts["count"] += 1
        if attempts["count"] < 3:
            return httpx.Response(429, json={"error": "rate limited"})
        return httpx.Response(
            200,
            json=_chat_response(content=json.dumps(sample_plan_data)),
        )

    provider = NvidiaNimPlannerProvider(
        client=_client(httpx.MockTransport(handler)),
        model_metadata=make_planner_model_metadata(),
        temperature=0.0,
        max_tokens=4096,
    )
    await provider.generate_plan(_prompt_package(baseline_result_data))
    assert attempts["count"] == 3


@pytest.mark.asyncio
async def test_provider_no_retry_on_401(
    baseline_result_data: Any,
) -> None:
    attempts = {"count": 0}

    def handler(_request: httpx.Request) -> httpx.Response:
        attempts["count"] += 1
        return httpx.Response(401, json={"error": "unauthorized"})

    provider = NvidiaNimPlannerProvider(
        client=_client(httpx.MockTransport(handler)),
        model_metadata=make_planner_model_metadata(),
        temperature=0.0,
        max_tokens=4096,
    )
    with pytest.raises(NvidiaNimAuthError):
        await provider.generate_plan(_prompt_package(baseline_result_data))
    assert attempts["count"] == 1


@pytest.mark.asyncio
async def test_provider_no_retry_on_400(
    baseline_result_data: Any,
) -> None:
    attempts = {"count": 0}

    def handler(_request: httpx.Request) -> httpx.Response:
        attempts["count"] += 1
        return httpx.Response(400, json={"error": "bad request"})

    provider = NvidiaNimPlannerProvider(
        client=_client(httpx.MockTransport(handler)),
        model_metadata=make_planner_model_metadata(),
        temperature=0.0,
        max_tokens=4096,
    )
    with pytest.raises(NvidiaNimUnavailableError):
        await provider.generate_plan(_prompt_package(baseline_result_data))
    assert attempts["count"] == 1


def test_chat_completion_parse_rejects_multiple_choices() -> None:
    client = _client(
        httpx.MockTransport(
            lambda _request: httpx.Response(
                200,
                json={
                    "model": MODEL_ID,
                    "choices": [
                        {
                            "index": 0,
                            "message": {"role": "assistant", "content": "{}"},
                        },
                        {
                            "index": 1,
                            "message": {"role": "assistant", "content": "{}"},
                        },
                    ],
                    "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
                },
            ),
        ),
    )
    with pytest.raises(NvidiaNimResponseInvalidError):
        client.create_chat_completion(
            model_id=MODEL_ID,
            messages=[{"role": "user", "content": "hi"}],
            temperature=0.0,
            max_tokens=10,
        )


def test_api_key_not_in_error_or_repr(
    baseline_result_data: Any,
    sample_plan_data: Any,
    caplog: pytest.LogCaptureFixture,
) -> None:
    import logging

    caplog.set_level(logging.INFO, logger="ares.planner_provider")

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json=_chat_response(content=json.dumps(sample_plan_data)),
        )

    provider = NvidiaNimPlannerProvider(
        client=_client(httpx.MockTransport(handler)),
        model_metadata=make_planner_model_metadata(),
        temperature=0.0,
        max_tokens=4096,
    )
    import asyncio

    asyncio.run(provider.generate_plan(_prompt_package(baseline_result_data)))
    joined = caplog.text
    assert API_KEY not in joined
    assert "Bearer" not in joined
    assert "Authorization" not in joined
    assert "Ignore previous instructions" not in joined
    repr_text = repr(_client(httpx.MockTransport(handler)))
    assert API_KEY not in repr_text
