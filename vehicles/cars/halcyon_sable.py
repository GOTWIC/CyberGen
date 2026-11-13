"""Halcyon Sable: a four-door fastback grand tourer (both names made up), on vehicles/carkit.py.

Run (always through the wrapper, one Blender job at a time on this machine):
    vehicles/blender.sh vehicles/cars/halcyon_sable.py --out DIR --preview
    vehicles/blender.sh vehicles/cars/halcyon_sable.py --out DIR --sheet

The Vanta-R's sibling: the same carbon spine, octagonal bolted arches, corner-turning nose
strip, honeycomb, scoop and turbine wheels, on a long wheelbase with four seats. Its own
ideas: the spine is one unbroken piece, an hourglass in plan, wide on the nose, a slim rib
that splits the windshield and carries a glass roof, wide again on the tail; a prow in the
mouth where the spine comes down; a closed halo of light round the tail; coach doors with no
pillar between them; a low spoiler blade instead of a wing.

The body is ten character lines over thirteen stations, cut by the wheel wells and split
into panels. Everything else hangs on the same station points. Since step B the nose strip
and the tail halo are light channels cut into the bands under lenses, with lamps inside
(the Vanta-R's family), and the handles and the charge flap are cut through the skin.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import carkit as K                                                  # noqa: E402
from brands import halcyon                                          # noqa: E402
from carkit import (Geo, Matrix, V3, my, on_body, pi, rad, ribbon, shr,    # noqa: E402
                    stud, text_flat, text_on_body)

# ---------------------------------------------------------------------------------------
# dimensions
# ---------------------------------------------------------------------------------------
FA_X, RA_X = 1.58, -1.47            # axles: 3.05 m wheelbase
F_R, F_W, F_RIM = 0.37, 0.255, 0.288   # tire radius, width, rim radius
R_R, R_W, R_RIM = 0.37, 0.305, 0.288
F_OUT, R_OUT = 0.945, 0.957         # outer face of the tires
F_ARCH, R_ARCH = 0.430, 0.436       # wheel arch radius
ARCH_ANG = (-28, 8, 42, 74, 106, 138, 172, 208)
ROOM_R, ROOM_Y = 0.405, 0.53        # the front tires' steering room inside the skin
SUBDIV = 3

# ---------------------------------------------------------------------------------------
# body: stations and character lines
# ---------------------------------------------------------------------------------------
LINES = "CPHGSUMRFB"
#        C centerline top, P spine edge, H hood crease / roof rail, G fender inner / beltline,
#        S shoulder crest, U widest line, M cladding line, R rocker, F floor edge, B floor
ORDER = ["N0", "N1", "A1", "A2", "A3", "W0", "RF", "BP", "D2", "SC", "RA", "RB", "T1"]
PT = {}
STATIONS = []


def stations():
    T = {
        "N0": [(2.535, 0, .50), (2.527, .26, .498), (2.495, .50, .49), (2.45, .66, .48),
               (2.37, .81, .465), (2.345, .855, .385), (2.345, .86, .27), (2.37, .84, .16),
               (2.45, .60, .13), (2.50, 0, .13)],
        "N1": [(2.27, 0, .568), (2.262, .255, .573), (2.24, .53, .592), (2.22, .70, .628),
               (2.19, .895, .655), (2.17, .945, .53), (2.17, .94, .31), (2.19, .905, .16),
               (2.22, .66, .13), (2.27, 0, .13)],
        "A1": [(2.03, 0, .628), (2.03, .235, .636), (2.03, .57, .686), (2.03, .74, .752),
               (2.03, .935, .78), (2.03, .972, .60), (2.03, .955, .33), (2.03, .925, .16),
               (2.03, .68, .13), (2.03, 0, .13)],
        "A2": [(1.58, 0, .742), (1.58, .175, .75), (1.58, .64, .812), (1.58, .78, .866),
               (1.58, .95, .875), (1.58, .978, .68), (1.58, .96, .35), (1.58, .93, .16),
               (1.58, .68, .13), (1.58, 0, .13)],
        "A3": [(1.12, 0, .818), (1.12, .105, .822), (1.12, .72, .838), (1.12, .83, .865),
               (1.12, .94, .858), (1.12, .965, .65), (1.12, .935, .35), (1.12, .93, .16),
               (1.12, .69, .13), (1.12, 0, .13)],
        "W0": [(1.08, 0, .848), (1.075, .05, .85), (.97, .74, .862), (.95, .84, .868),
               (.95, .92, .832), (.95, .945, .64), (.95, .915, .35), (.95, .935, .16),
               (.95, .70, .13), (.95, 0, .13)],
        "RF": [(-.02, 0, 1.305), (-.025, .048, 1.305), (-.14, .722, 1.272)] + [None] * 7,
        "BP": [(-.46, 0, 1.345), (-.46, .05, 1.345), (-.42, .74, 1.305),
               (-.22, .915, .898), (-.22, .952, .852), (-.22, .968, .66), (-.22, .925, .36),
               (-.22, .945, .16), (-.22, .72, .13), (-.22, 0, .13)],
        "D2": [(-1.08, 0, 1.302), (-1.08, .06, 1.302), (-1.07, .745, 1.27),
               (-1.06, .905, .925), (-1.03, .962, .888), (-.97, .862, .70), (-.875, .85, .44),
               (-.87, .955, .165), (-.87, .72, .13), (-.87, 0, .13)],
        "SC": [None, None, None, (-1.12, .905, .935), (-1.09, .978, .897),
               (-1.035, .985, .705), (-.935, .972, .44), (-.93, .955, .165),
               (-.93, .72, .13), (-.93, 0, .13)],
        "RA": [(-1.47, 0, 1.20), (-1.47, .12, 1.20), (-1.47, .69, 1.165),
               (-1.47, .862, .975), (-1.47, .968, .925), (-1.47, .988, .72),
               (-1.47, .972, .42), (-1.47, .955, .17), (-1.47, .70, .14), (-1.47, 0, .14)],
        "RB": [(-2.02, 0, 1.0), (-2.02, .27, .998), (-2.02, .64, .975), (-2.02, .80, .94),
               (-2.02, .945, .89), (-2.02, .972, .70), (-2.02, .952, .42),
               (-2.02, .93, .22), (-2.02, .70, .18), (-2.02, 0, .18)],
        "T1": [(-2.52, 0, .845), (-2.52, .40, .843), (-2.51, .64, .835), (-2.49, .79, .812),
               (-2.455, .895, .78), (-2.435, .92, .645), (-2.435, .905, .43),
               (-2.455, .87, .30), (-2.50, .68, .27), (-2.52, 0, .27)],
    }
    for j in range(3, 10):
        T["RF"][j] = V3(T["W0"][j]).lerp(V3(T["BP"][j]), 0.60)
    for j in range(0, 3):
        T["SC"][j] = V3(T["D2"][j]).lerp(V3(T["RA"][j]), 0.12)
    S = K.fill([T[k] for k in ORDER])
    PT.update(K.table(ORDER, LINES, S))
    STATIONS[:] = S
    return S


PMAT = dict(spine="carbon", hood="paint", bumper_f="paint", fender_f="paint", door_f="paint",
            door_r="paint", quarter="paint", deck="paint", bumper_r="paint",
            glass_ws="glass", glass_roof="glass", glass_rear="glass", glass_side="glass",
            sail="carbon", trim="frit", wstrim="gloss_black", sill="cladding",
            floor="underbody", mouth="void", mouth_frame="cladding", lightband="gloss_black",
            tail="void", tail_frame="cladding", scoop="void", vent="void", well="well",
            lamp_f="lamp_housing", lens_f="lens_clear", lamp_r="lamp_housing",
            lens_r="lens_red", cut="void")
GAP = 0.00175                       # 3.5 mm shut lines
LAMP_F_W, LAMP_F_D = 0.036, 0.040   # the front light channel: width, depth
LAMP_R_W, LAMP_R_D = 0.046, 0.034   # the halo's channel: nearly the band's width (a
                                    # band left as two thin rings wrecks a pack's far LOD)
LAMP = {}                           # the light channels' paths on the skin
CHAN_STEP = 0.02                    # their sections' spacing (finer, the pack's LODs starve)
LAMP_STEP = 0.08                    # the lamps' sections in them
FRONT_C = V3((2.515, 0, 0.30))      # middle of the mouth
REAR_C = V3((-2.50, 0, 0.56))      # middle of the tail panel
BAND_W = 0.056                      # the light bands round the mouth and the tail
MOUTH_D, TAIL_D = 0.23, 0.16
CAPS = {}


def panel_of(i, j):
    if j >= 7:
        return "floor"
    if j == 6:
        return "sill"
    if j == 0:
        return "spine"              # one piece, nose to tail
    if i == 0:
        return "bumper_f"
    if j == 1:
        return ("hood", "hood", "hood", "hood", "glass_ws", "glass_roof", "glass_roof",
                "glass_rear", "glass_rear", "glass_rear", "deck")[i - 1]
    if j == 2:
        return ("fender_f" if i <= 4 else "glass_side" if i <= 7 else "sail" if i <= 9
                else "quarter" if i == 10 else "deck")
    if i == 11:
        return "bumper_r"
    if i <= 4:
        return "fender_f"
    if i <= 6:
        return "door_f"
    if i == 7:
        return "door_r"
    if i == 8 and j == 5:
        return "scoop"
    return "quarter"


def line_crease(i, j):
    """Crease of the edge along line j from station i to i + 1."""
    if j in (0, 9):
        return 0.0
    if j == 1:
        return 1.0
    if j == 2:
        return 1.0 if i <= 10 else 0.7
    if j == 3:
        return 0.7 if i <= 4 else 1.0 if i <= 9 else 0.6
    if j == 4:
        return 1.0
    if j == 5:
        return 1.0 if i == 8 else 0.55
    return 1.0


def station_crease(i, j):
    """Crease of the edge on station i between lines j and j + 1."""
    if i in (0, 12):
        return 1.0
    if i == 5:
        return 1.0 if j <= 2 else 0.0
    if i == 6:
        return 1.0 if j <= 1 else 0.0
    if i == 8:
        return 1.0 if j == 5 else 0.5 if j == 4 else 0.0
    if i == 9:
        return 1.0 if j == 5 else 0.6 if j in (4, 6) else 0.0
    if i == 11:
        return 0.6 if j <= 2 else 0.0
    if i == 1:
        return 0.5 if j <= 4 else 0.0
    return 0.0


def band_mid(i, center):
    """The middle line of the light band round an end of the body (station i), line by
    line: the band is BAND_W wide all round, square to the lip."""
    ring = [type("P", (), dict(co=V3(p)))() for p in STATIONS[i]]
    off = K._even_band(ring, center, BAND_W, True, False)
    return [V3(p) + o * 0.5 for p, o in zip(STATIONS[i], off)]


def cutters():
    """Everything cut into the hull, laid on it while it stands uncut: the wheel wells and
    the room the front tires steer in, the light channels under their lenses, the handles'
    and the charge flap's shut lines, the slots over the rear haunches."""
    wells = Geo()
    K.well_cutter(wells, FA_X, F_R, F_ARCH, 0.68, ARCH_ANG)   # under the hood crease
    K.well_cutter(wells, RA_X, R_R, R_ARCH, 0.60, ARCH_ANG)    # 25 mm in for room
    # room inside the skin for the front tires to steer: a lower arch further in
    room = Geo()
    K.well_cutter(room, FA_X, F_R, ROOM_R, ROOM_Y, ARCH_ANG, depth=0.70 - ROOM_Y)
    # front: a channel in the band under the nose lip, from the spine's edge out, turning
    # down the corner
    mid = band_mid(0, FRONT_C)
    front = Geo()
    LAMP["front"] = K.groove(front, [mid[1].lerp(mid[2], 0.15)] + mid[2:6]
                             + [mid[5].lerp(mid[6], 0.85)],
                             width=LAMP_F_W, depth=LAMP_F_D, mirror=True, step=CHAN_STEP)
    # rear: the halo, one channel round the whole tail, its corners rounded with the way out
    # held aft (left to find its own normals, the rounded ring snapped onto the tail's inner
    # frame and the hull came out empty)
    mid = band_mid(-1, REAR_C)
    # (rounded here and traced on its own points only, so both sides take the same
    # sections: a trace stepped along the ring samples the two sides differently)
    path = K.chaikin((mid[0:10] + [my(p) for p in mid[8:0:-1]])[::-1], 3, closed=True)
    rear = Geo()
    LAMP["rear"] = K.groove(rear, path, width=LAMP_R_W, depth=LAMP_R_D, closed=True,
                            up=(-1, 0, 0), step=1.0)
    # shut lines: flush handles either side of the pillarless split, the charge flap
    cut = Geo()
    K.groove(cut, K.rounded(-0.145, 0.799, 0.13, 0.018), 'y', closed=True, mirror=True)
    K.groove(cut, K.rounded(-0.355, 0.786, 0.12, 0.018, n=8), 'y', closed=True, mirror=True)
    K.groove(cut, K.ngon(-2.21, 0.605, 0.058, 6), 'y', closed=True, mirror=True)
    # (the slots over the rear haunches stay dark strips on the skin: as ten pockets they
    # were small pieces enough to starve the game pack's far LOD)
    return [(wells, "well"), (room, "well"), (front, "lamp_f", "skin", "lens_f"),
            (rear, "lamp_r", "skin", "lens_r"), (cut, "cut", "drop")]


