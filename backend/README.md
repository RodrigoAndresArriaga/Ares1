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

## Run (Phase 1 health)

Requires a valid `.env` and a built simulator binary.

```powershell
cd backend
uvicorn app.main:create_app --factory --host 127.0.0.1 --port 8000
```

Then open `http://127.0.0.1:8000/api/health` or `/docs`.

## Tests and checks

```powershell
pytest tests/unit -q
pytest -q
ruff check app tests
mypy app
```

## Layout

- `app/core/config.py` — Settings and CWD-independent path resolution (Section 9)
- `app/main.py` — application factory and lifespan readiness (Section 9)
- `app/api/routes/health.py` — `GET /api/health` (Section 9)
- `app/schemas/` — strict Pydantic v2 contracts (Section 8)
- `app/services/scenario_registry.py` — trusted scenario ID → path (Section 10)
- `app/services/run_store.py` — UUID run workspaces and artifacts (Section 11)
- `tests/fixtures/results/` — immutable Section 7 capture fixtures
- Release plans remain under repo `plans/`

## Authority

C++ simulator output and JsonIO are the contract authority. Python validates structure only.
