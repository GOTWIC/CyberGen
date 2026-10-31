"""The material library (scope 5.2, decisions 13.1 and 13.3: everything generated, shared by
every city, rebuilt only when its generator changes): `assetgen library [OUT]`.

- **Tileable sets** (`SETS`): per era the wall surfaces its facade systems use (concrete,
  plaster, brick, panel, cladding) and its roof, in the era's look (wear, bond, joints, board
  marks, profiles); the shared building surfaces (spandrel, trim, metals, patches, timber,
  stone, roof tiles, AG2's parts); the street surfaces (asphalt by class, paint, paving
  families, curbs, concrete, stone, steel, ballast, lawn, containers); AG8's prop surfaces
  (plastic, car paint, galvanized and rusty metal, bark, leaf clumps); AG13's ground cover
  (lawn, meadow and its dry wild form, dirt, mud, gravel, sand, moss, rubble). Each set is
  three maps (`pbr`): base color with height, normal, occlusion-roughness-metallic with the tint
  mask. A set covers `tile_m` meters at the texel density of its band: 512 px/m for what is
  within reach of the street, 256 px/m above (roofs), so its size is a power of two.
- **Atlases** (`atlases`, `interiors`): trim sheets per era, the decal atlas (grime, leaks,
  rust, graffiti, posters, stickers, cracks), the road atlas (stains, cracks, patches,
  manholes, drains, arrows), window interiors per use by day and by night, and a macro
  variation map that breaks up tiling over tens of meters.

`library.json` indexes it: per image its file, size, pixel sha256 and per set its tile size,
band, reference color (the mean of its tinted pixels, which a tint replaces) and generator
hash. A set whose hash (generator code, version, its parameters, the density) is unchanged
and whose files are there is kept, so a second run writes nothing.
"""

from __future__ import annotations

import hashlib
import json
import os
import time
from pathlib import Path

from .. import canon as C

LIB_VERSION = "ag6.2"
DENSITY = 512           # px/m within reach of the street (decision 13.4)
UPPER = 256             # px/m above it
MAX_WORKERS = 3
CODE = ("noise.py", "surfaces.py", "pbr.py", "library.py", "atlases.py", "interiors.py",
        "water_surfaces.py")


def default_root() -> Path:
    env = os.environ.get("ASSETGEN_LIBRARY")
    if env:
        return Path(env)
    return Path.home() / ".cache" / "cybergen" / "assetgen_library"


def code_hash() -> str:
    here = Path(__file__).resolve().parent
    h = hashlib.sha256(LIB_VERSION.encode())
    for name in CODE:
        p = here / name
        h.update(name.encode())
        h.update(p.read_bytes() if p.is_file() else b"")
    return h.hexdigest()


# --- eras ------------------------------------------------------------------------------------

