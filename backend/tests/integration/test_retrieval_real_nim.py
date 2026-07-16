# Phase 4 Step 4 real NVIDIA NIM release gate
# proves corpus → embed → persist → reload → retrieve → rerank → HTTP
from __future__ import annotations

import hashlib
import json
import logging
import math
import os
import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import pytest
from app.core.config import (
    DEFAULT_EMBED_DIMENSIONS,
    DEFAULT_NVIDIA_EMBED_MODEL_ID,
    DEFAULT_NVIDIA_RERANK_MODEL_ID,
    Settings,
)
from app.integrations.nvidia_nim import NvidiaNimClient
from app.main import create_app
from app.schemas.embedding import (
    EmbeddingIndexSnapshot,
    EmbeddingModelDescriptor,
    RerankerModelDescriptor,
)
from app.schemas.retrieval_query import ProcedureRetrievalResult
from app.services.embedding_provider import EmbeddingInputType, EmbeddingProvider
from app.services.procedure_corpus import ProcedureCorpusBuilder
from app.services.procedure_embedding_index_builder import ProcedureEmbeddingIndexBuilder
from app.services.procedure_embedding_index_store import ProcedureEmbeddingIndexStore
from app.services.procedure_retrieval import ProcedureRetrievalService
from fastapi.testclient import TestClient
from pydantic import SecretStr
from tests.conftest import (
    BACKEND_ROOT,
    REPO_ROOT,
    require_real_nim,
    resolve_nvidia_api_key,
    settings_from_layout,
    sha256_hex_upper,
)

pytestmark = [pytest.mark.integration, pytest.mark.real_nim]

REAL_MANIFEST = REPO_ROOT / "docs" / "procedures" / "corpus_manifest.json"
REAL_MANUALS = REPO_ROOT / "docs" / "procedures" / "manuals"
RELEASE_QUERIES_PATH = (
    BACKEND_ROOT / "tests" / "fixtures" / "retrieval" / "phase4_release_queries.json"
)
ADMIN_SCRIPT = BACKEND_ROOT / "scripts" / "build_procedure_embedding_index.py"

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
DEFERRED_PROCEDURE_IDS = frozenset(
    {
        "ARES-PROC-COMMS-001",
        "ARES-PROC-CO2-001",
    }
)
EXPECTED_REAL_CHUNK_COUNT = 94
EXPECTED_BATCH_SIZE = 32
EXPECTED_DOC_EMBED_CALLS = 3
EXPECTED_RERANK_CANDIDATES = 40
LOCKED_EMBED_MODEL = DEFAULT_NVIDIA_EMBED_MODEL_ID
LOCKED_RERANK_MODEL = DEFAULT_NVIDIA_RERANK_MODEL_ID
LOCKED_DIMENSIONS = DEFAULT_EMBED_DIMENSIONS

MANUAL_FILENAMES = EXPECTED_INCLUDED + EXPECTED_EXCLUDED


@pytest.fixture(autouse=True)
def _require_nim() -> None:
    require_real_nim()


class CountingEmbeddingProvider:
    # Test-only wrapper around the real NVIDIA embedding provider.
    def __init__(self, inner: EmbeddingProvider) -> None:
        self._inner = inner
        self.document_embed_calls = 0
        self.query_embed_calls = 0
        self.passage_batch_sizes: list[int] = []

    @property
    def model(self) -> EmbeddingModelDescriptor:
        return self._inner.model

    def embed(
        self,
        texts: Sequence[str],
        *,
        input_type: EmbeddingInputType = "passage",
    ) -> Sequence[Sequence[float]]:
        if input_type == "passage":
            self.document_embed_calls += 1
            self.passage_batch_sizes.append(len(texts))
        elif input_type == "query":
            self.query_embed_calls += 1
        return self._inner.embed(texts, input_type=input_type)

    def reset_counts(self) -> None:
        self.document_embed_calls = 0
        self.query_embed_calls = 0
        self.passage_batch_sizes.clear()


