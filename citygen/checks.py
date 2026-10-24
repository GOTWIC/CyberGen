"""Checks and stats for a built city (scope section 9: water, district and primary road parts).

Every check reads only the city model and the filled spec, so a model can be loaded from JSON
and re-checked, and tests can break a model on purpose. A failed check means the city is not
delivered (`citygen build` exits non-zero).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import shapely
from shapely.geometry import LineString
from shapely.ops import unary_union

from . import geom as G
from . import relations as R
from .model import CityModel
from .spec import BoundaryKind, CitySpec

SHARE_TOL = 0.15          # district area share, relative
ISLAND_TOL = 0.10         # island area, relative
MIN_WIDTH_M = 40.0        # land narrower than this is a sliver
SLIVER_AREA_M2 = 2000.0   # a removed piece this large counts as a sliver
LAND_KINDS = ("highway", "ring_road", "rail", "wall")
CANAL_MIN_ANGLE_DEG = 30.0  # canals and creeks never cross or join at a shallower angle
CANAL_DUP_GAP_M = 35.0      # two canals closer than this ...
CANAL_DUP_LEN_M = 100.0     # ... over this length (junctions aside) are near duplicates
# Primary roads (M1b).
ROAD_MIN_RADIUS_M = {"highway": 150.0, "avenue": 40.0}
ROAD_MIN_SEGMENT_M = {"highway": 60.0, "avenue": 40.0}
RADIUS_BASE_M = {"highway": 20.0, "avenue": 10.0}   # chord used to measure curvature
# The stretch next to a junction is junction geometry, not alignment: M2 builds avenue
# junctions; at-grade highway junctions become interchanges in M7.
JUNCTION_SKIP_M = {"highway": 60.0, "avenue": 25.0}
ROAD_DUP_GAP_M = 25.0       # two roads closer than this ...
ROAD_DUP_LEN_M = 150.0      # ... over this length (60 m around shared points aside)
SERVED_M = 50.0             # an avenue runs at least this long along (within 25 m of) a district
WATER_CLASS_OF = {"sea": "sea", "sea_channel": "sea", "basin": "sea", "river": "river",
                  "delta_branch": "river", "separation": "canal", "canal": "canal",
                  "creek": "canal", "inlet": "canal", "marina": "canal"}
CLEARANCE_RANGE_M = {"sea": (25.0, 80.0), "river": (10.0, 15.0), "canal": (3.0, 4.0)}


@dataclass
class Check:
    id: str
    title: str
    failures: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return not self.failures

    def to_dict(self) -> dict:
        return {"id": self.id, "title": self.title, "passed": self.passed,
                "failures": self.failures, "notes": self.notes}


class _Geo:
    """Shapely views of the model, built once."""

    def __init__(self, m: CityModel):
        def P(poly):  # repaired view; check_geometry reports the raw polygons
            shp = G.from_model_poly(poly)
            return shp if shp.is_valid else G.polygonal(shapely.make_valid(shp))

        self.m = m
        self.canvas = shapely.box(*m.bounds)
        self.sea = unary_union([P(p) for s in m.seas for p in s.polygons])
        self.land = unary_union([P(p) for x in m.land for p in x.polygons])
        self.districts = {d.name: P(d.polygon) for d in m.districts}
        self.district_by_id = {d.id: d for d in m.districts}
        self.landmasses = {lm.id: P(lm.polygon) for lm in m.landmasses}
        self.islands = {i.name: P(i.polygon) for i in m.islands}
        self.rivers = {r.id: P(r.polygon) for r in m.rivers}
        self.channels = {c.id: P(c.polygon) for c in m.channels}
        self.waterways = {w.id: P(w.polygon) for w in m.waterways}
        self.network = unary_union([self.sea, *self.rivers.values(), *self.channels.values()])
        self.coastal = unary_union([self.sea] + [self.channels[c.id] for c in m.channels
                                                 if c.kind == "sea_channel"])
        # Water by navigable class (bridges), and road geometry.
        cls_geoms: dict[str, list] = {"sea": [self.sea], "river": [], "canal": []}
        for r in m.rivers:
            cls_geoms["river"].append(self.rivers[r.id])
        for c in m.channels:
            cls_geoms[WATER_CLASS_OF[c.kind]].append(self.channels[c.id])
        for w in m.waterways:
            cls_geoms[WATER_CLASS_OF[w.kind]].append(self.waterways[w.id])
        self.water_by_class = {k: unary_union(v) for k, v in cls_geoms.items()}
        self.all_water = unary_union(list(self.water_by_class.values()))
        self.roads = {s.id: LineString(s.centerline) for s in m.road_segments}

    def named_water(self, name: str):
        ids = [r.id for r in self.m.rivers if r.name == name]
        ids += [c.id for c in self.m.channels if c.name == name and c.kind == "sea_channel"]
        ids += [c.id for c in self.m.channels if c.river_id in ids]
        geoms = [self.rivers.get(i) or self.channels.get(i) for i in ids]
        return unary_union([g for g in geoms if g is not None]) if geoms else None

    def kind_water(self, kind: str):
        m = self.m
        if kind == "sea":
            return self.sea
        if kind == "river":
            return unary_union(list(self.rivers.values()) + [
                self.channels[c.id] for c in m.channels if c.kind == "delta_branch"])
        if kind == "channel":
            return unary_union([self.channels[c.id] for c in m.channels])
        if kind == "canal":
            return unary_union([self.channels[c.id] for c in m.channels if c.kind == "separation"]
                               + [self.waterways[w.id] for w in m.waterways if w.kind == "canal"])
        return self.network


# ---------------------------------------------------------------------------
# Individual checks
# ---------------------------------------------------------------------------

def check_geometry(m: CityModel, g: _Geo) -> Check:
    c = Check("geometry_valid", "All geometry valid (shapely is_valid), non-empty")
    groups = [("land", [(x.id, p) for x in m.land for p in x.polygons]),
              ("landmass", [(x.id, x.polygon) for x in m.landmasses]),
              ("island", [(x.id, x.polygon) for x in m.islands]),
              ("sea", [(x.id, p) for x in m.seas for p in x.polygons]),
              ("river", [(x.id, x.polygon) for x in m.rivers]),
              ("channel", [(x.id, x.polygon) for x in m.channels]),
              ("waterway", [(x.id, x.polygon) for x in m.waterways]),
              ("district", [(x.id, x.polygon) for x in m.districts])]
    for kind, items in groups:
        for ident, poly in items:
            shp = G.from_model_poly(poly)
            if shp.is_empty or shp.area <= 0:
                c.failures.append(f"{kind} {ident}: empty polygon")
            elif not shp.is_valid:
                c.failures.append(f"{kind} {ident}: invalid ({shapely.is_valid_reason(shp)})")
    for q in m.quays:
        if LineString(q.line).length <= 0:
            c.failures.append(f"quay {q.id}: zero length")
    # Districts must not overlap each other or the water network.
    names = sorted(g.districts)
    tree = shapely.STRtree([g.districts[n] for n in names])
    for i, n in enumerate(names):
        for j in tree.query(g.districts[n]):
            if j <= i:
                continue
            ov = g.districts[n].intersection(g.districts[names[j]]).area
            if ov > 1.0:
                c.failures.append(f"districts '{n}' and '{names[j]}' overlap by {ov:.0f} m2")
        wet = g.districts[n].intersection(g.network).area
        if wet > 50.0:
            c.failures.append(f"district '{n}' covers {wet:.0f} m2 of sea, river or channel")
    return c


def check_waterways(m: CityModel, g: _Geo) -> Check:
    c = Check("waterways_connected",
              "Every waterway connects to a river, channel or the sea (declared basins aside)")
    ids = sorted(g.waterways)
    connected = {i for i in ids if g.waterways[i].distance(g.network) <= 1.0}
    changed = True
    while changed:
        changed = False
        for i in ids:
            if i in connected:
                continue
            if any(g.waterways[i].distance(g.waterways[j]) <= 1.0 for j in connected):
                connected.add(i)
                changed = True
    for w in m.waterways:
        if w.ornamental:
            continue
        if w.id not in connected:
            c.failures.append(f"waterway {w.id} ({w.kind} in "
                              f"{g.district_by_id[w.district_id].name}) is not connected")
    for ch in m.channels:
        if ch.kind == "separation" and g.channels[ch.id].distance(
                unary_union([g.sea, *g.rivers.values(), *[
                    g.channels[x.id] for x in m.channels if x.id != ch.id]])) > 1.0:
            c.failures.append(f"separation channel {ch.id} is not connected")
    return c


def district_areas(m: CityModel, g: _Geo) -> dict[str, float]:
    return {n: G.area(p) for n, p in g.districts.items()}


def check_shares(m: CityModel, g: _Geo) -> Check:
    c = Check("district_shares", f"District area shares within {SHARE_TOL:.0%} of the spec")
    areas = district_areas(m, g)
    total = math.fsum(areas.values()) or 1.0
    for d in m.districts:
        target = d.attrs.get("area_share_target")
        if not target:
            continue
        actual = areas[d.name] / total
        err = (actual - target) / target
        if abs(err) > SHARE_TOL + 1e-9:
            src = d.attrs.get("area_share_source", "spec")
            c.failures.append(f"'{d.name}': share {actual:.3f} vs {target:.3f} ({src}), "
                              f"{err:+.0%}")
    return c


def _ref_geom(spec: CitySpec, g: _Geo, ref: str):
    from .districts import resolve

    hit = resolve(spec, ref)
    if hit is None:
        return None, None
    if hit[0] == "island":
        return g.islands.get(hit[1]), hit[1]
    return g.districts.get(hit[1]), hit[1]


def check_placement(spec: CitySpec, m: CityModel, g: _Geo) -> Check:
    c = Check("placement", "Placement relations (direction by centroid, edge, coast, "
                           "on_island, along_river, adjacent_to, separated_by)")
    for d in spec.districts:
        poly = g.districts.get(d.name)
        if poly is None:
            c.failures.append(f"'{d.name}': district was not built")
            continue
        pl = d.placement
        cen = poly.centroid
        for direction, ref in pl.relations():
            other, oname = _ref_geom(spec, g, ref)
            if other is None or oname == d.name:
                continue
            oc = other.centroid
            if not R.direction_ok((cen.x, cen.y), (oc.x, oc.y), direction):
                ang = math.degrees(math.atan2(cen.y - oc.y, cen.x - oc.x))
                c.failures.append(f"'{d.name}' is not {direction}_of '{ref}' "
                                  f"(bearing {(90 - ang) % 360:.0f} deg)")
        if pl.edge and not R.edge_ok(poly, g.canvas, pl.edge, g.land):
            c.failures.append(f"'{d.name}' is not at edge '{pl.edge}'")
        if pl.coast is True and not R.touches(poly, g.coastal):
            c.failures.append(f"'{d.name}' should be on the coast")
        if pl.coast is False and R.touches(poly, g.coastal):
            c.failures.append(f"'{d.name}' should be inland")
        if pl.on_island:
            isl = g.islands.get(pl.on_island)
            if isl is None or poly.intersection(isl).area < 0.95 * poly.area:
                c.failures.append(f"'{d.name}' is not on island '{pl.on_island}'")
        if pl.along_river:
            wat = g.named_water(pl.along_river)
            if wat is None or not R.touches(poly, wat):
                c.failures.append(f"'{d.name}' is not along river '{pl.along_river}'")
        for ref in pl.adjacent_to:
            other, oname = _ref_geom(spec, g, ref)
            if other is not None and oname != d.name and \
                    poly.distance(other) > R.ADJACENT_M:
                c.failures.append(f"'{d.name}' is not adjacent to '{ref}'")
        sep = pl.separated_by
        if sep in ("highway", "ring_road") and m.road_segments:
            if _road_along(m, g, poly, sep) < 200.0:
                c.failures.append(f"'{d.name}' is not bordered by a {sep.replace('_', ' ')} "
                                  "(separated_by)")
        elif sep and sep in LAND_KINDS:
            later = {"rail": "transit (M5)", "wall": "walls (M3)"}.get(sep, "roads")
            c.notes.append(f"'{d.name}': separated_by '{sep}' is checked once {later} exist")
        elif sep:
            wat = g.kind_water(sep) if sep in BoundaryKind.__args__ else g.named_water(sep)
            if wat is None or not R.touches(poly, wat):
                c.failures.append(f"'{d.name}' does not border '{sep}' (separated_by)")
            if sep == "water" and _land_neighbors(m, g, d.name):
                c.failures.append(f"'{d.name}' shares land with "
                                  f"{', '.join(_land_neighbors(m, g, d.name))} "
                                  "(separated_by water)")
    return c


def _road_along(m: CityModel, g: _Geo, poly, kind: str) -> float:
    """Length of highway (or ring road) running within 60 m of a district's boundary."""
    if kind == "highway":
        segs = [s for s in m.road_segments if s.road_class == "highway"]
    else:
        segs = [s for s in m.road_segments if s.attrs.get("role") in ("ring", "ring_road")]
    if not segs:
        return 0.0
    edge = poly.boundary.buffer(60.0)
    return sum(LineString(s.centerline).intersection(edge).length for s in segs)


