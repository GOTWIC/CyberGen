"""M11 checks: the gameplay layer (points of interest, zones, fields, densities, parking,
travel points, sign slots), with the reachability of every place on foot and by car."""

from __future__ import annotations

import math

import numpy as np
import shapely
from shapely.geometry import LineString, Point

from . import geom as G
from . import gameplay as GP
from .buildout import GROUND_WALKS
from .checks import Check
from .model import HOUR_BANDS, CityModel

LIMIT = 12
TOL_M = 0.05


def _limit(c: Check, msg: str) -> None:
    if len(c.failures) < LIMIT:
        c.failures.append(msg)
    elif len(c.failures) == LIMIT:
        c.failures.append("... more")


def _places(m: CityModel):
    """(owner id, access) of every door with an access: POIs, parking, travel points."""
    for p in m.pois:
        for a in p.entrances:
            yield p.id, a
    for p in m.parking:
        for a in p.entrances:
            yield p.id, a
    for t in m.travel_points:
        yield t.id, t.access


class _Net:
    def __init__(self, m: CityModel):
        self.roots, self.main = GP.foot_roots(m)
        self.walk = {w.id: w for w in m.walkways}
        self.ground = [w for w in m.walkways if w.kind in GROUND_WALKS and
                       all(abs(p[2]) <= 1e-9 for p in w.line)]
        self.glines = [LineString([p[:2] for p in w.line]) for w in self.ground]
        self.ggeo = np.array(self.glines, dtype=object)
        self.gtree = shapely.STRtree(self.glines) if self.glines else None
        self.lane = {ln.id: ln for ln in m.lanes}
        self.scc = GP.largest_scc(GP.lane_graph(m))
        self.seg = {s.id: s for s in m.road_segments}

    def root(self, w) -> tuple:
        return self.roots.get(tuple(w.line[0][:2]))


def check_reach_foot(m: CityModel, n: _Net) -> Check:
    c = Check("poi_reachable_foot", "Every point of interest, parking entrance and travel "
                                    "point reachable on foot: its door opens on a ground "
                                    "walkway within 40 m in the walkway component of its "
                                    "landmass, and its curb point is on the same component")
    count = 0
    for oid, a in _places(m):
        count += 1
        w = n.walk.get(a.walkway_id)
        if w is None:
            _limit(c, f"{oid}: walkway {a.walkway_id} missing")
            continue
        if w.kind not in GROUND_WALKS or any(abs(p[2]) > 1e-9 for p in w.line):
            _limit(c, f"{oid}: walkway {w.id} ({w.kind}) is not on the ground")
            continue
        r = n.root(w)
        if r not in n.main:
            _limit(c, f"{oid}: walkway {w.id} is off the main walkway component of its "
                      "landmass")
            continue
        d = G.dist(LineString([p[:2] for p in w.line]), Point(a.position))
        if d > GP.WALK_REACH_M + 0.01 or abs(d - a.walk_link_m) > TOL_M:
            _limit(c, f"{oid}: door {d:.2f} m from walkway {w.id} (recorded "
                      f"{a.walk_link_m} m)")
            continue
        hit = GP._nearest(n.gtree, n.ggeo, Point(a.curb), GP.WALK_REACH_M,
                          ok=lambda i: n.root(n.ground[i]) in n.main)
        if hit is None or n.root(n.ground[hit[1]]) != r:
            _limit(c, f"{oid}: curb point {a.curb} is not on the door's walkway component")
    c.notes.append(f"{count} doors")
    return c


def check_reach_car(m: CityModel, n: _Net) -> Check:
    c = Check("poi_reachable_car", "Every point of interest, parking entrance and travel "
                                   "point reachable by car: its curb lane is a ground drive "
                                   "lane of a local road in the lane graph's largest strongly "
                                   "connected part, the curb on that lane within 150 m of the "
                                   "door")
    for oid, a in _places(m):
        ln = n.lane.get(a.lane_id)
        if ln is None:
            _limit(c, f"{oid}: lane {a.lane_id} missing")
            continue
        s = n.seg.get(ln.segment_id)
        if ln.kind != "lane" or s is None or s.road_class not in GP.DRIVE_CLASSES or \
                any(abs(p[2]) > 0.5 for p in ln.centerline):
            _limit(c, f"{oid}: lane {ln.id} is not a ground drive lane of a local road")
            continue
        if ln.id not in n.scc:
            _limit(c, f"{oid}: lane {ln.id} is off the lane graph's largest strongly "
                      "connected part")
            continue
        d = G.dist(LineString([p[:2] for p in ln.centerline]), Point(a.curb))
        if d > TOL_M:
            _limit(c, f"{oid}: curb point {d:.2f} m off lane {ln.id}")
        far = math.hypot(a.curb[0] - a.position[0], a.curb[1] - a.position[1])
        if far > GP.DRIVE_REACH_M + 0.01 or abs(far - a.curb_m) > TOL_M:
            _limit(c, f"{oid}: curb {far:.1f} m from the door (recorded {a.curb_m} m)")
    return c


