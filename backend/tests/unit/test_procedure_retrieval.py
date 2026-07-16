# Phase 4 Step 3 procedure retrieval service unit tests
from __future__ import annotations

import math
from collections.abc import Sequence
from pathlib import Path

import pytest
from app.core.errors import (
    EmbeddingModelMismatchError,
    EmbeddingProviderError,
    EmbeddingValidationError,
    RerankResponseInvalidError,
    RetrievalQueryInvalidError,
)
from app.schemas.actions import ActionType
from app.schemas.embedding import (
    EMBEDDING_SCHEMA_VERSION,
    EmbeddedChunk,
    EmbeddingIndexSnapshot,
    EmbeddingModelDescriptor,
    RerankerModelDescriptor,
)
from app.schemas.retrieval import (
    CORPUS_SCHEMA_VERSION,
    EvidenceReference,
    ProcedureChunk,
    ProcedureStatus,
    SourceClassification,
)
from app.schemas.retrieval_query import RETRIEVAL_QUERY_SCHEMA_VERSION
from app.services.embedding_index import EmbeddingIndexBuilder
from app.services.embedding_provider import DeterministicFakeEmbeddingProvider
from app.services.procedure_corpus import ProcedureCorpusBuilder
from app.services.procedure_retrieval import ProcedureRetrievalService

BACKEND_ROOT = Path(__file__).resolve().parents[2]
REPO_ROOT = BACKEND_ROOT.parent
REAL_MANIFEST = REPO_ROOT / "docs" / "procedures" / "corpus_manifest.json"
REAL_MANUALS = REPO_ROOT / "docs" / "procedures" / "manuals"

_SHA = "a" * 64
_SHA_B = "b" * 64
_SHA_C = "c" * 64
_SHA_D = "d" * 64
_SHA_E = "e" * 64
_SHA_F = "f" * 64
_SHA_0 = "0" * 64
_SHA_1 = "1" * 64
_SHA_2 = "2" * 64
_SHA_3 = "3" * 64

EXPECTED_EXCLUDED = (
    "comms_blackout.md",
    "co2_scrubber_failure.md",
)
EXPECTED_REAL_CHUNK_COUNT = 94
DEFAULT_DIMS = 2


def _evidence() -> EvidenceReference:
    return EvidenceReference(
        evidence_id="EVID-ARES_ASM-001",
        classification=SourceClassification.ARES_ASSUMPTION,
        source_title="Test",
        locator="unit-test",
        supports="Unit test evidence.",
        url="",
    )


def _chunk(
    *,
    chunk_id: str = _SHA,
    content_sha256: str = _SHA_B,
    chunk_index: int = 0,
    procedure_id: str = "ARES-PROC-OXY-001",
    procedure_title: str = "Test Procedure",
    section_path: tuple[str, ...] = ("Purpose",),
    content: str | None = None,
) -> ProcedureChunk:
    return ProcedureChunk(
        schema_version=CORPUS_SCHEMA_VERSION,
        chunk_id=chunk_id,
        procedure_id=procedure_id,
        procedure_title=procedure_title,
        manual_path="docs/procedures/manuals/oxygen_leak.md",
        section_path=section_path,
        section_title=section_path[-1] if section_path else "Purpose",
        chunk_index=chunk_index,
        content=content if content is not None else f"content-{chunk_index}",
        embedding_text=f"embed-{chunk_index}",
        content_sha256=content_sha256,
        manual_sha256=_SHA_C,
        source_classifications=(SourceClassification.ARES_ASSUMPTION,),
        evidence_references=(_evidence(),),
        allowed_actions=(ActionType.ISOLATE_MODULE,),
        procedure_status=ProcedureStatus.PARTIAL_EVIDENCE,
    )


def _model(
    *,
    provider: str = "fake",
    model_id: str = "deterministic-fake",
    dimensions: int = DEFAULT_DIMS,
    model_revision: str | None = "1",
) -> EmbeddingModelDescriptor:
    return EmbeddingModelDescriptor(
        provider=provider,
        model_id=model_id,
        model_revision=model_revision,
        dimensions=dimensions,
    )


def _reranker_model() -> RerankerModelDescriptor:
    return RerankerModelDescriptor(
        provider="fake",
        model_id="deterministic-rerank",
        model_revision="1",
    )


