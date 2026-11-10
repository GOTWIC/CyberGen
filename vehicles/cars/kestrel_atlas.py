"""Kestrel Aerodyne Atlas: a two-seat hover hauler with an open load bed (both names made
up), on vehicles/carkit.py.

Run (always through the wrapper, one Blender job at a time on this machine):
    vehicles/blender.sh vehicles/cars/kestrel_atlas.py --out DIR --preview
    vehicles/blender.sh vehicles/cars/kestrel_atlas.py --out DIR --sheet

The working Kestrel (docs/progress/AG18/kestrel_dart lists the family cues): the knife chine
with its strip from prow to stern, flat top facets with flush glass, the ribbed graphite
lower hull, eight-sided emitter pods, canted fins, slot thrusters, the keel blade and
stencil registration. Its own: a cab-forward wedge over a chisel prow with a work-lamp slot,
the shoulder line running on as the top of two raised rails beside an open bed, six pods (the
rear pairs larger) on ribbed outriggers with heavy skids, the fins standing on the rail ends
and bridged by a hoist beam over a fold-down tailgate, and a load in the bed (a cable drum
and two cases, strapped to the rails' tie-down track).
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import carkit as K                                                  # noqa: E402
from carkit import (Geo, Matrix, V3, band_point, cos, on_body, pi, rad,    # noqa: E402
                    ribbon, sin, stud, text_flat, text_on_body)

SUBDIV = 2
Z_BED, Z_RAIL = 1.00, 1.34

# ---------------------------------------------------------------------------------------
# hull: seven lines over nine stations. In the cab: C roof ridge, R roof edge, M the top of
# the side glass, S the shoulder, K the chine (widest, a knife edge), L lower hull edge,
# B keel. Behind the cab the same lines go on as: C bed floor, R the floor's edge, M the
# rail's inner top edge, S its outer top edge (the shoulder, unbroken from the windshield
# to the stern), K, L, B.
# ---------------------------------------------------------------------------------------
LINES = "CRMSKLB"
ORDER = ["P0", "P1", "P2", "P3", "P4", "P5", "P6", "P7", "P8"]
PT = {}
T = {
    # the prow: a chisel, wide and thin, with a slot in its edge
    "P0": [(2.90, 0, 1.005), (2.885, .44, .995), None, (2.84, .62, .97), (2.78, .715, .915),
           (2.83, .50, .815), (2.90, 0, .79)],
    # windshield base, windshield top
    "P1": [(2.32, 0, 1.17), (2.30, .56, 1.15), (2.24, .72, 1.135), (2.13, .85, 1.11),
           (2.13, .93, .925), (2.20, .58, .585), (2.25, 0, .51)],
    "P2": [(1.42, 0, 2.00), (1.40, .60, 1.975), (1.44, .745, 1.87), (1.54, .90, 1.31),
           (1.52, .965, .935), (1.50, .60, .555), (1.50, 0, .50)],
    # the roof's end, the rear window's base, the foot of the cab's back wall
    "P3": [(.74, 0, 2.03), (.74, .60, 2.005), (.74, .745, 1.90), (.76, .90, Z_RAIL),
           (.76, .97, .94), (.76, .60, .555), (.76, 0, .50)],
    "P4": [(.69, 0, 1.50), (.69, .63, 1.50), (.69, .74, 1.50), (.70, .895, Z_RAIL),
           None, None, None],
    "P5": [(.64, 0, Z_BED), (.64, .70, Z_BED), (.64, .72, Z_RAIL), (.64, .885, Z_RAIL),
           (.64, .968, .94), (.64, .60, .555), (.64, 0, .50)],
    # the bed, the rails' chamfered ends, the stern
    "P6": [(-.80, 0, Z_BED), (-.80, .70, Z_BED), (-.80, .72, Z_RAIL), (-.80, .88, Z_RAIL),
           (-.80, .96, .945), (-.80, .60, .555), (-.80, 0, .50)],
    "P7": [(-2.08, 0, Z_BED), (-2.08, .70, Z_BED), (-2.08, .72, Z_RAIL), (-2.08, .87, Z_RAIL),
           (-2.08, .935, .955), (-2.00, .58, .60), (-2.00, 0, .53)],
    "P8": [(-2.40, 0, Z_BED), (-2.40, .70, Z_BED), (-2.40, .72, 1.05), (-2.40, .85, 1.05),
           (-2.37, .90, .965), (-2.40, .56, .70), (-2.40, 0, .64)],
}
T["P0"][2] = tuple((u + v) / 2 for u, v in zip(T["P0"][1], T["P0"][3]))
FRONT_C, FRONT_D = V3((2.90, 0, 0.90)), 0.12
REAR_C = V3((-2.40, 0, 0.83))
TAIL_D, BAND_W = 0.13, 0.035

PMAT = dict(nose="paint", fender="paint", door="paint", flank_f="paint", flank_r="paint",
            rail="paint", roof="paint", back="paint", bulkhead="paint2",
            bedfloor="bedliner", railin="paint2", railtop="paint2", lower="paint2",
            belly="bellyplate", glass_ws="glass_coat", glass_rear="glass_smoke",
            glass_sf="glass", glass_s="glass",
            trim="gloss_black", visor="visor", lightband="gloss_black",
            prow_frame="cladding", prow_in="visor",
            tail_frame="cladding", tail="void", vent="void")


def panel_of(i, j):
    if j == 5:
        return "belly"
    if j == 4:
        return "lower"
    if j == 3:
        return ("fender", "door", "door", "flank_f", "flank_f", "flank_f", "flank_r",
                "flank_r")[i]
    if i == 0:
        return "visor" if j == 0 else "nose"
    if j == 0:
        return ("glass_ws", "roof", "glass_rear", "bulkhead", "bedfloor", "bedfloor",
                "bedfloor")[i - 1]
    if j == 1:
        return "rail" if i <= 2 else "back" if i == 3 else "bulkhead" if i == 4 else "railin"
    return ("glass_sf", "glass_s", "back", "back", "railtop", "railtop", "railtop")[i - 1]


def station_crease(i, j):
    if i in (0, 8):
        return 1.0
    return 1.0 if j <= 2 else 0.0           # folds between the top facets; flanks flow


def build_hull():
    S = K.fill([T[k] for k in ORDER])
    PT.update(K.table(ORDER, LINES, S))
    K.build_body(
        S, panel_of, PMAT, 1.0, station_crease,
        front=dict(center=FRONT_C, depth=FRONT_D, band=0.026, frame="prow_frame",
                   inner="prow_in", reach=0.06),
        rear=dict(center=REAR_C, depth=TAIL_D, band=BAND_W, band_panel="lightband",
                  band_lines=4, frame="tail_frame", inner="tail"),
        glass=[("glass_ws", 0.036), ("glass_sf", 0.028), ("glass_s", 0.028),
               ("glass_rear", 0.034)],
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


STRAP = [(-0.002, -0.024), (0.002, -0.024), (0.002, 0.024), (-0.002, 0.024)]


def strap(g, gr, x, pts, ratchet=1):
    """A webbing strap across the bed at x over the (y, z) points, a ratchet on one fall."""
    g.sweep([(x, y, z) for (y, z) in pts], STRAP, up=(1, 0, 0))
    a, b = V3((x,) + tuple(pts[ratchet - 1])), V3((x,) + tuple(pts[ratchet]))
    c = a.lerp(b, 0.45)
    d = (b - a).normalized()
    o = V3((1, 0, 0)).cross(d)
    gr.box(c + o * 0.012, (0.062, 0.09, 0.026),
           rot=Matrix(((1, d.x, o.x), (0, d.y, o.y), (0, d.z, o.z))))


# ---------------------------------------------------------------------------------------
# emitter pods: the family's nacelle, six of them, on ribbed outriggers, with heavy skids
# ---------------------------------------------------------------------------------------
POD_SEC = [(-.11, .14), (.09, .14), (.19, .05), (.19, -.06), (.13, -.14), (-.13, -.14),
           (-.19, -.06), (-.19, .05)]
PODS = dict(f=dict(xc=1.74, yc=0.895, zc=0.585, L=1.00, s=0.88),
            m=dict(xc=-0.02, yc=0.908, zc=0.590, L=1.16, s=1.02),
            r=dict(xc=-1.62, yc=0.915, zc=0.600, L=1.34, s=1.14))
POD_MAT = dict(pod_top="paint", pod_side="paint2", pod_low="cladding", pod_belly="cladding",
               pod_nose="paint", tip_f="led_front", tip_m="led_accent", tip_r="led_accent",
               vent="void", pod_frame="cladding", pod_end="void")


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

    # the skid: a heavy sled outboard of the emitter on two braced legs, a pad at each end
    ys = yc + 0.172 * s
    zs = zb - 0.045
    g = Geo()
    g.sweep([(xc + 0.47 * s, ys, zb + 0.06), (xc + 0.38 * s, ys, zs),
             (xc - 0.38 * s, ys, zs), (xc - 0.47 * s, ys, zb + 0.06)],
            [(-0.021, -0.013), (0.021, -0.013), (0.021, 0.013), (-0.021, 0.013)],
            up=(0, 1, 0))
    for x in (xc + 0.22 * s, xc - 0.22 * s):
        g.box((x, ys - 0.012, (zs + zb + 0.05) / 2), (0.05, 0.03, zb + 0.05 - zs))
        g.lathe([(-0.03, 0.002), (-0.03, 0.022), (0.03, 0.022), (0.03, 0.002)], 8,
                xf=Matrix.Translation((x, ys - 0.012, zb + 0.05)))
        g.box((x, ys, zs - 0.012), (0.16, 0.06, 0.014))
    g.obj("pod.skid." + tag, "rim_bright", bevel=0.003, mirror=True)

    # the outrigger: a ribbed arm from the lower hull over the pod's back
    zt = zc + 0.14 * s
    g = Geo()
    g.hexa([(xc + 0.27 * s, 0.60, zt - 0.05), (xc - 0.27 * s, 0.60, zt - 0.05),
            (xc - 0.22 * s, yc + 0.02, zt - 0.02), (xc + 0.22 * s, yc + 0.02, zt - 0.02),
            (xc + 0.27 * s, 0.60, zt + 0.075), (xc - 0.27 * s, 0.60, zt + 0.075),
            (xc - 0.22 * s, yc + 0.02, zt + 0.028), (xc + 0.22 * s, yc + 0.02, zt + 0.028)])
    g.obj("pod.arm." + tag, "paint2", bevel=0.004, mirror=True)
    g = Geo()
    for k in range(7):
        x = xc + (0.18 - 0.06 * k) * s
        g.hexa([(x + 0.008, 0.66, zt + 0.062), (x - 0.008, 0.66, zt + 0.062),
                (x - 0.008, yc + 0.01, zt + 0.024), (x + 0.008, yc + 0.01, zt + 0.024),
                (x + 0.005, 0.66, zt + 0.078), (x - 0.005, 0.66, zt + 0.078),
                (x - 0.005, yc + 0.01, zt + 0.036), (x + 0.005, yc + 0.01, zt + 0.036)])
    g.obj("pod.armribs." + tag, "cladding", mirror=True)

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
             and ob.name.split(".")[1] in PODS]
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
# fins on the rail ends, the hoist beam between them
# ---------------------------------------------------------------------------------------
CANT = 20
FIN_BASE, FIN_UP = V3((0, 0.80, Z_RAIL)), V3((0, sin(rad(CANT)), cos(rad(CANT))))
FIN_T = 0.70
FIN = [(-1.30, 0.0), (-2.22, FIN_T), (-2.80, FIN_T), (-2.84, FIN_T - 0.10), (-2.64, 0.22),
       (-2.45, -0.27), (-2.10, -0.03)]
BEAM_A, BEAM_T = -2.42, 0.60


def fin_pt(a, t, off=0.0, side=1):
    """A point of the fin's plane, off toward the outside."""
    n = V3((1, 0, 0)).cross(FIN_UP).normalized()        # inboard and up
    p = FIN_BASE + V3((a, 0, 0)) + FIN_UP * t - n * off
    return V3((p.x, side * p.y, p.z))


