"""Orrin Pebble: a two-seat city pod, a river stone held in four soft paws (both names made
up), built on vehicles/carkit.py. The Lumen's little sibling.

Run (always through the wrapper, one Blender job at a time on this machine):
    vehicles/blender.sh vehicles/cars/orrin_pebble.py --out DIR --preview
    vehicles/blender.sh vehicles/cars/orrin_pebble.py --out DIR --sheet [--night]

The body is nine lines over eleven ring stations with no crease anywhere. As on the Lumen the
rings close on a small pole at the nose and at the tail, and the three lines nearest the top
are the glass: one dome leaf from pole to pole. Here the glass edge dips low at the doors and
the four fenders rise round it, so the stone sits in them like a gem in its claws. The dome
forward of the hinge ring (over the rear axle) lifts as the door; the glass behind it is
fixed over the luggage shelf. One light ribbon runs all the way round the waist, white ahead
of the flank pebbles and red behind, swelling into a lit pebble on each pole and on each
flank (the left one is the charge port). The view "open" (the sheet's fifth tile) renders
with the leaf lifted about its hinge. PEBBLE_PROBE=1 builds the bare hull and prints the
skin's position round the wheels (room for tires and cavities).
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import bpy                                                          # noqa: E402
import carkit as K                                                  # noqa: E402
from carkit import Geo, Matrix, V3, cos, on_body, pi, rad, sin, stud, text_flat   # noqa: E402

PROBE = bool(os.environ.get("PEBBLE_PROBE"))

# ---------------------------------------------------------------------------------------
# dimensions
# ---------------------------------------------------------------------------------------
FA_X, RA_X = 0.90, -0.88            # axles: wheelbase 1.78
R, W, RIM = 0.295, 0.185, 0.232     # tire radius, width, rim radius
OUT = 0.660                         # outer face of the tires
CAV = 0.320                         # wheel cavity radius
F_LID, R_LID = 0.350, 0.335         # top of the wheel openings: the body lids the wheels
NOSE = V3((1.40, 0, 0.55))          # the poles the rings close on
TAIL = V3((-1.40, 0, 0.60))
FLANK = (-0.30, 0.558)              # where white turns red: the flank pebbles (x, z)

# ---------------------------------------------------------------------------------------
# body: stations (rings) and lines
# ---------------------------------------------------------------------------------------
LINES = "CGKESULRB"
#        C top centerline, G dome crown, K dome side, E glass edge, S fender shoulder,
#        U widest (the ribbon), L lower flank, R rocker, B floor centerline
ORDER = ["P0", "N1", "N2", "FA", "D1", "M", "D2", "RA", "T2", "T1", "T0"]
PT = {}


def ring(x, c, g, k, e, s, u, lo, r, b):
    """A station at one x (or one x per line): z of C, (y, z) of the others, z of B."""
    xs = x if isinstance(x, (list, tuple)) else [x] * 9
    pts = [(0.0, c), g, k, e, s, u, lo, r, (0.0, b)]
    return [(xs[i], p[0], p[1]) for i, p in enumerate(pts)]


def stations():
    T = {
        "N1": [(1.37, 0, .70), (1.369, .08, .698), (1.367, .17, .69), (1.363, .26, .675),
               (1.35, .39, .635), (1.34, .46, .55), (1.358, .46, .44), (1.368, .30, .378),
               (1.370, 0, .365)],
        "N2": [(1.25, 0, .915), (1.247, .18, .907), (1.24, .35, .878), (1.23, .47, .84),
               (1.205, .665, .755), (1.19, .765, .555), (1.232, .775, .34), (1.258, .64, .215),
               (1.265, 0, .20)],
        # over the wheels the fenders rise beside the glass (the paws) and the flank comes
        # straight down round the tires
        "FA": ring(FA_X, 1.235, (.33, 1.205), (.555, 1.065), (.625, .955), (.755, .86),
                   (.815, .565), (.80, .30), (.70, .15), .145),
        # the two petal cuts fan: forward at the top, back at the top; between them the
        # glass edge dips to the waist, the low sill you step over
        "D1": ring((.46, .46, .46, .45, .43, .40, .36, .345, .345), 1.46, (.39, 1.42),
                   (.675, 1.09), (.75, .77), (.79, .69), (.80, .56), (.78, .30),
                   (.66, .15), .14),
        "M": ring(0.0, 1.548, (.42, 1.498), (.715, 1.115), (.78, .68), (.795, .628),
                  (.80, .555), (.775, .295), (.65, .15), .14),
        "D2": ring((-.46, -.46, -.46, -.45, -.43, -.40, -.36, -.345, -.345), 1.495,
                   (.40, 1.455), (.685, 1.105), (.75, .78), (.79, .695), (.80, .565),
                   (.78, .305), (.66, .15), .14),
        "RA": ring(RA_X, 1.29, (.35, 1.255), (.57, 1.09), (.625, .975), (.755, .875),
                   (.815, .575), (.80, .305), (.70, .155), .15),
        "T2": [(-1.25, 0, .97), (-1.247, .19, .96), (-1.24, .36, .93),
               (-1.23, .47, .885), (-1.205, .675, .785), (-1.19, .775, .585),
               (-1.232, .785, .365), (-1.258, .65, .24), (-1.265, 0, .225)],
        "T1": [(-1.37, 0, .75), (-1.369, .08, .748), (-1.367, .17, .74), (-1.363, .26, .725),
               (-1.35, .39, .685), (-1.34, .46, .60), (-1.358, .46, .49),
               (-1.368, .30, .428), (-1.370, 0, .415)],
    }
    for name, src, pole in (("P0", "N1", NOSE), ("T0", "T1", TAIL)):
        T[name] = [(pole.x, p[1] * 0.22, pole.z + (p[2] - pole.z) * 0.22) for p in T[src]]
    S = K.fill([T[k] for k in ORDER])
    PT.update(K.table(ORDER, LINES, S))
    return S


PMAT = dict(front="paint", petal="paint", rear="paint", glass="glass_dome", glass_t="glass_dome",
            floor="underbody", well="well", slot="void")


def panel_of(i, j):
    if j == 7 and 2 <= i <= 7:           # the belly is painted where it turns up at both ends
        return "floor"
    if j <= 2:                           # the dome: the leaf that lifts, and the fixed tail
        return "glass" if i <= 6 else "glass_t"
    if i <= 3:
        return "front"
    return "petal" if i <= 5 else "rear"


def lid_cutter(g, cx, top, a=0.322, z0=0.27, n=2.6, y0=0.648, depth=0.4):
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
        rim = [V3((p.x, sgn * p.y, p.z)) for p in hi + lo[::-1]]      # lo[k] sits at 2n - k
        rim2 = [V3((p.x, sgn * p.y, p.z)) for p in hi2 + lo2[::-1]]
        m = 2 * n
        faces = [(k, (k + 1) % m, m + (k + 1) % m, m + k) for k in range(m)]
        for o in (0, m):                    # caps as a strip of quads between the two edges
            faces.append((o, o + 1, o + m - 1))
            faces += [(o + k, o + k + 1, o + m - k - 1, o + m - k) for k in range(1, n - 1)]
            faces.append((o + n - 1, o + n, o + n + 1))
        g.add([p + dd * out for p in rim] + [p - dd * depth for p in rim2], faces)


def build_hull():
    ang = list(range(-25, 206, 10))
    cav, cav2, lids, slots = Geo(), Geo(), Geo(), Geo()
    for cx, top in ((FA_X, F_LID), (RA_X, R_LID)):
        K.well_cutter(cav, cx, R, CAV, 0.45, ang, depth=0.155)
        K.well_cutter(cav2, cx, R, R + 0.008, 0.60, ang, depth=OUT + 0.004 - 0.60)
        lid_cutter(lids, cx, top)
    # crescents: a pair under the ribbon at each end, and one beside each wheel lid, facing
    # each other across the petal like a pair of brackets
    lune(slots, (1.378, .15, .470), (1.298, .50, .460), (0.80, 0.55, -0.30), (0, 0, -1),
         0.040, 0.019, depth=0.04, flare=0.012)
    lune(slots, (-1.378, .15, .520), (-1.298, .50, .510), (-0.80, 0.55, -0.30), (0, 0, -1),
         0.040, 0.019, depth=0.04, flare=0.012)
    for cx, sx in ((FA_X, 1), (RA_X, -1)):
        xe = cx - sx * 0.322                # the lid's edge toward the middle
        lune(slots, (xe - sx * 0.052, .690, .25), (xe - sx * 0.028, .792, .48), (0, 1, -0.2),
             (-sx, 0, 0), 0.040, 0.018, depth=0.05, flare=0.016)
    # the grab recess: a crescent under the glass where it dips lowest, to lift the leaf by
    lune(slots, (0.30, .792, .636), (0.06, .792, .630), (0, 1, 0.12), (0, 0, -1), 0.024, 0.007,
         depth=0.035, flare=0.010)
    cutters = [(cav, "well"), (cav2, "well"), (lids, "well"), (slots, "slot")]
    if PROBE:
        cutters = []
    K.build_body(stations(), panel_of, PMAT, 0.0, 0.0,
                 front=dict(kind="flat", panel="front", crease=0.0),
                 rear=dict(kind="flat", panel="rear", crease=0.0),
                 cutters=cutters, subdiv=4, thick=0.003)


def probe():
    """PEBBLE_PROBE=1: the skin where the tires and the wheel cavities need room."""
    for cx in (FA_X, RA_X):
        for dx in (-0.31, -0.29, -0.25, 0.0, 0.25, 0.29, 0.31):
            row = []
            for z in (0.20, 0.25, 0.30, 0.35, 0.40, 0.45, 0.50, 0.60):
                loc, _ = on_body(cx + dx, z, 'y')
                row.append("%.3f" % loc.y if loc else " none")
            print("skin y at x %+.2f (tire face %.3f): %s" % (cx + dx, OUT, " ".join(row)))
        row = []
        for y in (0.45, 0.55, 0.62, 0.68):
            loc, _ = on_body(cx, y, 'z')
            row.append("%.3f" % loc.z)
        print("skin z over the axle at x %.2f: %s" % (cx, " ".join(row)))
    for x in (0.54, 0.3, 0.0, -0.3, -0.54):
        row = []
        for z in (0.25, 0.32, 0.48, 0.56, 0.64, 0.70, 0.76):
            loc, _ = on_body(x, z, 'y')
            row.append("%.3f" % loc.y if loc else " none")
        print("flank y at x %+.2f: %s" % (x, " ".join(row)))
    for y in (0.0, 0.15, 0.3, 0.5):
        row = []
        for z in (0.40, 0.45, 0.50, 0.55, 0.62, 0.70):
            loc, _ = on_body(y, z, 'x')
            row.append("%.3f" % loc.x if loc else " none")
        print("nose x at y %.2f: %s" % (y, " ".join(row)))
    for st in ORDER[1:-1]:
        print("glass edge near %s: %s" % (st, tuple(round(c, 3) for c in snap(PT[st]["E"])[0])))


# ---------------------------------------------------------------------------------------
# things lying on the surface as built
# ---------------------------------------------------------------------------------------
def snap(p):
    """The body's nearest surface point to p and its outward normal."""
    if K._BVH[0] is None:
        K.body_bvh()
    loc, n, _, _ = K._BVH[0].find_nearest(V3(p))
    if n.dot(loc - V3((max(-0.8, min(0.8, loc.x)), 0, 0.7))) < 0:
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


