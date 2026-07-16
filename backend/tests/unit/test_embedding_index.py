# Phase 4 Step 2 embedding index builder unit tests
from __future__ import annotations

import ast
import math
import os
from collections.abc import Sequence
from pathlib import Path

import pytest
from app.core.errors import EmbeddingProviderError, EmbeddingValidationError
from app.schemas.actions import ActionType
from app.schemas.embedding import (
    EMBEDDING_SCHEMA_VERSION,
    EmbeddingModelDescriptor,
)
from app.schemas.retrieval import (
    CORPUS_SCHEMA_VERSION,
    EvidenceReference,
    ProcedureChunk,
    ProcedureCorpusSnapshot,
    ProcedureDocumentDescriptor,
    ProcedureStatus,
    SourceClassification,
)
from app.services.embedding_index import EmbeddingIndexBuilder
from app.services.embedding_provider import DeterministicFakeEmbeddingProvider
from app.services.procedure_corpus import ProcedureCorpusBuilder

BACKEND_ROOT = Path(__file__).resolve().parents[2]
REPO_ROOT = BACKEND_ROOT.parent
REAL_MANIFEST = REPO_ROOT / "docs" / "procedures" / "corpus_manifest.json"
REAL_MANUALS = REPO_ROOT / "docs" / "procedures" / "manuals"

_SHA = "a" * 64
_SHA_B = "b" * 64
_SHA_C = "c" * 64
_SHA_D = "d" * 64
_SHA_E = "e" * 64

EXPECTED_INCLUDED = (
    "oxygen_leak.md",
    "solar_array_failure.md",
    "power_rationing.md",
    "eva_repair.md",
)
EXPECTED_EXCLUDED = (
    "comms_blackout.md",
    "co2_scrubber_failure.md",
)
EXPECTED_REAL_CHUNK_COUNT = 94
DEFAULT_DIMS = 8


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
    embedding_text: str = "embed-one",
    chunk_index: int = 0,
    procedure_id: str = "ARES-PROC-OXY-001",
) -> ProcedureChunk:
    return ProcedureChunk(
        schema_version=CORPUS_SCHEMA_VERSION,
        chunk_id=chunk_id,
        procedure_id=procedure_id,
        procedure_title="Test Procedure",
        manual_path="docs/procedures/manuals/oxygen_leak.md",
        section_path=("Purpose",),
        section_title="Purpose",
        chunk_index=chunk_index,
        content=f"content-{chunk_index}",
        embedding_text=embedding_text,
        content_sha256=content_sha256,
        manual_sha256=_SHA_C,
        source_classifications=(SourceClassification.ARES_ASSUMPTION,),
        evidence_references=(_evidence(),),
        allowed_actions=(ActionType.ISOLATE_MODULE,),
        procedure_status=ProcedureStatus.PARTIAL_EVIDENCE,
    )


def _document(*, index_eligible: bool = True) -> ProcedureDocumentDescriptor:
    return ProcedureDocumentDescriptor(
        procedure_id="ARES-PROC-OXY-001",
        title="Test Procedure",
        manual_path="docs/procedures/manuals/oxygen_leak.md",
        status=ProcedureStatus.PARTIAL_EVIDENCE,
        index_eligible=index_eligible,
        primary_actions=(ActionType.ISOLATE_MODULE,),
        supporting_actions=(),
        prohibited_actions=(),
        source_classifications=(SourceClassification.ARES_ASSUMPTION,),
        evidence_references=(_evidence(),),
        manual_sha256=_SHA_C,
    )


def _corpus(
    chunks: tuple[ProcedureChunk, ...] = (),
    *,
    corpus_sha256: str = _SHA_D,
) -> ProcedureCorpusSnapshot:
    included = (_document(),) if chunks else ()
    return ProcedureCorpusSnapshot(
        schema_version=CORPUS_SCHEMA_VERSION,
        manifest_sha256=_SHA_E,
        corpus_sha256=corpus_sha256,
        included_documents=included,
        excluded_documents=(),
        chunks=chunks,
    )


