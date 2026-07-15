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

Copy `.env.example` to `.env` and adjust paths if needed. Paths are relative to `backend/`.

## Schema tests and checks

```powershell
pytest tests/unit -q
pytest -q
ruff check app tests
mypy app
```

## Layout

- `app/schemas/` — strict Pydantic v2 contracts (Section 8)
- `app/api/`, `app/core/`, `app/services/` — scaffold only until later sections
- `tests/fixtures/results/` — immutable Section 7 capture fixtures
- Release plans remain under repo `plans/`

## Authority

C++ simulator output and JsonIO are the contract authority. Python validates structure only.
