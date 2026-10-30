"""Presets and fixed tables from docs/citygen_scope.md.

Section 4.4 (district archetypes), 5.3 (transit modes), 5.4 (water) and 5.7 (megasites).
Everything here is plain data; `defaults.py` uses it to expand a sparse spec.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

DIRECTIONS = (
    "north", "north_east", "east", "south_east",
    "south", "south_west", "west", "north_west",
)

# Unit vectors (x east, y north) for each compass direction.
DIRECTION_VECTORS: dict[str, tuple[float, float]] = {
    d: (round(math.cos(math.radians(90 - 45 * i)), 9), round(math.sin(math.radians(90 - 45 * i)), 9))
    for i, d in enumerate(DIRECTIONS)
}


def opposite(direction: str) -> str:
    return DIRECTIONS[(DIRECTIONS.index(direction) + 4) % 8]


# ---------------------------------------------------------------------------
# District archetypes (section 4.4)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ArchetypePreset:
    street_pattern: str
    block_size_m: tuple[float, float]
    height_m: tuple[float, float]
    character: tuple[str, ...]
    grid_angle_deg: float = 0.0
    landmark_height_m: float | None = None
    complexes: tuple[str, ...] = ()
    skybridge_density: float = 0.1
    grime: float = 0.4
    neon: float = 0.4
    greenery: float = 0.3
    waterway_style: tuple[str, ...] = ()
    waterway_density: float = 0.0
    megasites: tuple[str, ...] = ()
    # Relative weight used when area shares are left out of the spec.
    area_weight: float = 1.0
    # Whether the archetype wants a coastline (used as a soft default and by the schematic).
    prefers_coast: bool = False
    height_limited: bool = False
    # M11 gameplay layer: district base values of the wealth, danger and police fields
    wealth: float = 0.5
    danger: float = 0.4
    police: float = 0.5
    # M21: how far the district's towers depart from boxes (forms.weights)
    variety: float = 0.4


ARCHETYPES: dict[str, ArchetypePreset] = {
    "corporate_core": ArchetypePreset(
        street_pattern="rotated_grid", block_size_m=(120, 200), height_m=(80, 320),
        character=("plazas", "podium_towers", "skybridges", "sky_stations", "clean"),
        grid_angle_deg=45, landmark_height_m=450, complexes=("twin_towers", "tower_cluster"),
        skybridge_density=0.6, grime=0.1, neon=0.4, greenery=0.3, area_weight=1.2,
        wealth=0.9, danger=0.15, police=0.9, variety=0.9,
    ),
    "megablock_residential": ArchetypePreset(
        street_pattern="superblocks", block_size_m=(150, 250), height_m=(120, 250),
        character=("megabuildings", "atriums", "elevated_decks"),
        complexes=("megabuilding_campus",), skybridge_density=0.6, grime=0.5, neon=0.4,
        greenery=0.2, area_weight=1.2,
        wealth=0.35, danger=0.55, police=0.4, variety=0.35,
    ),
    "midtown_mixed": ArchetypePreset(
        street_pattern="grid_ring_park", block_size_m=(80, 140), height_m=(30, 150),
        character=("culture", "living", "commerce", "central_plaza"),
        complexes=("bridged_pair",), skybridge_density=0.3, grime=0.3, neon=0.5,
        greenery=0.5, megasites=("central_park",), area_weight=1.3,
        wealth=0.6, danger=0.3, police=0.6, variety=0.75,
    ),
    "entertainment_market": ArchetypePreset(
        street_pattern="organic", block_size_m=(30, 80), height_m=(10, 60),
        character=("clubs", "covered_alleys", "stalls", "billboards", "heavy_neon"),
        complexes=("straddle_building",), skybridge_density=0.3, grime=0.6, neon=0.9,
        greenery=0.1, waterway_style=("organic_canals",), waterway_density=0.3,
        area_weight=0.9,
        wealth=0.45, danger=0.6, police=0.35, variety=0.55,
    ),
    "old_town": ArchetypePreset(
        street_pattern="organic", block_size_m=(20, 60), height_m=(6, 30),
        character=("markets", "food", "heritage", "temples", "stacked_shanties", "grime"),
        complexes=(), skybridge_density=0.2, grime=0.7, neon=0.6, greenery=0.3,
        waterway_style=("organic_canals", "creeks"), waterway_density=0.5, area_weight=1.0,
        prefers_coast=True,
        wealth=0.3, danger=0.65, police=0.25, variety=0.15,
    ),
    "industrial_port": ArchetypePreset(
        street_pattern="large_grid", block_size_m=(150, 300), height_m=(8, 25),
        character=("warehouses", "container_yards", "cranes", "berths", "freight_terminal"),
        complexes=(), skybridge_density=0.0, grime=0.8, neon=0.2, greenery=0.05,
        waterway_style=("harbor_basins",), waterway_density=0.5,
        megasites=("freight_terminal",), area_weight=1.3, prefers_coast=True,
        wealth=0.25, danger=0.7, police=0.2, variety=0.1,
    ),
    "residential_heights": ArchetypePreset(
        street_pattern="curvilinear", block_size_m=(80, 150), height_m=(10, 60),
        character=("lower_density", "parks", "walls", "guard_gates"),
        complexes=(), skybridge_density=0.05, grime=0.15, neon=0.2, greenery=0.7,
        area_weight=1.0,
        wealth=0.8, danger=0.15, police=0.7, variety=0.2,
    ),
    "research_campus": ArchetypePreset(
        street_pattern="campus_loops", block_size_m=(100, 200), height_m=(15, 90),
        character=("labs", "medical", "r_and_d", "landscaped_grounds"),
        complexes=("campus",), skybridge_density=0.2, grime=0.1, neon=0.3, greenery=0.7,
        area_weight=0.6,
        wealth=0.75, danger=0.15, police=0.7, variety=0.5,
    ),
    "transit_hub": ArchetypePreset(
        street_pattern="radial_ring", block_size_m=(60, 120), height_m=(20, 120),
        character=("multi_level_station", "bus_bays", "maglev_metro_interchange"),
        complexes=("tower_cluster",), skybridge_density=0.5, grime=0.3, neon=0.6,
        greenery=0.2, megasites=("transit_nexus",), area_weight=0.6,
        wealth=0.5, danger=0.4, police=0.65, variety=0.6,
    ),
    "spaceport": ArchetypePreset(
        street_pattern="service_roads", block_size_m=(200, 400), height_m=(10, 60),
        character=("launch_pads", "terminal", "hangars", "cargo"),
        complexes=(), skybridge_density=0.0, grime=0.3, neon=0.3, greenery=0.05,
        megasites=("spaceport",), area_weight=0.9, prefers_coast=True, height_limited=True,
        wealth=0.6, danger=0.25, police=0.8, variety=0.3,
    ),
}

STREET_PATTERNS = (
    "rotated_grid", "grid", "large_grid", "superblocks", "grid_ring_park", "organic",
    "curvilinear", "campus_loops", "radial_ring", "service_roads",
)

# ---------------------------------------------------------------------------
# Transit modes (section 5.3)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ModePreset:
    altitude_m: tuple[float, float]       # allowed range
    default_altitude_m: tuple[float, float]
    max_grade: float | None
    min_curve_radius_m: float | None
    support_spacing_m: tuple[float, float] | None
    station_spacing_m: tuple[float, float]
    palette: tuple[str, ...] = field(default=())


TRANSIT_MODES: dict[str, ModePreset] = {
    # Metro is underground; altitude is the track depth (negative), carried as data only.
    "metro": ModePreset((-60, 0), (-20, -12), None, None, None, (600, 1000),
                        ("#2f7bff", "#5aa0ff", "#1d4fbf")),
    "elevated_rail": ModePreset((8, 20), (10, 16), 0.04, 150, (25, 40), (500, 900),
                                ("#ffb020", "#ffcf6a", "#c98600")),
    "monorail": ModePreset((10, 30), (12, 22), 0.06, 100, (20, 30), (400, 800),
                           ("#3ddc84", "#8ff0b8", "#1f9c57")),
    "maglev": ModePreset((15, 60), (25, 45), 0.10, 500, (30, 60), (1200, 2500),
                         ("#ff2bd6", "#ff7ae6", "#b0009a")),
    "sky_tube": ModePreset((40, 150), (70, 120), 0.08, 300, (40, 80), (800, 1600),
                           ("#22e5ff", "#8ff3ff", "#0aa6bd")),
}

# ---------------------------------------------------------------------------
# Water (sections 4.2, 5.4)
# ---------------------------------------------------------------------------

COAST_FORMS = ("bay", "peninsula", "delta", "archipelago", "crescent", "straight")

# Rough share of the map that is sea for each coast form; used for area estimates and the schematic.
COAST_SEA_SHARE = {
    "straight": 0.2, "bay": 0.3, "peninsula": 0.45, "delta": 0.3,
    "archipelago": 0.55, "crescent": 0.35,
}

RIVER_WIDTH_DEFAULT_M = (60.0, 120.0)
CHANNEL_WIDTH_DEFAULT_M = (150.0, 300.0)

WATERWAY_STYLES = (
    "canal_grid", "organic_canals", "creeks", "inlets", "harbor_basins", "marina",
)

# Navigable clearance by waterway class (section 5.4), meters.
BRIDGE_CLEARANCE_M = {"sea_channel": 25.0, "river": (10.0, 15.0), "canal": (3.0, 4.0)}

# ---------------------------------------------------------------------------
# Megasites (section 5.7)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class MegasitePreset:
    area_km2: float
    coast: bool | None = None          # True: must be on the coast or a river mouth
    edge_or_coast: bool = False        # True: coast or city edge
    needs_highway: bool = False
    needs_transit: tuple[str, ...] = ()  # one of these modes must serve it
    height_limit_m: float | None = None


MEGASITES: dict[str, MegasitePreset] = {
    "spaceport": MegasitePreset(0.5, edge_or_coast=True, needs_highway=True,
                                needs_transit=("maglev", "sky_tube"), height_limit_m=60),
    "skyport": MegasitePreset(0.02),
    "transit_nexus": MegasitePreset(0.08, needs_highway=True,
                                    needs_transit=("metro", "maglev", "sky_tube")),
    "freight_terminal": MegasitePreset(0.4, coast=True, needs_highway=True,
                                       needs_transit=("elevated_rail", "metro", "monorail")),
    "stadium": MegasitePreset(0.06),
    "arcology": MegasitePreset(0.04),
    "temple_complex": MegasitePreset(0.04),
    "central_park": MegasitePreset(0.1),
    "grand_plaza": MegasitePreset(0.03),
    "attraction": MegasitePreset(0.01),
}

COMPLEX_KINDS = (
    "twin_towers", "tower_cluster", "megabuilding_campus", "bridged_pair",
    "straddle_building", "campus",
)

PLACE_KINDS = (
    "plaza", "park", "garden", "street", "pedestrian_street", "market", "canal", "creek",
    "waterfront", "promenade", "pier", "docks", "marina", "beach", "gate", "neighborhood",
    "monument", "station",
)

HIGHWAY_PATTERNS = ("ring", "ring_plus_spine", "spine", "grid", "radial", "coastal", "none")

# Landmark kinds with a known default height; any other snake_case kind is allowed.
LANDMARK_HEIGHTS_M = {
    "megatower": 480.0, "arcology": 400.0, "spire": 350.0, "observation_tower": 250.0,
    "ferris_wheel": 120.0, "monument": 40.0, "temple": 35.0,
}