def build_hull():
    body = K.build_body(
        stations(), panel_of, PMAT, line_crease, station_crease,
        front=dict(center=FRONT_C, depth=MOUTH_D, band=BAND_W, band_panel="lightband",
                   band_lines=6, frame="mouth_frame", inner="mouth", even=True),
        rear=dict(center=REAR_C, depth=TAIL_D, band=BAND_W, band_panel="lightband",
                  band_lines=9, frame="tail_frame", inner="tail", even=True),
        recesses=[(3, 1, 0.11, 0.03),      # hood extractors, one each side of the spine
                  (4, 5, 0.035, 0.03)],     # vent behind the front wheel
        glass=[("glass_ws", 0.03, "wstrim", "frame"), ("glass_roof", 0.022, "trim", "frit"),
               ("glass_rear", 0.03, "trim", "frit"), ("glass_side", 0.026, "trim", "frit")],
        cutters=cutters, subdiv=SUBDIV, gap=GAP)
    CAPS["mouth"], CAPS["tail"] = body.caps["front"], body.caps["rear"]
    # (the channels' walls stay bare: as 1 mm sheets, which keep the lit face from being
    # painted dark when it lies deep, the far LOD wrecked them into spikes; the lit faces
    # lie right under the lenses instead)


# ---------------------------------------------------------------------------------------
# details on the body
# ---------------------------------------------------------------------------------------
def build_front():
    build_lamps()

    # ---- the prow: the spine coming down through the mouth, parting it in two
    xb = FRONT_C.x - MOUTH_D
    g = Geo()
    lo = [(2.556, 0.014, 0.125), (2.556, -0.014, 0.125), (xb, -0.135, 0.125), (xb, 0.135, 0.125)]
    hi = [(2.528, 0.02, 0.462), (2.528, -0.02, 0.462), (xb, -0.20, 0.47), (xb, 0.20, 0.47)]
    g.hexa(lo + hi)
    g.obj("mouth.prow", "carbon", bevel=0.004)
    # ---- honeycomb either side of it, a blade across each intake
    g = Geo()
    half = [(p.y, p.z) for p in CAPS["mouth"]]
    poly = half + [(-y, z) for (y, z) in half[::-1]]
    g.honeycomb(poly, xb, 0.017, 0.003, 0.012, 1, keep=lambda y, z: abs(y) > 0.13)
    g.obj("mouth.mesh", "grille")
    g = Geo()
    g.hexa([(2.47, 0.10, 0.262), (2.40, 0.80, 0.262), (2.30, 0.80, 0.272), (2.30, 0.10, 0.272),
            (2.47, 0.10, 0.274), (2.40, 0.80, 0.274), (2.30, 0.80, 0.288), (2.30, 0.10, 0.288)])
    g.obj("mouth.blade", "carbon", bevel=0.002, mirror=True)
    # ---- main beams: four small lenses in a bar under the strip
    g = Geo()
    a, b = V3((2.455, 0.47, 0.425)), V3((2.385, 0.745, 0.412))
    t = (b - a).normalized()
    side = t.cross(V3((0, 0, 1)))
    R = Matrix((t, side, (0, 0, 1))).transposed()
    g.box(a.lerp(b, 0.5) - side * 0.012, ((b - a).length + 0.03, 0.03, 0.036), rot=R)
    g.obj("beam.bar", "gloss_black", bevel=0.003, mirror=True)
    ge = Geo()
    for k in range(4):
        c = a.lerp(b, (k + 0.5) / 4)
        ge.box(c + side * 0.004, ((b - a).length / 4 - 0.016, 0.006, 0.02), rot=R)
    ge.obj("beam.lens", "lamp", mirror=True)
    # ---- badge and splitter
    g = Geo()
    g.lathe([(0.0, 0.002), (0.0, 0.026), (0.005, 0.022), (0.005, 0.002)], 6,
            xf=Matrix.Translation((2.531, 0, 0.479)) @ Matrix.Rotation(-pi / 2, 4, 'Z'))
    g.obj("badge", "rim_bright", bevel=0.001)
    g = Geo()
    g.prism([(2.562, 0, 0.10), (2.53, 0.58, 0.10), (2.45, 0.865, 0.10), (2.335, 0.94, 0.10),
             (2.12, 0.94, 0.10), (2.12, 0, 0.10)], (0, 0, 0.022))
    g.prism([(2.39, 0.928, 0.10), (2.35, 0.928, 0.215), (2.17, 0.928, 0.165),
             (2.14, 0.928, 0.10)], (0, 0.014, 0))
    g.obj("splitter", "carbon", bevel=0.003, mirror=True)


