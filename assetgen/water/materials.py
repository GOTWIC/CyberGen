"""Material slots of the water packs and the masters they map to in Unreal (AG6's catalog
gives them textures and the water parameters: `assetgen/materials/catalog.py`, `WATER`).

A slot is (master, flat preview color as sRGB hex, roughness, metallic), as AG7's street
slots. `water.<kind>`: a surface of that water kind (master `water`: Single Layer Water in
Unreal); `bed.<material>`: a bed of M16's material (master `bed`: the textured surface with
caustics); `bank.<kind>`: a bank's slope above the water; `wall.*`: stone walls along rivers
and the sea; `stone.riprap`: the instanced riprap stones.
"""

from __future__ import annotations

from ..streets.materials import srgb

MASTERS = ("water", "bed", "concrete")

# the water kinds of AG6's catalog: M16's body kinds (and a body along marshes) to them
WATER_KINDS = ("sea", "river", "canal", "ornamental", "marsh")
KIND_OF = {"sea": "sea", "sea_channel": "sea", "basin": "sea", "marina": "sea",
           "river": "river", "delta_branch": "river", "creek": "river",
           "canal": "canal", "separation": "canal", "inlet": "canal", "ornamental": "ornamental"}

SLOTS: dict[str, tuple[str, str, float, float]] = {
    "water.sea": ("water", "#1d4a5c", 0.04, 0.0),
    "water.river": ("water", "#2f5a52", 0.05, 0.0),
    "water.canal": ("water", "#2e4f4c", 0.05, 0.0),
    "water.ornamental": ("water", "#3a6f7a", 0.03, 0.0),
    "water.marsh": ("water", "#3f4a32", 0.08, 0.0),
    "bed.silt": ("bed", "#5d5546", 0.95, 0.0),
    "bed.mud": ("bed", "#4a4033", 0.95, 0.0),
    "bed.sand": ("bed", "#9c8b68", 0.9, 0.0),
    "bed.gravel": ("bed", "#6f6a5f", 0.9, 0.0),
    "bed.stone": ("bed", "#5f5d58", 0.85, 0.0),
    "bank.natural_bank": ("concrete", "#5d5440", 0.95, 0.0),
    "bank.beach": ("concrete", "#c8b48a", 0.9, 0.0),
    "bank.marsh_edge": ("concrete", "#4c4632", 0.95, 0.0),
    "bank.riprap": ("concrete", "#6d6a63", 0.9, 0.0),
    "bank.road_embankment": ("concrete", "#7a756b", 0.88, 0.0),
    "wall.stone": ("concrete", "#6f6a62", 0.9, 0.0),
    "wall.coping": ("concrete", "#9c978d", 0.8, 0.0),
    "stone.riprap": ("concrete", "#77736b", 0.85, 0.0),
}

# M16's bed materials to bed slots, and what a bank's underwater slope shows
BED_SLOT = {"silt": "bed.silt", "mud": "bed.mud", "sand": "bed.sand", "gravel": "bed.gravel",
            "stone": "bed.stone"}
BANK_BED = {"riprap": "bed.stone", "road_embankment": "bed.stone", "beach": "bed.sand",
            "marsh_edge": "bed.mud", "canal_wall": None, "quay": None, "natural_bank": None}


def gltf_materials(g, names) -> dict[str, int]:
    out = {}
    for n in sorted(set(names)):
        master, color, rough, metal = SLOTS[n]
        out[n] = g.material(n, srgb(color), metallic=metal, roughness=rough,
                            extras={"master": master})
    return out


def contribution_materials(names) -> dict:
    out = {}
    for n in sorted(set(names)):
        master, color, rough, metal = SLOTS[n]
        out[n] = {"master": master, "color": [round(v, 4) for v in srgb(color)[:3]],
                  "roughness": rough, "metallic": metal}
    return out
