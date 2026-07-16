# ARES-1 Phase 3 Mission Lifecycle and Telemetry Replay Backend Implementation Guide

**Frozen C++ Simulator + Phase 1 FastAPI Bridge + Phase 2 Procedure Corpus**

## Ownership rule

Cursor implements the complete Phase 3 Python backend described in this guide. The user reviews architecture, contracts, and release gates. Documentation is authored and approved outside Cursor.

The C++ simulator remains frozen and is the sole authority for mission physics, crew physiology, action execution, validation, telemetry values, mission status, metrics, timeline, failure reasons, and final outcome.

## Development principle

> The session coordinates. The simulator computes. The replay preserves.

Phase 3 must not become a telemetry generator or second simulator. It creates mission sessions, triggers the already-registered compound accident, executes the existing baseline simulation, persists the relationship between the mission session and the Phase 1 run artifact, and replays the simulator's exact telemetry history to clients.

---

## Document contents

1. Boundary, authority, and ownership rules  
2. Phase 3 objective and locked scope  
3. Architectural decisions  
4. Mission lifecycle state machine  
5. Nominal-state policy  
6. Required repository structure  
7. Component responsibilities and dependency direction  
8. Configuration  
9. Pydantic contracts  
10. Session artifact store  
11. Existing run-result retrieval  
12. Mission lifecycle service  
13. Accident trigger  
14. Replay clock and deterministic indexing  
15. Server-Sent Events transport  
16. Current telemetry endpoint  
17. API routes and response semantics  
18. Error model  
19. Security, concurrency, and restart behavior  
20. Testing strategy  
21. Exact implementation order  
22. Build and run commands  
23. Phase 3 release gate  
24. Cursor execution prompts  
Appendix A. File responsibility matrix  
Appendix B. State transition matrix  
Appendix C. SSE event contract  

## How to use this guide

Give Cursor one implementation section at a time. Cursor must inspect the current repository before editing, implement only the requested section, run the named tests, report changed files and command results, then stop.

Do not provide the entire guide as one unconstrained implementation request.

---

# 1. Boundary, Authority, and Ownership Rules

## 1.1 Frozen simulator authority

The C++ simulator owns:

- every physical state transition;
- atmosphere, power, thermal, EVA, communications, and crew calculations;
- action execution and dynamic feasibility;
- warning and hard-failure evaluation;
- stabilization logic;
- mission status;
- final outcome;
- metrics;
- timeline events;
- telemetry history;
- failure reasons.

Phase 3 may select and replay existing samples. It must not recalculate, interpolate, normalize, clamp, thin, or repair them.

## 1.2 Phase 1 backend authority

The existing Phase 1 backend remains responsible for:

- strict request and result validation;
- registered scenario resolution;
- isolated run workspaces;
- safe subprocess execution;
- simulator timeout and concurrency control;
- exact result parsing;
- run artifact persistence;
- unchanged simulator-result delivery.

Phase 3 must reuse `SimulationService`, `ScenarioRegistry`, `RunStore`, `SimulatorClient`, and existing strict schemas. It must not create a parallel subprocess path.

## 1.3 Phase 2 procedure corpus

The validated procedure corpus is present, but Phase 3 does not parse, chunk, embed, retrieve, rerank, or inject it.

The procedure corpus becomes executable infrastructure in Phase 4.

## 1.4 Cursor responsibility

Cursor may implement:

- mission-session schemas;
- session artifact persistence;
- mission lifecycle orchestration;
- accident-trigger routes;
- baseline-run linkage;
- run-result retrieval;
- deterministic telemetry replay;
- SSE transport;
- current telemetry lookup;
- typed errors;
- focused tests;
- Phase 3 documentation updates and release evidence.

Cursor may not author or rewrite procedure manuals.

## 1.5 User responsibility

The user:

- approves lifecycle and API contracts;
- reviews diffs;
- rejects duplicated simulator logic;
- verifies that replayed telemetry remains value-equivalent;
- authorizes each next implementation section.

## 1.6 Non-negotiable rules

1. Do not modify `Simulator/`, its tests, release fixtures, equations, serializers, or numerical behavior.
2. Do not modify the six procedure manuals except through a separately approved documentation task.
3. Do not implement NVIDIA NIM clients.
4. Do not implement RAG parsing, embeddings, vector storage, retrieval, or reranking.
5. Do not implement planner prompts or AI plan generation.
6. Do not implement frontend code.
7. Do not introduce a database or authentication system.
8. Do not add `survival_probability`.
9. `FAILURE` and `REJECTED` remain valid simulator results, not HTTP infrastructure errors.
10. Every replayed `TelemetrySample` must be the existing strict model parsed from the simulator result.
11. Backend lifecycle status must never be represented as simulator `mission_status`.
12. No arbitrary filesystem path may be accepted from a client.

---

# 2. Phase 3 Objective and Locked Scope

## 2.1 Final Phase 3 flow

