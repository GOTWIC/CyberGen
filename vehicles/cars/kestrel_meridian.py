"""Kestrel Aerodyne Meridian: a four-seat, four-door hover sedan (both names made up), on
vehicles/carkit.py.

Run (always through the wrapper, one Blender job at a time on this machine):
    vehicles/blender.sh vehicles/cars/kestrel_meridian.py --out DIR --preview
    vehicles/blender.sh vehicles/cars/kestrel_meridian.py --out DIR --sheet

The Dart's calm sibling (docs/progress/AG18/kestrel_dart lists the family cues): the same
knife chine with its strip from prow to stern, flat top facets, ribbed graphite lower hull,
eight-sided emitter pods, canted fins, slot thrusters, keel blade and stencil registration.
Its own: a blunt axe-head prow with a light blade bridging a recessed mouth, a tall framed
cabin with a body-color rail round six side windows, the four pods tucked under the chine
and half sunk in the hull, low fins on the deck, the stern thrusters in two banks either
side of a stern post, and a boarding step that folds out of the lower hull under the doors
(out on the left, stowed on the right).
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import carkit as K                                                  # noqa: E402
from carkit import (Geo, Matrix, V3, band_point, cos, on_body, pi, rad,    # noqa: E402
                    ribbon, sin, stud, text_flat, text_on_body)

SUBDIV = 2

# ---------------------------------------------------------------------------------------
# hull: seven lines over eight stations, every top facet flat, the flanks flowing
# ---------------------------------------------------------------------------------------
LINES = "CRMSKLB"
#        C top centerline (a ridge), R hood crease / roof edge, M the rail's lower edge
#        (the top of the side glass), S shoulder (glass base), K the chine (widest, a knife
#        edge), L lower hull edge, B keel
ORDER = ["P0", "P1", "P2", "P3", "P4", "P5", "P6", "P7"]
PT = {}
T = {
    # the prow: a blunt axe head, a shallow vee in plan
    "P0": [(2.56, 0, .935), (2.545, .34, .925), None, (2.51, .50, .89), (2.47, .585, .80),
           (2.50, .40, .60), (2.56, 0, .555)],
    "P1": [(2.02, 0, 1.005), (2.02, .50, .985), None, (2.00, .76, .945), (1.98, .865, .825),
           (2.00, .58, .52), (2.02, 0, .45)],
    # windshield base, windshield top (the front door's leading edge leans with the pillar)
    "P2": [(1.50, 0, 1.10), (1.46, .60, 1.075), (1.40, .75, 1.06), (1.30, .865, 1.04),
           (1.28, .955, .84), (1.30, .65, .475), (1.30, 0, .42)],
    "P3": [(0.52, 0, 1.63), (0.48, .60, 1.60), (0.56, .75, 1.49), (0.80, .895, 1.07),
           (0.80, .985, .85), (0.70, .66, .47), (0.70, 0, .42)],
    # between the doors, the roof's end, the rear glass's base, the stern
    "P4": [(-.30, 0, 1.665), (-.30, .61, 1.635), (-.30, .755, 1.525), (-.30, .91, 1.09),
           (-.30, .995, .86), (-.30, .67, .47), (-.30, 0, .42)],
    "P5": [(-1.15, 0, 1.64), (-1.17, .60, 1.61), (-1.20, .74, 1.505), (-1.28, .905, 1.10),
           (-1.28, .99, .87), (-1.20, .66, .475), (-1.20, 0, .42)],
    "P6": [(-1.95, 0, 1.25), (-1.95, .60, 1.225), (-1.95, .71, 1.20), (-1.95, .835, 1.14),
           (-1.95, .95, .905), (-1.95, .64, .56), (-1.95, 0, .48)],
    "P7": [(-2.50, 0, 1.165), (-2.50, .58, 1.14), (-2.49, .67, 1.12), (-2.48, .765, 1.085),
           (-2.45, .87, .925), (-2.49, .58, .67), (-2.50, 0, .60)],
}
for _k in ("P0", "P1"):
    T[_k][2] = tuple((u + v) / 2 for u, v in zip(T[_k][1], T[_k][3]))
FRONT_C, FRONT_D = V3((2.56, 0, 0.755)), 0.15
REAR_C = V3((-2.50, 0, 0.91))
TAIL_D, BAND_W = 0.14, 0.04

PMAT = dict(nose="paint", hood="paint", fender="paint", door_f="paint", door_r="paint",
            quarter="paint", rail="paint", roof="paint", deck="paint2", lower="paint2",
            belly="bellyplate", glass_ws="glass_coat", glass_roof="glass_smoke",
            glass_rear="glass_coat",
            glass_sf="glass", glass_sr="glass", glass_sq="glass",
            trim="gloss_black", visor="visor", lightband="gloss_black",
            prow_frame="cladding", prow_in="visor",
            tail_frame="cladding", tail="void", vent="void")


def panel_of(i, j):
    if j == 5:
        return "belly"
    if j == 4:
        return "lower"
    if i == 0:
        return "nose"
    if j == 0:
        return ("visor", "glass_ws", "glass_roof", "roof", "glass_rear", "deck")[i - 1]
    if j == 1:
        return "hood" if i < 2 else "rail" if i <= 5 else "quarter"
    if j == 2:
        return ("hood", "glass_sf", "glass_sf", "glass_sr", "glass_sq", "quarter")[i - 1]
    return "fender" if i < 3 else "door_f" if i == 3 else "door_r" if i == 4 else "quarter"


def line_crease(i, j):
    if j == 2:
        return 1.0 if i >= 2 else 0.0       # the rail's edge, from the windshield's corner
    return 1.0


def station_crease(i, j):
    if i in (0, 7):
        return 1.0
    return 1.0 if j <= 2 else 0.0           # folds between the top facets; flanks flow


def build_hull():
    S = K.fill([T[k] for k in ORDER])
    PT.update(K.table(ORDER, LINES, S))
    K.build_body(
        S, panel_of, PMAT, line_crease, station_crease,
        front=dict(center=FRONT_C, depth=FRONT_D, band=0.032, frame="prow_frame",
                   inner="prow_in", reach=0.075),
        rear=dict(center=REAR_C, depth=TAIL_D, band=BAND_W, band_panel="lightband",
                  band_lines=4, frame="tail_frame", inner="tail"),
        glass=[("glass_ws", 0.034), ("glass_roof", 0.032), ("glass_sf", 0.026),
               ("glass_sr", 0.026), ("glass_sq", 0.024), ("glass_rear", 0.036)],
        subdiv=SUBDIV)


# ---------------------------------------------------------------------------------------
# helpers of this car (chine, rib, plate and build_pod are the Dart's: the family's parts)
# ---------------------------------------------------------------------------------------
_CH = {}


def chine(x):
    """The chine as built at x: the widest point of the hull seen from above."""
    key = round(x, 4)
    if key not in _CH:
        lo, hi = 0.0, 1.3
        for _ in range(18):
            mid = (lo + hi) / 2
            if on_body(x, mid, 'z')[0] is not None:
                lo = mid
            else:
                hi = mid
        loc = on_body(x, lo - 0.0015, 'z')[0]
        _CH[key] = V3((x, lo, loc.z)) if loc is not None else None
    return _CH[key]


def rib(g, pts, proj, w, h, objs=None):
    """A raised rib on the body (or on objs) along a path given in projection."""
    P, N = [], []
    for q in pts:
        loc, n = on_body(q[0], q[1], proj, objs)
        if loc is not None:
            P.append(loc)
            N.append(n)
    if len(P) < 2:
        return
    vs = []
    for i in range(len(P)):
        t = (P[min(i + 1, len(P) - 1)] - P[max(i - 1, 0)]).normalized()
        sd = N[i].cross(t).normalized()
        b = P[i] - N[i] * 0.003
        vs += [b + sd * w / 2, b - sd * w / 2, P[i] + N[i] * h - sd * w * 0.28,
               P[i] + N[i] * h + sd * w * 0.28]
    k = len(P) - 1
    faces = [(0, 1, 2, 3), tuple(4 * k + j for j in range(4))]
    for i in range(k):
        faces += [(4 * i + j, 4 * i + (j + 1) % 4, 4 * i + 4 + (j + 1) % 4, 4 * i + 4 + j)
                  for j in range(4)]
    g.add(vs, faces)


def plate(g, base, along, up, poly, th0, th1=None, tmax=1.0):
    """A flat blade: poly as (a, t) in the plane through base spanned by along and up,
    th0 thick at t = 0 and th1 at t = tmax."""
    base, along, up = V3(base), V3(along).normalized(), V3(up).normalized()
    n = along.cross(up).normalized()
    th1 = th0 if th1 is None else th1
    lo, hi = [], []
    for (a, t) in poly:
        p = base + along * a + up * t
        th = th0 + (th1 - th0) * min(1.0, max(0.0, t / tmax))
        lo.append(p - n * th / 2)
        hi.append(p + n * th / 2)
    m = len(poly)
    g.add(lo + hi, [tuple(range(m)), tuple(range(m, 2 * m))]
          + [(i, (i + 1) % m, m + (i + 1) % m, m + i) for i in range(m)])
    return n


def slab(g, o, ev, ew, u0, u1, v0, v1, w0, w1):
    """A box in a tilted frame: u along x, v along ev, w along ew, from the point o."""
    o, ev, ew = V3(o), V3(ev), V3(ew)
    ex = V3((1, 0, 0))
    g.hexa([o + ex * u + ev * v + ew * w for w in (w0, w1)
            for (u, v) in ((u0, v0), (u1, v0), (u1, v1), (u0, v1))])


# ---------------------------------------------------------------------------------------
# emitter pods: the family's nacelle, here tucked under the chine and half sunk in the hull
# ---------------------------------------------------------------------------------------
POD_SEC = [(-.11, .14), (.09, .14), (.19, .05), (.19, -.06), (.13, -.14), (-.13, -.14),
           (-.19, -.06), (-.19, .05)]
PODS = dict(f=dict(xc=1.44, yc=0.80, zc=0.555, L=1.12, s=0.92),
            r=dict(xc=-1.50, yc=0.84, zc=0.565, L=1.30, s=1.0))
POD_MAT = dict(pod_top="paint", pod_side="paint2", pod_low="cladding", pod_belly="cladding",
               pod_nose="paint", tip_f="led_front", tip_r="led_accent", vent="void",
               pod_frame="cladding", pod_end="void")


def build_pod(tag, xc, yc, zc, L, s):
    def sec(x, ky=1.0, kz=1.0, dz=0.0):
        return [(x, yc + y * s * ky, zc + dz + z * s * kz) for (y, z) in POD_SEC]
    h = L / 2
    S = [sec(xc + h, 0.13, 0.40, 0.025 * s), sec(xc + h - 0.34 * s), sec(xc + 0.28 * s),
         sec(xc - 0.28 * s), sec(xc - h + 0.14 * s, 0.97, 0.97), sec(xc - h, 0.80, 0.78, 0.012 * s)]

    def pod_panel(i, j):
        if i == 0:
            return "pod_nose" if j in (7, 0, 1, 2, 6) else "pod_low"
        if j == 4:
            return "pod_belly"
        if j in (3, 5):
            return "pod_low"
        return "pod_side" if j in (2, 6) else "pod_top"

    K.build_body(S, pod_panel, POD_MAT, 1.0, 1.0, name="pod." + tag,
                 front=dict(kind="flat", panel="tip_" + tag),
                 rear=dict(center=(xc - h, yc, zc + 0.012 * s), depth=0.08 * s, band=0.022 * s,
                           frame="pod_frame", inner="pod_end", reach=0.05 * s),
                 recesses=[(2, 4, 0.022 * s, 0.03, "vent", "pod_belly")],
                 subdiv=1, wrap=True, project=False)
    zb = zc - 0.14 * s

    # the emitter: a collar under the pod, a glowing ring on its lip, vanes over a core
    ring = [(xc + 0.25 * s, yc, zb), (xc + 0.17 * s, yc + 0.098 * s, zb),
            (xc - 0.17 * s, yc + 0.098 * s, zb), (xc - 0.25 * s, yc, zb),
            (xc - 0.17 * s, yc - 0.098 * s, zb), (xc + 0.17 * s, yc - 0.098 * s, zb)]
    g = Geo()
    g.sweep(ring, [(-0.013, -0.030), (0.013, -0.030), (0.013, 0.004), (-0.013, 0.004)],
            closed=True)
    for k in range(6):                                  # clamps on the collar
        a, b = V3(ring[k]), V3(ring[(k + 1) % 6])
        c = a.lerp(b, 0.5)
        d = (b - a).normalized()
        o = V3((d.y, -d.x, 0))
        g.box(c + V3((0, 0, -0.012)), (0.05, 0.034, 0.03),
              rot=Matrix(((d.x, o.x, 0), (d.y, o.y, 0), (0, 0, 1))))
    g.obj("pod.collar." + tag, "rim", bevel=0.003, mirror=True)
    g = Geo()
    g.sweep(ring, [(-0.017, -0.048), (0.017, -0.048), (0.017, -0.030), (-0.017, -0.030)],
            closed=True)
    g.obj("pod.ring." + tag, "emitter", mirror=True)
    g = Geo()
    g.box((xc, yc, zb + 0.024), (0.47 * s, 0.17 * s, 0.004))
    g.obj("pod.core." + tag, "emitter_core", mirror=True)
    g = Geo()
    zv = zb + 0.004
    g.louvers((xc + 0.225 * s, yc - 0.085 * s, zv), (xc - 0.225 * s, yc - 0.085 * s, zv),
              (xc - 0.225 * s, yc + 0.085 * s, zv), (xc + 0.225 * s, yc + 0.085 * s, zv),
              9, 0.03, 0.004, rad(32), out=(0, 0, -1), margin=0.03)
    g.box((xc, yc, zv - 0.004), (0.50 * s, 0.014, 0.022))
    g.obj("pod.vanes." + tag, "grille", bevel=0.0015, mirror=True)

    # the skid, folded up beside the emitter, on two struts
    ys = yc + 0.168 * s
    g = Geo()
    g.sweep([(xc + 0.40 * s, ys, zb + 0.045), (xc + 0.33 * s, ys, zb - 0.02),
             (xc - 0.33 * s, ys, zb - 0.02), (xc - 0.40 * s, ys, zb + 0.045)],
            [(-0.013, -0.009), (0.013, -0.009), (0.013, 0.009), (-0.013, 0.009)],
            up=(0, 1, 0))
    for x in (xc + 0.2 * s, xc - 0.2 * s):
        g.box((x, ys - 0.012, zb + 0.012), (0.03, 0.02, 0.06))
        g.lathe([(-0.02, 0.002), (-0.02, 0.016), (0.02, 0.016), (0.02, 0.002)], 8,
                xf=Matrix.Translation((x, ys - 0.012, zb + 0.04)))
    g.obj("pod.skid." + tag, "rim_bright", bevel=0.003, mirror=True)

    # thruster in the pod's stern
    g = Geo()
    g.box((xc - h + 0.07 * s, yc, zc + 0.012 * s), (0.006, 0.20 * s, 0.045 * s))
    g.obj("pod.jet." + tag, "thrust", mirror=True)
    g = Geo()
    for k in (-1, 0, 1):
        g.box((xc - h + 0.045 * s, yc + k * 0.075 * s, zc + 0.012 * s), (0.06 * s, 0.008, 0.11 * s))
    g.obj("pod.jetvanes." + tag, "grille", mirror=True)


def pod_ribs():
    """Fine ribbing on the housings: on the pods as built, seen from the side."""
    parts = [ob for ob in K.CAR.objects if ob.name.startswith("pod.") and ob.type == 'MESH'
             and ob.name.split(".")[1] in ("f", "r")]
    g = Geo()
    for tag, p in PODS.items():
        xc, zc, L, s = p["xc"], p["zc"], p["L"], p["s"]
        x0, x1 = xc + L / 2 - 0.36 * s, xc - L / 2 + 0.16 * s
        n = int((x0 - x1) / 0.05)
        for k in range(7):
            z = zc + (0.038 - k * 0.0215) * s
            rib(g, [(x0 + (x1 - x0) * i / n - 0.03 * k * s * (1 if i == 0 else 0), z)
                    for i in range(n + 1)], 'y', 0.009, 0.005, parts)
    g.obj("pod.ribs", "cladding", mirror=True)
    g = Geo()                                           # emitter numbers on the pods' noses
    for side in (1, -1):
        for k, p in enumerate(PODS.values()):
            text_on_body(g, "E%d" % (2 * k + (1 if side > 0 else 2)), 0.062 * p["s"],
                         p["xc"] + p["L"] / 2 - 0.235 * p["s"], p["zc"] + 0.012 * p["s"], side,
                         objs=parts)
    g.obj("pod.stencils", "stencil")


# ---------------------------------------------------------------------------------------
# details
# ---------------------------------------------------------------------------------------
FIN_BASE, FIN_UP = V3((0, 0.66, 1.10)), V3((0, sin(rad(24)), cos(rad(24))))
FIN_T = 0.44
FIN = [(-1.70, 0.0), (-2.30, FIN_T), (-2.64, FIN_T), (-2.665, FIN_T - 0.09), (-2.60, 0.20),
       (-2.52, 0.0)]


def fin_pt(a, t, off=0.0, side=1):
    """A point of the fin's plane, off toward the outside."""
    n = V3((1, 0, 0)).cross(FIN_UP).normalized()        # inboard and up
    p = FIN_BASE + V3((a, 0, 0)) + FIN_UP * t - n * off
    return V3((p.x, side * p.y, p.z))


