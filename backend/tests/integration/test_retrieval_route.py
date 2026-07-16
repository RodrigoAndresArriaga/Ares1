# Phase 4 Step 3 POST /api/retrieval/query integration tests
from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

import pytest
from app.core.errors import (
    NvidiaNimTimeoutError,
    RetrievalIndexUnavailableError,
)
from app.main import create_app
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
from app.services.procedure_retrieval import ProcedureRetrievalService
from fastapi.testclient import TestClient
from tests.conftest import settings_from_layout

_SHA = "a" * 64
_SHA_B = "b" * 64
_SHA_C = "c" * 64
_SHA_D = "d" * 64
_SHA_E = "e" * 64
_SHA_F = "f" * 64


def _evidence() -> EvidenceReference:
    return EvidenceReference(
        evidence_id="EVID-ARES_ASM-001",
        classification=SourceClassification.ARES_ASSUMPTION,
        source_title="Test",
        locator="unit-test",
        supports="Unit test evidence.",
        url="",
    )


def _chunk() -> ProcedureChunk:
    return ProcedureChunk(
        schema_version=CORPUS_SCHEMA_VERSION,
        chunk_id=_SHA,
        procedure_id="ARES-PROC-OXY-001",
        procedure_title="Oxygen Leak Response",
        manual_path="docs/procedures/manuals/oxygen_leak.md",
        section_path=("Purpose",),
        section_title="Purpose",
        chunk_index=0,
        content="Isolate the leaking module.",
        embedding_text="Procedure: Oxygen Leak Response\n\nIsolate the leaking module.",
        content_sha256=_SHA_B,
        manual_sha256=_SHA_C,
        source_classifications=(SourceClassification.ARES_ASSUMPTION,),
        evidence_references=(_evidence(),),
        allowed_actions=(ActionType.ISOLATE_MODULE,),
        procedure_status=ProcedureStatus.PARTIAL_EVIDENCE,
    )


class ScriptedProvider:
    def __init__(self) -> None:
        self.model = EmbeddingModelDescriptor(
            provider="fake",
            model_id="deterministic-fake",
            model_revision="1",
            dimensions=2,
        )
        self.calls = 0

    def embed(
        self,
        texts: Sequence[str],
        *,
        input_type: str = "passage",
    ) -> Sequence[Sequence[float]]:
        _ = texts, input_type
        self.calls += 1
        return ((1.0, 0.0),)


class FakeReranker:
    def __init__(self) -> None:
        self.model = RerankerModelDescriptor(
            provider="fake",
            model_id="deterministic-rerank",
            model_revision="1",
        )
        self.calls = 0

    def rerank(
        self,
        *,
        query: str,
        documents: Sequence[str],
    ) -> tuple[float, ...]:
        _ = query
        self.calls += 1
        return tuple(float(len(documents) - i) for i in range(len(documents)))


def _index() -> EmbeddingIndexSnapshot:
    chunk = _chunk()
    return EmbeddingIndexSnapshot(
        schema_version=EMBEDDING_SCHEMA_VERSION,
        corpus_sha256=_SHA_E,
        manifest_sha256=_SHA_D,
        embedding_model=EmbeddingModelDescriptor(
            provider="fake",
            model_id="deterministic-fake",
            model_revision="1",
            dimensions=2,
        ),
        vector_dimensions=2,
        embedded_chunks=(
            EmbeddedChunk(
                chunk=chunk,
                content_sha256=chunk.content_sha256,
                embedding_text_sha256=_SHA_F,
                vector=(1.0, 0.0),
            ),
        ),
        index_sha256=_SHA_F,
        chunk_count=1,
    )


def _service() -> ProcedureRetrievalService:
    return ProcedureRetrievalService(
        index=_index(),
        provider=ScriptedProvider(),
        reranker=FakeReranker(),
        rerank_candidate_count=20,
        max_top_k=10,
    )


