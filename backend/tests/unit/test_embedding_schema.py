# Phase 4 Step 2 embedding schema contract tests
from __future__ import annotations

import pytest
from app.schemas.actions import ActionType
from app.schemas.api import ErrorCode
from app.schemas.embedding import (
    EMBEDDING_SCHEMA_VERSION,
    EmbeddedChunk,
    EmbeddingIndexSnapshot,
    EmbeddingModelDescriptor,
)
from app.schemas.retrieval import (
    CORPUS_SCHEMA_VERSION,
    EvidenceReference,
    ProcedureChunk,
    ProcedureStatus,
    SourceClassification,
)
from pydantic import ValidationError

_SHA = "a" * 64
_SHA_B = "b" * 64
_SHA_C = "c" * 64


def _evidence() -> EvidenceReference:
    return EvidenceReference(
        evidence_id="EVID-ARES_ASM-001",
        classification=SourceClassification.ARES_ASSUMPTION,
        source_title="Test",
        locator="unit-test",
        supports="Unit test evidence.",
        url="",
    )


def _chunk(**overrides: object) -> ProcedureChunk:
    payload: dict[str, object] = {
        "schema_version": CORPUS_SCHEMA_VERSION,
        "chunk_id": _SHA,
        "procedure_id": "ARES-PROC-OXY-001",
        "procedure_title": "Test Procedure",
        "manual_path": "docs/procedures/manuals/oxygen_leak.md",
        "section_path": ("Purpose",),
        "section_title": "Purpose",
        "chunk_index": 0,
        "content": "Test content.",
        "embedding_text": "Procedure: Test\n\nTest content.",
        "content_sha256": _SHA_B,
        "manual_sha256": _SHA_C,
        "source_classifications": (SourceClassification.ARES_ASSUMPTION,),
        "evidence_references": (_evidence(),),
        "allowed_actions": (ActionType.ISOLATE_MODULE,),
        "procedure_status": ProcedureStatus.PARTIAL_EVIDENCE,
    }
    payload.update(overrides)
    return ProcedureChunk.model_validate(payload)


def _model(**overrides: object) -> EmbeddingModelDescriptor:
    payload: dict[str, object] = {
        "provider": "fake",
        "model_id": "deterministic-fake",
        "model_revision": "1",
        "dimensions": 4,
    }
    payload.update(overrides)
    return EmbeddingModelDescriptor.model_validate(payload)


def test_error_codes_registered() -> None:
    assert ErrorCode.EMBEDDING_PROVIDER_ERROR.value == "EMBEDDING_PROVIDER_ERROR"
    assert ErrorCode.EMBEDDING_VALIDATION_ERROR.value == "EMBEDDING_VALIDATION_ERROR"


def test_model_rejects_extra_and_invalid_dimensions() -> None:
    with pytest.raises(ValidationError):
        EmbeddingModelDescriptor.model_validate(
            {
                "provider": "fake",
                "model_id": "m",
                "dimensions": 8,
                "extra": True,
            }
        )
    with pytest.raises(ValidationError):
        EmbeddingModelDescriptor.model_validate(
            {
                "provider": "fake",
                "model_id": "m",
                "dimensions": 0,
            }
        )


def test_embedded_chunk_rejects_bool_and_hash_mismatch() -> None:
    chunk = _chunk()
    with pytest.raises(ValidationError):
        EmbeddedChunk.model_validate(
            {
                "chunk": chunk,
                "content_sha256": chunk.content_sha256,
                "embedding_text_sha256": _SHA,
                "vector": (1.0, True, 0.0, 0.0),
            }
        )
    with pytest.raises(ValidationError):
        EmbeddedChunk.model_validate(
            {
                "chunk": chunk,
                "content_sha256": _SHA,
                "embedding_text_sha256": _SHA,
                "vector": (1.0, 0.0, 0.0, 0.0),
            }
        )


def test_snapshot_round_trip_and_consistency() -> None:
    chunk = _chunk()
    embedded = EmbeddedChunk(
        chunk=chunk,
        content_sha256=chunk.content_sha256,
        embedding_text_sha256=_SHA,
        vector=(0.1, 0.2, 0.3, 0.4),
    )
    snap = EmbeddingIndexSnapshot(
        schema_version=EMBEDDING_SCHEMA_VERSION,
        corpus_sha256=_SHA,
        manifest_sha256=_SHA_C,
        embedding_model=_model(),
        vector_dimensions=4,
        embedded_chunks=(embedded,),
        index_sha256=_SHA_B,
        chunk_count=1,
    )
    restored = EmbeddingIndexSnapshot.model_validate(snap.model_dump(mode="json"))
    assert restored.index_sha256 == snap.index_sha256
    with pytest.raises(ValidationError):
        EmbeddingIndexSnapshot(
            schema_version=EMBEDDING_SCHEMA_VERSION,
            corpus_sha256=_SHA,
            manifest_sha256=_SHA_C,
            embedding_model=_model(),
            vector_dimensions=4,
            embedded_chunks=(embedded,),
            index_sha256=_SHA_B,
            chunk_count=2,
        )