def fin_half(t):
    return (0.034 + (0.012 - 0.034) * t / FIN_T) / 2


def build_details():
    P = PT
    # ---- the chine blade: a bright knife edge from the prow to the stern, lit at both ends
    xs = [2.42 - 0.05 * k for k in range(98)]
    pts = [chine(x) for x in xs]
    pts = [p + V3((0, 0.003, -0.004)) for p in pts if p is not None]
    sec = [(-0.007, -0.004), (0.007, -0.004), (0.007, 0.004), (-0.007, 0.004)]
    nf = 17
    g = Geo()
    g.sweep(pts[nf - 1:-6], sec, up=(0, 1, 0))
    g.obj("chine.blade", "rim_bright", mirror=True)
    g = Geo()
    lit = [(-0.009, -0.005), (0.009, -0.005), (0.009, 0.005), (-0.009, 0.005)]
    g.sweep(pts[:nf], lit, up=(0, 1, 0))
    # the Meridian's face: the lit chine turns the corner and bridges the mouth as a blade
    g.sweep([pts[0], V3((2.505, 0.565, pts[0].z)), V3((2.60, 0.0, pts[0].z))],
            [(-0.012, -0.007), (0.012, -0.007), (0.012, 0.007), (-0.012, 0.007)], up=(0, 0, 1))
    g.obj("led.front", "led_front", mirror=True)
    g = Geo()
    g.sweep(pts[-7:], sec, up=(0, 1, 0))
    g.obj("led.chine.rear", "led_rear", mirror=True)

    # ---- the prow: a stem blade from the keel up to the light, lamp cells in the mouth
    zb = pts[0].z
    g = Geo()
    xm = FRONT_C.x - FRONT_D
    zt = zb - 0.012
    g.hexa([(xm - 0.01, -0.045, 0.60), (xm - 0.01, 0.045, 0.60), (2.598, 0.010, 0.548),
            (2.598, -0.010, 0.548), (xm - 0.01, -0.045, zt), (xm - 0.01, 0.045, zt),
            (2.612, 0.010, zt), (2.612, -0.010, zt)])
    g.obj("prow.stem", "paint", bevel=0.003)
    g = Geo()
    gl = Geo()
    gs = Geo()
    for k in range(3):
        y = 0.105 + 0.105 * k
        g.box((xm + 0.012, y, 0.705), (0.03, 0.092, 0.052))
        gl.box((xm + 0.029, y, 0.705), (0.006, 0.074, 0.034))
    gs.box((xm + 0.006, 0.215, 0.853), (0.012, 0.29, 0.016))    # a sensor slit over the blade
    g.louvers((xm + 0.02, 0.06, 0.612), (xm + 0.02, 0.06, 0.66), (xm + 0.02, 0.31, 0.66),
              (xm + 0.02, 0.31, 0.612), 3, 0.03, 0.004, rad(25), out=(1, 0, 0), margin=0.1)
    g.obj("prow.cells", "gloss_black", bevel=0.003, mirror=True)
    gl.obj("prow.lamps", "lamp", mirror=True)
    gs.obj("prow.sensor", "keel_led", mirror=True)

    # ---- fine ribbing on the lower hull, parallel to the chine
    g = Geo()
    xr = [1.96 - 0.06 * k for k in range(73)]
    for k in range(7):
        d = 0.045 + 0.030 * k
        rib(g, [(x, chine(x).z - d) for x in xr[k:len(xr) - k] if chine(x) is not None],
            'y', 0.010, 0.006)
    g.obj("hull.ribs", "cladding", mirror=True)
    # ---- ribs across the deck, between the fins
    g = Geo()
    for k in range(8):
        x = -2.04 - 0.048 * k
        rib(g, [(x, -0.50 + 0.04 * i) for i in range(26)], 'z', 0.012, 0.007)
    g.obj("deck.ribs", "cladding")

    # ---- keel blade and its light
    g = Geo()
    keel = [(2.30, 0.50), (1.85, 0.335), (-1.55, 0.335), (-1.95, 0.50), (-1.2, 0.46),
            (1.3, 0.46)]
    g.prism([(x, -0.014, z) for (x, z) in keel], (0, 0.028, 0))
    g.obj("keel", "paint2", bevel=0.004)
    g = Geo()
    g.box((0.15, 0, 0.3315), (3.30, 0.018, 0.009))
    g.obj("led.keel", "keel_led")
    # ---- strakes under the stern's kick-up
    g = Geo()
    for y, dz in ((0.18, 0.0), (0.40, 0.04)):
        g.prism([(-1.75, y - 0.007, 0.50 + dz), (-2.515, y - 0.007, 0.66 + dz),
                 (-2.54, y - 0.007, 0.50), (-2.22, y - 0.007, 0.44), (-1.92, y - 0.007, 0.44)],
                (0, 0.014, 0))
    g.obj("strakes", "paint2", bevel=0.003, mirror=True)

    # ---- belly: cross ribs, conduits from the keel to each emitter, two hatches
    def belly(y):
        return 0.42 + 0.05 * abs(y) / 0.66

    g = Geo()
    for k in range(12):
        x = 0.70 - 0.11 * k
        g.hexa([(x + 0.012, 0.05, belly(0.05) - 0.012), (x - 0.012, 0.05, belly(0.05) - 0.012),
                (x - 0.012, 0.60, belly(0.60) - 0.012), (x + 0.012, 0.60, belly(0.60) - 0.012),
                (x + 0.016, 0.05, belly(0.05) + 0.004), (x - 0.016, 0.05, belly(0.05) + 0.004),
                (x - 0.016, 0.60, belly(0.60) + 0.004), (x + 0.016, 0.60, belly(0.60) + 0.004)])
    g.obj("belly.ribs", "cladding", mirror=True)
    g = Geo()
    gh = Geo()
    for tag, p in PODS.items():
        for dx in (-0.12, 0.12):
            x = p["xc"] + dx
            g.tube((x, 0.012, 0.405), (x, p["yc"] - 0.16 * p["s"], 0.43), 0.02, 10)
            g.box((x, 0.30, belly(0.30) - 0.02), (0.07, 0.03, 0.05))
        gh.hexa([(p["xc"] + 0.24, 0.10, belly(0.10) - 0.006), (p["xc"] - 0.24, 0.10, belly(0.10) - 0.006),
                 (p["xc"] - 0.24, 0.46, belly(0.46) - 0.006), (p["xc"] + 0.24, 0.46, belly(0.46) - 0.006),
                 (p["xc"] + 0.24, 0.10, belly(0.10) + 0.004), (p["xc"] - 0.24, 0.10, belly(0.10) + 0.004),
                 (p["xc"] - 0.24, 0.46, belly(0.46) + 0.004), (p["xc"] + 0.24, 0.46, belly(0.46) + 0.004)])
    g.obj("belly.conduits", "rim", bevel=0.003, mirror=True)
    gh.obj("belly.hatches", "paint2", bevel=0.003, mirror=True)

    # ---- twin canted fins, low, on the deck's edges
    g = Geo()
    plate(g, FIN_BASE, (1, 0, 0), FIN_UP, FIN, 0.034, 0.012, FIN_T)
    g.obj("fins", "paint", bevel=0.003, mirror=True)
    g = Geo()
    g.sweep([fin_pt(-2.525, 0.02, 0), fin_pt(-2.605, 0.20, 0), fin_pt(-2.67, FIN_T - 0.09, 0)],
            [(-0.016, -0.005), (0.016, -0.005), (0.016, 0.007), (-0.016, 0.007)],
            up=(-1, 0, 0))
    g.obj("led.fin", "led_rear", mirror=True)
    g = Geo()
    plate(g, FIN_BASE, (1, 0, 0), FIN_UP,
          [(-1.68, -0.012), (-2.305, FIN_T + 0.012), (-2.36, FIN_T + 0.012), (-1.755, -0.012)],
          0.040, 0.018, FIN_T)
    g.obj("fin.edge", "paint2", bevel=0.002, mirror=True)
    g = Geo()
    gt = Geo()
    gm = Geo()
    for side in (1, -1):
        for a0, a1 in ((0.0, 0.45), (0.55, 1.0)):       # the rudder's cut line
            q0, q1 = fin_pt(-2.47, 0.06, 0.018, side), fin_pt(-2.47, FIN_T - 0.04, 0.008, side)
            g.sweep([q0.lerp(q1, a0), q0.lerp(q1, a1)],
                    [(-0.003, -0.002), (0.003, -0.002), (0.003, 0.002), (-0.003, 0.002)],
                    up=(1, 0, 0))
        up = V3((0, side * FIN_UP.y, FIN_UP.z))
        text_flat(gt, "KM-404", 0.078, fin_pt(-2.285, 0.235, fin_half(0.235) + 0.0025, side),
                  (-side, 0, 0), up, spacing=1.08)
        text_flat(gt, "MERIDIAN", 0.024, fin_pt(-2.44, FIN_T - 0.06,
                                                fin_half(FIN_T - 0.06) + 0.002, side),
                  (-side, 0, 0), up, spacing=1.3)
        text_flat(gt, "404", 0.12, fin_pt(-2.33, 0.25, -fin_half(0.25) - 0.0025, side),
                  (side, 0, 0), up, spacing=1.1)
        gm.sweep([fin_pt(-2.34, FIN_T - 0.02, 0.011, side),
                  fin_pt(-2.47, FIN_T - 0.02, 0.011, side)],
                 [(-0.006, -0.003), (0.006, -0.003), (0.006, 0.003), (-0.006, 0.003)], up=up)
    g.obj("fin.lines", "void")
    gt.obj("fin.code", "stencil")
    gm.obj("led.fin.marker", "led_accent")

    # ---- stern: a light bar round the top of the mouth, two banks of slanted slot
    # thrusters either side of a stern post
    half = [P["P7"][n] for n in "KSMR"]
    hp = [band_point(p, REAR_C, BAND_W * 0.5, 0.0) for p in half]
    path = hp + [hp[-1].lerp(band_point(P["P7"]["C"], REAR_C, BAND_W * 0.5, 0.0), 0.45)]
    g = Geo()                                           # the bar stops for the maker's name
    g.sweep(path, [(-0.007, -0.006), (0.007, -0.006), (0.007, 0.004), (-0.007, 0.004)],
            up=(-1, 0, 0))
    g.obj("led.rear", "led_rear", mirror=True)
    xt = REAR_C.x + TAIL_D
    g = Geo()
    gg = Geo()
    for k in range(3):
        y = 0.265 + 0.155 * k
        sh = Matrix.Identity(4)
        sh[1][2] = 0.30                                 # lean outward toward the top
        xf = Matrix.Translation((xt, y, 0.905 + 0.006 * k)) @ sh @ Matrix.Rotation(pi / 2, 4, 'Z') \
            @ Matrix.Diagonal((0.66, 1.0, 1.38 - 0.07 * k, 1.0))
        g.lathe([(0.0, 0.082), (0.105, 0.082), (0.118, 0.074), (0.118, 0.066), (0.0, 0.066)],
                4, a0=pi / 4, a1=pi / 4 + 2 * pi, xf=xf)
        gg.lathe([(0.035, 0.002), (0.035, 0.066), (0.04, 0.066), (0.04, 0.002)],
                 4, a0=pi / 4, a1=pi / 4 + 2 * pi, xf=xf)
    g.obj("thrusters", "rim", bevel=0.003, mirror=True)
    gg.obj("thruster.glow", "thrust", mirror=True)
    g = Geo()                                           # the stern post between the banks
    g.hexa([(xt + 0.01, -0.13, 0.76), (xt + 0.01, 0.13, 0.76), (-2.53, 0.03, 0.80),
            (-2.53, -0.03, 0.80), (xt + 0.01, -0.13, 1.07), (xt + 0.01, 0.13, 1.07),
            (-2.53, 0.03, 1.05), (-2.53, -0.03, 1.05)])
    g.obj("stern.post", "paint2", bevel=0.004)
    g = Geo()
    g.box((-2.533, 0, 0.925), (0.008, 0.022, 0.21))
    g.obj("led.post", "led_rear")
    g = Geo()
    text_flat(g, "K E S T R E L", 0.026, (-2.5085, 0, 1.143), (0, -1, 0), (0, 0, 1), spacing=1.2)
    g.obj("led.name", "led_rear")

    build_steps()
    build_surface_details()


