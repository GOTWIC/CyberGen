"""Checks and stats for buildings, complexes, skybridges, landmarks and megasites (M3; scope
section 9).

Like `checks.py`, every check reads only the city model and the filled spec.
"""

from __future__ import annotations

import math

import numpy as np
import shapely
from shapely.geometry import LineString, Point, Polygon

from . import dmath as M
from . import geom as G
from . import massing as MS
from .model import CityModel
from .spec import CitySpec

AREA_TOL_M2 = 0.5          # a footprint may stick out of its lot or into a clear zone this much
OVERLAP_TOL_M2 = 1.0       # two masses of different owners may overlap this much (grid seams)
UNIT_W_M = (4.0, 12.0)
ROAD_CLEAR_M = 5.5
DECK_M = 1.0
SKY_LEN_M = (8.0, 80.0)
PERP_TOL_DEG = 15.0
ENTRANCE_REACH_M = 20.0
SITE_ROAD_M = 40.0
WATER_CLEAR = {"sea": 25.0, "river": 15.0, "canal": 4.0}
WHEEL_CLEAR_M = 6.5
CONE_SLOPE = 1.0          # clearance surface around a flight cone (see buildings.height_cap)
ANCILLARY = ("parking_structure",)
SPAN_ROLES = ("span",)
REQUIRED = {
    "spaceport": ("launch_pad", "launch_tower", "hangar", "terminal", "control_tower",
                  "fuel_tank", "container_stack"),
    "transit_nexus": ("station", "platform", "bus_bay"),
    "freight_terminal": ("berth", "gantry_crane", "container_stack", "rail_track",
                         "truck_gate"),
    "stadium": ("stadium", "pitch"),
    "central_park": ("lawn", "plaza"),
    "grand_plaza": ("plaza", "monument"),
    "arcology": ("arcology",),
    "temple_complex": ("wall", "gate", "temple_hall", "pagoda"),
    "attraction": ("ferris_wheel",),
    "skyport": ("skyport",),
}


def _check(id_: str, title: str):
    from .checks import Check as C

    return C(id_, title)


def _limit(c, failures: list, msg: str, cap: int = 40) -> None:
    if len(c.failures) < cap:
        c.failures.append(msg)
    elif len(c.failures) == cap:
        c.failures.append("... (more)")


class _B:
    """Shapely views of the M3 parts of a model, built once (polygons converted in bulk)."""

    def __init__(self, m: CityModel):
        F = G.from_model_polys
        self.m = m
        self.lot = dict(zip([lt.id for lt in m.lots], F([lt.polygon for lt in m.lots])))
        self.lot_front = {lt.id: set(lt.frontage_ids) for lt in m.lots}
        self.prop = {p.id: p for p in m.properties}
        self.bld = {b.id: b for b in m.buildings}
        self.site = {s.id: s for s in m.megasites}
        self.site_poly = dict(zip([s.id for s in m.megasites],
                                  F([s.polygon for s in m.megasites])))
        self.open = dict(zip([o.id for o in m.open_spaces],
                             F([o.polygon for o in m.open_spaces])))
        self.district = {d.id: d for d in m.districts}
        owners, refs = [], []
        for b in m.buildings:
            for k, mass in enumerate(b.masses):
                owners.append((b.id, "building", mass.z0_m, mass.z1_m, mass.role, mass.shape,
                               k))
                refs.append(mass.footprint)
        for e in m.site_elements:
            for k, mass in enumerate(e.masses):
                owners.append((e.id, "element", mass.z0_m, mass.z1_m, mass.role, mass.shape, k))
                refs.append(mass.footprint)
        polys = F(refs)
        self.masses = []   # (owner id, kind, z0, z1, polygon, role)
        self.rings = {}    # index in masses -> wheel info
        self.mass_of: dict = {}   # (owner id, mass index) -> polygon
        for (oid, kind, z0, z1, role, shape, k), poly in zip(owners, polys):
            if shape == "ring":
                self.rings[len(self.masses)] = MS.ring_info(poly, z0, z1)
            self.masses.append((oid, kind, z0, z1, poly, role))
            self.mass_of[(oid, k)] = poly
        self.foot = dict(zip([b.id for b in m.buildings],
                             F([b.footprint for b in m.buildings])))
        self.cones = [(G.from_model_poly(s.flight_cone), float(s.height_limit_m), s.id)
                      for s in m.megasites if s.flight_cone is not None and s.height_limit_m]
        self.roads = {s.id: s for s in m.road_segments}

    def allowed(self, b) -> object:
        """Ground the building may stand on: its property's lots, its reserve, or a landmark's
        host open spaces."""
        if b.megasite_id:
            return self.site_poly.get(b.megasite_id)
        polys = []
        p = self.prop.get(b.property_id)
        ids = list(p.lot_ids) if p is not None and p.lot_ids else ([b.lot_id] if b.lot_id
                                                                    else [])
        polys += [self.lot[i] for i in ids if i in self.lot]
        for host in [b.attrs.get("open_space_id")] + list(b.attrs.get("open_space_ids", [])):
            if host in self.open:
                polys.append(self.open[host])
        if not polys:
            return None
        return polys[0] if len(polys) == 1 else G.union(polys)

    def cap(self, p) -> float:
        cap = math.inf
        for poly, lim, _ in self.cones:
            cap = min(cap, lim + G.dist(poly, p) * CONE_SLOPE)
        return cap


