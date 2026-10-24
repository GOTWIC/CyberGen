"""Checks and stats for a built city (scope section 9, water and district parts).

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
    return {n: p.area for n, p in g.districts.items()}


def check_shares(m: CityModel, g: _Geo) -> Check:
    c = Check("district_shares", f"District area shares within {SHARE_TOL:.0%} of the spec")
    areas = district_areas(m, g)
    total = sum(areas.values()) or 1.0
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
        if sep and sep in LAND_KINDS:
            c.notes.append(f"'{d.name}': separated_by '{sep}' is checked from M1b (roads, walls)")
        elif sep:
            wat = g.kind_water(sep) if sep in BoundaryKind.__args__ else g.named_water(sep)
            if wat is None or not R.touches(poly, wat):
                c.failures.append(f"'{d.name}' does not border '{sep}' (separated_by)")
            if sep == "water" and _land_neighbors(m, g, d.name):
                c.failures.append(f"'{d.name}' shares land with "
                                  f"{', '.join(_land_neighbors(m, g, d.name))} "
                                  "(separated_by water)")
    return c


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
# Stats and report
# ---------------------------------------------------------------------------

def stats(spec: CitySpec, m: CityModel, g: _Geo) -> dict:
    map_area = g.canvas.area
    land = sum(G.from_model_poly(p).area for x in m.land for p in x.polygons)
    areas = district_areas(m, g)
    total = sum(areas.values()) or 1.0
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
                 for o in m.open_spaces]
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
        "unassigned_land_km2": round(sum(g.landmasses[lm.id].area for lm in unassigned) / 1e6,
                                     3),
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


def run_checks(spec: CitySpec, m: CityModel) -> tuple[list[Check], dict]:
    g = _Geo(m)
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
    return checks, stats(spec, m, g)


def report_dict(spec: CitySpec, checks: list[Check], st: dict, notes: list[str],
                variant: int) -> dict:
    return {
        "name": spec.name, "seed": spec.seed, "stage": "M1a2 (water, districts, waterways)",
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
            + f"), quays {st['quay_km']} km", "",
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

