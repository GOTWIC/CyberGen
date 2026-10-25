"""Shape helpers for buildings and site generators (M3).

Everything here works on grid geometry (0.01 m) and decides only with exact predicates
(`covers`, `intersects` on grid coordinates) and plain Python arithmetic. Local frames turn
with `dmath` cosines; points are computed in separate IEEE operations and rounded to the
grid, so the same input gives the same shapes on every machine. Circles and regular polygons
are built from `dmath` too (no round buffer joins, whose vertices come from the platform libm).
"""

from __future__ import annotations

import math

import shapely
from shapely.geometry import LineString, Polygon

from . import dmath as M
from . import geom as G

q = G.q


class Frame:
    """Local frame at (ox, oy) turned by `angle` (radians): u along the facade, v across it
    (into the lot for a lot frame)."""

    __slots__ = ("ox", "oy", "angle", "c", "s")

    def __init__(self, ox: float, oy: float, angle: float):
        self.ox, self.oy = q(ox), q(oy)
        self.angle = float(angle)
        self.c = float(M.cos(self.angle))
        self.s = float(M.sin(self.angle))

    def world(self, u: float, v: float) -> tuple[float, float]:
        return (q(self.ox + (u * self.c - v * self.s)), q(self.oy + (u * self.s + v * self.c)))

    def local(self, x: float, y: float) -> tuple[float, float]:
        dx = x - self.ox
        dy = y - self.oy
        return (dx * self.c + dy * self.s, dy * self.c - dx * self.s)

    def rect(self, u0: float, v0: float, u1: float, v1: float) -> Polygon:
        return Polygon([self.world(u0, v0), self.world(u1, v0), self.world(u1, v1),
                        self.world(u0, v1)])

    def poly(self, pts) -> Polygon:
        return Polygon([self.world(u, v) for u, v in pts])

    def bounds(self, poly) -> tuple[float, float, float, float]:
        """Local bounds of a polygon's exterior (u0, v0, u1, v1)."""
        us, vs = [], []
        for x, y in poly.exterior.coords:
            u, v = self.local(x, y)
            us.append(u)
            vs.append(v)
        return min(us), min(vs), max(us), max(vs)

    def yaw_deg(self) -> float:
        return q(M.degrees(self.angle))

    def moved(self, u: float, v: float) -> Frame:
        x, y = self.world(u, v)
        return Frame(x, y, self.angle)

    def turned(self, d_angle: float) -> Frame:
        return Frame(self.ox, self.oy, self.angle + d_angle)


def edge_angle(pts) -> float:
    """Direction (radians) of the longest straight edge of a polyline (the first of equally
    long ones)."""
    best = None
    for a, b in zip(pts, pts[1:]):
        dx, dy = b[0] - a[0], b[1] - a[1]
        L2 = dx * dx + dy * dy
        if best is None or L2 > best[0]:
            best = (L2, dx, dy)
    if best is None or best[0] == 0:
        return 0.0
    return float(M.atan2(best[2], best[1]))


def lot_frame(poly, line) -> Frame:
    """Frame of a lot: origin at its centroid, u along the frontage line, v into the lot."""
    cx, cy = G.centroid(poly)
    ang = edge_angle(line)
    fr = Frame(cx, cy, ang)
    # v points from the frontage into the lot: the frontage midpoint must have v < 0
    mx = (line[0][0] + line[-1][0]) / 2.0
    my = (line[0][1] + line[-1][1]) / 2.0
    if fr.local(mx, my)[1] > 0:
        fr = Frame(cx, cy, ang + M.PI)
    return fr


def prep(poly):
    shapely.prepare(poly)
    return poly


SHRINK = ((1.0, 1.0), (1.0, 0.85), (0.85, 1.0), (0.85, 0.85), (0.85, 0.7), (0.7, 0.85),
          (0.7, 0.7), (0.7, 0.55), (0.55, 0.7), (0.55, 0.55), (0.45, 0.45), (0.36, 0.36))


