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
from functools import partial                                       # noqa: E402

import carkit as K                                                  # noqa: E402
from brands import kestrel                                          # noqa: E402
from brands.kestrel import chine, plate, rib                        # noqa: E402
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
            trim="frit", visor="visor", lightband="gloss_black",
            prow_frame="cladding", prow_in="visor",
            tail_frame="cladding", tail="void", vent="void", lamp_n="lamp_housing",
            lamp_c="lamp_housing", lens_c="lens_clear",
            lamp_cr="lamp_housing", lens_cr="lens_red", lamp_t="lamp_housing",
            lens_t="lens_red", cut="void")
GAP = 0.00175                       # 3.5 mm shut lines
LAMP = {}                           # the lamps' pockets and channels on the skin
CH_F = (2.42, 1.62)                 # the chine's front light channel, from x to x
CH_R = (-2.12, -2.41)               # and its rear one
CH_W, CH_D = 0.018, 0.022           # their width (up the knife edge) and depth
NOSE_Y = (0.105, 0.21, 0.315)       # the nose lamps' cells across the mouth, and their height
NOSE_Z = 0.705


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


def rear_path():
    """The middle of the light band round the top of the stern's mouth, the left half,
    stopping short of the maker's name."""
    half = [PT["P7"][n] for n in "KSMR"]
    hp = [band_point(p, REAR_C, BAND_W * 0.5, 0.0) for p in half]
    return hp + [hp[-1].lerp(band_point(PT["P7"]["C"], REAR_C, BAND_W * 0.5, 0.0), 0.45)]


def tail_w(t):
    """The stern bar's channel width along its path: narrower where the band narrows past
    the mouth's middle."""
    return 0.016 - 0.007 * min(1.0, max(0.0, (t - 0.58) / 0.22))


def cutters():
    """Everything cut into the hull, laid on it while it stands uncut: the nose lamps' slot
    in the mouth, the light channels along the chine's knife edge and round the stern's
    lip, the shoulder groove, the door releases and the charge flap."""
    # nose lamps: a slot across each half of the mouth's back wall (its lens and surround
    # stand proud of the wall: build_lamps)
    nose = Geo()
    LAMP["nose"] = K.pocket(nose, K.rounded(0.21, NOSE_Z, 0.33, 0.064, 0.012), 'x',
                            depth=0.04, mirror=True)
    # the chine's light channels: cut into the knife edge itself, so the lens is the edge
    chf, chr_ = Geo(), Geo()
    for g, (x0, x1), key in ((chf, CH_F, "chine_f"), (chr_, CH_R, "chine_r")):
        n = int(abs(x1 - x0) / 0.02)
        pts = [chine(x0 + (x1 - x0) * k / n) for k in range(n + 1)]
        LAMP[key] = K.groove(g, [p for p in pts if p is not None], width=CH_W, depth=CH_D,
                             up=(0, 1, 0), step=0.02, mirror=True)
    # the stern's light bar: a channel round the top of the mouth, in the band
    tail = Geo()
    LAMP["tail"] = K.groove(tail, rear_path(), width=tail_w, depth=0.026, up=(-1, 0, 0),
                            mirror=True)
    # shut lines: the styling groove under the glass (a point every 4 cm: the flank is
    # nearly flat there, and a denser cut was a weight on the pack's far LODs), a flush
    # release on each door, the charge flap
    cut = Geo()
    K.groove(cut, [(1.22, 1.008), (0.80, 1.035), (-0.30, 1.055), (-1.28, 1.065),
                   (-1.90, 1.095)], 'y', width=0.0035, step=0.04, mirror=True)
    for x, z in ((-0.16, 1.014), (-1.13, 1.024)):
        K.groove(cut, K.rounded(x, z, 0.18, 0.018), 'y', closed=True, mirror=True)
    K.groove(cut, [(-1.62 + 0.05 * cos(rad(a)), 1.01 + 0.036 * sin(rad(a)))
                   for a in range(0, 360, 60)], 'y', closed=True, mirror=True)
    return [(nose, "lamp_n"), (chf, "lamp_c", "skin", "lens_c"),
            (chr_, "lamp_cr", "skin", "lens_cr"), (tail, "lamp_t", "skin", "lens_t"),
            (cut, "cut", "drop")]


