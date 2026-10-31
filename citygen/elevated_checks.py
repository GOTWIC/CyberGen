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


def grade_kind(s) -> str | None:
    """M18: which grade limit a road's z profile keeps: `ramp` (ramps, loops, flyovers and
    stack ramps), `run` (viaducts), `approach` (other raised highways and avenues: bridge
    approaches), `deck_ramp` (M14), `local` (streets ramping to a raised junction), or None
    (footbridge stairs)."""
    if s.road_class == "footbridge":
        return None
    if s.attrs.get("role") == "deck_ramp":
        return "deck_ramp"
    if s.attrs.get("role") == "ramp":
        return "ramp"
    if s.attrs.get("elevated"):
        return "run"
    if s.road_class in ("highway", "avenue"):
        return "approach"
    return "local"


def grade_caps(spec) -> dict:
    """M18: the steepest grade of each kind (`highways.grades`; approaches as steep as a run
    where a junction on them is levelled, local streets as steep as a ramp)."""
    from .decks import RAMP_GRADE

    gr = spec.highways.grades
    return {"ramp": gr.ramp_max, "run": gr.run_max, "approach": gr.run_max,
            "deck_ramp": RAMP_GRADE, "local": gr.ramp_max}


def steepest(p) -> tuple[float, float, float]:
    """(grade, s0, s1) of the steepest piece of a z profile (both s and z are on the 1 cm
    grid: a step of 1 cm in z is rounding)."""
    best = (0.0, 0.0, 0.0)
    for (s0, z0), (s1, z1) in zip(p, p[1:]):
        if s1 - s0 > 1e-6:
            g = (abs(z1 - z0) - 0.01) / (s1 - s0)
            if g > best[0]:
                best = (g, s0, s1)
    return best


def check_grades(spec, m: CityModel) -> Check:
    cap = spec.highways.grades.ramp_max
    c = Check("road_grades", f"Every road at most {cap:.0%} steep along its z profile "
                             "(viaducts, ramps, bridge approaches, streets ramping up to a "
                             "raised junction; footbridge stairs aside, M14's deck ramps as "
                             "steep as a street)")
    caps = grade_caps(spec)
    for s in m.road_segments:
        k = grade_kind(s)
        if k is None:
            continue
        lim = caps["deck_ramp"] if k == "deck_ramp" else cap
        g, s0, s1 = steepest(_prof(s))
        if g > lim + 1e-4:
            _limit(c, f"{s.id} ({s.road_class}): {g + 0.01 / max(s1 - s0, 1e-6):.1%} at "
                      f"s {s0:.0f} to {s1:.0f} m")
    return c


def check_ramp_grades(spec, m: CityModel) -> Check:
    gr = spec.highways.grades
    c = Check("ramp_grades", f"M18: ramps, loops, flyovers and stack ramps at most "
                             f"{gr.ramp_max:.0%} steep, viaduct runs and bridge approaches "
                             f"{gr.run_max:.0%} (`highways.grades`)")
    caps = grade_caps(spec)
    for s in m.road_segments:
        k = grade_kind(s)
        if k not in ("ramp", "run", "approach"):
            continue
        g, s0, s1 = steepest(_prof(s))
        if g > caps[k] + 1e-4:
            _limit(c, f"{s.id} ({k}): {g:.1%} at s {s0:.0f} to {s1:.0f} m, over "
                      f"{caps[k]:.0%}")
    return c


def grade_stats(m: CityModel) -> dict:
    """M18: per kind of raised road, how many and their steepest grades (the steepest, and
    the median of each road's steepest)."""
    by: dict = {}
    for s in m.road_segments:
        k = grade_kind(s)
        p = _prof(s)
        if k is None or not any(z > 0.05 for _, z in p):
            continue
        by.setdefault(k, []).append(steepest(p)[0])
    return {k: {"n": len(v), "max": round(max(v), 4), "median": round(float(np.median(v)), 4)}
            for k, v in sorted(by.items())}


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
    cols = [s for s in m.structures if (s.attrs or {}).get("road_id") and s.kind == "column"]
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


# --- M12: stacks and turbines -------------------------------------------------------------

SYSTEM = ("stack", "turbine")


def _systems(m: CityModel) -> dict:
    """Interchange id -> its directional ramps, for every stack and turbine."""
    by: dict = {}
    for s in m.road_segments:
        if s.attrs.get("role") == "ramp" and s.attrs.get("template") in SYSTEM:
            by.setdefault(s.attrs.get("interchange"), []).append(s)
    return dict(sorted(by.items()))


def _unit(a, b):
    dx, dy = b[0] - a[0], b[1] - a[1]
    L = (dx * dx + dy * dy) ** 0.5
    return (dx / L, dy / L) if L > 0 else (1.0, 0.0)


def _along(pts, d: float, from_end: bool = False):
    """The point d m along a polyline (from its end when asked)."""
    line = LineString(pts)
    p = line.interpolate(line.length - d if from_end else d)
    return (p.x, p.y)


