"""Mesh shapes for props, plants and signs, on AG7's integer millimeter mesh (`streets.kit`).

Every prop is built in its own frame: x along the prop's yaw, y to its left, z up from its
position (M6's convention, which the blockout's prototypes follow). These helpers add to a
`Mesh` whose origin is that frame's: boxes from bounds, oriented boxes, quads facing a given
side, extrusions of a profile, surfaces of revolution, tubes along 3D polylines (parallel
transport frames), flat fans (leaves) and catenaries. Angles come from citygen's `dmath`, so
the vertices are the same on every machine.
"""

from __future__ import annotations

import math

from citygen import dmath as M

from ..streets.kit import Mesh, ccw

__all__ = ["Mesh", "blk", "obb", "quad_out", "extrude", "lathe", "tube", "fan", "ring",
           "rot", "norm", "cross", "sub", "add", "mul", "catenary"]

_RINGS: dict[int, list[tuple[float, float]]] = {}


def ring(n: int, phase: float = 0.0) -> list[tuple[float, float]]:
    """(cos, sin) of n angles round a circle (dmath, cached when phase is 0)."""
    if phase == 0.0 and n in _RINGS:
        return _RINGS[n]
    out = [(M.cos(2.0 * M.PI * k / n + phase), M.sin(2.0 * M.PI * k / n + phase))
           for k in range(n)]
    if phase == 0.0:
        _RINGS[n] = out
    return out


def sub(a, b):
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def add(a, b):
    return (a[0] + b[0], a[1] + b[1], a[2] + b[2])


def mul(a, k: float):
    return (a[0] * k, a[1] * k, a[2] * k)


def dot(a, b) -> float:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def cross(a, b):
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def norm(a):
    L = math.sqrt(dot(a, a))
    return (0.0, 0.0, 1.0) if L == 0.0 else (a[0] / L, a[1] / L, a[2] / L)


def rot(x: float, y: float, yaw_deg: float) -> tuple[float, float]:
    a = M.radians(yaw_deg)
    c, s = M.cos(a), M.sin(a)
    return (x * c - y * s, x * s + y * c)


def quad_out(m: Mesh, slot: str, a, b, c, d, out) -> None:
    """A planar quad a-b-c-d (in order round it), facing `out` (its winding fixed to it)."""
    n = cross(sub(b, a), sub(c, a))
    if dot(n, out) < 0.0:
        a, b, c, d = a, d, c, b
    m.quad(slot, a, b, c, d)


def blk(m: Mesh, slot: str, x0: float, x1: float, y0: float, y1: float, z0: float,
        z1: float, bottom: bool = False) -> None:
    """An axis-aligned box from its bounds (frame axes)."""
    if x1 - x0 < 0.002 or y1 - y0 < 0.002 or z1 - z0 < 0.002:
        return
    m.prism(slot, [(x0, y0), (x1, y0), (x1, y1), (x0, y1)], z0, z1, True, bottom)


def obb(m: Mesh, slot: str, c, ax, ay, az, hx: float, hy: float, hz: float,
        faces: str = "xXyYzZ") -> None:
    """An oriented box: center c, unit axes ax, ay, az (right-handed), half extents; `faces`
    picks the sides drawn (x: -ax, X: +ax, ...)."""
    def P(i, j, k):
        return (c[0] + ax[0] * i * hx + ay[0] * j * hy + az[0] * k * hz,
                c[1] + ax[1] * i * hx + ay[1] * j * hy + az[1] * k * hz,
                c[2] + ax[2] * i * hx + ay[2] * j * hy + az[2] * k * hz)
    if "X" in faces:
        quad_out(m, slot, P(1, -1, -1), P(1, 1, -1), P(1, 1, 1), P(1, -1, 1), ax)
    if "x" in faces:
        quad_out(m, slot, P(-1, -1, -1), P(-1, 1, -1), P(-1, 1, 1), P(-1, -1, 1), mul(ax, -1))
    if "Y" in faces:
        quad_out(m, slot, P(-1, 1, -1), P(1, 1, -1), P(1, 1, 1), P(-1, 1, 1), ay)
    if "y" in faces:
        quad_out(m, slot, P(-1, -1, -1), P(1, -1, -1), P(1, -1, 1), P(-1, -1, 1), mul(ay, -1))
    if "Z" in faces:
        quad_out(m, slot, P(-1, -1, 1), P(1, -1, 1), P(1, 1, 1), P(-1, 1, 1), az)
    if "z" in faces:
        quad_out(m, slot, P(-1, -1, -1), P(1, -1, -1), P(1, 1, -1), P(-1, 1, -1), mul(az, -1))


