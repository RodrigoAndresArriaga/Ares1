# Phase 4 Step 3 procedure retrieval service unit tests
from __future__ import annotations

import ast
import math
from collections.abc import Sequence
from pathlib import Path

import pytest
from app.core.errors import (
    EmbeddingModelMismatchError,
    EmbeddingProviderError,
    EmbeddingValidationError,
    RetrievalQueryInvalidError,
)
from app.schemas.actions import ActionType
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
    dims = resolved_model.dimensions if embedded else resolved_model.dimensions
    return EmbeddingIndexSnapshot(
        schema_version=EMBEDDING_SCHEMA_VERSION,
        corpus_sha256=_SHA_E,
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
        self.calls: list[tuple[str, ...]] = []

    @property
    def model(self) -> EmbeddingModelDescriptor:
        return self._model

    def embed(self, texts: Sequence[str]) -> Sequence[Sequence[float]]:
        self.calls.append(tuple(texts))
        if self._raise_typed_provider:
            raise EmbeddingProviderError("typed provider failure")
        if self._raise_provider:
            raise RuntimeError("provider boom")
        if self._query_vectors is not None:
            return self._query_vectors
        if self._query_vector is None:
            raise RuntimeError("no scripted query vector")
        return (self._query_vector,)


def _service(
    index: EmbeddingIndexSnapshot,
    provider: ScriptedProvider | DeterministicFakeEmbeddingProvider,
) -> ProcedureRetrievalService:
    return ProcedureRetrievalService(index=index, provider=provider)


def test_cosine_similarity_ordering() -> None:
    # query [1,0]: A=1.0, B~0.707, C=0.0, D=-1.0
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
    assert [m.rank for m in result.matches] == [1, 2, 3, 4]
    assert [m.index_position for m in result.matches] == [0, 1, 2, 3]


def test_stable_tie_breaking_by_index_position() -> None:
    model = _model(dimensions=2)
    index = _index(
        ((1.0, 0.0), (1.0, 0.0), (0.0, 1.0)),
        model=model,
        chunks=(
            _chunk(chunk_id=_SHA, content_sha256=_SHA_B, chunk_index=0),
            _chunk(chunk_id=_SHA_0, content_sha256=_SHA_D, chunk_index=1),
            _chunk(chunk_id=_SHA_1, content_sha256=_SHA_E, chunk_index=2),
        ),
    )
    provider = ScriptedProvider(model=model, query_vector=(1.0, 0.0))
    result = _service(index, provider).retrieve(query="tie", top_k=3)
    assert [m.chunk_id for m in result.matches] == [_SHA, _SHA_0, _SHA_1]
    assert result.matches[0].index_position == 0
    assert result.matches[1].index_position == 1
    assert result.matches[0].similarity == result.matches[1].similarity


def test_preserves_chunk_id_and_vector_association() -> None:
    model = _model(dimensions=2)
    chunks = (
        _chunk(
            chunk_id=_SHA,
            content_sha256=_SHA_B,
            chunk_index=0,
            procedure_title="Alpha",
            section_path=("Alpha",),
        ),
        _chunk(
            chunk_id=_SHA_0,
            content_sha256=_SHA_D,
            chunk_index=1,
            procedure_title="Beta",
            section_path=("Beta",),
        ),
    )
    index = _index(((0.0, 1.0), (1.0, 0.0)), model=model, chunks=chunks)
    provider = ScriptedProvider(model=model, query_vector=(1.0, 0.0))
    result = _service(index, provider).retrieve(query="assoc", top_k=2)
    assert result.matches[0].chunk_id == _SHA_0
    assert result.matches[0].chunk.procedure_title == "Beta"
    assert result.matches[0].index_position == 1
    assert result.matches[1].chunk_id == _SHA
    assert result.matches[1].chunk.procedure_title == "Alpha"


def test_provider_called_once_with_single_query() -> None:
    model = _model(dimensions=2)
    index = _index(((1.0, 0.0),), model=model)
    provider = ScriptedProvider(model=model, query_vector=(1.0, 0.0))
    _service(index, provider).retrieve(query="  oxygen leak  ", top_k=1)
    assert provider.calls == [("oxygen leak",)]


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


def test_invalid_top_k_rejected() -> None:
    model = _model(dimensions=2)
    index = _index(((1.0, 0.0),), model=model)
    provider = ScriptedProvider(model=model, query_vector=(1.0, 0.0))
    service = _service(index, provider)
    with pytest.raises(RetrievalQueryInvalidError):
        service.retrieve(query="ok", top_k=0)
    with pytest.raises(RetrievalQueryInvalidError):
        service.retrieve(query="ok", top_k=-1)
    with pytest.raises(RetrievalQueryInvalidError):
        service.retrieve(query="ok", top_k=True)  # type: ignore[arg-type]
    with pytest.raises(RetrievalQueryInvalidError):
        service.retrieve(query="ok", top_k=1.5)  # type: ignore[arg-type]


def test_top_k_larger_than_index_returns_all() -> None:
    model = _model(dimensions=2)
    index = _index(((1.0, 0.0), (0.0, 1.0)), model=model)
    provider = ScriptedProvider(model=model, query_vector=(1.0, 0.0))
    result = _service(index, provider).retrieve(query="cap", top_k=99)
    assert result.requested_top_k == 99
    assert result.returned_count == 2
    assert len(result.matches) == 2


def test_query_result_count_mismatch() -> None:
    model = _model(dimensions=2)
    index = _index(((1.0, 0.0),), model=model)
    provider = ScriptedProvider(
        model=model,
        query_vectors=((1.0, 0.0), (0.0, 1.0)),
    )
    with pytest.raises(EmbeddingValidationError, match="exactly one"):
        _service(index, provider).retrieve(query="multi", top_k=1)


def test_empty_query_vector() -> None:
    model = _model(dimensions=2)
    index = _index(((1.0, 0.0),), model=model)
    provider = ScriptedProvider(model=model, query_vectors=((),))
    with pytest.raises(EmbeddingValidationError, match="non-empty"):
        _service(index, provider).retrieve(query="empty-vec", top_k=1)


def test_wrong_query_vector_dimensions() -> None:
    model = _model(dimensions=2)
    index = _index(((1.0, 0.0),), model=model)
    provider = ScriptedProvider(model=model, query_vector=(1.0, 0.0, 0.0))
    with pytest.raises(EmbeddingValidationError, match="wrong dimensions"):
        _service(index, provider).retrieve(query="dims", top_k=1)


def test_non_numeric_and_bool_query_vector_rejected() -> None:
    model = _model(dimensions=2)
    index = _index(((1.0, 0.0),), model=model)
    bad_numeric = ScriptedProvider(model=model, query_vectors=(("x", 0.0),))
    with pytest.raises(EmbeddingValidationError, match="invalid numeric"):
        _service(index, bad_numeric).retrieve(query="nan-str", top_k=1)
    bad_bool = ScriptedProvider(model=model, query_vectors=((True, 0.0),))
    with pytest.raises(EmbeddingValidationError, match="invalid numeric"):
        _service(index, bad_bool).retrieve(query="bool", top_k=1)


def test_nan_and_infinity_query_vector_rejected() -> None:
    model = _model(dimensions=2)
    index = _index(((1.0, 0.0),), model=model)
    for vector in ((math.nan, 0.0), (math.inf, 0.0), (-math.inf, 0.0)):
        provider = ScriptedProvider(model=model, query_vector=vector)
        with pytest.raises(EmbeddingValidationError, match="invalid numeric"):
            _service(index, provider).retrieve(query="nonfinite", top_k=1)


def test_zero_norm_query_vector_rejected() -> None:
    model = _model(dimensions=2)
    index = _index(((1.0, 0.0),), model=model)
    provider = ScriptedProvider(model=model, query_vector=(0.0, 0.0))
    with pytest.raises(EmbeddingValidationError, match="zero norm"):
        _service(index, provider).retrieve(query="zero-q", top_k=1)


def test_zero_norm_indexed_vector_rejected() -> None:
    model = _model(dimensions=2)
    index = _index(((0.0, 0.0), (1.0, 0.0)), model=model)
    provider = ScriptedProvider(model=model, query_vector=(1.0, 0.0))
    with pytest.raises(EmbeddingValidationError, match="indexed embedding"):
        _service(index, provider).retrieve(query="zero-i", top_k=2)


def test_provider_model_mismatch() -> None:
    index_model = _model(model_id="index-model", dimensions=2)
    query_model = _model(model_id="other-model", dimensions=2)
    index = _index(((1.0, 0.0),), model=index_model)
    provider = ScriptedProvider(model=query_model, query_vector=(1.0, 0.0))
    with pytest.raises(EmbeddingModelMismatchError):
        _service(index, provider).retrieve(query="mismatch", top_k=1)


def test_provider_revision_and_dimension_mismatch() -> None:
    index = _index(((1.0, 0.0),), model=_model(model_revision="1", dimensions=2))
    rev_provider = ScriptedProvider(
        model=_model(model_revision="2", dimensions=2),
        query_vector=(1.0, 0.0),
    )
    with pytest.raises(EmbeddingModelMismatchError):
        _service(index, rev_provider).retrieve(query="rev", top_k=1)
    dim_provider = ScriptedProvider(
        model=_model(model_revision="1", dimensions=3),
        query_vector=(1.0, 0.0, 0.0),
    )
    with pytest.raises(EmbeddingModelMismatchError):
        _service(index, dim_provider).retrieve(query="dim", top_k=1)


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
    typed = ScriptedProvider(
        model=model,
        query_vector=(1.0, 0.0),
        raise_typed_provider=True,
    )
    with pytest.raises(EmbeddingProviderError, match="typed provider"):
        _service(index, typed).retrieve(query="typed", top_k=1)


def test_empty_index_returns_zero_matches() -> None:
    model = _model(dimensions=2)
    index = EmbeddingIndexSnapshot(
        schema_version=EMBEDDING_SCHEMA_VERSION,
        corpus_sha256=_SHA_E,
        embedding_model=model,
        vector_dimensions=2,
        embedded_chunks=(),
        index_sha256=_SHA_F,
        chunk_count=0,
    )
    provider = ScriptedProvider(model=model, query_vector=(1.0, 0.0))
    result = _service(index, provider).retrieve(query="empty-index", top_k=5)
    assert result.returned_count == 0
    assert result.matches == ()
    assert result.requested_top_k == 5
    assert result.schema_version == RETRIEVAL_QUERY_SCHEMA_VERSION


def test_no_mutation_of_index_vectors() -> None:
    model = _model(dimensions=2)
    index = _index(((1.0, 0.0), (0.0, 1.0)), model=model)
    before = tuple(tuple(item.vector) for item in index.embedded_chunks)
    provider = ScriptedProvider(model=model, query_vector=(1.0, 0.0))
    _service(index, provider).retrieve(query="mutate", top_k=2)
    after = tuple(tuple(item.vector) for item in index.embedded_chunks)
    assert after == before


def test_repeated_retrieval_identical() -> None:
    model = _model(dimensions=2)
    index = _index(
        ((1.0, 0.0), (1.0, 1.0), (0.0, 1.0), (-1.0, 0.0)),
        model=model,
    )
    provider = ScriptedProvider(model=model, query_vector=(1.0, 0.0))
    service = _service(index, provider)
    first = service.retrieve(query="repeat", top_k=4)
    second = service.retrieve(query="repeat", top_k=4)
    assert first.model_dump(mode="json") == second.model_dump(mode="json")


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
    service = ProcedureRetrievalService(index=index, provider=fake)
    result = service.retrieve(query="oxygen leak isolation", top_k=5)
    assert result.returned_count == 5
    assert result.requested_top_k == 5
    assert result.corpus_sha256 == corpus.corpus_sha256
    assert result.index_sha256 == index.index_sha256
    assert result.embedding_model.model_id == model.model_id
    assert all(m.chunk.procedure_id not in excluded_ids for m in result.matches)
    assert all(m.rank == i for i, m in enumerate(result.matches, start=1))
    again = service.retrieve(query="oxygen leak isolation", top_k=5)
    assert again.model_dump(mode="json") == result.model_dump(mode="json")
    # excluded COMMS/CO2 never appear even when scanning all matches
    full = service.retrieve(query="oxygen leak isolation", top_k=EXPECTED_REAL_CHUNK_COUNT)
    assert full.returned_count == EXPECTED_REAL_CHUNK_COUNT
    assert all(m.chunk.procedure_id not in excluded_ids for m in full.matches)
    assert {m.chunk.chunk_id for m in full.matches} == {
        e.chunk.chunk_id for e in index.embedded_chunks
    }


def test_no_network_routes_or_later_phase_wiring() -> None:
    service_text = (
        BACKEND_ROOT / "app" / "services" / "procedure_retrieval.py"
    ).read_text(encoding="utf-8")
    schema_text = (
        BACKEND_ROOT / "app" / "schemas" / "retrieval_query.py"
    ).read_text(encoding="utf-8")
    forbidden = (
        "nvidia",
        "openai",
        "httpx",
        "requests",
        "urllib",
        "rerank",
        "APIRouter",
        "lifespan",
        "MissionLifecycleService",
        "faiss",
        "pinecone",
        "chroma",
        "pgvector",
        "Settings",
        "get_settings",
    )
    combined = (service_text + "\n" + schema_text).lower()
    for token in forbidden:
        assert token not in combined
    tree = ast.parse(service_text)
    imports: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.append(node.module)
    assert "httpx" not in imports
    assert "requests" not in imports
    assert "urllib" not in imports
    assert "nvidia" not in imports
    assert not (BACKEND_ROOT / "app" / "api" / "retrieval.py").exists()
    main_text = (BACKEND_ROOT / "app" / "main.py").read_text(encoding="utf-8")
    assert "ProcedureRetrievalService" not in main_text
    assert "EmbeddingIndexBuilder" not in main_text
    # Step 2 modules must remain free of cosine/query search
    step2 = (
        (BACKEND_ROOT / "app" / "services" / "embedding_index.py").read_text(
            encoding="utf-8"
        )
        + (BACKEND_ROOT / "app" / "services" / "embedding_provider.py").read_text(
            encoding="utf-8"
        )
        + (BACKEND_ROOT / "app" / "schemas" / "embedding.py").read_text(encoding="utf-8")
    ).lower()
    assert "cosine" not in step2
