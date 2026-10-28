"""Facade systems, type rules and material slots (scope 5.1.2, 5.2).

AG1 builds six of the v1 systems. Every other system an era or a spec names falls back to
the nearest of the six (`FALLBACK`) until AG2 adds it, so every era draws only from what is
built. Each system fixes which genes it reads and their ranges (`SYSTEMS`): window types,
rhythms, the opening's proportions, reveal depth, slab bands, cornice and parapet, and its
material slots.

Material slots are shared by every building of a city (one material instance each in
Unreal); per-building color comes from the genome as tints (glTF node extras, Custom
Primitive Data in Unreal: `CPD_TINT`).
"""

from __future__ import annotations

from citygen import dmath as M

AG1_SYSTEMS = ("unitized_curtain_wall", "punched_concrete", "precast_panel", "punched_brick",
               "corrugated", "shanty_patchwork")

# the rest of scope 5.1.2's systems, until AG2 builds them
FALLBACK = {
    "spandrel_ribbon": "unitized_curtain_wall",
    "fin_wall": "unitized_curtain_wall",
    "diagrid": "unitized_curtain_wall",
    "exoskeleton": "unitized_curtain_wall",
    "perforated_skin": "precast_panel",
    "capsule_stack": "precast_panel",
    "board_marked_concrete": "punched_concrete",
    "stucco_shutters": "punched_concrete",
    "timber_infill": "punched_brick",
    "tiled_eaves": "punched_brick",
    "standing_seam": "corrugated",
    "louvered_industrial": "corrugated",
    "hangar_cladding": "corrugated",
}


def ag1_system(name: str) -> str:
    return name if name in AG1_SYSTEMS else FALLBACK[name]


# Ranges are [low, high] in meters (or ratios), drawn per building and quantized (`STEP`).
# sill and head are heights above the floor line; wwr is the opening's share of its bay.
SYSTEMS: dict[str, dict] = {
    "unitized_curtain_wall": {
        "wall": "spandrel", "glass": "glass",
        "windows": ("full", "split", "banded"), "rhythms": ("even", "grouped"),
        "wwr": (0.9, 0.95), "sill": (0.1, 0.8), "head_gap": (0.25, 0.55),
        "reveal": (0.06, 0.12), "corner": (0.12, 0.4), "bay_scale": (0.8, 1.1),
        "cornices": ("none",), "parapets": ("none", "low"), "bands": ("none",),
        "ground": ("lobby", "storefront"),
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
    },
    "precast_panel": {
        "wall": "panel", "glass": "glass",
        "windows": ("single", "wide", "ribbon", "paired"), "rhythms": ("even", "grouped"),
        "wwr": (0.45, 0.75), "sill": (0.6, 0.9), "head_gap": (0.35, 0.6),
        "reveal": (0.1, 0.18), "corner": (0.4, 1.0), "bay_scale": (0.9, 1.2),
        "cornices": ("none",), "parapets": ("low", "high"),
        "bands": ("none", "every", "podium"),
        "ground": ("storefront", "raised", "lobby"),
    },
    "punched_brick": {
        "wall": "brick", "glass": "glass",
        "windows": ("single", "paired", "tall"), "rhythms": ("even", "aba"),
        "wwr": (0.28, 0.45), "sill": (0.8, 1.0), "head_gap": (0.35, 0.6),
        "reveal": (0.12, 0.22), "corner": (0.5, 1.2), "bay_scale": (0.9, 1.15),
        "cornices": ("thin", "deep"), "parapets": ("low", "high"),
        "bands": ("none", "every", "podium"),
        "ground": ("storefront", "raised"),
    },
    "corrugated": {
        "wall": "cladding", "glass": "glass",
        "windows": ("clerestory", "strip", "sparse"), "rhythms": ("even",),
        "wwr": (0.3, 0.8), "sill": (0.9, 1.2), "head_gap": (0.4, 0.7),
        "reveal": (0.05, 0.08), "corner": (0.3, 0.8), "bay_scale": (1.0, 1.0),
        "cornices": ("none",), "parapets": ("none", "low"), "bands": ("none",),
        "ground": ("raised", "blank"),
    },
    "shanty_patchwork": {
        "wall": "patch_sheet", "glass": "glass",
        "windows": ("patch", "slit", "square"), "rhythms": ("irregular", "tight", "loose"),
        "wwr": (0.3, 0.55), "sill": (0.8, 1.1), "head_gap": (0.5, 0.9),
        "reveal": (0.04, 0.06), "corner": (0.15, 0.35), "bay_scale": (0.6, 0.9),
        "cornices": ("none",), "parapets": ("none",), "bands": ("none",),
        "ground": ("raised", "storefront"),
    },
}

PATCH_SLOTS = ("patch_sheet", "patch_rust", "patch_tarp", "patch_panel", "patch_ply")
# shanty patchwork: which patches a building is mostly made of (weights per PATCH_SLOTS)
PATCH_MIXES = {"sheet": (4, 1, 1, 1, 1), "rust": (1, 4, 1, 1, 1), "tarp": (1, 1, 4, 1, 1),
               "panel": (1, 1, 1, 4, 1), "ply": (1, 1, 1, 1, 4), "mixed": (1, 1, 1, 1, 1)}

# Discrete-gene value lists the genome draws from when a system leaves them open.
CORNERS = ("plain", "heavy", "tight")
GLASS = ("#1b2430", "#22303a", "#1e2b26", "#2b251e", "#2a3440", "#15191d", "#283238")
ROOFS = ("#3d3d3d", "#4d4b47", "#5a5650", "#2f3133", "#6b6a66", "#544a40")
STEP = {"bay_m": 0.05, "wwr": 0.01, "sill_m": 0.05, "head_m": 0.05, "reveal_m": 0.01,
        "corner_m": 0.05, "cornice_m": 0.05, "parapet_m": 0.05, "band_m": 0.01,
        "open_p": 0.05, "patch_w": 0.1, "patch_h": 0.1,
        "wear": 0.05, "dirt_m": 0.5, "neon": 0.05, "lit": 0.05, "wall_v": 0.02,
        "wall_w": 0.02, "trim_v": 0.02, "mech_every": 1, "seed": 0.0001}

# M3 types with a fixed system (else the era's draw).
TYPE_SYSTEM = {
    "building.shanty_stack": "shanty_patchwork",
    "building.warehouse": "corrugated",
    "building.shed": "corrugated",
    "building.hangar": "corrugated",
    "building.yard": "corrugated",
    "building.parking_structure": "punched_concrete",
    "building.temple_hall": "punched_brick",
    "building.pagoda": "punched_brick",
    "building.gate_house": "punched_brick",
}
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
    "proxy": ("facade", "#8c8a86", 0.9, 0.0, "wall"),
    "proxy_roof": ("facade", "#4d4b47", 0.95, 0.0, "roof"),
}
GLASS_SLOTS = ("glass", "storefront")     # UV1 and vertex colors (window ids) only here

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
