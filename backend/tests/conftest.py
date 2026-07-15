# shared fixture loaders for immutable Section 7 evidence
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

BACKEND_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND_ROOT.parent
RESULTS_DIR = BACKEND_ROOT / "tests" / "fixtures" / "results"
PLANS_DIR = REPO_ROOT / "plans"

BASELINE_SHA256 = "C9EAE8F26A37E6D3587038A49984548C0BFF2DEE8367D91C29CFEB76C13A4A79"
VALID_RESULT_SHA256 = "A2662DE223878CCB03723063DF5987D933251547B4D8F3FB96499CB3B2EB112C"
INVALID_RESULT_SHA256 = "7D9D09FCAC6A0D504F4EE8A9AF6AC89A837E3345B258940CB83A0C1A0AA05CC1"


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.fixture(scope="session")
def baseline_result_data() -> Any:
    return _load_json(RESULTS_DIR / "baseline_result.json")


@pytest.fixture(scope="session")
def valid_plan_result_data() -> Any:
    return _load_json(RESULTS_DIR / "valid_plan_result.json")


@pytest.fixture(scope="session")
def invalid_plan_result_data() -> Any:
    return _load_json(RESULTS_DIR / "invalid_plan_result.json")


@pytest.fixture(scope="session")
def sample_plan_data() -> Any:
    return _load_json(PLANS_DIR / "sample_plan.json")


@pytest.fixture(scope="session")
def invalid_plan_data() -> Any:
    return _load_json(PLANS_DIR / "invalid_plan.json")


@pytest.fixture(scope="session")
def all_result_data(
    baseline_result_data: Any,
    valid_plan_result_data: Any,
    invalid_plan_result_data: Any,
) -> list[Any]:
    return [baseline_result_data, valid_plan_result_data, invalid_plan_result_data]