def build_lights():
    P = PT
    fx, fz = FLANK
    # one ribbon round the waist on the widest line: white from one flank pebble round the
    # nose to the other, red from there round the tail
    half = [(fx, .80, fz), (0.10, .80, .556), (0.50, .80, .558), (FA_X, .81, .563),
            P["N2"]["U"], P["N1"]["U"], (NOSE.x, 0, NOSE.z + 0.012)]
    g = Geo()
    strip(g, both(half), 0.017)
    pebble(g, (NOSE.x + 0.05, 0, NOSE.z + 0.030), 0.066, 0.043, 0.011)
    g.obj("led.front", "led_front", sharp=50)
    half = [(fx, .80, fz), (-0.60, .80, .566), (RA_X, .81, .575), P["T2"]["U"], P["T1"]["U"],
            (TAIL.x, 0, TAIL.z + 0.012)]
    g = Geo()
    strip(g, both(half), 0.017)
    pebble(g, (TAIL.x - 0.05, 0, TAIL.z + 0.030), 0.066, 0.043, 0.011)
    g.obj("led.rear", "led_rear", sharp=50)
    # the flank pebbles, where white turns red: the left one is the charge port
    g = Geo()
    for sgn in (1, -1):
        pebble(g, (fx, sgn * 0.85, fz), 0.050, 0.031, 0.011)
    g.obj("led.flank", "led_flank", sharp=50)