def _model(
    *,
    model_id: str = "deterministic-fake",
    dimensions: int = DEFAULT_DIMS,
    model_revision: str | None = "1",
) -> EmbeddingModelDescriptor:
    return EmbeddingModelDescriptor(
        provider="fake",
        model_id=model_id,
        model_revision=model_revision,
        dimensions=dimensions,
    )


def _fake(model: EmbeddingModelDescriptor | None = None) -> DeterministicFakeEmbeddingProvider:
    return DeterministicFakeEmbeddingProvider(model=model or _model())


class ScriptedProvider:
    def __init__(
        self,
        *,
        model: EmbeddingModelDescriptor,
        vectors: Sequence[Sequence[float]] | None = None,
        by_batch: Sequence[Sequence[Sequence[float]]] | None = None,
        fail_after: int | None = None,
        raise_provider: bool = False,
    ) -> None:
        self._model = model
        self._vectors = list(vectors) if vectors is not None else None
        self._by_batch = list(by_batch) if by_batch is not None else None
        self._fail_after = fail_after
        self._raise_provider = raise_provider
        self._calls = 0
        self.partial_batches: list[Sequence[Sequence[float]]] = []

    @property
    def model(self) -> EmbeddingModelDescriptor:
        return self._model

    def embed(self, texts: Sequence[str]) -> Sequence[Sequence[float]]:
        self._calls += 1
        if self._raise_provider:
            raise RuntimeError("provider boom")
        if self._fail_after is not None and self._calls > self._fail_after:
            raise RuntimeError("provider mid-run failure")
        if self._by_batch is not None:
            idx = self._calls - 1
            if idx >= len(self._by_batch):
                raise RuntimeError("no scripted batch left")
            batch = self._by_batch[idx]
            self.partial_batches.append(batch)
            return batch
        if self._vectors is None:
            raise RuntimeError("no scripted vectors")
        if len(texts) != len(self._vectors):
            # allow slicing for batching when vectors covers full corpus
            start = (self._calls - 1) * len(texts)
            end = start + len(texts)
            batch = self._vectors[start:end]
            self.partial_batches.append(batch)
            return batch
        self.partial_batches.append(self._vectors)
        return self._vectors


def _unit_vector(dims: int, *values: float) -> tuple[float, ...]:
    if len(values) != dims:
        raise AssertionError("test helper length mismatch")
    return tuple(values)


def test_deterministic_snapshot_construction() -> None:
    chunks = (
        _chunk(chunk_id=_SHA, embedding_text="alpha", content_sha256=_SHA_B),
        _chunk(
            chunk_id=_SHA_B,
            embedding_text="beta",
            content_sha256=_SHA_C,
            chunk_index=1,
        ),
    )
    corpus = _corpus(chunks)
    builder = EmbeddingIndexBuilder(provider=_fake(), batch_size=2)
    snap = builder.build(corpus)
    assert snap.schema_version == EMBEDDING_SCHEMA_VERSION
    assert snap.chunk_count == 2
    assert snap.vector_dimensions == DEFAULT_DIMS
    assert snap.corpus_sha256 == corpus.corpus_sha256
    assert len(snap.index_sha256) == 64
    assert snap.embedded_chunks[0].chunk.chunk_id == _SHA
    assert snap.embedded_chunks[1].chunk.chunk_id == _SHA_B


def test_preserves_corpus_order_and_chunk_vector_association() -> None:
    chunks = (
        _chunk(chunk_id=_SHA, embedding_text="first", content_sha256=_SHA_B),
        _chunk(
            chunk_id=_SHA_B,
            embedding_text="second",
            content_sha256=_SHA_C,
            chunk_index=1,
        ),
        _chunk(
            chunk_id=_SHA_C,
            embedding_text="third",
            content_sha256=_SHA_D,
            chunk_index=2,
        ),
    )
    provider = _fake()
    expected = [provider.embed([c.embedding_text])[0] for c in chunks]
    snap = EmbeddingIndexBuilder(provider=provider, batch_size=2).build(_corpus(chunks))
    assert [e.chunk.chunk_id for e in snap.embedded_chunks] == [
        _SHA,
        _SHA_B,
        _SHA_C,
    ]
    for item, vector in zip(snap.embedded_chunks, expected, strict=True):
        assert item.vector == tuple(vector)


