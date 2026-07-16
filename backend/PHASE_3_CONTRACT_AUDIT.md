# ARES-1 Phase 3 — Repository and Replay-Contract Audit

Audit date: 2026-07-15

Scope: Phase 3 Guide Step 1 only. No production code, simulator, fixture, scenario, plan, result, or procedure manual was modified. No sessions, replay, SSE, routes, schemas, or configuration were implemented.

Authoritative sources: current Phase 1 backend production code, authoritative release fixtures under `backend/tests/fixtures/results/`, frozen C++ simulator timestep ordering, Phase 2 corpus layout (presence only), and the Phase 3 guide used for conflict recording (not as schema truth).

---

## Sources inspected

| Area | Paths |
|------|--------|
| App wiring | `backend/app/main.py`, `backend/app/api/router.py`, `backend/app/api/routes/health.py`, `backend/app/api/routes/simulation.py` |
| Core | `backend/app/core/config.py`, `backend/app/core/errors.py`, `backend/app/core/logging.py`, `backend/.env.example` |
| Schemas | `backend/app/schemas/api.py`, `backend/app/schemas/result.py`, `backend/app/schemas/telemetry.py`, `backend/app/schemas/crew.py`, `backend/app/schemas/plan.py`, `backend/app/schemas/actions.py`, `backend/app/schemas/common.py` |
| Services | `backend/app/services/scenario_registry.py`, `backend/app/services/run_store.py`, `backend/app/services/simulator_client.py`, `backend/app/services/simulation_service.py` |
| Tests / gate | `backend/tests/conftest.py`, `backend/tests/fixtures/results/` (including `README.md`, `baseline_result.json`), `backend/pyproject.toml`, `backend/RELEASE_GATE.md` |
| Phase 2 | `docs/procedures/corpus_manifest.json`, `backend/scripts/validate_procedure_corpus.py` |
| Simulator / scenario | `scenarios/mars_hab_atmosphere_solar_failure.json`, `Simulator/src/Simulation.cpp`, `Simulator/src/JsonIO.cpp`, relevant headers under `Simulator/include/` |
| Guide | `docs/ARES-1_Phase_3_Mission_Lifecycle_Telemetry_Replay_Implementation_Guide.md` |

Discovered real paths: C++ tree is `Simulator/` (not guide/example `sim_core/`); authoritative baseline fixture is `backend/tests/fixtures/results/baseline_result.json` (not repo root `results/`).

---

## 1. Current application lifecycle and dependency wiring

### Application factory

- Entry: `create_app(settings_override: Settings | None = None, *, simulation_service_override: SimulationService | None = None) -> FastAPI` in `backend/app/main.py`.
- Settings: `settings_override` if provided, else `get_settings()`.
- Logging: `configure_logging(settings)` before app construction.
- FastAPI metadata currently: title `"ARES-1 Phase 1 Backend"`, version `"0.1.0"`, lifespan `_lifespan`.
- `app.state.settings = settings`.
- Optional `simulation_service_override` sets `app.state.simulation_service` before lifespan.
- `register_exception_handlers(app)`.
- `app.include_router(api_router, prefix="/api")`.

### Lifespan-managed objects

`_lifespan` always:

1. Reads `app.state.settings`.
2. Calls `evaluate_readiness(settings)` and stores `app.state.startup_readiness`.
3. If `app.state.simulation_service` is missing, constructs dependents and wires them.
4. Logs ready vs degraded, then `yield`.

Construction order when not overridden:

1. `ScenarioRegistry(settings.scenario_dir)`
2. `RunStore(settings.runs_dir)`
3. `SimulatorClient(settings)`
4. `SimulationService(scenario_registry=..., run_store=..., simulator_client=...)`

Stored on `app.state`: `scenario_registry`, `run_store`, `simulator_client`, `simulation_service`. If a service override is present, lifespan skips building registry/store/client.

### How routes obtain dependencies

- Aggregation: `api_router` includes `health.router` and `simulation.router` with no extra router prefix.
- Simulation: `Depends(get_simulation_service)` → `request.app.state.simulation_service`.
- Health: reads `request.app.state.settings` (and uses startup readiness helpers); no FastAPI `Depends` for the service graph.
- `ScenarioRegistry`, `RunStore`, and `SimulatorClient` are not separate FastAPI dependencies; they are composed inside `SimulationService` / `app.state`.