def build_steps():
    """The boarding steps: a ribbed tread hinged on the lower hull under each door, out on
    the left side and stowed flat against the hull on the right."""
    HY, HZ = 0.705, 0.52                                # the hinge line on the hull's flank
    fl = V3((0, 0.33, 0.385)).normalized()              # up the flank
    fn = V3((0, fl.z, -fl.y))                           # out of it
    W = 0.33
    gt, gr, gl, gd, gh = Geo(), Geo(), Geo(), Geo(), Geo()
    for xc in (0.36, -0.52):
        x0, x1 = xc - 0.30, xc + 0.30
        for side in (1, -1):
            o = V3((0, side * HY, HZ))
            if side > 0:                                # out: a level tread, two links
                ev, ew = V3((0, 1, 0)), V3((0, 0, 1))
                slab(gt, o, ev, ew, x0, x1, 0.0, W, -0.022, 0.0)
                for k in range(5):
                    v = 0.045 + 0.058 * k
                    slab(gr, o, ev, ew, x0 + 0.03, x1 - 0.03, v, v + 0.022, 0.0, 0.006)
                slab(gl, o, ev, ew, x0 + 0.02, x1 - 0.02, W - 0.004, W + 0.006, -0.018, -0.004)
                for x in (x0 + 0.006, x1 - 0.006):      # a stringer at each end
                    gh.prism([(x - 0.006, HY + 0.012, HZ), (x - 0.006, HY + W - 0.03, HZ),
                              V3((x - 0.006, HY, HZ)) + fl * 0.23 + fn * 0.012], (0.012, 0, 0))
                # the bay it folded out of
                slab(gd, o + fn * 0.009, fl, fn, x0 - 0.01, x1 + 0.01, 0.012, W + 0.01, 0.0, 0.003)
            else:                                       # stowed: flat on the flank
                ev, ew = V3((0, side * fl.y, fl.z)), V3((0, side * fn.y, fn.z))
                slab(gt, o + ew * 0.009, ev, ew, x0, x1, 0.012, W, 0.0, 0.02)
                for k in range(2):
                    v = 0.07 + 0.17 * k
                    slab(gr, o + ew * 0.029, ev, ew, x0 + 0.03, x1 - 0.03, v, v + 0.02, 0.0, 0.004)
            for x in (x0 + 0.07, x1 - 0.07):            # hinge knuckles
                gh.lathe([(-0.035, 0.002), (-0.035, 0.014), (0.035, 0.014), (0.035, 0.002)], 8,
                         xf=Matrix.Translation((x, side * (HY + 0.004), HZ - 0.006))
                         @ Matrix.Rotation(pi / 2, 4, 'Z'))
    gt.obj("step.tread", "paint2", bevel=0.004)
    gr.obj("step.grip", "cladding", bevel=0.001)
    gl.obj("led.step", "led_front")
    gd.obj("step.bay", "cladding")
    gh.obj("step.links", "rim", bevel=0.002)


