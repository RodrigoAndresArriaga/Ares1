# Phase 4 Step 3 query embedding, cosine candidates, mandatory NVIDIA rerank
from __future__ import annotations

import logging
import math
from collections.abc import Sequence

from app.core.errors import (
    EmbeddingModelMismatchError,
    EmbeddingProviderError,
    EmbeddingValidationError,
    NvidiaNimAuthError,
    NvidiaNimRateLimitedError,
    NvidiaNimResponseInvalidError,
    NvidiaNimTimeoutError,
    NvidiaNimUnavailableError,
    RerankResponseInvalidError,
    RetrievalQueryInvalidError,
)
from app.core.logging import log_run_event
from app.integrations.nvidia_nim import RerankerProvider
from app.schemas.embedding import (
    EmbeddingIndexSnapshot,
    EmbeddingModelDescriptor,
    RerankerModelDescriptor,
)
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
    # Rank index chunks by cosine candidates then mandatory rerank scores.
    def __init__(
        self,
        *,
        index: EmbeddingIndexSnapshot,
        provider: EmbeddingProvider,
        reranker: RerankerProvider,
        rerank_candidate_count: int,
        max_top_k: int,
    ) -> None:
        if max_top_k < 1:
            raise RetrievalQueryInvalidError("max_top_k must be >= 1")
        if rerank_candidate_count < max_top_k:
            raise RetrievalQueryInvalidError(
                "rerank_candidate_count must be >= max_top_k",
            )
        self._index = index
        self._provider = provider
        self._reranker = reranker
        self._rerank_candidate_count = rerank_candidate_count
        self._max_top_k = max_top_k

    def retrieve(
        self,
        *,
        query: str,
        top_k: int | None = None,
    ) -> ProcedureRetrievalResult:
        resolved_top_k = self._max_top_k if top_k is None else top_k
        stripped = self._validate_request(query=query, top_k=resolved_top_k)
        model = self._provider.model
        reranker_model = self._reranker.model
        log_run_event(
            logger,
            logging.INFO,
            "procedure retrieval started",
            event="procedure_retrieval_started",
            index_sha256=self._index.index_sha256,
            corpus_sha256=self._index.corpus_sha256,
            model_id=model.model_id,
            reranker_model_id=reranker_model.model_id,
            top_k=resolved_top_k,
        )
        try:
            result = self._retrieve(
                query=stripped,
                top_k=resolved_top_k,
                model=model,
                reranker_model=reranker_model,
            )
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
                top_k=resolved_top_k,
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
        reranker_model: RerankerModelDescriptor,
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
        candidate_limit = min(self._rerank_candidate_count, len(scored))
        candidates = scored[:candidate_limit]
        if not candidates:
            return ProcedureRetrievalResult(
                schema_version=RETRIEVAL_QUERY_SCHEMA_VERSION,
                query=query,
                requested_top_k=top_k,
                returned_count=0,
                embedding_model=self._index.embedding_model,
                reranker_model=reranker_model,
                corpus_sha256=self._index.corpus_sha256,
                index_sha256=self._index.index_sha256,
                matches=(),
            )

        candidate_texts = [
            self._index.embedded_chunks[position].chunk.embedding_text
            for _, position in candidates
        ]
        rerank_scores = self._rerank(query=query, documents=candidate_texts)
        if len(rerank_scores) != len(candidates):
            raise EmbeddingValidationError(
                "reranker returned wrong score count",
            )

        reranked: list[tuple[float, float, int]] = []
        for (similarity, position), rerank_score in zip(
            candidates,
            rerank_scores,
            strict=True,
        ):
            reranked.append((float(rerank_score), float(similarity), position))

        # descending rerank, then descending similarity, then ascending position
        reranked.sort(key=lambda item: (-item[0], -item[1], item[2]))
        selected = self._select_with_procedure_coverage(
            reranked,
            top_k=top_k,
        )
        matches: list[ProcedureRetrievalMatch] = []
        for rank, (rerank_score, similarity, position) in enumerate(
            selected,
            start=1,
        ):
            embedded = self._index.embedded_chunks[position]
            matches.append(
                ProcedureRetrievalMatch(
                    rank=rank,
                    similarity=similarity,
                    rerank_score=rerank_score,
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
            reranker_model=reranker_model,
            corpus_sha256=self._index.corpus_sha256,
            index_sha256=self._index.index_sha256,
            matches=tuple(matches),
        )

    def _select_with_procedure_coverage(
        self,
        reranked: list[tuple[float, float, int]],
        *,
        top_k: int,
    ) -> list[tuple[float, float, int]]:
        # Prefer one highest-scoring chunk per procedure, then fill by score.
        # Preserves multi-topic coverage without procedure-specific boosts.
        if not reranked or top_k <= 0:
            return []
        selected: list[tuple[float, float, int]] = []
        selected_positions: set[int] = set()
        seen_procedures: set[str] = set()
        for item in reranked:
            _rerank_score, _similarity, position = item
            procedure_id = self._index.embedded_chunks[position].chunk.procedure_id
            if procedure_id in seen_procedures:
                continue
            selected.append(item)
            selected_positions.add(position)
            seen_procedures.add(procedure_id)
            if len(selected) >= top_k:
                break
        if len(selected) < top_k:
            for item in reranked:
                _rerank_score, _similarity, position = item
                if position in selected_positions:
                    continue
                selected.append(item)
                selected_positions.add(position)
                if len(selected) >= top_k:
                    break
        # final order remains pure score order among the selected set
        selected.sort(key=lambda item: (-item[0], -item[1], item[2]))
        return selected[:top_k]

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
        if top_k > self._max_top_k:
            raise RetrievalQueryInvalidError(
                f"top_k must be <= {self._max_top_k}",
            )
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
            raw = self._provider.embed([query], input_type="query")
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

    def _rerank(
        self,
        *,
        query: str,
        documents: Sequence[str],
    ) -> tuple[float, ...]:
        try:
            scores = self._reranker.rerank(query=query, documents=documents)
        except (
            NvidiaNimAuthError,
            NvidiaNimRateLimitedError,
            NvidiaNimTimeoutError,
            NvidiaNimUnavailableError,
            NvidiaNimResponseInvalidError,
            RerankResponseInvalidError,
            EmbeddingProviderError,
            EmbeddingValidationError,
        ):
            raise
        except Exception as exc:
            raise RerankResponseInvalidError(
                f"reranker raised: {exc}",
            ) from exc
        if not isinstance(scores, Sequence) or isinstance(scores, (str, bytes)):
            raise RerankResponseInvalidError(
                "reranker must return a sequence of scores",
            )
        values: list[float] = []
        for score in scores:
            if not _is_strict_finite_float(score):
                raise RerankResponseInvalidError(
                    "reranker returned a non-finite score",
                )
            values.append(float(score))
        return tuple(values)

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