def _land_neighbors(m: CityModel, g: _Geo, name: str) -> list[str]:
    me = next(d for d in m.districts if d.name == name)
    return sorted(d.name for d in m.districts
                  if d.name != name and d.landmass_id == me.landmass_id)


def check_separation(spec: CitySpec, m: CityModel, g: _Geo) -> Check:
    c = Check("water_required", "water_required districts share no land with another district")
    for d in spec.districts:
        mode = d.water_separation or spec.water.district_separation
        if mode != "water_required" or d.name not in g.districts:
            continue
        others = _land_neighbors(m, g, d.name)
        if others:
            c.failures.append(f"'{d.name}' shares landmass with {', '.join(others)}")
    return c


def check_pieces(spec: CitySpec, m: CityModel, g: _Geo) -> Check:
    c = Check("district_pieces", "Every district is one piece on one landmass")
    for d in m.districts:
        poly = g.districts[d.name]
        lm = g.landmasses.get(d.landmass_id) if d.landmass_id else None
        if lm is None:
            c.failures.append(f"'{d.name}' has no landmass")
            continue
        outside = poly.area - poly.intersection(lm).area
        if outside > 1.0:
            c.failures.append(f"'{d.name}' reaches {outside:.0f} m2 beyond landmass "
                              f"{d.landmass_id}")
    return c


