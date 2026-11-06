"""M22: triangles of a pavement face (the blockout and the height checks draw a face so):
its boundary's vertices in order, never split (holes bridged to the outer ring), its interior
samples inserted strictly inside, with Lawson flips across the edges that are not boundary.
Exact integer orientation and in-circle tests on the 1 mm grid, so the triangles are the
same on every machine."""

from __future__ import annotations

CELL = 4000     # mm: the reflex vertex hash


def _orient(a, b, c) -> int:
    v = (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])
    return (v > 0) - (v < 0)


def _area2(r) -> int:
    s = 0
    n = len(r)
    for i in range(n):
        s += r[i][0] * r[(i + 1) % n][1] - r[(i + 1) % n][0] * r[i][1]
    return s


def _cross(p, q, a, b) -> bool:
    """Whether segments pq and ab cross at a point inside both (not at an end)."""
    o1, o2 = _orient(p, q, a), _orient(p, q, b)
    o3, o4 = _orient(a, b, p), _orient(a, b, q)
    return o1 * o2 < 0 and o3 * o4 < 0


def _bridge(outer: list, holes: list) -> list:
    """One ring: every hole joined to the outer ring by a two-way cut from its rightmost
    vertex to the nearest outer vertex it sees (no edge crossed)."""
    ring = list(outer)
    for h in sorted(holes, key=lambda h: -max(p[0] for p in h)):
        k = max(range(len(h)), key=lambda i: (h[i][0], -h[i][1]))
        M = h[k]
        others = [x for x in holes if x is not h]
        edges = [(ring[i], ring[(i + 1) % len(ring)]) for i in range(len(ring))]
        for o in others:
            edges += [(o[i], o[(i + 1) % len(o)]) for i in range(len(o))]
        edges += [(h[i], h[(i + 1) % len(h)]) for i in range(len(h))]
        order = sorted(range(len(ring)), key=lambda i: ((ring[i][0] - M[0]) ** 2 +
                                                        (ring[i][1] - M[1]) ** 2, i))
        best = order[0]
        for i in order:
            if not any(_cross(M, ring[i], a, b) for a, b in edges):
                best = i
                break
        hh = h[k:] + h[:k]
        ring = ring[:best + 1] + hh + [hh[0]] + ring[best:]
    return ring


