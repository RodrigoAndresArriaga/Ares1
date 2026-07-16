# POST /api/retrieval/query — thin bridge to ProcedureRetrievalService
from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from app.core.config import Settings
from app.core.errors import RetrievalIndexUnavailableError, RetrievalQueryInvalidError
from app.schemas.retrieval_query import (
    ProcedureRetrievalResult,
    RetrievalQueryRequest,
)
from app.services.procedure_retrieval import ProcedureRetrievalService

router = APIRouter(prefix="/retrieval", tags=["retrieval"])


def get_procedure_retrieval_service(request: Request) -> ProcedureRetrievalService:
    service = getattr(request.app.state, "procedure_retrieval_service", None)
    if service is None:
        raise RetrievalIndexUnavailableError(
            "procedure retrieval service is unavailable",
        )
    if not isinstance(service, ProcedureRetrievalService):
        raise RetrievalIndexUnavailableError(
            "procedure retrieval service is unavailable",
        )
    return service


@router.post(
    "/query",
    response_model=ProcedureRetrievalResult,
    status_code=200,
    summary="Retrieve cited procedure evidence for a query",
    description=(
        "Embed the query once, run deterministic cosine candidate retrieval, "
        "then mandatory NVIDIA reranking. Returns a strict cited evidence "
        "package. Does not rebuild the embedding index or guarantee mission "
        "success."
    ),
)
def query_retrieval(
    body: RetrievalQueryRequest,
    request: Request,
    service: ProcedureRetrievalService = Depends(get_procedure_retrieval_service),
) -> ProcedureRetrievalResult:
    settings: Settings = request.app.state.settings
    top_k = (
        settings.retrieval_default_top_k if body.top_k is None else body.top_k
    )
    if top_k > settings.retrieval_max_top_k:
        raise RetrievalQueryInvalidError(
            f"top_k must be <= {settings.retrieval_max_top_k}",
        )
    return service.retrieve(query=body.query, top_k=top_k)
