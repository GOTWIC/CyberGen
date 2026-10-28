"""Plane polygons on integer millimeters: rings, exact tests, offset strips, convex pieces.

Every decision is exact (orientation tests on Python integers); offsets are computed in
IEEE doubles in a fixed order and rounded to the millimeter once, then checked exactly
(simple, same orientation, edges not reversed), so a strip that would fold is refused, not
drawn wrong.
"""

from __future__ import annotations

import math

from ..triangulate import TriangulationError, area2, orient, triangulate


def mm_ring(points) -> list[tuple[int, int]]:
    """A ring in meters to integer millimeters, without a closing point or repeats."""
    out: list[tuple[int, int]] = []
    for p in points:
        q = (int(round(p[0] * 1000.0)), int(round(p[1] * 1000.0)))
        if not out or q != out[-1]:
            out.append(q)
    while len(out) > 1 and out[0] == out[-1]:
        out.pop()
    return out


def clean(ring) -> list[tuple[int, int]]:
    out: list[tuple[int, int]] = []
    for q in ring:
        q = (int(q[0]), int(q[1]))
        if not out or q != out[-1]:
            out.append(q)
    while len(out) > 1 and out[0] == out[-1]:
        out.pop()
    return out


def _on_seg(a, b, p) -> bool:
    return min(a[0], b[0]) <= p[0] <= max(a[0], b[0]) and \
        min(a[1], b[1]) <= p[1] <= max(a[1], b[1])


def seg_hit(a, b, c, d) -> bool:
    """Closed segments a-b and c-d share a point."""
    o1, o2, o3, o4 = orient(a, b, c), orient(a, b, d), orient(c, d, a), orient(c, d, b)
    if ((o1 > 0) != (o2 > 0)) and o1 != 0 and o2 != 0 and \
            ((o3 > 0) != (o4 > 0)) and o3 != 0 and o4 != 0:
        return True
    return (o1 == 0 and _on_seg(a, b, c)) or (o2 == 0 and _on_seg(a, b, d)) or \
        (o3 == 0 and _on_seg(c, d, a)) or (o4 == 0 and _on_seg(c, d, b))


def is_simple(ring) -> bool:
    """No zero-length edge and no two edges meeting except neighbors at their shared
    vertex."""
    n = len(ring)
    if n < 3:
        return False
    for i in range(n):
        if ring[i] == ring[(i + 1) % n]:
            return False
    box = []
    for i in range(n):
        a, b = ring[i], ring[(i + 1) % n]
        box.append((min(a[0], b[0]), min(a[1], b[1]), max(a[0], b[0]), max(a[1], b[1])))
    for i in range(n):
        a, b = ring[i], ring[(i + 1) % n]
        bi = box[i]
        for j in range(i + 1, n):
            if j == i + 1 or (i == 0 and j == n - 1):
                # neighbors: only their shared vertex in common (no folding back)
                c = ring[(j + 1) % n] if j == i + 1 else ring[j]
                p = b if j == i + 1 else a
                q = a if j == i + 1 else b
                if orient(q, p, c) == 0 and (c[0] - p[0]) * (q[0] - p[0]) + \
                        (c[1] - p[1]) * (q[1] - p[1]) > 0:
                    return False
                continue
            bj = box[j]
            if bj[0] > bi[2] or bj[2] < bi[0] or bj[1] > bi[3] or bj[3] < bi[1]:
                continue
            if seg_hit(a, b, ring[j], ring[(j + 1) % n]):
                return False
    return True


def rings_apart(r1, r2) -> bool:
    """No edge of r1 meets an edge of r2."""
    for i in range(len(r1)):
        a, b = r1[i], r1[(i + 1) % len(r1)]
        for j in range(len(r2)):
            if seg_hit(a, b, r2[j], r2[(j + 1) % len(r2)]):
                return False
    return True


def inside(p, ring) -> int:
    """1 strictly inside, 0 on the boundary, -1 outside (exact crossing number)."""
    n = len(ring)
    c = False
    for i in range(n):
        a, b = ring[i], ring[(i + 1) % n]
        if orient(a, b, p) == 0 and _on_seg(a, b, p):
            return 0
        if (a[1] > p[1]) != (b[1] > p[1]):
            # x of the crossing compared exactly: p.x < a.x + (p.y-a.y)(b.x-a.x)/(b.y-a.y)
            lhs = (p[0] - a[0]) * (b[1] - a[1])
            rhs = (p[1] - a[1]) * (b[0] - a[0])
            if (lhs < rhs) == (b[1] > a[1]):
                c = not c
    return 1 if c else -1