def check_pois(m: CityModel, n: _Net) -> Check:
    c = Check("poi_places", "Points of interest: every one named (names unique among places "
                            "and travel points), at its building (doors on the facade, units "
                            "of the right use), fixers in an existing venue, valid hours and "
                            "zones")
    bld = {b.id: b for b in m.buildings}
    zones = {z.id for z in m.zones}
    ids = {p.id for p in m.pois}
    names: dict[str, str] = {}
    for x in [*m.pois, *m.travel_points]:
        if not x.name.strip():
            _limit(c, f"{x.id}: no name")
        elif x.name in names:
            _limit(c, f"{x.id}: name '{x.name}' also used by {names[x.name]}")
        else:
            names[x.name] = x.id
    for p in m.pois:
        if p.kind != p.type.split(".")[1]:
            _limit(c, f"{p.id}: type {p.type} does not match kind {p.kind}")
        if not (0 <= p.hours[0] <= 24 and 0 <= p.hours[1] <= 24):
            _limit(c, f"{p.id}: hours {p.hours}")
        if p.zone_id is not None and p.zone_id not in zones:
            _limit(c, f"{p.id}: zone {p.zone_id} missing")
        if p.kind == "fixer":
            if p.host_id not in ids:
                _limit(c, f"{p.id}: host {p.host_id} missing")
            continue
        b = bld.get(p.building_id)
        if b is None:
            _limit(c, f"{p.id}: building {p.building_id} missing")
            continue
        if p.unit_index is not None:
            if not 0 <= p.unit_index < len(b.units):
                _limit(c, f"{p.id}: unit {p.unit_index} missing")
                continue
            u = b.units[p.unit_index]
            if GP.UNIT_POI.get(u.use, (None,))[0] != p.kind:
                _limit(c, f"{p.id}: unit use {u.use} is not a {p.kind}")
        if p.kind == "apartment" and not 0 <= p.floor < max(1, b.floors):
            _limit(c, f"{p.id}: floor {p.floor} of {b.floors}")
        foot = [G.from_model_poly(ms.footprint) for ms in b.masses if ms.z0_m <= 0.5]
        if b.footprint is not None:
            foot.append(G.from_model_poly(b.footprint))
        for a in p.entrances:
            d = min(G.dist(f.exterior, Point(a.position)) for f in foot) if foot else 1e9
            if d > 1.5:
                _limit(c, f"{p.id}: door {d:.2f} m off the facade of {b.id}")
    return c