def build_details():
    P = PT
    # ---- the hinge of the leaf: a hairline over the glass on the hinge ring, two knuckles
    g = Geo()
    half = [P["RA"][k] for k in "ESKGC"][1:]
    half = [P["RA"]["E"].lerp(P["RA"]["K"], 0.08)] + half[1:]
    strip(g, both(half), 0.007, lift=0.0014, n=10)
    g.obj("glass.hinge", "gloss_black", sharp=50)
    g = Geo()
    for sgn in (1, -1):
        c = P["RA"]["C"].lerp(P["RA"]["G"], 0.62)
        pebble(g, (c.x, sgn * c.y, c.z), 0.036, 0.015, 0.008, up=(0, 1, 0))
    g.obj("hinge", "wheel_vane", sharp=50)
    # ---- the charge port's flap: a hairline ring round the left flank pebble
    fx, fz = FLANK
    g = Geo()
    strip(g, [(fx + 0.082 * cos(rad(a)), 0.85, fz + 0.060 * sin(rad(a)))
              for a in range(0, 361, 20)], 0.0035, lift=0.0010, n=3)
    g.obj("lines", "void", sharp=50)
    # ---- where it breathes: dot fields under both poles
    g = Geo()
    dot_field(g, 'x', 0.0, 0.468, 0.115, 0.030)
    dot_field(g, 'X', 0.0, 0.518, 0.115, 0.030)
    for sgn in (1, -1):                     # and a small lens on each rear paw, over the motors
        dot_field(g, 'z', -0.80, sgn * 0.705, 0.085, 0.030, pitch=0.011, rmax=0.0038)
    g.obj("dots", "void")
    # ---- lettering: one small word each
    g = Geo()
    for side in (1, -1):
        text_proj(g, "pebble", 0.030, 0.0, 0.335, 'y' if side > 0 else 'Y', spacing=1.3)
    text_proj(g, "orrin", 0.026, 0.0, 0.452, 'X', spacing=1.4)
    g.obj("lettering", "decal")
    # ---- camera pods on the front paws, sensors round both ends
    g = Geo()
    gl = Geo()
    for sgn in (1, -1):
        loc, n = snap((0.60, sgn * 0.80, 0.76))
        fwd = V3((1, 0, 0.10)).normalized()
        xf = (Matrix.Translation(loc + n * 0.004)
              @ V3((0, 1, 0)).rotation_difference(fwd).to_matrix().to_4x4())
        prof = [(-0.075 * cos(rad(a)), 0.021 * sin(rad(a)) ** 0.8 + 0.0005)
                for a in range(0, 181, 12)]
        g.lathe(prof, 24, xf=xf)
        gl.lathe([(-0.076, 0.001), (-0.076, 0.009), (-0.072, 0.011), (-0.072, 0.001)], 16,
                 xf=xf)
    g.obj("cameras", "paint", sharp=40)
    gl.obj("camera.lens", "gloss_black")
    g = Geo()
    for y, z, proj in ((0.26, 0.50, 'x'), (-0.26, 0.50, 'x'), (0.26, 0.552, 'X'),
                       (-0.26, 0.552, 'X')):
        loc, n = on_body(y, z, proj)
        if loc is not None:
            stud(g, loc, n, [(-0.002, 0.001), (-0.002, 0.009), (0.0012, 0.009),
                             (0.0012, 0.001)], 14)
    g.obj("sensors", "gloss_black")