```text
Create mission session
        ↓
Session is READY / accident not triggered
        ↓
Trigger registered compound accident
        ↓
Reuse Phase 1 SimulationService with no plan
        ↓
Persist baseline run_id and strict simulator result relationship
        ↓
Start deterministic replay clock
        ↓
Stream exact telemetry_history samples over SSE
        ↓
Expose current authoritative sample and final result
        ↓
Complete with simulator baseline outcome
```

The release fixture is expected to produce `FAILURE` with no plan. Production code must not overwrite or fabricate this outcome if the simulator changes.

## 2.2 Included deliverables

| Deliverable | Required result |
|---|---|
| Mission-session schemas | Strict lifecycle and API contracts |
| SessionStore | Isolated, auditable filesystem session records |
| MissionLifecycleService | Creates sessions and coordinates accident trigger |
| Baseline run linkage | Stores the Phase 1 `run_id`; no duplicate result calculation |
| Result retrieval | Retrieves a strict persisted result by trusted `run_id` |
| ReplayClock | Deterministically maps wall time to telemetry sample index |
| TelemetryReplayService | Selects exact samples without mutation |
| SSE endpoint | Streams ordered samples and supports reconnection |
| Current telemetry endpoint | Returns the sample authoritative at the current replay position |
| Mission routes | Create/read session, trigger accident, start replay |
| Tests | Lifecycle, persistence, replay, SSE, determinism, concurrency, security |
| Release evidence | Phase 3 gate report and updated README |

## 2.3 Excluded work

| Excluded item | Reason |
|---|---|
| Numerical nominal telemetry generation | Backend cannot invent pre-fault physical state |
| New C++ scenario behavior | Simulator is frozen |
| Procedure parsing and chunking | Phase 4 |
| NVIDIA embedder/reranker/planner | Phases 4–5 |
| AI diagnosis | Phase 5 |
| Recovery-plan execution through lifecycle | Phase 5 |
| Baseline-versus-ARES comparison | Phase 5/6 |
| Next.js, Open MCT, Three.js | Phase 6 |
| Database/authentication | Outside hackathon MVP |
| Pause/seek/edit controls | Not required for Phase 3 |
| Multi-scenario mission operations | Current MVP uses one registered release scenario |

## 2.4 Phase exit condition

The backend must prove:

```text
READY session
→ one valid accident trigger
→ existing baseline simulation
→ persisted run/result relationship
→ deterministic ordered replay
→ reconnect-safe SSE
→ exact final simulator result
```

No replay code may change a telemetry value.

---

# 3. Architectural Decisions

## 3.1 Transport: Server-Sent Events

Use SSE, not WebSockets, for Phase 3.

Reason:

- replay is primarily server-to-client;
- command operations remain ordinary HTTP POST requests;
- browser reconnection and `Last-Event-ID` are built in;
- the protocol is simpler to test and operate;
- no bidirectional socket state is needed.

## 3.2 Replay model: persisted start time, derived cursor

The replay cursor is derived rather than advanced by a permanent background task.

Persist:

- `replay_started_at`;
- `sample_interval_ms`;
- sample count.

At time `now`, derive:

```text
elapsed_ms = max(0, now - replay_started_at)
current_index = min(sample_count - 1, floor(elapsed_ms / sample_interval_ms))
```

Advantages:

- multiple clients observe the same session position;
- backend restart does not require restoring a background coroutine;
- current telemetry is deterministic;
- SSE clients may reconnect and catch up;
- no mutable per-sample cursor file is required.

`sample_interval_ms = 0` is allowed only in test/internal instant-replay mode if configuration explicitly permits it. Production HTTP requests must use a configured positive bounded value.

## 3.3 Replay source

The only replay source is:

```text
SimulationResult.telemetry_history
```

The replay layer must not read raw unvalidated JSON after initial validation unless it validates it again through the strict `SimulationResult` model.

## 3.4 Baseline execution

Accident trigger calls the existing Phase 1 `SimulationService` with:

- registered release scenario ID;
- no plan.

It must not invoke `SimulatorClient` directly.

## 3.5 Storage

Use filesystem storage under a configured session root:

```text
backend/data/sessions/<session_id>/session.json
```

The Phase 1 run artifact remains in the existing runs root. The session record stores the trusted `baseline_run_id`; it does not copy or rewrite the canonical simulator result unless the current RunStore contract requires an immutable reference copy.

## 3.6 No global current mission

All mission APIs are scoped by `session_id`.

Do not add a mutable singleton `/api/telemetry` state. A compatibility endpoint may be added later only after a frontend contract requires one.

---

# 4. Mission Lifecycle State Machine

## 4.1 Lifecycle enum

Use exact backend lifecycle values:

```text
READY
TRIGGERING
BASELINE_READY
REPLAYING
COMPLETED
ERROR
```

These values are backend orchestration states. They are not simulator mission statuses.

## 4.2 State meaning

| State | Meaning |
|---|---|
| `READY` | Session exists. Accident has not been triggered. No numerical telemetry is claimed. |
| `TRIGGERING` | Baseline simulator execution is in progress. |
| `BASELINE_READY` | Strict baseline result is persisted and linked. Replay has not started. |
| `REPLAYING` | `replay_started_at` exists and the final sample is not yet due. |
| `COMPLETED` | Final replay sample is due or has been emitted. |
| `ERROR` | Infrastructure failure prevented the lifecycle from continuing. |

