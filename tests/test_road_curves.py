"""The road curves fix: arcs cut to G.ROAD_SAG_M of chord sag, local roads' corners on arcs."""

import math

from citygen import dmath as M
from citygen import geom as G
from citygen import junctions as JN
from citygen import pavement as PV
from citygen import roads as RD
from citygen import streets as ST


def _sag(pts, center, r):
    """The largest chord sag of a polyline from the circle (center, r)."""
    worst = 0.0
    for a, b in zip(pts, pts[1:]):
        mx, my = (a[0] + b[0]) / 2.0, (a[1] + b[1]) / 2.0
        worst = max(worst, r - math.hypot(mx - center[0], my - center[1]))
    return worst


def test_arc_steps_keep_the_sag():
    for r in (3.0, 12.0, 45.0, 160.0, 420.0):
        for sweep in (0.1, 0.5, math.pi / 2, 1.5 * math.pi, 2 * math.pi):
            n = G.arc_steps(r, sweep)
            assert r * (1.0 - math.cos(sweep / n / 2.0)) <= G.ROAD_SAG_M + 1e-12
    assert G.arc_steps(0.01, 1.0) == 1 and G.arc_steps(10.0, 0.0) == 1
    assert G.arc_steps(10.0, -1.0) == G.arc_steps(10.0, 1.0)


def test_junction_corner_arc_within_the_sag():
    O, r = (0.0, 0.0), 12.0
    A, B = (r, 0.0), (0.0, r)
    pts = [A] + JN._arc(O, A, B, r) + [B]
    assert _sag(pts, O, r) <= G.ROAD_SAG_M + 1e-9
    assert len(pts) - 1 >= G.arc_steps(r, math.pi / 2)


def test_bulb_and_m1b_fillet_within_the_sag():
    ring = list(PV._circle((5.0, -3.0), 14.0).exterior.coords)
    assert _sag(ring, (5.0, -3.0), 14.0) <= G.ROAD_SAG_M + 1e-9
    # an M1b corner: its arc's chords keep the outer edge (r + hw) within the sag
    pts = [(0.0, 0.0), (400.0, 0.0), (400.0, 400.0)]
    radii, tans = RD._fillet_radii(pts, 160.0, False, 0.0)
    line = list(RD._arc_line(pts, radii, tans, False, hw=14.0).coords)
    arc = [p for p in line if 0.0 < p[0] < 400.0 and 0.0 < p[1] < 400.0] + [line[-2]]
    O = (400.0 - 160.0, 160.0)
    assert _sag(arc, O, 160.0) * (160.0 + 14.0) / 160.0 <= G.ROAD_SAG_M + 1e-6
    # transit keeps M1b's steps (no hw)
    assert len(RD._arc_line(pts, radii, tans, False).coords) < len(line)


def test_round_corners_on_arcs():
    pts = [(0.0, 0.0), (8.0, 0.0), (15.88, 1.39), (23.5, 4.0), (40.0, 20.0), (60.0, 20.0)]
    out = ST.round_corners(pts, 5.0)
    assert out[0] == pts[0] and out[-1] == pts[-1]
    assert len(out) > len(pts)
    # every vertex of the result turns little: chords within the sag of their arc
    for a, b, c in zip(out, out[1:], out[2:]):
        u = ST._unit(b[0] - a[0], b[1] - a[1])
        v = ST._unit(c[0] - b[0], c[1] - b[1])
        assert ST._turn_deg(u, v) < 12.0
    # no point strays more than ROUND_DEV_M (and the grid) from the polyline
    from shapely.geometry import LineString, Point
    line = LineString(pts)
    assert max(line.distance(Point(p)) for p in out) <= ST.ROUND_DEV_M + 0.01
    # rounded again it moves by no more than the sag (held roads in a regeneration are not
    # rounded again at all, `round_edges`)
    again = ST.round_corners(out, 5.0)
    assert max(LineString(out).distance(Point(p)) for p in again) <= 0.021
    # sharp corners and roads too wide for the arc stay
    sq = [(0.0, 0.0), (30.0, 0.0), (30.0, 30.0)]
    assert ST.round_corners(sq, 4.0) == sq
    assert ST.round_corners(pts, 100.0) == pts
    assert ST.round_corners([(0.0, 0.0), (5.0, 0.0)], 4.0) == [(0.0, 0.0), (5.0, 0.0)]
    assert float(M.tan(0.0)) == 0.0