def build_surface_details():
    # ---- lettering: the model on the front door, a registration by the nose and on the roof
    g = Geo()
    for side in (1, -1):
        text_on_body(g, "MERIDIAN", 0.062, 0.24, 0.955, side, spacing=1.25)
        text_on_body(g, "KA 4-404", 0.03, 1.72, 0.895, side, spacing=1.15)
    text_on_body(g, "KM-404", 0.15, -0.63, 0.0, 1, proj='z', spacing=1.1)
    g.obj("lettering", "stencil")
    # ---- a groove under the glass from the windshield's corner to the fin, a release
    # slot on each door, a charge port outline, hood sensor slits
    g = Geo()
    ribbon(g, [(1.22, 1.008), (0.80, 1.035), (-0.30, 1.055), (-1.28, 1.065), (-1.90, 1.095)],
           'y', 0.007)
    ribbon(g, [(-0.07, 1.012), (-0.25, 1.016)], 'y', 0.018)
    ribbon(g, [(-1.04, 1.022), (-1.22, 1.026)], 'y', 0.018)
    hexa = [(-1.62 + 0.05 * cos(rad(a)), 1.01 + 0.036 * sin(rad(a))) for a in range(0, 360, 60)]
    ribbon(g, hexa, 'y', 0.004, closed=True)
    for k in range(4):
        x = 1.30 - 0.05 * k
        ribbon(g, [(x, 0.66), (x - 0.03, 0.78)], 'z', 0.016)
    g.obj("lines", "void", mirror=True)
    # ---- the visor: sensor slits and a status light at its front edge
    g = Geo()
    for k in range(3):
        x = 1.86 - 0.085 * k
        ribbon(g, [(x, 0.05 + 0.022 * k), (x - 0.012, 0.26 + 0.05 * k)], 'z', 0.012)
    g.obj("visor.slits", "grille", mirror=True)
    g = Geo()
    ribbon(g, [(1.985, -0.14), (1.985, 0.14)], 'z', 0.010)
    g.obj("led.visor", "keel_led")
    # ---- amber markers on the shoulder, warning stripes by the stern
    g = Geo()
    ribbon(g, [(1.05, 0.985), (0.93, 0.992)], 'y', 0.012)
    g.obj("led.marker", "led_accent", mirror=True)
    g = Geo()
    for k in range(5):
        x = -2.02 - 0.045 * k
        ribbon(g, [(x, 1.06), (x - 0.025, 1.025)], 'y', 0.013)
    g.obj("decals", "stencil", mirror=True)
    # ---- a sensor blade on the roof, pitot pins on the nose, studs on the panels
    zr = on_body(-1.04, 0.0, 'z')[0].z
    g = Geo()
    g.prism([(-0.93, -0.006, zr - 0.008), (-1.08, -0.006, zr + 0.075), (-1.13, -0.006, zr + 0.075),
             (-1.16, -0.006, zr - 0.012)], (0, 0.012, 0))
    g.obj("roof.blade", "paint2", bevel=0.002)
    g = Geo()
    gp = Geo()
    for y in (0.16, 0.34):
        loc, n = on_body(1.94, y, 'z')
        if loc is not None:
            stud(g, loc, n, [(-0.002, 0.001), (-0.002, 0.010), (0.0015, 0.010), (0.0015, 0.001)],
                 10)
    for (x, y) in ((2.30, 0.30), (1.62, 0.66), (0.40, 0.655), (-0.42, 0.50), (-1.06, 0.50),
                   (-1.60, 0.655), (-2.20, 0.62)):
        loc, n = on_body(x, y, 'z')
        if loc is not None:
            stud(gp, loc, n, [(-0.002, 0.001), (-0.002, 0.008), (0.002, 0.008), (0.002, 0.001)], 6)
    g.obj("sensors", "gloss_black", mirror=True)
    gp.obj("fasteners", "rim_bright", mirror=True)
    g = Geo()
    for y in (0.24,):
        g.sweep([(2.52, y, 0.925), (2.64, y, 0.925)],
                [(-0.004, -0.004), (0.004, -0.004), (0.004, 0.004), (-0.004, 0.004)])
    g.obj("pitot", "rim_bright", mirror=True)
    # ---- camera blades in place of mirrors
    g = Geo()
    g.hexa([(1.27, 0.84, 1.040), (1.09, 0.86, 1.050), (1.07, 1.03, 1.066), (1.17, 1.03, 1.060),
            (1.27, 0.84, 1.050), (1.09, 0.86, 1.064), (1.07, 1.03, 1.092), (1.17, 1.03, 1.084)])
    g.obj("camera.blades", "paint2", bevel=0.003, mirror=True)
    g = Geo()
    g.box((1.068, 0.99, 1.078), (0.004, 0.06, 0.016))
    g.obj("camera.lens", "gloss_black", mirror=True)


