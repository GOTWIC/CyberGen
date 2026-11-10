"""Kestrel Aerodyne Dart: a two-seat hover coupe (both names made up), on vehicles/carkit.py.

Run (always through the wrapper, one Blender job at a time on this machine):
    vehicles/blender.sh vehicles/cars/kestrel_dart.py --out DIR --preview
    vehicles/blender.sh vehicles/cars/kestrel_dart.py --out DIR --sheet

The first Kestrel, so it sets the family's cues (see docs/progress/AG18/kestrel_dart):
a hull folded along one knife chine from the prow's point to the stern, flat glass facets
over it, a dark ribbed lower hull under it, an emitter pod at each corner (an eight-sided
ribbed nacelle with a blade nose, a glowing ring and vanes under it, a skid folded beside
it), a keel light blade, twin canted fins and a row of slanted thruster slots.
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
#        C top centerline, R hood crease / roof edge, M the fold in the side glass,
#        S shoulder (glass base), K the chine (widest, a knife edge), L lower hull edge, B keel
ORDER = ["P0", "P1", "P2", "P3", "P4", "P5", "P6", "P7"]
PT = {}
T = {
    "P0": [(2.25, 0, .705), (2.25, .02, .705), None, (2.245, .04, .70), (2.235, .055, .68),
           (2.245, .03, .615), (2.25, 0, .60)],
    "P1": [(1.80, 0, .805), (1.80, .20, .795), None, (1.78, .37, .775), (1.76, .45, .715),
           (1.80, .26, .53), (1.80, 0, .47)],
    "P2": [(1.15, 0, .925), (1.12, .38, .92), (1.11, .52, .90), (1.10, .61, .875),
           (1.08, .69, .76), (1.15, .44, .50), (1.15, 0, .41)],
    "P3": [(0.0, 0, 1.365), (-.04, .44, 1.36), (-.02, .69, 1.27), (0, .78, .985),
           (0, .88, .80), (0, .54, .47), (0, 0, .40)],
    "P4": [(-.55, 0, 1.405), (-.55, .45, 1.395), (-.55, .70, 1.305), (-.55, .80, 1.01),
           (-.55, .90, .83), (-.55, .55, .46), (-.55, 0, .40)],
    "P5": [(-1.0, 0, 1.36), (-1.02, .44, 1.345), (-1.04, .70, 1.258), (-1.05, .80, 1.03),
           (-1.05, .91, .86), (-1.0, .55, .47), (-1.0, 0, .40)],
    "P6": [(-1.8, 0, 1.09), (-1.8, .50, 1.075), (-1.8, .66, 1.05), (-1.8, .76, 1.00),
           (-1.8, .88, .91), (-1.8, .54, .60), (-1.8, 0, .50)],
    "P7": [(-2.2, 0, 1.02), (-2.2, .50, 1.005), (-2.19, .62, .992), (-2.18, .70, .96),
           (-2.15, .80, .905), (-2.19, .50, .68), (-2.2, 0, .60)],
}
for _k in ("P0", "P1"):                     # the fold starts at the windshield's corner
    T[_k][2] = tuple((u + v) / 2 for u, v in zip(T[_k][1], T[_k][3]))
REAR_C = V3((-2.2, 0, 0.82))
TAIL_D, BAND_W = 0.14, 0.04

PMAT = dict(nose="paint", hood="paint", fender="paint", door="paint", quarter="paint",
            roof="paint", deck="paint2", lower="paint2", belly="underbody",
            glass_ws="glass", glass_roof="glass", glass_side="glass", glass_rear="glass",
            trim="gloss_black", prow="gloss_black", visor="visor", lightband="gloss_black",
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
    if j in (1, 2):
        return "hood" if i < 2 else "glass_side" if i <= 4 else "quarter"
    return "fender" if i < 3 else "door" if i <= 4 else "quarter"


def line_crease(i, j):
    if j == 0:
        return 1.0 if i < 2 else 0.0        # the nose's ridge; the glass is one plane
    if j == 2:
        return 1.0 if i >= 2 else 0.0       # the fold, from the windshield's corner back
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
        front=dict(kind="flat", panel="prow"),
        rear=dict(center=REAR_C, depth=TAIL_D, band=BAND_W, band_panel="lightband",
                  band_lines=4, frame="tail_frame", inner="tail"),
        glass=[("glass_ws", 0.032), ("glass_roof", 0.03), ("glass_side", 0.028),
               ("glass_rear", 0.035)],
        subdiv=SUBDIV)


# ---------------------------------------------------------------------------------------
# helpers of this car
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
    """A raised rib on the body (or on objs) along a path given in projection (its samples
    as given)."""
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


# ---------------------------------------------------------------------------------------
# emitter pods
# ---------------------------------------------------------------------------------------
POD_SEC = [(-.11, .14), (.09, .14), (.19, .05), (.19, -.06), (.13, -.14), (-.13, -.14),
           (-.19, -.06), (-.19, .05)]
PODS = dict(f=dict(xc=1.20, yc=0.805, zc=0.522, L=1.08, s=0.86),
            r=dict(xc=-1.36, yc=0.80, zc=0.537, L=1.40, s=1.0))
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
        for k in range(3):                              # three short ribs on the top chamfer
            z = zc + (0.075 + k * 0.022) * s
            rib(g, [(xc + (0.30 - 0.6 * i / 12) * s, z) for i in range(13)], 'y', 0.008, 0.004,
                parts)
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
FIN_BASE, FIN_UP = V3((0, 0.60, 0.93)), V3((0, sin(rad(24)), cos(rad(24))))
FIN_T = 0.63
FIN = [(-1.00, 0.08), (-1.74, FIN_T), (-2.28, FIN_T), (-2.31, FIN_T - 0.11), (-2.23, 0.26),
       (-2.10, 0.0), (-1.20, 0.0)]


def fin_pt(a, t, off=0.0, side=1):
    """A point of the fin's plane, off toward the outside."""
    n = V3((1, 0, 0)).cross(FIN_UP).normalized()        # inboard and up
    p = FIN_BASE + V3((a, 0, 0)) + FIN_UP * t - n * off
    return V3((p.x, side * p.y, p.z))