### Existing concurrency semaphore

- Owned by `SimulatorClient`, not the FastAPI app.
- `asyncio.Semaphore(settings.max_concurrent_runs)` (env `ARES_MAX_CONCURRENT_RUNS`, default `2`).
- Binary and workspace precondition checks run outside the semaphore; spawn/`communicate` run inside `async with self._semaphore`.

### Where future SessionStore and replay-stream semaphore should be wired

Wire in the same lifespan block in `backend/app/main.py` that constructs Phase 1 services:

- Construct `SessionStore(settings.sessions_dir)` and assign `app.state.session_store`.
- Construct a **separate** `asyncio.Semaphore(settings.max_replay_streams)` for SSE streams (do not reuse the simulator-run semaphore). Prefer attaching it to the replay service or `app.state` as an explicit stream limiter.
- Construct `MissionLifecycleService` (needs `SessionStore`, `SimulationService`, and likely `ScenarioRegistry`) → `app.state.mission_lifecycle_service`.
- Construct `TelemetryReplayService` (needs `SessionStore`, `RunStore`, `ReplayClock`) → `app.state.telemetry_replay_service`.
- Extend `create_app` with typed overrides for tests, mirroring `simulation_service_override`.
- Mission routes should use thin `Depends(get_*_from_app_state)` helpers like `get_simulation_service`.

No `SessionStore`, replay clock, SSE, or stream semaphore exists today.

---

## 2. Current SimulationService contract

| Item | Current value |
|------|----------------|
| Class | `SimulationService` |
| Constructor | `__init__(scenario_registry, run_store, simulator_client)` |
| Public method | `async def run_simulation(self, request: SimulationRunRequest) -> SimulationRunResponse` |
| Request type | `SimulationRunRequest` (`scenario_id: str`, `plan: RecoveryPlan \| None = None`) |
| Return type | `SimulationRunResponse` |

### run_id creation and return

- `RunStore.create_workspace` allocates `run_id = str(uuid.uuid4())` and creates `{runs_root}/{run_id}/`.
- Success response includes that `run_id` in `SimulationRunResponse`.
- On infrastructure failure, typed errors are re-raised with `with_run_id(workspace.run_id)` after failed-metadata finalization.

### Absent plan representation

- HTTP/body: omit `plan` or set `plan: null` → `request.plan is None`.
- Store: `mode="baseline"`; **no** `plan.json` written; `metadata.plan_id` is `None`; `metadata.plan_sha256` is `None`.
- Client CLI: `[binary, "--scenario", scenario_path, "--output", result_path]` (no `--plan`).
- Service logging uses `mode="baseline"` and `plan_id=None`.

### Baseline execution invocation

Accident/baseline path must call `SimulationService.run_simulation(SimulationRunRequest(scenario_id=..., plan=None))`. It must not call `SimulatorClient` directly.

### Artifacts written on success path

Via `RunStore` / `SimulatorClient`:

- `request.json`, `scenario.json`, optional `plan.json`, `result.json` (simulator-written), `stdout.log`, `stderr.log`, `metadata.json` (status `completed` with hashes/outcome/duration).

### Exceptions that may escape

Any `AresBackendError` subclass from registry/store/client, re-raised after failure finalization; possibly `ArtifactStorageError` if post-success artifact writes fail. The service does not return an error envelope; HTTP handlers turn exceptions into `ErrorResponse`.

### Envelope vs strict result

The service returns the **HTTP success envelope** `SimulationRunResponse` with nested strict `SimulationResult` in `result`. It does not return bare `SimulationResult`.

---

## 3. Current RunStore contract and artifact layout

### Run directory structure

```text
{runs_root}/
└── <uuid>/
    ├── request.json
    ├── scenario.json
    ├── plan.json          # only when request.plan is not None
    ├── result.json        # canonical simulator output
    ├── stdout.log
    ├── stderr.log
    └── metadata.json
```

- Canonical result filename: `result.json`.
- Metadata filename: `metadata.json`.

### RunMetadata JSON shape

Fields (dataclass `RunMetadata`):