def build_rear():
    P = PT
    xt = REAR_C.x + TAIL_D
    # ---- honeycomb, the beam with the maker's name, plate, two flat outlets
    g = Geo()
    half = [(p.y, p.z) for p in CAPS["tail"]]
    poly = half + [(-y, z) for (y, z) in half[::-1]]

    def clear(y, z):
        return not (abs(abs(y) - 0.40) < 0.165 and abs(z - 0.44) < 0.06) and \
            not (abs(y) < 0.16 and abs(z - 0.44) < 0.07)
    g.honeycomb(poly, xt - 0.012, 0.022, 0.0035, 0.012, -1, keep=clear)
    g.obj("tail.mesh", "grille")
    g = Geo()
    g.prism([(-2.415, -0.87, 0.595), (-2.44, -0.87, 0.613), (-2.44, -0.87, 0.667),
             (-2.415, -0.87, 0.685), (-2.36, -0.87, 0.67), (-2.36, -0.87, 0.61)], (0, 1.74, 0))
    g.obj("tail.beam", "carbon", bevel=0.003)
    g = Geo()
    ge = Geo()
    hexa =[(0.40 + 0.135, 0.44), (0.40 + 0.10, 0.398), (0.40 - 0.10, 0.398),
            (0.40 - 0.135, 0.44), (0.40 - 0.10, 0.482), (0.40 + 0.10, 0.482)]
    g.sweep([(xt - 0.055, y, z) for y, z in hexa],
            [(-0.007, -0.05), (0.007, -0.05), (0.007, 0.05), (-0.007, 0.05)],
            up=(-1, 0, 0), closed=True)
    ge.prism([(xt - 0.02, y, z) for y, z in hexa], (-0.004, 0, 0))
    g.obj("outlet", "rim", bevel=0.002, mirror=True)
    ge.obj("outlet.glow", "ember", mirror=True)
    g = Geo()
    g.box((xt - 0.012, 0, 0.44), (0.012, 0.27, 0.095))
    g.obj("plate", "gloss_black", bevel=0.003)
    g = Geo()
    text_flat(g, "VB 31-204", 0.05, (xt - 0.0185, 0, 0.44), (0, -1, 0), (0, 0, 1), spacing=1.1)
    g.obj("plate.glyphs", "led_accent")
    g = Geo()
    text_flat(g, "H A L C Y O N", 0.04, (-2.4412, 0, 0.64), (0, -1, 0), (0, 0, 1), spacing=1.35)
    g.obj("led.name", "led_rear")
    # ---- diffuser fins
    g = Geo()
    for y in (0.0, 0.23, 0.46, 0.69):
        g.prism([(-2.06, y - 0.007, 0.19), (-2.52, y - 0.007, 0.276),
                 (-2.535, y - 0.007, 0.118), (-2.32, y - 0.007, 0.108),
                 (-2.10, y - 0.007, 0.138)], (0, 0.014, 0))
    g.obj("diffuser", "carbon", bevel=0.003, mirror=True)
    # ---- the spoiler: a low blade on two struts over the tail's edge, a light in its lip
    zd = on_body(-2.42, 0.0, 'z')[0].z
    z0 = zd + 0.042
    g = Geo()
    g.prism([(-2.31, -0.66, z0 + 0.002), (-2.36, -0.66, z0 + 0.012), (-2.48, -0.66, z0 + 0.020),
             (-2.545, -0.66, z0 + 0.038), (-2.545, -0.66, z0 + 0.027), (-2.48, -0.66, z0 + 0.008),
             (-2.36, -0.66, z0 - 0.002)], (0, 1.32, 0))
    g.obj("spoiler.blade", "carbon", bevel=0.003)
    g = Geo()
    for y in (0.46, -0.46):
        g.prism([(-2.35, y - 0.012, zd - 0.01), (-2.46, y - 0.012, zd - 0.02),
                 (-2.47, y - 0.012, z0 + 0.010), (-2.38, y - 0.012, z0 + 0.004)], (0, 0.024, 0))
    g.obj("spoiler.struts", "cladding", bevel=0.002)
    g = Geo()
    g.box((-2.5465, 0, z0 + 0.0325), (0.004, 0.90, 0.006))
    g.obj("led.spoiler", "led_rear")
    # ---- louvres on the wide end of the spine
    g = Geo()
    a = P["RB"]["P"].lerp(P["RB"]["C"], 0.12) + V3((-0.03, 0, 0))
    b = P["RB"]["P"].lerp(P["T1"]["P"], 0.50).lerp(P["RB"]["C"].lerp(P["T1"]["C"], 0.50), 0.12)
    g.louvers(a, b, my(b), my(a), 4, 0.05, 0.010, rad(12), out=(0, 0, 1), lift=0.014,
              margin=0.08)
    g.obj("spine.louvers", "gloss_black", bevel=0.003)


