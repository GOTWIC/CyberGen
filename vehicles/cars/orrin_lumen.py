"""Orrin Lumen: a four-seat sedan poured as one long drop (both names made up), built on
vehicles/carkit.py.

Run (always through the wrapper, one Blender job at a time on this machine):
    vehicles/blender.sh vehicles/cars/orrin_lumen.py --out DIR --preview
    vehicles/blender.sh vehicles/cars/orrin_lumen.py --out DIR --sheet [--night]

The body is nine lines over sixteen stations with no crease anywhere. The stations are rings
about the car's long axis that close on a small pole at the nose and at the tail, so every
line flows from one tip to the other: the two lines nearest the top are the glass canopy,
the line at the car's widest carries the light ribbons round both ends, each swelling into
a lit pebble on its pole. Lights, shut lines and dot fields are laid on the surface as built
(snap), crescent slots and lidded wheel wells are cut out. LUMEN_PROBE=1 builds the bare
hull and prints the skin's position round the wheels (room for tires and cavities).
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import bpy                                                          # noqa: E402
import carkit as K                                                  # noqa: E402
from carkit import Geo, Matrix, V3, cos, on_body, pi, rad, sin, stud, text_flat   # noqa: E402

# ---------------------------------------------------------------------------------------
# dimensions
# ---------------------------------------------------------------------------------------
FA_X, RA_X = 1.58, -1.52            # axles: wheelbase 3.1
R, W, RIM = 0.37, 0.245, 0.292      # tire radius, width, rim radius
F_OUT, R_OUT = 0.945, 0.880         # outer face of the tires (the tail tapers)
CAV = 0.415                         # wheel cavity radius
F_LID, R_LID = 0.655, 0.575         # top of the wheel openings: the body lids the wheels
NOSE = V3((2.505, 0, 0.452))        # the poles the rings close on
TAIL = V3((-2.51, 0, 0.612))

# ---------------------------------------------------------------------------------------
# body: stations (rings) and lines
# ---------------------------------------------------------------------------------------
LINES = "CGESHULRB"
#        C top centerline, G mid canopy, E canopy edge, S shoulder, H haunch, U widest,
#        L lower flank, R rocker, B floor centerline
ORDER = ["P0", "N1", "N2", "A1", "FA", "A3", "D1", "M1", "D2", "M2", "D3", "RA", "R3", "T2",
         "T1", "T0"]
PT = {}


def ring(x, c, g, e, s, h, u, lo, r, b):
    """A station at one x (or one x per line): z of C, (y, z) of the others, z of B."""
    xs = x if isinstance(x, (list, tuple)) else [x] * 9
    pts = [(0.0, c), g, e, s, h, u, lo, r, (0.0, b)]
    return [(xs[k], p[0], p[1]) for k, p in enumerate(pts)]


def stations():
    T = {
        "N1": [(2.468, 0, .565), (2.467, .06, .564), (2.465, .12, .560), (2.448, .30, .532),
               (2.432, .42, .494), (2.42, .48, .45), (2.43, .43, .375), (2.446, .26, .325),
               (2.454, 0, .31)],
        "N2": [(2.31, 0, .675), (2.307, .135, .672), (2.30, .27, .662), (2.27, .62, .635),
               (2.245, .80, .565), (2.235, .88, .455), (2.245, .83, .31), (2.27, .62, .215),
               (2.29, 0, .19)],
        "A1": [(2.07, 0, .775), (2.07, .21, .768), (2.07, .41, .742), (2.06, .80, .75),
               (2.055, .96, .685), (2.05, 1.0, .50), (2.055, .978, .30), (2.07, .80, .15),
               (2.09, 0, .14)],
        # between the wheels the belt dips and the flank draws in a little (a waist), then
        # the body rises again over the rear wheel
        "FA": ring(FA_X, .915, (.28, .905), (.53, .848), (.86, .878), (.985, .795),
                   (1.008, .58), (.99, .31), (.84, .13), .13),
        "A3": ring(1.18, 1.04, (.34, 1.022), (.63, .89), (.875, .875), (.978, .79),
                   (1.004, .58), (.985, .31), (.84, .13), .13),
        # the three door cuts fan like petals: forward at the top, upright, back at the top
        "D1": ring((1.02, 1.02, 1.01, .995, .955, .905, .865, .855, .855), 1.10, (.375, 1.08),
                   (.685, .90), (.875, .866), (.972, .78), (.998, .58), (.975, .31),
                   (.84, .13), .13),
        "M1": ring(0.45, 1.262, (.425, 1.232), (.745, .895), (.885, .855), (.962, .775),
                   (.988, .585), (.962, .31), (.835, .13), .13),
        "D2": ring((.03, .03, .03, .02, 0, -.02, -.03, -.03, -.03), 1.357, (.465, 1.318),
                   (.775, .89), (.892, .85), (.958, .772), (.984, .59), (.955, .31),
                   (.83, .13), .13),
        "M2": ring(-0.50, 1.398, (.485, 1.356), (.78, .90), (.893, .86), (.958, .78),
                   (.985, .592), (.955, .312), (.83, .13), .13),
        "D3": ring((-1.10, -1.10, -1.105, -1.11, -1.065, -1.005, -.965, -.955, -.955), 1.368,
                   (.465, 1.328), (.75, .93), (.885, .892), (.962, .80), (.988, .596),
                   (.962, .318), (.83, .133), .132),
        "RA": ring(RA_X, 1.275, (.42, 1.232), (.67, .955), (.83, .918), (.925, .815),
                   (.955, .60), (.94, .33), (.80, .14), .135),
        "R3": ring(-1.98, 1.05, (.33, 1.028), (.52, .885), (.76, .86), (.88, .768),
                   (.935, .60), (.927, .36), (.77, .19), .185),
        "T2": [(-2.27, 0, .89), (-2.265, .19, .876), (-2.255, .32, .82), (-2.235, .575, .785),
               (-2.22, .705, .722), (-2.21, .76, .615), (-2.22, .727, .475),
               (-2.235, .545, .34), (-2.25, 0, .315)],
        "T1": [(-2.455, 0, .75), (-2.454, .06, .748), (-2.452, .12, .742), (-2.435, .30, .705),
               (-2.42, .40, .662), (-2.41, .45, .615), (-2.418, .40, .545),
               (-2.435, .26, .48), (-2.445, 0, .46)],
    }
    for name, src, pole in (("P0", "N1", NOSE), ("T0", "T1", TAIL)):
        T[name] = [(pole.x, p[1] * 0.22, pole.z + (p[2] - pole.z) * 0.22) for p in T[src]]
    S = K.fill([T[k] for k in ORDER])
    PT.update(K.table(ORDER, LINES, S))
    return S


PMAT = dict(front="paint", door_f="paint", door_r="paint", sill="paint", rear="paint",
            glass="glass", floor="underbody", well="well", slot="void")


def panel_of(i, j):
    if j == 7 and 3 <= i <= 11:          # the belly is painted where it turns up at both ends
        return "floor"
    if j <= 1:                           # the canopy: from the nose pole to the tail pole
        return "glass"
    if i <= 5:                           # one piece from the nose to the front door
        return "front"
    if i <= 9:
        return "sill" if j == 6 else "door_f" if i <= 7 else "door_r"
    return "rear"


def lid_cutter(g, cx, top, a=0.41, z0=0.31, n=2.6, y0=0.89, depth=0.4):
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
    K.well_cutter(cav, FA_X, R, CAV, 0.665, ang, depth=0.235)
    K.well_cutter(cav, RA_X, R, CAV, 0.60, ang, depth=0.235)
    K.well_cutter(cav2, FA_X, R, 0.378, 0.89, ang, depth=F_OUT + 0.008 - 0.89)
    K.well_cutter(cav2, RA_X, R, 0.378, 0.82, ang, depth=R_OUT + 0.008 - 0.82)
    lid_cutter(lids, FA_X, F_LID)
    lid_cutter(lids, RA_X, R_LID, y0=0.82)
    # crescents: a pair under each ribbon, and one in the wake of each front wheel
    lune(slots, (2.405, .35, .392), (2.165, .865, .40), (0.62, 0.75, -0.22), (0, 0, -1),
         0.050, 0.024, depth=0.04, flare=0.012)
    lune(slots, (-2.40, .34, .548), (-2.165, .755, .512), (-0.62, 0.72, -0.30), (0, 0, -1),
         0.046, 0.022, depth=0.04, flare=0.012)
    lune(slots, (1.108, .99, .285), (1.172, .99, .645), (0, 1, 0), (-1, 0, 0), 0.062, 0.03,
         depth=0.055, flare=0.02)
    cutters = [(cav, "well"), (cav2, "well"), (lids, "well"), (slots, "slot")]
    if os.environ.get("LUMEN_PROBE"):
        cutters = []
    K.build_body(stations(), panel_of, PMAT, 0.0, 0.0,
                 front=dict(kind="flat", panel="front", crease=0.0),
                 rear=dict(kind="flat", panel="rear", crease=0.0),
                 cutters=cutters, subdiv=4, thick=0.004)


def probe():
    """LUMEN_PROBE=1: the skin where the tires and the wheel cavities need room."""
    for cx, out in ((FA_X, F_OUT), (RA_X, R_OUT)):
        for dx in (-0.39, -0.3, 0.0, 0.3, 0.39):
            row = []
            for z in (0.37, 0.50, 0.60, 0.70, 0.74, 0.78):
                loc, _ = on_body(cx + dx, z, 'y')
                row.append("%.3f" % loc.y if loc else " none")
            print("skin y at x %+.2f (tire face %.3f): %s" % (cx + dx, out, " ".join(row)))
        row = []
        for y in (0.66, 0.75, 0.85, 0.90, 0.94):
            loc, _ = on_body(cx, y, 'z')
            row.append("%.3f" % loc.z)
        print("skin z over the axle at x %.2f: %s" % (cx, " ".join(row)))


# ---------------------------------------------------------------------------------------
# things lying on the surface as built
# ---------------------------------------------------------------------------------------
def snap(p):
    """The body's nearest surface point to p and its outward normal."""
    if K._BVH[0] is None:
        K.body_bvh()
    loc, n, _, _ = K._BVH[0].find_nearest(V3(p))
    if n.dot(loc - V3((max(-2.0, min(2.0, loc.x)), 0, 0.62))) < 0:
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


