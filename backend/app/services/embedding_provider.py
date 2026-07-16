# Phase 4 Step 2 embedding provider abstraction
# deterministic fake only; no remote embedding clients
from __future__ import annotations

import hashlib
import math
import struct
from collections.abc import Sequence
from typing import Protocol

from app.schemas.embedding import EmbeddingModelDescriptor


class EmbeddingProvider(Protocol):
    @property
    def model(self) -> EmbeddingModelDescriptor: ...

    def embed(self, texts: Sequence[str]) -> Sequence[Sequence[float]]: ...


class DeterministicFakeEmbeddingProvider:
    # stable float vectors from SHA-256 of each input text
    def __init__(self, *, model: EmbeddingModelDescriptor) -> None:
        self._model = model

    @property
    def model(self) -> EmbeddingModelDescriptor:
        return self._model

    def embed(self, texts: Sequence[str]) -> Sequence[Sequence[float]]:
        return tuple(self._vector_for(text) for text in texts)

    def _vector_for(self, text: str) -> tuple[float, ...]:
        digest = hashlib.sha256(text.encode("utf-8")).digest()
        dims = self._model.dimensions
        values: list[float] = []
        seed = digest
        while len(values) < dims:
            for i in range(0, len(seed) - 7, 8):
                raw = struct.unpack_from("<Q", seed, i)[0]
                # map to open unit interval excluding exact 0.0 for diversity
                unit = ((raw % 10_000_000) + 1) / 10_000_001.0
                values.append(math.sin(unit * math.pi))
                if len(values) >= dims:
                    break
            seed = hashlib.sha256(seed).digest()
        return tuple(values)
