"""District styles of the prop families and the deterministic draws (scope 5.4).

citygen gives every district archetype one era; the props group the ten eras into five
styles, so a city's street lights share a model within a style ("sleek in the Corporate
Core, improvised in Old Town"):

| style | eras | look |
|---|---|---|
| sleek | corporate_glass, clean_tech, aerospace | thin, white and chrome, LED bars, glass |
| civic | mixed_modern, suburban_modern, transit_modern | standard municipal |
| heavy | brutalist, industrial | thick, concrete and galvanized steel, sodium lamps |
| neon | neon_retro | painted, neon accents, screens, improvised additions |
| old | heritage | cast iron and wood, lanterns, patched and improvised |

Every family has `variants(kind)` members per style (4 to 12); a prop picks one by a
blake2b hash of its id (`pick`), plants by species the same way.
"""

from __future__ import annotations

import hashlib

STYLES = ("sleek", "civic", "heavy", "neon", "old")
STYLE_OF_ERA = {"corporate_glass": "sleek", "clean_tech": "sleek", "aerospace": "sleek",
                "mixed_modern": "civic", "suburban_modern": "civic", "transit_modern": "civic",
                "brutalist": "heavy", "industrial": "heavy", "neon_retro": "neon",
                "heritage": "old"}
# citygen's era per district archetype (`citygen/presets.py`, as AG7's paving follows it)
ERA_OF = {"old_town": "heritage", "entertainment_market": "neon_retro",
          "industrial_port": "industrial", "corporate_core": "corporate_glass",
          "megablock_residential": "brutalist", "research_campus": "clean_tech",
          "residential_heights": "suburban_modern", "transit_hub": "transit_modern",
          "midtown_mixed": "mixed_modern", "spaceport": "aerospace"}

# variants per prop kind and style (the scope's 4 to 12; more where a street shows many)
PROP_VARIANTS = {
    "street_light": 6, "wall_light": 5, "traffic_signal": 4, "trash_can": 5, "bus_stop": 4,
    "hydrant": 4, "bollard": 5, "bench": 6, "kiosk": 4, "vending_machine": 6,
    "food_stall": 6, "planter": 5, "parked_vehicle": 12, "boat": 6, "barrier": 4,
    "railing": 4, "awning": 8, "ac_unit": 8, "dumpster": 5, "trash": 12, "bracket": 4,
}
# kinds that are meshes of their own (their M6 geometry exactly), not instanced variants
EXACT = ("overhead_cable", "scaffolding", "gate")
# kinds an M11 sign slot stands for
SLOTTED = ("sign",)

# plant species: variants per species (the scope's 6 to 10 for trees)
PLANT_VARIANTS = {
    "plane": 8, "maple": 8, "ginkgo": 8, "birch": 8, "linden": 8, "elm": 8, "oak": 8,
    "ficus": 8, "pine": 8, "fan_palm": 6, "date_palm": 6, "boxwood": 6, "sedum": 6,
    "ivy": 6, "scrub": 6,
}
# what a plant type without a species gets
SPECIES_OF_TYPE = {"street_tree": "plane", "median_tree": "plane", "park_tree": "oak",
                   "roof_tree": "maple", "conifer": "pine", "palm": "fan_palm",
                   "shrub": "boxwood", "overgrowth": "scrub", "facade_greenery": "ivy"}


def era_of(archetype: str | None) -> str:
    return ERA_OF.get(archetype or "", "mixed_modern")


def style_of(archetype: str | None) -> str:
    return STYLE_OF_ERA[era_of(archetype)]


def u(*key) -> float:
    """A uniform number in [0, 1) from a blake2b hash of the key (as citygen's `props._u`)."""
    h = hashlib.blake2b("|".join(str(k) for k in key).encode("utf-8"), digest_size=8).digest()
    return int.from_bytes(h, "big") / 18446744073709551616.0


def pick(n: int, *key) -> int:
    return min(int(u(*key) * n), n - 1)


def choice(seq, *key):
    return seq[pick(len(seq), *key)]


def rng(lo: float, hi: float, *key) -> float:
    """A draw in [lo, hi), quantized to the millimeter."""
    return round((lo + (hi - lo) * u(*key)) * 1000.0) / 1000.0


def variant_name(kind: str, style: str, k: int) -> str:
    """A prop variant's node and part kind: `prop.<kind>.<style>.v<k>`."""
    return f"prop.{kind}.{style}.v{k}"


def plant_name(species: str, k: int) -> str:
    return f"plant.{species}.v{k}"