def in_poly(p, rings) -> int:
    """Against an exterior and holes: 1 inside, 0 on a boundary, -1 outside."""
    r = inside(p, rings[0])
    if r <= 0:
        return r
    for h in rings[1:]:
        k = inside(p, h)
        if k == 0:
            return 0
        if k == 1:
            return -1
    return 1


# ---------------------------------------------------------------------------
# Offsets: a ring whose solid lies to the left of every edge (exterior counterclockwise,
# holes clockwise); d > 0 moves an edge outward (right), d < 0 into the solid.
# ---------------------------------------------------------------------------

def _dir(a, b):
    dx, dy = b[0] - a[0], b[1] - a[1]
    L = math.sqrt(dx * dx + dy * dy)
    return dx / L, dy / L


MITER = 1.5          # a miter longer than this many offsets is beveled


def _corner(p, u0, d0, u1, d1):
    """Where the edge before p (direction u0) moved by d0 meets the edge after p (u1) moved
    by d1: (end of the first, start of the second), one point for a miter, two for a bevel
    (a convex corner whose miter would run past MITER times the offset); None when the edges
    are parallel with different offsets."""
    n0 = (u0[1], -u0[0])
    n1 = (u1[1], -u1[0])
    q1 = (p[0] + n0[0] * d0, p[1] + n0[1] * d0)
    q2 = (p[0] + n1[0] * d1, p[1] + n1[1] * d1)
    cr = u0[0] * u1[1] - u0[1] * u1[0]          # > 0: a left turn
    if abs(cr) < 1e-9:
        if abs(d0 - d1) > 0.5 or u0[0] * u1[0] + u0[1] * u1[1] < 0:
            return None
        return q1, q1
    t = (u1[0] * (q2[1] - q1[1]) - u1[1] * (q2[0] - q1[0])) / -cr
    x, y = q1[0] + t * u0[0], q1[1] + t * u0[1]
    dx, dy = x - p[0], y - p[1]
    dd = max(abs(d0), abs(d1))
    if math.sqrt(dx * dx + dy * dy) > MITER * dd + 2.0:
        outward = (d0 + d1) > 0
        if (cr > 0) == outward:
            return q1, q2                          # bevel the sharp corner
        return None
    return (x, y), (x, y)


def _ipt(p):
    return (int(round(p[0])), int(round(p[1])))


def offset_ring(ring, d: list[float]):
    """The closed ring with edge i moved by d[i] (mm); None if it does not stay simple and
    in the same orientation with every edge pointing the same way."""
    n = len(ring)
    us = [_dir(ring[i], ring[(i + 1) % n]) for i in range(n)]
    ends, starts = [None] * n, [None] * n
    for i in range(n):
        c = _corner(ring[i], us[i - 1], d[i - 1], us[i], d[i])
        if c is None:
            return None
        ends[i - 1], starts[i] = _ipt(c[0]), _ipt(c[1])
    pts = []
    for i in range(n):
        for q in (ends[i - 1], starts[i]):
            if not pts or pts[-1] != q:
                pts.append(q)
    if len(pts) > 1 and pts[0] == pts[-1]:
        pts.pop()
    for i in range(n):
        if not _same_dir(ring[i], ring[(i + 1) % n], starts[i], ends[i]):
            return None
    return pts


def offset_chain(ring, i0: int, m: int, d: float, setback: float):
    """The open chain along edges i0 .. i0+m-1 (mod n) moved by d (mm), its two ends moved
    `setback` mm in along the chain; None where it folds."""
    n = len(ring)
    idx = [(i0 + k) % n for k in range(m + 1)]
    us = [_dir(ring[idx[k]], ring[idx[k + 1]]) for k in range(m)]
    a, u = ring[idx[0]], us[0]
    starts = [_ipt((a[0] + u[1] * d + u[0] * setback, a[1] - u[0] * d + u[1] * setback))]
    ends = []
    for k in range(1, m):
        c = _corner(ring[idx[k]], us[k - 1], d, us[k], d)
        if c is None:
            return None
        ends.append(_ipt(c[0]))
        starts.append(_ipt(c[1]))
    b, u = ring[idx[m]], us[m - 1]
    ends.append(_ipt((b[0] + u[1] * d - u[0] * setback, b[1] - u[0] * d - u[1] * setback)))
    for k in range(m):
        if not _same_dir(ring[idx[k]], ring[idx[k + 1]], starts[k], ends[k]):
            return None
    out = []
    for k in range(m):
        for q in (starts[k], ends[k]):
            if not out or out[-1] != q:
                out.append(q)
    return out