def test_stable_hash_across_repeated_builds() -> None:
    chunks = (
        _chunk(chunk_id=_SHA, embedding_text="alpha", content_sha256=_SHA_B),
        _chunk(
            chunk_id=_SHA_B,
            embedding_text="beta",
            content_sha256=_SHA_C,
            chunk_index=1,
        ),
    )
    corpus = _corpus(chunks)
    a = EmbeddingIndexBuilder(provider=_fake(), batch_size=1).build(corpus)
    b = EmbeddingIndexBuilder(provider=_fake(), batch_size=1).build(corpus)
    assert a.index_sha256 == b.index_sha256
    assert a.model_dump(mode="json") == b.model_dump(mode="json")


def test_cwd_independence(tmp_path: Path) -> None:
    chunks = (_chunk(chunk_id=_SHA, embedding_text="cwd", content_sha256=_SHA_B),)
    corpus = _corpus(chunks)
    first = EmbeddingIndexBuilder(provider=_fake()).build(corpus)
    previous = Path.cwd()
    os.chdir(tmp_path)
    try:
        second = EmbeddingIndexBuilder(provider=_fake()).build(corpus)
    finally:
        os.chdir(previous)
    assert first.index_sha256 == second.index_sha256


def test_batch_size_does_not_change_snapshot() -> None:
    chunks = tuple(
        _chunk(
            chunk_id=(f"{i:064x}"),
            embedding_text=f"text-{i}",
            content_sha256=(f"{i + 1:064x}"),
            chunk_index=i,
        )
        for i in range(5)
    )
    corpus = _corpus(chunks)
    one = EmbeddingIndexBuilder(provider=_fake(), batch_size=1).build(corpus)
    many = EmbeddingIndexBuilder(provider=_fake(), batch_size=3).build(corpus)
    assert one.index_sha256 == many.index_sha256
    assert [e.vector for e in one.embedded_chunks] == [
        e.vector for e in many.embedded_chunks
    ]


def test_provider_count_mismatch() -> None:
    chunks = (_chunk(),)
    empty_batch = ScriptedProvider(model=_model(), by_batch=[()])
    with pytest.raises(EmbeddingValidationError):
        EmbeddingIndexBuilder(provider=empty_batch, batch_size=1).build(_corpus(chunks))
    double = ScriptedProvider(
        model=_model(),
        by_batch=[
            (
                _unit_vector(DEFAULT_DIMS, *([0.1] * DEFAULT_DIMS)),
                _unit_vector(DEFAULT_DIMS, *([0.2] * DEFAULT_DIMS)),
            )
        ],
    )
    with pytest.raises(EmbeddingValidationError):
        EmbeddingIndexBuilder(provider=double, batch_size=1).build(_corpus(chunks))


def test_wrong_and_inconsistent_dimensions() -> None:
    chunks = (
        _chunk(chunk_id=_SHA, embedding_text="a", content_sha256=_SHA_B),
        _chunk(
            chunk_id=_SHA_B,
            embedding_text="b",
            content_sha256=_SHA_C,
            chunk_index=1,
        ),
    )
    wrong = ScriptedProvider(
        model=_model(dimensions=4),
        by_batch=[((0.1, 0.2, 0.3),)],
    )
    with pytest.raises(EmbeddingValidationError):
        EmbeddingIndexBuilder(provider=wrong, batch_size=1).build(
            _corpus((chunks[0],)),
        )
    inconsistent = ScriptedProvider(
        model=_model(dimensions=3),
        by_batch=[
            ((0.1, 0.2, 0.3),),
            ((0.1, 0.2),),
        ],
    )
    with pytest.raises(EmbeddingValidationError):
        EmbeddingIndexBuilder(provider=inconsistent, batch_size=1).build(_corpus(chunks))


