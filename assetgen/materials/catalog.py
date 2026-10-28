"""Materials of a city (scope 5.2): which master and texture set each material slot of the
packs takes, with its parameters, the same in Unreal (`citygen/ue/import_city.py`) and in
Blender (`assetgen/blender/materials.py`).

Masters (AG6): `facade` (textured walls, roofs and trims: the set's base color with the
actor's tint over its tinted pixels, normal, occlusion-roughness-metallic, a dirt gradient
from the ground, rain streaks from the top, the macro map against tiling), `concrete` (the
same for street structures and paving, tinted by the slot's own color), `metal` (the same
with metallic from the set), `road` (asphalt and paint, with stains, cracks and patches from
the road atlas laid by a hash of each 8 m cell), `glass` (opaque, reflective, with interior
mapping from the interior atlases on the building's room grid, lit rooms at night), `neon`
(emissive tubes, the actor's neon level), `sign` (an atlas page, emissive), `decal` (the
decal atlas, deferred). AG1's and AG7's `opaque`, `emissive`, `translucent` and `foliage`
stay for what has no texture.

A material's color: where the set's tint mask is 1, the base color times tint / ref (ref:
the set's mean color there, so the tint replaces it); where 0 (mortar, joints, rust), the
base color as it is. The tint is the actor's Custom Primitive Data channel (buildings) or the
slot's own color (streets).

Era-varied slots (`ERA_SLOTS`: walls and roofs) have one material per era, keyed
`<slot>@<era>`; a building's entry maps its slots to its era's (`materials`).
"""

from __future__ import annotations

from ..buildings import systems as SY
from ..streets import materials as SM
from . import library as LB

ERA_SLOTS = {"concrete": "concrete", "plaster": "plaster", "brick": "brick", "panel": "panel",
             "cladding": "cladding", "roof": "roof", "proxy_roof": "roof"}
DEFAULT_ERA = "mixed_modern"

# building slots (AG1's and AG2's) to (master, set or None, scalars)
BUILDING: dict[str, tuple[str, str | None]] = {
    "spandrel": ("facade", "spandrel"), "spandrel_panel": ("facade", "spandrel"),
    "patch_sheet": ("metal", "patch_sheet"), "patch_rust": ("metal", "patch_rust"),
    "patch_tarp": ("facade", "patch_tarp"), "patch_panel": ("facade", "patch_panel"),
    "patch_ply": ("facade", "plywood"), "trim": ("facade", "trim_paint"),
    "glass": ("glass", None), "storefront": ("glass", None), "glazing": ("glass", None),
    "louver": ("metal", "louver"), "void": ("facade", None),
    "equipment": ("metal", "metal_painted"), "structure": ("facade", "structure"),
    "band_panel": ("metal", "panel_corporate_glass"), "board_concrete": ("facade",
                                                                          "board_concrete"),
    "stucco": ("facade", "stucco"), "infill": ("facade", "plaster_heritage"),
    "seam": ("metal", "seam"), "hangar": ("metal", "hangar"),
    "dado": ("facade", "structure"), "frame": ("metal", "metal_dark"),
    "sill": ("facade", "sill_stone"), "mullion": ("metal", "aluminum"),
    "balcony": ("facade", "structure"), "railing": ("metal", "metal_dark"),
    "fin": ("metal", "aluminum"), "member": ("metal", "metal_painted"),
    "timber": ("facade", "timber"), "shutter": ("facade", "shutter"),
    "grille": ("metal", "metal_dark"), "perforated": ("metal", "perforated"),
    "pod": ("facade", "pod"), "ac": ("metal", "metal_painted"),
    "dish": ("metal", "metal_painted"), "tile": ("facade", "roof_tile"),
    "canopy": ("metal", "aluminum"), "mast": ("metal", "aluminum"),
    "column": ("facade", "structure"), "proxy": ("facade", None),
}
INTERIOR_SHOP = 3              # the interior atlas row a storefront always shows

