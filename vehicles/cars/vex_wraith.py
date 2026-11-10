"""Vex Wraith: a two-seat open-wheel speedster (both names made up), on vehicles/carkit.py.

Run (always through the wrapper, one Blender job at a time on this machine):
    vehicles/blender.sh vehicles/cars/vex_wraith.py --out DIR --preview
    vehicles/blender.sh vehicles/cars/vex_wraith.py --out DIR --sheet

The first Vex, so it sets the family's cues (see docs/progress/AG18/vex_wraith): four pods
(nose, cabin tub, two side pods) that never touch, each a weave capsule with a color cap
above its widest line; one raw metal spine that shows on every pod as an inlaid strip and
jumps the gaps between them as a drilled beam; everything else hung on blades, rods and
drilled links in plain sight (wishbones, pushrods, dampers, the motor, its cables); lights
as three-dot clusters on stalks and hairline strips on the wing edges.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import carkit as K                                                  # noqa: E402
from carkit import (Geo, Matrix, V3, cos, on_body, pi, rad, ribbon,        # noqa: E402
                    shr, sin, stud, text_flat, text_on_body)

# ---------------------------------------------------------------------------------------
# dimensions
# ---------------------------------------------------------------------------------------
FA_X, RA_X = 1.50, -1.28                    # axles: wheelbase 2.78
F_R, F_W, F_RIM, OUT_Y = 0.35, 0.25, 0.245, 1.0
R_R, R_W, R_RIM = 0.36, 0.32, 0.245
F_YC, R_YC = OUT_Y - F_W / 2, OUT_Y - R_W / 2
F_IN, R_IN = OUT_Y - F_W, OUT_Y - R_W       # the tires' inner faces
FLOOR_Z0, FLOOR_Z1 = 0.058, 0.082
NUM = "27"

PT = {}


# ---------------------------------------------------------------------------------------
# helpers of this car
# ---------------------------------------------------------------------------------------
def _up_for(pts):
    segs = [(V3(b) - V3(a)).normalized() for a, b in zip(pts, pts[1:])]
    best = None
    for c in ((0, 0, 1), (1, 0, 0), (0, 1, 0)):
        m = max(abs(s.dot(V3(c))) for s in segs)
        if best is None or m < best[0]:
            best = (m, c)
    return best[1]


def tube(g, pts, r, n=8):
    """A round tube along a path."""
    sec = [(r * cos(2 * pi * k / n), r * sin(2 * pi * k / n)) for k in range(n)]
    g.sweep(pts, sec, up=_up_for(pts))


def blade(g, pts, w, t, up=(0, 0, 1)):
    """A flat blade along a path: w across, t along up."""
    g.sweep(pts, [(-w / 2, -t / 2), (w / 2, -t / 2), (w / 2, t / 2), (-w / 2, t / 2)], up=up)


def ring(g, c, axis, r_out, r_in, t, n=20):
    xf = Matrix.Translation(V3(c)) @ V3((0, 1, 0)).rotation_difference(
        V3(axis).normalized()).to_matrix().to_4x4()
    g.lathe([(-t / 2, r_in), (-t / 2, r_out), (t / 2, r_out), (t / 2, r_in)], n, xf=xf)


def drilled(g, a, b, h, t, axis=(0, 1, 0), fl=0.012, flw=0.05, hole=0.60):
    """The Vex beam: from a to b, h deep, a web of rings (real holes, light comes through)
    between two flanges; axis is the holes' direction."""
    a, b = V3(a), V3(b)
    d = b - a
    L = d.length
    d.normalize()
    ax = V3(axis).normalized()
    n = ax.cross(d).normalized()
    ro = h / 2 - fl * 0.4
    k = max(1, int(L / (2 * ro) + 0.999))
    step = L / k
    for i in range(k):
        ring(g, a + d * (step * (i + 0.5)), ax, ro, ro * hole, t)
    for s in (-1, 1):
        o = n * (s * (h / 2 - fl / 2))
        g.sweep([a + o, b + o], [(-flw / 2, -fl / 2), (flw / 2, -fl / 2), (flw / 2, fl / 2),
                                 (-flw / 2, fl / 2)], up=n)


def ball(g, c, r=0.016):
    """A rod end: a short fat disc."""
    g.lathe([(-r * 0.6, 0.002), (-r * 0.6, r), (r * 0.6, r), (r * 0.6, 0.002)], 10,
            xf=Matrix.Translation(V3(c)))


def side_pt(x, z):
    """The outermost body surface on the left at (x, z)."""
    return on_body(x, z, 'y')[0]


def top_z(x, y, default=0.5):
    loc = on_body(x, y, 'z')[0]
    return loc.z if loc is not None else default


def text_top(g, txt, size, x0, y0, right=(-1, 0), lift=0.0012, spacing=1.0):
    """Text on the top of the body, its middle at (x0, y0), reading along right."""
    vs, fs = K.text_mesh(txt, size, spacing)
    rx, ry = right
    ux, uy = -ry, rx
    out = []
    for p in vs:
        loc, n = on_body(x0 + rx * p.x + ux * p.y, y0 + ry * p.x + uy * p.y, 'z')
        if loc is None:
            return
        out.append(loc + n * lift)
    g.add(out, fs)


def block(g, gt, txt, size, x0, z0, side, pad=0.012, spacing=1.05, wide=None):
    """A sponsor-like block on a flank: a plate in g, its word in gt."""
    w = wide if wide is not None else size * 0.62 * len(txt) * spacing + 2 * pad
    ribbon(g, [(x0 - w / 2, z0), (x0 + w / 2, z0)], 'y' if side > 0 else 'Y', size + 2 * pad)
    text_on_body(gt, txt, size, x0, z0, side, lift=0.0022, spacing=spacing)


# ---------------------------------------------------------------------------------------
# the pods
# ---------------------------------------------------------------------------------------
PMAT = dict(spine="alloy", cap="paint", flank="carbon", belly="carbon", bulk="alloy",
            tip="alloy", pit="interior", rad="grille", duct="carbon", mouth="void",
            out="void")

