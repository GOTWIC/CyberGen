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


# ---------------------------------------------------------------------------
# M21: true arcs. A curved stretch of a footprint is cut so that no chord sags more than
# SAG_M from the curve (2 cm at most once its vertices are on the grid), and recorded as an
# arc (center and radius to the millimeter, start and sweep), which stage 2 draws as the
# curve itself.
# ---------------------------------------------------------------------------

SAG_M = 0.010


def arc_steps(r: float, sweep: float) -> int:
    """Segments of an arc of radius r over `sweep` radians so that no chord sags more than
    SAG_M (a step of 2 sqrt(2 SAG / r) never does, since 1 - cos x <= x^2 / 2; plain
    arithmetic, so every machine cuts the same count)."""
    if r <= 2.0 * SAG_M or sweep <= 0.0:
        return 1
    step = 2.0 * math.sqrt(2.0 * SAG_M / r)
    return max(1, int(math.ceil(sweep / step - 1e-9)))


def _deg(a: float) -> float:
    d = float(M.degrees(a)) % 360.0
    return round(d if d < 359.99995 else 0.0, 4) + 0.0


def arc_rec(cx: float, cy: float, r: float, a0: float, sweep: float) -> dict:
    """An arc of the model (`model.Arc`) in world coordinates, angles in radians."""
    return {"center": (round(float(cx), 3) + 0.0, round(float(cy), 3) + 0.0),
            "radius_m": round(float(r), 3) + 0.0, "start_deg": _deg(a0),
            "sweep_deg": round(float(M.degrees(sweep)), 4) + 0.0}


def _arc_local(pts: list, cu: float, cv: float, r: float, a0: float, sweep: float) -> None:
    """Local points of an arc from a0 to its end (where the next arc starts at the same
    point, `Plate.ring` drops the repeat)."""
    n = arc_steps(r, sweep)
    for k in range(n + 1):
        a = a0 + sweep * k / n
        pts.append((cu + r * float(M.cos(a)), cv + r * float(M.sin(a))))