def check_islands(spec: CitySpec, m: CityModel, g: _Geo) -> Check:
    c = Check("island_sizes", f"Every island built, area within {ISLAND_TOL:.0%} of the spec")
    for isl in spec.water.islands:
        poly = g.islands.get(isl.name)
        if poly is None:
            c.failures.append(f"island '{isl.name}' was not built")
            continue
        want = isl.area_km2 * 1e6
        err = (poly.area - want) / want
        if abs(err) > ISLAND_TOL + 1e-9:
            c.failures.append(f"island '{isl.name}': {poly.area / 1e6:.3f} km2 vs "
                              f"{isl.area_km2:g} km2 ({err:+.0%})")
    return c


def check_land_use(spec: CitySpec, m: CityModel, g: _Geo) -> Check:
    c = Check("land_use", "Every landmass holds a district or is named open land (marsh, park); "
                          "no orphan wedges")
    if spec.districts and all(d.placement.on_island for d in spec.districts):
        c.notes.append("every district is on its own island; the rest of the land is outside "
                       "the city")
        return c
    fillers = {i.landmass_id for i in m.islands if i.type == "island.filler"}
    open_lm = {o.attrs.get("landmass_id") for o in m.open_spaces}
    for lm in m.landmasses:
        if lm.district_ids or lm.id in fillers:
            continue
        if lm.id in open_lm:
            o = next(x for x in m.open_spaces if x.attrs.get("landmass_id") == lm.id)
            c.notes.append(f"landmass {lm.id} ({g.landmasses[lm.id].area / 1e6:.2f} km2) is "
                           f"open land: {o.kind} '{o.name}'")
            continue
        c.failures.append(f"landmass {lm.id} ({g.landmasses[lm.id].area / 1e6:.2f} km2) has no "
                          "district and is not open land")
    return c


def _tangent_at(line: LineString, p) -> tuple[float, float]:
    d = line.project(p)
    a = line.interpolate(max(d - 15.0, 0.0))
    b = line.interpolate(min(d + 15.0, line.length))
    return b.x - a.x, b.y - a.y


def meet_angle(a: LineString, b: LineString, p) -> float:
    """Acute angle (degrees) between two lines at a point where they meet."""
    ux, uy = _tangent_at(a, p)
    vx, vy = _tangent_at(b, p)
    nu, nv = math.hypot(ux, uy), math.hypot(vx, vy)
    if nu < 1e-6 or nv < 1e-6:
        return 90.0
    cos = min(abs(ux * vx + uy * vy) / (nu * nv), 1.0)
    return math.degrees(math.acos(cos))


def canal_problems(m: CityModel) -> list[str]:
    """Canals and creeks that cross or join at less than 30 degrees, or run within 35 m of
    each other for more than 100 m away from their junctions (near duplicates)."""
    lines = [(w.id, LineString(w.centerline)) for w in m.waterways
             if w.kind in ("canal", "creek") and len(w.centerline) > 1]
    out = []
    for i, (ia, a) in enumerate(lines):
        for ib, b in lines[i + 1:]:
            if a.distance(b) > CANAL_DUP_GAP_M:
                continue
            meet = a.intersection(b.buffer(3.0))
            pts = []
            for part in getattr(meet, "geoms", [meet]):
                if part.is_empty:
                    continue
                pts.append(part.interpolate(0.5, normalized=True) if part.length > 0
                           else part.centroid)
            for p in pts:
                ang = meet_angle(a, b, p)
                if ang < CANAL_MIN_ANGLE_DEG:
                    out.append(f"{ia} and {ib} meet at {ang:.0f} deg near "
                               f"({p.x:.0f}, {p.y:.0f})")
            near = a.intersection(b.buffer(CANAL_DUP_GAP_M))
            if pts:
                near = near.difference(unary_union([p.buffer(60.0) for p in pts]))
            if near.length > CANAL_DUP_LEN_M:
                out.append(f"{ia} and {ib} run within {CANAL_DUP_GAP_M:.0f} m of each other "
                           f"for {near.length:.0f} m")
    return out