def fin_half(t):
    return (0.040 + (0.014 - 0.040) * max(0.0, t) / FIN_T) / 2


def build_fins():
    g = Geo()
    plate(g, FIN_BASE, (1, 0, 0), FIN_UP, FIN, 0.040, 0.014, FIN_T)
    g.obj("fins", "paint", bevel=0.003, mirror=True)
    g = Geo()                                           # red down the trailing edge
    g.sweep([fin_pt(-2.655, 0.24, 0), fin_pt(-2.845, FIN_T - 0.10, 0)],
            [(-0.016, -0.005), (0.016, -0.005), (0.016, 0.007), (-0.016, 0.007)],
            up=(-1, 0, 0))
    g.obj("led.fin", "led_rear", mirror=True)
    g = Geo()                                           # graphite leading edge
    plate(g, FIN_BASE, (1, 0, 0), FIN_UP,
          [(-1.275, -0.012), (-2.225, FIN_T + 0.012), (-2.29, FIN_T + 0.012), (-1.36, -0.012)],
          0.046, 0.020, FIN_T)
    g.obj("fin.edge", "paint2", bevel=0.002, mirror=True)
    g = Geo()
    gt = Geo()
    gm = Geo()
    for side in (1, -1):
        up = V3((0, side * FIN_UP.y, FIN_UP.z))
        text_flat(gt, "KH-626", 0.092, fin_pt(-2.20, 0.34, fin_half(0.34) + 0.0025, side),
                  (-side, 0, 0), up, spacing=1.08)
        text_flat(gt, "ATLAS", 0.028, fin_pt(-2.58, FIN_T - 0.07,
                                             fin_half(FIN_T - 0.07) + 0.002, side),
                  (-side, 0, 0), up, spacing=1.3)
        text_flat(gt, "626", 0.13, fin_pt(-2.30, 0.30, -fin_half(0.30) - 0.0025, side),
                  (side, 0, 0), up, spacing=1.1)
        gm.sweep([fin_pt(-2.40, FIN_T - 0.02, 0.012, side),
                  fin_pt(-2.58, FIN_T - 0.02, 0.012, side)],
                 [(-0.006, -0.003), (0.006, -0.003), (0.006, 0.003), (-0.006, 0.003)], up=up)
        for a0, a1 in ((0.0, 0.45), (0.55, 1.0)):       # the rudder's cut line
            q0, q1 = fin_pt(-2.62, 0.26, 0.016, side), fin_pt(-2.62, FIN_T - 0.04, 0.009, side)
            g.sweep([q0.lerp(q1, a0), q0.lerp(q1, a1)],
                    [(-0.003, -0.002), (0.003, -0.002), (0.003, 0.002), (-0.003, 0.002)],
                    up=(1, 0, 0))
    g.obj("fin.lines", "void")
    gt.obj("fin.code", "stencil")
    gm.obj("led.fin.marker", "led_accent")

    # ---- the hoist beam: a bridge between the fins, over the tailgate's hinge
    pb = fin_pt(BEAM_A, BEAM_T)
    yb, zb = pb.y, pb.z
    g = Geo()
    g.prism([(BEAM_A + 0.075, -yb, zb - 0.045), (BEAM_A + 0.055, -yb, zb + 0.05),
             (BEAM_A - 0.055, -yb, zb + 0.05), (BEAM_A - 0.075, -yb, zb - 0.045)],
            (0, 2 * yb, 0))
    g.obj("hoist.beam", "paint2", bevel=0.004)
    g = Geo()
    for sy in (1, -1):                                  # shoes where it meets the fins
        g.box((BEAM_A, sy * (yb - 0.035), zb), (0.20, 0.07, 0.125))
        g.box((BEAM_A, sy * 0.45, zb - 0.05), (0.03, 0.04, 0.03))        # trolley stops
    g.box((BEAM_A, 0.0, zb - 0.075), (0.25, 0.30, 0.09))                  # the trolley
    g.box((BEAM_A, 0.0, zb + 0.065), (0.18, 0.22, 0.03))
    g.lathe([(-0.10, 0.004), (-0.10, 0.062), (-0.085, 0.062), (-0.085, 0.045), (0.085, 0.045),
             (0.085, 0.062), (0.10, 0.062), (0.10, 0.004)], 14,
            xf=Matrix.Translation((BEAM_A, 0, zb - 0.165)))
    g.box((BEAM_A, 0.115, zb - 0.14), (0.10, 0.016, 0.13))
    g.box((BEAM_A, -0.115, zb - 0.14), (0.10, 0.016, 0.13))
    g.obj("hoist.trolley", "rim", bevel=0.004)
    g = Geo()
    zh = 1.50
    g.tube((BEAM_A, 0, zb - 0.20), (BEAM_A, 0, zh + 0.10), 0.006, 8)
    g.obj("hoist.cable", "cable")
    g = Geo()
    g.box((BEAM_A, 0, zh + 0.06), (0.07, 0.05, 0.10))
    g.sweep([(BEAM_A, 0, zh + 0.02), (BEAM_A, 0, zh - 0.05), (BEAM_A - 0.035, 0, zh - 0.085),
             (BEAM_A - 0.075, 0, zh - 0.05), (BEAM_A - 0.075, 0, zh - 0.02)],
            [(-0.011, -0.011), (0.011, -0.011), (0.011, 0.011), (-0.011, 0.011)], up=(0, 1, 0))
    g.obj("hoist.hook", "hazard", bevel=0.003)
    g = Geo()                                           # work light under the beam
    for sy in (1, -1):
        g.box((BEAM_A, sy * 0.58, zb - 0.048), (0.05, 0.62, 0.008))
    g.obj("led.hoist.work", "lamp")
    g = Geo()                                           # the high tail light, the maker's name
    for sy in (1, -1):
        g.box((BEAM_A - 0.068, sy * 0.60, zb), (0.008, 0.66, 0.026))
    text_flat(g, "K E S T R E L", 0.030, (BEAM_A - 0.0665, 0, zb - 0.012), (0, -1, 0),
              (0, 0, 1), spacing=1.2)
    g.obj("led.rear.beam", "led_rear")
    g = Geo()
    text_flat(g, "HOIST 600 KG", 0.026, (BEAM_A + 0.067, 0.52, zb - 0.012), (0, 1, 0),
              (0, 0, 1), spacing=1.15)
    text_flat(g, "HOIST 600 KG", 0.026, (BEAM_A + 0.067, -0.52, zb - 0.012), (0, 1, 0),
              (0, 0, 1), spacing=1.15)
    g.obj("hoist.stencil", "stencil")