def test_empty_vector_rejected() -> None:
    provider = ScriptedProvider(model=_model(dimensions=4), by_batch=[((),)])
    with pytest.raises(EmbeddingValidationError):
        EmbeddingIndexBuilder(provider=provider, batch_size=1).build(
            _corpus((_chunk(),)),
        )


def test_nan_and_infinity_rejected() -> None:
    dims = 4
    for bad in (math.nan, math.inf, -math.inf):
        values = [0.1] * dims
        values[1] = bad
        provider = ScriptedProvider(
            model=_model(dimensions=dims),
            by_batch=[(tuple(values),)],
        )
        with pytest.raises(EmbeddingValidationError):
            EmbeddingIndexBuilder(provider=provider, batch_size=1).build(
                _corpus((_chunk(),)),
            )


def test_non_numeric_and_bool_rejected() -> None:
    provider_bool = ScriptedProvider(
        model=_model(dimensions=4),
        by_batch=[((0.1, True, 0.2, 0.3),)],
    )
    with pytest.raises(EmbeddingValidationError):
        EmbeddingIndexBuilder(provider=provider_bool, batch_size=1).build(
            _corpus((_chunk(),)),
        )
    provider_str = ScriptedProvider(
        model=_model(dimensions=4),
        by_batch=[((0.1, "x", 0.2, 0.3),)],
    )
    with pytest.raises(EmbeddingValidationError):
        EmbeddingIndexBuilder(provider=provider_str, batch_size=1).build(
            _corpus((_chunk(),)),
        )


def test_duplicate_chunk_ids_rejected() -> None:
    chunks = (
        _chunk(chunk_id=_SHA, embedding_text="a", content_sha256=_SHA_B),
        _chunk(
            chunk_id=_SHA,
            embedding_text="b",
            content_sha256=_SHA_C,
            chunk_index=1,
        ),
    )
    with pytest.raises(EmbeddingValidationError):
        EmbeddingIndexBuilder(provider=_fake()).build(_corpus(chunks))


def test_empty_corpus_allowed() -> None:
    snap = EmbeddingIndexBuilder(provider=_fake()).build(_corpus(()))
    assert snap.chunk_count == 0
    assert snap.embedded_chunks == ()
    again = EmbeddingIndexBuilder(provider=_fake()).build(_corpus(()))
    assert snap.index_sha256 == again.index_sha256


def test_provider_failure_leaves_no_partial_snapshot() -> None:
    chunks = (
        _chunk(chunk_id=_SHA, embedding_text="a", content_sha256=_SHA_B),
        _chunk(
            chunk_id=_SHA_B,
            embedding_text="b",
            content_sha256=_SHA_C,
            chunk_index=1,
        ),
    )
    provider = ScriptedProvider(
        model=_model(),
        fail_after=1,
        by_batch=[
            (tuple(0.1 for _ in range(DEFAULT_DIMS)),),
        ],
    )
    with pytest.raises(EmbeddingProviderError):
        EmbeddingIndexBuilder(provider=provider, batch_size=1).build(_corpus(chunks))
    assert len(provider.partial_batches) == 1


def test_model_descriptor_changes_index_hash() -> None:
    chunks = (_chunk(chunk_id=_SHA, embedding_text="shared", content_sha256=_SHA_B),)
    corpus = _corpus(chunks)
    vector = tuple(0.25 for _ in range(DEFAULT_DIMS))
    a = EmbeddingIndexBuilder(
        provider=ScriptedProvider(
            model=_model(model_id="model-a"),
            by_batch=[(vector,)],
        ),
        batch_size=1,
    ).build(corpus)
    b = EmbeddingIndexBuilder(
        provider=ScriptedProvider(
            model=_model(model_id="model-b"),
            by_batch=[(vector,)],
        ),
        batch_size=1,
    ).build(corpus)
    assert a.index_sha256 != b.index_sha256
    assert a.embedded_chunks[0].vector == b.embedded_chunks[0].vector


