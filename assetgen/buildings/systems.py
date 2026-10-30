"""Facade systems, type rules, articulation tables and material slots (scope 5.1.2, 5.2).

AG1 built six of the v1 systems; AG2 builds the rest, so every system an era or a spec
names is its own (`FALLBACK` only maps a name this table does not know). Each system fixes
which genes it reads and their ranges (`SYSTEMS`): window types, rhythms, the opening's
proportions, reveal depth, slab bands, cornice and parapet, its material slots, and (AG2)
its window frame styles, sills, balconies and its feature: the parts and articulation that
make it what it is (mullion caps, ribbons and sunshades, fins, diagrids, exoskeletons, egg
crates, shutters, timber frames, eaves, louver panels, capsule pods, screens, ribs).

Material slots are shared by every building of a city (one material instance each in
Unreal); per-building color comes from the genome as tints (glTF node extras, Custom
Primitive Data in Unreal: `CPD_TINT`, the six channels the exporter reads).
"""

from __future__ import annotations

from citygen import dmath as M

AG1_SYSTEMS = ("unitized_curtain_wall", "punched_concrete", "precast_panel", "punched_brick",
               "corrugated", "shanty_patchwork")
AG2_SYSTEMS = ("spandrel_ribbon", "fin_wall", "diagrid", "exoskeleton",
               "board_marked_concrete", "stucco_shutters", "timber_infill", "tiled_eaves",
               "standing_seam", "louvered_industrial", "capsule_stack", "perforated_skin",
               "hangar_cladding")
ALL_SYSTEMS = AG1_SYSTEMS + AG2_SYSTEMS

# a name no table here knows (an asset spec may name one) builds as the nearest system
FALLBACK: dict[str, str] = {}

CURTAIN = ("unitized_curtain_wall", "fin_wall", "diagrid", "exoskeleton", "spandrel_ribbon",
           "perforated_skin")
INDUSTRIAL = ("corrugated", "louvered_industrial", "hangar_cladding", "standing_seam")
# systems that need a size of building: (fewest floors, most floors, the stand-in outside)
FLOORS = {"diagrid": (10, 999, "fin_wall"), "exoskeleton": (6, 999, "fin_wall"),
          "capsule_stack": (4, 40, "precast_panel"), "tiled_eaves": (1, 6, "punched_brick"),
          "timber_infill": (2, 5, "stucco_shutters"), "shanty_patchwork": (1, 5,
                                                                         "precast_panel")}


def system(name: str) -> str:
    return name if name in SYSTEMS else FALLBACK.get(name, "punched_concrete")


def ag1_system(name: str) -> str:
    """Kept for AG1's callers: every system is built now."""
    return system(name)


# Ranges are [low, high] in meters (or ratios), drawn per building and quantized (`STEP`).
# sill and head are heights above the floor line; wwr is the opening's share of its bay.
# AG2: `frames` the window part styles (parts.gen_window), `sills` stone sills and lintels,
# `balconies` the balcony styles (with "none"), `feature` the system's own parts.
_GLASSY = {"cornices": ("none",), "parapets": ("none", "low"), "bands": ("none",),
           "ground": ("lobby", "storefront"), "frames": ("unit",), "sills": ("none",),
           "balconies": ("none",)}