def beam(m: Mesh, slot: str, p, q, w: float, h: float | None = None,
         ends: bool = True) -> None:
    """A square beam between two 3D points (w across, h in the vertical plane), with ends."""
    d = sub(q, p)
    L = math.sqrt(dot(d, d))
    if L < 0.004:
        return
    t = mul(d, 1.0 / L)
    s = cross((0.0, 0.0, 1.0), t)
    if dot(s, s) < 1e-10:
        s = (0.0, 1.0, 0.0)
    s = norm(s)
    u = cross(t, s)
    obb(m, slot, mul(add(p, q), 0.5), t, s, u, L / 2.0, w / 2.0, (h or w) / 2.0,
        "xXyYzZ" if ends else "yYzZ")


def extrude(m: Mesh, slot: str, prof, axis: str, a0: float, a1: float,
            ends: bool = True) -> None:
    """A profile extruded along a frame axis: `axis` "x" (profile in (y, z)) or "y" (profile
    in (x, z)), from a0 to a1; flat sides, both end faces."""
    r = ccw(prof)
    n = len(r)
    if axis == "y":
        def P(u, v, a):
            return (u, a, v)
        end_n = (0.0, 1.0, 0.0)
    else:
        def P(u, v, a):
            return (a, u, v)
        end_n = (1.0, 0.0, 0.0)
    for i in range(n):
        (u0, v0), (u1, v1) = r[i], r[(i + 1) % n]
        if abs(u1 - u0) + abs(v1 - v0) < 0.002:
            continue
        # outward in the profile plane: (dv, -du) for a counterclockwise ring
        o2 = (v1 - v0, -(u1 - u0))
        out = P(o2[0], o2[1], 0.0)
        quad_out(m, slot, P(u0, v0, a0), P(u1, v1, a0), P(u1, v1, a1), P(u0, v0, a1), out)
    if ends:
        if axis == "y":
            # (u, v) = (x, z): x cross z = -y
            m.face(slot, (0.0, a0, 0.0), (1.0, 0.0, 0.0), (0.0, 0.0, 1.0), r)
            m.face(slot, (0.0, a1, 0.0), (0.0, 0.0, 1.0), (1.0, 0.0, 0.0),
                   [(v, u) for u, v in r[::-1]])
        else:
            # (u, v) = (y, z): y cross z = +x
            m.face(slot, (a1, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0), r)
            m.face(slot, (a0, 0.0, 0.0), (0.0, 0.0, 1.0), (0.0, 1.0, 0.0),
                   [(v, u) for u, v in r[::-1]])
    del end_n


def lathe(m: Mesh, slot: str, prof, n: int = 12, cx: float = 0.0, cy: float = 0.0,
          caps: bool = True) -> None:
    """A surface of revolution round the vertical through (cx, cy): prof [(r, z), ...] from
    the bottom up; caps where the first or last radius is not zero."""
    rows, uvs = [], []
    rg = ring(n)
    for k in range(n + 1):
        c, s = rg[k % n]
        rows.append([(cx + r * c, cy + r * s, z) for r, z in prof])
        uvs.append([(r * 2.0 * M.PI * k / n, z) for r, z in prof])
    m.grid(slot, rows, uvs)
    if caps:
        r0, z0 = prof[0]
        r1, z1 = prof[-1]
        if r0 > 0.002:
            m.poly(slot, [(cx + r0 * c, cy + r0 * s) for c, s in rg], z=z0, up=False)
        if r1 > 0.002:
            m.poly(slot, [(cx + r1 * c, cy + r1 * s) for c, s in rg], z=z1)


