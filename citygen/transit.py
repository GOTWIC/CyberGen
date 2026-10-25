"""M5: transit lines, stations and their structures, on the built city (scope 5.3).

Runs after M3, on the city with its buildings, so every line sees what it passes:

1. **Stops.** Each route name becomes a point: a district's transit nexus platform for the
   line's mode, else the avenue junction nearest the district's center (for a stop between
   two others, the one nearest the line's way); a place, megasite or island by its polygon;
   `<dir>_exit` at the highway exit (or the map edge).
2. **Routes.** Elevated rail and monorail route on the road graph (a turn penalty at every
   node, their stops at the nearest node). The maglev, sky tubes and the metro use A* on a 15
   m raster whose costs depend on the mode: a sky tube flies over everything lower than its
   altitude less 10 m and, with `through_towers`, is drawn through towers tall enough for a
   portal. Forbidden: landmarks, complex and megasite buildings in the way, buildings a sky
   line cannot clear, skybridges of complexes, spaceport flight cones above their limit. Then
   Douglas-Peucker between the stops and straight runs joined by arcs at the mode's radius
   (`arc_path`), with every change and every arc kept clear of what the line cannot pass.
3. **Profile.** z from the mode's altitude between two envelopes limited to the grade: from
   below navigable water, road decks, the roofs under the line and kept skybridges passed
   over; from above the towers a sky tube passes through and skybridges passed under.
4. **Clearing.** Buildings an elevated line cannot clear are taken out of its corridor (the lot
   stays, marked `transit_corridor`); sky tubes get a declared portal in every tower they pass
   through; skybridges in a line's way are removed (complex skybridges are obstacles instead).
5. **Stations** at every stop and at the mode's spacing between them: platforms on the deck
   with stairs and an elevator to the nearest sidewalk, sky stations inside the portal tower
   (elevator to its main entrance) or on a pylon, metro concourses with two entrance kiosks;
   elevated walkways from platforms to buildings with a floor at platform level.
6. **Structures:** deck, guideway or tube per leg, columns or pylons at the mode's spacing
   (in road medians, at the curbs of streets without one, never in lanes, sidewalk clear paths,
   buildings or water), station platforms, canopies.

Coordinates are on the 0.01 m grid; the raster search, the fillets and every decision use exact
predicates, sorted tree hits and plain arithmetic (dmath angles), like the road builder.
"""

from __future__ import annotations

import heapq
import math
from dataclasses import dataclass, field

import numpy as np
import shapely
from shapely.geometry import LineString, Point, Polygon

from . import dmath as M
from . import geom as G
from . import presets
from . import trace as T
from .buildout import _foot, _ground, _landmass_index, _nearest_on, _neighbors, _split
from .roads import _arc_line, _fillet_radii

CELL_M = 15.0
INF = math.inf

# structure width (m) and the clearance kept to buildings beside it
WIDTH_M = {"metro": 10.0, "elevated_rail": 9.0, "monorail": 3.5, "maglev": 7.0,
           "sky_tube": 7.0}
SIDE_PAD_M = 2.0
DECK_M = {"metro": 0.0, "elevated_rail": 1.6, "monorail": 1.8, "maglev": 2.0, "sky_tube": 7.0}
SKY_CLEAR_M = 10.0          # sky lines clear buildings by this much (scope 5.3)
ROAD_CLEAR_M = 5.5          # under any deck over a road (scope 5.2)
PORTAL_HEADROOM_M = 8.0     # a portal tower rises at least this far above the tube's top
STATION_LEN_M = {"metro": 120.0, "elevated_rail": 110.0, "monorail": 60.0, "maglev": 160.0,
                 "sky_tube": 50.0}
PLATFORM_M = {"metro": 4.0, "elevated_rail": 4.0, "monorail": 3.0, "maglev": 5.0,
              "sky_tube": 4.0}
COLUMN_M = {"elevated_rail": 1.6, "monorail": 1.2, "maglev": 2.2, "sky_tube": 3.5}
METRO_CONCOURSE_Z = -8.0
STATION_TOWER_M = 200.0     # a sky station uses a portal tower within this of its stop

# raster costs per meter, by what a cell is (lower is preferred)
COSTS = {
    "elevated_rail": {"avenue": 1.0, "highway": 1.8, "street": 1.6, "minor": 3.0,
                      "water": 2.2, "open": 2.4, "land": 4.0, "low": 4.5, "tall": 30.0,
                      "raised": 8.0},
    "monorail": {"avenue": 1.0, "highway": 1.8, "street": 1.5, "minor": 2.8, "water": 2.0,
                 "open": 2.2, "land": 3.8, "low": 4.2, "tall": 30.0, "raised": 8.0},
    "maglev": {"avenue": 1.5, "highway": 1.0, "street": 2.2, "minor": 3.5, "water": 2.0,
               "open": 2.4, "land": 3.5, "low": 3.0, "tall": 40.0, "raised": 1.2},
    "sky_tube": {"avenue": 1.0, "highway": 1.0, "street": 1.0, "minor": 1.0, "water": 1.0,
                 "open": 1.0, "land": 1.0, "low": 1.0, "tall": INF, "raised": 1.0,
                 "portal": 0.55},
    "metro": {"avenue": 0.8, "highway": 1.0, "street": 0.9, "minor": 1.0, "water": 1.4,
              "open": 1.0, "land": 1.1, "low": 1.1, "tall": 1.1, "raised": 1.0},
}
TURN_COST_M = {"sky_tube": 700.0, "elevated_rail": 300.0, "monorail": 250.0, "maglev": 900.0}
# raster search: penalty (m) for a 90 degree turn, twice that for turning back
ROAD_MODES = ("elevated_rail", "monorail")  # route on the road graph (the maglev flies over)
# road graph weights per meter by class (missing: not used), raised (elevated, not bridge)
ROAD_W = {
    "elevated_rail": {"avenue": 1.0, "highway": 1.7, "street": 1.9, "service": 3.0},
    "monorail": {"avenue": 1.0, "highway": 1.7, "street": 1.7, "service": 2.8},
    "maglev": {"highway": 1.0, "avenue": 1.5, "street": 3.2},
}
RAISED_W = 6.0
CLIMB_W = 6.0         # raster: over a building the line climbs to clear (within its altitude)
REUSE_W = 2.0         # a later leg of the same line on a segment an earlier leg used
REUSE_PAD_M = 120.0   # raster: cells this close to an earlier leg cost REUSE_W times more
TURN_M = {"elevated_rail": 450.0, "monorail": 350.0, "maglev": 1600.0}  # at a 90 degree turn
SIMPLIFY_M = {"elevated_rail": 6.0, "monorail": 5.0, "maglev": 120.0, "sky_tube": 75.0,
              "metro": 12.0}   # Douglas-Peucker tolerance before the arcs (a quarter of the
#                                radius for the lines that fly, a lane for the street lines)

_MOVES = []
for _dx, _dy in [(1, 0), (0, 1), (-1, 0), (0, -1), (1, 1), (1, -1), (-1, 1), (-1, -1),
                 (2, 1), (1, 2), (-1, 2), (-2, 1), (-2, -1), (-1, -2), (1, -2), (2, -1)]:
    _MOVES.append((_dx, _dy, math.sqrt(_dx * _dx + _dy * _dy)))


def q(v: float) -> float:
    return round(float(v), 2)


def _d(a, b) -> float:
    dx, dy = b[0] - a[0], b[1] - a[1]
    return math.sqrt(dx * dx + dy * dy)


def _plen(pts) -> float:
    return math.fsum(_d(a, b) for a, b in zip(pts, pts[1:]))


# ---------------------------------------------------------------------------
# Context
# ---------------------------------------------------------------------------

def below(mode: str) -> float:
    """Structure under the track z: the deck of an elevated line (z is the rail level), half
    the tube of a sky line (z is the tube axis)."""
    return DECK_M[mode] / 2.0 if mode == "sky_tube" else DECK_M[mode]


def above(mode: str) -> float:
    return DECK_M[mode] / 2.0 if mode == "sky_tube" else 0.0


@dataclass
class Stop:
    name: str
    p: tuple[float, float]
    district_id: str | None
    kind: str                       # district, place, megasite, island, exit
    z: float | None = None          # platform level at a transit nexus
    tower_id: str | None = None     # a nexus sky station tower
    area: object = None             # what the stop names (district, site, place polygon)


@dataclass
class Bld:
    id: str
    poly: Polygon
    top: float
    removable: bool
    bottom: float = 0.0             # lowest mass (straddle spans start high)
    portal_ok: bool = False         # wide and solid enough for a tube portal


@dataclass
class Ctx:
    spec: object
    m: object
    x0: float = 0.0
    y0: float = 0.0
    nx: int = 0
    ny: int = 0
    xs: np.ndarray = None
    ys: np.ndarray = None
    pts: np.ndarray = None
    cls: dict = field(default_factory=dict)     # name -> bool array per cell
    road_z: np.ndarray = None
    blds: list = field(default_factory=list)
    btree: object = None
    water: list = field(default_factory=list)   # (polygon, clearance m, navigable)
    cones: list = field(default_factory=list)   # (polygon, limit m)
    skyb: list = field(default_factory=list)    # (line, z0, z1, complex, id, width)
    decks: list = field(default_factory=list)   # raised roads: (line, half width, z profile)
    dtree: object = None


def raised_roads(m) -> list:
    """Road decks off the ground (bridges, elevated stretches): (centerline, half width,
    [(s, z)] along it)."""
    out = []
    for s in m.road_segments:
        if s.bridge or any(z.z > 0.5 for z in s.z_profile):
            prof = [(z.s, z.z) for z in s.z_profile] or [(0.0, 0.0)]
            out.append((LineString(s.centerline), s.width_m / 2.0, prof))
    return out


def _z_at(prof, s: float) -> float:
    if s <= prof[0][0]:
        return prof[0][1]
    for (s0, z0), (s1, z1) in zip(prof, prof[1:]):
        if s <= s1:
            return z0 if s1 <= s0 else z0 + (z1 - z0) * (s - s0) / (s1 - s0)
    return prof[-1][1]


def deck_heights(decks, tree, arr, pad: float) -> list[tuple[int, float]]:
    """(point index, road deck z) for the points over a raised road (within its half width
    plus pad), the deck z where the point projects on its centerline."""
    if tree is None:
        return []
    out = []
    reach = max(d[1] for d in decks) + pad
    ip, il = tree.query(arr, predicate="dwithin", distance=reach)
    for i, l_ in sorted(zip(ip.tolist(), il.tolist())):
        line, hw, prof = decks[l_]
        p = arr[i]
        if line.distance(p) <= hw + pad:
            out.append((i, _z_at(prof, line.project(p))))
    return out