def build_details():
    P = PT
    # ---- the chine blade: a bright knife edge from the prow to the stern, lit at both ends
    xs = [2.20 - 0.05 * k for k in range(88)]
    pts = [chine(x) for x in xs]
    pts = [p + V3((0, 0.003, -0.004)) for p in pts if p is not None]
    sec = [(-0.007, -0.004), (0.007, -0.004), (0.007, 0.004), (-0.007, 0.004)]
    nf = 17
    g = Geo()
    g.sweep(pts[nf - 1:-6], sec, up=(0, 1, 0))
    g.obj("chine.blade", "rim_bright", mirror=True)
    g = Geo()
    g.sweep(pts[:nf], [(-0.009, -0.005), (0.009, -0.005), (0.009, 0.005), (-0.009, 0.005)],
            up=(0, 1, 0))
    g.obj("led.front", "led_front", mirror=True)
    g = Geo()
    g.sweep(pts[-7:], sec, up=(0, 1, 0))
    g.obj("led.chine.rear", "led_rear", mirror=True)

    # ---- nose lamps: a dark slot on the nose flank with four lamp cells
    g = Geo()
    gl = Geo()
    def lamp_z(x):                                      # the middle of the nose's flank
        return chine(x).z + 0.028 + 0.035 * (1.74 - x)

    ribbon(g, [(x, lamp_z(x)) for x in (1.74, 1.60, 1.46, 1.32, 1.18)], 'y', 0.032, lift=0.001)
    for k in range(4):
        x = 1.705 - k * 0.135
        ribbon(gl, [(x, lamp_z(x)), (x - 0.095, lamp_z(x - 0.095))], 'y', 0.017, lift=0.0025)
    g.obj("nose.slot", "gloss_black", mirror=True)
    gl.obj("nose.lamps", "lamp", mirror=True)

    # ---- fine ribbing on the lower hull, parallel to the chine
    g = Geo()
    xr = [1.62 - 0.06 * k for k in range(61)]
    for k in range(7):
        d = 0.045 + 0.030 * k
        rib(g, [(x, chine(x).z - d) for x in xr[k:len(xr) - k] if chine(x) is not None],
            'y', 0.010, 0.006)
    g.obj("hull.ribs", "cladding", mirror=True)
    # ---- ribs across the deck, between the fins
    g = Geo()
    for k in range(8):
        x = -1.865 - 0.04 * k
        rib(g, [(x, -0.44 + 0.04 * i) for i in range(23)], 'z', 0.012, 0.007)
    g.obj("deck.ribs", "cladding")

    # ---- keel blade and its light
    g = Geo()
    keel = [(1.55, 0.44), (1.20, 0.325), (-1.30, 0.325), (-1.62, 0.47), (-1.0, 0.44),
            (1.0, 0.44)]
    g.prism([(x, -0.014, z) for (x, z) in keel], (0, 0.028, 0))
    g.obj("keel", "paint2", bevel=0.004)
    g = Geo()
    g.box((-0.05, 0, 0.3215), (2.42, 0.018, 0.009))
    g.obj("led.keel", "keel_led")
    # ---- strakes under the stern's kick-up
    g = Geo()
    for y, dz in ((0.16, 0.0), (0.38, 0.05)):
        g.prism([(-1.45, y - 0.007, 0.50 + dz), (-2.215, y - 0.007, 0.66 + dz),
                 (-2.24, y - 0.007, 0.50), (-1.92, y - 0.007, 0.435), (-1.62, y - 0.007, 0.435)],
                (0, 0.014, 0))
    g.obj("strakes", "paint2", bevel=0.003, mirror=True)

    # ---- twin canted fins
    g = Geo()
    plate(g, FIN_BASE, (1, 0, 0), FIN_UP, FIN, 0.034, 0.012, FIN_T)
    g.obj("fins", "paint", bevel=0.003, mirror=True)
    g = Geo()
    g.sweep([fin_pt(-2.105, 0.02, 0), fin_pt(-2.235, 0.26, 0), fin_pt(-2.315, FIN_T - 0.11, 0)],
            [(-0.016, -0.005), (0.016, -0.005), (0.016, 0.007), (-0.016, 0.007)],
            up=(-1, 0, 0))
    g.obj("led.fin", "led_rear", mirror=True)
    g = Geo()
    plate(g, FIN_BASE, (1, 0, 0), FIN_UP,
          [(-0.98, 0.065), (-1.745, FIN_T + 0.012), (-1.80, FIN_T + 0.012), (-1.05, 0.065)],
          0.040, 0.018, FIN_T)
    g.obj("fin.edge", "paint2", bevel=0.002, mirror=True)
    g = Geo()
    gt = Geo()
    gm = Geo()
    for side in (1, -1):
        for a0, a1 in ((0.0, 0.45), (0.55, 1.0)):       # the rudder's cut line
            pa = fin_pt(-2.02, 0.10, 0.02, side).lerp(fin_pt(-2.02, FIN_T - 0.04, 0.008, side), a0)
            pb = fin_pt(-2.02, 0.10, 0.02, side).lerp(fin_pt(-2.02, FIN_T - 0.04, 0.008, side), a1)
            g.sweep([pa, pb], [(-0.003, -0.002), (0.003, -0.002), (0.003, 0.002), (-0.003, 0.002)],
                    up=(1, 0, 0))
        up = V3((0, side * FIN_UP.y, FIN_UP.z))
        text_flat(gt, "KD-217", 0.105, fin_pt(-1.72, 0.30, 0.0145, side), (-side, 0, 0), up,
                  spacing=1.08)
        text_flat(gt, "DART", 0.034, fin_pt(-1.975, FIN_T - 0.085, 0.0105, side), (-side, 0, 0), up,
                  spacing=1.3)
        text_flat(gt, "217", 0.16, fin_pt(-1.86, 0.33, -0.0135, side), (side, 0, 0), up,
                  spacing=1.1)
        gm.sweep([fin_pt(-1.80, FIN_T - 0.02, 0.012, side),
                  fin_pt(-1.93, FIN_T - 0.02, 0.012, side)],
                 [(-0.006, -0.003), (0.006, -0.003), (0.006, 0.003), (-0.006, 0.003)], up=up)
    g.obj("fin.lines", "void")
    gt.obj("fin.code", "stencil")
    gm.obj("led.fin.marker", "led_accent")

    # ---- pylons: flat blades from under the chine to the pods
    g = Geo()
    g.hexa([(1.62, 0.36, 0.615), (0.86, 0.50, 0.615), (0.94, 0.80, 0.615), (1.44, 0.80, 0.615),
            (1.60, 0.36, 0.648), (0.88, 0.50, 0.648), (0.96, 0.80, 0.648), (1.42, 0.80, 0.648)])
    g.hexa([(-0.86, 0.60, 0.655), (-1.86, 0.60, 0.655), (-1.76, 0.94, 0.64), (-1.02, 0.94, 0.64),
            (-0.88, 0.60, 0.70), (-1.84, 0.60, 0.70), (-1.75, 0.93, 0.668), (-1.04, 0.93, 0.668)])
    g.obj("pylons", "paint2", bevel=0.004, mirror=True)

    # ---- stern: a light bar round the top of the mouth, slanted thruster slots in it
    half = [P["P7"][n] for n in "KSMR"]
    hp = [band_point(p, REAR_C, BAND_W * 0.5, 0.0) for p in half]
    path = hp + [hp[-1].lerp(band_point(P["P7"]["C"], REAR_C, BAND_W * 0.5, 0.0), 0.5)]
    g = Geo()                                           # the bar stops for the maker's name
    g.sweep(path, [(-0.007, -0.006), (0.007, -0.006), (0.007, 0.004), (-0.007, 0.004)],
            up=(-1, 0, 0))
    g.obj("led.rear", "led_rear", mirror=True)
    xt = REAR_C.x + TAIL_D
    g = Geo()
    gg = Geo()
    for k in range(4):
        y = 0.075 + 0.142 * k
        sh = Matrix.Identity(4)
        sh[1][2] = 0.38                                 # lean outward toward the top
        xf = Matrix.Translation((xt, y, 0.815)) @ sh @ Matrix.Rotation(pi / 2, 4, 'Z') \
            @ Matrix.Diagonal((0.62, 1.0, 1.12, 1.0))
        g.lathe([(0.0, 0.082), (0.105, 0.082), (0.118, 0.074), (0.118, 0.066), (0.0, 0.066)],
                4, a0=pi / 4, a1=pi / 4 + 2 * pi, xf=xf)
        gg.lathe([(0.035, 0.002), (0.035, 0.066), (0.04, 0.066), (0.04, 0.002)],
                 4, a0=pi / 4, a1=pi / 4 + 2 * pi, xf=xf)
    g.obj("thrusters", "rim", bevel=0.003, mirror=True)
    gg.obj("thruster.glow", "thrust", mirror=True)
    g = Geo()
    text_flat(g, "K E S T R E L", 0.026, (-2.2085, 0, 1.0), (0, -1, 0), (0, 0, 1), spacing=1.2)
    g.obj("led.name", "led_rear")

    build_surface_details()


