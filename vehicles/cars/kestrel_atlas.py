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
from functools import partial                                       # noqa: E402

import carkit as K                                                  # noqa: E402
from brands import kestrel                                          # noqa: E402
from brands.kestrel import chine, plate, rib                        # noqa: E402
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
            trim="frit", visor="visor", lightband="gloss_black",
            prow_frame="cladding", prow_in="visor",
            tail_frame="cladding", tail="void", vent="void", lamp_n="lamp_housing",
            lamp_c="lamp_housing", lens_c="lens_clear",
            lamp_cr="lamp_housing", lens_cr="lens_red", lamp_t="lamp_housing",
            lens_t="lens_red", cut="void")
GAP = 0.00175                       # 3.5 mm shut lines
LAMP = {}                           # the lamps' pockets and channels on the skin
CH_F = (2.70, 1.92)                 # the chine's front light channel, from x to x
CH_R = (-2.03, -2.33)               # and its rear one
CH_W, CH_D = 0.018, 0.022           # their width (up the knife edge) and depth
NOSE_Y = (0.075, 0.193, 0.311, 0.429)   # the work lamps' cells across the prow's slot
NOSE_Z = 0.895                          # and their height
NOSE_C, NOSE_W, NOSE_H = 0.252, 0.47, 0.068     # the slot cut for them: middle, width, height


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


def band_mid(names, w=BAND_W * 0.5):
    """The stern's lip points (lines of P8) moved w in, square to the lip, as the even
    band is drawn: the middle of the band at each."""
    ring = [PT["P8"][n] for n in "LKSMRC"]
    ring.append(V3((ring[-1].x, -ring[-2].y, ring[-2].z)))      # past the middle, mirrored
    out = {}
    for i, n in enumerate("LKSMRC"):
        if n not in names:
            continue
        ns = []
        for a, b in ((ring[i - 1], ring[i]), (ring[i], ring[i + 1])):
            ey, ez = b.y - a.y, b.z - a.z
            ln = (ey * ey + ez * ez) ** 0.5 or 1.0
            ny, nz = -ez / ln, ey / ln
            if ny * (REAR_C.y - (a.y + b.y) / 2) + nz * (REAR_C.z - (a.z + b.z) / 2) < 0:
                ny, nz = -ny, -nz
            ns.append((ny, nz))
        d = max(0.3, 1 + ns[0][0] * ns[1][0] + ns[0][1] * ns[1][1])
        out[n] = ring[i] + V3((0, (ns[0][0] + ns[1][0]) / d * w, (ns[0][1] + ns[1][1]) / d * w))
    return out


def rear_paths():
    """The stern bar's two runs in the middle of the band: round the outer corner (from the
    chine to the rail's end) and along the top of the mouth under the bed's edge."""
    m = band_mid("KSRC")
    return ([m["K"], m["S"]], [m["R"], m["R"].lerp(m["C"], 0.80)])


