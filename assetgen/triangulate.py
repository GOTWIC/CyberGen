"""Exact ear clipping of a polygon with holes on integer coordinates (scope sections 8, 10).

Every decision is an orientation test on Python integers, so the triangles are the same on
every machine and no rounding can make an ear go wrong. Holes (window openings in a wall,
courts in a roof) are bridged to the outer ring one at a time, the hole with the rightmost
vertex first, each to the nearest vertex its rightmost vertex sees (Eberly, "Triangulation
by Ear Clipping", 2002); the bridged ring is then clipped ear by ear in a fixed order.

`triangulate(outer, holes)` returns triangles as indices into the input vertices (the outer
ring's, then each hole's in turn), counterclockwise in the plane. A ring may be given in
either direction; a repeated closing point and consecutive duplicates are ignored. Straight
vertices (between their neighbors on one line) are dropped, unless `keep_straight`: then
every vertex is a corner of some triangle, so a face meets its neighbors without T-junctions
(AG1's roofs and caps, whose rings carry the facades' corner points).
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


def triangulate(outer, holes=(), keep_straight: bool = False) -> list[tuple[int, int, int]]:
    got = _prepare(outer, holes)
    if got is None:
        return []
    pts, ring = got
    return _clip(pts, ring, keep_straight)


def _prepare(outer, holes):
    """(points, the one ring with its holes bridged in, as point indices), or None where
    the outer ring has fewer than three vertices."""
    pts = [tuple(int(c) for c in p) for p in outer]
    rings = [_clean(outer, 0)]
    base = len(pts)
    for h in holes:
        pts += [tuple(int(c) for c in p) for p in h]
        rings.append(_clean(h, base))
        base += len(h)
    ring = rings[0]
    if len(ring) < 3:
        return None
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
    return pts, ring


def _clip(pts, ring: list[int], keep: bool = False) -> list[tuple[int, int, int]]:
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
            cut = a == c or not _between(a, c, b) or (alive > 3 and not keep)
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


# ---------------------------------------------------------------------------------------
# AG17: a face of M22's pavement map
# ---------------------------------------------------------------------------------------

def _incircle(a, b, c, d) -> int:
    """Sign of d against the circle through a, b, c (counterclockwise): positive inside."""
    adx, ady = a[0] - d[0], a[1] - d[1]
    bdx, bdy = b[0] - d[0], b[1] - d[1]
    cdx, cdy = c[0] - d[0], c[1] - d[1]
    det = ((adx * adx + ady * ady) * (bdx * cdy - cdx * bdy) -
           (bdx * bdx + bdy * bdy) * (adx * cdy - cdx * ady) +
           (cdx * cdx + cdy * cdy) * (adx * bdy - bdx * ady))
    return (det > 0) - (det < 0)


class _Tri:
    """A triangulation being refined: triangles (counterclockwise index triples), each
    directed edge's triangle, and the constrained edges (the face's boundary), never split
    or flipped."""

    def __init__(self, pts, tris, fixed):
        self.p = pts
        self.t: list = [tuple(t) for t in tris]
        self.he: dict = {}
        for i, t in enumerate(self.t):
            self._link(i, t)
        self.fixed = fixed
        self.last = 0

    def _link(self, i: int, t) -> None:
        a, b, c = t
        self.he[(a, b)] = i
        self.he[(b, c)] = i
        self.he[(c, a)] = i

    def _unlink(self, i: int) -> None:
        a, b, c = self.t[i]
        for e in ((a, b), (b, c), (c, a)):
            if self.he.get(e) == i:
                del self.he[e]

    def _put(self, i: int, t) -> None:
        if i < len(self.t):
            self._unlink(i)
            self.t[i] = t
        else:
            self.t.append(t)
        self._link(i, t)

    def _locate(self, q):
        """(triangle, where): where -1 strictly inside, k on its edge k (from vertex k to
        k + 1), or None (outside every triangle, or on a vertex)."""
        P = self.p
        i = self.last if self.last < len(self.t) else 0
        for _ in range(len(self.t) + 8):
            t = self.t[i]
            nxt, on, blocked = None, [], False
            for k in range(3):
                a, b = t[k], t[(k + 1) % 3]
                o = orient(P[a], P[b], q)
                if o < 0:
                    nxt = self.he.get((b, a))
                    blocked = nxt is None       # (past the boundary of a concave face)
                    break
                if o == 0:
                    on.append(k)
            if blocked:
                break
            if nxt is None:
                return self._where(i, on)
            i = nxt
        # (a walk that met the boundary or went round: every triangle in turn)
        for i, t in enumerate(self.t):
            os_ = [orient(P[t[k]], P[t[(k + 1) % 3]], q) for k in range(3)]
            if min(os_) >= 0:
                return self._where(i, [k for k in range(3) if os_[k] == 0])
        return None, None

    @staticmethod
    def _where(i: int, on: list):
        if not on:
            return i, -1
        if len(on) == 1:
            return i, on[0]
        return None, None       # (on a vertex)

    def insert(self, q) -> bool:
        """A point strictly inside the face: split the triangle it is in (or the two on the
        edge it lies on), then restore the Delaunay condition round it. False where it is
        not strictly inside (outside, on a vertex or on the boundary)."""
        i, where = self._locate(q)
        if i is None:
            return False
        a, b, c = self.t[i]
        if where >= 0:
            u, v = self.t[i][where], self.t[i][(where + 1) % 3]
            if (min(u, v), max(u, v)) in self.fixed:
                return False
            j = self.he.get((v, u))
            if j is None:
                return False
        k = len(self.p)
        self.p.append(q)
        if where < 0:
            self._put(i, (a, b, k))
            self._put(len(self.t), (b, c, k))
            self._put(len(self.t), (c, a, k))
            todo = [(a, b), (b, c), (c, a)]
        else:
            w = [x for x in self.t[i] if x not in (u, v)][0]
            x = [y for y in self.t[j] if y not in (u, v)][0]
            self._put(i, (u, k, w))
            self._put(len(self.t), (k, v, w))
            self._put(j, (v, k, x))
            self._put(len(self.t), (k, u, x))
            todo = [(v, w), (w, u), (u, x), (x, v)]
        self.last = i
        self._legalize(todo)
        return True

    def _flip(self, u: int, v: int) -> list | None:
        """Flip the edge u-v where its two triangles form a convex quad that breaks the
        Delaunay condition; the quad's outer edges, else None."""
        if (min(u, v), max(u, v)) in self.fixed:
            return None
        i, j = self.he.get((u, v)), self.he.get((v, u))
        if i is None or j is None:
            return None
        P = self.p
        a = [x for x in self.t[i] if x not in (u, v)][0]
        b = [x for x in self.t[j] if x not in (u, v)][0]
        if _incircle(P[u], P[v], P[a], P[b]) <= 0:
            return None
        if orient(P[a], P[b], P[u]) >= 0 or orient(P[b], P[a], P[v]) >= 0:
            return None         # (not convex)
        self._put(i, (a, u, b))
        self._put(j, (b, v, a))
        return [(u, b), (b, v), (v, a), (a, u)]

    def _legalize(self, todo: list) -> None:
        guard = 0
        limit = 256 * (len(self.t) + 16)
        while todo and guard < limit:
            guard += 1
            u, v = todo.pop()
            got = self._flip(u, v)
            if got:
                todo += got

    def delaunay(self) -> None:
        """Flip every edge that is not constrained until none breaks the condition (the ear
        clipper's fans become a Delaunay triangulation of the face)."""
        edges = sorted({(min(a, b), max(a, b)) for t in self.t
                        for a, b in ((t[0], t[1]), (t[1], t[2]), (t[2], t[0]))})
        self._legalize([e for e in edges[::-1] if e not in self.fixed])