# nose pod: C top centerline, D the spine strip's edge, S cap edge, W widest, L lower, B keel
NOSE = [
    [(2.12, 0, .335), (2.12, .012, .335), (2.12, .026, .332), (2.115, .040, .310),
     (2.12, .026, .288), (2.12, 0, .284)],
    [(1.92, 0, .425), (1.92, .028, .425), (1.92, .085, .418), (1.92, .125, .345),
     (1.92, .080, .258), (1.92, 0, .248)],
    [(1.56, 0, .500), (1.56, .032, .500), (1.56, .115, .492), (1.56, .172, .375),
     (1.56, .110, .228), (1.56, 0, .212)],
    [(1.24, 0, .500), (1.24, .032, .500), (1.24, .112, .492), (1.24, .165, .380),
     (1.24, .105, .232), (1.24, 0, .216)],
]
# cabin tub: C, D, R the cockpit's rim, W widest, L lower, B keel
TUB = [
    [(0.86, 0, .470), (0.86, .030, .470), (0.86, .075, .465), (0.85, .115, .370),
     (0.86, .080, .245), (0.86, 0, .225)],
    [(0.62, 0, .560), (0.62, .036, .560), (0.62, .340, .550), (0.61, .420, .410),
     (0.62, .330, .210), (0.62, 0, .185)],
    [(0.38, 0, .600), (0.38, .040, .600), (0.38, .500, .590), (0.38, .570, .440),
     (0.38, .460, .195), (0.38, 0, .172)],
    [(-.54, 0, .610), (-.54, .040, .610), (-.54, .500, .600), (-.54, .570, .450),
     (-.54, .460, .195), (-.54, 0, .172)],
    [(-.70, 0, .570), (-.70, .036, .570), (-.70, .410, .560), (-.70, .485, .440),
     (-.70, .390, .225), (-.70, 0, .195)],
]
# side pod: eight points round, from the top's inner edge outward and back under
POD_SEC = [(-.085, .150), (.085, .150), (.140, .070), (.140, -.080), (.085, -.150),
           (-.085, -.150), (-.140, -.080), (-.140, .070)]
POD_Y, POD_Z = 0.835, 0.338
POD_X = (0.68, 0.36, -0.34, -0.66)


def nose_panel(i, j):
    return ("spine", "cap", "cap", "flank", "belly")[j]


def tub_panel(i, j):
    if j == 1 and i == 2:
        return "pit"
    return ("spine", "cap", "cap", "flank", "belly")[j]


def pod_panel(i, j):
    if j == 0 and i == 1:
        return "rad"
    return "cap" if j in (7, 0, 1) else "belly" if j == 4 else "flank"


def pod_station(k):
    x = POD_X[k]
    sc = (1.0, 1.0, 1.0, 0.86)[k]
    rake = (0.55, 0.0, 0.0, -0.25)[k]           # the mouth leans back, the outlet forward
    dyc, dzc = ((0.0, 0.0), (0.0, 0.004), (-0.012, -0.004), (-0.035, -0.022))[k]
    return [(x - rake * (dz + 0.15), POD_Y + dyc + dy * sc, POD_Z + dzc + dz * sc)
            for (dy, dz) in POD_SEC]


def build_pods():
    def lc(i, j):                               # creases along the lines
        return (0.0, 1.0, 0.45, 1.0, 0.35, 0.0)[j]

    S = K.fill(NOSE)
    PT["nose"] = S
    K.build_body(S, nose_panel, PMAT, lc, 0.0, name="nose",
                 front=dict(kind="flat", panel="tip"), rear=dict(kind="flat", panel="bulk"))
    S = K.fill(TUB)
    PT["tub"] = S
    K.build_body(S, tub_panel, PMAT, lc, 0.0, name="tub",
                 front=dict(kind="flat", panel="bulk"), rear=dict(kind="flat", panel="bulk"),
                 recesses=[(2, 1, 0.04, 0.33, "pit", "pit")])
    S = K.fill([pod_station(k) for k in range(4)])
    PT["pod"] = S
    cf = V3((POD_X[0] - 0.08, POD_Y, POD_Z))
    cr = V3((POD_X[3] + 0.03, POD_Y - 0.035, POD_Z - 0.022))
    body = K.build_body(
        S, pod_panel, PMAT,
        lambda i, j: (0.5, 0.5, 1.0, 0.35, 0.35, 0.35, 0.35, 1.0)[j], 0.0, name="pod",
        front=dict(center=cf, depth=0.10, band=0.018, frame="duct", inner="mouth",
                   reach=0.03),
        rear=dict(center=cr, depth=0.07, band=0.016, frame="duct", inner="out", reach=0.03),
        recesses=[(1, 0, 0.022, 0.028, "rad", "cap")], wrap=True)
    return body, cf, cr


# ---------------------------------------------------------------------------------------
# spine, floor, wings
# ---------------------------------------------------------------------------------------
BOOM_A, BOOM_B, BOOM_H = V3((-0.72, 0, 0.510)), V3((-1.90, 0, 0.600)), 0.12
WING_Z = 0.84


def boom_top(x):
    t = (BOOM_A.x - x) / (BOOM_A.x - BOOM_B.x)
    return BOOM_A.z + (BOOM_B.z - BOOM_A.z) * t + BOOM_H / 2


def build_spine():
    g = Geo()
    # the front jump: nose pod to tub, its top flange in line with the inlaid strips
    drilled(g, (1.26, 0, 0.440), (0.84, 0, 0.412), 0.115, 0.022, flw=0.062)
    # a keel tube under it and two diagonals: a truss you can see through
    tube(g, [(1.26, 0, 0.250), (0.84, 0, 0.262)], 0.016)
    tube(g, [(1.24, 0, 0.385), (1.05, 0, 0.258)], 0.011)
    tube(g, [(1.05, 0, 0.258), (0.86, 0, 0.360)], 0.011)
    # the tail boom: tub to the wing mast
    drilled(g, BOOM_A, BOOM_B, BOOM_H, 0.022, flw=0.062)
    # the wing mast, leaning back
    drilled(g, (-1.80, 0, 0.640), (-1.915, 0, WING_Z + 0.012), 0.15, 0.020, flw=0.05)
    g.box((-1.925, 0, WING_Z + 0.008), (0.20, 0.09, 0.016))
    g.obj("spine", "alloy", bevel=0.0025)
    # the inlaid strips' fasteners, two rows
    g = Geo()
    prof = [(-0.002, 0.001), (-0.002, 0.0065), (0.0022, 0.0065), (0.0022, 0.001)]
    for x in [2.02 - 0.11 * k for k in range(8)] + [0.80 - 0.105 * k for k in range(15)]:
        loc, n = on_body(x, 0.019, 'z')
        if loc is not None:
            stud(g, loc, n, prof, 6)
    g.obj("spine.bolts", "gloss_black", mirror=True)