def pebble(g, at, a, b, h, seg=40):
    """A low oval bead on the surface at the point nearest `at`: a wide, b high, h proud."""
    loc, n = snap(at)
    t1 = V3((0, 0, 1)).cross(n).normalized()
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
    # the nose ribbon: from behind one front wheel, over its lid, round the nose, to the other
    half = [(0.98, 1.0, .752), (1.25, 1.0, .748), (FA_X, 1.0, .742), (1.90, .985, .70),
            (2.10, .92, .615), P["N2"]["H"].lerp(P["N2"]["U"], 0.55),
            P["N1"]["H"].lerp(P["N1"]["U"], 0.8), (NOSE.x, 0, NOSE.z + 0.016)]
    g = Geo()
    strip(g, both(half), 0.017, taper=(0.5, 0.5))
    pebble(g, (NOSE.x + 0.05, 0, NOSE.z + 0.03), 0.044, 0.033, 0.009)   # the ribbon swells
    g.obj("led.front", "led_front", sharp=50)
    half = [(-1.0, .99, .757), (-1.22, .98, .754), (RA_X, .95, .748), (-1.90, .90, .715),
            P["T2"]["H"].lerp(P["T2"]["U"], 0.5), P["T1"]["H"].lerp(P["T1"]["U"], 0.75),
            (TAIL.x, 0, TAIL.z + 0.016)]
    g = Geo()
    strip(g, both(half), 0.017, taper=(0.5, 0.5))
    pebble(g, (TAIL.x - 0.05, 0, TAIL.z + 0.034), 0.044, 0.035, 0.009)
    g.obj("led.rear", "led_rear", sharp=50)