# ---------------------------------------------------------------------------------------
# interior: four seats, a yoke, a screen across the dash, a console down the middle
# ---------------------------------------------------------------------------------------
def build_interior():
    g = Geo()
    g.box((-0.10, 0, 0.495), (2.70, 1.30, 0.02))
    g.prism([(-1.45, -0.60, 0.50), (-1.45, 0.60, 0.50), (-1.45, 0.84, 0.80), (-1.45, 0.82, 1.08),
             (-1.45, 0.55, 1.14), (-1.45, -0.55, 1.14), (-1.45, -0.82, 1.08),
             (-1.45, -0.84, 0.80)], (0.04, 0, 0))
    g.prism([(1.28, -0.70, 0.50), (1.28, -0.70, 1.03), (0.96, -0.70, 1.045),
             (0.80, -0.70, 0.97), (0.86, -0.70, 0.72), (0.86, -0.70, 0.50)], (0, 1.40, 0))
    g.box((-0.25, 0, 0.60), (2.10, 0.17, 0.20))
    g.box((-1.70, 0, 1.13), (0.52, 1.36, 0.02))
    for sy in (1, -1):                                  # door cards under the glass
        g.prism([(1.0, sy * 0.63, 0.50), (1.0, sy * 0.69, 0.50), (1.0, sy * 0.83, 0.72),
                 (1.0, sy * 0.84, 1.02), (1.0, sy * 0.77, 1.02), (1.0, sy * 0.74, 0.80)],
                (-2.45, 0, 0))
    g.obj("interior.tub", "interior", bevel=0.006)
    g = Geo()
    tilt = Matrix.Rotation(rad(-20), 3, 'Y')
    for x0 in (0.25, -0.80):
        for y in (0.36, -0.36):
            g.box((x0, y, 0.63), (0.52, 0.44, 0.20))
            g.box((x0 - 0.36, y, 1.04), (0.11, 0.42, 0.64), rot=tilt)
            g.box((x0 - 0.50, y, 1.42), (0.07, 0.22, 0.15), rot=tilt)
            for s in (-1, 1):
                g.box((x0, y + s * 0.22, 0.70), (0.48, 0.05, 0.16))
                g.box((x0 - 0.34, y + s * 0.215, 1.00), (0.14, 0.05, 0.50), rot=tilt)
    g.obj("interior.seats", "seat", bevel=0.012, segs=3)
    # a yoke, not a wheel
    g = Geo()
    yk = Matrix.Translation((0.70, 0.36, 1.02)) @ Matrix.Rotation(rad(-62), 4, 'Y')
    g.box((0, 0, 0), (0.03, 0.30, 0.035), xf=yk)
    for s in (-1, 1):
        g.box((0, s * 0.15, 0.045), (0.035, 0.035, 0.12), xf=yk)
    g.box((0.80, 0.36, 0.99), (0.20, 0.05, 0.05))
    g.obj("interior.yoke", "interior", bevel=0.004)
    g = Geo()
    scr = Matrix.Rotation(rad(-24), 3, 'Y')
    g.box((0.865, 0.0, 1.035), (0.008, 1.10, 0.085), rot=scr)
    g.box((0.20, 0.0, 0.703), (0.34, 0.11, 0.006))
    g.box((-0.26, 0.0, 0.95), (0.008, 0.26, 0.15), rot=scr)      # the rear cabin's screen
    g.obj("interior.screens", "screen")
    g = Geo()
    g.box((-0.245, 0.0, 0.82), (0.03, 0.10, 0.26))
    g.obj("interior.post", "interior", bevel=0.004)
    g = Geo()                                           # a warm light strip under each rail
    g.box((-0.38, 0.555, 1.578), (1.45, 0.014, 0.008))
    g.obj("led.cabin", "cabin_led", mirror=True)
    # power cell under the rear glass: a ribbed block with glowing seams
    g = Geo()
    ge = Geo()
    g.prism([(-1.50, -0.40, 1.14), (-1.50, -0.40, 1.20), (-1.62, -0.40, 1.20),
             (-1.92, -0.40, 1.16), (-1.92, -0.40, 1.14)], (0, 0.80, 0))
    for k in range(8):
        y = -0.35 + 0.10 * k
        g.prism([(-1.51, y - 0.012, 1.20), (-1.62, y - 0.012, 1.214), (-1.92, y - 0.012, 1.174),
                 (-1.92, y - 0.012, 1.16), (-1.62, y - 0.012, 1.20)], (0, 0.024, 0))
    for y in (-0.25, 0.25):
        ge.prism([(-1.53, y - 0.03, 1.2025), (-1.61, y - 0.03, 1.2025), (-1.61, y + 0.03, 1.2025),
                  (-1.53, y + 0.03, 1.2025)], (0, 0, 0.003))
    g.obj("power.cell", "rim", bevel=0.003)
    ge.obj("power.glow", "emitter_core")


