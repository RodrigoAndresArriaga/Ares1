# assert Section 7 captured fixture SHA-256 values remain unchanged
from __future__ import annotations

from pathlib import Path

from tests.conftest import FIXTURE_SHA256_BY_NAME, RESULTS_DIR, sha256_hex_upper


def test_section7_fixture_hashes_unchanged() -> None:
    for name, expected in FIXTURE_SHA256_BY_NAME.items():
        path = RESULTS_DIR / name
        assert path.is_file()
        assert sha256_hex_upper(path) == expected


def test_fixture_hash_constants_are_uppercase_hex() -> None:
    for expected in FIXTURE_SHA256_BY_NAME.values():
        assert len(expected) == 64
        assert expected == expected.upper()
        int(expected, 16)


def test_fixture_files_are_not_empty() -> None:
    for name in FIXTURE_SHA256_BY_NAME:
        path: Path = RESULTS_DIR / name
        assert path.stat().st_size > 0
