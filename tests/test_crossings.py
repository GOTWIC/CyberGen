"""Crossings fix: crosswalk and crossing walkways straight across the road from sidewalk to
sidewalk, corners and sidewalks led round a junction's carriageway on its corner pads, and
the `walkway_carriageway` check (`network_checks.walk_on_roads`).

Covers the helpers on small shapes (the way round a carriageway, never across a leg's port
nor off the right of way; a corner whose sidewalks meet in a fillet; splitting a sidewalk
for a crossing), a built sample (the check passes, every crosswalk walkway square across its
crosswalk record, joined to the sidewalks at its ends) and a failing case.
"""

import math

from shapely.geometry import LineString, Point, Polygon, box

from citygen import junctions as JN
from citygen import network_checks as NC
from citygen import streets as ST
from citygen.model import CityModel
from citygen.validate import load_spec

from conftest import ROOT, built_sample

VESPER_BAY = ROOT / "cities" / "vesper_bay" / "city_spec.json"


def _deep(C, pts) -> float:
    """How far a polyline runs inside C taken in by 1 cm (its length there)."""
    return LineString(pts).intersection(C.buffer(-0.01)).length


def test_round_leads_a_walk_round_the_carriageway():
    C = box(-5, -5, 5, 5)
    cx = JN._Carriage(C, R=box(-10, -10, 10, 10))
    out = JN._round([(-8.0, 0.0), (8.0, 0.0)], cx)
    assert out[0] == (-8.0, 0.0) and out[-1] == (8.0, 0.0)
    assert _deep(C, out) == 0.0
    assert box(-10.1, -10.1, 10.1, 10.1).contains(LineString(out))


def test_way_round_never_crosses_a_port():
    """The shorter way round (under the square) would walk along a leg's end: the way goes
    over the top."""
    C = box(-5, -5, 5, 5)
    port = ((0.0, -6.0), (0.0, -4.0))
    cx = JN._Carriage(C, ports=[port], R=box(-10, -10, 10, 10))
    out = JN._round([(-8.0, -2.0), (8.0, -2.0)], cx)
    assert _deep(C, out) == 0.0
    assert not LineString(out).intersects(LineString(port))
    assert max(y for _, y in out) > 5.0


def test_no_way_round_off_the_right_of_way():
    """With no pad round the carriageway (the right of way is the carriageway), the walk
    goes across: never through the lots beside it."""
    C = box(-5, -5, 5, 5)
    cx = JN._Carriage(C, R=box(-5, -5, 5, 5))
    out = JN._round([(-8.0, 0.0), (8.0, 0.0)], cx)
    assert out[0] == (-8.0, 0.0) and out[-1] == (8.0, 0.0) and all(y == 0.0 for _, y in out)


def test_corner_walk_round_a_fillet():
    """Two roads at a right angle (carriageways 10 m, sidewalks 4 m) whose corner fillet
    reaches past the sidewalks' meeting point: the corner and the walks to both sidewalks
    keep off the carriageway, on the right of way."""
    fillet = Polygon([(5, 5), (16, 5), (5, 16)])
    C = box(-5, -40, 5, 40).union(box(-40, -5, 40, 5)).union(fillet)
    R = box(-9, -40, 9, 40).union(box(-40, -9, 40, 9)).union(
        Polygon([(5, 5), (25, 5), (5, 25)]))
    cx = JN._Carriage(C, R=R)
    X, pa, pb = (7.0, 7.0), (30.0, 7.0), (7.0, 30.0)
    assert C.contains(Point(X))
    c, ta, tb = JN._corner_walk(X, pa, pb, cx)
    assert not C.contains(Point(c)) and R.buffer(0.2).contains(Point(c))
    assert ta[0] == c and ta[-1] == pa and tb[0] == c and tb[-1] == pb
    assert _deep(C, ta) == 0.0 and _deep(C, tb) == 0.0
    # (beside a road with no sidewalk the corner is where the sidewalk reaches the curb)
    c1, t1, t2 = JN._corner_walk(X, pa, None, cx)
    assert t2 == [c1] and t1[-1] == pa and _deep(C, t1) == 0.0
    assert abs(c1[1] - 7.0) < 0.05 and c1[0] > 5.0