def _index(
    vectors: Sequence[Sequence[float]],
    *,
    model: EmbeddingModelDescriptor | None = None,
    chunks: Sequence[ProcedureChunk] | None = None,
) -> EmbeddingIndexSnapshot:
    resolved_model = model or _model(dimensions=len(vectors[0]) if vectors else 2)
    if chunks is None:
        ids = (_SHA, _SHA_0, _SHA_1, _SHA_2, _SHA_3, _SHA_F)
        content_hashes = (_SHA_B, _SHA_D, _SHA_E, _SHA_C, _SHA_F, _SHA_0)
        built_chunks = tuple(
            _chunk(
                chunk_id=ids[i],
                content_sha256=content_hashes[i],
                chunk_index=i,
            )
            for i in range(len(vectors))
        )
    else:
        built_chunks = tuple(chunks)
    if len(built_chunks) != len(vectors):
        raise AssertionError("chunks/vectors length mismatch")
    embedded = tuple(
        EmbeddedChunk(
            chunk=chunk,
            content_sha256=chunk.content_sha256,
            embedding_text_sha256=_SHA_D,
            vector=tuple(float(v) for v in vector),
        )
        for chunk, vector in zip(built_chunks, vectors, strict=True)
    )
    dims = resolved_model.dimensions
    return EmbeddingIndexSnapshot(
        schema_version=EMBEDDING_SCHEMA_VERSION,
        corpus_sha256=_SHA_E,
        manifest_sha256=_SHA_D,
        embedding_model=resolved_model,
        vector_dimensions=dims,
        embedded_chunks=embedded,
        index_sha256=_SHA_F,
        chunk_count=len(embedded),
    )


class ScriptedProvider:
    def __init__(
        self,
        *,
        model: EmbeddingModelDescriptor,
        query_vector: Sequence[float] | None = None,
        query_vectors: Sequence[Sequence[float]] | None = None,
        raise_provider: bool = False,
        raise_typed_provider: bool = False,
    ) -> None:
        self._model = model
        self._query_vector = tuple(query_vector) if query_vector is not None else None
        self._query_vectors = (
            [tuple(row) for row in query_vectors] if query_vectors is not None else None
        )
        self._raise_provider = raise_provider
        self._raise_typed_provider = raise_typed_provider
        self.calls: list[tuple[tuple[str, ...], str]] = []

    @property
    def model(self) -> EmbeddingModelDescriptor:
        return self._model

    def embed(
        self,
        texts: Sequence[str],
        *,
        input_type: str = "passage",
    ) -> Sequence[Sequence[float]]:
        self.calls.append((tuple(texts), input_type))
        if self._raise_typed_provider:
            raise EmbeddingProviderError("typed provider failure")
        if self._raise_provider:
            raise RuntimeError("provider boom")
        if self._query_vectors is not None:
            return self._query_vectors
        if self._query_vector is None:
            raise RuntimeError("no scripted query vector")
        return (self._query_vector,)


class FakeReranker:
    # Default scores preserve candidate order (descending by position).
    def __init__(
        self,
        *,
        scores: Sequence[float] | None = None,
        raise_error: bool = False,
    ) -> None:
        self._scores = tuple(scores) if scores is not None else None
        self._raise_error = raise_error
        self.calls: list[tuple[str, tuple[str, ...]]] = []
        self._model = _reranker_model()

    @property
    def model(self) -> RerankerModelDescriptor:
        return self._model

    def rerank(
        self,
        *,
        query: str,
        documents: Sequence[str],
    ) -> tuple[float, ...]:
        self.calls.append((query, tuple(documents)))
        if self._raise_error:
            raise RerankResponseInvalidError("scripted rerank failure")
        if self._scores is not None:
            return tuple(self._scores[: len(documents)])
        return tuple(float(len(documents) - i) for i in range(len(documents)))


def _service(
    index: EmbeddingIndexSnapshot,
    provider: ScriptedProvider | DeterministicFakeEmbeddingProvider,
    reranker: FakeReranker | None = None,
    *,
    rerank_candidate_count: int = 100,
    max_top_k: int = 100,
) -> ProcedureRetrievalService:
    return ProcedureRetrievalService(
        index=index,
        provider=provider,
        reranker=reranker or FakeReranker(),
        rerank_candidate_count=rerank_candidate_count,
        max_top_k=max_top_k,
    )