class CountingReranker:
    # Test-only wrapper around the real NVIDIA reranker.
    def __init__(self, inner: Any) -> None:
        self._inner = inner
        self.rerank_calls = 0
        self.last_document_count = 0

    @property
    def model(self) -> RerankerModelDescriptor:
        return self._inner.model

    def rerank(
        self,
        *,
        query: str,
        documents: Sequence[str],
    ) -> tuple[float, ...]:
        self.rerank_calls += 1
        self.last_document_count = len(documents)
        return self._inner.rerank(query=query, documents=documents)

    def reset_counts(self) -> None:
        self.rerank_calls = 0
        self.last_document_count = 0


def _load_release_fixture() -> dict[str, Any]:
    return json.loads(RELEASE_QUERIES_PATH.read_text(encoding="utf-8"))


def _load_release_queries() -> list[dict[str, Any]]:
    payload = _load_release_fixture()
    return list(payload["queries"])


def _deferred_procedure_ids() -> frozenset[str]:
    payload = _load_release_fixture()
    return frozenset(payload["deferred_procedure_ids"])


def _capture_manual_hashes() -> dict[str, str]:
    hashes: dict[str, str] = {}
    for name in MANUAL_FILENAMES:
        path = REAL_MANUALS / name
        hashes[name] = sha256_hex_upper(path)
    return hashes


def _assert_secrets_absent(text: str, api_key: str) -> None:
    assert api_key not in text
    assert "Bearer " not in text
    assert "Authorization:" not in text
    assert "ARES_NVIDIA_API_KEY=" not in text
    if api_key.startswith("nvapi-"):
        assert api_key[:12] not in text


def _assert_deferred_absent_ids(procedure_ids: set[str]) -> None:
    assert procedure_ids.isdisjoint(DEFERRED_PROCEDURE_IDS)


def _assert_chunk_metadata_complete(chunk: Any) -> None:
    assert len(chunk.source_classifications) >= 1
    assert len(chunk.evidence_references) >= 1
    assert len(chunk.allowed_actions) >= 1
    assert len(chunk.section_path) >= 1
    assert chunk.section_title
    assert chunk.content
    assert chunk.embedding_text
    assert chunk.procedure_id
    assert chunk.manual_path
    assert chunk.chunk_id


def _assert_ranking_invariants(
    result: ProcedureRetrievalResult,
    index: EmbeddingIndexSnapshot,
) -> None:
    assert result.returned_count == len(result.matches)
    assert result.returned_count <= result.requested_top_k
    by_id = {item.chunk.chunk_id: item.chunk for item in index.embedded_chunks}
    for expected_rank, match in enumerate(result.matches, start=1):
        assert match.rank == expected_rank
        assert math.isfinite(match.similarity)
        assert math.isfinite(match.rerank_score)
        assert match.chunk_id in by_id
        assert match.chunk == by_id[match.chunk_id]
        _assert_chunk_metadata_complete(match.chunk)
        dumped = match.model_dump(mode="json")
        assert "vector" not in dumped
        assert "vector" not in dumped.get("chunk", {})
    for left, right in zip(result.matches, result.matches[1:], strict=False):
        left_key = (-left.rerank_score, -left.similarity, left.index_position)
        right_key = (-right.rerank_score, -right.similarity, right.index_position)
        assert left_key <= right_key
    _assert_deferred_absent_ids({m.chunk.procedure_id for m in result.matches})


def _ranking_diagnostic(result: ProcedureRetrievalResult) -> str:
    rows: list[str] = []
    for match in result.matches:
        section = "/".join(match.chunk.section_path)
        rows.append(
            f"rank={match.rank} procedure_id={match.chunk.procedure_id} "
            f"section={section} similarity={match.similarity:.6f} "
            f"rerank_score={match.rerank_score:.6f}"
        )
    return "\n".join(rows)


