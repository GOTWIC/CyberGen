"""Orrin Aria: a two-seat hypercar poured as five drops (both names made up), built on
vehicles/carkit.py.

Run (always through the wrapper, one Blender job at a time on this machine):
    vehicles/blender.sh vehicles/cars/orrin_aria.py --out DIR --preview
    vehicles/blender.sh vehicles/cars/orrin_aria.py --out DIR --sheet [--night]

Five closed bodies with no crease anywhere, each a ring cage that closes on a pole at both
ends, as the Lumen's and the Pebble's hulls do:
  core    the cabin and the low nose: a teardrop from the nose pole to the tail pole, its two
          top lines the glass canopy, pole to pole;
  pods    a front fender each side (a tube beside the nose, free of it ahead of the axle) and
          a rear hip each side (a tube that stands clear of the cabin: the channel);
  yoke    one hoop over the glass behind the heads whose two legs fly back over the channels
          and sink into the hips' crests: the flying buttresses.
A blade under the nose (the through-duct's floor) and a blade across the three tails tie the
drops together; faired arms cross the channels at the rear axle. Lights, shut lines and dot
fields lie on the surface as built (snap), crescents and lidded wheel wells are cut out.
"""
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import bpy                                                          # noqa: E402
import carkit as K                                                  # noqa: E402
from carkit import Geo, Matrix, V3, cos, on_body, pi, rad, sin, text_flat   # noqa: E402

# ---------------------------------------------------------------------------------------
# dimensions
# ---------------------------------------------------------------------------------------
FA_X, RA_X = 1.40, -1.35            # axles: wheelbase 2.75
R, RIM = 0.38, 0.30                 # tire radius, rim radius
F_W, R_W = 0.265, 0.31              # tire widths
F_OUT, R_OUT = 0.940, 0.955         # outer face of the tires
F_LID, R_LID = 0.60, 0.565          # top of the wheel openings: the body lids the wheels
NOSE = V3((2.345, 0, 0.405))        # the poles the core closes on
TAIL = V3((-2.375, 0, 0.53))

# ---------------------------------------------------------------------------------------
# the core: stations (rings) and lines
# ---------------------------------------------------------------------------------------
LINES = "CGESULRB"
#        C top centerline, G mid canopy, E canopy edge, S shoulder, U widest, L lower flank,
#        R rocker, B floor centerline
ORDER = ["P0", "N1", "N2", "A1", "FA", "A3", "D1", "M1", "D2", "B1", "RA", "R3", "T1", "T0"]
PT = {}


def ring(x, c, g, e, s, u, lo, r, b):
    """A station at one x (or one x per line): z of C, (y, z) of the others, z of B."""
    xs = x if isinstance(x, (list, tuple)) else [x] * 8
    pts = [(0.0, c), g, e, s, u, lo, r, (0.0, b)]
    return [(xs[k], p[0], p[1]) for k, p in enumerate(pts)]


def stations():
    T = {
        # the nose: a slim drop held between the fender pods, its belly lifted off the blade
        "N1": ring(2.295, .462, (.05, .46), (.10, .455), (.155, .438), (.185, .405), (.155, .372),
                   (.09, .352), .347),
        "N2": ring(2.08, .515, (.09, .512), (.18, .502), (.27, .48), (.315, .435), (.285, .375),
                   (.17, .335), .325),
        "A1": ring(1.75, .578, (.14, .573), (.28, .558), (.39, .522), (.44, .45), (.41, .34),
                   (.27, .265), .255),
        "FA": ring(FA_X, .665, (.19, .658), (.37, .634), (.52, .585), (.62, .47), (.60, .30),
                   (.44, .17), .15),
        "A3": ring(1.05, .81, (.24, .795), (.45, .735), (.62, .67), (.72, .50), (.70, .29),
                   (.57, .14), .13),
        # the door cuts fan like petals: forward at the top, back at the top
        "D1": ring((.81, .81, .79, .755, .70, .66, .64, .64), .975, (.29, .948), (.52, .805),
                   (.70, .715), (.795, .515), (.78, .285), (.66, .135), .13),
        "M1": ring(0.20, 1.14, (.33, 1.097), (.575, .835), (.74, .725), (.83, .52), (.81, .285),
                   (.69, .135), .13),
        "D2": ring((-.40, -.40, -.375, -.34, -.30, -.275, -.265, -.265), 1.12, (.305, 1.078),
                   (.50, .86), (.615, .745), (.70, .53), (.685, .295), (.60, .145), .135),
        # behind the seats the core draws in to a slim tail: the cabin stands free of the hips
        "B1": ring(-0.82, .995, (.225, .965), (.345, .815), (.405, .71), (.44, .53), (.43, .32),
                   (.37, .17), .15),
        "RA": ring(RA_X, .825, (.15, .805), (.24, .715), (.29, .655), (.325, .53), (.315, .36),
                   (.26, .225), .195),
        "R3": ring(-1.86, .685, (.095, .675), (.16, .635), (.20, .60), (.22, .53), (.205, .435),
                   (.155, .345), .315),
        "T1": ring(-2.24, .592, (.04, .589), (.075, .58), (.095, .562), (.105, .53), (.095, .50),
                   (.065, .476), .468),
    }
    for name, src, pole in (("P0", "N1", NOSE), ("T0", "T1", TAIL)):
        T[name] = [(pole.x, p[1] * 0.22, pole.z + (p[2] - pole.z) * 0.22) for p in T[src]]
    S = K.fill([T[k] for k in ORDER])
    PT.update(K.table(ORDER, LINES, S))
    return S


