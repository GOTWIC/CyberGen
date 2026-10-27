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
   M8b: each leg keeps off the line's earlier legs (on the roads, else on the raster), a
   road leg may end at any junction near a district stop, and a loop is one simple ring:
   its district stops move to junctions that put them in route order around the middle
   (`_loop_points`), deep enough in their districts for the curves (`_deepen`); a loop
   on the roads that would cross or wind round itself is routed off them, and every loop
   off the roads also along its guide ring (`_guide_loop`). Stations follow the route
   order (`ordered_stops`); a line's track does not depend on the other lines (only its
   heights see the buildings they remove). A fast line (maglev, sky tube) puts a middle
   stop where its curve stays in the district and clear, or turns beside the district
   (`_fast_point`), and is also drawn along its guide line (`_guide_line`); a line ends at a
   site where the zone its station serves begins (`_site_point`). The raster search skips
   what it cannot reach and, over 600 m, is guided by the exact turn-free cost to go.
   M8c: a flying loop is one ring of Dubins paths through its stops (`_dubins_track`, the
   mode's radius by construction); an open road line the roads fail goes off them
   (`_off_roads_line`), and any open line still flawed is tried as Dubins paths from stop
   to stop (`_dubins_line`).
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
import shapely.ops
from shapely.geometry import LineString, Point, Polygon

from . import dmath as M
from . import geom as G
from . import presets
from . import trace as T
from .buildout import _foot, _ground, _landmass_index, _nearest_on, _neighbors, _split, wk_max
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
ROAD_DECK_M = 2.0           # depth under a road deck (viaducts 1.8 m, bridges 1.5 m)
UNDER_PAD_M = 1.0           # a track passing under a road deck stays this far below it
PORTAL_HEADROOM_M = 8.0     # a portal tower rises at least this far above the tube's top
PORTAL_TIGHT_M = 3.0        # ... or this far, where the line could not climb over it
STATION_LEN_M = {"metro": 120.0, "elevated_rail": 110.0, "monorail": 60.0, "maglev": 160.0,
                 "sky_tube": 50.0}
PLATFORM_M = {"metro": 4.0, "elevated_rail": 4.0, "monorail": 3.0, "maglev": 5.0,
              "sky_tube": 4.0}
COLUMN_M = {"elevated_rail": 1.6, "monorail": 1.2, "maglev": 2.2, "sky_tube": 3.5}
METRO_CONCOURSE_Z = -8.0
METRO_RUN_M = 12.0          # a metro stair runs this far along the concourse from its kiosk
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
RAISED_MIN_M = 4.0    # a road deck higher than this counts as raised for the road graph
CLIMB_W = 6.0         # raster: over a building the line climbs to clear (within its altitude)
RESTOP_TRIES = 6      # avenue nodes a missed road-line stop tries
EXIT_RUN_M = 400.0    # a line that leaves the map is fitted as if it ran on this far
RESTOP_BUDGET = 4     # routes the stop retry may try in all, per line
MAX_TURN_COS = -0.5   # road-graph routes turn at most 120 degrees at a node
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


def road_underside(z: float) -> float:
    """Underside of a road deck whose surface is at z."""
    return z - ROAD_DECK_M


def _z_at(prof, s: float) -> float:
    if s <= prof[0][0]:
        return prof[0][1]
    for (s0, z0), (s1, z1) in zip(prof, prof[1:]):
        if s <= s1:
            return z0 if s1 <= s0 else z0 + (z1 - z0) * (s - s0) / (s1 - s0)
    return prof[-1][1]


def deck_heights(decks, tree, arr, pad: float, which: bool = False) -> list[tuple]:
    """(point index, road deck z) for the points over a raised road (within its half width
    plus pad), the deck z where the point projects on its centerline (with `which`, the
    deck's index too)."""
    if tree is None:
        return []
    out = []
    reach = max(d[1] for d in decks) + pad
    ip, il = tree.query(arr, predicate="dwithin", distance=reach)
    for i, l_ in sorted(zip(ip.tolist(), il.tolist())):
        line, hw, prof = decks[l_]
        p = arr[i]
        if line.distance(p) <= hw + pad:
            z = _z_at(prof, line.project(p))
            out.append((i, z, l_) if which else (i, z))
    return out


def _envelope(pts, need: list[float], g: float, closed: bool = False) -> list[float]:
    """The lowest profile over `need` with grades of at most g (closed: around a loop whose
    last point is its first)."""
    return _graded(pts, need, g, max, -1.0, closed)


def _graded(pts, vals: list[float], g: float, pick, sign: float, closed: bool) -> list[float]:
    """vals limited to the grade g from both sides: pick(v, neighbor + sign g d) (max and -1
    lift the lows, min and +1 cap the highs); around a closed track (first point = last)
    each pass runs twice, so a bound near the seam reaches the other side."""
    v = list(vals)
    n = len(v)
    for _ in range(2 if closed and n > 2 else 1):
        if closed and n > 2:
            v[0] = v[-1] = pick(v[0], v[-1])
        for i in range(1, n):
            v[i] = pick(v[i], v[i - 1] + sign * g * _d(pts[i - 1], pts[i]))
        if closed and n > 2:
            v[0] = v[-1] = pick(v[0], v[-1])
        for i in range(n - 2, -1, -1):
            v[i] = pick(v[i], v[i + 1] + sign * g * _d(pts[i], pts[i + 1]))
    if closed and n > 2:
        v[0] = v[-1] = pick(v[0], v[-1])
    return v


def deck_crossings(decks, tree, arr, pad: float) -> list[list[tuple[int, float]]]:
    """The track points over each raised road, grouped by crossing (one road, consecutive
    points): [[(point index, deck z), ...], ...]."""
    by: dict = {}
    for i, z, l_ in deck_heights(decks, tree, arr, pad, which=True):
        by.setdefault(l_, []).append((i, z))
    out = []
    for l_ in sorted(by):
        run = []
        for i, z in sorted(by[l_]):
            if run and i > run[-1][0] + 1:
                out.append(run)
                run = []
            run.append((i, z))
        if run:
            out.append(run)
    return out


def passes_under(mode: str, zs: list[float], z0: float) -> bool:
    """A crossing of road decks at heights zs that the track passes under: over it would
    take the track above its mode's altitude, under it keeps the track at its base."""
    lo_alt, hi_alt = presets.TRANSIT_MODES[mode].altitude_m
    over = max(zs) + ROAD_CLEAR_M + below(mode)
    under = road_underside(min(zs)) - above(mode) - UNDER_PAD_M
    return over > hi_alt and under >= max(lo_alt, z0 - 0.01) - 1e-9


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
                    # the road's height at this cell (M7: a long road raised at one end)
                    prof = [(z.s, z.z) for z in s.z_profile]
                    zc = _z_at(prof, lines[l_].project(c.pts[p_]))
                    if zc <= 0.5:
                        continue
                    if zc > c.road_z[p_]:
                        c.road_z[p_] = zc
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
        # traced (pinned) buildings stay as drawn
        removable = not (b.landmark or b.megasite_id or complex_member or
                         "pinned" in b.attrs)
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
    rp = G.from_model_poly(d.polygon).representative_point()
    best = None
    for p, rank in _district_cands(c, d, mode, inset=toward is not None):
        if toward is not None:
            key = (round(toward.distance(Point(p)) + 150.0 * rank, 2), 0, p)
        else:
            key = (rank, round(_d(p, (rp.x, rp.y)), 2), p)
        if best is None or key < best:
            best = key
    return best[2] if best else (q(rp.x), q(rp.y))


def _district_cands(c: Ctx, d, mode: str, inset: bool) -> list[tuple[tuple, int]]:
    """(junction, class rank) of the roads a stop of the mode may use in the district (avenues
    then streets; highways then avenues for the maglev), with `inset` only those well inside
    it (see `_district_point`), sorted by position."""
    poly = G.from_model_poly(d.polygon)
    if inset:
        for x in ((120.0, 60.0) if mode in ROAD_MODES else (250.0, 150.0, 60.0)):
            inner = G.qpoly(poly.buffer(-x))
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
    shapely.prepare(poly)
    return [(p, rank) for p, rank in sorted(ends.items()) if poly.contains(Point(p))]


LOOP_SECTORS = 36        # a district stop of a loop tries a junction per sector (10 degrees)
LOOP_MIN_GAP = 0.15      # radians (about 9 degrees) between two stops seen from the center


def _ring_of(stops: list) -> list:
    """The stops of a loop once each (the route repeats the first at the end)."""
    if len(stops) > 2 and stops[-1].name == stops[0].name and stops[-1].kind == stops[0].kind:
        return stops[:-1]
    return list(stops)


def _gap_cost(d: float, n: int) -> float:
    """How far the turn between two stops of a loop (seen from its middle) is from an even
    share of the turn (stops crowded on one side make sharp corners at them)."""
    even = 2.0 * M.PI / n
    return ((d - even) / even) ** 2


def _loop_points(c: Ctx, ln: Line, pads: dict | None = None) -> list | None:
    """Points for a loop's stops that make it one simple closed curve in their route order:
    the district stops (not a nexus platform, a site or a place) move to a junction of their
    district so that, seen from the middle of the stops, they come in route order around one
    turn (a star-shaped ring is simple), each edge less than half a turn and the stops as
    near a circle as the districts allow (the ring the line will follow). A dynamic program
    over the junctions, both ways round; None when no choice puts them in order (the line
    keeps its district points). Returns a point per stop of the route."""
    ring = _ring_of(ln.stops)
    n = len(ring)
    if n < 3:
        return None
    dist = {d.id: d for d in c.m.districts}
    home = [s.p for s in ring]
    ox = q(math.fsum(p[0] for p in home) / n)
    oy = q(math.fsum(p[1] for p in home) / n)
    R = math.fsum(_d(p, (ox, oy)) for p in home) / n
    if R < 1.0:
        return None
    cands, every = [], []
    for s in ring:
        every.append([])
        if s.kind == "district" and s.z is None and s.district_id in dist:
            # in each sector seen from the center, the junction nearest the ring
            by: dict = {}
            for p, _ in _district_cands(c, dist[s.district_id], ln.mode, True):
                every[-1].append((p, float(M.atan2(p[1] - oy, p[0] - ox)),
                                  ((_d(p, (ox, oy)) - R) / R) ** 2))
                t = float(M.atan2(p[1] - oy, p[0] - ox))
                key = (round(abs(_d(p, (ox, oy)) - R), 2), p)
                k = int((t + M.PI) // (2.0 * M.PI / LOOP_SECTORS))
                if k not in by or key < by[k][0]:
                    by[k] = (key, p)
            pts = [by[k][1] for k in sorted(by)] or [s.p]
        else:
            pts = [s.p]
        cands.append([(p, float(M.atan2(p[1] - oy, p[0] - ox)),
                       ((_d(p, (ox, oy)) - R) / R) ** 2) for p in pts])
    two_pi = 2.0 * M.PI
    area = math.fsum(home[k][0] * home[(k + 1) % n][1] - home[(k + 1) % n][0] * home[k][1]
                     for k in range(n))
    best = None
    for sgn in (1.0, -1.0):
        def inc(a, b, sgn=sgn):
            return (sgn * (b - a)) % two_pi
        for p0, t0, w0 in cands[0]:
            # per candidate of the stop: non-dominated (turn so far, cost, points)
            fronts = {p0: [(0.0, w0, (p0,), t0)]}
            for k in range(1, n):
                new: dict = {}
                for p, t, w in cands[k]:
                    opts = []
                    for front in fronts.values():
                        for A, cost, path, tp in front:
                            d = inc(tp, t)
                            if not LOOP_MIN_GAP < d < M.PI - LOOP_MIN_GAP or \
                                    A + d >= two_pi - LOOP_MIN_GAP:
                                continue
                            opts.append((A + d, cost + w + _gap_cost(d, n), path + (p,), t))
                    if opts:
                        opts.sort(key=lambda o: (o[0], round(o[1], 9), o[2]))
                        keep, low = [], INF
                        for o in opts:
                            if round(o[1], 9) < low:
                                keep.append(o)
                                low = round(o[1], 9)
                        new[p] = keep
                fronts = new
                if not fronts:
                    break
            for p in sorted(fronts):
                for A, cost, path, tp in fronts[p]:
                    d = inc(tp, t0)
                    if not LOOP_MIN_GAP < d < M.PI - LOOP_MIN_GAP:
                        continue
                    key = (round(cost + _gap_cost(d, n), 9), 0 if sgn * area >= 0 else 1, path)
                    if best is None or key < best[0]:
                        best = (key, path, sgn)
    if best is None:
        return None
    pts = list(best[1])
    r_min = presets.TRANSIT_MODES[ln.mode].min_curve_radius_m or 0.0
    if r_min > 0:
        zones = [G.from_model_poly(dist[s.district_id].polygon) if every[k] else None
                 for k, s in enumerate(ring)]
        _deepen(pts, every, zones, best[2], (ox, oy), 1.15 * r_min, pads or {})
    at = dict(zip([id(s) for s in ring], pts))
    return [at.get(id(s), pts[0]) for s in ln.stops]


APEX_PAD_M = 30.0   # a loop's curve at a stop stays this far inside its district


def _apex_in(a, p, b, r: float, zone, pad: float = APEX_PAD_M) -> bool:
    """A curve of radius r at corner p (between a and b) passes inside zone, pad in: it cuts
    the corner by r (1 / cos(turn / 2) - 1) toward its inside."""
    if not zone.covers(Point(p)):
        return False
    th, _ = _turn_info([a, p, b], 1, False)
    la, lb = _d(a, p), _d(p, b)
    if th < M.radians(1.0) or la < 1.0 or lb < 1.0:
        return True
    e = r * (1.0 / float(M.cos(min(th, M.radians(150.0)) / 2.0)) - 1.0) + pad
    ix = (a[0] - p[0]) / la + (b[0] - p[0]) / lb
    iy = (a[1] - p[1]) / la + (b[1] - p[1]) / lb
    L = math.sqrt(ix * ix + iy * iy)
    if L < 1e-9:
        return True
    return bool(zone.covers(Point(p[0] + e * ix / L, p[1] + e * iy / L)))


def _deepen(pts: list, every: list, zones: list, sgn: float, o, r: float, pads: dict) -> None:
    """A loop stop whose corner the curves would cut out of its district moves (in place,
    a few rounds) to the junction of its district, still between its neighbors seen from
    the middle o, where the curve stays in (`_apex_in`, APEX_PAD_M in plus pads[k] for the
    k-th stop): the one nearest the ring and the even turn (the costs of `_loop_points`)."""
    n = len(pts)
    two_pi = 2.0 * M.PI

    def ang(p):
        return float(M.atan2(p[1] - o[1], p[0] - o[0]))

    def inc(a, b):
        return (sgn * (b - a)) % two_pi
    for _ in range(3):
        moved = False
        for k in range(n):
            if not every[k]:
                continue
            prv, nxt = pts[k - 1], pts[(k + 1) % n]
            pad = APEX_PAD_M + pads.get(k, 0.0)
            if _apex_in(prv, pts[k], nxt, r, zones[k], pad):
                continue
            tp, tn = ang(prv), ang(nxt)
            span = inc(tp, tn)
            best = None
            for p, t, w in every[k]:
                d1 = inc(tp, t)
                d2 = span - d1
                if not (LOOP_MIN_GAP < d1 < M.PI - LOOP_MIN_GAP and
                        LOOP_MIN_GAP < d2 < M.PI - LOOP_MIN_GAP):
                    continue
                if not _apex_in(prv, p, nxt, r, zones[k], pad):
                    continue
                key = (round(w + _gap_cost(d1, n) + _gap_cost(d2, n), 9), p)
                if best is None or key < best:
                    best = key
            if best is not None:
                pts[k] = best[1]
                moved = True
        if not moved:
            break


# ---------------------------------------------------------------------------
# Loops on Dubins rings (M8c)
# ---------------------------------------------------------------------------

RING_HEADINGS = 16      # headings a loop's ring may pass a stop in (22.5 degrees apart)
RING_GRID_M = 60.0      # pass points tried in a stop's district, on this grid at least ...
RING_POINTS = 160       # ... coarser where the district would give more than this many
RING_ROUNDS = 6         # rounds of the ring search, each moving every pose once
RING_EVALS = 400        # poses of one stop sampled in a round before its ring is clean
RING_VIAS = 2           # free poses a blocked ring may add (it goes round what it cannot pass)
RING_VIA_M = 720.0      # a free pose is tried this far around the blocked stretch
RING_VIA_GRID_M = 90.0
RING_RADII = (1.15, 1.06)   # times the mode's radius, the wider first
RING_R = 1.05           # an open line's curves as fitted at least this times the radius (a
#                         polyline measures a few percent tighter)
RING_ARC_W = 1.0        # a meter of curve costs this much more than a straight one (the same
#                         for every convex ring: it keeps rings from looping round a stop)
_TWO_PI = 2.0 * M.PI


def _mod2pi(x: float) -> float:
    return x - _TWO_PI * math.floor(x / _TWO_PI)


def _heading(k: int) -> float:
    return _TWO_PI * k / RING_HEADINGS


def _acos_s(x: float) -> float:
    x = min(1.0, max(-1.0, x))
    return M._atan2_s(math.sqrt((1.0 - x) * (1.0 + x)), x)


def dubins(a, b, rho: float):
    """The shortest path of curvature at most 1 / rho from pose a to pose b ((x, y, heading)):
    (length, word, (t, p, q)) with t, p, q in units of rho (the straight part of a CSC word
    too), or None when the poses coincide. Shkel and Lumelsky's six words; every angle from
    dmath."""
    dx, dy = b[0] - a[0], b[1] - a[1]
    D = math.sqrt(dx * dx + dy * dy)
    d = D / rho
    th = _mod2pi(M._atan2_s(dy, dx)) if D > 1e-9 else 0.0
    al, be = _mod2pi(a[2] - th), _mod2pi(b[2] - th)
    sa, sb = M._sin_s(al), M._sin_s(be)
    ca, cb = M._cos_s(al), M._cos_s(be)
    cab = M._cos_s(al - be)
    best = None

    def take(word, t, p, q_):
        nonlocal best
        L = t + p + q_
        if best is None or L < best[0] - 1e-12:
            best = (L, word, (t, p, q_))
    p2 = 2.0 + d * d - 2.0 * cab + 2.0 * d * (sa - sb)
    if p2 >= 0.0:
        tmp = M._atan2_s(cb - ca, d + sa - sb)
        take("LSL", _mod2pi(-al + tmp), math.sqrt(p2), _mod2pi(be - tmp))
    p2 = 2.0 + d * d - 2.0 * cab + 2.0 * d * (sb - sa)
    if p2 >= 0.0:
        tmp = M._atan2_s(ca - cb, d - sa + sb)
        take("RSR", _mod2pi(al - tmp), math.sqrt(p2), _mod2pi(-be + tmp))
    p2 = -2.0 + d * d + 2.0 * cab + 2.0 * d * (sa + sb)
    if p2 >= 0.0:
        p = math.sqrt(p2)
        tmp = M._atan2_s(-ca - cb, d + sa + sb) - M._atan2_s(-2.0, p)
        take("LSR", _mod2pi(-al + tmp), p, _mod2pi(-_mod2pi(be) + tmp))
    p2 = -2.0 + d * d + 2.0 * cab - 2.0 * d * (sa + sb)
    if p2 >= 0.0:
        p = math.sqrt(p2)
        tmp = M._atan2_s(ca + cb, d - sa - sb) - M._atan2_s(2.0, p)
        take("RSL", _mod2pi(al - tmp), p, _mod2pi(be - tmp))
    tmp = (6.0 - d * d + 2.0 * cab + 2.0 * d * (sa - sb)) / 8.0
    if abs(tmp) <= 1.0:
        p = _mod2pi(_TWO_PI - _acos_s(tmp))
        t = _mod2pi(al - M._atan2_s(ca - cb, d - sa + sb) + p / 2.0)
        take("RLR", t, p, _mod2pi(al - be - t + p))
    tmp = (6.0 - d * d + 2.0 * cab + 2.0 * d * (sb - sa)) / 8.0
    if abs(tmp) <= 1.0:
        p = _mod2pi(_TWO_PI - _acos_s(tmp))
        t = _mod2pi(-al - M._atan2_s(ca - cb, d + sa - sb) + p / 2.0)
        take("LRL", t, p, _mod2pi(be - al - t + p))
    if best is None:
        return None
    return best[0] * rho, best[1], best[2]


def dubins_points(a, word: str, params, rho: float, step: float = 10.0) -> list[tuple]:
    """Points along a Dubins path from pose a, at most step apart (the first is a's)."""
    x, y, h = float(a[0]), float(a[1]), float(a[2])
    out = [(G.q(x), G.q(y))]
    for kind, u in zip(word, params):
        L = u * rho
        if L <= 1e-9:
            continue
        m = max(1, int(math.ceil(L / step)))
        f = np.arange(1, m + 1, dtype=np.float64) / m
        if kind == "S":
            xs = x + L * f * M._cos_s(h)
            ys = y + L * f * M._sin_s(h)
            h1 = h
        elif kind == "L":
            cx, cy = x - rho * M._sin_s(h), y + rho * M._cos_s(h)
            hs = h + u * f
            xs, ys = cx + rho * M.sin(hs), cy - rho * M.cos(hs)
            h1 = h + u
        else:
            cx, cy = x + rho * M._sin_s(h), y - rho * M._cos_s(h)
            hs = h - u * f
            xs, ys = cx - rho * M.sin(hs), cy + rho * M.cos(hs)
            h1 = h - u
        for px, py in zip(np.atleast_1d(xs).tolist(), np.atleast_1d(ys).tolist()):
            p = (G.q(px), G.q(py))
            if p != out[-1]:
                out.append(p)
        x, y, h = float(np.atleast_1d(xs)[-1]), float(np.atleast_1d(ys)[-1]), h1
    return out


def _cells(c: Ctx, pts) -> np.ndarray:
    """The raster cell of every point (`cell_of`, vectorized)."""
    a = np.array(pts, dtype=np.float64)
    i = np.clip(np.floor((a[:, 0] - c.x0) / CELL_M).astype(np.int64), 0, c.nx - 1)
    j = np.clip(np.floor((a[:, 1] - c.y0) / CELL_M).astype(np.int64), 0, c.ny - 1)
    return j * c.nx + i


def _arc_of(path, rho: float) -> float:
    """The length of a Dubins path's curves."""
    _, word, (t, p, q_) = path
    return (t + q_ + (p if word[1] != "S" else 0.0)) * rho


def _grid_in(zone, step: float) -> list[tuple]:
    x0, y0, x1, y1 = G.qbounds(zone)
    out = []
    for j in range(int(math.ceil(y0 / step)), int(math.floor(y1 / step)) + 1):
        for i in range(int(math.ceil(x0 / step)), int(math.floor(x1 / step)) + 1):
            p = (q(i * step), q(j * step))
            if zone.covers(Point(p)):
                out.append(p)
    return out


def _dubins_track(c: Ctx, ln: Line, cost, r_min: float):
    """M8c: a line as Dubins paths from stop to stop, straight runs and arcs of RING_RADII
    times the mode's radius (a loop as one ring): each stop is passed at a point APEX_PAD_M
    inside its zone (a sky tube's nexus in its tower, an exit at its point heading off the
    map) in one of RING_HEADINGS headings. The poses are searched in turn (coordinate
    descent from the stop points, the cheaper paths first), keeping the track over the
    fewest cells the line cannot pass, then the cheapest over the raster costs and its
    curves (towers it climbs cost more, portals less); a track still blocked adds free
    poses beside the blocked stretch. Its curves are the mode's by construction, so where
    legs and their fitted curves would cut a stop, turn back at one or wind between towers,
    this track passes. Returns (track, pass point of each stop, radius) for a clean track
    that keeps clear of itself, else None."""
    stops = _ring_of(ln.stops) if ln.loop else list(ln.stops)
    n = len(stops)
    if n < (3 if ln.loop else 2):
        return None
    x0, y0, x1, y1 = c.m.bounds
    cands, heads = [], []
    every = list(range(RING_HEADINGS))
    for k, s in enumerate(stops):
        z = _zone(s)
        if z is not None:
            # (mitre joins: no arcs, so no libm trigonometry in GEOS)
            zi = G.qpoly(z.buffer(-APEX_PAD_M, join_style="mitre"))
            z = zi if not zi.is_empty else z
            shapely.prepare(z)
        heads.append(every)
        if s.kind == "exit":
            # off the map at its nearest edge (into the map, for a line that starts there)
            q4 = RING_HEADINGS // 4
            out = min(((round(s.p[0] - x0, 2), 2 * q4), (round(x1 - s.p[0], 2), 0),
                       (round(s.p[1] - y0, 2), 3 * q4), (round(y1 - s.p[1], 2), q4)))
            h = out[1] if k else (out[1] + RING_HEADINGS // 2) % RING_HEADINGS
            heads[-1] = sorted((h + d) % RING_HEADINGS for d in (-2, -1, 0, 1, 2))
            cands.append([s.p])
        elif z is not None and s.tower_id is None:
            step = RING_GRID_M
            area = G.area(z)
            if area / (step * step) > RING_POINTS:
                step = 30.0 * math.ceil(math.sqrt(area / RING_POINTS) / 30.0)
            pts = set(_grid_in(z, step))
            if s.kind == "district":
                pts.update(p for p, _ in _district_cands(c, _district_of(c, s), ln.mode, False)
                           if z.covers(Point(p)))
            if z.covers(Point(s.p)):
                pts.add(s.p)
            cands.append(sorted(pts) or [s.p])
        else:
            cands.append([s.p])
    fin = np.isfinite(cost)
    cmin = float(cost[fin].min()) if fin.any() else 1.0
    for f in RING_RADII:
        rho = f * r_min
        res = _pose_descent(c, stops, cands, heads, cost, rho, cmin, ln.mode, ln.loop)
        if res is not None:
            return res[0], res[1], rho
    return None


def _pose_descent(c: Ctx, stops, cands, heads, cost, rho: float, cmin: float, mode: str,
                  closed: bool):
    """The coordinate descent of `_dubins_track`."""
    n = len(stops)
    seg_cache: dict = {}
    len_cache: dict = {}

    def pose(p, h):
        return (p[0], p[1], h)

    def low(a, b):
        """A lower bound of seg(a, b)'s cost (the path at the cheapest cost, its curves),
        None when there is no path."""
        key = (a, b)
        if key not in len_cache:
            len_cache[key] = dubins((a[0], a[1], _heading(a[2])), (b[0], b[1],
                                                                   _heading(b[2])), rho)
        r = len_cache[key]
        if r is None:
            return None
        return cmin * r[0] + RING_ARC_W * _arc_of(r, rho)

    def seg(a, b):
        """(blocked points, cost integral and curves, points) of the path from pose a to
        pose b."""
        key = (a, b)
        if key not in seg_cache:
            r = len_cache.get(key) or dubins((a[0], a[1], _heading(a[2])),
                                             (b[0], b[1], _heading(b[2])), rho)
            pts = dubins_points((a[0], a[1], _heading(a[2])), r[1], r[2], rho)
            cv = cost[_cells(c, pts)]
            ok = np.isfinite(cv)
            mid = np.where(ok[:-1] & ok[1:], (cv[:-1] + cv[1:]) / 2.0, 0.0)
            dx, dy = np.diff([p[0] for p in pts]), np.diff([p[1] for p in pts])
            steps = np.sqrt(dx * dx + dy * dy)
            seg_cache[key] = (int((~ok).sum()), round(math.fsum((mid * steps).tolist()) +
                                                      RING_ARC_W * _arc_of(r, rho), 6), pts)
        return seg_cache[key]

    def pairs(ps):
        m = len(ps)
        return [(ps[k], ps[(k + 1) % m]) for k in range(m if closed else m - 1)]

    def total(ps):
        segs = [seg(a, b) for a, b in pairs(ps)]
        return (sum(x[0] for x in segs), round(math.fsum(x[1] for x in segs), 6)), segs

    def clear(ps):
        """Whether the track keeps clear of itself (`meets`), and its points."""
        pts = []
        for a, b in pairs(ps):
            for p in seg(a, b)[2]:
                if not pts or p != pts[-1]:
                    pts.append(p)
        if closed and pts[0] != pts[-1]:
            pts.append(pts[0])
        return LineString(pts).is_simple and not meets(pts, closed, mode), pts

    # first poses: the stop points, headed along the chord between their neighbors
    P = [s.p if s.p in cands[k] else min(cands[k], key=lambda x: (round(_d(x, s.p), 2), x))
         for k, s in enumerate(stops)]
    poses = []
    for k in range(n):
        a = P[k - 1] if closed or k > 0 else P[k]
        b = P[(k + 1) % n] if closed or k < n - 1 else P[k]
        t = _mod2pi(M._atan2_s(b[1] - a[1], b[0] - a[0]))
        h = int(round(t / _heading(1))) % RING_HEADINGS
        if h not in heads[k]:
            h = min(heads[k], key=lambda x: (min((x - h) % RING_HEADINGS,
                                                 (h - x) % RING_HEADINGS), x))
        poses.append(pose(P[k], h))
    where = list(cands)                     # the points each pose may take (free poses too)
    hdg = list(heads)
    owner = list(range(n))                  # the stop of each pose, -1 for a free pose
    if any(low(a, b) is None for a, b in pairs(poses)):
        return None
    cur, _ = total(poses)
    for _round in range(RING_ROUNDS + 2 * RING_VIAS):
        moved = False
        for k in range(len(poses)):
            m = len(poses)
            prv = poses[k - 1] if closed or k > 0 else None
            nxt = poses[(k + 1) % m] if closed or k < m - 1 else None
            opts = []
            for p in where[k]:
                for h in hdg[k]:
                    ps = pose(p, h)
                    l1 = low(prv, ps) if prv is not None else 0.0
                    l2 = low(ps, nxt) if nxt is not None else 0.0
                    if l1 is not None and l2 is not None:
                        opts.append((round(l1 + l2, 6), p, h))
            opts.sort()
            here = [seg(prv, poses[k]) if prv is not None else (0, 0.0),
                    seg(poses[k], nxt) if nxt is not None else (0, 0.0)]
            rest = (cur[0] - here[0][0] - here[1][0], cur[1] - here[0][1] - here[1][1])
            best, pick, tried = cur, None, 0
            for L, p, h in opts:
                if best[0] == 0 and L >= best[1] - rest[1]:
                    break
                if best[0] > 0 and tried >= RING_EVALS:
                    break
                ps = pose(p, h)
                if ps == poses[k]:
                    continue
                tried += 1
                s1 = seg(prv, ps) if prv is not None else (0, 0.0)
                s2 = seg(ps, nxt) if nxt is not None else (0, 0.0)
                val = (rest[0] + s1[0] + s2[0], round(rest[1] + s1[1] + s2[1], 6))
                if val < best:
                    trial = list(poses)
                    trial[k] = ps
                    if clear(trial)[0]:
                        best, pick = val, ps
            if pick is not None:
                poses[k] = pick
                cur, moved = best, True
        if cur[0] > 0 and not moved and owner.count(-1) < RING_VIAS:
            # a free pose beside the most blocked stretch, tried around it
            segs = total(poses)[1]
            k = max(range(len(segs)), key=lambda i: (segs[i][0], -i))
            bad = [p for p in segs[k][2] if not np.isfinite(cost[cell_of(c, p)])]
            mx = q(math.fsum(p[0] for p in bad) / len(bad))
            my = q(math.fsum(p[1] for p in bad) / len(bad))
            box = G.qpoly(shapely.box(mx - RING_VIA_M, my - RING_VIA_M, mx + RING_VIA_M,
                                      my + RING_VIA_M))
            pts_v = [p for p in _grid_in(box, RING_VIA_GRID_M)
                     if _d(p, (mx, my)) <= RING_VIA_M and np.isfinite(cost[cell_of(c, p)])]
            if not pts_v:
                break
            a, b = poses[k], poses[(k + 1) % len(poses)]
            t = _mod2pi(M._atan2_s(b[1] - a[1], b[0] - a[0]))
            p0 = min(pts_v, key=lambda x: (round(_d(x, (mx, my)), 2), x))
            poses.insert(k + 1, pose(p0, int(round(t / _heading(1))) % RING_HEADINGS))
            owner.insert(k + 1, -1)
            where.insert(k + 1, pts_v)
            hdg.insert(k + 1, list(range(RING_HEADINGS)))
            cur, _ = total(poses)
            continue
        if not moved:
            break
    if cur[0] > 0:
        return None
    ok, pts = clear(poses)
    if not ok:
        return None
    passes = [(poses[k][0], poses[k][1]) for k in range(len(poses)) if owner[k] >= 0]
    return _densify(pts), passes


def _district_of(c: Ctx, s: Stop):
    return next(d for d in c.m.districts if d.id == s.district_id)


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
          lo: float = 0.0, tall_scale: float = 1.0) -> tuple:
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
            cost[p_] = max(cost[p_], k["tall"] * tall_scale)
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


def reachable(c: Ctx, cost: np.ndarray, a: int, b: int) -> bool:
    """Whether the 16 moves of `search` lead from cell a to cell b over passable cells (a
    numpy flood fill: a search that cannot arrive returns at once instead of visiting every
    cell in every direction)."""
    nx, ny = c.nx, c.ny
    ok = (cost != INF).reshape(ny, nx)
    ok.flat[a] = ok.flat[b] = True
    reach = np.zeros((ny, nx), bool)
    reach.flat[a] = True
    by, bx = divmod(b, nx)
    while not reach[by, bx]:
        grown = reach.copy()
        for dx, dy, _ in _MOVES:
            # cells (x + dx, y + dy) reached from reached cells (x, y)
            ys, yd = (slice(0, ny - dy), slice(dy, ny)) if dy >= 0 else \
                (slice(-dy, ny), slice(0, ny + dy))
            xs, xd = (slice(0, nx - dx), slice(dx, nx)) if dx >= 0 else \
                (slice(-dx, nx), slice(0, nx + dx))
            grown[yd, xd] |= reach[ys, xs]
        grown &= ok
        if (grown == reach).all():
            return False
        reach = grown
    return True


TOGO_M = 600.0   # a search longer than this is guided by the exact cost to go (`_togo`)


def _togo(c: Ctx, cl: list, b: int) -> list:
    """The cost from every cell to cell b over the 16 moves, turns left out (numpy
    relaxation until nothing changes): a lower bound of `search`'s cost, so a heuristic
    that never overestimates and leads the search along the cheap ground."""
    nx, ny = c.nx, c.ny
    C = np.array(cl, dtype=np.float64).reshape(ny, nx)
    bad = ~np.isfinite(C)
    D = np.full((ny, nx), INF)
    D.flat[b] = 0.0
    while True:
        N = D.copy()
        for dx, dy, L in _MOVES:
            # from (x, y) to (x + dx, y + dy): D(x, y) <= w + D(x + dx, y + dy)
            ys, yd = (slice(0, ny - dy), slice(dy, ny)) if dy >= 0 else \
                (slice(-dy, ny), slice(0, ny + dy))
            xs, xd = (slice(0, nx - dx), slice(dx, nx)) if dx >= 0 else \
                (slice(-dx, nx), slice(0, nx + dx))
            w = L * CELL_M * (C[ys, xs] + C[yd, xd]) / 2.0
            np.minimum(N[ys, xs], D[yd, xd] + w, out=N[ys, xs])
        N[bad] = INF
        N.flat[b] = 0.0
        if np.array_equal(N, D):
            return D.ravel().tolist()
        D = N


REACH_POPS = 20000   # a search this long checks first whether it can arrive at all


def search(c: Ctx, cost: np.ndarray, a: int, b: int, turn: float, din=None
           ) -> list[int] | None:
    """A* from cell a to cell b (both always passable); 16 moves; a turn penalty for every
    change of direction above 45 degrees, from the arrival direction din at a (the previous
    leg's), so a line does not turn back at a stop. M8b: integer states (flat arrays for a
    long search), over TOGO_M the exact turn-free cost to go as the heuristic (the straight
    distance at the cheapest cost otherwise), and a search that has run REACH_POPS steps
    stops at once if b cannot be reached (`reachable`)."""
    nx, ny = c.nx, c.ny
    cl = cost.tolist()
    cl[a] = min(cl[a], 2.0) if cl[a] == INF else cl[a]
    cl[b] = min(cl[b], 2.0) if cl[b] == INF else cl[b]
    bx, by = b % nx, b // nx
    pos = cost[cost > 0]
    cmin = min(float(pos.min()) if pos.size else INF, *(x for x in (cl[a], cl[b]) if x > 0))
    d0 = -1
    if din is not None:
        d0 = max(range(len(_MOVES)), key=lambda k: ((_MOVES[k][0] * din[0] + _MOVES[k][1] *
                                                      din[1]) / _MOVES[k][2], -k))
    nm = len(_MOVES)
    ns = nm + 1                       # a state: cell * ns + arrival move (nm: none)
    moves = [(k, dx, dy, L * CELL_M) for k, (dx, dy, L) in enumerate(_MOVES)]
    pen = [[0.0] * nm for _ in range(nm)]
    if turn > 0:
        for du, (ddx, ddy, dL) in enumerate(_MOVES):
            for k, (dx, dy, L) in enumerate(_MOVES):
                cosang = (ddx * dx + ddy * dy) / (dL * L)
                if cosang < 0.70:
                    pen[du][k] = turn * (1.0 - cosang)
    far = math.hypot(a % nx - bx, a // nx - by) * CELL_M > TOGO_M
    togo = _togo(c, cl, b) if far else None
    if far:
        g = [INF] * (nx * ny * ns)
        came = [-1] * (nx * ny * ns)
        done = bytearray(nx * ny * ns)
    else:
        g, came, done = _Table(INF), _Table(-1), _Table(0)
    start = a * ns + (d0 if d0 >= 0 else nm)
    g[start] = 0.0
    heap = [(0.0, 0, a, d0)]
    cnt = 1
    pops = 0
    push, pop, sqrt = heapq.heappush, heapq.heappop, math.sqrt
    while heap:
        _, _, u, du = pop(heap)
        key = u * ns + (du if du >= 0 else nm)
        if done[key]:
            continue
        done[key] = 1
        pops += 1
        if pops == REACH_POPS and not reachable(c, cost, a, b):
            return None
        if u == b:
            path = [u]
            while came[key] >= 0:
                key = came[key]
                path.append(key // ns)
            return path[::-1]
        ux, uy = u % nx, u // nx
        gu = g[key]
        cu = cl[u]
        pu = pen[du] if du >= 0 else None
        for k, dx, dy, LC in moves:
            vx, vy = ux + dx, uy + dy
            if vx < 0 or vy < 0 or vx >= nx or vy >= ny:
                continue
            v = vy * nx + vx
            cv = cl[v]
            if cv == INF:
                continue
            step = LC * (cu + cv) / 2.0
            if pu is not None and turn > 0:
                step += pu[k]
            nk = v * ns + k
            nd = gu + step
            if nd < g[nk]:
                g[nk] = nd
                came[nk] = key
                h = togo[v] if togo is not None else \
                    sqrt((vx - bx) ** 2 + (vy - by) ** 2) * CELL_M * cmin
                push(heap, (nd + h, cnt, v, k))
                cnt += 1
    return None


class _Table(dict):
    """A sparse array: a dict whose missing entries read as the default (a short search
    touches few of the cell and direction states)."""

    def __init__(self, default):
        super().__init__()
        self.default = default

    def __missing__(self, key):
        return self.default


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
    tall_scale: float = 1.0                      # raster: cost of the towers it would clear
    on_roads: bool = True                        # road modes: legs on the road graph
    corners: dict = field(default_factory=dict)  # stop index -> guide corner (fast lines)
    keep_free: bool = False                      # legs may run back along the line
    held: bool = False                           # M10: the old track kept (regeneration)


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
            if s.road_class not in w or s.attrs.get("role") == "ramp":
                continue
            pts = [tuple(p) for p in s.centerline]
            a = self.pos.get(s.start)
            if a is not None and _d(pts[-1], a) < _d(pts[0], a):
                pts = pts[::-1]
            # a deck the track must climb over (M7: not a low approach or a ramp's foot)
            raised = not s.bridge and any(z.z > RAISED_MIN_M for z in s.z_profile)
            f = w[s.road_class] * (RAISED_W if raised and mode != "maglev" else 1.0)
            # M7: a highway and the avenue under it still meet at the overpass for a track
            # above both (a node of the graph there)
            cuts = [0]
            for ov in s.attrs.get("overpass_at", []):
                ov = (q(ov[0]), q(ov[1]))
                if ov in pts[1:-1]:
                    cuts.append(pts.index(ov))
                    self.pos[f"ov{ov[0]:.2f}_{ov[1]:.2f}"] = ov
            cuts = sorted(set(cuts)) + [len(pts) - 1]
            ids = [s.start] + [f"ov{pts[i][0]:.2f}_{pts[i][1]:.2f}" for i in cuts[1:-1]] + \
                [s.end]
            for part, (a_, b_, na, nb) in enumerate(zip(cuts, cuts[1:], ids, ids[1:])):
                sub = pts[a_:b_ + 1]
                wt = _plen(sub) * f
                key = k if len(cuts) == 2 else (k, part)
                self.adj.setdefault(na, []).append((nb, key, wt, sub))
                self.adj.setdefault(nb, []).append((na, key, wt, sub[::-1]))
                if s.road_class in ("avenue", "highway"):
                    self.major.update((na, nb))
        for key in self.adj:
            self.adj[key].sort(key=lambda e: (e[0], e[1] if isinstance(e[1], tuple)
                                              else (e[1], -1)))
        self.turn = TURN_M[mode]
        # every edge once, for the legs a line must keep off (its own earlier legs)
        seen: dict = {}
        for u in sorted(self.adj):
            for v, k, wt, pts in self.adj[u]:
                seen.setdefault(k, pts)
        self.ekeys = list(seen)
        self.at = {}
        for nid in sorted(self.adj):
            self.at.setdefault((q(self.pos[nid][0]), q(self.pos[nid][1])), nid)
        self.elines = [LineString(seen[k]) for k in self.ekeys]
        self.etree = shapely.STRtree(self.elines) if self.elines else None

    def targets(self, st: Stop, c: Ctx) -> set:
        """Where a leg may reach a stop: its node (`node_near`), and for a district stop any
        junction within STOP_REACH_M of its point in the district (the leg passes it on its
        way instead of turning there)."""
        n0 = self.node_near(st, c)
        if n0 is None:
            return set()
        out = {n0}
        if st.kind == "district" and st.z is None:
            dpoly = next((G.from_model_poly(d.polygon) for d in c.m.districts
                          if d.id == st.district_id), None)
            if dpoly is not None:
                for nid in sorted(self.adj):
                    x = self.pos[nid]
                    if not nid.startswith("ov") and _d(x, st.p) <= STOP_REACH_M and \
                            dpoly.covers(Point(x)):
                        out.add(nid)
        elif _site_end(st):
            # M8b: a site at a line's end, reached where its zone begins (an avenue or
            # highway junction in it), not round the site to the node beside its middle
            zone = _site_zone(st)
            for nid in sorted(self.major):
                if not nid.startswith("ov") and zone.covers(Point(self.pos[nid])):
                    out.add(nid)
        return out

    def touching(self, geom) -> set:
        """The edges that meet geom."""
        if self.etree is None or geom is None or geom.is_empty:
            return set()
        return {self.ekeys[i] for i in self.etree.query(geom, predicate="intersects").tolist()}

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

    def route(self, a: str, b, din=None, used=frozenset(), avoid=frozenset(),
              dend=None) -> tuple | None:
        """Cheapest path from node a to node b (or the first of a set of nodes) with a turn
        penalty at every node, starting in direction din (the previous leg's arrival), off the
        edges in avoid, and (dend) arriving so that it can go on in that direction (a loop's
        first leg): (the polyline, its edges, the node it ends at)."""
        goal = {b} if isinstance(b, str) else set(b)
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
            if u in goal:
                runs, ks = self._chain(came, key)
                return self._join(runs), ks, u
            din = arrive[key]
            for v, k, wt, pts in self.adj.get(u, ()):
                if k == ku or k in avoid:
                    continue
                step = wt * (REUSE_W if k in used else 1.0)
                if din is not None:
                    dout = self._dir(pts)
                    cosang = max(-1.0, min(1.0, din[0] * dout[0] + din[1] * dout[1]))
                    if cosang < MAX_TURN_COS:
                        continue      # a train does not turn back (its curves would cut it)
                    if cosang < 0.94:
                        step += self.turn * (1.0 - cosang)
                if v in goal and dend is not None:
                    arr = self._dir(pts, rev=True)
                    cosang = max(-1.0, min(1.0, arr[0] * dend[0] + arr[1] * dend[1]))
                    if cosang < MAX_TURN_COS:
                        continue
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
    first (a loop's to the junctions that keep it one simple ring, `_loop_points`); where
    that leaves a stop unserved or the track meeting itself, again from the district points,
    and the route that serves more stops, then meets itself less."""
    mode = ln.mode
    stops = ln.stops
    dist = {d.id: d for d in c.m.districts}
    home = [s.p for s in stops]
    r_min = presets.TRANSIT_MODES[mode].min_curve_radius_m or 0.0
    fast_cost = None
    for k in range(1, len(stops) - 1):
        st = stops[k]
        # (a loop's stops move below: the chord between its neighbors crosses the loop)
        if not ln.loop and st.kind == "district" and st.z is None and \
                st.district_id in dist:
            chord = LineString([stops[k - 1].p, stops[k + 1].p])
            if chord.length > 1.0 and r_min >= FAST_R:
                if fast_cost is None:
                    fast_cost = costs(c, mode, ln.z0, ln.through, None, ln.alt[1],
                                      ln.alt[0], ln.tall_scale)[0]
                st.p, corner = _fast_point(c, dist[st.district_id], mode, stops[k - 1].p,
                                           stops[k + 1].p, fast_cost)
                if corner is not None:
                    ln.corners[k] = corner
            elif chord.length > 1.0:
                st.p = _district_point(c, dist[st.district_id], mode, chord)
    if not ln.loop and len(stops) >= 2:
        for k, nb in ((0, 1), (len(stops) - 1, len(stops) - 2)):
            if _site_end(stops[k]):
                if fast_cost is None:
                    fast_cost = costs(c, mode, ln.z0, ln.through, None, ln.alt[1],
                                      ln.alt[0], ln.tall_scale)[0]
                stops[k].p = _site_point(c, stops[k], stops[nb].p, fast_cost)
    if ln.loop:
        ring = _loop_points(c, ln)
        if ring is not None:
            for s, p in zip(stops, ring):
                s.p = p
        if mode not in ROAD_MODES and r_min > 0:
            # M8c: a flying loop as one ring of Dubins paths, when one is clear
            cost = costs(c, mode, ln.z0, ln.through, None, ln.alt[1], ln.alt[0],
                         ln.tall_scale)[0]
            dub = _dubins_track(c, ln, cost, r_min)
            if dub is not None:
                track, passes, rho = dub
                at = dict(zip([id(s) for s in _ring_of(stops)], passes))
                for s in stops:
                    s.p = at.get(id(s), passes[0])
                ln.pts, ln.min_radius = track, rho
                ln.stop_at = ordered_stops(track, stops, True)
                return
    moved = [s.p for s in stops]
    notes, conflicts = list(ln.notes), list(ln.conflicts)
    _route(c, ln)

    def flaws():
        return (sum(1 for s in stops if not _served(ln.pts, s)), meets(ln.pts, ln.loop, mode))

    def tight():
        return ln.min_radius < 0.95 * r_min
    if moved != home and flaws() != (0, 0):
        first = (ln.pts, ln.min_radius, ln.stop_at, ln.notes, ln.conflicts, flaws())
        for s, p in zip(stops, home):
            s.p = p
        ln.notes, ln.conflicts = list(notes), list(conflicts)
        _route(c, ln)
        if flaws() >= first[5]:
            ln.pts, ln.min_radius, ln.stop_at, ln.notes, ln.conflicts = first[:5]
            for s, p in zip(stops, moved):
                s.p = p
    elif moved == home or flaws() == (0, 0):
        if tight() and mode not in ROAD_MODES:
            _straighter(c, ln, flaws, notes, conflicts)
    # (a loop on the roads is routed off them next instead of trying other junctions)
    if (flaws() != (0, 0) or tight()) and mode in ROAD_MODES and not ln.loop:
        _restop(c, ln, flaws, notes, conflicts)
    if ln.min_radius < r_min and mode in ROAD_MODES and not ln.loop:
        _spurs(c, ln, flaws, notes, conflicts)
    if mode in ROAD_MODES and not ln.loop:
        _off_roads_line(c, ln, flaws, notes, conflicts)
    if ln.loop and mode in ROAD_MODES:
        _off_roads(c, ln, flaws, moved, notes, conflicts)
    if not ln.loop and r_min > 0:
        _dubins_line(c, ln, flaws, r_min)


def _line_score(c: Ctx, ln: Line, flaws, r_min: float) -> tuple:
    """How flawed an open line is, lower better: stops missed and places where it meets
    itself, a curve under its radius (as fitted, RING_R: a polyline measures a few percent
    tighter), buildings in its corridor it cannot pass."""
    return (flaws(), 1 if ln.min_radius < RING_R * r_min else 0,
            len(_corridor(c, ln, ln.pts, check_only=True)))


def _dubins_line(c: Ctx, ln: Line, flaws, r_min: float) -> None:
    """M8c: an open line still flawed after its routes on and off the roads, as Dubins paths
    from stop to stop (`_dubins_track`: a stop it must turn back at gets a loop of the
    mode's radius instead of a hairpin the curves cut); kept when that is better."""
    first = _line_score(c, ln, flaws, r_min)
    if first == ((0, 0), 0, 0):
        return
    cost = costs(c, ln.mode, ln.z0, ln.through, None, ln.alt[1], ln.alt[0], ln.tall_scale)[0]
    dub = _dubins_track(c, ln, cost, r_min)
    if dub is None:
        return
    before = (ln.pts, ln.min_radius, ln.stop_at, ln.on_roads, [s.p for s in ln.stops])
    track, passes, rho = dub
    for s, p in zip(ln.stops, passes):
        s.p = p
    ln.pts, ln.min_radius, ln.on_roads = track, rho, False
    ln.stop_at = ordered_stops(track, ln.stops, False)
    if _line_score(c, ln, flaws, r_min) < first:
        ln.notes.append(f"{ln.name}: drawn from stop to stop with {rho:g} m curves")
        return
    ln.pts, ln.min_radius, ln.stop_at, ln.on_roads, pts = before
    for s, p in zip(ln.stops, pts):
        s.p = p


OFF_ROADS_LONGER = 1.35   # a loop on the roads this much longer than off them goes off them
DEEPEN_TRIES = 3          # rings a loop off the roads tries, stops the curves cut deeper
DEEPEN_STEP_M = 60.0      # each time


def _off_roads(c: Ctx, ln: Line, flaws, ring: list, notes: list, conflicts: list) -> None:
    """M8b: a road-following loop routed again with its legs on the raster, from the ring's
    points (avenues still cost least; its own viaducts elsewhere), kept when that serves
    more stops or meets itself less, then has no curve too tight, or is the same but the
    roads made a ring OFF_ROADS_LONGER times longer (the roads cannot make one simple ring
    through its stops: one bridge between two of them, a stop at a road's end, so the legs
    go round each other)."""
    r_min = presets.TRANSIT_MODES[ln.mode].min_curve_radius_m or 0.0

    def score():
        return (flaws(), 1 if ln.min_radius < 0.95 * r_min else 0)
    before = (score(), ln.pts, ln.min_radius, ln.stop_at, ln.notes, ln.conflicts,
              [s.p for s in ln.stops])
    ln.on_roads = False
    best = None
    pads: dict = {}
    ring_of = _ring_of(ln.stops)
    for _ in range(DEEPEN_TRIES):
        for s, p in zip(ln.stops, ring):
            s.p = p
        ln.notes, ln.conflicts = list(notes), list(conflicts)
        _route(c, ln)
        if best is None or score() < best[0]:
            best = (score(), ln.pts, ln.min_radius, ln.stop_at, ln.notes, ln.conflicts,
                    [s.p for s in ln.stops])
        # a stop the curves still cut away: its corner deeper in its district next time
        cut = [k for k, s in enumerate(ring_of) if not _served(ln.pts, s)]
        if not cut:
            break
        for k in cut:
            pads[k] = pads.get(k, 0.0) + DEEPEN_STEP_M
        nxt = _loop_points(c, ln, pads)
        if nxt is None or nxt == ring:
            break
        ring = nxt
    sc, ln.pts, ln.min_radius, ln.stop_at, ln.notes, ln.conflicts, pts = best
    for s, p in zip(ln.stops, pts):
        s.p = p
    if sc < before[0] or (sc == before[0] and
                          _plen(before[1]) > OFF_ROADS_LONGER * _plen(ln.pts)):
        ln.notes.append(f"{ln.name}: off the roads where they would not make one ring through "
                        f"its stops")
        return
    _, ln.pts, ln.min_radius, ln.stop_at, ln.notes, ln.conflicts, pts = before
    for s, p in zip(ln.stops, pts):
        s.p = p
    ln.on_roads = True


def _off_roads_line(c: Ctx, ln: Line, flaws, notes: list, conflicts: list) -> None:
    """M8c: an open road line still flawed on the roads (a stop missed, a curve under its
    radius where a road turns hard beside buildings it cannot take out, or such a building
    in its corridor, which it would climb over: a hub's site buildings beside the road to
    its platform) routed again with its legs on the raster (avenues still cheapest, its own
    viaduct elsewhere), then also with its middle stops at a site, place or island moved to
    where their zone meets the way between their neighbors (`_way_point`; a hub's platform
    between two stops close together makes a hairpin); the best route is kept: fewer stops
    missed or places where it meets itself, then no curve too tight, then nothing in its
    corridor it cannot pass."""
    r_min = presets.TRANSIT_MODES[ln.mode].min_curve_radius_m or 0.0

    def score():
        return _line_score(c, ln, flaws, r_min)

    def snap():
        return (score(), ln.pts, ln.min_radius, ln.stop_at, ln.notes, ln.conflicts,
                [s.p for s in ln.stops], ln.on_roads, ln.keep_free)
    best = snap()
    if best[0] == ((0, 0), 0, 0):
        return
    home = best[6]
    cost = None
    for move in (False, True):
        if move:
            mid = [k for k, s in enumerate(ln.stops[1:-1], 1)
                   if s.kind in ("megasite", "place", "island") and s.tower_id is None]
            if not mid:
                break
            cost = costs(c, ln.mode, ln.z0, ln.through, None, ln.alt[1], ln.alt[0],
                         ln.tall_scale)[0]
        for on in ((False,) if not move else (True, False)):
            for s, p in zip(ln.stops, home):
                s.p = p
            if move:
                for k in mid:
                    ln.stops[k].p = _way_point(c, ln.stops[k], ln.stops[k - 1].p,
                                               ln.stops[k + 1].p, cost)
            ln.on_roads, ln.keep_free = on, False
            ln.notes, ln.conflicts = list(notes), list(conflicts)
            _route(c, ln)
            if score() < best[0]:
                best = snap()
                best[4].append(f"{ln.name}: off the roads where they turn too hard or pass "
                               f"what it cannot" if not on else
                               f"{ln.name}: passes its middle stops on its way")
            if best[0] == ((0, 0), 0, 0):
                break
        if best[0] == ((0, 0), 0, 0):
            break
    (_, ln.pts, ln.min_radius, ln.stop_at, ln.notes, ln.conflicts, pts, ln.on_roads,
     ln.keep_free) = best
    for s, p in zip(ln.stops, pts):
        s.p = p


def _way_point(c: Ctx, s: Stop, prev, nxt, cost) -> tuple[float, float]:
    """M8c: where a line passes a middle stop at a site, place or island on its way: the
    passable cell SITE_IN_M inside the zone its station serves nearest the chord between
    its neighbors (ties: nearest the stop's own point)."""
    zone = G.qpoly(_zone(s).buffer(-SITE_IN_M, join_style="mitre")) \
        if _zone(s) is not None else None
    if zone is None or zone.is_empty:
        return s.p
    shapely.prepare(zone)
    ins = np.nonzero(shapely.contains_xy(zone, c.xs, c.ys) & np.isfinite(cost))[0].tolist()
    if not ins:
        return s.p
    chord = LineString([prev, nxt])
    if chord.length <= 1.0:
        return s.p
    d = shapely.distance(chord, c.pts[ins]).tolist()
    k = min(range(len(ins)), key=lambda i: (round(d[i], 2), round(_d(cell_xy(c, ins[i]), s.p),
                                                                    2), ins[i]))
    p = cell_xy(c, ins[k])
    return (q(p[0]), q(p[1]))


def _straighter(c: Ctx, ln: Line, flaws, notes: list, conflicts: list) -> None:
    """A flying line whose curves came out too tight (it wound between towers): routed
    again with the towers it would clear costing a quarter, so it takes a straighter way
    and clears more of them; kept when that serves as many stops with wider curves."""
    first = (ln.pts, ln.min_radius, ln.stop_at, ln.notes, ln.conflicts, flaws())
    ln.tall_scale = 0.25
    ln.notes, ln.conflicts = list(notes), list(conflicts)
    _route(c, ln)
    if flaws() > first[5] or ln.min_radius <= first[1]:
        ln.pts, ln.min_radius, ln.stop_at, ln.notes, ln.conflicts = first[:5]
        ln.tall_scale = 1.0


def _spurs(c: Ctx, ln: Line, flaws, notes: list, conflicts: list) -> None:
    """M8b: an open road line whose curves are still too tight (a leg that keeps off the
    line's earlier legs loops round the blocks past a stop it cannot turn at, a hub's
    platform say) routed again with its legs free to run back along the line, as before
    M8b (the curves then cut the spur); kept when that serves as many stops, meets itself
    no more and has wider curves."""
    first = (ln.pts, ln.min_radius, ln.stop_at, ln.notes, ln.conflicts, flaws())
    ln.keep_free = True
    ln.notes, ln.conflicts = list(notes), list(conflicts)
    _route(c, ln)
    if flaws() > first[5] or ln.min_radius <= first[1]:
        ln.pts, ln.min_radius, ln.stop_at, ln.notes, ln.conflicts = first[:5]
        ln.keep_free = False


def _restop(c: Ctx, ln: Line, flaws, notes: list, conflicts: list) -> None:
    """A road-following line that still misses a district stop (it turns back there, and its
    curves cut the turn) or keeps a curve tighter than its radius: each stop tries the next
    avenue nodes of its district, nearest first; the route that serves the most stops wins,
    then the one without a tight curve, then the one with the widest."""
    stops = ln.stops
    graph = RoadGraph(c, ln.mode)
    dist = {d.id: d for d in c.m.districts}

    r_min = presets.TRANSIT_MODES[ln.mode].min_curve_radius_m or 0.0

    def snap():
        return (ln.pts, ln.min_radius, ln.stop_at, ln.notes, ln.conflicts,
                [s.p for s in stops])

    def score():
        return (flaws(), 1 if ln.min_radius < 0.95 * r_min else 0,
                -round(min(ln.min_radius, r_min), 1))
    best = (score(), snap())
    budget = [RESTOP_BUDGET]
    for st in list(stops):
        if best[0][:2] == ((0, 0), 0):
            break
        if st.kind != "district" or st.z is not None or st.district_id not in dist:
            continue
        if _served(ln.pts, st) and best[0][1] == 0 and best[0][0][1] == 0:
            continue
        poly = G.from_model_poly(dist[st.district_id].polygon)
        twins = [s for s in stops if s.name == st.name and s.kind == st.kind]
        here = st.p
        cands = sorted((round(_d(graph.pos[n], here), 2), n) for n in sorted(graph.major)
                       if not n.startswith("ov") and poly.contains(Point(graph.pos[n])))
        pts = [graph.pos[nid] for _, nid in cands[:RESTOP_TRIES]]
        # first, for a loop: the district point nearest the chord between its neighbors
        # (where the loop passes through instead of turning back at the stop)
        k = stops.index(st)
        if ln.loop and len(stops) > 3:
            prev = stops[k - 1] if k > 0 else stops[-2]
            nxt = stops[k + 1] if k + 1 < len(stops) - 1 or k == 0 else stops[1]
            chord = LineString([prev.p, nxt.p])
            if chord.length > 1.0:
                pts = [_district_point(c, dist[st.district_id], ln.mode, chord)] + pts
        for p in pts:
            if p == here:
                continue
            if budget[0] <= 0:
                break
            budget[0] -= 1
            for s in twins:
                s.p = p
            ln.notes, ln.conflicts = list(notes), list(conflicts)
            _route(c, ln)
            if score() < best[0]:
                best = (score(), snap())
                if best[0][:2] == ((0, 0), 0):
                    break
        ln.pts, ln.min_radius, ln.stop_at, ln.notes, ln.conflicts = best[1][:5]
        for s, p in zip(stops, best[1][5]):
            s.p = p


STOP_REACH_M = 150.0  # a road-following leg may end at a junction this near its district stop


def _legs(c: Ctx, ln: Line, graph, cost) -> tuple[list, set, list, bool]:
    """The route through the stops before the curves: (points, indices where it reaches a
    stop, the index for each stop, every leg found). Each leg starts where the last one
    ended and keeps off the line's earlier legs (M8b), but near its own ends:

    - a road-following line runs on the road graph to a junction within STOP_REACH_M of a
      district stop in its district (the node nearest a site, platform or exit), a loop's
      last leg back to where its first left, arriving the way that one went on;
    - where the roads cannot keep it off the earlier legs (one bridge both ways, say), the
      leg runs on the raster instead (its own viaduct), and only where that fails too on
      the roads again, over the earlier legs (a loop on the roads takes the roads again at
      once: `_off_roads` routes it on the raster as a whole);
    - the other modes search the raster, off the earlier legs where they can."""
    mode = ln.mode
    stops = ln.stops
    raw: list = []
    at_stop = {0}
    hit = [0]       # the index in raw where the route reaches each stop
    din = None
    ok = True
    used_segs: set = set()
    used_cells = np.zeros(c.nx * c.ny, bool)
    dstart = None   # the first leg's departure (a loop's last leg arrives to go on so)
    first = cur = None   # graph nodes: where the line starts, where the last leg ended
    nleg = len(stops) - 1
    for leg, (a, b) in enumerate(zip(stops, stops[1:])):
        run = None
        closing = ln.loop and leg == nleg - 1
        here = raw[-1] if raw else a.p
        # M8b: a leg keeps off the line's earlier legs (it would cross or run along them),
        # but near where it starts and, closing a loop, near where the loop started
        keep_off = None if ln.keep_free else \
            _keep_off(raw, here, raw[0] if closing and raw else None)
        if graph is not None:
            na = cur if cur is not None else graph.node_near(a, c)
            goal = ({first} if closing and first is not None else graph.targets(b, c))
            if na is not None and goal:
                if na in goal:
                    res = ([graph.pos[na]], set(), na)
                else:
                    dend = dstart if closing else None
                    res = graph.route(na, goal, din, used_segs, graph.touching(keep_off), dend)
                    if res is not None and not ln.loop and _winds(res[0]):
                        # M8b: a leg that winds round the blocks (a stop at a road's end,
                        # the way on blocked by the line itself): the raster's when shorter
                        ras = _raster_leg(c, ln, cost, here, b.p, keep_off, din)
                        if ras is not None and _plen(ras) * WIND_SHORTER < _plen(res[0]):
                            res = None
                if res is not None:
                    run, ks, cur = res
                    used_segs |= ks
                    first = na if first is None else first
        if run is None:
            path = None
            end = raw[0] if closing and raw else b.p
            pa = snap_cell(c, cost, here)
            pb = snap_cell(c, cost, end)
            # (a loop on the roads goes to the raster as a whole instead, `_off_roads`)
            if (keep_off is not None or graph is not None) and not (graph and ln.loop):
                run = _raster_leg(c, ln, cost, here, end, keep_off, din)
                path = run and run[1:-1]
            if run is None and graph is not None:
                # the roads again, over the earlier legs (the curves may still part them)
                na = cur if cur is not None else graph.node_near(a, c)
                goal = ({first} if closing and first is not None else graph.targets(b, c))
                res = graph.route(na, goal, din, used_segs) if na is not None and goal and \
                    na not in goal else None
                if res is not None:
                    run, ks, cur = res
                    used_segs |= ks
                    first = na if first is None else first
            if run is None:
                leg_cost = cost
                if used_cells.any():
                    near_ends = shapely.dwithin(Point(here), c.pts, 2 * REUSE_PAD_M) | \
                        shapely.dwithin(Point(end), c.pts, 2 * REUSE_PAD_M)
                    leg_cost = np.where(used_cells & ~near_ends, cost * REUSE_W, cost)
                path = search(c, leg_cost, pa, pb, TURN_COST_M.get(mode, 0.0), din)
                if path is None:
                    ln.notes.append(f"{ln.name}: no route from {a.name} to {b.name}")
                    ok = False
                    path = [cell_of(c, here), cell_of(c, end)]
                run = [here] + [cell_xy(c, k) for k in path] + [end]
            if graph is not None and path is not None:
                # (a raster leg ends at the stop point: its junction, if it is one)
                cur = graph.at.get((q(end[0]), q(end[1])))
                if first is None:
                    first = graph.at.get((q(here[0]), q(here[1])))
        if len(run) >= 2:
            used_cells |= shapely.dwithin(LineString(run), c.pts, REUSE_PAD_M)
        for p in run:
            if not raw or _d(raw[-1], p) > 0.01:
                raw.append((G.q(p[0]), G.q(p[1])))
        at_stop.add(len(raw) - 1)
        hit.append(len(raw) - 1)
        if len(raw) >= 2:
            din = RoadGraph._dir(raw, rev=True)
            if leg == 0:
                dstart = RoadGraph._dir(raw)
    if ln.loop and raw[0] != raw[-1]:
        raw.append(raw[0])
        at_stop.add(len(raw) - 1)
    return raw, at_stop, hit, ok


def _fit(c: Ctx, ln: Line, raw: list, at_stop: set, hit, cost, graph) -> tuple[list, float]:
    """The track through a route (raw, reaching the stops at `at_stop`): simplified, then
    arcs at the mode's radius (`arc_path`), cut back to its exits; (points every 10 m at
    most, the smallest arc radius). `hit`: the index in raw of each stop (pinned where the
    curves would cut it away), or None."""
    mode = ln.mode
    stops = ln.stops
    r_min = presets.TRANSIT_MODES[mode].min_curve_radius_m or 0.0
    # simplified between stops (a loop would collapse as one run), then arcs at the
    # mode's radius with only the ends fixed: curves may pass beside a stop
    pts, _ = simplify_runs(raw, at_stop, SIMPLIFY_M[mode])
    # a line that leaves the map runs on straight beyond its exit: its last curve may use
    # the room past the edge (cut back to the exit below)
    cut_ends = []
    if not ln.loop and r_min > 0 and len(pts) >= 2:
        for end in (0, -1):
            if stops[end].kind == "exit":
                a_, b_ = (pts[1], pts[0]) if end == 0 else (pts[-2], pts[-1])
                L_ = _d(a_, b_)
                if L_ > 1.0:
                    far = (q(b_[0] + (b_[0] - a_[0]) / L_ * EXIT_RUN_M),
                           q(b_[1] + (b_[1] - a_[1]) / L_ * EXIT_RUN_M))
                    pts = [far] + pts[1:] if end == 0 else pts[:-1] + [far]
                    cut_ends.append((end, b_))
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
        pins = frozenset(raw[i] for s, i in zip(stops, hit or ())
                         if s.kind != "exit" and not _served(fitted, s))
        if pins:
            fitted, rmin = arc_path(pts, r_min, ln.loop, ok_cut, 2.0 * r_min, pins)
        if ln.loop and fitted[0] != fitted[-1]:
            fitted = fitted + [fitted[0]]
        fitted = _cut_to_exits(fitted, cut_ends)
        dense = _densify(fitted)
    else:
        dense, rmin = _densify(pts), INF
    return dense, rmin


def _route(c: Ctx, ln: Line) -> None:
    mode = ln.mode
    stops = ln.stops
    pre = presets.TRANSIT_MODES[mode]
    r_min = pre.min_curve_radius_m or 0.0
    graph = RoadGraph(c, mode) if mode in ROAD_MODES and ln.on_roads else None
    block = None
    dense, rmin, ok = [], INF, True
    for attempt in range(ATTEMPTS):
        cost, portal = costs(c, mode, ln.z0, ln.through, block, ln.alt[1], ln.alt[0],
                             ln.tall_scale)
        if graph is None:
            # a stop in a forbidden area (a flight cone, a tower the line cannot pass) moves
            # to the nearest passable cell; its station goes there
            for st in stops:
                k = cell_of(c, st.p)
                if cost[k] == INF:
                    st.p = cell_xy(c, snap_cell(c, cost, st.p))
                    st.p = (G.q(st.p[0]), G.q(st.p[1]))
        raw, at_stop, hit, legs_ok = _legs(c, ln, graph, cost)
        ok = ok and legs_ok
        dense, rmin = _fit(c, ln, raw, at_stop, hit, cost, graph)
        conflicts = _corridor(c, ln, dense, check_only=True)
        if not conflicts or attempt == ATTEMPTS - 1 or graph is not None:
            break
        # wider each time: the curves fitted to the route cut inside its corners
        block = np.zeros(c.nx * c.ny, bool) if block is None else block
        for b in conflicts:
            block |= shapely.dwithin(b.poly, c.pts, WIDTH_M[mode] / 2.0 + SIDE_PAD_M +
                                     CELL_M * (1 + 2 * attempt))
        ln.notes.append(f"{ln.name}: rerouted around {len(conflicts)} building(s)")
    if not ln.loop and r_min >= FAST_R and graph is None and len(stops) >= 2:
        # M8b: a fast line also along its guide line; kept only when it is better
        alt = _guide_line(c, ln, cost, r_min)
        if alt is not None and _line_key(c, ln, alt[0], alt[1], r_min) < \
                _line_key(c, ln, dense, rmin, r_min):
            dense, rmin = alt
            ln.notes.append(f"{ln.name}: drawn along its stops with {r_min:g} m curves")
    if ln.loop and r_min > 0 and graph is None and len(_ring_of(stops)) >= 3:
        # M8b: a loop off the roads also along its guide ring; the better of the two
        alt = _guide_loop(c, ln, cost, r_min)
        if alt is not None and _loop_key(alt[0], alt[1], stops, mode, r_min) <= \
                _loop_key(dense, rmin, stops, mode, r_min):
            dense, rmin = alt
    # (M8b: only for a curve the check would fail, as for a loop that meets itself)
    if ln.loop and r_min > 0 and len(stops) >= 3 and \
            (rmin < HULL_BELOW * r_min or meets(dense, True, mode)):
        alt = None
        for pad in HULL_PADS:
            alt = _hull_loop(c, ln, cost, r_min, pad)
            if alt is None or alt[1] >= HULL_BELOW * r_min:
                break
        if alt is not None and in_order(alt[0], stops, True):
            m0, m1 = meets(dense, True, mode), meets(alt[0], True, mode)
            if m1 < m0 or (m1 == m0 and alt[1] > rmin):
                dense, rmin = alt
                why = "it met itself" if m0 > m1 else \
                    f"their order makes turns tighter than {r_min:g} m"
                ln.notes.append(f"{ln.name}: loop drawn around its stops ({why})")
    if ln.loop and len(dense) > 2 and dense[0] == dense[-1]:
        # M8b: a loop's track starts at its first stop, its stations follow in route order
        dense = _start_at(dense, stop_index(dense, stops[0]))
    ln.pts = dense
    ln.min_radius = rmin
    ln.stop_at = ordered_stops(dense, stops, ln.loop)
    for s, i in zip(stops, ln.stop_at):
        zone = _zone(s)
        if zone is not None and not zone.covers(Point(dense[i])):
            ln.notes.append(f"{ln.name}: the track passes {zone.distance(Point(dense[i])):.0f} m "
                            f"from {s.name} (its {r_min:g} m curves cut the turn there; a "
                            f"route that runs through its stops keeps them)")
    if not ok:
        ln.conflicts.append("route")


KEEP_END_M = 60.0   # a leg may meet the line's earlier legs this near its own ends
WIND_M = (1.5, 300.0)   # a road leg longer than 1.5 times its chord plus 300 m winds
WIND_SHORTER = 1.3      # ... and runs on the raster where that is this much shorter


def _winds(run: list) -> bool:
    return _plen(run) > WIND_M[0] * _d(run[0], run[-1]) + WIND_M[1]


def _raster_leg(c: Ctx, ln: Line, cost, a, b, keep_off, din) -> list | None:
    """A leg from a to b on the raster, off keep_off (the line so far)."""
    leg_cost = cost
    if keep_off is not None:
        leg_cost = np.where(shapely.dwithin(keep_off, c.pts, WIDTH_M[ln.mode] + CELL_M), INF,
                            cost)
    path = search(c, leg_cost, snap_cell(c, cost, a), snap_cell(c, cost, b),
                  TURN_COST_M.get(ln.mode, 0.0), din)
    return None if path is None else [a] + [cell_xy(c, k) for k in path] + [b]
HULL_BELOW = 0.98   # a loop with a curve this much tighter than its radius tries its hull
HULL_PADS = (1.1, 1.25)  # its hull widened by this times the radius (more, if still tight)


def _keep_off(raw: list, a, b=None):
    """What a new leg of a line keeps off: the line so far, but within KEEP_END_M of the stop
    it leaves (and of b, the first stop, for the leg that closes a loop). None when there is
    nothing."""
    if len(raw) < 2:
        return None
    ends = [p for p in (a, b) if p is not None]
    parts, run = [], []
    for p in _densify(raw):
        if all(_d(p, e) > KEEP_END_M for e in ends):
            run.append(p)
            continue
        if len(run) >= 2:
            parts.append(run)
        run = []
    if len(run) >= 2:
        parts.append(run)
    return shapely.MultiLineString(parts) if parts else None


def _cut_to_exits(pts: list, cut_ends: list) -> list:
    """The fitted line cut back to its exits (where it was run on past the map edge)."""
    for end, e in sorted(cut_ends, key=lambda t: -t[0]):   # the far end first
        line = LineString(pts)
        s_e = line.project(Point(e))
        L = line.length
        if end == -1 and s_e < L:
            keep = shapely.ops.substring(line, 0.0, s_e)
        elif end == 0 and s_e > 0:
            keep = shapely.ops.substring(line, s_e, L)
        else:
            continue
        pts = [(q(x), q(y)) for x, y in keep.coords]
    return pts


GUIDE_STEP_M = 120.0   # waypoints along a loop's guide ring


def _loop_key(pts, rmin: float, stops, mode: str, r_min: float) -> tuple:
    """How good a loop is, lower better: its stops served in route order, where it meets
    itself, a curve too tight."""
    return (0 if in_order(pts, stops, True) else 1, meets(pts, True, mode),
            1 if rmin < HULL_BELOW * r_min else 0)


FAST_R = 300.0   # modes with curves at least this wide (maglev, sky tube) are fast lines


def _line_key(c: Ctx, ln: Line, pts, rmin: float, r_min: float) -> tuple:
    """How good an open line is, lower better: its stops served in route order, where it
    meets itself, a curve too tight, a building in its corridor it cannot pass."""
    return (0 if in_order(pts, ln.stops, False) else 1, meets(pts, False, ln.mode),
            1 if rmin < HULL_BELOW * r_min else 0,
            1 if _corridor(c, ln, pts, check_only=True) else 0)


def _guide_line(c: Ctx, ln: Line, cost, r_min: float):
    """M8b: a fast line along its guide line, the polyline of its stops with curves of
    1.15 r_min (`_fast_point` puts a middle stop where the curve at its corner stays in its
    district), as waypoints every GUIDE_STEP_M routed on the raster around what the line
    cannot pass, then fitted like any route. Legs from stop to stop may reach a stop off
    the line's way as a spur the curves cannot follow."""
    stops = ln.stops
    pts = [ln.corners.get(k, s.p) for k, s in enumerate(stops)]
    if len(pts) > 2:
        guide, _ = arc_path(pts, r_min, False, lambda run: True, 2.0 * r_min)
    else:
        guide = pts
    if len(guide) < 2 or _plen(guide) < 1.0:
        return None
    # the guide at each stop: its point in the stop's zone nearest the stop, in order
    dense = _densify(guide)
    arr = shapely.points(np.array(dense, dtype=np.float64))
    at = [0]
    for s in stops[1:-1]:
        zone = _zone(s)
        idx = list(range(at[-1], len(dense)))
        if zone is not None:
            ins = [at[-1] + i for i in np.nonzero(shapely.covers(zone, arr[at[-1]:]))[0].tolist()]
            idx = ins or idx
        at.append(min(idx, key=lambda i: (round(_d(dense[i], s.p), 3), i)))
    at.append(len(dense) - 1)
    raw: list = []
    hit = []
    din = None
    turn = TURN_COST_M.get(ln.mode, 0.0)
    for i0, i1 in zip(at, at[1:]):
        part = dense[i0:i1 + 1]
        way = resample(part, GUIDE_STEP_M) if len(part) > 1 and _plen(part) > 1.0 else part
        if not raw:
            raw.append((G.q(way[0][0]), G.q(way[0][1])))
            hit.append(0)
        for a, b in zip(way, way[1:]):
            path = search(c, cost, snap_cell(c, cost, a), snap_cell(c, cost, b), turn, din)
            run = [cell_xy(c, k) for k in path][1:-1] if path else []
            for p in run + [b]:
                p = (G.q(p[0]), G.q(p[1]))
                if _d(raw[-1], p) > 0.01:
                    raw.append(p)
            if len(raw) >= 2:
                din = RoadGraph._dir(raw, rev=True)
        hit.append(len(raw) - 1)
    if len(raw) < 2:
        return None
    return _fit(c, ln, raw, set(hit), hit, cost, None)


CORNER_STEP_M = 60.0   # the grid a fast line's corner beside a stop is searched on
CORNER_IN_M = 40.0     # its guide runs a station's length this far inside the district


def _fast_point(c: Ctx, d, mode: str, prev, nxt, cost) -> tuple[tuple, tuple | None]:
    """M8b: a fast line's stop between two others, and the corner of its guide line there
    when that is not the stop itself:

    - the junction nearest the chord between them (avenues first, as `_district_point`)
      where a curve of 1.15 times the mode's radius at the corner stays in the district
      (`_apex_in`) and clear of what the line cannot pass;
    - else a corner on a CORNER_STEP_M grid within twice that radius of the district, the
      nearest the way (the shortest run through it) whose guide (straight runs and the
      curve) is clear and runs a station's length CORNER_IN_M inside the district; the
      stop goes to the middle of that stretch (the line turns beside the district, over
      the water say, instead of in it);
    - else `_district_point`'s junction."""
    r = 1.15 * (presets.TRANSIT_MODES[mode].min_curve_radius_m or 0.0)
    zone = G.from_model_poly(d.polygon)
    shapely.prepare(zone)
    chord = LineString([prev, nxt])

    def free(run):
        return all(_segment_free(c, cost, a, b) for a, b in zip(run, run[1:]))
    cands = sorted(((round(chord.distance(Point(p)) + 150.0 * rank, 2), p)
                    for p, rank in _district_cands(c, d, mode, inset=False)))
    for _, p in cands:
        if _apex_in(prev, p, nxt, r, zone) and free(_corner_arc(prev, p, nxt, r)):
            return p, None
    # (the route and its curves drift from the guide by a few cells: deep enough in)
    deep = G.qpoly(zone.buffer(-CORNER_IN_M))
    if deep.is_empty:
        return _district_point(c, d, mode, chord), None
    shapely.prepare(deep)
    x0, y0, x1, y1 = G.qbounds(zone)
    i0, i1 = int(math.floor((x0 - 2 * r) / CORNER_STEP_M)), int(math.ceil((x1 + 2 * r) /
                                                                         CORNER_STEP_M))
    j0, j1 = int(math.floor((y0 - 2 * r) / CORNER_STEP_M)), int(math.ceil((y1 + 2 * r) /
                                                                         CORNER_STEP_M))
    need = STATION_LEN_M[mode]
    grid = []
    for j in range(j0, j1 + 1):
        for i in range(i0, i1 + 1):
            qp = (q(i * CORNER_STEP_M), q(j * CORNER_STEP_M))
            grid.append((round(_d(prev, qp) + _d(qp, nxt), 2), qp))
    best = None
    for _, qp in sorted(grid):
        if cost[cell_of(c, qp)] == INF:
            continue
        guide = _corner_arc(prev, qp, nxt, r)
        dense = _densify(guide)
        inside = shapely.covers(deep, shapely.points(np.array(dense, dtype=np.float64)))
        run, longest = [], []
        for k, f in enumerate(inside.tolist()):
            run = run + [k] if f else []
            if len(run) > len(longest):
                longest = run
        if len(longest) < 2 or _plen(dense[longest[0]:longest[-1] + 1]) < need:
            continue
        if not free(guide):
            continue
        best = (None, qp, dense[longest[len(longest) // 2]])
        break
    if best is not None:
        return best[2], best[1]
    return _district_point(c, d, mode, chord), None


def _guide_loop(c: Ctx, ln: Line, cost, r_min: float):
    """M8b: a loop along its guide ring, the polygon of its stops in route order with curves
    of 1.15 r_min (`_loop_points` places the stops so that these pass in their districts),
    as waypoints every GUIDE_STEP_M routed on the raster around what the line cannot pass,
    then arcs. Legs from stop to stop would reach a stop off the ring as a spur that the
    curves cut away."""
    ring = [s.p for s in _ring_of(ln.stops)]
    guide, _ = arc_path(ring + [ring[0]], r_min, True, lambda run: True, 2.0 * r_min)
    if len(guide) < 4:
        return None
    way = resample(guide, GUIDE_STEP_M, True)
    k0 = min(range(len(way)), key=lambda i: (round(_d(way[i], ring[0]), 3), i))
    way = way[k0:] + way[:k0]
    raw: list = []
    din = None
    turn = TURN_COST_M.get(ln.mode, 0.0)
    for a, b in zip(way, way[1:] + way[:1]):
        path = search(c, cost, snap_cell(c, cost, a), snap_cell(c, cost, b), turn, din)
        run = [cell_xy(c, k) for k in path] if path else [a, b]
        for p in run:
            if not raw or _d(raw[-1], p) > 0.01:
                raw.append((G.q(p[0]), G.q(p[1])))
        if len(raw) >= 2:
            din = RoadGraph._dir(raw, rev=True)
    if len(raw) < 3:
        return None
    pts, _ = simplify_runs(raw + [raw[0]], {0}, SIMPLIFY_M[ln.mode])

    def ok_cut(run):
        return all(_segment_free(c, cost, p, r) for p, r in zip(run, run[1:]))
    fitted, rmin = arc_path(pts, r_min, True, ok_cut, 2.0 * r_min)
    if fitted[0] != fitted[-1]:
        fitted = fitted + [fitted[0]]
    return _densify(fitted), rmin


def _hull_loop(c: Ctx, ln: Line, cost, r_min: float, pad: float = 1.1):
    """A loop around its stops: the outline of their convex hull widened by pad r_min
    (every curve of it at least that wide), as waypoints every 120 m routed on the raster
    around what the line cannot pass, then arcs."""
    hull = shapely.convex_hull(shapely.multipoints([s.p for s in ln.stops]))
    ring = G.qpoly(hull.buffer(pad * r_min, quad_segs=16))
    if ring.is_empty:
        return None
    # M8b: around the way the route goes round
    ps = [s.p for s in _ring_of(ln.stops)]
    turn = math.fsum(a[0] * b[1] - b[0] * a[1] for a, b in zip(ps, ps[1:] + ps[:1]))
    ring = shapely.geometry.polygon.orient(G.parts(ring)[0], 1.0 if turn >= 0 else -1.0)
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
SITE_IN_M = 30.0  # a line ends at a site this far inside the zone its station serves


def _site_end(s: Stop) -> bool:
    """A stop at a site (a spaceport, a terminal) without a platform or tower of its own."""
    return s.kind == "megasite" and s.z is None and s.tower_id is None and s.area is not None


def _site_zone(s: Stop):
    return G.qpoly(s.area.buffer(SERVE_M - SITE_IN_M))


def _site_point(c: Ctx, s: Stop, toward, cost) -> tuple[float, float]:
    """M8b: where a line that begins or ends at a site meets it: the passable cell of the
    zone its station serves (SITE_IN_M inside) nearest the neighboring stop, not the site's
    middle (inside its terminal, say, which the line would wind round)."""
    zone = _site_zone(s)
    if zone.is_empty:
        return s.p
    shapely.prepare(zone)
    ins = np.nonzero(shapely.contains_xy(zone, c.xs, c.ys) & np.isfinite(cost))[0].tolist()
    if not ins:
        return s.p
    k = min(ins, key=lambda k: (round(_d(cell_xy(c, k), toward), 2), k))
    p = cell_xy(c, k)
    return (q(p[0]), q(p[1]))


def _zone(s: Stop):
    """Where a station serves the stop: in its district, within SERVE_M of anything else."""
    if s.area is None or s.area.is_empty:
        return None
    return G.qpoly(s.area.buffer(SERVE_M) if s.kind != "district" else s.area)


EXIT_REACH_M = 250.0   # a line to an exit ends this near it (the check allows 300 m)


def _served(pts, s: Stop) -> bool:
    if s.kind == "exit":
        # M8c: a line to an exit ends there (its last curve run past the map edge and cut
        # back may end elsewhere)
        return len(pts) > 0 and min(_d(pts[0], s.p), _d(pts[-1], s.p)) <= EXIT_REACH_M
    zone = _zone(s)
    if zone is None:
        return True
    return bool(shapely.covers(zone, shapely.points(np.array(pts, dtype=np.float64))).any())


SELF_GAP_M = 100.0   # parts of one line this far apart along it must not meet


def self_clear_m(mode: str) -> float:
    """Height between two parts of one line where one passes over the other: 5.5 m under the
    upper structure, over the lower one."""
    return ROAD_CLEAR_M + below(mode) + above(mode)


def self_meets(pts, loop: bool, reach: float, zs=None, clear: float = 0.0) -> list[tuple]:
    """Where a line meets itself: (s, x, y) for every place where two parts of its track more
    than SELF_GAP_M apart along it come within `reach` in plan (with zs, less than `clear`
    apart in height there), one per place (within 50 m of one already found is the same
    place)."""
    pts = [tuple(p[:2]) for p in pts]
    n = len(pts) - 1
    if n < 2:
        return []
    cum = _cum(pts)
    L = cum[-1]
    segs = [LineString([pts[i], pts[i + 1]]) for i in range(n)]
    tree = shapely.STRtree(segs)
    ia, ib = tree.query(segs, predicate="dwithin", distance=reach)
    hits = []
    for i, j in sorted(zip(ia.tolist(), ib.tolist())):
        if j <= i:
            continue
        gap = cum[j] - cum[i + 1]
        if loop:
            gap = min(gap, L - cum[j + 1] + cum[i])
        if gap <= SELF_GAP_M:
            continue
        a, b = shapely.ops.nearest_points(segs[i], segs[j])
        if zs is not None:
            za = _z_on(pts, zs, i, (a.x, a.y))
            zb = _z_on(pts, zs, j, (b.x, b.y))
            if abs(za - zb) >= clear - 0.01:
                continue
        if any(_d((a.x, a.y), (h[1], h[2])) <= 50.0 for h in hits):
            continue
        s = cum[i] + _d(pts[i], (a.x, a.y))
        hits.append((round(s, 1), round(a.x, 1), round(a.y, 1)))
    return hits


def _z_on(pts, zs, i: int, p) -> float:
    L = _d(pts[i], pts[i + 1])
    f = 0.0 if L <= 0 else min(max(_d(pts[i], p) / L, 0.0), 1.0)
    return zs[i] + (zs[i + 1] - zs[i]) * f


def meets(pts, loop: bool, mode: str) -> int:
    """How many places the track (in plan) meets itself: within the structure's width."""
    return len(self_meets(pts, loop, WIDTH_M[mode]))


def in_order(pts, stops, loop: bool) -> bool:
    """Every stop served by its station in route order (`ordered_stops`); a loop's track is
    tried from its first stop."""
    if loop and len(pts) > 2 and pts[0] == pts[-1]:
        pts = _start_at(pts, stop_index(pts, stops[0]))
    at = ordered_stops(pts, stops, loop)
    return all(_zone(s) is None or _zone(s).covers(Point(pts[i])) for s, i in zip(stops, at))


def ordered_stops(pts, stops, loop: bool) -> list[int]:
    """The track vertex of each stop's station, in route order: each the vertex nearest the
    stop point among those after the previous stop's that serve it (in its district, or
    within SERVE_M of its site or place), else the nearest after it; a loop's last stop (the
    first again) is its last vertex. The track of a loop starts at its first stop."""
    out = []
    prev = 0
    arr = shapely.points(np.array(pts, dtype=np.float64))
    for k, s in enumerate(stops):
        if k == 0:
            out.append(0 if loop else _first_stop(pts, s, arr))
            prev = out[-1]
            continue
        if loop and k == len(stops) - 1 and s.name == stops[0].name:
            out.append(len(pts) - 1)
            continue
        zone = _zone(s)
        idx = list(range(prev, len(pts)))
        if zone is not None:
            ins = np.nonzero(shapely.covers(zone, arr[prev:]))[0].tolist()
            if ins:
                idx = [prev + i for i in ins]
        i = min(idx, key=lambda i: (round(_d(pts[i], s.p), 3), i))
        out.append(i)
        prev = i
    return out


def _first_stop(pts, s: Stop, arr) -> int:
    """A line's first station: the vertex nearest the stop point where the track first
    serves it (it may come back through the district later)."""
    zone = _zone(s)
    if zone is None:
        return _nearest_index(pts, s.p)
    ins = np.nonzero(shapely.covers(zone, arr))[0].tolist()
    if not ins:
        return _nearest_index(pts, s.p)
    run = [ins[0]]
    for i in ins[1:]:
        if i != run[-1] + 1:
            break
        run.append(i)
    return min(run, key=lambda i: (round(_d(pts[i], s.p), 3), i))


def _start_at(pts: list, i: int) -> list:
    """A closed track (first point = last) started again at vertex i."""
    if i <= 0 or i >= len(pts) - 1:
        return pts
    return pts[i:] + pts[1:i + 1]


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
        elif b.top + SKY_CLEAR_M > ln.alt[1] and b.top >= z1 + r + PORTAL_TIGHT_M - 0.01 \
                and b.bottom <= z0 - r - 1.0:
            # M8b: a tower the line could not climb within its altitude range keeps its
            # portal with less headroom (climbing over it would lift the line out of its
            # range and its neighbors out of their portals, one after another)
            ln.portals[bid] = (q(z0 - r - 1.0), q(z1 + r + 1.0))
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
    g = (presets.TRANSIT_MODES[mode].max_grade or 0.05) * 0.95
    closed = ln.loop and n > 2 and ln.pts[0] == ln.pts[-1]
    low = _envelope(ln.pts, need, g, closed)  # what the water already needs, at the grade
    runs = deck_crossings(c.decks, c.dtree, arr, WIDTH_M[mode] / 2.0)
    need0 = list(need)
    over_runs: set = set()
    for _attempt in range(4):
        need = list(need0)
        zs = _profile_pass(c, ln, gone, arr, need, runs, over_runs, low)
        # a deck the track was to pass under but other needs lift it into: over it instead
        late = set()
        for k, run in enumerate(runs):
            if k in over_runs:
                continue
            if any(zs[i] > road_underside(z) - above(mode) - UNDER_PAD_M + 0.01
                   for i, z in run) and _under_choice(mode, run, ln.z0, low):
                late.add(k)
        if not late:
            break
        over_runs |= late
    ln.zs = zs


def _under_choice(mode: str, run, z0: float, low) -> bool:
    ucap = min(road_underside(z) - above(mode) - UNDER_PAD_M for _, z in run)
    return passes_under(mode, [z for _, z in run], z0) and all(low[i] <= ucap for i, _ in run)


def _profile_pass(c: Ctx, ln: Line, gone: set, arr, need: list, runs, over_runs: set,
                  low) -> list[float]:
    mode = ln.mode
    n = len(ln.pts)
    deck = below(mode)
    unders = []
    for k, run in enumerate(runs):
        if k not in over_runs and _under_choice(mode, run, ln.z0, low):
            # M7: a high road deck (an approach viaduct) the track passes under
            unders += [(i, road_underside(z) - above(mode) - UNDER_PAD_M) for i, z in run]
        else:
            for i, z in run:
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
    # upper bounds: the towers a sky tube passes through (8 m of headroom under the roof),
    # high road decks passed under
    cap = [INF] * n
    for i, z in unders:
        cap[i] = min(cap[i], z)
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
    closed = ln.loop and n > 2 and ln.pts[0] == ln.pts[-1]
    lo = _graded(ln.pts, need, g, max, -1.0, closed)
    hi = _graded(ln.pts, cap, g, min, 1.0, closed)
    return [q(max(a, min(b, ln.z0))) for a, b in zip(lo, hi)]


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
                    None)
        if name is None:
            # M8b: off every district (a bank between two river arms): the nearest one
            near = min(((round(G.from_model_poly(d.polygon).distance(pt), 2), d.name)
                        for d in m.districts), default=None)
            name = near[1] if near is not None and near[0] <= 300.0 else ln.name
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
        vertex inside it (M8c: one where the station still serves its stop)."""
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
            cands = [x[1] for x in sorted(cands)]
        zone = _zone(stop) if stop is not None else None
        for bid in cands:
            b = bld[bid]
            inside = [i for i, p in enumerate(ln.pts) if b.poly.contains(Point(p)) and
                      (zone is None or zone.covers(Point(p)))]
            if inside:
                return b, inside[len(inside) // 2]
        return None, idx

    def _metro(self, sid, seg, foot, acc) -> None:
        z = METRO_CONCOURSE_Z
        k = self.walk("path", [(x, y, z) for x, y in seg], 6.0, {"station": sid,
                                                                  "concourse": True})
        acc.append(k)
        self.struct(f"{sid}.cc", "deck", -14.0, -4.0, footprint=foot,
                    attrs={"station": sid, "role": "concourse", "underground": True})
        line = LineString(seg)
        for e, tag in ((seg[0], "a"), (seg[-1], "b")):
            f, d = self.foot(e)
            if d < 0.5:  # stairs need a run: step the kiosk 12 m along the concourse (M8c)
                r = line.interpolate(min(METRO_RUN_M, line.length / 2.0) if tag == "a" else
                                     max(line.length - METRO_RUN_M, line.length / 2.0))
                e = (q(r.x), q(r.y))
                if _d(e, f) < 0.5:
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
        # the building stands on the landmass the station's stairs reach (a platform over
        # the water between two would leave the skywalk's end apart from its own streets)
        lm_e = _landmass_index(self.lms, [e])[0]
        k = _nearest_on(self.gtree, self.glines, self.walks, self.gi, self.land_of, Point(e),
                        lm_e)
        if _landmass_index(self.lms, [tgt])[0] != self.land_of[k]:
            return
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
        # M9: no footing on a road tunnel's box or open approach
        if not hasattr(c, "_tunnels"):
            boxes = [LineString([p_[:2] for p_ in t.line]).buffer(t.width_m / 2.0 + 1.0,
                                                                 cap_style="flat")
                     for t in c.m.tunnels if t.kind in ("immersed_tube", "cut_and_cover")]
            c._tunnels = (shapely.STRtree(boxes), boxes) if boxes else None
        if c._tunnels is not None and len(c._tunnels[0].query(sq, predicate="intersects")):
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


def build(spec, m, fixed: dict | None = None) -> Out:
    """`fixed` (M10, a district regeneration): line name -> the old line's row; such a line
    keeps its track and heights, and the buildings now in its way go."""
    with G.canonical():
        return _build(spec, m, fixed or {})


def _build(spec, m, fixed: dict) -> Out:
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
        fx = fixed.get(tl.name)
        if fx is not None and len(fx["attrs"].get("stop_vertices", [])) == len(ln.stops):
            ln.pts = [(p[0], p[1]) for p in fx["path"]]
            ln.zs = [p[2] for p in fx["path"]]
            ln.stop_at = list(fx["attrs"]["stop_vertices"])
            r = fx["attrs"].get("min_radius_m")
            ln.min_radius = INF if r is None else r
            ln.held = True
        else:
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
        if ln.held:
            # M10: the old track and heights; a portal that no longer fits goes, and what is
            # now in the way (a building of the regenerated district) is taken out
            for _ in range(len(ln.portals)):
                if not _fit_portals(c, ln):
                    break
            out = [x for x in ln.conflicts if x != "route"] + clearance_conflicts(c, ln, gone)
            ln.removed += out
            gone |= set(out)
            ln.conflicts = [x for x in ln.conflicts if x == "route"]
            notes += ln.notes
            continue
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
    k = wk_max(walks)
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
