import copy
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = sorted((ROOT / "docs" / "progress" / "M0").glob("*/city_spec.json"))

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


def write(tmp_path: Path, data, name: str = "spec.json") -> Path:
    p = tmp_path / name
    p.write_text(data if isinstance(data, str) else json.dumps(data), encoding="utf-8")
    return p