def _interior_pairs(a_arr, b_arr, ia, ib):
    """Mask of the pairs (ia[k], ib[k]) whose interiors meet (an exact predicate)."""
    if not len(ia):
        return np.zeros(0, dtype=bool)
    return shapely.relate_pattern(a_arr[ia], b_arr[ib], "T********")


def _outside(poly, allowed) -> float:
    if allowed is None:
        return G.area1(poly)
    if allowed.covers(poly):
        return 0.0
    return G.area1(G.diff(poly, allowed))


def check_footprints(m: CityModel, bx: _B):
    c = _check("building_footprints", "Buildings stand inside their lots (property lots, "
                                      "megasite reserve, or a landmark's host open space); only "
                                      "straddle spans leave them, over a street, clear of "
                                      "junctions and 5.5 m above it")
    junctions = G.from_model_polys([j.polygon for j in m.junctions])
    jtree = shapely.STRtree(junctions) if junctions else None
    lot_ids = list(bx.lot)
    loose_lots = dict(zip(lot_ids, G.snap_many(shapely.buffer(
        np.array([bx.lot[i] for i in lot_ids], dtype=object), 0.05, join_style="mitre")))) \
        if lot_ids else {}
    for b in m.buildings:
        allowed = bx.allowed(b)
        p = bx.prop.get(b.property_id)
        single = (not b.megasite_id and p is not None and len(p.lot_ids) == 1 and
                  not b.attrs.get("open_space_id") and not b.attrs.get("open_space_ids"))
        if single:
            loose = loose_lots.get(p.lot_ids[0])
        else:
            loose = G.qpoly(allowed.buffer(0.05, join_style="mitre")) \
                if allowed is not None else None
        if loose is not None:
            shapely.prepare(loose)
        for k, mass in enumerate(b.masses):
            poly = bx.mass_of[(b.id, k)]
            if mass.role in SPAN_ROLES:
                sid = b.attrs.get("span_over")
                road = bx.roads.get(sid)
                if road is None or road.road_class not in ("street", "alley", "pedestrian",
                                                           "service"):
                    _limit(c, c.failures, f"{b.id}: span over '{sid}' (not a street)")
                    continue
                zmax = max((z.z for z in road.z_profile), default=0.0)
                if mass.z0_m - DECK_M - zmax < ROAD_CLEAR_M - 1e-6:
                    _limit(c, c.failures, f"{b.id}: span {mass.z0_m - DECK_M - zmax:.1f} m "
                                          f"over its street (needs {ROAD_CLEAR_M} m)")
                if jtree is not None:
                    for j in sorted(int(i) for i in jtree.query(poly, predicate="intersects")):
                        if G.area1(G.inter(poly, junctions[j])) > AREA_TOL_M2:
                            _limit(c, c.failures, f"{b.id}: span over junction "
                                                  f"{m.junctions[j].id}")
                continue
            if mass.shape == "ring":
                poly = MS.ring_ground(MS.ring_info(poly, mass.z0_m, mass.z1_m), poly,
                                      WHEEL_CLEAR_M)
                if poly.is_empty:
                    continue
            if loose is not None and loose.covers(poly):
                continue
            out = _outside(poly, allowed)
            if out > AREA_TOL_M2 + 0.002 * G.area1(poly):
                _limit(c, c.failures, f"{b.id}: {mass.role} mass {out:.1f} m2 outside its "
                                      f"{'reserve' if b.megasite_id else 'lots'}")
    for e in m.site_elements:
        allowed = bx.site_poly.get(e.megasite_id) if e.megasite_id else bx.lot.get(e.lot_id)
        for k, mass in enumerate(e.masses):
            out = _outside(bx.mass_of[(e.id, k)], allowed)
            if out > AREA_TOL_M2:
                _limit(c, c.failures, f"{e.id}: {e.kind} {out:.1f} m2 outside its "
                                      f"{'reserve' if e.megasite_id else 'lot'}")
    return c