def _earclip(pts: list) -> list[tuple[int, int, int]]:
    """Triangles (index triples) of a simple counterclockwise ring (bridged holes allowed:
    a bridge's two vertices appear twice, told apart by index)."""
    n = len(pts)
    if n < 3:
        return []
    nxt = [(i + 1) % n for i in range(n)]
    prv = [(i - 1) % n for i in range(n)]
    alive = [True] * n
    cells: dict = {}

    def key(p):
        return (p[0] // CELL, p[1] // CELL)

    def convex(i):
        return _orient(pts[prv[i]], pts[i], pts[nxt[i]]) > 0
    refl = set()
    for i in range(n):
        if not convex(i):
            refl.add(i)
            cells.setdefault(key(pts[i]), set()).add(i)

    def drop(i):
        if i in refl:
            refl.discard(i)
            cells.get(key(pts[i]), set()).discard(i)

    def ear(i) -> bool:
        a, b, c = pts[prv[i]], pts[i], pts[nxt[i]]
        if _orient(a, b, c) <= 0:
            return False
        x0, x1 = min(a[0], b[0], c[0]), max(a[0], b[0], c[0])
        y0, y1 = min(a[1], b[1], c[1]), max(a[1], b[1], c[1])
        for cx in range(x0 // CELL, x1 // CELL + 1):
            for cy in range(y0 // CELL, y1 // CELL + 1):
                for j in cells.get((cx, cy), ()):
                    if j in (prv[i], i, nxt[i]) or not alive[j]:
                        continue
                    p = pts[j]
                    if p == a or p == b or p == c:
                        continue
                    if _orient(a, b, p) >= 0 and _orient(b, c, p) >= 0 and \
                            _orient(c, a, p) >= 0:
                        return False
        return True
    out = []
    left = n
    i = 0
    stall = 0
    while left > 3:
        if alive[i] and ear(i):
            p, q = prv[i], nxt[i]
            out.append((p, i, q))
            alive[i] = False
            drop(i)
            nxt[p], prv[q] = q, p
            left -= 1
            for j in (p, q):
                if convex(j):
                    drop(j)
                elif j not in refl:
                    refl.add(j)
                    cells.setdefault(key(pts[j]), set()).add(j)
            i = p
            stall = 0
            continue
        i = nxt[i]
        stall += 1
        if stall > left + 2:
            # (degenerate leftovers: a fan from the next live vertex)
            a = i
            b = nxt[a]
            while nxt[b] != a:
                if _orient(pts[a], pts[b], pts[nxt[b]]) != 0:
                    out.append((a, b, nxt[b]))
                b = nxt[b]
            return out
    p = i
    while not alive[p]:
        p = nxt[p]
    q, r = nxt[p], nxt[nxt[p]]
    if _orient(pts[p], pts[q], pts[r]) != 0:
        out.append((p, q, r))
    return out


def _incircle(a, b, c, d) -> bool:
    """Whether d lies inside the circle through a, b, c (counterclockwise)."""
    adx, ady = a[0] - d[0], a[1] - d[1]
    bdx, bdy = b[0] - d[0], b[1] - d[1]
    cdx, cdy = c[0] - d[0], c[1] - d[1]
    det = ((adx * adx + ady * ady) * (bdx * cdy - cdx * bdy) -
           (bdx * bdx + bdy * bdy) * (adx * cdy - cdx * ady) +
           (cdx * cdx + cdy * cdy) * (adx * bdy - bdx * ady))
    return det > 0


def triangulate(rings: list, samples: list = ()) -> tuple[list, list]:
    """(points, triangles) of a face: rings of (x_mm, y_mm), the exterior counterclockwise,
    holes clockwise; samples (x_mm, y_mm) strictly inside. Points are the rings' vertices
    (bridged duplicates merged) and then the samples; triangles counterclockwise."""
    ext = rings[0] if _area2(rings[0]) > 0 else rings[0][::-1]
    holes = [h if _area2(h) < 0 else h[::-1] for h in rings[1:]]
    ring = _bridge(ext, holes) if holes else list(ext)
    tris = _earclip(ring)
    index: dict = {}
    pts: list = []
    remap = []
    for p in ring:
        if p not in index:
            index[p] = len(pts)
            pts.append(p)
        remap.append(index[p])
    T = [(remap[a], remap[b], remap[c]) for a, b, c in tris]
    T = [t for t in T if len({*t}) == 3]
    if not samples:
        return pts, T
    fixed = set()
    for r in [ext] + holes:
        for i in range(len(r)):
            a, b = index[r[i]], index[r[(i + 1) % len(r)]]
            fixed.add((min(a, b), max(a, b)))
    E: dict = {}            # edge -> triangles

    def link(ti, sign):
        a, b, c = T[ti]
        for u, v in ((a, b), (b, c), (c, a)):
            key = (min(u, v), max(u, v))
            if sign > 0:
                E.setdefault(key, set()).add(ti)
            else:
                E[key].discard(ti)
    for ti in range(len(T)):
        link(ti, 1)

    def put(ti, t):
        link(ti, -1)
        T[ti] = t
        link(ti, 1)
    for s in samples:
        if s in index:
            continue
        hit = None
        for ti, (a, b, c) in enumerate(T):
            if _orient(pts[a], pts[b], s) > 0 and _orient(pts[b], pts[c], s) > 0 and \
                    _orient(pts[c], pts[a], s) > 0:
                hit = ti
                break
        if hit is None:
            continue
        k = len(pts)
        pts.append(s)
        index[s] = k
        a, b, c = T[hit]
        put(hit, (a, b, k))
        for t in ((b, c, k), (c, a, k)):
            T.append(t)
            link(len(T) - 1, 1)
        stack = [(a, b), (b, c), (c, a)]
        while stack:
            u, v = stack.pop()
            key = (min(u, v), max(u, v))
            if key in fixed:
                continue
            ts = sorted(E.get(key, ()))
            if len(ts) != 2:
                continue
            t1, t2 = (ts[0], ts[1]) if k in T[ts[0]] else (ts[1], ts[0])
            if k not in T[t1]:
                continue
            w = [x for x in T[t2] if x not in (u, v)][0]
            a1, b1, c1 = T[t1]          # (u, v, k) counterclockwise up to rotation
            if not _incircle(pts[a1], pts[b1], pts[c1], pts[w]):
                continue
            if _orient(pts[k], pts[u], pts[w]) > 0 and _orient(pts[k], pts[w], pts[v]) > 0:
                put(t1, (k, u, w))
                put(t2, (k, w, v))
            elif _orient(pts[k], pts[v], pts[w]) > 0 and _orient(pts[k], pts[w], pts[u]) > 0:
                put(t1, (k, v, w))
                put(t2, (k, w, u))
            else:
                continue
            stack += [(u, w), (w, v)]
    return pts, T
