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
            trim="frit", prow="gloss_black", visor="visor", lightband="gloss_black",
            tail_frame="cladding", tail="void", vent="void", lamp_n="lamp_housing",
            lens_n="lens_clear", lamp_c="lamp_housing", lens_c="lens_clear",
            lamp_cr="lamp_housing", lens_cr="lens_red", lamp_t="lamp_housing",
            lens_t="lens_red", cut="void")
GAP = 0.00175                       # 3.5 mm shut lines
LAMP = {}                           # the lamps' pockets and channels on the skin
CH_F = (2.16, 1.40)                 # the chine's front light channel, from x to x
CH_R = (-1.86, -2.13)               # and its rear one
CH_W, CH_D = 0.018, 0.022           # their width (up the knife edge) and depth


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


def lamp_z(x):
    """The middle of the nose lamps' slot on the nose's flank facet."""
    return chine(x).z + 0.028 + 0.035 * (1.74 - x)


def rear_path():
    """The middle of the light band round the top of the stern's mouth, the left half,
    stopping short of the maker's name."""
    half = [PT["P7"][n] for n in "KSMR"]
    hp = [band_point(p, REAR_C, BAND_W * 0.5, 0.0) for p in half]
    return hp + [hp[-1].lerp(band_point(PT["P7"]["C"], REAR_C, BAND_W * 0.5, 0.0), 0.4)]


def tail_w(t):
    """The stern bar's channel width along its path: narrower where the band narrows past
    the mouth's middle."""
    return 0.016 - 0.007 * min(1.0, max(0.0, (t - 0.58) / 0.22))


def cutters():
    """Everything cut into the hull, laid on it while it stands uncut: the nose lamps'
    slot, the light channels along the chine's knife edge and round the stern's lip, the
    shoulder groove, the door handle and the charge flap."""
    # nose lamps: a slot in the flank facet over the chine, flush under a clear lens
    nose = Geo()
    xs = (1.745, 1.60, 1.46, 1.32, 1.175)
    out = [(x, lamp_z(x) + 0.016) for x in xs] + [(x, lamp_z(x) - 0.016) for x in xs[::-1]]
    LAMP["nose"] = K.pocket(nose, out, 'y', depth=0.042, mirror=True)
    # the chine's light channels: cut into the knife edge itself, so the lens is the edge
    chf, chr_ = Geo(), Geo()
    for g, (x0, x1), key in ((chf, CH_F, "chine_f"), (chr_, CH_R, "chine_r")):
        n = int(abs(x1 - x0) / 0.02)
        pts = [chine(x0 + (x1 - x0) * k / n) for k in range(n + 1)]
        LAMP[key] = K.groove(g, [p for p in pts if p is not None], width=CH_W, depth=CH_D,
                             up=(0, 1, 0), mirror=True)
    # the stern's light bar: a channel round the top of the mouth, in the band
    tail = Geo()
    LAMP["tail"] = K.groove(tail, rear_path(), width=tail_w, depth=0.026, up=(-1, 0, 0),
                            mirror=True)
    # shut lines: the styling groove under the glass, the flush door release, the charge flap
    cut = Geo()
    K.groove(cut, [(0.78, 0.867), (0.0, 0.945), (-0.55, 0.97), (-1.05, 0.99), (-1.38, 0.985)],
             'y', width=0.0035, mirror=True)
    K.groove(cut, K.rounded(-0.81, 0.95, 0.18, 0.018), 'y', closed=True, mirror=True)
    K.groove(cut, [(-1.50 + 0.05 * cos(rad(a)), 0.955 + 0.036 * sin(rad(a)))
                   for a in range(0, 360, 60)], 'y', closed=True, mirror=True)
    return [(nose, "lamp_n", "skin", "lens_n"), (chf, "lamp_c", "skin", "lens_c"),
            (chr_, "lamp_cr", "skin", "lens_cr"), (tail, "lamp_t", "skin", "lens_t"),
            (cut, "cut", "drop")]


