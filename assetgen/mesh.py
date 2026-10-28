"""Mesh building on integer millimeters (scope section 8).

Generators describe planar faces in a frame of their own: an origin and two axes in
integer millimeters, the face as 2D integer rings (outer and holes) in that frame. The
builder triangulates them exactly (`triangulate`), maps the vertices to the building
frame (rounded to the millimeter once), and adds a flat normal, UV0 in meters along the
face (world-scale tiling), UV1 from 0 to 1 over the face, and a vertex color. Faces are
grouped per material slot into glTF primitives in the order the slots are first used.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

from .gltf import Primitive
from .triangulate import triangulate


@dataclass
class Frame:
    """A plane: origin (mm), axis u and axis v (unit vectors, citygen frame), and where
    its UV0 starts (meters along u and v)."""
    o: tuple[int, int, int]
    u: tuple[float, float, float]
    v: tuple[float, float, float]
    uv_at: tuple[float, float] = (0.0, 0.0)

    def point(self, s: int, t: int) -> tuple[int, int, int]:
        return tuple(int(round(self.o[i] + s * self.u[i] + t * self.v[i])) for i in range(3))

    @property
    def normal(self) -> tuple[float, float, float]:
        u, v = self.u, self.v
        n = (u[1] * v[2] - u[2] * v[1], u[2] * v[0] - u[0] * v[2], u[0] * v[1] - u[1] * v[0])
        L = math.sqrt(n[0] * n[0] + n[1] * n[1] + n[2] * n[2])
        return (n[0] / L, n[1] / L, n[2] / L)


def wall_frame(a: tuple[int, int], b: tuple[int, int], z0: int, s_at: float = 0.0) -> Frame:
    """A vertical wall from a to b (mm, plan), outward to the right of a -> b; u along
    the wall, v up."""
    dx, dy = b[0] - a[0], b[1] - a[1]
    L = math.sqrt(dx * dx + dy * dy)
    return Frame((a[0], a[1], z0), (dx / L, dy / L, 0.0), (0.0, 0.0, 1.0),
                 (s_at, z0 / 1000.0))


def flat_frame(z: int, up: bool = True) -> Frame:
    """A horizontal plane at height z, facing up (roofs) or down (soffits)."""
    return Frame((0, 0, z), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0) if up else (0.0, -1.0, 0.0))


@dataclass
class _Prim:
    pos: list = field(default_factory=list)
    nrm: list = field(default_factory=list)
    uv0: list = field(default_factory=list)
    uv1: list = field(default_factory=list)
    col: list = field(default_factory=list)
    idx: list = field(default_factory=list)


class MeshBuilder:
    def __init__(self):
        self.slots: dict[str, _Prim] = {}

    def _slot(self, material: str) -> _Prim:
        if material not in self.slots:
            self.slots[material] = _Prim()
        return self.slots[material]

    @property
    def triangles(self) -> int:
        return sum(len(p.idx) // 3 for p in self.slots.values())

    def face(self, material: str, fr: Frame, outer, holes=(), color=(255, 255, 255, 255)):
        """A planar face: 2D integer rings in the frame (mm), counterclockwise seen from
        the side the normal points to."""
        tris = triangulate(outer, holes)
        if not tris:
            return
        pts2 = [tuple(p) for p in outer] + [tuple(p) for h in holes for p in h]
        used = sorted({i for t in tris for i in t})
        ss = [pts2[i][0] for i in used]
        ts = [pts2[i][1] for i in used]
        s0, s1, t0, t1 = min(ss), max(ss), min(ts), max(ts)
        ds, dt = max(s1 - s0, 1), max(t1 - t0, 1)
        pr = self._slot(material)
        base = len(pr.pos)
        where = {}
        n = fr.normal
        for i in used:
            s, t = pts2[i]
            where[i] = base + len(where)
            pr.pos.append(fr.point(s, t))
            pr.nrm.append(n)
            pr.uv0.append((fr.uv_at[0] + s / 1000.0, fr.uv_at[1] + t / 1000.0))
            pr.uv1.append(((s - s0) / ds, (t - t0) / dt))
            pr.col.append(color)
        for a, b, c in tris:
            pr.idx += [where[a], where[b], where[c]]

    def quad(self, material: str, fr: Frame, s0: int, t0: int, s1: int, t1: int,
             color=(255, 255, 255, 255)):
        self.face(material, fr, [(s0, t0), (s1, t0), (s1, t1), (s0, t1)], (), color)

    def box(self, material: str, x0: int, y0: int, z0: int, x1: int, y1: int, z1: int,
            color=(255, 255, 255, 255), bottom: bool = False):
        """An axis-aligned box in the building frame (mm), five or six faces."""
        dx, dy, dz = x1 - x0, y1 - y0, z1 - z0
        self.quad(material, Frame((x0, y0, z0), (1.0, 0.0, 0.0), (0.0, 0.0, 1.0),
                                  (x0 / 1000.0, z0 / 1000.0)), 0, 0, dx, dz, color)
        self.quad(material, Frame((x1, y1, z0), (-1.0, 0.0, 0.0), (0.0, 0.0, 1.0),
                                  (-x1 / 1000.0, z0 / 1000.0)), 0, 0, dx, dz, color)
        self.quad(material, Frame((x1, y0, z0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0),
                                  (y0 / 1000.0, z0 / 1000.0)), 0, 0, dy, dz, color)
        self.quad(material, Frame((x0, y1, z0), (0.0, -1.0, 0.0), (0.0, 0.0, 1.0),
                                  (-y1 / 1000.0, z0 / 1000.0)), 0, 0, dy, dz, color)
        self.quad(material, Frame((x0, y0, z1), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0),
                                  (x0 / 1000.0, y0 / 1000.0)), 0, 0, dx, dy, color)
        if bottom:
            self.quad(material, Frame((x0, y1, z0), (1.0, 0.0, 0.0), (0.0, -1.0, 0.0)),
                      0, 0, dx, dy, color)

    def oriented_box(self, material: str, cx: int, cy: int, z0: int, along: int, across: int,
                     up: int, ux: float, uy: float, color=(255, 255, 255, 255)):
        """A box centered at (cx, cy) on the plan, `along` mm in direction (ux, uy),
        `across` mm across it, from z0 up `up` mm (walls and a top)."""
        vx, vy = -uy, ux
        ha, hc = along / 2.0, across / 2.0
        corners = [(cx - ux * ha - vx * hc, cy - uy * ha - vy * hc),
                   (cx + ux * ha - vx * hc, cy + uy * ha - vy * hc),
                   (cx + ux * ha + vx * hc, cy + uy * ha + vy * hc),
                   (cx - ux * ha + vx * hc, cy - uy * ha + vy * hc)]
        corners = [(int(round(x)), int(round(y))) for x, y in corners]
        for i in range(4):
            a, b = corners[i], corners[(i + 1) % 4]
            fr = wall_frame(a, b, z0)
            L = int(round(math.sqrt((b[0] - a[0]) ** 2 + (b[1] - a[1]) ** 2)))
            self.quad(material, fr, 0, 0, L, up, color)
        top = Frame((corners[0][0], corners[0][1], z0 + up), (ux, uy, 0.0), (vx, vy, 0.0))
        self.quad(material, top, 0, 0, along, across, color)

    def primitives(self, materials: dict[str, int]) -> list[Primitive]:
        out = []
        for name, pr in self.slots.items():
            if not pr.idx:
                continue
            out.append(Primitive(
                material=materials[name], positions=np.array(pr.pos, dtype=np.int64),
                indices=np.array(pr.idx, dtype=np.int64),
                normals=np.array(pr.nrm, dtype=np.float64),
                uv0=np.array(pr.uv0, dtype=np.float64), uv1=np.array(pr.uv1, dtype=np.float64),
                colors=np.array(pr.col, dtype=np.uint8)))
        return out


def _cross(a, b):
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def quad3(mb: MeshBuilder, material: str, p0, p1, p2, p3, color=(255, 255, 255, 255)):
    """A planar quad from four integer mm points, counterclockwise seen from its front; flat
    normal from the exact cross product, UV0 in meters on the face's own axes, UV1 its
    corners."""
    e1 = tuple(p1[i] - p0[i] for i in range(3))
    e2 = tuple(p3[i] - p0[i] for i in range(3))
    n = _cross(e1, e2)
    L = math.sqrt(n[0] * n[0] + n[1] * n[1] + n[2] * n[2])
    if L == 0:
        return
    nf = (n[0] / L, n[1] / L, n[2] / L)
    l1 = math.sqrt(sum(c * c for c in e1)) or 1.0
    l2 = math.sqrt(sum(c * c for c in e2)) or 1.0
    pr = mb._slot(material)
    base = len(pr.pos)
    for p, uv1 in ((p0, (0.0, 0.0)), (p1, (1.0, 0.0)), (p2, (1.0, 1.0)), (p3, (0.0, 1.0))):
        pr.pos.append(tuple(int(c) for c in p))
        pr.nrm.append(nf)
        d = tuple(p[i] - p0[i] for i in range(3))
        pr.uv0.append((sum(d[i] * e1[i] for i in range(3)) / l1 / 1000.0,
                       sum(d[i] * e2[i] for i in range(3)) / l2 / 1000.0))
        pr.uv1.append(uv1)
        pr.col.append(color)
    pr.idx += [base, base + 1, base + 2, base, base + 2, base + 3]