# ---------------------------------------------------------------------------------------
# interior: a liner under the dome (nose deck, tub, luggage shelf), two seats of stones
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


def rim_at(x):
    """A point just under the paint below the glass edge at x: the liner's rim."""
    xs = [PT[k]["U"].x for k in ORDER]
    for a, b, xa, xb in zip(ORDER, ORDER[1:], xs, xs[1:]):
        if xb <= x <= xa:
            t = (xa - x) / (xa - xb)
            e = PT[a]["E"].lerp(PT[b]["E"], t)
            s = PT[a]["S"].lerp(PT[b]["S"], t)
            loc, n = snap(e.lerp(s, 0.4))
            return loc - n * 0.018
    raise ValueError(x)


def build_interior():
    # the liner: rows of (x, floor height); None follows the glass edge (a deck under it)
    rows = [(1.385, None, .006), (1.31, None, .012), (1.16, None, .03), (FA_X, None, .045), (0.64, .80, 0),
            (0.56, .80, 0), (0.53, .225, 0), (0.30, .225, 0), (0.0, .225, 0), (-0.30, .225, 0),
            (-0.52, .225, 0), (-0.555, .735, 0), (-0.70, .74, 0), (RA_X, None, .12),
            (-1.16, None, .045), (-1.31, None, .012), (-1.385, None, .006)]
    S, rims = [], []
    for x, zf, drop in rows:
        rm = rim_at(x)
        rims.append(rm)
        zf = rm.z - drop if zf is None else zf
        deep = rm.z - zf > 0.2
        S.append([tuple(rm), (rm.x, rm.y * 0.95, zf + (rm.z - zf) * 0.45),
                  (rm.x, rm.y * (0.80 if deep else 0.86), zf), (rm.x, 0.0, zf)])
    hold = {4: 0.5, 5: 0.75, 6: 0.75, 10: 0.75, 11: 0.75, 12: 0.4}
    K.build_body(S, lambda i, j: "liner", dict(liner="interior"), 0.0,
                 lambda i, j: hold.get(i, 0.0), name="liner", project=False, subdiv=3)
    # ---- a hair of light under the glass, round both tongues of the dome
    g = Geo()
    sec = [(-0.0025, -0.002), (0.0025, -0.002), (0.0025, 0.002), (-0.0025, 0.002)]
    for part in (rims[:4], rims[:-5:-1]):
        half = [V3((p.x, p.y - 0.012, p.z - 0.004)) for p in part[::-1]]
        tip = part[0]
        half.append(V3((tip.x + (0.004 if tip.x > 0 else -0.004), 0, tip.z - 0.006)))
        g.sweep(spline(both(half), 8), sec, up=(0, 0, 1))
    a, b = V3((rims[2].x, 0, rims[2].z - 0.03)), V3((rims[3].x, 0, rims[3].z - 0.045))
    up = (b - a).normalized()
    text_flat(g, "orrin", 0.036, a.lerp(b, 0.42) + V3((0, 0, 0.022)), (0, 1, 0), up,
              spacing=1.5)
    g.obj("led.cabin", "led_accent")
    # ---- two seats, each three stones on a foot
    g, gi = Geo(), Geo()
    back = Matrix.Rotation(rad(-15), 3, 'Y')
    for y in (0.345, -0.345):
        stone(g, (-0.07, y, 0.415), (0.255, 0.265, 0.085), Matrix.Rotation(rad(-6), 3, 'Y'),
              n=3.0)
        stone(g, (-0.375, y, 0.76), (0.075, 0.245, 0.30), back, n=3.0)
        stone(g, (-0.455, y, 1.105), (0.050, 0.115, 0.078), back, n=2.6)
        stone(gi, (-0.10, y, 0.285), (0.19, 0.20, 0.07), n=3.0)
    g.obj("interior.seats", "seat", sharp=60)
    # ---- dash: one long stone, a screen let into it, a yoke
    stone(gi, (0.615, 0, 0.815), (0.085, 0.60, 0.042), Matrix.Rotation(rad(12), 3, 'Y'), n=3.2)
    stone(gi, (-0.02, 0, 0.30), (0.26, 0.055, 0.085), n=3.0)             # the tunnel between
    yoke = (Matrix.Translation((0.47, 0.345, 0.80)) @ Matrix.Rotation(rad(-66), 4, 'Y')
            @ Matrix.Rotation(pi / 2, 4, 'X'))
    gi.lathe([(-0.010, 0.140), (0.0, 0.150), (0.010, 0.140), (0.0, 0.130)], 28, xf=yoke)
    gi.tube((0.50, 0.345, 0.79), (0.60, 0.345, 0.81), 0.018)
    gi.obj("interior.fittings", "interior", sharp=60)
    g = Geo()
    stone(g, (0.535, 0, 0.822), (0.012, 0.50, 0.024), Matrix.Rotation(rad(12), 3, 'Y'), n=4)
    g.obj("interior.screen", "screen", sharp=60)
    # ---- the luggage shelf behind the seats: a case and a soft bag, strapped, and a rail
    g, gs = Geo(), Geo()
    stone(g, (-0.86, 0.17, 0.865), (0.20, 0.235, 0.115), Matrix.Rotation(rad(4), 3, 'Z'), n=5)
    for dx in (-0.09, 0.09):
        stone(gs, (-0.86 + dx, 0.17, 0.865), (0.014, 0.239, 0.119),
              Matrix.Rotation(rad(4), 3, 'Z'), n=5)
    g.obj("luggage.case", "luggage", sharp=60)
    g = Geo()
    stone(g, (-0.83, -0.24, 0.835), (0.16, 0.15, 0.09), Matrix.Rotation(rad(-12), 3, 'Z'), n=2.3)
    g.obj("luggage.bag", "luggage2", sharp=60)
    stone(gs, (-0.83, -0.24, 0.84), (0.012, 0.153, 0.092), Matrix.Rotation(rad(-12), 3, 'Z'),
          n=2.3)
    gs.obj("luggage.straps", "interior", sharp=60)
    g = Geo()
    rail = [(-0.60, y, 0.775 + 0.035 * (1 - (y / 0.56) ** 2)) for y in
            (-0.56, -0.42, -0.2, 0, 0.2, 0.42, 0.56)]
    g.sweep(spline(rail, 6), [(0.007 * cos(rad(a)), 0.007 * sin(rad(a)))
                              for a in range(0, 360, 45)], up=(0, 0, 1))
    g.obj("luggage.rail", "wheel_vane", sharp=60)