SYSTEMS: dict[str, dict] = {
    "unitized_curtain_wall": {
        "wall": "spandrel", "glass": "glass",
        "windows": ("full", "split", "banded"), "rhythms": ("even", "grouped"),
        "wwr": (0.9, 0.95), "sill": (0.1, 0.8), "head_gap": (0.25, 0.55),
        "reveal": (0.06, 0.12), "corner": (0.12, 0.4), "bay_scale": (0.8, 1.1),
        **_GLASSY, "balconies": ("none", "glass"), "feature": "caps",
    },
    "punched_concrete": {
        "wall": "concrete", "finishes": ("concrete", "plaster"), "glass": "glass",
        "windows": ("single", "paired", "tall", "square", "wide"),
        "rhythms": ("even", "aba", "grouped"),
        "wwr": (0.3, 0.6), "sill": (0.75, 1.0), "head_gap": (0.45, 0.8),
        "reveal": (0.14, 0.26), "corner": (0.6, 1.4), "bay_scale": (0.9, 1.2),
        "cornices": ("none", "thin"), "parapets": ("low", "high"),
        "bands": ("none", "every", "alternate", "podium"),
        "ground": ("storefront", "raised", "lobby"),
        "frames": ("casement", "fixed", "awning"), "sills": ("none", "stone"),
        "balconies": ("none", "rail", "solid"), "feature": None,
    },
    "precast_panel": {
        "wall": "panel", "glass": "glass",
        "windows": ("single", "wide", "ribbon", "paired"), "rhythms": ("even", "grouped"),
        "wwr": (0.45, 0.75), "sill": (0.6, 0.9), "head_gap": (0.35, 0.6),
        "reveal": (0.1, 0.18), "corner": (0.4, 1.0), "bay_scale": (0.9, 1.2),
        "cornices": ("none",), "parapets": ("low", "high"),
        "bands": ("none", "every", "podium"),
        "ground": ("storefront", "raised", "lobby"),
        "frames": ("casement", "fixed", "awning"), "sills": ("none",),
        "balconies": ("none", "solid", "rail", "glass"), "feature": None,
    },
    "punched_brick": {
        "wall": "brick", "glass": "glass",
        "windows": ("single", "paired", "tall"), "rhythms": ("even", "aba"),
        "wwr": (0.28, 0.45), "sill": (0.8, 1.0), "head_gap": (0.35, 0.6),
        "reveal": (0.12, 0.22), "corner": (0.5, 1.2), "bay_scale": (0.9, 1.15),
        "cornices": ("thin", "deep"), "parapets": ("low", "high"),
        "bands": ("none", "every", "podium"),
        "ground": ("storefront", "raised"),
        "frames": ("sash", "casement"), "sills": ("stone",), "balconies": ("none",),
        "feature": None,
    },
    "corrugated": {
        "wall": "cladding", "glass": "glass",
        "windows": ("clerestory", "strip", "sparse"), "rhythms": ("even",),
        "wwr": (0.3, 0.8), "sill": (0.9, 1.2), "head_gap": (0.4, 0.7),
        "reveal": (0.05, 0.08), "corner": (0.3, 0.8), "bay_scale": (1.0, 1.0),
        "cornices": ("none",), "parapets": ("none", "low"), "bands": ("none",),
        "ground": ("raised", "blank"),
        "frames": ("industrial", "fixed"), "sills": ("none",), "balconies": ("none",),
        "feature": None,
    },
    "shanty_patchwork": {
        "wall": "patch_sheet", "glass": "glass",
        "windows": ("patch", "slit", "square"), "rhythms": ("irregular", "tight", "loose"),
        "wwr": (0.3, 0.55), "sill": (0.8, 1.1), "head_gap": (0.5, 0.9),
        "reveal": (0.04, 0.06), "corner": (0.15, 0.35), "bay_scale": (0.6, 0.9),
        "cornices": ("none",), "parapets": ("none",), "bands": ("none",),
        "ground": ("raised", "storefront"),
        "frames": ("fixed", "casement"), "sills": ("none",), "balconies": ("none",),
        "feature": "addons",
    },
    # -- AG2 --------------------------------------------------------------------------
    "spandrel_ribbon": {
        "wall": "band_panel", "glass": "glass",
        "windows": ("ribbon",), "rhythms": ("even",),
        "wwr": (0.9, 0.96), "sill": (0.8, 1.05), "head_gap": (0.35, 0.6),
        "reveal": (0.08, 0.14), "corner": (0.3, 0.8), "bay_scale": (0.8, 1.1),
        **_GLASSY, "parapets": ("low", "high"), "frames": ("ribbon",),
        "feature": "ribbon",
    },
    "fin_wall": {
        "wall": "spandrel", "glass": "glass",
        "windows": ("full", "split"), "rhythms": ("even", "grouped"),
        "wwr": (0.86, 0.94), "sill": (0.1, 0.7), "head_gap": (0.3, 0.55),
        "reveal": (0.06, 0.12), "corner": (0.2, 0.5), "bay_scale": (0.8, 1.1),
        **_GLASSY, "feature": "fins",
    },
    "diagrid": {
        "wall": "spandrel", "glass": "glass",
        "windows": ("full",), "rhythms": ("even",),
        "wwr": (0.9, 0.96), "sill": (0.1, 0.4), "head_gap": (0.3, 0.5),
        "reveal": (0.35, 0.6), "corner": (0.4, 0.9), "bay_scale": (0.8, 1.0),
        **_GLASSY, "feature": "diagrid",
    },
    "exoskeleton": {
        "wall": "spandrel", "glass": "glass",
        "windows": ("full", "split"), "rhythms": ("even",),
        "wwr": (0.88, 0.95), "sill": (0.1, 0.5), "head_gap": (0.3, 0.55),
        "reveal": (0.4, 0.65), "corner": (0.5, 1.0), "bay_scale": (0.9, 1.1),
        **_GLASSY, "feature": "exo",
    },
    "board_marked_concrete": {
        "wall": "board_concrete", "glass": "glass",
        "windows": ("single", "wide", "tall", "slot"), "rhythms": ("even", "aba", "grouped"),
        "wwr": (0.3, 0.55), "sill": (0.8, 1.0), "head_gap": (0.5, 0.9),
        "reveal": (0.25, 0.45), "corner": (0.8, 1.6), "bay_scale": (1.0, 1.3),
        "cornices": ("none",), "parapets": ("high",), "bands": ("none", "every"),
        "ground": ("raised", "lobby", "storefront"),
        "frames": ("fixed", "awning"), "sills": ("none",), "balconies": ("none", "solid"),
        "feature": "eggcrate",
    },
    "stucco_shutters": {
        "wall": "stucco", "glass": "glass",
        "windows": ("single", "tall", "paired"), "rhythms": ("even", "aba"),
        "wwr": (0.25, 0.4), "sill": (0.85, 1.0), "head_gap": (0.4, 0.6),
        "reveal": (0.1, 0.18), "corner": (0.6, 1.2), "bay_scale": (0.95, 1.2),
        "cornices": ("thin", "deep"), "parapets": ("low",), "bands": ("none", "podium"),
        "ground": ("storefront", "raised"),
        "frames": ("sash", "casement"), "sills": ("stone",),
        "balconies": ("none", "balconette"), "feature": "shutters",
    },
    "timber_infill": {
        "wall": "infill", "glass": "glass",
        "windows": ("single", "paired", "square"), "rhythms": ("even", "aba"),
        "wwr": (0.25, 0.4), "sill": (0.8, 1.0), "head_gap": (0.3, 0.5),
        "reveal": (0.06, 0.1), "corner": (0.25, 0.45), "bay_scale": (0.8, 1.0),
        "cornices": ("none", "thin"), "parapets": ("none", "low"), "bands": ("none",),
        "ground": ("storefront", "raised"),
        "frames": ("casement", "lattice"), "sills": ("none",), "balconies": ("none",),
        "feature": "timber",
    },
    "tiled_eaves": {
        "wall": "plaster", "glass": "glass",
        "windows": ("single", "wide", "paired"), "rhythms": ("even", "aba"),
        "wwr": (0.35, 0.6), "sill": (0.7, 0.95), "head_gap": (0.55, 0.8),
        "reveal": (0.06, 0.1), "corner": (0.3, 0.6), "bay_scale": (0.9, 1.1),
        "cornices": ("none",), "parapets": ("none", "low"), "bands": ("none",),
        "ground": ("storefront",),
        "frames": ("lattice", "casement"), "sills": ("none",), "balconies": ("none",),
        "feature": "eaves",
    },
    "standing_seam": {
        "wall": "seam", "glass": "glass",
        "windows": ("strip", "single", "ribbon"), "rhythms": ("even", "grouped"),
        "wwr": (0.4, 0.75), "sill": (0.9, 1.1), "head_gap": (0.4, 0.7),
        "reveal": (0.05, 0.09), "corner": (0.2, 0.5), "bay_scale": (1.0, 1.3),
        "cornices": ("none",), "parapets": ("none", "low"), "bands": ("every", "alternate"),
        "ground": ("raised", "storefront", "blank"),
        "frames": ("fixed", "industrial"), "sills": ("none",), "balconies": ("none",),
        "feature": None,
    },
    "louvered_industrial": {
        "wall": "cladding", "glass": "glass",
        "windows": ("louver", "clerestory", "sparse"), "rhythms": ("even",),
        "wwr": (0.5, 0.85), "sill": (1.2, 2.0), "head_gap": (0.4, 0.8),
        "reveal": (0.05, 0.1), "corner": (0.3, 0.7), "bay_scale": (1.0, 1.0),
        "cornices": ("none",), "parapets": ("none", "low"), "bands": ("none",),
        "ground": ("raised", "blank"),
        "frames": ("industrial",), "sills": ("none",), "balconies": ("none",),
        "feature": "louvers",
    },
    "capsule_stack": {
        "wall": "concrete", "glass": "glass",
        "windows": ("pod",), "rhythms": ("even", "tight"),
        "wwr": (0.85, 0.95), "sill": (0.05, 0.1), "head_gap": (0.05, 0.1),
        "reveal": (0.15, 0.25), "corner": (0.3, 0.7), "bay_scale": (0.8, 0.95),
        "cornices": ("none",), "parapets": ("low",), "bands": ("none",),
        "ground": ("storefront", "lobby"),
        "frames": ("fixed",), "sills": ("none",), "balconies": ("none",),
        "feature": "capsules",
    },
    "perforated_skin": {
        "wall": "panel", "glass": "glass",
        "windows": ("full", "wide", "ribbon"), "rhythms": ("even",),
        "wwr": (0.6, 0.85), "sill": (0.3, 0.8), "head_gap": (0.3, 0.5),
        "reveal": (0.06, 0.12), "corner": (0.3, 0.8), "bay_scale": (0.8, 1.1),
        **_GLASSY, "frames": ("unit", "fixed"), "feature": "screen",
    },
    "hangar_cladding": {
        "wall": "hangar", "glass": "glass",
        "windows": ("clerestory", "strip", "sparse"), "rhythms": ("even",),
        "wwr": (0.4, 0.8), "sill": (1.0, 1.5), "head_gap": (0.5, 0.9),
        "reveal": (0.05, 0.08), "corner": (0.6, 1.2), "bay_scale": (1.0, 1.0),
        "cornices": ("none",), "parapets": ("none", "low"), "bands": ("none",),
        "ground": ("raised", "blank"),
        "frames": ("industrial", "fixed"), "sills": ("none",), "balconies": ("none",),
        "feature": "ribs",
    },
}

