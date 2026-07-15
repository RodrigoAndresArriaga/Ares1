# ARES-1 Phase 1 Release Gate Evidence

Sections 16, 17, 19.8, 20, and 21. Relative repository paths only.

## Environment

| Item | Value |
|------|-------|
| Date (local) | 2026-07-15T10:07:47-05:00 |
| Platform | Windows-11-10.0.26200-SP0 |
| Python | 3.13.14 (MSC v.1944 64 bit AMD64) |
| CMake / CTest | 4.4.0-rc3 |
| Generator | Ninja (existing `Simulator/build`) |

## Fixture hashes (unchanged)

| Fixture | SHA-256 |
|---------|---------|
| `baseline_result.json` | `C9EAE8F26A37E6D3587038A49984548C0BFF2DEE8367D91C29CFEB76C13A4A79` |
| `valid_plan_result.json` | `A2662DE223878CCB03723063DF5987D933251547B4D8F3FB96499CB3B2EB112C` |
| `invalid_plan_result.json` | `7D9D09FCAC6A0D504F4EE8A9AF6AC89A837E3345B258940CB83A0C1A0AA05CC1` |

Hash verification: `pytest tests/unit/test_fixture_hashes.py` — **PASS**

## C++ release

| Gate | Result |
|------|--------|
| `cmake --build build` | Succeeded (`ninja: no work to do.`) |
| `ctest --test-dir build --output-on-failure` | **114/114 passed** (100%), ~4.33 s |

No Simulator source, scenario, plan, or fixture changes.

## API outcomes (real FastAPI → `Simulator/build/sim_core.exe`)

| Case | HTTP | Outcome | Notes |
|------|------|---------|-------|
| Baseline | 200 | `FAILURE` | 6 telemetry samples, 2 crew/sample, artifacts complete, result SHA matches fixture |
| Valid plan | 200 | `STABILIZED` | 43 telemetry samples, empty `failure_reasons`, plan.json preserved |
| Invalid plan | 200 | `REJECTED` | empty timeline/telemetry, infrastructure `completed`, not 400/422/500 |

## Determinism

Two identical valid-plan HTTP requests:

- HTTP 200 both
- Equal `SimulationResult.model_dump(mode="json")`
- Equal on-disk `result.json` bytes
- Equal SHA-256 `A2662DE223878CCB03723063DF5987D933251547B4D8F3FB96499CB3B2EB112C`
- Metadata `result_sha256` matches each file
- `result.json` contains no backend `run_id` / timestamps
- Distinct `run_id` / workspaces

## Concurrency

Four simultaneous HTTP posts (baseline, valid, invalid, valid repeat) under `max_concurrent_runs=2`:

- Expected outcomes returned
- Unique `run_id`s and workspaces
- Isolated request/scenario/plan/result/stdout/stderr/metadata
- Peak active processes ≤ 2; semaphore restored
- Event-loop probe completed while runs were in flight
- Shared `results/sim_result.json` untouched

## Failure paths

| Path | Result |
|------|--------|
| Unavailable binary (503) | PASS — health + sim `SIMULATOR_UNAVAILABLE`, no path leak, failed metadata |
| Timeout (504) | PASS — kill/reap, failed metadata, no fabricated result, subsequent run OK |
| Malformed output (502) | PASS — `SIMULATOR_OUTPUT_INVALID_JSON`, malformed bytes preserved |
| Artifact failure (500) | PASS — `ARTIFACT_STORAGE_ERROR`, prior evidence retained |

## Quality

| Gate | Result |
|------|--------|
| `pytest` (full, `ARES_REQUIRE_REAL_SIMULATOR=1`) | **269 passed, 2 skipped, 0 failed** (~12.9–14.6 s) |
| Skips | Conditional only: `test_symlink_inside_root_accepted`, `test_symlink_outside_root_rejected` — `symlinks not supported` on this OS/privilege context |
| Real simulator skips | **None** (require-env fail-hard active; all real tests executed) |
| `ruff check app tests` | All checks passed |
| `mypy app` | Success: no issues found in 24 source files |

Focused selections also green: `pytest tests/unit`, `pytest tests/integration`, `pytest -m real_simulator`.

## Security / scope audit

- No `shell=True` / `os.system` / `subprocess.run` / `create_subprocess_shell` in `backend/app`
- No `survival_probability`, NVIDIA, FAISS, WebSocket/SSE in production app
- No Simulator / scenarios / plans / Section 7 fixture diffs
- Production `app/` unchanged for this release-gate step (tests + docs + markers only)
- Shared repository `results/sim_result.json` not used as API output

## Git / scope audit

Branch `main` ahead of `origin/main`. Release-gate delta limited to:

- Backend tests (determinism, concurrency, failure paths, security, fixture hashes, deepened outcome tests)
- `backend/pyproject.toml` marker registration
- `backend/tests/conftest.py` helpers
- `backend/README.md`, `backend/.env.example`, `backend/RELEASE_GATE.md`

## Phase 1 status

**COMPLETE** — HTTP bridge reproduces frozen baseline `FAILURE`, valid-plan `STABILIZED`, and invalid-plan `REJECTED`; preserves the deterministic result contract; distinguishes infrastructure failures from mission outcomes; C++ 114/114 and backend quality gates pass.