# ---------------------------------------------------------------------------------------
# wheels: the kit's tire round a smooth disc with a turbine of fine vanes and two light rings
# ---------------------------------------------------------------------------------------
def build_disc(tag, cx, out_y, side, vanes=44):
    K.build_wheel(tag, cx, R, W, RIM, out_y, side, style="disc", ring=None, caliper=None)
    for part in ("rim.", "hub."):
        ob = bpy.data.objects[part + tag]
        me = ob.data
        bpy.data.objects.remove(ob)
        bpy.data.meshes.remove(me)
    hw = W / 2
    flip = side < 0
    loc = (cx, side * (out_y - hw), R)
    r_in, r_out = 0.108, RIM - 0.022
    g = Geo()
    g.lathe([(-hw + 0.03, RIM), (hw - 0.006, RIM), (hw - 0.004, RIM - 0.006),
             (hw - 0.011, RIM - 0.014), (hw - 0.032, RIM - 0.018), (hw - 0.034, r_in - 0.004),
             (hw - 0.013, 0.094), (hw - 0.008, 0.066), (hw - 0.004, 0.035), (hw - 0.003, 0.004),
             (hw - 0.07, 0.004), (hw - 0.07, RIM - 0.026), (-hw + 0.03, RIM - 0.018)], 96)
    g.obj("rim." + tag, "wheel_face", flip_y=flip, loc=loc, sharp=35)
    g = Geo()
    for k in range(vanes):
        a0 = 2 * pi * k / vanes
        path = []
        for q in range(6):
            f = q / 5
            a = a0 + rad(34) * f ** 1.3
            r = r_in + (r_out - r_in) * f
            path.append((r * cos(a), hw - 0.023 + 0.004 * f, r * sin(a)))
        g.sweep(path, [(-0.0014, -0.009), (0.0014, -0.009), (0.0014, 0.009), (-0.0014, 0.009)],
                up=(0, 1, 0))
    g.lathe([(hw - 0.0025, 0.024), (hw - 0.0025, 0.032), (hw - 0.0005, 0.032),
             (hw - 0.0005, 0.024)], 40)
    g.obj("vanes." + tag, "wheel_vane", flip_y=flip, loc=loc, sharp=40)
    g = Geo()
    g.lathe([(hw - 0.0335, r_out - 0.010), (hw - 0.0335, r_out + 0.003),
             (hw - 0.029, r_out + 0.003), (hw - 0.029, r_out - 0.010)], 96)
    g.lathe([(hw - 0.0335, r_in - 0.003), (hw - 0.0335, r_in + 0.007),
             (hw - 0.029, r_in + 0.007), (hw - 0.029, r_in - 0.003)], 64)
    g.obj("ring." + tag, "led_wheel", flip_y=flip, loc=loc)