def _same_dir(a, b, p, q) -> bool:
    if p == q:
        return False
    return (b[0] - a[0]) * (q[0] - p[0]) + (b[1] - a[1]) * (q[1] - p[1]) > 0


def strip(ring, i0: int, m: int, d_out: float, d_in: float, setback: float):
    """The plan polygon between the chain of edges i0 .. i0+m-1 moved by d_out and by d_in
    (d_out > d_in): a simple ring (counterclockwise), or None. With m equal to the ring's
    edge count, the annulus between the two closed offsets: (outer, hole) or None."""
    n = len(ring)
    if m >= n:
        outer = ring if d_out == 0 else offset_ring(ring, [d_out] * n)
        inner = ring if d_in == 0 else offset_ring(ring, [d_in] * n)
        if outer is None or inner is None:
            return None
        if not is_simple(outer) or not is_simple(inner) or not rings_apart(outer, inner):
            return None
        o, h = (outer, inner)
        if area2(o) < 0:          # a hole ring: the solid's band lies outside it
            o, h = h, o
        o = o if area2(o) > 0 else o[::-1]
        h = h if area2(h) < 0 else h[::-1]
        if inside(h[0], o) != 1:
            return None
        return o, h
    a = offset_chain(ring, i0, m, d_out, setback) if d_out != 0 or setback else \
        [ring[(i0 + k) % n] for k in range(m + 1)]
    b = offset_chain(ring, i0, m, d_in, setback) if d_in != 0 or setback else \
        [ring[(i0 + k) % n] for k in range(m + 1)]
    if a is None or b is None:
        return None
    poly = clean(a + b[::-1])
    if len(poly) < 3 or not is_simple(poly):
        return None
    if area2(poly) < 0:
        poly = poly[::-1]
    return poly, None


# ---------------------------------------------------------------------------
# Convex pieces (simple collision)
# ---------------------------------------------------------------------------

def convex(ring) -> bool:
    n = len(ring)
    s = None
    for i in range(n):
        o = orient(ring[i - 1], ring[i], ring[(i + 1) % n])
        if o == 0:
            continue
        if s is None:
            s = o > 0
        elif (o > 0) != s:
            return False
    return True


def convex_pieces(outer, holes=()) -> list[list[tuple[int, int]]]:
    """Convex polygons covering the polygon exactly: its triangles merged across diagonals
    while the union stays convex (Hertel and Mehlhorn), in a fixed order."""
    o = outer if area2(outer) > 0 else outer[::-1]
    if not holes and convex(o):
        return [list(o)]
    try:
        tris = triangulate(o, [h for h in holes])
    except TriangulationError:
        return [list(o)]
    pts = list(o) + [p for h in holes for p in h]
    polys: list[list[int] | None] = [list(t) for t in tris]
    changed = True
    while changed:
        changed = False
        edge: dict[tuple, int] = {}
        for k, pg in enumerate(polys):
            if pg is None:
                continue
            for i in range(len(pg)):
                edge[(pg[i], pg[(i + 1) % len(pg)])] = k
        for (a, b), k in sorted(edge.items()):
            j = edge.get((b, a))
            if j is None or j <= k or polys[k] is None or polys[j] is None:
                continue
            p, q = polys[k], polys[j]
            ia = p.index(a)
            # p: ... a b ...; q: ... b a ...; merged: p from b round to a, then q after a to b
            ib = q.index(b)
            rp = p[(ia + 1):] + p[:(ia + 1)]          # starts at b, ends at a
            rq = q[(ib + 1):] + q[:(ib + 1)]          # starts at a, ends at b
            merged = rp + rq[1:-1]
            ring = [pts[i] for i in merged]
            if convex(ring) and area2(ring) > 0 and len(set(merged)) == len(merged):
                polys[k], polys[j] = merged, None
                changed = True
                break
    out = []
    for pg in polys:
        if pg is not None:
            out.append([pts[i] for i in pg])
    return out