def build_details():
    P = PT
    # ---- petal doors: hairlines over the glass on the door cuts, joined along the canopy
    g = Geo()
    for sgn in (1, -1):
        def m(p):
            return V3((p.x, sgn * p.y, p.z))
        for st in ("D1", "D2", "D3"):
            strip(g, [m(P[st]["E"]), m(P[st]["E"].lerp(P[st]["G"], 0.5)), m(P[st]["G"])],
                  0.005, lift=0.0012, n=8)
        strip(g, [m(P[st]["G"]) for st in ("D1", "M1", "D2", "M2", "D3")], 0.005,
              lift=0.0012, n=10)
    g.obj("glass.lines", "gloss_black", sharp=50)
    # ---- door pulls: small crescents under the haunch, and the charge port's ring
    g = Geo()
    for sgn in (1, -1):
        for x0 in (0.20, -0.72):
            strip(g, [(x0, sgn, .742), (x0 - 0.07, sgn, .752), (x0 - 0.14, sgn, .742)], 0.014,
                  lift=0.0009, taper=(0.05, 0.05), n=6)
    g.obj("lines", "void", sharp=50)
    g = Geo()                               # the charge ports: a small ring of light each side
    for sgn in (1, -1):
        strip(g, [(-2.0 + 0.045 * cos(rad(a)), sgn, 0.655 + 0.045 * sin(rad(a)))
                  for a in range(0, 361, 30)], 0.005, lift=0.0012, n=3)
    g.obj("led.port", "led_accent", sharp=50)
    # ---- where it breathes: dot fields under both tips
    g = Geo()
    dot_field(g, 'x', 0.0, 0.385, 0.25, 0.034)
    dot_field(g, 'X', 0.0, 0.545, 0.24, 0.030)
    g.obj("dots", "void")
    # ---- lettering: one small word each
    g = Geo()
    for side in (1, -1):
        text_proj(g, "lumen", 0.034, 0.60, 0.40, 'y' if side > 0 else 'Y', spacing=1.25)
    text_proj(g, "orrin", 0.03, 0.0, 0.468, 'X', spacing=1.4)
    g.obj("lettering", "decal")
    # ---- camera pods where mirrors would be, sensors round the nose
    g = Geo()
    gl = Geo()
    for sgn in (1, -1):
        loc, n = snap((1.10, sgn * 1.0, 0.80))
        fwd = V3((1, 0, 0.06)).normalized()
        xf = (Matrix.Translation(loc + n * 0.006)
              @ V3((0, 1, 0)).rotation_difference(fwd).to_matrix().to_4x4())
        prof = [(-0.10 * cos(rad(a)), 0.026 * sin(rad(a)) ** 0.8 + 0.0005)
                for a in range(0, 181, 12)]
        g.lathe(prof, 24, xf=xf)
        gl.lathe([(-0.101, 0.001), (-0.101, 0.011), (-0.097, 0.013), (-0.097, 0.001)], 16, xf=xf)
    g.obj("cameras", "paint", sharp=40)
    gl.obj("camera.lens", "gloss_black")
    g = Geo()
    for y, z, proj in ((0.30, 0.43, 'x'), (-0.30, 0.43, 'x'), (0.30, 0.588, 'X'),
                       (-0.30, 0.588, 'X')):
        loc, n = on_body(y, z, proj)
        if loc is not None:
            stud(g, loc, n, [(-0.002, 0.001), (-0.002, 0.010), (0.0012, 0.010),
                             (0.0012, 0.001)], 14)
    g.obj("sensors", "gloss_black")
    # ---- side markers: a short light dash low behind each wheel lid
    g = Geo()
    for sgn in (1, -1):
        strip(g, [(-1.99, sgn, .50), (-2.07, sgn * 0.9, .505), (-2.14, sgn * 0.8, .51)],
              0.008, taper=(0.04, 0.04), n=6)
    g.obj("led.marker", "led_rear", sharp=50)