def build_floor():
    z0, dz = FLOOR_Z0, FLOOR_Z1 - FLOOR_Z0
    g = Geo()

    def slab(poly):
        g.prism([(x, y, z0) for (x, y) in poly], (0, 0, dz))
    # the plank under the tub, the tongue under the nose
    slab([(1.10, -0.20), (1.10, 0.20), (0.98, 0.555), (-0.84, 0.555), (-0.84, -0.555),
          (0.98, -0.555)])
    slab([(1.10, -0.20), (1.95, -0.10), (1.95, 0.10), (1.10, 0.20)])
    for s in (1, -1):
        # outer rails under the side pods, cross plates joining them to the plank; the
        # slots between are open to the ground under the gaps
        slab([(0.98, s * 0.70), (0.90, s * 0.97), (-0.80, s * 0.97), (-0.80, s * 0.70)])
        slab([(0.98, s * 0.555), (0.98, s * 0.70), (0.78, s * 0.70), (0.78, s * 0.555)])
        slab([(-0.62, s * 0.555), (-0.62, s * 0.70), (-0.80, s * 0.70), (-0.80, s * 0.555)])
        slab([(0.14, s * 0.555), (0.14, s * 0.70), (0.04, s * 0.70), (0.04, s * 0.555)])
    g.obj("floor", "plank", bevel=0.002)
    # diffuser: a ramp between the rear wheels, strakes under it
    g = Geo()
    g.prism([(-0.84, -0.62, z0), (-0.84, -0.62, z0 + dz), (-1.92, -0.62, 0.232),
             (-1.92, -0.62, 0.212)], (0, 1.24, 0))
    for y in (-0.61, -0.41, -0.205, 0.0, 0.205, 0.41, 0.61):
        g.prism([(-1.02, y - 0.005, 0.078), (-1.92, y - 0.005, 0.215), (-1.92, y - 0.005, 0.085),
                 (-1.30, y - 0.005, 0.045)], (0, 0.010, 0))
    g.obj("diffuser", "plank", bevel=0.002)
    # skid blocks under the plank, raw metal wear strips on the rails' edges
    g = Geo()
    for s in (1, -1):
        blade(g, [(0.88, s * 0.972, 0.07), (-0.80, s * 0.972, 0.07)], 0.008, 0.026)
    g.obj("floor.edge", "alloy", bevel=0.001)
    # the pods stand off the floor on drilled links
    g = Geo()
    for x in (0.38, -0.36):
        ring(g, (x, POD_Y, 0.135), (0, 1, 0), 0.056, 0.034, 0.014)
        ring(g, (x, -POD_Y, 0.135), (0, 1, 0), 0.056, 0.034, 0.014)
    for x in (0.52, 0.06, -0.40):
        for y in (0.36, -0.36):
            ring(g, (x, y, 0.130), (0, 1, 0), 0.052, 0.031, 0.014)
    ring(g, (1.42, 0, 0.150), (0, 1, 0), 0.070, 0.042, 0.014)
    ring(g, (1.80, 0, 0.165), (0, 1, 0), 0.085, 0.052, 0.014)
    g.obj("standoffs", "alloy", bevel=0.002)
    # blades from the tub to the side pods, across the gaps
    g = Geo()
    for x in (0.34, -0.34):
        blade(g, [(x, 0.53, 0.37), (x, 0.72, 0.37)], 0.07, 0.014)
        tube(g, [(x + 0.05, 0.54, 0.29), (x - 0.05, 0.71, 0.29)], 0.009)
    g.obj("pod.struts", "alloy", bevel=0.002, mirror=True)


def airfoil(x0, z0, c, th=1.0):
    """A downforce section: leading edge at x0, chord c toward the rear, the tail kicked up."""
    return [(x0, z0 + 0.020 * th), (x0 - 0.12 * c, z0 + 0.040 * th),
            (x0 - 0.55 * c, z0 + 0.046 * th), (x0 - c, z0 + 0.105 * th),
            (x0 - 0.96 * c, z0 + 0.075 * th), (x0 - 0.55 * c, z0 + 0.012 * th),
            (x0 - 0.18 * c, z0)]