def test_split_at_crossings():
    chain = [(0.0, 0.0), (10.0, 0.0), (10.0, 10.0)]
    pieces, at = JN._split_at(chain, [(4.0, 0.3), (10.02, 6.0)])
    assert at == [(4.0, 0.0), (10.0, 6.0)]
    assert pieces == [[(0.0, 0.0), (4.0, 0.0)], [(4.0, 0.0), (10.0, 0.0), (10.0, 6.0)],
                      [(10.0, 6.0), (10.0, 10.0)]]
    pieces, at = JN._split_at(chain, [(10.03, 0.01)])     # (at a vertex)
    assert at == [(10.0, 0.0)] and len(pieces) == 2


# --- a built sample ------------------------------------------------------------------------

def test_walkways_keep_off_the_carriageway_on_a_sample():
    b, _, _ = built_sample(VESPER_BAY)
    m = b.model
    checks = {c.id: c for c in b.checks}
    assert checks["walkway_carriageway"].passed, checks["walkway_carriageway"].failures[:5]
    st = NC.walk_road_stats(m)
    for kind in NC.CROSS_KINDS:
        d = st[kind]
        assert d["past_span_m"] <= 0.001 * d["length_m"] and not d["past_tol"], (kind, d)
    d = st["sidewalk"]          # (main's: 5.5%; what is left mostly on clusters' faces)
    assert d["on_carriageway_m"] <= 0.02 * d["length_m"], d
    # every crosswalk record of a road with sidewalks has its walkway: square across it, from
    # sidewalk to sidewalk (a highway's runs between its corners)
    walks = [w for w in m.walkways if w.kind == "crosswalk" and len(w.line) >= 4]
    side_ends: dict = {}
    for w in m.walkways:
        if w.kind == "sidewalk":
            for p in (w.line[0], w.line[-1]):
                side_ends.setdefault((round(p[0], 2), round(p[1], 2)), 0)
    joined = 0
    xs = [x for x in m.crosswalks if x.attrs.get("road_class") != "highway"]
    for x in xs:
        a, c = x.line
        mid = ((a[0] + c[0]) / 2, (a[1] + c[1]) / 2)
        best = min(walks, key=lambda w: min(ST._dist(mid, ((p[0] + q[0]) / 2, (p[1] + q[1]) / 2))
                                            for p, q in zip(w.line, w.line[1:])))
        k = min(range(len(best.line) - 1), key=lambda i: ST._dist(
            mid, ((best.line[i][0] + best.line[i + 1][0]) / 2,
                  (best.line[i][1] + best.line[i + 1][1]) / 2)))
        p, q = best.line[k], best.line[k + 1]
        assert ST._dist(mid, ((p[0] + q[0]) / 2, (p[1] + q[1]) / 2)) < 0.5, x.id
        if len(best.line) == 4:
            ends = (best.line[0], best.line[-1])
            joined += all((round(e[0], 2), round(e[1], 2)) in side_ends for e in ends)
            # (its tails square to the crosswalk: no run along the curb)
            dx, dy = c[0] - a[0], c[1] - a[1]
            L = math.hypot(dx, dy)
            for e, f in ((best.line[0], best.line[1]), (best.line[2], best.line[3])):
                along = abs((f[0] - e[0]) * dy - (f[1] - e[1]) * dx) / L
                assert along < 1.0, (x.id, along)
    assert joined >= 0.9 * len(xs)


def test_check_walk_roads_fails():
    b, _, _ = built_sample(VESPER_BAY)
    d = b.model.model_dump(mode="json")
    # (a crossing that runs along a street's carriageway (no median), in three stretches)
    seg = next(s for s in d["road_segments"] if s["road_class"] == "street" and
               not (s["cross_section"].get("median_m") or 0.0) and
               not any(p["z"] for p in s["z_profile"]) and
               ST._plen([tuple(p[:2]) for p in s["centerline"]]) > 60.0)
    pts = [tuple(p[:2]) for p in seg["centerline"]]
    L = ST._plen(pts)
    line = [ST._along(pts, L * k / 6)[0] for k in (2, 3, 4)] + [ST._along(pts, L * 5 / 6)[0]]
    d["walkways"].append({"id": "wk.test", "kind": "crossing", "type": "walkway.crossing",
                          "line": [[p[0], p[1], 0.0] for p in line], "width_m": 2.0,
                          "neighbors": [], "attrs": {}})
    c = NC.check_walk_roads(load_spec(VESPER_BAY).filled, CityModel.model_validate(d))
    assert not c.passed and "wk.test" in " ".join(c.failures)
