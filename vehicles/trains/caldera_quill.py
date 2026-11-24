"""Caldera Quill: a sky tube pod by Caldera Transit Works (made-up names only).

A magnetically levitated, wheel-less capsule that runs inside a 7 m glass tube, two tracks
side by side: 9.0 m long, 2.4 m wide, 2.7 m tall, one double plug door a side at x = 0, a
flat floor at z = 0.30 and a complete interior a person can stand in. The end pod (the
default) has the nib: the section is cut by a raked surface from the spine's edge down to a
point, the cut is the windshield over an observation lounge, and its tip is metal.
CYBERGEN_VARIANT=mid builds the middle pod, a gangway at both ends; CYBERGEN_SHUT=1 builds
every door shut (the left door is slid open in the views "hero" and "door" otherwise).

The body is not a subdivision cage: it is one surface in closed form, F(x, s) below the rim
(s the arc length round the body's section, x along the pod) and G(x, y) over it (the spine
of the roof, and on the end pod the windshield and the nib), and every panel, pane, lining
and frame is a region of that surface meshed in its own right (trim), so the outer skin, the
glass and the inner lining are different surfaces with real thickness between them. Glass
is one surface, drawn thin (thin_glass).

Walkability, as built: floor flat at z = 0.30 from the gangway to the lounge; the aisle
0.78 m clear between the poles; 2.26 m under the spine's console, 2.06 m in the gangway,
2.01 m in the doorways; seats clear of the doorway behind draught screens.

Frame: x forward along the tube, y left, z up, meters; z = 0 is the bottom of the body.
Names: body.* the shell, glass.* the panes, door.<l|r>.<a|b> the four door leaves,
interior.* everything inside, mag.* the levitation gear, track.* (in the studio's
collection) what it rides on and the tube round it.
"""
import os
import sys
from math import atan2, ceil, cos, pi, sin, sqrt
from math import radians as rad

import bpy
import numpy as np
from mathutils import Matrix, Vector
from mathutils.geometry import delaunay_2d_cdt

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import carkit as K                                  # noqa: E402
from carkit import Geo, V3                          # noqa: E402

MID = os.environ.get("CYBERGEN_VARIANT", "").strip().lower() == "mid"
SHUT = bool(os.environ.get("CYBERGEN_SHUT"))
STAGE = os.environ.get("QUILL_STAGE", "")           # "hull": the shell alone, to judge it

# ---------------------------------------------------------------------------------------
# the hard numbers
# ---------------------------------------------------------------------------------------
XA, XF = -4.5, 4.5                  # the body's ends
HW, TOP = 1.2, 2.7                  # half width, height
FLOOR = 0.30                        # top of the passenger floor
TH = 0.065                          # outer skin to inner lining
TUBE_R, TUBE_Z, TUBE_Y = 3.5, 2.45, 1.25    # the tube: radius, axis height, axis offset
DOOR_X = 0.70                       # half the door opening (1.4 m)
# the section (left half, from the keel up): belly, bilge, side, an elliptical vault, spine
BY, BR = 0.78, 0.42                 # where the belly ends, the bilge's radius
ZW = 1.25                           # the side is upright to here; above it the vault
VB = TOP - ZW                       # the vault's height (its half width is HW)
YSP = 0.24                          # the spine's edge (the rim on the barrel)
ZSP = ZW + VB * sqrt(1 - (YSP / HW) ** 2)
CH_Y, CH_D = 0.30, 0.19             # the guide beam's channel in the belly: half width, depth
# the nose (end pod): from X0 the plan narrows, the rim comes down, the keel rises
X0, X1 = (1.3, 4.5) if not MID else (98.0, 99.0)
ZTIP, BTIP = 0.95, 0.78             # the rim and the keel at the tip


def _section():
    P = [(BY * k / 200.0, 0.0) for k in range(200)]
    i_bilge = len(P)
    P += [(BY + BR * sin(a), BR - BR * cos(a)) for a in np.linspace(0, pi / 2, 400)]
    P += [(HW, z) for z in np.linspace(BR, ZW, 400)[1:]]
    a_sp = np.arccos(YSP / HW)
    P += [(HW * cos(a), ZW + VB * sin(a)) for a in np.linspace(0, a_sp, 1400)[1:]]
    i_spine = len(P) - 1
    P += [(HW * cos(a), ZW + VB * sin(a)) for a in np.linspace(a_sp, pi / 2, 200)[1:]]
    P = np.array(P)
    P[-1, 0] = 0.0
    s = np.concatenate([[0.0], np.cumsum(np.hypot(np.diff(P[:, 0]), np.diff(P[:, 1])))])
    return P[:, 0], P[:, 1], s, i_bilge, i_spine


SY_, SZ_, SS_, _IB, _ISP = _section()
S_END = float(SS_[-1])
S_SP = float(SS_[_ISP])             # the spine's edge


def s_z(z):
    """The arc length at which the section stands at height z (above the belly)."""
    return np.interp(z, SZ_[_IB:], SS_[_IB:])


def nose_u(x):
    return np.clip((np.asarray(x, float) - X0) / (X1 - X0), 0.0, 1.0)


def _smooth(t):
    t = np.clip(t, 0.0, 1.0)
    return t * t * (3 - 2 * t)


def plan(x):
    """The plan's scale: 1 on the barrel, 0 at the tip."""
    return (1 - nose_u(x) ** 1.9) ** 0.6


def keel(x):
    """How far the keel has risen."""
    return BTIP * np.clip((nose_u(x) - 0.45) / 0.55, 0, 1) ** 2.0


def rim_z(x):
    return ZSP - (ZSP - ZTIP) * nose_u(x) ** 1.3


def F(x, s, d=0.0):
    """The hull at x and arc length s (arrays), d inside it along its normal."""
    x = np.asarray(x, float)
    s = np.asarray(s, float)
    y0 = np.interp(s, SS_, SY_)
    z0 = np.interp(s, SS_, SZ_)
    b = keel(x)
    z = np.where(z0 < 1.0, b + z0 * (1 - b), z0)
    P = np.stack([x + 0 * y0, plan(x) * y0, z + 0 * x], axis=-1)
    d = np.asarray(d, float)
    if d.ndim or float(d) != 0.0:
        P = P - (d[..., None] if d.ndim else float(d)) * Fn(x, s)
    return P


def Fn(x, s):
    """The hull's outward normal."""
    e = 2e-4
    a = F(x, np.asarray(s) + e) - F(x, np.asarray(s) - e)
    b = F(np.asarray(x) + e, s) - F(np.asarray(x) - e, s)
    n = np.cross(a, b)
    ln = np.linalg.norm(n, axis=-1, keepdims=True)
    return n / np.maximum(ln, 1e-12)


_RX = np.linspace(XA - 1.0, 4.5, 6000)


def _rim_table():
    zr = rim_z(_RX)
    b = keel(_RX)
    z0 = np.where(zr < 1.0, (zr - b) / (1 - b), zr)
    return s_z(z0)


_RS = _rim_table()


def RS(x):
    """The rim: the arc length at which the hull ends and the cap begins."""
    return np.interp(x, _RX, _RS)


def rim_y(x):
    return plan(x) * np.interp(RS(x), SS_, SY_)


def cap_c(x):
    m = _smooth(nose_u(x) / 0.25)
    return (TOP - ZSP) * (1 - m) + 0.16 * rim_y(x) * m


def G(x, y, d=0.0):
    """The cap (the glass spine, the windshield) at x and y, d under it."""
    x = np.asarray(x, float)
    y = np.asarray(y, float)
    yr = np.maximum(rim_y(x), 1e-6)
    w = np.clip(y / yr, -1.0, 1.0)
    P = np.stack([x + 0 * y, y + 0 * x, rim_z(x) + cap_c(x) * (1 - w * w)], axis=-1)
    if d:
        P = P - d * Gn(x, y)
    return P


def Gn(x, y):
    e = 2e-4
    a = G(np.asarray(x) + e, y) - G(np.asarray(x) - e, y)
    b = G(x, np.asarray(y) + e) - G(x, np.asarray(y) - e)
    n = np.cross(a, b)
    return n / np.maximum(np.linalg.norm(n, axis=-1, keepdims=True), 1e-12)


def Fi(d):
    return lambda x, s: F(x, s, d)


def Gi(d):
    return lambda x, y: G(x, y, d)


def p3(P):
    return V3((float(P[0]), float(P[1]), float(P[2])))


def f1(x, s, d=0.0):
    return p3(F(np.array([x]), np.array([s]), d)[0])


def g1(x, y, d=0.0):
    return p3(G(np.array([x]), np.array([y]), d)[0])


# named lines of the section
S_SK = float(s_z(0.265))            # skirt to side; the doors' foot
S_ST0, S_ST1 = float(s_z(0.80)), float(s_z(0.905))      # the line color's stripe
S_DT = float(s_z(2.35))             # the doors' top
GAP = 0.0016                        # half a panel gap


# ---------------------------------------------------------------------------------------
# regions of a surface: loops in its two parameters, meshed with a constrained Delaunay
# triangulation over a lattice
# ---------------------------------------------------------------------------------------
XN = np.concatenate([np.arange(XA - 0.5, 1.5, 0.25), np.arange(1.5, 4.5001, 0.05)]) \
    if not MID else np.arange(XA - 0.5, 4.76, 0.25)


def _wa(a):
    return np.interp(a, XN, np.arange(len(XN)))


def _unwa(w):
    return np.interp(w, np.arange(len(XN)), XN)


def _inside(px, py, poly):
    x0, y0 = poly[:, 0], poly[:, 1]
    x1, y1 = np.roll(x0, -1), np.roll(y0, -1)
    c = np.zeros(len(px), bool)
    for i in range(len(poly)):
        if y0[i] == y1[i]:
            continue
        hit = ((y0[i] > py) != (y1[i] > py)) & \
              (px < x0[i] + (x1[i] - x0[i]) * (py - y0[i]) / (y1[i] - y0[i]))
        c ^= hit
    return c


def _resample(loop, hb, step=0.8, wa=_wa):
    P = np.asarray(loop, float)
    keep = [0]
    for i in range(1, len(P)):
        if np.hypot(*(P[i] - P[keep[-1]])) > 1e-7:
            keep.append(i)
    if len(keep) > 1 and np.hypot(*(P[keep[-1]] - P[keep[0]])) < 1e-7:
        keep.pop()
    P = P[keep]
    W = np.stack([wa(P[:, 0]), P[:, 1] / hb], axis=1)
    out = []
    n = len(W)
    for i in range(n):
        p, q = W[i], W[(i + 1) % n]
        k = max(1, int(ceil(np.hypot(*(q - p)) / step)))
        for j in range(k):
            out.append(p + (q - p) * j / k)
    return np.array(out)


def trim(surf, outer, holes=(), hb=0.04, out=True, lattice=True, plain=False):
    """A region of surf(a, b) -> points: outer and holes are loops of (a, b). Returns
    (vertices, triangles); out: the faces look along the surface's outward side (the hull:
    d(b) x d(a), which is the left half's outside), else the other way. plain: a and b are
    both meters (no warp of a onto the stations)."""
    wa = (lambda a: np.asarray(a, float) / hb) if plain else _wa
    un = (lambda w: np.asarray(w, float) * hb) if plain else _unwa
    loops = [_resample(outer, hb, wa=wa)] + [_resample(h, hb, wa=wa) for h in holes]
    pts, edges = [], []
    for L in loops:
        o = len(pts)
        pts += [tuple(p) for p in L]
        edges += [(o + i, o + (i + 1) % len(L)) for i in range(len(L))]
    B = np.array(pts)
    if lattice:
        lo, hi = B.min(axis=0), B.max(axis=0)
        ga, gb = np.meshgrid(np.arange(np.floor(lo[0]), np.ceil(hi[0]) + 1),
                             np.arange(np.floor(lo[1]), np.ceil(hi[1]) + 1))
        ga, gb = ga.ravel(), gb.ravel()
        ok = _inside(ga, gb, loops[0])
        for L in loops[1:]:
            ok &= ~_inside(ga, gb, L)
        ga, gb = ga[ok], gb[ok]
        if len(ga):
            far = np.ones(len(ga), bool)
            for k in range(0, len(B), 400):
                d2 = (ga[:, None] - B[None, k:k + 400, 0]) ** 2 + \
                     (gb[:, None] - B[None, k:k + 400, 1]) ** 2
                far &= d2.min(axis=1) > 0.2
            pts += list(zip(ga[far], gb[far]))
    res = delaunay_2d_cdt([Vector(p) for p in pts], edges, [], 0, 1e-7)
    vc = np.array([tuple(v) for v in res[0]])
    fc = [tuple(f) for f in res[2] if len(f) == 3]
    if not fc:
        return np.zeros((0, 3)), []
    T = np.array(fc)
    cen = vc[T].mean(axis=1)
    ok = _inside(cen[:, 0], cen[:, 1], loops[0])
    for L in loops[1:]:
        ok &= ~_inside(cen[:, 0], cen[:, 1], L)
    T = T[ok]
    a, b, c = vc[T[:, 0]], vc[T[:, 1]], vc[T[:, 2]]
    area = (b[:, 0] - a[:, 0]) * (c[:, 1] - a[:, 1]) - (b[:, 1] - a[:, 1]) * (c[:, 0] - a[:, 0])
    T = T[np.abs(area) > 1e-9]
    area = area[np.abs(area) > 1e-9]
    ccw = area > 0
    T = np.where((ccw != out)[:, None], T, T[:, ::-1])       # the hull's outside is cw
    used = np.unique(T)
    remap = -np.ones(len(vc), int)
    remap[used] = np.arange(len(used))
    V = surf(un(vc[used, 0]), vc[used, 1] * hb)
    return V, [tuple(int(i) for i in t) for t in remap[T]]


def mk(name, V, Fc, mat, mirror=True, solid=0.014, rim=True, bevel=0.003, coll=None,
       angle=22.0, body=False):
    """An object from vertices and faces: mirrored, given thickness (inward) and a bevel."""
    me = bpy.data.meshes.new(name)
    me.from_pydata([tuple(float(c) for c in v) for v in V], [], [tuple(f) for f in Fc])
    me.materials.append(K.need(mat))
    ob = bpy.data.objects.new(name, me)
    (coll or K.CAR).objects.link(ob)
    if mirror:
        md = ob.modifiers.new("mirror", 'MIRROR')
        md.use_axis = (False, True, False)
        md.merge_threshold = 0.0005
    if solid:
        md = ob.modifiers.new("solid", 'SOLIDIFY')
        md.offset = -1.0
        md.thickness = solid
        md.use_rim_only = rim
    if bevel:
        K.finish(ob, bevel=bevel, segs=2, angle=angle)
    else:
        me.shade_smooth()
        me.set_sharp_from_angle(angle=rad(35))
    if body:
        K.BODY.append(ob)
    return ob