# ---------------------------------------------------------------------------------------
# the bed: liner ribs, the tie-down track on the rails, the tailgate, the load
# ---------------------------------------------------------------------------------------
def build_bed():
    # ---- ribs along the floor, uprights on the bulkhead
    g = Geo()
    for k in range(15):
        y = -0.63 + 0.09 * k
        g.box((-0.88, y, Z_BED + 0.003), (2.96, 0.036, 0.010))
    for k in range(11):
        y = -0.55 + 0.11 * k
        rib(g, [(y, 1.05 + 0.04 * i) for i in range(11)], 'X', 0.022, 0.012)
    g.obj("bed.ribs", "cladding")
    # ---- the track on each rail: a slotted strip, a cleat every 0.4 m, a ring on each
    g = Geo()
    gc = Geo()
    gs = Geo()
    g.box((-0.75, 0.80, Z_RAIL + 0.004), (2.60, 0.062, 0.010))
    for k in range(7):
        x = 0.40 - 0.40 * k
        gc.box((x, 0.80, Z_RAIL + 0.016), (0.09, 0.044, 0.016))
        gc.sweep([(x - 0.03, 0.80, Z_RAIL + 0.02), (x - 0.03, 0.80, Z_RAIL + 0.05),
                  (x + 0.03, 0.80, Z_RAIL + 0.05), (x + 0.03, 0.80, Z_RAIL + 0.02)],
                 [(-0.005, -0.005), (0.005, -0.005), (0.005, 0.005), (-0.005, 0.005)],
                 up=(0, 1, 0))
        for dx in (-0.20, -0.12, 0.12, 0.20):
            gs.box((x + dx, 0.80, Z_RAIL + 0.0095), (0.05, 0.016, 0.002))
    g.obj("rail.track", "rim", bevel=0.002, mirror=True)
    gc.obj("rail.cleats", "rim_bright", bevel=0.002, mirror=True)
    gs.obj("rail.slots", "void", mirror=True)
    # ---- a rub strip along each rail's inner top edge, lit amber at the bulkhead
    g = Geo()
    g.box((-0.72, 0.712, Z_RAIL - 0.03), (2.66, 0.012, 0.018))
    g.obj("rail.rub", "cladding", mirror=True)
    g = Geo()
    g.box((-0.72, 0.706, Z_BED + 0.10), (2.60, 0.006, 0.012))
    g.obj("led.bed", "lamp_dim", mirror=True)

    # ---- the tailgate, folded down as a loading shelf on two stays
    HX, HZ, GL, DROP = -2.405, Z_BED - 0.005, 0.50, rad(1.5)
    ex, ez = V3((-cos(DROP), 0, -sin(DROP))), V3((-sin(DROP), 0, cos(DROP)))
    o = V3((HX, 0, HZ))

    def gp(u, y, w):
        return o + ex * u + V3((0, y, 0)) + ez * w

    def gbox(g, u0, u1, y0, y1, w0, w1):
        g.hexa([gp(u, y, w) for w in (w0, w1)
                for (u, y) in ((u0, y0), (u1, y0), (u1, y1), (u0, y1))])

    g = Geo()
    gbox(g, 0.0, GL, -0.69, 0.69, -0.055, 0.0)
    g.obj("gate", "paint", bevel=0.004)
    g = Geo()
    for k in range(15):
        y = -0.63 + 0.09 * k
        gbox(g, 0.03, GL - 0.10, y - 0.018, y + 0.018, 0.0, 0.008)
    gbox(g, 0.0, GL, -0.69, 0.69, -0.062, -0.055)
    g.obj("gate.tread", "cladding")
    g = Geo()                                           # hazard blocks on its lip and its edge
    for k in range(9):
        y = -0.64 + 0.16 * k
        gbox(g, GL - 0.075, GL - 0.012, y - 0.045, y + 0.045, 0.0, 0.003)
        gbox(g, GL, GL + 0.002, y - 0.045, y + 0.045, -0.050, -0.006)
    g.obj("gate.hazard", "hazard")
    g = Geo()                                           # hinges and the stays up to the fins
    for y in (-0.52, 0.0, 0.52):
        g.lathe([(-0.07, 0.003), (-0.07, 0.022), (0.07, 0.022), (0.07, 0.003)], 10,
                xf=Matrix.Translation((HX, y, HZ - 0.02)))
    for sy in (1, -1):
        g.tube(fin_pt(-2.50, 0.02, -0.03, sy), gp(GL - 0.05, sy * 0.672, -0.02), 0.007, 8)
        g.box(gp(GL - 0.05, sy * 0.68, -0.02), (0.05, 0.03, 0.05))
    g.obj("gate.hardware", "rim_bright", bevel=0.002)
    g = Geo()
    text_flat(g, "ATLAS", 0.10, gp(GL / 2 + 0.02, 0, -0.0635), (0, -1, 0), (-ex.x, 0, -ex.z),
              spacing=1.5)
    g.obj("gate.name", "stencil")

    build_load()