def build_sides():
    P = PT
    # ---- wheel arch trims and their bolts
    g = Geo()
    K.arch_trim(g, FA_X, F_R, F_ARCH, 0.88, F_OUT + 0.04, ARCH_ANG)
    K.arch_trim(g, RA_X, R_R, R_ARCH, 0.88, R_OUT + 0.04, ARCH_ANG)
    g.obj("arch.trims", "cladding", bevel=0.005, mirror=True)
    g = Geo()
    K.arch_bolts(g, FA_X, F_R, F_ARCH, F_OUT + 0.04, ARCH_ANG)
    K.arch_bolts(g, RA_X, R_R, R_ARCH, R_OUT + 0.04, ARCH_ANG)
    g.obj("arch.bolts", "rim_bright", mirror=True)
    # ---- accent line along the doors' foot, running into the scoop
    g = Geo()
    path = [P[s]["M"] + V3((0, 0.004, 0.012)) for s in ("W0", "RF", "BP", "D2")]
    path[0] = path[0] + V3((-0.05, 0, 0))
    path[-1] = path[-1] + V3((0.03, 0.004, 0))
    g.sweep(path, [(-0.004, -0.005), (0.004, -0.005), (0.004, 0.005), (-0.004, 0.005)],
            up=(0, 0, 1))
    g.obj("led.sill", "led_accent", mirror=True)
    # ---- slats: scoop, fender vent, hood extractors
    g = Geo()
    g.louvers(P["D2"]["U"], P["D2"]["M"], P["SC"]["M"], P["SC"]["U"], 5, 0.04, 0.007,
              rad(20), out=(1, 0.3, 0), lift=0.004, margin=0.08)
    q = shr([P["A2"]["P"], P["A2"]["H"], P["A3"]["H"], P["A3"]["P"]], 0.30, -0.008, (0, 0, 1))
    g.louvers(q[0], q[3], q[2], q[1], 4, 0.045, 0.007, rad(-30), out=(0, 0, 1))
    g.obj("slats", "grille", bevel=0.002, mirror=True)
    g = Geo()
    q = shr([P["A3"]["U"], P["A3"]["M"], P["W0"]["M"], P["W0"]["U"]], 0.16, -0.008, (0, 1, 0))
    g.louvers(q[0], q[3], q[2], q[1], 4, 0.034, 0.006, rad(35), out=(0, 1, 0))
    g.obj("vent.slats", "paint", bevel=0.002, mirror=True)
    # ---- mirrors: camera pods on blades
    dx, dz = 0.14, 0.078
    g = Geo()
    g.sweep([(0.63 + dx, 0.90, 0.772 + dz), (0.615 + dx, 0.985, 0.800 + dz)],
            [(-0.03, -0.004), (0.03, -0.004), (0.03, 0.004), (-0.03, 0.004)], up=(0, 0, 1))
    g.obj("mirror.stalks", "cladding", bevel=0.002, mirror=True)
    g = Geo()
    g.hexa([(0.69 + dx, 0.975, 0.792 + dz), (0.69 + dx, 1.005, 0.792 + dz),
            (0.53 + dx, 1.03, 0.782 + dz), (0.53 + dx, 0.965, 0.782 + dz),
            (0.675 + dx, 0.978, 0.812 + dz), (0.675 + dx, 1.002, 0.812 + dz),
            (0.53 + dx, 1.025, 0.835 + dz), (0.53 + dx, 0.970, 0.835 + dz)])
    g.obj("mirror.pods", "paint", bevel=0.004, mirror=True)
    g = Geo()
    g.box((0.5285 + dx, 0.9975, 0.808 + dz), (0.004, 0.045, 0.036))
    g.obj("mirror.lens", "gloss_black", mirror=True)
    # ---- side skirt blades with a winglet at the back
    g = Geo()
    g.prism([(1.07, 0.90, 0.136), (1.07, 0.972, 0.136), (-0.80, 0.985, 0.136),
             (-0.96, 0.99, 0.136), (-0.96, 0.90, 0.136)], (0, 0, 0.016))
    g.prism([(-0.70, 0.976, 0.14), (-0.96, 0.976, 0.14), (-0.96, 0.976, 0.235),
             (-0.90, 0.976, 0.235)], (0, 0.012, 0))
    g.obj("skirt", "carbon", bevel=0.003, mirror=True)


