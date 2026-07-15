# ScenarioRegistry: explicit mapping, containment, and typed not-found
from __future__ import annotations

from pathlib import Path

import pytest
from app.core.errors import ScenarioNotFoundError
from app.schemas.api import ErrorCode
from app.services.scenario_registry import (
    DEFAULT_SCENARIO_MAPPING,
    ScenarioRegistry,
)
from tests.conftest import (
    RELEASE_SCENARIO_ID,
    RELEASE_SCENARIO_PATH,
    install_release_scenario,
)


def test_default_mapping_matches_release_evidence() -> None:
    assert DEFAULT_SCENARIO_MAPPING[RELEASE_SCENARIO_ID] == (
        RELEASE_SCENARIO_PATH.name
    )


def test_resolve_release_scenario(tmp_path: Path) -> None:
    scenario_dir = tmp_path / "scenarios"
    installed = install_release_scenario(scenario_dir)
    registry = ScenarioRegistry(scenario_dir)
    resolved = registry.resolve_scenario(RELEASE_SCENARIO_ID)
    assert resolved == installed.resolve()
    assert resolved.is_file()
    assert resolved.read_bytes() == RELEASE_SCENARIO_PATH.read_bytes()


def test_exact_scenario_id_required(tmp_path: Path) -> None:
    install_release_scenario(tmp_path / "scenarios")
    registry = ScenarioRegistry(tmp_path / "scenarios")
    with pytest.raises(ScenarioNotFoundError) as exc_info:
        registry.resolve_scenario(RELEASE_SCENARIO_ID + ".json")
    assert exc_info.value.code == ErrorCode.SCENARIO_NOT_FOUND


@pytest.mark.parametrize(
    "scenario_id",
    [
        "",
        "unknown_scenario",
        "../../file",
        r"..\..\file",
        r"C:\Windows\System32\drivers",
        "/etc/passwd",
        "mars_hab_atmosphere_solar_failure/../other",
    ],
)
def test_unknown_and_traversal_ids_rejected(
    tmp_path: Path, scenario_id: str
) -> None:
    install_release_scenario(tmp_path / "scenarios")
    registry = ScenarioRegistry(tmp_path / "scenarios")
    with pytest.raises(ScenarioNotFoundError) as exc_info:
        registry.resolve_scenario(scenario_id)
    assert exc_info.value.scenario_id == scenario_id
    assert str(tmp_path.resolve()) not in exc_info.value.message
    assert "Scenario not found" == exc_info.value.message


def test_no_filename_derivation_for_unknown_id(tmp_path: Path) -> None:
    scenario_dir = tmp_path / "scenarios"
    scenario_dir.mkdir()
    crafted = scenario_dir / "invented_id.json"
    crafted.write_text("{}", encoding="utf-8")
    registry = ScenarioRegistry(scenario_dir)
    with pytest.raises(ScenarioNotFoundError):
        registry.resolve_scenario("invented_id")


def test_registered_target_missing(tmp_path: Path) -> None:
    scenario_dir = tmp_path / "scenarios"
    scenario_dir.mkdir()
    registry = ScenarioRegistry(scenario_dir)
    with pytest.raises(ScenarioNotFoundError):
        registry.resolve_scenario(RELEASE_SCENARIO_ID)


def test_registered_target_is_directory(tmp_path: Path) -> None:
    scenario_dir = tmp_path / "scenarios"
    target = scenario_dir / RELEASE_SCENARIO_PATH.name
    target.mkdir(parents=True)
    registry = ScenarioRegistry(scenario_dir)
    with pytest.raises(ScenarioNotFoundError):
        registry.resolve_scenario(RELEASE_SCENARIO_ID)


def test_configured_scenario_root_resolution(tmp_path: Path) -> None:
    scenario_dir = tmp_path / "scenarios"
    install_release_scenario(scenario_dir)
    registry = ScenarioRegistry(scenario_dir)
    assert registry.resolve_scenario(RELEASE_SCENARIO_ID).is_relative_to(
        scenario_dir.resolve()
    )


def test_cwd_independence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    scenario_dir = tmp_path / "scenarios"
    installed = install_release_scenario(scenario_dir)
    other = tmp_path / "other_cwd"
    other.mkdir()
    monkeypatch.chdir(other)
    registry = ScenarioRegistry(scenario_dir)
    assert registry.resolve_scenario(RELEASE_SCENARIO_ID) == installed.resolve()


def test_list_scenarios_deterministic(tmp_path: Path) -> None:
    mapping = {
        "z_scenario": "z.json",
        "a_scenario": "a.json",
        "m_scenario": "m.json",
    }
    for name in mapping.values():
        (tmp_path / name).write_text("{}", encoding="utf-8")
    registry = ScenarioRegistry(tmp_path, mapping=mapping)
    assert registry.list_scenarios() == ("a_scenario", "m_scenario", "z_scenario")


def test_mapping_not_mutated(tmp_path: Path) -> None:
    install_release_scenario(tmp_path)
    injected = {"alpha": "alpha.json"}
    (tmp_path / "alpha.json").write_text("{}", encoding="utf-8")
    registry = ScenarioRegistry(tmp_path, mapping=injected)
    injected["beta"] = "beta.json"
    assert registry.list_scenarios() == ("alpha",)
    with pytest.raises(ScenarioNotFoundError):
        registry.resolve_scenario("beta")


def test_mapping_proxy_immutable(tmp_path: Path) -> None:
    install_release_scenario(tmp_path)
    registry = ScenarioRegistry(tmp_path)
    with pytest.raises(TypeError):
        registry._mapping["x"] = "y"  # type: ignore[index]


def _try_symlink(link: Path, target: Path) -> bool:
    try:
        link.symlink_to(target)
        return True
    except OSError:
        return False


def test_symlink_inside_root_accepted(tmp_path: Path) -> None:
    scenario_dir = tmp_path / "scenarios"
    scenario_dir.mkdir()
    real = scenario_dir / "real_payload.json"
    real.write_text('{"ok": true}', encoding="utf-8")
    link = scenario_dir / RELEASE_SCENARIO_PATH.name
    if not _try_symlink(link, real):
        pytest.skip("symlinks not supported")
    registry = ScenarioRegistry(scenario_dir)
    resolved = registry.resolve_scenario(RELEASE_SCENARIO_ID)
    assert resolved.is_file()
    assert resolved.read_text(encoding="utf-8") == '{"ok": true}'


def test_symlink_outside_root_rejected(tmp_path: Path) -> None:
    scenario_dir = tmp_path / "scenarios"
    outside = tmp_path / "outside"
    scenario_dir.mkdir()
    outside.mkdir()
    secret = outside / "secret.json"
    secret.write_text('{"secret": true}', encoding="utf-8")
    link = scenario_dir / RELEASE_SCENARIO_PATH.name
    if not _try_symlink(link, secret):
        pytest.skip("symlinks not supported")
    registry = ScenarioRegistry(scenario_dir)
    with pytest.raises(ScenarioNotFoundError) as exc_info:
        registry.resolve_scenario(RELEASE_SCENARIO_ID)
    assert str(secret) not in exc_info.value.message
    assert str(outside) not in exc_info.value.message
