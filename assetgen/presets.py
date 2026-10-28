"""Era presets (scope 4.2): what an asset spec leaves out comes from here.

citygen gives every building one era by its district archetype (`Building.style.era`). Each
era names the facade systems it draws from (weights), a palette, crown and roof types,
signage scripts, and ranges for a few continuous genes. An asset spec may replace any field
of any era; the rest stays as here.
"""

from __future__ import annotations

ERAS = ("heritage", "neon_retro", "corporate_glass", "brutalist", "industrial", "clean_tech",
        "suburban_modern", "transit_modern", "mixed_modern", "aerospace")

# The v1 facade systems (scope 5.1.2). AG1 builds the first six (marked), AG2 the rest.
FACADE_SYSTEMS = (
    "unitized_curtain_wall",    # AG1
    "spandrel_ribbon",
    "fin_wall",
    "diagrid",
    "exoskeleton",
    "punched_concrete",         # AG1
    "precast_panel",            # AG1
    "board_marked_concrete",
    "punched_brick",            # AG1
    "stucco_shutters",
    "timber_infill",
    "tiled_eaves",
    "corrugated",               # AG1
    "standing_seam",
    "louvered_industrial",
    "shanty_patchwork",         # AG1
    "capsule_stack",
    "perforated_skin",
    "hangar_cladding",
)

CROWNS = ("flat", "parapet", "lantern", "halo", "mast", "spire", "stepped", "pitched",
          "pagoda_roof", "sawtooth", "dome", "billboard_frame")

SCRIPTS = ("latin", "hanzi", "hangul", "kana", "cyrillic", "devanagari")

ERA_PRESETS: dict[str, dict] = {
    "heritage": {
        "systems": {"punched_brick": 0.4, "stucco_shutters": 0.3, "timber_infill": 0.1,
                    "tiled_eaves": 0.2},
        "palette": ["#7a4a35", "#b9a58c", "#3d3a36", "#8c2f2b", "#d8cbb3"],
        "crowns": ["pitched", "pagoda_roof", "parapet"],
        "signage_scripts": {"hanzi": 0.5, "latin": 0.3, "hangul": 0.2},
        "window_to_wall": [0.2, 0.35], "bay_m": [2.4, 3.6], "wear": 0.8,
    },
    "neon_retro": {
        "systems": {"precast_panel": 0.3, "punched_concrete": 0.25, "standing_seam": 0.15,
                    "capsule_stack": 0.1, "shanty_patchwork": 0.2},
        "palette": ["#2b2d42", "#4a4e69", "#8d99ae", "#c9c6c1", "#1f1d2b"],
        "crowns": ["flat", "billboard_frame", "parapet"],
        "signage_scripts": {"latin": 0.4, "kana": 0.3, "hanzi": 0.3},
        "window_to_wall": [0.3, 0.5], "bay_m": [2.7, 3.6], "wear": 0.7,
    },
    "corporate_glass": {
        "systems": {"unitized_curtain_wall": 0.5, "fin_wall": 0.2, "diagrid": 0.1,
                    "spandrel_ribbon": 0.2},
        "palette": ["#1b2430", "#9fb4c7", "#c9d2da", "#3a4a5c"],
        "crowns": ["lantern", "halo", "mast"],
        "signage_scripts": {"latin": 0.7, "kana": 0.15, "hanzi": 0.15},
        "window_to_wall": [0.6, 0.85], "bay_m": [1.5, 3.0], "wear": 0.15,
    },
    "brutalist": {
        "systems": {"board_marked_concrete": 0.5, "precast_panel": 0.3, "punched_concrete": 0.2},
        "palette": ["#8a8782", "#6b6964", "#a9a59d", "#4d4b47"],
        "crowns": ["flat", "stepped"],
        "signage_scripts": {"latin": 0.5, "cyrillic": 0.2, "hanzi": 0.3},
        "window_to_wall": [0.25, 0.4], "bay_m": [3.0, 4.5], "wear": 0.6,
    },
    "industrial": {
        "systems": {"corrugated": 0.4, "louvered_industrial": 0.3, "standing_seam": 0.2,
                    "precast_panel": 0.1},
        "palette": ["#5c6670", "#8f6b4a", "#a3a8ad", "#3f4448", "#b5452f"],
        "crowns": ["sawtooth", "flat"],
        "signage_scripts": {"latin": 0.6, "hanzi": 0.2, "hangul": 0.2},
        "window_to_wall": [0.05, 0.2], "bay_m": [4.0, 7.5], "wear": 0.9,
    },
    "clean_tech": {
        "systems": {"perforated_skin": 0.4, "fin_wall": 0.3, "unitized_curtain_wall": 0.3},
        "palette": ["#e8ecef", "#b7c4cc", "#5f7a87", "#2f3d44"],
        "crowns": ["flat", "halo"],
        "signage_scripts": {"latin": 0.8, "kana": 0.2},
        "window_to_wall": [0.45, 0.7], "bay_m": [1.8, 3.0], "wear": 0.1,
    },
    "suburban_modern": {
        "systems": {"stucco_shutters": 0.4, "timber_infill": 0.3, "precast_panel": 0.3},
        "palette": ["#e3ddd2", "#9a8f80", "#5b6b5a", "#3b3a39"],
        "crowns": ["pitched", "flat"],
        "signage_scripts": {"latin": 0.8, "hangul": 0.2},
        "window_to_wall": [0.25, 0.45], "bay_m": [2.7, 4.2], "wear": 0.2,
    },
    "transit_modern": {
        "systems": {"unitized_curtain_wall": 0.3, "standing_seam": 0.3, "exoskeleton": 0.2,
                    "spandrel_ribbon": 0.2},
        "palette": ["#d0d4d8", "#26303a", "#6f7c87", "#c2a03a"],
        "crowns": ["flat", "mast"],
        "signage_scripts": {"latin": 0.6, "kana": 0.2, "hanzi": 0.2},
        "window_to_wall": [0.4, 0.7], "bay_m": [3.0, 6.0], "wear": 0.3,
    },
    "mixed_modern": {
        "systems": {"spandrel_ribbon": 0.3, "punched_concrete": 0.3,
                    "unitized_curtain_wall": 0.2, "precast_panel": 0.2},
        "palette": ["#c8c2b8", "#5d6770", "#2e3338", "#a1866f"],
        "crowns": ["parapet", "mast", "flat"],
        "signage_scripts": {"latin": 0.5, "hanzi": 0.3, "kana": 0.2},
        "window_to_wall": [0.35, 0.6], "bay_m": [2.4, 3.6], "wear": 0.4,
    },
    "aerospace": {
        "systems": {"hangar_cladding": 0.5, "exoskeleton": 0.2, "standing_seam": 0.3},
        "palette": ["#e6e8ea", "#9aa3ab", "#2d3238", "#d9531e"],
        "crowns": ["flat", "mast", "dome"],
        "signage_scripts": {"latin": 0.8, "cyrillic": 0.2},
        "window_to_wall": [0.1, 0.3], "bay_m": [4.0, 8.0], "wear": 0.3,
    },
}

# Global defaults (decisions 13.2 and 13.4, provisional, 2026-10-27).
DEFAULTS = {
    "uniqueness": "U1",
    "hero_uniqueness": "U2",
    "min_gene_distance": 4,
    "share_parts": True,
    "texel_density_px_m": 512,
    "texel_density_upper_px_m": 256,
}