def _touching(rings: list) -> list:
    """Rings where holes touch each other or the outer ring at a vertex, joined there into
    one ring that passes that vertex twice (a weakly simple ring the ear clipper takes);
    the rings as they are otherwise. Holes run clockwise, the outer ring counterclockwise."""
    outer = rings[0] if area2(rings[0]) > 0 else rings[0][::-1]
    holes = [h if area2(h) < 0 else h[::-1] for h in rings[1:] if len(h) >= 3]

    def splice(a: list, b: list):
        at = {p: i for i, p in enumerate(a)}
        for j, p in enumerate(b):
            i = at.get(p)
            if i is not None:
                return a[:i + 1] + b[j + 1:] + b[:j + 1] + a[i + 1:]
        return None
    changed = True
    while changed:
        changed = False
        for k, h in enumerate(holes):
            got = splice(outer, h)
            if got is not None:
                outer = got
                holes.pop(k)
                changed = True
                break
            for m in range(k + 1, len(holes)):
                got = splice(h, holes[m])
                if got is not None:
                    holes[k] = got
                    holes.pop(m)
                    changed = True
                    break
            if changed:
                break
    if len(holes) == len(rings) - 1 and outer == (rings[0] if area2(rings[0]) > 0
                                                  else rings[0][::-1]):
        return rings
    return [outer] + holes


