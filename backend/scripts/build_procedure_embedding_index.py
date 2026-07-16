# build and atomically replace the persistent procedure embedding index
# administrative/script operation only; never an HTTP query side effect
from __future__ import annotations

import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.core.config import Settings, get_settings  # noqa: E402
from app.integrations.nvidia_nim import NvidiaNimClient  # noqa: E402
from app.schemas.embedding import (  # noqa: E402
    EmbeddingModelDescriptor,
    RerankerModelDescriptor,
)
from app.services.procedure_embedding_index_builder import (  # noqa: E402
    ProcedureEmbeddingIndexBuilder,
)
from app.services.procedure_embedding_index_store import (  # noqa: E402
    ProcedureEmbeddingIndexStore,
)


def main() -> int:
    try:
        settings: Settings = get_settings()
        if settings.nvidia_api_key is None:
            print(
                "error: ARES_NVIDIA_API_KEY is required to build the index",
                file=sys.stderr,
            )
            return 1
        embed_model = EmbeddingModelDescriptor(
            provider="nvidia",
            model_id=settings.nvidia_embed_model_id,
            model_revision=settings.nvidia_embed_model_revision,
            dimensions=settings.nvidia_embed_dimensions,
        )
        rerank_model = RerankerModelDescriptor(
            provider="nvidia",
            model_id=settings.nvidia_rerank_model_id,
            model_revision=settings.nvidia_rerank_model_revision,
        )
        client = NvidiaNimClient(
            api_key=settings.nvidia_api_key.get_secret_value(),
            embed_base_url=settings.nvidia_embed_base_url,
            rerank_base_url=settings.nvidia_rerank_base_url,
            embed_model=embed_model,
            rerank_model=rerank_model,
            timeout_seconds=settings.nvidia_request_timeout_seconds,
            max_retries=settings.nvidia_max_retries,
            retry_backoff_seconds=settings.nvidia_retry_backoff_seconds,
        )
        store = ProcedureEmbeddingIndexStore(
            index_path=settings.procedure_embedding_index_path,
        )
        builder = ProcedureEmbeddingIndexBuilder(
            provider=client.embedding_provider,
            store=store,
            manifest_path=settings.procedure_manifest_path,
            manuals_root=settings.procedure_manuals_root,
            repository_root=settings.project_root,
            batch_size=settings.nvidia_embed_batch_size,
        )
        snapshot = builder.build_and_persist()
        print(
            "procedure embedding index built "
            f"chunk_count={snapshot.chunk_count} "
            f"index_sha256={snapshot.index_sha256} "
            f"corpus_sha256={snapshot.corpus_sha256} "
            f"manifest_sha256={snapshot.manifest_sha256} "
            f"model_id={snapshot.embedding_model.model_id} "
            f"dimensions={snapshot.vector_dimensions}"
        )
        return 0
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