def test_cosine_similarity_ordering() -> None:
    model = _model(dimensions=2)
    index = _index(
        ((1.0, 0.0), (1.0, 1.0), (0.0, 1.0), (-1.0, 0.0)),
        model=model,
        chunks=(
            _chunk(chunk_id=_SHA, content_sha256=_SHA_B, chunk_index=0),
            _chunk(chunk_id=_SHA_0, content_sha256=_SHA_D, chunk_index=1),
            _chunk(chunk_id=_SHA_1, content_sha256=_SHA_E, chunk_index=2),
            _chunk(chunk_id=_SHA_2, content_sha256=_SHA_C, chunk_index=3),
        ),
    )
    provider = ScriptedProvider(model=model, query_vector=(1.0, 0.0))
    result = _service(index, provider).retrieve(query="leak", top_k=4)
    assert [m.chunk_id for m in result.matches] == [_SHA, _SHA_0, _SHA_1, _SHA_2]
    assert result.matches[0].similarity == pytest.approx(1.0)
    assert result.matches[1].similarity == pytest.approx(math.sqrt(0.5))
    assert result.matches[2].similarity == pytest.approx(0.0)
    assert result.matches[3].similarity == pytest.approx(-1.0)


def test_rerank_overrides_vector_order() -> None:
    model = _model(dimensions=2)
    index = _index(
        ((1.0, 0.0), (0.5, 0.0), (0.25, 0.0)),
        model=model,
        chunks=(
            _chunk(chunk_id=_SHA, content_sha256=_SHA_B, chunk_index=0),
            _chunk(chunk_id=_SHA_0, content_sha256=_SHA_D, chunk_index=1),
            _chunk(chunk_id=_SHA_1, content_sha256=_SHA_E, chunk_index=2),
        ),
    )
    provider = ScriptedProvider(model=model, query_vector=(1.0, 0.0))
    reranker = FakeReranker(scores=(1.0, 9.0, 5.0))
    result = _service(index, provider, reranker).retrieve(query="override", top_k=3)
    assert [m.chunk_id for m in result.matches] == [_SHA_0, _SHA_1, _SHA]
    assert [m.rerank_score for m in result.matches] == [9.0, 5.0, 1.0]
    assert len(reranker.calls) == 1


def test_rerank_tie_breaks_by_similarity_then_position() -> None:
    model = _model(dimensions=2)
    index = _index(
        ((1.0, 0.0), (0.5, 0.0), (0.5, 0.0)),
        model=model,
        chunks=(
            _chunk(chunk_id=_SHA, content_sha256=_SHA_B, chunk_index=0),
            _chunk(chunk_id=_SHA_0, content_sha256=_SHA_D, chunk_index=1),
            _chunk(chunk_id=_SHA_1, content_sha256=_SHA_E, chunk_index=2),
        ),
    )
    provider = ScriptedProvider(model=model, query_vector=(1.0, 0.0))
    reranker = FakeReranker(scores=(1.0, 5.0, 5.0))
    result = _service(index, provider, reranker).retrieve(query="ties", top_k=3)
    assert [m.chunk_id for m in result.matches] == [_SHA_0, _SHA_1, _SHA]
    assert result.matches[0].index_position == 1
    assert result.matches[1].index_position == 2


def test_only_configured_candidates_reranked() -> None:
    model = _model(dimensions=2)
    index = _index(
        ((1.0, 0.0), (0.8, 0.0), (0.6, 0.0), (0.4, 0.0)),
        model=model,
    )
    provider = ScriptedProvider(model=model, query_vector=(1.0, 0.0))
    reranker = FakeReranker()
    _service(
        index,
        provider,
        reranker,
        rerank_candidate_count=2,
        max_top_k=2,
    ).retrieve(query="cand", top_k=2)
    assert len(reranker.calls) == 1
    assert len(reranker.calls[0][1]) == 2


def test_query_embedding_once_and_input_type_query() -> None:
    model = _model(dimensions=2)
    index = _index(((1.0, 0.0),), model=model)
    provider = ScriptedProvider(model=model, query_vector=(1.0, 0.0))
    _service(index, provider).retrieve(query="  oxygen leak  ", top_k=1)
    assert provider.calls == [(("oxygen leak",), "query")]