def fn(v):
    return v if callable(v) else (lambda x, v=v: np.full(np.shape(x), float(v)))


def _xs(xa, xb):
    """Sample stations of a band: its ends, and fine ones along the nose."""
    xs = [xa, xb]
    if xb > X0 - 0.2:
        xs += list(np.arange(max(xa, X0 - 0.2), xb, 0.02))
    return np.unique(np.clip(np.array(xs), xa, xb))


def band(xa, xb, lo, hi, g=GAP, ga=None, gb=None):
    """The loop between s = lo(x) and s = hi(x) over [xa, xb], set in by g (ga, gb at the
    two ends). Where the two lines cross, the band ends in a point."""
    lo, hi = fn(lo), fn(hi)
    ga = g if ga is None else ga
    gb = g if gb is None else gb
    xa, xb = xa + ga, xb - gb
    xs = _xs(xa, xb)
    wide = lambda x: hi(x) - lo(x) - 2 * g
    ok = wide(xs) > 0.003
    if not ok.any():
        return None
    i0 = int(np.argmax(ok))
    i1 = len(xs) - 1 - int(np.argmax(ok[::-1]))
    tip_a = tip_b = None
    if i0 > 0:
        tip_a = _cross(wide, xs[i0 - 1], xs[i0])
    if i1 < len(xs) - 1:
        tip_b = _cross(wide, xs[i1 + 1], xs[i1])
    xs = xs[i0:i1 + 1]
    low = [(x, s) for x, s in zip(xs, lo(xs) + g)]
    up = [(x, s) for x, s in zip(xs, hi(xs) - g)]
    loop = []
    if tip_a is not None:
        loop.append((tip_a, float((lo(tip_a) + hi(tip_a)) / 2)))
    loop += low
    if tip_b is not None:
        loop.append((tip_b, float((lo(tip_b) + hi(tip_b)) / 2)))
    loop += up[::-1]
    return np.array(loop, float)


def _cross(f, a, b):
    """Where f changes sign between a (not ok) and b (ok)."""
    for _ in range(40):
        m = (a + b) / 2
        if f(np.array([m]))[0] > 0.003:
            b = m
        else:
            a = m
    return float(b)


def clip(loop, a, b, c):
    """The part of a loop where a x + b s <= c (Sutherland and Hodgman)."""
    if loop is None:
        return None
    out = []
    n = len(loop)
    for i in range(n):
        p, q = loop[i], loop[(i + 1) % n]
        fp, fq = a * p[0] + b * p[1] - c, a * q[0] + b * q[1] - c
        if fp <= 0:
            out.append(tuple(p))
        if (fp < 0 < fq) or (fq < 0 < fp):
            t = fp / (fp - fq)
            out.append(tuple(p + (q - p) * t))
    return np.array(out, float) if len(out) >= 3 else None


def fillet(loop, r, n=6, turn=25.0):
    """A loop with its sharp corners (turning more than turn degrees) cut round at r."""
    P = [np.array(p, float) for p in loop]
    m = len(P)
    out = []
    for i in range(m):
        a, p, b = P[i - 1], P[i], P[(i + 1) % m]
        u, v = a - p, b - p
        lu, lv = np.hypot(*u), np.hypot(*v)
        if lu < 1e-9 or lv < 1e-9:
            continue
        u, v = u / lu, v / lv
        ang = np.arccos(np.clip(np.dot(u, v), -1, 1))
        if abs(pi - ang) < rad(turn):
            out.append(p)
            continue
        t = min(r / np.tan(ang / 2), 0.45 * lu, 0.45 * lv)
        rr = t * np.tan(ang / 2)
        bis = (u + v) / np.hypot(*(u + v))
        cen = p + bis * (rr / np.sin(ang / 2))
        a0 = p + u * t - cen
        a1 = p + v * t - cen
        th0, th1 = atan2(a0[1], a0[0]), atan2(a1[1], a1[0])
        dth = (th1 - th0 + pi) % (2 * pi) - pi
        for k in range(n + 1):
            th = th0 + dth * k / n
            out.append(cen + rr * np.array((cos(th), sin(th))))
    return np.array(out)


def rrect(a0, a1, b0, b1, r, n=6):
    return fillet([(a0, b0), (a1, b0), (a1, b1), (a0, b1)], r, n)


def inset(loop, d):
    """A loop moved in by d (out with a negative d): each point along its corner's
    bisector. For smooth or filleted loops."""
    P = np.asarray(loop, float)
    a = np.roll(P, 1, axis=0)
    b = np.roll(P, -1, axis=0)
    t = b - a
    t /= np.maximum(np.hypot(t[:, 0], t[:, 1]), 1e-12)[:, None]
    nrm = np.stack([-t[:, 1], t[:, 0]], axis=1)             # left of the way round
    area = np.sum(P[:, 0] * b[:, 1] - b[:, 0] * P[:, 1])
    return P + nrm * (d if area > 0 else -d)


def ruled(surf_a, loop_a, surf_b, loop_b, closed=True, flip=False):
    """A strip between two loops of the same length on two surfaces (a reveal, a rim)."""
    A = surf_a(loop_a[:, 0], loop_a[:, 1])
    B = surf_b(loop_b[:, 0], loop_b[:, 1])
    n = len(A)
    V = np.concatenate([A, B])
    Fc = []
    for i in range(n if closed else n - 1):
        j = (i + 1) % n
        q = (i, j, n + j, n + i)
        Fc.append(q[::-1] if flip else q)
    return V, Fc


def dense(loop, step=0.03):
    """A loop with a point at least every step (in meters of its parameters)."""
    P = np.asarray(loop, float)
    out = []
    n = len(P)
    for i in range(n):
        p, q = P[i], P[(i + 1) % n]
        k = max(1, int(ceil(np.hypot(*(q - p)) / step)))
        for j in range(k):
            out.append(p + (q - p) * j / k)
    return np.array(out)


class Parts:
    """Meshes of several materials that become one object."""

    def __init__(self):
        self.items = []

    def add(self, V, Fc, mat, flat=False):
        if len(Fc):
            self.items.append((np.asarray(V, float), [tuple(f) for f in Fc], mat, flat))

    def geo(self, g, mat, flat=True):
        if g.f:
            self.items.append((np.array([tuple(p) for p in g.v]), list(g.f), mat, flat))

    def obj(self, name, flip_y=False, bevel=0.0, angle=30.0, coll=None, smooth=40.0):
        mats, V, Fc, mi, sm = [], [], [], [], []
        for (v, f, mat, flat) in self.items:
            if mat not in mats:
                mats.append(mat)
            o = len(V)
            v = v * np.array((1, -1, 1)) if flip_y else v
            V += [tuple(float(c) for c in p) for p in v]
            f = [tuple(o + i for i in (q[::-1] if flip_y else q)) for q in f]
            Fc += f
            mi += [mats.index(mat)] * len(f)
            sm += [not flat] * len(f)
        me = bpy.data.meshes.new(name)
        me.from_pydata(V, [], Fc)
        for m in mats:
            me.materials.append(K.need(m))
        me.polygons.foreach_set("material_index", mi)
        me.update()
        ob = bpy.data.objects.new(name, me)
        (coll or K.CAR).objects.link(ob)
        me.shade_smooth()
        me.set_sharp_from_angle(angle=rad(smooth))
        if bevel:
            md = ob.modifiers.new("bevel", 'BEVEL')
            md.width = bevel
            md.segments = 2
            md.limit_method = 'ANGLE'
            md.angle_limit = rad(angle)
        return ob


def geo_closed(g):
    """A Geo's solids with their faces turned outward (each solid is closed)."""
    me = g.mesh("tmp")
    V = np.array([tuple(v.co) for v in me.vertices])
    Fc = [tuple(p.vertices) for p in me.polygons]
    bpy.data.meshes.remove(me)
    return V, Fc


# ---------------------------------------------------------------------------------------
# materials
# ---------------------------------------------------------------------------------------
def thin_glass(name, color, ior=1.5):
    """A pane drawn as one surface: tinted, straight through (no bending, so a pane needs
    no thickness), mirroring by its angle; light and shadows pass it tinted. The kit's
    glass stays in the material (the game pack reads it), unlinked."""
    m, b = K.glass(name, color, ior)
    nt = m.node_tree
    out = next(n for n in nt.nodes if n.type == 'OUTPUT_MATERIAL')
    tr = nt.nodes.new('ShaderNodeBsdfTransparent')
    tr.inputs["Color"].default_value = (*color, 1.0)
    gl = nt.nodes.new('ShaderNodeBsdfGlossy')
    gl.inputs["Roughness"].default_value = 0.0
    fr = nt.nodes.new('ShaderNodeFresnel')
    geo = nt.nodes.new('ShaderNodeNewGeometry')         # the same from both sides
    io = nt.nodes.new('ShaderNodeMix')
    io.data_type = 'FLOAT'
    io.inputs[2].default_value = ior
    io.inputs[3].default_value = 1.0 / ior
    nt.links.new(geo.outputs["Backfacing"], io.inputs[0])
    nt.links.new(io.outputs[0], fr.inputs["IOR"])
    mx = nt.nodes.new('ShaderNodeMixShader')
    nt.links.new(fr.outputs[0], mx.inputs["Fac"])
    nt.links.new(tr.outputs[0], mx.inputs[1])
    nt.links.new(gl.outputs[0], mx.inputs[2])
    nt.links.new(mx.outputs[0], out.inputs["Surface"])
    return m


def make_materials():
    K.materials(paint=(0.60, 0.61, 0.60), paint_finish="pearl",
                paint2=(0.62, 0.17, 0.004), paint2_finish="gloss",
                dust_amount=0.0, glass=(0.40, 0.45, 0.48), glass_ior=1.3,
                led_front=(0.90, 0.96, 1.0), led_front_strength=44.0,
                led_rear=(1.0, 0.03, 0.02), led_rear_strength=22.0,
                led_accent=(0.25, 0.85, 1.0), led_accent_strength=26.0,
                seat=(0.020, 0.055, 0.075), interior=(0.50, 0.50, 0.48),
                screen=(0.25, 0.75, 1.0), decal=(0.10, 0.105, 0.11),
                floor=(0.10, 0.10, 0.11))
    K.pbr("graphite", (0.040, 0.043, 0.048), 0.75, 0.40)
    K.pbr("nib", (0.44, 0.45, 0.47), 1.0, 0.34)
    K.pbr("steel", (0.55, 0.56, 0.58), 1.0, 0.30)
    K.pbr("dark_metal", (0.05, 0.052, 0.056), 0.9, 0.42)
    thin_glass("glass_pod", (0.50, 0.57, 0.61))
    thin_glass("glass_ws", (0.42, 0.49, 0.53))
    thin_glass("glass_clear", (0.86, 0.90, 0.92), 1.4)
    K.need("frit", "seal", "chrome", "lamp_housing", "lens_clear", "lens_red")
    K.emit("glow", (0.20, 0.80, 1.0), 110.0)
    K.pbr("floor_path", (0.105, 0.11, 0.12), 0.0, 0.5)
    K.emit("door_led", (0.25, 1.0, 0.55), 30.0)
    K.emit("pixel", (1.0, 0.62, 0.12), 34.0)
    K.emit("pixel_w", (0.92, 0.96, 1.0), 26.0)
    K.pbr("copper", (0.72, 0.36, 0.16), 1.0, 0.35)
    K.pbr("concrete", (0.17, 0.17, 0.168), 0.0, 0.8)
    K.pbr("track_steel", (0.11, 0.115, 0.125), 0.9, 0.42)
    K.pbr("tube_rib", (0.42, 0.43, 0.45), 0.9, 0.35)
    K.glass("glass_tube", (0.80, 0.90, 0.95), 1.08)
    K.pbr("lining", (0.62, 0.62, 0.60), 0.0, 0.55)
    K.pbr("lining_lo", (0.16, 0.165, 0.175), 0.0, 0.6)
    # the seats' cloth: a fine weave in its roughness and its relief
    m = K.MAT["seat"]
    nt = m.node_tree
    b = next(n for n in nt.nodes if n.type == 'BSDF_PRINCIPLED')
    tc = nt.nodes.new('ShaderNodeTexCoord')
    wv = nt.nodes.new('ShaderNodeTexChecker')
    wv.inputs["Scale"].default_value = 520.0
    nz = nt.nodes.new('ShaderNodeTexNoise')
    nz.inputs["Scale"].default_value = 1400.0
    ad = nt.nodes.new('ShaderNodeMath')
    ad.operation = 'ADD'
    bp = nt.nodes.new('ShaderNodeBump')
    bp.inputs["Strength"].default_value = 0.35
    bp.inputs["Distance"].default_value = 0.0008
    nt.links.new(tc.outputs["Object"], wv.inputs["Vector"])
    nt.links.new(tc.outputs["Object"], nz.inputs["Vector"])
    nt.links.new(wv.outputs["Fac"], ad.inputs[0])
    nt.links.new(nz.outputs["Fac"], ad.inputs[1])
    nt.links.new(ad.outputs[0], bp.inputs["Height"])
    nt.links.new(bp.outputs["Normal"], b.inputs["Normal"])
    b.inputs["Roughness"].default_value = 0.78
    b.inputs["Sheen Weight"].default_value = 0.4
    m, b = K.pbr("floor_pod", (0.05, 0.055, 0.062), 0.0, 0.55)
    nt = m.node_tree
    tc = nt.nodes.new('ShaderNodeTexCoord')
    nz = nt.nodes.new('ShaderNodeTexNoise')
    nz.inputs["Scale"].default_value = 380.0
    nz.inputs["Detail"].default_value = 1.0
    mr = nt.nodes.new('ShaderNodeMapRange')
    mr.inputs["From Min"].default_value = 0.62
    mr.inputs["From Max"].default_value = 0.70
    mx = nt.nodes.new('ShaderNodeMixRGB')
    mx.inputs["Color1"].default_value = (0.05, 0.055, 0.062, 1)
    mx.inputs["Color2"].default_value = (0.30, 0.31, 0.32, 1)
    nt.links.new(tc.outputs["Object"], nz.inputs["Vector"])
    nt.links.new(nz.outputs["Fac"], mr.inputs["Value"])
    nt.links.new(mr.outputs["Result"], mx.inputs["Fac"])
    nt.links.new(mx.outputs["Color"], b.inputs["Base Color"])
    K.emit("cabin_led", (1.0, 0.93, 0.84), 125.0)
    K.pbr("shell", (0.50, 0.50, 0.49), 0.0, 0.45)
    K.pbr("seat2", (0.035, 0.036, 0.04), 0.0, 0.42)
    K.pbr("deck", (0.025, 0.026, 0.028), 0.0, 0.85)
    K.pbr("tactile", (0.85, 0.62, 0.02), 0.0, 0.6)
    K.pbr("red", (0.55, 0.015, 0.012), 0.0, 0.35)
    K.pbr("sign_blue", (0.02, 0.12, 0.45), 0.0, 0.5)
    K.pbr("sign_white", (0.86, 0.86, 0.84), 0.0, 0.5)
    K.pbr("sign_ink", (0.03, 0.035, 0.045), 0.0, 0.5)
    K.pbr("screen_off", (0.008, 0.009, 0.011), 0.0, 0.12)