def build_load():
    # ---- a cable drum on chocks, strapped over both flanges
    xd, R = -1.22, 0.43
    zd = Z_BED + 0.012 + R
    g = Geo()
    prof = [(-0.40, 0.07), (-0.40, R), (-0.355, R), (-0.355, 0.20), (0.355, 0.20), (0.355, R),
            (0.40, R), (0.40, 0.07)]
    g.lathe(prof, 40, xf=Matrix.Translation((xd, 0, zd)))
    g.obj("drum", "drum", bevel=0.004)
    g = Geo()                                           # the wound cable, in turns
    turns = [(-0.355, 0.20)]
    for k in range(22):
        y = -0.345 + 0.0314 * k
        turns += [(y, 0.330), (y + 0.0157, 0.342), (y + 0.0314, 0.330)]
    turns.append((0.355, 0.20))
    g.lathe(turns, 40, xf=Matrix.Translation((xd, 0, zd)))
    g.obj("drum.cable", "cable")
    g = Geo()
    for sy in (1, -1):                                  # flange bolts and the hub plate
        g.lathe([(sy * 0.40, 0.03), (sy * 0.40, 0.13), (sy * 0.415, 0.12), (sy * 0.415, 0.03)],
                12, xf=Matrix.Translation((xd, 0, zd)))
        for k in range(8):
            a = rad(45 * k + 22.5)
            g.box((xd + 0.31 * cos(a), sy * 0.404, zd + 0.31 * sin(a)), (0.03, 0.012, 0.03))
    g.tube((xd, -0.47, zd), (xd, 0.47, zd), 0.028, 12)
    g.obj("drum.hub", "rim_bright", bevel=0.002)
    g = Geo()
    for sy in (1, -1):
        for sx in (1, -1):
            x = xd + sx * 0.24
            g.prism([(x - sx * 0.07, sy * 0.40 - 0.06, Z_BED + 0.012),
                     (x + sx * 0.15, sy * 0.40 - 0.06, Z_BED + 0.012),
                     (x + sx * 0.15, sy * 0.40 - 0.06, Z_BED + 0.11)], (0, 0.12, 0))
    g.obj("drum.chocks", "hazard", bevel=0.004)
    gs, gr = Geo(), Geo()
    for dx in (-0.16, 0.16):
        zt = zd + (R * R - dx * dx) ** 0.5 + 0.003
        strap(gs, gr, xd + dx, [(0.775, Z_RAIL + 0.03), (0.40, zt), (-0.40, zt),
                                (-0.775, Z_RAIL + 0.03)])
    g = Geo()
    text_flat(g, "KA LINE 40 KV", 0.05, (xd - 0.02, 0.4165, zd - 0.25), (-1, 0, 0), (0, 0, 1),
              spacing=1.1)
    text_flat(g, "KA LINE 40 KV", 0.05, (xd - 0.02, -0.4165, zd - 0.25), (1, 0, 0), (0, 0, 1),
              spacing=1.1)
    g.obj("drum.stencil", "stencil_dark")

    # ---- two transit cases against the bulkhead under one strap
    cases = [((0.17, -0.27, 0.62), (0.80, 0.70, 0.62)), ((0.21, 0.40, 0.44), (0.68, 0.52, 0.44))]
    g, gb, gl = Geo(), Geo(), Geo()
    for (x, y, h), (sx, sy, sz) in cases:
        z0 = Z_BED + 0.014
        g.box((x, y, z0 + h / 2), (sx, sy, sz))
        for zz in (z0 + 0.012, z0 + h - 0.012, z0 + h * 0.62):      # bands round the case
            gb.box((x, y, zz), (sx + 0.012, sy + 0.012, 0.024))
        for ax in (-1, 1):
            for ay in (-1, 1):                          # corner posts and latches
                gb.box((x + ax * sx / 2, y + ay * sy / 2, z0 + h / 2), (0.03, 0.03, sz + 0.004))
            gl.box((x + ax * 0.2, y + (sy / 2 + 0.008) * (1 if y > 0 else -1), z0 + h * 0.62),
                   (0.06, 0.012, 0.07))
            gl.box((x - sx / 2 - 0.008, y + ax * 0.16, z0 + h * 0.62), (0.012, 0.06, 0.07))
    g.obj("cases", "case", bevel=0.006)
    gb.obj("case.bands", "rim", bevel=0.003)
    gl.obj("case.latches", "rim_bright", bevel=0.002)
    za, zb2 = Z_BED + 0.014 + 0.62 + 0.004, Z_BED + 0.014 + 0.44 + 0.004
    strap(gs, gr, 0.17, [(-0.775, Z_RAIL + 0.03), (-0.627, za), (0.087, za), (0.133, zb2),
                         (0.667, zb2), (0.775, Z_RAIL + 0.03)], ratchet=5)
    gs.obj("straps", "webbing")
    gr.obj("strap.ratchets", "rim_bright", bevel=0.003)
    g = Geo()
    text_flat(g, "LOT 07", 0.07, (-0.232, -0.27, Z_BED + 0.26), (0, -1, 0), (0, 0, 1),
              spacing=1.1)
    text_flat(g, "KEEP DRY", 0.04, (-0.132, 0.40, Z_BED + 0.19), (0, -1, 0), (0, 0, 1),
              spacing=1.1)
    text_flat(g, "LOT 07", 0.09, (0.17, -0.27, za - 0.0025), (0, -1, 0), (-1, 0, 0),
              spacing=1.1)
    g.obj("case.stencil", "stencil")