def build_wings():
    # ---- front: a main plane the width of the car, flaps inboard of the tires
    g = Geo()
    g.prism([(x, -0.94, z) for (x, z) in airfoil(2.19, 0.085, 0.29, 0.55)], (0, 1.88, 0))
    for s in (1, -1):
        y0, y1 = (0.24, 0.735) if s > 0 else (-0.735, -0.24)
        g.prism([(x, y0, z) for (x, z) in airfoil(1.965, 0.150, 0.13, 0.75)], (0, y1 - y0, 0))
        g.prism([(2.195, s * 0.94 - 0.006, 0.062), (2.195, s * 0.94 - 0.006, 0.19),
                 (2.07, s * 0.94 - 0.006, 0.262), (1.875, s * 0.94 - 0.006, 0.262),
                 (1.86, s * 0.94 - 0.006, 0.062)], (0, 0.012, 0))
        g.prism([(1.965, s * 0.245 - 0.005, 0.10), (1.965, s * 0.245 - 0.005, 0.245),
                 (1.84, s * 0.245 - 0.005, 0.245), (1.86, s * 0.245 - 0.005, 0.10)],
                (0, 0.010, 0))
    g.obj("wing.front", "weave", bevel=0.002)
    g = Geo()                                   # drilled pylons from the nose down to it
    for y in (0.062, -0.062):
        drilled(g, (2.03, y, 0.118), (2.00, y, 0.292), 0.10, 0.010, fl=0.008, flw=0.022)
    g.obj("wing.front.pylons", "alloy", bevel=0.0015)
    g = Geo()                                   # the hairline along the leading edge
    g.box((2.1915, 0.585, 0.0965), (0.006, 0.69, 0.007))
    g.box((2.1965, 0.94, 0.125), (0.005, 0.008, 0.12))
    g.obj("led.wing.front", "led_front", mirror=True)

    # ---- rear: one deep plane on the spine's mast, endplates behind the wheels
    g = Geo()
    g.prism([(x, -0.80, z) for (x, z) in airfoil(-1.76, WING_Z, 0.36)], (0, 1.60, 0))
    g.prism([(x, -0.80, z) for (x, z) in airfoil(-2.10, WING_Z + 0.10, 0.065, 0.5)],
            (0, 1.60, 0))
    for s in (1, -1):
        g.prism([(-1.70, s * 0.806 - 0.006, 0.80), (-1.74, s * 0.806 - 0.006, 0.995),
                 (-2.165, s * 0.806 - 0.006, 0.995), (-2.165, s * 0.806 - 0.006, 0.70),
                 (-2.00, s * 0.806 - 0.006, 0.655), (-1.80, s * 0.806 - 0.006, 0.70)],
                (0, 0.012, 0))
    g.obj("wing.rear", "weave", bevel=0.002)
    g = Geo()
    g.box((-2.168, 0.45, WING_Z + 0.153), (0.006, 0.68, 0.007))
    g.box((-2.168, 0.806, 0.845), (0.005, 0.008, 0.27))
    g.obj("led.wing.rear", "led_rear", mirror=True)
    g = Geo()                                   # stays from the endplates down to the boom
    for s in (1, -1):
        tube(g, [(-1.86, s * 0.795, 0.70), (-1.82, s * 0.035, 0.60)], 0.008)
    g.obj("wing.rear.stays", "alloy")
    # lettering on the endplates, inside and out
    gt = Geo()
    for s in (1, -1):
        text_flat(gt, "VEX", 0.105, (-1.975, s * 0.8135, 0.885), (-s, 0, 0), (0, 0, 1),
                  spacing=1.15)
        text_flat(gt, NUM, 0.07, (-2.075, s * 0.8135, 0.745), (-s, 0, 0), (0, 0, 1))
        text_flat(gt, NUM, 0.075, (2.03, s * 0.9475, 0.165), (-s, 0, 0), (0, 0, 1))
    gt.obj("wing.lettering", "decal")


# ---------------------------------------------------------------------------------------
# suspension: blades, rods, rockers and dampers in plain sight
# ---------------------------------------------------------------------------------------
def damper(g, gs, a, b, r=0.020):
    """A coil-over from a to b: a body in g, the spring's coils in gs."""
    a, b = V3(a), V3(b)
    d = (b - a)
    L = d.length
    xf = Matrix.Translation(a) @ V3((0, 1, 0)).rotation_difference(d.normalized()).to_matrix().to_4x4()
    g.lathe([(0, 0.002), (0, r * 0.55), (L * 0.45, r * 0.55), (L * 0.45, r * 0.8), (L, r * 0.8),
             (L, 0.002)], 10, xf=xf)
    for k in range(7):
        y = L * (0.10 + 0.105 * k)
        gs.lathe([(y, r * 0.95), (y, r * 1.3), (y + L * 0.045, r * 1.3), (y + L * 0.045, r * 0.95)],
                 10, xf=xf)