def _angle(a, b) -> float:
    return float(np.degrees(np.arctan2(a[0] * b[1] - a[1] * b[0], a[0] * b[0] + a[1] * b[1])))


def _turning(pts) -> float:
    """Signed total turn of a polyline in degrees (left positive), over 10 m steps."""
    line = LineString(pts)
    qs = [line.interpolate(d) for d in np.arange(0.0, line.length, 10.0).tolist()]
    qs.append(line.interpolate(line.length))
    hs = [_unit((a.x, a.y), (b.x, b.y)) for a, b in zip(qs, qs[1:]) if a.distance(b) > 0.5]
    return sum(_angle(a, b) for a, b in zip(hs, hs[1:]))


def check_stack_ramps(m: CityModel) -> Check:
    c = Check("stack_ramps", "Every stack and turbine has its eight directional ramps, one per "
                             "movement (four right turns, four left turns, none a loop), each "
                             "one-way from the right side of one highway to the right side of "
                             "the other")
    at: dict = {}
    for s in m.road_segments:
        for nid in (s.start, s.end):
            at.setdefault(nid, []).append(s)
    pos = {n.id: (n.position[0], n.position[1]) for n in m.road_nodes}
    systems = _systems(m)
    for ic, rs in systems.items():
        turns = sorted(s.attrs.get("turn") or "" for s in rs)
        if turns != ["left"] * 4 + ["right"] * 4:
            _limit(c, f"{ic}: ramps {', '.join(turns)} (four right and four left turns wanted)")
            continue
        heads = []
        for s in rs:
            pts = [tuple(p) for p in s.centerline]
            h0 = _unit(pts[0], _along(pts, 30.0))
            h1 = _unit(_along(pts, 30.0, True), pts[-1])
            heads.append((h0, h1, s.id))
            turn = _turning(pts)
            if not s.one_way:
                _limit(c, f"{s.id} ({ic}): not one-way")
            if abs(turn) > 150.0:
                _limit(c, f"{s.id} ({ic}): turns {turn:.0f} degrees (a loop)")
            elif (turn > 0) != (s.attrs.get("turn") == "left"):
                _limit(c, f"{s.id} ({ic}): a {s.attrs.get('turn')} turn that turns {turn:.0f} "
                          "degrees")
            for nid, h, far, end in ((s.start, h0, _along(pts, 60.0), "leaves"),
                                     (s.end, h1, _along(pts, 60.0, True), "joins")):
                roads = [o for o in at.get(nid, []) if o.id != s.id and
                         o.road_class == "highway" and o.attrs.get("role") != "ramp"]
                if len(roads) != 2:
                    _limit(c, f"{s.id} ({ic}) {end} no highway at {nid}")
                    continue
                # the road's direction of travel there: its piece that runs on with the ramp
                P = pos[nid]
                ds = []
                for o in roads:
                    op = [tuple(p) for p in o.centerline]
                    op = op if o.start == nid else op[::-1]
                    ds.append(_unit(P, _along(op, 25.0)))
                d = max(ds, key=lambda v: v[0] * h[0] + v[1] * h[1])
                if d[0] * h[0] + d[1] * h[1] < 0.0:
                    d = (-d[0], -d[1])
                side = d[0] * (far[1] - P[1]) - d[1] * (far[0] - P[0])
                if side > -1.0:
                    _limit(c, f"{s.id} ({ic}) {end} its highway at {nid} from the left side")
        for i, (a0, a1, ia) in enumerate(heads):
            for b0, b1, ib in heads[i + 1:]:
                if abs(_angle(a0, b0)) < 45.0 and abs(_angle(a1, b1)) < 45.0:
                    _limit(c, f"{ic}: {ia} and {ib} make the same movement")
    c.notes.append(f"{len(systems)} stacks and turbines, "
                   f"{sum(len(r) for r in systems.values())} directional ramps")
    return c


def _z_near(s, p) -> float:
    line = LineString(s.centerline)
    return EL._z_at(_prof(s), line.project(Point(p)))