# ---------------------------------------------------------------------------------------
# the shell
# ---------------------------------------------------------------------------------------
def chan(x):
    """The channel's edge (arc length): it closes ahead of the nose's rise."""
    x = np.asarray(x, float)
    return CH_Y * np.clip((2.80 - x) / 0.35, 0, 1) if not MID else np.full(x.shape, CH_Y)


def upto(s, off=0.0):
    """A band's upper line: s, or the rim where that comes lower."""
    return lambda x: np.minimum(s, RS(x) - off)


# the nib's rear edge: a line in (x, s), from the keel to the rim

WS_X, WS_END = 3.35, 3.86           # the windshield's glass leaves the rim, and ends
SP_X = 1.3 if not MID else XF       # where the spine ends and the windshield begins

# windows: (xa, xb) of each pane of the glazing, and the hoops between
if MID:
    PANES = [(-4.25, -2.69), (-2.48, -0.92), (0.92, 2.48), (2.69, 4.25)]
else:
    PANES = [(-4.25, -2.69), (-2.48, -0.92), (0.92, 2.48), (2.69, 3.70)]
BAND_END = 4.5 if MID else 4.40
RAKE = 0.30                         # the quarter light's front edge leans back with the rim


GLOW = ((-3.9, -2.5), (-2.3, -0.9), (0.7, 2.3))     # the light slots in the belly (x ranges)


def rim_w(x):
    """The width of the trim along the rim: a seal on the barrel, a rail round the nose."""
    return 0.016 + 0.034 * _smooth((np.asarray(x, float) - X0) / 0.6)


def glaze_hi(x):
    """The glazing's top: the rim's trim."""
    return RS(x) - rim_w(x)


def build_shell():
    hull = []

    def panel(name, loop, mat, d=0.0, **kw):
        if loop is None:
            return None
        V, Fc = trim(Fi(d) if d else F, loop)
        if not Fc:
            return None
        ob = mk(name, V, Fc, mat, body=True, **kw)
        hull.append(ob)
        return ob


    xe = XF if MID else 4.497
    # ---- the skirt: belly and bilge, graphite, with slots for the light under the pod
    slots = [dense(rrect(a, b, 0.50, 0.57, 0.03), 0.05) for a, b in GLOW]
    for tag, a, b in (("r", XA, 0.0), ("f", 0.0, xe)):
        loop = band(a, b, chan, upto(S_SK, 0.004) if b > 0 else S_SK)

        V, Fc = trim(F, loop, [h for h, q in zip(slots, GLOW) if a < q[0] < b])
        hull.append(mk("body.skirt." + tag, V, Fc, "graphite", body=True))
    P = Parts()
    for h in slots:
        V, Fc = trim(Fi(0.008), inset(h, -0.006))
        P.add(V, Fc, "glow")
        V, Fc = ruled(F, h, Fi(0.008), h)
        P.add(V, Fc, "dark_metal")
    mirrored(P.obj("mag.glow"))
    # ---- the lower side, the body color, and the line color's stripe
    for k, (a, b) in enumerate(((XA, -2.585), (-2.585, -DOOR_X))):
        panel("body.side.r%d" % k, band(a, b, S_SK, S_ST0), "paint", bevel=0.004)
        panel("body.stripe.r%d" % k, band(a, b, S_ST0, S_ST1, g=0.0008), "paint2",
              bevel=0.002)
    for k, (a, b) in enumerate(((DOOR_X, 2.585), (2.585, xe))):
        panel("body.side.f%d" % k, band(a, b, S_SK, upto(S_ST0, 0.004)), "paint", bevel=0.004)
        panel("body.stripe.f%d" % k,
              band(a, b, S_ST0, upto(S_ST1, 0.004), g=0.0008), "paint2",
              bevel=0.002)
    # ---- the glazing, from the stripe to the spine: panes, and gloss black hoops between
    edges = sorted({XA, -DOOR_X, DOOR_X, BAND_END} | {x for p in PANES for x in p})
    for k, (a, b) in enumerate(zip(edges, edges[1:])):
        if (a, b) == (-DOOR_X, DOOR_X):         # over the doors: the header
            panel("body.header", band(a, b, S_DT, glaze_hi, g=0.0012), "gloss_black",
                  bevel=0.002)
            continue
        loop = band(a, b, S_ST1, glaze_hi, g=0.0012)
        if (a, b) in PANES:
            if not MID and b > 3.0:             # the quarter light's raked front edge
                loop = clip(loop, 1.0, RAKE, b + RAKE * S_ST1)
            V, Fc = trim(F, loop)
            ob = mk("glass.side.%d" % PANES.index((a, b)), V, Fc, "glass_pod", solid=0.0,
                    bevel=0.0, body=True)
            hull.append(ob)
        else:
            if not MID and a > 3.0:
                loop = clip(band(a - 0.8, b, S_ST1, glaze_hi, g=0.0012), -1.0, -RAKE,
                            -(a + RAKE * S_ST1) - 0.003)

            panel("body.hoop.%d" % k, loop, "gloss_black", bevel=0.002)
    # ---- the trim along the rim
    panel("body.rim.r", band(XA, 0.0, glaze_hi, RS, g=0.0008), "gloss_black", bevel=0.0015)
    panel("body.rim.f", band(0.0, xe, glaze_hi, RS, g=0.0008), "gloss_black",
          bevel=0.0015)
    # ---- the cap: the spine in the body color, then the windshield
    yr = lambda x: rim_y(x) - GAP
    cuts = [XA, -1.5, SP_X] if not MID else [XA, -1.5, 1.5, XF]
    for k, (a, b) in enumerate(zip(cuts, cuts[1:])):
        xs = np.array([a + GAP, b - GAP])
        loop = [(x, 0.0) for x in xs] + [(x, float(yr(x))) for x in xs[::-1]]
        V, Fc = trim(G, np.array(loop), out=False)
        hull.append(mk("body.spine.%d" % k, V, Fc, "paint", bevel=0.004, body=True))
    if not MID:
        def ws_front(x):                        # the glass's front edge: off the rim at WS_X
            t = np.clip((np.asarray(x, float) - WS_X) / (WS_END - WS_X), 0, 1)
            return yr(x) * np.sqrt(1 - t * t)
        xs = np.concatenate([np.arange(SP_X + GAP, WS_END, 0.02), [WS_END]])
        loop = [(SP_X + GAP, 0.0), (WS_END, 0.0)]
        loop += [(x, float(ws_front(x))) for x in xs[::-1]]
        V, Fc = trim(G, np.array(loop), out=False)
        hull.append(mk("glass.windshield", V, Fc, "glass_ws", solid=0.0, bevel=0.0,
                       body=True))
        # ---- the nib: the cap ahead of the glass and the hull ahead of its line, metal
        xs2 = np.arange(WS_X, xe + 1e-6, 0.01)
        lo = np.where(xs2 < WS_END + 2 * GAP, ws_front(xs2 - 2 * GAP) + 2 * GAP, 0.0)
        hi = yr(xs2)
        ok = hi - lo > 0.003
        xs2, lo, hi = xs2[ok], lo[ok], hi[ok]
        loop = list(zip(xs2, lo)) + list(zip(xs2[::-1], hi[::-1]))
        V, Fc = trim(G, np.array(loop), out=False)
        hull.append(mk("body.nib", V, Fc, "nib", bevel=0.003, body=True))
    return hull


# ---------------------------------------------------------------------------------------
# flat pieces, tables
# ---------------------------------------------------------------------------------------
def flat(poly, plane, at, hb=0.08, up=True, holes=()):
    """A planar polygon ('xy' at z, 'yz' at x, 'xz' at y) as (vertices, triangles); up: its
    faces look along the third axis' positive way."""
    i, j = "xyz".index(plane[0]), "xyz".index(plane[1])
    k = 3 - i - j

    def surf(a, b):
        P = np.zeros((len(a), 3))
        P[:, i], P[:, j], P[:, k] = a, b, at
        return P
    # (a, b, third) is right-handed for xy and yz, left-handed for xz
    return trim(surf, np.asarray(poly, float), holes, hb=hb, out=(not up) ^ (plane == "xz"),
                plain=True)


def _floor_table():
    lo = np.full(len(_RX), BY - 0.2)
    hi = np.full(len(_RX), float(s_z(0.9)))
    for _ in range(40):
        m = (lo + hi) / 2
        z = F(_RX, m, TH)[:, 2]
        hi = np.where(z > FLOOR - 0.012, m, hi)
        lo = np.where(z > FLOOR - 0.012, lo, m)
    return hi


_SFL = _floor_table()


def SFL(x):
    """The arc length at which the lining meets the floor."""
    return np.interp(x, _RX, _SFL)


def wall_y(x, z, d=TH):
    """The inner wall's y at height z (above the bilge) at x (scalars)."""
    b = float(keel(x))
    z0 = (z - b) / (1 - b) if z < 1.0 else z
    return float(F(np.array([x]), np.array([float(s_z(z0))]), d)[0, 1])


DASH_X = 3.45                       # the nose: where the floor ends
DECK_Z, COWL_X = 1.10, 3.80         # the deck under the windshield, and its front wall
LIN_A = XA + 0.08                   # the lining's ends
LIN_B = 3.95 if not MID else XF - 0.08
FL_B = DASH_X if not MID else XF - 0.08
S_D = float(s_z(0.93))              # dado to upper lining
S_A0 = float(s_z(0.985))            # the windows' inner sill


def ap_hi(x):
    """The top of the windows' apertures in the lining."""
    return RS(x) - 0.115


def lin_hi(x):
    """The lining's upper edge, under the spine's console and the rim."""
    return RS(x) - 0.035


def _thin(loop, tol=0.004):
    """A loop without the points that lie on the line between their neighbors (so that
    fillet() sees its corners)."""
    P = [np.array(p, float) for p in loop]
    changed = True
    while changed and len(P) > 4:
        changed = False
        for i in range(len(P)):
            a, p, b = P[i - 1], P[i], P[(i + 1) % len(P)]
            ab = b - a
            ln = np.hypot(*ab)
            if ln < 1e-9:
                continue
            dist = abs(ab[0] * (p[1] - a[1]) - ab[1] * (p[0] - a[0])) / ln
            if dist < tol * min(1.0, ln / 0.1):
                P.pop(i)
                changed = True
                break
    return np.array(P)


def apertures():
    """The window openings of the lining, loops in (x, s), by pane."""
    out = []
    for (a, b) in PANES:
        if not MID and b > X0:
            loop = band(a + 0.04, b - 0.04, S_A0, ap_hi, g=0.0)
            if b > 3.0:
                loop = clip(loop, 1.0, RAKE, b - 0.05 + RAKE * S_ST1)
            loop = fillet(_thin(loop), 0.07)
        else:
            loop = rrect(a + 0.04, b - 0.04, S_A0, float(ap_hi(0.0)), 0.07)
        out.append(dense(loop, 0.04))
    return out


def _ccw(loop):
    P = np.asarray(loop)
    b = np.roll(P, -1, axis=0)
    return float(np.sum(P[:, 0] * b[:, 1] - b[:, 0] * P[:, 1])) > 0


def mirrored(ob):
    md = ob.modifiers.new("mirror", 'MIRROR')
    md.use_axis = (False, True, False)
    return ob


# ---------------------------------------------------------------------------------------
# the inner shell: lining, reveals, frit, floor, the spine's console
# ---------------------------------------------------------------------------------------
def build_lining():
    aps = apertures()
    lin = Fi(TH)
    # ---- dado and upper lining, each side of the doors; the header over them
    for tag, a, b in (("r", LIN_A, -DOOR_X), ("f", DOOR_X, LIN_B)):
        fb = min(b, FL_B)
        V, Fc = trim(lin, band(a, fb, SFL, S_D, g=0.0), out=False)
        mk("interior.dado." + tag, V, Fc, "lining_lo", solid=0, bevel=0)
        holes = [h for h, (pa, pb) in zip(aps, PANES) if a < (pa + pb) / 2 < b]
        V, Fc = trim(lin, band(a, b, S_D, lin_hi, g=0.0), holes, out=False)
        mk("interior.lining." + tag, V, Fc, "lining", solid=0, bevel=0)
    V, Fc = trim(lin, band(-DOOR_X, DOOR_X, S_DT + 0.004, lin_hi, g=0.0), out=False)
    mk("interior.lining.header", V, Fc, "lining", solid=0, bevel=0)
    # ---- reveals from the lining to the glass, and the frit round each pane
    P = Parts()
    Q = Parts()
    for h, (pa, pb) in zip(aps, PANES):
        V, Fc = ruled(lin, h, Fi(0.0095), h, flip=_ccw(h))
        P.add(V, Fc, "lining")
        loop = band(pa, pb, S_ST1, glaze_hi, g=0.004)
        if not MID and pb > 3.0:
            loop = clip(loop, 1.0, RAKE, pb - 0.004 + RAKE * S_ST1)
        V, Fc = trim(Fi(0.0095), loop, [inset(h, 0.005)], out=True)
        Q.add(V, Fc, "frit")
    # ---- the doorway's frame: jambs and header, from the lining out to the skin
    for sg in (1, -1):
        ss = np.linspace(float(SFL(0.0)), S_DT + 0.004, 60)
        path = np.stack([np.full(60, sg * (DOOR_X + 0.001)), ss], axis=1)
        V, Fc = ruled(lin, path, F, path, closed=False, flip=sg > 0)
        P.add(V, Fc, "lining_lo")
    xs = np.linspace(-DOOR_X, DOOR_X, 30)
    path = np.stack([xs, np.full(30, S_DT + 0.004)], axis=1)
    V, Fc = ruled(lin, path, F, path, closed=False, flip=True)
    P.add(V, Fc, "lining_lo")
    mirrored(P.obj("interior.reveals"))
    mirrored(Q.obj("glass.frit"))

    # ---- hoop lights: a line of light up every hoop, from the sill to the console
    hoops = sorted({XA + 0.14, -2.585, -0.81, 0.81, 2.585} | ({XF - 0.14} if MID else set()))
    P = Parts()
    for xh in hoops:
        V, Fc = trim(Fi(TH + 0.0015), band(xh - 0.008, xh + 0.008, S_A0 + 0.02,
                                           lambda x: RS(x) - 0.06, g=0.0), out=False)
        P.add(V, Fc, "cabin_led")
    mirrored(P.obj("interior.light.hoops"))

    # ---- the floor: one plate, out to the doors' inner faces in the doorway
    xs = np.concatenate([np.arange(LIN_A, FL_B, 0.05), [FL_B]])
    edge = [(x, wall_y(x, FLOOR) + 0.012) for x in xs if not -DOOR_X < x < DOOR_X]
    ydoor = wall_y(0.0, FLOOR, LEAF_T + 0.004)
    k = next(i for i, q in enumerate(edge) if q[0] > 0)
    edge[k:k] = [(-DOOR_X, edge[k - 1][1]), (-DOOR_X, ydoor), (DOOR_X, ydoor),
                 (DOOR_X, edge[k][1])]
    poly = edge + [(x, -y) for x, y in edge[::-1]]
    V, Fc = flat(poly, "xy", FLOOR, hb=0.12)
    mk("interior.floor", V, Fc, "floor_pod", mirror=False, solid=0, bevel=0)

    # ---- the spine's console: a keel of the ceiling with a light line each side
    xb = SP_X + 0.10 if not MID else XF - 0.08
    n = len(CONSOLE)
    V = [(x, y, z) for x in (LIN_A, xb) for y, z in CONSOLE]
    Fc = [(i, i + 1, n + i + 1, n + i) for i in range(n - 1)]
    P = Parts()
    P.add(np.array(V), Fc, "lining", flat=True)
    if not MID:                                 # its prow, over the lounge
        P.add(np.array([(xb, y, z) for y, z in CONSOLE]), [tuple(range(n))[::-1]], "lining",
              flat=True)
    P.obj("interior.console")
    g = Geo()
    for sg in (1, -1):
        g.box(((LIN_A + xb) / 2, sg * 0.2335, 2.5705), (xb - LIN_A - 0.06, 0.03, 0.004),
              rot=Matrix.Rotation(sg * rad(25.3), 3, 'X'))
    g.obj("interior.light.lines", "cabin_led")