def build_surface_details():
    # ---- lettering: the model on the door, a registration by the nose
    g = Geo()
    for side in (1, -1):
        text_on_body(g, "DART", 0.075, -0.30, 0.905, side, spacing=1.25)
        text_on_body(g, "KA 2-217", 0.03, 0.96, 0.832, side, spacing=1.15)
    g.obj("lettering", "stencil")
    # ---- door release slots, a charge port outline, hood sensor slits, a groove under
    # the glass from the windshield's corner to the fin
    g = Geo()
    ribbon(g, [(0.78, 0.867), (0.0, 0.945), (-0.55, 0.97), (-1.05, 0.99), (-1.38, 0.985)],
           'y', 0.007)
    ribbon(g, [(-0.72, 0.945), (-0.90, 0.955)], 'y', 0.018)
    hexa = [(-1.50 + 0.05 * cos(rad(a)), 0.955 + 0.036 * sin(rad(a))) for a in range(0, 360, 60)]
    ribbon(g, hexa, 'y', 0.004, closed=True)
    for k in range(4):
        x = 1.02 - 0.05 * k
        ribbon(g, [(x, 0.47), (x - 0.03, 0.585)], 'z', 0.016)
    g.obj("lines", "void", mirror=True)
    # ---- the visor: sensor slits and a status light at its point
    g = Geo()
    for k in range(3):
        x = 1.42 - 0.07 * k
        ribbon(g, [(x, 0.04 + 0.022 * k), (x - 0.012, 0.20 + 0.04 * k)], 'z', 0.012)
    g.obj("visor.slits", "grille", mirror=True)
    g = Geo()
    ribbon(g, [(1.735, -0.10), (1.735, 0.10)], 'z', 0.010)
    g.obj("led.visor", "keel_led")
    # ---- amber markers on the shoulder, warning stripes by the pods' pylons
    g = Geo()
    ribbon(g, [(0.62, 0.845), (0.50, 0.855)], 'y', 0.012)
    g.obj("led.marker", "led_accent", mirror=True)
    g = Geo()
    for k in range(5):
        x = -1.62 - 0.045 * k
        ribbon(g, [(x, 0.965), (x - 0.025, 0.93)], 'y', 0.013)
    g.obj("decals", "stencil", mirror=True)
    # ---- a sensor blade on the roof, pitot pins at the prow, studs on the hood
    zr = on_body(-0.78, 0.0, 'z')[0].z
    g = Geo()
    g.prism([(-0.62, -0.006, zr - 0.006), (-0.80, -0.006, zr + 0.085), (-0.86, -0.006, zr + 0.085),
             (-0.90, -0.006, zr - 0.006)], (0, 0.012, 0))
    g.obj("roof.blade", "paint2", bevel=0.002)
    g = Geo()
    gp = Geo()
    for y in (0.12, 0.26):
        loc, n = on_body(1.70, y, 'z')
        if loc is not None:
            stud(g, loc, n, [(-0.002, 0.001), (-0.002, 0.010), (0.0015, 0.010), (0.0015, 0.001)],
                 10)
    for (x, y) in ((1.24, 0.30), (0.20, 0.60), (-0.80, 0.62), (-1.30, 0.60)):
        loc, n = on_body(x, y, 'z')
        if loc is not None:
            stud(gp, loc, n, [(-0.002, 0.001), (-0.002, 0.008), (0.002, 0.008), (0.002, 0.001)], 6)
    g.obj("sensors", "gloss_black", mirror=True)
    gp.obj("fasteners", "rim_bright", mirror=True)
    g = Geo()
    g.sweep([(2.24, 0.0, 0.655), (2.335, 0.0, 0.655)],
            [(-0.004, -0.004), (0.004, -0.004), (0.004, 0.004), (-0.004, 0.004)])
    g.obj("pitot", "rim_bright")
    # ---- camera blades in place of mirrors
    g = Geo()
    g.hexa([(0.70, 0.70, 0.905), (0.52, 0.72, 0.915), (0.50, 0.90, 0.93), (0.60, 0.90, 0.925),
            (0.70, 0.70, 0.915), (0.52, 0.72, 0.928), (0.50, 0.90, 0.955), (0.60, 0.90, 0.948)])
    g.obj("camera.blades", "paint2", bevel=0.003, mirror=True)
    g = Geo()
    g.box((0.498, 0.86, 0.942), (0.004, 0.06, 0.016))
    g.obj("camera.lens", "gloss_black", mirror=True)