def context(spec, m) -> Ctx:
    c = Ctx(spec, m)
    x0, y0, x1, y1 = m.bounds
    c.x0, c.y0 = x0, y0
    c.nx = int(math.ceil((x1 - x0) / CELL_M))
    c.ny = int(math.ceil((y1 - y0) / CELL_M))
    ii, jj = np.meshgrid(np.arange(c.nx), np.arange(c.ny))
    c.xs = x0 + (ii.ravel() + 0.5) * CELL_M
    c.ys = y0 + (jj.ravel() + 0.5) * CELL_M
    c.pts = shapely.points(np.column_stack([c.xs, c.ys]))
    n = c.nx * c.ny
    # roads by class (a cell is on a road when its center is within the half width)
    groups = {"highway": ("highway",), "avenue": ("avenue",), "street": ("street",),
              "minor": ("alley", "service", "pedestrian")}
    c.road_z = np.zeros(n)
    raised = np.zeros(n, bool)
    for name, classes in groups.items():
        segs = [s for s in m.road_segments if s.road_class in classes]
        mask = np.zeros(n, bool)
        if segs:
            lines = [LineString(s.centerline) for s in segs]
            tree = shapely.STRtree(lines)
            idx_p, idx_l = tree.query(c.pts, predicate="dwithin",
                                      distance=max(s.width_m for s in segs) / 2.0)
            d = shapely.distance(c.pts[idx_p], np.array(lines, dtype=object)[idx_l])
            half = np.array([segs[k].width_m / 2.0 for k in idx_l.tolist()])
            ok = d <= half
            mask[idx_p[ok]] = True
            for p_, l_ in zip(idx_p[ok].tolist(), idx_l[ok].tolist()):
                s = segs[l_]
                if s.bridge or any(z.z > 0.5 for z in s.z_profile):
                    zmax = max((z.z for z in s.z_profile), default=0.0)
                    if zmax > c.road_z[p_]:
                        c.road_z[p_] = zmax
                    raised[p_] = True
        c.cls[name] = mask
    c.cls["raised"] = raised
    c.decks = raised_roads(m)
    c.dtree = shapely.STRtree([d[0] for d in c.decks]) if c.decks else None
    # water
    wet = np.zeros(n, bool)
    for e in [*m.seas]:
        for p in e.polygons:
            poly = G.from_model_poly(p)
            c.water.append((poly, 25.0, True))
    for e in m.rivers:
        c.water.append((G.from_model_poly(e.polygon), 12.0, True))
    for e in m.channels:
        c.water.append((G.from_model_poly(e.polygon), 25.0 if e.kind == "sea_channel" else
                        12.0, True))
    for e in m.waterways:
        c.water.append((G.from_model_poly(e.polygon), 4.0, not e.ornamental))
    for poly, _, _ in c.water:
        wet |= shapely.contains_xy(poly, c.xs, c.ys)
    c.cls["water"] = wet
    opens = [G.from_model_poly(o.polygon) for o in m.open_spaces if o.z_m <= 0.5]
    c.cls["open"] = _cover(opens, c.xs, c.ys)
    land = [G.from_model_poly(p) for lnd in m.land for p in lnd.polygons]
    c.cls["onland"] = _cover(land, c.xs, c.ys)
    # buildings
    prop = {p.id: p for p in m.properties}
    for b in m.buildings:
        polys = [G.from_model_poly(ms.footprint) for ms in b.masses
                 if ms.role != "void" and ms.z1_m > ms.z0_m]
        if not polys:
            continue
        poly = G.union(polys)
        if poly.is_empty:
            continue
        p = prop.get(b.property_id)
        complex_member = p is not None and p.complex not in ("single",)
        removable = not (b.landmark or b.megasite_id or complex_member)
        bottom = min(ms.z0_m for ms in b.masses if ms.z1_m > ms.z0_m)
        w = G._strip_width(G.parts(poly)[0]) if G.parts(poly) else 0.0
        c.blds.append(Bld(b.id, poly, b.height_m, removable, bottom, w >= 12.0 and
                          G.area(poly) >= 600.0))
    c.btree = shapely.STRtree([x.poly for x in c.blds]) if c.blds else None
    for s in m.megasites:
        if s.flight_cone is not None and s.height_limit_m is not None:
            c.cones.append((G.from_model_poly(s.flight_cone), s.height_limit_m))
    props = {p.id: p for p in m.properties}
    for sb in m.skybridges:
        p = props.get(sb.property_id)
        cx = p is not None and p.complex not in ("single",)
        top = sb.z_m + sb.levels * sb.level_height_m
        c.skyb.append((LineString(sb.line), sb.z_m - 1.0, top, cx, sb.id, sb.width_m))
    return c


def _cover(polys, xs, ys) -> np.ndarray:
    out = np.zeros(len(xs), bool)
    for p in polys:
        if not p.is_empty:
            out |= shapely.contains_xy(p, xs, ys)
    return out


# ---------------------------------------------------------------------------
# Stops
# ---------------------------------------------------------------------------

def _rep(poly) -> tuple[float, float]:
    pt = poly.representative_point()
    return (q(pt.x), q(pt.y))


def resolve_stop(c: Ctx, name: str, mode: str) -> Stop | None:
    m = c.m
    if name.endswith("_exit"):
        for n in m.road_nodes:
            if n.attrs.get("exit") == name:
                return Stop(name, (q(n.position[0]), q(n.position[1])), None, "exit")
        x0, y0, x1, y1 = m.bounds
        cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
        d = name[:-5]
        p = {"north": (cx, y1 - 5), "south": (cx, y0 + 5), "east": (x1 - 5, cy),
             "west": (x0 + 5, cy)}.get(d.split("_")[0], (cx, cy))
        return Stop(name, (q(p[0]), q(p[1])), None, "exit")
    sites = [s for s in m.megasites if s.name == name]
    dist = next((d for d in m.districts if d.name == name), None)
    if dist is not None and not sites:
        # a district's transit nexus is its station
        sites = [s for s in m.megasites if s.district_id == dist.id and
                 s.kind == "transit_nexus"]
    if sites:
        s = sites[0]
        area = G.from_model_poly(s.polygon)
        if dist is not None and s.name != name:
            area = G.from_model_poly(dist.polygon)  # a district reached by its nexus
        if s.kind == "transit_nexus":
            st = _nexus_stop(c, s, mode, name)
            if st is not None:
                st.area = area
                return st
        return Stop(name, _rep(G.from_model_poly(s.polygon)), s.district_id, "megasite",
                    area=area)
    if dist is not None:
        return Stop(name, _district_point(c, dist, mode), dist.id, "district",
                    area=G.from_model_poly(dist.polygon))
    place = next((p for p in m.places if p.name == name), None)
    if place is not None:
        p = place.label_at or _rep(G.from_model_poly(place.polygon))
        return Stop(name, (q(p[0]), q(p[1])), place.district_id, "place",
                    area=G.from_model_poly(place.polygon))
    isl = next((i for i in m.islands if i.name == name), None)
    if isl is not None:
        return Stop(name, _rep(G.from_model_poly(isl.polygon)), None, "island",
                    area=G.from_model_poly(isl.polygon))
    return None


def _nexus_stop(c: Ctx, site, mode: str, name: str) -> Stop | None:
    m = c.m
    members = set(site.member_ids)
    if mode == "sky_tube":
        for b in m.buildings:
            if b.id in members and b.attrs.get("mode") == "sky_tube":
                ext = [tuple(p) for p in b.footprint.exterior] if b.footprint else None
                if ext:
                    cx = sum(p[0] for p in ext) / len(ext)
                    cy = sum(p[1] for p in ext) / len(ext)
                    return Stop(name, (q(cx), q(cy)), site.district_id, "megasite",
                                z=b.attrs.get("sky_platform_z_m"), tower_id=b.id)
    want = "elevated_rail" if mode == "monorail" else mode
    for e in m.site_elements:
        if e.id in members and e.kind == "platform" and e.attrs.get("mode") in (mode, want):
            poly = G.from_model_poly(e.footprint)
            z = max((ms.z1_m for ms in e.masses), default=None)
            return Stop(name, _rep(poly), site.district_id, "megasite", z=z)
    if mode == "metro":
        return Stop(name, _rep(G.from_model_poly(site.polygon)), site.district_id, "megasite")
    return None


def _district_point(c: Ctx, d, mode: str, toward=None) -> tuple[float, float]:
    """The avenue (or street) junction nearest the district's representative point (the
    highway for the maglev); for a stop between two others (toward: the chord between them),
    the one nearest that chord, well inside the district (120 m for the lines along the
    avenues, 250 m for the others, less where the district is narrower: the curves fitted
    later pass inside the junction), so that the line serves the district on its way instead
    of detouring to its middle."""
    poly = G.from_model_poly(d.polygon)
    rp = poly.representative_point()
    if toward is not None:
        for inset in ((120.0, 60.0) if mode in ROAD_MODES else (250.0, 150.0, 60.0)):
            inner = G.qpoly(poly.buffer(-inset))
            if not inner.is_empty and inner.area > 4.0e4:
                poly = inner
                break
    want = {"maglev": ("highway", "avenue"), "metro": ("avenue", "street"),
            "sky_tube": ("avenue", "street")}.get(mode, ("avenue", "street"))
    ends: dict = {}
    for s in c.m.road_segments:
        if s.road_class in want and not s.bridge and \
                not any(z.z > 0.5 for z in s.z_profile):
            for p in (s.centerline[0], s.centerline[-1]):
                key = (q(p[0]), q(p[1]))
                ends[key] = min(ends.get(key, 9), want.index(s.road_class))
    best = None
    shapely.prepare(poly)
    for p, rank in sorted(ends.items()):
        if not poly.contains(Point(p)):
            continue
        if toward is not None:
            key = (round(toward.distance(Point(p)) + 150.0 * rank, 2), 0, p)
        else:
            key = (rank, round(_d(p, (rp.x, rp.y)), 2), p)
        if best is None or key < best:
            best = key
    return best[2] if best else (q(rp.x), q(rp.y))


# ---------------------------------------------------------------------------
# Raster
# ---------------------------------------------------------------------------

def base_z(mode: str, alt) -> float:
    lo, hi = alt
    if mode == "metro":
        return q((lo + hi) / 2.0)
    if mode == "sky_tube":
        return q(lo + 0.45 * (hi - lo))
    return q(lo + 0.3 * (hi - lo))


def sky_pass(b, z: float, alt: tuple, through: bool) -> str:
    """How a sky tube at base altitude z gets past a building in its corridor: "clear" (10 m
    over the roof), "portal" (through a tower, the track at least 8 m of headroom under its
    roof), "climb" (over it, within the altitude range) or "block". Where both a portal and
    a climb work, the one closer to z."""
    r = DECK_M["sky_tube"] / 2.0
    if b.top <= z - SKY_CLEAR_M or b.bottom >= z + 6.0:
        return "clear"
    portal = through and b.portal_ok and b.top >= alt[0] + r + PORTAL_HEADROOM_M
    climb = b.top <= alt[1] - SKY_CLEAR_M
    if portal and climb:
        return "climb" if b.top + SKY_CLEAR_M - z <= z - (b.top - r - PORTAL_HEADROOM_M) \
            else "portal"
    return "portal" if portal else "climb" if climb else "block"


