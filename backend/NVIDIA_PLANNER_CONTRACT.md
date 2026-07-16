# NVIDIA Planner Contract Lock — Phase 5 Step 1

Access date: 2026-07-15

Authority: official NVIDIA API Catalog / NIM OpenAPI pages only.

No real hosted calls are required for Step 1 tests.

---

## Planner — `nvidia/llama-3.3-nemotron-super-49b-v1`

### Official sources

| Title | URL |
| --- | --- |
| Creates a model response for the given chat conversation (OpenAPI) | https://docs.api.nvidia.com/nim/reference/nvidia-llama-3_3-nemotron-super-49b-v1-infer |
| nvidia / llama-3.3-nemotron-super-49b-v1 (model overview) | https://docs.api.nvidia.com/nim/reference/nvidia-llama-3_3-nemotron-super-49b-v1 |
| LLM APIs (hosted catalog) | https://docs.api.nvidia.com/nim/reference/llm-apis |
| Use Reasoning Models with NVIDIA NIM for LLMs | https://docs.nvidia.com/nim/large-language-models/latest/reasoning-model.html |

### Contract

| Item | Value |
| --- | --- |
| HTTP method | POST |
| Endpoint path | `/chat/completions` |
| Server | `https://integrate.api.nvidia.com/v1` |
| Auth header | `Authorization: Bearer $NVIDIA_API_KEY` |
| Model identifier | `nvidia/llama-3.3-nemotron-super-49b-v1` |
| Model version (model card) | 1.0 (2025-03-18) |
| Context length | 131,072 tokens (model overview) |
| Output context | 131,072 tokens (model overview) |

### Request JSON (OpenAPI `ChatCompletionRequest`)

Required field: `messages`.

Official schema sets `additionalProperties: false`. Fields documented for this model:

| Field | Type | Default | ARES-1 usage |
| --- | --- | --- | --- |
| `model` | string | `nvidia/llama-3.3-nemotron-super-49b-v1` | always send locked model ID |
| `messages` | array of `{role, content}` objects | — | system + user from `PlannerPromptPackage` |
| `stream` | boolean | `false` | always `false` (non-streaming) |
| `temperature` | number 0–1 | `0.6` | `0.0` (Reasoning OFF, greedy) |
| `top_p` | number (0, 1] | `0.95` | omitted when temperature is 0 |
| `max_tokens` | integer 1–16384 | `4096` | from `ARES_NVIDIA_PLANNER_MAX_TOKENS` |
| `stop` | string \| array \| null | null | not sent |
| `frequency_penalty` | number -2–2 | 0 | not sent |
| `presence_penalty` | number -2–2 | 0 | not sent |
| `seed` | integer 0–18446744073709552000 | 0 | not sent (prompt hash is backend-owned) |

Fields **not** in official OpenAPI for this model (do not send):

- `response_format`
- `json_schema`
- `tools` / `tool_choice`
- `enable_thinking` (documented for other Nemotron models; not in this model OpenAPI)

### Reasoning mode

Model overview: Reasoning ON/OFF is controlled via the system prompt.
ARES-1 sets Reasoning OFF by including `detailed thinking off` in the planner
system prompt. All planning instructions remain in the user prompt per model
guidance.

Reasoning ON defaults (not used by ARES-1): temperature `0.6`, top_p `0.95`.
Reasoning OFF: greedy decoding (temperature `0`).

### Response JSON shape (OpenAPI `ChatCompletionResponse`)

Required: `model`, `choices`, `usage`.

```json
{
  "id": "chatcmpl-123",
  "object": "chat.completion",
  "created": 1677652288,
  "model": "nvidia/llama-3.3-nemotron-super-49b-v1",
  "choices": [
    {
      "index": 0,
      "message": {
        "role": "assistant",
        "content": "..."
      },
      "finish_reason": "stop"
    }
  ],
  "usage": {
    "prompt_tokens": 9,
    "completion_tokens": 12,
    "total_tokens": 21
  }
}
```

### Assistant content location

`choices[0].message.content` — string. ARES-1 parses this string only.
No chain-of-thought, hidden reasoning, or non-`content` message fields are
stored or exposed.

### Finish reason behavior

| Value | ARES-1 action |
| --- | --- |
| `stop` | accept when content parses to `RecoveryPlan` |
| `length` | reject as incomplete (`PLANNER_RESPONSE_INCOMPLETE`) |
| `null` | reject as incomplete |

### Token / usage metadata

`usage.prompt_tokens`, `usage.completion_tokens`, `usage.total_tokens` may be
logged as counts only. Raw provider response bodies are never logged or returned.

### JSON mode / response_format

Not present in the official OpenAPI request schema for this exact model.
ARES-1 relies on strict prompt instructions plus backend strict JSON parsing
into the frozen `RecoveryPlan` schema. Do not invent a `response_format` field.

### Seed support

Documented in OpenAPI. ARES-1 omits `seed` because prompt determinism is
backend-owned via `prompt_sha256`; seed is best-effort only per NVIDIA docs.

### Retry / timeout / auth

Reuse Phase 4 `NvidiaNimClient._request_json` policy:

- Retry: HTTP 429, 500, 502, 503, 504; transport/timeout errors
- No retry: 401, 403, 400, invalid envelope, invalid plan JSON
- Auth: Bearer header; empty key rejected at client construction

### Implementation decisions

1. Derive endpoint from `ARES_NVIDIA_EMBED_BASE_URL` + `/chat/completions`.
2. One POST per `generate_plan` call.
3. Planner output is a candidate `RecoveryPlan` only; simulator validates.
4. Invalid model JSON is never repaired or re-requested.
5. Evidence traceability is backend-owned via `PlannerGenerationResult`.

### Official ambiguities

1. OpenAI-compatible docs mention optional fields not in this model's OpenAPI;
   ARES-1 sends only documented fields.
2. Reasoning-model docs describe `enable_thinking` for newer Nemotron models;
   this model uses system-prompt reasoning control instead.
3. `response_format` appears in general OpenAI docs but not in this model's
   locked OpenAPI schema.