def check_clear_zones(m: CityModel, bx: _B):
    c = _check("building_clear_zones", "No ground mass of a building or site element on a "
                                       "road, junction, sidewalk, crosswalk, water, open space "
                                       "or another megasite's reserve or flight cone")
    P = G.from_model_poly
    zones, labels = [], []

    def strips(lines, half):
        arr = shapely.buffer(np.array([LineString(x) for x in lines], dtype=object),
                             np.asarray(half, dtype=np.float64), cap_style="flat",
                             join_style="mitre")
        return list(G.snap_many(arr)) if len(lines) else []

    zones += strips([s.centerline for s in m.road_segments],
                    [max(s.width_m / 2.0 - 0.05, 0.5) for s in m.road_segments])
    labels += [("road", s.id) for s in m.road_segments]
    zones += G.from_model_polys([j.polygon for j in m.junctions])
    labels += [("junction", j.id) for j in m.junctions]
    zones += strips([sw.line for sw in m.sidewalks],
                    [max(sw.width_m / 2.0 - 0.05, 0.3) for sw in m.sidewalks])
    labels += [("sidewalk", sw.id) for sw in m.sidewalks]
    zones += strips([cw.line for cw in m.crosswalks], [cw.width_m / 2.0 for cw in m.crosswalks])
    labels += [("crosswalk", cw.id) for cw in m.crosswalks]
    for r in m.rivers:
        zones.append(P(r.polygon))
        labels.append(("water", r.id))
    for ch in m.channels:
        zones.append(P(ch.polygon))
        labels.append(("water", ch.id))
    for w in m.waterways:
        zones.append(P(w.polygon))
        labels.append(("water", w.id))
    for s in m.seas:
        for p in s.polygons:
            zones.append(P(p))
            labels.append(("water", s.id))
    for o in m.open_spaces:
        if o.district_id:
            zones.append(P(o.polygon))
            labels.append(("open", o.id))
    for s in m.megasites:
        zones.append(P(s.polygon))
        labels.append(("reserve", s.id))
        if s.flight_cone is not None:
            zones.append(P(s.flight_cone))
            labels.append(("cone", s.id))
    zones = [z for z in zones]
    tree = shapely.STRtree(zones)
    owners = {b.id: b for b in m.buildings}
    elems = {e.id: e for e in m.site_elements}
    ground = []
    for i, (o, k, z0, z1, p, r) in enumerate(bx.masses):
        if z0 >= ROAD_CLEAR_M:
            continue
        if i in bx.rings:
            p = MS.ring_ground(bx.rings[i], p, WHEEL_CLEAR_M)
            if p.is_empty:
                continue
        ground.append((o, k, z0, z1, p, r))
    if not ground:
        return c
    arr = np.array([g[4] for g in ground], dtype=object)
    zarr = np.array(zones, dtype=object)
    gi, zi = tree.query(arr, predicate="intersects")
    hit = _interior_pairs(arr, zarr, gi, zi)
    pairs = sorted(zip(gi[hit].tolist(), zi[hit].tolist()))
    for i, k in pairs:
        owner, kind, z0, z1, poly, role = ground[i]
        lab, zid = labels[k]
        if kind == "building":
            b = owners[owner]
            site = b.megasite_id
            if lab == "open" and (b.attrs.get("open_space_id") == zid or
                                  zid in b.attrs.get("open_space_ids", ())):
                continue
        else:
            site = elems[owner].megasite_id
        if lab in ("reserve", "cone") and site == zid:
            continue
        a = G.area1(G.inter(poly, zones[k]))
        if a > AREA_TOL_M2:
            _limit(c, c.failures, f"{owner}: {role} mass on {lab} {zid} ({a:.1f} m2)")
    return c


def check_overlaps(m: CityModel, bx: _B):
    c = _check("building_overlaps", "No two buildings, site elements or skybridge decks "
                                    "overlap (plan and height)")
    items = list(bx.masses)
    for s in m.skybridges:
        (ax, ay), (bx_, by) = s.line
        L = math.sqrt((bx_ - ax) * (bx_ - ax) + (by - ay) * (by - ay))
        if L <= 0.6:
            continue
        ux, uy = (bx_ - ax) / L, (by - ay) / L
        h = s.width_m / 2.0
        pa = (ax + ux * 0.3, ay + uy * 0.3)
        pb = (bx_ - ux * 0.3, by - uy * 0.3)
        poly = Polygon([(pa[0] - uy * h, pa[1] + ux * h), (pb[0] - uy * h, pb[1] + ux * h),
                        (pb[0] + uy * h, pb[1] - ux * h), (pa[0] + uy * h, pa[1] - ux * h)])
        items.append((s.id, "skybridge", s.z_m - DECK_M, s.z_m + s.levels * s.level_height_m,
                      poly, "deck"))
    if len(items) < 2:
        return c
    arr = np.array([it[4] for it in items], dtype=object)
    tree = shapely.STRtree(arr)
    ia, ib = tree.query(arr, predicate="intersects")
    keep = ia < ib
    ia, ib = ia[keep], ib[keep]
    z0 = np.array([it[2] for it in items])
    z1 = np.array([it[3] for it in items])
    zok = (z0[ia] < z1[ib] - 0.01) & (z0[ib] < z1[ia] - 0.01)
    ia, ib = ia[zok], ib[zok]
    hit = _interior_pairs(arr, arr, ia, ib)
    seen = set()
    for a, b in sorted(zip(ia[hit].tolist(), ib[hit].tolist())):
        A, B = items[a], items[b]
        if A[0] == B[0]:
            continue
        if not (A[2] < B[3] - 0.01 and B[2] < A[3] - 0.01):
            continue
        inter = G.inter(A[4], B[4])
        ring = bx.rings.get(a) if a < len(bx.masses) else None
        ring = ring or (bx.rings.get(b) if b < len(bx.masses) else None)
        if ring is not None and not inter.is_empty:
            other = B if a in bx.rings else A
            zb = MS.ring_zband(ring, G.parts(inter)[0])
            if zb is None or not (other[2] < zb[1] - 0.01 and zb[0] < other[3] - 0.01):
                continue
        ar = G.area1(inter)
        if ar > OVERLAP_TOL_M2:
            key = (A[0], B[0])
            if key in seen:
                continue
            seen.add(key)
            _limit(c, c.failures, f"{A[0]} ({A[5]}) and {B[0]} ({B[5]}) overlap by "
                                  f"{ar:.1f} m2 between {max(A[2], B[2]):.1f} and "
                                  f"{min(A[3], B[3]):.1f} m")
    return c