| Field | Type / notes |
|-------|----------------|
| `run_id` | `str` |
| `created_at` | UTC ISO string |
| `mode` | `"baseline"` \| `"plan"` |
| `scenario_id` | `str` |
| `plan_id` | `str \| None` |
| `scenario_sha256` | uppercase hex |
| `plan_sha256` | `str \| None` |
| `result_sha256` | `str \| None` |
| `process_exit_code` | `int \| None` |
| `duration_ms` | `int \| None` |
| `outcome` | `str \| None` |
| `status` | `"created"` \| `"completed"` \| `"failed"` |
| `error_code` | `str \| None` |

Serialized via `to_json_dict()` → `asdict`.

### Current public methods

- `create_workspace(request, scenario_source) -> RunWorkspace`
- `write_stdout` / `write_stderr`
- `hash_result_artifact` / `try_hash_result_artifact`
- `write_completed_metadata` / `write_failed_metadata`

### Typed result retrieval

**Does not exist.** No `read_result`, `get_result`, `load_result`, or `read_metadata` public API. Phase 1 only writes and hashes.

### Exact Phase 3 RunStore changes required

1. Add path containment for trusted `run_id` under `self._runs_root` (validate UUID string format; reject traversal).
2. Add sync retrieval consistent with current store style (not guide async/UUID sketches):
   - `read_metadata(self, run_id: str) -> RunMetadata`
   - `read_result(self, run_id: str) -> SimulationResult` (parse `result.json` through `SimulationResult.model_validate`)
3. Raise typed storage/not-found errors without exposing absolute paths to clients.
4. Do not rewrite or copy canonical `result.json` into session directories unless a later approved step requires an immutable reference copy; session records should store trusted `baseline_run_id` only.

### Path containment and atomic-write patterns

- Atomic writes already present: `write_bytes_atomic`, `write_json_atomic` (temp file + `fsync` + `os.replace`).
- RunStore today has **no** `is_relative_to` / containment helper. Containment exists in `ScenarioRegistry.resolve_scenario` and `SimulatorClient._is_under_root`. Phase 3 result retrieval must add RunStore-side containment.

---

## 4. Strict schema inventory

All contract models use `CONTRACT_CONFIG` (`extra="forbid"`) unless noted. No Pydantic field aliases; JSON keys match Python names.

### SimulationResult (`backend/app/schemas/result.py`)

```text
scenario_id: str
plan_id: str
outcome: OutcomeStatus   # FAILURE | STABILIZED | REJECTED
valid_plan: StrictBool
metrics: SimulationMetrics
timeline: list[TimelineEvent]
telemetry_history: list[TelemetrySample]
failure_reasons: list[str]
```

### SimulationMetrics

```text
minimum_inspired_o2_mmhg: float
minimum_cabin_pressure_kpa: float
maximum_co2_one_hour_avg_mmhg: float
minimum_battery_soc_percent: float
minimum_power_margin_kw: float
minimum_temperature_margin_c: float
minimum_eva_safe_return_margin_min: float
minimum_crew_spo2_percent: float
maximum_crew_fatigue_percent: float
eva_completed: StrictBool
communications_sent: StrictBool
time_to_stabilization_hr: float
```

### TelemetrySample (`backend/app/schemas/telemetry.py`)

```text
simulation_time_min: StrictInt
habitat: HabitatTelemetry
crew: list[CrewTelemetry]
events: list[TimelineEvent]
active_actions: list[ActiveActionState]
has_warning: StrictBool
has_critical: StrictBool
```

### HabitatTelemetry

```text
cabin_pressure_kpa: float
inspired_oxygen_mmhg: float
co2_one_hour_avg_mmhg: float
oxygen_hours_remaining: float
battery_soc_percent: float
solar_generation_percent: float
power_margin_kw: float
cabin_temperature_c: float
temperature_margin_c: float
eva_safe_return_margin_min: float
mission_status: MissionStatus
  # NOMINAL | WARNING | CRITICAL | STABILIZED | FAILURE | REJECTED
```

### CrewTelemetry (`backend/app/schemas/crew.py`, JSON key `crew`)

```text
crew_id: str
display_name: str
activity: CrewActivity
heart_rate_bpm: float
respiratory_rate_bpm: float
spo2_percent: float
core_temperature_c: float
fatigue_percent: float
cognitive_performance_percent: float
physical_performance_percent: float
health_status: CrewHealthStatus
alarms: list[CrewAlarmType]
```

### TimelineEvent

```text
time_min: StrictInt
event_type: str
message: str
severity: ConstraintSeverity  # INFO | WARNING | CRITICAL | FAILURE
```

