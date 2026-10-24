import copy
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = sorted((ROOT / "docs" / "progress" / "M0").glob("*/city_spec.json"))
# The M1a build samples: the four M0 cities (specs as adjusted for M1a) and Nyxllor.
CITIES = sorted((ROOT / "docs" / "progress" / "M1a").glob("*/city_spec.json")) + [
    ROOT / "cities" / "nyxllor" / "city_spec.json"]

# A small, fast city for build tests: straight coast, one river, one island district.
SMALL = {
    "name": "Testport", "seed": 7, "size_km": [2.4, 2.4],
    "water": {"coast": {"form": "straight", "side": "south", "sea_share": 0.35},
              "rivers": [{"name": "Test River", "from": "north", "to": "sea",
                          "width_m": [50, 80]}],
              "islands": [{"name": "Test Isle", "position": "south_east",
                           "setting": "nearshore", "area_km2": 0.15}]},
    "districts": [
        {"name": "Core", "archetype": "corporate_core", "placement": {"edge": "center"}},
        {"name": "Harbor", "archetype": "industrial_port",
         "placement": {"coast": True, "west_of": "Core"}},
        {"name": "Old Quarter", "archetype": "old_town",
         "placement": {"coast": True, "east_of": "Core"}},
        {"name": "Uptown", "archetype": "residential_heights", "placement": {"north_of": "Core"}},
        {"name": "Test Isle", "archetype": "research_campus",
         "placement": {"on_island": "Test Isle"}},
    ],
}

MINIMAL = {
    "name": "Harborlight",
    "seed": 42,
    "water": {"coast": {"form": "straight", "side": "south"},
              "rivers": [{"name": "Grey River", "from": "north", "to": "sea"}]},
    "transit": {"lines": [{"mode": "metro", "name": "Line 1",
                           "route": ["Harbor", "Core", "Uptown"]},
                          {"mode": "maglev", "name": "Express",
                           "route": ["Core", "Launch", "east_exit"]}]},
    "districts": [
        {"name": "Core", "archetype": "corporate_core", "placement": {"edge": "center"},
         "landmarks": ["megatower"]},
        {"name": "Harbor", "archetype": "industrial_port",
         "placement": {"coast": True, "south_of": "Core"}},
        {"name": "Uptown", "archetype": "residential_heights", "placement": {"north_of": "Core"}},
        {"name": "Launch", "archetype": "spaceport", "area_share": 0.2,
         "placement": {"edge": "east", "coast": True}},
    ],
}


@pytest.fixture
def minimal() -> dict:
    return copy.deepcopy(MINIMAL)


@pytest.fixture
def small() -> dict:
    return copy.deepcopy(SMALL)


def write(tmp_path: Path, data, name: str = "spec.json") -> Path:
    p = tmp_path / name
    p.write_text(data if isinstance(data, str) else json.dumps(data), encoding="utf-8")
    return p