def check_heights(spec: CitySpec, m: CityModel, bx: _B):
    c = _check("building_heights", "Building heights within the district's archetype range "
                                   "(under a flight-cone cap where one applies; parking "
                                   "structures only under the top); landmarks and megasites "
                                   "aside")
    rng = {d.name: d.height_m for d in spec.districts}
    for b in m.buildings:
        if b.landmark or b.megasite_id or not b.district_id:
            continue
        d = bx.district[b.district_id]
        lo, hi = rng[d.name]
        cap = bx.cap(bx.foot[b.id]) if bx.foot.get(b.id) is not None and bx.cones \
            else math.inf
        top = min(hi, cap)
        kind = b.type.split(".", 1)[1] if "." in b.type else b.type
        # under a cap, the floor grid may leave the building up to one floor below it
        low = 0.0 if kind in ANCILLARY else lo if top >= lo else top - b.floor_height_m
        if not (low - 0.01 <= b.height_m <= top + 0.01):
            _limit(c, c.failures, f"{b.id} ({kind}): {b.height_m:g} m outside {low:g} to "
                                  f"{top:g} m ('{d.name}', {d.archetype})")
    return c


def _ground_walks(m: CityModel):
    from .buildout import GROUND_WALKS

    ws = [w for w in m.walkways if w.kind in GROUND_WALKS and
          all(abs(p[2]) < 1e-9 for p in w.line)]
    lines = [LineString([p[:2] for p in w.line]) for w in ws]
    return ws, lines


def check_entrances(m: CityModel, bx: _B):
    c = _check("building_entrances", "Every building has a main entrance on its facade, "
                                     "within 20 m of a ground walkway or a shared alley, service "
                                     "lane or pedestrian street, or joined to the walkway graph "
                                     "by a path (megasite buildings and landmarks always)")
    ws, lines = _ground_walks(m)
    lines += [LineString(s.centerline) for s in m.road_segments
              if s.road_class in ("alley", "service", "pedestrian")]
    tree = shapely.STRtree(lines) if lines else None
    ids = {w.id for w in m.walkways}
    doors = {w.attrs.get("building") for w in m.walkways if w.attrs.get("door")}
    pts, owners = [], []
    for b in m.buildings:
        main = [e for e in b.entrances if e.kind in ("main", "gate")]
        if not main:
            _limit(c, c.failures, f"{b.id}: no main entrance")
            continue
        e = main[0]
        foot = bx.foot.get(b.id)
        if foot is not None and G.dist(foot.exterior, Point(e.position)) > 0.6:
            _limit(c, c.failures, f"{b.id}: main entrance {G.dist(foot.exterior, Point(e.position)):.1f} m off its "
                                  f"facade")
        if e.walkway_id is not None and e.walkway_id not in ids:
            _limit(c, c.failures, f"{b.id}: entrance walkway {e.walkway_id} missing")
        if b.megasite_id or b.landmark:
            if b.id not in doors:
                _limit(c, c.failures, f"{b.id}: megasite building not joined to the walkways")
            continue
        if b.id in doors:
            continue   # a path joins the entrance to the walkways
        pts.append(Point(e.position))
        owners.append(b.id)
    if tree is not None and pts:
        arr = np.array(pts, dtype=object)
        ok = tree.query(arr, predicate="dwithin", distance=ENTRANCE_REACH_M + 1e-6)
        reached = set(ok[0].tolist())
        for i, bid in enumerate(owners):
            if i not in reached:
                _limit(c, c.failures, f"{bid}: main entrance more than {ENTRANCE_REACH_M:g} m "
                                      f"from a walkway")
    return c


def check_units(m: CityModel, bx: _B):
    c = _check("ground_floor_units", "Ground-floor units 4 to 12 m wide, on the ground "
                                     "facade, facing one of the lot's frontage roads")
    for b in m.buildings:
        if not b.units:
            continue
        foot = bx.foot.get(b.id)
        fronts = set()
        p = bx.prop.get(b.property_id)
        for lid in (p.lot_ids if p is not None else [b.lot_id]):
            fronts |= bx.lot_front.get(lid, set())
        for u in b.units:
            (ax, ay), (bx_, by) = u.edge
            L = math.sqrt((bx_ - ax) * (bx_ - ax) + (by - ay) * (by - ay))
            if not (UNIT_W_M[0] - 0.05 <= u.width_m <= UNIT_W_M[1] + 0.05):
                _limit(c, c.failures, f"{b.id}: unit {u.width_m:g} m wide")
            if L > u.width_m + 0.05:
                _limit(c, c.failures, f"{b.id}: unit edge {L:.2f} m longer than its width")
            if foot is not None:
                d = max(G.dist(foot.exterior, Point(ax, ay)),
                        G.dist(foot.exterior, Point(bx_, by)))
                if d > 0.6:
                    _limit(c, c.failures, f"{b.id}: unit {d:.1f} m off the facade")
            if u.segment_id not in fronts:
                _limit(c, c.failures, f"{b.id}: unit faces {u.segment_id}, not a frontage road")
    return c


def _item_rect(it, shrink: float = 0.0) -> Polygon:
    x, y, _ = it.position
    su, sv, _ = it.size
    su, sv = max(su - 2 * shrink, 0.02), max(sv - 2 * shrink, 0.02)
    a = M.radians(it.yaw_deg)
    ca, sa = float(M.cos(a)), float(M.sin(a))
    pts = []
    for u, v in ((-su / 2, -sv / 2), (su / 2, -sv / 2), (su / 2, sv / 2), (-su / 2, sv / 2)):
        pts.append((x + (u * ca - v * sa), y + (u * sa + v * ca)))
    return Polygon(pts)