CONSOLE = [(0.31, 2.652), (0.262, 2.585), (0.205, 2.558), (-0.205, 2.558), (-0.262, 2.585),
           (-0.31, 2.652)]          # the console's section under the spine


# ---------------------------------------------------------------------------------------
# the doors: four leaves, each one object
# ---------------------------------------------------------------------------------------
LEAF_T = 0.042                      # a leaf's thickness


def build_doors():
    doors = {}
    for tag, xa, xb in (("a", 0.0, DOOR_X), ("b", -DOOR_X, 0.0)):
        mid = xa if tag == "a" else xb          # the meeting edge
        sg = 1 if tag == "a" else -1
        P = Parts()
        g = 0.003
        whole = band(xa, xb, S_SK, S_DT, g=g)
        win = dense(rrect(xa + 0.105, xb - 0.105, float(s_z(1.00)), S_DT - 0.10, 0.075), 0.03)
        for lo, hi, mat in ((S_SK + g, S_ST0, "paint"), (S_ST0, S_ST1, "paint2"),
                            (S_ST1, S_DT - g, "gloss_black")):
            loop = np.array([(xa + g, lo), (xb - g, lo), (xb - g, hi), (xa + g, hi)])
            V, Fc = trim(F, loop, [win] if mat == "gloss_black" else ())
            P.add(V, Fc, mat)
        inner = Fi(LEAF_T)
        kick = float(s_z(0.62))
        for lo, hi, mat in ((S_SK + g, kick, "lining_lo"), (kick, S_DT - g, "lining")):
            loop = np.array([(xa + g, lo), (xb - g, lo), (xb - g, hi), (xa + g, hi)])
            V, Fc = trim(inner, loop, [win] if mat == "lining" else (), out=False)
            P.add(V, Fc, mat)
        edge = dense(whole, 0.05)
        V, Fc = ruled(F, edge, inner, edge, flip=not _ccw(edge))
        P.add(V, Fc, "seal")
        # the window: a pane in the middle of the leaf, a reveal each side of it
        V, Fc = trim(Fi(0.018), inset(win, -0.004))
        P.add(V, Fc, "glass_pod")
        V, Fc = ruled(F, win, Fi(0.018), win, flip=_ccw(win))
        P.add(V, Fc, "gloss_black")
        V, Fc = ruled(inner, win, Fi(0.018), win, flip=not _ccw(win))
        P.add(V, Fc, "lining")
        # the rubber of the meeting edge, proud of both faces
        ss = np.linspace(S_SK + 0.01, S_DT - 0.01, 50)
        a = F(np.full(50, mid + sg * 0.002), ss, -0.0008)
        b = F(np.full(50, mid + sg * 0.011), ss, -0.0008)
        c = F(np.full(50, mid + sg * 0.011), ss, LEAF_T + 0.003)
        d = F(np.full(50, mid + sg * 0.002), ss, LEAF_T + 0.003)
        V = np.concatenate([a, b, c, d])
        Fc = []
        for i in range(49):
            for q in range(4):
                r = (q + 1) % 4
                f = (q * 50 + i, r * 50 + i, r * 50 + i + 1, q * 50 + i + 1)
                Fc.append(f if sg < 0 else f[::-1])
        P.add(V, Fc, "seal")
        # the push buttons: a lit ring on each face, by the meeting edge
        gb, gl = Geo(), Geo()
        for d, way in ((-0.001, 1), (LEAF_T + 0.001, -1)):
            xb_ = mid + sg * 0.062
            sb = float(s_z(1.50 if way > 0 else 1.28))
            c = f1(xb_, sb, d)
            n = p3(Fn(np.array([xb_]), np.array([sb]))[0]) * way
            gb.lathe([(0.0, 0.0), (0.0, 0.034), (0.008, 0.034), (0.010, 0.026), (0.010, 0.0)],
                     20, axis=n, at=c)
            gl.lathe([(0.0095, 0.019), (0.0095, 0.025), (0.0112, 0.025), (0.0112, 0.019)], 20,
                     axis=n, at=c)
        P.add(*geo_closed(gb), "gloss_black", flat=True)
        P.add(*geo_closed(gl), "door_led", flat=True)
        # a pull handle inside, by the leaf's outer edge
        gh = Geo()
        xh = mid + sg * 0.645
        pts = [f1(xh, float(s_z(z)), LEAF_T + off) for z, off in
               ((1.02, 0.0), (1.05, 0.038), (1.38, 0.038), (1.41, 0.0))]
        gh.pipe(pts, 0.011, n=10, up=(1, 0, 0))
        P.add(*geo_closed(gh), "steel")
        for side, flip in (("l", False), ("r", True)):
            # the notice on the glass, read from inside: its own for each side
            r = -1 if flip else 1
            Q = Parts()
            Q.items = list(P.items)
            xs_, sz = mid + sg * 0.35, float(s_z(1.20))
            c = f1(xs_, sz, 0.0195)
            n = -p3(Fn(np.array([xs_]), np.array([sz]))[0])
            up = (V3((0, 0, 1)) - n * n.z).normalized()
            rt = V3((r * 1.0, 0, 0))
            gr, gw = Geo(), Geo()
            ring = [(0.04 * cos(a), 0.04 * sin(a)) for a in np.linspace(0, 2 * pi, 25)]
            for (a, b) in zip(ring, ring[1:]):
                _bar(gr, c + rt * a[0] + up * a[1], c + rt * b[0] + up * b[1], n, 0.008)
            _bar(gr, c + rt * 0.026 + up * 0.026, c - rt * 0.026 - up * 0.026, n, 0.008)
            K.text_flat(gw, "KEEP CLEAR", 0.012, c - up * 0.062, rt, up)
            K.text_flat(gw, "DOORS SLIDE OUTWARD", 0.0065, c - up * 0.078, rt, up)
            Q.geo(gr, "red")
            Q.geo(gw, "sign_white")
            doors[side + tag] = Q.obj("door.%s.%s" % (side, tag), flip_y=flip, bevel=0.0)
    return doors


# ---------------------------------------------------------------------------------------
# the gangway ends
# ---------------------------------------------------------------------------------------
GW_Y, GW_Z0, GW_Z1 = 0.50, FLOOR, 2.36      # the gangway's clear opening
GW_OUT = 0.25                               # how far its collar stands off the end


def _half_outline(x, d=0.0):
    """The section at x from the channel's edge to the centerline's top, as (y, z)."""
    ss = np.concatenate([np.linspace(CH_Y, S_SP, 240), np.linspace(S_SP, S_END, 30)[1:]])
    P = F(np.full(len(ss), x), ss, d)
    return [(float(p[1]), float(p[2])) for p in P]


def build_end(e):
    """A coupling end at x = e * 4.5 (e = -1 the rear): wall, gangway, bellows."""
    xw = e * XF                                 # the outer wall
    xi = xw - e * 0.08                          # the inner one
    xo = xw + e * GW_OUT                        # the collar's face
    tag = "r" if e < 0 else "f"
    r = 0.10
    hole = [(0.0, GW_Z0 - 0.06), (GW_Y + 0.06, GW_Z0 - 0.06)]
    hole += [(GW_Y + 0.06 - r + r * cos(a), GW_Z1 + 0.06 - r + r * sin(a))
             for a in np.linspace(0, pi / 2, 7)]
    hole += [(0.0, GW_Z1 + 0.06)]
    # ---- the outer wall: the section less the gangway, graphite
    poly = [(0.0, CH_D), (CH_Y, CH_D)] + _half_outline(xw) + hole[::-1]
    V, Fc = flat(poly, "yz", xw - e * 0.004, hb=0.07, up=e > 0)
    mk("body.end." + tag, V, Fc, "graphite", solid=0, bevel=0)
    # ---- the inner wall, lining: from the floor up, under the console
    ss = np.linspace(float(SFL(xi)), float(lin_hi(xi)), 120)
    side = [(float(p[1]), max(float(p[2]), FLOOR)) for p in F(np.full(120, xi), ss, TH)]
    hole_i = [(0.0, FLOOR), (GW_Y, FLOOR)]
    hole_i += [(GW_Y - r + r * cos(a), GW_Z1 - r + r * sin(a))
               for a in np.linspace(0, pi / 2, 7)]
    hole_i += [(0.0, GW_Z1)]
    poly = side[1:] + [(0.262, 2.585), (0.205, 2.558), (0.0, 2.558)] + hole_i[:0:-1]
    V, Fc = flat(poly, "yz", xi, hb=0.07, up=e < 0)
    mk("interior.end." + tag, V, Fc, "lining", solid=0, bevel=0)
    # ---- the passage: a liner through the wall, then the bellows' inner folds out to the
    # collar's face
    P = Parts()
    path = np.array(hole_i[1:])                 # from the floor up and over to the top
    n = len(path)
    V = np.array([(xi, y, z) for y, z in path] + [(xw, y, z) for y, z in path])
    Fc = [(i, i + 1, n + i + 1, n + i) if e < 0 else (i, n + i, n + i + 1, i + 1)
          for i in range(n - 1)]
    P.add(V, Fc, "lining_lo")
    tn = np.gradient(path, axis=0)
    tn /= np.hypot(tn[:, 0], tn[:, 1])[:, None]
    nr = np.stack([tn[:, 1], -tn[:, 0]], axis=1)
    nr[0], nr[-1] = (1, 0), (0, 1)
    V, Fc = [], []
    cols = 4 * 4 + 1
    for c in range(cols):
        x = xw + e * (GW_OUT - 0.02) * c / (cols - 1)
        off = (0.004, 0.026, 0.004, 0.026)[c % 4] if c % 2 else 0.004
        V += [(x, y + off * ny, z + off * nz) for (y, z), (ny, nz) in zip(path, nr)]
    for c in range(cols - 1):
        for i in range(n - 1):
            q = (c * n + i, c * n + i + 1, (c + 1) * n + i + 1, (c + 1) * n + i)
            Fc.append(q if e < 0 else q[::-1])
    P.add(np.array(V), Fc, "rubber")
    mirrored(P.obj("interior.gangway.liner." + tag, smooth=50.0))
    # ---- on the outer wall: a buffer and a jumper box each side of the passage
    g, gs = Geo(), Geo()
    for sy in (1, -1):
        g.cyl((xw, sy * 0.84, 0.66), e * 0.11, 0.075, n=24, axis='x')
        gs.cyl((xw + e * 0.11, sy * 0.84, 0.66), e * 0.012, 0.085, n=24, axis='x')
        g.box((xw + e * 0.03, sy * 0.84, 1.02), (0.06, 0.20, 0.13))
        for k in range(3):
            gs.cyl((xw + e * 0.06, sy * (0.78 + 0.06 * k), 1.02), e * 0.012, 0.02, n=14, axis='x')
    g.obj("body.end.gear." + tag, "dark_metal", bevel=0.004)
    gs.obj("body.end.gear.trim." + tag, "steel", bevel=0.002)
    # ---- the floor plate of the passage: ribbed steel
    g = Geo()
    xm, ln = (xi + xo) / 2 - e * 0.03, abs(xo - xi) + 0.06
    g.box((xm, 0, FLOOR - 0.008), (ln, 2 * GW_Y + 0.02, 0.022))
    for k in range(9):
        g.box((xm, -0.40 + 0.10 * k, FLOOR + 0.004), (ln - 0.05, 0.018, 0.004))
    g.obj("interior.gangway.plate." + tag, "steel", bevel=0.0015)
    # ---- the bellows: a corrugated rubber collar round the passage, a frame on its face
    ring = [(0.0, GW_Z0 - 0.10)]
    rr = 0.16
    for (cy, cz, a0) in ((GW_Y + 0.11 - rr, GW_Z0 - 0.10 + rr, -pi / 2),
                         (GW_Y + 0.11 - rr, GW_Z1 + 0.11 - rr, 0.0)):
        ring += [(cy + rr * cos(a0 + a), cz + rr * sin(a0 + a))
                 for a in np.linspace(0, pi / 2, 8)]
    ring += [(0.0, GW_Z1 + 0.11)]
    R = np.array(ring)
    tn = np.gradient(R, axis=0)
    tn /= np.hypot(tn[:, 0], tn[:, 1])[:, None]
    nr = np.stack([tn[:, 1], -tn[:, 0]], axis=1)
    nr[0], nr[-1] = (0, -1), (0, 1)
    V, Fc = [], []
    folds = 5
    cols = 4 * folds + 1
    for c in range(cols):
        x = xw + e * (GW_OUT - 0.03) * c / (cols - 1)
        off = (0.0, 0.028, 0.0, -0.02)[c % 4]
        V += [(x, y + off * ny, z + off * nz) for (y, z), (ny, nz) in zip(R, nr)]
    m = len(R)
    for c in range(cols - 1):
        for i in range(m - 1):
            q = (c * m + i, c * m + i + 1, (c + 1) * m + i + 1, (c + 1) * m + i)
            Fc.append(q if e < 0 else q[::-1])
    P = Parts()
    P.add(np.array(V), Fc, "rubber")
    mirrored(P.obj("body.bellows." + tag, smooth=70.0))
    g = Geo()
    sec = [(-0.03, -0.012), (0.03, -0.012), (0.03, 0.012), (-0.03, 0.012)]
    g.sweep([(xo - e * 0.015, y, z) for y, z in ring], sec, up=(e, 0, 0))
    g.obj("body.collar." + tag, "dark_metal", bevel=0.002, mirror=True)