def fit_rect(region, fr: Frame, w: float, d: float, cu: float, cv: float,
             min_w: float = 0.0, min_d: float = 0.0, shrink=SHRINK,
             front: float | None = None) -> Polygon | None:
    """The largest rectangle of the shrink sequence (w x d, centered at local (cu, cv), or
    from v = front inward when `front` is given) that `region` covers, at least
    min_w x min_d; None when none fits. `region` should be prepared."""
    for fw, fd in shrink:
        ww, dd = w * fw, d * fd
        if ww < min_w or dd < min_d:
            continue
        v0 = cv - dd / 2.0 if front is None else front
        r = fr.rect(cu - ww / 2.0, v0, cu + ww / 2.0, v0 + dd)
        if r.is_valid and region.covers(r):
            return r
    return None


def fit_rect_any(region, fr: Frame, w: float, d: float, anchors, min_w: float = 0.0,
                 min_d: float = 0.0) -> tuple[Polygon, tuple[float, float]] | None:
    """fit_rect at the first anchor that fits (anchors in local coordinates)."""
    for cu, cv in anchors:
        r = fit_rect(region, fr, w, d, cu, cv, min_w, min_d)
        if r is not None:
            return r, (cu, cv)
    return None


def anchors_of(region, fr: Frame) -> list[tuple[float, float]]:
    """Candidate centers: the centroid, the representative point, and the middle of the
    local bounds."""
    c = G.centroid(region)
    r = G.qpoint(region.representative_point())
    u0, v0, u1, v1 = fr.bounds(region)
    out = []
    for p in (fr.local(*c), fr.local(*r), ((u0 + u1) / 2.0, (v0 + v1) / 2.0)):
        if p not in out:
            out.append(p)
    return out


def ngon(cx: float, cy: float, r: float, n: int, phase: float = 0.0) -> Polygon:
    """Regular n-gon (grid vertices), counterclockwise."""
    pts = []
    for k in range(n):
        a = phase + 2.0 * M.PI * k / n
        pts.append((q(cx + r * float(M.cos(a))), q(cy + r * float(M.sin(a)))))
    return Polygon(pts)


def circle(cx: float, cy: float, r: float) -> Polygon:
    n = 12 if r < 3.0 else 20 if r < 12.0 else 32
    return ngon(cx, cy, r, n)


def ring(cx: float, cy: float, r_out: float, r_in: float, n: int = 32) -> Polygon:
    outer = ngon(cx, cy, r_out, n)
    inner = ngon(cx, cy, r_in, n)
    return Polygon(outer.exterior.coords, [inner.exterior.coords])


def ellipse(fr: Frame, a: float, b: float, n: int = 32) -> Polygon:
    pts = []
    for k in range(n):
        t = 2.0 * M.PI * k / n
        pts.append(fr.world(a * float(M.cos(t)), b * float(M.sin(t))))
    return Polygon(pts)


def ellipse_ring(fr: Frame, a: float, b: float, a_in: float, b_in: float,
                 n: int = 32) -> Polygon:
    return Polygon(ellipse(fr, a, b, n).exterior.coords,
                   [ellipse(fr, a_in, b_in, n).exterior.coords])


def inset(poly, d: float):
    """Polygon shrunk by d (mitre joins), largest part, grid; empty when nothing is left."""
    if poly is None or poly.is_empty:
        return Polygon()
    g = G.qpoly(poly.buffer(-d, join_style="mitre", mitre_limit=2.0))
    ps = G.parts(g)
    return ps[0] if ps else Polygon()


def simplified(poly, tol: float = 0.3):
    g = G.qpoly(shapely.simplify(poly, tol, preserve_topology=True))
    ps = G.parts(g)
    return ps[0] if ps else Polygon()


def strip_along(line_pts, depth: float):
    """Buffer of a frontage line to `depth` (flat caps, mitre), grid."""
    return G.qpoly(LineString(line_pts).buffer(depth, cap_style="flat", join_style="mitre",
                                               mitre_limit=2.0))