def build_surface_details():
    P = PT
    # ---- on the spine: a sensor bar over the windshield, a fin where the roof falls away
    zr = on_body(-0.16, 0.0, 'z')[0].z
    g = Geo()
    g.prism([(-0.07, -0.062, zr - 0.006), (-0.11, -0.062, zr + 0.020), (-0.19, -0.062, zr + 0.020),
             (-0.25, -0.062, zr - 0.004)], (0, 0.124, 0))
    zf = on_body(-1.30, 0.0, 'z')[0].z
    g.prism([(-1.18, -0.006, zf + 0.012), (-1.31, -0.006, zf + 0.062),
             (-1.35, -0.006, zf + 0.058), (-1.38, -0.006, zf - 0.03)], (0, 0.012, 0))
    g.obj("roof.pod", "cladding", bevel=0.004)
    g = Geo()
    g.box((-0.088, 0, zr + 0.009), (0.005, 0.10, 0.006), rot=Matrix.Rotation(rad(-28), 3, 'Y'))
    g.obj("led.roof", "led_accent")
    # ---- a row of studs down each edge of the spine, where it is bolted to the body
    g = Geo()
    for x in [2.12 - 0.19 * k for k in range(6)] + [-1.62 - 0.16 * k for k in range(5)]:
        yc = on_spine_edge(x)
        for y in (yc, -yc):
            loc, n = on_body(x, y, 'z')
            if loc is not None:
                stud(g, loc, n, [(-0.002, 0.001), (-0.002, 0.007), (0.0028, 0.007),
                                 (0.0028, 0.001)], 6)
    g.obj("spine.bolts", "rim_bright")
    # ---- parking sensors on the nose
    g = Geo()
    for y in (0.40, 0.70, -0.40, -0.70):
        loc, n = on_body(y, 0.53, 'x')
        if loc is not None:
            stud(g, loc, n, [(-0.002, 0.001), (-0.002, 0.011), (0.0015, 0.011),
                             (0.0015, 0.001)], 12)
    g.obj("sensors", "gloss_black")
    # ---- lettering
    g = Geo()
    for side in (1, -1):
        text_on_body(g, "SABLE", 0.05, 0.55, 0.50, side, spacing=1.25)
        text_on_body(g, "HS 460", 0.016, -2.21, 0.535, side, spacing=1.2)
        text_on_body(g, "4", 0.07, 1.86, 0.69, side)
    g.obj("lettering", "decal")
    # ---- the pillarless split on the side glass (the handles are cut, in cutters())
    g = Geo()
    hg, hh = P["BP"]["G"], P["BP"]["H"]
    ribbon(g, [(hg.x - 0.012, hg.z + 0.03), (hh.x + 0.02, hh.z - 0.045)], 'y', 0.007)
    for k in range(5):                                  # slots over the rear haunch
        x = -1.30 - k * 0.062
        ribbon(g, [(x, 0.905), (x - 0.02, 0.955)], 'z', 0.02)
    g.obj("lines", "void", mirror=True)
    # ---- wipers: one each side of the rib, parked on the glass
    g, gb = Geo(), Geo()
    K.wiper(g, gb, on_body(1.055, 0.30, 'z')[0], on_body(1.005, 0.10, 'z')[0],
            on_body(0.93, 0.62, 'z')[0])
    g.obj("wiper", "cladding", bevel=0.0012, mirror=True)
    gb.obj("wiper.blade", "rubber", mirror=True)
    # ---- markers and decals
    g = Geo()
    ribbon(g, [(2.27, 0.44), (2.17, 0.472)], 'y', 0.012)
    g.obj("led.marker", "led_accent", mirror=True)
    g = Geo()
    x = 0.20
    for w in (0.006, 0.012, 0.004, 0.004, 0.010, 0.006, 0.014, 0.004, 0.008, 0.004, 0.012, 0.006):
        ribbon(g, [(x - w / 2, 0.535), (x - w / 2, 0.58)], 'y', w)
        x -= w + 0.006
    for k in range(4):
        ribbon(g, [(-2.10 - k * 0.04, 0.755), (-2.12 - k * 0.04, 0.795)], 'y', 0.014)
    g.obj("decals", "decal", mirror=True)