class Plate:
    """M21: a floor plate in frame `fr` (centered on its origin): a rectangle 2 hw x 2 hd
    with corners rounded to radius r (r = the half short side: a stadium; hw = hd = r: a
    circle) or cut by chamfer c, or a four-centre oval of semi-axes hw and hd (`oval`: two
    end arcs and two side arcs meeting tangent). Turned, scaled and moved exactly, it gives
    its polygon (grid, counterclockwise) and its arcs."""

    __slots__ = ("fr", "hw", "hd", "r", "c", "oval")

    def __init__(self, fr: Frame, hw: float, hd: float, r: float = 0.0, c: float = 0.0,
                 oval: bool = False):
        self.fr = fr
        self.hw, self.hd = float(hw), float(hd)
        lim = min(self.hw, self.hd)
        self.oval = bool(oval) and abs(self.hw - self.hd) >= 0.5
        if oval and not self.oval:
            r = self.hw = self.hd = lim       # (an oval of equal axes is the circle)
        self.r = min(max(float(r), 0.0), lim) if not self.oval else 0.0
        self.c = min(max(float(c), 0.0), lim * 0.9) if self.r <= 0.0 and not self.oval \
            else 0.0

    @staticmethod
    def of_rect(fr: Frame, rect) -> Plate:
        """The plate of a rectangle that frame `fr` sees axis aligned."""
        u0, v0, u1, v1 = fr.bounds(rect)
        return Plate(fr.moved((u0 + u1) / 2.0, (v0 + v1) / 2.0), (u1 - u0) / 2.0,
                     (v1 - v0) / 2.0)

    def _new(self, fr=None, hw=None, hd=None, r=None, c=None, oval=None) -> Plate:
        return Plate(self.fr if fr is None else fr, self.hw if hw is None else hw,
                     self.hd if hd is None else hd, self.r if r is None else r,
                     self.c if c is None else c, self.oval if oval is None else oval)

    def turned(self, d_angle: float) -> Plate:
        return self._new(fr=self.fr.turned(d_angle))

    def scaled(self, f: float) -> Plate:
        return self._new(hw=self.hw * f, hd=self.hd * f, r=self.r * f, c=self.c * f)

    def grown(self, d: float) -> Plate:
        """The plate offset outward by d (inward when negative): its corners keep their
        center, so a rounded corner's radius grows by d."""
        r = self.r + d if self.r > 0.0 else 0.0
        return self._new(hw=self.hw + d, hd=self.hd + d, r=max(r, 0.0),
                         c=self.c * (1.0 + d / max(min(self.hw, self.hd), 1.0)))

    def moved(self, du: float, dv: float) -> Plate:
        return self._new(fr=self.fr.moved(du, dv))

    def shifted(self, dx: float, dy: float) -> Plate:
        return self._new(fr=Frame(self.fr.ox + dx, self.fr.oy + dy, self.fr.angle))

    def rounded(self, r: float) -> Plate:
        return self._new(r=r, c=0.0)

    @property
    def reach(self) -> float:
        """Farthest distance of the plate from its center (what it sweeps when turned)."""
        if self.oval:
            return max(self.hw, self.hd)
        a, b = self.hw - self.r, self.hd - self.r
        if self.c > 0.0:
            return max(math.sqrt(self.hw * self.hw + (self.hd - self.c) ** 2),
                       math.sqrt((self.hw - self.c) ** 2 + self.hd * self.hd))
        return math.sqrt(a * a + b * b) + self.r

    def _local(self) -> tuple[list, list]:
        """(local points counterclockwise, local arcs (cu, cv, r, a0, sweep))."""
        hw, hd, r, c = self.hw, self.hd, self.r, self.c
        pts: list = []
        arcs: list = []
        if self.oval:
            swap = self.hd > self.hw
            a, b = (hd, hw) if swap else (hw, hd)
            r1 = 0.6 * b
            r2 = ((a - r1) * (a - r1) + b * b - r1 * r1) / (2.0 * (b - r1))
            phi = float(M.atan2(r2 - b, a - r1))
            for cu, cv, rr, a0, sw in ((a - r1, 0.0, r1, -phi, 2.0 * phi),
                                       (0.0, b - r2, r2, phi, M.PI - 2.0 * phi),
                                       (r1 - a, 0.0, r1, M.PI - phi, 2.0 * phi),
                                       (0.0, r2 - b, r2, M.PI + phi, M.PI - 2.0 * phi)):
                arcs.append((cu, cv, rr, a0, sw))
                _arc_local(pts, cu, cv, rr, a0, sw)
            if swap:   # the oval along v: a quarter turn of the plate's local frame
                pts = [(-v, u) for u, v in pts]
                arcs = [(-cv, cu, rr, a0 + M.HALF_PI, sw) for cu, cv, rr, a0, sw in arcs]
            return pts, arcs
        if r > 0.0:
            for k, (cu, cv) in enumerate(((hw - r, r - hd), (hw - r, hd - r),
                                          (r - hw, hd - r), (r - hw, r - hd))):
                a0 = -M.HALF_PI + k * M.HALF_PI
                arcs.append((cu, cv, r, a0, M.HALF_PI))
                _arc_local(pts, cu, cv, r, a0, M.HALF_PI)
            return pts, arcs
        if c > 0.0:
            return [(hw, c - hd), (hw, hd - c), (hw - c, hd), (c - hw, hd), (-hw, hd - c),
                    (-hw, c - hd), (c - hw, -hd), (hw - c, -hd)], arcs
        return [(hw, -hd), (hw, hd), (-hw, hd), (-hw, -hd)], arcs

    def ring(self) -> list:
        """The plate's points in world coordinates (grid, no repeats)."""
        pts, _ = self._local()
        out = []
        for u, v in pts:
            p = self.fr.world(u, v)
            if not out or p != out[-1]:
                out.append(p)
        if len(out) > 1 and out[0] == out[-1]:
            out.pop()
        return out

    def polygon(self) -> Polygon:
        return Polygon(self.ring())

    def arcs(self) -> list[dict]:
        _, arcs = self._local()
        out = []
        f = self.fr
        for cu, cv, r, a0, sw in arcs:
            # (the center unrounded: the arc the ring's grid points were cut from)
            x, y = f.ox + (cu * f.c - cv * f.s), f.oy + (cu * f.s + cv * f.c)
            out.append(arc_rec(x, y, r, f.angle + a0, sw))
        return out


