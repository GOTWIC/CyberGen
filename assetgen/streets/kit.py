"""Street meshes on integer millimeters (scope sections 8 and 10).

A piece's mesh lives in its own frame: an origin on the 0.01 m grid (the middle of what it
covers), x east, y north, z up. Generators hand in world points in meters; each is moved to
the piece frame and rounded to the millimeter once, and everything after that (triangle
tests, normals) works on those integers in a fixed order. Triangles that round to a line
are dropped.

Normals: faces built from grids and triangulated polygons share their vertices and take the
sum of their triangles' exact integer cross products (smooth along a road, a deck, a tube);
flat parts (boxes, prism walls, quads) carry the face normal on vertices of their own.
UV0 is in meters (world-scale tiling: along and across a road, or plan x and y); the street
packs are lean, without UV1 and vertex colors (AG0's advice for Nanite size).
"""

from __future__ import annotations

import math

import numpy as np

from citygen import dmath as M

from ..gltf import Primitive
from ..triangulate import TriangulationError, triangulate


def mmr(v: float) -> int:
    return int(round(v * 1000.0))


class _Slot:
    __slots__ = ("pos", "nrm", "uv", "idx", "auto")

    def __init__(self):
        self.pos: list[tuple[int, int, int]] = []
        self.nrm: list = []          # a unit normal, or None: summed from the triangles
        self.uv: list[tuple[float, float]] = []
        self.idx: list[int] = []
        self.auto = False


def _cross(a, b, c) -> tuple[int, int, int]:
    ux, uy, uz = b[0] - a[0], b[1] - a[1], b[2] - a[2]
    vx, vy, vz = c[0] - a[0], c[1] - a[1], c[2] - a[2]
    return (uy * vz - uz * vy, uz * vx - ux * vz, ux * vy - uy * vx)


def _unit3(n) -> tuple[float, float, float]:
    L = math.sqrt(float(n[0]) * n[0] + float(n[1]) * n[1] + float(n[2]) * n[2])
    if L == 0.0:
        return (0.0, 0.0, 1.0)
    return (n[0] / L, n[1] / L, n[2] / L)