def check_zones(m: CityModel, n: _Net) -> Check:
    c = Check("territories", "Zones: each district's territories cover it without overlap "
                             "and hold each of its blocks once, every district has a police "
                             "precinct, factions and zones refer to each other")
    fac = {f.id: f for f in m.factions}
    zone = {z.id: z for z in m.zones}
    for f in m.factions:
        for zid in f.zone_ids:
            if zid not in zone or zone[zid].faction_id != f.id:
                _limit(c, f"{f.id}: zone {zid} missing or held by another faction")
    blocks: dict[str, list] = {}
    for b in m.blocks:
        blocks.setdefault(b.district_id, []).append(b.id)
    for d in m.districts:
        terr = [z for z in m.zones if z.district_id == d.id and z.kind == "territory"]
        pol = [z for z in m.zones if z.district_id == d.id and z.kind == "police"]
        if not terr:
            _limit(c, f"{d.id}: no territory")
            continue
        if len(pol) != 1:
            _limit(c, f"{d.id}: {len(pol)} police precincts")
        for z in terr + pol:
            if z.faction_id not in fac:
                _limit(c, f"{z.id}: faction {z.faction_id} missing")
        polys = [shapely.MultiPolygon([G.from_model_poly(p) for p in z.polygons])
                 for z in terr]
        area = G.area(G.from_model_poly(d.polygon))
        cover = sum(G.area(p) for p in polys)
        over = 0.0
        for i in range(len(polys)):
            for j in range(i + 1, len(polys)):
                over += G.area(G.inter(polys[i], polys[j]))
        if over > 1.0 + 1e-4 * area:
            _limit(c, f"{d.id}: territories overlap by {over:.0f} m2")
        if abs(cover - over - area) > 1.0 + 0.005 * area:
            _limit(c, f"{d.id}: territories cover {cover - over:.0f} of {area:.0f} m2")
        held: dict[str, int] = {}
        for z in terr:
            for bid in z.block_ids:
                held[bid] = held.get(bid, 0) + 1
        for bid in blocks.get(d.id, []):
            if held.get(bid, 0) != 1:
                _limit(c, f"{d.id}: block {bid} in {held.get(bid, 0)} territories")
    return c


def check_fields(m: CityModel, n: _Net) -> Check:
    c = Check("gameplay_fields", "Wealth, danger and police fields: one raster each over the "
                                 "city bounds, every value between 0 and 1")
    kinds = {f.kind: f for f in m.fields}
    x0, y0, x1, y1 = m.bounds
    for k in ("wealth", "danger", "police"):
        f = kinds.get(k)
        if f is None:
            _limit(c, f"no {k} field")
            continue
        if f.nx * f.ny != len(f.values):
            _limit(c, f"{f.id}: {len(f.values)} values for {f.nx} x {f.ny} cells")
        if f.origin[0] > x0 + 1e-6 or f.origin[1] > y0 + 1e-6 or \
                f.origin[0] + f.nx * f.cell_m < x1 - 1e-6 or \
                f.origin[1] + f.ny * f.cell_m < y1 - 1e-6:
            _limit(c, f"{f.id}: does not cover the city bounds")
        bad = [v for v in f.values if not 0.0 <= v <= 1.0]
        if bad:
            _limit(c, f"{f.id}: {len(bad)} values out of 0 to 1")
    return c


def check_density(m: CityModel, n: _Net) -> Check:
    c = Check("street_density", "Street density: one row per road segment with every hour "
                                "band, nothing negative, traffic within the lanes' capacity, "
                                "no cars on pedestrian ways")
    by = {d.segment_id: d for d in m.densities}
    for s in m.road_segments:
        d = by.get(s.id)
        if d is None:
            _limit(c, f"{s.id}: no density row")
            continue
        cap = s.lanes * GP.LANE_CAP.get(s.road_class, 0.0)
        for name in ("traffic_vph", "vehicles_per_100m", "crowd_per_100m", "gang_per_100m",
                     "police_per_100m"):
            vals = getattr(d, name)
            if len(vals) != len(HOUR_BANDS) or min(vals) < 0:
                _limit(c, f"{d.id}: {name} {vals}")
        if max(d.traffic_vph) > cap + 0.01:
            _limit(c, f"{d.id}: traffic {max(d.traffic_vph)} over the capacity {cap:.0f}")
        if s.road_class in ("pedestrian", "footbridge") and (max(d.traffic_vph) > 0 or
                                                             d.speed_kmh > 0):
            _limit(c, f"{d.id}: cars on a {s.road_class}")
    if len(by) != len(m.densities):
        _limit(c, "density rows repeat a segment")
    return c