Placed both: per-sample `TelemetrySample.events` and top-level `SimulationResult.timeline`.

### ActiveActionState

```text
action_index: StrictInt
type: ActionType
status: ActionExecutionStatus
actual_start_min: StrictInt | None
elapsed_min: StrictInt
progress_fraction: float
assigned_crew_id: str | None
eva_crew_id: str | None
assigned_crew_ids: list[str]
failure_reason: str
```

### Warnings / events

There is **no** dedicated Warnings model. Warning/critical signaling uses:

- `TelemetrySample.has_warning` / `has_critical`
- `TimelineEvent.severity`
- `SimulationResult.failure_reasons`

### API success and error envelopes (`backend/app/schemas/api.py`)

Success (`SimulationRunResponse`):

```text
run_id: str
duration_ms: StrictInt
result: SimulationResult
```

Error (`ErrorResponse`):

```text
code: ErrorCode
message: str
run_id: str | None
```

Current `ErrorCode` values: `SCENARIO_NOT_FOUND`, `SIMULATOR_UNAVAILABLE`, `SIMULATOR_TIMEOUT`, `SIMULATOR_EXECUTION_FAILED`, `SIMULATOR_OUTPUT_MISSING`, `SIMULATOR_OUTPUT_INVALID_JSON`, `SIMULATOR_OUTPUT_CONTRACT_ERROR`, `ARTIFACT_STORAGE_ERROR`, `INTERNAL_SERVER_ERROR`.

Health envelope (`HealthResponse`): `status` (`ok`|`degraded`), `simulator_ready`, `message`.

---

## 5. Baseline release-result analysis

Authoritative fixture: `backend/tests/fixtures/results/baseline_result.json`  
(SHA-256 pinned in `backend/tests/conftest.py`: `C9EAE8F26A37E6D3587038A49984548C0BFF2DEE8367D91C29CFEB76C13A4A79`)

| Field | Value |
|-------|--------|
| `scenario_id` | `mars_hab_atmosphere_solar_failure` |
| `plan_id` | `""` (empty string, not null/omitted) |
| `outcome` | `FAILURE` |
| `valid_plan` | `true` |
| telemetry sample count | **6** |
| first sample index | `0` |
| first `simulation_time_min` | `0` |
| first `habitat.mission_status` | `WARNING` |
| first `events` | `[]` |
| first solar marker | `solar_generation_percent: 5.0` (faulted) |
| final `simulation_time_min` | `5` |
| final `habitat.mission_status` | `FAILURE` |
| `failure_reasons` | `["critical_repair_impossible"]` |
| top-level `timeline` | one event: `mission_failure` / `critical_repair_impossible` / `FAILURE` / `time_min: 5` |
| sample times | `[0, 1, 2, 3, 4, 5]` strictly increasing |

Repo root `results/` copies are not the hash-pinned test authority.

---

## 6. First-sample and nominal-state semantics

### Evidence from C++ timestep ordering (`Simulation.cpp`)

1. `initializeState` sets `time_min = 0` and applies fault fields immediately (`total_gas_leak_kg_hr`, `solar_fault_factor`, `active_faults` when `failure_type` non-empty). Scenario has no delayed injection / `start_min` for the fault.
2. Per loop iteration: optional actions → **pre-step** `buildTelemetry` (not stored) → crew/resource updates (physics under fault) → **post-step** `buildTelemetry` → mission evaluation → **store** sample with `simulation_time_min = state.time_min` → then advance clock.
3. Therefore the first **persisted** sample is post-fault and post one physics step at `simulation_time_min == 0`.

### Evidence from baseline fixture

- First sample `mission_status` is already `WARNING`, not `NOMINAL`.
- Compound failure numericals are active from sample 0 (e.g. solar generation 5.0% on all six samples).
- No sample with `mission_status: NOMINAL` exists in the authoritative baseline history.
- `events` on the first sample are empty; failure event appears at the final sample / top-level timeline.

### Conclusions

| Question | Answer |
|----------|--------|
| First sample pre-fault or post-fault? | **Post-fault** |
| Compound failure already active? | **Yes** |
| Authoritative numerical nominal telemetry exists? | **No** |
| May first sample be shown before accident trigger as nominal? | **No** |
| Must Phase 3 expose READY without numerical telemetry? | **Yes** |

### Selected nominal-state policy

**B. READY_WITHOUT_NUMERICAL_TELEMETRY**