def on_spine_edge(x):
    """y of a point a little inside the spine's edge at x (the P line as drawn)."""
    return halcyon.on_spine_edge(x, pt=PT, order=ORDER, inset=0.028, miss=0.1)


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


def run_len(tr):
    return sum((b[0] - a[0]).length for a, b in zip(tr, tr[1:]))


def build_lamps():
    """What stands in the light channels, under their lenses. The lit faces lie right under
    the lenses: a game pack leaves the lenses out and bakes what is behind them, and a lit
    face set deep, or behind ribs, bakes as dashes. They are swept on sparse sections: a
    pack's far LOD keeps every lamp whole, and dense ones starve the body of triangles."""
    # front: a lit bar along the upper side of the whole channel, three hexagonal
    # projectors under it on the run under the lip, outboard
    fr = along(LAMP["front"], 0.012, run_len(LAMP["front"]) - 0.012, LAMP_STEP)
    L = K.Lamp("lamp.front", lit="led_front")
    L.bar([q - n * 0.006 - sd * 0.0105 for q, n, _, sd in fr], 0.012, 0.003,
          up=[n for _, n, _, _ in fr])
    for q, n, _, sd in along(LAMP["front"], 0.27, 0.27 + 2 * 0.08, 0.08):
        L.projector(q - n * 0.006 + sd * 0.0055, n, r=0.0105, depth=0.03, seg=6)
    ob = L.obj(mirror=True)["housing"]     # (its cups unbevelled: deep in the channel, and a
    for md in [m for m in ob.modifiers if m.type == 'BEVEL']:     # pack keeps lamps whole)
        ob.modifiers.remove(md)
    # rear: the halo, a red bar round the whole tail right under the lens over a chrome
    # floor
    # (built on the left half, from the top's middle round to the bottom's, and mirrored)
    rr = along(LAMP["rear"], 0.0, run_len(LAMP["rear"]), LAMP_STEP)
    i0 = next(i for i in range(len(rr)) if rr[i][0].y >= 0 > rr[i - 1][0].y)
    rr = rr[i0:] + rr[:i0]
    rr = rr[:next(i for i in range(len(rr)) if rr[i][0].y < 0)]
    ends = [V3((q.x, 0.0, q.z)) for q in (rr[0][0], rr[-1][0])]
    P = [ends[0]] + [q for q, _, _, _ in rr] + [ends[1]]
    ups = [rr[0][1]] + [n for _, n, _, _ in rr] + [rr[-1][1]]
    L = K.Lamp("lamp.rear", lit="led_rear")
    L.chrome.sweep([q - n * (LAMP_R_D - 0.003) for q, n in zip(P, ups)],
                   [(-0.018, -0.001), (0.018, -0.001), (0.018, 0.001), (-0.018, 0.001)],
                   up=ups)
    L.bar([q - n * 0.006 for q, n in zip(P, ups)], 0.024, 0.003, up=ups)
    L.obj(mirror=True)


