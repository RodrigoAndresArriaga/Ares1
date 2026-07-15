# ARES-1 Phase 1 Backend

FastAPI bridge for the frozen C++ simulator. Phase 1 proves that HTTP can
launch isolated simulator runs, return strict `SimulationResult` contracts, and
preserve artifacts — without reimplementing mission physics in Python.

## Authority boundary

- C++ simulator (`Simulator/build/sim_core.exe`) owns physics, physiology,
  feasibility, metrics, telemetry, timeline, and outcome.
- Python validates JSON structure, isolates run workspaces, and maps
  infrastructure failures to typed HTTP errors.
- Mission outcomes `FAILURE`, `STABILIZED`, and `REJECTED` are valid results
  and return HTTP **200** when infrastructure succeeds.

## Implemented scope

- Strict Pydantic v2 contracts (`extra="forbid"`)
- CWD-independent Settings and application factory
- `GET /api/health` readiness
- Explicit `ScenarioRegistry` (trusted `scenario_id` only)
- UUID-isolated `RunStore` artifacts
- Async `SimulatorClient` with shared semaphore and timeout kill/reap
- `SimulationService` orchestration
- `POST /api/sim/run`
- Typed HTTP error mapping and structured run logging
- Real FastAPI → C++ release integration, determinism, and concurrency tests

## Explicitly excluded (later phases)

NVIDIA / NIM clients, RAG / FAISS, procedure manuals, accident lifecycle,
telemetry replay, WebSockets / SSE, planner implementation, frontend,
database, authentication, and deployment.

## Prerequisites

- Python **3.11+**
- Built frozen simulator at `Simulator/build/sim_core.exe` (Windows) or the
  equivalent non-Windows binary path
- Release scenario:
  `scenarios/mars_hab_atmosphere_solar_failure.json`
- Release plans: `plans/sample_plan.json`, `plans/invalid_plan.json`
- CMake/CTest tooling for the C++ gate (for full release verification)

## Repository paths

| Role | Path |
|------|------|
| Backend package | `backend/` |
| Frozen simulator tree | `Simulator/` |
| Executable (Windows) | `Simulator/build/sim_core.exe` |
| Scenarios | `scenarios/` |
| Plans | `plans/` |
| Shared CLI scratch (never API output) | `results/` |
| Per-run artifacts | `backend/data/runs/<uuid>/` |
| Section 7 fixtures | `backend/tests/fixtures/results/` |

## Virtual environment setup

### PowerShell

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
Copy-Item .env.example .env
```

### Bash

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
cp .env.example .env
```

On non-Windows hosts, set `ARES_SIM_BINARY` in `.env` to the built binary
path without assuming `.exe`.

## Environment configuration

Relative path values resolve against the **backend package root on disk**
(`backend/`), not the process CWD. Absolute paths are used as given.

See [`.env.example`](.env.example) for:

- `ARES_PROJECT_ROOT`
- `ARES_SIM_BINARY`
- `ARES_SCENARIO_DIR`
- `ARES_RUNS_DIR`
- `ARES_SIM_TIMEOUT_SECONDS`
- `ARES_MAX_CONCURRENT_RUNS`
- `ARES_LOG_LEVEL`

No API keys, NVIDIA settings, or secrets belong in Phase 1 env files.

## Run (Uvicorn factory)

Requires a valid `.env` and a built simulator binary.

```powershell
cd backend
uvicorn app.main:create_app --factory --host 127.0.0.1 --port 8000
```

Optional local reload:

```powershell
uvicorn app.main:create_app --factory --reload --host 127.0.0.1 --port 8000
```

Do not use a non-factory `app.main:app` target; the module exports
`create_app` only.

## Health endpoint

`GET /api/health`

- HTTP 200 and `simulator_ready: true` when binary, scenario root, release
  scenario file, and runs directory are usable
- HTTP 503 and `simulator_ready: false` when prerequisites are missing
- Does not launch a simulation

## Simulation endpoint

`POST /api/sim/run`

Accepts registered `scenario_id` and optional inline `plan`. Does not accept
arbitrary scenario paths, executable paths, output paths, or command arguments.

### Baseline request (expected `FAILURE`)

```powershell
curl.exe -s -X POST http://127.0.0.1:8000/api/sim/run `
  -H "Content-Type: application/json" `
  -d "{\"scenario_id\":\"mars_hab_atmosphere_solar_failure\"}"
```

### Valid release plan (expected `STABILIZED`)

Load `plans/sample_plan.json` as the `plan` field. Example with
`Invoke-RestMethod`:

```powershell
$plan = Get-Content ..\plans\sample_plan.json -Raw | ConvertFrom-Json
$body = @{
  scenario_id = "mars_hab_atmosphere_solar_failure"
  plan = $plan
} | ConvertTo-Json -Depth 20
Invoke-RestMethod -Method POST -Uri http://127.0.0.1:8000/api/sim/run `
  -ContentType "application/json" -Body $body |
  Select-Object run_id, @{n='outcome';e={$_.result.outcome}}
```

Responses include full `telemetry_history` (large for stabilized runs). Inspect
`run_id` and selected result fields; do not paste entire telemetry into docs.

### Invalid release plan (expected `REJECTED`)

Use `plans/invalid_plan.json` as `plan`. Returns HTTP **200** with
`outcome: REJECTED`. This is not a 400/422/500.

## HTTP status semantics

| Condition | Status |
|-----------|--------|
| `FAILURE` / `STABILIZED` / `REJECTED` | 200 |
| Invalid request schema | 422 |
| Unknown `scenario_id` | 404 |
| Simulator unavailable | 503 |
| Simulator timeout | 504 |
| Process / output bridge failure | 502 |
| Artifact storage failure | 500 |

## Run artifact directory structure

Each request creates `backend/data/runs/<uuid>/` (or the configured
`ARES_RUNS_DIR`) containing:

- `request.json`
- `scenario.json` (exact copy)
- `plan.json` (plan mode only)
- `result.json` (simulator-written; backend does not rewrite)
- `stdout.log` / `stderr.log`
- `metadata.json` (hashes, status, outcome)

The shared repository file `results/sim_result.json` is never used as API output.

## Test commands

```powershell
cd backend
pytest
pytest tests/unit
pytest tests/integration
pytest -m real_simulator
```

Release gate (fail if frozen binary missing instead of silently skipping):

```powershell
$env:ARES_REQUIRE_REAL_SIMULATOR = "1"
pytest -m real_simulator
pytest
```

Markers (registered in `pyproject.toml`):

- `integration` — HTTP/service integration tests
- `real_simulator` — requires `Simulator/build/sim_core.exe`

## Ruff and mypy

```powershell
ruff check app tests
mypy app
```

## C++ build and CTest

From the simulator tree (build directory already configured):

```powershell
cd Simulator
cmake --build build
ctest --test-dir build --output-on-failure
```

Do not modify simulator sources for Phase 1 backend work. Expected historical
gate: **114/114** CTest tests.

## Determinism

Identical scenario bytes and identical validated plan bytes produce identical
simulator `SimulationResult` content. Section 7 proved the valid-plan release
result is byte-deterministic (SHA-256
`A2662DE223878CCB03723063DF5987D933251547B4D8F3FB96499CB3B2EB112C`).
The backend must not insert `run_id` or timestamps into `result.json`.

## Security constraints

- Launch only via `asyncio.create_subprocess_exec` (no shell)
- Clients supply `scenario_id`, never filesystem paths or argv
- Executable and output paths come only from Settings / UUID workspaces
- HTTP errors exclude absolute paths, tracebacks, stdout/stderr, and env dumps
- Structured logs exclude full telemetry, complete plans, and secrets
- Shared semaphore limits concurrent external processes
- No `survival_probability` in the API contract; crew remains `crew`

## Troubleshooting

| Symptom | Check |
|---------|-------|
| Health 503 / `SIMULATOR_UNAVAILABLE` | Built binary path in `.env`; file exists and is non-empty |
| Settings `ValueError` at startup | Paths resolve against `backend/`; runs dir writable |
| Real simulator tests skip | Build `sim_core.exe`, or set `ARES_REQUIRE_REAL_SIMULATOR=1` for fail-hard release |
| `REJECTED` looks like an error | Invalid plans return HTTP 200 with outcome `REJECTED` |

## Confirmation

This Phase 1 backend includes **no** NVIDIA clients, RAG/FAISS, frontend,
WebSocket/SSE, database, or authentication code.

## Release evidence

Final gate results are recorded in [`RELEASE_GATE.md`](RELEASE_GATE.md).

## Layout

- `app/core/config.py` — Settings and CWD-independent path resolution
- `app/core/errors.py` — typed errors and HTTP handlers
- `app/core/logging.py` — structured run event logging
- `app/main.py` — application factory and lifespan
- `app/api/routes/health.py` — `GET /api/health`
- `app/api/routes/simulation.py` — `POST /api/sim/run`
- `app/schemas/` — strict Pydantic contracts
- `app/services/scenario_registry.py` — trusted scenario ID → path
- `app/services/run_store.py` — UUID workspaces and artifacts
- `app/services/simulator_client.py` — frozen C++ subprocess client
- `app/services/simulation_service.py` — orchestration
- `tests/fixtures/results/` — immutable Section 7 capture fixtures