Before accident trigger, return lifecycle metadata only (`lifecycle_status = READY`). Do not fabricate or infer numerical nominal telemetry from scenario configuration. Do not treat the first baseline sample as a pre-accident nominal snapshot.

Option A (`AUTHORITATIVE_PREFAULT_SAMPLE`) is rejected because no such sample exists in the frozen simulator output.

---

## 7. Replay-source contract

| Item | Contract |
|------|----------|
| Only replay source | `SimulationResult.telemetry_history` after strict `SimulationResult` validation |
| Ordering | Array order as emitted; `simulation_time_min` values `[0..5]` monotonic increasing in baseline |
| Sample times monotonic? | **Yes** for baseline (must preserve order; do not reorder) |
| Events embedded per sample? | **Yes** — `TelemetrySample.events` |
| Separate timeline SSE required? | **No** for Phase 3 completeness of per-step events; samples carry step events. Top-level `timeline` is the aggregated final-result list (same failure event at end for baseline). Completion envelopes may expose result-level fields. |
| Samples contain frontend-useful engineering state? | Habitat, crew, events, active_actions, warning/critical flags — yes for live replay |
| Final-result-only fields | `outcome`, `metrics`, `failure_reasons`, top-level `timeline`, `plan_id`, `valid_plan` (plus session linkage `baseline_run_id`) |

Never interpolate, thin, clamp, or recalculate telemetry values.

---

## 8. Existing route and error patterns

### Route prefix and modules

- Global API prefix: `/api` (`create_app` → `include_router(api_router, prefix="/api")`).
- Existing routes:
  - `GET /api/health` (`health.router`, no module prefix)
  - `POST /api/sim/run` (`simulation.router` with `prefix="/sim"`)
- Dependency pattern: thin handlers + `Depends(get_simulation_service)` from `request.app.state`.

### Success / error envelopes

- Success for simulation: `SimulationRunResponse` JSON.
- Error: `ErrorResponse` via `register_exception_handlers` for `AresBackendError` and unexpected `Exception`.

### Status-code semantics (current)

| Situation | HTTP |
|-----------|------|
| Successful run including simulator `FAILURE` / `STABILIZED` / `REJECTED` | **200** |
| Unknown scenario | 404 `SCENARIO_NOT_FOUND` |
| Simulator unavailable | 503 |
| Timeout | 504 |
| Process/output failures | 502 (several codes) |
| Artifact storage | 500 |
| Unexpected | 500 `INTERNAL_SERVER_ERROR` |
| Health degraded | 503 with `HealthResponse` (not `ErrorResponse`) |

### Typed exception-handler pattern

`AresBackendError` → look up `ARES_HTTP_STATUS_BY_CODE` → `ErrorResponse.model_dump(mode="json")`. Subclasses override `with_run_id`.

### FAILURE and REJECTED behavior

Valid simulator outcomes delivered inside HTTP 200 success envelopes when infrastructure succeeds. They are **not** infrastructure error codes.

### Naming convention for future Phase 3 error codes

- Add SCREAMING_SNAKE members to `ErrorCode` in `schemas/api.py`.
- Add matching `*Error(AresBackendError)` classes in `core/errors.py`.
- Map HTTP in `ARES_HTTP_STATUS_BY_CODE`.
- Proposed codes aligned with guide + current style: `SESSION_NOT_FOUND` (404), `MISSION_STATE_CONFLICT` (409), `REPLAY_NOT_STARTED` (409), `REPLAY_STREAM_LIMIT` (503), plus reuse existing simulator/storage codes where accident trigger hits infrastructure.

---

## 9. Current configuration conventions

| Item | Current |
|------|---------|
| Settings class | `Settings(BaseSettings)` in `backend/app/core/config.py` |
| Env prefix | `ARES_` |
| Frozen / extra | `frozen=True`, `extra="ignore"` |
| Relative paths | `resolve_against_backend` against `BACKEND_ROOT` (= `backend/`) |
| Runs dir | `ensure_writable_runs_dir` (mkdir + write probe) |
| Scenario dir | must exist and lie under `project_root` |
| Test override | construct `Settings(_env_file=None, ...)` / `create_app(settings_override=...)`; `clear_settings_cache()` exists |
| `.env.example` | documents relative-path rule, binary path, timeout, concurrency, log level; no secrets |