def test_retrieval_query_200_and_openapi(valid_layout: dict[str, Path]) -> None:
    settings = settings_from_layout(
        valid_layout,
        procedure_embedding_index_path=valid_layout["project_root"]
        / "retrieval"
        / "index.json",
    )
    service = _service()
    app = create_app(
        settings_override=settings,
        procedure_retrieval_service_override=service,
    )
    with TestClient(app) as client:
        response = client.post(
            "/api/retrieval/query",
            json={"query": "oxygen leak", "top_k": 1},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["returned_count"] == 1
        assert body["matches"][0]["chunk"]["allowed_actions"] == ["isolate_module"]
        assert "rerank_score" in body["matches"][0]
        assert "vector" not in body["matches"][0]
        assert API_KEY_ABSENT(body)
        schema = client.get("/openapi.json").json()
        assert "/api/retrieval/query" in schema["paths"]
        assert client.app.state.procedure_retrieval_service is service


def API_KEY_ABSENT(payload: object) -> bool:
    text = json_dumps(payload)
    return "nvapi-" not in text and "Bearer " not in text and "secret" not in text.lower()


def json_dumps(payload: object) -> str:
    import json

    return json.dumps(payload)


def test_unknown_fields_and_invalid_top_k(valid_layout: dict[str, Path]) -> None:
    settings = settings_from_layout(
        valid_layout,
        procedure_embedding_index_path=valid_layout["project_root"]
        / "retrieval"
        / "index.json",
    )
    app = create_app(
        settings_override=settings,
        procedure_retrieval_service_override=_service(),
    )
    with TestClient(app, raise_server_exceptions=False) as client:
        unknown = client.post(
            "/api/retrieval/query",
            json={"query": "oxygen", "model_id": "x"},
        )
        assert unknown.status_code == 422
        empty = client.post("/api/retrieval/query", json={"query": ""})
        assert empty.status_code == 422
        bad_top = client.post(
            "/api/retrieval/query",
            json={"query": "oxygen", "top_k": 0},
        )
        assert bad_top.status_code == 422
        over = client.post(
            "/api/retrieval/query",
            json={"query": "oxygen", "top_k": 99},
        )
        assert over.status_code == 400
        assert over.json()["code"] == "RETRIEVAL_QUERY_INVALID"


def test_missing_service_and_nim_timeout_safe(
    valid_layout: dict[str, Path],
) -> None:
    settings = settings_from_layout(
        valid_layout,
        procedure_embedding_index_path=valid_layout["project_root"]
        / "retrieval"
        / "index.json",
    )
    app = create_app(settings_override=settings)
    app.state.procedure_retrieval_service = None
    with TestClient(app, raise_server_exceptions=False) as client:
        missing = client.post(
            "/api/retrieval/query",
            json={"query": "oxygen"},
        )
        assert missing.status_code == 503
        assert missing.json()["code"] == "RETRIEVAL_INDEX_UNAVAILABLE"
        body_text = missing.text
        assert str(settings.procedure_embedding_index_path) not in body_text

    class TimeoutService(ProcedureRetrievalService):
        def retrieve(self, *, query: str, top_k: int | None = None):  # type: ignore[override]
            raise NvidiaNimTimeoutError("NVIDIA NIM request timed out")

    timeout_app = create_app(
        settings_override=settings,
        procedure_retrieval_service_override=TimeoutService(
            index=_index(),
            provider=ScriptedProvider(),
            reranker=FakeReranker(),
            rerank_candidate_count=20,
            max_top_k=10,
        ),
    )
    with TestClient(timeout_app, raise_server_exceptions=False) as client:
        timed = client.post(
            "/api/retrieval/query",
            json={"query": "oxygen"},
        )
        assert timed.status_code == 504
        assert timed.json()["code"] == "NVIDIA_NIM_TIMEOUT"
        assert "nvapi" not in timed.text.lower()


def test_unavailable_error_type() -> None:
    with pytest.raises(RetrievalIndexUnavailableError):
        raise RetrievalIndexUnavailableError()