# ---------------------------------------------------------------------------------------
# interior: decks under the long glass, a tub, four seats
# ---------------------------------------------------------------------------------------
def build_interior():
    def sheet(name, rows, hold):
        K.build_body([[(x, 0.0, z0), (x, y1, z1), (x, y2, z2)]
                      for (x, z0, y1, z1, y2, z2) in rows],
                     lambda i, j: "deck", dict(deck="interior"), 0.0,
                     lambda i, j: 0.7 if i == hold else 0.0, name=name, project=False)
    sheet("deck.front", [(2.478, .462, .012, .462, .024, .461), (2.45, .50, .035, .499, .07, .496),
                         (2.41, .535, .06, .533, .12, .527), (2.29, .632, .13, .628, .25, .615),
                         (2.02, .728, .20, .722, .38, .70), (1.60, .815, .27, .81, .50, .78),
                         (1.20, .865, .33, .86, .60, .838), (0.95, .875, .36, .87, .655, .855),
                         (0.83, .855, .37, .85, .68, .838), (0.79, .60, .37, .60, .68, .60)], 8)
    sheet("deck.rear", [(-1.09, .60, .40, .60, .69, .60), (-1.13, .93, .40, .925, .70, .90),
                        (-1.50, .95, .38, .945, .64, .92), (-1.92, .90, .30, .895, .50, .862),
                        (-2.22, .80, .19, .795, .31, .775), (-2.41, .71, .06, .708, .12, .70),
                        (-2.445, .675, .035, .674, .07, .671),
                        (-2.478, .625, .012, .625, .024, .624)], 1)
    g = Geo()
    g.prism([(1.0, -.74, .90), (1.0, -.70, .90), (1.0, -.655, .215), (1.0, .655, .215),
             (1.0, .70, .90), (1.0, .74, .90), (1.0, .74, .16), (1.0, -.74, .16)], (-2.07, 0, 0))
    g.box((-1.10, 0, .55), (0.05, 1.26, .78))
    g.box((0.93, 0, .50), (0.06, 1.30, .68))
    g.box((-0.05, 0, .31), (1.9, 0.20, .20))
    g.obj("interior.tub", "interior", bevel=0.01)
    g = Geo()
    tilt = Matrix.Rotation(rad(-24), 3, 'Y')
    for x in (0.38, -0.55):
        for y in (0.385, -0.385):
            g.hexa([(x - 0.27, y - 0.25, .26), (x + 0.26, y - 0.25, .26),
                    (x + 0.26, y + 0.25, .26), (x - 0.27, y + 0.25, .26),
                    (x - 0.27, y - 0.24, .43), (x + 0.25, y - 0.23, .40),
                    (x + 0.25, y + 0.23, .40), (x - 0.27, y + 0.24, .43)])
            g.hexa([(x - 0.31, y - 0.24, .38), (x - 0.17, y - 0.24, .38),
                    (x - 0.17, y + 0.24, .38), (x - 0.31, y + 0.24, .38),
                    (x - 0.50, y - 0.185, .97), (x - 0.42, y - 0.185, .97),
                    (x - 0.42, y + 0.185, .97), (x - 0.50, y + 0.185, .97)])
            g.box((x - 0.475, y, 1.04), (0.07, 0.22, 0.13), rot=tilt)
    g.obj("interior.seats", "seat", bevel=0.035, segs=4)
    g = Geo()
    yoke = (Matrix.Translation((0.70, 0.385, 0.78)) @ Matrix.Rotation(rad(-68), 4, 'Y')
            @ Matrix.Rotation(pi / 2, 4, 'X'))
    g.lathe([(-0.011, 0.150), (0.0, 0.161), (0.011, 0.150), (0.0, 0.139)], 28, xf=yoke)
    g.box((0.75, 0.385, 0.755), (0.14, 0.05, 0.05))
    g.obj("interior.wheel", "interior", sharp=40)
    g = Geo()
    g.box((0.785, 0, 0.775), (0.006, 1.24, 0.06))
    g.obj("interior.screen", "screen")
    g = Geo()
    text_flat(g, "orrin", 0.055, (2.12, 0, 0.705), (0, 1, 0), (-0.94, 0, 0.34), spacing=1.5)
    # a hair of light under the glass, round the canopy's front tongue
    half = [(0.97, .575, .868), (1.20, .53, .852), (1.60, .44, .795), (2.02, .33, .712),
            (2.29, .205, .626), (2.385, .09, .548), (2.405, 0, .538)]
    sec = [(-0.0025, -0.002), (0.0025, -0.002), (0.0025, 0.002), (-0.0025, 0.002)]
    g.sweep(spline(both(half), 8), sec, up=(0, 0, 1))
    half = [(-1.19, .60, .918), (-1.50, .55, .934), (-1.92, .43, .874), (-2.22, .265, .787),
            (-2.37, .09, .712), (-2.39, 0, .706)]
    g.sweep(spline(both(half), 8), sec, up=(0, 0, 1))
    g.obj("led.cabin", "led_accent")