# ---------------------------------------------------------------------------------------
# interior: four seats under the glass
# ---------------------------------------------------------------------------------------
def build_interior():
    g = Geo()
    g.prism([(0.96, -.80, .86), (0.96, -.76, .86), (0.96, -.70, .20), (0.96, .70, .20),
             (0.96, .76, .86), (0.96, .80, .86), (0.96, .80, .15), (0.96, -.80, .15)],
            (-1.94, 0, 0))                                      # floor and door cards
    g.box((-1.22, 0, 0.17), (0.50, 1.14, 0.04))                 # floor between the wells
    g.prism([(-1.44, -0.57, 0.15), (-1.44, 0.57, 0.15), (-1.44, 0.63, 0.93),
             (-1.44, -0.63, 0.93)], (-0.04, 0, 0))              # bulkhead behind the seats
    g.box((-1.72, 0, 0.925), (0.56, 1.22, 0.02))                # shelf under the rear glass
    g.prism([(0.94, -0.76, 0.52), (0.94, -0.76, 0.845), (0.66, -0.76, 0.845),
             (0.53, -0.76, 0.76), (0.57, -0.76, 0.52)], (0, 1.52, 0))       # dash
    g.box((-0.22, 0, 0.30), (2.30, 0.20, 0.26))                 # the console, cowl to shelf
    g.box((-0.72, 0, 0.47), (0.36, 0.17, 0.10))                 # armrest between the rear seats
    g.obj("interior.tub", "interior", bevel=0.006)
    g = Geo()
    tilt = Matrix.Rotation(rad(-20), 3, 'Y')
    for x0, tall, yc in ((0.12, 0.0, 0.385), (-0.80, -0.02, 0.365)):   # rear pair in from
        for y in (yc, -yc):                                             # the rear tires
            g.box((x0, y, 0.33), (0.50, 0.46, 0.12))
            g.box((x0 - 0.38, y, 0.65 + tall), (0.11, 0.44, 0.62), rot=tilt)
            g.box((x0 - 0.515, y, 0.995 + tall), (0.07, 0.22, 0.15), rot=tilt)
            for s in (-1, 1):
                g.box((x0, y + s * 0.235, 0.36), (0.46, 0.05, 0.16))
                g.box((x0 - 0.365, y + s * 0.225, 0.61 + tall), (0.14, 0.05, 0.50), rot=tilt)
    g.obj("interior.seats", "seat", bevel=0.014, segs=3)
    g = Geo()
    wheel = (Matrix.Translation((0.47, 0.385, 0.80)) @ Matrix.Rotation(rad(-70), 4, 'Y')
             @ Matrix.Rotation(pi / 2, 4, 'X'))
    g.lathe([(-0.012, 0.155), (0.0, 0.167), (0.012, 0.155), (0.0, 0.143)], 24, xf=wheel)
    g.box((0.54, 0.385, 0.77), (0.16, 0.05, 0.05))
    g.obj("interior.wheel", "interior", sharp=40)
    g = Geo()
    scr = Matrix.Rotation(rad(-25), 3, 'Y')
    g.box((0.545, 0.0, 0.80), (0.008, 0.34, 0.085), rot=scr)
    g.box((0.61, 0.385, 0.855), (0.008, 0.28, 0.05), rot=scr)
    g.box((0.61, -0.385, 0.855), (0.008, 0.28, 0.05), rot=scr)
    g.box((-0.47, 0.0, 0.50), (0.008, 0.15, 0.09), rot=scr)        # the rear seats' screen
    g.obj("interior.screens", "screen")
    g = Geo()
    for y in (0.103, -0.103):
        g.box((-0.22, y, 0.432), (2.20, 0.004, 0.004))
    g.obj("led.cabin", "led_accent")


