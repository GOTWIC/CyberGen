"""The exact integer triangulator: areas add up exactly, every triangle counterclockwise,
holes bridged, invalid input refused, the same triangles every time."""

import random

import pytest
from shapely.geometry import Polygon

from assetgen import canon as C
from assetgen.triangulate import TriangulationError, area2, orient, triangulate
from citygen import dmath as M

from agtools import golden


def check(outer, holes=()):
    pts = [tuple(p) for p in outer] + [tuple(p) for h in holes for p in h]
    tris = triangulate(outer, holes)
    total = sum(orient(pts[a], pts[b], pts[c]) for a, b, c in tris)
    assert total == abs(area2(outer)) - sum(abs(area2(h)) for h in holes)
    assert all(orient(pts[a], pts[b], pts[c]) > 0 for a, b, c in tris)
    return tris


def rect(x0, y0, x1, y1):
    return [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]


def test_square_and_orientation():
    t = check(rect(0, 0, 10, 10))
    assert len(t) == 2
    assert len(check(rect(0, 0, 10, 10)[::-1])) == 2


def test_wall_with_windows():
    """A facade with a row of windows: n + 2h - 2 triangles."""
    holes = [rect(x, 900, x + 1200, 2700) for x in range(600, 10800, 2000)]
    t = check(rect(0, 0, 12000, 3600), holes)
    assert len(t) == 4 + 4 * len(holes) + 2 * len(holes) - 2


def test_window_grid():
    holes = [rect(x, y, x + 600, y + 800) for x in range(300, 30300, 1000)
             for y in (300, 1500)]
    check(rect(0, 0, 30300, 2700), holes)


def test_collinear_and_comb():
    comb = [(0, 0), (1000, 0), (2000, 0), (2000, 1000)] + \
        [(x, 1000 if (x // 100) % 2 else 300) for x in range(1900, 0, -100)] + [(0, 1000)]
    check(comb)
    check([(0, 0), (5, 0), (10, 0), (10, 5), (10, 10), (0, 10), (0, 5)])


def test_holes_in_line():
    """Holes whose edges line up with each other and with the bridge rays."""
    holes = [rect(200, 200, 400, 400), rect(200, 600, 400, 800), rect(600, 200, 800, 800)]
    check(rect(0, 0, 1000, 1000), holes)


def test_random_polygons_with_holes():
    rnd = random.Random(1)
    done = 0
    for _ in range(1500):
        n = rnd.randint(3, 30)
        R = [rnd.randint(500, 1000) for _ in range(n)]
        outer = [(int(R[i] * M.cos(2 * M.PI * i / n)),
                  int(R[i] * M.sin(2 * M.PI * i / n))) for i in range(n)]
        holes = []
        if rnd.random() < 0.7:
            m, r = rnd.randint(3, 8), rnd.randint(50, 200)
            holes = [[(int(r * M.cos(2 * M.PI * i / m) + rnd.randint(-100, 100)),
                       int(r * M.sin(2 * M.PI * i / m))) for i in range(m)]]
            if rnd.random() < 0.5:
                holes.append([(x + 300, y) for x, y in rect(0, 0, 60, 60)])
        if not Polygon(outer, holes).is_valid or \
                any(not Polygon(h).is_valid for h in holes):
            continue
        check(outer, holes)
        done += 1
    assert done > 1000


def test_hole_touching_the_outline_is_refused():
    with pytest.raises(TriangulationError):
        triangulate(rect(0, 0, 10, 10), [rect(2, 0, 4, 3)])


def test_golden():
    """The same triangles on every machine (Mac = x86)."""
    holes = [rect(x, y, x + 600, y + 800) for x in range(300, 9300, 1000) for y in (300, 1500)]
    t1 = triangulate(rect(0, 0, 9300, 2700), holes)
    rnd = random.Random(7)
    n = 40
    star = [(int(rnd.randint(500, 1000) * M.cos(2 * M.PI * i / n)),
             int(rnd.randint(500, 1000) * M.sin(2 * M.PI * i / n))) for i in range(n)]
    t2 = triangulate(star, [rect(-50, -50, 50, 50)])
    assert C.digest([t1, t2]) == golden()["triangulate"]


# -- AG17: a face of M22's pavement map ----------------------------------------------------

def _face_check(rings, steiner=()):
    from assetgen.triangulate import triangulate_face
    pts, tris = triangulate_face(rings, steiner)
    total = sum(orient(pts[a], pts[b], pts[c]) for a, b, c in tris)
    assert total == abs(area2(rings[0])) - sum(abs(area2(h)) for h in rings[1:])
    assert all(orient(pts[a], pts[b], pts[c]) > 0 for a, b, c in tris)
    # every boundary segment is a triangle edge, never split
    edges = {}
    for a, b, c in tris:
        for u, v in ((a, b), (b, c), (c, a)):
            edges[(pts[u], pts[v])] = edges.get((pts[u], pts[v]), 0) + 1
    for r in rings:
        rr = r if (area2(r) > 0) == (r is rings[0]) else r[::-1]
        for k in range(len(rr)):
            p, q = tuple(rr[k]), tuple(rr[(k + 1) % len(rr)])
            assert edges.get((p, q), 0) == 1, (p, q)
    return pts, tris


def test_a_face_keeps_every_boundary_vertex_and_its_samples():
    # a band with vertices along both long edges (collinear runs) and interior samples
    ring = [(x, 0) for x in range(0, 40001, 4000)] + \
        [(x, 7000) for x in range(40000, -1, -4000)]
    ring = [p for i, p in enumerate(ring) if i == 0 or p != ring[i - 1]]
    smp = [(x, 3500) for x in range(2000, 40000, 4000)] + [(0, 3500), (40000, 0)]
    pts, tris = _face_check([ring], smp)
    used = {pts[i] for t in tris for i in t}
    assert set(ring) <= used                                   # nothing dropped
    assert {(x, 3500) for x in range(2000, 40000, 4000)} <= used   # inside: inserted
    assert (0, 3500) not in used                               # on the boundary: left out
    # Delaunay: no sliver fans along the band
    assert max(len([t for t in tris if i in t]) for i in range(len(pts))) <= 8


def test_a_face_with_holes_touching_at_a_vertex():
    outer = rect(0, 0, 20000, 20000)
    h1 = [(5000, 5000), (5000, 10000), (10000, 10000), (10000, 5000)]
    h2 = [(10000, 10000), (10000, 15000), (15000, 15000), (15000, 10000)]
    _face_check([outer, h1, h2], [(2000, 2000), (17000, 3000)])
    # a hole touching the outer ring at one of its vertices
    h3 = [(0, 8000), (4000, 12000), (4000, 8000)]
    _face_check([[(0, 0), (20000, 0), (20000, 20000), (0, 20000), (0, 8000)], h3])


def test_face_triangles_are_the_same_every_time():
    from assetgen.triangulate import triangulate_face
    rnd = random.Random(7)
    ring = [(int(20000 * M.cos(2 * M.PI * k / 40)) + rnd.randrange(-300, 300),
             int(20000 * M.sin(2 * M.PI * k / 40)) + rnd.randrange(-300, 300)) for k in range(40)]
    smp = [(x, y) for x in range(-16000, 16001, 2000) for y in range(-16000, 16001, 2000)
           if x * x + y * y < 15000 ** 2]
    a = triangulate_face([ring], smp)
    assert a == triangulate_face([ring], smp)
    _face_check([ring], smp)
