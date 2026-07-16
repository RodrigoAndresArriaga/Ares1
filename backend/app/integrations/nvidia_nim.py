# Phase 4 Step 3 production NVIDIA hosted NIM embed + rerank clients
# Phase 5 Step 1 planner chat/completions on shared transport
# contracts locked in backend/NVIDIA_NIM_CONTRACT.md; no real calls in unit tests
from __future__ import annotations

import logging
import math
import time
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal, Protocol

import httpx

from app.core.errors import (
    NvidiaNimAuthError,
    NvidiaNimRateLimitedError,
    NvidiaNimResponseInvalidError,
    NvidiaNimTimeoutError,
    NvidiaNimUnavailableError,
    RerankResponseInvalidError,
)
from app.schemas.embedding import EmbeddingModelDescriptor, RerankerModelDescriptor
from app.services.embedding_provider import EmbeddingInputType

logger = logging.getLogger("ares.nvidia_nim")

_RETRYABLE_STATUS = frozenset({429, 500, 502, 503, 504})
_AUTH_STATUS = frozenset({401, 403})


@dataclass(frozen=True)
class ChatCompletionResult:
    content: str
    finish_reason: str | None
    model_id: str


class RerankerProvider(Protocol):
    @property
    def model(self) -> RerankerModelDescriptor: ...

    def rerank(
        self,
        *,
        query: str,
        documents: Sequence[str],
    ) -> tuple[float, ...]: ...


def _is_strict_finite_float(value: object) -> bool:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    return math.isfinite(float(value))


def _safe_error_message(exc: BaseException) -> str:
    text = str(exc)
    # Never echo bearer tokens or raw API key material in error messages.
    if "Bearer " in text:
        parts = text.split("Bearer ", 1)
        remainder = parts[1]
        token, sep, tail = remainder.partition(" ")
        text = f"{parts[0]}Bearer ***{sep}{tail}"
    return text


