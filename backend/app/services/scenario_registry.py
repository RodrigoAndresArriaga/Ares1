# resolve approved scenario IDs to trusted filesystem paths
# never derive filenames from arbitrary client input
from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from types import MappingProxyType

from app.core.errors import ScenarioNotFoundError

DEFAULT_SCENARIO_MAPPING: Mapping[str, str] = MappingProxyType(
    {
        "mars_hab_atmosphere_solar_failure": (
            "mars_hab_atmosphere_solar_failure.json"
        ),
    }
)


class ScenarioRegistry:
    def __init__(
        self,
        scenario_root: Path,
        mapping: Mapping[str, str] | None = None,
    ) -> None:
        self._root = scenario_root.resolve()
        source = dict(DEFAULT_SCENARIO_MAPPING if mapping is None else mapping)
        self._mapping: Mapping[str, str] = MappingProxyType(source)

    def resolve_scenario(self, scenario_id: str) -> Path:
        filename = self._mapping.get(scenario_id)
        if filename is None:
            raise ScenarioNotFoundError(scenario_id=scenario_id)

        if Path(filename).is_absolute() or "/" in filename or "\\" in filename:
            raise ScenarioNotFoundError(scenario_id=scenario_id)

        candidate = (self._root / filename).resolve()
        if not candidate.is_relative_to(self._root):
            raise ScenarioNotFoundError(scenario_id=scenario_id)
        if not candidate.is_file():
            raise ScenarioNotFoundError(scenario_id=scenario_id)
        return candidate

    def list_scenarios(self) -> tuple[str, ...]:
        return tuple(sorted(self._mapping.keys()))