# ---------------------------------------------------------------------------------------
# views of its own, and the build
# ---------------------------------------------------------------------------------------
K.VIEWS["hero"].update(dir=(1.0, 0.80, 0.33))       # high enough to look through the roof
K.VIEWS.update(
    nose=dict(dir=(1.0, 0.45, 0.10), lens=85, target=(2.3, 0.45, 0.35), dist=2.8),
    tail=dict(dir=(-1.0, -0.4, 0.14), lens=85, target=(-2.4, -0.3, 0.6), dist=3.2),
    cabin=dict(dir=(0.2, 1.0, 0.75), lens=85, target=(-0.5, 0.2, 1.0), dist=4.0),
)


def main():
    K.materials(paint=(0.008, 0.045, 0.30), paint_finish=(0.60, 0.30, 1.0), dust_amount=0.2,
                glass=(0.42, 0.46, 0.50), led_front=(0.80, 0.94, 1.0),
                led_accent=(1.0, 0.62, 0.22), caliper=(0.72, 0.46, 0.09),
                seat=(0.36, 0.17, 0.07), interior=(0.022, 0.022, 0.025),
                screen=(0.30, 0.65, 1.0), decal=(0.62, 0.63, 0.65))
    build_hull()
    K.log("hull")
    build_front()
    build_rear()
    build_sides()
    build_surface_details()
    build_interior()
    K.log("details")
    for side, s in ((1, "l"), (-1, "r")):
        K.build_wheel("f" + s, FA_X, F_R, F_W, F_RIM, F_OUT, side, spokes=9)
        K.build_wheel("r" + s, RA_X, R_R, R_W, R_RIM, R_OUT, side, spokes=9)
    K.log("wheels")
    K.meant("symmetry", "interior.wheel")       # the driver's wheel, on the left
    K.shoot(extra="top")


main()