PMAT = dict(front="paint", door="paint", sill="paint", rear="paint", glass="glass_dome",
            floor="underbody", well="well", slot="void", pod="paint", hip="paint", yoke="paint")


def panel_of(i, j):
    if j == 6 and 3 <= i <= 10:
        return "floor"
    if j <= 1:                           # the canopy: from the nose pole to the tail pole
        return "glass"
    if i <= 5:
        return "front"
    if i <= 7:
        return "sill" if j == 5 else "door"
    return "rear"


# ---------------------------------------------------------------------------------------
# the pods: tubes of egg sections that close on a pole at both ends
# ---------------------------------------------------------------------------------------
POD_M = 12
#          x     yc    zc    out   in    up    down
FRONT = [(2.24, .800, .345, .100, .100, .085, .075),
         (2.05, .800, .365, .170, .160, .200, .160),
         (1.78, .800, .410, .215, .210, .340, .215),
         (FA_X, .800, .430, .225, .235, .450, .250),
         (1.02, .795, .430, .215, .225, .370, .250),
         (0.72, .780, .440, .170, .190, .250, .230),
         (0.42, .745, .450, .110, .120, .150, .160)]
FRONT_POLES = (V3((2.305, .80, .34)), V3((0.20, .70, .46)))
HIP = [(-0.24, .910, .430, .080, .080, .100, .100),
       (-0.52, .885, .430, .140, .140, .250, .230),
       (-0.92, .825, .430, .210, .230, .400, .260),
       (RA_X, .800, .430, .240, .250, .470, .270),
       (-1.80, .775, .450, .235, .220, .400, .250),
       (-2.12, .730, .500, .180, .160, .210, .170),
       (-2.28, .690, .520, .090, .085, .085, .075)]
HIP_POLES = (V3((-0.12, .915, .43)), V3((-2.345, .675, .525)))


def egg(x, yc, zc, ro, ri, ru, rd, n=2.8, m=POD_M):
    """A ring about the x axis at x: an egg with its own radius out, in, up and down."""
    def pw(v):
        return (abs(v) ** (2.0 / n)) * (1 if v >= 0 else -1)
    out = []
    for k in range(m):
        t = 2 * pi * k / m
        c, s = sin(t), cos(t)
        out.append((x, yc + (ro if c >= 0 else ri) * pw(c), zc + (ru if s >= 0 else rd) * pw(s)))
    return out


def pod_cage(rows, poles):
    S = [egg(*r) for r in rows]
    a, b = poles
    first = [(a.x, a.y + (p[1] - rows[0][1]) * 0.22, a.z + (p[2] - rows[0][2]) * 0.22)
             for p in S[0]]
    last = [(b.x, b.y + (p[1] - rows[-1][1]) * 0.22, b.z + (p[2] - rows[-1][2]) * 0.22)
            for p in S[-1]]
    return [first] + S + [last]


def lid_cutter(g, cx, top, a=0.425, z0=0.31, n=2.6, y0=0.92, depth=0.4):
    """A wheel opening: straight sides and a flattened arch for a top (a superellipse), so
    the body comes down over the tire like an eyelid."""
    b = top - z0
    pts = []
    for k in range(29):
        t = pi * k / 28
        c, s = cos(t), sin(t)
        pts.append((cx + a * (abs(c) ** (2 / n)) * (1 if c >= 0 else -1),
                    z0 + b * (s ** (2 / n))))
    for sgn in (1, -1):
        poly = ([V3((pts[0][0], sgn * y0, -0.3))] + [V3((x, sgn * y0, z)) for x, z in pts]
                + [V3((pts[-1][0], sgn * y0, -0.3))])
        g.prism(poly, (0, sgn * depth, 0))


def lune(g, a, b, d, toward, far, near, out=0.2, depth=0.04, flare=0.02, n=16):
    """A crescent slot for the cutters: the chord a to b seen about along d, both edges bowed
    toward `toward` (by far and by near), cut from outside to depth behind the chord. The
    slot widens by flare on its way in, so the panels' rims stay behind its walls."""
    a, b, d = V3(a), V3(b), V3(d).normalized()
    u = b - a
    ln = u.length
    u.normalize()
    d = (d - u * d.dot(u)).normalized()     # cut square to the chord: both tips on the skin
    v = d.cross(u).normalized()
    if v.dot(V3(toward)) < 0:
        v = -v
    ts = [k / n for k in range(n + 1)]
    hi = [a + u * ln * t + v * far * 4 * t * (1 - t) for t in ts]
    lo = [a + u * ln * t + v * near * 4 * t * (1 - t) for t in ts[1:-1]]
    hi2 = [p + v * flare * (4 * t * (1 - t)) ** 0.5 for p, t in zip(hi, ts)]
    lo2 = [p - v * flare * (4 * t * (1 - t)) ** 0.5 for p, t in zip(lo, ts[1:-1])]
    for sgn in (1, -1):
        dd = V3((d.x, sgn * d.y, d.z))
        rim = [V3((p.x, sgn * p.y, p.z)) for p in hi + lo[::-1]]
        rim2 = [V3((p.x, sgn * p.y, p.z)) for p in hi2 + lo2[::-1]]
        m = 2 * n
        faces = [(k, (k + 1) % m, m + (k + 1) % m, m + k) for k in range(m)]
        for o in (0, m):
            faces.append((o, o + 1, o + m - 1))
            faces += [(o + k, o + k + 1, o + m - k - 1, o + m - k) for k in range(1, n - 1)]
            faces.append((o + n - 1, o + n, o + n + 1))
        g.add([p + dd * out for p in rim] + [p - dd * depth for p in rim2], faces)


