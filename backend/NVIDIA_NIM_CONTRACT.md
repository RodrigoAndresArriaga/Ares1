# NVIDIA NIM Contract Lock — Phase 4 Step 3

Access date: 2026-07-15

Authority: official NVIDIA API Catalog / NIM OpenAPI pages only.
Supporting evidence (not payload authority): previously verified hosted access;
embed base `https://integrate.api.nvidia.com/v1`;
rerank URL
`https://ai.api.nvidia.com/v1/retrieval/nvidia/llama-nemotron-rerank-1b-v2/reranking`.

No real hosted calls are required for Step 3 tests.

---

## Embedder — `nvidia/llama-nemotron-embed-1b-v2`

### Official sources

| Title | URL |
| --- | --- |
| Creates an embedding vector from the input text (OpenAPI) | https://docs.api.nvidia.com/nim/reference/nvidia-llama-nemotron-embed-1b-v2-infer |
| nvidia / llama-nemotron-embed-1b-v2 (model overview) | https://docs.api.nvidia.com/nim/reference/nvidia-llama-nemotron-embed-1b-v2 |
| llama-nemotron-embed-1b-v2 (API Catalog) | https://build.nvidia.com/nvidia/llama-nemotron-embed-1b-v2 |

### Contract

| Item | Value |
| --- | --- |
| HTTP method | POST |
| Endpoint path | `/embeddings` |
| Server | `https://integrate.api.nvidia.com/v1` |
| Auth header | `Authorization: Bearer $NVIDIA_API_KEY` |
| Model identifier | `nvidia/llama-nemotron-embed-1b-v2` |
| Default embedding dimension | 2048 (model overview) |
| Max sequence length | 8192 tokens (model overview) |

### Request JSON (official example shape)

Content and API key replaced; structure unchanged from official OpenAPI example.

```json
{
  "input": "What is the capital of France?",
  "model": "nvidia/llama-nemotron-embed-1b-v2",
  "input_type": "query",
  "encoding_format": "float",
  "truncate": "NONE"
}
```

`input` may be a string or an array of strings (OpenAPI `oneOf`).

`input_type` enum: `passage` | `query`.
Official prose: use `passage` when indexing documents; use `query` when embedding queries.
Failure to use the correct `input_type` causes large retrieval accuracy drops.

Optional fields from OpenAPI: `encoding_format` (`float` \| `base64`, default `float`),
`truncate` (`NONE` \| `START` \| `END`, default `NONE`), `user` (ignored).

There is **no** `dimensions` field in this model's OpenAPI request schema.

### Response JSON shape (official)

```json
{
  "object": "list",
  "data": [
    {
      "index": 0,
      "embedding": [0.0],
      "object": "embedding"
    }
  ],
  "model": "nvidia/llama-nemotron-embed-1b-v2",
  "usage": {
    "prompt_tokens": 10,
    "total_tokens": 10
  }
}
```

(Official example returns a full 2048-float vector; abbreviated here.)

Ordering: each `data[].index` maps to the corresponding input position.
Clients must reorder by `index` before use.

Batching: array `input` is documented; no explicit max batch size in OpenAPI.
ARES uses a configurable server-side max batch size.

### Implementation decisions

- Always send `input_type`, `encoding_format="float"`, `truncate="NONE"`.
- Never send `dimensions`.
- Lock vector dimensions to 2048 in Settings / `EmbeddingModelDescriptor`.
- Document indexing calls use `input_type="passage"`.
- Query embedding calls use `input_type="query"`.

### Discrepancies / uncertainty

1. Prose requires `input_type`; OpenAPI `required` lists only `input` and `model`.
   Decision: always send `input_type`.
2. Model overview documents Matryoshka output dims (384/512/768/1024/2048);
   infer OpenAPI has no `dimensions` request field.
   Decision: use default 2048 only; do not invent a dimensions parameter.
3. OpenAPI describes input max as 32k tokens in one place and `maxLength: 4096`
   on the string schema in another.
   Decision: ARES chunks are soft-capped at 1800 characters; keep `truncate="NONE"`.

---

## Reranker — `nvidia/llama-nemotron-rerank-1b-v2`

### Official sources

| Title | URL |
| --- | --- |
| Rank passages by their relation to a query (OpenAPI) | https://docs.api.nvidia.com/nim/reference/nvidia-llama-nemotron-rerank-1b-v2-infer |
| nvidia / llama-nemotron-rerank-1b-v2 (model overview) | https://docs.api.nvidia.com/nim/reference/nvidia-llama-nemotron-rerank-1b-v2 |
| llama-nemotron-rerank-1b-v2 (API Catalog) | https://build.nvidia.com/nvidia/llama-nemotron-rerank-1b-v2 |

### Contract

| Item | Value |
| --- | --- |
| HTTP method | POST |
| Endpoint path | `/retrieval/nvidia/llama-nemotron-rerank-1b-v2/reranking` |
| Server | `https://ai.api.nvidia.com/v1` |
| Full URL | `https://ai.api.nvidia.com/v1/retrieval/nvidia/llama-nemotron-rerank-1b-v2/reranking` |
| Auth header | `Authorization: Bearer $NVIDIA_API_KEY` |
| Model identifier | `nvidia/llama-nemotron-rerank-1b-v2` |
| Passages limit | minItems 1, maxItems 1000 |
| Max sequence length | 8192 tokens (model overview) |

Note: embed and rerank hosts differ in official OpenAPI servers.

### Request JSON (official example shape)

```json
{
  "model": "nvidia/llama-nemotron-rerank-1b-v2",
  "query": {
    "text": "What is the GPU memory bandwidth of H100 SXM?"
  },
  "passages": [
    {
      "text": "Accelerated servers with H100 deliver the compute power..."
    },
    {
      "text": "A100 provides up to 20X higher performance..."
    }
  ]
}
```

Optional: `truncate` enum `NONE` | `END` (OpenAPI default `END`).

### Response JSON shape (official)

```json
{
  "rankings": [
    {
      "index": 2,
      "logit": 4.55078125
    },
    {
      "index": 0,
      "logit": -1.70703125
    },
    {
      "index": 1,
      "logit": -5.12109375
    }
  ],
  "usage": {
    "prompt_tokens": 233,
    "total_tokens": 233
  }
}
```

Ordering: examples return rankings sorted by relevance (descending logit).
`index` is the original passage index in the request `passages` array.

### Implementation decisions

- Separate Settings base URLs for embed vs rerank.
- Map `rankings[].logit` back to input document order via `index`.
- Require exact coverage: score count equals passage count, unique indices, finite logits.
- Expose raw logits as `rerank_score` (no sigmoid).
- Send `truncate="END"` unless Settings override.
- One rerank request per retrieval operation; no silent fallback to vector ranking.

### Discrepancies / uncertainty

1. Supporting evidence cited `integrate.api.nvidia.com` as a shared base URL;
   official rerank OpenAPI server is `https://ai.api.nvidia.com/v1`.
   Decision: use the official OpenAPI server for each model.
2. Schema does not explicitly guarantee that every input passage appears in `rankings`.
   Decision: fail closed unless rankings cover every input index exactly once.

---

## Shared auth

Both models use HTTP bearer auth (`Authorization: Bearer <key>`).
API keys load only from environment / Settings (`SecretStr`); never serialize into
responses, logs, errors, or `.env.example` with a real value.
