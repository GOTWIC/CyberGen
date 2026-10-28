"""Exact ear clipping of a polygon with holes on integer coordinates (scope sections 8, 10).

Every decision is an orientation test on Python integers, so the triangles are the same on
every machine and no rounding can make an ear go wrong. Holes (window openings in a wall,
courts in a roof) are bridged to the outer ring one at a time, the hole with the rightmost
vertex first, each to the nearest vertex its rightmost vertex sees (Eberly, "Triangulation
by Ear Clipping", 2002); the bridged ring is then clipped ear by ear in a fixed order.

`triangulate(outer, holes)` returns triangles as indices into the input vertices (the outer
ring's, then each hole's in turn), counterclockwise in the plane. A ring may be given in
either direction; a repeated closing point and consecutive duplicates are ignored.
"""

from __future__ import annotations


class TriangulationError(ValueError):
    pass


def orient(a, b, c) -> int:
    """Twice the signed area of a, b, c (counterclockwise positive), exact."""
    return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])


def area2(pts) -> int:
    s = 0
    n = len(pts)
    for i in range(n):
        x0, y0 = pts[i]
        x1, y1 = pts[(i + 1) % n]
        s += x0 * y1 - x1 * y0
    return s


def _clean(ring, base: int) -> list[int]:
    """Indices (offset by base) of a ring without its closing point or repeats."""
    pts = [tuple(p) for p in ring]
    n = len(pts)
    if n > 1 and pts[0] == pts[-1]:
        n -= 1
    out = []
    for i in range(n):
        if not out or pts[i] != pts[out[-1] - base]:
            out.append(base + i)
    while len(out) > 1 and pts[out[-1] - base] == pts[out[0] - base]:
        out.pop()
    return out


def _between(a, b, p) -> bool:
    """p strictly inside the segment a-b, given that the three are collinear."""
    if a[0] != b[0]:
        return min(a[0], b[0]) < p[0] < max(a[0], b[0])
    return min(a[1], b[1]) < p[1] < max(a[1], b[1])


def _crosses(m, v, a, b) -> bool:
    """Whether the segment a-b blocks the segment m-v anywhere but at m and v."""
    o1, o2 = orient(m, v, a), orient(m, v, b)
    o3, o4 = orient(a, b, m), orient(a, b, v)
    if ((o1 > 0 and o2 < 0) or (o1 < 0 and o2 > 0)) and \
            ((o3 > 0 and o4 < 0) or (o3 < 0 and o4 > 0)):
        return True
    for p in (a, b):
        if p != m and p != v and orient(m, v, p) == 0 and _between(m, v, p):
            return True
    for p in (m, v):
        if p != a and p != b and orient(a, b, p) == 0 and _between(a, b, p):
            return True
    return False


def _sees(pts, ring: list[int], i: int, m) -> bool:
    """Whether direction v -> m points strictly into the polygon at ring position i."""
    p, v, n = pts[ring[i - 1]], pts[ring[i]], pts[ring[(i + 1) % len(ring)]]
    if orient(p, v, n) > 0:
        return orient(p, v, m) > 0 and orient(v, n, m) > 0
    return orient(p, v, m) > 0 or orient(v, n, m) > 0


def _bridge(pts, ring: list[int], hole: list[int], others: list[list[int]]) -> list[int]:
    """The ring with the hole spliced in at the nearest vertex its rightmost vertex sees."""
    j = max(range(len(hole)), key=lambda k: (pts[hole[k]][0], -pts[hole[k]][1], -hole[k]))
    m = pts[hole[j]]
    order = sorted(range(len(ring)), key=lambda i: (
        (pts[ring[i]][0] - m[0]) ** 2 + (pts[ring[i]][1] - m[1]) ** 2,
        pts[ring[i]][0] < m[0], i))
    edges = [(ring[k], ring[(k + 1) % len(ring)]) for k in range(len(ring))]
    for h in [hole] + others:
        edges += [(h[k], h[(k + 1) % len(h)]) for k in range(len(h))]
    for i in order:
        v = pts[ring[i]]
        if v == m or not _sees(pts, ring, i, m):
            continue
        if any(_crosses(m, v, pts[a], pts[b]) for a, b in edges):
            continue
        loop = hole[j:] + hole[:j + 1]
        return ring[:i + 1] + loop + ring[i:]
    raise TriangulationError("no vertex of the outer ring sees the hole")


def triangulate(outer, holes=()) -> list[tuple[int, int, int]]:
    pts = [tuple(int(c) for c in p) for p in outer]
    rings = [_clean(outer, 0)]
    base = len(pts)
    for h in holes:
        pts += [tuple(int(c) for c in p) for p in h]
        rings.append(_clean(h, base))
        base += len(h)
    ring = rings[0]
    if len(ring) < 3:
        return []
    if area2([pts[i] for i in ring]) < 0:
        ring = ring[::-1]
    hs = []
    for h in rings[1:]:
        if len(h) < 3:
            continue
        a = area2([pts[i] for i in h])
        if a == 0:
            continue
        hs.append(h[::-1] if a > 0 else h)
    hs.sort(key=lambda h: (-max(pts[i][0] for i in h), min(h)))
    for k, h in enumerate(hs):
        ring = _bridge(pts, ring, h, hs[k + 1:])
    return _clip(pts, ring)


def _clip(pts, ring: list[int]) -> list[tuple[int, int, int]]:
    n = len(ring)
    prev = [(k - 1) % n for k in range(n)]
    nxt = [(k + 1) % n for k in range(n)]
    alive = n
    out: list[tuple[int, int, int]] = []
    k = 0
    stall = 0
    while alive > 3:
        p, q = prev[k], nxt[k]
        a, b, c = pts[ring[p]], pts[ring[k]], pts[ring[q]]
        o = orient(a, b, c)
        cut = False
        if o == 0:
            cut = a == c or not _between(a, c, b) or alive > 3
            if cut:
                # a straight or folded-back vertex: drop it, no triangle
                nxt[p], prev[q] = q, p
                alive -= 1
                k, stall = p, 0
                continue
        if o > 0 and _empty(pts, ring, nxt, k, p, q, a, b, c):
            out.append((ring[p], ring[k], ring[q]))
            nxt[p], prev[q] = q, p
            alive -= 1
            k, stall = p, 0
            continue
        k = q
        stall += 1
        if stall > alive:
            raise TriangulationError("no ear left: the polygon is not simple")
    p, q = prev[k], nxt[k]
    if orient(pts[ring[p]], pts[ring[k]], pts[ring[q]]) > 0:
        out.append((ring[p], ring[k], ring[q]))
    return out


def _empty(pts, ring, nxt, k, p, q, a, b, c) -> bool:
    """No other reflex or straight vertex inside or on the triangle a, b, c (vertices at
    the triangle's own corners, the bridges' doubles, do not count)."""
    j = nxt[q]
    while j != p:
        v = pts[ring[j]]
        if v != a and v != b and v != c:
            if orient(a, b, v) >= 0 and orient(b, c, v) >= 0 and orient(c, a, v) >= 0:
                return False
        j = nxt[j]
    return True