# ---------------------------------------------------------------------------------------
# details
# ---------------------------------------------------------------------------------------
def build_details():
    P = PT
    # ---- the chine blade: a bright knife edge from the prow to the stern, lit at both ends
    xs = [2.72 - 0.05 * k for k in range(102)]
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
    g.obj("led.front", "led_front", mirror=True)
    g = Geo()
    g.sweep(pts[-7:], sec, up=(0, 1, 0))
    g.obj("led.chine.rear", "led_rear", mirror=True)

    # ---- the prow: work lamps in the slot, a sensor slit over them, two mooring horns
    xm = FRONT_C.x - FRONT_D
    g, gl, gs = Geo(), Geo(), Geo()
    for k in range(4):
        y = 0.075 + 0.118 * k
        g.box((xm + 0.012, y, 0.895), (0.03, 0.104, 0.062))
        gl.box((xm + 0.029, y, 0.895), (0.006, 0.086, 0.044))
    gs.box((xm + 0.006, 0.26, 0.952), (0.012, 0.40, 0.010))
    g.obj("prow.cells", "gloss_black", bevel=0.003, mirror=True)
    gl.obj("prow.lamps", "lamp", mirror=True)
    gs.obj("prow.sensor", "keel_led", mirror=True)
    g = Geo()
    for y in (0.30,):                                   # tow horns under the slot
        g.sweep([(2.80, y, 0.78), (2.935, y, 0.775), (2.965, y, 0.80), (2.955, y, 0.835)],
                [(-0.016, -0.013), (0.016, -0.013), (0.016, 0.013), (-0.016, 0.013)],
                up=(0, 1, 0))
    g.obj("prow.horns", "hazard", bevel=0.003, mirror=True)

    # ---- fine ribbing on the lower hull, parallel to the chine
    g = Geo()
    xr = [2.30 - 0.06 * k for k in range(77)]
    for k in range(7):
        d = 0.045 + 0.030 * k
        rib(g, [(x, chine(x).z - d) for x in xr[k:len(xr) - k] if chine(x) is not None],
            'y', 0.010, 0.006)
    g.obj("hull.ribs", "cladding", mirror=True)

    # ---- keel blade and its light
    g = Geo()
    keel = [(2.52, 0.625), (2.05, 0.41), (-1.80, 0.41), (-2.15, 0.575), (-1.4, 0.535),
            (1.6, 0.535)]
    g.prism([(x, -0.016, z) for (x, z) in keel], (0, 0.032, 0))
    g.obj("keel", "paint2", bevel=0.004)
    g = Geo()
    g.box((0.125, 0, 0.4065), (3.75, 0.02, 0.009))
    g.obj("led.keel", "keel_led")
    # ---- strakes under the stern's kick-up
    g = Geo()
    for y, dz in ((0.18, 0.0), (0.40, 0.03)):
        g.prism([(-1.72, y - 0.007, 0.55 + dz), (-2.415, y - 0.007, 0.70 + dz),
                 (-2.44, y - 0.007, 0.56), (-2.16, y - 0.007, 0.50), (-1.88, y - 0.007, 0.50)],
                (0, 0.014, 0))
    g.obj("strakes", "paint2", bevel=0.003, mirror=True)

    # ---- belly: cross ribs, conduits from the keel to each emitter
    def belly(y):
        return 0.50 + 0.055 * abs(y) / 0.60

    g = Geo()
    for k in range(22):
        x = 1.40 - 0.13 * k
        g.hexa([(x + 0.012, 0.05, belly(0.05) - 0.012), (x - 0.012, 0.05, belly(0.05) - 0.012),
                (x - 0.012, 0.56, belly(0.56) - 0.012), (x + 0.012, 0.56, belly(0.56) - 0.012),
                (x + 0.016, 0.05, belly(0.05) + 0.004), (x - 0.016, 0.05, belly(0.05) + 0.004),
                (x - 0.016, 0.56, belly(0.56) + 0.004), (x + 0.016, 0.56, belly(0.56) + 0.004)])
    g.obj("belly.ribs", "cladding", mirror=True)
    g = Geo()
    for tag, p in PODS.items():
        for dx in (-0.12, 0.12):
            x = p["xc"] + dx
            g.tube((x, 0.012, 0.485), (x, p["yc"] - 0.16 * p["s"], 0.50), 0.02, 10)
            g.box((x, 0.30, belly(0.30) - 0.02), (0.07, 0.03, 0.05))
    g.obj("belly.conduits", "rim", bevel=0.003, mirror=True)

    # ---- stern: a light bar round the top of the mouth, six slanted slot thrusters, a
    # stern post between the banks
    half = [P["P8"][n] for n in "KSMR"]
    hp = [band_point(p, REAR_C, BAND_W * 0.5, 0.0) for p in half]
    path = hp + [hp[-1].lerp(band_point(P["P8"]["C"], REAR_C, BAND_W * 0.5, 0.0), 0.80)]
    g = Geo()
    g.sweep(path, [(-0.007, -0.006), (0.007, -0.006), (0.007, 0.004), (-0.007, 0.004)],
            up=(-1, 0, 0))
    g.obj("led.rear", "led_rear", mirror=True)
    xt = REAR_C.x + TAIL_D
    g = Geo()
    gg = Geo()
    for k in range(3):
        y = 0.20 + 0.165 * k
        sh = Matrix.Identity(4)
        sh[1][2] = 0.30                                 # lean outward toward the top
        xf = Matrix.Translation((xt, y, 0.835 + 0.004 * k)) @ sh @ Matrix.Rotation(pi / 2, 4, 'Z') \
            @ Matrix.Diagonal((0.70, 1.0, 1.16 - 0.05 * k, 1.0))
        g.lathe([(0.0, 0.082), (0.105, 0.082), (0.118, 0.074), (0.118, 0.066), (0.0, 0.066)],
                4, a0=pi / 4, a1=pi / 4 + 2 * pi, xf=xf)
        gg.lathe([(0.035, 0.002), (0.035, 0.066), (0.04, 0.066), (0.04, 0.002)],
                 4, a0=pi / 4, a1=pi / 4 + 2 * pi, xf=xf)
    g.obj("thrusters", "rim", bevel=0.003, mirror=True)
    gg.obj("thruster.glow", "thrust", mirror=True)
    g = Geo()
    g.hexa([(xt + 0.01, -0.085, 0.72), (xt + 0.01, 0.085, 0.72), (-2.425, 0.025, 0.75),
            (-2.425, -0.025, 0.75), (xt + 0.01, -0.085, 0.95), (xt + 0.01, 0.085, 0.95),
            (-2.425, 0.025, 0.94), (-2.425, -0.025, 0.94)])
    g.obj("stern.post", "paint2", bevel=0.004)
    g = Geo()
    g.box((-2.428, 0, 0.845), (0.008, 0.02, 0.15))
    g.obj("led.post", "led_rear")

    build_surface_details()


