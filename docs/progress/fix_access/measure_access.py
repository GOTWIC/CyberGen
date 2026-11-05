"""The access fixes' measures of a build: full-city tries, open spaces with no way in (and
how the new ways reach the others), green verges, walled-in entrances, gateways, entrances
through their complex, station stairs through a building (as `walkway_building_clash` tests
a walkway). Run from the repository root:

    python docs/progress/fix_access/measure_access.py BUILD_DIR [BUILD_DIR ...]
"""
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, ".")

from shapely.geometry import LineString  # noqa: E402

from citygen import network_checks as NC  # noqa: E402
from citygen.model import CityModel  # noqa: E402


def measure(d: Path) -> dict:
    r = json.loads((d / "report.json").read_text(encoding="utf-8"))
    m = CityModel.model_validate_json((d / "city_model.json").read_text(encoding="utf-8"))
    acc = Counter((o.attrs or {}).get("access") for o in m.open_spaces)
    verges = sum(1 for o in m.open_spaces if o.kind == "green" and (o.attrs or {}).get("verge"))
    ms = NC._Masses(m)
    own_of = NC._passes(m)
    stairs = 0
    for w in m.walkways:
        if w.kind in ("stairs", "escalator") and (w.attrs or {}).get("station") and \
                len(w.line) >= 2:
            line = LineString([p[:2] for p in w.line])
            if line.length > 0 and ms.hits(line, NC._walk_z(m, w.line), own_of(w)):
                stairs += 1
    tries = r["stats"].get("city_tries", [])
    return {
        "tries": len(tries),
        "no_way_in": acc.get("none", 0),
        "via_open_space": acc.get("via_open_space", 0),
        "under_road": acc.get("under_road", 0),
        "far_path": acc.get("path", 0),
        "verges": verges,
        "walled_in": sum(len((b.attrs or {}).get("walled_in", ())) for b in m.buildings),
        "gateways": sum(1 for b in m.buildings if (b.attrs or {}).get("passage_cut")),
        "through_complex": sum(1 for w in m.walkways if (w.attrs or {}).get("through")),
        "stairs_through": stairs,
        "checks": f"{sum(c['passed'] for c in r['checks'])} of {len(r['checks'])}",
    }


if __name__ == "__main__":
    for a in sys.argv[1:]:
        print(Path(a).name, json.dumps(measure(Path(a))))
