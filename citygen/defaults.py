"""Fill-defaults: expand a sparse spec into a complete one using the presets.

`fill_defaults` never invents districts, names the prompt did not imply, or transit lines; it
fills parameters. It is deterministic: the same input spec gives the same filled spec.
"""

from __future__ import annotations

import zlib

from shapely.geometry import Polygon

from . import presets
from .spec import (
    CitySpec,
    Complex,
    Coast,
    District,
    Megasite,
    River,
    Waterways,
)

SHARE_DECIMALS = 4


def derive_seed(*parts: object) -> int:
    """Stable 31-bit seed from any parts (independent of Python's hash randomization)."""
    return zlib.crc32("|".join(str(p) for p in parts).encode()) & 0x7FFFFFFF


def kind_label(kind: str) -> str:
    return kind.replace("_", " ").title()


def megasite_default_name(district: District, kind: str) -> str:
    label = kind_label(kind)
    if label.lower() in district.name.lower():
        return district.name
    name = f"{district.name} {label}"
    return name[:60]


def land_edges(sea_side: str) -> list[str]:
    """Cardinal edges that do not face the sea."""
    sx, sy = presets.DIRECTION_VECTORS[sea_side]
    out = []
    for d in ("north", "east", "south", "west"):
        x, y = presets.DIRECTION_VECTORS[d]
        if x * sx + y * sy <= 1e-9:
            out.append(d)
    return out


def fill_shares(districts: list[District]) -> None:
    given = [d.area_share for d in districts if d.area_share is not None]
    missing = [d for d in districts if d.area_share is None]
    rest = max(0.0, 1.0 - sum(given))
    weight = sum(presets.ARCHETYPES[d.archetype].area_weight for d in missing)
    for d in missing:
        d.area_share = rest * presets.ARCHETYPES[d.archetype].area_weight / weight if weight else 0.0
    total = sum(d.area_share for d in districts) or 1.0
    for d in districts:
        d.area_share = round(d.area_share / total, SHARE_DECIMALS)
    # Put rounding drift on the largest district so the shares sum to exactly 1.
    drift = round(1.0 - sum(d.area_share for d in districts), SHARE_DECIMALS)
    if drift:
        big = max(districts, key=lambda d: d.area_share)
        big.area_share = round(big.area_share + drift, SHARE_DECIMALS)


def fill_district(d: District, city_seed: int, separation: str) -> None:
    p = presets.ARCHETYPES[d.archetype]
    if d.seed is None:
        d.seed = derive_seed(city_seed, "district", d.name)
    if d.street_pattern is None:
        d.street_pattern = p.street_pattern
    if d.grid_angle_deg is None:
        d.grid_angle_deg = p.grid_angle_deg
    if d.block_size_m is None:
        d.block_size_m = p.block_size_m
    if d.height_m is None:
        d.height_m = p.height_m
    if d.water_separation is None:
        d.water_separation = separation
    if d.waterways is None:
        d.waterways = Waterways(style=list(p.waterway_style), density=p.waterway_density)
    if d.complexes is None:
        d.complexes = [Complex(kind=k) for k in p.complexes]
    for attr in ("skybridge_density", "grime", "neon", "greenery", "wealth", "danger", "police"):
        if getattr(d, attr) is None:
            setattr(d, attr, getattr(p, attr))

    for lm in d.landmarks:
        if lm.height_m is None:
            lm.height_m = presets.LANDMARK_HEIGHTS_M.get(lm.kind) or p.landmark_height_m \
                or round(d.height_m[1] * 1.4)
        if lm.name is None:
            lm.name = f"{d.name} {kind_label(lm.kind)}"[:60]

    # Megasites: preset kinds when left out, plus places whose kind is a megasite kind.
    sites: list[Megasite] = (
        [Megasite(kind=k) for k in p.megasites] if d.megasites is None else list(d.megasites)
    )
    keep_places = []
    for place in d.places:
        if place.kind in presets.MEGASITES:
            unnamed = next((s for s in sites if s.kind == place.kind and s.name is None), None)
            if unnamed is not None:
                unnamed.name = place.name
            elif not any(s.name == place.name for s in sites):
                sites.append(Megasite(kind=place.kind, name=place.name))
        else:
            keep_places.append(place)
    d.places = keep_places

    counts: dict[str, int] = {}
    for s in sites:
        mp = presets.MEGASITES[s.kind]
        if s.name is None:
            counts[s.kind] = counts.get(s.kind, 0) + 1
            base = megasite_default_name(d, s.kind)
            s.name = base if counts[s.kind] == 1 else f"{base} {counts[s.kind]}"[:60]
        if s.area_km2 is None:
            s.area_km2 = mp.area_km2
        if s.coast is None and mp.coast is not None:
            s.coast = mp.coast
        if s.height_limit_m is None and mp.height_limit_m is not None:
            s.height_limit_m = mp.height_limit_m
    d.megasites = sites


def fill_defaults(spec: CitySpec) -> CitySpec:
    s = spec.model_copy(deep=True)
    if s.seed is None:
        s.seed = derive_seed("city", s.name) % 1_000_000

    w = s.water
    if w.coast is None:
        w.coast = Coast(form="bay", side="south")
    if w.coast.sea_share is None:
        w.coast.sea_share = presets.COAST_SEA_SHARE[w.coast.form]
    if w.rivers is None:
        w.rivers = [River.model_validate({
            "name": f"{s.name} River"[:60], "from": presets.opposite(w.coast.side),
            "to": "bay" if w.coast.form in ("bay", "crescent") else "sea",
        })]
    for isl in w.islands:
        if isl.pinned is not None:
            from . import pinned as PN

            land = PN.load_cached(isl.pinned.source).land
            isl.area_km2 = round(Polygon(land.exterior).area / 1e6, 4)
    for r in w.rivers:
        if r.width_m is None:
            r.width_m = (presets.CHANNEL_WIDTH_DEFAULT_M if r.kind == "channel"
                         else presets.RIVER_WIDTH_DEFAULT_M)
        if r.meander is None:
            r.meander = 0.1 if r.kind == "channel" else 0.4

    if s.highways.exits is None:
        s.highways.exits = land_edges(w.coast.side)

    fill_shares(s.districts)
    for d in s.districts:
        fill_district(d, s.seed, w.district_separation)

    t = s.transit
    if t.hubs is None:
        hubs = [d.name for d in s.districts if d.archetype == "transit_hub"]
        for d in s.districts:
            if d.name in hubs:  # a hub district's own nexus is the same interchange
                continue
            for site in d.megasites:
                if site.kind == "transit_nexus" and site.name not in hubs:
                    hubs.append(site.name)
        t.hubs = hubs
    per_mode: dict[str, int] = {}
    for line in t.lines:
        mp = presets.TRANSIT_MODES[line.mode]
        i = per_mode.get(line.mode, 0)
        per_mode[line.mode] = i + 1
        if line.altitude_m is None:
            line.altitude_m = mp.default_altitude_m
        if line.color is None:
            line.color = mp.palette[i % len(mp.palette)]
    return s