PATCH_SLOTS = ("patch_sheet", "patch_rust", "patch_tarp", "patch_panel", "patch_ply")
# shanty patchwork: which patches a building is mostly made of (weights per PATCH_SLOTS)
PATCH_MIXES = {"sheet": (4, 1, 1, 1, 1), "rust": (1, 4, 1, 1, 1), "tarp": (1, 1, 4, 1, 1),
               "panel": (1, 1, 1, 4, 1), "ply": (1, 1, 1, 1, 4), "mixed": (1, 1, 1, 1, 1)}

# AG2 feature genes per system: discrete options the genome draws when the system has them
FEATURE_GENES = {
    "fins": {"fin_deg": (0, 0, 15, 30)},
    "ribbon": {"shade": ("none", "blade")},
    "diagrid": {"node_f": (2, 3, 4)},
    "exo": {"brace": ("none", "x", "alternate"), "node_f": (2, 3, 4)},
    "eggcrate": {"crate": ("none", "eggcrate")},
    "timber": {"pattern": ("posts", "braced", "cross")},
    "screen": {"blades": ("flat", "alternate", "wave")},
    "capsules": {"pods": ("single", "paired")},
}
BALCONY_USES = ("residential", "hotel")

# Massing articulation (scope pipeline stage 3) by era: weights of the corner cut (none,
# chamfer, round), of a setback ledge on towers, a podium canopy, an arcade under a
# cantilevered first floor, and the crown types AG2 builds (the rest are AG4's roofs).
ARTICULATION = {
    "corporate_glass": {"cut": (0.4, 0.25, 0.35), "setback": 0.5, "canopy": 0.6,
                        "arcade": 0.15},
    "clean_tech": {"cut": (0.4, 0.2, 0.4), "setback": 0.3, "canopy": 0.4, "arcade": 0.1},
    "brutalist": {"cut": (0.8, 0.2, 0.0), "setback": 0.4, "canopy": 0.2, "arcade": 0.4},
    "transit_modern": {"cut": (0.55, 0.15, 0.3), "setback": 0.2, "canopy": 0.6,
                       "arcade": 0.1},
    "mixed_modern": {"cut": (0.6, 0.25, 0.15), "setback": 0.35, "canopy": 0.3,
                     "arcade": 0.15},
    "neon_retro": {"cut": (0.75, 0.2, 0.05), "setback": 0.2, "canopy": 0.2, "arcade": 0.1},
    "heritage": {"cut": (0.85, 0.15, 0.0), "setback": 0.1, "canopy": 0.0, "arcade": 0.25},
    "industrial": {"cut": (1.0, 0.0, 0.0), "setback": 0.0, "canopy": 0.0, "arcade": 0.0},
    "suburban_modern": {"cut": (0.9, 0.1, 0.0), "setback": 0.1, "canopy": 0.1,
                        "arcade": 0.0},
    "aerospace": {"cut": (0.7, 0.0, 0.3), "setback": 0.1, "canopy": 0.3, "arcade": 0.0},
}
ARTICULATION_DEFAULT = {"cut": (0.7, 0.2, 0.1), "setback": 0.25, "canopy": 0.3,
                        "arcade": 0.1}