CORE = []                               # the core's panels: what the liner and the yoke snap to


def build_hull():
    ang = list(range(-25, 206, 10))
    # ---- the core
    slots = Geo()
    lune(slots, (2.285, .17, .385), (2.10, .305, .40), (0.45, 0.85, -0.25), (0, 0, -1),
         0.030, 0.014, depth=0.035, flare=0.010)
    body = K.build_body(stations(), panel_of, PMAT, 0.0, 0.0,
                        front=dict(kind="flat", panel="front", crease=0.0),
                        rear=dict(kind="flat", panel="rear", crease=0.0),
                        cutters=[(slots, "slot")], subdiv=4, thick=0.004)
    CORE.extend(ob for pn, ob in body.parts.items() if pn not in ("slot",))
    # ---- the front fender pods
    cav, cav2, lids, slots = Geo(), Geo(), Geo(), Geo()
    K.well_cutter(cav, FA_X, R, 0.405, 0.685, ang, depth=0.245)
    K.well_cutter(cav2, FA_X, R, 0.392, 0.92, ang, depth=F_OUT + 0.008 - 0.92)
    lid_cutter(lids, FA_X, F_LID)
    lune(slots, (0.905, .97, .30), (0.955, .97, .63), (0, 1, 0), (-1, 0, 0), 0.058, 0.028,
         depth=0.05, flare=0.018)                                   # the wheel's wake
    K.build_body(pod_cage(FRONT, FRONT_POLES), lambda i, j: "pod", PMAT, 0.0, 0.0, name="pod",
                 front=dict(kind="flat", panel="pod", crease=0.0),
                 rear=dict(kind="flat", panel="pod", crease=0.0), wrap=True,
                 cutters=[(cav, "well"), (cav2, "well"), (lids, "well"), (slots, "slot")],
                 subdiv=4, thick=0.004)
    # ---- the rear hips
    cav, cav2, lids, slots = Geo(), Geo(), Geo(), Geo()
    K.well_cutter(cav, RA_X, R, 0.405, 0.63, ang, depth=0.30)
    K.well_cutter(cav2, RA_X, R, 0.392, 0.92, ang, depth=R_OUT + 0.008 - 0.92)
    lid_cutter(lids, RA_X, R_LID)
    for x0 in (-0.845, -0.775):                                     # paired crescents: intakes
        lune(slots, (x0 + 0.03, 1.0, .31), (x0 - 0.02, 1.0, .60), (0, 1, 0), (1, 0, 0),
             0.044, 0.022, depth=0.045, flare=0.014)
    K.build_body(pod_cage(HIP, HIP_POLES), lambda i, j: "hip", PMAT, 0.0, 0.0, name="hip",
                 front=dict(kind="flat", panel="hip", crease=0.0),
                 rear=dict(kind="flat", panel="hip", crease=0.0), wrap=True,
                 cutters=[(cav, "well"), (cav2, "well"), (lids, "well"), (slots, "slot")],
                 subdiv=4, thick=0.004)


# ---------------------------------------------------------------------------------------
# the yoke: a hoop over the glass, its legs the flying buttresses
# ---------------------------------------------------------------------------------------
#        x      y      z (None: on the core's skin)  half width, half thickness
YOKE = [(-0.30, 0.00, None, .066, .019),
        (-0.31, 0.16, None, .070, .020),
        (-0.34, 0.31, None, .080, .023),
        (-0.42, 0.445, .990, .094, .028),
        (-0.57, 0.555, .962, .105, .034),
        (-0.80, 0.640, .938, .108, .038),
        (-1.07, 0.705, .918, .112, .042),
        (RA_X, 0.770, .895, .125, .055),
        (-1.68, 0.775, .835, .120, .060)]
YOKE_POLE = V3((-2.0, 0.76, 0.74))


def build_yoke():
    tree = K.body_bvh(CORE, default=False)
    P, N = [], []
    for x, y, z, _, _ in YOKE:
        if z is None:
            loc, n, _, _ = tree.ray_cast(V3((x, y, 3.0)), V3((0, 0, -1)))
            n = n if n.z > 0 else -n
            P.append(loc + n * 0.010)
            N.append(V3((0, n.y, n.z)).normalized() if y == 0 else n)
        else:
            P.append(V3((x, y, z)))
            N.append(V3((0, 0.22, 1)).normalized())
    N[3] = (N[2] + N[4]).normalized()
    S = []
    for i, (x, y, z, hw, ht) in enumerate(YOKE):
        t = (P[min(i + 1, len(P) - 1)] - P[max(i - 1, 0)]).normalized()
        if i == 0:
            t = V3((0, 1, 0))
        w = t.cross(N[i]).normalized()
        n = w.cross(t).normalized()
        ringp = []
        for k in range(8):
            a = 2 * pi * k / 8
            c, s = cos(a), sin(a)
            p = P[i] + w * (hw * abs(c) ** 0.8 * (1 if c >= 0 else -1)) \
                + n * (ht * abs(s) ** 0.8 * (1 if s >= 0 else -1))
            ringp.append((p.x, 0.0 if i == 0 else p.y, p.z))
        S.append(ringp)
    c = P[-1]
    S.append([tuple(YOKE_POLE + (V3(p) - c) * 0.25) for p in S[-1]])
    K.build_body(S, lambda i, j: "yoke", PMAT, 0.0, 0.0, name="yoke", front=None,
                 rear=dict(kind="flat", panel="yoke", crease=0.0), wrap=True, subdiv=3,
                 thick=0.004)
    return P, N


