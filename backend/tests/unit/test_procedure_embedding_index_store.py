# Phase 4 Step 3 persistent embedding index store/builder tests
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
from app.core.errors import (
    RetrievalIndexCorruptError,
    RetrievalIndexNotFoundError,
    RetrievalIndexStaleError,
)
from app.schemas.embedding import EmbeddingModelDescriptor
from app.services.embedding_provider import DeterministicFakeEmbeddingProvider
from app.services.procedure_embedding_index_builder import ProcedureEmbeddingIndexBuilder
from app.services.procedure_embedding_index_store import ProcedureEmbeddingIndexStore

BACKEND_ROOT = Path(__file__).resolve().parents[2]
REPO_ROOT = BACKEND_ROOT.parent
REAL_MANIFEST = REPO_ROOT / "docs" / "procedures" / "corpus_manifest.json"
REAL_MANUALS = REPO_ROOT / "docs" / "procedures" / "manuals"

EXPECTED_EXCLUDED = (
    "comms_blackout.md",
    "co2_scrubber_failure.md",
)
EXPECTED_REAL_CHUNK_COUNT = 94


def _model(dimensions: int = 8) -> EmbeddingModelDescriptor:
    return EmbeddingModelDescriptor(
        provider="fake",
        model_id="deterministic-fake",
        model_revision="1",
        dimensions=dimensions,
    )


def test_build_write_load_round_trip(tmp_path: Path) -> None:
    index_path = tmp_path / "procedure_embedding_index.json"
    store = ProcedureEmbeddingIndexStore(index_path=index_path)
    provider = DeterministicFakeEmbeddingProvider(model=_model())
    builder = ProcedureEmbeddingIndexBuilder(
        provider=provider,
        store=store,
        manifest_path=REAL_MANIFEST,
        manuals_root=REAL_MANUALS,
        repository_root=REPO_ROOT,
        batch_size=7,
    )
    snap = builder.build_and_persist()
    assert index_path.is_file()
    text = index_path.read_text(encoding="utf-8")
    assert text.endswith("\n")
    loaded = store.load()
    assert loaded.index_sha256 == snap.index_sha256
    assert loaded.model_dump(mode="json") == snap.model_dump(mode="json")
    assert loaded.chunk_count == EXPECTED_REAL_CHUNK_COUNT
    excluded = {
        c.chunk.manual_path.split("/")[-1] for c in loaded.embedded_chunks
    }
    assert excluded.isdisjoint(EXPECTED_EXCLUDED)


def test_deterministic_bytes_and_hashes(tmp_path: Path) -> None:
    path_a = tmp_path / "a" / "index.json"
    path_b = tmp_path / "b" / "index.json"
    provider = DeterministicFakeEmbeddingProvider(model=_model())
    for path in (path_a, path_b):
        store = ProcedureEmbeddingIndexStore(index_path=path)
        ProcedureEmbeddingIndexBuilder(
            provider=provider,
            store=store,
            manifest_path=REAL_MANIFEST,
            manuals_root=REAL_MANUALS,
            repository_root=REPO_ROOT,
            batch_size=5,
        ).build_and_persist()
    assert path_a.read_bytes() == path_b.read_bytes()
    assert (
        ProcedureEmbeddingIndexStore(index_path=path_a).load().index_sha256
        == ProcedureEmbeddingIndexStore(index_path=path_b).load().index_sha256
    )


def test_atomic_replacement(tmp_path: Path) -> None:
    index_path = tmp_path / "index.json"
    store = ProcedureEmbeddingIndexStore(index_path=index_path)
    provider = DeterministicFakeEmbeddingProvider(model=_model())
    first = ProcedureEmbeddingIndexBuilder(
        provider=provider,
        store=store,
        manifest_path=REAL_MANIFEST,
        manuals_root=REAL_MANUALS,
        repository_root=REPO_ROOT,
    ).build_and_persist()
    second = ProcedureEmbeddingIndexBuilder(
        provider=DeterministicFakeEmbeddingProvider(model=_model(dimensions=8)),
        store=store,
        manifest_path=REAL_MANIFEST,
        manuals_root=REAL_MANUALS,
        repository_root=REPO_ROOT,
    ).build_and_persist()
    assert second.index_sha256 == first.index_sha256
    assert not any(tmp_path.glob(".*.tmp"))
    assert store.load().index_sha256 == second.index_sha256


def test_missing_index(tmp_path: Path) -> None:
    store = ProcedureEmbeddingIndexStore(index_path=tmp_path / "missing.json")
    with pytest.raises(RetrievalIndexNotFoundError):
        store.load()


def test_malformed_json(tmp_path: Path) -> None:
    path = tmp_path / "bad.json"
    path.write_text("{not-json", encoding="utf-8")
    with pytest.raises(RetrievalIndexCorruptError):
        ProcedureEmbeddingIndexStore(index_path=path).load()


def test_schema_invalid_index(tmp_path: Path) -> None:
    path = tmp_path / "invalid.json"
    path.write_text(json.dumps({"schema_version": "1.0.0"}) + "\n", encoding="utf-8")
    with pytest.raises(RetrievalIndexCorruptError):
        ProcedureEmbeddingIndexStore(index_path=path).load()


def test_stale_corpus_and_model_mismatch(tmp_path: Path) -> None:
    path = tmp_path / "index.json"
    store = ProcedureEmbeddingIndexStore(index_path=path)
    provider = DeterministicFakeEmbeddingProvider(model=_model())
    snap = ProcedureEmbeddingIndexBuilder(
        provider=provider,
        store=store,
        manifest_path=REAL_MANIFEST,
        manuals_root=REAL_MANUALS,
        repository_root=REPO_ROOT,
    ).build_and_persist()
    with pytest.raises(RetrievalIndexStaleError):
        store.load_compatible(expected_corpus_sha256="0" * 64)
    with pytest.raises(RetrievalIndexStaleError):
        store.load_compatible(
            expected_model=EmbeddingModelDescriptor(
                provider="nvidia",
                model_id="other",
                model_revision=None,
                dimensions=8,
            ),
        )
    loaded = store.load_compatible(
        expected_corpus_sha256=snap.corpus_sha256,
        expected_manifest_sha256=snap.manifest_sha256,
        expected_model=provider.model,
    )
    assert loaded.index_sha256 == snap.index_sha256


def test_cwd_independence_and_no_read_mutation(tmp_path: Path) -> None:
    index_path = tmp_path / "index.json"
    other = tmp_path / "other"
    other.mkdir()
    store = ProcedureEmbeddingIndexStore(index_path=index_path)
    provider = DeterministicFakeEmbeddingProvider(model=_model())
    ProcedureEmbeddingIndexBuilder(
        provider=provider,
        store=store,
        manifest_path=REAL_MANIFEST,
        manuals_root=REAL_MANUALS,
        repository_root=REPO_ROOT,
    ).build_and_persist()
    before = index_path.read_bytes()
    previous = Path.cwd()
    os.chdir(other)
    try:
        loaded = store.load()
    finally:
        os.chdir(previous)
    assert index_path.read_bytes() == before
    assert loaded.chunk_count == EXPECTED_REAL_CHUNK_COUNT