AG2_CROWNS = ("flat", "parapet", "lantern", "stepped", "halo", "mast", "spire")
# AG4's crowns: pitched (hip, gable, mansard), pagoda_roof, sawtooth, dome (a barrel vault),
# billboard_frame (an empty frame on the roof); `roofs.py`
AG4_CROWNS = ("pitched", "pagoda_roof", "sawtooth", "dome", "billboard_frame")

# AG4: roofs. Sheds and halls take a roof form of their own (gene `roof_form`, weights by
# type: sawtooth, gable, barrel, flat); the era's share of gables among its pitched roofs;
# the finish of its flat roofs (gravel, pavers, membrane); stone copings; pitch ranges
# (degrees) and eaves (m); the styles of roof equipment.
SHED_TYPES = ("building.shed", "building.warehouse", "building.hangar", "building.yard")
SHED_FORMS = {"building.shed": (("sawtooth", "gable", "barrel", "flat"), (0.3, 0.4, 0.1, 0.2)),
              "building.warehouse": (("sawtooth", "gable", "barrel", "flat"),
                                     (0.35, 0.35, 0.05, 0.25)),
              "building.hangar": (("barrel", "gable", "flat"), (0.6, 0.25, 0.15)),
              "building.yard": (("gable", "flat"), (0.4, 0.6))}
GABLE_SHARE = {"heritage": 0.55, "suburban_modern": 0.45}
ROOF_FINISHES = {
    "heritage": (0.2, 0.5, 0.1, 0.2), "neon_retro": (0.1, 0.35, 0.1, 0.45),
    "corporate_glass": (0.0, 0.3, 0.5, 0.2), "brutalist": (0.0, 0.6, 0.15, 0.25),
    "industrial": (0.0, 0.25, 0.0, 0.75), "clean_tech": (0.0, 0.25, 0.45, 0.3),
    "suburban_modern": (0.3, 0.35, 0.2, 0.15), "transit_modern": (0.0, 0.4, 0.25, 0.35),
    "mixed_modern": (0.05, 0.4, 0.25, 0.3), "aerospace": (0.0, 0.2, 0.1, 0.7),
}
ROOF_FINISH_NAMES = ("tile", "gravel", "pavers", "membrane")
STONE_COPING = ("heritage", "brutalist", "suburban_modern")
PITCH = {"heritage": (32.0, 45.0), "suburban_modern": (24.0, 36.0), "*": (18.0, 30.0)}
SHED_PITCH = (10.0, 18.0)
EAVE = {"heritage": (0.35, 0.55), "suburban_modern": (0.3, 0.5), "*": (0.2, 0.4)}
EQUIP_STYLES = {
    "ac": {"heritage": (("old", "fans"), (0.6, 0.4)), "neon_retro": (("old", "fans", "box"),
                                                                    (0.4, 0.4, 0.2)),
           "corporate_glass": (("box", "fans"), (0.8, 0.2)), "clean_tech": (("box",), None),
           "aerospace": (("box", "fans"), (0.6, 0.4)),
           "transit_modern": (("box", "fans"), (0.6, 0.4)),
           "*": (("fans", "box", "old"), (0.5, 0.3, 0.2))},
    "tank": {"heritage": (("timber", "steel"), (0.75, 0.25)),
             "neon_retro": (("timber", "steel", "panel"), (0.5, 0.3, 0.2)),
             "industrial": (("steel", "panel"), (0.7, 0.3)),
             "brutalist": (("steel", "panel"), (0.5, 0.5)),
             "suburban_modern": (("panel", "steel"), (0.6, 0.4)),
             "*": (("panel", "steel"), (0.6, 0.4))},
}

# Discrete-gene value lists the genome draws from when a system leaves them open.
CORNERS = ("plain", "heavy", "tight")
GLASS = ("#1b2430", "#22303a", "#1e2b26", "#2b251e", "#2a3440", "#15191d", "#283238")
ROOFS = ("#3d3d3d", "#4d4b47", "#5a5650", "#2f3133", "#6b6a66", "#544a40")
# AG2: roofs of the industrial systems (galvanized and coated metal, white membrane, tar)
ROOFS_INDUSTRIAL = ("#9ea3a7", "#c9ccc9", "#7a3e2c", "#4d5a66", "#3d3d3d", "#6b6a66", "#8a8f86")
STEP = {"bay_m": 0.05, "wwr": 0.01, "sill_m": 0.05, "head_m": 0.05, "reveal_m": 0.01,
        "corner_m": 0.05, "cornice_m": 0.05, "parapet_m": 0.05, "band_m": 0.01,
        "open_p": 0.05, "patch_w": 0.1, "patch_h": 0.1,
        "wear": 0.05, "dirt_m": 0.5, "neon": 0.05, "lit": 0.05, "wall_v": 0.02,
        "wall_w": 0.02, "trim_v": 0.02, "mech_every": 1, "seed": 0.0001}

