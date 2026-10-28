"""Plane geometry for the brief: rings, strip clipping, a point grid, point-in-polygon and
distance to polylines over many points at once.

Only IEEE operations (+, -, *, /, sqrt, comparisons) in a fixed order, on Python floats or
numpy element-wise, so every machine gets the same bits (scope section 10); no GEOS output
reaches a decision.
"""

from __future__ import annotations

import math

import numpy as np


def ring(points) -> list[tuple[float, float]]:
    """A ring as a list of (x, y) without the closing point."""
    pts = [(float(p[0]), float(p[1])) for p in points]
    if len(pts) > 1 and pts[0] == pts[-1]:
        pts.pop()
    return pts


def signed_area2(pts) -> float:
    """Twice the signed area (counterclockwise positive), summed in ring order."""
    s = 0.0
    n = len(pts)
    for i in range(n):
        x0, y0 = pts[i]
        x1, y1 = pts[(i + 1) % n]
        s += x0 * y1 - x1 * y0
    return s


def oriented(pts, ccw: bool) -> list[tuple[float, float]]:
    """The ring turned counterclockwise (ccw) or clockwise."""
    a = signed_area2(pts)
    return list(pts) if (a > 0) == ccw else list(reversed(pts))


def bbox(pts) -> tuple[float, float, float, float]:
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    return min(xs), min(ys), max(xs), max(ys)


def seg_len(a, b) -> float:
    dx, dy = b[0] - a[0], b[1] - a[1]
    return math.sqrt(dx * dx + dy * dy)


def clip_strip(local: list[tuple[float, float]], length: float, depth: float):
    """Clip a polygon given in edge coordinates (s along the edge, t outward) to the strip
    0 <= s <= length, 0 <= t <= depth (Sutherland-Hodgman). Returns (s0, s1, t_min, area)
    of what is left, or None when nothing with area is left."""
    poly = local
    for axis, bound, keep_low in ((0, 0.0, False), (0, length, True), (1, 0.0, False),
                                  (1, depth, True)):
        if not poly:
            return None
        out = []
        n = len(poly)
        for i in range(n):
            p, c = poly[i - 1], poly[i]
            pin = p[axis] <= bound if keep_low else p[axis] >= bound
            cin = c[axis] <= bound if keep_low else c[axis] >= bound
            if cin:
                if not pin:
                    out.append(_cut(p, c, axis, bound))
                out.append(c)
            elif pin:
                out.append(_cut(p, c, axis, bound))
        poly = out
    if len(poly) < 3:
        return None
    area = abs(signed_area2(poly)) / 2.0
    if area < 1e-5:
        return None
    ss = [p[0] for p in poly]
    ts = [p[1] for p in poly]
    return min(ss), max(ss), min(ts), area


def _cut(p, c, axis: int, bound: float):
    other = 1 - axis
    f = (bound - p[axis]) / (c[axis] - p[axis])
    v = p[other] + f * (c[other] - p[other])
    return (bound, v) if axis == 0 else (v, bound)


def to_edge(pts, a, ux: float, uy: float, nx: float, ny: float):
    """Points in the edge frame: s along (ux, uy) from a, t along the outward normal."""
    ax, ay = a
    out = []
    for x, y in pts:
        dx, dy = x - ax, y - ay
        out.append((dx * ux + dy * uy, dx * nx + dy * ny))
    return out


def point_seg_dist(p, a, b) -> tuple[float, float]:
    """(distance, s along a->b of the nearest point) from p to the segment a-b."""
    dx, dy = b[0] - a[0], b[1] - a[1]
    L2 = dx * dx + dy * dy
    if L2 == 0.0:
        return seg_len(p, a), 0.0
    f = ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / L2
    f = 0.0 if f < 0.0 else (1.0 if f > 1.0 else f)
    qx, qy = a[0] + f * dx, a[1] + f * dy
    ex, ey = p[0] - qx, p[1] - qy
    return math.sqrt(ex * ex + ey * ey), f * math.sqrt(L2)


# ---------------------------------------------------------------------------
# Many points at once
# ---------------------------------------------------------------------------

class PointGrid:
    """Points bucketed by a square grid, for box queries in a fixed order."""

    def __init__(self, x: np.ndarray, y: np.ndarray, cell: float = 32.0):
        self.x, self.y, self.cell = x, y, cell
        ix = np.floor(x / cell).astype(np.int64)
        iy = np.floor(y / cell).astype(np.int64)
        self.ix0, self.iy0 = (int(ix.min()), int(iy.min())) if len(x) else (0, 0)
        self.nx = (int(ix.max()) - self.ix0 + 1) if len(x) else 1
        key = (iy - self.iy0) * self.nx + (ix - self.ix0)
        self.order = np.argsort(key, kind="stable")
        self.keys = key[self.order]

    def query(self, x0: float, y0: float, x1: float, y1: float) -> np.ndarray:
        """Indices of the points in cells touching the box (a superset), ascending by
        cell then index."""
        if not len(self.x):
            return np.zeros(0, dtype=np.int64)
        c = self.cell
        ix0 = max(int(math.floor(x0 / c)) - self.ix0, 0)
        ix1 = min(int(math.floor(x1 / c)) - self.ix0, self.nx - 1)
        iy0 = int(math.floor(y0 / c)) - self.iy0
        iy1 = int(math.floor(y1 / c)) - self.iy0
        if ix1 < ix0 or iy1 < 0:
            return np.zeros(0, dtype=np.int64)
        parts = []
        for iy in range(max(iy0, 0), iy1 + 1):
            lo = np.searchsorted(self.keys, iy * self.nx + ix0, side="left")
            hi = np.searchsorted(self.keys, iy * self.nx + ix1, side="right")
            if hi > lo:
                parts.append(self.order[lo:hi])
        if not parts:
            return np.zeros(0, dtype=np.int64)
        return np.concatenate(parts)


def inside_ring(px: np.ndarray, py: np.ndarray, pts) -> np.ndarray:
    """Crossing-number test of many points against one ring (boundary points may go
    either way, the same on every machine)."""
    inside = np.zeros(len(px), dtype=bool)
    n = len(pts)
    for i in range(n):
        x0, y0 = pts[i - 1]
        x1, y1 = pts[i]
        if y0 == y1:
            continue
        cross = (py < y0) != (py < y1)
        xs = x0 + (py - y0) * ((x1 - x0) / (y1 - y0))
        inside ^= cross & (px < xs)
    return inside


def inside_poly(px, py, exterior, holes=()) -> np.ndarray:
    r = inside_ring(px, py, exterior)
    for h in holes:
        if r.any():
            r &= ~inside_ring(px, py, h)
    return r


def dist_polyline(px: np.ndarray, py: np.ndarray, line) -> np.ndarray:
    """Distance from many points to a polyline."""
    best = np.full(len(px), np.inf)
    for i in range(len(line) - 1):
        ax, ay = line[i]
        bx, by = line[i + 1]
        dx, dy = bx - ax, by - ay
        L2 = dx * dx + dy * dy
        if L2 == 0.0:
            f = np.zeros(len(px))
        else:
            f = ((px - ax) * dx + (py - ay) * dy) / L2
            f = np.clip(f, 0.0, 1.0)
        ex = px - (ax + f * dx)
        ey = py - (ay + f * dy)
        best = np.minimum(best, np.sqrt(ex * ex + ey * ey))
    return best