def test_corpus_hash_changes_index_hash() -> None:
    chunks = (_chunk(chunk_id=_SHA, embedding_text="shared", content_sha256=_SHA_B),)
    vector = tuple(0.25 for _ in range(DEFAULT_DIMS))
    provider = ScriptedProvider(model=_model(), by_batch=[(vector,)])
    a = EmbeddingIndexBuilder(provider=provider, batch_size=1).build(
        _corpus(chunks, corpus_sha256=_SHA_D),
    )
    provider2 = ScriptedProvider(model=_model(), by_batch=[(vector,)])
    b = EmbeddingIndexBuilder(provider=provider2, batch_size=1).build(
        _corpus(chunks, corpus_sha256=_SHA_E),
    )
    assert a.index_sha256 != b.index_sha256


def test_invalid_batch_size_rejected() -> None:
    with pytest.raises(EmbeddingValidationError):
        EmbeddingIndexBuilder(provider=_fake(), batch_size=0)


def test_missing_vector_rejected() -> None:
    provider = ScriptedProvider(model=_model(), by_batch=[(None,)])  # type: ignore[list-item]
    with pytest.raises(EmbeddingValidationError):
        EmbeddingIndexBuilder(provider=provider, batch_size=1).build(
            _corpus((_chunk(),)),
        )


def test_real_corpus_embedding_with_fake_provider() -> None:
    corpus = ProcedureCorpusBuilder(
        manifest_path=REAL_MANIFEST,
        manuals_root=REAL_MANUALS,
        repository_root=REPO_ROOT,
    ).build()
    assert len(corpus.chunks) == EXPECTED_REAL_CHUNK_COUNT
    assert tuple(d.manual_path.split("/")[-1] for d in corpus.included_documents) == (
        EXPECTED_INCLUDED
    )
    assert tuple(d.manual_path.split("/")[-1] for d in corpus.excluded_documents) == (
        EXPECTED_EXCLUDED
    )
    excluded_ids = {d.procedure_id for d in corpus.excluded_documents}
    model = _model(dimensions=16)
    snap = EmbeddingIndexBuilder(provider=_fake(model), batch_size=7).build(corpus)
    assert snap.chunk_count == EXPECTED_REAL_CHUNK_COUNT
    assert snap.vector_dimensions == 16
    assert len(snap.embedded_chunks) == EXPECTED_REAL_CHUNK_COUNT
    assert [e.chunk.chunk_id for e in snap.embedded_chunks] == [
        c.chunk_id for c in corpus.chunks
    ]
    assert all(e.chunk.procedure_id not in excluded_ids for e in snap.embedded_chunks)
    for item, chunk in zip(snap.embedded_chunks, corpus.chunks, strict=True):
        assert item.chunk.chunk_id == chunk.chunk_id
        assert item.content_sha256 == chunk.content_sha256
        assert len(item.vector) == 16
    again = EmbeddingIndexBuilder(provider=_fake(model), batch_size=1).build(corpus)
    assert again.index_sha256 == snap.index_sha256


def test_no_network_or_later_phase_in_step2_modules() -> None:
    service_index = (
        BACKEND_ROOT / "app" / "services" / "embedding_index.py"
    ).read_text(encoding="utf-8")
    service_provider = (
        BACKEND_ROOT / "app" / "services" / "embedding_provider.py"
    ).read_text(encoding="utf-8")
    schema = (BACKEND_ROOT / "app" / "schemas" / "embedding.py").read_text(
        encoding="utf-8"
    )
    forbidden = (
        "nvidia",
        "openai",
        "httpx",
        "requests",
        "urllib",
        "cosine",
        "rerank",
        "APIRouter",
        "lifespan",
        "MissionLifecycleService",
        "faiss",
    )
    combined = (service_index + "\n" + service_provider + "\n" + schema).lower()
    for token in forbidden:
        assert token not in combined
    for path in (
        BACKEND_ROOT / "app" / "services" / "embedding_index.py",
        BACKEND_ROOT / "app" / "services" / "embedding_provider.py",
    ):
        tree = ast.parse(path.read_text(encoding="utf-8"))
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
    assert "EmbeddingIndexBuilder" not in main_text
    assert "DeterministicFakeEmbeddingProvider" not in main_text