def halfplane(fr: Frame, v_min: float | None = None, v_max: float | None = None,
              u_min: float | None = None, u_max: float | None = None,
              far: float = 2000.0) -> Polygon:
    """Local box u_min..u_max x v_min..v_max (open sides reach `far`)."""
    return fr.rect(-far if u_min is None else u_min, -far if v_min is None else v_min,
                   far if u_max is None else u_max, far if v_max is None else v_max)


def floors_for(h: float, fh: float, lo: int = 1) -> int:
    return max(lo, int(math.floor(h / fh + 0.5)))


def seg_dist(p, a, b) -> float:
    """Distance from p to segment ab (plain arithmetic)."""
    dx, dy = b[0] - a[0], b[1] - a[1]
    L2 = dx * dx + dy * dy
    if L2 <= 0:
        ex, ey = p[0] - a[0], p[1] - a[1]
        return math.sqrt(ex * ex + ey * ey)
    t = ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / L2
    t = 0.0 if t < 0 else 1.0 if t > 1 else t
    ex = p[0] - (a[0] + t * dx)
    ey = p[1] - (a[1] + t * dy)
    return math.sqrt(ex * ex + ey * ey)


def line_dist(p, pts) -> tuple[float, int]:
    """(distance, index of the nearest segment) from p to a polyline."""
    best = (math.inf, 0)
    for i in range(len(pts) - 1):
        d = seg_dist(p, pts[i], pts[i + 1])
        if d < best[0]:
            best = (d, i)
    return best


def ring_edges(poly) -> list[tuple[tuple[float, float], tuple[float, float]]]:
    """Edges of the exterior ring, counterclockwise."""
    p = G.oriented(poly)
    c = [(x, y) for x, y in p.exterior.coords]
    return [(c[i], c[i + 1]) for i in range(len(c) - 1) if c[i] != c[i + 1]]


def unit(dx: float, dy: float) -> tuple[float, float]:
    n = math.sqrt(dx * dx + dy * dy)
    return (dx / n, dy / n) if n > 0 else (1.0, 0.0)


def lerp(a, b, t: float) -> tuple[float, float]:
    return (q(a[0] + (b[0] - a[0]) * t), q(a[1] + (b[1] - a[1]) * t))


def pick(rng, weights) -> str:
    """Weighted choice from ((name, weight), ...) with one uniform draw."""
    tot = math.fsum(w for _, w in weights)
    u = float(rng.random()) * tot
    acc = 0.0
    for name, w in weights:
        acc += w
        if u < acc:
            return name
    return weights[-1][0]


def uniform(rng, lo: float, hi: float) -> float:
    lo, hi = float(lo), float(hi)
    return lo + (hi - lo) * float(rng.random())


FRONT_SHRINK = tuple(sorted(((fw, fd) for fw in (1.0, 0.9, 0.8, 0.7, 0.6, 0.5)
                             for fd in (1.0, 0.8, 0.6, 0.45, 0.3)),
                            key=lambda t: (-round(t[0] * t[1], 6), -t[1])))