def build_surface_details():
    # ---- lettering: the model on the door, registrations by the nose, on the bed sides and
    # on the roof, load and hazard notes
    g = Geo()
    for side in (1, -1):
        text_on_body(g, "ATLAS", 0.070, 1.22, 1.075, side, spacing=1.3)
        text_on_body(g, "KA 2-626", 0.032, 2.30, 0.985, side, spacing=1.15)
        text_on_body(g, "KH-626", 0.17, -0.42, 1.135, side, spacing=1.12)
        text_on_body(g, "MAX LOAD 1400 KG", 0.030, -1.27, 1.235, side, spacing=1.15)
        text_on_body(g, "KEEP CLEAR OF EMITTERS", 0.024, -1.27, 1.045, side, spacing=1.15)
    text_on_body(g, "KH-626", 0.15, 1.08, 0.0, 1, proj='z', spacing=1.1)
    g.obj("lettering", "stencil")
    # ---- hazard chevrons on the bed sides by the stern
    g = Geo()
    for k in range(5):
        x = -1.64 - 0.07 * k
        ribbon(g, [(x, 1.265), (x - 0.11, 1.03)], 'y', 0.030)
    g.obj("hazard.stripes", "hazard", mirror=True)
    # ---- grooves: the door's release slot and step notch, a line under the shoulder along
    # the bed, a charge port
    g = Geo()
    ribbon(g, [(0.60, 1.30), (-0.80, 1.30), (-2.05, 1.30)], 'y', 0.007)
    ribbon(g, [(0.92, 1.235), (1.12, 1.23)], 'y', 0.018)
    hexa = [(0.30 + 0.05 * cos(rad(a)), 1.13 + 0.038 * sin(rad(a))) for a in range(0, 360, 60)]
    ribbon(g, hexa, 'y', 0.004, closed=True)
    g.obj("lines", "void", mirror=True)
    # ---- the visor: sensor slits and a status light at its front edge
    g = Geo()
    for k in range(3):
        x = 2.74 - 0.10 * k
        ribbon(g, [(x, 0.05 + 0.02 * k), (x - 0.012, 0.24 + 0.05 * k)], 'z', 0.012)
    g.obj("visor.slits", "grille", mirror=True)
    g = Geo()
    ribbon(g, [(2.86, -0.16), (2.86, 0.16)], 'z', 0.010)
    g.obj("led.visor", "keel_led")
    # ---- amber markers on the flank
    g = Geo()
    ribbon(g, [(2.02, 1.02), (1.88, 1.03)], 'y', 0.012)
    ribbon(g, [(-2.14, 1.10), (-2.26, 1.095)], 'y', 0.012)
    g.obj("led.marker", "led_accent", mirror=True)
    # ---- the roof: a beacon, a sensor blade, work lamps over the rear window
    zr = on_body(0.95, 0.0, 'z')[0].z
    g = Geo()
    up = Matrix.Rotation(pi / 2, 4, 'X')
    g.lathe([(0.0, 0.004), (0.0, 0.07), (0.022, 0.07), (0.022, 0.004)], 12,
            xf=Matrix.Translation((0.98, 0.34, zr - 0.012)) @ up)
    g.prism([(1.30, -0.006, zr - 0.02), (1.14, -0.006, zr + 0.075), (1.09, -0.006, zr + 0.075),
             (1.06, -0.006, zr - 0.02)], (0, 0.012, 0))
    for sy in (1, -1):
        g.box((0.775, sy * 0.36, zr + 0.016), (0.07, 0.24, 0.055))
    g.obj("roof.gear", "paint2", bevel=0.003)
    g = Geo()
    g.lathe([(0.022, 0.004), (0.022, 0.052), (0.085, 0.052), (0.105, 0.036), (0.105, 0.004)], 12,
            xf=Matrix.Translation((0.98, 0.34, zr - 0.012)) @ up)
    g.obj("led.beacon", "beacon")
    g = Geo()
    for sy in (1, -1):
        g.box((0.738, sy * 0.36, zr + 0.016), (0.006, 0.20, 0.034))
    g.obj("led.worklamps", "lamp")
    # ---- pitot pins, studs on the panels
    g = Geo()
    gp = Geo()
    for (x, y) in ((2.62, 0.40), (2.42, 0.62), (1.30, 0.50), (0.84, 0.50), (0.84, 0.15)):
        loc, n = on_body(x, y, 'z')
        if loc is not None:
            stud(gp, loc, n, [(-0.002, 0.001), (-0.002, 0.008), (0.002, 0.008), (0.002, 0.001)], 6)
    for k in range(8):                                  # a row of fasteners down each flank
        loc, n = on_body(0.40 - 0.36 * k, 0.98, 'y')
        if loc is not None:
            stud(gp, loc, n, [(-0.002, 0.001), (-0.002, 0.009), (0.002, 0.009), (0.002, 0.001)], 6)
    gp.obj("fasteners", "rim_bright", mirror=True)
    for y in (0.30,):
        g.sweep([(2.86, y, 0.995), (3.0, y, 0.995)],
                [(-0.004, -0.004), (0.004, -0.004), (0.004, 0.004), (-0.004, 0.004)])
    g.obj("pitot", "rim_bright", mirror=True)
    # ---- camera blades in place of mirrors
    g = Geo()
    g.hexa([(2.10, 0.84, 1.118), (1.92, 0.86, 1.150), (1.90, 1.06, 1.166), (2.00, 1.06, 1.150),
            (2.10, 0.84, 1.130), (1.92, 0.86, 1.168), (1.90, 1.06, 1.194), (2.00, 1.06, 1.176)])
    g.obj("camera.blades", "paint2", bevel=0.003, mirror=True)
    g = Geo()
    g.box((1.898, 1.02, 1.18), (0.004, 0.06, 0.016))
    g.obj("camera.lens", "gloss_black", mirror=True)
    # ---- a boarding step under each door, between the front and middle pods
    g = Geo()
    gr = Geo()
    for sy in (1, -1):
        g.box((0.92, sy * 0.86, 0.70), (0.46, 0.24, 0.022))
        for x in (0.72, 1.12):
            g.prism([(x - 0.007, sy * 0.70, 0.66), (x - 0.007, sy * 0.97, 0.692),
                     (x - 0.007, sy * 0.70, 0.80)], (0.014, 0, 0))
        for k in range(4):
            gr.box((0.92, sy * (0.79 + 0.05 * k), 0.713), (0.40, 0.02, 0.006))
    g.obj("step", "paint2", bevel=0.003)
    gr.obj("step.grip", "cladding")
    g = Geo()
    g.box((0.92, 0.983, 0.70), (0.42, 0.006, 0.012))
    g.obj("led.step", "led_front", mirror=True)