# ---------------------------------------------------------------------------------------
# lettering on the surfaces
# ---------------------------------------------------------------------------------------
def text_on(g, txt, size, x0, s0, d, right=1, flip=False, font=None, surf=None):
    """Text on the hull (d inside it; a negative d stands off its outside), its middle at
    x0 and arc length s0, running toward +x (right = 1) or -x; flip: on the right side."""
    vs, fs = K.text_mesh(txt, size, 1.0, font)
    X = np.array([x0 + right * p.x for p in vs])
    Sv = np.array([s0 + p.y for p in vs])
    P = (surf or F)(X, Sv, d) if surf is None else surf(X, Sv)
    if flip:
        P = P * np.array((1, -1, 1))
    g.add([p3(q) for q in P], fs)


def patch_on(xa, xb, sa, sb, d, r=0.012, out=False):
    """A rounded rectangle of the hull's offset surface: a panel, a screen, a sticker."""
    return trim(Fi(d), dense(rrect(xa, xb, sa, sb, r), 0.04), out=out)


def inst(name, me, loc, rz=0.0):
    ob = bpy.data.objects.new(name, me)
    K.CAR.objects.link(ob)
    ob.location = loc
    ob.rotation_euler = (0, 0, rz)
    return ob


def baked(ob):
    """An object's mesh with its modifiers applied (for instances); the object is removed."""
    me = K.evaluated_mesh(ob)
    old = ob.data
    bpy.data.objects.remove(ob)
    bpy.data.meshes.remove(old)
    return me


# ---------------------------------------------------------------------------------------
# seats
# ---------------------------------------------------------------------------------------
SEAT_W = 0.42                       # a cushion's width; an armrest of 0.04 on its aisle side
ROW_PITCH = 0.90


def seat_meshes(flip):
    """A seat facing +x, its cushion's middle over the origin, z from the floor: the soft
    parts and the hard ones, as two meshes. The armrest stands on the -y side (flip: +y)."""
    w = SEAT_W / 2
    soft, hard = Parts(), Parts()
    tilt = Matrix.Rotation(rad(-5.0), 4, 'Y')

    def slab(g, outline, z0, th, xf):               # an outline in plan (x, y), th thick
        g.prism([(x, y, z0) for x, y in outline], (0, 0, th), xf=xf)

    def leaf(g, outline, o, lean, th):              # an outline (y, up the back), th behind
        o = V3(o)
        v = V3((-sin(rad(lean)), 0, cos(rad(lean))))
        n = V3((cos(rad(lean)), 0, sin(rad(lean))))
        g.prism([o + V3((0, 1, 0)) * a + v * b for a, b in outline], -n * th)

    cushion = fillet([(-0.215, -w + 0.012), (0.10, -w + 0.012), (0.235, -w + 0.04),
                      (0.235, w - 0.04), (0.10, w - 0.012), (-0.215, w - 0.012)], 0.05, 5)
    g = Geo()
    slab(g, cushion, 0.0, 0.082, Matrix.Translation((0, 0, 0.372)) @ tilt)
    back = fillet([(-w + 0.022, 0.0), (w - 0.022, 0.0), (w - 0.012, 0.36), (w - 0.05, 0.585),
                   (-w + 0.05, 0.585), (-w + 0.012, 0.36)], 0.06, 5)
    leaf(g, back, (-0.200, 0, 0.435), 14.0, 0.062)
    soft.add(*geo_closed(g), "seat", flat=True)
    g = Geo()
    head = fillet([(-0.13, 0.0), (0.13, 0.0), (0.155, 0.10), (0.125, 0.185), (-0.125, 0.185),
                   (-0.155, 0.10)], 0.045, 5)
    leaf(g, head, (-0.338, 0, 1.035), 10.0, 0.058)
    pad = fillet([(-0.17, -0.021), (0.15, -0.021), (0.17, 0.0), (0.15, 0.021), (-0.17, 0.021)],
                 0.012, 3)
    slab(g, pad, 0.648, 0.034, Matrix.Translation((0.01, -w - 0.02, 0)))
    soft.add(*geo_closed(g), "seat2", flat=True)
    g = Geo()
    pan = fillet([(-0.30, -w), (0.14, -w), (0.215, -w + 0.05), (0.215, w - 0.05), (0.14, w),
                  (-0.30, w)], 0.04, 4)
    slab(g, pan, 0.0, 0.03, Matrix.Translation((0, 0, 0.342)) @ tilt)
    shell = fillet([(-w, -0.14), (w, -0.14), (w + 0.006, 0.40), (w - 0.045, 0.80),
                    (-w + 0.045, 0.80), (-w - 0.006, 0.40)], 0.075, 6)
    leaf(g, shell, (-0.262, 0, 0.43), 14.0, 0.022)
    hard.add(*geo_closed(g), "shell", flat=True)
    g = Geo()
    g.box((-0.03, 0.0, 0.17), (0.075, 0.26, 0.32))                      # pedestal, foot
    g.box((-0.03, 0.0, 0.008), (0.34, 0.34, 0.016))
    g.box((-0.10, -w - 0.02, 0.50), (0.045, 0.024, 0.30),
          rot=Matrix.Rotation(rad(-12), 3, 'Y'))                        # the armrest's post
    hard.add(*geo_closed(g), "dark_metal", flat=True)
    g = Geo()                                                           # a net pocket
    net = fillet([(-0.14, 0.0), (0.14, 0.0), (0.14, 0.17), (-0.14, 0.17)], 0.02, 3)
    leaf(g, net, (-0.378, 0, 0.58), 14.0, 0.012)
    hard.add(*geo_closed(g), "lining_lo", flat=True)
    g = Geo()                                                           # a grab loop
    g.pipe([(-0.412, -w + 0.05, 1.105), (-0.432, -w - 0.018, 1.12),
            (-0.452, -w - 0.018, 1.205), (-0.450, -w + 0.05, 1.225)], 0.011, n=10,
           up=(1, 0, 0))
    hard.add(*geo_closed(g), "paint2")
    a = baked(soft.obj("seat.soft", flip_y=flip, bevel=0.016, angle=50.0))
    b = baked(hard.obj("seat.hard", flip_y=flip, bevel=0.004, angle=50.0))
    return a, b


def seat_plan():
    """Where the seats stand: (x, y, armrest on +y)."""
    left = [1.095 - SEAT_W / 2, 1.095 - SEAT_W - 0.04 - SEAT_W / 2]     # the double's two
    right = -1.095 + SEAT_W / 2
    out = []
    for x in (-1.68, -2.58, -3.48):
        out += [(x, left[0], False), (x, left[1], False), (x, right, True)]
    out += [(1.45, left[0], False), (1.45, left[1], False)]
    if MID:
        for x in (2.35, 3.25):
            out += [(x, left[0], False), (x, left[1], False)]
        out += [(2.62, right, True), (3.52, right, True)]
    return out


def build_seats():
    ma = seat_meshes(False)
    mb = seat_meshes(True)
    for k, (x, y, flip) in enumerate(seat_plan()):
        soft, hard = mb if flip else ma
        inst("interior.seat.%02d" % k, soft, (x, y, FLOOR))
        inst("interior.seat.%02d.frame" % k, hard, (x, y, FLOOR))
    return len(seat_plan())


def build_lounge():
    """The observation lounge: a bench round the nose under the windshield, the deck and
    its front wall, the windshield's frame."""
    # ---- the bench: plinth, cushion and a low back, swept round the nose's wall
    path = [(2.25, 0.79), (2.55, 0.74)]
    path += [(2.86 + 0.32 * sin(a), 0.37 + 0.32 * cos(a)) for a in np.linspace(0, pi / 2, 9)]
    path += [(x, -y) for x, y in path[::-1]]
    P3 = [(x, y, FLOOR) for x, y in path]
    for name, sec, mat, bev in (
            ("plinth", [(-0.24, 0.0), (0.16, 0.0), (0.16, 0.30), (0.20, 0.34), (-0.24, 0.34)],
             "lining_lo", 0.004),
            ("cushion", [(-0.20, 0.34), (0.215, 0.34), (0.235, 0.37), (0.225, 0.445),
                         (-0.20, 0.43)], "seat", 0.018),
            ("back", [(-0.25, 0.40), (-0.165, 0.42), (-0.20, 0.70), (-0.255, 0.715)], "seat",
             0.016),
            ("cap", [(-0.262, 0.30), (-0.245, 0.30), (-0.245, 0.725), (-0.19, 0.74),
                     (-0.19, 0.755), (-0.262, 0.755)], "shell", 0.004)):
        g = Geo()
        g.sweep(P3, sec, up=(0, 0, 1))
        g.obj("interior.lounge." + name, mat, bevel=bev, angle=40.0)
    # ---- the wall under the deck, the deck, its front wall up to the glass
    zs = np.linspace(FLOOR, DECK_Z, 12)
    poly = [(wall_y(DASH_X, z) + 0.012, z) for z in zs]
    poly = [(-y, z) for y, z in poly[::-1]] + poly
    V, Fc = flat(poly, "yz", DASH_X, hb=0.1, up=False)
    mk("interior.lounge.wall", V, Fc, "lining_lo", mirror=False, solid=0, bevel=0)
    xs = np.linspace(DASH_X, COWL_X, 9)
    edge = [(x, wall_y(x, DECK_Z) + 0.012) for x in xs]
    poly = edge + [(x, -y) for x, y in edge[::-1]]
    V, Fc = flat(poly, "xy", DECK_Z, hb=0.1)
    mk("interior.lounge.deck", V, Fc, "deck", mirror=False, solid=0, bevel=0)
    yr = float(rim_y(COWL_X))
    ss = np.linspace(float(s_z(DECK_Z)), float(lin_hi(COWL_X)), 30)
    side = [(float(p[1]) + 0.004, float(p[2])) for p in F(np.full(30, COWL_X), ss, TH - 0.02)]
    side[0] = (side[0][0], DECK_Z)
    top = [(y, float(G(np.array([COWL_X]), np.array([y]), 0.0095)[0, 2]))
           for y in np.linspace(yr - 0.03, 0.0, 12)]
    half = side + top
    poly = half + [(-y, z) for y, z in half[-2::-1]]
    V, Fc = flat(poly, "yz", COWL_X, hb=0.1, up=False)
    mk("interior.lounge.cowl", V, Fc, "deck", mirror=False, solid=0, bevel=0)
    # ---- on the deck: demister slots along the glass, a forward sensor's housing
    g, gs = Geo(), Geo()
    for k in range(-5, 6):
        g.box((COWL_X - 0.05, 0.085 * k, DECK_Z + 0.0015), (0.035, 0.06, 0.003))
    gs.lathe([(0.0, 0.0), (0.0, 0.075), (0.02, 0.072), (0.045, 0.05), (0.055, 0.0)], 24,
             axis='z', at=(DASH_X + 0.16, 0.0, DECK_Z))
    g.lathe([(0.052, 0.0), (0.052, 0.03), (0.057, 0.026), (0.058, 0.0)], 20, axis='z',
            at=(DASH_X + 0.16, 0.0, DECK_Z))
    K.text_flat(g, "FORWARD VIEW  NO DRIVER ABOARD", 0.012, (DASH_X + 0.045, 0.0, DECK_Z + 0.001),
                (0, -1, 0), (1, 0, 0))
    g.obj("interior.lounge.deck.slots", "screen_off")
    gs.obj("interior.lounge.sensor", "dark_metal")
    # ---- the windshield from inside: a reveal from the lining up to the glass, the frit
    xs = np.concatenate([np.arange(SP_X - 0.04, LIN_B, 0.04), [LIN_B]])
    a = np.stack([xs, lin_hi(xs)], axis=1)
    b = np.stack([xs, rim_y(xs) - 0.075], axis=1)
    V, Fc = ruled(Fi(TH), a, Gi(0.011), b, closed=False)
    P = Parts()
    P.add(V, Fc, "lining")
    mirrored(P.obj("interior.lounge.reveal"))
    xo = np.concatenate([np.arange(SP_X + 0.004, WS_END, 0.02), [WS_END - 0.004]])
    t = np.clip((xo - WS_X) / (WS_END - WS_X), 0, 1)
    outer = [(SP_X + 0.004, 0.0), (WS_END - 0.004, 0.0)] + \
        [(x, float((rim_y(x) - 0.004) * sqrt(max(0.0, 1 - tt * tt))))
         for x, tt in zip(xo[::-1], t[::-1])]
    xc = np.concatenate([np.arange(SP_X + 0.16, COWL_X - 0.05, 0.03), [COWL_X - 0.05]])
    tc = np.clip((xc - WS_X) / (WS_END - WS_X), 0, 1)
    clear = [(SP_X + 0.16, 0.0), (COWL_X - 0.05, 0.0)] + \
        [(x, float(min(rim_y(x) - 0.085, rim_y(x) * sqrt(1 - tt * tt) - 0.075)))
         for x, tt in zip(xc[::-1], tc[::-1])]
    clear = fillet(_thin(np.array(clear)), 0.07)
    V, Fc = trim(Gi(0.009), np.array(outer), [clear], out=False)
    P = Parts()
    P.add(V, Fc, "frit")
    mirrored(P.obj("glass.frit.windshield"))