def test_no_document_embedding_during_query() -> None:
    model = _model(dimensions=2)
    index = _index(((1.0, 0.0), (0.0, 1.0)), model=model)
    provider = ScriptedProvider(model=model, query_vector=(1.0, 0.0))
    _service(index, provider).retrieve(query="q", top_k=2)
    assert all(input_type == "query" for _, input_type in provider.calls)
    assert len(provider.calls) == 1


def test_empty_and_whitespace_query_rejected() -> None:
    model = _model(dimensions=2)
    index = _index(((1.0, 0.0),), model=model)
    provider = ScriptedProvider(model=model, query_vector=(1.0, 0.0))
    service = _service(index, provider)
    with pytest.raises(RetrievalQueryInvalidError):
        service.retrieve(query="", top_k=1)
    with pytest.raises(RetrievalQueryInvalidError):
        service.retrieve(query="   \t\n  ", top_k=1)
    assert provider.calls == []


def test_invalid_top_k_and_max_enforced() -> None:
    model = _model(dimensions=2)
    index = _index(((1.0, 0.0),), model=model)
    provider = ScriptedProvider(model=model, query_vector=(1.0, 0.0))
    service = _service(index, provider, max_top_k=3)
    with pytest.raises(RetrievalQueryInvalidError):
        service.retrieve(query="ok", top_k=0)
    with pytest.raises(RetrievalQueryInvalidError):
        service.retrieve(query="ok", top_k=4)


def test_rerank_failure_has_no_vector_fallback() -> None:
    model = _model(dimensions=2)
    index = _index(((1.0, 0.0), (0.0, 1.0)), model=model)
    provider = ScriptedProvider(model=model, query_vector=(1.0, 0.0))
    reranker = FakeReranker(raise_error=True)
    with pytest.raises(RerankResponseInvalidError):
        _service(index, provider, reranker).retrieve(query="fail", top_k=2)


def test_provider_exception_translated() -> None:
    model = _model(dimensions=2)
    index = _index(((1.0, 0.0),), model=model)
    provider = ScriptedProvider(
        model=model,
        query_vector=(1.0, 0.0),
        raise_provider=True,
    )
    with pytest.raises(EmbeddingProviderError, match="provider boom"):
        _service(index, provider).retrieve(query="boom", top_k=1)


def test_provider_model_mismatch() -> None:
    index_model = _model(model_id="index-model", dimensions=2)
    query_model = _model(model_id="other-model", dimensions=2)
    index = _index(((1.0, 0.0),), model=index_model)
    provider = ScriptedProvider(model=query_model, query_vector=(1.0, 0.0))
    with pytest.raises(EmbeddingModelMismatchError):
        _service(index, provider).retrieve(query="mismatch", top_k=1)


def test_empty_index_returns_zero_matches() -> None:
    model = _model(dimensions=2)
    index = EmbeddingIndexSnapshot(
        schema_version=EMBEDDING_SCHEMA_VERSION,
        corpus_sha256=_SHA_E,
        manifest_sha256=_SHA_D,
        embedding_model=model,
        vector_dimensions=2,
        embedded_chunks=(),
        index_sha256=_SHA_F,
        chunk_count=0,
    )
    provider = ScriptedProvider(model=model, query_vector=(1.0, 0.0))
    reranker = FakeReranker()
    result = _service(index, provider, reranker).retrieve(query="empty-index", top_k=5)
    assert result.returned_count == 0
    assert result.matches == ()
    assert result.schema_version == RETRIEVAL_QUERY_SCHEMA_VERSION
    assert reranker.calls == []