# ---------------------------------------------------------------------------------------
# things lying on the surface as built
# ---------------------------------------------------------------------------------------
def snap(p, tree=None):
    """The nearest surface point to p (of every body piece, or of tree) and its normal,
    turned toward p (give points a little outside the skin)."""
    if tree is None:
        if K._BVH[0] is None:
            K.body_bvh()
        tree = K._BVH[0]
    p = V3(p)
    loc, n, _, _ = tree.find_nearest(p)
    if (p - loc).length > 1e-5 and n.dot(p - loc) < 0:
        n = -n
    return loc, n


def spline(ctrl, n=12):
    """A smooth curve through the control points."""
    P = [V3(p) for p in ctrl]
    out = []
    for i in range(len(P) - 1):
        p0, p1, p2, p3 = P[max(i - 1, 0)], P[i], P[i + 1], P[min(i + 2, len(P) - 1)]
        for k in range(n):
            t = k / n
            out.append(0.5 * (2 * p1 + (p2 - p0) * t + (2 * p0 - 5 * p1 + 4 * p2 - p3) * t * t
                              + (3 * p1 - p0 - 3 * p2 + p3) * t ** 3))
    out.append(P[-1])
    return out


def strip(g, ctrl, w, lift=0.0026, sink=-0.0003, taper=(0.0, 0.0), n=12):
    """A band of width w lying on the surface along a curve near it, its ends drawn out to
    points over the taper lengths. It stays above the skin (a light under it would shine
    into the shell, which has no thickness)."""
    P, N = [], []
    for q in spline(ctrl, n):
        loc, nn = snap(q)
        if not P or (loc - P[-1]).length > 1e-4:
            P.append(loc)
            N.append(nn)
    s = [0.0]
    for a, b in zip(P, P[1:]):
        s.append(s[-1] + (b - a).length)
    vs = []
    for i in range(len(P)):
        t = (P[min(i + 1, len(P) - 1)] - P[max(i - 1, 0)]).normalized()
        sd = N[i].cross(t).normalized()
        k = 1.0
        if taper[0]:
            k = min(k, (s[i] / taper[0]) ** 0.6)
        if taper[1]:
            k = min(k, ((s[-1] - s[i]) / taper[1]) ** 0.6)
        h = w * max(k, 0.06) / 2
        vs += [P[i] - N[i] * sink + sd * h, P[i] + N[i] * lift + sd * h,
               P[i] + N[i] * lift - sd * h, P[i] - N[i] * sink - sd * h]
    m = len(P)
    faces = [(4 * i + j, 4 * i + (j + 1) % 4, 4 * i + 4 + (j + 1) % 4, 4 * i + 4 + j)
             for i in range(m - 1) for j in range(4)]
    faces += [(0, 1, 2, 3), tuple(4 * (m - 1) + j for j in range(4))]
    g.add(vs, faces)


def pebble(g, at, a, b, h, seg=40, up=(0, 0, 1)):
    """A low oval bead on the surface at the point nearest `at`: a wide, b high, h proud."""
    loc, n = snap(at)
    t1 = V3(up).cross(n).normalized()
    t2 = n.cross(t1)
    rings = [(1.0, -0.003), (1.0, 0.0), (0.95, h * 0.42), (0.80, h * 0.76), (0.52, h * 0.95),
             (0.2, h)]
    o = len(g.v)
    for r, z in rings:
        g.v += [loc + n * z + t1 * (a * r * cos(2 * pi * k / seg))
                + t2 * (b * r * sin(2 * pi * k / seg)) for k in range(seg)]
    for i in range(len(rings) - 1):
        g.f += [(o + i * seg + k, o + i * seg + (k + 1) % seg, o + (i + 1) * seg + (k + 1) % seg,
                 o + (i + 1) * seg + k) for k in range(seg)]
    g.f.append(tuple(o + (len(rings) - 1) * seg + k for k in range(seg)))


def both(half):
    """A left-side curve ending on the centerline, carried on round the right side."""
    half = [V3(p) for p in half]
    return half + [V3((p.x, -p.y, p.z)) for p in half[-2::-1]]


def mir(pts, sgn):
    return [V3((p[0], sgn * p[1], p[2])) for p in pts]


def text_proj(g, txt, size, u0, v0, proj, lift=0.0012, spacing=1.0):
    """Lettering on the body seen along proj (as carkit.on_body), reading left to right."""
    vs, fs = K.text_mesh(txt, size, spacing)
    sx = {'y': -1, 'Y': 1, 'x': 1, 'X': -1}[proj]
    out = []
    for p in vs:
        loc, n = on_body(u0 + sx * p.x, v0 + p.y, proj)
        if loc is None:
            return
        out.append(loc + n * lift)
    g.add(out, fs)