# ---------------------------------------------------------------------------------------
# the vestibule: screens, poles, thresholds, the wheelchair bay
# ---------------------------------------------------------------------------------------
SCR_X = 0.93                        # the draught screens, each side of the doorway
AISLE = (-1.095 + SEAT_W + 0.04, 1.095 - 2 * SEAT_W - 0.08)    # the aisle's two edges (y)


def build_vestibule():
    ya, yb = AISLE                               # the right edge, the left edge
    gg, gs, gp, gm = Parts(), Geo(), Geo(), Geo()
    for sx in (-1, 1):
        for sy, edge in ((1, yb), (-1, -ya if sx < 0 else 0.72)):
            x = sx * SCR_X
            # the modesty panel below, glass above, following the wall
            zs = np.concatenate([np.linspace(FLOOR + 0.04, 1.18, 6)])
            wall = [(wall_y(x, z) - 0.006, z) for z in zs]
            poly = [(edge, FLOOR + 0.04)] + wall + [(edge, 1.18)]
            gs.prism([(x - 0.016, sy * y, z) for y, z in poly], (0.032, 0, 0))
            zs = np.linspace(1.18, 1.98, 9)
            wall = [(wall_y(x, z) - 0.006, z) for z in zs]
            poly = [(edge, 1.18)] + wall + [(edge, 1.98)]
            V, Fc = flat([(sy * y, z) for y, z in poly], "yz", x, hb=0.12)
            gg.add(V, Fc, "glass_clear")
            # a steel cap along the glass's top
            gm.box((x, sy * (edge + wall[-1][0]) / 2, 1.985), (0.022, abs(wall[-1][0] - edge),
                                                           0.018))
            # the pole at the screen's edge: up to the console
            if sy > 0:
                gp.pipe([(x, yb, FLOOR), (x, yb, 2.56)], 0.017, n=14, up=(1, 0, 0))
            else:
                e = edge
                pts = [(x, -e, FLOOR), (x, -e, 1.95)]
                pts += [(x, -(0.50 + (e - 0.50) * cos(a)), 1.95 + 0.52 * sin(a))
                        for a in np.linspace(0, pi / 2, 9)[1:]]
                pts += [(x, -0.22, 2.47 + 0.0), (x, -0.215, 2.565)]
                gp.pipe(pts, 0.017, n=14, up=(1, 0, 0))
            gm.cyl((x, sy * abs(edge), FLOOR), 0.02, 0.035, n=16)
    gg.obj("interior.screens.glass")
    gs.obj("interior.screens", "lining_lo", bevel=0.004)
    gp.obj("interior.poles", "paint2")
    gm.obj("interior.screens.trim", "steel", bevel=0.002)

    # ---- thresholds: a ribbed steel plate in each doorway, a tactile strip inside it
    yd = wall_y(0.0, FLOOR, LEAF_T + 0.004)
    g, gt, gy = Geo(), Geo(), Geo()
    for sy in (1, -1):
        g.box((0.0, sy * (yd - 0.085), FLOOR + 0.0015), (2 * DOOR_X - 0.01, 0.17, 0.003))
        for k in range(6):
            g.box((0.0, sy * (yd - 0.155 + 0.026 * k), FLOOR + 0.004), (2 * DOOR_X - 0.06, 0.008,
                                                                    0.003))
        gy.box((0.0, sy * (yd - 0.235), FLOOR + 0.0012), (2 * DOOR_X - 0.01, 0.12, 0.0024))
        for i in range(34):
            for j in range(3):
                gt.cyl((-0.66 + 0.04 * i, sy * (yd - 0.275 + 0.04 * j), FLOOR + 0.002), 0.0035,
                       0.012, n=8)
        # the sill under the leaves, outside the floor's edge, and the floor's edge itself
        g.box((0.0, sy * (yd + 0.022), FLOOR - 0.06), (2 * DOOR_X - 0.004, 0.044, 0.05))
        g.box((0.0, sy * (yd - 0.004), FLOOR - 0.03), (2 * DOOR_X - 0.004, 0.008, 0.06))
    g.obj("interior.threshold", "steel", bevel=0.001)
    gy.obj("interior.tactile", "tactile")
    gt.obj("interior.tactile.studs", "tactile")

    # ---- the wheelchair bay (front right): a leaning pad on its screen, a rail along the
    # wall, a call button, the sign on the floor and on the wall
    g = Geo()
    g.box((SCR_X + 0.045, -0.905, FLOOR + 0.98), (0.06, 0.33, 0.50))
    g.obj("interior.bay.pad", "seat2", bevel=0.02, angle=50.0)
    g = Geo()
    yw = wall_y(1.5, 1.12)
    pts = [(1.12, -yw + 0.01, 1.13), (1.16, -yw + 0.075, 1.13), (2.02, -yw + 0.075, 1.13),
           (2.06, -yw + 0.01, 1.13)]
    g.pipe(pts, 0.016, n=12)
    g.obj("interior.bay.rail", "paint2")
    sign = Parts()
    blue, white = Geo(), Geo()
    blue.box((1.56, -0.88, FLOOR + 0.0012), (0.42, 0.42, 0.0024))
    wheelchair(white, V3((1.56, -0.88, FLOOR + 0.003)), V3((0, -1, 0)), V3((-1, 0, 0)), 0.30)
    sb = float(s_z(0.72))
    V, Fc = patch_on(1.42, 1.70, sb - 0.14, sb + 0.14, TH + 0.002, r=0.03)
    sign.add(V * np.array((1, -1, 1)), [f[::-1] for f in Fc], "sign_blue")
    c = f1(1.56, sb, TH + 0.004)
    n = p3(Fn(np.array([1.56]), np.array([sb]))[0])
    c.y, n.y = -c.y, -n.y
    up = V3((0, 0, 1)) - n * n.z
    up.normalize()
    wheelchair(white, c, V3((-1, 0, 0)), up, 0.20)
    sign.geo(blue, "sign_blue")
    sign.geo(white, "sign_white")
    sign.obj("interior.bay.sign")
    g, gl = Geo(), Geo()
    cb = f1(1.92, float(s_z(0.80)), TH)
    cb.y = -cb.y
    g.box(cb + V3((0, 0.012, 0)), (0.09, 0.024, 0.09))
    gl.cyl(cb + V3((0, 0.022, 0)), 0.006, 0.024, n=20, axis='y')
    g.obj("interior.bay.call", "lining_lo", bevel=0.004)
    gl.obj("interior.bay.call.button", "sign_blue")


def wheelchair(g, c, right, up, size):
    """The wheelchair sign as flat pieces: a wheel's ring, a seated figure."""
    def at(u, v):
        return c + right * (u * size) + up * (v * size)
    n = right.cross(up)
    n.normalize()
    ring = [(0.06 + 0.22 * cos(a), -0.14 + 0.22 * sin(a)) for a in np.linspace(0.9, 5.6, 22)]
    for (a, b), w in zip(zip(ring, ring[1:]), [0.05] * 21):
        _bar(g, at(*a), at(*b), n, w * size)
    for a, b, w in (((-0.10, 0.30), (-0.06, -0.02), 0.07), ((-0.06, -0.02), (0.20, -0.02), 0.07),
                    ((0.20, -0.02), (0.30, -0.30), 0.07), ((0.30, -0.30), (0.40, -0.30), 0.06),
                    ((-0.09, 0.16), (0.14, 0.16), 0.055)):
        _bar(g, at(*a), at(*b), n, w * size)
    head = [at(-0.11 + 0.07 * cos(a), 0.42 + 0.07 * sin(a))
            for a in np.linspace(0, 2 * pi, 12, endpoint=False)]
    g.add(head, [tuple(range(12))])


def _bar(g, a, b, n, w):
    t = (b - a).normalized()
    s = n.cross(t) * (w / 2)
    a2, b2 = a - t * (w / 2), b + t * (w / 2)
    g.add([a2 - s, b2 - s, b2 + s, a2 + s], [(0, 1, 2, 3)])


# ---------------------------------------------------------------------------------------
# information, safety, small fittings
# ---------------------------------------------------------------------------------------
STOPS = ("CINDER GATE", "LOWMARKET", "GLASSWHARF", "NINTH SPIRE", "IRONMERE", "SOLACE PARK")
POD_NO = "Q-217"