def check_canals(m: CityModel, g: _Geo) -> Check:
    c = Check("canal_quality", f"Canals and creeks: no crossings below "
                               f"{CANAL_MIN_ANGLE_DEG:.0f} deg, no near-duplicate canals")
    c.failures += canal_problems(m)
    return c


def slivers(poly, min_width: float = MIN_WIDTH_M) -> list[float]:
    removed = poly.difference(G.opening(poly, min_width / 2))
    return [p.area for p in G.parts(removed) if p.area >= SLIVER_AREA_M2]


def check_slivers(m: CityModel, g: _Geo) -> Check:
    c = Check("no_slivers", f"No land narrower than {MIN_WIDTH_M:.0f} m (districts, landmasses)")
    for ident, poly in sorted(g.landmasses.items()):
        for a in slivers(poly):
            c.failures.append(f"landmass {ident}: sliver of {a:.0f} m2")
    for name, poly in sorted(g.districts.items()):
        for a in slivers(poly):
            c.failures.append(f"district '{name}': sliver of {a:.0f} m2")
    return c


# ---------------------------------------------------------------------------
# Primary roads (M1b)
# ---------------------------------------------------------------------------

def _road_components(m: CityModel) -> list[set[str]]:
    parent = {n.id: n.id for n in m.road_nodes}

    def find(a):
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a

    for s in m.road_segments:
        if s.start in parent and s.end in parent:
            parent[find(s.start)] = find(s.end)
    comps: dict[str, set[str]] = {}
    for n in m.road_nodes:
        comps.setdefault(find(n.id), set()).add(n.id)
    return sorted(comps.values(), key=lambda c: (-len(c), sorted(c)[0]))


def _segment_landmasses(m: CityModel, g: _Geo) -> dict[str, set[str]]:
    if getattr(g, "_seg_lm", None) is not None:
        return g._seg_lm
    import numpy as np

    ids = [s.id for s in m.road_segments]
    lines = np.array([g.roads[i] for i in ids], dtype=object)
    out: dict[str, set[str]] = {i: set() for i in ids}
    if len(lines):
        tree = shapely.STRtree(lines)
        for lid, lm in g.landmasses.items():
            zone = lm.buffer(2.0)
            hit = np.array(sorted(int(k) for k in tree.query(zone)), dtype=int)
            if not len(hit):
                continue
            lens = shapely.length(shapely.intersection(lines[hit], zone))
            for k, L in zip(hit.tolist(), lens.tolist()):
                if L > 5.0:
                    out[ids[k]].add(lid)
    g._seg_lm = out
    return out


def check_road_graph(spec: CitySpec, m: CityModel, g: _Geo) -> Check:
    c = Check("road_graph", "Road graph connected: one component reaching every landmass with "
                            "a district (islands by bridge or causeway), every exit built")
    ids = {n.id for n in m.road_nodes}
    for s in m.road_segments:
        for end in (s.start, s.end):
            if end not in ids:
                c.failures.append(f"segment {s.id}: unknown node {end}")
    comps = _road_components(m)
    if not m.road_segments:
        c.failures.append("no roads")
        return c
    if len(comps) > 1:
        c.failures.append(f"{len(comps)} road components (sizes "
                          f"{', '.join(str(len(x)) for x in comps)})")
    main = comps[0]
    seg_lm = _segment_landmasses(m, g)
    reached: set[str] = set()
    for s in m.road_segments:
        if s.start in main:
            reached |= seg_lm[s.id]
    for lm in m.landmasses:
        if lm.district_ids and lm.id not in reached:
            names = ", ".join(g.district_by_id[d].name for d in lm.district_ids)
            c.failures.append(f"landmass {lm.id} ({names}) is not reached by the road network")
    exits = {n.attrs.get("exit") for n in m.road_nodes if n.attrs.get("kind") == "exit"}
    for d in spec.highways.exits or []:
        if f"{d}_exit" not in exits:
            c.failures.append(f"exit '{d}' was not built")
    unconnected = [lm.id for lm in m.landmasses if not lm.district_ids and lm.id not in reached]
    if unconnected:
        c.notes.append(f"land without a district left without roads: {', '.join(unconnected)}")
    return c


def check_districts_served(m: CityModel, g: _Geo) -> Check:
    c = Check("districts_served", f"Every district is touched by an avenue (at least "
                                  f"{SERVED_M:.0f} m within 25 m of it)")
    avenues = unary_union([g.roads[s.id] for s in m.road_segments if s.road_class == "avenue"])
    for d in m.districts:
        poly = g.districts[d.name]
        if avenues.is_empty or avenues.intersection(poly.buffer(25.0)).length < SERVED_M:
            c.failures.append(f"'{d.name}' is not served by an avenue")
    return c


def check_named_bridges(spec: CitySpec, m: CityModel, g: _Geo) -> Check:
    c = Check("named_bridges", "Every named bridge is built")
    built = {b.name for b in m.bridges if b.name}
    for nb in spec.water.bridges.named:
        if nb.name not in built:
            c.failures.append(f"named bridge '{nb.name}' ({nb.kind}, "
                              f"{' to '.join(nb.connects)}) was not built")
    return c


def bridge_water_class(g: _Geo, line: LineString) -> str | None:
    """Highest navigable class of the water a line crosses (more than 0.5 m)."""
    for cls in ("sea", "river", "canal"):
        geom = g.water_by_class[cls]
        if not geom.is_empty and line.intersection(geom).length > 0.5:
            return cls
    return None