# M3 types whose system is fixed (one name) or drawn from their own weights (else the era's).
TYPE_SYSTEM = {
    "building.shanty_stack": "shanty_patchwork",
    "building.warehouse": {"corrugated": 0.5, "louvered_industrial": 0.25,
                           "standing_seam": 0.25},
    "building.shed": {"corrugated": 0.6, "standing_seam": 0.4},
    "building.hangar": "hangar_cladding",
    "building.yard": "corrugated",
    "building.parking_structure": "punched_concrete",
    "building.temple_hall": {"punched_brick": 0.5, "tiled_eaves": 0.5},
    "building.pagoda": "tiled_eaves",
    "building.gate_house": "punched_brick",
    # AG5: a terminal's and a station's glass halls
    "building.terminal": {"unitized_curtain_wall": 0.5, "fin_wall": 0.3, "hangar_cladding": 0.2},
    "building.station": {"unitized_curtain_wall": 0.4, "fin_wall": 0.3, "punched_concrete": 0.3},
}
# AG5: a hero's facade system by its landmark kind (weights), drawn from its id
LANDMARK_SYSTEM = {
    "megatower": {"unitized_curtain_wall": 0.5, "fin_wall": 0.3, "diagrid": 0.2},
    "spire": {"fin_wall": 0.45, "unitized_curtain_wall": 0.35, "diagrid": 0.2},
    "arcology": {"exoskeleton": 0.4, "precast_panel": 0.35, "capsule_stack": 0.25},
}
# AG5: the families of complexes whose buildings are one design (twin towers: the same
# genes to the last step; the others step their continuous genes off the family's)
TWINS = ("twin_towers",)
NO_CURTAIN = ("building.villa", "building.terraced", "building.shopfront_row",
              "building.courtyard_block", "building.perimeter")
SHANTY_MAX_FLOORS = 5          # patchwork only on low buildings outside shanty stacks

# Mass roles: which of the genome's three systems a mass takes, or "structure" (blank).
ROLE_GROUP = {
    "podium": "base", "dock": "base", "hall": "base", "wing": "base", "platform": "base",
    "crown": "top", "roof_tier": "top", "cab": "top", "mechanical": "top",
    "spire": "structure", "mast": "structure", "deck": "structure", "span": "structure",
    "leg": "structure", "ramp": "structure",
    "void": "structure", "shaft": "structure",
}


def role_group(role: str) -> str:
    return ROLE_GROUP.get(role, "body")


