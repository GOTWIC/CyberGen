"""Polylines for street pieces: arc length, points and frames at a distance, offset lines,
height profiles.

Only IEEE operations (+, -, *, /, sqrt) on Python floats in a fixed order, and citygen's
`dmath` for angles, so every machine gets the same bits (scope section 10).
"""

from __future__ import annotations

import math

from citygen import dmath as M

MITER_CAP = 2.0
TIDY_SEG_M = 0.5        #`Path.tidied`: a vertex this close to the last kept one ...
TIDY_OFF_M = 0.02       # ... and this close to the line through its neighbors is dropped


def dedupe(pts, tol: float = 0.005) -> list[tuple[float, float]]:
    out: list[tuple[float, float]] = []
    for p in pts:
        x, y = float(p[0]), float(p[1])
        if not out or dist(out[-1], (x, y)) > tol:
            out.append((x, y))
    return out


def dist(a, b) -> float:
    dx, dy = b[0] - a[0], b[1] - a[1]
    return math.sqrt(dx * dx + dy * dy)


def unit(dx: float, dy: float) -> tuple[float, float]:
    L = math.sqrt(dx * dx + dy * dy)
    if L == 0.0:
        return 1.0, 0.0
    return dx / L, dy / L


class Profile:
    """Height z at distance s from (s, z) samples, linear between them, held at the ends."""

    def __init__(self, samples):
        self.s = [float(a) for a, _ in samples]
        self.z = [float(b) for _, b in samples]

    @classmethod
    def of(cls, rows) -> Profile:
        """From model rows ({"s", "z"} dicts or ZSample objects); empty means 0."""
        out = []
        for r in rows or ():
            if isinstance(r, dict):
                out.append((r["s"], r["z"]))
            else:
                out.append((r.s, r.z))
        return cls(out)

    def __call__(self, s: float) -> float:
        n = len(self.s)
        if n == 0:
            return 0.0
        if s <= self.s[0]:
            return self.z[0]
        if s >= self.s[-1]:
            return self.z[-1]
        lo, hi = 0, n - 1
        while hi - lo > 1:
            mid = (lo + hi) // 2
            if self.s[mid] <= s:
                lo = mid
            else:
                hi = mid
        s0, s1 = self.s[lo], self.s[hi]
        if s1 - s0 <= 1e-9:
            return self.z[hi]
        return self.z[lo] + (self.z[hi] - self.z[lo]) * (s - s0) / (s1 - s0)

    def knots(self, s0: float, s1: float) -> list[float]:
        return [s for s in self.s if s0 < s < s1]