def check_bridges(m: CityModel, g: _Geo) -> Check:
    c = Check("bridge_clearance", "Every bridge has the clearance of the water it crosses (sea "
                                  "channel and port approach 25 m+, river 10 to 15 m, canal 3 "
                                  "to 4 m), every road over water is a bridge, no junction on "
                                  "a bridge")
    spans: dict[str, float] = {}
    for b in m.bridges:
        line = LineString([(x, y) for x, y, _ in b.line])
        cls = bridge_water_class(g, line)
        if cls is None:
            c.failures.append(f"bridge {b.id} crosses no water")
            continue
        if b.water_class != cls:
            c.failures.append(f"bridge {b.id}: class {b.water_class} but crosses {cls} water")
        lo, hi = CLEARANCE_RANGE_M[cls]
        if not lo - 1e-6 <= b.clearance_m <= hi + 1e-6:
            c.failures.append(f"bridge {b.id}: clearance {b.clearance_m:g} m over {cls} water "
                              f"(needs {lo:g} to {hi:g} m)")
        want = (b.clearance_m + 1.5) / 0.06
        if b.ramp_length_m is not None and abs(b.ramp_length_m - want) > 0.05:
            c.failures.append(f"bridge {b.id}: ramp {b.ramp_length_m} m, expected {want:.2f} m")
        for sid in b.segment_ids:
            spans[sid] = spans.get(sid, 0.0) + line.length
    deg: dict[str, int] = {}
    for s in m.road_segments:
        deg[s.start] = deg.get(s.start, 0) + 1
        deg[s.end] = deg.get(s.end, 0) + 1
    inner = g.all_water.buffer(-3.0)
    for n in m.road_nodes:
        if deg.get(n.id, 0) >= 3 and inner.contains(shapely.Point(n.position[:2])):
            c.failures.append(f"junction {n.id} is out on the water (on a bridge)")
    for s in m.road_segments:
        wet = g.roads[s.id].intersection(g.all_water).length
        if wet - spans.get(s.id, 0.0) > 3.0:
            c.failures.append(f"segment {s.id} runs {wet - spans.get(s.id, 0.0):.0f} m over "
                              "water without a bridge")
    return c


def check_road_avoidance(m: CityModel, g: _Geo) -> Check:
    c = Check("road_avoidance", "No road through megasite reserves or spaceport flight cones, "
                                "nor through marsh or park open land (declared causeways aside)")
    zones = [(f"megasite '{s.name}'", G.from_model_poly(s.polygon)) for s in m.megasites]
    zones += [(f"flight cone of '{s.name}'", G.from_model_poly(s.flight_cone))
              for s in m.megasites if s.flight_cone is not None]
    opens = [(f"{o.kind} '{o.name}'", G.from_model_poly(o.polygon)) for o in m.open_spaces
             if o.kind in ("marsh", "park")]
    for s in m.road_segments:
        line = g.roads[s.id]
        for label, poly in zones:
            inside = line.intersection(poly).length
            if inside > 1.0:
                c.failures.append(f"segment {s.id} ({s.road_class}) runs {inside:.0f} m through "
                                  f"{label}")
        if s.attrs.get("causeway"):
            continue
        for label, poly in opens:
            inside = line.intersection(poly).length
            if inside > 1.0:
                c.failures.append(f"segment {s.id} ({s.road_class}) runs {inside:.0f} m through "
                                  f"{label}")
    return c