def tube(m: Mesh, slot: str, pts, radii, n: int = 6, caps: bool = True,
         phase: float = 0.0) -> None:
    """A tube along a 3D polyline (radius per point or one radius), parallel-transport
    frames so it does not twist; flat caps at both ends."""
    pts = [tuple(p) for p in pts]
    k = len(pts)
    if k < 2:
        return
    rr = radii if isinstance(radii, (list, tuple)) else [radii] * k
    tans = []
    for i in range(k):
        a = pts[max(i - 1, 0)]
        b = pts[min(i + 1, k - 1)]
        tans.append(norm(sub(b, a)))
    t0 = tans[0]
    ref = (0.0, 0.0, 1.0) if abs(t0[2]) < 0.9 else (1.0, 0.0, 0.0)
    nrm = norm(cross(ref, t0))
    rg = ring(n, phase)
    rows, uvs = [], []
    s_acc = 0.0
    frames = []
    for i in range(k):
        t = tans[i]
        # transport the normal: remove its component along the new tangent
        nrm = norm(sub(nrm, mul(t, dot(nrm, t))))
        bi = cross(t, nrm)
        frames.append((nrm, bi))
        if i:
            d = sub(pts[i], pts[i - 1])
            s_acc += math.sqrt(dot(d, d))
        ring_pts = []
        uv_row = []
        for j in range(n + 1):
            c, s = rg[j % n]
            r = rr[i]
            ring_pts.append((pts[i][0] + (nrm[0] * c + bi[0] * s) * r,
                             pts[i][1] + (nrm[1] * c + bi[1] * s) * r,
                             pts[i][2] + (nrm[2] * c + bi[2] * s) * r))
            uv_row.append((s_acc, r * 2.0 * M.PI * j / n))
        rows.append(ring_pts)
        uvs.append(uv_row)
    # rows along the tube, columns round it: turned over to face outward
    m.grid(slot, rows, uvs, flip=True)
    if caps:
        for i, sign in ((0, -1.0), (k - 1, 1.0)):
            if rr[i] < 0.004:
                continue
            nrm_i, bi_i = frames[i]
            t = tans[i]
            pts3 = [(pts[i][0] + (nrm_i[0] * c + bi_i[0] * s) * rr[i],
                     pts[i][1] + (nrm_i[1] * c + bi_i[1] * s) * rr[i],
                     pts[i][2] + (nrm_i[2] * c + bi_i[2] * s) * rr[i]) for c, s in rg]
            fan(m, slot, pts[i], pts3, mul(t, sign))


def fan(m: Mesh, slot: str, center, pts3, out) -> None:
    """A flat polygon as a fan round `center` (a convex or star-shaped outline), facing
    `out`: its own vertices, the face normal."""
    sl = m._slot(slot)
    n3 = norm(out)
    c = m.P(*center)
    ci = m._add(sl, c, n3, (0.0, 0.0))
    ids = []
    for p in pts3:
        q = m.P(*p)
        ids.append(m._add(sl, q, n3, ((p[0] - center[0]) + (p[1] - center[1]),
                                      p[2] - center[2])))
    e = (int(round(out[0] * 1000)), int(round(out[1] * 1000)), int(round(out[2] * 1000)))
    for i in range(len(ids)):
        a, b = ids[i], ids[(i + 1) % len(ids)]
        if not m._tri(sl, ci, a, b, e):
            m._tri(sl, ci, b, a, e)


def catenary(a, b, sag: float, n: int = 10) -> list[tuple[float, float, float]]:
    """Points of a hanging cable from a to b (3D) sagging `sag` at its middle (a parabola,
    close to the catenary at these ratios)."""
    out = []
    for i in range(n + 1):
        t = i / n
        out.append((a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t,
                    a[2] + (b[2] - a[2]) * t - 4.0 * sag * t * (1.0 - t)))
    return out


def check(slots: dict) -> dict:
    """Mesh validity for props (scope section 9) on the integer positions: degenerate and
    duplicate triangles (the same three positions in a slot: two faces fighting), normals
    that agree with their faces, indices in range, finite UVs, unit normals. A prop is an
    assembly of closed parts that may touch, so unlike a street piece's mesh an edge may be
    shared by more than two of its triangles."""
    from ..streets.kit import _cross, _normals
    bad = {"degenerate": 0, "duplicate": 0, "winding": 0, "index": 0, "uv": 0, "normal": 0}
    for sl in slots.values():
        nrm = _normals(sl)
        nv = len(sl.pos)
        seen = set()
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
            for v in (a, b, c):
                mv = sl.nrm[v]
                if mv is not None and n[0] * mv[0] + n[1] * mv[1] + n[2] * mv[2] <= 0.0:
                    bad["winding"] += 1
                    break
        for uu, vv in sl.uv:
            if not (math.isfinite(uu) and math.isfinite(vv)):
                bad["uv"] += 1
        for n in nrm:
            L = n[0] * n[0] + n[1] * n[1] + n[2] * n[2]
            if abs(L - 1.0) > 1e-6:
                bad["normal"] += 1
    return bad
