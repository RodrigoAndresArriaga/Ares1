# Phase 4 Step 3 retrieval query / result contracts
# in-memory cosine retrieval only; no routes or cross-encoder stages
from __future__ import annotations

from typing import Annotated

from pydantic import BaseModel, Field, StrictFloat, model_validator

from app.schemas.common import CONTRACT_CONFIG, StrictInt
from app.schemas.embedding import EmbeddingModelDescriptor
from app.schemas.retrieval import ProcedureChunk, Sha256Hex

RETRIEVAL_QUERY_SCHEMA_VERSION = "1.0.0"

NonEmptyStr = Annotated[str, Field(min_length=1)]


class ProcedureRetrievalMatch(BaseModel):
    model_config = CONTRACT_CONFIG

    rank: StrictInt = Field(ge=1)
    similarity: StrictFloat
    index_position: StrictInt = Field(ge=0)
    chunk_id: Sha256Hex
    chunk: ProcedureChunk

    @model_validator(mode="after")
    def _chunk_id_matches(self) -> ProcedureRetrievalMatch:
        if self.chunk_id != self.chunk.chunk_id:
            raise ValueError("chunk_id must match chunk.chunk_id")
        return self


class ProcedureRetrievalResult(BaseModel):
    model_config = CONTRACT_CONFIG

    schema_version: NonEmptyStr
    query: NonEmptyStr
    requested_top_k: StrictInt = Field(ge=1)
    returned_count: StrictInt = Field(ge=0)
    embedding_model: EmbeddingModelDescriptor
    corpus_sha256: Sha256Hex
    index_sha256: Sha256Hex
    matches: tuple[ProcedureRetrievalMatch, ...]

    @model_validator(mode="after")
    def _consistency(self) -> ProcedureRetrievalResult:
        if self.returned_count != len(self.matches):
            raise ValueError("returned_count must equal len(matches)")
        for expected_rank, match in enumerate(self.matches, start=1):
            if match.rank != expected_rank:
                raise ValueError("match ranks must be contiguous starting at 1")
        return self