def costs(c: Ctx, mode: str, z: float, through: bool, extra_block=None, hi: float = 0.0,
          lo: float = 0.0) -> tuple:
    """(cost per meter of each cell, portal cell mask). A building the line cannot clear at
    z but could by climbing (up to its altitude limit hi) costs CLIMB_W; one it can neither
    clear nor take out (nor pass through, sky tubes) is forbidden."""
    k = COSTS[mode]
    n = c.nx * c.ny
    cost = np.full(n, k["land"])
    cost = np.where(c.cls["open"], k["open"], cost)
    cost = np.where(c.cls["water"], k["water"], cost)
    cost = np.where(c.cls["minor"], k["minor"], cost)
    cost = np.where(c.cls["street"], k["street"], cost)
    cost = np.where(c.cls["highway"], k["highway"], cost)
    cost = np.where(c.cls["avenue"], k["avenue"], cost)
    if mode != "metro":
        cost = np.where(c.cls["raised"] & (c.road_z > z - below(mode) - ROAD_CLEAR_M),
                        k["raised"] * 3.0, cost)
    portal = np.zeros(n, bool)
    if mode == "metro" or c.btree is None:
        return cost, portal
    half = WIDTH_M[mode] / 2.0 + SIDE_PAD_M + 0.75 * CELL_M
    ip, ib = c.btree.query(c.pts, predicate="dwithin", distance=half)
    clear = below(mode) + 2.0 if mode != "sky_tube" else SKY_CLEAR_M
    clear_top = z - clear
    for p_, b_ in sorted(zip(ip.tolist(), ib.tolist())):
        b = c.blds[b_]
        if b.top <= clear_top or b.bottom >= z + 6.0:
            if cost[p_] < k["low"] and c.cls["onland"][p_] and not c.cls["water"][p_]:
                cost[p_] = max(cost[p_], k["low"])
            continue
        if mode == "sky_tube":
            how = sky_pass(b, z, (lo, hi), through)
            if how == "portal":
                portal[p_] = True
            else:
                cost[p_] = max(cost[p_], CLIMB_W) if how == "climb" else INF
            continue
        if b.removable:
            cost[p_] = max(cost[p_], k["tall"])
        else:
            cost[p_] = max(cost[p_], CLIMB_W) if b.top <= hi - clear else INF
    if mode == "sky_tube":
        cost = np.where(portal & np.isfinite(cost), k["portal"], cost)
    for poly, lim in c.cones:
        if z > lim:
            cost = np.where(shapely.contains_xy(poly, c.xs, c.ys), INF, cost)
    for line, z0, z1, cx, _, _ in c.skyb:
        if not cx or z1 < z - below(mode) - 2.0 or z0 > z + above(mode) + 4.0:
            continue
        hit = shapely.dwithin(line, c.pts, half)
        cost = np.where(hit, INF, cost)
    if extra_block is not None:
        cost = np.where(extra_block, INF, cost)
    return cost, portal


