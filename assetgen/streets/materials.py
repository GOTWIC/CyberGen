"""Material slots of the street packs and the masters they map to in Unreal.

A slot is a material instance: its master, a flat preview color (linear-ish sRGB hex, as the
blockout's), roughness and metallic. AG6 gives them textures; until then the colors carry
the look in Blender and Unreal. Paving and curb families follow the district's era.
"""

from __future__ import annotations

# masters: road (asphalt and paint), opaque (concrete, stone, paving), metal, emissive
# (light strips), translucent (sky tube glass, non-Nanite)
MASTERS = ("road", "opaque", "metal", "emissive", "translucent", "foliage")

SLOTS: dict[str, tuple[str, str, float, float]] = {
    # roads
    "asphalt.highway": ("road", "#26282c", 0.82, 0.0),
    "asphalt.avenue": ("road", "#2c2e33", 0.85, 0.0),
    "asphalt.street": ("road", "#323439", 0.88, 0.0),
    "asphalt.alley": ("road", "#3a3a3c", 0.92, 0.0),
    "asphalt.patch": ("road", "#1e1f22", 0.8, 0.0),
    "marking.white": ("road", "#d8d8d2", 0.6, 0.0),
    "marking.yellow": ("road", "#d9a521", 0.6, 0.0),
    "marking.red": ("road", "#8c1f24", 0.7, 0.0),
    "manhole": ("metal", "#3d3b38", 0.55, 0.9),
    "grate": ("metal", "#2a2a2a", 0.6, 0.85),
    "tactile": ("opaque", "#c9a227", 0.7, 0.0),
    "lawn": ("foliage", "#3f5a2c", 0.95, 0.0),
    # curbs and paving families
    "curb.granite": ("opaque", "#8e8e8a", 0.7, 0.0),
    "curb.concrete": ("opaque", "#9a9890", 0.85, 0.0),
    "paving.cobble": ("opaque", "#5a5550", 0.9, 0.0),
    "paving.tile": ("opaque", "#76726c", 0.85, 0.0),
    "paving.granite": ("opaque", "#a7a6a1", 0.7, 0.0),
    "paving.granite_dark": ("opaque", "#55575a", 0.7, 0.0),
    "paving.concrete_slab": ("opaque", "#8f8c86", 0.88, 0.0),
    "paving.concrete_cast": ("opaque", "#86837c", 0.9, 0.0),
    "paving.concrete_tile": ("opaque", "#9b968d", 0.86, 0.0),
    "paving.resin": ("opaque", "#c4c2b8", 0.75, 0.0),
    "paving.brick": ("opaque", "#8a4f3c", 0.88, 0.0),
    "paving.timber": ("opaque", "#6b5038", 0.8, 0.0),
    # structures
    "concrete": ("opaque", "#8a8883", 0.88, 0.0),
    "concrete.deck": ("opaque", "#7e7c77", 0.88, 0.0),
    "concrete.barrier": ("opaque", "#a19e96", 0.85, 0.0),
    "concrete.column": ("opaque", "#76746f", 0.88, 0.0),
    "concrete.dark": ("opaque", "#55534f", 0.9, 0.0),
    # M14's decks (AG10): the soffit, the edge fascia, grime streaks and stains
    "concrete.soffit": ("opaque", "#6b6965", 0.92, 0.0),
    "concrete.fascia": ("opaque", "#8f8d87", 0.85, 0.0),
    "stain": ("opaque", "#3b3833", 0.95, 0.0),
    "stone.quay": ("opaque", "#6f6a62", 0.9, 0.0),
    "stone.coping": ("opaque", "#9c978d", 0.8, 0.0),
    "stone.arch": ("opaque", "#8b8273", 0.9, 0.0),
    "tile.tunnel": ("opaque", "#c9c7bd", 0.45, 0.0),
    "steel": ("metal", "#5d6166", 0.45, 1.0),
    "steel.painted": ("metal", "#3f4a55", 0.55, 0.6),
    "steel.red": ("metal", "#8e2a22", 0.5, 0.6),
    "steel.cable": ("metal", "#2d2f33", 0.4, 1.0),
    "steel.joint": ("metal", "#4b4c4e", 0.5, 1.0),
    "rail": ("metal", "#7b7d80", 0.35, 1.0),
    "ballast": ("opaque", "#4f4b47", 0.95, 0.0),
    "sleeper": ("opaque", "#5c5a56", 0.9, 0.0),
    "rubber": ("opaque", "#1c1c1c", 0.9, 0.0),
    "light": ("emissive", "#fff1d6", 0.3, 0.0),
    "light.cool": ("emissive", "#d6ecff", 0.3, 0.0),
    "glass.tube": ("translucent", "#9fd6e8", 0.05, 0.0),
    "glass.panel": ("translucent", "#8fb8c8", 0.05, 0.0),
    "glass.opaque": ("opaque", "#5f7f8f", 0.1, 0.3),
    "water.pond": ("opaque", "#2b4b5a", 0.1, 0.0),
    "pitch": ("foliage", "#3d6b35", 0.9, 0.0),
    # megasites
    "container.c0": ("metal", "#8c2b22", 0.6, 0.4),
    "container.c1": ("metal", "#1f4e79", 0.6, 0.4),
    "container.c2": ("metal", "#3b6b3a", 0.6, 0.4),
    "container.c3": ("metal", "#b98a2b", 0.6, 0.4),
    "container.c4": ("metal", "#6d6f72", 0.6, 0.4),
    "container.c5": ("metal", "#d4d2cc", 0.6, 0.4),
    "tank": ("metal", "#d9dad6", 0.5, 0.5),
    "pad": ("opaque", "#6a6964", 0.85, 0.0),
    "crane": ("metal", "#c75b12", 0.5, 0.5),
}

# paving and curb by era (citygen gives every district archetype one era)
ERA_OF = {"old_town": "heritage", "entertainment_market": "neon_retro",
          "industrial_port": "industrial", "corporate_core": "corporate_glass",
          "megablock_residential": "brutalist", "research_campus": "clean_tech",
          "residential_heights": "suburban_modern", "transit_hub": "transit_modern",
          "midtown_mixed": "mixed_modern", "spaceport": "aerospace"}

PAVING = {"heritage": "paving.cobble", "neon_retro": "paving.tile",
          "corporate_glass": "paving.granite", "brutalist": "paving.concrete_slab",
          "industrial": "paving.concrete_cast", "clean_tech": "paving.resin",
          "suburban_modern": "paving.brick", "transit_modern": "paving.granite_dark",
          "mixed_modern": "paving.concrete_tile", "aerospace": "paving.concrete_cast"}

CURB = {"heritage": "curb.granite", "corporate_glass": "curb.granite",
        "transit_modern": "curb.granite", "clean_tech": "curb.granite"}

# crosswalk paint: ladder (continental bars between two side lines) in the planned, wealthy
# eras, zebra elsewhere
LADDER_ERAS = ("corporate_glass", "transit_modern", "clean_tech", "aerospace")


def era_of(archetype: str | None) -> str:
    return ERA_OF.get(archetype or "", "mixed_modern")


def paving(archetype: str | None) -> str:
    return PAVING[era_of(archetype)]


def curb(archetype: str | None) -> str:
    return CURB.get(era_of(archetype), "curb.concrete")


def srgb(hexcolor: str) -> tuple[float, float, float, float]:
    h = hexcolor.lstrip("#")
    return tuple(round(int(h[k:k + 2], 16) / 255.0, 4) for k in (0, 2, 4)) + (1.0,)


def gltf_materials(g, names) -> dict[str, int]:
    """Add the slots used (sorted) to a glTF document; their indices."""
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