def dot_field(g, proj, u0, v0, hu, hv, pitch=0.0125, rmax=0.0044):
    """Perforations: a lens of dots that shrink toward its rim (seen along proj)."""
    rows = int(hv / (pitch * 0.866)) + 1
    for r in range(-rows, rows + 1):
        v = r * pitch * 0.866
        cols = int(hu / pitch) + 1
        for c in range(-cols, cols + 1):
            u = (c + (0.5 if r % 2 else 0.0)) * pitch
            f = 1.0 - (u / hu) ** 2 - (v / hv) ** 2
            if f <= 0.08:
                continue
            loc, n = on_body(u0 + u, v0 + v, proj)
            if loc is None:
                continue
            rad_ = rmax * min(1.0, f * 1.6) ** 0.5
            t = n.cross(V3((0, 0, 1)))
            t = t.normalized() if t.length > 1e-3 else V3((0, 1, 0))
            b = n.cross(t)
            o = len(g.v)
            g.v += [loc + n * 0.0009 + (t * cos(rad(a)) + b * sin(rad(a))) * rad_
                    for a in range(0, 360, 60)]
            g.f.append(tuple(range(o, o + 6)))


LENS = [(0.5 * cos(rad(a)), 0.5 * sin(rad(a)) * abs(sin(rad(a))) ** 0.3)
        for a in range(0, 360, 20)]


def lens(cx, th):
    """A lens section: chord cx across, th thick."""
    return [(cx * a, th * b) for a, b in LENS]


def build_blades():
    # ---- under the nose: the floor of the through-duct, from pod to pod
    g = Geo()
    path = [(2.06 - 0.10 * (y / 0.70) ** 2, y, 0.172 + 0.075 * (y / 0.70) ** 4)
            for y in (-0.70, -0.6, -0.4, -0.2, 0, 0.2, 0.4, 0.6, 0.70)]
    g.sweep(spline(path, 5), lens(0.30, 0.030), up=(0, 0, 1))
    ob = g.obj("blade.nose", "paint", sharp=50)
    # ---- across the three tails
    g = Geo()
    path = [(-2.262 + 0.02 * (y / 0.63) ** 2, y, 0.526) for y in
            (-0.63, -0.5, -0.3, -0.12, 0, 0.12, 0.3, 0.5, 0.63)]
    g.sweep(spline(path, 5), lens(0.12, 0.022), up=(0, 0, 1))
    g.obj("blade.tail", "paint", sharp=50)
    g = Geo()
    g.sweep(spline([(p[0] - 0.060, p[1], p[2]) for p in path], 5),
            [(-0.004, -0.0045), (0.004, -0.0045), (0.004, 0.0045), (-0.004, 0.0045)],
            up=(0, 0, 1))
    g.obj("led.tailblade", "led_rear")
    # ---- faired arms across each channel at the rear axle (the hips hang on them)
    g = Geo()
    for sgn in (1, -1):
        for x, z in ((RA_X + 0.14, 0.275), (RA_X - 0.14, 0.275), (RA_X, 0.50)):
            g.sweep(mir([(x, 0.26, z), (x, 0.45, z + 0.006), (x, 0.66, z)], sgn),
                    lens(0.085, 0.022), up=(0, 0, 1))
    g.obj("arms", "wheel_face", sharp=50)
    return ob


def build_lights(YP, YN):
    P = PT
    # ---- the nose ribbon traces the slots between the nose and the fenders: from behind a
    # front wheel over its lid, round the pod's tip, back up the slot, out along the nose
    half = [(0.60, .93, .50), (0.86, .99, .60), (1.12, 1.03, .668), (FA_X, 1.04, .682),
            (1.70, 1.03, .655), (1.95, 1.0, .56), (2.14, .96, .45), (2.27, .90, .37),
            (2.32, .80, .335), (2.27, .70, .355), (2.14, .625, .395), (1.95, .585, .425),
            (1.74, .575, .445), (1.60, .58, .452), (1.53, .575, .456), (1.50, .555, .46),
            (1.53, .53, .457), (1.62, .50, .455), (1.76, .455, .45), (1.95, .375, .44),
            (2.10, .32, .43), (2.24, .24, .42), (2.31, .14, .41),
            (NOSE.x + 0.01, 0, NOSE.z + 0.012)]
    g = Geo()
    strip(g, both(half), 0.016, taper=(0.45, 0.45), n=8)
    pebble(g, (NOSE.x + 0.05, 0, NOSE.z + 0.02), 0.040, 0.030, 0.008)
    g.obj("led.front", "led_front", sharp=50)
    # ---- the tail ribbon traces the channels: down each buttress from the roof, along the
    # hip's crest, round its tip, and across the tail blade to the pebble on the tail pole
    g = Geo()
    for sgn in (1, -1):
        crest = [YP[i] + YN[i] * 0.08 for i in range(2, len(YP))]
        crest += [V3((-1.90, .775, .90)), V3((-2.08, .745, .80)), V3((-2.22, .715, .70)),
                  V3((-2.32, .69, .61)), V3((-2.37, .675, .525)), V3((-2.34, .62, .52)),
                  V3((-2.30, .585, .525))]
        strip(g, mir(crest, sgn), 0.016, taper=(0.35, 0.0), n=8)
    pebble(g, (TAIL.x - 0.05, 0, TAIL.z + 0.02), 0.036, 0.030, 0.008)
    g.obj("led.rear", "led_rear", sharp=50)