def sector(cx: float, cy: float, r_in: float, r_out: float, a0: float,
           sweep: float) -> tuple[Polygon, list[dict]]:
    """M21: an annular sector (a curved slab's plan) around (cx, cy) from angle a0 by
    `sweep` radians, and its two arcs."""
    out: list = []
    n = arc_steps(r_out, sweep)
    for k in range(n + 1):
        a = a0 + sweep * k / n
        out.append((q(cx + r_out * float(M.cos(a))), q(cy + r_out * float(M.sin(a)))))
    n = arc_steps(r_in, sweep)
    for k in range(n, -1, -1):
        a = a0 + sweep * k / n
        out.append((q(cx + r_in * float(M.cos(a))), q(cy + r_in * float(M.sin(a)))))
    return Polygon(out), [arc_rec(cx, cy, r_out, a0, sweep), arc_rec(cx, cy, r_in, a0, sweep)]


def circle(cx: float, cy: float, r: float) -> Polygon:
    """A circle cut by `arc_steps` (its arc: `circle_arcs`)."""
    return Plate(Frame(cx, cy, 0.0), r, r, r).polygon()


def circle_arcs(cx: float, cy: float, r: float) -> list[dict]:
    return Plate(Frame(cx, cy, 0.0), r, r, r).arcs()


def ring(cx: float, cy: float, r_out: float, r_in: float) -> Polygon:
    outer = circle(cx, cy, r_out)
    inner = circle(cx, cy, r_in)
    return Polygon(outer.exterior.coords, [inner.exterior.coords])


def ellipse(fr: Frame, a: float, b: float) -> Polygon:
    """An oval of semi-axes a (along u) and b: four arcs (`Plate` with `oval`)."""
    return Plate(fr, a, b, oval=True).polygon()


def ellipse_arcs(fr: Frame, a: float, b: float) -> list[dict]:
    return Plate(fr, a, b, oval=True).arcs()


def ellipse_ring(fr: Frame, a: float, b: float, a_in: float, b_in: float) -> Polygon:
    return Polygon(ellipse(fr, a, b).exterior.coords, [ellipse(fr, a_in, b_in).exterior.coords])


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
               v_front: float | None = None, u_lim: tuple | None = None):
    """A rectangle along the street front of `region` (from v_front, or the region's front
    when that is not given or lies in front of it), `depth` deep (or less) and as wide as the
    region is at both its front and back lines (at most w_max), or None. `region` should be
    prepared."""
    u0, v0, u1, v1 = fr.bounds(region)
    if v_front is not None and v_front > v0:
        v0 = v_front
    if u_lim is not None:   # along the main frontage only (big, irregular lots)
        u0, u1 = max(u0, u_lim[0]), min(u1, u_lim[1])
        if u1 - u0 < min_w:
            return None
    spans: dict = {}

    def span(v):
        if v not in spans:
            cut = G.inter(region, fr.rect(u0 - 0.5, v - 0.2, u1 + 0.5, v + 0.2))
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
    """Direction of the long side of a polygon's minimum-area bounding rectangle: tried along
    every edge of its convex hull (grid vertices in canonical order, dmath angles, plain
    arithmetic; the first of equal areas wins), so every machine picks the same one."""
    hull = G.qpoly(shapely.convex_hull(poly))
    ps = G.parts(hull)
    if not ps:
        return 0.0
    pts = [(x, y) for x, y in shapely.normalize(ps[0]).exterior.coords]
    best = None
    for a, b in zip(pts, pts[1:]):
        dx, dy = b[0] - a[0], b[1] - a[1]
        L = math.sqrt(dx * dx + dy * dy)
        if L <= 0:
            continue
        ux, uy = dx / L, dy / L
        us = [x * ux + y * uy for x, y in pts]
        vs = [y * ux - x * uy for x, y in pts]
        W, D = max(us) - min(us), max(vs) - min(vs)
        area = round(W * D, 6)
        if best is None or area < best[0]:
            ang = float(M.atan2(dy, dx))
            best = (area, ang if W >= D else ang + M.HALF_PI)
    return best[1] if best else 0.0


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
