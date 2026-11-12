"""Halcyon Vanta-R: a mid-engined wedge (both names made up), built on vehicles/carkit.py.

Run (always through the wrapper, one Blender job at a time on this machine):
    vehicles/blender.sh vehicles/cars/vanta_r.py --out DIR --preview
    vehicles/blender.sh vehicles/cars/vanta_r.py --out DIR --sheet [--night]
    ... --views hero,rear,wheel --res 3840 2160 --samples 160 [--blend] [--glb]

The body is nine character lines over twelve stations, cut by the wheel wells and split into
panels. Everything else (lights, vents, wing, interior) is built on the same station points,
so it follows the body when a station moves.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import carkit as K                                                  # noqa: E402
from carkit import (Geo, Matrix, V3, hypot, my, on_body, pi, rad, ribbon, shr,    # noqa: E402
                    stud, text_flat, text_on_body)

# ---------------------------------------------------------------------------------------
# dimensions
# ---------------------------------------------------------------------------------------
FA_X, RA_X = 1.40, -1.32            # axles
F_R, F_W, F_RIM = 0.35, 0.255, 0.262   # front tire radius, width, rim radius
R_R, R_W, R_RIM = 0.37, 0.325, 0.275
F_OUT, R_OUT = 0.948, 0.968         # outer face of the tires
F_ARCH, R_ARCH = 0.405, 0.428       # wheel arch radius
ARCH_ANG = (-28, 8, 42, 74, 106, 138, 172, 208)
SUBDIV = 3

# ---------------------------------------------------------------------------------------
# body: stations and character lines
# ---------------------------------------------------------------------------------------
LINES = "CHGSUMRFB"
#        C centerline top, H hood crease / roof edge, G fender inner / beltline,
#        S shoulder crest, U widest line, M cladding line, R rocker, F floor edge, B floor
ORDER = ["N0", "N1", "A1", "A2", "A3", "W0", "RF", "BP", "SC", "RA", "RB", "T1"]
PT = {}
STATIONS = []


def stations():
    T = {
        "N0": [(2.30, 0, .455), (2.275, .38, .455), (2.215, .62, .455), (2.13, .80, .45),
               (2.11, .85, .37), (2.11, .86, .26), (2.14, .84, .15), (2.22, .60, .12),
               (2.27, 0, .12)],
        "N1": [(2.05, 0, .525), (2.03, .40, .54), (2.00, .66, .585), (1.98, .885, .62),
               (1.96, .94, .50), (1.96, .935, .30), (1.98, .90, .15), (2.00, .66, .12),
               (2.05, 0, .12)],
        "A1": [(1.84, 0, .58), (1.84, .44, .60), (1.84, .70, .68), (1.84, .935, .725),
               (1.84, .975, .57), (1.84, .955, .32), (1.84, .92, .15), (1.84, .68, .12),
               (1.84, 0, .12)],
        "A2": [(1.40, 0, .685), (1.40, .50, .715), (1.40, .74, .795), (1.40, .96, .815),
               (1.40, .985, .64), (1.40, .965, .34), (1.40, .93, .15), (1.40, .68, .12),
               (1.40, 0, .12)],
        "A3": [(.975, 0, .76), (.975, .64, .775), (.975, .80, .80), (.975, .945, .795),
               (.975, .965, .61), (.975, .935, .34), (.975, .93, .15), (.975, .69, .12),
               (.975, 0, .12)],
        "W0": [(.96, 0, .79), (.86, .70, .80), (.84, .815, .80), (.84, .915, .765),
               (.84, .94, .60), (.84, .91, .34), (.84, .935, .15), (.84, .70, .12),
               (.84, 0, .12)],
        "RF": [(0.0, 0, 1.15), (-.08, .60, 1.125)] + [None] * 7,
        "BP": [(-.72, 0, 1.13), (-.72, .585, 1.105), (-.72, .86, .835), (-.72, .925, .775),
               (-.70, .82, .66), (-.70, .81, .46), (-.72, .95, .15), (-.72, .72, .12),
               (-.72, 0, .12)],
        "SC": [None, None, (-.80, .865, .85), (-.80, .95, .805), (-.775, .985, .69),
               (-.775, .975, .46), (-.78, .955, .155), (-.78, .72, .12), (-.78, 0, .12)],
        "RA": [(-1.32, 0, 1.00), (-1.32, .56, .985), (-1.32, .80, .905),
               (-1.32, .98, .865), (-1.32, 1.005, .68), (-1.32, .985, .40),
               (-1.32, .955, .16), (-1.32, .70, .13), (-1.32, 0, .13)],
        "RB": [(-1.80, 0, .915), (-1.80, .60, .905), (-1.80, .80, .87), (-1.80, .96, .845),
               (-1.80, .985, .67), (-1.80, .965, .40), (-1.80, .93, .21), (-1.80, .70, .17),
               (-1.80, 0, .17)],
        "T1": [(-2.22, 0, .885), (-2.21, .62, .875), (-2.19, .80, .845),
               (-2.15, .905, .815), (-2.13, .93, .66), (-2.13, .915, .42),
               (-2.15, .88, .28), (-2.20, .68, .25), (-2.22, 0, .25)],
    }
    for j in range(2, 9):
        T["RF"][j] = V3(T["W0"][j]).lerp(V3(T["BP"][j]), 0.62)
    for j in range(0, 2):
        T["SC"][j] = V3(T["BP"][j]).lerp(V3(T["RA"][j]), 0.12)
    S = K.fill([T[k] for k in ORDER])
    PT.update(K.table(ORDER, LINES, S))
    STATIONS[:] = S
    return S


PMAT = dict(hood="carbon", bumper_f="paint", fender_f="paint", door="paint", quarter="paint",
            deck="carbon", bumper_r="paint", roof="carbon", glass_ws="glass",
            glass_side="glass", glass_rear="glass", trim="frit", sill="cladding",
            floor="underbody", mouth="void", mouth_frame="cladding",
            lightband="gloss_black", tail="void", tail_frame="cladding", scoop="void",
            vent="void", well="well", wstrim="gloss_black", lamp_f="lamp_housing", lens_f="lens_clear",
            lamp_r="lamp_housing", lens_r="lens_red", cut="void", slit="void")
GAP = 0.00175                       # 3.5 mm shut lines
LAMP_F_W, LAMP_F_D = 0.038, 0.055   # the front light channel: width, depth
LAMP_R_W, LAMP_R_D = 0.030, 0.034
LAMP = {}                           # the light channels' paths on the skin
FRONT_C = V3((2.285, 0, 0.285))     # middle of the mouth
REAR_C = V3((-2.20, 0, 0.56))       # middle of the tail panel
BAND_W = 0.058                      # the light bands round the mouth and the tail
MOUTH_D, TAIL_D = 0.235, 0.16
CAPS = {}


def panel_of(i, j):
    if j >= 6:
        return "floor"
    if j == 5:
        return "sill"
    if i == 0:
        return "bumper_f"
    if i == 10:
        return "bumper_r"
    if j == 0:
        return ("hood", "hood", "hood", "hood", "glass_ws", "roof", "glass_rear",
                "glass_rear", "deck")[i - 1]
    if j == 1:
        return "fender_f" if i <= 4 else "glass_side" if i <= 6 else "quarter"
    if i <= 4:
        return "fender_f"
    if i <= 6:
        return "door"
    if i == 7 and j == 4:
        return "scoop"
    return "quarter"


def line_crease(i, j):
    """Crease of the edge along line j from station i to i + 1."""
    if j in (0, 8):
        return 0.0
    if j == 1:
        return 1.0 if i <= 8 else 0.7
    if j == 2:
        return 0.7 if i <= 4 else 1.0 if i <= 6 else 0.6
    if j == 3:
        return 1.0
    if j == 4:
        return 1.0 if i == 7 else 0.55
    return 1.0


def station_crease(i, j):
    """Crease of the edge on station i between lines j and j + 1."""
    if i in (0, 11):
        return 1.0
    if i == 5:
        return 1.0 if j <= 1 else 0.0
    if i == 6:
        return 1.0 if j == 0 else 0.0
    if i == 7:
        return 1.0 if j in (0, 1, 4) else 0.5 if j == 3 else 0.0
    if i == 8:
        return 1.0 if j == 4 else 0.6 if j in (3, 5) else 0.0
    if i == 1:
        return 0.5 if j <= 3 else 0.0
    return 0.0


def band_mid(i, center):
    """The middle line of the light band round an end of the body (station i), line by
    line: the band is BAND_W wide all round, square to the lip."""
    ring = [type("P", (), dict(co=V3(p)))() for p in STATIONS[i]]
    off = K._even_band(ring, center, BAND_W, True, False)
    return [V3(p) + o * 0.5 for p, o in zip(STATIONS[i], off)]


def cutters():
    """Everything cut into the hull, laid on it while it stands uncut: the wheel wells, the
    light channels under their lenses, the handles' and the charge flap's shut lines, the
    slots over the fenders."""
    P = PT
    wells = Geo()
    K.well_cutter(wells, FA_X, F_R, F_ARCH, 0.675, ARCH_ANG)
    K.well_cutter(wells, RA_X, R_R, R_ARCH, 0.62, ARCH_ANG)
    # front: a channel in the band under the nose lip, turning down the outer edge
    mid = band_mid(0, FRONT_C)
    front = Geo()
    LAMP["front"] = K.groove(front, [mid[0].lerp(mid[1], 0.45)] + mid[1:5]
                             + [mid[4].lerp(mid[5], 0.85)],
                             width=LAMP_F_W, depth=LAMP_F_D, mirror=True)
    # rear: one channel across the tail and down both sides
    mid = band_mid(-1, REAR_C)
    hp = [mid[4].lerp(mid[5], 0.8)] + mid[4:0:-1]
    path = hp + [mid[0]] + [my(p) for p in hp[::-1]]
    rear = Geo()
    LAMP["rear"] = K.groove(rear, path, width=LAMP_R_W, depth=LAMP_R_D, round=3)
    # shut lines: a flush handle in each door, the charge flap on each quarter
    cut = Geo()
    K.groove(cut, K.rounded(-0.44, 0.708, 0.17, 0.026), 'y', closed=True, mirror=True)
    K.groove(cut, K.ngon(-1.965, 0.60, 0.062, 6), 'y', closed=True, mirror=True)
    # slots over the wheels
    slits = Geo()
    for x0, ya, yb in ((1.56, 0.80, 0.925), (-1.14, 0.845, 0.95)):
        for k in range(5):
            x = x0 - k * 0.062
            K.pocket(slits, [(x + 0.008, ya), (x - 0.012, yb), (x - 0.028, yb), (x - 0.008, ya)],
                     'z', depth=0.02, mirror=True)
    return [(wells, "well"), (front, "lamp_f", "skin", "lens_f"),
            (rear, "lamp_r", "skin", "lens_r"), (cut, "cut", "drop"), (slits, "slit")]


def build_hull():
    body = K.build_body(
        stations(), panel_of, PMAT, line_crease, station_crease,
        front=dict(center=FRONT_C, depth=MOUTH_D, band=BAND_W, band_panel="lightband",
                   band_lines=5, frame="mouth_frame", inner="mouth", even=True),
        rear=dict(center=REAR_C, depth=TAIL_D, band=BAND_W, band_panel="lightband",
                  band_lines=5, frame="tail_frame", inner="tail", even=True),
        recesses=[(3, 0, 0.085, 0.03),      # hood extractor
                  (4, 4, 0.035, 0.03),      # vent behind the front wheel
                  (9, 0, 0.09, 0.025)],     # deck vents
        glass=[("glass_ws", 0.035, "wstrim", "frame"), ("glass_side", 0.028, "trim", "frit"),
               ("glass_rear", 0.04, "trim", "frit")],
        cutters=cutters, subdiv=SUBDIV, gap=GAP)
    CAPS["mouth"], CAPS["tail"] = body.caps["front"], body.caps["rear"]


# ---------------------------------------------------------------------------------------
# details on the body
# ---------------------------------------------------------------------------------------
def build_details():
    P = PT
    build_lamps()

    # ---- mouth: struts, honeycomb in the middle, slats in the side ducts, splitter
    xb = FRONT_C.x - MOUTH_D
    g = Geo()
    a = V3((2.262, 0.40, 0.392))
    b = V3((2.225, 0.45, 0.125))
    g.sweep([a, b], [(-0.03, -0.21), (0.03, -0.21), (0.022, 0.0), (-0.022, 0.0)], up=(1, 0, 0))
    g.obj("mouth.struts", "paint", bevel=0.004, mirror=True)
    g = Geo()
    half = [(p.y, p.z) for p in CAPS["mouth"]]
    poly = half + [(-y, z) for (y, z) in half[::-1]]
    g.honeycomb(poly, xb, 0.015, 0.0028, 0.012, 1, keep=lambda y, z: abs(y) < 0.46)
    g.obj("mouth.mesh", "grille")
    g = Geo()
    g.louvers((xb + 0.022, 0.43, 0.40), (xb + 0.03, 0.45, 0.15), (xb + 0.03, 0.80, 0.15),
              (xb + 0.022, 0.80, 0.40), 5, 0.05, 0.008, rad(28), out=(1, 0, 0), margin=0.04)
    g.obj("mouth.slats", "grille", bevel=0.002, mirror=True)
    # canards and badge
    g = Geo()
    for z0 in (0.20, 0.31):
        lo = [(2.115, 0.83, z0), (1.94, 0.91, z0 + 0.035), (1.94, 0.99, z0 + 0.05),
              (2.10, 0.905, z0 + 0.008)]
        g.hexa(lo + [(p[0], p[1], p[2] + 0.008) for p in lo])
    g.obj("canards", "carbon", bevel=0.002, mirror=True)
    g = Geo()
    g.lathe([(0.0, 0.002), (0.0, 0.028), (0.005, 0.024), (0.005, 0.002)], 6,
            xf=Matrix.Translation((2.294, 0, 0.428)) @ Matrix.Rotation(-pi / 2, 4, 'Z'))
    g.obj("badge", "rim_bright", bevel=0.001)
    g = Geo()
    g.prism([(2.335, 0, 0.095), (2.295, 0.58, 0.095), (2.215, 0.865, 0.095),
             (2.10, 0.945, 0.095), (1.88, 0.945, 0.095), (1.88, 0, 0.095)], (0, 0, 0.022))
    g.prism([(2.16, 0.932, 0.095), (2.12, 0.932, 0.235), (1.93, 0.932, 0.175),
             (1.90, 0.932, 0.095)], (0, 0.014, 0))
    g.obj("splitter", "carbon", bevel=0.003, mirror=True)

    xt = REAR_C.x + TAIL_D
    g = Geo()
    half = [(p.y, p.z) for p in CAPS["tail"]]
    poly = half + [(-y, z) for (y, z) in half[::-1]]

    def clear(y, z):
        return hypot(abs(y) - 0.21, z - 0.50) > 0.085 and not (abs(y) < 0.16 and abs(z - 0.335) < 0.07)
    g.honeycomb(poly, xt - 0.012, 0.021, 0.0035, 0.012, -1, keep=clear)
    g.obj("tail.mesh", "grille")
    g = Geo()
    g.prism([(-2.115, -0.86, 0.60), (-2.14, -0.86, 0.618), (-2.14, -0.86, 0.672),
             (-2.115, -0.86, 0.69), (-2.06, -0.86, 0.675), (-2.06, -0.86, 0.615)], (0, 1.72, 0))
    g.obj("tail.beam", "carbon", bevel=0.003)
    # ---- diffuser fins and exhausts
    g = Geo()
    for y in (0.0, 0.23, 0.46, 0.69):
        g.prism([(-1.76, y - 0.007, 0.185), (-2.235, y - 0.007, 0.268),
                 (-2.25, y - 0.007, 0.115), (-2.02, y - 0.007, 0.105),
                 (-1.80, y - 0.007, 0.135)], (0, 0.014, 0))
    g.obj("diffuser", "carbon", bevel=0.003, mirror=True)
    g = Geo()
    rz = Matrix.Translation((xt, 0.21, 0.50)) @ Matrix.Rotation(pi / 2, 4, 'Z')
    g.lathe([(0, 0.060), (0.13, 0.060), (0.145, 0.054), (0.145, 0.047), (0, 0.047)], 6, xf=rz)
    g.lathe([(0, 0.075), (0.02, 0.075), (0.03, 0.062), (0, 0.062)], 6, xf=rz)
    g.lathe([(0.0, 0.002), (0.0, 0.047), (0.03, 0.047), (0.03, 0.002)], 6, xf=rz)
    g.obj("exhaust", "rim", bevel=0.003, mirror=True)
    g = Geo()
    g.lathe([(0.031, 0.002), (0.031, 0.044), (0.034, 0.044), (0.034, 0.002)], 6, xf=rz)
    g.obj("exhaust.glow", "ember", mirror=True)

    # ---- wheel arch trims
    g = Geo()
    K.arch_trim(g, FA_X, F_R, F_ARCH, 0.88, F_OUT + 0.04, ARCH_ANG)
    K.arch_trim(g, RA_X, R_R, R_ARCH, 0.88, R_OUT + 0.04, ARCH_ANG)
    g.obj("arch.trims", "cladding", bevel=0.005, mirror=True)

    # ---- accent line along the sill
    g = Geo()
    path = [P[s]["M"] + V3((0, 0.004, 0.012)) for s in ("W0", "RF", "BP")]
    path[0] = path[0] + V3((-0.05, 0, 0))
    path[-1] = path[-1] + V3((0.04, 0, 0))
    g.sweep(path, [(-0.004, -0.005), (0.004, -0.005), (0.004, 0.005), (-0.004, 0.005)],
            up=(0, 0, 1))
    g.obj("led.sill", "led_accent", mirror=True)

    # ---- slats: scoop, fender vent, hood extractor, deck vents, engine cover
    g = Geo()
    g.louvers(P["BP"]["U"], P["BP"]["M"], P["SC"]["M"], P["SC"]["U"], 5, 0.04, 0.007,
              rad(20), out=(1, 0.3, 0), lift=0.004, margin=0.08)
    gp = Geo()
    q = shr([P["A3"]["U"], P["A3"]["M"], P["W0"]["M"], P["W0"]["U"]], 0.16, -0.008, (0, 1, 0))
    gp.louvers(q[0], q[3], q[2], q[1], 4, 0.034, 0.006, rad(35), out=(0, 1, 0))
    gp.obj("vent.slats", "paint", bevel=0.002, mirror=True)
    q = shr([P["A2"]["C"], P["A2"]["H"], P["A3"]["H"], P["A3"]["C"]], 0.30, -0.008, (0, 0, 1))
    g.louvers(q[0], q[3], q[2], q[1], 4, 0.045, 0.007, rad(-30), out=(0, 0, 1))
    q = shr([P["RA"]["C"], P["RA"]["H"], P["RB"]["H"], P["RB"]["C"]], 0.30, -0.008, (0, 0, 1))
    g.louvers(q[0], q[3], q[2], q[1], 4, 0.045, 0.007, rad(30), out=(0, 0, 1))
    g.obj("slats", "grille", bevel=0.002, mirror=True)
    g = Geo()
    a, b = P["BP"]["H"].lerp(P["BP"]["C"], 0.08), P["RA"]["H"].lerp(P["RA"]["C"], 0.08)
    g.louvers(a, b, my(b), my(a), 6, 0.075, 0.012, rad(10), out=(0, 0, 1), lift=0.022,
              margin=0.07)
    g.obj("engine.louvers", "gloss_black", bevel=0.003)

    # ---- mirrors: camera pods on blades
    g = Geo()
    g.sweep([(0.63, 0.895, 0.772), (0.615, 0.985, 0.800)],
            [(-0.03, -0.004), (0.03, -0.004), (0.03, 0.004), (-0.03, 0.004)], up=(0, 0, 1))
    g.obj("mirror.stalks", "cladding", bevel=0.002, mirror=True)
    g = Geo()
    g.hexa([(0.69, 0.975, 0.792), (0.69, 1.005, 0.792), (0.53, 1.03, 0.782),
            (0.53, 0.965, 0.782), (0.675, 0.978, 0.812), (0.675, 1.002, 0.812),
            (0.53, 1.025, 0.835), (0.53, 0.970, 0.835)])
    g.obj("mirror.pods", "paint", bevel=0.004, mirror=True)
    g = Geo()
    g.box((0.5285, 0.9975, 0.808), (0.004, 0.045, 0.036))
    g.obj("mirror.lens", "gloss_black", mirror=True)

    # ---- bolts on the arch trims
    g = Geo()
    K.arch_bolts(g, FA_X, F_R, F_ARCH, F_OUT + 0.04, ARCH_ANG)
    K.arch_bolts(g, RA_X, R_R, R_ARCH, R_OUT + 0.04, ARCH_ANG)
    g.obj("arch.bolts", "rim_bright", mirror=True)

    # ---- plate
    g = Geo()
    g.box((xt - 0.012, 0, 0.335), (0.012, 0.27, 0.095))
    g.obj("plate", "gloss_black", bevel=0.003)
    g = Geo()
    text_flat(g, "VB 27-881", 0.05, (xt - 0.0185, 0, 0.335), (0, -1, 0), (0, 0, 1), spacing=1.1)
    g.obj("plate.glyphs", "led_accent")

    build_surface_details()

    # ---- wing
    g = Geo()
    g.prism([(-2.00, -0.86, 1.022), (-2.06, -0.86, 1.042), (-2.20, -0.86, 1.048),
             (-2.32, -0.86, 1.062), (-2.32, -0.86, 1.050), (-2.20, -0.86, 1.030),
             (-2.06, -0.86, 1.016)], (0, 1.72, 0))
    g.obj("wing.blade", "carbon", bevel=0.003)
    g = Geo()
    g.box((-2.3215, 0, 1.056), (0.004, 0.50, 0.006))
    g.obj("led.wing", "led_rear")
    # side skirt blades with a winglet at the back
    g = Geo()
    g.prism([(0.93, 0.90, 0.126), (0.93, 0.975, 0.126), (-0.70, 0.995, 0.126),
             (-0.86, 1.0, 0.126), (-0.86, 0.90, 0.126)], (0, 0, 0.016))
    g.prism([(-0.60, 0.985, 0.13), (-0.86, 0.985, 0.13), (-0.86, 0.985, 0.225),
             (-0.80, 0.985, 0.225)], (0, 0.012, 0))
    g.obj("skirt", "carbon", bevel=0.003, mirror=True)
    g = Geo()
    g.prism([(-1.97, 0.86, 0.995), (-2.34, 0.86, 1.00), (-2.35, 0.86, 1.09),
             (-2.12, 0.86, 1.078), (-1.99, 0.86, 1.045)], (0, 0.014, 0))
    g.prism([(-1.86, 0.45, 0.895), (-2.10, 0.45, 0.875), (-2.21, 0.45, 1.04),
             (-2.09, 0.45, 1.035)], (0, 0.022, 0))
    g.obj("wing.plates", "paint", bevel=0.003, mirror=True)


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


def build_lamps():
    """What stands in the light channels, under their lenses."""
    # front: a light guide along the whole channel, a row of small projectors in cups on
    # the run under the lip, bright liners on the floor
    total = K_len(LAMP["front"])
    fr = along(LAMP["front"], 0.012, total - 0.012, 0.012)
    L = K.Lamp("lamp.front", lit="led_front")
    L.guide([q - n * 0.009 - sd * 0.0125 for q, n, _, sd in fr], r=0.0032, sleeve=1.5,
            up=[n for _, n, _, _ in fr])
    for q, n, _, sd in along(LAMP["front"], 0.30, 0.30 + 2 * 0.085, 0.085):
        L.projector(q - n * 0.006 + sd * 0.0055, n, r=0.0115, depth=0.045, seg=20)
    L.obj(mirror=True)
    # rear: a red guide round the whole tail behind bright ribs
    rr = along(LAMP["rear"], 0.012, K_len(LAMP["rear"]) - 0.012, 0.012)
    L = K.Lamp("lamp.rear", lit="led_rear")
    ups = [n for _, n, _, _ in rr]
    L.chrome.sweep([q - n * (LAMP_R_D - 0.003) for q, n, _, _ in rr],
                   [(-0.010, -0.001), (0.010, -0.001), (0.010, 0.001), (-0.010, 0.001)], up=ups)
    L.guide([q - n * 0.016 for q, n, _, _ in rr], r=0.004, sleeve=1.6, up=ups)
    for q, n, tg, sd in along(LAMP["rear"], 0.03, K_len(LAMP["rear"]) - 0.03, 0.032):
        L.chrome.box(q - n * 0.018, (0.0022, LAMP_R_W - 0.006, 0.022),
                     rot=Matrix((tg, sd, n)).transposed())
    L.obj()


def K_len(tr):
    return sum((b[0] - a[0]).length for a, b in zip(tr, tr[1:]))


def build_surface_details():
    # roof: a slim light bar and a fin, seated on the roof as built
    zr = on_body(-0.10, 0.0, 'z')[0].z
    g = Geo()
    g.prism([(-0.03, -0.17, zr - 0.004), (-0.07, -0.17, zr + 0.016), (-0.13, -0.17, zr + 0.016),
             (-0.18, -0.17, zr - 0.004)], (0, 0.34, 0))
    zf = on_body(-0.60, 0.0, 'z')[0].z
    g.prism([(-0.50, -0.006, zf - 0.005), (-0.62, -0.006, zf + 0.065), (-0.66, -0.006, zf + 0.065),
             (-0.69, -0.006, zf - 0.005)], (0, 0.012, 0))
    g.obj("roof.pod", "cladding", bevel=0.004)
    g = Geo()
    g.box((-0.048, 0, zr + 0.007), (0.005, 0.28, 0.005), rot=Matrix.Rotation(rad(-22), 3, 'Y'))
    g.obj("led.roof", "led_accent")
    # parking sensors on the nose, pins on the hood
    g = Geo()
    gp = Geo()
    for y in (0.24, 0.60, -0.24, -0.60):
        loc, n = on_body(y, 0.495, 'x')
        stud(g, loc, n, [(-0.002, 0.001), (-0.002, 0.011), (0.0015, 0.011), (0.0015, 0.001)], 12)
    for y in (0.37, -0.37):
        loc, n = on_body(1.90, y, 'z')
        stud(gp, loc, n, [(-0.002, 0.001), (-0.002, 0.019), (0.003, 0.019), (0.003, 0.001)], 16)
        stud(gp, loc, n, [(0.003, 0.001), (0.003, 0.0045), (0.013, 0.0045), (0.013, 0.001)], 8)
        stud(g, loc, n, [(0.003, 0.012), (0.003, 0.016), (0.0045, 0.016), (0.0045, 0.012)], 16)
    g.obj("sensors", "gloss_black")
    gp.obj("hood.pins", "rim_bright", bevel=0.0008)
    # lettering
    g = Geo()
    for side in (1, -1):
        text_on_body(g, "VANTA-R", 0.05, 0.50, 0.475, side, spacing=1.15)
        text_on_body(g, "HV 800", 0.016, -1.965, 0.515, side, spacing=1.2)
        text_flat(g, "09", 0.06, (-2.17, side * 0.8745, 1.04), (-side, 0, 0), (0, 0, 1))
    g.obj("lettering", "decal")
    g = Geo()
    text_flat(g, "H A L C Y O N", 0.034, (-2.1412, 0, 0.645), (0, -1, 0), (0, 0, 1), spacing=1.3)
    g.obj("led.name", "led_rear")
    # wiper: an arm on a boss at the cowl, its blade lying on the glass
    g, gb = Geo(), Geo()
    a, b = on_body(0.945, -0.04, 'z')[0], on_body(0.86, 0.58, 'z')[0]
    K.wiper(g, gb, on_body(0.985, 0.14, 'z')[0], a, b)
    g.obj("wiper", "cladding", bevel=0.0012)
    gb.obj("wiper.blade", "rubber")
    # markers and decals
    g = Geo()
    ribbon(g, [(2.03, 0.425), (1.935, 0.44)], 'y', 0.012)
    g.obj("led.marker", "led_accent", mirror=True)
    g = Geo()
    x = -0.30
    for k, w in enumerate((0.006, 0.012, 0.004, 0.004, 0.010, 0.006, 0.014, 0.004, 0.008,
                           0.004, 0.012, 0.006)):
        ribbon(g, [(x - w / 2, 0.515), (x - w / 2, 0.56)], 'y', w)
        x -= w + 0.006
    for k in range(4):
        ribbon(g, [(-1.86 - k * 0.04, 0.735), (-1.88 - k * 0.04, 0.775)], 'y', 0.014)
    g.obj("decals", "decal", mirror=True)


# ---------------------------------------------------------------------------------------
# interior
# ---------------------------------------------------------------------------------------
def build_interior():
    g = Geo()
    g.box((0.0, 0, 0.15), (1.45, 1.6, 0.03))
    g.prism([(-0.66, -0.80, 0.14), (-0.66, 0.80, 0.14), (-0.66, 0.84, 0.80),
             (-0.66, 0.60, 1.06), (-0.66, -0.60, 1.06), (-0.66, -0.84, 0.80)], (0.04, 0, 0))
    g.prism([(0.80, -0.78, 0.50), (0.80, -0.78, 0.775), (0.52, -0.78, 0.775),
             (0.40, -0.78, 0.70), (0.44, -0.78, 0.50)], (0, 1.56, 0))
    g.box((0.05, 0, 0.27), (0.95, 0.2, 0.24))
    g.obj("interior.tub", "interior", bevel=0.006)
    g = Geo()
    tilt = Matrix.Rotation(rad(-20), 3, 'Y')
    for y in (0.37, -0.37):
        g.box((-0.02, y, 0.30), (0.50, 0.46, 0.12))
        g.box((-0.40, y, 0.62), (0.11, 0.44, 0.62), rot=tilt)
        g.box((-0.535, y, 0.965), (0.07, 0.22, 0.15), rot=tilt)
        for s in (-1, 1):
            g.box((-0.02, y + s * 0.235, 0.33), (0.46, 0.05, 0.16))
            g.box((-0.385, y + s * 0.225, 0.58), (0.14, 0.05, 0.50), rot=tilt)
    g.obj("interior.seats", "seat", bevel=0.012, segs=3)
    g = Geo()
    wheel = (Matrix.Translation((0.33, 0.37, 0.75)) @ Matrix.Rotation(rad(-70), 4, 'Y')
             @ Matrix.Rotation(pi / 2, 4, 'X'))
    g.lathe([(-0.012, 0.155), (0.0, 0.167), (0.012, 0.155), (0.0, 0.143)], 24, xf=wheel)
    g.box((0.40, 0.37, 0.72), (0.16, 0.05, 0.05))
    g.obj("interior.wheel", "interior", sharp=40)
    g = Geo()
    scr = Matrix.Rotation(rad(-25), 3, 'Y')
    g.box((0.41, 0.0, 0.745), (0.008, 0.30, 0.08), rot=scr)
    g.box((0.47, 0.37, 0.795), (0.008, 0.26, 0.05), rot=scr)
    g.obj("interior.screens", "screen")
    # power unit under the rear glass
    g = Geo()
    ge = Geo()
    g.box((-1.03, 0, 0.80), (0.60, 1.04, 0.02))
    up = Matrix.Rotation(pi / 2, 4, 'X')
    g.lathe([(0.0, 0.004), (0.0, 0.17), (0.10, 0.17), (0.13, 0.12), (0.13, 0.004)], 8,
            xf=Matrix.Translation((-1.02, 0, 0.81)) @ up)
    ge.lathe([(0.045, 0.171), (0.045, 0.176), (0.06, 0.176), (0.06, 0.171)], 8,
             xf=Matrix.Translation((-1.02, 0, 0.81)) @ up)
    ge.lathe([(0.131, 0.02), (0.131, 0.09), (0.134, 0.09), (0.134, 0.02)], 8,
             xf=Matrix.Translation((-1.02, 0, 0.81)) @ up)
    along = Matrix.Rotation(pi / 2, 4, 'Z')
    for y in (0.30, -0.30):
        xf = Matrix.Translation((-0.80, y, 0.875)) @ along
        g.lathe([(0.0, 0.004), (0.0, 0.058), (0.44, 0.058), (0.44, 0.004)], 12, xf=xf)
        for k in range(4):
            ge.lathe([(0.06 + k * 0.1, 0.058), (0.06 + k * 0.1, 0.061), (0.075 + k * 0.1, 0.061),
                      (0.075 + k * 0.1, 0.058)], 12, xf=xf)
        g.sweep([(-1.02, y * 0.45, 0.90), (-1.02, y * 0.8, 0.93), (-1.02, y, 0.90)],
                [(-0.012, -0.012), (0.012, -0.012), (0.012, 0.012), (-0.012, 0.012)],
                up=(1, 0, 0))
    g.obj("power.unit", "rim", bevel=0.004)
    ge.obj("power.glow", "ember")


# ---------------------------------------------------------------------------------------
# views of its own, and the build
# ---------------------------------------------------------------------------------------
K.VIEWS.update(

    wheel=dict(dir=(0.55, 1.0, 0.12), lens=85, target=(FA_X, 0.9, 0.36), fit=("tire.fl",),
               margin=0.0),
    nose=dict(dir=(1.0, 0.45, 0.10), lens=85, target=(2.1, 0.45, 0.35), dist=2.6),
    tail=dict(dir=(-1.0, -0.4, 0.14), lens=85, target=(-2.1, -0.3, 0.6), dist=3.0),
    cabin=dict(dir=(0.35, 1.0, 0.5), lens=85, target=(-0.2, 0.3, 0.9), dist=3.4),
)


def main():
    K.materials()           # the kit's default palette is this car's: titanium and carbon
    build_hull()
    K.log("hull")
    build_details()
    build_interior()
    K.log("details")
    for side, s in ((1, "l"), (-1, "r")):
        K.build_wheel("f" + s, FA_X, F_R, F_W, F_RIM, F_OUT, side)
        K.build_wheel("r" + s, RA_X, R_R, R_W, R_RIM, R_OUT, side)
    K.log("wheels")
    K.shoot()


main()