# ---------------------------------------------------------------------------------------
# views and the build
# ---------------------------------------------------------------------------------------
K.VIEWS["hero"].update(dir=(1.0, 0.80, 0.23), focus=(1.3, 0.6, 0.9), fstop=11.0)
K.VIEWS["rear"].update(focus=(-1.3, -0.6, 0.9), fstop=11.0)
K.VIEWS.update(
    pod=dict(dir=(0.6, 1.0, -0.10), lens=85, target=(1.4, 0.8, 0.55), dist=2.8),
    nose=dict(dir=(1.0, 0.45, 0.10), lens=85, target=(2.2, 0.2, 0.8), dist=3.4),
    tail=dict(dir=(-1.0, -0.45, 0.16), lens=85, target=(-2.3, -0.3, 0.95), dist=3.8),
    cabin=dict(dir=(0.5, 1.0, 0.40), lens=85, target=(-0.3, 0.3, 1.2), dist=4.2),
    step=dict(dir=(0.35, 1.0, 0.18), lens=85, target=(-0.1, 0.9, 0.7), dist=3.2),
)


def main():
    K.materials(paint=(0.006, 0.040, 0.25), paint_finish="pearl",
                paint2=(0.030, 0.034, 0.042), paint2_finish="satin", dust_amount=0.12,
                led_front=(0.72, 0.95, 1.0), led_accent=(1.0, 0.42, 0.04),
                seat=(0.52, 0.30, 0.13), screen=(0.12, 0.75, 0.9), decal=(0.05, 0.055, 0.065))
    K.emit("emitter", (0.10, 0.80, 1.0), 110.0)
    K.emit("emitter_core", (0.08, 0.55, 1.0), 26.0)
    K.emit("thrust", (0.30, 0.55, 1.0), 26.0)
    K.emit("keel_led", (0.10, 0.80, 1.0), 45.0)
    K.pbr("stencil", (0.62, 0.66, 0.70), 0.0, 0.55)
    # the facets that face the sky: coated, so the studio's top light is a sheen in them and
    # not a white slab; the roof smoked, so that light does not flood the cabin
    K.pbr("glass_coat", (0.30, 0.33, 0.36), 0.0, 0.0, **{"Transmission Weight": 1.0, "IOR": 1.12})
    K.pbr("glass_smoke", (0.045, 0.05, 0.06), 0.0, 0.0, **{"Transmission Weight": 1.0, "IOR": 1.12})
    K.emit("cabin_led", (1.0, 0.82, 0.60), 40.0)
    K.pbr("bellyplate", (0.055, 0.06, 0.068), 0.55, 0.5)
    K.pbr("visor", (0.016, 0.017, 0.020), 0.0, 0.65, **{"Specular IOR Level": 0.06})
    build_hull()
    K.log("hull")
    for tag, p in PODS.items():
        build_pod(tag, **p)
    pod_ribs()
    K.log("pods")
    build_details()
    build_interior()
    K.log("details")
    K.shoot(extra=dict(view="under", size=(1000, 400)))


main()