def check_roof_items(m: CityModel, bx: _B):
    c = _check("roof_items", "Rooftop items stand on a roof of their building (a mass top at "
                             "their level that holds their footprint)")
    for b in m.buildings:
        if not b.roof_items:
            continue
        tops: dict = {}
        for k, mass in enumerate(b.masses):
            tops.setdefault(round(mass.z1_m, 2), []).append(k)
        for it in b.roof_items:
            ks = tops.get(round(it.position[2], 2), [])
            r = _item_rect(it, 0.05)
            if not any(bx.mass_of[(b.id, k)].covers(r) for k in ks):
                _limit(c, c.failures, f"{b.id}: {it.kind} at z {it.position[2]:g} is not on a "
                                      f"roof")
    return c


def _sky_pairs(m: CityModel) -> set:
    return {tuple(sorted(s.building_ids)) for s in m.skybridges}


def check_complexes(m: CityModel, bx: _B):
    c = _check("complexes", "Every merged lot group is built as its complex: twin towers "
                            "(two equal towers and a skybridge), tower clusters (three or more "
                            "stepped towers bridged), megabuilding campuses, campuses, bridged "
                            "pairs and straddle buildings")
    want: dict = {}
    for lt in m.lots:
        if lt.merged_group_id:
            want.setdefault((lt.district_id, lt.attrs.get("complex")), set()).add(
                lt.merged_group_id)
    sky = _sky_pairs(m)
    have: dict = {}
    for p in m.properties:
        if p.complex not in ("single", "landmark", "megasite"):
            have.setdefault((p.district_id, p.complex), []).append(p)
    for key in sorted(want, key=lambda k: (k[0], k[1] or "")):
        did, kind = key
        props = have.get(key, [])
        if len(props) < len(want[key]):
            _limit(c, c.failures, f"{did}: {len(props)} {kind} built for {len(want[key])} "
                                  f"merged groups")
    for key in sorted(have):
        kind = key[1]
        for p in have[key]:
            gid = p.id
            bs = [bx.bld[i] for i in p.building_ids if i in bx.bld]
            pairs = {tuple(sorted((a.id, b.id))) for i, a in enumerate(bs) for b in bs[i + 1:]}
            bridged = pairs & sky
            _complex_rules(c, m, gid, kind, bs, bridged)
    return c


def _complex_rules(c, m, gid, kind, bs, bridged) -> None:
    if True:
        if kind == "twin_towers":
            if len(bs) != 2 or abs(bs[0].height_m - bs[1].height_m) > 0.01 or not bridged:
                _limit(c, c.failures, f"{gid}: twin towers need two equal towers and a "
                                      f"skybridge")
        elif kind == "tower_cluster":
            hs = sorted({round(b.height_m, 2) for b in bs})
            if len(bs) < 3 or len(hs) < 3 or len(bridged) < len(bs) - 1:
                _limit(c, c.failures, f"{gid}: cluster needs three stepped towers, bridged")
        elif kind == "megabuilding_campus":
            if len(bs) < 2 or len(bridged) < len(bs) - 1:
                _limit(c, c.failures, f"{gid}: megabuilding campus needs satellites joined "
                                      f"by bridges")
        elif kind == "campus":
            canopies = [s for s in m.structures if s.attrs.get("campus") == gid.rsplit(".", 1)[0]]
            if len(bs) < 3 or not canopies:
                _limit(c, c.failures, f"{gid}: campus needs three buildings and covered "
                                      f"walkways")
        elif kind == "bridged_pair":
            ok = any(any(x.startswith("rs") for x in s.crosses) for s in m.skybridges
                     if tuple(sorted(s.building_ids)) in bridged)
            if len(bs) != 2 or not ok:
                _limit(c, c.failures, f"{gid}: bridged pair needs a skybridge across a "
                                      f"street")
        elif kind == "straddle_building":
            span = [mass for b in bs for mass in b.masses if mass.role in SPAN_ROLES]
            if not span:
                _limit(c, c.failures, f"{gid}: straddle building has no span")