def build_details():
    P = PT
    # ---- petal doors: hairlines over the glass on the door cuts, joined along the canopy
    g = Geo()
    for sgn in (1, -1):
        for st in ("D1", "D2"):
            strip(g, mir([P[st]["E"], P[st]["E"].lerp(P[st]["G"], 0.5), P[st]["G"]], sgn),
                  0.005, lift=0.0012, n=8)
        strip(g, mir([P[st]["G"] for st in ("D1", "M1", "D2")], sgn), 0.005, lift=0.0012, n=10)
    g.obj("glass.lines", "gloss_black", sharp=50)
    # ---- door pulls: a small crescent under each shoulder
    g = Geo()
    for sgn in (1, -1):
        strip(g, mir([(0.34, .80, .70), (0.27, .80, .71), (0.20, .80, .70)], sgn), 0.014,
              lift=0.0009, taper=(0.05, 0.05), n=6)
    g.obj("lines", "void", sharp=50)
    # ---- the charge port: a ring of light on the left hip's nose, a pebble in it
    g = Geo()
    strip(g, [(-0.42 + 0.04 * cos(rad(a)), 1.1, 0.50 + 0.04 * sin(rad(a)))
              for a in range(0, 361, 30)], 0.005, lift=0.0012, n=3)
    strip(g, [(-0.42 + 0.04 * cos(rad(a)), -1.1, 0.50 + 0.04 * sin(rad(a)))
              for a in range(0, 361, 30)], 0.005, lift=0.0012, n=3)
    g.obj("led.port", "led_accent", sharp=50)
    # ---- where it breathes: dot lenses on the pods' fronts and the hips' tails
    g = Geo()
    for sgn in (1, -1):
        dot_field(g, 'x', sgn * 0.80, 0.262, 0.15, 0.028, pitch=0.011, rmax=0.0038)
        dot_field(g, 'X', sgn * 0.705, 0.425, 0.12, 0.030, pitch=0.011, rmax=0.0038)
    g.obj("dots", "void")
    # ---- lettering: one small word each
    g = Geo()
    for side in (1, -1):
        text_proj(g, "aria", 0.034, 0.26, 0.335, 'y' if side > 0 else 'Y', spacing=1.3)
    K.text_on_body(g, "orrin", 0.026, -0.30, 0.0, 1, proj='z', turn=90, spacing=1.4)
    g.obj("lettering", "decal")
    # ---- camera pods where mirrors would be (on the fenders' tails), sensors on the nose
    g, gl = Geo(), Geo()
    for sgn in (1, -1):
        loc, n = snap((0.74, sgn * 1.0, 0.72))
        fwd = V3((1, 0, 0.05)).normalized()
        xf = (Matrix.Translation(loc + n * 0.006)
              @ V3((0, 1, 0)).rotation_difference(fwd).to_matrix().to_4x4())
        prof = [(-0.10 * cos(rad(a)), 0.024 * sin(rad(a)) ** 0.8 + 0.0005)
                for a in range(0, 181, 12)]
        g.lathe(prof, 24, xf=xf)
        gl.lathe([(-0.101, 0.001), (-0.101, 0.010), (-0.097, 0.012), (-0.097, 0.001)], 16, xf=xf)
        for y in (0.07, 0.13):
            loc, n = on_body(sgn * y, 0.372, 'x')
            if loc is not None:
                K.stud(gl, loc, n, [(-0.002, 0.001), (-0.002, 0.008), (0.0012, 0.008),
                                    (0.0012, 0.001)], 14)
    g.obj("cameras", "paint", sharp=40)
    gl.obj("camera.lens", "gloss_black")
    # ---- side markers: a short light dash low on each hip behind the wheel lid
    g = Geo()
    for sgn in (1, -1):
        strip(g, mir([(-1.84, 1.05, .47), (-1.93, 1.0, .475), (-2.02, .95, .48)], sgn),
              0.008, taper=(0.04, 0.04), n=6)
    g.obj("led.marker", "led_rear", sharp=50)


# ---------------------------------------------------------------------------------------
# interior: a liner under the long glass (nose deck, tub, tail deck), two seats of stones
# ---------------------------------------------------------------------------------------
def stone(g, c, r, rot=None, n=2.6, seg=32, rows=16):
    """A smooth stone: a superellipsoid at c with half sizes r, turned by rot (a matrix)."""
    e = 2.0 / n

    def pw(v):
        return (abs(v) ** e) * (1 if v >= 0 else -1)

    xf = Matrix.Translation(V3(c)) @ (rot.to_4x4() if rot is not None else Matrix.Identity(4))
    vs = [(0, 0, -r[2])]
    for i in range(1, rows):
        ph = -pi / 2 + pi * i / rows
        for k in range(seg):
            th = 2 * pi * k / seg
            vs.append((r[0] * pw(cos(ph)) * pw(cos(th)), r[1] * pw(cos(ph)) * pw(sin(th)),
                       r[2] * pw(sin(ph))))
    vs.append((0, 0, r[2]))
    fs = [(0, 1 + (k + 1) % seg, 1 + k) for k in range(seg)]
    for i in range(rows - 2):
        a, b = 1 + i * seg, 1 + (i + 1) * seg
        fs += [(a + k, a + (k + 1) % seg, b + (k + 1) % seg, b + k) for k in range(seg)]
    top, a = len(vs) - 1, 1 + (rows - 2) * seg
    fs += [(a + k, a + (k + 1) % seg, top) for k in range(seg)]
    g.add(vs, fs, xf=xf)


def rim_at(x, tree):
    """A point just under the paint below the glass edge at x: the liner's rim."""
    xs = [PT[k]["S"].x for k in ORDER]
    for a, b, xa, xb in zip(ORDER, ORDER[1:], xs, xs[1:]):
        if xb <= x <= xa:
            t = (xa - x) / (xa - xb)
            e = PT[a]["E"].lerp(PT[b]["E"], t)
            s = PT[a]["S"].lerp(PT[b]["S"], t)
            loc, n = snap(e.lerp(s, 0.35) + V3((0, 0.03, 0.03)), tree)
            return loc - n * 0.016
    raise ValueError(x)