# per era: wear, and the parameters of its wall surfaces and roof (colors are nominal: a
# building's tint replaces the tinted pixels' mean; joints, mortar and rust keep theirs)
ERA_LOOK: dict[str, dict] = {
    "heritage": {
        "wear": 0.8,
        "concrete": {"color": "#8f8a80"},
        "plaster": {"color": "#c9b89c", "coarse": 0.75},
        "brick": {"color": "#7a4a35", "bond": "english", "burnt": 0.7, "mortar": "#a59e90"},
        "panel": {"size_m": (1.0, 1.0), "aggregate": 0.6, "color": "#a49d90"},
        "cladding": {"profile": "corrugated", "color": "#7d776d"},
        "roof": {"kind": "tar", "color": "#3d3a36"},
    },
    "neon_retro": {
        "wear": 0.7,
        "concrete": {"color": "#8a8884", "joints": (1.0, 1.0), "ties": True},
        "plaster": {"color": "#b5aca0", "coarse": 0.4},
        "brick": {"color": "#6e4434", "burnt": 0.35},
        "panel": {"size_m": (1.0, 1.333), "aggregate": 0.25, "seal": "#262626",
                  "color": "#a7a39b"},
        "cladding": {"profile": "corrugated", "color": "#80878c"},
        "roof": {"kind": "gravel", "color": "#4a4846"},
    },
    "corporate_glass": {
        "wear": 0.15,
        "concrete": {"color": "#a8a7a2", "joints": (2.0, 1.0), "ties": True, "rough": 0.7},
        "plaster": {"color": "#c4c0b8", "coarse": 0.2},
        "brick": {"color": "#6a5146", "burnt": 0.1},
        "panel": {"size_m": (2.0, 1.0), "aggregate": 0.1, "metallic": 0.25, "rough": 0.55,
                  "color": "#b2b4b5"},
        "cladding": {"profile": "seam", "color": "#8b9298"},
        "roof": {"kind": "membrane", "color": "#8e8f8d"},
    },
    "brutalist": {
        "wear": 0.65,
        "concrete": {"color": "#8a8782", "boards": 0.12},
        "plaster": {"color": "#a9a59d", "coarse": 0.6},
        "brick": {"color": "#5e4436", "burnt": 0.5},
        "panel": {"size_m": (2.0, 1.333), "aggregate": 0.85, "color": "#9e9a91"},
        "cladding": {"profile": "trapezoid", "color": "#6c7176"},
        "roof": {"kind": "gravel", "color": "#555350"},
    },
    "industrial": {
        "wear": 0.9,
        "concrete": {"color": "#85827c", "joints": (4.0, 2.0)},
        "plaster": {"color": "#a39d92", "coarse": 0.7},
        "brick": {"color": "#6b3f2f", "burnt": 0.6},
        "panel": {"size_m": (4.0, 1.0), "aggregate": 0.4, "color": "#9a968e"},
        "cladding": {"profile": "trapezoid", "color": "#5c6670"},
        "roof": {"kind": "tar", "color": "#3a3a3a"},
    },
    "clean_tech": {
        "wear": 0.1,
        "concrete": {"color": "#b4b4b0", "rough": 0.65},
        "plaster": {"color": "#dcdcd6", "coarse": 0.15},
        "brick": {"color": "#8a7a70", "burnt": 0.05},
        "panel": {"size_m": (1.333, 2.0), "aggregate": 0.0, "metallic": 0.1, "rough": 0.45,
                  "color": "#d6dadc"},
        "cladding": {"profile": "seam", "color": "#b7c4cc"},
        "roof": {"kind": "membrane", "color": "#b8bab8"},
    },
    "suburban_modern": {
        "wear": 0.2,
        "concrete": {"color": "#a29e96"},
        "plaster": {"color": "#e3ddd2", "coarse": 0.5},
        "brick": {"color": "#8a5a45", "burnt": 0.15},
        "panel": {"size_m": (1.0, 1.0), "aggregate": 0.2, "color": "#c9c4ba"},
        "cladding": {"profile": "seam", "color": "#7f8a7e"},
        "roof": {"kind": "membrane", "color": "#6b6a66"},
    },
    "transit_modern": {
        "wear": 0.3,
        "concrete": {"color": "#9c9a95", "joints": (2.0, 2.0), "ties": True},
        "plaster": {"color": "#c8c4bc", "coarse": 0.3},
        "brick": {"color": "#704c3c", "burnt": 0.2},
        "panel": {"size_m": (2.0, 1.0), "aggregate": 0.15, "metallic": 0.3, "rough": 0.5,
                  "color": "#c4c8cc"},
        "cladding": {"profile": "trapezoid", "color": "#d0d4d8"},
        "roof": {"kind": "membrane", "color": "#7c7d7b"},
    },
    "mixed_modern": {
        "wear": 0.4,
        "concrete": {"color": "#8c8a86", "joints": (2.0, 1.0)},
        "plaster": {"color": "#c8c2b8", "coarse": 0.45},
        "brick": {"color": "#7a4a35", "burnt": 0.3},
        "panel": {"size_m": (2.0, 1.333), "aggregate": 0.3, "color": "#a9a59d"},
        "cladding": {"profile": "corrugated", "color": "#7f868c"},
        "roof": {"kind": "gravel", "color": "#4d4b47"},
    },
    "aerospace": {
        "wear": 0.3,
        "concrete": {"color": "#a5a39e", "joints": (4.0, 4.0)},
        "plaster": {"color": "#d4d4d0", "coarse": 0.25},
        "brick": {"color": "#7b5a4a", "burnt": 0.1},
        "panel": {"size_m": (4.0, 2.0), "aggregate": 0.0, "metallic": 0.4, "rough": 0.4,
                  "color": "#dfe2e4"},
        "cladding": {"profile": "trapezoid", "color": "#c4c9ce"},
        "roof": {"kind": "membrane", "color": "#c6c8c6"},
    },
}
ERAS = tuple(ERA_LOOK)
ERA_SURFACES = ("concrete", "plaster", "brick", "panel", "cladding", "roof")