def build_hull():
    S = K.fill([T[k] for k in ORDER])
    PT.update(K.table(ORDER, LINES, S))
    K.build_body(
        S, panel_of, PMAT, line_crease, station_crease,
        front=dict(center=FRONT_C, depth=FRONT_D, band=0.032, frame="prow_frame",
                   inner="prow_in", reach=0.075),
        rear=dict(center=REAR_C, depth=TAIL_D, band=BAND_W, band_panel="lightband",
                  band_lines=4, frame="tail_frame", inner="tail"),
        glass=[(p, i, "trim", "frit") for p, i in (
            ("glass_ws", 0.034), ("glass_roof", 0.032), ("glass_sf", 0.026),
            ("glass_sr", 0.026), ("glass_sq", 0.024), ("glass_rear", 0.036))],
        cutters=cutters, subdiv=SUBDIV, gap=GAP)


# ---------------------------------------------------------------------------------------
# helpers of this car (chine, rib, plate, the fin plane and the pods are the family's:
# vehicles/brands/kestrel.py)
# ---------------------------------------------------------------------------------------
def slab(g, o, ev, ew, u0, u1, v0, v1, w0, w1):
    """A box in a tilted frame: u along x, v along ev, w along ew, from the point o."""
    o, ev, ew = V3(o), V3(ev), V3(ew)
    ex = V3((1, 0, 0))
    g.hexa([o + ex * u + ev * v + ew * w for w in (w0, w1)
            for (u, v) in ((u0, v0), (u1, v0), (u1, v1), (u0, v1))])


# ---------------------------------------------------------------------------------------
# emitter pods: the family's nacelle (vehicles/brands/kestrel.py), here tucked under the
# chine and half sunk in the hull
# ---------------------------------------------------------------------------------------
PODS = dict(f=dict(xc=1.44, yc=0.80, zc=0.555, L=1.12, s=0.92),
            r=dict(xc=-1.50, yc=0.84, zc=0.565, L=1.30, s=1.0))
POD_MAT = dict(pod_top="paint", pod_side="paint2", pod_low="cladding", pod_belly="cladding",
               pod_nose="paint", tip_f="led_front", tip_r="led_accent", vent="void",
               pod_frame="cladding", pod_end="void")


# ---------------------------------------------------------------------------------------
# details
# ---------------------------------------------------------------------------------------
KEEL_X, KEEL_H = (1.80, -1.50), 0.024    # the keel lamp's channel: from x to x, its height
KEEL_Z = 0.335                           # the keel blade's foot
FIN_BASE, FIN_UP = V3((0, 0.66, 1.10)), V3((0, sin(rad(24)), cos(rad(24))))
FIN_T = 0.44
FIN = [(-1.70, 0.0), (-2.30, FIN_T), (-2.64, FIN_T), (-2.665, FIN_T - 0.09), (-2.60, 0.20),
       (-2.52, 0.0)]


fin_pt = partial(kestrel.fin_pt, base=FIN_BASE, up=FIN_UP)


def fin_half(t):
    return (0.034 + (0.012 - 0.034) * t / FIN_T) / 2