def _make_nim_client(api_key: str) -> NvidiaNimClient:
    embed_model = EmbeddingModelDescriptor(
        provider="nvidia",
        model_id=LOCKED_EMBED_MODEL,
        model_revision=None,
        dimensions=LOCKED_DIMENSIONS,
    )
    rerank_model = RerankerModelDescriptor(
        provider="nvidia",
        model_id=LOCKED_RERANK_MODEL,
        model_revision=None,
    )
    return NvidiaNimClient(
        api_key=api_key,
        embed_base_url="https://integrate.api.nvidia.com/v1",
        rerank_base_url="https://ai.api.nvidia.com/v1",
        embed_model=embed_model,
        rerank_model=rerank_model,
        timeout_seconds=60.0,
        max_retries=2,
        retry_backoff_seconds=0.5,
    )


def _retrieval_settings(
    layout: dict[str, Path],
    *,
    index_path: Path,
    api_key: str,
) -> Settings:
    return settings_from_layout(
        layout,
        procedure_manifest_path=REAL_MANIFEST,
        procedure_manuals_root=REAL_MANUALS,
        procedure_embedding_index_path=index_path,
        nvidia_api_key=SecretStr(api_key),
        nvidia_embed_model_id=LOCKED_EMBED_MODEL,
        nvidia_rerank_model_id=LOCKED_RERANK_MODEL,
        nvidia_embed_dimensions=LOCKED_DIMENSIONS,
        nvidia_embed_batch_size=EXPECTED_BATCH_SIZE,
        retrieval_default_top_k=5,
        retrieval_max_top_k=10,
        retrieval_rerank_candidate_count=EXPECTED_RERANK_CANDIDATES,
    )


@pytest.fixture(scope="session")
def real_nim_api_key() -> str:
    key = resolve_nvidia_api_key()
    assert key is not None
    return key