def _era_sets() -> dict[str, dict]:
    out = {}
    for era, look in ERA_LOOK.items():
        w = look["wear"]
        c = look["concrete"]
        big = bool(c.get("joints")) and max(c["joints"]) > 2.0
        out[f"concrete_{era}"] = {"gen": "concrete", "tile_m": 4.0 if big else 2.0,
                                  "band": "street", "params": {"wear": w, **c}}
        out[f"plaster_{era}"] = {"gen": "plaster", "tile_m": 2.0, "band": "street",
                                 "params": {"wear": w, **look["plaster"]}}
        out[f"brick_{era}"] = {"gen": "brick", "tile_m": 2.0, "band": "street",
                               "params": {"wear": w, **look["brick"]}}
        out[f"panel_{era}"] = {"gen": "panel", "tile_m": 4.0, "band": "street",
                               "params": {"wear": w, **look["panel"]}}
        out[f"cladding_{era}"] = {"gen": "ribbed", "tile_m": 4.0, "band": "street",
                                  "params": {"wear": w, "metallic": 0.55, "sheet_m": 4.0,
                                             **look["cladding"]}}
        out[f"roof_{era}"] = {"gen": "roof", "tile_m": 4.0, "band": "upper",
                              "params": {"wear": w, **look["roof"]}}
    return out


# shared building surfaces (AG1's and AG2's other slots)
BUILDING_SETS: dict[str, dict] = {
    "spandrel": {"gen": "smooth_paint", "tile_m": 2.0, "band": "street",
                 "params": {"color": "#2a3440", "rough": 0.3, "metallic": 0.3, "wear": 0.1,
                            "under": "#20262c"}},
    "trim_paint": {"gen": "smooth_paint", "tile_m": 2.0, "band": "street",
                   "params": {"color": "#bdb6aa", "rough": 0.6, "wear": 0.35}},
    "structure": {"gen": "concrete", "tile_m": 2.0, "band": "street",
                  "params": {"color": "#77736d", "wear": 0.5}},
    "board_concrete": {"gen": "concrete", "tile_m": 2.0, "band": "street",
                       "params": {"color": "#8f8b84", "wear": 0.6, "boards": 0.15}},
    "stucco": {"gen": "plaster", "tile_m": 2.0, "band": "street",
               "params": {"color": "#d8cbb2", "wear": 0.4, "coarse": 0.95}},
    "metal_painted": {"gen": "smooth_paint", "tile_m": 2.0, "band": "street",
                      "params": {"color": "#6f757b", "rough": 0.5, "metallic": 0.5,
                                 "wear": 0.5, "under": "#5e3a26", "metal_under": True}},
    "metal_dark": {"gen": "smooth_paint", "tile_m": 2.0, "band": "street",
                   "params": {"color": "#2e3236", "rough": 0.55, "metallic": 0.7,
                              "wear": 0.4, "under": "#6b3b22", "metal_under": True}},
    "aluminum": {"gen": "brushed", "tile_m": 2.0, "band": "street",
                 "params": {"color": "#a8adb2", "rough": 0.35}},
    "louver": {"gen": "louver", "tile_m": 2.0, "band": "street",
               "params": {"color": "#3a3f45"}},
    "perforated": {"gen": "perforated", "tile_m": 2.0, "band": "street",
                   "params": {"color": "#d9dcde", "metallic": 0.6, "rough": 0.45}},
    "seam": {"gen": "ribbed", "tile_m": 4.0, "band": "street",
             "params": {"profile": "seam", "color": "#6e767d", "wear": 0.3, "sheet_m": 4.0}},
    "hangar": {"gen": "ribbed", "tile_m": 4.0, "band": "street",
               "params": {"profile": "trapezoid", "color": "#c4c9ce", "wear": 0.25,
                          "pitch_m": 0.333, "sheet_m": 4.0}},
    "patch_sheet": {"gen": "sheet", "tile_m": 2.0, "band": "street",
                    "params": {"color": "#8a8172", "wear": 0.7}},
    "patch_rust": {"gen": "ribbed", "tile_m": 4.0, "band": "street",
                   "params": {"profile": "corrugated", "color": "#8f4a2b", "wear": 1.0,
                              "sheet_m": 2.0, "metallic": 0.3}},
    "patch_tarp": {"gen": "fabric", "tile_m": 2.0, "band": "street",
                   "params": {"color": "#2f5f8a", "wear": 0.6}},
    "patch_panel": {"gen": "smooth_paint", "tile_m": 2.0, "band": "street",
                    "params": {"color": "#9a9a92", "rough": 0.7, "wear": 0.8,
                               "under": "#4d4a44"}},
    "plywood": {"gen": "wood", "tile_m": 4.0, "band": "street",
                "params": {"color": "#9c7a52", "wear": 0.6, "plywood": True,
                           "board_m": 1.333}},
    "timber": {"gen": "wood", "tile_m": 2.0, "band": "street",
               "params": {"color": "#4a3426", "wear": 0.3, "board_m": 0.14}},
    "shutter": {"gen": "wood", "tile_m": 2.0, "band": "street",
                "params": {"color": "#5f7a63", "wear": 0.5, "board_m": 0.08, "along": "u"}},
    "sill_stone": {"gen": "stone", "tile_m": 2.0, "band": "street",
                   "params": {"color": "#c7c0b2", "wear": 0.4}},
    "roof_tile": {"gen": "tiles", "tile_m": 2.0, "band": "street",   # (AG2's eaves, low)
                  "params": {"shape": "shingle", "size_m": (0.25, 0.2), "color": "#3b3f45",
                             "joint": "#22252a", "joint_m": 0.004, "tone": 0.25}},
    "pod": {"gen": "smooth_paint", "tile_m": 2.0, "band": "street",
            "params": {"color": "#c9c6bf", "rough": 0.4, "metallic": 0.1, "wear": 0.4}},
}