# Material slots: master (spike's masters), preview color (sRGB), roughness, metallic, and
# which of the building's tints multiplies it (None: the slot's own color only).
SLOTS: dict[str, tuple] = {
    "concrete": ("facade", "#8c8a86", 0.85, 0.0, "wall"),
    "plaster": ("facade", "#b9ad9c", 0.9, 0.0, "wall"),
    "panel": ("facade", "#a9a59d", 0.8, 0.0, "wall"),
    "brick": ("facade", "#7a4a35", 0.9, 0.0, "wall"),
    "cladding": ("metal", "#7f868c", 0.55, 0.6, "wall"),
    "spandrel": ("facade", "#2a3440", 0.45, 0.3, "spandrel"),
    "patch_sheet": ("metal", "#8a8172", 0.7, 0.5, "patch"),
    "patch_rust": ("metal", "#8f4a2b", 0.8, 0.4, "patch"),
    "patch_tarp": ("facade", "#2f5f8a", 0.8, 0.0, "patch"),
    "patch_panel": ("facade", "#9a9a92", 0.8, 0.0, "patch"),
    "patch_ply": ("facade", "#9c7a52", 0.85, 0.0, "patch"),
    "trim": ("facade", "#bdb6aa", 0.75, 0.0, "trim"),
    "glass": ("glass", "#1b2430", 0.08, 0.0, "glass"),
    "storefront": ("glass", "#22303c", 0.06, 0.0, None),
    "louver": ("metal", "#3a3f45", 0.5, 0.8, None),
    "void": ("facade", "#0d0e10", 0.95, 0.0, None),
    "roof": ("facade", "#4d4b47", 0.95, 0.0, "roof"),
    "equipment": ("metal", "#6f757b", 0.5, 0.7, None),
    "structure": ("facade", "#77736d", 0.9, 0.0, "trim"),
    # AG2: walls of the new systems
    "band_panel": ("metal", "#c9c7c1", 0.45, 0.5, "wall"),
    "board_concrete": ("facade", "#8f8b84", 0.9, 0.0, "wall"),
    "stucco": ("facade", "#d8cbb2", 0.9, 0.0, "wall"),
    "infill": ("facade", "#e0d6c2", 0.9, 0.0, "wall"),
    "seam": ("metal", "#6e767d", 0.45, 0.65, "wall"),
    "hangar": ("metal", "#c4c9ce", 0.4, 0.6, "wall"),
    "dado": ("facade", "#a39f97", 0.9, 0.0, None),
    # AG2: parts
    "frame": ("metal", "#5d6166", 0.45, 0.6, "trim"),
    "sill": ("facade", "#c7c0b2", 0.8, 0.0, None),
    "mullion": ("metal", "#9aa1a8", 0.35, 0.8, "trim"),
    "spandrel_panel": ("facade", "#2a3440", 0.45, 0.3, "spandrel"),
    "balcony": ("facade", "#a7a39b", 0.85, 0.0, "wall"),
    "railing": ("metal", "#2e3236", 0.5, 0.7, None),
    "glazing": ("metal", "#33414c", 0.08, 0.3, "glass"),
    "fin": ("metal", "#b8bcc0", 0.4, 0.7, "trim"),
    "member": ("metal", "#d6d8da", 0.5, 0.4, "trim"),
    "timber": ("facade", "#4a3426", 0.85, 0.0, None),
    "shutter": ("facade", "#5f7a63", 0.75, 0.0, "trim"),
    "grille": ("metal", "#25282b", 0.6, 0.8, None),
    "perforated": ("metal", "#d9dcde", 0.5, 0.6, "trim"),
    "pod": ("facade", "#c9c6bf", 0.6, 0.1, "wall"),
    "ac": ("metal", "#b5b8b4", 0.6, 0.3, None),
    "dish": ("metal", "#dcdcd8", 0.5, 0.3, None),
    "tile": ("facade", "#3b3f45", 0.8, 0.0, "roof"),
    "canopy": ("metal", "#8a9096", 0.4, 0.7, "trim"),
    "mast": ("metal", "#a8adb2", 0.4, 0.8, None),
    "column": ("facade", "#8b8780", 0.85, 0.0, "trim"),
    "proxy": ("facade", "#8c8a86", 0.9, 0.0, "wall"),
    "proxy_roof": ("facade", "#4d4b47", 0.95, 0.0, "roof"),
    # AG3: street fronts (doors, docks, shutters, risers, mounts, painted surfaces)
    "storefront_dark": ("glass", "#0b0e12", 0.05, 0.0, None),
    "door_metal": ("metal", "#3b4046", 0.55, 0.6, None),
    "door_wood": ("facade", "#5a3b26", 0.7, 0.0, None),
    "step": ("facade", "#9c978d", 0.85, 0.0, None),
    "steel": ("metal", "#5d6166", 0.45, 0.8, None),
    "rubber": ("facade", "#1c1c1c", 0.9, 0.0, None),
    "seal": ("facade", "#22262a", 0.85, 0.0, None),
    "rollup": ("metal", "#8e9399", 0.5, 0.6, None),
    "rope": ("facade", "#7a1420", 0.8, 0.0, None),
    "stanchion": ("metal", "#b8a26a", 0.35, 0.9, None),
    "fascia": ("facade", "#bdb6aa", 0.7, 0.0, "trim"),
    "mount": ("metal", "#4a4f55", 0.5, 0.7, None),
    "trellis": ("metal", "#2f3a33", 0.6, 0.6, None),
    "pipe": ("metal", "#5b6168", 0.5, 0.6, "trim"),
    "cabinet": ("metal", "#15171a", 0.5, 0.4, None),
    "frosted": ("facade", "#d7dde0", 0.3, 0.0, None),
    "club": ("metal", "#16181c", 0.45, 0.5, None),
    "riser_tile": ("facade", "#3f5c63", 0.35, 0.0, None),
    "riser_stone": ("facade", "#a49d91", 0.8, 0.0, None),
    "riser_dark": ("facade", "#26292c", 0.5, 0.1, None),
    "lit_menu": ("neon", "#ffe7b8", 0.5, 0.0, None),
    "lit_white": ("neon", "#e8f4ff", 0.5, 0.0, None),
    # AG4: roof finishes and forms, roof equipment, green roofs, facade details, portals,
    # sky stations, courts and decks
    "roof_gravel": ("facade", "#6a6762", 0.95, 0.0, None),
    "roof_paver": ("facade", "#8f8c86", 0.85, 0.0, None),
    "roof_deck": ("facade", "#6b5038", 0.8, 0.0, None),
    "roof_walkway": ("facade", "#7f7c76", 0.85, 0.0, None),
    "roof_metal": ("metal", "#7a8086", 0.45, 0.6, "roof"),
    "coping": ("metal", "#9aa0a6", 0.4, 0.7, None),
    "coping_stone": ("facade", "#c7c0b2", 0.8, 0.0, None),
    "soffit": ("facade", "#bdb6aa", 0.8, 0.0, "trim"),
    "skylight": ("metal", "#2a3a48", 0.1, 0.4, None),
    "green_roof": ("foliage", "#4f7a3a", 0.95, 0.0, None),
    "soil": ("facade", "#4a3b2e", 0.95, 0.0, None),
    "equip_dark": ("metal", "#2b2f33", 0.6, 0.6, None),
    "equip_rust": ("metal", "#6e3a22", 0.8, 0.4, None),
    "equip_steel": ("metal", "#55595e", 0.5, 0.8, None),
    "tank_timber": ("facade", "#6b4a32", 0.85, 0.0, None),
    "tank_steel": ("metal", "#b9bcba", 0.5, 0.6, None),
    "tank_panel": ("facade", "#c9c6bc", 0.6, 0.1, None),
    "tank_roof": ("metal", "#3b3f45", 0.6, 0.5, None),
    "antenna": ("metal", "#c9ccce", 0.45, 0.8, None),
    "lamp_red": ("neon", "#ff2a1a", 0.5, 0.0, None),
    "lamp_green": ("neon", "#3dff6a", 0.5, 0.0, None),
    "lamp_amber": ("neon", "#ffb000", 0.5, 0.0, None),
    "lamp_white": ("neon", "#f2f6ff", 0.5, 0.0, None),
    "pad_deck": ("facade", "#5a5d61", 0.85, 0.0, None),
    "pad_paint_white": ("facade", "#e8e8e2", 0.6, 0.0, None),
    "pad_paint_yellow": ("facade", "#d9b21f", 0.6, 0.0, None),
    "roof_wall": ("facade", "#9a968e", 0.85, 0.0, None),
    "penthouse": ("facade", "#9a968e", 0.85, 0.0, "wall"),
    "escape": ("metal", "#1f2326", 0.6, 0.7, None),
    "duct": ("metal", "#9ea3a7", 0.5, 0.6, None),
    "cable": ("facade", "#141414", 0.7, 0.0, None),
    "camera": ("facade", "#d8dadc", 0.4, 0.0, None),
    "camera_lens": ("metal", "#0b0d10", 0.1, 0.5, None),
    "portal_lining": ("metal", "#aeb4ba", 0.35, 0.7, None),
    "portal_floor": ("facade", "#8d8c88", 0.7, 0.0, None),
    "platform": ("facade", "#a7a6a1", 0.65, 0.0, None),
    "platform_edge": ("facade", "#c9a227", 0.6, 0.0, None),
    "court_paving": ("facade", "#9b968d", 0.75, 0.0, None),
    "planter": ("facade", "#8a8883", 0.85, 0.0, None),
    # AG4: skybridges (pieces of their own, untinted: they carry no building's CPD)
    "bridge_deck": ("facade", "#85827c", 0.85, 0.0, None),
    "bridge_floor": ("facade", "#a7a6a1", 0.65, 0.0, None),
    "bridge_glass": ("glass", "#2a3a48", 0.06, 0.0, None),
    "bridge_frame": ("metal", "#a8adb2", 0.35, 0.8, None),
    "bridge_roof": ("metal", "#6f757b", 0.5, 0.6, None),
    "bridge_steel": ("metal", "#3f4a55", 0.55, 0.7, None),
    "bridge_rail": ("metal", "#2e3236", 0.5, 0.7, None),
    # AG5: slopes (stepped plinths, retaining skirts), the type generators and the heroes
    "plinth": ("facade", "#8f8b84", 0.9, 0.0, None),
    "retaining": ("facade", "#9a968e", 0.9, 0.0, None),
    "eave_tile": ("facade", "#3b3f45", 0.8, 0.0, "roof"),
    "eave_soffit": ("facade", "#7a3326", 0.8, 0.0, None),
    "lacquer": ("facade", "#8e1c16", 0.55, 0.0, None),
    "stone": ("facade", "#a49d91", 0.85, 0.0, None),
    "finial": ("metal", "#b8a26a", 0.35, 0.9, None),
    "hangar_door": ("metal", "#9aa1a8", 0.5, 0.6, "wall"),
    "dormer": ("facade", "#b9ad9c", 0.85, 0.0, "wall"),
    "tarp": ("facade", "#2f5f8a", 0.8, 0.0, "patch"),
    "shanty_roof": ("metal", "#7a5a40", 0.8, 0.4, "roof"),
    "pergola": ("facade", "#6b5038", 0.8, 0.0, None),
    "chimney": ("facade", "#7a4a35", 0.9, 0.0, None),
    "radome": ("facade", "#e8e8e2", 0.5, 0.0, None),
    "wheel_steel": ("metal", "#e8e8e2", 0.45, 0.6, "trim"),
    "gondola": ("metal", "#d8dadc", 0.4, 0.5, "trim"),
    "hero_frame": ("metal", "#2b2f33", 0.4, 0.8, "trim"),
    "hero_light": ("neon", "#ff2a6d", 0.5, 0.0, None),
    "halo_frame": ("metal", "#2b2f33", 0.4, 0.8, "trim"),
    "halo_light": ("neon", "#ff2a6d", 0.5, 0.0, None),
    "escape_rust": ("metal", "#5a3424", 0.8, 0.5, None),
    "atrium_glass": ("glass", "#2a3a48", 0.06, 0.0, None),
    "atrium_frame": ("metal", "#d6d8da", 0.4, 0.6, "trim"),
}
# AG3: a shopfront's paint (frame, fascia, riser, door) per unit, from its era's list
PAINTS = {"paint_red": "#7e1f1c", "paint_green": "#1f4a36", "paint_blue": "#1d3557",
          "paint_black": "#17191b", "paint_cream": "#d6cbb0", "paint_teal": "#1f6a66",
          "paint_ochre": "#b07e2a", "paint_white": "#e6e6e1", "paint_grey": "#5a5f65",
          "paint_wine": "#57202b", "paint_yellow": "#d9b21f", "paint_orange": "#c4561d"}