def min_radius(line: LineString, base: float, skip0: float = 0.0, skip1: float = 0.0
               ) -> tuple[float, float]:
    """Smallest circumradius of points `base` apart along a line (and where), ignoring the
    first `skip0` and last `skip1` meters."""
    import numpy as np

    L = line.length
    n = int(L // base)
    if n < 2:
        return math.inf, 0.0
    ds = np.arange(n + 1) * base
    xy = np.array([line.interpolate(d).coords[0] for d in ds])
    a, b, cc = xy[:-2], xy[1:-1], xy[2:]
    ab = np.sqrt(((b - a) ** 2).sum(axis=1))
    bc = np.sqrt(((cc - b) ** 2).sum(axis=1))
    ca = np.sqrt(((a - cc) ** 2).sum(axis=1))
    cross = np.abs((b[:, 0] - a[:, 0]) * (cc[:, 1] - a[:, 1])
                   - (b[:, 1] - a[:, 1]) * (cc[:, 0] - a[:, 0]))
    with np.errstate(divide="ignore", invalid="ignore"):
        r = np.where(cross > 1e-9, ab * bc * ca / (2 * cross), np.inf)
    mid = ds[1:-1]
    keep = (mid >= skip0 + base) & (mid <= L - skip1 - base)
    if not keep.any():
        return math.inf, 0.0
    r = np.where(keep, r, np.inf)
    k = int(np.argmin(r))
    return float(r[k]), float(mid[k])


def primary_chains(m: CityModel, g: _Geo) -> list[tuple[str, str, LineString, str, str]]:
    """Primary roads as M1b laid them: (label, class, line, start node, end node). M2 splits a
    primary segment wherever a local street joins it; the pieces of one M1b segment (attrs
    `m1b_segment`) are joined back here, so alignment checks see the primary road itself."""
    groups: dict[str, list] = {}
    for s in m.road_segments:
        if s.road_class not in ROAD_MIN_RADIUS_M:
            continue
        groups.setdefault(s.attrs.get("m1b_segment", s.id), []).append(s)
    out = []
    for key in sorted(groups):
        segs = groups[key]
        if len(segs) == 1:
            s = segs[0]
            out.append((s.id, s.road_class, g.roads[s.id], s.start, s.end))
            continue
        by_start = {s.start: s for s in segs}
        ends = {s.end for s in segs}
        first = next((s for s in segs if s.start not in ends), segs[0])
        chain, coords, cur = [first], list(first.centerline), first
        while cur.end in by_start and len(chain) < len(segs):
            cur = by_start[cur.end]
            chain.append(cur)
            coords += list(cur.centerline)[1:]
        if len(chain) != len(segs):  # not one chain: check the pieces one by one
            out += [(s.id, s.road_class, g.roads[s.id], s.start, s.end) for s in segs]
            continue
        out.append((f"{chain[0].id}..{chain[-1].id}", first.road_class, LineString(coords),
                    chain[0].start, chain[-1].end))
    return out


def check_curve_radius(m: CityModel, g: _Geo) -> Check:
    c = Check("curve_radius", "Minimum curve radius per class (highway "
                              f"{ROAD_MIN_RADIUS_M['highway']:.0f} m, avenue "
                              f"{ROAD_MIN_RADIUS_M['avenue']:.0f} m), outside junction areas "
                              f"({JUNCTION_SKIP_M['avenue']:.0f} m from an avenue junction, M2; "
                              f"{JUNCTION_SKIP_M['highway']:.0f} m from a highway junction, "
                              "an interchange in M7)")
    deg: dict[str, int] = {}
    for s in m.road_segments:
        if s.road_class in ROAD_MIN_RADIUS_M:
            deg[s.start] = deg.get(s.start, 0) + 1
            deg[s.end] = deg.get(s.end, 0) + 1
    for label, cls, line, a, b in primary_chains(m, g):
        rmin = ROAD_MIN_RADIUS_M[cls]
        skip = JUNCTION_SKIP_M[cls]
        skip0 = skip if deg.get(a, 0) >= 3 else 0.0
        skip1 = skip if deg.get(b, 0) >= 3 else 0.0
        r, at = min_radius(line, RADIUS_BASE_M[cls], skip0, skip1)
        if r < 0.95 * rmin:
            p = line.interpolate(at)
            c.failures.append(f"segment {label} ({cls}): radius {r:.0f} m near "
                              f"({p.x:.0f}, {p.y:.0f}), minimum {rmin:.0f} m")
    return c


def check_segment_length(m: CityModel, g: _Geo) -> Check:
    c = Check("segment_length", "No highway segment under "
                                f"{ROAD_MIN_SEGMENT_M['highway']:.0f} m, no avenue segment under "
                                f"{ROAD_MIN_SEGMENT_M['avenue']:.0f} m (a stretch that leaves "
                                "the map is cut by the map border and not counted)")
    off_map = {n.id for n in m.road_nodes if n.attrs.get("kind") in ("exit", "edge")}
    for label, cls, line, a, b in primary_chains(m, g):
        if a in off_map or b in off_map:
            continue
        lmin = ROAD_MIN_SEGMENT_M[cls]
        if line.length < lmin - 1e-6:
            c.failures.append(f"segment {label} ({cls}) is {line.length:.0f} m long")
    return c


def road_duplicates(m: CityModel, g: _Geo) -> list[str]:
    """Primary roads only (local roads: `street_duplicates`)."""
    ids = [s.id for s in m.road_segments if s.road_class in ROAD_MIN_RADIUS_M]
    lines = [g.roads[i] for i in ids]
    if not lines:
        return []
    tree = shapely.STRtree(lines)
    out = []
    for i, a in enumerate(lines):
        for j in sorted(int(x) for x in tree.query(a.buffer(ROAD_DUP_GAP_M))):
            if j <= i:
                continue
            b = lines[j]
            near = a.intersection(b.buffer(ROAD_DUP_GAP_M))
            if near.length <= ROAD_DUP_LEN_M:
                continue
            meet = a.intersection(b)
            shared = [p for p in (a.coords[0], a.coords[-1]) if b.distance(shapely.Point(p)) < 1.0]
            shared += [p for p in (b.coords[0], b.coords[-1]) if a.distance(shapely.Point(p)) < 1.0]
            spots = [shapely.Point(p) for p in shared]
            if not meet.is_empty:
                spots.append(meet)
            if spots:
                near = near.difference(unary_union([p.buffer(60.0) for p in spots]))
            if near.length > ROAD_DUP_LEN_M:
                out.append(f"segments {ids[i]} and {ids[j]} run within {ROAD_DUP_GAP_M:.0f} m "
                           f"of each other for {near.length:.0f} m")
    return out


def check_road_duplicates(m: CityModel, g: _Geo) -> Check:
    c = Check("road_duplicates", f"No near-parallel duplicate roads (within "
                                 f"{ROAD_DUP_GAP_M:.0f} m for over {ROAD_DUP_LEN_M:.0f} m)")
    c.failures += road_duplicates(m, g)
    return c


def road_stats(spec: CitySpec, m: CityModel, g: _Geo) -> dict:
    km: dict[str, float] = {}
    for s in m.road_segments:
        km[s.road_class] = km.get(s.road_class, 0.0) + g.roads[s.id].length / 1000
    by_cls = {"sea": 0, "river": 0, "canal": 0}
    for b in m.bridges:
        if b.bridge_class != "pedestrian" and b.water_class:
            by_cls[b.water_class] += 1
    with_d = [lm.id for lm in m.landmasses if lm.district_ids]
    comps = _road_components(m)
    seg_lm = _segment_landmasses(m, g)
    reached: set[str] = set()
    if comps:
        for s in m.road_segments:
            if s.start in comps[0]:
                reached |= seg_lm[s.id]
    hw = [s for s in m.road_segments if s.road_class == "highway"]
    hw_len = sum(g.roads[s.id].length for s in hw)
    elev = sum(g.roads[s.id].length for s in hw if s.attrs.get("elevated"))
    return {
        "road_km": {k: round(v, 2) for k, v in sorted(km.items())},
        "road_nodes": len(m.road_nodes),
        "road_segments": len(m.road_segments),
        "road_components": len(comps),
        "bridges": sum(by_cls.values()),
        "bridges_by_class": by_cls,
        "bridge_span_km": round(sum(b.span_m or 0.0 for b in m.bridges
                                    if b.bridge_class != "pedestrian") / 1000, 2),
        "named_bridges": sorted(b.name for b in m.bridges if b.name),
        "pedestrian_bridges": sum(1 for b in m.bridges if b.bridge_class == "pedestrian"),
        "landmasses_connected": [len(set(with_d) & reached), len(with_d)],
        "exits": sorted(n.attrs.get("exit") for n in m.road_nodes if n.attrs.get("exit")),
        "highway_elevated_share": round(elev / hw_len, 4) if hw_len else 0.0,
        "megasites": len(m.megasites),
    }


# ---------------------------------------------------------------------------
# Stats and report
# ---------------------------------------------------------------------------

def stats(spec: CitySpec, m: CityModel, g: _Geo) -> dict:
    map_area = g.canvas.area
    land = math.fsum(G.area(G.from_model_poly(p)) for x in m.land for p in x.polygons)
    areas = district_areas(m, g)
    total = math.fsum(areas.values()) or 1.0
    rows = []
    for d in m.districts:
        target = d.attrs.get("area_share_target") or 0.0
        actual = areas[d.name] / total
        rows.append({"id": d.id, "name": d.name, "archetype": d.archetype,
                     "landmass": d.landmass_id, "area_km2": round(areas[d.name] / 1e6, 3),
                     "share": round(actual, 4), "target": round(target, 4),
                     "target_source": d.attrs.get("area_share_source", "spec"),
                     "error": round((actual - target) / target, 4) if target else None})
    ww_km: dict[str, float] = {}
    for w in m.waterways:
        ww_km[w.kind] = ww_km.get(w.kind, 0.0) + (
            LineString(w.centerline).length / 1000 if len(w.centerline) > 1 else 0.0)
    boundary_len, wet_len = 0.0, 0.0
    edge = g.canvas.exterior.buffer(1.0)
    wet = g.network.buffer(2.0)
    for p in g.districts.values():
        b = p.boundary.difference(edge)
        boundary_len += b.length
        wet_len += b.intersection(wet).length
    open_lm = {o.attrs.get("landmass_id") for o in m.open_spaces}
    unassigned = [lm for lm in m.landmasses if not lm.district_ids and lm.id not in open_lm]
    open_rows = [{"name": o.name, "kind": o.kind,
                  "area_km2": round(G.from_model_poly(o.polygon).area / 1e6, 3)}
                 for o in m.open_spaces if not o.attrs.get("m2")]  # M2 parks are in stats["local"]
    samples = R.boundary_samples(g.districts, g.network, g.canvas)
    b_wet = sum(float((k == 2).sum()) * seg for _, seg, k in samples)
    b_dry = sum(float((k == 1).sum()) * seg for _, seg, k in samples)
    curv = R.boundary_curvature(samples, kinds=(1,))
    curv_all = R.boundary_curvature(samples)
    water = map_area - land
    preferred = spec.water.district_separation == "water_preferred" or any(
        d.water_separation == "water_preferred" for d in spec.districts)
    return {
        "map_km2": round(map_area / 1e6, 3),
        "land_km2": round(land / 1e6, 3),
        "district_land_km2": round(total / 1e6, 3),
        "water_share": round(water / map_area, 4),
        "sea_share": round(g.sea.area / map_area, 4),
        "landmasses": len(m.landmasses),
        "landmasses_with_districts": len(m.landmasses) - len(unassigned),
        "unassigned_land_km2": round(math.fsum(G.area(g.landmasses[lm.id])
                                               for lm in unassigned) / 1e6, 3),
        "open_land_km2": round(sum(r["area_km2"] for r in open_rows), 3),
        "open_land": open_rows,
        "islands": len(m.islands),
        "river_km": round(sum(LineString(r.centerline).length for r in m.rivers) / 1000, 2),
        "channel_km": {k: round(sum(LineString(c.centerline).length for c in m.channels
                                    if c.kind == k) / 1000, 2)
                       for k in sorted({c.kind for c in m.channels})},
        "separation_channels": sum(1 for c in m.channels if c.kind == "separation"),
        "waterway_km": round(sum(ww_km.values()), 2),
        "waterway_km_by_kind": {k: round(v, 2) for k, v in sorted(ww_km.items())},
        "waterways": len(m.waterways),
        "quay_km": round(sum(LineString(q.line).length for q in m.quays) / 1000, 2),
        "district_boundary_on_water": round(wet_len / boundary_len, 4) if boundary_len else 1.0,
        "boundary_on_water": round(b_wet / (b_wet + b_dry), 4) if b_wet + b_dry else None,
        "boundary_on_water_target": spec.water.boundary_water_share if preferred else None,
        "boundary_km": {"water": round(b_wet / 2000, 2), "land": round(b_dry / 2000, 2)},
        "land_boundary_curvature": round(curv, 4) if curv is not None else None,
        "boundary_curvature": round(curv_all, 4) if curv_all is not None else None,
        "districts": rows,
    }


def run_checks(spec: CitySpec, m: CityModel, roads: bool | None = None
               ) -> tuple[list[Check], dict]:
    """All checks. Road checks run when the model has roads (or `roads` is True); the variant
    search runs without them (roads are built once, on the chosen variant)."""
    g = _Geo(m)
    if roads is None:
        roads = bool(m.road_segments or m.road_nodes or m.bridges or m.megasites)
    checks = [
        check_geometry(m, g),
        check_waterways(m, g),
        check_shares(m, g),
        check_placement(spec, m, g),
        check_separation(spec, m, g),
        check_pieces(spec, m, g),
        check_islands(spec, m, g),
        check_slivers(m, g),
        check_land_use(spec, m, g),
        check_canals(m, g),
    ]
    if roads:
        checks += [
            check_road_graph(spec, m, g),
            check_districts_served(m, g),
            check_named_bridges(spec, m, g),
            check_bridges(m, g),
            check_road_avoidance(m, g),
            check_curve_radius(m, g),
            check_segment_length(m, g),
            check_road_duplicates(m, g),
        ]
    if m.lots or m.blocks or m.junctions:
        from . import street_checks as SC

        checks += SC.run(spec, m, g)
    st = stats(spec, m, g)
    if m.road_segments:
        st.update(road_stats(spec, m, g))
    if m.lots or m.blocks or m.junctions:
        from . import street_checks as SC

        st["local"] = SC.stats(spec, m)
    return checks, st


def report_dict(spec: CitySpec, checks: list[Check], st: dict, notes: list[str],
                variant: int) -> dict:
    return {
        "name": spec.name, "seed": spec.seed,
        "stage": ("M2 (water, districts, waterways, roads, local streets, blocks, lots)"
                  if "local" in st else
                  "M1b (water, districts, waterways, primary roads)" if "road_km" in st
                  else "M1a2 (water, districts, waterways)"),
        "passed": all(c.passed for c in checks), "variant": variant,
        "checks": [c.to_dict() for c in checks], "stats": st, "notes": notes,
    }


def _pct(v) -> str:
    return "n/a" if v is None else f"{v:.0%}"


def report_text(rep: dict) -> str:
    st = rep["stats"]
    out = [f"citygen build report: {rep['name']} (seed {rep['seed']}, {rep['stage']})",
           f"result: {'PASS' if rep['passed'] else 'FAIL'}"
           f"  (hydrology variant {rep['variant']})", "", "checks:"]
    for c in rep["checks"]:
        out.append(f"  [{'pass' if c['passed'] else 'FAIL'}] {c['id']}: {c['title']}")
        for f in c["failures"]:
            out.append(f"         - {f}")
        for n in c["notes"]:
            out.append(f"         note: {n}")
    out += ["", "stats:",
            f"  map {st['map_km2']} km2, land {st['land_km2']} km2 (districts "
            f"{st['district_land_km2']} km2, unassigned {st['unassigned_land_km2']} km2)",
            f"  water share {st['water_share']:.1%} (sea {st['sea_share']:.1%})",
            f"  landmasses {st['landmasses']} ({st['landmasses_with_districts']} with districts),"
            f" islands {st['islands']}",
            f"  rivers {st['river_km']} km; channels "
            + (", ".join(f"{k} {v} km" for k, v in st["channel_km"].items()) or "none"),
            f"  separation channels {st['separation_channels']}; boundary between districts on "
            f"water {_pct(st['boundary_on_water'])}"
            + (f" (target {st['boundary_on_water_target']:.0%})"
               if st.get("boundary_on_water_target") is not None else "")
            + f", {st['boundary_km']['water']} km on water, {st['boundary_km']['land']} km on land",
            f"  district perimeter facing water {st['district_boundary_on_water']:.0%}; "
            f"boundary curvature (arc / chord over 400 m) {st['boundary_curvature']}, land "
            f"boundaries {st['land_boundary_curvature']}",
            f"  open land {st['open_land_km2']} km2"
            + "".join(f"; {r['kind']} '{r['name']}' {r['area_km2']} km2" for r in st["open_land"]),
            f"  inner waterways {st['waterways']} ({st['waterway_km']} km: "
            + (", ".join(f"{k} {v}" for k, v in st["waterway_km_by_kind"].items()) or "none")
            + f"), quays {st['quay_km']} km"]
    if "road_km" in st:
        bc = st["bridges_by_class"]
        lc = st["landmasses_connected"]
        out += [
            "  roads " + ", ".join(f"{k} {v} km" for k, v in st["road_km"].items())
            + f"; {st['road_segments']} segments, {st['road_nodes']} nodes, "
            f"{st['road_components']} component(s); exits {', '.join(st['exits']) or 'none'}",
            f"  bridges {st['bridges']} (sea {bc['sea']}, river {bc['river']}, canal "
            f"{bc['canal']}; {st['bridge_span_km']} km of span), pedestrian "
            f"{st['pedestrian_bridges']}; named: {', '.join(st['named_bridges']) or 'none'}",
            f"  landmasses with districts connected by road {lc[0]} of {lc[1]}; highway "
            f"planned elevated {st['highway_elevated_share']:.0%}; megasite reserves "
            f"{st['megasites']}; road variant {st.get('road_variant', 0)}"]
    lo = st.get("local")
    if lo:
        rk = st.get("road_km", {})
        out += [
            "  local roads " + ", ".join(f"{k} {rk[k]} km" for k in
                                         ("street", "alley", "service", "pedestrian",
                                          "footbridge") if k in rk)
            + f"; {lo['one_way_segments']} one-way segments, {lo['footbridges']} footbridges",
            f"  junctions {lo['junctions']} ({lo['junctions_signalized']} signalized), "
            f"crosswalks {lo['crosswalks']}, sidewalks {lo['sidewalk_km']} km, lanes "
            f"{lo['lanes']} + {lo['lane_connectors']} connectors, walkways {lo['walkways']} ("
            + ", ".join(f"{k} {v} km" for k, v in lo["walkway_km"].items()) + ")",
            "  junctions by type: " + ", ".join(f"{k} {v}" for k, v in
                                                list(lo["junctions_by_type"].items())[:12]),
            f"  blocks {lo['blocks']}, lots {lo['lots']} ({lo['merged_lot_groups']} merged "
            f"groups), open space {lo['open_share']:.1%} of net land ("
            + ", ".join(f"{k} {v}" for k, v in lo["open_spaces_by_kind"].items()) + "), "
            f"named places {lo['places']}",
            "",
            "  lots by archetype            count   min m2   p10    median    p90      max"
            "  median frontage m"]
        for k, r in lo["lot_area_m2_by_archetype"].items():
            out.append(f"  {k[:26]:<26} {r['count']:>7} {r['min']:>8.0f} {r['p10']:>6.0f} "
                       f"{r['median']:>8.0f} {r['p90']:>7.0f} {r['max']:>8.0f}  "
                       f"{r['median_frontage_m'] or 0:>6.1f}")
        out += ["", "  blocks and open space by district  blocks  median block m  open share"]
        for name, r in lo["block_size_m_by_district"].items():
            out.append(f"  {name[:32]:<32} {r.get('count', 0):>7} {r.get('median', 0):>14.0f}"
                       f"  {lo['open_share_by_district'].get(name, 0):>9.1%}")
    out += ["",
            "  district                     archetype              landmass  km2    share  "
            "target  error"]
    for r in st["districts"]:
        err = f"{r['error']:+.1%}" if r["error"] is not None else "n/a"
        out.append(f"  {r['name'][:28]:<28} {r['archetype'][:22]:<22} {r['landmass'] or '-':<8}"
                   f"  {r['area_km2']:<6.3f} {r['share']:.3f}  {r['target']:.3f}  {err:>6}"
                   f"  ({r['target_source']})")
    if rep["notes"]:
        out += ["", "notes:"] + [f"  - {n}" for n in rep["notes"]]
    return "\n".join(out) + "\n"

