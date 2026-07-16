# Phase 4 Step 3 NVIDIA NIM client unit tests with mocked HTTP
from __future__ import annotations

import json

import httpx
import pytest
from app.core.errors import (
    NvidiaNimAuthError,
    NvidiaNimResponseInvalidError,
    NvidiaNimTimeoutError,
    NvidiaNimUnavailableError,
    RerankResponseInvalidError,
)
from app.integrations.nvidia_nim import NvidiaNimClient
from app.schemas.embedding import EmbeddingModelDescriptor, RerankerModelDescriptor

EMBED_URL = "https://integrate.api.nvidia.com/v1/embeddings"
RERANK_URL = (
    "https://ai.api.nvidia.com/v1/retrieval/nvidia/"
    "llama-nemotron-rerank-1b-v2/reranking"
)
API_KEY = "test-secret-key-do-not-leak"


def _embed_model(dimensions: int = 4) -> EmbeddingModelDescriptor:
    return EmbeddingModelDescriptor(
        provider="nvidia",
        model_id="nvidia/llama-nemotron-embed-1b-v2",
        model_revision=None,
        dimensions=dimensions,
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


def _embedding_response(
    vectors: list[list[float]],
    *,
    shuffle_indices: bool = False,
) -> dict[str, object]:
    items = []
    indices = list(range(len(vectors)))
    if shuffle_indices:
        indices = list(reversed(indices))
    for index in indices:
        items.append(
            {
                "index": index,
                "embedding": vectors[index],
                "object": "embedding",
            }
        )
    return {
        "object": "list",
        "data": items,
        "model": "nvidia/llama-nemotron-embed-1b-v2",
        "usage": {"prompt_tokens": 1, "total_tokens": 1},
    }


def test_embed_request_structure_and_ordering() -> None:
    seen: list[dict[str, object]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url == EMBED_URL
        assert request.headers["Authorization"] == f"Bearer {API_KEY}"
        body = json.loads(request.content.decode("utf-8"))
        seen.append(body)
        vectors = [[0.1, 0.2, 0.3, 0.4], [0.5, 0.6, 0.7, 0.8]]
        return httpx.Response(200, json=_embedding_response(vectors, shuffle_indices=True))

    with _client(httpx.MockTransport(handler)) as client:
        result = client.embedding_provider.embed(
            ["doc-a", "doc-b"],
            input_type="passage",
        )
    assert seen[0]["model"] == "nvidia/llama-nemotron-embed-1b-v2"
    assert seen[0]["input_type"] == "passage"
    assert seen[0]["encoding_format"] == "float"
    assert seen[0]["truncate"] == "NONE"
    assert seen[0]["input"] == ["doc-a", "doc-b"]
    assert "dimensions" not in seen[0]
    assert result == ((0.1, 0.2, 0.3, 0.4), (0.5, 0.6, 0.7, 0.8))


def test_query_embedding_uses_query_input_type() -> None:
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content.decode("utf-8"))
        seen.append(body["input_type"])
        return httpx.Response(
            200,
            json=_embedding_response([[0.1, 0.2, 0.3, 0.4]]),
        )

    with _client(httpx.MockTransport(handler)) as client:
        client.embedding_provider.embed(["query text"], input_type="query")
    assert seen == ["query"]


def test_malformed_embedding_response() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"data": "bad"})

    with _client(httpx.MockTransport(handler)) as client:
        with pytest.raises(NvidiaNimResponseInvalidError):
            client.embedding_provider.embed(["x"], input_type="passage")


def test_auth_errors_do_not_retry() -> None:
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(401, json={"detail": "no"})

    with _client(httpx.MockTransport(handler)) as client:
        with pytest.raises(NvidiaNimAuthError):
            client.embedding_provider.embed(["x"], input_type="passage")
    assert calls["n"] == 1


def test_429_and_5xx_retry() -> None:
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] < 3:
            return httpx.Response(429, json={"detail": "slow"})
        return httpx.Response(
            200,
            json=_embedding_response([[0.1, 0.2, 0.3, 0.4]]),
        )

    with _client(httpx.MockTransport(handler)) as client:
        result = client.embedding_provider.embed(["x"], input_type="passage")
    assert calls["n"] == 3
    assert result[0][0] == 0.1

    calls["n"] = 0

    def fail_5xx(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(503, json={"detail": "down"})

    with _client(httpx.MockTransport(fail_5xx)) as client:
        with pytest.raises(NvidiaNimUnavailableError):
            client.embedding_provider.embed(["x"], input_type="passage")
    assert calls["n"] == 3


def test_timeout() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("timeout", request=request)

    with _client(httpx.MockTransport(handler)) as client:
        with pytest.raises(NvidiaNimTimeoutError):
            client.embedding_provider.embed(["x"], input_type="passage")


def test_api_key_absent_from_repr_and_errors() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError(f"Bearer {API_KEY} failed", request=request)

    with _client(httpx.MockTransport(handler)) as client:
        assert API_KEY not in repr(client)
        with pytest.raises(NvidiaNimUnavailableError) as exc_info:
            client.embedding_provider.embed(["x"], input_type="passage")
        assert API_KEY not in str(exc_info.value)
        assert API_KEY not in exc_info.value.message


def test_rerank_request_order_and_score_remap() -> None:
    seen: list[dict[str, object]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == RERANK_URL
        body = json.loads(request.content.decode("utf-8"))
        seen.append(body)
        return httpx.Response(
            200,
            json={
                "rankings": [
                    {"index": 2, "logit": 9.0},
                    {"index": 0, "logit": 1.0},
                    {"index": 1, "logit": 5.0},
                ],
                "usage": {"prompt_tokens": 1, "total_tokens": 1},
            },
        )

    with _client(httpx.MockTransport(handler)) as client:
        scores = client.reranker.rerank(
            query="q",
            documents=["a", "b", "c"],
        )
    assert seen[0]["query"] == {"text": "q"}
    assert seen[0]["passages"] == [{"text": "a"}, {"text": "b"}, {"text": "c"}]
    assert scores == (1.0, 5.0, 9.0)


def test_rerank_rejects_nonfinite_and_count_mismatch() -> None:
    def nonfinite(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            content=b'{"rankings":[{"index":0,"logit":NaN}]}',
            headers={"Content-Type": "application/json"},
        )

    with _client(httpx.MockTransport(nonfinite)) as client:
        with pytest.raises((RerankResponseInvalidError, NvidiaNimResponseInvalidError)):
            client.reranker.rerank(query="q", documents=["a"])

    def mismatch(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"rankings": [{"index": 0, "logit": 1.0}]},
        )

    with _client(httpx.MockTransport(mismatch)) as client:
        with pytest.raises(RerankResponseInvalidError):
            client.reranker.rerank(query="q", documents=["a", "b"])