def build_interior():
    tree = K.body_bvh(CORE, default=False)
    rows = [(2.26, None, .004), (2.10, None, .010), (1.75, None, .022), (FA_X, None, .034),
            (1.05, None, .045), (0.90, None, .05), (0.86, .17, 0), (0.80, .17, 0),
            (0.40, .17, 0), (0.0, .17, 0), (-0.38, .17, 0), (-0.46, .17, 0),
            (-0.50, None, .05), (-0.82, None, .04), (RA_X, None, .028), (-1.86, None, .014),
            (-2.20, None, .005)]
    S, rims = [], []
    for x, zf, drop in rows:
        rm = rim_at(x, tree)
        rims.append(rm)
        zf = rm.z - drop if zf is None else zf
        deep = rm.z - zf > 0.2
        S.append([tuple(rm), (rm.x, rm.y * 0.95, zf + (rm.z - zf) * 0.45),
                  (rm.x, rm.y * (0.82 if deep else 0.86), zf), (rm.x, 0.0, zf)])
    hold = {5: 0.6, 6: 0.75, 7: 0.5, 10: 0.5, 11: 0.75, 12: 0.6}
    K.build_body(S, lambda i, j: "liner", dict(liner="liner"), 0.0,
                 lambda i, j: hold.get(i, 0.0), name="liner", project=False, subdiv=3)
    # ---- a hair of light under the glass round both tongues, the word under the nose glass
    g = Geo()
    sec = [(-0.0025, -0.002), (0.0025, -0.002), (0.0025, 0.002), (-0.0025, 0.002)]
    for part in (rims[:6], rims[:-6:-1]):
        half = [V3((p.x, p.y - 0.012, p.z - 0.004)) for p in part[::-1]]
        tip = part[0]
        half.append(V3((tip.x + (0.004 if tip.x > 0 else -0.004), 0, tip.z - 0.006)))
        g.sweep(spline(both(half), 8), sec, up=(0, 0, 1))
    a, b = V3((rims[3].x, 0, rims[3].z - 0.030)), V3((rims[4].x, 0, rims[4].z - 0.041))
    text_flat(g, "orrin", 0.040, a.lerp(b, 0.5) + V3((0, 0, 0.012)), (0, 1, 0),
              (b - a).normalized(), spacing=1.5)
    g.obj("led.cabin", "led_accent")
    # ---- two seats, each three stones; a spine between them
    g, gi = Geo(), Geo()
    back = Matrix.Rotation(rad(-24), 3, 'Y')
    for y in (0.325, -0.325):
        stone(g, (0.14, y, 0.305), (0.26, 0.225, 0.07), Matrix.Rotation(rad(-9), 3, 'Y'), n=3.0)
        stone(g, (-0.215, y, 0.60), (0.070, 0.215, 0.30), back, n=3.0)
        stone(g, (-0.375, y, 0.935), (0.045, 0.105, 0.070), back, n=2.6)
        stone(gi, (0.10, y, 0.215), (0.20, 0.18, 0.05), n=3.0)
    g.obj("interior.seats", "seat", sharp=60)
    stone(gi, (0.86, 0, 0.705), (0.085, 0.56, 0.040), Matrix.Rotation(rad(14), 3, 'Y'), n=3.2)
    stone(gi, (0.25, 0, 0.27), (0.50, 0.060, 0.095), n=3.0)
    yoke = (Matrix.Translation((0.66, 0.325, 0.665)) @ Matrix.Rotation(rad(-66), 4, 'Y')
            @ Matrix.Rotation(pi / 2, 4, 'X'))
    gi.lathe([(-0.010, 0.140), (0.0, 0.150), (0.010, 0.140), (0.0, 0.130)], 28, xf=yoke)
    gi.tube((0.69, 0.325, 0.66), (0.80, 0.325, 0.69), 0.018)
    gi.obj("interior.fittings", "interior", sharp=60)
    g = Geo()
    stone(g, (0.775, 0, 0.705), (0.012, 0.46, 0.022), Matrix.Rotation(rad(14), 3, 'Y'), n=4)
    g.obj("interior.screen", "screen", sharp=60)