class Path:
    """A plan polyline with arc length; frames (point, left normal, miter factor) at any s."""

    def __init__(self, pts):
        self.p = dedupe(pts)
        if len(self.p) < 2:
            raise ValueError("degenerate path")
        self.cum = [0.0]
        self.d = []
        for a, b in zip(self.p, self.p[1:]):
            self.cum.append(self.cum[-1] + dist(a, b))
            self.d.append(unit(b[0] - a[0], b[1] - a[1]))
        self.L = self.cum[-1]

    def seg_at(self, s: float) -> int:
        n = len(self.d)
        if s <= 0.0:
            return 0
        if s >= self.L:
            return n - 1
        lo, hi = 0, n
        while hi - lo > 1:
            mid = (lo + hi) // 2
            if self.cum[mid] <= s:
                lo = mid
            else:
                hi = mid
        return lo

    def point(self, s: float) -> tuple[float, float]:
        i = self.seg_at(s)
        f = s - self.cum[i]
        dx, dy = self.d[i]
        return self.p[i][0] + dx * f, self.p[i][1] + dy * f

    def tangent(self, s: float) -> tuple[float, float]:
        return self.d[self.seg_at(s)]

    def frame(self, s: float, at_vertex: int | None = None):
        """(x, y, nx, ny, k): point, unit left normal and miter factor at s. At an inner
        vertex the normal bisects the two segments and k stretches offsets so that offset
        lines keep their distance (capped)."""
        if at_vertex is not None and 0 < at_vertex < len(self.p) - 1:
            d0, d1 = self.d[at_vertex - 1], self.d[at_vertex]
            nx, ny = -(d0[1] + d1[1]), d0[0] + d1[0]
            L = math.sqrt(nx * nx + ny * ny)
            x, y = self.p[at_vertex]
            if L < 1e-9:
                return x, y, -d1[1], d1[0], 1.0
            nx, ny = nx / L, ny / L
            c = nx * -d1[1] + ny * d1[0]
            k = 1.0 / max(c, 1.0 / MITER_CAP)
            return x, y, nx, ny, k
        x, y = self.point(s)
        dx, dy = self.tangent(s)
        return x, y, -dy, dx, 1.0

    def stations(self, s0: float, s1: float, step: float, extra=()) -> list[tuple[float, int | None]]:
        """Distances from s0 to s1: the ends, every inner vertex (with its index, for a
        mitered frame), the extra distances, and enough between them that no gap exceeds
        step."""
        marks: list[tuple[float, int | None]] = [(s0, None)]
        for i in range(1, len(self.p) - 1):
            if s0 + 1e-6 < self.cum[i] < s1 - 1e-6:
                marks.append((self.cum[i], i))
        for e in extra:
            if s0 + 1e-6 < e < s1 - 1e-6:
                marks.append((float(e), None))
        marks.append((s1, None))
        marks.sort(key=lambda m: (m[0], -1 if m[1] is None else m[1]))
        out: list[tuple[float, int | None]] = []
        for m in marks:
            if out and m[0] - out[-1][0] < 0.02:
                # too close to the last mark: keep a vertex over a plain mark, but never
                # move the first station
                if m[1] is not None and out[-1][1] is None and len(out) > 1:
                    out[-1] = m
                continue
            if out:
                base = out[-1][0]
                gap = m[0] - base
                n = int(gap / step)
                if gap > step * n + 1e-9:
                    n += 1
                for k in range(1, n):
                    out.append((base + gap * k / n, None))
            out.append(m)
        if out[-1][0] < s1 - 1e-6:
            out.append((s1, None))
        return out

    def project(self, x: float, y: float) -> tuple[float, float]:
        """(s, t): distance along the path of the nearest point and the signed distance
        from it (left positive)."""
        best = None
        for i, (a, b) in enumerate(zip(self.p, self.p[1:])):
            dx, dy = self.d[i]
            L = self.cum[i + 1] - self.cum[i]
            f = (x - a[0]) * dx + (y - a[1]) * dy
            f = 0.0 if f < 0.0 else (L if f > L else f)
            qx, qy = a[0] + dx * f, a[1] + dy * f
            ex, ey = x - qx, y - qy
            d2 = ex * ex + ey * ey
            if best is None or d2 < best[0]:
                t = -dy * ex + dx * ey
                best = (d2, self.cum[i] + f, t)
        return best[1], best[2]

    def tidied(self, seg_m: float = TIDY_SEG_M, off_m: float = TIDY_OFF_M) -> Path:
        """The path without its micro-kinks: an inner vertex less than seg_m past the last
        kept one and within off_m of the chord to the next vertex is dropped. A kink that
        small barely bends the line, but a curb 9 m out swings round it on a radius of
        meters, so its offset lines fold over themselves."""
        keep = [self.p[0]]
        for i in range(1, len(self.p) - 1):
            a, b, c = keep[-1], self.p[i], self.p[i + 1]
            ux, uy = unit(c[0] - a[0], c[1] - a[1])
            off = abs((b[0] - a[0]) * uy - (b[1] - a[1]) * ux)
            if dist(a, b) < seg_m and off <= off_m:
                continue
            keep.append(b)
        keep.append(self.p[-1])
        return self if len(keep) == len(self.p) else Path(keep)

    def sub(self, s0: float, s1: float) -> list[tuple[float, float]]:
        pts = [self.point(s0)]
        for i in range(1, len(self.p) - 1):
            if s0 < self.cum[i] < s1:
                pts.append(self.p[i])
        pts.append(self.point(s1))
        return dedupe(pts)


def heading(dx: float, dy: float) -> float:
    """Degrees counterclockwise from east."""
    return M.degrees(M.atan2(dy, dx))


def seg_cross(p, q, a, b):
    """Parameters (u along p->q, v along a->b) where two segments cross, or None."""
    rx, ry = q[0] - p[0], q[1] - p[1]
    sx, sy = b[0] - a[0], b[1] - a[1]
    den = rx * sy - ry * sx
    if den == 0.0:
        return None
    ax, ay = a[0] - p[0], a[1] - p[1]
    u = (ax * sy - ay * sx) / den
    v = (ax * ry - ay * rx) / den
    if -1e-9 <= u <= 1.0 + 1e-9 and -1e-9 <= v <= 1.0 + 1e-9:
        return u, v
    return None


def first_exit(path_pts, ring):
    """Where a polyline starting inside a ring first crosses it: (s along the polyline, edge
    index i of ring[i] -> ring[i+1], v along that edge), or None."""
    cum = 0.0
    n = len(ring)
    for k in range(len(path_pts) - 1):
        p, q = path_pts[k], path_pts[k + 1]
        L = dist(p, q)
        best = None
        for i in range(n):
            a, b = ring[i], ring[(i + 1) % n]
            c = seg_cross(p, q, a, b)
            if c is None:
                continue
            u, v = c
            if u * L < 0.01 and k == 0:
                continue
            if best is None or u < best[0]:
                best = (u, i, v)
        if best is not None:
            return cum + best[0] * L, best[1], best[2]
        cum += L
    return None