def build_details():
    P = PT
    # ---- the chine blade: a bright knife edge between the light channels at its ends
    x0, x1 = CH_F[1] - 0.012, CH_R[0] + 0.012
    n = int((x0 - x1) / 0.05)
    pts = [chine(x0 + (x1 - x0) * k / n) for k in range(n + 1)]
    pts = [p + V3((0, 0.003, -0.004)) for p in pts if p is not None]
    sec = [(-0.007, -0.004), (0.007, -0.004), (0.007, 0.004), (-0.007, 0.004)]
    g = Geo()
    g.sweep(pts, sec, up=(0, 1, 0))
    g.obj("chine.blade", "rim_bright", mirror=True)
    # the Meridian's face: from the lit chine's end a light blade turns the corner and
    # bridges the mouth
    p0 = chine(CH_F[0]) + V3((0, 0.003, -0.004))
    g = Geo()
    g.sweep([p0, V3((2.505, 0.565, p0.z)), V3((2.60, 0.0, p0.z))],
            [(-0.012, -0.007), (0.012, -0.007), (0.012, 0.007), (-0.012, 0.007)], up=(0, 0, 1))
    g.obj("led.front", "led_front", mirror=True)
    build_lamps()

    # ---- the prow: a stem blade from the keel up to the light, louvers under the lamps
    # (its foot reaches down to the keel's height, so the pack's far LOD keeps it)
    zb = p0.z
    g = Geo()
    xm = FRONT_C.x - FRONT_D
    zt = zb - 0.012
    g.hexa([(xm - 0.01, -0.045, 0.60), (xm - 0.01, 0.045, 0.60), (2.588, 0.010, 0.51),
            (2.588, -0.010, 0.51), (xm - 0.01, -0.045, zt), (xm - 0.01, 0.045, zt),
            (2.612, 0.010, zt), (2.612, -0.010, zt)])
    g.obj("prow.stem", "paint", bevel=0.003)
    g = Geo()
    gs = Geo()
    gs.box((xm + 0.006, 0.215, 0.853), (0.012, 0.29, 0.016))    # a sensor slit over the blade
    g.louvers((xm + 0.02, 0.06, 0.612), (xm + 0.02, 0.06, 0.66), (xm + 0.02, 0.31, 0.66),
              (xm + 0.02, 0.31, 0.612), 3, 0.03, 0.004, rad(25), out=(1, 0, 0), margin=0.1)
    g.obj("prow.cells", "gloss_black", bevel=0.003, mirror=True)
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
    # the blade's foot is a lamp: a channel up into it, a light guide in a frosted sleeve
    # over a bright reflector strip, flush under a clear lens
    g = Geo()
    kz = KEEL_Z
    keel = [(2.30, 0.50), (1.85, kz), (KEEL_X[0], kz), (KEEL_X[0], kz + KEEL_H),
            (KEEL_X[1], kz + KEEL_H), (KEEL_X[1], kz), (-1.55, kz), (-1.95, 0.50),
            (-1.2, 0.46), (1.3, 0.46)]
    g.prism([(x, -0.014, z) for (x, z) in keel], (0, 0.028, 0))
    g.obj("keel", "paint2", bevel=0.004)
    L = K.Lamp("lamp.keel", lit="keel_led")
    x0, x1 = KEEL_X[0] - 0.0015, KEEL_X[1] + 0.0015
    xm, lx = (x0 + x1) / 2, x0 - x1
    for sy in (1, -1):                                  # the channel's dark walls
        L.housing.box((xm, sy * 0.0125, kz + KEEL_H / 2), (lx, 0.003, KEEL_H))
    L.housing.box((xm, 0, kz + KEEL_H - 0.0015), (lx, 0.022, 0.003))
    L.chrome.box((xm, 0, kz + KEEL_H - 0.0035), (lx - 0.004, 0.016, 0.001))
    L.guide([(x0 - 0.006, 0, kz + 0.010), (x1 + 0.006, 0, kz + 0.010)], r=0.0035, sleeve=1.6,
            up=(0, 0, 1))
    L.glass.box((xm, 0, kz + 0.0015), (lx - 2 * GAP, 0.022, 0.003))
    L.obj()
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

    # ---- stern: two banks of slanted slot thrusters either side of a stern post (the
    # light bar round the top of the mouth is a lamp)
    xt = REAR_C.x + TAIL_D
    g = Geo()
    gg = Geo()
    gv = Geo()
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
        for kz in (-1, 0, 1):                           # vanes across the slot, set back
            gv.box((0, 0.068, kz * 0.024), (0.096, 0.05, 0.0035), xf=xf)
        gv.box((0, 0.068, 0), (0.0035, 0.05, 0.096), xf=xf)
    g.obj("thrusters", "rim", bevel=0.003, mirror=True)
    gg.obj("thruster.glow", "thrust", mirror=True)
    gv.obj("thruster.vanes", "grille", mirror=True)
    g = Geo()                                           # the stern post between the banks
    g.hexa([(xt + 0.01, -0.13, 0.76), (xt + 0.01, 0.13, 0.76), (-2.53, 0.03, 0.80),
            (-2.53, -0.03, 0.80), (xt + 0.01, -0.13, 1.07), (xt + 0.01, 0.13, 1.07),
            (-2.53, 0.03, 1.05), (-2.53, -0.03, 1.05)])
    g.obj("stern.post", "paint2", bevel=0.004)
    g = Geo()
    g.box((-2.533, 0, 0.925), (0.008, 0.022, 0.21))
    g.obj("led.post", "led_rear")
    g = Geo()
    band = [ob for ob in K.CAR.objects if ob.name == "body.lightband"]
    if not text_on_body(g, "K E S T R E L", 0.026, 0.0, 1.143, 1, proj='X', spacing=1.2,
                        objs=band):                 # seated on the band, not floating off it
        text_flat(g, "K E S T R E L", 0.026, (-2.5085, 0, 1.143), (0, -1, 0), (0, 0, 1),
                  spacing=1.2)
    ob = g.obj("led.name", "led_rear")
    md = ob.modifiers.new("solid", 'SOLIDIFY')  # letters 5 mm proud: a game pack keeps them
    md.thickness = 0.008                        # as they are (laid flat, they were baked
    md.offset = 0.0                             # down and lost strokes)

    build_steps()
    build_surface_details()