def build_hull():
    S = K.fill([T[k] for k in ORDER])
    PT.update(K.table(ORDER, LINES, S))
    K.build_body(
        S, panel_of, PMAT, line_crease, station_crease,
        front=dict(kind="flat", panel="prow"),
        rear=dict(center=REAR_C, depth=TAIL_D, band=BAND_W, band_panel="lightband",
                  band_lines=4, frame="tail_frame", inner="tail"),
        glass=[("glass_ws", 0.032, "trim", "frit"), ("glass_roof", 0.03, "trim", "frit"),
               ("glass_side", 0.028, "trim", "frit"), ("glass_rear", 0.035, "trim", "frit")],
        cutters=cutters, subdiv=SUBDIV, gap=GAP)


# ---------------------------------------------------------------------------------------
# emitter pods (vehicles/brands/kestrel.py)
# ---------------------------------------------------------------------------------------
PODS = dict(f=dict(xc=1.20, yc=0.805, zc=0.522, L=1.08, s=0.86),
            r=dict(xc=-1.36, yc=0.80, zc=0.537, L=1.40, s=1.0))
POD_MAT = dict(pod_top="paint", pod_side="paint2", pod_low="cladding", pod_belly="cladding",
               pod_nose="paint", tip_f="led_front", tip_r="led_accent", vent="void",
               pod_frame="cladding", pod_end="void")


# ---------------------------------------------------------------------------------------
# details
# ---------------------------------------------------------------------------------------
KEEL_X, KEEL_H = (1.17, -1.27), 0.024    # the keel lamp's channel: from x to x, its height
FIN_BASE, FIN_UP = V3((0, 0.60, 0.93)), V3((0, sin(rad(24)), cos(rad(24))))
FIN_T = 0.63
FIN = [(-1.00, 0.08), (-1.74, FIN_T), (-2.28, FIN_T), (-2.31, FIN_T - 0.11), (-2.23, 0.26),
       (-2.10, 0.0), (-1.20, 0.0)]


fin_pt = partial(kestrel.fin_pt, base=FIN_BASE, up=FIN_UP)


