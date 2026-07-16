# Phase 4 Step 3 retrieval query schema contract tests
from __future__ import annotations

import pytest
from app.core.errors import (
    ARES_HTTP_STATUS_BY_CODE,
    EmbeddingModelMismatchError,
    RetrievalQueryInvalidError,
)
from app.schemas.actions import ActionType
from app.schemas.api import ErrorCode
from app.schemas.embedding import EmbeddingModelDescriptor, RerankerModelDescriptor
from app.schemas.retrieval import (
    CORPUS_SCHEMA_VERSION,
    EvidenceReference,
    ProcedureChunk,
    ProcedureStatus,
    SourceClassification,
)
from app.schemas.retrieval_query import (
    RETRIEVAL_QUERY_SCHEMA_VERSION,
    ProcedureRetrievalMatch,
    ProcedureRetrievalResult,
    RetrievalQueryRequest,
)
from pydantic import ValidationError

_SHA = "a" * 64
_SHA_B = "b" * 64
_SHA_C = "c" * 64
_SHA_D = "d" * 64
_SHA_E = "e" * 64


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


def _model() -> EmbeddingModelDescriptor:
    return EmbeddingModelDescriptor(
        provider="fake",
        model_id="deterministic-fake",
        model_revision="1",
        dimensions=2,
    )


def _reranker() -> RerankerModelDescriptor:
    return RerankerModelDescriptor(
        provider="nvidia",
        model_id="nvidia/llama-nemotron-rerank-1b-v2",
        model_revision=None,
    )


def _match(**overrides: object) -> ProcedureRetrievalMatch:
    chunk = _chunk()
    payload: dict[str, object] = {
        "rank": 1,
        "similarity": 1.0,
        "rerank_score": 2.5,
        "index_position": 0,
        "chunk_id": chunk.chunk_id,
        "chunk": chunk,
    }
    payload.update(overrides)
    return ProcedureRetrievalMatch.model_validate(payload)


def test_error_codes_registered() -> None:
    assert ErrorCode.RETRIEVAL_QUERY_INVALID.value == "RETRIEVAL_QUERY_INVALID"
    assert ErrorCode.EMBEDDING_MODEL_MISMATCH.value == "EMBEDDING_MODEL_MISMATCH"
    assert ARES_HTTP_STATUS_BY_CODE[ErrorCode.RETRIEVAL_QUERY_INVALID] == 400
    assert ARES_HTTP_STATUS_BY_CODE[ErrorCode.EMBEDDING_MODEL_MISMATCH] == 400
    assert RetrievalQueryInvalidError().code == ErrorCode.RETRIEVAL_QUERY_INVALID
    assert EmbeddingModelMismatchError().code == ErrorCode.EMBEDDING_MODEL_MISMATCH
    assert ErrorCode.RETRIEVAL_INDEX_NOT_FOUND.value == "RETRIEVAL_INDEX_NOT_FOUND"
    assert ErrorCode.NVIDIA_NIM_TIMEOUT.value == "NVIDIA_NIM_TIMEOUT"
    assert ErrorCode.RERANK_RESPONSE_INVALID.value == "RERANK_RESPONSE_INVALID"


def test_match_rejects_extra_and_chunk_id_mismatch() -> None:
    chunk = _chunk()
    with pytest.raises(ValidationError):
        ProcedureRetrievalMatch.model_validate(
            {
                "rank": 1,
                "similarity": 0.5,
                "rerank_score": 1.0,
                "index_position": 0,
                "chunk_id": chunk.chunk_id,
                "chunk": chunk,
                "extra": True,
            }
        )
    with pytest.raises(ValidationError):
        ProcedureRetrievalMatch.model_validate(
            {
                "rank": 1,
                "similarity": 0.5,
                "rerank_score": 1.0,
                "index_position": 0,
                "chunk_id": _SHA_B,
                "chunk": chunk,
            }
        )


def test_result_rejects_bad_counts_and_ranks() -> None:
    match = _match()
    with pytest.raises(ValidationError):
        ProcedureRetrievalResult.model_validate(
            {
                "schema_version": RETRIEVAL_QUERY_SCHEMA_VERSION,
                "query": "oxygen leak",
                "requested_top_k": 1,
                "returned_count": 2,
                "embedding_model": _model(),
                "reranker_model": _reranker(),
                "corpus_sha256": _SHA_D,
                "index_sha256": _SHA_E,
                "matches": (match,),
            }
        )
    with pytest.raises(ValidationError):
        ProcedureRetrievalResult.model_validate(
            {
                "schema_version": RETRIEVAL_QUERY_SCHEMA_VERSION,
                "query": "oxygen leak",
                "requested_top_k": 1,
                "returned_count": 1,
                "embedding_model": _model(),
                "reranker_model": _reranker(),
                "corpus_sha256": _SHA_D,
                "index_sha256": _SHA_E,
                "matches": (_match(rank=2),),
            }
        )


def test_valid_result_round_trip() -> None:
    match = _match()
    result = ProcedureRetrievalResult(
        schema_version=RETRIEVAL_QUERY_SCHEMA_VERSION,
        query="oxygen leak",
        requested_top_k=3,
        returned_count=1,
        embedding_model=_model(),
        reranker_model=_reranker(),
        corpus_sha256=_SHA_D,
        index_sha256=_SHA_E,
        matches=(match,),
    )
    assert result.matches[0].chunk.allowed_actions == (ActionType.ISOLATE_MODULE,)
    assert result.matches[0].rerank_score == 2.5
    assert result.schema_version == RETRIEVAL_QUERY_SCHEMA_VERSION


def test_request_forbids_extra_and_empty_query() -> None:
    with pytest.raises(ValidationError):
        RetrievalQueryRequest.model_validate({"query": "ok", "model_id": "x"})
    with pytest.raises(ValidationError):
        RetrievalQueryRequest.model_validate({"query": ""})
    req = RetrievalQueryRequest.model_validate({"query": "oxygen leak", "top_k": 3})
    assert req.top_k == 3