STREET_SETS: dict[str, dict] = {
    "asphalt_highway": {"gen": "asphalt", "tile_m": 4.0, "band": "street",
                        "params": {"color": "#26282c", "wear": 0.2}},
    "asphalt_avenue": {"gen": "asphalt", "tile_m": 4.0, "band": "street",
                       "params": {"color": "#2c2e33", "wear": 0.4}},
    "asphalt_street": {"gen": "asphalt", "tile_m": 4.0, "band": "street",
                       "params": {"color": "#323439", "wear": 0.6}},
    "asphalt_alley": {"gen": "asphalt", "tile_m": 4.0, "band": "street",
                      "params": {"color": "#3a3a3c", "wear": 0.95}},
    "asphalt_patch": {"gen": "asphalt", "tile_m": 2.0, "band": "street",
                      "params": {"color": "#1e1f22", "wear": 0.05}},
    "road_paint": {"gen": "smooth_paint", "tile_m": 2.0, "band": "street",
                   "params": {"color": "#d8d8d2", "rough": 0.6, "wear": 0.45,
                              "under": "#3a3b3e"}},
    "cast_iron": {"gen": "sheet", "tile_m": 1.0, "band": "street",
                  "params": {"color": "#3d3b38", "wear": 0.05, "sheet_m": 0.25,
                             "spangle": 0.3, "metallic": 0.8}},
    "tactile": {"gen": "tiles", "tile_m": 1.0, "band": "street",
                "params": {"shape": "cobble", "size_m": (0.05, 0.05), "color": "#c9a227",
                           "joint": "#a8871c", "wear": 0.4}},
    "grass": {"gen": "grass", "tile_m": 2.0, "band": "street",
              "params": {"color": "#3f5a2c"}},
    "paving_cobble": {"gen": "tiles", "tile_m": 2.0, "band": "street",
                      "params": {"shape": "cobble", "size_m": (0.12, 0.12),
                                 "color": "#5a5550", "joint": "#3b3835", "wear": 0.7}},
    "paving_tile": {"gen": "tiles", "tile_m": 2.0, "band": "street",
                    "params": {"size_m": (0.25, 0.25), "color": "#76726c", "wear": 0.6}},
    "paving_granite": {"gen": "tiles", "tile_m": 2.0, "band": "street",
                       "params": {"shape": "running", "size_m": (0.667, 0.333),
                                  "color": "#a7a6a1", "joint_m": 0.004, "tone": 0.08,
                                  "rough": 0.65, "wear": 0.2}},
    "paving_concrete_slab": {"gen": "tiles", "tile_m": 2.0, "band": "street",
                             "params": {"size_m": (0.667, 0.667), "color": "#8f8c86",
                                        "joint_m": 0.008, "tone": 0.12, "wear": 0.6}},
    "paving_concrete_cast": {"gen": "concrete", "tile_m": 4.0, "band": "street",
                             "params": {"color": "#86837c", "wear": 0.7,
                                        "joints": (2.0, 2.0)}},
    "paving_concrete_tile": {"gen": "tiles", "tile_m": 2.0, "band": "street",
                             "params": {"size_m": (0.333, 0.333), "color": "#9b968d",
                                        "bevel_m": 0.012, "wear": 0.5}},
    "paving_resin": {"gen": "plaster", "tile_m": 2.0, "band": "street",
                     "params": {"color": "#c4c2b8", "wear": 0.2, "coarse": 0.3}},
    "paving_brick": {"gen": "brick", "tile_m": 2.0, "band": "street",
                     "params": {"color": "#8a4f3c", "course_m": 0.1, "length_m": 0.2,
                                "joint_m": 0.005, "mortar": "#6e6a62", "wear": 0.4}},
    "paving_timber": {"gen": "wood", "tile_m": 2.0, "band": "street",
                      "params": {"color": "#6b5038", "wear": 0.6, "board_m": 0.14}},
    "curb_granite": {"gen": "stone", "tile_m": 2.0, "band": "street",
                     "params": {"color": "#8e8e8a", "block_m": (1.0, 2.0), "wear": 0.4,
                                "rough": 0.65}},
    "concrete_smooth": {"gen": "concrete", "tile_m": 2.0, "band": "street",
                        "params": {"color": "#8a8883", "wear": 0.5}},
    "concrete_formed": {"gen": "concrete", "tile_m": 4.0, "band": "street",
                        "params": {"color": "#7e7c77", "wear": 0.6, "joints": (4.0, 2.0),
                                   "ties": True}},
    "stone_blocks": {"gen": "stone", "tile_m": 2.0, "band": "street",
                     "params": {"color": "#6f6a62", "block_m": (0.667, 0.333), "wear": 0.7}},
    "stone_dressed": {"gen": "stone", "tile_m": 2.0, "band": "street",
                      "params": {"color": "#9c978d", "wear": 0.5}},
    "tile_glazed": {"gen": "tiles", "tile_m": 1.0, "band": "street",
                    "params": {"size_m": (0.15, 0.075), "shape": "running",
                               "color": "#c9c7bd", "joint": "#8d8a80", "rough": 0.25,
                               "joint_m": 0.003, "tone": 0.06, "wear": 0.5}},
    "steel_mill": {"gen": "brushed", "tile_m": 2.0, "band": "street",
                   "params": {"color": "#5d6166", "rough": 0.45}},
    "steel_painted": {"gen": "smooth_paint", "tile_m": 2.0, "band": "street",
                      "params": {"color": "#3f4a55", "rough": 0.55, "metallic": 0.6,
                                 "wear": 0.5, "under": "#6b3b22", "metal_under": True}},
    "ballast": {"gen": "gravel", "tile_m": 2.0, "band": "street",
                "params": {"color": "#4f4b47"}},
    "rubber": {"gen": "smooth_paint", "tile_m": 2.0, "band": "street",
               "params": {"color": "#1c1c1c", "rough": 0.9, "wear": 0.2}},
    "container": {"gen": "ribbed", "tile_m": 4.0, "band": "street",
                  "params": {"profile": "trapezoid", "color": "#8c2b22", "pitch_m": 0.286,
                             "wear": 0.6, "metallic": 0.4, "sheet_m": 4.0}},
    "tank_metal": {"gen": "sheet", "tile_m": 4.0, "band": "street",
                   "params": {"color": "#d9dad6", "wear": 0.3, "sheet_m": 2.0,
                              "spangle": 0.02, "metallic": 0.5}},
    "pad_concrete": {"gen": "concrete", "tile_m": 4.0, "band": "street",
                     "params": {"color": "#6a6964", "wear": 0.8, "joints": (4.0, 4.0)}},
}