Current fields: `project_root`, `sim_binary`, `scenario_dir`, `runs_dir`, `sim_timeout_seconds`, `max_concurrent_runs`, `log_level`.

### Exact Phase 3 setting names (proposed)

| Settings field | Env var | Role |
|----------------|---------|------|
| `sessions_dir: Path` | `ARES_SESSIONS_DIR` | default `./data/sessions`; resolve against backend root; create + writability probe (same pattern as runs) |
| `replay_default_interval_ms: int` | `ARES_REPLAY_DEFAULT_INTERVAL_MS` | default `250`; within min/max |
| `replay_min_interval_ms: int` | `ARES_REPLAY_MIN_INTERVAL_MS` | default `25`; positive |
| `replay_max_interval_ms: int` | `ARES_REPLAY_MAX_INTERVAL_MS` | default `60000`; >= min |
| `max_replay_streams: int` | `ARES_MAX_REPLAY_STREAMS` | default `20`; > 0; separate from `max_concurrent_runs` |
| `sse_heartbeat_seconds: float` | `ARES_SSE_HEARTBEAT_SECONDS` | default `15`; positive finite |

Do not implement these in Step 1. Update `.env.example` in the schemas/configuration step.

---

## 10. Test and release-gate conventions

| Item | Convention |
|------|------------|
| Pytest layout | `backend/tests/` with `unit/`, `integration/`, `helpers/`, `fixtures/results/` |
| Asyncio | `asyncio_mode = "auto"` in `pyproject.toml` |
| Markers | `integration`, `real_simulator` |
| Real simulator gate | `require_real_simulator()` in `conftest.py`; missing binary → skip unless `ARES_REQUIRE_REAL_SIMULATOR=1` → `pytest.fail` |
| Ruff | `src = ["app", "tests", "scripts"]`; select `E,F,I`; line-length 100 |
| Mypy | `packages = ["app"]`, `strict = true`, pydantic plugin |
| Shared fixtures | session-scoped `baseline_result_data`, plan fixtures, `make_real_app_settings(tmp_path)`, SHA pins, `RELEASE_SCENARIO_ID` |
| App instances in tests | `create_app(settings_override=...)` and/or `simulation_service_override=...`; httpx ASGI client patterns already used in integration tests |
| Release gate doc | `backend/RELEASE_GATE.md` (Phase 1 complete). Phase 3 evidence target: `backend/RELEASE_GATE_PHASE_3.md` |

Phase 2 corpus is validated by `backend/scripts/validate_procedure_corpus.py` against `docs/procedures/corpus_manifest.json`. Phase 3 must not parse or execute procedures.

---

## 11. Proposed exact Phase 3 files

Grounded in current package layout (`app/api/routes/`, `app/schemas/`, `app/services/`, `app/core/`).

### Create

| File | Purpose |
|------|---------|
| `backend/app/schemas/mission.py` | Mission lifecycle / session / create-accident-replay request-response models |
| `backend/app/schemas/replay.py` | Replay start, current telemetry, SSE event envelopes |
| `backend/app/services/session_store.py` | `SessionStore` — atomic `session.json` under sessions root |
| `backend/app/services/replay_clock.py` | Pure `ReplayClock` (no I/O) |
| `backend/app/services/mission_lifecycle_service.py` | `MissionLifecycleService` |
| `backend/app/services/telemetry_replay_service.py` | `TelemetryReplayService` |
| `backend/app/api/routes/missions.py` | Mission HTTP routes (`APIRouter(prefix="/missions", tags=["missions"])`) |
| `backend/RELEASE_GATE_PHASE_3.md` | Phase 3 release evidence |
| `backend/tests/unit/test_mission_*.py`, `test_replay_*.py`, `test_session_store.py`, etc. | Focused unit coverage |
| `backend/tests/integration/test_missions_*.py` | ASGI lifecycle / SSE / result retrieval |

### Edit

| File | Purpose |
|------|---------|
| `backend/app/core/config.py` | Phase 3 settings fields + validation |
| `backend/app/core/errors.py` | New typed errors + HTTP map |
| `backend/app/schemas/api.py` | Extend `ErrorCode` |
| `backend/app/services/run_store.py` | `read_result` / `read_metadata` + containment |
| `backend/app/main.py` | Lifespan wiring for session/replay services; title/description update when Phase 3 lands |
| `backend/app/api/router.py` | `include_router(missions.router)` |
| `backend/app/api/routes/simulation.py` | Add `GET /result/{run_id}` under existing `/sim` prefix |
| `backend/.env.example` | Document new `ARES_*` settings |
| `backend/tests/conftest.py` | Session/settings helpers as needed |