def check_skybridges(m: CityModel, bx: _B):
    c = _check("skybridges", "Skybridges: 8 to 80 m, ends on facades of masses that reach "
                             "the deck, level on both floor grids, roughly perpendicular, 5.5 m "
                             "over roads and the navigable clearance over water, through no "
                             "other building, joined to the walkway graph")
    P = G.from_model_poly
    roads = [(s.id, G.qpoly(LineString(s.centerline).buffer(s.width_m / 2.0, cap_style="flat",
                                                            join_style="mitre")),
              max((z.z for z in s.z_profile), default=0.0)) for s in m.road_segments]
    rtree = shapely.STRtree([r[1] for r in roads]) if roads else None
    water = []
    for r in m.rivers:
        water.append((r.id, P(r.polygon), WATER_CLEAR["river"]))
    for ch in m.channels:
        cls = "sea" if ch.kind == "sea_channel" else "river" if ch.kind == "delta_branch" \
            else "canal"
        water.append((ch.id, P(ch.polygon), WATER_CLEAR[cls]))
    for w in m.waterways:
        water.append((w.id, P(w.polygon), WATER_CLEAR["sea" if w.kind == "basin" else "canal"]))
    for s in m.seas:
        for p in s.polygons:
            water.append((s.id, P(p), WATER_CLEAR["sea"]))
    wtree = shapely.STRtree([w[1] for w in water]) if water else None
    walk = {w.id: w for w in m.walkways}
    comp = _walk_components(m)
    ground_roots = {comp.get(tuple(w.line[0][:2])) for w in m.walkways if w.kind == "sidewalk"}
    for s in m.skybridges:
        (ax, ay), (bx_, by) = s.line
        L = math.sqrt((bx_ - ax) * (bx_ - ax) + (by - ay) * (by - ay))
        if not (SKY_LEN_M[0] - 0.05 <= L <= SKY_LEN_M[1] + 0.05):
            _limit(c, c.failures, f"{s.id}: {L:.1f} m long")
        top = s.z_m + s.levels * s.level_height_m
        ux, uy = ((bx_ - ax) / L, (by - ay) / L) if L > 0 else (1.0, 0.0)
        for bid, (px, py) in zip(s.building_ids, s.line):
            b = bx.bld.get(bid)
            if b is None:
                _limit(c, c.failures, f"{s.id}: building {bid} missing")
                continue
            k = s.z_m / b.floor_height_m
            if abs(k - round(k)) > 0.003:
                _limit(c, c.failures, f"{s.id}: level {s.z_m:g} m is not a floor of {bid} "
                                      f"({b.floor_height_m:g} m floors)")
            ok = False
            for mass in b.masses:
                if mass.z0_m <= s.z_m + 1e-6 and mass.z1_m >= top - 1e-6:
                    poly = P(mass.footprint)
                    if G.dist(poly.exterior, Point(px, py)) <= 0.05:
                        ok = _perpendicular(poly, (px, py), ux, uy)
                        if ok:
                            break
            if not ok:
                _limit(c, c.failures, f"{s.id}: end at {bid} is not on a facade that reaches "
                                      f"{s.z_m:g} to {top:g} m (perpendicular within "
                                      f"{PERP_TOL_DEG:g} degrees)")
        h = s.width_m / 2.0
        deck = Polygon([(ax + ux * 0.3 - uy * h, ay + uy * 0.3 + ux * h),
                        (bx_ - ux * 0.3 - uy * h, by - uy * 0.3 + ux * h),
                        (bx_ - ux * 0.3 + uy * h, by - uy * 0.3 - ux * h),
                        (ax + ux * 0.3 + uy * h, ay + uy * 0.3 - ux * h)])
        under = s.z_m - DECK_M
        if rtree is not None:
            for k in sorted(int(i) for i in rtree.query(deck, predicate="intersects")):
                rid, rp, zmax = roads[k]
                if under - zmax < ROAD_CLEAR_M - 1e-6:
                    _limit(c, c.failures, f"{s.id}: {under - zmax:.1f} m over road {rid}")
        if wtree is not None:
            for k in sorted(int(i) for i in wtree.query(deck, predicate="intersects")):
                wid, wp, cl = water[k]
                if under < cl - 1e-6:
                    _limit(c, c.failures, f"{s.id}: {under:.1f} m over {wid} (needs {cl:g})")
        if under < 2.5 - 1e-6:
            _limit(c, c.failures, f"{s.id}: deck {under:.1f} m above the ground")
        ids = [w for w in s.walkway_ids if w in walk]
        if not any(walk[w].kind == "skybridge" for w in ids):
            _limit(c, c.failures, f"{s.id}: no skybridge walkway")
        elif comp.get(tuple(walk[ids[0]].line[0][:2])) not in ground_roots:
            _limit(c, c.failures, f"{s.id}: not joined to the ground walkways")
    return c


def _perpendicular(poly, p, ux, uy) -> bool:
    """The facade edge of poly through p is within PERP_TOL_DEG of perpendicular to (ux, uy)."""
    c = list(poly.exterior.coords)
    best = None
    for i in range(len(c) - 1):
        a, b = c[i], c[i + 1]
        dx, dy = b[0] - a[0], b[1] - a[1]
        L2 = dx * dx + dy * dy
        if L2 <= 0:
            continue
        t = ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / L2
        t = min(1.0, max(0.0, t))
        ex, ey = p[0] - (a[0] + t * dx), p[1] - (a[1] + t * dy)
        d = ex * ex + ey * ey
        if best is None or d < best[0]:
            best = (d, dx, dy, math.sqrt(L2))
    if best is None:
        return False
    _, dx, dy, L = best
    cosang = abs((dx * ux + dy * uy) / L)
    return cosang <= float(M.sin(M.radians(PERP_TOL_DEG))) + 1e-9


def _walk_components(m: CityModel) -> dict:
    parent: dict = {}

    def find(x):
        while parent.setdefault(x, x) != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for w in m.walkways:
        a, b = tuple(w.line[0][:2]), tuple(w.line[-1][:2])
        parent[find(a)] = find(b)
    return {x: find(x) for x in list(parent)}


