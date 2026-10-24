"""Megasite reserves (scope stage 9, reserved right after districts so roads route around them).

M1b only reserves the ground: each megasite of a district (spaceport, transit nexus, freight
terminal, central park, ...) gets a compact footprint of its `area_km2` inside the district,
oriented to the district grid. The site generators of M3 fill these reserves. A spaceport also
gets the ground footprint of its flight cone: a 15 degree wedge (900 m) pointing away from the
city center, plus a 40 m apron, kept within the spaceport district and the water. Roads stay out
of reserves and cones.

Placement by kind: spaceports far from the city center and on the coast; freight terminals on
the shore (they own the waterfront); the others (transit nexus, central park, stadium, ...)
near the middle of the district. `edge` and `coast` from the spec override that. A site that
does not fit shrinks in steps of 15% (noted in the report).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np
from shapely import affinity
from shapely.geometry import Point, Polygon
from shapely.ops import unary_union

from . import dmath as M
from . import geom as G
from . import presets
from .spec import CitySpec

LAND_INSET_M = 30.0     # room for a road on the district boundary
WATER_INSET_M = 70.0    # room for a waterfront road, unless the site owns the shore
SITE_GAP_M = 30.0
CONE_HALF_ANGLE_DEG = 15.0
CONE_LENGTH_M = 900.0
CONE_APRON_M = 20.0
SHORE_KINDS = ("spaceport", "freight_terminal")


@dataclass
class SiteRec:
    id: str
    kind: str
    name: str
    district: str
    polygon: Polygon
    target_m2: float
    height_limit_m: float | None = None
    flight_cone: object = None
    notes: list[str] = field(default_factory=list)


def _shape(kind: str, area: float, angle_deg: float) -> Polygon:
    """Unit-centered footprint of `area`: a long rectangle for a spaceport, a rounded
    rectangle otherwise."""
    aspect = 2.0 if kind == "spaceport" else 1.5
    w = math.sqrt(area * aspect)
    h = area / w
    if kind == "spaceport":
        p = Polygon([(-w / 2, -h / 2), (w / 2, -h / 2), (w / 2, h / 2), (-w / 2, h / 2)])
    else:
        r = 0.18 * h
        p = Polygon([(-w / 2 + r, -h / 2 + r), (w / 2 - r, -h / 2 + r), (w / 2 - r, h / 2 - r),
                     (-w / 2 + r, h / 2 - r)]).buffer(r, 8)
        p = affinity.scale(p, math.sqrt(area / p.area), math.sqrt(area / p.area))
    return affinity.rotate(p, angle_deg, origin=(0, 0))


def _score(kind: str, site, pos: Point, ctx: dict) -> float:
    """Lower is better."""
    cx, cy = ctx["center"]
    far = M.hypot(pos.x - cx, pos.y - cy)
    if site.edge and site.edge != "center":
        ux, uy = presets.DIRECTION_VECTORS[site.edge]
        return -(pos.x * ux + pos.y * uy)
    shore = ctx["coast"].distance(pos) if not ctx["coast"].is_empty else 0.0
    if kind == "spaceport":
        return -far + 0.5 * shore
    if kind == "freight_terminal" or site.coast:
        return shore
    mx, my = ctx["middle"]
    return M.hypot(pos.x - mx, pos.y - my)


def _fit(kind: str, site, allowed, area: float, angle: float, ctx: dict) -> Polygon | None:
    base = _shape(kind, area, angle)
    base90 = _shape(kind, area, angle + 90.0)
    minx, miny, maxx, maxy = allowed.bounds
    step = max(math.sqrt(area) / 5.0, 25.0)
    best = None
    xs = np.arange(minx, maxx + step, step)
    ys = np.arange(miny, maxy + step, step)
    for x in xs:
        for y in ys:
            p = Point(G.q(x), G.q(y))
            if not allowed.contains(p):
                continue
            s = _score(kind, site, p, ctx)
            if best is not None and s >= best[0]:
                continue
            for shp in (base, base90):
                cand = affinity.translate(shp, p.x, p.y)
                if allowed.contains(cand):
                    best = (s, cand)
                    break
    return best[1] if best else None


def place_megasites(spec: CitySpec, polygons: dict[str, object], h, waterways,
                    district_ids: dict[str, str]) -> tuple[list[SiteRec], list[str]]:
    sites: list[SiteRec] = []
    notes: list[str] = []
    land = unary_union(list(polygons.values()))
    c = land.centroid if not land.is_empty else Point(0, 0)
    ww = unary_union([w.polygon for w in waterways.items]) if waterways.items else Polygon()
    taken = Polygon()
    for d in spec.districts:
        poly = polygons.get(d.name)
        if poly is None or poly.is_empty or not d.megasites:
            continue
        others = unary_union([p for n, p in polygons.items() if n != d.name])
        wet_edge = poly.boundary.intersection(h.water.buffer(2.0))
        dry_edge = poly.boundary.difference(h.water.buffer(2.0))
        coast = poly.boundary.intersection(h.coastal.buffer(3.0))
        for j, site in enumerate(d.megasites):
            kind = site.kind
            shore = kind in SHORE_KINDS or bool(site.coast)
            allowed = poly.difference(ww.buffer(15.0)) if not ww.is_empty else poly
            if not dry_edge.is_empty:
                allowed = allowed.difference(dry_edge.buffer(LAND_INSET_M))
            if not wet_edge.is_empty:
                allowed = allowed.difference(wet_edge.buffer(10.0 if shore else WATER_INSET_M))
            allowed = G.polygonal(allowed.difference(taken.buffer(SITE_GAP_M))
                                  if not taken.is_empty else allowed)
            if allowed.is_empty:
                notes.append(f"megasite '{site.name}' ({kind}): no room in '{d.name}'")
                continue
            inner = G.parts(allowed)[0]
            ctx = {"center": (c.x, c.y), "coast": coast if shore else wet_edge,
                   "middle": (inner.centroid.x, inner.centroid.y)}
            target = site.area_km2 * 1e6
            area, fp = target, None
            for _ in range(10):
                fp = _fit(kind, site, allowed, area, d.grid_angle_deg or 0.0, ctx)
                if fp is not None:
                    break
                area *= 0.85
            if fp is None:
                notes.append(f"megasite '{site.name}' ({kind}): does not fit in '{d.name}'")
                continue
            fp = G.qpoly(fp)
            rec = SiteRec(f"{district_ids[d.name]}.ms{j + 1:02d}", kind, site.name, d.name, fp,
                          target, site.height_limit_m)
            if area < target * 0.999:
                msg = (f"megasite '{site.name}' ({kind}) shrunk to {area / 1e6:.2f} km2 "
                       f"(asked {target / 1e6:.2f}) to fit '{d.name}'")
                rec.notes.append(msg)
                notes.append(msg)
            if kind == "spaceport":
                rec.flight_cone = flight_cone(fp, (c.x, c.y), poly, others, h.canvas)
            sites.append(rec)
            taken = taken.union(fp)
    return sites, notes


def flight_cone(site: Polygon, center: tuple[float, float], district, others, canvas):
    """Ground footprint of a spaceport's flight cone: a wedge from the site away from the city
    center plus an apron, kept off other districts."""
    p = site.centroid
    ang = M.atan2(p.y - center[1], p.x - center[0])
    if M.hypot(p.x - center[0], p.y - center[1]) < 1.0:
        ang = 0.0
    half = M.radians(CONE_HALF_ANGLE_DEG)
    pts = [(p.x, p.y)]
    for k in range(9):
        a = ang - half + 2 * half * k / 8
        pts.append((p.x + CONE_LENGTH_M * M.cos(a), p.y + CONE_LENGTH_M * M.sin(a)))
    cone = unary_union([Polygon(pts), site.buffer(CONE_APRON_M)]).intersection(canvas)
    if others is not None and not others.is_empty:
        cone = cone.difference(others)
    return G.qpoly(G.parts(cone)[0] if G.parts(cone) else cone)