# neon tubes (bar frames, club lines), game screens, posters, murals and graffiti
NEONS = ("ff2a6d", "05d9e8", "b967ff", "ffb000", "39ff8a")
SCREENS = {"screen_blue": "#3a7bff", "screen_green": "#3dff9a", "screen_magenta": "#ff3df0"}
POSTERS = {"poster_a": "#d8452b", "poster_b": "#f2c230", "poster_c": "#2b7bd8",
           "poster_d": "#e9e4d8"}
MURALS = {"mural_a": "#c23b6b", "mural_b": "#2a8fa8", "mural_c": "#e0a43a",
          "mural_d": "#5b3fa6"}
GRAFFITI = {"graffiti_a": "#e8324f", "graffiti_b": "#36c8e8", "graffiti_c": "#f3e23a",
            "graffiti_d": "#7be84a", "graffiti_e": "#efefef"}
for _n, _c in PAINTS.items():
    SLOTS[_n] = ("metal", _c, 0.55, 0.3, None)
for _c in NEONS:
    SLOTS[f"neon_{_c}"] = ("neon", f"#{_c}", 0.5, 0.0, None)
for _d, _r in ((SCREENS, 0.4), (POSTERS, 0.7), (MURALS, 0.85), (GRAFFITI, 0.6)):
    for _n, _c in _d.items():
        SLOTS[_n] = ("neon" if _d is SCREENS else "facade", _c, _r, 0.0, None)