# AG8's props and plants: plastics, car paint, galvanized and rusty metal, bark, and leaf
# clumps for the alpha-cut leaf cards (a card shows the whole tile: `leaves` is not tileable)
PROP_SETS: dict[str, dict] = {
    "plastic": {"gen": "smooth_paint", "tile_m": 1.0, "band": "street",
                "params": {"color": "#5a5e63", "rough": 0.55, "wear": 0.15,
                           "under": "#3a3a3a"}},
    "car_paint": {"gen": "smooth_paint", "tile_m": 2.0, "band": "street",
                  "params": {"color": "#8c9095", "rough": 0.22, "metallic": 0.45,
                             "wear": 0.08, "under": "#2a2a2a"}},
    "metal_galvanized": {"gen": "sheet", "tile_m": 1.0, "band": "street",
                         "params": {"color": "#8c9298", "wear": 0.25, "sheet_m": 1.0,
                                    "spangle": 0.5, "metallic": 0.85}},
    "metal_rusty": {"gen": "smooth_paint", "tile_m": 2.0, "band": "street",
                    "params": {"color": "#6e3a22", "rough": 0.8, "wear": 0.95,
                               "under": "#5a2e18", "metal_under": True}},
    "bark_furrowed": {"gen": "bark", "tile_m": 1.0, "band": "street",
                      "params": {"kind": "furrowed", "color": "#4a3a2e"}},
    "bark_smooth": {"gen": "bark", "tile_m": 1.0, "band": "street",
                    "params": {"kind": "smooth", "color": "#d8d4c8", "lichen": 0.1}},
    "bark_ringed": {"gen": "bark", "tile_m": 1.0, "band": "street",
                    "params": {"kind": "ringed", "color": "#7a6650", "lichen": 0.15}},
    "leaves_broad": {"gen": "leaves", "tile_m": 1.0, "band": "street",
                     "params": {"shape": "broad", "leaf_m": 0.13, "aspect": 0.5,
                                "twigs": 7, "per": 9}},
    "leaves_lobed": {"gen": "leaves", "tile_m": 1.0, "band": "street",
                     "params": {"shape": "lobed", "leaf_m": 0.13, "aspect": 0.75}},
    "leaves_fan": {"gen": "leaves", "tile_m": 1.0, "band": "street",
                   "params": {"shape": "fan", "leaf_m": 0.08, "aspect": 0.8,
                              "twigs": 7, "per": 8}},
    "leaves_needle": {"gen": "leaves", "tile_m": 1.0, "band": "street",
                      "params": {"shape": "needle", "leaf_m": 0.13, "aspect": 1.0,
                                 "twigs": 7, "per": 8, "rough": 0.7}},
    "leaves_small": {"gen": "leaves", "tile_m": 1.0, "band": "street",
                     "params": {"shape": "small", "leaf_m": 0.05, "aspect": 0.5,
                                "twigs": 10, "per": 12}},
}


