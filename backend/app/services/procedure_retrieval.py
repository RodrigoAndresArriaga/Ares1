# Phase 4 Step 3 deterministic query embedding and cosine retrieval
# in-memory over EmbeddingIndexSnapshot; no routes or persistence
from __future__ import annotations

import logging
import math
from collections.abc import Sequence

from app.core.errors import (
    EmbeddingModelMismatchError,
    EmbeddingProviderError,
    EmbeddingValidationError,
    RetrievalQueryInvalidError,
)
from app.core.logging import log_run_event
from app.schemas.embedding import EmbeddingIndexSnapshot, EmbeddingModelDescriptor
from app.schemas.retrieval_query import (
    RETRIEVAL_QUERY_SCHEMA_VERSION,
    ProcedureRetrievalMatch,
    ProcedureRetrievalResult,
)
from app.services.embedding_provider import EmbeddingProvider

logger = logging.getLogger("ares.procedure_retrieval")


def _is_strict_finite_float(value: object) -> bool:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    as_float = float(value)
    return math.isfinite(as_float)


def _vector_norm(vector: Sequence[float]) -> float:
    return math.sqrt(math.fsum(component * component for component in vector))


def _dot_product(left: Sequence[float], right: Sequence[float]) -> float:
    return math.fsum(a * b for a, b in zip(left, right, strict=True))


class ProcedureRetrievalService:
    # Rank index chunks by cosine similarity to an embedded query.
    def __init__(
        self,
        *,
        index: EmbeddingIndexSnapshot,
        provider: EmbeddingProvider,
    ) -> None:
        self._index = index
        self._provider = provider

    def retrieve(
        self,
        *,
        query: str,
        top_k: int,
    ) -> ProcedureRetrievalResult:
        stripped = self._validate_request(query=query, top_k=top_k)
        model = self._provider.model
        log_run_event(
            logger,
            logging.INFO,
            "procedure retrieval started",
            event="procedure_retrieval_started",
            index_sha256=self._index.index_sha256,
            corpus_sha256=self._index.corpus_sha256,
            model_id=model.model_id,
            top_k=top_k,
        )
        try:
            result = self._retrieve(query=stripped, top_k=top_k, model=model)
        except (
            RetrievalQueryInvalidError,
            EmbeddingModelMismatchError,
            EmbeddingValidationError,
            EmbeddingProviderError,
        ):
            log_run_event(
                logger,
                logging.ERROR,
                "procedure retrieval failed",
                event="procedure_retrieval_failed",
                index_sha256=self._index.index_sha256,
                corpus_sha256=self._index.corpus_sha256,
                model_id=model.model_id,
                top_k=top_k,
            )
            raise
        log_run_event(
            logger,
            logging.INFO,
            "procedure retrieval complete",
            event="procedure_retrieval_complete",
            index_sha256=result.index_sha256,
            corpus_sha256=result.corpus_sha256,
            model_id=result.embedding_model.model_id,
            top_k=result.requested_top_k,
            returned_count=result.returned_count,
        )
        return result

    def _retrieve(
        self,
        *,
        query: str,
        top_k: int,
        model: EmbeddingModelDescriptor,
    ) -> ProcedureRetrievalResult:
        self._assert_model_compatible(model)
        query_vector = self._embed_query(query)
        query_norm = _vector_norm(query_vector)
        if query_norm == 0.0:
            raise EmbeddingValidationError("query embedding vector has zero norm")

        scored: list[tuple[float, int]] = []
        for position, embedded in enumerate(self._index.embedded_chunks):
            chunk_norm = _vector_norm(embedded.vector)
            if chunk_norm == 0.0:
                raise EmbeddingValidationError(
                    "indexed embedding vector has zero norm",
                )
            similarity = _dot_product(query_vector, embedded.vector) / (
                query_norm * chunk_norm
            )
            scored.append((similarity, position))

        # descending similarity, then ascending original index position
        scored.sort(key=lambda item: (-item[0], item[1]))
        limit = min(top_k, len(scored))
        matches: list[ProcedureRetrievalMatch] = []
        for rank, (similarity, position) in enumerate(scored[:limit], start=1):
            embedded = self._index.embedded_chunks[position]
            matches.append(
                ProcedureRetrievalMatch(
                    rank=rank,
                    similarity=float(similarity),
                    index_position=position,
                    chunk_id=embedded.chunk.chunk_id,
                    chunk=embedded.chunk,
                )
            )

        return ProcedureRetrievalResult(
            schema_version=RETRIEVAL_QUERY_SCHEMA_VERSION,
            query=query,
            requested_top_k=top_k,
            returned_count=len(matches),
            embedding_model=self._index.embedding_model,
            corpus_sha256=self._index.corpus_sha256,
            index_sha256=self._index.index_sha256,
            matches=tuple(matches),
        )

    def _validate_request(self, *, query: str, top_k: int) -> str:
        if not isinstance(query, str):
            raise RetrievalQueryInvalidError("query must be a string")
        stripped = query.strip()
        if stripped == "":
            raise RetrievalQueryInvalidError("query must be non-empty")
        if isinstance(top_k, bool) or not isinstance(top_k, int):
            raise RetrievalQueryInvalidError("top_k must be a positive integer")
        if top_k <= 0:
            raise RetrievalQueryInvalidError("top_k must be >= 1")
        return stripped

    def _assert_model_compatible(self, model: EmbeddingModelDescriptor) -> None:
        index_model = self._index.embedding_model
        if (
            model.provider != index_model.provider
            or model.model_id != index_model.model_id
            or model.model_revision != index_model.model_revision
            or model.dimensions != index_model.dimensions
            or self._index.vector_dimensions != model.dimensions
        ):
            raise EmbeddingModelMismatchError(
                "embedding provider model does not match index model",
            )

    def _embed_query(self, query: str) -> tuple[float, ...]:
        try:
            raw = self._provider.embed([query])
        except EmbeddingValidationError:
            raise
        except EmbeddingProviderError:
            raise
        except Exception as exc:
            raise EmbeddingProviderError(
                f"embedding provider raised: {exc}",
            ) from exc
        if not isinstance(raw, Sequence) or isinstance(raw, (str, bytes)):
            raise EmbeddingValidationError(
                "provider must return a sequence of vectors",
            )
        if len(raw) != 1:
            raise EmbeddingValidationError(
                "provider must return exactly one query vector",
            )
        return self._validate_vector(
            raw[0],
            expected_dims=self._provider.model.dimensions,
        )

    def _validate_vector(
        self,
        raw: object,
        *,
        expected_dims: int,
    ) -> tuple[float, ...]:
        if raw is None:
            raise EmbeddingValidationError("missing embedding vector")
        if not isinstance(raw, Sequence) or isinstance(raw, (str, bytes)):
            raise EmbeddingValidationError("embedding vector must be a sequence")
        if len(raw) == 0:
            raise EmbeddingValidationError("embedding vector must be non-empty")
        if len(raw) != expected_dims:
            raise EmbeddingValidationError(
                "embedding vector has wrong dimensions",
            )
        values: list[float] = []
        for item in raw:
            if not _is_strict_finite_float(item):
                raise EmbeddingValidationError(
                    "embedding vector contains invalid numeric values",
                )
            values.append(float(item))
        return tuple(values)
