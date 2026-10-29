"""Per-building material parameters (scope 5.2: per-building variation without unique
textures): the era whose sets a building's walls and roof take, and the Custom Primitive
Data AG6 adds after AG1's 23 floats (`CPD_LAYOUT`):

| index | value |
|---|---|
| 23 | room width (m): the building's bay, the interior grid across a facade |
| 24 | floor height (m): the interior grid up a facade (UV0 v is the height from the base) |
| 25 | interior atlas row (`interiors.USES`, by the building's use and type) |
| 26 | rain streaks, 0 to 1 (wear and era) |
| 27 | the top of the building over its pivot (m): where the streaks start |
| 28 | the share of rooms with their blinds down |
| 29 | the era's index in `library.ERAS` |

They are computed in the main process from each brief and genome on every build (cheap),
so records kept from an earlier build get them too.
"""

from __future__ import annotations

from . import catalog as CT
from . import interiors as IN
from . import library as LB

CPD_EXT = {"23": "room width (m)", "24": "floor height (m)", "25": "interior atlas row",
           "26": "rain streaks", "27": "top over the pivot (m)", "28": "blinds down",
           "29": "era index"}
BLINDS = {"office": 0.25, "apartment": 0.5, "capsule": 0.4, "shop": 0.1, "club": 0.6,
          "warehouse": 0.3}


def building(brief: dict, genome: dict, rec: dict) -> dict:
    era = CT.era_of_building(brief)
    look = LB.ERA_LOOK[era]
    b = brief["building"]
    row = IN.use_row(b.get("use") or "", b.get("type") or "")
    wear = float(genome["cont"]["wear"])
    room = min(max(float(rec.get("bay_m") or 3.0), 2.4), 6.0)
    floor = float(rec.get("floor_m") or b["floor_grid"]["floor_height_m"] or 3.5)
    top = float(rec["bounds"][1][2]) if rec.get("bounds") else float(b.get("height_m") or 10)
    streaks = min(1.0, 0.25 + 0.5 * wear + 0.3 * look["wear"])
    ext = [round(room, 3), round(floor, 3), float(row), round(streaks, 3), round(top, 3),
           BLINDS[IN.USES[row]], float(LB.ERAS.index(era))]
    return {"era": era, "interior": IN.USES[row], "cpd": ext}


def annotate(records: dict, briefs: dict, genomes: dict) -> None:
    """Add `material` (era, interior use, the extra CPD) to every building record."""
    for bid, rec in records.items():
        if bid in briefs:
            rec["material"] = building(briefs[bid], genomes[bid], rec)


def slot_materials(slots, era: str) -> dict[str, str]:
    """A building's slot -> material key, for the slots whose key is not the slot's own."""
    return {s: f"{s}@{era}" for s in sorted(slots) if s in CT.ERA_SLOTS}