def check_stack_levels(m: CityModel) -> Check:
    c = Check("stack_levels", f"A stack is four levels: the highway at grade passes under the "
                              f"lifted one ({EL.LEVEL_Z[1]:g} m deck), its left ramps onto the "
                              f"lifted highway cross the core at tier 2 ({EL.LEVEL_Z[2]:g} m) and "
                              f"those off it at tier 3 ({EL.LEVEL_Z[3]:g} m) over them; a "
                              f"turbine's left ramps each cross a highway at a point of their "
                              f"own (at most three levels)")
    systems = _systems(m)
    hw = [s for s in m.road_segments if s.road_class == "highway" and
          s.attrs.get("role") != "ramp"]
    lines = [LineString(s.centerline) for s in hw]
    tree = shapely.STRtree(lines) if lines else None
    for ic, rs in systems.items():
        C = rs[0].attrs.get("crossing")
        if C is None or tree is None:
            _limit(c, f"{ic}: no crossing point")
            continue
        pt = Point(C)
        near = [hw[i] for i in sorted(int(x) for x in tree.query(pt, predicate="dwithin",
                                                                 distance=2.0))]
        up = [s for s in near if s.attrs.get("elevated")]
        gnd = [s for s in near if not s.attrs.get("elevated")]
        if not up or max(_z_near(s, C) for s in up) < EL.LEVEL_Z[1] - 0.5:
            _limit(c, f"{ic}: no deck at {EL.LEVEL_Z[1]:g} m over its crossing")
        if not gnd or min(_z_near(s, C) for s in gnd) > 0.5:
            _limit(c, f"{ic}: no highway at grade under its crossing")
        left = [s for s in rs if s.attrs.get("turn") == "left"]
        if rs[0].attrs.get("template") == "stack":
            for s in left:
                tier = s.attrs.get("tier")
                top = max(z.z for z in s.z_profile)
                if tier not in (2, 3) or not (EL.LEVEL_Z[tier] - 0.05 <= top <=
                                              EL.STACK_TOP_M + 0.05):
                    _limit(c, f"{s.id} ({ic}): tier {tier}, crest {top:.1f} m")
            for a in [s for s in left if s.attrs.get("tier") == 3]:
                la = LineString(a.centerline)
                for b in [s for s in left if s.attrs.get("tier") == 2]:
                    for p in EL.G_points(la.intersection(LineString(b.centerline))):
                        za, zb = _z_near(a, p), _z_near(b, p)
                        if za < EL.LEVEL_Z[3] - 0.05 or zb < EL.LEVEL_Z[2] - 0.05 or \
                                za - zb < EL.CLEAR_M + EL.DECK_M - 0.05:
                            _limit(c, f"{a.id} over {b.id} ({ic}) at ({p[0]:.0f}, "
                                      f"{p[1]:.0f}): {za:.1f} m over {zb:.1f} m")
        else:
            # the left ramps' crossings of each highway at points of their own
            for road in near:
                rl = LineString(road.centerline)
                hits = sorted(rl.project(Point(p)) for s in left
                              for p in EL.G_points(rl.intersection(LineString(s.centerline))))
                for x0, x1 in zip(hits, hits[1:]):
                    if x1 - x0 < 15.0:
                        _limit(c, f"{ic}: two left ramps cross {road.id} {x1 - x0:.0f} m "
                                  "apart")
    c.notes.append(f"{sum(1 for r in systems.values() if r[0].attrs.get('template') == 'stack')}"
                   f" stacks, {sum(1 for r in systems.values() if r[0].attrs.get('template') == 'turbine')} turbines")
    return c


def run(spec, m: CityModel, supports: bool) -> list[Check]:
    with G.canonical():
        out = [check_grades(spec, m), check_ramp_grades(spec, m), check_continuity(m),
               check_clearance(m), check_ramps(m), check_stack_ramps(m),
               check_stack_levels(m)]
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
    cols = [s for s in m.structures if (s.attrs or {}).get("road_id") and s.kind == "column"]
    emb = [s for s in m.structures if s.kind == "embankment"]
    under = [s for s in m.road_segments if s.attrs.get("role") == "underpass"]
    fly = [s for s in ramps if s.attrs.get("flyover")]
    sysr = [s for s in ramps if s.attrs.get("template") in SYSTEM]
    return {
        "elevated_km": round(sum(s.attrs.get("length_m", 0.0) for s in el) / 1000.0, 2),
        "elevated_runs": len({s.attrs.get("split_of") for s in el if not s.attrs.get("direct")}),
        "direct_branches": len({s.attrs.get("split_of") for s in el if s.attrs.get("direct")}),
        "ramps": len(ramps),
        "ramp_km": round(sum(s.attrs.get("length_m", 0.0) for s in ramps) / 1000.0, 2),
        "interchanges": dict(sorted(tmpl.items())),
        "flyovers": len(fly),
        "max_flyover_m": round(max((z.z for s in fly for z in s.z_profile), default=0.0), 2),
        "stacks": tmpl.get("stack", 0),
        "turbines": tmpl.get("turbine", 0),
        "stack_ramps": len(sysr),
        "max_stack_m": round(max((z.z for s in sysr for z in s.z_profile), default=0.0), 2),
        "overpasses": over,
        "max_deck_m": round(max((z.z for s in el for z in s.z_profile), default=0.0), 2),
        "raised_other_km": round(sum(s.attrs.get("length_m", 0.0) for s in raised) / 1000.0,
                                 2),
        "underpass_streets": len(under),
        "road_columns": len(cols),
        "embankments": len(emb),
        "embankment_km": round(sum(s.attrs.get("s1_m", 0.0) - s.attrs.get("s0_m", 0.0)
                                   for s in emb) / 1000.0, 2),
        "grades": grade_stats(m),
    }