Do not create a second application package.

---

## 12. Locked route proposal

Guide proposal revised only for confirmation against current `/api` + resource-prefix conventions. **Final locked paths:**

```text
POST   /api/missions
GET    /api/missions/{session_id}
POST   /api/missions/{session_id}/accident
POST   /api/missions/{session_id}/replay
GET    /api/missions/{session_id}/telemetry
GET    /api/missions/{session_id}/stream
GET    /api/sim/result/{run_id}
```

Implementation notes:

- Missions router: `APIRouter(prefix="/missions", tags=["missions"])` included from `api_router`.
- Result route: additional handler on existing `simulation.router` (`prefix="/sim"`), not a new top-level namespace.
- No global `/api/telemetry` singleton.

Recommended create status (requires approval; see § unresolved): guide prefers **201** for `POST /api/missions`; Phase 1 `POST /api/sim/run` uses **200**. Audit recommends following the guide **201** for mission create only.

---

## 13. Guide conflicts and required amendments

Do not edit the guide in this step. Record discrepancies:

1. **Nominal strategies:** Guide §5.3 lists three strategies; Step 1 forces A or B. Evidence selects **B**; strategy 3 (future nominal scenario) is out of Phase 3 scope.
2. **RunStore retrieval signatures:** Guide sketches `async def read_result(self, run_id: UUID)`. Current `RunStore` is **synchronous** and uses **`str` UUID** identifiers. Phase 3 should keep sync + `str`.
3. **RunStore result ownership:** Guide describes RunStore as owning result retrieval; retrieval methods **do not exist yet** and must be added.
4. **Path containment:** Guide requires contained run-id reads; RunStore currently has **no** containment helper (unlike registry/client).
5. **Baseline `plan_id`:** Fixture uses empty string `""`, not null/omitted; `valid_plan` is `true` for no-plan FAILURE.
6. **Crew schema location / key:** Crew live in `schemas/crew.py` with JSON key `crew` (not `crew_vitals` or nesting under a differently named field).
7. **App still Phase 1 branded:** title/description/version strings remain Phase 1; expected until later Phase 3 wiring.
8. **POST status convention:** Guide mission create → `201`; existing sim run → `200`. Deliberate split required.
9. **Authoritative result path:** Guide consumers may confuse repo `results/` with release fixtures; authority is `backend/tests/fixtures/results/`.
10. **Pre-step telemetry:** C++ builds pre-step telemetry but does **not** persist it; no pre-fault sample can be assumed from current serializer behavior.
11. **Illustrative guide schemas:** Any older/overview field names must lose to current Pydantic models and fixtures.
12. **Procedure corpus:** Present and validated (Phase 2); Phase 3 must not parse/chunk/retrieve it despite corpus presence in-repo.

---

## 14. Step 1 exit checklist

| Check | Status |
|-------|--------|
| No production code changed | Confirmed (this file only) |
| No `Simulator/` modified | Confirmed |
| No `scenarios/`, `plans/`, or `results/` modified | Confirmed |
| No procedure manuals modified | Confirmed |
| First-sample semantics resolved (post-fault WARNING at t=0) | Confirmed |
| Nominal-state policy resolved: **B. READY_WITHOUT_NUMERICAL_TELEMETRY** | Confirmed |
| Phase 3 file plan grounded in current naming | Confirmed |
| Route proposal grounded (`/api` + `/missions` + `/sim`) | Confirmed |
| No later-phase implementation started | Confirmed |

---

## Unresolved decisions requiring approval

These recommendations are locked in this audit for implementation planning but should be explicitly acknowledged before Step 2+:

1. Confirm **B. READY_WITHOUT_NUMERICAL_TELEMETRY**.
2. Confirm locked route set in §12.
3. Confirm RunStore retrieval remains **sync methods with `run_id: str`** (reject guide async/`UUID` sketch as API shape).
4. Confirm `POST /api/missions` returns **201 Created** (guide), distinct from `POST /api/sim/run` **200**.

---

## Validation commands (Step 1)

```text
git diff --check
git status --short
```

Full C++/backend suites were not required for this documentation-only step.