# AG13's ground cover (M16's open land): lawn, meadow (and its dry, wild form), dirt, mud,
# gravel, sand, moss and rubble; the paving kinds take AG7's paving sets
GROUND_SETS: dict[str, dict] = {
    "ground_lawn": {"gen": "turf", "tile_m": 2.0, "band": "street",
                    "params": {"color": "#4f7a34", "stripe_m": 1.0, "bare": 0.25}},
    "ground_meadow": {"gen": "meadow", "tile_m": 2.0, "band": "street",
                      "params": {"color": "#6b8a3a", "dry": 0.3}},
    "ground_wild": {"gen": "meadow", "tile_m": 2.0, "band": "street",
                    "params": {"color": "#7d7a44", "dry": 0.85}},
    "ground_dirt": {"gen": "soil", "tile_m": 2.0, "band": "street",
                    "params": {"color": "#6a5038", "dry": 0.45, "trodden": 0.35}},
    "ground_mud": {"gen": "mud", "tile_m": 2.0, "band": "street",
                   "params": {"color": "#4a3a2b", "puddles": 0.6}},
    "ground_gravel": {"gen": "loose_gravel", "tile_m": 1.0, "band": "street",
                      "params": {"color": "#8a8378", "stone_m": 0.03, "oil": 0.2}},
    "ground_sand": {"gen": "sand", "tile_m": 2.0, "band": "street",
                    "params": {"color": "#d2bd8a", "ripple_m": 0.12}},
    "ground_moss": {"gen": "moss", "tile_m": 1.0, "band": "street",
                    "params": {"color": "#4d6a2a"}},
    "ground_rubble": {"gen": "rubble", "tile_m": 2.0, "band": "street",
                      "params": {"color": "#7f7c75", "chunk_m": 0.12, "brick": 0.25}},
# AG12's water beds (under the water: the upper band's density) and banks
WATER_SETS: dict[str, dict] = {
    "bed_mud": {"gen": "sediment", "tile_m": 4.0, "band": "upper",
                "params": {"kind": "mud", "color": "#4a4033", "shells": 0.3}},
    "bed_silt": {"gen": "sediment", "tile_m": 4.0, "band": "upper",
                 "params": {"kind": "silt", "color": "#5d5546", "bump": 6.0}},
    "bed_sand": {"gen": "sediment", "tile_m": 4.0, "band": "upper",
                 "params": {"kind": "sand", "color": "#9c8b68", "pebbles": 0.04,
                            "shells": 0.5, "rough": 0.85}},
    "bed_gravel": {"gen": "sediment", "tile_m": 4.0, "band": "upper",
                   "params": {"kind": "silt", "color": "#6f6a5f", "pebbles": 0.75}},
    "bed_stone": {"gen": "water_rubble", "tile_m": 4.0, "band": "upper",
                  "params": {"color": "#5f5d58", "stone_m": 0.3, "joint": "#3a362e",
                             "wet": 0.5}},
    "bank_soil": {"gen": "water_soil", "tile_m": 2.0, "band": "street",
                  "params": {"color": "#5d5440", "grass": "#4f6a35"}},
    "bank_rubble": {"gen": "water_rubble", "tile_m": 2.0, "band": "street",
                    "params": {"color": "#6d6a63", "stone_m": 0.22}},
    "bank_rock": {"gen": "stone", "tile_m": 1.0, "band": "street",
                  "params": {"color": "#77736b", "wear": 0.8, "rough": 0.85}},
}


def sets() -> dict[str, dict]:
    out = _era_sets()
    for d in (BUILDING_SETS, STREET_SETS, PROP_SETS, GROUND_SETS, WATER_SETS):
        for k, v in d.items():
            if k in out:
                raise ValueError(f"set {k} twice")
            out[k] = v
    for k, v in out.items():
        v["params"] = {"seed": _seed(k), **v["params"]}
    return dict(sorted(out.items()))


def _seed(name: str) -> int:
    from . import noise as N
    return N.seed_of("ag6.set", name) & 0x7FFFFFFF


def size_of(entry: dict, density: int) -> int:
    d = density if entry["band"] == "street" else density // 2
    return int(round(entry["tile_m"] * d))


# --- generation ------------------------------------------------------------------------------

def _set_job(job: dict) -> dict:
    from . import pbr as P
    from . import surfaces as S
    t = time.perf_counter()
    e = job["entry"]
    n = job["size"]
    s = S.make(e["gen"], n, e["tile_m"], dict(e["params"]))
    maps = P.pack(s, e["tile_m"])
    out = Path(job["dir"])
    files = {}
    for k, a in maps.items():
        f = f"sets/{job['name']}_{k}.png"
        P.save_png(out / f, a)
        files[k] = {"file": f, "size": [int(a.shape[1]), int(a.shape[0])],
                    "channels": int(a.shape[2]), "pixels_sha256": P.pixels_sha256(a)}
    return {"name": job["name"], "kind": "set", "hash": job["hash"], "files": files,
            "tile_m": e["tile_m"], "band": e["band"], "gen": e["gen"],
            "px_per_m": round(n / e["tile_m"], 3),
            "ref": P.ref_color(maps["base"], maps["orm"][:, :, 3]),
            "rough": P.mean_u8(maps["orm"][:, :, 1]),
            "seconds": round(time.perf_counter() - t, 2)}


def _atlas_job(job: dict) -> dict:
    from . import atlases as A
    t = time.perf_counter()
    rec = A.make(job["name"], job["dir"], job["density"])
    rec.update(name=job["name"], hash=job["hash"], seconds=round(time.perf_counter() - t, 2))
    return rec


def _run(fn, jobs, nw):
    if nw <= 1 or len(jobs) <= 1:
        for j in jobs:
            yield fn(j)
        return
    import multiprocessing as mp
    from concurrent.futures import ProcessPoolExecutor, as_completed
    with ProcessPoolExecutor(max_workers=nw, mp_context=mp.get_context("spawn")) as ex:
        futs = [ex.submit(fn, j) for j in jobs]
        for f in as_completed(futs):
            yield f.result()


def library_dir(root: str | Path | None = None, density: int = DENSITY) -> Path:
    return Path(root) if root else default_root() / f"d{density}"


def generate(out: str | Path | None = None, density: int = DENSITY,
             workers: int | None = None, only: list[str] | None = None, log=print) -> dict:
    """Make (or keep) every set and atlas in `out` (default: `default_root()/d<density>`);
    write `library.json`. Returns the index."""
    from . import atlases as A
    t0 = time.perf_counter()
    od = library_dir(out, density)
    od.mkdir(parents=True, exist_ok=True)
    idx_path = od / "library.json"
    old = {}
    if idx_path.is_file():
        try:
            old = json.loads(idx_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            old = {}
    ch = code_hash()
    S = sets()
    jobs, atl, keep = [], [], {}
    for name, e in S.items():
        if only and name not in only:
            continue
        h = C.digest([ch, density, name, e])[:16]
        o = (old.get("sets") or {}).get(name)
        if o and o.get("hash") == h and all((od / f["file"]).is_file()
                                             for f in o["files"].values()):
            keep[name] = o
            continue
        jobs.append({"name": name, "entry": e, "size": size_of(e, density), "hash": h,
                     "dir": str(od)})
    akeep = {}
    for name in A.ATLASES:
        if only and name not in only:
            continue
        h = C.digest([ch, density, name])[:16]
        o = (old.get("atlases") or {}).get(name)
        if o and o.get("hash") == h and all((od / f["file"]).is_file()
                                             for f in o["files"].values()):
            akeep[name] = o
            continue
        atl.append({"name": name, "density": density, "hash": h, "dir": str(od)})
    nw = max(1, min(workers or MAX_WORKERS, MAX_WORKERS))
    log(f"library: {len(jobs)} sets and {len(atl)} atlases to make, "
        f"{len(keep) + len(akeep)} kept, {nw} workers")
    made_sets = dict(keep)
    for r in _run(_set_job, sorted(jobs, key=lambda j: -j["size"]), nw):
        made_sets[r["name"]] = r
        log(f"  set {r['name']} {r['files']['base']['size'][0]} px {r['seconds']} s")
    made_atl = dict(akeep)
    for r in _run(_atlas_job, atl, nw):
        made_atl[r["name"]] = r
        log(f"  atlas {r['name']} {r['seconds']} s")
    if only:
        made_sets = {**(old.get("sets") or {}), **made_sets}
        made_atl = {**(old.get("atlases") or {}), **made_atl}
    idx = {"version": LIB_VERSION, "density_px_m": density, "upper_px_m": density // 2,
           "code_hash": ch,
           "sets": {k: made_sets[k] for k in sorted(made_sets)},
           "atlases": {k: made_atl[k] for k in sorted(made_atl)}}
    idx["hash"] = C.digest(_hashable(idx))[:16]
    from ..manifest import dumps, write_if_changed
    write_if_changed(idx_path, dumps(idx))
    idx["seconds"] = round(time.perf_counter() - t0, 1)
    idx["dir"] = str(od)
    return idx


def _hashable(idx: dict) -> dict:
    """What identifies the library's pixels (no timings)."""
    def strip(d):
        return {k: v for k, v in d.items() if k != "seconds"}
    return {"version": idx["version"], "density": idx["density_px_m"],
            "sets": {k: strip(v) for k, v in idx["sets"].items()},
            "atlases": {k: strip(v) for k, v in idx["atlases"].items()}}


def load(out: str | Path | None = None, density: int = DENSITY) -> dict | None:
    p = library_dir(out, density) / "library.json"
    if not p.is_file():
        return None
    idx = json.loads(p.read_text(encoding="utf-8"))
    idx["dir"] = str(p.parent)
    return idx


def disk(idx: dict) -> dict:
    """Bytes on disk (source PNGs) and the cooked estimate of section 11 (BC7 and BC5 at a
    byte per texel, mips 4/3)."""
    d = Path(idx["dir"])
    src = 0
    texels = 0
    for group in ("sets", "atlases"):
        for r in idx[group].values():
            for f in r["files"].values():
                p = d / f["file"]
                src += p.stat().st_size if p.is_file() else 0
                texels += f["size"][0] * f["size"][1]
    return {"source_bytes": src, "cooked_bytes": int(texels * 4 / 3), "texels": texels}