def check_parking(m: CityModel, n: _Net) -> Check:
    c = Check("parking", "Parking: every garage, lot and curb has capacity; garages in their "
                         "building, lots clear of buildings and carriageways, curb parking on "
                         "streets with parking lanes and drive lanes")
    bld = {b.id: b for b in m.buildings}
    foot, carr = [], []
    for b in m.buildings:
        if b.footprint is not None:
            foot.append(G.from_model_poly(b.footprint))
    for s in m.road_segments:
        if s.bridge or s.road_class in ("pedestrian", "footbridge") or s.level > 0:
            continue
        cs = s.cross_section
        half = (cs.total_width_m - cs.sidewalk_m[0] - cs.sidewalk_m[1]) / 2.0
        carr.append(LineString(s.centerline).buffer(max(half, 0.5), cap_style="flat"))
    ft = shapely.STRtree(foot) if foot else None
    ct = shapely.STRtree(carr) if carr else None
    lanes_of = {ln.segment_id for ln in m.lanes if ln.kind == "lane" and ln.id in n.scc}
    for p in m.parking:
        if p.capacity <= 0:
            _limit(c, f"{p.id}: capacity {p.capacity}")
        if p.kind == "garage":
            if p.building_id not in bld:
                _limit(c, f"{p.id}: building {p.building_id} missing")
            if not p.entrances:
                _limit(c, f"{p.id}: no entrance")
        elif p.kind == "lot":
            if p.polygon is None or not p.entrances:
                _limit(c, f"{p.id}: no polygon or entrance")
                continue
            poly = G.from_model_poly(p.polygon)
            for tree, geoms, what in ((ft, foot, "a building"), (ct, carr, "a carriageway")):
                if tree is None:
                    continue
                for i in sorted(tree.query(poly, predicate="intersects").tolist()):
                    a = G.area(G.inter(poly, G.snap(geoms[i])))
                    if a > 1.0:
                        _limit(c, f"{p.id}: overlaps {what} by {a:.1f} m2")
                        break
        else:
            s = n.seg.get(p.segment_id)
            if s is None or not any(s.cross_section.parking) or s.id not in lanes_of:
                _limit(c, f"{p.id}: segment {p.segment_id} has no parking lane or drive lane")
    return c


def check_travel(m: CityModel, n: _Net) -> Check:
    c = Check("travel_points", "Taxi stands and fast travel: a fast-travel point in every "
                               "district with streets, taxi stands at least 250 m apart, "
                               "every stand on its sidewalk")
    have = {t.district_id for t in m.travel_points if t.kind == "fast_travel"}
    streets = {s.district_ids[0] for s in m.road_segments if s.district_ids and
               s.road_class in GP.DRIVE_CLASSES}
    for d in m.districts:
        if d.id in streets and d.id not in have:
            _limit(c, f"{d.id} ({d.name}): no fast-travel point")
    taxis = [t for t in m.travel_points if t.kind == "taxi_stand"]
    for i, a in enumerate(taxis):
        for b in taxis[i + 1:]:
            if math.hypot(a.position[0] - b.position[0],
                          a.position[1] - b.position[1]) < GP.TAXI_GAP_M - 0.01:
                _limit(c, f"{a.id} and {b.id} closer than {GP.TAXI_GAP_M:.0f} m")
    for t in m.travel_points:
        w = n.walk.get(t.access.walkway_id)
        if w is None:
            continue  # reported by poi_reachable_foot
        d = G.dist(LineString([p[:2] for p in w.line]), Point(t.position))
        if d > TOL_M:
            _limit(c, f"{t.id}: {d:.2f} m off its walkway {w.id}")
    return c


def _box(s):
    """z interval of a slot."""
    return (s.position[2] - s.height_m / 2.0, s.position[2] + s.height_m / 2.0)