def test_procedure_coverage_surfaces_crowded_out_procedure() -> None:
    # Three strong chunks from one procedure would crowd out a weaker second
    # procedure under pure top_k truncation; coverage selection keeps both.
    model = _model(dimensions=2)
    chunks = (
        _chunk(
            chunk_id=_SHA,
            content_sha256=_SHA_B,
            chunk_index=0,
            procedure_id="ARES-PROC-SOLAR-001",
            content="solar a",
        ),
        _chunk(
            chunk_id=_SHA_0,
            content_sha256=_SHA_D,
            chunk_index=1,
            procedure_id="ARES-PROC-SOLAR-001",
            content="solar b",
        ),
        _chunk(
            chunk_id=_SHA_1,
            content_sha256=_SHA_E,
            chunk_index=2,
            procedure_id="ARES-PROC-SOLAR-001",
            content="solar c",
        ),
        _chunk(
            chunk_id=_SHA_2,
            content_sha256=_SHA_C,
            chunk_index=3,
            procedure_id="ARES-PROC-PWR-001",
            content="power rationing",
        ),
    )
    index = _index(
        ((1.0, 0.0), (0.99, 0.01), (0.98, 0.02), (0.5, 0.0)),
        model=model,
        chunks=chunks,
    )
    provider = ScriptedProvider(model=model, query_vector=(1.0, 0.0))
    reranker = FakeReranker(scores=(30.0, 20.0, 10.0, 5.0))
    result = ProcedureRetrievalService(
        index=index,
        provider=provider,
        reranker=reranker,
        rerank_candidate_count=4,
        max_top_k=3,
    ).retrieve(query="solar and power", top_k=3)
    returned_ids = {m.chunk.procedure_id for m in result.matches}
    assert "ARES-PROC-SOLAR-001" in returned_ids
    assert "ARES-PROC-PWR-001" in returned_ids
    assert result.returned_count == 3
    for left, right in zip(result.matches, result.matches[1:], strict=False):
        assert (-left.rerank_score, -left.similarity, left.index_position) <= (
            -right.rerank_score,
            -right.similarity,
            right.index_position,
        )


def test_no_mutation_of_index_vectors() -> None:
    model = _model(dimensions=2)
    index = _index(((1.0, 0.0), (0.0, 1.0)), model=model)
    before = tuple(tuple(item.vector) for item in index.embedded_chunks)
    provider = ScriptedProvider(model=model, query_vector=(1.0, 0.0))
    _service(index, provider).retrieve(query="mutate", top_k=2)
    after = tuple(tuple(item.vector) for item in index.embedded_chunks)
    assert after == before


def test_nan_query_vector_rejected() -> None:
    model = _model(dimensions=2)
    index = _index(((1.0, 0.0),), model=model)
    provider = ScriptedProvider(model=model, query_vector=(math.nan, 0.0))
    with pytest.raises(EmbeddingValidationError, match="invalid numeric"):
        _service(index, provider).retrieve(query="nonfinite", top_k=1)


def test_real_94_chunk_corpus_retrieval() -> None:
    corpus = ProcedureCorpusBuilder(
        manifest_path=REAL_MANIFEST,
        manuals_root=REAL_MANUALS,
        repository_root=REPO_ROOT,
    ).build()
    assert len(corpus.chunks) == EXPECTED_REAL_CHUNK_COUNT
    excluded_ids = {d.procedure_id for d in corpus.excluded_documents}
    assert tuple(d.manual_path.split("/")[-1] for d in corpus.excluded_documents) == (
        EXPECTED_EXCLUDED
    )
    model = _model(dimensions=16)
    fake = DeterministicFakeEmbeddingProvider(model=model)
    index = EmbeddingIndexBuilder(provider=fake, batch_size=7).build(corpus)
    assert index.chunk_count == EXPECTED_REAL_CHUNK_COUNT
    assert index.manifest_sha256 == corpus.manifest_sha256
    reranker = FakeReranker()
    service = ProcedureRetrievalService(
        index=index,
        provider=fake,
        reranker=reranker,
        rerank_candidate_count=20,
        max_top_k=10,
    )
    result = service.retrieve(query="oxygen leak isolation", top_k=5)
    assert result.returned_count == 5
    assert result.requested_top_k == 5
    assert result.corpus_sha256 == corpus.corpus_sha256
    assert result.index_sha256 == index.index_sha256
    assert result.reranker_model.model_id == "deterministic-rerank"
    assert all(m.chunk.procedure_id not in excluded_ids for m in result.matches)
    assert len(reranker.calls) == 1
    assert len(reranker.calls[0][1]) == 20
    full = ProcedureRetrievalService(
        index=index,
        provider=fake,
        reranker=FakeReranker(),
        rerank_candidate_count=EXPECTED_REAL_CHUNK_COUNT,
        max_top_k=EXPECTED_REAL_CHUNK_COUNT,
    ).retrieve(query="oxygen leak isolation", top_k=EXPECTED_REAL_CHUNK_COUNT)
    assert full.returned_count == EXPECTED_REAL_CHUNK_COUNT
    assert all(m.chunk.procedure_id not in excluded_ids for m in full.matches)