GLASS_SLOTS = ("glass", "storefront", "storefront_dark")   # UV1 and window ids only here

# AG3: street fronts by era: the frame of a shopfront (aluminum, painted, steel, timber),
# its riser (glazed tile, stone, dark, painted, the wall's own), the paints a unit draws,
# how often a shop has a roll-up shutter or a grille (times the district's danger), and the
# steps up to a main entrance (0, 1, 2)
FRONT = {
    "heritage": {"frame": (0.0, 0.5, 0.1, 0.4), "riser": (0.25, 0.35, 0.1, 0.2, 0.1),
                 "paints": ("paint_green", "paint_wine", "paint_black", "paint_cream",
                            "paint_blue", "paint_red", "paint_ochre"),
                 "shutter": 0.5, "steps": (0.3, 0.4, 0.3)},
    "neon_retro": {"frame": (0.3, 0.4, 0.3, 0.0), "riser": (0.35, 0.05, 0.35, 0.15, 0.1),
                   "paints": ("paint_black", "paint_red", "paint_teal", "paint_yellow",
                              "paint_wine", "paint_blue", "paint_orange"),
                   "shutter": 0.7, "steps": (0.7, 0.3, 0.0)},
    "corporate_glass": {"frame": (0.85, 0.1, 0.05, 0.0), "riser": (0.0, 0.5, 0.4, 0.0, 0.1),
                        "paints": ("paint_black", "paint_grey", "paint_white"),
                        "shutter": 0.15, "steps": (0.6, 0.3, 0.1)},
    "brutalist": {"frame": (0.3, 0.1, 0.6, 0.0), "riser": (0.0, 0.2, 0.3, 0.0, 0.5),
                  "paints": ("paint_grey", "paint_black", "paint_ochre", "paint_red"),
                  "shutter": 0.6, "steps": (0.5, 0.4, 0.1)},
    "industrial": {"frame": (0.2, 0.2, 0.6, 0.0), "riser": (0.0, 0.0, 0.4, 0.2, 0.4),
                   "paints": ("paint_grey", "paint_yellow", "paint_blue", "paint_black",
                              "paint_orange"),
                   "shutter": 0.8, "steps": (0.9, 0.1, 0.0)},
    "clean_tech": {"frame": (0.8, 0.2, 0.0, 0.0), "riser": (0.0, 0.3, 0.2, 0.4, 0.1),
                   "paints": ("paint_white", "paint_grey", "paint_teal"),
                   "shutter": 0.1, "steps": (0.8, 0.2, 0.0)},
    "suburban_modern": {"frame": (0.4, 0.5, 0.0, 0.1), "riser": (0.1, 0.3, 0.1, 0.4, 0.1),
                        "paints": ("paint_white", "paint_green", "paint_blue", "paint_cream",
                                   "paint_red"),
                        "shutter": 0.2, "steps": (0.5, 0.4, 0.1)},
    "transit_modern": {"frame": (0.7, 0.2, 0.1, 0.0), "riser": (0.1, 0.3, 0.4, 0.1, 0.1),
                       "paints": ("paint_grey", "paint_black", "paint_blue", "paint_white",
                                  "paint_teal"),
                       "shutter": 0.4, "steps": (0.8, 0.2, 0.0)},
    "mixed_modern": {"frame": (0.45, 0.35, 0.15, 0.05), "riser": (0.2, 0.25, 0.25, 0.2, 0.1),
                     "paints": ("paint_black", "paint_grey", "paint_red", "paint_green",
                                "paint_blue", "paint_teal", "paint_cream", "paint_wine"),
                     "shutter": 0.45, "steps": (0.6, 0.3, 0.1)},
    "aerospace": {"frame": (0.8, 0.0, 0.2, 0.0), "riser": (0.0, 0.2, 0.3, 0.3, 0.2),
                  "paints": ("paint_white", "paint_grey", "paint_orange"),
                  "shutter": 0.2, "steps": (0.9, 0.1, 0.0)},
}
FRONT_DEFAULT = FRONT["mixed_modern"]
FRAMES_FRONT = ("alu", "paint", "steel", "timber")
RISERS = ("riser_tile", "riser_stone", "riser_dark", "paint", "wall")

# Custom Primitive Data per actor (Unreal), extends AG0's 0 to 7: a tint triple per channel.
CPD_TINT = {"wall": 0, "trim": 8, "glass": 11, "roof": 14, "spandrel": 17, "patch": 20}
CPD_SIZE = 23
CPD_LAYOUT = {"0-2": "wall tint (linear RGB)", "3": "wear", "4": "dirt height (m)",
              "5": "neon level", "6": "lit-window ratio", "7": "seed",
              "8-10": "trim tint", "11-13": "glass tint", "14-16": "roof tint",
              "17-19": "spandrel tint", "20-22": "patch tint"}


def srgb_linear(rgb) -> list[float]:
    """sRGB (a hex string or three 0..1 values) to linear, to 1e-6 (dmath's power, the same
    bits everywhere)."""
    if isinstance(rgb, str):
        rgb = [int(rgb[1 + 2 * k:3 + 2 * k], 16) / 255.0 for k in range(3)]
    out = []
    for c in rgb:
        c = min(max(float(c), 0.0), 1.0)
        lin = c / 12.92 if c <= 0.04045 else float(M.power((c + 0.055) / 1.055, 2.4))
        out.append(round(lin, 6))
    return out