def build_fittings():
    lit, litw, dark, steel, red, lab = Geo(), Geo(), Parts(), Geo(), Geo(), Geo()
    # ---- a line display over each door, on the header: the line, its stops, the next one
    for flip in (False, True):
        r = -1 if flip else 1
        s0 = S_DT + 0.105
        V, Fc = patch_on(-0.62, 0.62, s0 - 0.062, s0 + 0.062, TH + 0.003, r=0.02)
        if flip:
            V, Fc = V * np.array((1, -1, 1)), [f[::-1] for f in Fc]
        dark.add(V, Fc, "screen_off")
        d = TH + 0.005
        xs = np.linspace(-0.50, 0.50, len(STOPS))
        V, Fc = trim(Fi(d), np.array([(-0.52, s0 - 0.024), (0.52, s0 - 0.024),
                                      (0.52, s0 - 0.019), (-0.52, s0 - 0.019)]), out=False)
        if flip:
            V = V * np.array((1, -1, 1))
        lit.add([p3(q) for q in V], Fc)
        for k, (x, name) in enumerate(zip(xs, STOPS)):
            g = litw if k == 2 else lit
            ring = rrect(r * x - 0.009, r * x + 0.009, s0 - 0.0305, s0 - 0.0125, 0.009, 4)
            V, Fc = trim(Fi(d + 0.001), ring, out=False, lattice=False)
            if flip:
                V = V * np.array((1, -1, 1))
            g.add([p3(q) for q in V], Fc)
            text_on(g, name, 0.016, r * x, s0 + 0.012, d, right=r, flip=flip, font="condensed")
        text_on(litw, "NEXT  GLASSWHARF   2 MIN", 0.017, r * 0.0, s0 + 0.043, d, right=r,
                flip=flip)
        # the door-closing light: a bar along the header's lower edge
        V, Fc = trim(Fi(TH + 0.002), np.array([(-0.60, S_DT + 0.016), (0.60, S_DT + 0.016),
                                               (0.60, S_DT + 0.028), (-0.60, S_DT + 0.028)]),
                     out=False)
        if flip:
            V = V * np.array((1, -1, 1))
        lit.add([p3(q) for q in V], Fc)
    dark.obj("interior.display.glass")
    lit.obj("interior.display.amber", "pixel")
    litw.obj("interior.display.white", "pixel_w")

    # ---- on the door posts: the emergency handle box (front post) and the intercom (rear)
    for flip in (False, True):
        m = np.array((1, -1 if flip else 1, 1))
        r = -1 if flip else 1
        P = Parts()
        for x0, kind in ((0.81, "handle"), (-0.81, "intercom")):
            sz = float(s_z(1.52))
            c = f1(x0, sz, TH)
            n = -p3(Fn(np.array([x0]), np.array([sz]))[0])      # into the cabin
            up = (V3((0, 0, 1)) - n * n.z).normalized()
            g = Geo()
            R = Matrix((V3((1, 0, 0)), n, up)).transposed()
            g.box(c + n * 0.011, (0.105, 0.022, 0.19), rot=R)
            P.add(*geo_closed(g), "red" if kind == "handle" else "lining_lo", flat=True)
            g = Geo()
            if kind == "handle":
                g.box(c + n * 0.024 + up * 0.012, (0.028, 0.012, 0.085), rot=R)
                g.cyl(c + n * 0.022 + up * 0.012, 0.012, 0.022, n=14, axis=n)
                P.add(*geo_closed(g), "steel", flat=True)
                g = Geo()
                K.text_flat(g, "EMERGENCY", 0.011, c + n * 0.0226 + up * 0.078,
                            V3((r * 1.0, 0, 0)), up)
                K.text_flat(g, "DOOR RELEASE", 0.008, c + n * 0.0226 - up * 0.062,
                            V3((r * 1.0, 0, 0)), up)
                K.text_flat(g, "PULL DOWN", 0.007, c + n * 0.0226 - up * 0.078,
                            V3((r * 1.0, 0, 0)), up)
                P.geo(g, "sign_white")
            else:
                for k in range(7):
                    g.box(c + n * 0.022 + up * (0.03 + 0.009 * k), (0.07, 0.004, 0.0035), rot=R)
                P.add(*geo_closed(g), "dark_metal", flat=True)
                g = Geo()
                g.cyl(c + n * 0.022 - up * 0.035, 0.008, 0.017, n=18, axis=n)
                P.add(*geo_closed(g), "sign_blue", flat=True)
                g = Geo()
                K.text_flat(g, "HELP POINT", 0.009, c + n * 0.0226 - up * 0.07,
                            V3((r * 1.0, 0, 0)), up)
                K.text_flat(g, "SOS", 0.007, c + n * 0.031 - up * 0.035, V3((r * 1.0, 0, 0)), up)
                P.geo(g, "sign_white")
        P.obj("interior.posts." + ("r" if flip else "l"), flip_y=flip)

    # ---- under the console: speaker and vent grilles, a camera dome each side of the
    # doors, reading spots over the seats
    grille, dome, spots = Geo(), Geo(), Geo()
    zc = CONSOLE[2][1]
    ends = (LIN_A + 0.25, (SP_X - 0.15) if not MID else (XF - 0.33))
    xs = np.arange(ends[0], ends[1], 0.86)
    for k, x in enumerate(xs):
        if abs(x) < 0.5:
            continue
        for j in range(9):                              # a vent: slots across
            grille.box((x - 0.10 + 0.025 * j, 0.0, zc - 0.001), (0.012, 0.30, 0.004))
        for a in range(3):                              # a speaker: rings of holes
            for q in range(6 * (a + 1)):
                th = 2 * pi * q / (6 * (a + 1))
                grille.cyl((x + 0.32 + 0.018 * (a + 1) * cos(th), 0.018 * (a + 1) * sin(th),
                            zc - 0.002), 0.003, 0.005, n=6)
        for sy in (1, -1):
            spots.cyl((x + 0.32, sy * 0.15, zc - 0.004), 0.005, 0.016, n=14)
    for x in (-0.45, 0.45, -3.9):
        dome.lathe([(0.0, 0.0), (0.0, 0.05), (-0.012, 0.05), (-0.032, 0.042), (-0.05, 0.022),
                    (-0.056, 0.0)], 20, axis='z', at=(x, 0.0, zc))
    grille.obj("interior.console.grilles", "dark_metal")
    dome.obj("interior.cctv", "gloss_black")
    spots.obj("interior.light.spots", "cabin_led")

    # ---- the rear end: a screen and the pod's number over the gangway, grab handles each
    # side of it, luggage shelves, the fire extinguisher
    for e in ((-1, 1) if MID else (-1,)):
        xi = e * (XF - 0.08)
        fwd = V3((-e, 0, 0))                                    # into the cabin
        rt = V3((0, -e, 0))                                     # a reader's right
        g = Geo()
        g.box(V3((xi, 0, 2.45)) + fwd * 0.007, (0.014, 0.78, 0.085))
        g.obj("interior.end.screen." + ("r" if e < 0 else "f"), "screen_off", bevel=0.003)
        K.text_flat(litw, "POD " + POD_NO, 0.03, V3((xi, -e * 0.24, 2.45)) + fwd * 0.0146, rt,
                    V3((0, 0, 1)))
        K.text_flat(lab, "THROUGH TO NEXT POD", 0.012, V3((xi, 0.0, 2.386)) + fwd * 0.001, rt,
                    V3((0, 0, 1)))
        gl = Geo()
        K.text_flat(gl, "LOWMARKET  2", 0.03, V3((xi, e * 0.20, 2.45)) + fwd * 0.0146, rt,
                    V3((0, 0, 1)))
        gl.obj("interior.end.text." + ("r" if e < 0 else "f"), "pixel")
        for sy in (1, -1):
            steel.pipe([V3((xi, sy * 0.60, 1.18)), V3((xi, sy * 0.60, 1.22)) + fwd * 0.055,
                        V3((xi, sy * 0.60, 1.62)) + fwd * 0.055, V3((xi, sy * 0.60, 1.66))],
                       0.013, n=12, up=(0, 1, 0))
            # luggage: two shelves on tube frames between the wall and the passage
            x0, x1 = xi + fwd.x * 0.02, xi + fwd.x * (0.45 if sy > 0 else 0.36)
            ys = (sy * 0.545, sy * (wall_y(xi, 0.9) - 0.03))
            for z in (FLOOR + 0.36, FLOOR + 0.80):
                steel.box(((x0 + x1) / 2, (ys[0] + ys[1]) / 2, z),
                          (abs(x1 - x0), abs(ys[1] - ys[0]), 0.012))
                for q in range(5):
                    steel.box(((x0 + x1) / 2, ys[0] + (ys[1] - ys[0]) * (q + 0.5) / 5, z + 0.009),
                              (abs(x1 - x0) - 0.03, 0.012, 0.006))
            for x in (x1 - fwd.x * 0.012,):
                steel.pipe([(x, ys[0] + sy * 0.012, FLOOR), (x, ys[0] + sy * 0.012, FLOOR + 0.98),
                            (x - fwd.x * 0.08, ys[0] + sy * 0.012, FLOOR + 1.02)], 0.013, n=10,
                           up=(0, 1, 0))
        # the extinguisher: on the wall by the right shelf
        c = V3((xi, -0.82, FLOOR + 1.22)) + fwd * 0.07
        red.cyl(c - V3((0, 0, 0.19)), 0.34, 0.052, n=20)
        red.lathe([(0.0, 0.052), (0.03, 0.045), (0.05, 0.022), (0.06, 0.022), (0.06, 0.0),
                   (0.0, 0.0)], 20, axis='z', at=c + V3((0, 0, 0.15)))
        steel.box(c + V3((0, 0, 0.225)) + fwd * 0.012, (0.07, 0.022, 0.018))
        steel.box(c - fwd * 0.055, (0.012, 0.085, 0.26))
        K.text_flat(lab, "FIRE", 0.022, c + fwd * 0.0535 + V3((0, 0, 0.02)), rt, V3((0, 0, 1)))
    steel.obj("interior.steel", "steel", bevel=0.0015)
    red.obj("interior.extinguisher", "red")
    # ---- the route screen: on the rear left draught screen, facing the doorway
    g, ga, gw = Geo(), Geo(), Geo()
    x0 = -SCR_X + 0.02
    c = V3((x0, 0.66, 1.62))
    g.box(c + V3((-0.004, 0, 0)), (0.018, 0.64, 0.38))
    g.obj("interior.screen.route.case", "shell", bevel=0.005)
    g = Geo()
    g.box(c + V3((0.006, 0, 0)), (0.006, 0.62, 0.36))
    g.obj("interior.screen.route", "screen_off", bevel=0.002)
    f = c + V3((0.0096, 0, 0))
    rt, up = V3((0, 1, 0)), V3((0, 0, 1))               # read from the doorway, looking back
    K.text_flat(gw, "SKEIN TUBE   LINE 7   UPPER LOOP", 0.016, f + up * 0.145, rt, up)
    K.text_flat(gw, "22:47", 0.022, f + up * 0.143 + rt * 0.255, rt, up)
    _bar(ga, f + rt * -0.26 + up * 0.03, f + rt * 0.26 + up * 0.03, V3((1, 0, 0)), 0.006)
    for k, name in enumerate(STOPS):
        p = f + rt * (-0.26 + 0.104 * k) + up * 0.03
        dot = [p + rt * (0.012 * cos(a)) + up * (0.012 * sin(a))
               for a in np.linspace(0, 2 * pi, 14, endpoint=False)]
        (gw if k == 2 else ga).add([q + V3((0.0004, 0, 0)) for q in dot], [tuple(range(14))])
        K.text_flat(gw if k == 2 else ga, name, 0.0085, p - up * 0.03, rt, up, font="condensed")
    K.text_flat(gw, "NEXT  GLASSWHARF", 0.03, f - up * 0.075 + rt * -0.07, rt, up)
    K.text_flat(ga, "2 MIN", 0.03, f - up * 0.075 + rt * 0.20, rt, up)
    K.text_flat(gw, "DOORS OPEN ON EITHER SIDE   THIS POD IS " + POD_NO, 0.010,
                f - up * 0.135, rt, up, font="condensed")
    ga.obj("interior.screen.route.amber", "pixel")
    gw.obj("interior.screen.route.white", "pixel_w")
    # ---- pictograms on the hoops' linings: priority seats, no smoking, the pod's number
    for flip in (False, True):
        r = -1 if flip else 1
        m = np.array((1, -1 if flip else 1, 1))
        P = Parts()
        gw, gr = Geo(), Geo()
        for x0, kind in ((-2.585, "priority"), (-0.81, "number"), (2.585 if MID else 0.81,
                                                                    "smoke")):
            sz = float(s_z(1.86 if abs(x0) > 1 else 1.90))
            c = f1(x0, sz, TH + 0.003)
            n = -p3(Fn(np.array([x0]), np.array([sz]))[0])
            up = (V3((0, 0, 1)) - n * n.z).normalized()
            rt = V3((1.0, 0, 0))
            if kind == "priority":
                V, Fc = patch_on(x0 - 0.05, x0 + 0.05, sz - 0.05, sz + 0.05, TH + 0.002, r=0.012)
                P.add(V, Fc, "sign_blue")
                c2 = c - up * 0.008                    # a seated figure with a stick
                for a, b, w in (((-0.012, 0.012), (-0.012, -0.012), 0.011),
                                ((-0.012, -0.012), (0.012, -0.012), 0.011),
                                ((0.012, -0.012), (0.012, -0.034), 0.010),
                                ((0.028, 0.006), (0.028, -0.034), 0.005)):
                    _bar(gw, c2 + rt * a[0] + up * a[1], c2 + rt * b[0] + up * b[1], n, w)
                gw.add([c2 + rt * (-0.012 + 0.009 * cos(a)) + up * (0.028 + 0.009 * sin(a))
                        for a in np.linspace(0, 2 * pi, 10, endpoint=False)], [tuple(range(10))])
                K.text_flat(gw, "PRIORITY SEATS", 0.008, c - up * 0.064, rt * r, up)
            elif kind == "smoke":
                ring = [(0.036 * cos(a), 0.036 * sin(a)) for a in np.linspace(0, 2 * pi, 25)]
                for (a, b) in zip(ring, ring[1:]):
                    _bar(gr, c + rt * a[0] + up * a[1], c + rt * b[0] + up * b[1], n, 0.007)
                _bar(gr, c + rt * 0.024 + up * 0.024, c - rt * 0.024 - up * 0.024, n, 0.007)
                _bar(gw, c - rt * 0.02 + n * 0.0004, c + rt * 0.012 + n * 0.0004, n, 0.008)
                K.text_flat(gw, "NO SMOKING  NO VAPOR", 0.007, c - up * 0.052, rt * r, up)
            else:
                K.text_flat(gw, "POD", 0.011, c + up * 0.03, rt * r, up)
                K.text_flat(gw, POD_NO, 0.026, c, rt * r, up)
                K.text_flat(gw, "SKEIN TUBE  LINE 7", 0.007, c - up * 0.028, rt * r, up)
        P.geo(gw, "sign_ink")
        P.geo(gr, "red")
        P.obj("interior.pictograms." + ("r" if flip else "l"), flip_y=flip)
    lab.obj("interior.notices", "sign_white")


# ---------------------------------------------------------------------------------------
# under the floor: the beam's channel, the levitation gear
# ---------------------------------------------------------------------------------------
BEAM_HEAD = (0.20, 0.085, 0.135)            # the guide beam's head: half width, z from, to
BOGIES = ((-3.85, -1.85), (0.35, 2.35))     # where the magnet frames sit (x ranges)


def build_under():
    ce = XF if MID else 2.80                    # where the channel closes
    xs = np.concatenate([[XA], np.arange(-4.4, ce, 0.2), np.linspace(max(XA, ce - 0.36), ce,
                                                                     12)])
    xs = np.unique(np.clip(xs, XA, ce))
    ey = plan(xs) * chan(xs)
    ok = ey > 0.004
    xs, ey = xs[ok], ey[ok]
    P = Parts()
    roof = [(x, 0.0) for x in xs] + [(x, y) for x, y in zip(xs[::-1], ey[::-1])]
    V, Fc = flat(roof, "xy", CH_D, hb=0.15, up=False)
    P.add(V, Fc, "underbody")
    n = len(xs)
    V = np.array([(x, y, float(keel(x))) for x, y in zip(xs, ey)] +
                 [(x, y, CH_D) for x, y in zip(xs, ey)])
    P.add(V, [(i, i + 1, n + i + 1, n + i) for i in range(n - 1)], "underbody")
    mirrored(P.obj("body.channel"))
    # ---- two magnet frames: levitation magnets over the beam's head, guidance arms that
    # reach in under it from both walls, landing skids between the magnets
    lev, arm, skid, cu = Geo(), Geo(), Geo(), Geo()
    for (a, b) in BOGIES if not MID else ((-3.85, -1.85), (1.85, 3.85)):
        n_m = 4
        ln = (b - a) / n_m
        for k in range(n_m):
            x = a + ln * (k + 0.5)
            lev.box((x, 0.0, CH_D - 0.02), (ln - 0.10, 0.36, 0.036))
            for q in range(6):                                  # the windings' ribs
                cu.box((x - (ln - 0.14) / 2 + (ln - 0.14) * (q + 0.5) / 6, 0.0, CH_D - 0.0395),
                       ((ln - 0.14) / 6 - 0.012, 0.30, 0.005))
            for sy in (1, -1):
                arm.box((x, sy * 0.22, 0.040), (ln - 0.16, 0.16, 0.042))
                arm.box((x, sy * 0.285, 0.10), (ln - 0.16, 0.03, 0.16))
                cu.box((x, sy * 0.20, 0.0635), (ln - 0.20, 0.10, 0.005))
        for x in (a + 0.012, (a + b) / 2, b - 0.012):           # skids: between the magnets
            skid.box((x, 0.0, CH_D - 0.022), (0.075, 0.34, 0.044))
    lev.obj("mag.lev", "dark_metal", bevel=0.003)
    arm.obj("mag.arms", "graphite", bevel=0.004)
    skid.obj("mag.skids", "steel", bevel=0.004)
    cu.obj("mag.coils", "copper")


def tube_clearance():
    """The least distance from the section to the tube's wall, the pod on either track."""
    ss = np.linspace(0, S_END, 4000)
    y, z = np.interp(ss, SS_, SY_), np.interp(ss, SS_, SZ_)
    best = (9.0, 0, 0)
    for sg in (1, -1):
        r = np.hypot(sg * y + TUBE_Y, z - TUBE_Z)
        i = int(np.argmax(r))
        if TUBE_R - r[i] < best[0]:
            best = (float(TUBE_R - r[i]), float(sg * y[i]), float(z[i]))
    return best


