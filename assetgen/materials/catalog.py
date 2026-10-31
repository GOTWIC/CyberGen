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

AG8's props, plants and signs (`PROP`, `prop_set`): their slots tinted by the slot's own
color as the streets', the leaf cards on `leaves` (the leaf clump tile, cut where it has no
leaf), sign faces on `sign` with the city's sign page (`page.<page>`), holo-ad screens on
`holo` with the holo ad page.

AG12's water (`WATER_SLOT`, `WATER`): a surface per water kind on `water` (Single Layer
Water in Unreal: the kind's scattering and absorption, so a clear sea deepens slowly and a
marsh goes murky within a meter; its flow speed, foam and the sea's waves; ripples and foam
from the water atlas), the beds on `bed` (their set, M16's material, with the water atlas's
caustics), the banks, walls and riprap stones on `concrete` with their sets.
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
    # AG3: street fronts (doors, docks, shutters, risers, fascias, mounts, painted surfaces)
    "storefront_dark": ("glass", None), "door_metal": ("metal", "metal_dark"),
    "door_wood": ("facade", "timber"), "step": ("facade", "stone_dressed"),
    "steel": ("metal", "steel_mill"), "rubber": ("facade", "rubber"),
    "seal": ("facade", "rubber"), "rollup": ("metal", "louver"), "rope": ("facade", None),
    "stanchion": ("metal", "aluminum"), "fascia": ("facade", "trim_paint"),
    "mount": ("metal", "metal_dark"), "trellis": ("metal", "metal_painted"),
    "pipe": ("metal", "metal_painted"), "cabinet": ("metal", "metal_dark"),
    "frosted": ("facade", None), "club": ("metal", "metal_dark"),
    "riser_tile": ("facade", "tile_glazed"), "riser_stone": ("facade", "stone_dressed"),
    "riser_dark": ("facade", "stone_dressed"), "lit_menu": ("neon", None),
    "lit_white": ("neon", None),
    # AG4: roofs, roof equipment, green roofs, facade details, portals, stations, courts,
    # decks and skybridges (all on the shared library's sets)
    "roof_gravel": ("facade", "ballast"), "roof_paver": ("facade", "paving_concrete_slab"),
    "roof_deck": ("facade", "paving_timber"), "roof_walkway": ("facade",
                                                                 "paving_concrete_tile"),
    "roof_metal": ("metal", "seam"), "coping": ("metal", "aluminum"),
    "coping_stone": ("facade", "sill_stone"), "soffit": ("facade", "trim_paint"),
    "skylight": ("metal", None), "green_roof": ("foliage", "grass"),
    "soil": ("facade", "ballast"), "equip_dark": ("metal", "metal_dark"),
    "equip_rust": ("metal", "metal_rusty"), "equip_steel": ("metal", "metal_galvanized"),
    "tank_timber": ("facade", "timber"), "tank_steel": ("metal", "tank_metal"),
    "tank_panel": ("facade", "plastic"), "tank_roof": ("metal", "metal_dark"),
    "antenna": ("metal", "metal_galvanized"), "lamp_red": ("neon", None),
    "lamp_green": ("neon", None), "lamp_amber": ("neon", None), "lamp_white": ("neon", None),
    "pad_deck": ("facade", "pad_concrete"), "pad_paint_white": ("facade", "road_paint"),
    "pad_paint_yellow": ("facade", "road_paint"), "roof_wall": ("facade", "structure"),
    "penthouse": ("facade", "structure"),
    "escape": ("metal", "metal_dark"), "duct": ("metal", "metal_galvanized"),
    "cable": ("facade", "rubber"), "camera": ("facade", "plastic"),
    "camera_lens": ("metal", None), "portal_lining": ("metal", "panel_corporate_glass"),
    "portal_floor": ("facade", "paving_granite"), "platform": ("facade", "paving_granite"),
    "platform_edge": ("facade", "tactile"), "court_paving": ("facade", "paving_tile"),
    "planter": ("facade", "concrete_formed"), "bridge_deck": ("facade", "concrete_formed"),
    "bridge_floor": ("facade", "paving_granite"), "bridge_glass": ("glass", None),
    "bridge_frame": ("metal", "aluminum"), "bridge_roof": ("metal", "seam"),
    "bridge_steel": ("metal", "steel_painted"), "bridge_rail": ("metal", "metal_dark"),
    # AG5: stepped plinths and retaining skirts on slopes, the type generators' and the
    # heroes' parts
    "plinth": ("facade", "board_concrete"), "retaining": ("facade", "concrete_formed"),
    "eave_tile": ("facade", "roof_tile"), "eave_soffit": ("facade", "timber"),
    "lacquer": ("metal", "metal_painted"), "stone": ("facade", "stone_dressed"),
    "finial": ("metal", "aluminum"), "hangar_door": ("metal", "hangar"),
    "dormer": ("facade", "plaster_heritage"), "tarp": ("facade", "patch_tarp"),
    "shanty_roof": ("metal", "metal_rusty"), "pergola": ("facade", "timber"),
    "chimney": ("facade", "brick_heritage"), "radome": ("facade", "plastic"),
    "wheel_steel": ("metal", "steel_painted"), "gondola": ("metal", "aluminum"),
    "hero_frame": ("metal", "metal_dark"), "hero_light": ("neon", None),
    "halo_frame": ("metal", "metal_dark"), "halo_light": ("neon", None),
    "terrace_planter": ("facade", "concrete_formed"), "terrace_green": ("foliage", "grass"),
    "terrace_soil": ("facade", "ballast"),
    "escape_rust": ("metal", "metal_rusty"), "atrium_glass": ("glass", None),
    "atrium_frame": ("metal", "aluminum"),
}
for _s in SY.SLOTS:
    if _s.startswith("paint_"):
        BUILDING[_s] = ("metal", "metal_painted")
    elif _s.startswith(("neon_", "screen_")):
        BUILDING[_s] = ("neon", None)
    elif _s.startswith(("poster_", "graffiti_")):
        BUILDING[_s] = ("facade", None)
    elif _s.startswith("mural_"):
        BUILDING[_s] = ("facade", "stucco")
