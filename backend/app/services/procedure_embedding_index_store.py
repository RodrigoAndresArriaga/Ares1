# Phase 4 Step 3 persistent EmbeddingIndexSnapshot store
# atomic UTF-8 JSON; CWD-independent fixed path; no read-side mutation
from __future__ import annotations

import json
import logging
import math
from pathlib import Path

from pydantic import ValidationError

from app.core.errors import (
    RetrievalIndexCorruptError,
    RetrievalIndexNotFoundError,
    RetrievalIndexStaleError,
    RetrievalIndexUnavailableError,
)
from app.core.logging import log_run_event
from app.schemas.embedding import EmbeddingIndexSnapshot, EmbeddingModelDescriptor
from app.services.run_store import write_json_atomic

logger = logging.getLogger("ares.procedure_embedding_index_store")


def _contains_nonfinite(value: object) -> bool:
    if isinstance(value, float):
        return not math.isfinite(value)
    if isinstance(value, dict):
        return any(_contains_nonfinite(item) for item in value.values())
    if isinstance(value, (list, tuple)):
        return any(_contains_nonfinite(item) for item in value)
    return False


class ProcedureEmbeddingIndexStore:
    # Load and persist a strict EmbeddingIndexSnapshot at a fixed server path.
    def __init__(self, *, index_path: Path) -> None:
        self._index_path = index_path.resolve()

    @property
    def index_path(self) -> Path:
        return self._index_path

    def save(self, snapshot: EmbeddingIndexSnapshot) -> None:
        payload = snapshot.model_dump(mode="json")
        if _contains_nonfinite(payload):
            raise RetrievalIndexCorruptError(
                "embedding index contains non-finite numeric values",
            )
        try:
            write_json_atomic(self._index_path, payload)
        except Exception as exc:
            raise RetrievalIndexUnavailableError(
                "failed to write procedure embedding index",
            ) from exc
        log_run_event(
            logger,
            logging.INFO,
            "procedure embedding index saved",
            event="procedure_embedding_index_saved",
            index_sha256=snapshot.index_sha256,
            corpus_sha256=snapshot.corpus_sha256,
            chunk_count=snapshot.chunk_count,
        )

    def load(self) -> EmbeddingIndexSnapshot:
        path = self._index_path
        if not path.exists():
            raise RetrievalIndexNotFoundError(
                "procedure embedding index file not found",
            )
        if not path.is_file():
            raise RetrievalIndexCorruptError(
                "procedure embedding index path is not a regular file",
            )
        try:
            raw_text = path.read_text(encoding="utf-8")
        except OSError as exc:
            raise RetrievalIndexUnavailableError(
                "failed to read procedure embedding index",
            ) from exc
        try:
            payload = json.loads(raw_text)
        except json.JSONDecodeError as exc:
            raise RetrievalIndexCorruptError(
                "procedure embedding index JSON is malformed",
            ) from exc
        if not isinstance(payload, dict):
            raise RetrievalIndexCorruptError(
                "procedure embedding index root must be an object",
            )
        if _contains_nonfinite(payload):
            raise RetrievalIndexCorruptError(
                "procedure embedding index contains non-finite numeric values",
            )
        try:
            snapshot = EmbeddingIndexSnapshot.model_validate(payload)
        except ValidationError as exc:
            raise RetrievalIndexCorruptError(
                "procedure embedding index failed schema validation",
            ) from exc
        log_run_event(
            logger,
            logging.INFO,
            "procedure embedding index loaded",
            event="procedure_embedding_index_loaded",
            index_sha256=snapshot.index_sha256,
            corpus_sha256=snapshot.corpus_sha256,
            chunk_count=snapshot.chunk_count,
        )
        return snapshot

    def load_compatible(
        self,
        *,
        expected_corpus_sha256: str | None = None,
        expected_manifest_sha256: str | None = None,
        expected_model: EmbeddingModelDescriptor | None = None,
    ) -> EmbeddingIndexSnapshot:
        snapshot = self.load()
        if (
            expected_corpus_sha256 is not None
            and snapshot.corpus_sha256 != expected_corpus_sha256
        ):
            raise RetrievalIndexStaleError(
                "procedure embedding index corpus hash does not match",
            )
        if (
            expected_manifest_sha256 is not None
            and snapshot.manifest_sha256 != expected_manifest_sha256
        ):
            raise RetrievalIndexStaleError(
                "procedure embedding index manifest hash does not match",
            )
        if expected_model is not None:
            index_model = snapshot.embedding_model
            if (
                index_model.provider != expected_model.provider
                or index_model.model_id != expected_model.model_id
                or index_model.model_revision != expected_model.model_revision
                or index_model.dimensions != expected_model.dimensions
                or snapshot.vector_dimensions != expected_model.dimensions
            ):
                raise RetrievalIndexStaleError(
                    "procedure embedding index model does not match provider",
                )
        return snapshot