def build_details():
    P = PT
    # ---- the chine blade: a bright knife edge from the prow to the stern, lit at both ends
    x0, x1 = CH_F[1] - 0.012, CH_R[0] + 0.012           # between the light channels
    n = int((x0 - x1) / 0.05)
    pts = [chine(x0 + (x1 - x0) * k / n) for k in range(n + 1)]
    pts = [p + V3((0, 0.003, -0.004)) for p in pts if p is not None]
    sec = [(-0.007, -0.004), (0.007, -0.004), (0.007, 0.004), (-0.007, 0.004)]
    g = Geo()
    g.sweep(pts, sec, up=(0, 1, 0))
    g.obj("chine.blade", "rim_bright", mirror=True)
    build_lamps()

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
    # the blade's foot is a lamp: a channel up into it, a light guide in a frosted sleeve
    # over a bright reflector strip, flush under a clear lens
    g = Geo()
    keel = [(1.55, 0.44), (1.20, 0.325), (KEEL_X[0], 0.325), (KEEL_X[0], 0.325 + KEEL_H),
            (KEEL_X[1], 0.325 + KEEL_H), (KEEL_X[1], 0.325), (-1.30, 0.325), (-1.62, 0.47),
            (-1.0, 0.44), (1.0, 0.44)]
    g.prism([(x, -0.014, z) for (x, z) in keel], (0, 0.028, 0))
    g.obj("keel", "paint2", bevel=0.004)
    L = K.Lamp("lamp.keel", lit="keel_led")
    x0, x1 = KEEL_X[0] - 0.0015, KEEL_X[1] + 0.0015
    xm, lx = (x0 + x1) / 2, x0 - x1
    for sy in (1, -1):                                  # the channel's dark walls
        L.housing.box((xm, sy * 0.0125, 0.325 + KEEL_H / 2), (lx, 0.003, KEEL_H))
    L.housing.box((xm, 0, 0.325 + KEEL_H - 0.0015), (lx, 0.022, 0.003))
    L.chrome.box((xm, 0, 0.325 + KEEL_H - 0.0035), (lx - 0.004, 0.016, 0.001))
    L.guide([(x0 - 0.006, 0, 0.335), (x1 + 0.006, 0, 0.335)], r=0.0035, sleeve=1.6,
            up=(0, 0, 1))
    L.glass.box((xm, 0, 0.3265), (lx - 2 * GAP, 0.022, 0.003))
    L.obj()
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

    # ---- stern: slanted thruster slots in the mouth (the light bar over it is a lamp)
    xt = REAR_C.x + TAIL_D
    g = Geo()
    gg = Geo()
    gv = Geo()
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
        for kz in (-1, 0, 1):                           # vanes across the slot, set back
            gv.box((0, 0.068, kz * 0.024), (0.096, 0.05, 0.0035), xf=xf)
        gv.box((0, 0.068, 0), (0.0035, 0.05, 0.096), xf=xf)
    g.obj("thrusters", "rim", bevel=0.003, mirror=True)
    gg.obj("thruster.glow", "thrust", mirror=True)
    gv.obj("thruster.vanes", "grille", mirror=True)
    g = Geo()
    band = [ob for ob in K.CAR.objects if ob.name == "body.lightband"]
    if not text_on_body(g, "K E S T R E L", 0.026, 0.0, 1.0, 1, proj='X', spacing=1.2,
                        objs=band):                 # seated on the band, not floating off it
        text_flat(g, "K E S T R E L", 0.026, (-2.2085, 0, 1.0), (0, -1, 0), (0, 0, 1),
                  spacing=1.2)
    g.obj("led.name", "led_rear")

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
    # nose: four projector cells along the slot
    pk = LAMP["nose"]
    if pk is not None:
        # four lit cells, as before, now set back under the lens between bright dividers
        L = K.Lamp("lamp.nose", lit="led_front")
        for k in range(4):
            x = 1.705 - k * 0.135
            a, b = pk.on(x, lamp_z(x), back=0.009), pk.on(x - 0.095, lamp_z(x - 0.095), back=0.009)
            if a is not None and b is not None:
                L.bar([a, b], 0.015, 0.004, up=-pk.d)
        for x in (1.725, 1.59, 1.455, 1.32, 1.185):     # dividers from the lens to the floor
            q, f = pk.on(x, lamp_z(x), back=0.0045), pk.at(x, lamp_z(x), 0.0)
            if q is not None and f is not None:
                L.chrome.sweep([q, f], [(-0.0015, -0.015), (0.0015, -0.015), (0.0015, 0.015),
                                        (-0.0015, 0.015)], up=V3((0, 0, 1)))
        L.obj(mirror=True)
    # the chine's channels: a light guide down each, bright liners on the floor
    for key, lit in (("chine_f", "led_front"), ("chine_r", "led_rear")):
        tr = LAMP[key]
        if len(tr) < 2:
            continue
        fr = along(tr, 0.008, length(tr) - 0.008, 0.01)
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


def build_surface_details():
    # ---- lettering: the model on the door, a registration by the nose
    g = Geo()
    for side in (1, -1):
        text_on_body(g, "DART", 0.075, -0.30, 0.905, side, spacing=1.25)
        text_on_body(g, "KA 2-217", 0.03, 0.96, 0.832, side, spacing=1.15)
    g.obj("lettering", "stencil")
    # sensor slits printed on the side glass's foot (the shoulder groove, the door release
    # and the charge flap are cut into the hull: cutters())
    g = Geo()
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
    g.box((-0.11, 0, 0.485), (1.83, 0.80, 0.02))
    g.prism([(-0.98, -0.52, 0.50), (-0.98, 0.52, 0.50), (-0.98, 0.78, 0.84), (-0.98, 0.76, 0.98),
             (-0.98, 0.42, 1.31), (-0.98, -0.42, 1.31), (-0.98, -0.76, 0.98),
             (-0.98, -0.78, 0.84)], (0.04, 0, 0))
    g.prism([(0.90, -0.52, 0.60), (1.00, -0.52, 0.86), (0.66, -0.52, 0.93),
             (0.50, -0.52, 0.86), (0.56, -0.52, 0.55)], (0, 1.04, 0))
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
        kestrel.build_pod(tag, mat=POD_MAT, **p)
    kestrel.pod_ribs(PODS, chamfer=True)
    K.log("pods")
    build_details()
    build_interior()
    K.log("details")
    K.shoot()


main()