## 4.3 Allowed transitions

```text
READY → TRIGGERING
TRIGGERING → BASELINE_READY
TRIGGERING → ERROR
BASELINE_READY → REPLAYING
REPLAYING → COMPLETED
COMPLETED → REPLAYING    only through explicit replay restart
```

Disallowed transitions return a typed state-conflict error.

## 4.4 Idempotency

- Creating a session always creates a new UUID.
- Triggering an accident twice must not create a second baseline run.
- Preferred duplicate-trigger behavior: `409 MISSION_STATE_CONFLICT`.
- Replay start while already replaying returns `409` unless `restart=true`.
- Replay restart reuses the same baseline result and creates no new simulator run.

---

# 5. Nominal-State Policy

The project demo requires a nominal presentation before accident trigger. The backend must not fabricate numerical nominal telemetry.

## 5.1 Locked distinction

Before trigger:

```text
lifecycle_status = READY
```

This means the mission session is armed and awaiting accident trigger. It does not prove that the simulator emitted a nominal physical snapshot.

## 5.2 Section 1 audit requirement

Before implementation, inspect:

- the baseline result's first telemetry sample;
- its `simulation_time_min`;
- its events;
- its `mission_status`;
- whether the fault is already active at that sample;
- C++ timestep ordering and initial snapshot behavior.

## 5.3 Allowed nominal presentation strategies

Use the first strategy supported by evidence:

1. **Authoritative pre-fault sample exists:** expose it exactly.
2. **First sample is already post-fault:** expose no numerical nominal telemetry before trigger; return lifecycle metadata only.
3. **Future approved nominal scenario:** add only through a separate user-approved simulator-data task.

Phase 3 must not create an inferred numerical snapshot from scenario configuration.

---

# 6. Required Repository Structure

Cursor should extend the current backend approximately as follows, adapting to the real repository:

```text
backend/
├── app/
│   ├── api/routes/
│   │   ├── health.py
│   │   ├── simulation.py
│   │   └── missions.py
│   ├── core/
│   │   ├── config.py
│   │   ├── errors.py
│   │   └── logging.py
│   ├── schemas/
│   │   ├── mission.py
│   │   ├── replay.py
│   │   └── existing Phase 1 schemas...
│   └── services/
│       ├── mission_lifecycle_service.py
│       ├── replay_clock.py
│       ├── session_store.py
│       ├── telemetry_replay_service.py
│       └── existing Phase 1 services...
├── data/
│   ├── runs/
│   └── sessions/
├── tests/
│   ├── unit/
│   └── integration/
└── RELEASE_GATE_PHASE_3.md
```

Do not create a duplicate backend package or separate application.

---

# 7. Component Responsibilities and Dependency Direction

## 7.1 Component table

| Component | Responsibility |
|---|---|
| Mission route | HTTP parsing, status codes, response serialization |
| MissionLifecycleService | Creates sessions and coordinates state transitions |
| SessionStore | Persists strict session records atomically |
| SimulationService | Executes the existing baseline simulator run |
| RunStore | Owns persisted run artifacts and strict result retrieval |
| ReplayClock | Converts timestamps to deterministic sample indexes |
| TelemetryReplayService | Selects exact samples and creates SSE envelopes |
| SSE route | Streams service envelopes and handles disconnect/reconnect |
| Pydantic schemas | Strict lifecycle, replay, and response contracts |
| C++ simulator | Computes all engineering state and outcome |

## 7.2 Dependency direction

```text
missions route
    → MissionLifecycleService
        → SessionStore
        → SimulationService
            → ScenarioRegistry + RunStore + SimulatorClient

missions stream route
    → TelemetryReplayService
        → SessionStore
        → RunStore
        → ReplayClock
```

## 7.3 Architecture rules

- Routes remain thin.
- SessionStore launches no process.
- ReplayClock performs no I/O.
- Replay service does not know HTTP response codes.
- SimulationService does not know mission lifecycle state.
- RunStore does not know replay timing.
- Pydantic models perform no filesystem or subprocess work.
- No service recalculates simulator telemetry.

---

# 8. Configuration

Extend settings only after inspecting the current configuration pattern.

Recommended environment variables:

```env
ARES_SESSIONS_DIR=./data/sessions
ARES_REPLAY_DEFAULT_INTERVAL_MS=250
ARES_REPLAY_MIN_INTERVAL_MS=25
ARES_REPLAY_MAX_INTERVAL_MS=60000
ARES_MAX_REPLAY_STREAMS=20
ARES_SSE_HEARTBEAT_SECONDS=15
```

## 8.1 Validation rules

| Setting | Rule |
|---|---|
| Sessions directory | Resolve independently of CWD; create if missing; verify writable |
| Default interval | Positive and within min/max |
| Minimum interval | Positive |
| Maximum interval | Greater than or equal to minimum |
| Max streams | Integer greater than zero |
| Heartbeat | Positive finite value |

## 8.2 Test settings

Tests may inject:

- temporary session root;
- zero or near-zero interval through a direct service override;
- fake clock;
- fake sleeper;
- lower heartbeat.

Do not weaken production HTTP validation to accelerate tests.

---

# 9. Pydantic Contracts

Use Pydantic v2 with `extra="forbid"`.

## 9.1 `MissionSessionStatus`

Exact values:

```text
READY
TRIGGERING
BASELINE_READY
REPLAYING
COMPLETED
ERROR
```

## 9.2 `MissionCreateRequest`

Required:

- `scenario_id`

Do not accept paths, plan data, command arguments, output paths, or binary paths.

## 9.3 `MissionSession`

Required fields:

- `session_id`
- `scenario_id`
- `status`
- `created_at`
- `updated_at`
- `accident_triggered_at`
- `baseline_run_id`
- `baseline_outcome`
- `telemetry_sample_count`
- `replay_started_at`
- `replay_interval_ms`
- `error_code`

Optionality must reflect lifecycle state.

## 9.4 HTTP and replay models

Implement strict models for:

- `MissionCreateResponse`
- `AccidentTriggerResponse`
- `ReplayStartRequest`
- `ReplayStartResponse`
- `CurrentTelemetryResponse`
- `ReplayTelemetryEvent`
- `ReplayCompleteEvent`

The nested telemetry object must use the current strict `TelemetrySample` schema. Completion values come from the strict simulator result.

## 9.5 State consistency validation

Examples:

- `READY` must not have `baseline_run_id`.
- `BASELINE_READY` must have a run ID, outcome, sample count, and no replay start.
- `REPLAYING` and `COMPLETED` must have replay start and interval.
- `ERROR` must have an `error_code`.
- `telemetry_sample_count` must be positive after baseline completion.

Do not encode engineering feasibility.

---

# 10. Session Artifact Store

## 10.1 Directory structure

```text
sessions/
└── <uuid>/
    └── session.json
```

An append-only lifecycle log is optional and must be justified and tested.

## 10.2 Required behavior

`SessionStore` must:

- create UUID-based isolated directories;
- reject identifiers that are not valid UUIDs;
- resolve paths and verify containment;
- write strict canonical JSON atomically;
- read and validate through `MissionSession`;
- update through current-state logic;
- preserve UTC timezone-aware timestamps;
- survive process restart;
- avoid global mutable caches as source of truth.

## 10.3 Concurrency

Use per-session async locks for in-process state transitions.

The filesystem record remains authoritative for restart. Phase 3 assumes one backend process unless later revised.

---

# 11. Existing Run-Result Retrieval

Extend the existing `RunStore` only as required.

Provide typed methods equivalent to:

```python
async def read_result(self, run_id: UUID) -> SimulationResult: ...
async def read_metadata(self, run_id: UUID) -> RunMetadata: ...
```

Adapt names to current architecture.

Security requirements:

- validate run ID format;
- resolve contained path;
- require result artifact;
- validate JSON through `SimulationResult`;
- do not expose absolute paths;
- do not scan arbitrary directories from request input.

Add:

```http
GET /api/sim/result/{run_id}
```

A simulator `FAILURE` result returns HTTP `200` when the artifact is valid.

---

# 12. Mission Lifecycle Service

## 12.1 `create_session`

1. Validate `scenario_id` through `ScenarioRegistry`.
2. Create a strict `READY` session.
3. Persist it.
4. Return it.

Do not run the simulator during session creation.

## 12.2 `trigger_accident`

1. Acquire per-session lock.
2. Read session and require `READY`.
3. Persist `TRIGGERING`.
4. Call existing `SimulationService` with scenario ID and no plan.
5. Require non-empty `telemetry_history`.
6. Persist `BASELINE_READY`, trigger timestamp, baseline run ID, exact outcome, and sample count.
7. Return summary.

If infrastructure execution fails, persist `ERROR` with a stable code and re-raise the typed infrastructure error. Do not fabricate a result.

## 12.3 `start_replay`

1. Acquire session lock.
2. Require `BASELINE_READY`, or `COMPLETED` with `restart=true`.
3. Validate interval.
4. Persist `REPLAYING`, current UTC start time, and interval.
5. Return session and relative endpoint paths.

No simulator rerun occurs.

---

# 13. Accident Trigger

The accident trigger is an orchestration action. It selects the registered failure scenario and launches its no-plan baseline run.

Current scenario:

```text
mars_hab_atmosphere_solar_failure
```

Limitations:

- one trigger per session;
- no arbitrary accident payload;
- no client-supplied fault values;
- no scenario-file mutation;
- no inline plan;
- no direct executable call.

Recommended route:

```http
POST /api/missions/{session_id}/accident
```

Successful infrastructure execution returns `200`, including a simulator `FAILURE` result. Invalid lifecycle state returns `409`.

---

# 14. Replay Clock and Deterministic Indexing

## 14.1 Pure `ReplayClock`

Inputs:

- replay start UTC datetime;
- current UTC datetime;
- interval milliseconds;
- sample count.

Outputs:

- current sample index;
- completion flag;
- milliseconds until next sample.