def front_rect(region, fr: Frame, depth: float, w_max: float | None = None,
               gaps=(0.1, 0.8, 2.0, 4.0), min_w: float = 8.0, min_d: float = 6.0,
               v_front: float | None = None):
    """A rectangle along the street front of `region` (from v_front, or the region's front
    when that is not given or lies in front of it), `depth` deep (or less) and as wide as the
    region is at both its front and back lines (at most w_max), or None. `region` should be
    prepared."""
    u0, v0, u1, v1 = fr.bounds(region)
    if v_front is not None and v_front > v0:
        v0 = v_front
    spans: dict = {}

    def span(v):
        if v not in spans:
            cut = G.inter(region, fr.rect(u0 - 10.0, v - 0.2, u1 + 10.0, v + 0.2))
            ps = G.parts(cut)
            spans[v] = (fr.bounds(ps[0])[0], fr.bounds(ps[0])[2]) if ps else None
        return spans[v]

    cands = []
    for fd in (1.0, 0.8, 0.6, 0.45, 0.3):
        dd = depth * fd
        if dd < min_d:
            continue
        for g in gaps:
            a_ = span(round(v0 + g + 0.3, 2))
            b_ = span(round(v0 + g + dd - 0.3, 2))
            if a_ is None or b_ is None:
                continue
            lo, hi = max(a_[0], b_[0]) + 0.3, min(a_[1], b_[1]) - 0.3
            W = hi - lo if w_max is None else min(hi - lo, w_max)
            if W >= min_w:
                cands.append((round(-W * dd, 6), fd, g, dd, lo, hi, W))
    cands.sort()
    for _, fd, g, dd, lo, hi, W in cands[:6]:
        cu = (lo + hi) / 2.0
        for fw in (1.0, 0.9, 0.8, 0.7, 0.6):
            ww = W * fw
            if ww < min_w:
                break
            r = fr.rect(cu - ww / 2.0, v0 + g, cu + ww / 2.0, v0 + g + dd)
            if r.is_valid and region.covers(r):
                return r
    return None


def obb_angle(poly) -> float:
    """Direction of the long side of a polygon's minimum rotated rectangle (grid coordinates,
    dmath angle)."""
    r = G.qpoly(shapely.minimum_rotated_rectangle(poly))
    if r is None or r.is_empty or r.geom_type != "Polygon":
        return 0.0
    return edge_angle(list(r.exterior.coords))


# ---------------------------------------------------------------------------
# Vertical wheels (mass shape "ring"): the rim is a circle in a vertical plane, so over a plan
# point at distance u from the axis it spans z = zc -/+ sqrt(R^2 - u^2) only
# ---------------------------------------------------------------------------

def ring_info(poly, z0: float, z1: float):
    """(center x, center y, unit axis, R, zc) of a wheel whose plan is the thin rectangle
    `poly` (its long side the wheel plane)."""
    c = list(G.oriented(poly).exterior.coords)
    best = None
    for a, b in zip(c, c[1:]):
        dx, dy = b[0] - a[0], b[1] - a[1]
        L2 = dx * dx + dy * dy
        if best is None or L2 > best[0]:
            best = (L2, dx, dy)
    L = math.sqrt(best[0])
    ux, uy = best[1] / L, best[2] / L
    cx, cy = G.centroid(poly)
    R = (z1 - z0) / 2.0
    return cx, cy, (ux, uy), R, z0 + R


def ring_u(info, poly) -> tuple[float, float]:
    """Range of |u| (distance along the wheel plane from the axis) over a polygon's vertices
    and its crossing of the axis."""
    cx, cy, (ux, uy), R, zc = info
    us = [(x - cx) * ux + (y - cy) * uy for x, y in poly.exterior.coords]
    lo = 0.0 if min(us) <= 0.0 <= max(us) else min(abs(u) for u in us)
    return lo, max(abs(u) for u in us)


def ring_zband(info, poly) -> tuple[float, float] | None:
    """(lowest, highest) z of the rim over the part of the plane above `poly`, or None."""
    cx, cy, _, R, zc = info
    lo, hi = ring_u(info, poly)
    if lo >= R:
        return None
    h = math.sqrt(max(R * R - lo * lo, 0.0))
    return zc - h, zc + h


def ring_ground(info, poly, clear: float):
    """The part of a wheel's plan where the rim comes lower than `clear` (around the axis)."""
    cx, cy, (ux, uy), R, zc = info
    if zc - clear >= R:
        return Polygon()
    uc = math.sqrt(max(R * R - (zc - clear) * (zc - clear), 0.0))
    fr = Frame(cx, cy, float(M.atan2(uy, ux)))
    return G.inter(poly, fr.rect(-uc, -50.0, uc, 50.0))