# ---------------------------------------------------------------------------------------
# lights, displays and markings outside
# ---------------------------------------------------------------------------------------
def build_outside():
    front, rear, door, accent, mark, pix = Geo(), Geo(), Geo(), Geo(), Geo(), Geo()
    endmark = Geo()

    def lay(g, loop, d=-0.0012, flip=True):
        """A patch standing just off the hull, on both sides."""
        if loop is None:
            return
        V, Fc = trim(Fi(d), loop, lattice=False)
        g.add([p3(q) for q in V], Fc)
        if flip:
            g.add([p3(q * np.array((1, -1, 1))) for q in V], [f[::-1] for f in Fc])

    # ---- the running line: a thin light along the skirt's top, the length of the pod
    for a, b in ((XA + 0.05, -DOOR_X - 0.02), (DOOR_X + 0.02, XF - 0.05 if MID else 4.20)):
        lay(accent, band(a, b, S_SK - 0.009, upto(S_SK + 0.009, 0.01), g=0.0))
    # ---- the door's edge lights: a line up each post beside the leaves
    for sx in (-1, 1):
        x0 = sx * (DOOR_X + 0.032)
        lay(door, band(x0 - 0.006, x0 + 0.006, S_ST1 + 0.06, S_DT - 0.06, g=0.0))
    if not MID:
        # ---- the nose's signature: a line of light along the rim's rail down to the tip
        lay(front, band(1.75, 4.47, lambda x: RS(x) - 0.034, lambda x: RS(x) - 0.020, g=0.0))
        # ---- in the band's point: a head lamp's blade each side, a red marker under it
        wd = lambda x: glaze_hi(x) - S_ST1
        lay(front, band(3.98, 4.36, lambda x: S_ST1 + 0.36 * wd(x),
                        lambda x: S_ST1 + 0.58 * wd(x), g=0.0), d=-0.0015)
        lay(rear, band(4.04, 4.33, lambda x: S_ST1 + 0.10 * wd(x),
                       lambda x: S_ST1 + 0.20 * wd(x), g=0.0), d=-0.0015)
        g = Geo()                                       # the tip: a stem that closes the hull
        zk, zr = float(keel(4.497)), float(rim_z(4.497))
        g.sweep([(4.4935, 0, zk - 0.012), (4.4935, 0, zr + 0.014)],
                [(0.0065 * cos(a), 0.032 * sin(a)) for a in np.linspace(0, 2 * pi, 16,
                                                                         endpoint=False)],
                up=(0, 1, 0))
        g.obj("body.nib.tip", "chrome")
        # ---- the nib's slit and its eye: a sensor under a dark lens
        g = Geo()
        xs = np.arange(3.94, 4.47, 0.02)
        for sy in (1, -1):
            P = G(np.concatenate([xs, xs[::-1]]),
                  np.concatenate([np.zeros(len(xs)), np.full(len(xs), sy * 0.004)]), -0.001)
            n = len(xs)
            g.add([p3(q) for q in P], [(i, i + 1, 2 * n - 2 - i, 2 * n - 1 - i)
                                       for i in range(n - 1)])
        c = g1(3.925, 0.0, -0.0012)
        nn = p3(Gn(np.array([3.925]), np.array([0.0]))[0])
        g.lathe([(0.0, 0.0), (0.0, 0.036), (0.004, 0.034), (0.006, 0.0)], 24, axis=nn, at=c)
        g.obj("body.nib.eye", "gloss_black")
        # ---- the destination, on the console's prow behind the windshield
        K.text_flat(pix, "7  GLASSWHARF", 0.045, (SP_X + 0.1012, 0.0, 2.603), (0, 1, 0),
                    (0, 0, 1))
    else:
        for e in (-1, 1):
            for sy in (1, -1):
                rear.box((e * (XF + 0.002), sy * 0.86, 2.02), (0.006, 0.10, 0.03))
    for sy in (1, -1):                                  # the coupling end's markers
        rear.box((XA - 0.002, sy * 0.86, 2.02), (0.006, 0.10, 0.03))
    for e in ((-1, 1) if MID else (-1,)):               # the pod's number on its ends
        K.text_flat(endmark, POD_NO, 0.09, (e * (XF + 0.0015), e * 0.86, 1.72), (0, e, 0),
                    (0, 0, 1))
        K.text_flat(endmark, "COUPLE AT 0.50 M   GANGWAY 1.00 M", 0.016,
                    (e * (XF + 0.0015), e * 0.86, 1.62), (0, e, 0), (0, 0, 1),
                    font="condensed")
    # ---- on the header over each door: the line and where it goes
    for flip in (False, True):
        g = Geo()
        text_on(g, "7  GLASSWHARF", 0.058, 0.0, S_DT + 0.115, -0.0012, right=1 if flip else -1,
                flip=flip, font="condensed")
        pix.add(g.v, g.f)
        # ---- markings: the pod's number, the operator, the maker
        r = 1 if flip else -1
        g = Geo()
        sn = float(s_z(0.53))
        for x0 in (-3.55, 2.05 if not MID else 3.55):
            text_on(g, POD_NO, 0.17, x0, sn, -0.0012, right=r, flip=flip)
        text_on(g, "SKEIN TUBE", 0.075, -2.02, float(s_z(0.60)), -0.0012, right=r, flip=flip)
        text_on(g, "LINE 7  UPPER LOOP", 0.026, -2.02, float(s_z(0.50)), -0.0012, right=r,
                flip=flip, font="condensed")
        text_on(g, "CALDERA  QUILL", 0.02, r * -1.75, float(s_z(0.36)), -0.0012, right=r,
                flip=flip, font="condensed")
        mark.add(g.v, g.f)
    # a service hatch and a charge port on the lower side, as outlines
    for (a, b, za, zb) in ((-4.25, -3.95, 0.34, 0.70), (0.95, 1.30, 0.34, 0.60),
                           (-1.25, -0.92, 0.34, 0.50)):
        hatch = dense(rrect(a, b, float(s_z(za)), float(s_z(zb)), 0.03), 0.04)
        V, Fc = trim(Fi(-0.0008), hatch, [inset(hatch, 0.004)], lattice=False)
        mark.add([p3(q) for q in V], Fc)
        mark.add([p3(q * np.array((1, -1, 1))) for q in V], [f[::-1] for f in Fc])
    # hatches in the spine, as outlines
    for a, b in (((-2.5, -1.9), (0.2, 0.8)) if not MID else ((-2.5, -1.9), (1.9, 2.5))):
        hatch = dense(rrect(a, b, -0.15, 0.15, 0.04), 0.04)
        V, Fc = trim(Gi(-0.0008), hatch, [inset(hatch, 0.004)], out=False, lattice=False)
        mark.add([p3(q) for q in V], Fc)
    # the number on the spine, read from above
    K.text_flat(mark, POD_NO, 0.15, (-3.3, 0.0, TOP + 0.0015), (-1, 0, 0), (0, -1, 0))
    # ---- the aisle: a lighter path inlaid in the floor, guide lights along its edges
    if STAGE != "hull":
        g, gl = Geo(), Geo()
        xa_, xb_ = LIN_A + 0.03, (2.15 if not MID else XF - 0.11)
        ya, yb = AISLE[0] + 0.05, AISLE[1] - 0.05
        g.box(((xa_ + xb_) / 2, (ya + yb) / 2, FLOOR + 0.0006), (xb_ - xa_, yb - ya, 0.0012))
        for x in np.arange(xa_ + 0.2, xb_, 0.45):
            if abs(x) < DOOR_X + 0.25:
                continue
            for y in (ya - 0.018, yb + 0.018):
                gl.cyl((x, y, FLOOR), 0.0025, 0.011, n=10)
        g.obj("interior.floor.path", "floor_path")
        gl.obj("interior.light.guide", "door_led")
    front.obj("light.front", "led_front")
    rear.obj("light.rear", "led_rear")
    door.obj("light.door", "door_led")
    accent.obj("light.running", "led_accent")
    mark.obj("marking", "decal")
    endmark.obj("marking.end", "sign_white")
    pix.obj("display.destination", "pixel")


# ---------------------------------------------------------------------------------------
# what it rides on: the guideway's deck, two guide beams, the tube (in the studio)
# ---------------------------------------------------------------------------------------
def build_track():
    S_ = K.STUDIO
    ty, tz = -TUBE_Y, TUBE_Z                    # the tube's axis, in the pod's frame
    xa, xb = -5.6, 5.4
    deck_z = -0.40
    # ---- the deck: a chord of the tube under both tracks
    hw = sqrt(TUBE_R ** 2 - (tz - deck_z) ** 2) - 0.02
    a0 = atan2(deck_z - tz, hw)
    arc = [(ty + (TUBE_R - 0.012) * cos(a), tz + (TUBE_R - 0.012) * sin(a))
           for a in np.linspace(a0, -pi - a0, 40)]
    g = Geo()
    g.prism([(xa, y, z) for y, z in arc], (xb - xa, 0, 0))
    g.obj("track.deck", "concrete", coll=S_)
    g, cu, st = Geo(), Geo(), Geo()
    hy, hz0, hz1 = BEAM_HEAD
    for y0 in (0.0, 2 * ty):
        g.box(((xa + xb) / 2, y0, (deck_z + hz0) / 2), (xb - xa, 0.11, hz0 - deck_z))
        g.box(((xa + xb) / 2, y0, (hz0 + hz1) / 2), (xb - xa, 2 * hy, hz1 - hz0))
        g.box(((xa + xb) / 2, y0, deck_z + 0.03), (xb - xa, 0.34, 0.06))
        cu.box(((xa + xb) / 2, y0, hz1 + 0.0015), (xb - xa, 0.12, 0.003))
        for x in np.arange(xa + 0.5, xb, 1.0):              # gussets from the foot to the web
            for sy in (1, -1):
                st.prism([(x - 0.012, y0 + sy * 0.055, deck_z + 0.06),
                          (x - 0.012, y0 + sy * 0.16, deck_z + 0.06),
                          (x - 0.012, y0 + sy * 0.055, deck_z + 0.30)], (0.024, 0, 0))
    st.box(((xa + xb) / 2, ty, deck_z + 0.02), (xb - xa, 0.70, 0.04))    # a walkway's grating
    for k in range(int((xb - xa) / 0.12)):
        st.box((xa + 0.06 + 0.12 * k, ty, deck_z + 0.045), (0.05, 0.66, 0.012))
    g.obj("track.beam", "track_steel", bevel=0.004, coll=S_)
    cu.obj("track.beam.copper", "copper", coll=S_)
    st.obj("track.beam.fittings", "dark_metal", coll=S_)
    # ---- the tube: ribs open toward the viewer's side, glass between them on the far side
    a_cut = np.arcsin((0.0 - tz) / TUBE_R)              # the near side stops at the pod's foot
    ribs = Geo()
    sec = [(-0.06, 0.0), (0.06, 0.0), (0.06, 0.16), (-0.06, 0.16)]
    for x in (-5.0, -2.5, 0.0, 2.5, 5.0):
        angs = np.linspace(a_cut, a_cut - (2 * pi - (pi / 2 + 0.35 - a_cut)), 90)
        pts = [(x, ty + (TUBE_R + 0.0) * cos(a), tz + TUBE_R * sin(a)) for a in angs]
        ups = [V3((0, cos(a), sin(a))) for a in angs]
        ribs.sweep(pts, sec, up=ups)
    ribs.obj("track.tube.ribs", "tube_rib", bevel=0.004, coll=S_)
    P = Parts()
    angs = np.linspace(pi + 0.75, pi / 2 + 0.36, 50)
    V = np.array([(x, ty + (TUBE_R + 0.03) * cos(a), tz + (TUBE_R + 0.03) * sin(a))
                  for x in (xa + 0.5, xb - 0.3) for a in angs])
    P.add(V, [(i, i + 1, 50 + i + 1, 50 + i) for i in range(49)], "glass_tube")
    P.obj("track.tube.glass", coll=S_)
    g = Geo()                                           # rails along the ribs' ends
    for a in (a_cut, pi / 2 + 0.35):
        g.box(((xa + xb) / 2 + 0.1, ty + (TUBE_R + 0.08) * cos(a), tz + (TUBE_R + 0.08) * sin(a)),
              (xb - xa - 0.6, 0.10, 0.10))
    g.obj("track.tube.rails", "tube_rib", bevel=0.004, coll=S_)


# ---------------------------------------------------------------------------------------
# views, and the build
# ---------------------------------------------------------------------------------------
def studio():
    """The studio for a 9 m pod: the floor under the tube, wider lights."""
    cyc = K.STUDIO.objects.get("cyc")
    if cyc is not None:
        cyc.location.z = -1.30
    for name, (loc, size, power) in dict(
            top=((0.2, 0.0, 7.5), (5.0, 11.0), 2300),
            key=((8.5, 7.5, 4.4), (5.0, 3.0), 1500),
            rim=((-9.0, -6.5, 6.0), (6.0, 1.6), 1700),
            fill=((9.0, -6.0, 2.2), (4.0, 2.5), 500),
            strip=((0.0, 7.5, 1.6), (13.0, 0.6), 700),
            strip2=((0.0, -7.5, 1.6), (13.0, 0.6), 700)).items():
        o = K.STUDIO.objects.get(name)
        if o is None:
            continue
        o.location = loc
        o.data.size, o.data.size_y = size
        o.data.energy = power
        o.visible_camera = False                # a camera inside looks out through the glass
        K.aim(o, (0, 0, 1.2))


OPEN_VIEWS = ("hero", "door")


def main():
    make_materials()
    build_shell()
    K.log("shell")
    if STAGE != "hull":
        build_lining()
        K.log("lining")
        doors = build_doors()
        K.log("doors")
        for e in ((-1, 1) if MID else (-1,)):
            build_end(e)
        K.log("ends")
        n_seats = build_seats()
        if not MID:
            build_lounge()
        build_vestibule()
        build_fittings()
        K.log("interior, %d seats%s" % (n_seats, "" if MID else " and the lounge's bench"))
        build_under()
        build_outside()
        build_track()
        c = tube_clearance()
        K.log("least clearance to the tube: %.0f mm at y = %.2f, z = %.2f" % (
            c[0] * 1000, c[1], c[2]))
        if not SHUT:
            ga = K.Group("door.open.a", [doors["la"]], pivot=(0.35, 1.2, 1.3))
            gb = K.Group("door.open.b", [doors["lb"]], pivot=(-0.35, 1.2, 1.3))
            ga.pose_for(OPEN_VIEWS, loc=(0.70, 0.075, 0))
            gb.pose_for(OPEN_VIEWS, loc=(-0.70, 0.075, 0))

    K.unlit(("strip", "strip2", "top"), "glass.*")
    K.unlit("key", "glass.side.*")
    K.unlit("top", "body.header")               # mirrored whole in the side view otherwise
    K.unlit(("top", "key", "rim", "fill"), "track.tube.glass")
    K.meant("symmetry", "interior.*", "door.*", "marking*", "display.*", "light.*")
    K.meant("through", "interior.*")
    K.after_studio(studio)
    K.VIEWS["hero"].update(dir=(1.0, 0.80, 0.22))
    K.VIEWS["rear"].update(dir=(-1.0, -0.82, 0.26))
    ey = FLOOR + 1.6                            # a standing eye
    K.VIEWS.update(
        aisle=dict(dir=(-1.0, 0.0, 0.0), lens=17, target=(1.0, -0.22, ey - 0.12), dist=4.9),
        vestibule=dict(dir=(-0.62, -1.0, -0.03), lens=14, target=(0.05, 0.9, ey - 0.12),
                       dist=1.72),
        seats=dict(dir=(1.0, -0.75, 0.25), lens=20, target=(-2.9, 0.3, 1.0), dist=2.1),
        gangway=dict(dir=(1.0, 0.1, 0.02), lens=17, target=(-4.2, -0.1, ey - 0.25), dist=2.6),
        lounge=dict(dir=(-1.0, -0.12, 0.2), lens=16, target=(3.0, 0.0, 1.35), dist=1.9),
        lookback=dict(dir=(1.0, 0.03, 0.02), lens=15, target=(1.0, -0.1, FLOOR + 1.2),
                      dist=2.05),
        door=dict(dir=(0.5, 1.0, 0.16), lens=50, target=(0.0, 1.0, 1.25), dist=7.0),
        nose=dict(dir=(1.0, 0.55, 0.16), lens=70, target=(3.5, 0.2, 1.2), dist=7.0),
        low=dict(dir=(1.0, 0.9, -0.02), lens=40, target=(1.0, 0.3, 0.3), dist=7.5),
        tube=dict(dir=(1.0, 0.0, 0.04), lens=45, target=(0.0, -TUBE_Y, TUBE_Z - 0.3),
                  dist=17.0),
    )
    K.shoot(sheet=("hero", "front", "side", "back"), preview=("hero", "rear_l", "side", "front"),
            extra=dict(view="tube", size=(880, 495), corner="tl", margin=0.05))


main()