# street slots (AG7) to (master, set or None): asphalt by class, paint, paving by family
STREET: dict[str, tuple[str, str | None]] = {
    "asphalt.highway": ("road", "asphalt_highway"), "asphalt.avenue": ("road",
                                                                         "asphalt_avenue"),
    "asphalt.street": ("road", "asphalt_street"), "asphalt.alley": ("road", "asphalt_alley"),
    "asphalt.patch": ("road", "asphalt_patch"),
    "marking.white": ("road", "road_paint"), "marking.yellow": ("road", "road_paint"),
    "marking.red": ("road", "road_paint"),
    "manhole": ("metal", "cast_iron"), "grate": ("metal", "cast_iron"),
    "tactile": ("concrete", "tactile"), "lawn": ("foliage", "grass"),
    "curb.granite": ("concrete", "curb_granite"), "curb.concrete": ("concrete",
                                                                     "concrete_smooth"),
    "paving.cobble": ("concrete", "paving_cobble"), "paving.tile": ("concrete", "paving_tile"),
    "paving.granite": ("concrete", "paving_granite"),
    "paving.granite_dark": ("concrete", "paving_granite"),
    "paving.concrete_slab": ("concrete", "paving_concrete_slab"),
    "paving.concrete_cast": ("concrete", "paving_concrete_cast"),
    "paving.concrete_tile": ("concrete", "paving_concrete_tile"),
    "paving.resin": ("concrete", "paving_resin"), "paving.brick": ("concrete", "paving_brick"),
    "paving.timber": ("concrete", "paving_timber"),
    "concrete": ("concrete", "concrete_smooth"), "concrete.deck": ("concrete",
                                                                     "concrete_formed"),
    "concrete.barrier": ("concrete", "concrete_formed"),
    "concrete.column": ("concrete", "concrete_formed"),
    "concrete.dark": ("concrete", "concrete_smooth"),
    "stone.quay": ("concrete", "stone_blocks"), "stone.coping": ("concrete", "stone_dressed"),
    "stone.arch": ("concrete", "stone_blocks"), "tile.tunnel": ("concrete", "tile_glazed"),
    "steel": ("metal", "steel_mill"), "steel.painted": ("metal", "steel_painted"),
    "steel.red": ("metal", "steel_painted"), "steel.cable": ("metal", "steel_mill"),
    "steel.joint": ("metal", "steel_mill"), "rail": ("metal", "steel_mill"),
    "ballast": ("concrete", "ballast"), "sleeper": ("concrete", "concrete_smooth"),
    "rubber": ("concrete", "rubber"), "light": ("neon", None),
    "light.cool": ("neon", None), "glass.tube": ("translucent", None),
    "glass.panel": ("translucent", None), "glass.opaque": ("glass", None),
    "water.pond": ("opaque", None), "pitch": ("foliage", "grass"),
    "container.c0": ("metal", "container"), "container.c1": ("metal", "container"),
    "container.c2": ("metal", "container"), "container.c3": ("metal", "container"),
    "container.c4": ("metal", "container"), "container.c5": ("metal", "container"),
    "tank": ("metal", "tank_metal"), "pad": ("concrete", "pad_concrete"),
    "crane": ("metal", "steel_painted"),
}
TEXTURED = ("facade", "concrete", "metal", "road", "foliage")
MASTERS = ("facade", "glass", "metal", "concrete", "road", "neon", "sign", "decal",
           "opaque", "emissive", "translucent", "foliage")


def _master_of_building(slot: str) -> tuple[str, str | None]:
    if slot in ERA_SLOTS:
        surf = ERA_SLOTS[slot]
        master = "metal" if surf == "cladding" else "facade"
        return master, surf
    if slot in BUILDING:
        return BUILDING[slot]
    master = SY.SLOTS[slot][0] if slot in SY.SLOTS else "facade"
    return master, None