def check_landmarks(spec: CitySpec, m: CityModel, bx: _B):
    c = _check("landmarks", "Every landmark of the spec is built in its district with its "
                            "kind and height (the megatower with three arms)")
    did = {d.name: d.id for d in m.districts}
    for d in spec.districts:
        for lm in d.landmarks:
            b = next((x for x in m.buildings if x.landmark and x.name == lm.name and
                      x.district_id == did.get(d.name)), None)
            if b is None:
                _limit(c, c.failures, f"landmark '{lm.name}' ({lm.kind}) in '{d.name}' not "
                                      f"built")
                continue
            if b.attrs.get("landmark_kind") != lm.kind:
                _limit(c, c.failures, f"landmark '{lm.name}': kind "
                                      f"{b.attrs.get('landmark_kind')} (asked {lm.kind})")
            want = float(lm.height_m)
            if b.attrs.get("height_capped"):
                capm = float(b.attrs.get("height_cap_m", 0.0))
                if capm > bx.cap(bx.foot[b.id]) + 0.01:
                    _limit(c, c.failures, f"landmark '{lm.name}': cap {capm:g} m is above the "
                                          f"flight-cone limit")
                want = min(want, capm)
            if abs(b.height_m - want) > 0.05:
                _limit(c, c.failures, f"landmark '{lm.name}': {b.height_m:g} m (asked "
                                      f"{want:g} m)")
            if lm.kind == "megatower" and b.attrs.get("arms") != 3:
                _limit(c, c.failures, f"landmark '{lm.name}': megatower without three arms")
    return c


def check_megasite_contents(m: CityModel, bx: _B):
    c = _check("megasite_contents", "Every megasite reserve is filled by its site generator "
                                    "with the parts its kind needs, all inside the reserve")
    kinds: dict = {}
    for b in m.buildings:
        if b.megasite_id:
            kinds.setdefault(b.megasite_id, set()).add(b.type.split(".", 1)[1])
    for e in m.site_elements:
        if e.megasite_id:
            kinds.setdefault(e.megasite_id, set()).add(e.kind)
    ids = {b.id for b in m.buildings} | {e.id for e in m.site_elements} | \
        {s.id for s in m.structures}
    for s in m.megasites:
        have = kinds.get(s.id, set())
        if not s.member_ids:
            _limit(c, c.failures, f"{s.id} '{s.name}' ({s.kind}): reserve left empty")
            continue
        missing = [k for k in REQUIRED.get(s.kind, ()) if k not in have]
        if missing:
            _limit(c, c.failures, f"{s.id} '{s.name}' ({s.kind}): no {', '.join(missing)}")
        gone = [i for i in s.member_ids if i not in ids]
        if gone:
            _limit(c, c.failures, f"{s.id}: members missing ({gone[0]})")
        poly = bx.site_poly[s.id]
        shapely.prepare(poly)
        for e in m.site_elements:
            if e.megasite_id == s.id and e.footprint is not None:
                out = _outside(G.from_model_poly(e.footprint), poly)
                if out > AREA_TOL_M2:
                    _limit(c, c.failures, f"{e.id}: {e.kind} {out:.1f} m2 outside its reserve")
    return c


def check_megasite_heights(m: CityModel, bx: _B):
    c = _check("megasite_heights", "Nothing inside a spaceport flight cone above its height "
                                   "limit, and nothing near one above the transitional surface "
                                   "(limit + 1 m per 1 m away)")
    if not bx.cones or not bx.masses:
        return c
    arr = np.array([x[4] for x in bx.masses], dtype=object)
    z1 = np.array([x[3] for x in bx.masses])
    for cone, lim, sid in bx.cones:
        d = G.dists(cone, arr)
        bad = np.nonzero(z1 > lim + CONE_SLOPE * d + 0.01)[0].tolist()
        for i in bad:
            owner, kind, _, top, _, role = bx.masses[i]
            _limit(c, c.failures, f"{owner} ({role}): top {top:g} m, limit "
                                  f"{lim + CONE_SLOPE * float(d[i]):.1f} m near {sid}")
    return c


def check_megasite_access(m: CityModel, bx: _B):
    c = _check("megasite_access", "Every megasite reaches a road (within 40 m) and its "
                                  "buildings and paths join the walkway graph")
    lines = [LineString(s.centerline) for s in m.road_segments
             if s.road_class in ("highway", "avenue", "street", "service", "alley")]
    tree = shapely.STRtree(lines) if lines else None
    joined = {w.attrs.get("megasite") for w in m.walkways if w.attrs.get("megasite")}
    for s in m.megasites:
        poly = bx.site_poly[s.id]
        if tree is None or not len(tree.query(poly, predicate="dwithin", distance=SITE_ROAD_M)):
            _limit(c, c.failures, f"{s.id} '{s.name}': no road within {SITE_ROAD_M:g} m")
        has_b = any(b.megasite_id == s.id for b in m.buildings)
        paths = s.kind in ("central_park", "grand_plaza")
        if paths and s.id not in joined:
            _limit(c, c.failures, f"{s.id} '{s.name}': site paths not joined to the walkways")
        if not has_b and not paths and s.member_ids:
            c.notes.append(f"{s.id} '{s.name}': no buildings")
    c.notes.append("transit links of megasites are checked in M5 (no transit lines yet)")
    return c


def run(spec: CitySpec, m: CityModel, g, bx: _B | None = None) -> list:
    bx = bx or _B(m)
    return [
        check_footprints(m, bx),
        check_clear_zones(m, bx),
        check_overlaps(m, bx),
        check_heights(spec, m, bx),
        check_entrances(m, bx),
        check_units(m, bx),
        check_roof_items(m, bx),
        check_complexes(m, bx),
        check_skybridges(m, bx),
        check_landmarks(spec, m, bx),
        check_megasite_contents(m, bx),
        check_megasite_heights(m, bx),
        check_megasite_access(m, bx),
    ]


# ---------------------------------------------------------------------------
# Stats
# ---------------------------------------------------------------------------

