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


def test_offset_joins_the_parts_geos_splits_it_into():
    """Curves followups: GEOS offsets a line turning by a hair (1 cm over 85 m, on the 1 cm
    grid) on its inner side as two parts meeting end to end; the sidewalk's middle line and
    the lanes on that side run the road's whole length, not its longer part alone (Delta
    Megacity's `rs.e1701n1213`, whose right sidewalk ended 40 m short)."""
    base = [(1664.53, 1212.51), (1710.0, 1212.5), (1750.0, 1212.49)]
    for d in (11.5, -11.5, -6.95):
        line = JN._offset(base, d)
        assert line[0][0] == 1664.53 and line[-1][0] == 1750.0, (d, line)
        assert abs(ST._plen(line) - ST._plen(base)) < 0.05
    # (parts apart, a loop's, stay apart: the longer one alone)
    a, b = [(0.0, 0.0), (10.0, 0.0)], [(10.5, 0.0), (12.0, 0.0)]
    assert JN._joined(a, [a, b]) == a
    assert JN._joined(a, [b, [(10.0, 0.0), (11.0, 1.0)], a]) == [(0.0, 0.0), (10.0, 0.0),
                                                                 (11.0, 1.0)]


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
    walks = _crosswalk_walks(m)
    fallback = [w for w in walks if len(w.line) == 2]
    walks = [w for w in walks if len(w.line) >= 4]
    side_ends: dict = {}
    for w in m.walkways:
        if w.kind == "sidewalk":
            for p in (w.line[0], w.line[-1]):
                side_ends.setdefault((round(p[0], 2), round(p[1], 2)), 0)
    joined = between = 0
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
        if ST._dist(mid, ((p[0] + q[0]) / 2, (p[1] + q[1]) / 2)) >= 0.5:
            # (the crossings fix's fallback where a sidewalk does not reach the station: the
            # crossing between its leg's corners; the road curves fix's Vesper Bay had one, a
            # 49 m diagonal, its right sidewalk 40 m short where GEOS split its offset line:
            # none since the curves followups' `junctions._joined`)
            assert any(LineString([c_[:2] for c_ in w.line]).distance(
                LineString([a[:2], c[:2]])) < 2.0 for w in fallback), x.id
            between += 1
            continue
        if len(best.line) == 4:
            ends = (best.line[0], best.line[-1])
            joined += all((round(e[0], 2), round(e[1], 2)) in side_ends for e in ends)
            # (its tails square to the crosswalk: no run along the curb)
            dx, dy = c[0] - a[0], c[1] - a[1]
            L = math.hypot(dx, dy)
            for e, f in ((best.line[0], best.line[1]), (best.line[2], best.line[3])):
                along = abs((f[0] - e[0]) * dy - (f[1] - e[1]) * dx) / L
                assert along < 1.0, (x.id, along)
    assert joined >= 0.9 * len(xs) and between == 0, (joined, between)


def _crosswalk_walks(m) -> list:
    """The crosswalk walkways, the pieces a later split left (a link's foot on one; the road
    curves fix's Vesper Bay had a station stair's, `stn.the_stacks.2`, which the curves
    followups keep on the sidewalk) joined again end to end."""
    pieces: dict = {}
    for w in m.walkways:
        if w.kind == "crosswalk":
            pieces.setdefault((w.attrs or {}).get("split_of", w.id), []).append(w)
    out = []
    for root in sorted(pieces):
        ws = sorted(pieces[root], key=lambda w: w.id)
        line = list(ws[0].line)
        rest = ws[1:]
        while rest:
            for w in rest:
                if tuple(w.line[0][:2]) == tuple(line[-1][:2]):
                    line += list(w.line[1:])
                elif tuple(w.line[-1][:2]) == tuple(line[0][:2]):
                    line = list(w.line[:-1]) + line
                else:
                    continue
                rest.remove(w)
                break
            else:
                break
        # (the split point lies on the straight middle stretch: out again)
        keep = [line[0]] + [b for a, b, c in zip(line, line[1:], line[2:])
                            if abs((b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) *
                                   (c[0] - a[0])) > 0.02 * math.dist(a[:2], c[:2])] + \
            [line[-1]]
        out.append(ws[0].model_copy(update={"line": keep if len(ws) > 1 else line}))
    return out


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


def test_check_walk_roads_fails_a_diagonal_crossing_and_a_stair_on_a_crosswalk():
    """Curves followups: a crossing of one stretch run along a street's carriageway (the
    crossings fix's fallback between far corners: Vesper Bay's `cw.e637n26` on the road curves
    fix) fails, and so does a station's stair whose foot stands in a crosswalk's stripe
    (`stn.the_stacks.2` there)."""
    b, _, _ = built_sample(VESPER_BAY)
    m = b.model
    assert not NC.station_feet_on_crossings(m)
    d = m.model_dump(mode="json")
    seg = next(s for s in d["road_segments"] if s["road_class"] == "street" and
               not (s["cross_section"].get("median_m") or 0.0) and
               not any(p["z"] for p in s["z_profile"]) and
               ST._plen([tuple(p[:2]) for p in s["centerline"]]) > 60.0)
    pts = [tuple(p[:2]) for p in seg["centerline"]]
    L = ST._plen(pts)
    h = NC.carriageway_w(m.road_segments[[s.id for s in m.road_segments].index(seg["id"])]) / 2
    p0, t0 = ST._along(pts, L / 3)
    p1, t1 = ST._along(pts, 2 * L / 3)
    a = (p0[0] - t0[1] * h, p0[1] + t0[0] * h)
    e = (p1[0] + t1[1] * h, p1[1] - t1[0] * h)
    d["walkways"].append({"id": "wk.test", "kind": "crossing", "type": "walkway.crossing",
                          "line": [[a[0], a[1], 0.0], [e[0], e[1], 0.0]], "width_m": 2.0,
                          "neighbors": [], "attrs": {}})
    x = d["crosswalks"][0]
    mid = [(x["line"][0][0] + x["line"][1][0]) / 2, (x["line"][0][1] + x["line"][1][1]) / 2]
    d["walkways"].append({"id": "wk.stair", "kind": "stairs", "type": "walkway.stairs",
                          "line": [[mid[0], mid[1], 0.0], [mid[0] + 8.0, mid[1], -8.0]],
                          "width_m": 3.0, "neighbors": [], "attrs": {"station": "stn.test"}})
    c = NC.check_walk_roads(load_spec(VESPER_BAY).filled, CityModel.model_validate(d))
    text = " ".join(c.failures)
    assert not c.passed and "wk.test" in text and "wk.stair" in text and x["id"] in text