class Mesh:
    def __init__(self, origin):
        """origin: (x, y) or (x, y, z) in meters, on the 0.01 m grid."""
        self.ox = mmr(origin[0])
        self.oy = mmr(origin[1])
        self.oz = mmr(origin[2]) if len(origin) > 2 else 0
        self.slots: dict[str, _Slot] = {}
        self.dropped = 0
        self.folds = 0

    # -- vertices ------------------------------------------------------------------------

    def P(self, x: float, y: float, z: float) -> tuple[int, int, int]:
        return (mmr(x) - self.ox, mmr(y) - self.oy, mmr(z) - self.oz)

    def _slot(self, name: str) -> _Slot:
        s = self.slots.get(name)
        if s is None:
            s = self.slots[name] = _Slot()
        return s

    def _add(self, sl: _Slot, p, n, uv) -> int:
        sl.pos.append(p)
        sl.nrm.append(n)
        sl.uv.append((float(uv[0]), float(uv[1])))
        if n is None:
            sl.auto = True
        return len(sl.pos) - 1

    def _tri(self, sl: _Slot, a: int, b: int, c: int, expect=None) -> bool:
        """A triangle, unless it rounds to a line or faces away from `expect` (a fold: an
        offset line crossing itself on the inside of a sharp bend)."""
        pa, pb, pc = sl.pos[a], sl.pos[b], sl.pos[c]
        n = _cross(pa, pb, pc)
        if n == (0, 0, 0):
            self.dropped += 1
            return False
        if expect is not None and n[0] * expect[0] + n[1] * expect[1] + n[2] * expect[2] <= 0:
            self.folds += 1
            return False
        sl.idx += [a, b, c]
        return True

    @property
    def triangles(self) -> int:
        return sum(len(s.idx) // 3 for s in self.slots.values())

    # -- building blocks -----------------------------------------------------------------

    def grid(self, slot: str, rows, uvs, flip: bool = False, expect=None):
        """A surface over rows of world points: rows[i][j] (i along, j across, j growing to
        the left of the direction of travel), uvs[i][j] in meters. Seen from above (for
        rows along +s and columns to the left) the quads are counterclockwise; `flip`
        turns them over. Shared vertices, smooth normals. `expect`: the direction the
        surface faces (a vector, or one per row); triangles facing away are folds and
        left out."""
        sl = self._slot(slot)
        n_i = len(rows)
        if n_i < 2:
            return
        n_j = len(rows[0])
        base = len(sl.pos)
        for i in range(n_i):
            for j in range(n_j):
                x, y, z = rows[i][j]
                self._add(sl, self.P(x, y, z), None, uvs[i][j])
        for i in range(n_i - 1):
            e = expect[i] if isinstance(expect, list) else expect
            for j in range(n_j - 1):
                a = base + i * n_j + j
                b = base + (i + 1) * n_j + j
                c = base + (i + 1) * n_j + j + 1
                d = base + i * n_j + j + 1
                if flip:
                    self._tri(sl, a, d, c, e)
                    self._tri(sl, a, c, b, e)
                else:
                    self._tri(sl, a, b, c, e)
                    self._tri(sl, a, c, d, e)

    def quad(self, slot: str, p0, p1, p2, p3, uvs=None):
        """A flat quad of world points, counterclockwise seen from its front, with its own
        vertices and face normal (from the exact integer cross product of the diagonals)."""
        sl = self._slot(slot)
        q = [self.P(*p) for p in (p0, p1, p2, p3)]
        d1 = (q[2][0] - q[0][0], q[2][1] - q[0][1], q[2][2] - q[0][2])
        d2 = (q[3][0] - q[1][0], q[3][1] - q[1][1], q[3][2] - q[1][2])
        n = (d1[1] * d2[2] - d1[2] * d2[1], d1[2] * d2[0] - d1[0] * d2[2],
             d1[0] * d2[1] - d1[1] * d2[0])
        if n == (0, 0, 0):
            self.dropped += 1
            return
        nf = _unit3(n)
        if uvs is None:
            e = math.sqrt(float(sum((q[1][k] - q[0][k]) ** 2 for k in range(3))))
            h = math.sqrt(float(sum((q[3][k] - q[0][k]) ** 2 for k in range(3))))
            uvs = ((0.0, 0.0), (e / 1000.0, 0.0), (e / 1000.0, h / 1000.0), (0.0, h / 1000.0))
        ids = [self._add(sl, q[k], nf, uvs[k]) for k in range(4)]
        self._tri(sl, ids[0], ids[1], ids[2], n)
        self._tri(sl, ids[0], ids[2], ids[3], n)

    def poly(self, slot: str, ring, holes=(), z=0.0, zfun=None, up: bool = True,
             uvfun=None) -> bool:
        """A polygon of plan points (meters), lifted to a height (a constant or zfun(x, y)),
        facing up (or down). Triangulated exactly on its millimeter coordinates."""
        sl = self._slot(slot)
        rings = [ring] + list(holes)
        pts3 = []
        for r in rings:
            for x, y in r:
                pts3.append((x, y, zfun(x, y) if zfun else z))
        q = [self.P(*p) for p in pts3]
        outer = [(p[0], p[1]) for p in q[:len(ring)]]
        hs = []
        k = len(ring)
        for h in holes:
            hs.append([(p[0], p[1]) for p in q[k:k + len(h)]])
            k += len(h)
        try:
            tris = triangulate(outer, hs)
        except TriangulationError:
            return False
        if not tris:
            return False
        used = sorted({i for t in tris for i in t})
        where = {}
        nf = (0.0, 0.0, 1.0 if up else -1.0) if zfun is None else None
        for i in used:
            x, y = pts3[i][0], pts3[i][1]
            uv = uvfun(x, y) if uvfun else (x, y)
            where[i] = self._add(sl, q[i], nf, uv)
        for a, b, c in tris:
            if up:
                self._tri(sl, where[a], where[b], where[c])
            else:
                self._tri(sl, where[a], where[c], where[b])
        return True

    def poly_map(self, slot: str, ring, holes=(), fmap=None, expect=(0.0, 0.0, 1.0)) -> bool:
        """A polygon given in coordinates of its own (u, v in meters: along and across a
        road, say), triangulated exactly on its millimeters there, each vertex placed by
        fmap(u, v) -> (x, y, z); UV0 is (u, v). (u, v) must keep the handedness of (x, y)
        for the surface to face up (`expect`: triangles facing away are folds, where a mark
        spans a bend of its road, and are left out)."""
        sl = self._slot(slot)
        rings = [ring] + list(holes)
        uv = [(float(p[0]), float(p[1])) for r in rings for p in r]
        q2 = [(mmr(u), mmr(v)) for u, v in uv]
        outer = q2[:len(ring)]
        hs = []
        k = len(ring)
        for h in holes:
            hs.append(q2[k:k + len(h)])
            k += len(h)
        try:
            tris = triangulate(outer, hs)
        except TriangulationError:
            return False
        if not tris:
            return False
        where = {}
        for i in sorted({i for t in tris for i in t}):
            x, y, z = fmap(*uv[i])
            where[i] = self._add(sl, self.P(x, y, z), None, uv[i])
        for a, b, c in tris:
            self._tri(sl, where[a], where[b], where[c], expect)
        return True

    def face(self, slot: str, o, U, V, ring, holes=()) -> bool:
        """A planar face in the plane through o (meters) spanned by unit vectors U and V:
        2D rings in (U, V) meters, counterclockwise seen from the side U x V points to."""
        def fmap(u, v):
            return (o[0] + U[0] * u + V[0] * v, o[1] + U[1] * u + V[1] * v,
                    o[2] + U[2] * u + V[2] * v)
        n = (U[1] * V[2] - U[2] * V[1], U[2] * V[0] - U[0] * V[2], U[0] * V[1] - U[1] * V[0])
        return self.poly_map(slot, ring, holes, fmap, expect=n)

    def wall(self, slot: str, a, b, z0a: float, z1a: float, z0b: float, z1b: float,
             u0: float = 0.0):
        """A vertical wall from plan point a to b (outward to the right of a -> b), bottom
        and top heights at each end."""
        L = math.sqrt((b[0] - a[0]) ** 2 + (b[1] - a[1]) ** 2)
        if L < 0.002:
            return
        self.quad(slot, (a[0], a[1], z0a), (b[0], b[1], z0b), (b[0], b[1], z1b),
                  (a[0], a[1], z1a),
                  ((u0, z0a), (u0 + L, z0b), (u0 + L, z1b), (u0, z1a)))

    def prism(self, slot: str, ring, z0: float, z1: float, top: bool = True,
              bottom: bool = False, holes=()):
        """A vertical prism over a plan ring (any direction), walls flat-shaded."""
        r = _ccw(ring)
        u = 0.0
        for i in range(len(r)):
            a, b = r[i], r[(i + 1) % len(r)]
            self.wall(slot, a, b, z0, z1, z0, z1, u)
            u += math.sqrt((b[0] - a[0]) ** 2 + (b[1] - a[1]) ** 2)
        for h in holes:
            hr = _ccw(h)[::-1]
            for i in range(len(hr)):
                a, b = hr[i], hr[(i + 1) % len(hr)]
                self.wall(slot, a, b, z0, z1, z0, z1)
        if top:
            self.poly(slot, r, [_ccw(h)[::-1] for h in holes], z=z1)
        if bottom:
            self.poly(slot, r, [_ccw(h)[::-1] for h in holes], z=z0, up=False)

    def box(self, slot: str, cx: float, cy: float, z0: float, along: float, across: float,
            up: float, yaw_deg: float = 0.0, bottom: bool = False):
        """A box on a plan center, `along` its yaw, `across` it, from z0 up."""
        h = M.radians(yaw_deg)
        ux, uy = M.cos(h), M.sin(h)
        self.obox(slot, cx, cy, z0, along, across, up, ux, uy, bottom)

    def obox(self, slot: str, cx: float, cy: float, z0: float, along: float, across: float,
             up: float, ux: float, uy: float, bottom: bool = False):
        vx, vy = -uy, ux
        ha, hc = along / 2.0, across / 2.0
        ring = [(cx - ux * ha - vx * hc, cy - uy * ha - vy * hc),
                (cx + ux * ha - vx * hc, cy + uy * ha - vy * hc),
                (cx + ux * ha + vx * hc, cy + uy * ha + vy * hc),
                (cx - ux * ha + vx * hc, cy - uy * ha + vy * hc)]
        self.prism(slot, ring, z0, z0 + up, True, bottom)

    def beam(self, slot: str, p, q, w: float, h: float):
        """A square beam between two 3D points (its section w by h, `h` along the vertical
        plane through the beam), four sides, no ends."""
        dx, dy, dz = q[0] - p[0], q[1] - p[1], q[2] - p[2]
        L = math.sqrt(dx * dx + dy * dy + dz * dz)
        if L < 0.01:
            return
        tx, ty, tz = dx / L, dy / L, dz / L
        # side axis: horizontal, perpendicular to the beam (or east for a vertical one)
        sx, sy = -ty, tx
        sL = math.sqrt(sx * sx + sy * sy)
        if sL < 1e-6:
            sx, sy, sz = 1.0, 0.0, 0.0
        else:
            sx, sy, sz = sx / sL, sy / sL, 0.0
        ux = ty * sz - tz * sy
        uy = tz * sx - tx * sz
        uz = tx * sy - ty * sx
        hw, hh = w / 2.0, h / 2.0
        corners = [(-hw, -hh), (hw, -hh), (hw, hh), (-hw, hh)]

        def at(c, base):
            return (base[0] + sx * c[0] + ux * c[1], base[1] + sy * c[0] + uy * c[1],
                    base[2] + sz * c[0] + uz * c[1])
        for k in range(4):
            c0, c1 = corners[k], corners[(k + 1) % 4]
            self.quad(slot, at(c0, p), at(c0, q), at(c1, q), at(c1, p))

    def cylinder(self, slot: str, cx: float, cy: float, r: float, z0: float, z1: float,
                 n: int = 16, top: bool = True, r1: float | None = None):
        """A vertical cylinder (or a cone frustum with top radius r1), smooth sides."""
        r1 = r if r1 is None else r1
        rows = []
        uvs = []
        for k in range(n + 1):
            a = 2.0 * M.PI * (k % n) / n
            c, s = M.cos(a), M.sin(a)
            rows.append([(cx + r * c, cy + r * s, z0), (cx + r1 * c, cy + r1 * s, z1)])
            uvs.append([(r * a, z0), (r * a, z1)])
        self.grid(slot, rows, uvs)
        if top and r1 > 0.0:
            ring = [(cx + r1 * M.cos(2.0 * M.PI * k / n), cy + r1 * M.sin(2.0 * M.PI * k / n))
                    for k in range(n)]
            self.poly(slot, ring, z=z1)

    def sweep(self, slot: str, frames, profile, closed: bool = False, uscale=None):
        """A cross-section swept along frames [(x, y, z, nx, ny, k, s), ...] (left normal
        nx, ny, miter factor k, distance s): profile [(t, dz), ...] in the section plane (t
        to the left, dz up), clockwise in that plane (counterclockwise as seen looking along
        the direction of travel) for an outward-facing surface. Each profile edge is a strip of its own (hard edges at
        the profile's corners), smooth along the path."""
        prof = list(profile) + ([profile[0]] if closed else [])
        for e in range(len(prof) - 1):
            (t0, z0), (t1, z1) = prof[e], prof[e + 1]
            w = math.sqrt((t1 - t0) ** 2 + (z1 - z0) ** 2)
            if w < 1e-4:
                continue
            rows, uvs, exp = [], [], []
            dt, dz = t1 - t0, z1 - z0
            for (x, y, z, nx, ny, k, s) in frames:
                rows.append([(x + nx * k * t0, y + ny * k * t0, z + z0),
                             (x + nx * k * t1, y + ny * k * t1, z + z1)])
                uvs.append([(s, 0.0), (s, w)])
                # the section edge (dt, dz) faces (-dz, dt) in the section plane
                exp.append((-dz * nx, -dz * ny, dt))
            self.grid(slot, rows, uvs, expect=exp)

    # -- finishing -----------------------------------------------------------------------

    def finish(self, materials: dict[str, int]) -> list[Primitive]:
        """glTF primitives per slot (in the order slots were first used), lean."""
        out = []
        for name, sl in self.slots.items():
            if not sl.idx:
                continue
            nrm = _normals(sl)
            out.append(Primitive(material=materials[name],
                                 positions=np.array(sl.pos, dtype=np.int64),
                                 indices=np.array(sl.idx, dtype=np.int64),
                                 normals=np.array(nrm, dtype=np.float64),
                                 uv0=np.array(sl.uv, dtype=np.float64)))
        return out

    def bounds_mm(self):
        lo = [None, None, None]
        hi = [None, None, None]
        for sl in self.slots.values():
            for p in sl.pos:
                for k in range(3):
                    if lo[k] is None or p[k] < lo[k]:
                        lo[k] = p[k]
                    if hi[k] is None or p[k] > hi[k]:
                        hi[k] = p[k]
        return lo, hi


def _normals(sl: _Slot) -> list:
    if not sl.auto:
        return list(sl.nrm)
    acc: dict[int, list[int]] = {}
    for t in range(0, len(sl.idx), 3):
        a, b, c = sl.idx[t], sl.idx[t + 1], sl.idx[t + 2]
        n = _cross(sl.pos[a], sl.pos[b], sl.pos[c])
        for v in (a, b, c):
            if sl.nrm[v] is None:
                s = acc.get(v)
                if s is None:
                    acc[v] = [n[0], n[1], n[2]]
                else:
                    s[0] += n[0]
                    s[1] += n[1]
                    s[2] += n[2]
    out = []
    for v, n in enumerate(sl.nrm):
        if n is not None:
            out.append(n)
        else:
            out.append(_unit3(acc.get(v, (0, 0, 1))))
    return out


def _ccw(ring) -> list[tuple[float, float]]:
    pts = [(float(p[0]), float(p[1])) for p in ring]
    if len(pts) > 1 and pts[0] == pts[-1]:
        pts.pop()
    s = 0.0
    for i in range(len(pts)):
        x0, y0 = pts[i]
        x1, y1 = pts[(i + 1) % len(pts)]
        s += x0 * y1 - x1 * y0
    return pts if s > 0 else pts[::-1]


def ccw(ring) -> list[tuple[float, float]]:
    return _ccw(ring)


def check(slots: dict[str, _Slot]) -> dict:
    """Mesh validity (scope section 9) on the integer positions: degenerate triangles (none
    can be left: they are dropped), duplicate triangles, winding (no directed edge used by
    two triangles of a slot: neighbors run round their shared edge in opposite directions;
    a flat face's normal on the side its triangles face), indices in range, UVs finite,
    unit normals."""
    bad = {"degenerate": 0, "duplicate": 0, "winding": 0, "index": 0, "uv": 0, "normal": 0}
    for sl in slots.values():
        nrm = _normals(sl)
        nv = len(sl.pos)
        seen = set()
        edges = set()
        for t in range(0, len(sl.idx), 3):
            a, b, c = sl.idx[t], sl.idx[t + 1], sl.idx[t + 2]
            if not (0 <= a < nv and 0 <= b < nv and 0 <= c < nv):
                bad["index"] += 1
                continue
            pa, pb, pc = sl.pos[a], sl.pos[b], sl.pos[c]
            n = _cross(pa, pb, pc)
            if n == (0, 0, 0):
                bad["degenerate"] += 1
                continue
            key = tuple(sorted((pa, pb, pc)))
            if key in seen:
                bad["duplicate"] += 1
                continue
            seen.add(key)
            for e in ((pa, pb), (pb, pc), (pc, pa)):
                if e in edges:
                    bad["winding"] += 1
                    break
                edges.add(e)
            for v in (a, b, c):
                if sl.nrm[v] is not None:
                    m = sl.nrm[v]
                    if n[0] * m[0] + n[1] * m[1] + n[2] * m[2] <= 0.0:
                        bad["winding"] += 1
                        break
        for u, v in sl.uv:
            if not (math.isfinite(u) and math.isfinite(v)):
                bad["uv"] += 1
        for n in nrm:
            L = n[0] * n[0] + n[1] * n[1] + n[2] * n[2]
            if abs(L - 1.0) > 1e-6:
                bad["normal"] += 1
    return bad