INTERIOR_SHOP = 3              # the interior atlas row a storefront always shows
DECAL_PREFIX = "decal."        # AG3's decal slots, one per cell of the decal atlas
INTERIOR_BAR = 4               # and a bar's dark glazing (AG3: the club row)

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
    "concrete.soffit": ("concrete", "concrete_formed"),
    "concrete.fascia": ("concrete", "concrete_smooth"), "stain": ("concrete", "concrete_smooth"),
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
# AG8's prop and plant slots (`assetgen/props/materials.py`) to (master, set or None); a
# slot's darker tone (`<slot>.d`) takes its slot's; neon tubes (`neon.<hex>`) and lit faces
# (`lit.<hex>`) glow untextured; sign faces show the city's sign pages (`page.<page>`,
# master `sign`; `holopage.<page>`, master `holo`: AG6's ad pages on AG8's meshes)
PAINTED = ("metal.dark", "metal.black", "metal.green", "metal.yellow", "metal.red",
           "metal.blue", "metal.white", "sign.box", "sign.frame", "holo.base")
PROP: dict[str, tuple[str, str | None]] = {
    **{k: ("metal", "metal_painted") for k in PAINTED},
    "metal.galv": ("metal", "metal_galvanized"), "metal.steel": ("metal", "steel_mill"),
    "metal.chrome": ("metal", "aluminum"), "metal.bronze": ("metal", "aluminum"),
    "metal.rust": ("metal", "metal_rusty"),
    "concrete": ("concrete", "concrete_smooth"), "concrete.dark": ("concrete",
                                                                     "concrete_smooth"),
    "stone": ("concrete", "stone_dressed"), "soil": ("concrete", "ballast"),
    "wood": ("concrete", "timber"), "wood.light": ("concrete", "timber"),
    "wood.red": ("concrete", "timber"), "cardboard": ("concrete", "plywood"),
    "rubber": ("concrete", "rubber"), "bag.black": ("concrete", "plastic"),
    "paint.white": ("concrete", "trim_paint"), "net.debris": ("metal", "perforated"),
    "sign.face": ("concrete", "plastic"), "sign.back": ("concrete", "plastic"),
    "glass.prop": ("metal", None), "glass.dark": ("metal", None),
    "bark.dark": ("concrete", "bark_furrowed"), "bark.grey": ("concrete", "bark_furrowed"),
    "bark.plane": ("concrete", "bark_furrowed"), "bark.ginkgo": ("concrete",
                                                                 "bark_furrowed"),
    "bark.birch": ("concrete", "bark_smooth"), "bark.palm": ("concrete", "bark_ringed"),
    "leaf.plane": ("leaves", "leaves_lobed"), "leaf.maple": ("leaves", "leaves_lobed"),
    "leaf.oak": ("leaves", "leaves_lobed"), "leaf.ginkgo": ("leaves", "leaves_fan"),
    "leaf.birch": ("leaves", "leaves_broad"), "leaf.linden": ("leaves", "leaves_broad"),
    "leaf.elm": ("leaves", "leaves_broad"), "leaf.ficus": ("leaves", "leaves_broad"),
    "leaf.ivy": ("leaves", "leaves_broad"), "leaf.pine": ("leaves", "leaves_needle"),
    "leaf.boxwood": ("leaves", "leaves_small"),
    "sign.white": ("neon", None), "billboard.lamp": ("emissive", None),
}
PROP_PREFIX: dict[str, tuple[str, str | None]] = {
    "plastic": ("concrete", "plastic"), "fabric": ("concrete", "patch_tarp"),
    "car": ("metal", "car_paint"), "hull": ("concrete", "pod"),
    "foliage": ("foliage", "grass"), "light": ("emissive", None),
    "screen": ("emissive", None), "neon": ("neon", None), "lit": ("emissive", None),
    "holo": ("holo", None), "page": ("sign", None), "holopage": ("holo", None),
}
# AG12's water slots (`assetgen/water/materials.py`) to (master, set or None); the
# surfaces' `water.<kind>` on `water` with the kind's `WATER` parameters
WATER_SLOT: dict[str, tuple[str, str | None]] = {
    "bed.silt": ("bed", "bed_silt"), "bed.mud": ("bed", "bed_mud"),
    "bed.sand": ("bed", "bed_sand"), "bed.gravel": ("bed", "bed_gravel"),
    "bed.stone": ("bed", "bed_stone"),
    "bank.natural_bank": ("concrete", "bank_soil"), "bank.beach": ("concrete", "bed_sand"),
    "bank.marsh_edge": ("concrete", "bed_mud"), "bank.riprap": ("concrete", "bank_rubble"),
    "bank.road_embankment": ("concrete", "stone_blocks"),
    "wall.stone": ("concrete", "stone_blocks"), "wall.coping": ("concrete", "stone_dressed"),
    "stone.riprap": ("concrete", "bank_rock"),
}
# per water kind: `scatter` and `absorb` (linear RGB; Single Layer Water's coefficients per
# meter: the water's own color, and how fast each channel fades, red first), `shallow` and
# `deep` (linear RGB: the color over a shallow and a deep bed, the previews'), `clarity_m`
# (how far one sees into it), `flow` (the ripples' speed over M16's current), `foam` (the
# vertex foam's strength), `waves_m` and `wave_length_m` (the open sea's swell; M16's
# exposure weighs it per vertex), `ripple_m` (the ripple normals' tile)
WATER: dict[str, dict] = {
    "sea": {"scatter": [0.02, 0.07, 0.08], "absorb": [0.45, 0.11, 0.08],
            "shallow": [0.16, 0.36, 0.36], "deep": [0.02, 0.075, 0.095], "clarity_m": 6.0,
            "flow": 1.0, "foam": 1.0, "waves_m": 0.55, "wave_length_m": 26.0,
            "ripple_m": 8.0},
    "river": {"scatter": [0.035, 0.06, 0.045], "absorb": [0.65, 0.3, 0.3],
              "shallow": [0.2, 0.28, 0.2], "deep": [0.035, 0.06, 0.045], "clarity_m": 2.5,
              "flow": 1.0, "foam": 0.7, "waves_m": 0.0, "wave_length_m": 26.0,
              "ripple_m": 6.0},
    "canal": {"scatter": [0.03, 0.055, 0.045], "absorb": [0.75, 0.35, 0.35],
              "shallow": [0.17, 0.25, 0.2], "deep": [0.035, 0.06, 0.05], "clarity_m": 2.0,
              "flow": 1.0, "foam": 0.5, "waves_m": 0.0, "wave_length_m": 26.0,
              "ripple_m": 5.0},
    "ornamental": {"scatter": [0.04, 0.11, 0.13], "absorb": [0.28, 0.07, 0.05],
                   "shallow": [0.3, 0.55, 0.55], "deep": [0.04, 0.12, 0.15],
                   "clarity_m": 10.0, "flow": 0.3, "foam": 0.2, "waves_m": 0.0,
                   "wave_length_m": 26.0, "ripple_m": 4.0},
    "marsh": {"scatter": [0.05, 0.05, 0.02], "absorb": [1.1, 0.7, 0.9],
              "shallow": [0.18, 0.18, 0.08], "deep": [0.03, 0.035, 0.015], "clarity_m": 0.8,
              "flow": 0.6, "foam": 0.3, "waves_m": 0.0, "wave_length_m": 26.0,
              "ripple_m": 5.0},
}
TEXTURED = ("facade", "concrete", "metal", "road", "foliage", "leaves", "bed")
MASTERS = ("facade", "glass", "metal", "concrete", "road", "neon", "sign", "decal",
           "opaque", "emissive", "translucent", "foliage", "leaves", "holo", "water", "bed")