# ---------------------------------------------------------------------------------------
# views of its own, and the build
# ---------------------------------------------------------------------------------------
K.VIEWS["hero"].update(dir=(1.0, 1.1, 0.30), focus=(0.9, 0.8, 0.5))
K.VIEWS.update(
    # the leaf lifted (render_view below turns it about its hinge for this view alone)
    open=dict(dir=(1.0, 1.35, 0.20), lens=70, target=(0.2, 0, 1.08), dist=8.4),
    nose=dict(dir=(1.0, 0.4, 0.4), lens=85, target=(1.2, 0.1, 0.55), dist=2.2),
    tail=dict(dir=(-1.0, -0.5, 0.45), lens=85, target=(-1.0, -0.1, 0.8), dist=2.6),
    wheel=dict(dir=(0.45, 1.0, 0.10), lens=85, target=(FA_X, 0.7, 0.36), dist=2.0),
    cabin=dict(dir=(0.3, 1.0, 0.75), lens=85, target=(-0.1, 0.1, 0.8), dist=3.4),
    flank=dict(dir=(0.1, 1.0, 0.15), lens=85, target=(-0.1, 0.8, 0.55), dist=2.0),
)


LEAF_UP = 34.0                      # degrees the leaf lifts in the "open" view
_render_view = K.render_view


