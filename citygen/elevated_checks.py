"""M7 checks: road levels, grades, deck clearances, ramps and supports (scope 5.2 and 9)."""

from __future__ import annotations

import numpy as np
import shapely
from shapely.geometry import LineString, Point

from . import elevated as EL
from . import geom as G
from .checks import Check
from .model import CityModel

LIMIT = 12
BRIDGE_DECK_M = 1.5             # structure depth of a bridge (M1b)
WALK_CLEAR_M = 3.0              # over a pedestrian street
VEHICLE = ("highway", "avenue", "street", "alley", "service")


def _limit(c: Check, msg: str) -> None:
    if len(c.failures) < LIMIT:
        c.failures.append(msg)
    elif len(c.failures) == LIMIT:
        c.failures.append("... more")


def _prof(s) -> list[tuple[float, float]]:
    return [(z.s, z.z) for z in s.z_profile]


def check_grades(m: CityModel) -> Check:
    c = Check("road_grades", f"Every road at most {EL.MAX_GRADE:.0%} steep along its z "
                             "profile (viaducts, ramps, bridge approaches, streets ramping up "
                             "to a raised junction; footbridge stairs aside)")
    for s in m.road_segments:
        if s.road_class == "footbridge":
            continue
        p = _prof(s)
        for (s0, z0), (s1, z1) in zip(p, p[1:]):
            # (both s and z are on the 1 cm grid: a step of 1 cm in z is rounding)
            if s1 - s0 > 1e-6 and (abs(z1 - z0) - 0.01) / (s1 - s0) > EL.MAX_GRADE + 1e-4:
                _limit(c, f"{s.id} ({s.road_class}): {abs(z1 - z0) / (s1 - s0):.1%} at "
                          f"s {s0:.0f} to {s1:.0f} m")
                break
    return c


def check_continuity(m: CityModel) -> Check:
    c = Check("level_continuity", "Every road meets its nodes at their height (each road "
                                  "level system joined by ramps, no step at a node)")
    nz = {n.id: n.position[2] for n in m.road_nodes}
    for s in m.road_segments:
        p = _prof(s)
        if not p:
            continue
        for nid, z in ((s.start, p[0][1]), (s.end, p[-1][1])):
            if abs(nz.get(nid, 0.0) - z) > 0.05:
                _limit(c, f"{s.id} meets node {nid} at {z:g} m, the node is at "
                          f"{nz.get(nid, 0.0):g} m")
    return c


def _deck(s) -> float:
    return EL.DECK_M if (s.attrs.get("elevated") or s.attrs.get("role") == "ramp") else \
        BRIDGE_DECK_M


def check_clearance(m: CityModel) -> Check:
    c = Check("deck_clearance", f"Where roads cross without a node, the one under has "
                                f"{EL.CLEAR_M:g} m under the deck over it ({WALK_CLEAR_M:g} m "
                                "over a pedestrian street)")
    segs = [s for s in m.road_segments if s.road_class != "footbridge"]
    lines = [LineString(s.centerline) for s in segs]
    if not lines:
        return c
    tree = shapely.STRtree(lines)
    n = 0
    for i, a in enumerate(lines):
        for j in sorted(int(x) for x in tree.query(a, predicate="crosses")):
            if j <= i:
                continue
            sa, sb = segs[i], segs[j]
            if {sa.start, sa.end} & {sb.start, sb.end}:
                continue
            for p in EL.G_points(a.intersection(lines[j])):
                pt = Point(p)
                za = EL._z_at(_prof(sa), a.project(pt))
                zb = EL._z_at(_prof(sb), lines[j].project(pt))
                hi, lo, zh, zl = (sa, sb, za, zb) if za >= zb else (sb, sa, zb, za)
                need = (EL.CLEAR_M if lo.road_class in VEHICLE else WALK_CLEAR_M) + _deck(hi)
                n += 1
                if zh - zl < need - 0.05:
                    _limit(c, f"{hi.id} over {lo.id} at ({p[0]:.0f}, {p[1]:.0f}): "
                              f"{zh - zl - _deck(hi):.1f} m clear")
    c.notes.append(f"{n} crossings without a node")
    return c


def check_ramps(m: CityModel) -> Check:
    c = Check("ramps_land", "Every ramp is one-way and joins a viaduct at its deck height to a "
                            "ground road at the ground")
    nz = {n.id: n.position[2] for n in m.road_nodes}
    at: dict = {}
    for s in m.road_segments:
        for nid in (s.start, s.end):
            at.setdefault(nid, []).append(s)
    for s in m.road_segments:
        if s.attrs.get("role") != "ramp":
            continue
        if not s.one_way:
            _limit(c, f"{s.id}: a ramp that is not one-way")
        ends = sorted(((nz.get(x, 0.0), x) for x in (s.start, s.end)))
        (z_lo, n_lo), (z_hi, n_hi) = ends
        ground = [o for o in at.get(n_lo, []) if o.id != s.id and o.attrs.get("role") != "ramp"]
        deck = [o for o in at.get(n_hi, []) if o.id != s.id and o.attrs.get("elevated")]
        if z_lo > 0.05 + 3.0 or not ground:
            _limit(c, f"{s.id}: its low end ({z_lo:g} m) does not land on a ground road")
        if z_hi < EL.LEVEL_Z[1] * 0.2 or not deck:
            _limit(c, f"{s.id}: its high end ({z_hi:g} m) is not on a viaduct")
    return c