def _master_of_building(slot: str) -> tuple[str, str | None]:
    if slot.startswith(DECAL_PREFIX):
        return "decal", None                   # (AG3's mesh decals: a cell of the atlas)
    if slot in ERA_SLOTS:
        surf = ERA_SLOTS[slot]
        master = "metal" if surf == "cladding" else "facade"
        return master, surf
    if slot in BUILDING:
        return BUILDING[slot]
    master = SY.SLOTS[slot][0] if slot in SY.SLOTS else "facade"
    return master, None


def prop_set(slot: str) -> tuple[str, str | None]:
    """(master, library set) of an AG8 prop, plant or sign slot."""
    if slot.endswith(".d"):
        slot = slot[:-2]
    if slot in PROP:
        return PROP[slot]
    pre = slot.split(".", 1)[0]
    return PROP_PREFIX.get(pre, ("concrete", "concrete_smooth"))


def set_for(slot: str, era: str | None, part: str = "buildings") -> tuple[str, str | None]:
    """(master, library set) of a slot (for an era-varied slot, in that era); AG4's
    `connections` (skybridges) read the building table."""
    if part == "streets":
        return STREET.get(slot, ("concrete", "concrete_smooth"))
    if part == "water":
        if slot.startswith("water."):
            return "water", None
        return WATER_SLOT.get(slot, ("concrete", "concrete_smooth"))
    if part in ("props", "signs"):
        return prop_set(slot)
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
    if master == "water":
        w = WATER[slot.split(".", 1)[1]]
        rec["textures"] = {"NormalTex": atlas_tex("water", "normal"),
                           "FoamTex": atlas_tex("water", "foam")}
        rec["scalars"] = {"Clarity": w["clarity_m"], "FlowScale": w["flow"],
                          "FoamAmount": w["foam"], "WaveHeight": w["waves_m"],
                          "WaveLength": w["wave_length_m"], "RippleTileM": w["ripple_m"]}
        rec["vectors"] = {k.capitalize(): list(w[k]) for k in ("scatter", "absorb",
                                                                "shallow", "deep")}
        return rec
    if master == "decal":
        from .atlases import DECAL_CELLS
        rec["textures"] = {"BaseTex": atlas_tex("decals", "base"),
                           "NormalTex": atlas_tex("decals", "normal"),
                           "OrmTex": atlas_tex("decals", "orm")}
        rec["scalars"] = {"Cell": float(DECAL_CELLS.index(slot[len(DECAL_PREFIX):])),
                          "Cols": 4.0, "Rows": 4.0}
        return rec
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
    if master in ("facade", "metal", "concrete", "road", "foliage", "glass", "bed"):
        rec["textures"]["Macro"] = atlas_tex("macro", "macro")
    if master == "bed":
        rec["textures"]["Caustics"] = atlas_tex("water", "caustics")   # (AG12)
        rec["scalars"]["CausticTileM"] = 3.0
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
                              else (float(INTERIOR_BAR) if slot == "storefront_dark"
                                    else -1.0))
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
