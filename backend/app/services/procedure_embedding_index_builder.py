# Phase 4 Step 3 administrative embedding index build + persist
# never invoked from HTTP query handlers or ordinary lifespan startup
from __future__ import annotations

import logging
from pathlib import Path

from app.core.logging import log_run_event
from app.schemas.embedding import EmbeddingIndexSnapshot
from app.services.embedding_index import EmbeddingIndexBuilder
from app.services.embedding_provider import EmbeddingProvider
from app.services.procedure_corpus import ProcedureCorpusBuilder
from app.services.procedure_embedding_index_store import ProcedureEmbeddingIndexStore

logger = logging.getLogger("ares.procedure_embedding_index_builder")


class ProcedureEmbeddingIndexBuilder:
    # Build corpus, embed once per chunk, persist strict snapshot atomically.
    def __init__(
        self,
        *,
        provider: EmbeddingProvider,
        store: ProcedureEmbeddingIndexStore,
        manifest_path: Path,
        manuals_root: Path,
        repository_root: Path | None = None,
        batch_size: int = 32,
    ) -> None:
        self._provider = provider
        self._store = store
        self._manifest_path = manifest_path
        self._manuals_root = manuals_root
        self._repository_root = repository_root
        self._batch_size = batch_size

    def build_and_persist(self) -> EmbeddingIndexSnapshot:
        model = self._provider.model
        log_run_event(
            logger,
            logging.INFO,
            "procedure embedding index build started",
            event="procedure_embedding_index_build_started",
            model_id=model.model_id,
        )
        corpus = ProcedureCorpusBuilder(
            manifest_path=self._manifest_path,
            manuals_root=self._manuals_root,
            repository_root=self._repository_root,
        ).build()
        snapshot = EmbeddingIndexBuilder(
            provider=self._provider,
            batch_size=self._batch_size,
        ).build(corpus)
        self._store.save(snapshot)
        log_run_event(
            logger,
            logging.INFO,
            "procedure embedding index build complete",
            event="procedure_embedding_index_build_complete",
            index_sha256=snapshot.index_sha256,
            corpus_sha256=snapshot.corpus_sha256,
            chunk_count=snapshot.chunk_count,
            model_id=model.model_id,
        )
        return snapshot