@pytest.fixture(scope="session")
def real_nim_workspace(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return tmp_path_factory.mktemp("real_nim")


@pytest.fixture(scope="session")
def real_nim_index_path(real_nim_workspace: Path) -> Path:
    return real_nim_workspace / "procedure_embedding_index.json"


@pytest.fixture(scope="session")
def real_nim_build_evidence(
    real_nim_api_key: str,
    real_nim_index_path: Path,
) -> dict[str, Any]:
    client = _make_nim_client(real_nim_api_key)
    counting_provider = CountingEmbeddingProvider(client.embedding_provider)
    store = ProcedureEmbeddingIndexStore(index_path=real_nim_index_path)
    try:
        builder = ProcedureEmbeddingIndexBuilder(
            provider=counting_provider,
            store=store,
            manifest_path=REAL_MANIFEST,
            manuals_root=REAL_MANUALS,
            repository_root=REPO_ROOT,
            batch_size=EXPECTED_BATCH_SIZE,
        )
        built = builder.build_and_persist()
        loaded = ProcedureEmbeddingIndexStore(index_path=real_nim_index_path).load()
        index_bytes = real_nim_index_path.read_bytes()
        evidence = {
            "api_key": real_nim_api_key,
            "index_path": real_nim_index_path,
            "client": client,
            "counting_provider": counting_provider,
            "built": built,
            "index": loaded,
            "document_embed_calls": counting_provider.document_embed_calls,
            "passage_batch_sizes": list(counting_provider.passage_batch_sizes),
            "corpus_sha256": loaded.corpus_sha256,
            "manifest_sha256": loaded.manifest_sha256,
            "index_sha256": loaded.index_sha256,
            "index_bytes": index_bytes,
            "file_sha256": hashlib.sha256(index_bytes).hexdigest().lower(),
            "file_size": len(index_bytes),
            "manual_hashes_before": _capture_manual_hashes(),
            "admin_script_stdout": "",
            "admin_script_stderr": "",
        }
        yield evidence
    finally:
        client.close()


@pytest.fixture
def real_nim_service(
    real_nim_build_evidence: dict[str, Any],
) -> ProcedureRetrievalService:
    client: NvidiaNimClient = real_nim_build_evidence["client"]
    provider = CountingEmbeddingProvider(client.embedding_provider)
    reranker = CountingReranker(client.reranker)
    service = ProcedureRetrievalService(
        index=real_nim_build_evidence["index"],
        provider=provider,
        reranker=reranker,
        rerank_candidate_count=EXPECTED_RERANK_CANDIDATES,
        max_top_k=10,
    )
    service._counting_provider = provider  # type: ignore[attr-defined]
    service._counting_reranker = reranker  # type: ignore[attr-defined]
    return service


def test_real_index_build_evidence(real_nim_build_evidence: dict[str, Any]) -> None:
    corpus = ProcedureCorpusBuilder(
        manifest_path=REAL_MANIFEST,
        manuals_root=REAL_MANUALS,
        repository_root=REPO_ROOT,
    ).build()
    index: EmbeddingIndexSnapshot = real_nim_build_evidence["index"]

    assert len(corpus.included_documents) == 4
    assert len(corpus.excluded_documents) == 2
    assert tuple(d.manual_path.split("/")[-1] for d in corpus.included_documents) == (
        EXPECTED_INCLUDED
    )
    assert tuple(d.manual_path.split("/")[-1] for d in corpus.excluded_documents) == (
        EXPECTED_EXCLUDED
    )
    assert len(corpus.chunks) == EXPECTED_REAL_CHUNK_COUNT
    assert index.chunk_count == EXPECTED_REAL_CHUNK_COUNT
    assert len(index.embedded_chunks) == EXPECTED_REAL_CHUNK_COUNT
    assert index.vector_dimensions == LOCKED_DIMENSIONS
    assert index.embedding_model.model_id == LOCKED_EMBED_MODEL
    assert index.embedding_model.dimensions == LOCKED_DIMENSIONS
    assert index.corpus_sha256 == corpus.corpus_sha256
    assert index.manifest_sha256 == corpus.manifest_sha256
    assert index.index_sha256 == real_nim_build_evidence["index_sha256"]

    chunk_ids = [item.chunk.chunk_id for item in index.embedded_chunks]
    assert len(chunk_ids) == len(set(chunk_ids))
    for item in index.embedded_chunks:
        assert len(item.vector) == LOCKED_DIMENSIONS
        assert all(math.isfinite(v) for v in item.vector)
        assert item.chunk.procedure_id not in DEFERRED_PROCEDURE_IDS

    assert real_nim_build_evidence["document_embed_calls"] == EXPECTED_DOC_EMBED_CALLS
    assert real_nim_build_evidence["passage_batch_sizes"] == [32, 32, 30]
    _assert_deferred_absent_ids(
        {item.chunk.procedure_id for item in index.embedded_chunks},
    )


def test_index_persistence_reload_and_cwd(
    real_nim_build_evidence: dict[str, Any],
    real_nim_workspace: Path,
) -> None:
    index_path: Path = real_nim_build_evidence["index_path"]
    before_bytes = index_path.read_bytes()
    before_hash = hashlib.sha256(before_bytes).hexdigest().lower()
    original = real_nim_build_evidence["index"]

    store = ProcedureEmbeddingIndexStore(index_path=index_path)
    reloaded = store.load()
    assert reloaded.model_dump(mode="json") == original.model_dump(mode="json")
    assert index_path.read_bytes() == before_bytes
    assert hashlib.sha256(index_path.read_bytes()).hexdigest().lower() == before_hash

    client: NvidiaNimClient = real_nim_build_evidence["client"]
    counting = CountingEmbeddingProvider(client.embedding_provider)
    counting.reset_counts()
    _ = ProcedureEmbeddingIndexStore(index_path=index_path).load()
    assert counting.document_embed_calls == 0
    assert counting.query_embed_calls == 0

    alt_cwd = real_nim_workspace / "alt_cwd"
    alt_cwd.mkdir(exist_ok=True)
    before_listing = set(alt_cwd.rglob("*"))
    previous = Path.cwd()
    try:
        os.chdir(alt_cwd)
        cwd_store = ProcedureEmbeddingIndexStore(index_path=index_path)
        cwd_loaded = cwd_store.load()
        assert cwd_loaded.model_dump(mode="json") == original.model_dump(mode="json")
        after_listing = set(alt_cwd.rglob("*"))
        assert after_listing == before_listing
        assert not any(p.name == "procedure_embedding_index.json" for p in after_listing)
    finally:
        os.chdir(previous)


def test_admin_script_builds_temp_index(
    real_nim_api_key: str,
    real_nim_workspace: Path,
    real_nim_build_evidence: dict[str, Any],
) -> None:
    from tests.conftest import REAL_BINARY

    out_path = real_nim_workspace / "admin_script_index.json"
    runs_dir = real_nim_workspace / "admin_runs"
    sessions_dir = real_nim_workspace / "admin_sessions"
    runs_dir.mkdir(exist_ok=True)
    sessions_dir.mkdir(exist_ok=True)
    sim_binary = REAL_BINARY if REAL_BINARY.is_file() else real_nim_workspace / "dummy_sim.exe"
    if not sim_binary.is_file():
        sim_binary.write_bytes(b"dummy")
    env = os.environ.copy()
    env["ARES_NVIDIA_API_KEY"] = real_nim_api_key
    env["ARES_PROCEDURE_EMBEDDING_INDEX_PATH"] = str(out_path)
    env["ARES_PROJECT_ROOT"] = str(REPO_ROOT)
    env["ARES_SIM_BINARY"] = str(sim_binary)
    env["ARES_SCENARIO_DIR"] = str(REPO_ROOT / "scenarios")
    env["ARES_RUNS_DIR"] = str(runs_dir)
    env["ARES_SESSIONS_DIR"] = str(sessions_dir)
    env["ARES_PROCEDURE_MANIFEST_PATH"] = str(REAL_MANIFEST)
    env["ARES_PROCEDURE_MANUALS_ROOT"] = str(REAL_MANUALS)
    env["ARES_NVIDIA_EMBED_BATCH_SIZE"] = str(EXPECTED_BATCH_SIZE)
    completed = subprocess.run(
        [sys.executable, str(ADMIN_SCRIPT)],
        cwd=str(BACKEND_ROOT),
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    real_nim_build_evidence["admin_script_stdout"] = completed.stdout
    real_nim_build_evidence["admin_script_stderr"] = completed.stderr
    assert completed.returncode == 0, completed.stderr
    assert out_path.is_file()
    loaded = ProcedureEmbeddingIndexStore(index_path=out_path).load()
    assert loaded.chunk_count == EXPECTED_REAL_CHUNK_COUNT
    assert loaded.embedding_model.model_id == LOCKED_EMBED_MODEL
    assert loaded.vector_dimensions == LOCKED_DIMENSIONS
    assert f"chunk_count={EXPECTED_REAL_CHUNK_COUNT}" in completed.stdout
    assert f"model_id={LOCKED_EMBED_MODEL}" in completed.stdout
    assert f"dimensions={LOCKED_DIMENSIONS}" in completed.stdout
    assert "index_sha256=" in completed.stdout
    assert "corpus_sha256=" in completed.stdout
    assert "manifest_sha256=" in completed.stdout
    combined = completed.stdout + completed.stderr
    _assert_secrets_absent(combined, real_nim_api_key)
    assert '"embedding"' not in combined
    assert '"vector"' not in combined
    assert "chunk content" not in combined.lower()


def test_retrieval_benchmark_quality(
    real_nim_service: ProcedureRetrievalService,
) -> None:
    queries = _load_release_queries()
    single_top1_hits = 0
    single_top3_hits = 0
    single_total = 0
    compound_recall_ok = False
    deferred_seen = 0
    diagnostics: list[str] = []

    for entry in queries:
        top_k = int(entry["top_k"])
        result = real_nim_service.retrieve(query=entry["query"], top_k=top_k)
        _assert_ranking_invariants(result, real_nim_service._index)
        window = int(entry["acceptance_window"])
        window_ids = [m.chunk.procedure_id for m in result.matches[:window]]
        expected = list(entry["expected_procedure_ids"])
        diag = (
            f"query_id={entry['id']}\n"
            f"expected={expected}\n"
            f"{_ranking_diagnostic(result)}"
        )
        diagnostics.append(diag)
        deferred_seen += sum(
            1 for m in result.matches if m.chunk.procedure_id in DEFERRED_PROCEDURE_IDS
        )

        if entry["kind"] == "single":
            single_total += 1
            expected_id = expected[0]
            if result.matches and result.matches[0].chunk.procedure_id == expected_id:
                single_top1_hits += 1
            if expected_id in window_ids:
                single_top3_hits += 1
            else:
                pytest.fail(
                    "single-topic query missed expected procedure in top 3\n" + diag,
                )
        else:
            missing = [pid for pid in expected if pid not in window_ids]
            compound_recall_ok = not missing
            if missing:
                pytest.fail(
                    "compound query missing expected procedures in top 10\n"
                    f"missing={missing}\n{diag}",
                )

    assert single_total == 4
    assert single_top3_hits == 4
    top1_rate = single_top1_hits / single_total
    top3_rate = single_top3_hits / single_total
    assert top3_rate == 1.0
    assert compound_recall_ok
    assert deferred_seen == 0
    assert 0.0 <= top1_rate <= 1.0


def test_single_retrieval_call_counts(
    real_nim_service: ProcedureRetrievalService,
) -> None:
    provider: CountingEmbeddingProvider = real_nim_service._counting_provider
    reranker: CountingReranker = real_nim_service._counting_reranker
    provider.reset_counts()
    reranker.reset_counts()
    result = real_nim_service.retrieve(
        query=(
            "Habitat oxygen and pressure are dropping after a suspected module leak. "
            "Retrieve the immediate isolation and oxygen-conservation procedure."
        ),
        top_k=3,
    )
    assert provider.document_embed_calls == 0
    assert provider.query_embed_calls == 1
    assert reranker.rerank_calls == 1
    assert reranker.last_document_count == EXPECTED_RERANK_CANDIDATES
    assert reranker.last_document_count < EXPECTED_REAL_CHUNK_COUNT
    assert result.returned_count == 3
    _assert_ranking_invariants(result, real_nim_service._index)


def test_ranking_invariants_all_benchmark_queries(
    real_nim_service: ProcedureRetrievalService,
) -> None:
    for entry in _load_release_queries():
        result = real_nim_service.retrieve(
            query=entry["query"],
            top_k=int(entry["top_k"]),
        )
        _assert_ranking_invariants(result, real_nim_service._index)


def test_real_http_route_without_override(
    valid_layout: dict[str, Path],
    real_nim_build_evidence: dict[str, Any],
    real_nim_api_key: str,
) -> None:
    settings = _retrieval_settings(
        valid_layout,
        index_path=real_nim_build_evidence["index_path"],
        api_key=real_nim_api_key,
    )
    app = create_app(settings_override=settings)
    queries = _load_release_queries()
    single = next(q for q in queries if q["kind"] == "single")
    compound = next(q for q in queries if q["kind"] == "compound")
    with TestClient(app) as client:
        first = client.post(
            "/api/retrieval/query",
            json={"query": single["query"], "top_k": 3},
        )
        assert first.status_code == 200, first.text
        body = first.json()
        result = ProcedureRetrievalResult.model_validate(body)
        assert result.embedding_model.model_id == LOCKED_EMBED_MODEL
        assert result.reranker_model.model_id == LOCKED_RERANK_MODEL
        assert result.corpus_sha256 == real_nim_build_evidence["corpus_sha256"]
        assert result.index_sha256 == real_nim_build_evidence["index_sha256"]
        _assert_ranking_invariants(result, real_nim_build_evidence["index"])
        text = json.dumps(body)
        _assert_secrets_absent(text, real_nim_api_key)
        assert "vector" not in text
        assert "planner" not in body
        assert "simulator" not in body
        assert "plan" not in body
        for match in body["matches"]:
            manual_path = match["chunk"]["manual_path"]
            assert not manual_path.startswith("/")
            assert not manual_path.startswith("\\")
            assert manual_path.startswith("docs/")
            assert "vector" not in match
            assert "vector" not in match["chunk"]

        service_ref = client.app.state.procedure_retrieval_service
        assert service_ref is not None

        second = client.post(
            "/api/retrieval/query",
            json={"query": compound["query"], "top_k": 10},
        )
        assert second.status_code == 200, second.text
        compound_result = ProcedureRetrievalResult.model_validate(second.json())
        _assert_ranking_invariants(compound_result, real_nim_build_evidence["index"])
        returned_ids = {m.chunk.procedure_id for m in compound_result.matches}
        assert set(compound["expected_procedure_ids"]).issubset(returned_ids)
        assert client.app.state.procedure_retrieval_service is service_ref
        assert client.app.state.nvidia_nim_client is not None
        _assert_secrets_absent(json.dumps(second.json()), real_nim_api_key)


def test_startup_restart_stable_ordering(
    valid_layout: dict[str, Path],
    real_nim_build_evidence: dict[str, Any],
    real_nim_api_key: str,
) -> None:
    settings = _retrieval_settings(
        valid_layout,
        index_path=real_nim_build_evidence["index_path"],
        api_key=real_nim_api_key,
    )
    query = _load_release_queries()[0]["query"]
    index_bytes_before = real_nim_build_evidence["index_path"].read_bytes()

    with TestClient(create_app(settings_override=settings)) as client_a:
        assert client_a.app.state.procedure_retrieval_service is not None
        response_a = client_a.post(
            "/api/retrieval/query",
            json={"query": query, "top_k": 3},
        )
        assert response_a.status_code == 200
        result_a = ProcedureRetrievalResult.model_validate(response_a.json())
        ids_a = [m.chunk_id for m in result_a.matches]
        meta_a = (
            result_a.embedding_model.model_id,
            result_a.reranker_model.model_id,
            result_a.corpus_sha256,
            result_a.index_sha256,
        )

    with TestClient(create_app(settings_override=settings)) as client_b:
        assert client_b.app.state.procedure_retrieval_service is not None
        response_b = client_b.post(
            "/api/retrieval/query",
            json={"query": query, "top_k": 3},
        )
        assert response_b.status_code == 200
        result_b = ProcedureRetrievalResult.model_validate(response_b.json())
        ids_b = [m.chunk_id for m in result_b.matches]
        meta_b = (
            result_b.embedding_model.model_id,
            result_b.reranker_model.model_id,
            result_b.corpus_sha256,
            result_b.index_sha256,
        )

    assert meta_a == meta_b
    assert ids_a == ids_b
    assert real_nim_build_evidence["index_path"].read_bytes() == index_bytes_before


def test_cwd_independence_app_startup(
    valid_layout: dict[str, Path],
    real_nim_build_evidence: dict[str, Any],
    real_nim_api_key: str,
    real_nim_workspace: Path,
) -> None:
    settings = _retrieval_settings(
        valid_layout,
        index_path=real_nim_build_evidence["index_path"],
        api_key=real_nim_api_key,
    )
    alt_cwd = real_nim_workspace / "app_cwd"
    alt_cwd.mkdir(exist_ok=True)
    before = set(alt_cwd.rglob("*"))
    previous = Path.cwd()
    query = _load_release_queries()[0]["query"]
    try:
        os.chdir(alt_cwd)
        with TestClient(create_app(settings_override=settings)) as client:
            assert client.app.state.procedure_retrieval_service is not None
            response = client.post(
                "/api/retrieval/query",
                json={"query": query, "top_k": 3},
            )
            assert response.status_code == 200
            result = ProcedureRetrievalResult.model_validate(response.json())
            assert result.corpus_sha256 == real_nim_build_evidence["corpus_sha256"]
            assert result.index_sha256 == real_nim_build_evidence["index_sha256"]
        after = set(alt_cwd.rglob("*"))
        assert after == before
    finally:
        os.chdir(previous)


def test_artifact_integrity_after_retrieval(
    real_nim_build_evidence: dict[str, Any],
    real_nim_service: ProcedureRetrievalService,
    valid_layout: dict[str, Path],
) -> None:
    index_path: Path = real_nim_build_evidence["index_path"]
    before_bytes = index_path.read_bytes()
    before_hash = hashlib.sha256(before_bytes).hexdigest().lower()
    before_dir = sorted(p.name for p in index_path.parent.iterdir())
    before_manuals = real_nim_build_evidence["manual_hashes_before"]

    for entry in _load_release_queries():
        real_nim_service.retrieve(query=entry["query"], top_k=int(entry["top_k"]))

    assert index_path.read_bytes() == before_bytes
    assert hashlib.sha256(index_path.read_bytes()).hexdigest().lower() == before_hash
    assert sorted(p.name for p in index_path.parent.iterdir()) == before_dir
    assert _capture_manual_hashes() == before_manuals

    parent = index_path.parent
    assert not (parent / "query_cache.json").exists()
    assert not (parent / "rerank_cache.json").exists()
    assert not list(parent.glob("*cursor*"))
    assert not list(valid_layout["runs_dir"].glob("*"))
    assert not list(valid_layout["sessions_dir"].glob("*"))


def test_api_key_secrecy_across_outputs(
    real_nim_api_key: str,
    real_nim_build_evidence: dict[str, Any],
    valid_layout: dict[str, Path],
    caplog: pytest.LogCaptureFixture,
) -> None:
    settings = _retrieval_settings(
        valid_layout,
        index_path=real_nim_build_evidence["index_path"],
        api_key=real_nim_api_key,
    )
    query = _load_release_queries()[0]["query"]
    with caplog.at_level(logging.DEBUG):
        with TestClient(create_app(settings_override=settings)) as client:
            response = client.post(
                "/api/retrieval/query",
                json={"query": query, "top_k": 3},
            )
            assert response.status_code == 200
            bodies = [
                response.text,
                json.dumps(response.json()),
                real_nim_build_evidence.get("admin_script_stdout", ""),
                real_nim_build_evidence.get("admin_script_stderr", ""),
                "\n".join(r.getMessage() for r in caplog.records),
                repr(real_nim_build_evidence["client"]),
            ]
    for text in bodies:
        _assert_secrets_absent(text, real_nim_api_key)


def test_deferred_exclusion_end_to_end(
    real_nim_build_evidence: dict[str, Any],
    real_nim_service: ProcedureRetrievalService,
    valid_layout: dict[str, Path],
    real_nim_api_key: str,
) -> None:
    deferred = _deferred_procedure_ids()
    assert deferred == DEFERRED_PROCEDURE_IDS
    corpus = ProcedureCorpusBuilder(
        manifest_path=REAL_MANIFEST,
        manuals_root=REAL_MANUALS,
        repository_root=REPO_ROOT,
    ).build()
    index: EmbeddingIndexSnapshot = real_nim_build_evidence["index"]
    corpus_ids = {d.procedure_id for d in corpus.included_documents}
    excluded_ids = {d.procedure_id for d in corpus.excluded_documents}
    index_ids = {item.chunk.procedure_id for item in index.embedded_chunks}
    assert corpus_ids.isdisjoint(deferred)
    assert deferred.issubset(excluded_ids)
    assert index_ids.isdisjoint(deferred)

    for entry in _load_release_queries():
        result = real_nim_service.retrieve(
            query=entry["query"],
            top_k=int(entry["top_k"]),
        )
        result_ids = {m.chunk.procedure_id for m in result.matches}
        assert result_ids.isdisjoint(deferred)

    settings = _retrieval_settings(
        valid_layout,
        index_path=real_nim_build_evidence["index_path"],
        api_key=real_nim_api_key,
    )
    compound = next(q for q in _load_release_queries() if q["kind"] == "compound")
    with TestClient(create_app(settings_override=settings)) as client:
        response = client.post(
            "/api/retrieval/query",
            json={"query": compound["query"], "top_k": 10},
        )
        assert response.status_code == 200
        body = response.json()
        http_ids = {m["chunk"]["procedure_id"] for m in body["matches"]}
        assert http_ids.isdisjoint(deferred)