def _clip_best(pts, ring: list[int]) -> list[tuple[int, int, int]]:
    """Ear clipping that always takes the ear with the shortest new diagonal (ties by
    position in the ring): a long ribbon comes out as a zigzag strip, not a fan of slivers
    from one vertex (which Delaunay flips would need O(n^2) steps to undo). Every vertex is
    kept (straight runs too, as `triangulate(..., keep_straight=True)`); where no ear is
    left, the rest goes to `_clip`."""
    import heapq
    n = len(ring)
    if n < 3:
        return []
    prev = [(k - 1) % n for k in range(n)]
    nxt = [(k + 1) % n for k in range(n)]
    alive = [True] * n
    count = n
    ver = [0] * n

    def ear(k):
        p, q = prev[k], nxt[k]
        a, b, c = pts[ring[p]], pts[ring[k]], pts[ring[q]]
        if orient(a, b, c) <= 0 or not _empty(pts, ring, nxt, k, p, q, a, b, c):
            return None
        return (c[0] - a[0]) ** 2 + (c[1] - a[1]) ** 2
    heap: list = []
    for k in range(n):
        d = ear(k)
        if d is not None:
            heap.append((d, k, 0))
    heapq.heapify(heap)
    out: list[tuple[int, int, int]] = []
    while count > 3 and heap:
        d, k, v = heapq.heappop(heap)
        if not alive[k] or v != ver[k]:
            continue
        p, q = prev[k], nxt[k]
        out.append((ring[p], ring[k], ring[q]))
        alive[k] = False
        nxt[p], prev[q] = q, p
        count -= 1
        for m in (p, q):
            ver[m] += 1
            dm = ear(m)
            if dm is not None:
                heapq.heappush(heap, (dm, m, ver[m]))
    if count > 3:
        k = next(i for i in range(n) if alive[i])
        rest = [k]
        j = nxt[k]
        while j != k:
            rest.append(j)
            j = nxt[j]
        out += _clip(pts, [ring[i] for i in rest], True)
    elif count == 3:
        k = next(i for i in range(n) if alive[i])
        p, q = prev[k], nxt[k]
        if orient(pts[ring[p]], pts[ring[k]], pts[ring[q]]) > 0:
            out.append((ring[p], ring[k], ring[q]))
    return out


def triangulate_face(rings, steiner=()) -> tuple[list, list[tuple[int, int, int]]]:
    """AG17: triangles of a face of M22's pavement map on its integer millimeters: the
    boundary's vertices in order and never split (every one a corner, straight runs too;
    holes bridged; the ear with the shortest diagonal first, `_clip_best`), Steiner points (the face's interior samples) inserted strictly inside,
    and the Delaunay condition restored by flips across every edge that is not boundary.
    Returns (points, triangles): the rings' vertices in order (outer ring, then each hole),
    then the Steiner points kept (those not strictly inside are left out); triangles
    counterclockwise. Exact: orientation and in-circle tests on Python integers."""
    rings = [[(int(p[0]), int(p[1])) for p in r] for r in rings]
    if not rings or len(rings[0]) < 3:
        return [], []
    rings = _touching(rings)
    pts = [p for r in rings for p in r]
    got = _prepare(rings[0], rings[1:])
    tris = _clip_best(got[0], got[1]) if got is not None else []
    fixed = set()
    base = 0
    for r in rings:
        idx = _clean(r, base)
        for k in range(len(idx)):
            a, b = idx[k], idx[(k + 1) % len(idx)]
            if pts[a] != pts[b]:
                fixed.add((min(a, b), max(a, b)))
        base += len(r)
    T = _Tri(list(pts), tris, fixed)
    T.delaunay()
    seen = set(pts)
    for q in steiner:
        q = (int(q[0]), int(q[1]))
        if q in seen:
            continue
        if T.insert(q):
            seen.add(q)
    return T.p, T.t