# ---------------------------------------------------------------------------------------
# interior
# ---------------------------------------------------------------------------------------
def build_interior():
    g = Geo()
    g.box((-0.05, 0, 0.485), (1.95, 0.80, 0.02))
    g.prism([(-0.98, -0.52, 0.50), (-0.98, 0.52, 0.50), (-0.98, 0.78, 0.84), (-0.98, 0.76, 0.98),
             (-0.98, 0.42, 1.31), (-0.98, -0.42, 1.31), (-0.98, -0.76, 0.98),
             (-0.98, -0.78, 0.84)], (0.04, 0, 0))
    g.prism([(1.00, -0.56, 0.55), (1.00, -0.56, 0.86), (0.66, -0.60, 0.93),
             (0.50, -0.62, 0.86), (0.56, -0.62, 0.55)], (0, 1.18, 0))
    g.box((0.0, 0, 0.56), (1.1, 0.16, 0.14))
    for sy in (1, -1):
        g.box((-0.25, sy * 0.62, 0.78), (1.4, 0.08, 0.26))
    g.obj("interior.tub", "interior", bevel=0.006)
    g = Geo()
    tilt = Matrix.Rotation(rad(-24), 3, 'Y')
    for y in (0.33, -0.33):
        g.box((-0.28, y, 0.545), (0.50, 0.40, 0.10))
        g.box((-0.63, y, 0.85), (0.10, 0.38, 0.60), rot=tilt)
        g.box((-0.775, y, 1.185), (0.065, 0.20, 0.14), rot=tilt)
        for s in (-1, 1):
            g.box((-0.28, y + s * 0.20, 0.59), (0.46, 0.05, 0.12))
            g.box((-0.615, y + s * 0.195, 0.82), (0.13, 0.05, 0.48), rot=tilt)
    g.obj("interior.seats", "seat", bevel=0.012, segs=3)
    # a yoke, not a wheel
    g = Geo()
    yk = Matrix.Translation((0.30, 0.33, 0.90)) @ Matrix.Rotation(rad(-62), 4, 'Y')
    g.box((0, 0, 0), (0.03, 0.30, 0.035), xf=yk)
    for s in (-1, 1):
        g.box((0, s * 0.15, 0.045), (0.035, 0.035, 0.12), xf=yk)
    g.box((0.42, 0.33, 0.875), (0.22, 0.05, 0.05))
    g.obj("interior.yoke", "interior", bevel=0.004)
    g = Geo()
    scr = Matrix.Rotation(rad(-28), 3, 'Y')
    g.box((0.50, 0.0, 0.905), (0.008, 0.62, 0.075), rot=scr)
    g.box((0.565, 0.33, 0.955), (0.008, 0.24, 0.045), rot=scr)
    g.box((0.10, 0.0, 0.633), (0.30, 0.10, 0.006))
    g.obj("interior.screens", "screen")
    # power cell under the rear glass: a ribbed block with glowing seams
    g = Geo()
    ge = Geo()
    g.box((-1.42, 0, 0.93), (0.80, 0.86, 0.02))
    g.prism([(-1.08, -0.36, 0.94), (-1.08, -0.36, 1.10), (-1.30, -0.36, 1.10),
             (-1.74, -0.36, 0.99), (-1.74, -0.36, 0.94)], (0, 0.72, 0))
    for k in range(7):
        y = -0.30 + 0.10 * k
        g.prism([(-1.09, y - 0.012, 1.10), (-1.30, y - 0.012, 1.118), (-1.74, y - 0.012, 1.005),
                 (-1.74, y - 0.012, 0.99), (-1.30, y - 0.012, 1.10)], (0, 0.024, 0))
    for y in (-0.25, 0.25):
        ge.prism([(-1.12, y - 0.03, 1.103), (-1.29, y - 0.03, 1.103), (-1.29, y + 0.03, 1.103),
                  (-1.12, y + 0.03, 1.103)], (0, 0, 0.003))
    g.obj("power.cell", "rim", bevel=0.003)
    ge.obj("power.glow", "emitter_core")