def along(tr, s0=0.0, s1=None, step=0.03):
    """Frames every step along a traced path between the lengths s0 and s1:
    [(point, normal, tangent, side)], side = tangent x normal."""
    P = [q for q, _ in tr]
    S = [0.0]
    for a, b in zip(P, P[1:]):
        S.append(S[-1] + (b - a).length)
    s1 = S[-1] if s1 is None else min(s1, S[-1])
    n = max(1, int(round((s1 - s0) / step)))
    out, i = [], 0
    for k in range(n + 1):
        s = s0 + (s1 - s0) * k / n
        while i < len(S) - 2 and S[i + 1] < s:
            i += 1
        t = (s - S[i]) / max(S[i + 1] - S[i], 1e-9)
        tg = (P[i + 1] - P[i]).normalized()
        nn = tr[i][1].lerp(tr[i + 1][1], t).normalized()
        out.append((P[i].lerp(P[i + 1], t), nn, tg, tg.cross(nn).normalized()))
    return out


def length(tr):
    return sum((b[0] - a[0]).length for a, b in zip(tr, tr[1:]))


def build_lamps():
    """What stands in the lamps' pockets and channels, under their lenses."""
    # nose: three lit cells across each half of the mouth, standing a little proud of its
    # back wall between bright dividers that run to the slot's floor, under a clear lens in
    # a dark surround that stands proud round the slot (the game pack's far LOD draws the
    # wall across the slot: lamps behind it were lost there)
    pk = LAMP["nose"]
    if pk is not None:
        out = -pk.d

        def wall(y, z, off=0.0):                        # the back wall's plane at (y, z)
            q = V3((pk.c.x, y, z))
            return q - out * (q - pk.c).dot(out) + out * off

        def floor(q):
            return q + pk.d * ((pk._c0 - q.dot(pk.b)) / pk.d.dot(pk.b))
        L = K.Lamp("lamp.nose", lit="lamp")
        for y in NOSE_Y:
            L.bar([wall(y - 0.037, NOSE_Z, 0.003), wall(y + 0.037, NOSE_Z, 0.003)], 0.044,
                  0.004, up=out)
        for y in (0.06, 0.1575, 0.2625, 0.36):        # dividers from the lens to the floor
            q = wall(y, NOSE_Z, 0.009)
            L.chrome.sweep([q, floor(q)], [(-0.0015, -0.027), (0.0015, -0.027),
                                           (0.0015, 0.027), (-0.0015, 0.027)],
                           up=V3((0, 0, 1)))
        rim = [wall(y, z) for y, z in K.rounded(0.21, NOSE_Z, 0.338, 0.072, 0.016)]
        L.housing.sweep(rim, [(-0.004, -0.004), (0.004, -0.004), (0.004, 0.012),
                              (-0.004, 0.012)], up=out, closed=True)
        lens = [wall(y, z, 0.0095) for y, z in K.rounded(0.21, NOSE_Z, 0.332, 0.066, 0.013)]
        L.glass.prism(lens, out * 0.002)
        L.obj(mirror=True)
    # the chine's channels: a light guide down each, bright liners on the floor
    for key, lit in (("chine_f", "led_front"), ("chine_r", "led_rear")):
        tr = LAMP[key]
        if len(tr) < 2:
            continue
        fr = along(tr, 0.008, length(tr) - 0.008, 0.02)
        ups = [n for _, n, _, _ in fr]
        L = K.Lamp("lamp." + key, lit=lit)
        L.chrome.sweep([q - n * (CH_D - 0.003) for q, n, _, _ in fr],
                       [(-0.0065, -0.0005), (0.0065, -0.0005), (0.0065, 0.0005),
                        (-0.0065, 0.0005)], up=ups)
        L.guide([q - n * 0.008 for q, n, _, _ in fr], r=0.0045, sleeve=0, up=ups)
        L.obj(mirror=True)
    # the stern's bar: a red guide behind bright ribs
    tr = LAMP["tail"]
    if len(tr) >= 2:
        rr = along(tr, 0.008, length(tr) - 0.008, 0.01)
        ups = [n for _, n, _, _ in rr]
        L = K.Lamp("lamp.tail", lit="led_rear")
        L.chrome.sweep([q - n * 0.023 for q, n, _, _ in rr],
                       [(-0.006, -0.0005), (0.006, -0.0005), (0.006, 0.0005),
                        (-0.006, 0.0005)], up=ups)
        L.guide([q - n * 0.010 for q, n, _, _ in rr], r=0.0045, sleeve=0, up=ups)
        for q, n, tg, sd in along(tr, 0.02, length(tr) - 0.02, 0.028):
            L.chrome.box(q - n * 0.016, (0.002, 0.006, 0.012),
                         rot=Matrix((tg, sd, n)).transposed())
        L.obj(mirror=True)


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
    # hood sensor slits (the shoulder groove, the door releases and the charge flap are
    # cut into the hull: cutters())
    g = Geo()
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
    g = Geo()                                           # the floor (its rear corners cut
    g.prism([(1.25, -0.65, 0.485), (1.25, 0.65, 0.485), (-1.05, 0.65, 0.485),
             (-1.22, 0.57, 0.485), (-1.22, -0.57, 0.485), (-1.05, -0.65, 0.485)],
            (0, 0, 0.02))                               # in), a step up under the rear
    g.box((-1.335, 0, 0.51), (0.23, 1.10, 0.02))        # bench where the belly rises
    g.prism([(-1.45, -0.58, 0.52), (-1.45, 0.58, 0.52), (-1.45, 0.84, 0.80), (-1.45, 0.82, 1.08),
             (-1.45, 0.55, 1.14), (-1.45, -0.55, 1.14), (-1.45, -0.82, 1.08),
             (-1.45, -0.84, 0.80)], (0.04, 0, 0))
    g.prism([(1.28, -0.66, 0.50), (1.28, -0.66, 1.03), (0.96, -0.66, 1.045),
             (0.80, -0.66, 0.97), (0.86, -0.66, 0.72), (0.86, -0.66, 0.50)], (0, 1.32, 0))
    g.box((-0.25, 0, 0.60), (2.10, 0.17, 0.20))
    g.box((-1.70, 0, 1.13), (0.52, 1.36, 0.02))
    for sy in (1, -1):                                  # door cards under the glass
        g.prism([(1.0, sy * 0.62, 0.50), (1.0, sy * 0.665, 0.50), (1.0, sy * 0.83, 0.72),
                 (1.0, sy * 0.84, 1.02), (1.0, sy * 0.77, 1.02), (1.0, sy * 0.74, 0.80)],
                (-2.20, 0, 0))
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
        kestrel.build_pod(tag, mat=POD_MAT, **p)
    kestrel.pod_ribs(PODS)
    K.log("pods")
    build_details()
    build_interior()
    K.log("details")
    # the boarding step is out on the left and stowed on the right; the yoke is the pilot's
    K.meant("symmetry", "step.*", "led.step", "interior.yoke")
    K.shoot(extra=dict(view="under", size=(1000, 400)))


main()