# ---------------------------------------------------------------------------------------
# wheels: the kit's tire round a smooth disc with a turbine of fine vanes and two light rings
# ---------------------------------------------------------------------------------------
def build_disc(tag, cx, out_y, side, vanes=54):
    K.build_wheel(tag, cx, R, W, RIM, out_y, side, style="disc", ring=None, caliper=None)
    for part in ("rim.", "hub."):
        ob = bpy.data.objects[part + tag]
        me = ob.data
        bpy.data.objects.remove(ob)
        bpy.data.meshes.remove(me)
    hw = W / 2
    flip = side < 0
    loc = (cx, side * (out_y - hw), R)
    r_in, r_out = 0.138, RIM - 0.026
    g = Geo()
    g.lathe([(-hw + 0.03, RIM), (hw - 0.006, RIM), (hw - 0.004, RIM - 0.007),
             (hw - 0.012, RIM - 0.017), (hw - 0.036, RIM - 0.022), (hw - 0.038, r_in - 0.004),
             (hw - 0.014, 0.120), (hw - 0.008, 0.085), (hw - 0.004, 0.045), (hw - 0.003, 0.004),
             (hw - 0.08, 0.004), (hw - 0.08, RIM - 0.03), (-hw + 0.03, RIM - 0.02)], 96)
    g.obj("rim." + tag, "wheel_face", flip_y=flip, loc=loc, sharp=35)
    g = Geo()
    for k in range(vanes):
        a0 = 2 * pi * k / vanes
        path = []
        for q in range(6):
            f = q / 5
            a = a0 + rad(34) * f ** 1.3
            r = r_in + (r_out - r_in) * f
            path.append((r * cos(a), hw - 0.026 + 0.004 * f, r * sin(a)))
        g.sweep(path, [(-0.0016, -0.010), (0.0016, -0.010), (0.0016, 0.010), (-0.0016, 0.010)],
                up=(0, 1, 0))
    g.lathe([(hw - 0.0025, 0.030), (hw - 0.0025, 0.040), (hw - 0.0005, 0.040),
             (hw - 0.0005, 0.030)], 40)
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
K.VIEWS["hero"].update(dir=(1.0, 0.72, 0.25))     # where the key light falls clear of the cabin
K.VIEWS.update(
    nose=dict(dir=(1.0, 0.4, 0.5), lens=85, target=(2.2, 0.1, 0.55), dist=2.6),
    tail=dict(dir=(-1.0, -0.45, 0.4), lens=85, target=(-2.2, -0.1, 0.65), dist=2.8),
    wheel=dict(dir=(0.45, 1.0, 0.12), lens=85, target=(FA_X, 0.9, 0.42), dist=2.6),
    cabin=dict(dir=(0.3, 1.0, 0.75), lens=85, target=(-0.1, 0.2, 0.9), dist=4.2),
    slot=dict(dir=(1.0, 0.9, 0.12), lens=85, target=(2.25, 0.62, 0.40), dist=1.8),
)


def main():
    K.materials(paint=(0.011, 0.088, 0.094), paint_finish=(0.72, 0.36, 0.7), dust_amount=0.12,
                glass=(0.50, 0.55, 0.57), led_front=(0.86, 0.95, 1.0),
                led_rear=(1.0, 0.035, 0.03), led_accent=(0.30, 1.0, 0.78),
                led_wheel=(0.30, 1.0, 0.78), seat=(0.52, 0.45, 0.36),
                interior=(0.030, 0.032, 0.034), screen=(0.25, 0.9, 0.75))
    K.pbr("wheel_face", (0.19, 0.195, 0.20), 1.0, 0.30)
    K.pbr("wheel_vane", (0.24, 0.245, 0.25), 1.0, 0.26)
    build_hull()
    K.log("hull")
    if os.environ.get("LUMEN_PROBE"):
        probe()
        K.stats()
        return
    build_lights()
    build_details()
    build_interior()
    K.log("details")
    for side, s in ((1, "l"), (-1, "r")):
        build_disc("f" + s, FA_X, F_OUT, side)
        build_disc("r" + s, RA_X, R_OUT, side)
    K.log("wheels")
    K.shoot()


main()