def build_suspension():
    gb, ga, gs, gf = Geo(), Geo(), Geo(), Geo()     # weave blades, alloy, springs, fenders
    # ---- front: pickups on the nose pod as built
    yo = F_IN - 0.035
    up_o, lo_o = V3((FA_X, yo, 0.515)), V3((FA_X, yo, 0.185))
    for (o, z) in ((up_o, 0.425), (lo_o, 0.250)):
        for x in (1.82, 1.30):
            p = side_pt(x, z) or V3((x, 0.12, z))
            blade(gb, [p + V3((0, -0.01, 0)), o], 0.050, 0.011)
            ga.box(p, (0.07, 0.03, 0.035))
        ball(ga, o, 0.022)
    rk = V3((FA_X - 0.02, 0.105, top_z(FA_X - 0.02, 0.105) + 0.035))
    tube(ga, [lo_o + V3((0, -0.05, 0.03)), rk], 0.010)                      # pushrod
    ga.prism([rk + V3((0.05, -0.006, -0.03)), rk + V3((-0.05, -0.006, -0.03)),
              rk + V3((-0.02, -0.006, 0.035)), rk + V3((0.03, -0.006, 0.035))], (0, 0.012, 0))
    ring(ga, rk + V3((0, 0, 0.0)), (0, 1, 0), 0.016, 0.006, 0.02, 10)
    e = V3((FA_X - 0.30, 0.085, top_z(FA_X - 0.30, 0.085) + 0.028))
    damper(ga, gs, e, rk + V3((-0.02, 0, 0.02)))
    tp = side_pt(1.66, 0.345) or V3((1.66, 0.14, 0.345))
    tube(ga, [tp, (FA_X + 0.11, yo, 0.35)], 0.008)                          # steering rod
    ga.box((FA_X, yo + 0.012, F_R), (0.10, 0.045, 0.40))                    # the upright
    ga.box((FA_X + 0.08, yo, 0.35), (0.09, 0.03, 0.04))
    ga.lathe([(yo - 0.01, 0.002), (yo - 0.01, 0.045), (F_IN + 0.05, 0.045), (F_IN + 0.05, 0.002)],
             12, xf=Matrix.Translation((FA_X, 0, F_R)))
    # the cycle fender: a slim blade over the tire on two stays from the upright
    gf.lathe([(-0.105, F_R + 0.030), (-0.105, F_R + 0.038), (0.105, F_R + 0.038),
              (0.105, F_R + 0.030)], 18, a0=rad(52), a1=rad(150),
             xf=Matrix.Translation((FA_X, F_YC, F_R)))
    for a in (70, 128):
        q = V3((FA_X + (F_R + 0.036) * cos(rad(a)), F_IN - 0.012, F_R + (F_R + 0.036) * sin(rad(a))))
        tube(ga, [(FA_X, yo, 0.50), q], 0.006)
        tube(ga, [q, q + V3((0, 0.05, 0))], 0.006)

    # ---- rear: a tube frame round the motor carries the pickups
    def rail(z0, z1):
        return V3((-0.71, 0.300, z0)), V3((-1.64, 0.165, z1))
    frame = Geo()
    for (z0, z1) in ((0.455, 0.470), (0.225, 0.215)):
        a, b = rail(z0, z1)
        tube(frame, [a, b], 0.014)
    ua, ub = rail(0.455, 0.470)
    la, lb = rail(0.225, 0.215)
    for t in (0.30, 1.0):
        tube(frame, [ua.lerp(ub, t), la.lerp(lb, t)], 0.011)
    tube(frame, [ua.lerp(ub, 0.0), la.lerp(lb, 0.30)], 0.010)
    tube(frame, [ua.lerp(ub, 0.30), la.lerp(lb, 1.0)], 0.010)
    tube(frame, [ub, (ub.x - 0.10, 0.03, boom_top(ub.x - 0.10) - 0.10)], 0.011)
    tube(frame, [ua.lerp(ub, 0.30), (-1.02, 0.03, boom_top(-1.02) - 0.10)], 0.011)
    frame.obj("frame.rear", "alloy", mirror=True)
    frame = Geo()
    tube(frame, [lb, my_(lb)], 0.012)
    tube(frame, [ub, my_(ub)], 0.012)
    frame.obj("frame.rear.cross", "alloy")

    yo = R_IN - 0.03
    up_o, lo_o = V3((RA_X, yo, 0.535)), V3((RA_X, yo, 0.195))
    for (o, a, b) in ((up_o, ua, ub), (lo_o, la, lb)):
        for t in (0.20, 0.92):
            p = a.lerp(b, t)
            blade(gb, [p, o], 0.050, 0.011)
            ga.box(p, (0.06, 0.035, 0.035))
        ball(ga, o, 0.022)
    rk = V3((RA_X + 0.02, 0.060, boom_top(RA_X + 0.02) + 0.02))
    tube(ga, [lo_o + V3((0, -0.05, 0.03)), rk], 0.010)
    ga.prism([rk + V3((0.05, -0.006, -0.03)), rk + V3((-0.05, -0.006, -0.03)),
              rk + V3((-0.03, -0.006, 0.035)), rk + V3((0.02, -0.006, 0.035))], (0, 0.012, 0))
    ring(ga, rk, (0, 1, 0), 0.016, 0.006, 0.02, 10)
    e = V3((RA_X + 0.36, 0.058, boom_top(RA_X + 0.36) + 0.025))
    damper(ga, gs, e, rk + V3((0.02, 0, 0.02)))
    ga.box((RA_X, yo + 0.01, R_R), (0.10, 0.045, 0.42))
    ga.lathe([(0.17, 0.004), (0.17, 0.021), (R_IN + 0.05, 0.021), (R_IN + 0.05, 0.045),
              (R_IN + 0.06, 0.045), (R_IN + 0.06, 0.004)], 12,
             xf=Matrix.Translation((RA_X, 0, R_R)))                          # the half shaft
    for y in (0.21, yo - 0.07):
        ga.lathe([(y - 0.035, 0.022), (y, 0.040), (y + 0.035, 0.022)], 12,
                 xf=Matrix.Translation((RA_X, 0, R_R)))
    gb.obj("wishbones", "carbon", bevel=0.0025, mirror=True)
    ga.obj("suspension", "alloy", bevel=0.002, mirror=True)
    gs.obj("springs", "paint", mirror=True)
    gf.obj("fenders", "weave", bevel=0.002, mirror=True)


def my_(p):
    return V3((p.x, -p.y, p.z))


# ---------------------------------------------------------------------------------------
# power unit, cables
# ---------------------------------------------------------------------------------------
def build_power():
    g = Geo()
    c = Matrix.Translation((RA_X, 0, R_R))
    prof = [(-0.17, 0.004), (-0.17, 0.105)]
    for k in range(12):                                 # a finned casing
        y = -0.150 + 0.025 * k
        prof += [(y, 0.105), (y, 0.134), (y + 0.012, 0.134), (y + 0.012, 0.105)]
    prof += [(0.17, 0.105), (0.17, 0.004)]
    g.lathe(prof, 28, xf=c)
    g.box((RA_X, 0, boom_top(RA_X) - BOOM_H - 0.012), (0.16, 0.10, 0.06))  # hanger
    g.box((RA_X - 0.19, 0, 0.345), (0.14, 0.26, 0.17))                      # reduction gear
    for k in range(5):
        g.box((RA_X - 0.19, -0.10 + 0.05 * k, 0.345), (0.152, 0.012, 0.184))
    g.obj("motor", "alloy_dark", bevel=0.0025)
    g = Geo()
    back = Matrix.Translation((RA_X - 0.262, 0, 0.345)) @ Matrix.Rotation(pi / 2, 4, 'Z')
    g.lathe([(0.0, 0.004), (0.0, 0.070), (0.012, 0.070), (0.018, 0.058), (0.018, 0.004)], 20,
            xf=back)
    for k in range(8):
        a = 2 * pi * k / 8
        g.lathe([(0.010, 0.001), (0.010, 0.0065), (0.017, 0.0065), (0.017, 0.001)], 6,
                xf=back @ Matrix.Translation((0.064 * cos(a), 0, 0.064 * sin(a))))
    g.obj("motor.cover", "alloy", bevel=0.0015)
    g = Geo()
    for s in (1, -1):
        g.lathe([(s * 0.172, 0.03), (s * 0.172, 0.085), (s * 0.19, 0.07), (s * 0.19, 0.03)],
                6, xf=c)
    g.obj("motor.caps", "alloy", bevel=0.002)
    # the cell pack rides low behind the seats: a ribbed box on the frame, lit seams
    g = Geo()
    ge = Geo()
    g.box((-0.875, 0, 0.335), (0.20, 0.44, 0.19))
    for k in range(5):
        g.box((-0.875, -0.16 + 0.08 * k, 0.335), (0.212, 0.022, 0.202))
    ge.box((-0.875, 0, 0.335), (0.204, 0.40, 0.012))
    g.obj("cells", "alloy_dark", bevel=0.003)
    ge.obj("cells.glow", "ember")
    # cable runs: three orange phases cell pack to motor, a loom along the boom
    g = Geo()
    for k, y in enumerate((-0.07, 0.0, 0.07)):
        tube(g, [(-0.975, y, 0.39), (-1.03, y * 1.1, 0.445), (-1.10, y * 1.2, 0.47),
                 (-1.17, y * 1.2, 0.455), (-1.20, y * 1.2, 0.43)], 0.011)
    g.obj("cables.hv", "cable", sharp=60)
    g = Geo()
    zb = lambda x: boom_top(x) - BOOM_H / 2                 # noqa: E731
    for s in (1, -1):
        tube(g, [(-0.70, s * 0.10, 0.50), (-0.80, s * 0.036, zb(-0.80) + 0.02),
                 (-1.78, s * 0.036, zb(-1.78) + 0.02), (-1.90, s * 0.03, 0.70)], 0.006)
        # coolant lines: side pod to the motor, bright tube
        tube(g, [(-0.52, s * 0.705, 0.30), (-0.66, s * 0.62, 0.30), (-0.86, s * 0.40, 0.31),
                 (-1.08, s * 0.30, 0.33), (-1.20, s * 0.18, 0.36)], 0.013)
    g.obj("lines", "alloy", sharp=60)
    g = Geo()
    for x in (-0.95, -1.20, -1.45, -1.70):                 # clips holding the loom
        g.box((x, 0, zb(x) + 0.02), (0.016, 0.09, 0.02))
    g.obj("clips", "gloss_black")