def check_slots(m: CityModel, n: _Net) -> Check:
    c = Check("sign_slots", "Sign and ad slots: one per M6 shop sign and M3 roof billboard, "
                            "facade slots on a facade of their building above the shop signs "
                            "and apart from each other, holo-ads over their roof")
    bld = {b.id: b for b in m.buildings}
    signs = {p.id for p in m.props if p.type == "prop.sign"}
    seen: dict[str, str] = {}
    sign_top = 0.0
    top_of: dict[str, float] = {}
    for s in m.sign_slots:
        if s.width_m <= 0 or s.height_m <= 0:
            _limit(c, f"{s.id}: size {s.width_m} x {s.height_m}")
        if s.kind == "shop_sign":
            if s.prop_id not in signs:
                _limit(c, f"{s.id}: sign prop {s.prop_id} missing")
            elif s.prop_id in seen:
                _limit(c, f"{s.id}: prop {s.prop_id} already has slot {seen[s.prop_id]}")
            else:
                seen[s.prop_id] = s.id
            sign_top = max(sign_top, s.position[2] + s.height_m / 2.0)
            if s.building_id is not None:
                top_of[s.building_id] = max(top_of.get(s.building_id, 0.0),
                                            s.position[2] + s.height_m / 2.0)
    missing = len(signs) - len(seen)
    if missing:
        _limit(c, f"{missing} sign props without a slot")
    by_b: dict[str, list] = {}
    for s in m.sign_slots:
        if s.kind == "shop_sign":
            continue
        b = bld.get(s.building_id)
        if b is None:
            _limit(c, f"{s.id}: building {s.building_id} missing")
            continue
        z0, z1 = _box(s)
        if s.mount == "roof" and s.roof_item is not None:
            if not 0 <= s.roof_item < len(b.roof_items) or \
                    b.roof_items[s.roof_item].kind != "billboard":
                _limit(c, f"{s.id}: roof item {s.roof_item} is not a billboard")
            continue
        if s.mount == "roof":
            top = max(ms.z1_m for ms in b.masses)
            inside = any(shapely.contains_xy(G.from_model_poly(ms.footprint), s.position[0],
                                             s.position[1]) and ms.z1_m >= top - 1e-6
                         for ms in b.masses)
            if not inside or z0 < top - 1e-6:
                _limit(c, f"{s.id}: not over the roof of {b.id}")
            continue
        on = False
        for ms in b.masses:
            if ms.z0_m > z0 + 1e-6 or ms.z1_m < z1 - 1e-6:
                continue
            if G.dist(G.from_model_poly(ms.footprint).exterior, Point(s.position[:2])) <= 0.3:
                on = True
                break
        if not on:
            _limit(c, f"{s.id}: not on a facade of {b.id} from {z0:.1f} to {z1:.1f} m")
        if z0 < max(8.0, top_of.get(b.id, 0.0)) - 1e-6:
            _limit(c, f"{s.id}: starts at {z0:.1f} m, among the shop signs")
        by_b.setdefault(b.id, []).append(s)
    for bid, ss in by_b.items():
        for i, a in enumerate(ss):
            for b_ in ss[i + 1:]:
                turn = abs(((a.yaw_deg - b_.yaw_deg) + 180.0) % 360.0 - 180.0)
                if turn > 10.0:
                    continue  # another facade
                za, zb = _box(a), _box(b_)
                if za[1] <= zb[0] or zb[1] <= za[0]:
                    continue
                gap = math.hypot(a.position[0] - b_.position[0], a.position[1] - b_.position[1])
                if gap < (a.width_m + b_.width_m) / 2.0:
                    _limit(c, f"{a.id} and {b_.id} overlap on the same facade")
    c.notes.append(f"shop signs reach {sign_top:.1f} m")
    return c


def run(spec, m: CityModel) -> list:
    if not (m.pois or m.zones or m.fields or m.densities):
        return []
    with G.canonical():
        n = _Net(m)
        return [check_reach_foot(m, n), check_reach_car(m, n), check_pois(m, n),
                check_zones(m, n), check_fields(m, n), check_density(m, n),
                check_parking(m, n), check_travel(m, n), check_slots(m, n)]


def stats(m: CityModel) -> dict:
    def count(rows, key):
        out: dict = {}
        for r in rows:
            k = key(r)
            out[k] = out.get(k, 0) + 1
        return dict(sorted(out.items(), key=lambda kv: (-kv[1], kv[0])))

    fac = count(m.factions, lambda f: f.kind)
    return {
        "pois": len(m.pois), "pois_by_kind": count(m.pois, lambda p: f"{p.kind}.{p.sub}"),
        "factions": len(m.factions), "factions_by_kind": fac,
        "territories": sum(1 for z in m.zones if z.kind == "territory"),
        "contested": sum(1 for z in m.zones if z.attrs.get("contested")),
        "parking": count(m.parking, lambda p: p.kind),
        "parking_capacity": sum(p.capacity for p in m.parking),
        "taxi_stands": sum(1 for t in m.travel_points if t.kind == "taxi_stand"),
        "fast_travel": sum(1 for t in m.travel_points if t.kind == "fast_travel"),
        "sign_slots": count(m.sign_slots, lambda s: f"{s.kind}.{s.mount}"),
        "density_rows": len(m.densities),
        "peak_traffic_vph": max((max(d.traffic_vph) for d in m.densities), default=0.0),
        "peak_crowd_per_100m": max((max(d.crowd_per_100m) for d in m.densities),
                                   default=0.0),
    }