def check_supports(m: CityModel) -> Check:
    c = Check("road_supports", f"Columns under every raised road deck over land, at most "
                               f"{EL.SUPPORT_MAX_GAP_M:.0f} m apart, none in a lane, a road "
                               "or junction under the deck, a building, the water or a "
                               "transit structure")
    cols = [s for s in m.structures if (s.attrs or {}).get("road_id")]
    raised = EL.raised_segments(m)
    if not raised:
        return c
    cx = EL.support_context(m)
    seg = {s.id: s for s in m.road_segments}
    for s in cols:
        rs = seg.get(s.attrs["road_id"])
        if rs is None:
            _limit(c, f"{s.id}: no road {s.attrs['road_id']}")
            continue
        poly = G.from_model_poly(s.footprint)
        cc = poly.centroid
        size = (poly.area ** 0.5)
        if not EL.column_free(cx, rs, (cc.x, cc.y), size - 0.02, s.z1_m):
            _limit(c, f"{s.id}: stands in something")
    pts = [G.from_model_poly(s.footprint).centroid for s in cols]
    ctree = shapely.STRtree(pts) if pts else None
    wet = cx["wtree"]
    half = EL.SUPPORT_MAX_GAP_M / 2.0 + 3.0
    for s in raised:
        line = LineString(s.centerline)
        prof = _prof(s)
        need = []
        for d in np.arange(2.5, line.length, 5.0).tolist():
            if EL.under_m(EL._z_at(prof, d)) < EL.SUPPORT_MIN_UNDER_M:
                continue
            p = line.interpolate(d)
            if wet is not None and len(wet.query(p.buffer(3.0), predicate="intersects")):
                continue     # over the water (bridge piers)
            need.append(p)
        if not need:
            continue
        if ctree is None:
            _limit(c, f"{s.id}: raised over land with no columns")
            continue
        ip, _ = ctree.query(np.array(need, dtype=object), predicate="dwithin", distance=half)
        ok = np.zeros(len(need), bool)
        ok[ip] = True
        bad = np.nonzero(~ok)[0].tolist()
        if bad:
            p = need[bad[0]]
            _limit(c, f"{s.id}: no column within {half:.0f} m at ({p.x:.0f}, {p.y:.0f})")
    c.notes.append(f"{len(cols)} road columns under {len(raised)} raised segments")
    return c


def run(m: CityModel, supports: bool) -> list[Check]:
    with G.canonical():
        out = [check_grades(m), check_continuity(m), check_clearance(m), check_ramps(m)]
        if supports:
            out.append(check_supports(m))
    return out


def stats(m: CityModel) -> dict:
    el = [s for s in m.road_segments if s.attrs.get("elevated")]
    ramps = [s for s in m.road_segments if s.attrs.get("role") == "ramp"]
    ics: dict = {}
    for s in ramps:
        ics.setdefault(s.attrs.get("interchange"), s.attrs.get("template"))
    tmpl: dict = {}
    for t in ics.values():
        tmpl[t] = tmpl.get(t, 0) + 1
    over = sum(len(s.attrs.get("overpass_at", [])) for s in el)
    raised = [s for s in m.road_segments if not s.attrs.get("elevated") and
              s.attrs.get("role") != "ramp" and any(z.z > 0.5 for z in s.z_profile)]
    cols = [s for s in m.structures if (s.attrs or {}).get("road_id")]
    under = [s for s in m.road_segments if s.attrs.get("role") == "underpass"]
    return {
        "elevated_km": round(sum(s.attrs.get("length_m", 0.0) for s in el) / 1000.0, 2),
        "elevated_runs": len({s.attrs.get("split_of") for s in el if not s.attrs.get("direct")}),
        "direct_branches": len({s.attrs.get("split_of") for s in el if s.attrs.get("direct")}),
        "ramps": len(ramps),
        "ramp_km": round(sum(s.attrs.get("length_m", 0.0) for s in ramps) / 1000.0, 2),
        "interchanges": dict(sorted(tmpl.items())),
        "overpasses": over,
        "max_deck_m": round(max((z.z for s in el for z in s.z_profile), default=0.0), 2),
        "raised_other_km": round(sum(s.attrs.get("length_m", 0.0) for s in raised) / 1000.0,
                                 2),
        "underpass_streets": len(under),
        "road_columns": len(cols),
    }