# ---------------------------------------------------------------------------------------
# lights: three-dot clusters on stalks
# ---------------------------------------------------------------------------------------
def cluster(g, gl, root, head, facing, mat_r=0.013):
    """A stalk from root to a three-dot cluster at head, facing along x (1 or -1)."""
    root, head = V3(root), V3(head)
    tube(g, [root, root.lerp(head, 0.6) + V3((0, 0, 0.02)), head], 0.007)
    g.box(head, (0.05, 0.118, 0.040))
    for k in (-1, 0, 1):
        c = head + V3((facing * 0.026, k * 0.036, 0))
        xf = Matrix.Translation(c) @ Matrix.Rotation(pi / 2, 4, 'Z')
        gl.lathe([(-0.004, 0.001), (-0.004, mat_r), (0.004, mat_r), (0.004, 0.001)], 12, xf=xf)


def build_lights():
    g, gl, gr = Geo(), Geo(), Geo()
    p = side_pt(1.80, 0.40) or V3((1.80, 0.11, 0.40))
    cluster(g, gl, p, (1.90, 0.40, 0.515), 1)
    cluster(g, gr, (-1.86, 0.03, 0.655), (-2.02, 0.31, 0.715), -1)
    g.obj("stalks", "carbon", bevel=0.002, mirror=True)
    gl.obj("led.front", "lamp", mirror=True)
    gr.obj("led.rear", "led_rear", mirror=True)
    # the rain light on the end of the boom, amber markers on the pods' shoulders
    g = Geo()
    g.box((BOOM_B.x - 0.012, 0, BOOM_B.z), (0.012, 0.03, 0.10))
    g.obj("led.rain", "led_rear")
    g = Geo()
    ribbon(g, [(0.50, 0.985), (0.40, 0.985)], 'z', 0.010)
    g.obj("led.marker", "led_accent", mirror=True)