class NvidiaNimClient:
    # Shared sync httpx client for embed and rerank endpoints.
    def __init__(
        self,
        *,
        api_key: str,
        embed_base_url: str,
        rerank_base_url: str,
        embed_model: EmbeddingModelDescriptor,
        rerank_model: RerankerModelDescriptor,
        timeout_seconds: float = 60.0,
        max_retries: int = 2,
        retry_backoff_seconds: float = 0.5,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        if not api_key:
            raise NvidiaNimAuthError("NVIDIA API key is missing")
        self._api_key = api_key
        self._embed_base_url = embed_base_url.rstrip("/")
        self._rerank_base_url = rerank_base_url.rstrip("/")
        self._embed_model = embed_model
        self._rerank_model = rerank_model
        self._timeout_seconds = timeout_seconds
        self._max_retries = max_retries
        self._retry_backoff_seconds = retry_backoff_seconds
        self._client = httpx.Client(
            timeout=timeout_seconds,
            transport=transport,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Accept": "application/json",
                "Content-Type": "application/json",
            },
        )
        self.embedding_provider = NvidiaNimEmbeddingProvider(self)
        self.reranker = NvidiaNimReranker(self)

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> NvidiaNimClient:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    def __repr__(self) -> str:
        return (
            "NvidiaNimClient("
            f"embed_model={self._embed_model.model_id!r}, "
            f"rerank_model={self._rerank_model.model_id!r})"
        )

    def _request_json(
        self,
        *,
        method: Literal["POST"],
        url: str,
        payload: dict[str, object],
    ) -> object:
        attempts = self._max_retries + 1
        last_exc: BaseException | None = None
        for attempt in range(attempts):
            try:
                response = self._client.request(method, url, json=payload)
            except httpx.TimeoutException as exc:
                last_exc = exc
                if attempt + 1 >= attempts:
                    raise NvidiaNimTimeoutError(
                        "NVIDIA NIM request timed out",
                    ) from exc
                time.sleep(self._retry_backoff_seconds * (2**attempt))
                continue
            except httpx.TransportError as exc:
                last_exc = exc
                if attempt + 1 >= attempts:
                    raise NvidiaNimUnavailableError(
                        f"NVIDIA NIM connection failed: {_safe_error_message(exc)}",
                    ) from exc
                time.sleep(self._retry_backoff_seconds * (2**attempt))
                continue

            status = response.status_code
            if status in _AUTH_STATUS:
                raise NvidiaNimAuthError("NVIDIA NIM authentication failed")
            if status == 429:
                if attempt + 1 >= attempts:
                    raise NvidiaNimRateLimitedError("NVIDIA NIM rate limited")
                time.sleep(self._retry_backoff_seconds * (2**attempt))
                continue
            if status in _RETRYABLE_STATUS and status != 429:
                if attempt + 1 >= attempts:
                    raise NvidiaNimUnavailableError(
                        f"NVIDIA NIM unavailable (HTTP {status})",
                    )
                time.sleep(self._retry_backoff_seconds * (2**attempt))
                continue
            if status >= 400:
                raise NvidiaNimUnavailableError(
                    f"NVIDIA NIM request failed (HTTP {status})",
                )
            try:
                return response.json()
            except ValueError as exc:
                raise NvidiaNimResponseInvalidError(
                    "NVIDIA NIM response is not valid JSON",
                ) from exc
        if last_exc is not None:
            raise NvidiaNimUnavailableError(
                f"NVIDIA NIM request failed: {_safe_error_message(last_exc)}",
            ) from last_exc
        raise NvidiaNimUnavailableError("NVIDIA NIM request failed")

    def create_chat_completion(
        self,
        *,
        model_id: str,
        messages: list[dict[str, str]],
        temperature: float,
        max_tokens: int,
        stream: bool = False,
    ) -> ChatCompletionResult:
        payload: dict[str, object] = {
            "model": model_id,
            "messages": messages,
            "stream": stream,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        url = f"{self._embed_base_url}/chat/completions"
        raw = self._request_json(method="POST", url=url, payload=payload)
        return self._parse_chat_completion(raw)

    def _parse_chat_completion(
        self,
        raw: object,
    ) -> ChatCompletionResult:
        if not isinstance(raw, dict):
            raise NvidiaNimResponseInvalidError(
                "chat completion response must be an object",
            )
        response_model = raw.get("model")
        if not isinstance(response_model, str) or not response_model.strip():
            raise NvidiaNimResponseInvalidError(
                "chat completion response missing model",
            )
        choices = raw.get("choices")
        if not isinstance(choices, list):
            raise NvidiaNimResponseInvalidError(
                "chat completion response missing choices",
            )
        if len(choices) != 1:
            raise NvidiaNimResponseInvalidError(
                "chat completion response must contain exactly one choice",
            )
        choice = choices[0]
        if not isinstance(choice, dict):
            raise NvidiaNimResponseInvalidError(
                "chat completion choice must be an object",
            )
        message = choice.get("message")
        if not isinstance(message, dict):
            raise NvidiaNimResponseInvalidError(
                "chat completion choice missing message",
            )
        content = message.get("content")
        if not isinstance(content, str) or not content.strip():
            raise NvidiaNimResponseInvalidError(
                "chat completion assistant content must be a non-empty string",
            )
        finish_reason = choice.get("finish_reason")
        if finish_reason is not None and not isinstance(finish_reason, str):
            raise NvidiaNimResponseInvalidError(
                "chat completion finish_reason must be a string or null",
            )
        return ChatCompletionResult(
            content=content,
            finish_reason=finish_reason,
            model_id=response_model,
        )


class NvidiaNimEmbeddingProvider:
    def __init__(self, client: NvidiaNimClient) -> None:
        self._client = client

    @property
    def model(self) -> EmbeddingModelDescriptor:
        return self._client._embed_model

    def embed(
        self,
        texts: Sequence[str],
        *,
        input_type: EmbeddingInputType = "passage",
    ) -> Sequence[Sequence[float]]:
        if input_type not in ("passage", "query"):
            raise NvidiaNimResponseInvalidError("invalid embedding input_type")
        if not texts:
            return ()
        payload: dict[str, object] = {
            "input": list(texts),
            "model": self.model.model_id,
            "input_type": input_type,
            "encoding_format": "float",
            "truncate": "NONE",
        }
        url = f"{self._client._embed_base_url}/embeddings"
        raw = self._client._request_json(method="POST", url=url, payload=payload)
        return self._parse_embeddings(raw, expected_count=len(texts))

    def _parse_embeddings(
        self,
        raw: object,
        *,
        expected_count: int,
    ) -> tuple[tuple[float, ...], ...]:
        if not isinstance(raw, dict):
            raise NvidiaNimResponseInvalidError(
                "embedding response must be an object",
            )
        data = raw.get("data")
        if not isinstance(data, list):
            raise NvidiaNimResponseInvalidError(
                "embedding response missing data array",
            )
        if len(data) != expected_count:
            raise NvidiaNimResponseInvalidError(
                "embedding response count does not match input count",
            )
        by_index: dict[int, tuple[float, ...]] = {}
        dims = self.model.dimensions
        for item in data:
            if not isinstance(item, dict):
                raise NvidiaNimResponseInvalidError(
                    "embedding data item must be an object",
                )
            index = item.get("index")
            embedding = item.get("embedding")
            if isinstance(index, bool) or not isinstance(index, int):
                raise NvidiaNimResponseInvalidError(
                    "embedding data index must be an integer",
                )
            if index in by_index:
                raise NvidiaNimResponseInvalidError(
                    "duplicate embedding data index",
                )
            if not isinstance(embedding, list):
                raise NvidiaNimResponseInvalidError(
                    "embedding vector must be a list",
                )
            if len(embedding) != dims:
                raise NvidiaNimResponseInvalidError(
                    "embedding vector has wrong dimensions",
                )
            values: list[float] = []
            for component in embedding:
                if not _is_strict_finite_float(component):
                    raise NvidiaNimResponseInvalidError(
                        "embedding vector contains non-finite values",
                    )
                values.append(float(component))
            by_index[index] = tuple(values)
        if set(by_index) != set(range(expected_count)):
            raise NvidiaNimResponseInvalidError(
                "embedding data indices do not cover input order",
            )
        return tuple(by_index[i] for i in range(expected_count))


class NvidiaNimReranker:
    def __init__(self, client: NvidiaNimClient) -> None:
        self._client = client

    @property
    def model(self) -> RerankerModelDescriptor:
        return self._client._rerank_model

    def rerank(
        self,
        *,
        query: str,
        documents: Sequence[str],
    ) -> tuple[float, ...]:
        if not documents:
            return ()
        if len(documents) > 1000:
            raise RerankResponseInvalidError(
                "rerank passage count exceeds documented maximum of 1000",
            )
        payload: dict[str, object] = {
            "model": self.model.model_id,
            "query": {"text": query},
            "passages": [{"text": text} for text in documents],
            "truncate": "END",
        }
        url = (
            f"{self._client._rerank_base_url}/retrieval/nvidia/"
            f"llama-nemotron-rerank-1b-v2/reranking"
        )
        raw = self._client._request_json(method="POST", url=url, payload=payload)
        return self._parse_rankings(raw, expected_count=len(documents))

    def _parse_rankings(
        self,
        raw: object,
        *,
        expected_count: int,
    ) -> tuple[float, ...]:
        if not isinstance(raw, dict):
            raise RerankResponseInvalidError("rerank response must be an object")
        rankings = raw.get("rankings")
        if not isinstance(rankings, list):
            raise RerankResponseInvalidError("rerank response missing rankings")
        if len(rankings) != expected_count:
            raise RerankResponseInvalidError(
                "rerank score count does not match candidate count",
            )
        by_index: dict[int, float] = {}
        for item in rankings:
            if not isinstance(item, dict):
                raise RerankResponseInvalidError("ranking item must be an object")
            index = item.get("index")
            logit = item.get("logit")
            if isinstance(index, bool) or not isinstance(index, int):
                raise RerankResponseInvalidError("ranking index must be an integer")
            if index in by_index:
                raise RerankResponseInvalidError("duplicate ranking index")
            if not _is_strict_finite_float(logit):
                raise RerankResponseInvalidError("ranking logit must be finite")
            assert isinstance(logit, (int, float)) and not isinstance(logit, bool)
            by_index[index] = float(logit)
        if set(by_index) != set(range(expected_count)):
            raise RerankResponseInvalidError(
                "ranking indices do not cover all passages",
            )
        return tuple(by_index[i] for i in range(expected_count))
