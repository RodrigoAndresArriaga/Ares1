# ARES-1 Phase 1 Backend

FastAPI backend for the frozen C++ simulator (`Simulator/build/sim_core.exe`).

## Setup

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -U pip
pip install -e ".[dev]"
```

Copy `.env.example` to `.env` and adjust paths if needed.

Relative path values in `.env` resolve against the **backend package root on disk**
(`backend/`, derived from the installed package location), not the process current
working directory. Absolute paths are used as given.

## Run (Phase 1)

Requires a valid `.env` and a built simulator binary.

```powershell
cd backend
uvicorn app.main:create_app --factory --host 127.0.0.1 --port 8000
```

Then open `http://127.0.0.1:8000/api/health`, `POST /api/sim/run`, or `/docs`.

Mission outcomes `FAILURE`, `STABILIZED`, and `REJECTED` all return HTTP 200.

## Tests and checks

```powershell
pytest tests/unit -q
pytest -q
ruff check app tests
mypy app
```

## Layout

- `app/core/config.py` — Settings and CWD-independent path resolution (Section 9)
- `app/core/errors.py` — typed errors and HTTP handlers (Section 15)
- `app/core/logging.py` — structured run event logging (Section 15)
- `app/main.py` — application factory, lifespan, shared services (Sections 9/14)
- `app/api/routes/health.py` — `GET /api/health` (Section 9)
- `app/api/routes/simulation.py` — `POST /api/sim/run` (Section 14)
- `app/schemas/` — strict Pydantic v2 contracts (Section 8)
- `app/services/scenario_registry.py` — trusted scenario ID → path (Section 10)
- `app/services/run_store.py` — UUID run workspaces and artifacts (Section 11)
- `app/services/simulator_client.py` — frozen C++ subprocess client (Section 12)
- `app/services/simulation_service.py` — orchestration (Section 13)
- `tests/fixtures/results/` — immutable Section 7 capture fixtures
- Release plans remain under repo `plans/`

## Authority

C++ simulator output and JsonIO are the contract authority. Python validates structure only.
