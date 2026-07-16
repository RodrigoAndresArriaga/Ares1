# Phase 4 Step 2 deterministic embedding index snapshot builder
# validates provider vectors fail-closed; no query search or persistence
from __future__ import annotations

import hashlib
import json
import logging
import math
import struct
from collections.abc import Sequence

from app.core.errors import EmbeddingProviderError, EmbeddingValidationError
from app.core.logging import log_run_event
from app.schemas.embedding import (
    EMBEDDING_SCHEMA_VERSION,
    EmbeddedChunk,
    EmbeddingIndexSnapshot,
    EmbeddingModelDescriptor,
)
from app.schemas.retrieval import ProcedureCorpusSnapshot
from app.services.embedding_provider import EmbeddingProvider

logger = logging.getLogger("ares.embedding_index")


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _canonical_json(value: object) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )


def _vector_sha256(vector: Sequence[float]) -> str:
    packed = struct.pack(f"<{len(vector)}d", *vector)
    return hashlib.sha256(packed).hexdigest()


def _is_strict_finite_float(value: object) -> bool:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    as_float = float(value)
    return math.isfinite(as_float)


class EmbeddingIndexBuilder:
    # Build an immutable in-memory embedding snapshot from a corpus.
    def __init__(
        self,
        *,
        provider: EmbeddingProvider,
        batch_size: int = 32,
    ) -> None:
        if batch_size < 1:
            raise EmbeddingValidationError("batch_size must be >= 1")
        model = provider.model
        if model.dimensions < 1:
            raise EmbeddingValidationError("embedding model dimensions must be >= 1")
        self._provider = provider
        self._batch_size = batch_size

    def build(self, corpus: ProcedureCorpusSnapshot) -> EmbeddingIndexSnapshot:
        model = self._provider.model
        log_run_event(
            logger,
            logging.INFO,
            "embedding index build started",
            event="embedding_index_build_started",
            chunk_count=len(corpus.chunks),
            batch_size=self._batch_size,
            model_id=model.model_id,
        )
        try:
            snapshot = self._build_snapshot(corpus, model)
        except (EmbeddingValidationError, EmbeddingProviderError):
            log_run_event(
                logger,
                logging.ERROR,
                "embedding index build failed",
                event="embedding_index_build_failed",
                chunk_count=len(corpus.chunks),
                model_id=model.model_id,
            )
            raise
        log_run_event(
            logger,
            logging.INFO,
            "embedding index build complete",
            event="embedding_index_build_complete",
            chunk_count=snapshot.chunk_count,
            index_sha256=snapshot.index_sha256,
            model_id=model.model_id,
        )
        return snapshot

    def _build_snapshot(
        self,
        corpus: ProcedureCorpusSnapshot,
        model: EmbeddingModelDescriptor,
    ) -> EmbeddingIndexSnapshot:
        chunks = corpus.chunks
        chunk_ids = [chunk.chunk_id for chunk in chunks]
        if len(chunk_ids) != len(set(chunk_ids)):
            raise EmbeddingValidationError("duplicate chunk_id in corpus")

        texts = [chunk.embedding_text for chunk in chunks]
        raw_vectors = self._embed_all(texts)
        if len(raw_vectors) != len(chunks):
            raise EmbeddingValidationError(
                "provider returned wrong total vector count",
            )

        embedded: list[EmbeddedChunk] = []
        identity_chunks: list[dict[str, object]] = []
        for chunk, raw in zip(chunks, raw_vectors, strict=True):
            vector = self._validate_vector(raw, expected_dims=model.dimensions)
            embedding_text_sha256 = _sha256_text(chunk.embedding_text)
            vector_digest = _vector_sha256(vector)
            embedded.append(
                EmbeddedChunk(
                    chunk=chunk,
                    content_sha256=chunk.content_sha256,
                    embedding_text_sha256=embedding_text_sha256,
                    vector=vector,
                )
            )
            identity_chunks.append(
                {
                    "chunk_id": chunk.chunk_id,
                    "content_sha256": chunk.content_sha256,
                    "embedding_text_sha256": embedding_text_sha256,
                    "vector_sha256": vector_digest,
                }
            )

        index_sha256 = self._compute_index_sha256(
            corpus_sha256=corpus.corpus_sha256,
            model=model,
            embedded_identity=identity_chunks,
        )
        return EmbeddingIndexSnapshot.model_validate(
            {
                "schema_version": EMBEDDING_SCHEMA_VERSION,
                "corpus_sha256": corpus.corpus_sha256,
                "embedding_model": model,
                "vector_dimensions": model.dimensions,
                "embedded_chunks": embedded,
                "index_sha256": index_sha256,
                "chunk_count": len(embedded),
            }
        )

    def _embed_all(self, texts: Sequence[str]) -> list[Sequence[float]]:
        if not texts:
            return []
        combined: list[Sequence[float]] = []
        for start in range(0, len(texts), self._batch_size):
            batch = texts[start : start + self._batch_size]
            try:
                raw = self._provider.embed(batch)
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
            if len(raw) != len(batch):
                raise EmbeddingValidationError(
                    "provider batch result count does not match input count",
                )
            combined.extend(raw)
        return combined

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

    def _compute_index_sha256(
        self,
        *,
        corpus_sha256: str,
        model: EmbeddingModelDescriptor,
        embedded_identity: list[dict[str, object]],
    ) -> str:
        identity = {
            "schema_version": EMBEDDING_SCHEMA_VERSION,
            "corpus_sha256": corpus_sha256,
            "embedding_model": model.model_dump(mode="json"),
            "vector_dimensions": model.dimensions,
            "embedded_chunks": embedded_identity,
        }
        return _sha256_text(_canonical_json(identity))