def set_for(slot: str, era: str | None, part: str = "buildings") -> tuple[str, str | None]:
    """(master, library set) of a slot (for an era-varied slot, in that era)."""
    if part == "streets":
        return STREET.get(slot, ("concrete", "concrete_smooth"))
    master, s = _master_of_building(slot)
    if slot in ERA_SLOTS:
        return master, f"{s}_{era or DEFAULT_ERA}"
    return master, s


def tex_name(set_name: str, kind: str) -> str:
    return f"set.{set_name}.{kind}"


def atlas_tex(name: str, kind: str) -> str:
    return f"atlas.{name}.{kind}"


SHARED = {  # the atlases every textured master reads
    "Macro": ("macro", "macro"), "Decals": ("decals", "base"), "RoadAtlas": ("road", "base"),
    "InteriorDay": ("interiors", "day"), "InteriorNight": ("interiors", "night"),
}


def material(slot: str, era: str | None, lib: dict, part: str = "buildings") -> dict:
    """The textured material record of a slot (and era): master, textures by parameter,
    scalars and vectors (the contribution's and the Blender preview's)."""
    master, s = set_for(slot, era, part)
    rec: dict = {"master": master, "textures": {}, "scalars": {}, "vectors": {}}
    if s is not None and s in lib["sets"]:
        st = lib["sets"][s]
        rec["textures"] = {"BaseTex": tex_name(s, "base"), "NormalTex": tex_name(s, "normal"),
                           "OrmTex": tex_name(s, "orm")}
        rec["scalars"]["TileM"] = st["tile_m"]
        rec["scalars"]["Textured"] = 1.0
        rec["vectors"]["RefColor"] = SY.srgb_linear(st["ref"])      # linear, as tints
        rec["set"] = s
    else:
        rec["scalars"]["Textured"] = 0.0
    if master in ("facade", "metal", "concrete", "road", "foliage", "glass"):
        rec["textures"]["Macro"] = atlas_tex("macro", "macro")
    if master in ("facade", "metal"):
        rec["textures"]["Decals"] = atlas_tex("decals", "base")
        rec["scalars"]["Streaks"] = 1.0 if part == "buildings" else 0.0
    if master == "road":
        rec["textures"]["RoadAtlas"] = atlas_tex("road", "base")
        rec["scalars"]["Stains"] = 0.0 if slot.startswith("marking") else 1.0
    if master == "glass":
        rec["textures"]["InteriorDay"] = atlas_tex("interiors", "day")
        rec["textures"]["InteriorNight"] = atlas_tex("interiors", "night")
        ia = lib["atlases"].get("interiors") or {}
        rec["scalars"].update(Interior=1.0 if part == "buildings" else 0.0,
                              InteriorCols=float((ia.get("grid") or [8, 6])[0]),
                              InteriorRows=float((ia.get("grid") or [8, 6])[1]),
                              InteriorBack=float(ia.get("back", 0.5)),
                              RowOverride=float(INTERIOR_SHOP) if slot == "storefront"
                              else -1.0)
    if master == "neon":
        rec["scalars"]["NeonStrength"] = 6.0
    return rec


def texture_table(names: set[str], lib: dict) -> dict[str, dict]:
    """The textures named (`set.<set>.<map>`, `atlas.<atlas>.<map>`): file (from the assets
    folder: `library/...`), pixel hash, color space and kind."""
    out = {}
    for t in sorted(names):
        kind, name, m = t.split(".", 2)
        rec = (lib["sets"] if kind == "set" else lib["atlases"])[name]["files"][m]
        tkind = "normal" if m == "normal" else ("color" if m in ("base", "day", "night")
                                                 else "mask")
        out[t] = {"file": f"library/{rec['file']}", "pixels_sha256": rec["pixels_sha256"],
                  "size": rec["size"], "srgb": tkind == "color", "kind": tkind}
    return out


def era_of_building(brief: dict) -> str:
    era = (brief.get("spec") or {}).get("era") or (brief["building"].get("style") or {}).get(
        "era")
    return era if era in LB.ERA_LOOK else DEFAULT_ERA