# ---------------------------------------------------------------------------------------
# cockpit: two cells either side of the spine, a low screen, the hoop
# ---------------------------------------------------------------------------------------
def build_cockpit():
    # ---- the screen: two low arcs meeting at the spine
    g, gf = Geo(), Geo()
    N = 12
    rows = []
    for k in range(N + 1):
        y = 0.050 + (0.515 - 0.050) * k / N
        u = y / 0.515
        xb = 0.505 - 0.085 * u * u          # ahead of the cells all the way round
        zb = top_z(xb, y, 0.58) - 0.006
        h = 0.200 * (1 - 0.45 * u ** 3)
        rows.append((V3((xb, y, zb)), V3((xb - 0.115 - 0.03 * u, y, zb + h))))
    vs, fs = [], []
    for (b, t) in rows:
        vs += [b, t, t + V3((-0.006, 0, 0)), b + V3((-0.006, 0, 0))]
    for k in range(N):
        o = 4 * k
        fs += [(o + j, o + (j + 1) % 4, o + 4 + (j + 1) % 4, o + 4 + j) for j in range(4)]
    fs += [(0, 1, 2, 3), tuple(4 * N + j for j in range(4))]
    g.add(vs, fs)
    g.obj("screen", "visor", mirror=True, sharp=40)     # sharp edges, or the slab is a lens
    blade(gf, [b + V3((0.004, 0, 0.004)) for (b, t) in rows], 0.016, 0.012)
    b0, t0 = rows[0]
    blade(gf, [b0 + V3((0, -0.012, 0)), t0 + V3((0, -0.012, 0))], 0.012, 0.014, up=(0, 1, 0))
    gf.obj("screen.rail", "alloy", bevel=0.0015, mirror=True)

    # ---- mirrors on stalks, by the screen's ends
    g, gm = Geo(), Geo()
    root = V3((0.50, 0.44, top_z(0.50, 0.44, 0.56)))
    head = V3((0.47, 0.64, 0.685))
    tube(g, [root, root.lerp(head, 0.55) + V3((0, 0, 0.03)), head], 0.006)
    g.hexa([head + V3(o) for o in ((0.035, -0.055, -0.03), (0.035, 0.055, -0.03),
                                    (-0.012, 0.06, -0.034), (-0.012, -0.06, -0.034),
                                    (0.035, -0.055, 0.03), (0.035, 0.055, 0.03),
                                    (-0.012, 0.06, 0.034), (-0.012, -0.06, 0.034))])
    gm.box(head + V3((-0.0135, 0, 0)), (0.003, 0.105, 0.055))
    g.obj("mirrors", "weave", bevel=0.003, mirror=True)
    gm.obj("mirror.glass", "mirror", mirror=True)

    # ---- seats: weave shells, pads, belts
    gsh, gp, gbelt, gi, gscr = Geo(), Geo(), Geo(), Geo(), Geo()
    tilt = Matrix.Rotation(rad(-22), 3, 'Y')
    for y in (0.27, -0.27):
        gsh.box((-0.17, y, 0.292), (0.50, 0.38, 0.03))
        gsh.box((-0.455, y, 0.545), (0.035, 0.38, 0.56), rot=tilt)
        for s in (-1, 1):
            gsh.box((-0.20, y + s * 0.185, 0.335), (0.44, 0.022, 0.10))
            gsh.box((-0.43, y + s * 0.185, 0.56), (0.11, 0.022, 0.46), rot=tilt)
        gp.box((-0.16, y, 0.318), (0.42, 0.32, 0.04))
        gp.box((-0.425, y, 0.535), (0.04, 0.32, 0.42), rot=tilt)
        gp.box((-0.535, y, 0.800), (0.055, 0.20, 0.13), rot=tilt)
        for s in (-1, 1):
            gbelt.box((-0.403, y + s * 0.065, 0.56), (0.008, 0.045, 0.40), rot=tilt)
        gbelt.box((-0.18, y, 0.342), (0.05, 0.30, 0.008))
        # a screen each on the cell's front wall
        gscr.box((0.325, y, 0.545), (0.006, 0.25, 0.075), rot=Matrix.Rotation(rad(-18), 3, 'Y'))
        gi.box((0.345, y, 0.545), (0.02, 0.30, 0.10), rot=Matrix.Rotation(rad(-18), 3, 'Y'))
    # the driver's yoke on the left, on a column
    yk = Matrix.Translation((0.15, 0.27, 0.560)) @ Matrix.Rotation(rad(-24), 4, 'Y')
    gi.box((0, 0, 0), (0.028, 0.27, 0.035), xf=yk)
    for s in (-1, 1):
        gi.box((0, s * 0.135, 0.04), (0.032, 0.032, 0.11), xf=yk)
    tube(gi, [(0.155, 0.27, 0.555), (0.34, 0.27, 0.50)], 0.014)
    # a padded roll round each cell's rim, a heel plate and pedals in the driver's
    R = PT["tub"]
    gr, gh = Geo(), Geo()
    for s in (1, -1):
        loop = [V3((p.x, s * p.y, p.z + 0.004)) for p in (R[2][1], R[2][2], R[3][2], R[3][1])]
        tube(gr, loop + [loop[0]], 0.011)
        gh.box((0.20, s * 0.27, 0.278), (0.24, 0.32, 0.006))
    for k, w in enumerate((0.05, 0.07)):
        gh.box((0.315, 0.20 + 0.14 * k, 0.335), (0.012, w, 0.10),
               rot=Matrix.Rotation(rad(-20), 3, 'Y'))
    gh.box((0.30, -0.27, 0.31), (0.012, 0.30, 0.07), rot=Matrix.Rotation(rad(-30), 3, 'Y'))
    gr.obj("cockpit.roll", "interior", sharp=50)
    gh.obj("cockpit.plates", "alloy", bevel=0.002)
    gsh.obj("seat.shells", "carbon", bevel=0.004)
    gp.obj("seat.pads", "seat", bevel=0.012, segs=3)
    gbelt.obj("seat.belts", "belt")
    gi.obj("cockpit.trim", "interior", bevel=0.003)
    gscr.obj("cockpit.screens", "screen")

    # ---- the hoop: an arch behind both heads with a post on the spine, stays to the boom
    g = Geo()
    sec = [(-0.019, -0.022), (0.019, -0.022), (0.019, 0.022), (-0.019, 0.022)]
    zr = top_z(-0.60, 0.44, 0.58)
    arch = [(-0.585, 0.455, zr - 0.02), (-0.640, 0.385, 0.955), (-0.640, -0.385, 0.955),
            (-0.585, -0.455, zr - 0.02)]
    g.sweep(arch, sec, up=(1, 0, 0))
    g.obj("hoop", "alloy", bevel=0.006, segs=3)
    g = Geo()
    drilled(g, (-0.60, 0, 0.60), (-0.64, 0, 0.935), 0.085, 0.016, fl=0.008, flw=0.03)
    for s in (1, -1):
        tube(g, [(-0.645, s * 0.36, 0.935), (-1.14, s * 0.03, boom_top(-1.14) - 0.02)], 0.013)
        g.prism([(-0.625, s * 0.395, 0.90), (-0.625, s * 0.25, 0.94), (-0.625, s * 0.395, 0.80)],
                (-0.012, 0, 0))                           # gussets in the arch's corners
    g.obj("hoop.stays", "alloy", bevel=0.002)