## 14.2 Index formula

```text
index = floor(elapsed_ms / interval_ms)
index = clamp(index, 0, sample_count - 1)
complete = elapsed_ms >= interval_ms * (sample_count - 1)
```

The first sample is due immediately when replay starts.

## 14.3 Sequence IDs and resume

Telemetry event sequence equals sample index. Completion event sequence equals sample count.

Parse `Last-Event-ID` as an integer:

- absent: begin at sample 0;
- telemetry event ID `n`: begin at `n + 1`;
- invalid, negative, or out of range: stable `400`.

A reconnecting client receives missed exact samples in order, then future samples at the configured pace.

## 14.4 No interpolation

If wall time advances across multiple intervals, emit each missing authoritative sample. Never interpolate.

---

# 15. Server-Sent Events Transport

Endpoint:

```http
GET /api/missions/{session_id}/stream
```

Replay must already be started.

## 15.1 Event types

- `telemetry`: one exact sample per event;
- `complete`: final simulator-result summary;
- `heartbeat`: no physical state and no sequence ID;
- `error`: stream infrastructure errors only.

Telemetry frame:

```text
id: <sequence>
event: telemetry
data: <ReplayTelemetryEvent JSON>

```

Completion frame:

```text
id: <sample_count>
event: complete
data: <ReplayCompleteEvent JSON>

```

## 15.2 Required behavior

- `text/event-stream` response;
- no-cache behavior;
- proxy buffering disabled when supported;
- disconnect detection;
- shared stream semaphore;
- equivalent ordered values for multiple clients;
- heartbeat only when no telemetry is due within the configured interval.

A disconnect does not mutate mission state.

---

# 16. Current Telemetry Endpoint

Add:

```http
GET /api/missions/{session_id}/telemetry
```

Preferred behavior:

- `READY`: `409`;
- `TRIGGERING`: `409`;
- `BASELINE_READY`: `409 REPLAY_NOT_STARTED`;
- `REPLAYING`: derive current index and return exact sample;
- `COMPLETED`: return final sample.

The endpoint must not alter the nested sample.

---

# 17. API Routes and Response Semantics

Recommended Phase 3 API:

```http
POST /api/missions
GET  /api/missions/{session_id}
POST /api/missions/{session_id}/accident
POST /api/missions/{session_id}/replay
GET  /api/missions/{session_id}/telemetry
GET  /api/missions/{session_id}/stream
GET  /api/sim/result/{run_id}
```

| Route | Success | Important errors |
|---|---|---|
| `POST /api/missions` | `201` | `422`, unknown scenario |
| `GET /api/missions/{id}` | `200` | `404` |
| `POST .../accident` | `200` | `404`, `409`, infrastructure errors |
| `POST .../replay` | `200` | `404`, `409`, `422` |
| `GET .../telemetry` | `200` | `404`, `409` |
| `GET .../stream` | SSE `200` | `400`, `404`, `409`, `503` |
| `GET /api/sim/result/{id}` | `200` | `404`, artifact errors |

Routes remain thin and call services for all lifecycle/replay decisions.

---

# 18. Error Model

Recommended stable codes:

```text
MISSION_SESSION_NOT_FOUND
MISSION_STATE_CONFLICT
MISSION_SESSION_CORRUPT
BASELINE_RESULT_NOT_FOUND
BASELINE_TELEMETRY_EMPTY
REPLAY_NOT_STARTED
REPLAY_ALREADY_STARTED
REPLAY_INTERVAL_INVALID
REPLAY_EVENT_ID_INVALID
REPLAY_STREAM_LIMIT
RUN_NOT_FOUND
RUN_RESULT_CORRUPT
```

Do not expose absolute paths, stack traces, raw subprocess commands, or internal exception representations.

---

# 19. Security, Concurrency, and Restart Behavior

## 19.1 Path safety

- session/run IDs are UUIDs;
- all paths are server-resolved;
- verify containment after resolution;
- apply the current Phase 1 symlink policy.

## 19.2 Lifecycle locking

Use a per-session async lock registry to prevent duplicate triggers and conflicting replay starts in one process.

## 19.3 Stream limits

Use a shared semaphore. If exhausted, return `503 REPLAY_STREAM_LIMIT`.

## 19.4 Restart behavior

Persisted states survive restart.

- `REPLAYING` derives position from persisted start time.
- stale `TRIGGERING` cannot be assumed complete; reconcile to `ERROR` unless a completed run linkage proves otherwise.
- do not automatically rerun the simulator.

## 19.5 Logging

Log session ID, scenario ID, lifecycle transitions, baseline run ID, replay start, stream connection/disconnection, completion, and stable error code. Do not log full telemetry histories at INFO level.

---

# 20. Testing Strategy

## 20.1 Unit tests

Test:

- strict mission/replay schemas and state consistency;
- SessionStore create/read/update, atomicity, containment, CWD independence;
- ReplayClock boundaries without real sleep;
- MissionLifecycleService transitions, duplicate trigger, infrastructure failure, empty telemetry, restart;
- TelemetryReplayService sample order, value preservation, catch-up, resume, completion, no interpolation.

