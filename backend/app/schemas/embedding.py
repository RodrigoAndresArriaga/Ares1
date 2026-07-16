# Phase 4 Step 2 embedding / index snapshot contracts
# in-memory only; no query retrieval or vector DB
from __future__ import annotations

from typing import Annotated

from pydantic import BaseModel, Field, StrictFloat, model_validator

from app.schemas.common import CONTRACT_CONFIG, StrictInt
from app.schemas.retrieval import ProcedureChunk, Sha256Hex

EMBEDDING_SCHEMA_VERSION = "1.0.0"

NonEmptyStr = Annotated[str, Field(min_length=1)]


class EmbeddingModelDescriptor(BaseModel):
    model_config = CONTRACT_CONFIG

    provider: NonEmptyStr
    model_id: NonEmptyStr
    model_revision: str | None = None
    dimensions: StrictInt = Field(gt=0)


class RerankerModelDescriptor(BaseModel):
    model_config = CONTRACT_CONFIG

    provider: NonEmptyStr
    model_id: NonEmptyStr
    model_revision: str | None = None


class EmbeddedChunk(BaseModel):
    model_config = CONTRACT_CONFIG

    chunk: ProcedureChunk
    content_sha256: Sha256Hex
    embedding_text_sha256: Sha256Hex
    vector: tuple[StrictFloat, ...]

    @model_validator(mode="after")
    def _content_hash_matches_chunk(self) -> EmbeddedChunk:
        if self.content_sha256 != self.chunk.content_sha256:
            raise ValueError("content_sha256 must match chunk.content_sha256")
        if len(self.vector) == 0:
            raise ValueError("vector must be non-empty")
        return self


class EmbeddingIndexSnapshot(BaseModel):
    model_config = CONTRACT_CONFIG

    schema_version: NonEmptyStr
    corpus_sha256: Sha256Hex
    manifest_sha256: Sha256Hex
    embedding_model: EmbeddingModelDescriptor
    vector_dimensions: StrictInt = Field(gt=0)
    embedded_chunks: tuple[EmbeddedChunk, ...]
    index_sha256: Sha256Hex
    chunk_count: StrictInt = Field(ge=0)

    @model_validator(mode="after")
    def _consistency(self) -> EmbeddingIndexSnapshot:
        if self.chunk_count != len(self.embedded_chunks):
            raise ValueError("chunk_count must equal len(embedded_chunks)")
        if self.vector_dimensions != self.embedding_model.dimensions:
            raise ValueError("vector_dimensions must match embedding_model.dimensions")
        seen: set[str] = set()
        for item in self.embedded_chunks:
            if item.chunk.chunk_id in seen:
                raise ValueError("duplicate chunk_id in embedded_chunks")
            seen.add(item.chunk.chunk_id)
            if len(item.vector) != self.vector_dimensions:
                raise ValueError("vector length must match vector_dimensions")
        return self