# ---------------------------------------------------------------------------------------
# radiators, lettering, small things on the pods as built
# ---------------------------------------------------------------------------------------
def build_pod_details(body, cf, cr):
    S = PT["pod"]
    # radiator cores behind the mouths, slats over the exits on top
    g = Geo()
    poly = [(p.y, p.z) for p in body.caps["front"]]
    g.honeycomb(poly, cf.x - 0.10, 0.014, 0.0026, 0.012, 1)
    g.obj("pod.core", "copper", mirror=True)
    g = Geo()
    q = shr([S[1][0], S[2][0], S[2][1], S[1][1]], 0.10, -0.016, (0, 0, 1))
    g.louvers(q[0], q[1], q[2], q[3], 9, 0.045, 0.006, rad(-32), out=(0, 0, 1), margin=0.04)
    g.obj("pod.slats", "alloy", bevel=0.0015, mirror=True)
    g = Geo()                                           # three vanes in each outlet
    for k in (-1, 0, 1):
        g.box((cr.x + 0.035, cr.y + k * 0.06, cr.z), (0.07, 0.006, 0.20))
    g.obj("pod.vanes", "alloy", mirror=True)

    # numbers, names and sponsor-like blocks
    gd, gi, gw = Geo(), Geo(), Geo()                    # plates, dark ink, light ink
    for side in (1, -1):
        block(gd, gi, NUM, 0.105, 0.20, 0.335, side, pad=0.014, wide=0.21)
        text_on_body(gw, "WRAITH", 0.042, -0.14, 0.365, side, spacing=1.25)
        text_on_body(gw, "VEX SKELETAL WORKS", 0.016, -0.14, 0.318, side, spacing=1.3)
        block(gd, gi, "OHMIC", 0.026, -0.44, 0.372, side, pad=0.008)
        block(gd, gi, "NULLWERK", 0.022, -0.445, 0.318, side, pad=0.008)
        text_on_body(gw, "KITE FLUIDS", 0.022, 1.50, 0.325, side, spacing=1.2)
        text_on_body(gi, "W-" + NUM, 0.034, 1.72, 0.405, side, spacing=1.1)
    text_top(gi, NUM, 0.125, 0.585, 0.20)
    text_top(gi, NUM, 0.125, 0.585, -0.20, right=(1, 0))
    for s in (1, -1):
        text_top(gi, "WRAITH", 0.036, 0.52, s * POD_Y, right=(-s, 0), spacing=1.2)
        text_top(gi, "LIFT HERE", 0.014, -0.60, s * 0.30, right=(-s, 0), spacing=1.2)
    gd.obj("decal.plates", "decal")
    gi.obj("decal.ink", "ink")
    gw.obj("decal.light", "decal")
    # fasteners round the pods' caps, a filler on the scuttle
    g = Geo()
    prof = [(-0.002, 0.001), (-0.002, 0.006), (0.002, 0.006), (0.002, 0.001)]
    for x in [0.50 - 0.14 * k for k in range(8)]:
        for z in (0.428, 0.245):
            loc, n = on_body(x, z, 'y')
            if loc is not None:
                stud(g, loc, n, prof, 6)
    for x in (1.86, 1.70, 1.54, 1.38):
        loc, n = on_body(x, 0.262 + 0.02 * (1.86 - x), 'y')
        if loc is not None:
            stud(g, loc, n, prof, 6)
    g.obj("fasteners", "alloy", mirror=True)
    g = Geo()
    loc, n = on_body(0.74, 0.0, 'z')
    if loc is not None:
        stud(g, loc + V3((0, 0.0, 0)), n, [(-0.002, 0.002), (-0.002, 0.026), (0.006, 0.026),
                                            (0.008, 0.020), (0.008, 0.002)], 12)
    g.obj("filler", "gloss_black")
    # a tow eye on the nose, a pitot on the tip
    g = Geo()
    ring(g, (2.135, 0, 0.262), (0, 1, 0), 0.032, 0.019, 0.010, 16)
    tube(g, [(2.118, 0, 0.312), (2.175, 0, 0.312)], 0.004)
    g.obj("nose.bits", "alloy")


# ---------------------------------------------------------------------------------------
# views and the build
# ---------------------------------------------------------------------------------------
for v in K.VIEWS.values():
    v["target"] = (0, 0, 0.42)
K.VIEWS["hero"].update(dir=(1.0, 0.74, 0.33), focus=(1.3, 0.7, 0.4), fstop=11.0)
K.VIEWS["rear"].update(dir=(-1.0, -0.80, 0.36), focus=(-1.3, -0.7, 0.5), fstop=11.0)
K.VIEWS.update(
    gap=dict(dir=(0.5, 1.0, 0.22), lens=85, target=(1.1, 0.3, 0.35), dist=4.2),
    tail=dict(dir=(-1.0, 0.7, 0.30), lens=85, target=(-1.2, 0.2, 0.5), dist=4.6),
    cabin=dict(dir=(0.3, 1.0, 0.55), lens=85, target=(-0.1, 0.2, 0.5), dist=4.0),
)


def main():
    K.materials(paint=(0.20, 0.44, 0.0), paint_finish="gloss", dust_amount=0.10,
                caliper=(0.20, 0.44, 0.0), seat=(0.035, 0.035, 0.04),
                rim=(0.22, 0.225, 0.235), rim_bright=(0.62, 0.63, 0.65),
                decal=(0.82, 0.82, 0.80), screen=(0.35, 0.9, 0.2),
                led_front=(0.85, 0.95, 1.0), led_accent=(1.0, 0.45, 0.03),
                ember=(0.45, 1.0, 0.10))
    K.pbr("alloy", (0.56, 0.57, 0.59), 1.0, 0.30)           # raw machined metal
    K.pbr("alloy_dark", (0.16, 0.165, 0.175), 1.0, 0.42)
    K.pbr("copper", (0.70, 0.36, 0.17), 1.0, 0.38)
    K.pbr("cable", (0.95, 0.30, 0.02), 0.0, 0.45)
    K.pbr("belt", (0.55, 0.035, 0.02), 0.0, 0.7)
    K.pbr("ink", (0.012, 0.012, 0.014), 0.0, 0.5)
    K.pbr("mirror", (0.75, 0.77, 0.80), 1.0, 0.03)
    K.pbr("plank", (0.016, 0.016, 0.018), 0.0, 0.62)       # the floor: matte, so the slots read
    # wings and fenders: a dry lay-up. The kit's coated weave turns silver on a flat plane
    # seen at a grazing angle against the studio's rim light
    _, b = K.carbon("weave")
    b.inputs["Metallic"].default_value = 0.0
    b.inputs["Coat Weight"].default_value = 0.0
    b.inputs["Specular IOR Level"].default_value = 0.12
    mr = b.inputs["Roughness"].links[0].from_node
    mr.inputs["To Min"].default_value = 0.60
    mr.inputs["To Max"].default_value = 0.85
    K.pbr("visor", (0.16, 0.19, 0.17), 0.0, 0.0, **{"Transmission Weight": 1.0, "IOR": 1.5})
    body, cf, cr = build_pods()
    K.log("pods")
    build_spine()
    build_floor()
    build_wings()
    K.log("spine, floor, wings")
    build_suspension()
    build_power()
    build_lights()
    build_cockpit()
    build_pod_details(body, cf, cr)
    K.log("details")
    for side, s in ((1, "l"), (-1, "r")):
        K.build_wheel("f" + s, FA_X, F_R, F_W, F_RIM, OUT_Y, side, spokes=9, style="blade",
                      ring=None, rim="rim_bright", bright="rim")
        K.build_wheel("r" + s, RA_X, R_R, R_W, R_RIM, OUT_Y, side, spokes=9, style="blade",
                      ring=None, rim="rim_bright", bright="rim")
    K.log("wheels")
    K.shoot()


main()