def _pcts(vals) -> dict:
    a = sorted(vals)
    if not a:
        return {}
    q = lambda f: round(float(a[min(int(f * (len(a) - 1) + 0.5), len(a) - 1)]), 1)  # noqa
    return {"count": len(a), "min": round(float(a[0]), 1), "median": q(0.5), "p90": q(0.9),
            "max": round(float(a[-1]), 1)}


FLOOR_ROLES_SKIP = ("spire", "deck", "dock", "ramp", "wheel", "leg", "roof", "platform",
                    "plinth", "obelisk", "shaft", "pad", "boom", "stack", "tank", "tower_frame")


def floor_area(b, areas) -> float:
    tot = 0.0
    for mass, a in zip(b.masses, areas):
        if mass.role in FLOOR_ROLES_SKIP or mass.shape == "ring":
            continue
        n = max(1, int((mass.z1_m - mass.z0_m) / b.floor_height_m + 0.5))
        tot += a * n
    return tot


def stats(spec: CitySpec, m: CityModel, bx: _B | None = None) -> dict:
    names = {d.id: d.name for d in m.districts}
    arch = {d.id: d.archetype for d in m.districts}
    by_type: dict = {}
    by_use: dict = {}
    hs: dict = {}
    fa: dict = {}
    foot: dict = {}
    units: dict = {}
    roof: dict = {}
    total_fa = 0.0
    if bx is not None:
        mpolys = [x[4] for x in bx.masses if x[1] == "building"]
        fpolys = [bx.foot[b.id] if bx.foot.get(b.id) is not None else Polygon()
                  for b in m.buildings]
    else:
        mpolys = G.from_model_polys([mass.footprint for b in m.buildings for mass in b.masses])
        fpolys = [G.from_model_poly(b.footprint) if b.footprint else Polygon()
                  for b in m.buildings]
    mareas = G.areas(np.array(mpolys, dtype=object)).tolist() if mpolys else []
    fareas = dict(zip([b.id for b in m.buildings],
                      G.areas(np.array(fpolys, dtype=object)).tolist())) if fpolys else {}
    pos = 0
    for b in m.buildings:
        t = b.type.split(".", 1)[1]
        by_type[t] = by_type.get(t, 0) + 1
        by_use[b.use] = by_use.get(b.use, 0) + 1
        a = floor_area(b, mareas[pos:pos + len(b.masses)])
        pos += len(b.masses)
        total_fa += a
        if b.district_id and not b.megasite_id:
            hs.setdefault(b.district_id, []).append(b.height_m)
            fa[b.district_id] = fa.get(b.district_id, 0.0) + a
            foot[b.district_id] = foot.get(b.district_id, 0.0) + fareas[b.id]
        for u in b.units:
            units[u.use] = units.get(u.use, 0) + 1
        for it in b.roof_items:
            roof[it.kind] = roof.get(it.kind, 0) + 1
    lot_a: dict = {}
    for lt in m.lots:
        lot_a[lt.district_id] = lot_a.get(lt.district_id, 0.0) + lt.area_m2
    rows = {}
    for did in sorted(names):
        r = _pcts(hs.get(did, []))
        la = lot_a.get(did, 0.0)
        r.update({"archetype": arch[did], "floor_area_km2": round(fa.get(did, 0.0) / 1e6, 3),
                  "coverage": round(foot.get(did, 0.0) / la, 3) if la else 0.0,
                  "far": round(fa.get(did, 0.0) / la, 2) if la else 0.0})
        rows[names[did]] = r
    sk: dict = {}
    for s in m.skybridges:
        sk[s.kind] = sk.get(s.kind, 0) + 1
    cx: dict = {}
    for p in m.properties:
        if p.complex not in ("single",):
            cx[p.complex] = cx.get(p.complex, 0) + 1
    return {
        "count": len(m.buildings), "floor_area_km2": round(total_fa / 1e6, 3),
        "by_type": dict(sorted(by_type.items(), key=lambda t: (-t[1], t[0]))),
        "by_use": dict(sorted(by_use.items(), key=lambda t: (-t[1], t[0]))),
        "by_district": rows,
        "properties": len(m.properties), "complexes": dict(sorted(cx.items())),
        "skybridges": len(m.skybridges), "skybridges_by_kind": dict(sorted(sk.items())),
        "skybridge_km": round(sum(s.length_m for s in m.skybridges) / 1000, 2),
        "units": sum(units.values()), "units_by_use": dict(sorted(units.items(),
                                                                  key=lambda t: (-t[1], t[0]))),
        "roof_items": dict(sorted(roof.items(), key=lambda t: (-t[1], t[0]))),
        "green_roofs": sum(1 for g in m.green_areas if g.kind == "green_roof"),
        "green_roof_m2": round(sum(G.area1(G.from_model_poly(g.polygon))
                                   for g in m.green_areas if g.kind == "green_roof")),
        "landmarks": [{"name": b.name, "kind": b.attrs.get("landmark_kind"),
                       "height_m": b.height_m, "district": names.get(b.district_id)}
                      for b in m.buildings if b.landmark],
        "megasites": {s.name: {"kind": s.kind, "contents": s.attrs.get("contents", {})}
                      for s in m.megasites},
        "site_elements": len(m.site_elements), "structures": len(m.structures),
        "tallest_m": max((b.height_m for b in m.buildings), default=0.0),
    }