# ---------------------------------------------------------------------------------------
# interior: two seats, a yoke, a screen across the dash
# ---------------------------------------------------------------------------------------
def build_interior():
    g = Geo()
    g.box((1.50, 0, 0.60), (1.60, 1.22, 0.02))
    g.prism([(2.24, -0.74, 0.60), (2.24, -0.74, 1.12), (1.96, -0.74, 1.17),
             (1.78, -0.74, 1.10), (1.84, -0.74, 0.84), (1.84, -0.74, 0.60)], (0, 1.48, 0))
    g.box((1.30, 0, 0.71), (1.00, 0.17, 0.22))
    g.box((0.80, 0, 1.02), (0.05, 1.50, 0.86))          # the cab's back wall, inside
    for sy in (1, -1):                                  # door cards under the glass
        g.prism([(1.9, sy * 0.63, 0.60), (1.9, sy * 0.69, 0.60), (1.9, sy * 0.84, 0.80),
                 (1.9, sy * 0.86, 1.26), (1.9, sy * 0.78, 1.26), (1.9, sy * 0.74, 0.86)],
                (-1.10, 0, 0))
    g.obj("interior.tub", "interior", bevel=0.006)
    g = Geo()
    tilt = Matrix.Rotation(rad(-14), 3, 'Y')
    for y in (0.40, -0.40):
        g.box((1.24, y, 0.80), (0.52, 0.46, 0.20))
        g.box((0.94, y, 1.20), (0.11, 0.44, 0.66), rot=tilt)
        g.box((0.86, y, 1.60), (0.07, 0.24, 0.16), rot=tilt)
        for s in (-1, 1):
            g.box((1.24, y + s * 0.23, 0.87), (0.48, 0.05, 0.16))
            g.box((0.955, y + s * 0.225, 1.17), (0.14, 0.05, 0.52), rot=tilt)
    g.obj("interior.seats", "seat", bevel=0.012, segs=3)
    g = Geo()                                           # a yoke, not a wheel
    yk = Matrix.Translation((1.66, 0.40, 1.16)) @ Matrix.Rotation(rad(-62), 4, 'Y')
    g.box((0, 0, 0), (0.03, 0.30, 0.035), xf=yk)
    for s in (-1, 1):
        g.box((0, s * 0.15, 0.045), (0.035, 0.035, 0.12), xf=yk)
    g.box((1.76, 0.40, 1.13), (0.20, 0.05, 0.05))
    g.obj("interior.yoke", "interior", bevel=0.004)
    g = Geo()
    scr = Matrix.Rotation(rad(-24), 3, 'Y')
    g.box((1.845, 0.0, 1.17), (0.008, 1.16, 0.09), rot=scr)
    g.box((1.30, 0.0, 0.823), (0.34, 0.11, 0.006))
    g.obj("interior.screens", "screen")
    g = Geo()
    g.box((1.08, 0.57, 1.955), (0.60, 0.014, 0.008))
    g.obj("led.cabin", "cabin_led", mirror=True)