# ---------------------------------------------------------------------------------------
# wheels: the kit's tire round a smooth disc with a turbine of fine vanes and two light rings
# ---------------------------------------------------------------------------------------
def build_disc(tag, cx, W, out_y, side, vanes=60):
    K.build_wheel(tag, cx, R, W, RIM, out_y, side, style="disc", ring=None, caliper=None)
    for part in ("rim.", "hub."):
        ob = bpy.data.objects[part + tag]
        me = ob.data
        bpy.data.objects.remove(ob)
        bpy.data.meshes.remove(me)
    hw = W / 2
    flip = side < 0
    loc = (cx, side * (out_y - hw), R)
    r_in, r_out = 0.118, RIM - 0.026
    g = Geo()
    g.lathe([(-hw + 0.03, RIM), (hw - 0.006, RIM), (hw - 0.004, RIM - 0.007),
             (hw - 0.012, RIM - 0.017), (hw - 0.036, RIM - 0.022), (hw - 0.038, r_in - 0.004),
             (hw - 0.014, 0.102), (hw - 0.008, 0.072), (hw - 0.004, 0.040), (hw - 0.003, 0.004),
             (hw - 0.08, 0.004), (hw - 0.08, RIM - 0.03), (-hw + 0.03, RIM - 0.02)], 96)
    g.obj("rim." + tag, "wheel_face", flip_y=flip, loc=loc, sharp=35)
    g = Geo()
    for k in range(vanes):
        a0 = 2 * pi * k / vanes
        path = []
        for q in range(6):
            f = q / 5
            a = a0 + rad(40) * f ** 1.3
            r = r_in + (r_out - r_in) * f
            path.append((r * cos(a), hw - 0.026 + 0.004 * f, r * sin(a)))
        g.sweep(path, [(-0.0016, -0.010), (0.0016, -0.010), (0.0016, 0.010), (-0.0016, 0.010)],
                up=(0, 1, 0))
    g.lathe([(hw - 0.0025, 0.026), (hw - 0.0025, 0.035), (hw - 0.0005, 0.035),
             (hw - 0.0005, 0.026)], 40)
    g.obj("vanes." + tag, "wheel_vane", flip_y=flip, loc=loc, sharp=40)
    g = Geo()
    g.lathe([(hw - 0.0375, r_out - 0.012), (hw - 0.0375, r_out + 0.003),
             (hw - 0.033, r_out + 0.003), (hw - 0.033, r_out - 0.012)], 96)
    g.lathe([(hw - 0.0375, r_in - 0.003), (hw - 0.0375, r_in + 0.008),
             (hw - 0.033, r_in + 0.008), (hw - 0.033, r_in - 0.003)], 64)
    g.obj("ring." + tag, "led_wheel", flip_y=flip, loc=loc)


# ---------------------------------------------------------------------------------------
# views of its own, and the build
# ---------------------------------------------------------------------------------------
K.VIEWS["hero"].update(dir=(1.0, 0.80, 0.40), focus=(1.4, 0.8, 0.5))
K.VIEWS["rear"].update(dir=(-1.0, -0.62, 0.42))
K.VIEWS.update(
    quarter=dict(dir=(-1.0, 0.55, 0.50), lens=70),
    nose=dict(dir=(1.0, 0.35, 0.35), lens=85, target=(2.0, 0.3, 0.42), dist=2.6),
    tail=dict(dir=(-1.0, 0.5, 0.45), lens=85, target=(-1.7, 0.4, 0.6), dist=3.2),
    channel=dict(dir=(0.5, 1.0, 0.7), lens=85, target=(-0.9, 0.6, 0.8), dist=3.2),
)


def second_tile(view="top", size=(1000, 470)):
    """A sixth tile on the sheet, in the hero's bottom right corner: the kit lays one extra
    tile only, and this car wants the rear three-quarter and the plan both."""
    sheet = os.path.join(K.ARGS.out, "sheet.jpg")
    if not K.ARGS.sheet or not os.path.exists(sheet):
        return
    tmp = os.path.join(K.ARGS.out, "x_%s.jpg" % view)
    K.render_view(view, tmp, size, K.ARGS.samples or 160, 0.05)
    k, th = (0.9, 0.8) if K.ARGS.night else (0.45, 0.86)
    code = ("import sys; sys.path.insert(0, sys.argv[1]); import post; from PIL import Image; "
            "s = Image.open(sys.argv[2]).convert('RGB'); "
            "q = post.bloomed(Image.open(sys.argv[3]).convert('RGB'), %r, %r); "
            "x, y = s.width - q.width, %d - q.height; "
            "s.paste((14, 14, 16), (x - 4, y - 4, s.width, %d)); s.paste(q, (x, y)); "
            "s.save(sys.argv[2], quality=93)" % (k, th, K.SHEET_TOP, K.SHEET_TOP))
    subprocess.run([K._python(), "-c", code, K.HERE, sheet, tmp], check=True)
    os.remove(tmp)
    K.log("laid %s into the sheet" % view)


def main():
    K.materials(paint=(0.010, 0.010, 0.012), paint_finish=(0.80, 0.30, 0.9), dust_amount=0.06,
                glass=(0.60, 0.56, 0.50), led_front=(0.90, 0.95, 1.0),
                led_rear=(1.0, 0.035, 0.03), led_accent=(0.30, 0.82, 1.0),
                led_wheel=(0.30, 0.82, 1.0), seat=(0.42, 0.17, 0.06),
                interior=(0.030, 0.030, 0.032), screen=(0.30, 0.82, 1.0))
    K.pbr("wheel_face", (0.19, 0.195, 0.20), 1.0, 0.30)
    K.pbr("wheel_vane", (0.24, 0.245, 0.25), 1.0, 0.26)
    K.emit("led_rear", (1.0, 0.004, 0.002), 7.0)        # deeper than the kit's: a real red
    # the canopy's glass with a coating: the kit's glass mirrors the studio all over a dome
    K.pbr("glass_dome", (0.60, 0.56, 0.50), 0.0, 0.0,
          **{"Transmission Weight": 1.0, "IOR": 1.14})
    K.pbr("liner", (0.012, 0.012, 0.014), 0.0, 0.24)   # dark and glossy under the glass
    build_hull()
    YP, YN = build_yoke()
    K.log("hull")
    build_blades()
    build_lights(YP, YN)
    build_details()
    build_interior()
    K.log("details")
    for side, s in ((1, "l"), (-1, "r")):
        build_disc("f" + s, FA_X, F_W, F_OUT, side)
        build_disc("r" + s, RA_X, R_W, R_OUT, side)
    K.log("wheels")
    K.shoot(extra=dict(view="quarter", size=(1040, 585), corner="tl"))
    second_tile()


main()