def cell_of(c: Ctx, p) -> int:
    i = min(max(int((p[0] - c.x0) // CELL_M), 0), c.nx - 1)
    j = min(max(int((p[1] - c.y0) // CELL_M), 0), c.ny - 1)
    return j * c.nx + i


def search(c: Ctx, cost: np.ndarray, a: int, b: int, turn: float, din=None
           ) -> list[int] | None:
    """A* from cell a to cell b (both always passable); 16 moves; a turn penalty for every
    change of direction above 45 degrees, from the arrival direction din at a (the previous
    leg's), so a line does not turn back at a stop."""
    nx, ny = c.nx, c.ny
    cl = cost.tolist()
    cl[a] = min(cl[a], 2.0) if cl[a] == INF else cl[a]
    cl[b] = min(cl[b], 2.0) if cl[b] == INF else cl[b]
    bx, by = b % nx, b // nx
    cmin = min(x for x in cl if x > 0)
    d0 = -1
    if din is not None:
        d0 = max(range(len(_MOVES)), key=lambda k: ((_MOVES[k][0] * din[0] + _MOVES[k][1] *
                                                      din[1]) / _MOVES[k][2], -k))
    start = (a, d0)
    g = {start: 0.0}
    came: dict = {}
    heap = [(0.0, 0, a, d0)]
    cnt = 1
    done = set()
    while heap:
        _, _, u, du = heapq.heappop(heap)
        key = (u, du)
        if key in done:
            continue
        done.add(key)
        if u == b:
            path = [u]
            while key in came:
                key = came[key]
                path.append(key[0])
            return path[::-1]
        ux, uy = u % nx, u // nx
        gu = g[key]
        for k, (dx, dy, L) in enumerate(_MOVES):
            vx, vy = ux + dx, uy + dy
            if vx < 0 or vy < 0 or vx >= nx or vy >= ny:
                continue
            v = vy * nx + vx
            cv = cl[v]
            if cv == INF:
                continue
            step = L * CELL_M * (cl[u] + cv) / 2.0
            if du >= 0 and turn > 0:
                ddx, ddy, dL = _MOVES[du]
                cosang = (ddx * dx + ddy * dy) / (dL * L)
                if cosang < 0.70:
                    step += turn * (1.0 - cosang)
            nk = (v, k)
            nd = gu + step
            if nd < g.get(nk, INF):
                g[nk] = nd
                came[nk] = key
                h = math.sqrt((vx - bx) ** 2 + (vy - by) ** 2) * CELL_M * cmin
                heapq.heappush(heap, (nd + h, cnt, v, k))
                cnt += 1
    return None


def cell_xy(c: Ctx, k: int) -> tuple[float, float]:
    return (float(c.xs[k]), float(c.ys[k]))


# ---------------------------------------------------------------------------
# Fitting
# ---------------------------------------------------------------------------

def simplify_runs(pts: list[tuple], fixed: set[int], tol: float) -> tuple[list, set]:
    keep = sorted(set(fixed) | {0, len(pts) - 1})
    out = [tuple(pts[0])]
    new_fixed = {0}
    for a, b in zip(keep, keep[1:]):
        run = pts[a:b + 1]
        s = list(LineString(run).simplify(tol, preserve_topology=False).coords) \
            if len(run) > 2 else run
        out += [(G.q(p[0]), G.q(p[1])) for p in s[1:]]
        new_fixed.add(len(out) - 1)
    return out, new_fixed


ATTEMPTS = 4      # routes per line: the first, then rerouted around what it could not pass
SPAN = 3          # radius measured through points SPAN vertices apart (10 m spacing: 30 m)


def resample(pts: list[tuple], step: float = 10.0, closed: bool = False) -> list[tuple]:
    """Points every `step` m along the polyline (the last one kept)."""
    if closed and pts[0] != pts[-1]:
        pts = pts + [pts[0]]
    cum = [0.0]
    for a, b in zip(pts, pts[1:]):
        cum.append(cum[-1] + _d(a, b))
    L = cum[-1]
    n = max(2, int(round(L / step)))
    out = []
    j = 0
    for k in range(n + (0 if closed else 1)):
        s = L * k / n
        while j < len(cum) - 2 and cum[j + 1] < s:
            j += 1
        seg = cum[j + 1] - cum[j]
        f = 0.0 if seg <= 0 else (s - cum[j]) / seg
        a, b = pts[j], pts[j + 1]
        out.append((a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f))
    return out


def circumradius(a, b, c) -> float:
    """Radius of the circle through three points (inf when they are collinear)."""
    ab, bc, ca = _d(a, b), _d(b, c), _d(c, a)
    cross = (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])
    if abs(cross) < 1e-9:
        return INF
    return ab * bc * ca / (2.0 * abs(cross))


def radii(pts: list[tuple], closed: bool) -> list[float]:
    n = len(pts)
    out = [INF] * n
    for i in range(n):
        if closed:
            a, c = pts[(i - SPAN) % n], pts[(i + SPAN) % n]
        else:
            if i - SPAN < 0 or i + SPAN >= n:
                continue
            a, c = pts[i - SPAN], pts[i + SPAN]
        out[i] = circumradius(a, pts[i], c)
    return out


def _turn_info(pts, i: int, closed: bool) -> tuple[float, float]:
    """(turn angle in radians, side: +1 left, -1 right, 0 none) at vertex i."""
    n = len(pts)
    if not closed and (i == 0 or i == n - 1):
        return 0.0, 0.0
    a, b, c = pts[(i - 1) % n], pts[i], pts[(i + 1) % n]
    ux, uy = b[0] - a[0], b[1] - a[1]
    vx, vy = c[0] - b[0], c[1] - b[1]
    nu, nv = math.sqrt(ux * ux + uy * uy), math.sqrt(vx * vx + vy * vy)
    if nu < 1e-9 or nv < 1e-9:
        return 0.0, 0.0
    cos = max(-1.0, min(1.0, (ux * vx + uy * vy) / (nu * nv)))
    cross = ux * vy - uy * vx
    return float(M.acos(cos)), (1.0 if cross > 0 else -1.0 if cross < 0 else 0.0)


def _tangent(theta: float, r: float) -> float:
    if theta <= M.radians(0.5):
        return 0.0
    if theta >= M.radians(178.0):
        return INF
    return r * float(M.tan(theta / 2.0))


def _intersect(p1, p2, p3, p4):
    """Where line p1-p2 meets line p3-p4 (None when parallel)."""
    d = (p2[0] - p1[0]) * (p4[1] - p3[1]) - (p2[1] - p1[1]) * (p4[0] - p3[0])
    if abs(d) < 1e-9:
        return None
    t = ((p3[0] - p1[0]) * (p4[1] - p3[1]) - (p3[1] - p1[1]) * (p4[0] - p3[0])) / d
    return (p1[0] + (p2[0] - p1[0]) * t, p1[1] + (p2[1] - p1[1]) * t)


def _corner_arc(a, p, c, r: float, t: float | None = None) -> list[tuple]:
    """The fillet of radius r at corner p (between a and c) as points; the tangent length
    is r tan(turn / 2), at most 95% of the shorter run."""
    th, _ = _turn_info([a, p, c], 1, False)
    h = float(M.tan(th / 2.0)) if th > M.radians(0.5) else 0.0
    if h <= 0.0 or th >= M.radians(178.0):
        return [a, p, c]
    if t is None:
        t = min(r * h, 0.95 * min(_d(a, p), _d(p, c)))
    line = _arc_line([a, p, c], [None, t / h, None], [0.0, t, 0.0], False)
    return [tuple(x) for x in line.coords] if not line.is_empty else [a, p, c]


def _arcs_clear(pts, k: int, closed: bool, r: float, ok_cut) -> bool:
    """With vertex k gone, the arcs of radius r at its two neighbors pass ok_cut."""
    rest = pts[:k] + pts[k + 1:]
    m = len(rest)
    for j in ((k - 1) % m, k % m) if closed else (k - 1, k):
        if not closed and (j <= 0 or j >= m - 1):
            continue
        if not ok_cut(_corner_arc(rest[(j - 1) % m], rest[j], rest[(j + 1) % m], r)):
            return False
    return True


def arc_path(pts: list[tuple], r_min: float, closed: bool, ok_cut, max_dev: float,
             pins=frozenset()) -> tuple[list[tuple], float]:
    """Straight runs joined by arcs of 1.15 r_min (more where there is room) at every corner
    of pts. Where two corners' tangents do not fit on the run between them, corners turning
    the same way merge into one where their outer runs meet (the line takes a wider curve,
    at most max_dev from the corners it replaces); otherwise the vertex turning less goes
    (an S-bend straightens, a spur where the route turns back is cut). Every change must
    pass ok_cut(new runs); the points in pins (station platforms) stay. Returns the track and
    its smallest arc radius."""
    r_use = 1.15 * r_min
    r_low = 1.05 * r_min    # (an arc as a polyline measures a little tighter)
    pts = [tuple(p) for p in pts]
    if closed and pts[0] == pts[-1]:
        pts = pts[:-1]
    stuck: set = set()
    for _ in range(6 * len(pts) + 10):
        n = len(pts)
        if n < (4 if closed else 3):
            break
        info = [_turn_info(pts, i, closed) for i in range(n)]
        tan = [_tangent(t, r_use) for t, _ in info]
        worst = None
        for i in range(n if closed else n - 1):
            j = (i + 1) % n
            slack = _d(pts[i], pts[j]) - tan[i] - tan[j]
            if slack < -1e-6 and (pts[i], pts[j]) not in stuck and \
                    (worst is None or slack < worst[0]):
                worst = (slack, i, j)
        if worst is None:
            break
        _, i, j = worst
        done = False
        (ti, si), (tj, sj) = info[i], info[j]
        inner = closed or (0 < i and j < n - 1)
        if inner and si == sj and si != 0 and ti < M.radians(170) and tj < M.radians(170) \
                and pts[i] not in pins and pts[j] not in pins:
            x = _intersect(pts[(i - 1) % n], pts[i], pts[j], pts[(j + 1) % n])
            if x is not None and _d(x, pts[i]) <= max_dev and _d(x, pts[j]) <= max_dev:
                x = (G.q(x[0]), G.q(x[1]))
                prv, nxt = pts[(i - 1) % n], pts[(j + 1) % n]
                if ok_cut([prv, x, nxt]) and ok_cut(_corner_arc(prv, x, nxt, r_low)):
                    if closed and j == 0:
                        pts = [x] + pts[1:i]
                    else:
                        pts = pts[:i] + [x] + pts[j + 1:]
                    done = True
        if not done:
            order = sorted([k for k in (i, j) if (closed or 0 < k < n - 1) and
                            pts[k] not in pins],
                           key=lambda k: (info[k][0], k))
            for k in order:
                if ok_cut([pts[(k - 1) % n], pts[(k + 1) % n]]) and \
                        _arcs_clear(pts, k, closed, r_low, ok_cut):
                    del pts[k]
                    done = True
                    break
        if not done:
            stuck.add((pts[i], pts[j]))  # (the arcs there come out tighter)
    rads, tans = _fillet_radii(pts, r_use, closed, r_min)
    # an arc cutting inside its corner into what the line cannot pass: the tightest curve
    # allowed there (it stays nearer the corner)
    n = len(pts)
    for i in range(n):
        r = rads[i]
        if r is None or r <= r_low or (not closed and (i == 0 or i == n - 1)):
            continue
        a, p, c = pts[(i - 1) % n], pts[i], pts[(i + 1) % n]
        if not ok_cut(_corner_arc(a, p, c, r, tans[i])):
            rads[i], tans[i] = r_low, tans[i] * r_low / r
    line = _arc_line(pts, rads, tans, closed)
    used = [r for r in rads if r is not None]
    if line.is_empty:
        return [tuple(p) for p in pts], (min(used) if used else INF)
    coords = [(G.q(x), G.q(y)) for x, y in line.coords]
    out = [coords[0]]
    for p in coords[1:]:
        if p != out[-1]:
            out.append(p)
    return out, (min(used) if used else INF)


# ---------------------------------------------------------------------------
# Lines
# ---------------------------------------------------------------------------

@dataclass
class Line:
    id: str
    name: str
    mode: str
    color: str
    loop: bool
    alt: tuple[float, float]
    z0: float
    through: bool
    stops: list = field(default_factory=list)
    pts: list = field(default_factory=list)      # 2D, dense (<= 10 m)
    zs: list = field(default_factory=list)
    stop_at: list = field(default_factory=list)  # index of each stop in pts
    min_radius: float = INF
    removed: list = field(default_factory=list)
    portals: dict = field(default_factory=dict)  # building id -> (z0, z1)
    conflicts: list = field(default_factory=list)
    notes: list = field(default_factory=list)
    names: set = field(default_factory=set)      # station names used on the line


def _densify(pts, step: float = 10.0) -> list[tuple]:
    out = [tuple(pts[0])]
    for a, b in zip(pts, pts[1:]):
        L = _d(a, b)
        n = max(1, int(math.ceil(L / step)))
        for k in range(1, n + 1):
            f = k / n
            p = (G.q(a[0] + (b[0] - a[0]) * f), G.q(a[1] + (b[1] - a[1]) * f))
            if p != out[-1]:
                out.append(p)
    return out


class RoadGraph:
    """The road network as a graph for one mode: edges are the segments of the classes the
    mode runs along (raised sections, not bridges, cost more for rail and monorail)."""

    def __init__(self, c: Ctx, mode: str):
        w = ROAD_W[mode]
        self.pos = {n.id: (n.position[0], n.position[1]) for n in c.m.road_nodes}
        self.adj: dict = {}
        self.major: set = set()     # nodes on avenues and highways
        for k, s in enumerate(c.m.road_segments):
            if s.road_class not in w:
                continue
            pts = [tuple(p) for p in s.centerline]
            a = self.pos.get(s.start)
            if a is not None and _d(pts[-1], a) < _d(pts[0], a):
                pts = pts[::-1]
            raised = not s.bridge and any(z.z > 0.5 for z in s.z_profile)
            wt = _plen(pts) * w[s.road_class] * (RAISED_W if raised and mode != "maglev"
                                                  else 1.0)
            self.adj.setdefault(s.start, []).append((s.end, k, wt, pts))
            self.adj.setdefault(s.end, []).append((s.start, k, wt, pts[::-1]))
            if s.road_class in ("avenue", "highway"):
                self.major.update((s.start, s.end))
        for key in self.adj:
            self.adj[key].sort(key=lambda e: (e[0], e[1]))
        self.turn = TURN_M[mode]

    def node_near(self, st: Stop, c: Ctx, limit: float = 450.0) -> str | None:
        """The graph node nearest the stop, in its district first; for a megasite, on an
        avenue or highway within reach of its station first (the service roads around the
        site have corners too tight for a train)."""
        dpoly = next((G.from_model_poly(d.polygon) for d in c.m.districts
                      if d.id == st.district_id), None)
        zone = _zone(st) if st.kind == "megasite" else None
        best = None
        for nid in sorted(self.adj):
            x = self.pos[nid]
            d = _d(x, st.p)
            if d > limit:
                continue
            inside = 0 if dpoly is None or dpoly.covers(Point(x)) else 1
            side = 0 if zone is None or (nid in self.major and zone.covers(Point(x))) else 1
            key = (inside, side, round(d, 2), nid)
            if best is None or key < best:
                best = key
        return best[3] if best else None

    @staticmethod
    def _dir(pts, rev: bool = False):
        """Unit direction over the first 15 m of pts (or the last, rev)."""
        seq = pts[::-1] if rev else pts
        if len(seq) < 2:
            return (1.0, 0.0)
        a = seq[0]
        for b in seq[1:]:
            if _d(a, b) >= 15.0:
                break
        L = _d(a, b) or 1.0
        u = ((b[0] - a[0]) / L, (b[1] - a[1]) / L)
        return (-u[0], -u[1]) if rev else u

    def route(self, a: str, b: str, din=None, used=frozenset()) -> list | None:
        """Cheapest path a to b (node ids) with a turn penalty at every node, starting in
        direction din (the previous leg's arrival); the polyline."""
        heap = [(0.0, 0, a, -1)]
        best = {(a, -1): 0.0}
        came: dict = {}
        arrive: dict = {(a, -1): din}
        cnt = 1
        done = set()
        while heap:
            g, _, u, ku = heapq.heappop(heap)
            key = (u, ku)
            if key in done:
                continue
            done.add(key)
            if u == b:
                runs, ks = self._chain(came, key)
                return self._join(runs), ks
            din = arrive[key]
            for v, k, wt, pts in self.adj.get(u, ()):
                if k == ku:
                    continue
                step = wt * (REUSE_W if k in used else 1.0)
                if din is not None:
                    dout = self._dir(pts)
                    cosang = max(-1.0, min(1.0, din[0] * dout[0] + din[1] * dout[1]))
                    if cosang < 0.94:
                        step += self.turn * (1.0 - cosang)
                nk = (v, k)
                nd = g + step
                if nd < best.get(nk, INF):
                    best[nk] = nd
                    came[nk] = (key, pts)
                    arrive[nk] = self._dir(pts, rev=True)
                    heapq.heappush(heap, (nd, cnt, v, k))
                    cnt += 1
        return None

    @staticmethod
    def _chain(came, key) -> tuple[list, set]:
        runs, ks = [], set()
        while key in came:
            ks.add(key[1])
            key, pts = came[key]
            runs.append(pts)
        return runs[::-1], ks

    @staticmethod
    def _join(runs) -> list:
        out = []
        for pts in runs:
            for p in pts:
                if not out or _d(out[-1], p) > 0.01:
                    out.append(p)
        return out


def snap_cell(c: Ctx, cost, p) -> int:
    """The cell of p, or the nearest passable one (ties by index)."""
    k = cell_of(c, p)
    if cost[k] != INF:
        return k
    i0, j0 = k % c.nx, k // c.nx
    for r in range(1, 40):
        cands = []
        for j in range(max(0, j0 - r), min(c.ny, j0 + r + 1)):
            for i in range(max(0, i0 - r), min(c.nx, i0 + r + 1)):
                kk = j * c.nx + i
                if cost[kk] != INF:
                    cands.append((round(_d(cell_xy(c, kk), p), 2), kk))
        if cands:
            return min(cands)[1]
    return k


def route_line(c: Ctx, ln: Line) -> None:
    """The track: the stops in districts between two others moved toward the line's way
    first; where that leaves a stop unserved, again from the district points, and the
    route that serves more stops."""
    mode = ln.mode
    stops = ln.stops
    dist = {d.id: d for d in c.m.districts}
    home = [s.p for s in stops]
    for k in range(1, len(stops) - 1):
        st = stops[k]
        # (a loop keeps its stops: the chord between its neighbors crosses the loop)
        if not ln.loop and st.kind == "district" and st.z is None and \
                st.district_id in dist:
            chord = LineString([stops[k - 1].p, stops[k + 1].p])
            if chord.length > 1.0:
                st.p = _district_point(c, dist[st.district_id], mode, chord)
    moved = [s.p for s in stops]
    notes, conflicts = list(ln.notes), list(ln.conflicts)
    _route(c, ln)

    def missed():
        return sum(1 for s in stops if not _served(ln.pts, s))
    if moved == home or not missed():
        return
    first = (ln.pts, ln.min_radius, ln.stop_at, ln.notes, ln.conflicts, missed())
    for s, p in zip(stops, home):
        s.p = p
    ln.notes, ln.conflicts = list(notes), list(conflicts)
    _route(c, ln)
    if missed() >= first[5]:
        ln.pts, ln.min_radius, ln.stop_at, ln.notes, ln.conflicts = first[:5]
        for s, p in zip(stops, moved):
            s.p = p


def _route(c: Ctx, ln: Line) -> None:
    mode = ln.mode
    stops = ln.stops
    pre = presets.TRANSIT_MODES[mode]
    r_min = pre.min_curve_radius_m or 0.0
    graph = RoadGraph(c, mode) if mode in ROAD_MODES else None
    block = None
    dense, rmin, ok = [], INF, True
    for attempt in range(ATTEMPTS):
        cost, portal = costs(c, mode, ln.z0, ln.through, block, ln.alt[1], ln.alt[0])
        if graph is None:
            # a stop in a forbidden area (a flight cone, a tower the line cannot pass) moves
            # to the nearest passable cell; its station goes there
            for st in stops:
                k = cell_of(c, st.p)
                if cost[k] == INF:
                    st.p = cell_xy(c, snap_cell(c, cost, st.p))
                    st.p = (G.q(st.p[0]), G.q(st.p[1]))
        raw: list = []
        at_stop = {0}
        hit = [0]       # the index in raw where the route reaches each stop
        din = None
        used_segs: set = set()
        used_cells = np.zeros(c.nx * c.ny, bool)
        for a, b in zip(stops, stops[1:]):
            run = None
            if graph is not None:
                na, nb = graph.node_near(a, c), graph.node_near(b, c)
                if na is not None and nb is not None:
                    # a road-following line stops on the road: at the node nearest the stop
                    # (beside a megasite or a nexus platform, not inside it)
                    res = graph.route(na, nb, din, used_segs) if na != nb else \
                        ([graph.pos[na]], set())
                    run = None
                    if res is not None:
                        run, ks = res
                        used_segs |= ks
            if run is None:
                leg_cost = cost
                if used_cells.any():
                    near_ends = shapely.dwithin(Point(a.p), c.pts, 2 * REUSE_PAD_M) | \
                        shapely.dwithin(Point(b.p), c.pts, 2 * REUSE_PAD_M)
                    leg_cost = np.where(used_cells & ~near_ends, cost * REUSE_W, cost)
                path = search(c, leg_cost, snap_cell(c, cost, a.p), snap_cell(c, cost, b.p),
                              TURN_COST_M.get(mode, 0.0), din)
                if path is None:
                    ln.notes.append(f"{ln.name}: no route from {a.name} to {b.name}")
                    ok = False
                    path = [cell_of(c, a.p), cell_of(c, b.p)]
                run = [a.p] + [cell_xy(c, k) for k in path] + [b.p]
                if len(run) >= 2:
                    used_cells |= shapely.dwithin(LineString(run), c.pts, REUSE_PAD_M)
            for p in run:
                if not raw or _d(raw[-1], p) > 0.01:
                    raw.append((G.q(p[0]), G.q(p[1])))
            at_stop.add(len(raw) - 1)
            hit.append(len(raw) - 1)
            if len(raw) >= 2:
                din = RoadGraph._dir(raw, rev=True)
        if ln.loop and raw[0] != raw[-1]:
            raw.append(raw[0])
            at_stop.add(len(raw) - 1)
        # simplified between stops (a loop would collapse as one run), then arcs at the
        # mode's radius with only the ends fixed: curves may pass beside a stop
        pts, _ = simplify_runs(raw, at_stop, SIMPLIFY_M[mode])
        if r_min > 0:
            def ok_cut(run, cost=cost):
                for p, r in zip(run, run[1:]):
                    if graph is not None:
                        if not _segment_clear(c, ln, p, r):
                            return False
                    elif not _segment_free(c, cost, p, r):
                        return False
                return True
            fitted, rmin = arc_path(pts, r_min, ln.loop, ok_cut, 2.0 * r_min)
            # a platform (a nexus) the curves cut away stays on the track
            # a stop the curves cut away keeps the point where the route reached it
            pins = frozenset(raw[i] for s, i in zip(stops, hit) if not _served(fitted, s))
            if pins:
                fitted, rmin = arc_path(pts, r_min, ln.loop, ok_cut, 2.0 * r_min, pins)
            if ln.loop and fitted[0] != fitted[-1]:
                fitted = fitted + [fitted[0]]
            dense = _densify(fitted)
        else:
            dense, rmin = _densify(pts), INF
        conflicts = _corridor(c, ln, dense, check_only=True)
        if not conflicts or attempt == ATTEMPTS - 1 or graph is not None:
            break
        # wider each time: the curves fitted to the route cut inside its corners
        block = np.zeros(c.nx * c.ny, bool) if block is None else block
        for b in conflicts:
            block |= shapely.dwithin(b.poly, c.pts, WIDTH_M[mode] / 2.0 + SIDE_PAD_M +
                                     CELL_M * (1 + 2 * attempt))
        ln.notes.append(f"{ln.name}: rerouted around {len(conflicts)} building(s)")
    if ln.loop and r_min > 0 and rmin < r_min - 0.5 and len(stops) >= 3:
        alt = _hull_loop(c, ln, cost, r_min)
        if alt is not None and alt[1] > rmin and all(_served(alt[0], s) for s in stops):
            dense, rmin = alt
            ln.notes.append(f"{ln.name}: loop drawn around its stops (their order makes "
                            f"turns tighter than {r_min:g} m)")
    ln.pts = dense
    ln.min_radius = rmin
    ln.stop_at = [stop_index(dense, s) for s in stops]
    for s, i in zip(stops, ln.stop_at):
        zone = _zone(s)
        if zone is not None and not zone.covers(Point(dense[i])):
            ln.notes.append(f"{ln.name}: the track passes {zone.distance(Point(dense[i])):.0f} m "
                            f"from {s.name} (its {r_min:g} m curves cut the turn there; a "
                            f"route that runs through its stops keeps them)")
    if not ok:
        ln.conflicts.append("route")


def _hull_loop(c: Ctx, ln: Line, cost, r_min: float):
    """A loop around its stops: the outline of their convex hull widened by 1.1 r_min
    (every curve of it at least that wide), as waypoints every 120 m routed on the raster
    around what the line cannot pass, then arcs."""
    hull = shapely.convex_hull(shapely.multipoints([s.p for s in ln.stops]))
    ring = G.qpoly(hull.buffer(1.1 * r_min, quad_segs=16))
    if ring.is_empty:
        return None
    ring = shapely.geometry.polygon.orient(G.parts(ring)[0], 1.0)
    way = resample([tuple(p) for p in ring.exterior.coords][:-1], 120.0, True)
    first = ln.stops[0].p
    k0 = min(range(len(way)), key=lambda i: (round(_d(way[i], first), 3), i))
    way = way[k0:] + way[:k0]
    raw = []
    for a, b in zip(way, way[1:] + way[:1]):
        path = search(c, cost, snap_cell(c, cost, a), snap_cell(c, cost, b), 0.0)
        run = [cell_xy(c, k) for k in path] if path else [a, b]
        for p in run:
            if not raw or _d(raw[-1], p) > 0.01:
                raw.append((G.q(p[0]), G.q(p[1])))
    pts, _ = simplify_runs(raw + [raw[0]], {0}, SIMPLIFY_M[ln.mode])

    def ok_cut(run):
        return all(_segment_free(c, cost, p, r) for p, r in zip(run, run[1:]))
    fitted, rmin = arc_path(pts, r_min, True, ok_cut, 2.0 * r_min)
    if fitted[0] != fitted[-1]:
        fitted = fitted + [fitted[0]]
    return _densify(fitted), rmin


def _segment_clear(c: Ctx, ln: Line, p, r) -> bool:
    """A road-following shortcut is allowed when it passes no building the line could not
    take out (landmarks, complexes, megasites taller than its deck)."""
    if c.btree is None:
        return True
    seg = LineString([p, r])
    half = WIDTH_M[ln.mode] / 2.0 + SIDE_PAD_M
    clear_top = ln.z0 - below(ln.mode) - 2.0
    for i in c.btree.query(seg, predicate="dwithin", distance=half).tolist():
        b = c.blds[i]
        if not b.removable and b.top > clear_top and b.bottom < ln.z0 + 6.0:
            return False
    return True


def _segment_free(c: Ctx, cost, p, r) -> bool:
    """A raster shortcut is allowed when no sample on it lies in a forbidden cell."""
    L = _d(p, r)
    n = max(2, int(L / (CELL_M / 2)) + 1)
    for k in range(n + 1):
        f = k / n
        if cost[cell_of(c, (p[0] + (r[0] - p[0]) * f, p[1] + (r[1] - p[1]) * f))] == INF:
            return False
    return True


SERVE_M = 150.0  # a station within this of a stop's district, site or place serves it


def _zone(s: Stop):
    """Where a station serves the stop: in its district, within SERVE_M of anything else."""
    if s.area is None or s.area.is_empty:
        return None
    return G.qpoly(s.area.buffer(SERVE_M) if s.kind != "district" else s.area)


def _served(pts, s: Stop) -> bool:
    zone = _zone(s)
    if zone is None:
        return True
    return bool(shapely.covers(zone, shapely.points(np.array(pts, dtype=np.float64))).any())


def stop_index(pts, s: Stop) -> int:
    """The track vertex for a stop's station: the one nearest the stop point among those in
    (or within SERVE_M of) what the stop names, else the nearest overall."""
    zone = _zone(s)
    if zone is not None:
        arr = shapely.points(np.array(pts, dtype=np.float64))
        inside = np.nonzero(shapely.covers(zone, arr))[0].tolist()
        if inside:
            return min(inside, key=lambda i: (round(_d(pts[i], s.p), 3), i))
    return _nearest_index(pts, s.p)


def _nearest_index(pts, p) -> int:
    best = None
    for i, x in enumerate(pts):
        d = round(_d(x, p), 3)
        if best is None or d < best[0]:
            best = (d, i)
    return best[1]


def _corridor(c: Ctx, ln: Line, pts, check_only: bool = False) -> list:
    """Buildings in the line's corridor that it cannot pass: removable ones are taken out
    (elevated modes), towers become portals (sky tubes through towers); the rest are
    returned as conflicts."""
    mode = ln.mode
    if mode == "metro" or c.btree is None or len(pts) < 2:
        return []
    line = LineString(pts)
    half = WIDTH_M[mode] / 2.0 + SIDE_PAD_M
    z = ln.z0
    clear_top = z - below(mode) - 2.0 if mode != "sky_tube" else z - SKY_CLEAR_M
    out = []
    for i in sorted(c.btree.query(line, predicate="dwithin", distance=half).tolist()):
        b = c.blds[i]
        if b.top <= clear_top or b.bottom >= z + 6.0:
            continue
        climbable = b.top <= ln.alt[1] - (SKY_CLEAR_M if mode == "sky_tube" else
                                          below(mode) + 2.0)
        if mode == "sky_tube":
            how = sky_pass(b, z, ln.alt, ln.through)
            if how == "portal" and not check_only:
                ln.portals[b.id] = (q(z - DECK_M[mode] / 2 - 1.0),
                                    q(z + DECK_M[mode] / 2 + 1.0))
            elif how == "block":
                out.append(b)
            continue
        if b.removable:
            if not check_only:
                ln.removed.append(b.id)
            continue
        if not climbable:
            out.append(b)
    return out


def _fit_portals(c: Ctx, ln: Line) -> bool:
    """Portal heights from the final profile (the track may have climbed since the corridor
    was laid out). A tower the tube no longer fits through (headroom 8 m, or the tube now
    over its roof) loses its portal; True when one did, so the profile is redone with the
    line climbing over it."""
    if not ln.portals:
        return False
    bld = {b.id: b for b in c.blds}
    arr = shapely.points(np.array(ln.pts, dtype=np.float64))
    half = WIDTH_M[ln.mode] / 2.0 + SIDE_PAD_M
    r = DECK_M[ln.mode] / 2.0
    misfit = []
    for bid in sorted(ln.portals):
        b = bld[bid]
        idx = np.nonzero(shapely.dwithin(b.poly, arr, half))[0].tolist()
        if not idx:
            del ln.portals[bid]
            continue
        z0 = min(ln.zs[i] for i in idx)
        z1 = max(ln.zs[i] for i in idx)
        if b.top >= z1 + r + PORTAL_HEADROOM_M - 0.01 and b.bottom <= z0 - r - 1.0:
            ln.portals[bid] = (q(z0 - r - 1.0), q(z1 + r + 1.0))
        elif b.top <= z0 - SKY_CLEAR_M + 0.01:
            del ln.portals[bid]  # the track clears it after all
        else:
            misfit.append((b.top, bid))
    if not misfit:
        return False
    # the lowest tower that does not fit goes first: the line climbs over it, which may
    # leave room for the others
    del ln.portals[min(misfit)[1]]
    return True


def clearance_conflicts(c: Ctx, ln: Line, gone: set) -> list[str]:
    """Buildings left in the corridor that the track at its final height does not clear:
    deck underside 2 m over the roof (elevated), 10 m (sky lines), unless a portal."""
    mode = ln.mode
    if mode == "metro" or c.btree is None or len(ln.pts) < 2:
        return []
    arr = shapely.points(np.array(ln.pts, dtype=np.float64))
    half = WIDTH_M[mode] / 2.0 + SIDE_PAD_M
    clear = SKY_CLEAR_M if mode == "sky_tube" else 2.0 + below(mode)
    out = set()
    ip, ib = c.btree.query(arr, predicate="dwithin", distance=half)
    for i, b_ in zip(ip.tolist(), ib.tolist()):
        b = c.blds[b_]
        if b.id in gone or b.id in ln.portals:
            continue
        z = ln.zs[i]
        if b.top > z - clear + 0.01 and b.bottom < z + 6.0:
            out.add(b.id)
    return sorted(out)


def profile(c: Ctx, ln: Line, gone: set) -> None:
    """z at every vertex: the base altitude, raised over navigable water, road decks, the
    buildings left under the line and nexus platforms, then smoothed to the maximum grade."""
    mode = ln.mode
    n = len(ln.pts)
    if mode == "metro":
        ln.zs = [ln.z0] * n
        return
    deck = below(mode)
    need = [ln.z0] * n
    arr = shapely.points(np.array(ln.pts, dtype=np.float64))
    for poly, clr, nav in c.water:
        if not nav:
            continue
        for i in np.nonzero(shapely.contains(poly, arr))[0].tolist():
            need[i] = max(need[i], clr + deck + 1.0)
    for i, z in deck_heights(c.decks, c.dtree, arr, WIDTH_M[mode] / 2.0):
        need[i] = max(need[i], z + ROAD_CLEAR_M + deck)
    if c.btree is not None:
        half = WIDTH_M[mode] / 2.0 + SIDE_PAD_M
        ip, ib = c.btree.query(arr, predicate="dwithin", distance=half)
        clear = SKY_CLEAR_M if mode == "sky_tube" else 2.0 + deck
        for i, b_ in sorted(zip(ip.tolist(), ib.tolist())):
            b = c.blds[b_]
            if b.id in gone or b.id in ln.portals or b.bottom >= ln.z0 + 6.0:
                continue
            need[i] = max(need[i], b.top + clear)
    for s, i in zip(ln.stops, ln.stop_at):
        if s.z is not None:
            need[i] = max(need[i], s.z + (0.0 if mode == "sky_tube" else 1.0))
    # upper bounds: the towers a sky tube passes through (8 m of headroom under the roof)
    cap = [INF] * n
    # the skybridges of complexes (kept): over or under, whichever is nearer the base
    # altitude, 3 m clear
    for line, z0, z1, cx, _, w in c.skyb:
        if not cx:
            continue
        reach = WIDTH_M[mode] / 2.0 + SIDE_PAD_M + w / 2.0
        idx = np.nonzero(shapely.dwithin(line, arr, reach))[0].tolist()
        if not idx:
            continue
        over = z1 + below(mode) + 3.0 + 0.01
        under = z0 - above(mode) - 3.0 - 0.01
        if under >= ln.z0 or over <= ln.z0:
            continue    # the track passes under or over it at its base altitude
        for i in idx:
            if over - ln.z0 <= ln.z0 - under:
                need[i] = max(need[i], over)
            else:
                cap[i] = min(cap[i], under)
    if ln.portals and c.btree is not None:
        r = DECK_M[mode] / 2.0
        for i, b_ in sorted(zip(ip.tolist(), ib.tolist())):
            b = c.blds[b_]
            if b.id in ln.portals:
                cap[i] = min(cap[i], b.top - r - PORTAL_HEADROOM_M)
    # both envelopes limited to the grade, then the base altitude between them (a clamp
    # between two functions of bounded slope keeps that slope); the lower one wins where
    # they cross (the portal there is then dropped)
    g = (presets.TRANSIT_MODES[mode].max_grade or 0.05) * 0.95
    lo, hi = list(need), list(cap)
    for i in range(1, n):
        L = g * _d(ln.pts[i - 1], ln.pts[i])
        lo[i] = max(lo[i], lo[i - 1] - L)
        hi[i] = min(hi[i], hi[i - 1] + L)
    for i in range(n - 2, -1, -1):
        L = g * _d(ln.pts[i], ln.pts[i + 1])
        lo[i] = max(lo[i], lo[i + 1] - L)
        hi[i] = min(hi[i], hi[i + 1] + L)
    ln.zs = [q(max(a, min(b, ln.z0))) for a, b in zip(lo, hi)]


# ---------------------------------------------------------------------------
# Stations, structures, walkways
# ---------------------------------------------------------------------------

def _cum(pts) -> list[float]:
    s = [0.0]
    for a, b in zip(pts, pts[1:]):
        s.append(s[-1] + _d(a, b))
    return s


def _at(pts, cum, s) -> tuple[int, tuple[float, float]]:
    s = min(max(s, 0.0), cum[-1])
    for i in range(len(pts) - 1):
        if cum[i + 1] >= s:
            L = cum[i + 1] - cum[i]
            f = 0.0 if L <= 0 else (s - cum[i]) / L
            a, b = pts[i], pts[i + 1]
            return i, (G.q(a[0] + (b[0] - a[0]) * f), G.q(a[1] + (b[1] - a[1]) * f))
    return len(pts) - 1, pts[-1]


def _spot_name(c: Ctx, p, ln: Line) -> str:
    """A station between stops: named after a place within 250 m, else its district (then
    numbered when the line has one of that name already)."""
    m = c.m
    best = None
    for pl in m.places:
        if pl.label_at is not None:
            d = round(_d(p, pl.label_at), 2)
            if d <= 250.0 and (best is None or (d, pl.name) < best):
                best = (d, pl.name)
    if best is not None:
        name = best[1]
    else:
        pt = Point(p)
        name = next((d.name for d in m.districts if G.from_model_poly(d.polygon).covers(pt)),
                    ln.name)
    used = ln.names
    if not used:
        used.update(s.name for s in ln.stops)
    out, k = name, 1
    while out in used:
        k += 1
        out = f"{name} {k}"
    used.add(out)
    return out


def station_spots(c: Ctx, ln: Line) -> list[tuple[int, str, Stop | None]]:
    """(vertex index, name, stop) of every station: the stops (exits aside) and evenly spaced
    stations between them at the mode's spacing, off the water."""
    lo, hi = presets.TRANSIT_MODES[ln.mode].station_spacing_m
    cum = _cum(ln.pts)
    out = []
    wet = [poly for poly, _, _ in c.water]
    seen = set()
    for k, (s, i) in enumerate(zip(ln.stops, ln.stop_at)):
        if s.kind != "exit" and not (ln.loop and k == len(ln.stops) - 1):
            if i not in seen:
                out.append((i, s.name, s))
                seen.add(i)
        if k + 1 < len(ln.stops):
            j = ln.stop_at[k + 1]
            a, b = cum[i], cum[j]
            L = b - a
            nmid = max(0, int(round(L / ((lo + hi) / 2.0))) - 1)
            for t in range(1, nmid + 1):
                s0 = a + L * t / (nmid + 1)
                for off in (0.0, 40.0, -40.0, 80.0, -80.0, 120.0, -120.0):
                    idx, p = _at(ln.pts, cum, s0 + off)
                    if not any(w.contains(Point(p)) for w in wet):
                        if idx not in seen:
                            out.append((idx, _spot_name(c, p, ln), None))
                            seen.add(idx)
                        break
    return sorted(out, key=lambda x: x[0])


CLEAR_PATH_M = 1.8   # sidewalk left clear beside a support (scope 4.4)


def sidewalk_index(m) -> tuple:
    """(STRtree of sidewalk lines, [(sidewalk, its road centerline)], sidewalks by segment)."""
    seg = {s.id: s for s in m.road_segments}
    rows, by_seg = [], {}
    for w in m.sidewalks:
        r = seg.get(w.segment_id)
        if r is None:
            continue
        rows.append((w, LineString(r.centerline)))
        by_seg.setdefault(w.segment_id, []).append(w)
    tree = shapely.STRtree([LineString(w.line) for w, _ in rows]) if rows else None
    return tree, rows, by_seg


def _sidewalk_frame(sw_line, road_line, pt) -> tuple[tuple, tuple]:
    """The point of the sidewalk center line nearest pt and the unit normal there toward
    the road."""
    t = sw_line.project(pt)
    q_ = sw_line.interpolate(t)
    a = sw_line.interpolate(max(t - 1.0, 0.0))
    b = sw_line.interpolate(min(t + 1.0, sw_line.length))
    ux, uy = b.x - a.x, b.y - a.y
    L = math.sqrt(ux * ux + uy * uy) or 1.0
    nx, ny = -uy / L, ux / L
    r = road_line.interpolate(road_line.project(q_))
    if (r.x - q_.x) * nx + (r.y - q_.y) * ny < 0:
        nx, ny = -nx, -ny
    return (q_.x, q_.y), (nx, ny)


def clear_of_sidewalk(w, o: float, size: float) -> bool:
    """A support of this size whose center is o m from the sidewalk's center line (toward
    the road) leaves the clear path: off the sidewalk, or with 1.8 m (or the whole clear
    path, if narrower) between it and the property line."""
    half = w.width_m / 2.0
    if abs(o) >= half + size / 2.0 - 0.01:
        return True
    need = min(CLEAR_PATH_M, w.clear_path_m)
    return o - size / 2.0 >= -half + need - 0.01 and o + size / 2.0 <= half + 0.01


def sidewalks_clear(sw, pt, size: float) -> bool:
    tree, rows, _ = sw
    if tree is None:
        return True
    for i in sorted(tree.query(pt, predicate="dwithin", distance=8.0 + size).tolist()):
        w, road = rows[i]
        sw_line = LineString(w.line)
        if sw_line.distance(pt) >= w.width_m / 2.0 + size / 2.0:
            continue
        q_, n = _sidewalk_frame(sw_line, road, pt)
        o = (pt.x - q_[0]) * n[0] + (pt.y - q_[1]) * n[1]
        if not clear_of_sidewalk(w, o, size):
            return False
    return True


class Builder:
    def __init__(self, c: Ctx, walks: list):
        self.c = c
        self.walks = walks
        self.gi = _ground(walks)
        self.glines = [LineString([p[:2] for p in walks[i]["line"]]) for i in self.gi]
        self.gtree = shapely.STRtree(self.glines)
        lms = [G.from_model_poly(lm.polygon) for lm in c.m.landmasses]
        self.lms = lms
        self.land_of = _landmass_index(lms, [ln.coords[0] for ln in self.glines])
        self.splits: dict = {}
        self.new: list = []          # (key, kind, line3, width, attrs)
        self.structures: list = []
        self.stations: list = []
        self.nst = 0
        self.sw = sidewalk_index(c.m)

    def foot(self, p) -> tuple[tuple, float]:
        lm = _landmass_index(self.lms, [p])[0]
        best = _nearest_on(self.gtree, self.glines, self.walks, self.gi, self.land_of,
                           Point(p), lm)
        f = _foot(self.glines, self.walks, self.gi, best, p)
        self.splits.setdefault(best, []).append(f)
        return f, _d(f, p)

    def walk(self, kind: str, line3: list, width: float, attrs: dict) -> int:
        self.new.append((kind, [tuple(map(q, p)) for p in line3], width, attrs))
        return len(self.new) - 1

    def struct(self, sid: str, kind: str, z0: float, z1: float, footprint=None, line=None,
               attrs=None) -> None:
        rec = {"id": sid, "type": "structure", "kind": kind, "z0_m": q(z0), "z1_m": q(z1),
               "attrs": attrs or {}}
        if footprint is not None:
            rec["footprint"] = G.to_model_poly(footprint)
        if line is not None:
            rec["line"] = [[q(x), q(y), q(z)] for x, y, z in line]
        self.structures.append(rec)

    # -- stations ---------------------------------------------------------------------------

    def stations_of(self, ln: Line, bld: dict, ent: dict, gone: set) -> list[str]:
        c = self.c
        mode = ln.mode
        pts, zs = ln.pts, ln.zs
        cum = _cum(pts)
        ids = []
        for idx, name, stop in station_spots(c, ln):
            tower = None
            if mode == "sky_tube":
                tower, idx = self._tower_for(ln, stop, idx, bld)
            self.nst += 1
            sid = f"st{self.nst:03d}"
            half = STATION_LEN_M[mode] / 2.0
            a, b = cum[idx] - half, cum[idx] + half
            if a < 0:
                a, b = 0.0, min(cum[-1], 2 * half)
            if b > cum[-1]:
                a, b = max(0.0, cum[-1] - 2 * half), cum[-1]
            i0, p0 = _at(pts, cum, a)
            i1, p1 = _at(pts, cum, b)
            seg = [p0] + [p for p in pts[i0 + 1:i1 + 1] if p not in (p0, p1)] + [p1]
            seg = [p for k, p in enumerate(seg) if k == 0 or p != seg[k - 1]]
            if len(seg) < 2:
                continue
            z = zs[idx]
            width = WIDTH_M[mode] + 2 * PLATFORM_M[mode]
            foot = G.qpoly(LineString(seg).buffer(width / 2.0, cap_style="flat",
                                                  join_style="mitre"))
            if foot.is_empty:
                continue
            foot = max(G.parts(foot), key=lambda p_: (G.area(p_), G.qbounds(p_)))
            kind = {"metro": "underground", "sky_tube": "sky"}.get(mode, "elevated")
            acc: list[int] = []
            if mode == "metro":
                self._metro(sid, seg, foot, acc)
                zpos = METRO_CONCOURSE_Z
            elif tower is not None:
                self._sky_in_tower(sid, ln, pts[idx], z, tower, ent, acc)
                zpos = z
            else:
                self._elevated(sid, ln, seg, foot, z, bld, gone, acc,
                               pylon=(mode == "sky_tube"))
                zpos = z
            self.stations.append({
                "id": sid, "type": "station", "name": name, "kind": kind,
                "line_ids": [ln.id], "position": [pts[idx][0], pts[idx][1], q(zpos)],
                "footprint": G.to_model_poly(foot),
                "building_id": tower.id if tower is not None else None,
                "access_ids": acc, "attrs": {"mode": mode, "stop": stop.name if stop else None,
                                             "track_z_m": q(z)}})
            ids.append(sid)
        return ids

    def _tower_for(self, ln: Line, stop, idx: int, bld: dict):
        """The portal tower that hosts a sky station: the nexus station tower, else the
        portal tower nearest the stop within STATION_TOWER_M; the station moves to the line
        vertex inside it."""
        c = self.c
        cands = []
        if stop is not None and stop.tower_id and stop.tower_id in ln.portals:
            cands = [stop.tower_id]
        else:
            p = ln.pts[idx]
            for bid in sorted(ln.portals):
                b = bld[bid]
                d = round(b.poly.distance(Point(p)), 2)
                if d <= STATION_TOWER_M:
                    cands.append((d, bid))
            cands = [x[1] for x in sorted(cands)][:1]
        if not cands:
            return None, idx
        b = bld[cands[0]]
        inside = [i for i, p in enumerate(ln.pts) if b.poly.contains(Point(p))]
        if not inside:
            return None, idx
        return b, inside[len(inside) // 2]

    def _metro(self, sid, seg, foot, acc) -> None:
        z = METRO_CONCOURSE_Z
        k = self.walk("path", [(x, y, z) for x, y in seg], 6.0, {"station": sid,
                                                                  "concourse": True})
        acc.append(k)
        self.struct(f"{sid}.cc", "deck", -14.0, -4.0, footprint=foot,
                    attrs={"station": sid, "role": "concourse", "underground": True})
        for e, tag in ((seg[0], "a"), (seg[-1], "b")):
            f, d = self.foot(e)
            if d < 0.5:  # stairs need a run: step the kiosk 12 m along the concourse
                continue
            acc.append(self.walk("stairs", [(f[0], f[1], 0.0), (e[0], e[1], z)], 3.0,
                                 {"station": sid}))
            sq = G.qpoly(Point(f).buffer(2.5, cap_style="square"))
            self.struct(f"{sid}.ent{tag}", "canopy", 0.0, 3.2, footprint=sq,
                        attrs={"station": sid, "role": "metro_entrance"})

    def _elevated(self, sid, ln, seg, foot, z, bld, gone, acc, pylon: bool) -> None:
        mode = ln.mode
        k = self.walk("elevated", [(x, y, z) for x, y in seg], PLATFORM_M[mode] * 2,
                      {"station": sid, "platform": True})
        acc.append(k)
        self.struct(f"{sid}.pf", "deck", z - 1.0, z, footprint=foot,
                    attrs={"station": sid, "role": "platform", "mode": mode})
        ends = [seg[0], seg[-1]] if not pylon else [seg[0]]
        for e, tag in zip(ends, ("a", "b")):
            f, d = self.foot(e)
            if pylon or d < 1.0:
                # an elevator core: on the pylon (sky stations), or where the sidewalk is
                # right under the platform end
                acc.append(self.walk("elevator", [(e[0], e[1], 0.0), (e[0], e[1], z)], 2.5,
                                     {"station": sid}))
                if f != tuple(e):
                    acc.append(self.walk("path", [(e[0], e[1], 0.0), (f[0], f[1], 0.0)], 3.0,
                                         {"station": sid}))
                if pylon:
                    core = G.qpoly(Point(e).buffer(5.0, cap_style="square"))
                    self.struct(f"{sid}.core", "pylon", 0.0, z, footprint=core,
                                attrs={"station": sid, "role": "elevator_core"})
            else:
                acc.append(self.walk("stairs", [(e[0], e[1], z), (f[0], f[1], 0.0)], 3.0,
                                     {"station": sid}))
                cnp = G.qpoly(Point(f).buffer(3.0, cap_style="square"))
                self.struct(f"{sid}.cn{tag}", "canopy", 2.8, 3.2, footprint=cnp,
                            attrs={"station": sid, "role": "stair_canopy"})
        if not pylon:
            e = seg[0]
            acc.append(self.walk("elevator", [(e[0], e[1], 0.0), (e[0], e[1], z)], 2.5,
                                 {"station": sid}))
        self._skywalk(sid, seg, foot, z, bld, gone, acc)

    def _skywalk(self, sid, seg, foot, z, bld, gone, acc) -> None:
        """An elevated walkway from a platform end to the nearest building with a floor at
        platform level (within 35 m, crossing no other building)."""
        c = self.c
        if c.btree is None:
            return
        best = None
        for i in sorted(c.btree.query(foot, predicate="dwithin", distance=35.0).tolist()):
            b = c.blds[i]
            if b.id in gone or b.top < z + 4.0 or b.bottom > z - 2.0:
                continue
            for e in (seg[0], seg[-1]):
                d = round(b.poly.distance(Point(e)), 2)
                if 3.0 <= d <= 35.0 and (best is None or (d, b.id) < best[:2]):
                    best = (d, b.id, e, b)
        if best is None:
            return
        _, bid, e, b = best
        tgt = G.qpoint(shapely.ops.nearest_points(b.poly, Point(e))[0])
        seg2 = LineString([e, tgt])
        for i in c.btree.query(seg2, predicate="intersects").tolist():
            o = c.blds[i]
            if o.id != bid and o.id not in gone and o.top > z - 4.0 and \
                    seg2.crosses(o.poly):
                return
        acc.append(self.walk("elevated", [(e[0], e[1], z), (tgt[0], tgt[1], z)], 4.0,
                             {"station": sid, "skywalk": True, "building": bid}))
        self.struct(f"{sid}.sw", "deck", z - 0.8, z, line=[(e[0], e[1], z), (tgt[0], tgt[1], z)],
                    attrs={"station": sid, "role": "skywalk", "width_m": 4.0,
                           "building": bid})

    def _sky_in_tower(self, sid, ln, p, z, tower, ent, acc) -> None:
        e = ent.get(tower.id)
        if e is None:
            e = tuple(G.qpoint(tower.poly.representative_point()))
        acc.append(self.walk("elevated", [(p[0], p[1], z), (e[0], e[1], z)], 6.0,
                             {"station": sid, "platform": True, "building": tower.id}))
        acc.append(self.walk("elevator", [(e[0], e[1], 0.0), (e[0], e[1], z)], 3.0,
                             {"station": sid, "building": tower.id}))
        f, d = self.foot(e)
        if d > 0.01:
            acc.append(self.walk("path", [(e[0], e[1], 0.0), (f[0], f[1], 0.0)], 3.0,
                                 {"station": sid, "building": tower.id}))

    # -- line structures --------------------------------------------------------------------

    def line_structures(self, ln: Line, gone: set, segs, lanes) -> int:
        mode = ln.mode
        if mode == "metro":
            return 0
        pts, zs = ln.pts, ln.zs
        cum = _cum(pts)
        piece = 400.0
        k, s = 0, 0.0
        kind = "tube" if mode == "sky_tube" else "deck"
        while s < cum[-1] - 0.01:
            e = min(cum[-1], s + piece)
            i0 = max(i for i in range(len(cum)) if cum[i] <= s + 1e-9)
            i1 = min(i for i in range(len(cum)) if cum[i] >= e - 1e-9)
            k += 1
            # the structure's top line (rail level, or the top of a tube)
            line = [(pts[i][0], pts[i][1], zs[i] + above(mode)) for i in range(i0, i1 + 1)]
            if len(line) >= 2:
                self.struct(f"{ln.id}.{'tb' if kind == 'tube' else 'dk'}{k:03d}", kind,
                            min(z for _, _, z in line) - DECK_M[mode],
                            max(z for _, _, z in line), line=line,
                            attrs={"line_id": ln.id, "mode": mode, "width_m": WIDTH_M[mode],
                                   "deck_m": DECK_M[mode], "color": ln.color})
            s = e
        lo, hi = presets.TRANSIT_MODES[mode].support_spacing_m
        step = (lo + hi) / 2.0
        n = 0
        s = step / 2.0
        while s < cum[-1]:
            placed = self._support(ln, cum, s, gone, segs, lanes, n)
            n += placed
            s += step
        return n

    def _support(self, ln, cum, s, gone, segs, lanes, n0) -> int:
        c = self.c
        mode = ln.mode
        size = COLUMN_M[mode]
        for off in (0.0, 6.0, -6.0, 12.0, -12.0):
            i, p = _at(ln.pts, cum, s + off)
            f = 0.0 if cum[min(i + 1, len(cum) - 1)] == cum[i] else \
                (s + off - cum[i]) / (cum[min(i + 1, len(cum) - 1)] - cum[i])
            z = ln.zs[i] + (ln.zs[min(i + 1, len(ln.zs) - 1)] - ln.zs[i]) * min(max(f, 0), 1)
            top = z - below(mode)
            if top <= 1.0:
                return 0
            spots = self._column_spots(p, segs, mode)
            if spots and all(self._free(q_, size, gone, lanes, segs) for q_ in spots):
                for j, q_ in enumerate(spots):
                    sq = G.qpoly(Point(q_).buffer(size / 2.0, cap_style="square"))
                    self.struct(f"{ln.id}.col{n0 + 1:04d}{'ab'[j] if len(spots) > 1 else ''}",
                                "pylon" if mode in ("sky_tube", "maglev") else "column",
                                0.0, top, footprint=sq,
                                attrs={"line_id": ln.id, "mode": mode})
                return 1
        return 0

    def _column_spots(self, p, segs, mode) -> list[tuple]:
        """Where a support at p stands: in the median of the road under it, just inside both
        curbs of a road without one (a bent; only where 1.8 m of the sidewalk stays clear
        behind it), or at p off the roads."""
        tree, lines, recs = segs
        pt = Point(p)
        size = COLUMN_M[mode]
        hits = sorted(tree.query(pt, predicate="dwithin", distance=30.0).tolist())
        on = []
        for h in hits:
            s = recs[h]
            d = lines[h].distance(pt)
            if d <= max(s.width_m, s.cross_section.total_width_m) / 2.0:
                on.append((round(d, 3), s.id, h))
        if not on:
            return [p]
        _, _, h = min(on)
        s, line = recs[h], lines[h]
        cs = s.cross_section
        if cs.median_m >= size + 0.5:
            return [G.qpoint(line.interpolate(line.project(pt)))]
        out = []
        for w in self.sw[2].get(s.id, []):
            sw_line = LineString(w.line)
            q_, n = _sidewalk_frame(sw_line, line, pt)
            o = w.width_m / 2.0 - w.curb_m - size / 2.0
            spot = (G.q(q_[0] + n[0] * o), G.q(q_[1] + n[1] * o))
            if clear_of_sidewalk(w, o, size):
                out.append(spot)
        if len(out) < (1 if mode == "monorail" else 2):
            return []
        return out[:1] if mode == "monorail" else out

    def _free(self, p, size, gone, lanes, segs) -> bool:
        """Off the water, buildings, road decks, lanes and sidewalk clear paths."""
        c = self.c
        pt = Point(p)
        sq = pt.buffer(size / 2.0, cap_style="square")
        for poly, _, nav in c.water:
            if poly.intersects(sq):
                return False
        if c.dtree is not None:
            for i in c.dtree.query(pt, predicate="dwithin", distance=40.0).tolist():
                if c.decks[i][0].distance(pt) < c.decks[i][1] + size / 2.0 + 0.5:
                    return False
        if not sidewalks_clear(self.sw, pt, size):
            return False
        if c.btree is not None:
            for i in c.btree.query(pt, predicate="dwithin", distance=size).tolist():
                if c.blds[i].id not in gone:
                    return False
        ltree, llines, lw = lanes
        for i in ltree.query(pt, predicate="dwithin", distance=4.0 + size).tolist():
            if llines[i].distance(pt) < lw[i] / 2.0 + size / 2.0:
                return False
        return True


# ---------------------------------------------------------------------------
# The stage
# ---------------------------------------------------------------------------

@dataclass
class Out:
    rows: dict
    lines: list
    notes: list
    info: dict


def _colors(spec) -> list[str]:
    used: dict = {}
    out = []
    for tl in spec.transit.lines:
        pal = presets.TRANSIT_MODES[tl.mode].palette
        k = used.get(tl.mode, 0)
        used[tl.mode] = k + 1
        out.append(tl.color or pal[k % len(pal)])
    return out


def _skybridge_hits(c: Ctx, lines: list) -> list[str]:
    """Skybridges (not of complexes) in the way of an elevated or sky line."""
    out = []
    for ln in lines:
        if ln.mode == "metro" or len(ln.pts) < 2:
            continue
        tl = LineString(ln.pts)
        half = WIDTH_M[ln.mode] / 2.0 + SIDE_PAD_M
        for line, z0, z1, cx, sid, _ in c.skyb:
            if cx or sid in out or line.distance(tl) > half + 3.0:
                continue
            i = _nearest_index(ln.pts, G.qpoint(shapely.ops.nearest_points(tl, line)[0]))
            z = ln.zs[i]
            if z1 >= z - below(ln.mode) - 3.0 and z0 <= z + above(ln.mode) + 3.0:
                out.append(sid)
    return sorted(out)


def build(spec, m) -> Out:
    with G.canonical():
        return _build(spec, m)


def _build(spec, m) -> Out:
    import shapely.ops  # noqa: F401  (nearest_points)

    c = context(spec, m)
    notes: list = []
    lines: list[Line] = []
    colors = _colors(spec)
    for i, tl in enumerate(spec.transit.lines):
        pre = presets.TRANSIT_MODES[tl.mode]
        alt = tuple(tl.altitude_m) if tl.altitude_m else pre.default_altitude_m
        ln = Line(f"tl{i + 1:02d}", tl.name, tl.mode, colors[i], tl.loop, alt,
                  base_z(tl.mode, alt), bool(tl.through_towers))
        for name in tl.route:
            st = resolve_stop(c, name, tl.mode)
            if st is None:
                notes.append(f"{tl.name}: stop '{name}' not found; skipped")
            else:
                ln.stops.append(st)
        if len(ln.stops) < 2:
            notes.append(f"{tl.name}: fewer than two stops; not built")
            continue
        route_line(c, ln)
        T.stage(f"transit/{ln.id}/route", [ln.pts, round(ln.min_radius, 2)
                                           if ln.min_radius != INF else None])
        lines.append(ln)
    for ln in lines:
        ln.conflicts += [b.id for b in _corridor(c, ln, ln.pts)]
    gone = set()
    for ln in lines:
        gone |= set(ln.removed)
    for ln in lines:
        profile(c, ln, gone)
        for _ in range(40):
            if not _fit_portals(c, ln):
                break
            profile(c, ln, gone)
        ln.conflicts = [x for x in ln.conflicts if x == "route"] + clearance_conflicts(
            c, ln, gone)
        notes += ln.notes
    T.stage("transit/profiles", [[ln.id, ln.zs] for ln in lines])
    sky_gone = set(_skybridge_hits(c, lines)) | {s.id for s in m.skybridges
                                                  if set(s.building_ids) & gone}
    # walkways without the removed buildings and skybridges
    walks = []
    for w in m.walkways:
        a = w.attrs or {}
        if a.get("building") in gone or a.get("skybridge") in sky_gone:
            continue
        walks.append(w.model_dump(mode="json"))
    B = Builder(c, walks)
    bld = {b.id: b for b in c.blds}
    ent = {}
    for b in m.buildings:
        e = next((x for x in b.entrances if x.kind in ("main", "gate")),
                 b.entrances[0] if b.entrances else None)
        if e is not None:
            ent[b.id] = (e.position[0], e.position[1])
    seg_recs = [s for s in m.road_segments if not s.bridge]
    seg_lines = [LineString(s.centerline) for s in seg_recs]
    segs = (shapely.STRtree(seg_lines), seg_lines, seg_recs)
    lane_lines = [LineString([p[:2] for p in x.centerline]) for x in m.lanes]
    lanes = (shapely.STRtree(lane_lines), lane_lines, [x.width_m for x in m.lanes])
    tl_rows, supports = [], {}
    for ln in lines:
        st_ids = B.stations_of(ln, bld, ent, gone)
        supports[ln.id] = B.line_structures(ln, gone, segs, lanes)
        L = _plen(ln.pts)
        grades = [abs(ln.zs[k + 1] - ln.zs[k]) / max(_d(ln.pts[k], ln.pts[k + 1]), 1e-9)
                  for k in range(len(ln.pts) - 1)]
        tl_rows.append({
            "id": ln.id, "type": "transit_line", "name": ln.name, "mode": ln.mode,
            "color": ln.color, "path": [[x, y, z] for (x, y), z in zip(ln.pts, ln.zs)],
            "station_ids": st_ids, "loop": ln.loop,
            "attrs": {"length_m": q(L), "altitude_m": list(ln.alt), "base_z_m": ln.z0,
                      "min_radius_m": None if ln.min_radius == INF else q(ln.min_radius),
                      "max_grade": round(max(grades), 4) if grades else 0.0,
                      "stops": [s.name for s in ln.stops],
                      "stop_vertices": ln.stop_at,
                      "removed_buildings": sorted(set(ln.removed)),
                      "portals": sorted(ln.portals), "conflicts": sorted(set(ln.conflicts)),
                      "through_towers": ln.through, "supports": supports[ln.id]}})
    # ground walkways split at the station feet, then the new walkways
    walks = _split(walks, B.gi, B.glines, B.splits)
    k = max(int(w["id"][2:]) for w in walks)
    ids = []
    for kind, line3, width, attrs in B.new:
        k += 1
        wid = f"wk{k:06d}"
        ids.append(wid)
        walks.append({"id": wid, "type": "walkway", "kind": kind, "line": line3,
                      "width_m": width, "neighbors": [], "attrs": attrs})
    for st in B.stations:
        st["access_ids"] = [ids[i] for i in st["access_ids"]]
    _neighbors(walks)
    # buildings: removed ones out, portals declared
    portals: dict = {}
    station_at = {}
    for st in B.stations:
        if st["building_id"]:
            station_at.setdefault(st["building_id"], set()).update(st["line_ids"])
    for ln in lines:
        for bid, (z0, z1) in sorted(ln.portals.items()):
            portals.setdefault(bid, []).append({"line_id": ln.id, "z0_m": z0, "z1_m": z1,
                                                "station": ln.id in station_at.get(bid, ())})
    buildings = []
    for b in m.buildings:
        if b.id in gone:
            continue
        if b.id in portals:
            d = b.model_dump(mode="json")
            d["portals"] = list(d.get("portals") or []) + portals[b.id]
            buildings.append(d)
        else:
            buildings.append(b)
    props = []
    for p in m.properties:
        keep = [x for x in p.building_ids if x not in gone]
        if not keep:
            continue
        if len(keep) != len(p.building_ids):
            d = p.model_dump(mode="json")
            d["building_ids"] = keep
            props.append(d)
        else:
            props.append(p)
    lot_line = {}
    by_lot = {b.id: b.lot_id for b in m.buildings}
    for ln in lines:
        for bid in ln.removed:
            if by_lot.get(bid):
                lot_line.setdefault(by_lot[bid], ln.id)
    lots = []
    for lt in m.lots:
        if lt.id in lot_line:
            d = lt.model_dump(mode="json")
            d["attrs"] = {**d.get("attrs", {}), "transit_corridor": lot_line[lt.id]}
            lots.append(d)
        else:
            lots.append(lt)
    rows = {
        "transit_lines": tl_rows,
        "stations": sorted(B.stations, key=lambda s: s["id"]),
        "structures": sorted([*m.structures, *B.structures],
                             key=lambda s: s.id if hasattr(s, "id") else s["id"]),
        "walkways": walks,
        "buildings": buildings,
        "properties": props,
        "skybridges": [s for s in m.skybridges if s.id not in sky_gone],
        "green_areas": [g for g in m.green_areas if g.building_id not in gone],
        "lots": lots,
    }
    T.stage("transit", [[r["id"], r["path"], r["station_ids"]] for r in tl_rows])
    info = {"lines": len(tl_rows), "stations": len(B.stations),
            "removed_buildings": len(gone), "removed_skybridges": len(sky_gone),
            "portals": sum(len(v) for v in portals.values()),
            "structures": len(B.structures), "walkways_added": len(B.new)}
    return Out(rows, lines, notes, info)