# ---------------------------------------------------------------------------------------
# views and the build
# ---------------------------------------------------------------------------------------
K.VIEWS["hero"].update(dir=(0.94, 1.0, 0.42), focus=(1.6, 0.7, 1.0), fstop=11.0)
K.VIEWS["rear"].update(focus=(-1.6, -0.7, 1.0), fstop=11.0)
K.VIEWS.update(
    bed=dict(dir=(-0.75, 1.0, 0.55), lens=70, target=(-0.9, 0.0, 1.3), dist=6.5),
    nose=dict(dir=(1.0, 0.45, 0.12), lens=85, target=(2.4, 0.2, 1.0), dist=4.2),
    tail=dict(dir=(-1.0, -0.45, 0.20), lens=85, target=(-2.3, -0.2, 1.2), dist=5.0),
    pod=dict(dir=(0.5, 1.0, -0.06), lens=85, target=(-1.5, 0.9, 0.6), dist=3.4),
)


def main():
    K.materials(paint=(0.165, 0.215, 0.060), paint_finish="pearl",
                paint2=(0.030, 0.034, 0.042), paint2_finish="satin", dust_amount=0.16,
                dust_z=(0.45, 1.05),
                led_front=(0.72, 0.95, 1.0), led_accent=(1.0, 0.42, 0.04),
                seat=(0.46, 0.38, 0.25), screen=(0.12, 0.75, 0.9), decal=(0.05, 0.055, 0.065))
    K.emit("emitter", (0.10, 0.80, 1.0), 110.0)
    K.emit("emitter_core", (0.08, 0.55, 1.0), 26.0)
    K.emit("thrust", (0.30, 0.55, 1.0), 26.0)
    K.emit("keel_led", (0.10, 0.80, 1.0), 45.0)
    K.emit("beacon", (1.0, 0.36, 0.02), 30.0)
    K.emit("lamp_dim", (1.0, 0.60, 0.25), 6.0)
    K.emit("cabin_led", (1.0, 0.82, 0.60), 40.0)
    K.pbr("stencil", (0.78, 0.80, 0.76), 0.0, 0.55)
    K.pbr("stencil_dark", (0.03, 0.032, 0.035), 0.0, 0.6)
    K.pbr("hazard", (0.90, 0.20, 0.015), 0.0, 0.45)
    K.pbr("webbing", (0.62, 0.64, 0.60), 0.0, 0.8)
    K.pbr("cable", (0.012, 0.012, 0.014), 0.0, 0.5)
    K.pbr("drum", (0.60, 0.61, 0.60), 0.9, 0.42)
    K.pbr("case", (0.085, 0.09, 0.095), 0.2, 0.55)
    K.pbr("bedliner", (0.022, 0.024, 0.028), 0.0, 0.75)
    # the facets that face the sky: coated, so the studio's top light is a sheen in them and
    # not a white slab; the rear window smoked
    K.pbr("glass_coat", (0.30, 0.33, 0.36), 0.0, 0.0, **{"Transmission Weight": 1.0, "IOR": 1.12})
    K.pbr("glass_smoke", (0.045, 0.05, 0.06), 0.0, 0.0, **{"Transmission Weight": 1.0, "IOR": 1.12})
    K.pbr("bellyplate", (0.055, 0.06, 0.068), 0.55, 0.5)
    K.pbr("visor", (0.016, 0.017, 0.020), 0.0, 0.65, **{"Specular IOR Level": 0.06})
    build_hull()
    K.log("hull")
    for tag, p in PODS.items():
        build_pod(tag, **p)
    pod_ribs()
    K.log("pods")
    build_details()
    build_fins()
    build_bed()
    build_interior()
    K.log("details")
    K.shoot(extra=dict(view="top", size=(1040, 420)))


main()