def render_view(name, path, res, samples, margin=None):
    """The kit's render_view; for the view "open" the leaf is lifted about its hinge."""
    leaf = bpy.data.objects.get("body.glass") if name == "open" else None
    if leaf is not None:
        h, _ = snap(PT["RA"]["C"])
        leaf.matrix_world = (Matrix.Translation(h) @ Matrix.Rotation(rad(-LEAF_UP), 4, 'Y')
                             @ Matrix.Translation(-h))
    _render_view(name, path, res, samples, margin)
    if leaf is not None:
        leaf.matrix_world = Matrix.Identity(4)


K.render_view = render_view


def main():
    K.materials(paint=(0.105, 0.030, 0.205), paint_finish=(0.72, 0.36, 0.7), dust_amount=0.10,
                glass=(0.56, 0.54, 0.58), led_front=(0.90, 0.95, 1.0),
                led_rear=(1.0, 0.035, 0.03), led_accent=(1.0, 0.56, 0.16),
                led_wheel=(1.0, 0.56, 0.16), seat=(0.50, 0.42, 0.31),
                interior=(0.034, 0.030, 0.036), screen=(1.0, 0.62, 0.25))
    K.pbr("wheel_face", (0.19, 0.195, 0.20), 1.0, 0.30)
    K.pbr("wheel_vane", (0.24, 0.245, 0.25), 1.0, 0.26)
    K.emit("led_rear", (1.0, 0.004, 0.002), 7.0)        # deeper than the kit's: a real red
    K.emit("led_flank", (1.0, 0.36, 0.04), 10.0)
    # the dome's glass with a coating: the kit's glass mirrors the studio all over a dome
    K.pbr("glass_dome", (0.56, 0.54, 0.58), 0.0, 0.0,
          **{"Transmission Weight": 1.0, "IOR": 1.14})
    K.pbr("luggage", (0.36, 0.17, 0.05), 0.0, 0.55)
    K.pbr("luggage2", (0.16, 0.19, 0.17), 0.0, 0.75)
    build_hull()
    K.log("hull")
    if PROBE:
        probe()
        K.shoot()
        return
    build_lights()
    build_details()
    build_interior()
    K.log("details")
    for side, s in ((1, "l"), (-1, "r")):
        build_disc("f" + s, FA_X, OUT, side)
        build_disc("r" + s, RA_X, OUT, side)
    K.log("wheels")
    K.shoot(extra=dict(view="open", size=(900, 560), corner="tl"))


main()