## 20.2 Integration tests

Through ASGI:

1. Create session.
2. Confirm `READY`.
3. Trigger accident.
4. Confirm `BASELINE_READY`.
5. Retrieve result.
6. Start replay.
7. Read current telemetry.
8. Consume SSE.
9. Confirm event IDs and exact sample equality.
10. Confirm final completion event.
11. Reconnect with `Last-Event-ID`.
12. Confirm conflict/error paths.

## 20.3 Real simulator test

Use the existing fail-hard real-simulator convention:

```text
create session
→ trigger release scenario with no plan
→ strict result received
→ expected baseline outcome FAILURE
→ telemetry history non-empty
→ replay every sample
→ final SSE payload matches result
```

## 20.4 Determinism and concurrency

Compare two independent sessions while excluding session IDs, run IDs, backend timestamps, and wall-clock pacing.

Test simultaneous trigger race, independent session isolation, equivalent multi-client streams, and both replay/run semaphores.

---

# 21. Exact Implementation Order

Each step ends with review.

| Step | Implementation | Checkpoint |
|---:|---|---|
| 1 | Audit repository, first-sample semantics, current services | Contract report; no production code |
| 2 | Add schemas and configuration | Schema/config tests pass |
| 3 | Implement SessionStore | Persistence/security tests pass |
| 4 | Extend RunStore for strict result retrieval | Result retrieval tests pass |
| 5 | Implement MissionLifecycleService | State-transition tests pass |
| 6 | Add mission create/read/accident/replay-start routes | HTTP lifecycle tests pass |
| 7 | Implement ReplayClock | Boundary tests pass |
| 8 | Implement TelemetryReplayService | Exact-value/resume tests pass |
| 9 | Add current telemetry and SSE routes | SSE integration tests pass |
| 10 | Add real-simulator lifecycle/replay test | Baseline FAILURE and full replay proven |
| 11 | Add concurrency, restart, and security hardening | Isolation/recovery tests pass |
| 12 | Finalize README and release gate | Full Phase 3 gate passes |

Stop after the requested step.

---

# 22. Build and Run Commands

Adapt commands to the current environment and package structure.

Typical checks:

```bash
cd backend
python -m pytest tests/unit/test_mission_schema.py
python -m pytest tests/unit/test_session_store.py
python -m pytest tests/unit/test_mission_lifecycle_service.py
python -m pytest tests/unit/test_replay_clock.py
python -m pytest tests/unit/test_telemetry_replay_service.py
python -m pytest tests/integration/test_mission_routes.py
python -m pytest tests/integration/test_sse_replay.py
python -m pytest tests/integration/test_result_retrieval.py
python -m pytest tests/integration/test_mission_real_simulator.py
ruff check app tests scripts
mypy app
```

Manual flow:

```bash
uvicorn app.main:app --reload
```

```bash
curl -X POST http://127.0.0.1:8000/api/missions \
  -H "Content-Type: application/json" \
  -d '{"scenario_id":"mars_hab_atmosphere_solar_failure"}'

curl -X POST http://127.0.0.1:8000/api/missions/<session_id>/accident

curl -X POST http://127.0.0.1:8000/api/missions/<session_id>/replay \
  -H "Content-Type: application/json" \
  -d '{"interval_ms":250,"restart":false}'

curl -N http://127.0.0.1:8000/api/missions/<session_id>/stream
```

---

# 23. Phase 3 Release Gate

Create:

```text
backend/RELEASE_GATE_PHASE_3.md
```

Record:

- commit and repository evidence;
- Phase 1 gate still passing;
- Phase 2 corpus validator still passing;
- session/trigger/run/replay functional evidence;
- first and final SSE event;
- exact telemetry equality and sample count;
- reconnect behavior;
- duplicate trigger and invalid-state evidence;
- restart and stream-limit evidence;
- pytest, real-simulator, Ruff, mypy, and `git diff --check` results;
- confirmation that `Simulator/` and procedure manuals are unchanged.

Phase 3 is complete only when no numerical nominal telemetry is fabricated, accident trigger reuses Phase 1, replay is deterministic and restart-safe, SSE resume is proven, concurrent sessions are isolated, and no NVIDIA/RAG/frontend work exists.

---

# 24. Cursor Execution Prompts

## 24.1 Master operating prompt