def cutters():
    """Everything cut into the hull, laid on it while it stands uncut: the work lamps' slot
    in the prow's mouth, the light channels along the chine's knife edge and round the
    stern's lip, the line under the shoulder along the bed, the door release and the charge
    flap."""
    # work lamps: a slot across each half of the mouth's back wall (its lens and surround
    # stand proud of the wall: build_lamps)
    nose = Geo()
    LAMP["nose"] = K.pocket(nose, K.rounded(NOSE_C, NOSE_Z, NOSE_W, NOSE_H, 0.012), 'x',
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
    for k, path in enumerate(rear_paths()):
        LAMP["tail%d" % k] = K.groove(tail, path, width=0.014, depth=0.024, up=(-1, 0, 0),
                                      step=0.01, mirror=True)
    # shut lines: the line under the shoulder along the bed (a point every 4 cm, the flank
    # is flat there), the door's flush release, the six-sided charge flap
    cut = Geo()
    K.groove(cut, [(0.60, 1.30), (-2.05, 1.30)], 'y', width=0.0035, step=0.04, mirror=True)
    K.groove(cut, K.rounded(1.02, 1.232, 0.20, 0.018), 'y', closed=True, mirror=True)
    K.groove(cut, [(0.30 + 0.05 * cos(rad(a)), 1.13 + 0.038 * sin(rad(a)))
                   for a in range(0, 360, 60)], 'y', closed=True, mirror=True)
    return [(nose, "lamp_n"), (chf, "lamp_c", "skin", "lens_c"),
            (chr_, "lamp_cr", "skin", "lens_cr"), (tail, "lamp_t", "skin", "lens_t"),
            (cut, "cut", "drop")]


def build_hull():
    S = K.fill([T[k] for k in ORDER])
    PT.update(K.table(ORDER, LINES, S))
    K.build_body(
        S, panel_of, PMAT, 1.0, station_crease,
        front=dict(center=FRONT_C, depth=FRONT_D, band=0.026, frame="prow_frame",
                   inner="prow_in", reach=0.06),
        rear=dict(center=REAR_C, depth=TAIL_D, band=BAND_W, band_panel="lightband",
                  band_lines=4, frame="tail_frame", inner="tail", even=True),
        glass=[(p, i, "trim", "frit") for p, i in (
            ("glass_ws", 0.036), ("glass_sf", 0.028), ("glass_s", 0.028),
            ("glass_rear", 0.034))],
        cutters=cutters, subdiv=SUBDIV, gap=GAP)


# ---------------------------------------------------------------------------------------
# helpers of this car (chine, rib, plate, the fin plane and the pods are the family's:
# vehicles/brands/kestrel.py)
# ---------------------------------------------------------------------------------------
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
PODS = dict(f=dict(xc=1.74, yc=0.895, zc=0.585, L=1.00, s=0.88),
            m=dict(xc=-0.02, yc=0.908, zc=0.590, L=1.16, s=1.02),
            r=dict(xc=-1.62, yc=0.915, zc=0.600, L=1.34, s=1.14))
POD_MAT = dict(pod_top="paint", pod_side="paint2", pod_low="cladding", pod_belly="cladding",
               pod_nose="paint", tip_f="led_front", tip_m="led_accent", tip_r="led_accent",
               vent="void", pod_frame="cladding", pod_end="void")



# ---------------------------------------------------------------------------------------
# fins on the rail ends, the hoist beam between them
# ---------------------------------------------------------------------------------------
CANT = 20
FIN_BASE, FIN_UP = V3((0, 0.80, Z_RAIL)), V3((0, sin(rad(CANT)), cos(rad(CANT))))
FIN_T = 0.70
FIN = [(-1.30, 0.0), (-2.22, FIN_T), (-2.80, FIN_T), (-2.84, FIN_T - 0.10), (-2.64, 0.22),
       (-2.45, -0.27), (-2.10, -0.03)]
BEAM_A, BEAM_T = -2.42, 0.60


fin_pt = partial(kestrel.fin_pt, base=FIN_BASE, up=FIN_UP)


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
    beam = g.obj("hoist.beam", "paint2", bevel=0.004)
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
    # the high tail light: a lamp each side of the maker's name, standing proud of the
    # beam's rear face, three red cells behind a red lens in a dark rim
    L = K.Lamp("lamp.beam", lit="led_rear", glass="lens_red")
    xf = BEAM_A - 0.0655                                # the beam's rear face at its middle
    strip_lamp(L, xf, -1, 0.27, 0.93, zb, 0.040, cells=3)
    L.obj(mirror=True)
    g = Geo()
    if not text_on_body(g, "K E S T R E L", 0.030, 0.0, zb - 0.012, 1, proj='X', spacing=1.2,
                        objs=[beam]):                   # seated on the beam, not floating
        text_flat(g, "K E S T R E L", 0.030, (xf - 0.001, 0, zb - 0.012), (0, -1, 0),
                  (0, 0, 1), spacing=1.2)
    ob = g.obj("led.name", "led_rear")
    md = ob.modifiers.new("solid", 'SOLIDIFY')  # letters 5 mm proud: a game pack keeps them
    md.thickness = 0.008                        # as they are (laid flat, they are baked
    md.offset = 0.0                             # down and lose strokes)
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
KEEL_X, KEEL_H = (1.98, -1.72), 0.024    # the keel lamp's channel: from x to x, its height
KEEL_Z = 0.41                            # the keel blade's foot


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


def strip_lamp(L, x0, sgn, y0, y1, zc, h, cells=1):
    """A lamp standing proud of a face at x = x0 that looks along sgn x (-1: astern), from
    y0 to y1 and h high about zc: a dark back plate and rim, bright dividers between its
    cells, the lit face right under a lens set in the rim."""
    ym, ly = (y0 + y1) / 2, y1 - y0

    def bx(geo, a, b, y, w, z, hh):                 # a box from a to b out of the face
        geo.box((x0 + sgn * (a + b) / 2, y, z), (b - a, w, hh))
    bx(L.housing, -0.006, 0.003, ym, ly, zc, h)                     # the back plate
    for z in (zc - h / 2 + 0.002, zc + h / 2 - 0.002):              # the rim
        bx(L.housing, 0.003, 0.011, ym, ly, z, 0.004)
    for y in (y0 + 0.002, y1 - 0.002):
        bx(L.housing, 0.003, 0.011, y, 0.004, zc, h)
    for k in range(1, cells):                                       # dividers
        bx(L.chrome, 0.003, 0.0075, y0 + ly * k / cells, 0.003, zc, h - 0.008)
    bx(L.emit(), 0.003, 0.0055, ym, ly - 0.008, zc, h - 0.012)      # the lit face
    bx(L.glass, 0.0075, 0.0105, ym, ly - 0.008, zc, h - 0.008)      # the lens


def build_lamps():
    """What stands in the lamps' pockets and channels, under their lenses."""
    # prow: four work lamp cells across each half of the slot, standing a little proud of
    # its back wall between bright dividers that run to the slot's floor, under a clear lens
    # in a dark surround that stands proud round the slot (the game pack's far LOD draws the
    # wall across the slot: lamps behind it would be lost there)
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
            L.bar([wall(y - 0.046, NOSE_Z, 0.003), wall(y + 0.046, NOSE_Z, 0.003)], 0.046,
                  0.004, up=out)
        for y in (0.022, 0.134, 0.252, 0.370, 0.482):   # dividers from the lens to the floor
            q = wall(y, NOSE_Z, 0.009)
            L.chrome.sweep([q, floor(q)], [(-0.0015, -0.029), (0.0015, -0.029),
                                           (0.0015, 0.029), (-0.0015, 0.029)],
                           up=V3((0, 0, 1)))
        rim = [wall(y, z) for y, z in K.rounded(NOSE_C, NOSE_Z, NOSE_W + 0.008,
                                                 NOSE_H + 0.008, 0.016)]
        L.housing.sweep(rim, [(-0.004, -0.004), (0.004, -0.004), (0.004, 0.012),
                              (-0.004, 0.012)], up=out, closed=True)
        lens = [wall(y, z, 0.0095) for y, z in K.rounded(NOSE_C, NOSE_Z, NOSE_W + 0.002,
                                                          NOSE_H + 0.002, 0.013)]
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
    # the stern's bar: a red guide behind bright ribs, in two runs
    for key in ("tail0", "tail1"):
        tr = LAMP[key]
        if len(tr) < 2:
            continue
        rr = along(tr, 0.008, length(tr) - 0.008, 0.01)
        ups = [n for _, n, _, _ in rr]
        L = K.Lamp("lamp." + key, lit="led_rear")
        L.chrome.sweep([q - n * 0.021 for q, n, _, _ in rr],
                       [(-0.005, -0.0005), (0.005, -0.0005), (0.005, 0.0005),
                        (-0.005, 0.0005)], up=ups)
        L.guide([q - n * 0.009 for q, n, _, _ in rr], r=0.004, sleeve=0, up=ups)
        for q, n, tg, sd in along(tr, 0.02, length(tr) - 0.02, 0.028):
            L.chrome.box(q - n * 0.015, (0.002, 0.005, 0.010),
                         rot=Matrix((tg, sd, n)).transposed())
        L.obj(mirror=True)


def build_details():
    # ---- the chine blade: a bright knife edge between the light channels at its ends
    x0, x1 = CH_F[1] - 0.012, CH_R[0] + 0.012
    n = int((x0 - x1) / 0.05)
    pts = [chine(x0 + (x1 - x0) * k / n) for k in range(n + 1)]
    pts = [p + V3((0, 0.003, -0.004)) for p in pts if p is not None]
    sec = [(-0.007, -0.004), (0.007, -0.004), (0.007, 0.004), (-0.007, 0.004)]
    g = Geo()
    g.sweep(pts, sec, up=(0, 1, 0))
    g.obj("chine.blade", "rim_bright", mirror=True)
    build_lamps()

    # ---- the prow: a sensor slit over the work lamps' slot, two mooring horns
    xm = FRONT_C.x - FRONT_D
    gs = Geo()
    gs.box((xm + 0.006, 0.26, 0.952), (0.012, 0.40, 0.010))
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
    # the blade's foot is a lamp: a channel up into it, a light guide in a frosted sleeve
    # over a bright reflector strip, flush under a clear lens
    g = Geo()
    kz = KEEL_Z
    keel = [(2.52, 0.625), (2.05, kz), (KEEL_X[0], kz), (KEEL_X[0], kz + KEEL_H),
            (KEEL_X[1], kz + KEEL_H), (KEEL_X[1], kz), (-1.80, kz), (-2.15, 0.575),
            (-1.4, 0.535), (1.6, 0.535)]
    g.prism([(x, -0.016, z) for (x, z) in keel], (0, 0.032, 0))
    g.obj("keel", "paint2", bevel=0.004)
    L = K.Lamp("lamp.keel", lit="keel_led")
    x0, x1 = KEEL_X[0] - 0.0015, KEEL_X[1] + 0.0015
    xk, lx = (x0 + x1) / 2, x0 - x1
    for sy in (1, -1):                                  # the channel's dark walls
        L.housing.box((xk, sy * 0.0145, kz + KEEL_H / 2), (lx, 0.003, KEEL_H))
    L.housing.box((xk, 0, kz + KEEL_H - 0.0015), (lx, 0.026, 0.003))
    L.chrome.box((xk, 0, kz + KEEL_H - 0.0035), (lx - 0.004, 0.020, 0.001))
    L.guide([(x0 - 0.006, 0, kz + 0.010), (x1 + 0.006, 0, kz + 0.010)], r=0.0035, sleeve=1.6,
            up=(0, 0, 1))
    L.glass.box((xk, 0, kz + 0.0015), (lx - 2 * GAP, 0.026, 0.003))
    L.obj()
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

    # ---- stern: six slanted slot thrusters, a stern post between the banks (the light
    # bar round the top of the mouth is a lamp)
    xt = REAR_C.x + TAIL_D
    g = Geo()
    gg = Geo()
    gv = Geo()
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
        for kz in (-1, 0, 1):                           # vanes across the slot, set back
            gv.box((0, 0.068, kz * 0.024), (0.096, 0.05, 0.0035), xf=xf)
        gv.box((0, 0.068, 0), (0.0035, 0.05, 0.096), xf=xf)
    g.obj("thrusters", "rim", bevel=0.003, mirror=True)
    gg.obj("thruster.glow", "thrust", mirror=True)
    gv.obj("thruster.vanes", "grille", mirror=True)
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
    # (the line under the shoulder along the bed, the door's release and the charge flap
    # are cut into the hull: cutters())
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
    L = K.Lamp("lamp.work", lit="lamp")                 # work lamps over the bed
    for sy in (1, -1):
        strip_lamp(L, 0.740, -1, sy * 0.36 - 0.11, sy * 0.36 + 0.11, zr + 0.016, 0.044,
                   cells=2)
    L.obj()
    # ---- pitot pins, studs on the panels
    g = Geo()
    gp = Geo()
    for (x, y) in ((2.62, 0.40), (2.42, 0.62), (1.30, 0.50), (0.84, 0.50), (0.84, 0.15)):
        loc, n = on_body(x, y, 'z')
        if loc is not None:
            stud(gp, loc, n, [(-0.002, 0.001), (-0.002, 0.008), (0.002, 0.008), (0.002, 0.001)], 6)
    for k in range(7):                                  # a row of fasteners down each flank
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
    # the tub follows the hull's flare: narrow at the floor, as wide as the cab at the
    # shoulder (step A found the dash and the floor's front corners out under the prow)
    g = Geo()
    g.prism([(0.70, -0.60, 0.59), (1.60, -0.60, 0.59), (1.84, -0.56, 0.59), (2.12, -0.40, 0.59),
             (2.12, 0.40, 0.59), (1.84, 0.56, 0.59), (1.60, 0.60, 0.59), (0.70, 0.60, 0.59)],
            (0, 0, 0.02))

    def dash_w(z):                                      # the hull's half width less 3 cm
        return min(0.72, 0.50 + (z - 0.61) * 0.95)
    dash = [(2.14, 0.61), (2.14, 1.12), (1.96, 1.17), (1.78, 1.10), (1.84, 0.84), (1.84, 0.61)]
    n = len(dash)
    g.add([(x, -dash_w(z), z) for x, z in dash] + [(x, dash_w(z), z) for x, z in dash],
          [tuple(range(n)), tuple(range(n, 2 * n))]
          + [(i, (i + 1) % n, n + (i + 1) % n, n + i) for i in range(n)])
    g.box((1.30, 0, 0.71), (1.00, 0.17, 0.22))
    g.prism([(0.775, -0.58, 0.59), (0.775, 0.58, 0.59), (0.775, 0.87, 0.90),
             (0.775, 0.84, 1.45), (0.775, -0.84, 1.45), (0.775, -0.87, 0.90)],
            (0.05, 0, 0))                               # the cab's back wall, inside
    for sy in (1, -1):                                  # door cards under the glass
        g.prism([(1.84, sy * 0.55, 0.61), (1.84, sy * 0.59, 0.61), (1.84, sy * 0.80, 0.80),
                 (1.84, sy * 0.82, 1.26), (1.84, sy * 0.75, 1.26), (1.84, sy * 0.70, 0.86)],
                (-1.04, 0, 0))
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
        kestrel.build_pod(tag, mat=POD_MAT, heavy=True, **p)
    kestrel.pod_ribs(PODS)
    K.log("pods")
    build_details()
    build_fins()
    build_bed()
    build_interior()
    K.log("details")
    # the load stands where it was strapped, the beacon and the roof's sensor blade on one
    # side of the roof, the yoke is the pilot's
    K.meant("symmetry", "cases", "case.*", "straps", "strap.ratchets", "led.beacon",
            "roof.gear", "interior.yoke")
    K.shoot(extra=dict(view="top", size=(1040, 420)))


main()