# ---------------------------------------------------------------------------------------
# views and the build
# ---------------------------------------------------------------------------------------
K.VIEWS["hero"].update(dir=(1.0, 0.80, 0.21), focus=(1.2, 0.6, 0.8), fstop=11.0)
K.VIEWS["rear"].update(focus=(-1.2, -0.6, 0.9), fstop=11.0)
K.VIEWS.update(
    pod=dict(dir=(0.6, 1.0, -0.10), lens=85, target=(1.2, 0.8, 0.5), dist=2.6),
    nose=dict(dir=(1.0, 0.5, 0.12), lens=85, target=(1.7, 0.4, 0.7), dist=3.2),
    tail=dict(dir=(-1.0, -0.45, 0.16), lens=85, target=(-2.0, -0.3, 0.9), dist=3.6),
    cabin=dict(dir=(0.5, 1.0, 0.45), lens=85, target=(-0.2, 0.3, 1.1), dist=3.6),
)


def main():
    K.materials(paint=(0.64, 0.67, 0.70), paint_finish="pearl",
                paint2=(0.030, 0.034, 0.042), paint2_finish="satin", dust_amount=0.12,
                led_front=(0.72, 0.95, 1.0), led_accent=(1.0, 0.42, 0.04),
                seat=(0.20, 0.065, 0.02), screen=(0.12, 0.75, 0.9), decal=(0.05, 0.055, 0.065))
    K.emit("emitter", (0.10, 0.80, 1.0), 110.0)
    K.emit("emitter_core", (0.08, 0.55, 1.0), 26.0)
    K.emit("thrust", (0.30, 0.55, 1.0), 26.0)
    K.emit("keel_led", (0.10, 0.80, 1.0), 45.0)
    K.pbr("stencil", (0.045, 0.05, 0.06), 0.0, 0.55)
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
    K.shoot()


main()