```text
You are implementing ARES-1 Phase 3 only: mission lifecycle, accident triggering, baseline-run linkage, deterministic telemetry replay, and SSE transport.

Read the approved Phase 3 guide and inspect the current repository before editing.

Non-negotiable rules:

1. Simulator/ is frozen. Do not modify its source, tests, scenarios, plans, serializers, equations, or release behavior.
2. The C++ simulator owns physics, crew physiology, action behavior, validation, telemetry, metrics, timeline, mission status, failure reasons, and outcome.
3. Reuse the existing Phase 1 SimulationService, ScenarioRegistry, RunStore, SimulatorClient, strict schemas, lifespan wiring, errors, and logging.
4. Do not create a second simulator invocation path.
5. Do not calculate, interpolate, normalize, thin, or repair telemetry in Python.
6. Before accident trigger, do not fabricate numerical nominal telemetry.
7. FAILURE and REJECTED are valid simulator results, not HTTP errors.
8. Do not add survival_probability.
9. Use strict Pydantic v2 models with extra fields forbidden.
10. Use UUID session/run identifiers and server-resolved contained paths.
11. Use Server-Sent Events, not WebSockets, for Phase 3 replay.
12. Implement no NVIDIA, RAG, planner, frontend, database, authentication, or deployment work.
13. Do not rewrite Phase 2 manuals.
14. Implement production code completely. No TODOs, placeholders, temporary bypasses, or untested fallbacks.
15. Stop after the requested section checkpoint.

For the requested section:
- inspect relevant current files;
- list exact files to create/edit;
- implement only that section;
- add/update named tests;
- run required commands;
- fix failures within scope;
- report changed files, command results, and unresolved issues;
- stop.
```

## 24.2 Section 1 — Repository and replay-contract audit

```text
Implement only Phase 3 Guide Step 1: repository and replay-contract audit.

Do not modify production code.

Inspect at minimum:

- backend/app/main.py and lifespan wiring
- backend/app/api/router.py and current routes
- backend/app/core/config.py, errors.py, logging.py
- backend/app/schemas/api.py, telemetry.py, result.py
- backend/app/services/scenario_registry.py
- backend/app/services/run_store.py
- backend/app/services/simulator_client.py
- backend/app/services/simulation_service.py
- backend tests and release fixtures
- backend/RELEASE_GATE.md
- Phase 2 corpus manifest and validator
- current release scenario
- current C++ Simulation/JsonIO timestep and serialization behavior

Create only:

backend/PHASE_3_CONTRACT_AUDIT.md

The audit must record:

1. Current application dependency/lifespan pattern.
2. Exact SimulationService request/response and run_id behavior.
3. Exact RunStore artifact layout and requirements for result retrieval.
4. Exact strict telemetry/result model names.
5. Baseline result sample count, first sample, final sample, and outcome.
6. First-sample semantics: simulation_time_min, events, mission_status, fault activation, and whether a pre-fault numerical sample exists.
7. Current telemetry nesting and timeline/event placement.
8. Current backend error and API envelope patterns.
9. Current test markers and fail-hard real-simulator convention.
10. Recommended exact files for Phase 3 implementation.
11. Any conflict between this guide and current code.
12. Explicit nominal-state decision: proven pre-fault sample or READY lifecycle only.
13. Proposed locked Phase 3 route paths.
14. Phase 3 Step 1 exit checklist.

Run:

git diff --check
git status --short

Do not run full tests unless inspection reveals an unexpected repository issue.

Report findings and stop.
```

## 24.3 Section 2 — Schemas and configuration

```text
Implement only Phase 3 Guide Step 2: mission/replay schemas and configuration.

Use the approved Phase 3 contract audit as source of truth.

Implement strict mission/replay models and Phase 3 settings. Do not implement SessionStore, services, or routes yet.

Add focused positive and negative tests for every lifecycle state and setting.

Run focused pytest, Ruff, mypy, git diff --check, report and stop.
```

## 24.4 Section 3 — SessionStore

```text
Implement only Phase 3 Guide Step 3: SessionStore.

Implement atomic strict session persistence, UUID/path containment, CWD independence, and per-session lock support according to the guide and current backend conventions.

Do not implement lifecycle orchestration or routes.

Add tests for create/read/update, malformed data, unknown IDs, path traversal/symlink policy, atomic writes, and concurrent state updates.

Run focused pytest, Ruff, mypy, git diff --check, report and stop.
```

## 24.5 Section 4 — Run-result retrieval

```text
Implement only Phase 3 Guide Step 4: strict persisted run-result retrieval.

Extend the current RunStore minimally to retrieve existing run metadata/result by trusted run_id. Add the result route only if the approved checkpoint includes route wiring.

Do not alter canonical result artifacts.

Add positive and negative tests, including simulator FAILURE returning HTTP 200 once routed.

Run focused checks, report and stop.
```

## 24.6 Section 5 — MissionLifecycleService

```text
Implement only Phase 3 Guide Step 5: MissionLifecycleService.

Implement create_session, get_session, trigger_accident, start_replay, and effective completion reconciliation.

Reuse existing SimulationService with no plan. Do not call SimulatorClient directly. Do not implement routes or SSE.

Add state-transition, duplicate-trigger, infrastructure-error, empty-telemetry, restart, and exact-outcome-preservation tests.

Run focused checks, report and stop.
```

## 24.7 Section 6 — Mission lifecycle routes

```text
Implement only Phase 3 Guide Step 6: mission create/read/accident/replay-start HTTP routes and typed error mapping.

Do not implement current telemetry or SSE yet.

Keep routes thin and use exact schemas/services. Add ASGI integration tests for status codes, envelopes, duplicate trigger, invalid states, and valid simulator FAILURE semantics.

Run focused checks, report and stop.
```

## 24.8 Section 7 — ReplayClock

```text
Implement only Phase 3 Guide Step 7: pure ReplayClock.

Implement deterministic index/completion/next-delay calculations with injected time. No filesystem, HTTP, session, or telemetry logic.

Add exhaustive boundary tests without real sleeps.

Run focused checks, report and stop.
```

## 24.9 Section 8 — TelemetryReplayService

```text
Implement only Phase 3 Guide Step 8: TelemetryReplayService.

Use SessionStore, RunStore, ReplayClock, and strict result/telemetry schemas.

Implement exact sample selection, ordered catch-up, Last-Event-ID resume semantics, completion envelope creation, and concurrent-client equivalence.

Do not implement the SSE route yet. Never interpolate or modify telemetry.

Add exact-equality tests using captured release fixtures.

Run focused checks, report and stop.
```

## 24.10 Section 9 — Current telemetry and SSE routes

```text
Implement only Phase 3 Guide Step 9: mission current-telemetry and SSE routes.

Implement:

GET /api/missions/{session_id}/telemetry
GET /api/missions/{session_id}/stream

Use StreamingResponse with text/event-stream, no-cache behavior, disconnect handling, heartbeat, stream semaphore, and Last-Event-ID.

Add integration tests for ordered events, complete event, resume, invalid IDs, replay-not-started, disconnect, and stream limit.

Run focused checks, report and stop.
```

## 24.11 Section 10 — Real simulator gate

```text
Implement only Phase 3 Guide Step 10: real-simulator mission lifecycle and replay integration tests.

Use the current release scenario and existing fail-hard real-simulator convention.

Prove session creation, one no-plan baseline run, expected FAILURE outcome, non-empty telemetry history, exact replay equality, no dropped/reordered samples, and a final complete event matching the result.

Do not modify production behavior unless a genuine Phase 3 defect is exposed.

Run the real-simulator marker and report exact results, then stop.
```

## 24.12 Section 11 — Hardening

```text
Implement only Phase 3 Guide Step 11: concurrency, restart, security, and failure-path hardening.

Cover simultaneous trigger race, independent sessions, equivalent multiple streams, stale TRIGGERING reconciliation, corrupt/unknown artifacts, path containment, bounded interval, stream limit, and disconnect cleanup.

Run focused and relevant full backend tests, report and stop.
```

## 24.13 Section 12 — Final release gate

```text
Implement only Phase 3 Guide Step 12: documentation, release evidence, and full gate.

Create backend/RELEASE_GATE_PHASE_3.md and update backend/README.md and .env.example for implemented Phase 3 settings/routes.

Run the Phase 2 corpus validator, full backend pytest with required real-simulator mode, focused real-simulator marker, Ruff, mypy, and git diff --check.

Reconfirm Simulator/ and procedure manual contents are unchanged.

Record exact results and stop. Do not begin Phase 4.
```

---

# Appendix A. File Responsibility Matrix

| File | Responsibility |
|---|---|
| `schemas/mission.py` | Mission lifecycle state and request/response models |
| `schemas/replay.py` | Replay and SSE payload contracts |
| `services/session_store.py` | Session persistence and locks |
| `services/replay_clock.py` | Pure time-to-index calculation |
| `services/mission_lifecycle_service.py` | State transitions and baseline orchestration |
| `services/telemetry_replay_service.py` | Strict sample selection and event envelopes |
| `api/routes/missions.py` | Mission and replay HTTP transport |
| `services/run_store.py` | Existing run result retrieval extension |
| `core/config.py` | Session/replay settings |
| `core/errors.py` | Typed Phase 3 errors |
| `main.py` | Shared service/semaphore lifespan wiring |
| `tests/` | Unit, integration, determinism, concurrency, real simulator |
| `RELEASE_GATE_PHASE_3.md` | Phase 3 evidence |

# Appendix B. State Transition Matrix

| Current | Operation | Next | Allowed |
|---|---|---|---|
| READY | trigger accident | TRIGGERING | Yes |
| READY | start replay | — | No |
| TRIGGERING | simulator success | BASELINE_READY | Yes |
| TRIGGERING | infrastructure failure | ERROR | Yes |
| BASELINE_READY | trigger accident | — | No |
| BASELINE_READY | start replay | REPLAYING | Yes |
| REPLAYING | start replay | — | No unless restart policy permits |
| REPLAYING | final sample due | COMPLETED | Yes |
| COMPLETED | restart replay | REPLAYING | Yes |
| ERROR | trigger/replay | — | No in Phase 3 |

# Appendix C. SSE Event Contract

## Telemetry event

```json
{
  "session_id": "uuid",
  "sequence": 0,
  "sample_index": 0,
  "sample_count": 361,
  "telemetry": {
    "...": "exact TelemetrySample"
  }
}
```

## Completion event

```json
{
  "session_id": "uuid",
  "sequence": 361,
  "baseline_run_id": "uuid",
  "outcome": "FAILURE",
  "valid_plan": true,
  "failure_reasons": ["..."],
  "metrics": {
    "...": "exact strict SimulationMetrics"
  }
}
```

The exact nested field shapes come from the current Phase 1 strict schemas and captured simulator result, not from this illustrative appendix.
