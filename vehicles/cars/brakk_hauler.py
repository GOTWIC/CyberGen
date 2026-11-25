"""Brakk Hauler: a crew cab pickup of flat plates (both names made up), on vehicles/carkit.py.

Run (always through the wrapper, one Blender job at a time on this machine):
    vehicles/blender.sh vehicles/cars/brakk_hauler.py --out DIR --preview
    vehicles/blender.sh vehicles/cars/brakk_hauler.py --out DIR --sheet

The first Brakk, so it sets the family's cues (see docs/progress/AG18/brakk_hauler/README.md):
a narrow monolith hull of flat plates with 45 degree chamfers, the wheels outside it under
bolted three-facet fender plates, light pylons on the chamfered corners and a full-width bar
over the windshield, a ribbed nose slab, corrugated cargo sides, tread plate, rows of bolt
heads, real hardware (winch, shackles, rails, a sail frame) and stencilled unit numbers.

Pieces: the hull (nose, hood and cab: seven lines over ten stations, every edge sharp), the
bed (a tub: its walls are stations of their own), and plates, bars and tubes for the rest.
The lamps are pockets in housings of plates: an LED bar in a reflector under a lens, an
amber cell under its own, bolted bezels and a guard on the pylons; LED modules behind one
lens in the roof bar; the fuel flaps are cut through the quarters (cutters()). The brand's
helpers (plates, bolts, stencils, stripes, the coil, the wheel) are in
vehicles/brands/brakk.py.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import carkit as K                                                  # noqa: E402
import cabin as C                                                   # noqa: E402
from functools import partial                                       # noqa: E402
from brands import brakk                                            # noqa: E402
from brands.brakk import (bolt, chevrons, coil, on_plane, on_side, plate,   # noqa: E402
                          stencil, tube)
from carkit import Geo, Matrix, V3, cos, hypot, on_body, pi, rad, sin   # noqa: E402

# ---------------------------------------------------------------------------------------
# dimensions
# ---------------------------------------------------------------------------------------
FA_X, RA_X = 1.88, -1.62            # axles: wheelbase 3.5
T_R, T_W, T_RIM, T_OUT = 0.45, 0.32, 0.235, 1.075      # tire radius, width, rim, outer face
HOOD, BELT, ROOF = 1.26, 1.28, 1.88
RAIL, BFLOOR = 1.36, 0.74           # bed rail and bed floor
BED_Y = 0.72                        # bed half width
FEN_Z, FEN_T = 1.05, 0.03           # fender plates: top height, thickness
NUM = "27"
GAP = 0.00175                       # shut lines 3.5 mm
FLAP = (-0.88, 1.07, 0.08, 0.11)    # the fuel flap on the quarter: middle x, z, width, height

# the Brakk wheel (vehicles/brands/brakk.py) at this car's sizes, as its own copy built it
build_wheel = partial(brakk.wheel, motor=False, R=T_R, w=T_W, rim=T_RIM, out=T_OUT, lugs=22,
                      text="BRAKK  TRAKTOR  M/T    37 X 12.5 R19    ", seg=88,
                      dish=brakk.DISH_SMALL)


def lbox(g, o, R, a, b, z):
    """A box in a lamp's own frame: o its foot on the body, R its turn, a its range along
    the way out, b across, z up (absolute)."""
    c = V3(o) + R @ V3(((a[0] + a[1]) / 2, (b[0] + b[1]) / 2, 0))
    c.z = (z[0] + z[1]) / 2
    g.box(c, (a[1] - a[0], b[1] - b[0], z[1] - z[0]), rot=R)


def lpt(o, R, a, b, z):
    p = V3(o) + R @ V3((a, b, 0))
    p.z = z
    return p


# ---------------------------------------------------------------------------------------
# hull: nose, hood and cab
# ---------------------------------------------------------------------------------------
LINES = "CRHGUFB"
#        C top centerline, R roof plate edge / hood top, H glass top / hood edge,
#        G belt / foot of the hood chamfer, U foot of the side plate, F floor edge, B floor
ORDER = ["N0", "N1", "A0", "W0", "W1", "W2", "BP0", "BP1", "CP", "CB"]
PT = {}


def cab_row(x):
    return [(x, 0, ROOF), (x, .62, ROOF), (x, .76, 1.78), (x, .87, BELT), (x, .90, .82),
            (x, .74, .50), (x, 0, .48)]


def hull_stations():
    T = {
        "N0": [(2.50, 0, 1.14), (2.50, .22, 1.14), (2.50, .32, 1.14), (2.50, .44, 1.04),
               (2.50, .44, .74), (2.50, .32, .58), (2.50, 0, .58)],
        "N1": [(2.38, 0, HOOD), (2.38, .25, HOOD), (2.38, .44, HOOD), (2.38, .56, 1.14),
               (2.38, .56, .78), (2.38, .42, .52), (2.38, 0, .50)],
        "A0": [(1.32, 0, HOOD), (1.32, .25, HOOD), (1.32, .44, HOOD), (1.32, .56, 1.14),
               (1.32, .56, .78), (1.32, .42, .52), (1.32, 0, .48)],
        "W0": [(1.06, 0, BELT), (1.06, .56, BELT), (1.02, .80, BELT), (.96, .87, 1.24),
               (1.00, .90, .82), (1.00, .74, .50), (1.00, 0, .48)],
        "W1": [(.78, 0, 1.80), (.78, .60, 1.80), (.74, .76, 1.78), (.74, .87, BELT),
               (.74, .90, .82), (.74, .74, .50), (.74, 0, .48)],
        "W2": [(.64, 0, ROOF), (.62, .62, ROOF), (.64, .76, 1.78), (.64, .87, BELT),
               (.64, .90, .82), (.64, .74, .50), (.64, 0, .48)],
        "BP0": cab_row(-.02), "BP1": cab_row(-.14), "CP": cab_row(-.82), "CB": cab_row(-1.0),
    }
    S = K.fill([T[k] for k in ORDER])
    PT.update(K.table(ORDER, LINES, S))
    return S


def side_y(z):
    """The cab's side plate at height z (belt to the sill)."""
    return 0.87 + 0.03 * (BELT - z) / (BELT - 0.82)


def hull_panel(i, j):
    if j == 5:
        return "floor"
    if j == 4:
        return "sill"
    return (("nose_top", "nose_top", "nose_corner", "nose_corner"),
            ("hood", "hood", "nose_side", "nose_side"),
            ("cowl", "cowl", "cowl_side", "cowl_side"),
            ("glass_ws", "glass_ws", "pillar_a", "door_f"),
            ("brow", "brow", "glass_f", "door_f"),
            ("roof", "roof_edge", "glass_f", "door_f"),
            ("roof", "roof_edge", "pillar_b", "door_r"),
            ("roof", "roof_edge", "glass_r", "door_r"),
            ("roof", "roof_edge", "pillar_c", "quarter"))[i][j]


HULL_MAT = dict(nose_top="paint", nose_corner="paint", hood="paint", nose_side="paint",
                cowl="cladding", cowl_side="paint", glass_ws="glass", pillar_a="paint",
                door_f="paint", brow="paint", glass_f="glass", roof="paint",
                roof_edge="paint", pillar_b="paint", door_r="paint", glass_r="glass",
                pillar_c="paint", quarter="paint", sill="cladding", floor="underbody",
                trim="cladding", nose="cladding", cabback="paint", cut="void")


def bed_row(x, yo, top, yi=0.62):
    """A bed station: over a wall (top) its inner points lie on the rail, else on the floor."""
    zc = RAIL if top else BFLOOR
    return [(x, 0, zc), (x, yi - 0.02 if top else yi, zc), (x, yo - 0.08, RAIL),
            (x, yo - 0.04, RAIL), (x, yo, RAIL - 0.04), (x, yo, 1.00), (x, yo - 0.20, 0.68),
            (x, 0, 0.66)]


def bed_panel(i, j):
    if j == 6:
        return "floor"
    if j == 5:
        return "bedsill"
    if j >= 3:
        return "corner" if i >= 3 else "bedside"
    if j == 2:
        return "rail"
    if i in (0, 5):
        return "rail"
    if i in (1, 4) or j == 1:
        return "bedwall"
    return "bedfloor"


BED_MAT = dict(floor="underbody", bedsill="cladding", corner="paint", bedside="paint",
               rail="cladding", bedwall="liner", bedfloor="plate", bedfront="paint",
               tailgate="paint")


def cutters():
    """Cut into the hull as it stands uncut: the fuel flap on each quarter, its outline a
    shut line through the plate (the flap the plate inside it)."""
    cut = Geo()
    x, z, w, h = FLAP
    K.groove(cut, K.rounded(x, z, w, h, 0.012), 'y', closed=True, mirror=True)
    return [(cut, "cut", "drop")]


def build_hull():
    hull = K.build_body(hull_stations(), hull_panel, HULL_MAT, 1.0, 1.0, name="hull",
                        front=dict(kind="flat", panel="nose"),
                        rear=dict(kind="flat", panel="cabback"),
                        glass=[("glass_ws", 0.055, "trim", "frame"),
                               ("glass_f", 0.05, "trim", "frame"),
                               ("glass_r", 0.05, "trim", "frame")],
                        cutters=cutters, subdiv=2, gap=GAP)
    rows = [bed_row(-1.06, BED_Y, True), bed_row(-1.11, BED_Y, True),
            bed_row(-1.13, BED_Y, False), bed_row(-2.57, BED_Y, False),
            bed_row(-2.60, BED_Y - 0.03, False, 0.59), bed_row(-2.62, BED_Y - 0.05, True, 0.59),
            bed_row(-2.70, BED_Y - 0.13, True, 0.51)]
    bed = K.build_body(rows, bed_panel, BED_MAT, 1.0, 1.0, name="bed",
                       front=dict(kind="flat", panel="bedfront"),
                       rear=dict(kind="flat", panel="tailgate"), subdiv=2, gap=GAP)
    for body in (hull, bed):                # plates want a broader edge than a sports car
        for ob in body.parts.values():
            md = ob.modifiers.get("bevel")
            if md is not None:
                md.width = 0.008


# ---------------------------------------------------------------------------------------
# fender plates, bumpers, hardware
# ---------------------------------------------------------------------------------------
F_FEN = [(2.50, 0.80), (2.30, FEN_Z), (1.50, FEN_Z), (1.30, 0.84)]
R_FEN = [(-1.07, 0.83), (-1.27, FEN_Z), (-1.97, FEN_Z), (-2.19, 0.80)]


def build_fenders():
    g, gb, gk = Geo(), Geo(), Geo()
    for pts, y0, brackets in ((F_FEN, 0.585, (2.16, 1.62)), (R_FEN, BED_Y + 0.02, (-1.40, -1.84))):
        y1 = T_OUT + 0.01
        plate(g, pts, FEN_T, y0, y1)
        plate(g, pts, 0.075, y1 - 0.028, y1)            # the outer edge folded down
        plate(g, pts, 0.06, y0, y0 + 0.02)              # the mounting flange
        for a, b in zip(pts, pts[1:]):
            L = hypot(b[0] - a[0], b[1] - a[1])
            n = (-(b[1] - a[1]) / L, 0, (b[0] - a[0]) / L)
            n = (-n[0], 0, -n[2]) if n[2] < 0 else n
            k = max(2, int(L / 0.115))
            for i in range(k):
                t = (i + 0.5) / k
                x, z = a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t
                for y in (y0 + 0.045, y1 - 0.06):
                    bolt(gb, (x, y, z), n)
        for x in brackets:                              # gussets to the body
            gk.prism([(x - 0.012, y0 - 0.03, FEN_Z - FEN_T), (x - 0.012, y0 + 0.26, FEN_Z - FEN_T),
                      (x - 0.012, y0 - 0.03, FEN_Z - 0.19)], (0.024, 0, 0))
    sec = [(-0.022, 0.0), (0.022, 0.0), (0.012, 0.01), (-0.012, 0.01)]
    for (xa, xb), ys in (((2.24, 1.56), (0.74, 0.835, 0.93)), ((-1.33, -1.91), (0.86, 0.95))):
        for y in ys:
            g.sweep([(xa, y, FEN_Z - 0.002), (xb, y, FEN_Z - 0.002)], sec, up=(0, 0, 1))
    g.obj("fender.plates", "paint2", bevel=0.006, mirror=True)
    gk.obj("fender.gussets", "cladding", bevel=0.003, mirror=True)
    gb.obj("fender.bolts", "rim_bright", mirror=True)
    # mud flaps behind every wheel, markers on the folded edges
    g = Geo()
    g.box((1.292, 0.86, 0.67), (0.014, 0.38, 0.34))
    g.box((-2.198, 0.905, 0.55), (0.014, 0.31, 0.50))
    g.obj("mudflaps", "rubber", bevel=0.003, mirror=True)
    g = Geo()
    y = T_OUT + 0.011
    g.box((2.16, y, FEN_Z - 0.035), (0.16, 0.006, 0.028))
    g.box((-1.40, y, FEN_Z - 0.035), (0.10, 0.006, 0.028))
    g.obj("led.markers", "led_accent", mirror=True)
    g = Geo()
    g.box((-1.86, y, FEN_Z - 0.035), (0.16, 0.006, 0.028))
    g.obj("led.markers_r", "led_rear", mirror=True)


FACE = 0.05             # a pylon's front: how far its plates stand off the corner
LENS = 0.044            # its lenses, set back in their windows
SW = 0.03               # half the width of a pylon's windows


def pylon(key, x, y, z0, z1, yaw, lit, lens):
    """A light pylon on a chamfered corner, facing yaw (degrees): a housing of plates sunk
    into the corner, a tall window over a row of LED modules on a reflector plate and an
    amber cell at its foot, each under its own lens in a bolted bezel, a guard of bars over
    the tall one. Made on the left side and mirrored."""
    R = Matrix.Rotation(rad(yaw), 3, 'Z')
    o = V3((x, y, 0))
    n = R @ V3((1, 0, 0))
    wb, wt = z0 + 0.135, z1 - 0.035            # the tall window
    ab, at = z0 + 0.04, z0 + 0.105             # the amber cell's window
    g = Geo()                                  # the housing: plates round two pockets
    lbox(g, o, R, (-0.03, 0.0), (-0.05, 0.05), (z0, z1))
    for sg in (1, -1):
        lbox(g, o, R, (0.0, FACE), sorted((sg * SW, sg * 0.05)), (z0, z1))
    for zz in ((wt, z1), (at, wb), (z0, ab)):
        lbox(g, o, R, (0.0, FACE), (-SW, SW), zz)
    g.obj("pylon." + key, "cladding", bevel=0.003, mirror=True)
    gb, gn = Geo(), Geo()                      # bolted bezels, the guard over the tall window
    for lo, hi in ((wb, wt), (ab, at)):
        for sg in (1, -1):
            lbox(gb, o, R, (FACE, FACE + 0.006), sorted((sg * (SW - 0.005), sg * (SW + 0.012))),
                 (lo - 0.012, hi + 0.012))
        for zz in ((hi - 0.005, hi + 0.012), (lo - 0.012, lo + 0.005)):
            lbox(gb, o, R, (FACE, FACE + 0.006), (-SW + 0.005, SW - 0.005), zz)
        for zz in (lo - 0.006, hi + 0.006):
            for b in (-SW - 0.0035, SW + 0.0035):
                bolt(gn, lpt(o, R, FACE + 0.006, b, zz), n, 0.0045, 0.003)
    gb.obj("pylon.%s.bezel" % key, "paint2", bevel=0.0015, mirror=True)
    gn.obj("pylon.%s.bolts" % key, "rim_bright", mirror=True)
    gg = Geo()
    k = 4
    for i in range(k):
        zz = wb + (wt - wb) * (i + 0.5) / k
        tube(gg, lpt(o, R, FACE + 0.016, -SW - 0.006, zz), lpt(o, R, FACE + 0.016, SW + 0.006, zz),
             0.0035, 8)
    for b in (-SW - 0.006, SW + 0.006):
        lbox(gg, o, R, (FACE + 0.004, FACE + 0.02), (b - 0.004, b + 0.004), (wb - 0.004, wt + 0.004))
    gg.obj("pylon.%s.guard" % key, "rim", bevel=0.001, mirror=True)
    # inside: an LED bar right under the lens in a V of reflector plates, the amber cell on
    # a reflector plate, the lenses (lit faces near the lens: the game pack bakes them)
    L = K.Lamp("lamp.pylon_" + key, lit=lit, glass=lens)
    lbox(L.housing, o, R, (0.0, 0.012), (-SW, SW), (wb, wt))
    for sg in (1, -1):                         # the reflector's two leaves
        L.chrome.add([lpt(o, R, 0.012, sg * 0.004, z) for z in (wb, wt)]
                     + [lpt(o, R, 0.036, sg * SW, z) for z in (wt, wb)]
                     + [lpt(o, R, 0.012, sg * 0.006, z) for z in (wb, wt)]
                     + [lpt(o, R, 0.034, sg * SW, z) for z in (wt, wb)],
                     [(0, 1, 2, 3), (7, 6, 5, 4), (0, 4, 5, 1), (1, 5, 6, 2), (2, 6, 7, 3),
                      (3, 7, 4, 0)])
    L.bar([lpt(o, R, 0.036, 0, wb + 0.008), lpt(o, R, 0.036, 0, wt - 0.008)], 0.018, 0.008,
          up=n)
    lbox(L.housing, o, R, (0.012, 0.032), (-0.006, 0.006), (wb, wt))     # the bar's spine
    lbox(L.glass, o, R, (LENS - 0.003, LENS), (-SW, SW), (wb, wt))
    L.obj(mirror=True)
    A = K.Lamp("lamp.pylon_%s_turn" % key, lit="led_accent", glass="lens_amber")
    lbox(A.chrome, o, R, (0.0, 0.026), (-SW, SW), (ab, at))
    A.bar([lpt(o, R, 0.034, -SW + 0.007, (ab + at) / 2), lpt(o, R, 0.034, SW - 0.007, (ab + at) / 2)],
          0.012, at - ab - 0.016, up=V3((0, 0, 1)))      # the amber cell right under its lens
    lbox(A.glass, o, R, (LENS - 0.003, LENS), (-SW, SW), (ab, at))
    A.obj(mirror=True)


def build_lights():
    pylon("f", 2.44, 0.50, 0.71, 1.17, 45, "led_front", "lens_clear")
    pylon("r", -2.635, BED_Y - 0.065, 0.90, 1.37, 135, "led_rear", "lens_red")
    # the bar over the windshield: a housing on the roof's front edge, eight cells of LED
    # modules behind one clear lens between dividers, a bolted top, amber lamps at its ends
    x1, y1, zb, zt = 0.70, 0.655, ROOF + 0.008, ROOF + 0.05
    g = Geo()
    g.prism([(0.675, -0.70, ROOF - 0.01), (0.675, -0.70, ROOF + 0.065), (0.56, -0.70, ROOF + 0.065),
             (0.50, -0.70, ROOF - 0.01)], (0, 1.40, 0))
    g.box(((0.675 + x1) / 2, 0, (zt + ROOF + 0.065) / 2), (x1 - 0.675, 1.40, ROOF + 0.065 - zt))
    g.box(((0.675 + x1) / 2, 0, (zb + ROOF - 0.01) / 2), (x1 - 0.675, 1.40, zb - ROOF + 0.01))
    for sg in (1, -1):
        g.box(((0.675 + x1) / 2, sg * (y1 + 0.70) / 2, (zb + zt) / 2), (x1 - 0.675, 0.70 - y1, zt - zb))
    for k in range(1, 8):
        y = -y1 + 2 * y1 * k / 8
        g.box(((0.675 + x1) / 2 + 0.003, y, (zb + zt) / 2), (x1 - 0.675 + 0.006, 0.014, zt - zb))
    g.obj("roofbar", "cladding", bevel=0.003)
    g = Geo()
    for k in range(9):
        y = -0.64 + 1.28 * k / 8
        bolt(g, (0.685, y, ROOF + 0.065), (0, 0, 1), 0.006, 0.0035)
    g.obj("roofbar.bolts", "rim_bright")
    L = K.Lamp("lamp.roofbar", lit="led_front")
    L.chrome.box((0.677, 0, (zb + zt) / 2), (0.004, 2 * y1, zt - zb))
    for k in range(8):
        yc = -y1 + 2 * y1 * (k + 0.5) / 8
        L.leds((0.69, yc - 0.06, (zb + zt) / 2), (0.69, yc + 0.06, (zb + zt) / 2), 3, (1, 0, 0),
               r=0.015)
    L.glass.box((0.6955, 0, (zb + zt) / 2), (0.003, 2 * y1, zt - zb))
    L.obj()
    # its amber end lamps: a window in a bolted end plate, a reflector in the pocket behind
    g = Geo()
    xa, xb, za, zc = 0.60, 0.67, ROOF + 0.012, ROOF + 0.046
    for (x0, x2), (z0, z2) in (((0.56, xa), (ROOF - 0.01, ROOF + 0.065)),
                               ((xb, x1), (ROOF - 0.01, ROOF + 0.065)),
                               ((xa, xb), (ROOF - 0.01, za)), ((xa, xb), (zc, ROOF + 0.065))):
        g.box(((x0 + x2) / 2, 0.711, (z0 + z2) / 2), (x2 - x0, 0.022, z2 - z0))
    g.obj("roofbar.ends", "paint2", bevel=0.0015, mirror=True)
    A = K.Lamp("lamp.roofbar_end", lit="led_accent", glass="lens_amber")
    A.reflector(((xa + xb) / 2, 0.7155, (za + zc) / 2), (0, 1, 0), r=0.016, depth=0.012)
    A.glass.box(((xa + xb) / 2, 0.7195, (za + zc) / 2), (xb - xa, 0.003, zc - za))
    A.obj(mirror=True)
    # work lamps on the sail frame's crossbar, facing the bed: a pocket each, two reflectors
    g, gg = Geo(), Geo()
    zc, x0, x2 = ROOF - 0.005, -1.215, -1.158
    for (y0, y2), (z0, z2) in (((0.26, 0.42), (zc - 0.04, zc - 0.028)),
                               ((0.26, 0.42), (zc + 0.028, zc + 0.04)),
                               ((0.26, 0.275), (zc - 0.028, zc + 0.028)),
                               ((0.405, 0.42), (zc - 0.028, zc + 0.028))):
        g.box(((x0 + x2) / 2, (y0 + y2) / 2, (z0 + z2) / 2), (x2 - x0, y2 - y0, z2 - z0))
    g.box(((-1.162 + x2) / 2, 0.34, zc), (x2 + 1.162, 0.16, 0.08))
    for y in (0.30, 0.38):
        tube(gg, (x0 - 0.008, y, zc - 0.034), (x0 - 0.008, y, zc + 0.034), 0.003, 8)
    g.obj("work.lamps", "cladding", bevel=0.002, mirror=True)
    gg.obj("work.guards", "rim", mirror=True)
    W = K.Lamp("lamp.work", lit="lamp")
    for y in (0.307, 0.373):
        W.reflector((-1.185, y, zc), (-1, 0, 0), r=0.027, depth=0.016)
    W.glass.box((-1.2075, 0.34, zc), (0.003, 0.13, 0.056))
    W.obj(mirror=True)
    # the stop lamp over the rear window: ten LEDs behind a red lens in a slim housing
    S = K.Lamp("lamp.stop", lit="led_rear", glass="lens_red")
    for (y0, y2), (z0, z2) in (((-0.27, 0.27), (1.775, 1.785)), ((-0.27, 0.27), (1.81, 1.82)),
                               ((-0.27, -0.25), (1.785, 1.81)), ((0.25, 0.27), (1.785, 1.81))):
        S.housing.box((-1.016, (y0 + y2) / 2, (z0 + z2) / 2), (0.028, y2 - y0, z2 - z0))
    S.leds((-1.014, -0.24, 1.7975), (-1.014, 0.24, 1.7975), 10, (-1, 0, 0), r=0.0105)
    S.glass.box((-1.0265, 0, 1.7975), (0.003, 0.50, 0.025))
    S.obj()


def build_bumpers():
    # front: a beam with swept, rising ends, the winch in a housing in its middle
    g = Geo()
    g.prism([(2.72, -0.52, 0.48), (2.72, 0.52, 0.48), (2.52, 0.52, 0.48), (2.52, -0.52, 0.48)],
            (0, 0, 0.22))
    for s in (1, -1):
        g.hexa([(2.72, s * 0.52, 0.48), (2.58, s * 1.00, 0.60), (2.52, s * 1.00, 0.60),
                (2.52, s * 0.52, 0.48), (2.72, s * 0.52, 0.70), (2.58, s * 1.00, 0.70),
                (2.52, s * 1.00, 0.70), (2.52, s * 0.52, 0.70)])
    g.prism([(2.72, -0.25, 0.50), (2.775, -0.25, 0.52), (2.79, -0.25, 0.56), (2.79, -0.25, 0.64),
             (2.775, -0.25, 0.68), (2.72, -0.25, 0.70)], (0, 0.50, 0))
    g.obj("bumper.front", "paint2", bevel=0.007)
    g = Geo()                                           # fairlead, rollers, hook
    g.box((2.793, 0, 0.60), (0.008, 0.30, 0.085))
    g.obj("winch.fairlead", "rim_bright", bevel=0.002)
    g = Geo()
    g.box((2.7975, 0, 0.60), (0.004, 0.22, 0.036))
    g.obj("winch.slot", "void")
    g = Geo()
    for z in (0.578, 0.622):
        tube(g, (2.80, -0.115, z), (2.80, 0.115, z), 0.011, 10)
    tube(g, (2.80, 0, 0.60), (2.815, 0.02, 0.585), 0.007, 8)
    g.obj("winch.rollers", "rim", bevel=0.001)
    g = Geo()
    g.lathe([(-0.008, 0.022), (-0.008, 0.040), (0.008, 0.040), (0.008, 0.022)], 12, a0=rad(-200),
            a1=rad(60),
            xf=Matrix.Translation((2.835, 0.02, 0.555)) @ Matrix.Rotation(pi / 2, 4, 'Z'))
    for y in (0.40, -0.40):                             # shackles on tabs
        g.box((2.735, y, 0.60), (0.05, 0.03, 0.075))
        g.lathe([(-0.009, 0.030), (-0.009, 0.050), (0.009, 0.050), (0.009, 0.030)], 14,
                xf=Matrix.Translation((2.745, y, 0.565)))
    for y in (0.45, -0.45):
        g.box((-2.80, y, 0.50), (0.04, 0.03, 0.07))
        g.lathe([(-0.009, 0.030), (-0.009, 0.050), (0.009, 0.050), (0.009, 0.030)], 14,
                xf=Matrix.Translation((-2.775, y, 0.445)))
    g.obj("hooks", "caliper", bevel=0.003)
    g = Geo()                                           # skid plate under the nose
    g.prism([(2.60, -0.42, 0.485), (2.30, -0.42, 0.42), (1.45, -0.42, 0.42), (1.45, -0.42, 0.445),
             (2.30, -0.42, 0.445), (2.60, -0.42, 0.51)], (0, 0.84, 0))
    for y in (-0.28, -0.14, 0.0, 0.14, 0.28):
        g.prism([(2.56, y - 0.02, 0.47), (2.30, y - 0.02, 0.405), (1.60, y - 0.02, 0.405),
                 (1.60, y - 0.02, 0.425), (2.30, y - 0.02, 0.425), (2.56, y - 0.02, 0.49)],
                (0, 0.04, 0))
    g.obj("skid", "rim", bevel=0.003)
    # rear: a step beam with a hitch
    g = Geo()
    g.prism([(-2.70, -0.86, 0.47), (-2.70, 0.86, 0.47), (-2.75, 0.86, 0.47), (-2.80, 0.76, 0.47),
             (-2.80, -0.76, 0.47), (-2.75, -0.86, 0.47)], (0, 0, 0.165))
    g.box((-2.79, 0, 0.455), (0.10, 0.11, 0.09))
    g.obj("bumper.rear", "paint2", bevel=0.007)
    g = Geo()
    g.box((-2.842, 0, 0.455), (0.006, 0.062, 0.05))
    g.obj("hitch.hole", "void")
    g = Geo()
    for y in (0.60, -0.60):                             # step pads
        for k in range(7):
            g.box((-2.752, y - 0.12 + k * 0.04, 0.6365), (0.07, 0.014, 0.005))
    g.obj("step.pads", "rim_bright", bevel=0.001)
    # frame rails and the cab's side steps
    g = Geo()
    tube(g, (-0.92, 0.36, 0.565), (-2.71, 0.36, 0.565), 0.062, 4, phase=pi / 4)
    g.box((0.0, 0.985, 0.455), (1.78, 0.17, 0.045))
    for x in (0.70, 0.0, -0.70):
        tube(g, (x, 0.80, 0.52), (x, 0.95, 0.47), 0.02, 4, phase=pi / 4)
    g.obj("frame", "cladding", bevel=0.004, mirror=True)
    g = Geo()
    for k in range(34):
        g.box((0.83 - k * 0.05, 0.985, 0.479), (0.014, 0.13, 0.005))
    g.obj("step.ribs", "rim_bright", mirror=True)


def build_nose():
    g = Geo()                                           # the ribbed slab
    for z in (0.775, 0.85, 0.925, 1.0):
        g.prism([(2.498, -0.39, z - 0.028), (2.53, -0.39, z - 0.013), (2.53, -0.39, z + 0.013),
                 (2.498, -0.39, z + 0.028)], (0, 0.78, 0))
    g.box((2.506, 0, 1.085), (0.016, 0.56, 0.07))
    g.obj("nose.ribs", "paint", bevel=0.004)
    g = Geo()
    for y in (0.25, -0.25):
        for z in (1.063, 1.107):
            bolt(g, (2.514, y, z), (1, 0, 0), 0.007, 0.004)
    g.obj("nose.bolts", "rim_bright")
    # hood: a bolted access plate, two latches
    g = Geo()
    g.box((1.86, 0, HOOD + 0.004), (0.74, 0.56, 0.012))
    g.obj("hood.plate", "paint", bevel=0.004)
    g = Geo()
    for x in (2.19, 1.53):
        for y in (0.24, 0.08, -0.08, -0.24):
            bolt(g, (x, y, HOOD + 0.01), (0, 0, 1), 0.009, 0.005)
    for y in (0.24, -0.24):
        for x in (1.97, 1.75):
            bolt(g, (x, y, HOOD + 0.01), (0, 0, 1), 0.009, 0.005)
    g.obj("hood.bolts", "rim_bright")
    g = Geo()
    for x in (2.25, 1.50):
        g.box((x, 0.41, HOOD + 0.006), (0.10, 0.035, 0.016))
        g.box((x, 0.47, HOOD - 0.04), (0.05, 0.03, 0.10), rot=Matrix.Rotation(rad(45), 3, 'X'))
    g.obj("hood.latches", "rubber", bevel=0.003, mirror=True)
    # cowl: louvres under the windshield
    g = Geo()
    g.louvers((1.30, 0.06, HOOD + 0.004), (1.30, 0.50, HOOD + 0.004), (1.10, 0.50, BELT + 0.004),
              (1.10, 0.06, BELT + 0.004), 9, 0.03, 0.006, rad(30), out=(0, 0, 1), margin=0.03)
    g.obj("cowl.louvres", "grille", bevel=0.0015, mirror=True)


# ---------------------------------------------------------------------------------------
# cab details, bed, sail frame
# ---------------------------------------------------------------------------------------
BOLTS = Geo()           # bolt heads on the body's left side and middle, mirrored at the end


def build_cab():
    # rub strips low on the doors, grab handles, hinges
    g = Geo()
    sec = [(-0.016, 0.0), (0.016, 0.0), (0.009, 0.014), (-0.009, 0.014)]
    for x0, x1 in ((0.92, 0.05), (-0.09, -0.77)):
        for z in (0.865, 0.925):
            y = side_y(z) - 0.002
            g.sweep([(x0, y, z), (x1, y, z)], sec, up=(0, 1, 0))
    g.obj("rubstrips", "cladding", bevel=0.002, mirror=True)
    g = Geo()
    for x in (0.10, -0.70):
        y = side_y(1.16)
        g.box((x, y + 0.035, 1.16), (0.17, 0.022, 0.034))
        for dx in (-0.07, 0.07):
            g.box((x + dx, y + 0.014, 1.16), (0.022, 0.03, 0.03))
    for x in (0.955, -0.045):
        for z in (0.98, 1.19):
            g.box((x, side_y(z) + 0.008, z), (0.06, 0.022, 0.085))
            tube(g, (x, side_y(z) + 0.02, z - 0.05), (x, side_y(z) + 0.02, z + 0.05), 0.011, 8)
    x, z, w, h = FLAP                       # the fuel flap's hinge on its front edge
    tube(g, (x + w / 2 - 0.004, side_y(z) + 0.004, z - 0.03),
         (x + w / 2 - 0.004, side_y(z) + 0.004, z + 0.03), 0.0055, 8)
    g.obj("door.hardware", "cladding", bevel=0.003, mirror=True)
    # mirrors: a plate on a tube frame
    g = Geo()
    tube(g, (0.86, 0.885, 1.33), (0.88, 0.99, 1.38), 0.011)
    tube(g, (0.86, 0.87, 1.56), (0.88, 0.99, 1.56), 0.011)
    tube(g, (0.88, 0.99, 1.36), (0.88, 0.99, 1.60), 0.011)
    g.box((0.875, 1.025, 1.48), (0.035, 0.095, 0.25))
    g.obj("mirrors", "cladding", bevel=0.004, mirror=True)
    g = Geo()
    g.box((0.856, 1.025, 1.48), (0.004, 0.08, 0.225))
    g.obj("mirror.glass", "rim_bright", mirror=True)
    # rear window in a thick frame, wipers, antenna
    g = Geo()
    g.box((-1.004, 0, 1.55), (0.022, 1.22, 0.40))
    g.obj("rearwin.frame", "cladding", bevel=0.005)
    g = Geo()
    g.box((-1.014, 0, 1.55), (0.006, 1.10, 0.29))
    g.obj("rearwin.glass", "gloss_black")
    g, gr = Geo(), Geo()                    # wipers at rest on the glass, both parked left
    for y0 in (0.07, -0.43):
        piv = on_body(y0 + 0.02, 1.30, 'x')[0]
        a, b = on_body(y0, 1.345, 'x')[0], on_body(y0 + 0.40, 1.675, 'x')[0]
        if piv is not None and a is not None and b is not None:
            K.wiper(g, gr, piv, a, b)
    gr.obj("wiper.blades", "rubber")
    g.obj("wipers", "cladding", bevel=0.001)
    g = Geo()                               # the antenna
    tube(g, (-0.70, 0.50, ROOF), (-0.76, 0.50, ROOF + 0.20), 0.006, 6, r2=0.003)
    g.box((-0.70, 0.50, ROOF + 0.008), (0.06, 0.06, 0.02))
    g.obj("antenna", "cladding", bevel=0.001)
    # roof ribs
    g = Geo()
    sec = [(-0.03, 0.0), (0.03, 0.0), (0.018, 0.012), (-0.018, 0.012)]
    for y in (-0.42, -0.21, 0.0, 0.21, 0.42):
        g.sweep([(0.42, y, ROOF - 0.002), (-0.90, y, ROOF - 0.002)], sec, up=(0, 0, 1))
    g.obj("roof.ribs", "paint", bevel=0.003)


def build_bed():
    # corrugated sides over the fender plates, ribs on the tailgate
    g = Geo()
    x = -1.19
    while x > -2.52:
        g.prism([(x - 0.032, BED_Y - 0.002, 1.095), (x - 0.017, BED_Y + 0.018, 1.105),
                 (x + 0.017, BED_Y + 0.018, 1.105), (x + 0.032, BED_Y - 0.002, 1.095)],
                (0, 0, 0.21))
        x -= 0.105
    g.obj("bed.ribs", "paint", bevel=0.003, mirror=True)
    g = Geo()
    for z in (0.80, 1.285):
        g.prism([(-2.698, -0.50, z - 0.03), (-2.722, -0.50, z - 0.014), (-2.722, -0.50, z + 0.014),
                 (-2.698, -0.50, z + 0.03)], (0, 1.0, 0))
    g.obj("tailgate.ribs", "paint", bevel=0.003)
    g = Geo()
    for y in (0.40, -0.40):
        g.box((-2.708, y, 1.285), (0.03, 0.12, 0.03))
    g.box((-2.705, 0, 0.80), (0.012, 0.30, 0.085))
    g.obj("tailgate.latches", "cladding", bevel=0.003)
    # tread plate: raised lozenges, each row leaning the other way
    g = Geo()
    kx = 0
    x = -1.17
    while x > -2.575:
        ky = 0
        y = -0.585
        while y < 0.59:
            a = rad(45 if (kx + ky) % 2 else -45)
            g.box((x, y, BFLOOR + 0.0015), (0.034, 0.011, 0.005), rot=Matrix.Rotation(a, 3, 'Z'))
            y += 0.045
            ky += 1
        x -= 0.045
        kx += 1
    g.obj("bed.tread", "plate")
    # tie-down rings on the walls, a rack rail on stanchions
    g = Geo()
    for x in (-1.35, -1.85, -2.35):
        g.box((x, 0.628, 1.215), (0.05, 0.016, 0.03))
        g.lathe([(-0.005, 0.024), (-0.005, 0.036), (0.005, 0.036), (0.005, 0.024)], 12,
                xf=Matrix.Translation((x, 0.622, 1.175)))
    g.obj("bed.rings", "rim_bright", bevel=0.0015, mirror=True)
    g = Geo()
    tube(g, (-1.93, 0.66, RAIL + 0.10), (-2.54, 0.66, RAIL + 0.10), 0.018, 10)
    for x in (-2.20, -2.50):
        tube(g, (x, 0.66, RAIL - 0.005), (x, 0.66, RAIL + 0.10), 0.014, 8)
        g.box((x, 0.66, RAIL + 0.005), (0.07, 0.05, 0.012))
    g.obj("bed.rails", "cladding", bevel=0.002, mirror=True)
    # the sail frame: a bar frame with a web, joined across the top behind the cab
    y = 0.675
    path = [(-1.035, y, RAIL + 0.03), (-1.035, y, ROOF - 0.035), (-1.19, y, ROOF - 0.035),
            (-1.97, y, RAIL + 0.03)]
    g = Geo()
    g.sweep(path, [(-0.03, -0.022), (0.03, -0.022), (0.03, 0.022), (-0.03, 0.022)],
            up=(0, 1, 0), closed=True)
    g.box((-1.50, y, RAIL + 0.004), (1.02, 0.07, 0.012))
    g.obj("sail.frame", "paint2", bevel=0.005, mirror=True)
    g = Geo()
    g.prism([(-1.05, y - 0.006, RAIL + 0.04), (-1.05, y - 0.006, ROOF - 0.05),
             (-1.18, y - 0.006, ROOF - 0.05), (-1.93, y - 0.006, RAIL + 0.04)], (0, 0.012, 0))
    g.obj("sail.web", "paint", mirror=True)
    for x, z in ((-1.035, 1.50), (-1.035, 1.70), (-1.11, ROOF - 0.035), (-1.40, 1.725),
                 (-1.62, 1.60), (-1.84, 1.47), (-1.30, RAIL + 0.03), (-1.60, RAIL + 0.03)):
        bolt(BOLTS, (x, y + 0.022, z), (0, 1, 0), 0.009, 0.005)
    g = Geo()
    g.box((-1.115, 0, ROOF - 0.005), (0.09, 1.35 + 0.045, 0.07))
    g.obj("sail.bar", "paint2", bevel=0.005)
    g = Geo()
    for yy in (0.34, -0.34):
        g.box((-1.15, yy, ROOF - 0.005), (0.03, 0.16, 0.075))
    g.obj("work.lamps", "cladding", bevel=0.004)


def build_bolts():
    """Rows of bolt heads on the body as built."""
    def row(pts, proj):
        for u, v in pts:
            loc, n = on_body(u, v, proj)
            if loc is not None:
                bolt(BOLTS, loc, n)
    row([(2.32 - k * 0.147, 0.395) for k in range(7)], 'z')              # hood edges
    row([(2.335, 0.07 + k * 0.14) for k in range(3)], 'z')
    row([(2.30 - k * 0.15, 1.105) for k in range(7)], 'y')               # nose side plate
    row([(0.52 - k * 0.205, 0.575) for k in range(8)], 'z')              # roof plate
    row([(-0.94, 0.07 + k * 0.14) for k in range(4)], 'z')
    row([(0.92 - k * 0.152, 0.70) for k in range(13)], 'y')              # sill
    row([(-0.925, 0.92), (-0.925, 1.22)], 'y')                           # quarter
    row([(0.985 - k * 0.012, 0.92 + k * 0.10) for k in range(4)], 'y')   # door's front edge
    row([(0.90 - 0.055 * k, 1.36 + 0.105 * k) for k in range(4)], 'y')   # pillar gusset
    row([(1.22, 0.86), (1.16, 1.00), (1.10, 1.14)], 'y')                 # cowl flare
    row([(-0.08, 1.40 + k * 0.11) for k in range(4)], 'y')               # B pillar
    row([(-0.91, 1.40 + k * 0.11) for k in range(4)], 'y')               # C pillar
    row([(0.535, 0.76 + k * 0.105) for k in range(6)], 'X')              # tailgate edges
    row([(-1.25 - k * 0.21, 0.66) for k in range(7)], 'z')               # bed rail
    BOLTS.obj("bolts", "rim_bright", mirror=True)


def build_lettering():
    g = Geo()                               # dark stencils on the paint
    for side in (1, -1):
        stencil(g, NUM, 0.34, on_side(0.49, 1.075, side))
        stencil(g, "HAULER", 0.105, on_side(-0.43, 1.165, side))
        stencil(g, "BRAKK INDUSTRIAL", 0.034, on_side(-0.43, 1.065, side), gap=0.2, cut=0)
        stencil(g, "GVW 3900 KG", 0.026, on_side(-0.43, 1.015, side), gap=0.2, cut=0)
        stencil(g, "B-" + NUM, 0.15, on_plane((-1.275, side * 0.6815, 1.605), (-side, 0, 0),
                                                 (0, 0, 1)))
    stencil(g, "BRAKK", 0.36, on_plane((-2.7005, 0, 1.05), (0, -1, 0), (0, 0, 1)), gap=0.16)
    stencil(g, NUM, 0.40, on_plane((1.86, 0, HOOD + 0.0105), (0, 1, 0), (-1, 0, 0)))
    stencil(g, "BRAKK", 0.062, on_plane((2.5145, 0, 1.085), (0, 1, 0), (0, 0, 1)), gap=0.2)
    g.obj("lettering", "decal")
    g = Geo()                               # light markings on the dark parts
    for s in (1, -1):
        d = V3((-0.14, s * 0.48, 0)).normalized()
        chevrons(g, on_plane((2.65, s * 0.76, 0.655), d * s, (0, 0, 1)), 0.44, 0.07, 5, s * 0.05)
        chevrons(g, on_plane((-2.8005, s * 0.52, 0.5525), (0, -1, 0), (0, 0, 1)), 0.40, 0.11, 5,
                 -s * 0.07)
    stencil(g, "WINCH 5T", 0.03, on_plane((2.7205, 0.39, 0.675), (0, 1, 0), (0, 0, 1)),
            gap=0.2, cut=0)
    stencil(g, "BK 4-2207", 0.05, on_plane((-2.8005, 0, 0.59), (0, -1, 0), (0, 0, 1)),
            gap=0.18, cut=0)
    up = V3((-0.20, 0, 0.25)).normalized()
    for s in (1, -1):                       # the unit number on the front fender slopes
        stencil(g, NUM, 0.17, on_plane(V3((2.4, s * 0.835, 0.925)) + V3((0.78, 0, 0.625)) * 0.001,
                                       (0, 1, 0), up))
    g.obj("markings", "mark")


# ---------------------------------------------------------------------------------------
# suspension and driveline
# ---------------------------------------------------------------------------------------
def build_chassis():
    g, gs = Geo(), Geo()
    x = FA_X
    # front: double wishbones, upright, tie rod, half shaft
    for xi in (x - 0.19, x + 0.19):
        tube(g, (xi, 0.38, 0.50), (x, 0.80, 0.33), 0.024, 4, phase=pi / 4)
        tube(g, (xi - 0.03 * (1 if xi < x else -1), 0.50, 0.78), (x, 0.79, 0.58), 0.02, 4,
             phase=pi / 4)                  # its ball joint low in the rim, clear of the tire
    g.box((x, 0.805, 0.455), (0.10, 0.05, 0.33))
    tube(g, (x + 0.10, 0.40, 0.58), (x + 0.08, 0.77, 0.52), 0.012)      # tie rod
    tube(g, (x, 0.36, 0.50), (x, 0.80, 0.45), 0.026, 10)
    tube(g, (x, 0.42, 0.495), (x, 0.50, 0.485), 0.05, 10, r2=0.03)
    coil(g, gs, (x, 0.66, 0.39), (x, 0.56, 1.0))
    # rear: a beam axle with its housing, trailing links, dampers, the shaft
    x = RA_X
    tube(g, (x, 0.0, T_R), (x, 0.80, T_R), 0.055, 10)
    tube(g, (-0.95, 0.52, 0.52), (x, 0.60, 0.40), 0.026, 4, phase=pi / 4)
    tube(g, (-0.95, 0.30, 0.60), (x, 0.24, 0.52), 0.02, 4, phase=pi / 4)
    coil(g, gs, (x - 0.02, 0.655, 0.43), (x + 0.10, 0.645, 0.99), 0.018)
    g.obj("chassis", "rim", bevel=0.003, mirror=True)
    gs.obj("springs", "caliper", bevel=0.004, mirror=True)
    g = Geo()
    g.lathe([(-0.13, 0.05), (-0.09, 0.14), (0.09, 0.14), (0.13, 0.05)], 10,
            xf=Matrix.Translation((x, 0, T_R)))
    g.lathe([(-0.01, 0.004), (-0.01, 0.11), (0.03, 0.10), (0.05, 0.06), (0.05, 0.004)], 10,
            xf=Matrix.Translation((x - 0.13, 0, T_R)) @ Matrix.Rotation(pi / 2, 4, 'Z'))
    tube(g, (x + 0.12, 0, T_R + 0.01), (-0.90, 0, 0.56), 0.03, 10)
    g.obj("driveline", "rim", bevel=0.004)


# ---------------------------------------------------------------------------------------
# interior
# ---------------------------------------------------------------------------------------
CFLOOR = 0.60                       # the cab floor's top: a tall step up over the sill
CAB_X0, CAB_X1 = -0.97, 1.05        # the rear wall inside the cab's back, the firewall at the
#                                     windshield's base (ahead of it, the lining met the cowl)


def cab_zone(label, p, n):
    """The lining's material where the module's rule (head over the belt, trim under it, face
    by face) would saw across the leaning cowl and pillars: rubber up the footwells' kick
    panels, the cowl and the pillars' feet in the dash's hard trim, the walls changing from
    trim to headliner just over the side windows' sills (1.28), behind the door cards."""
    if label == "fill":
        return "interior.carpet"
    if p is None or n is None or label in ("floor", "fire", "rear", "well"):
        return None
    if p.x > 0.80 and p.z < 0.98:
        return "interior.carpet"
    if p.x > 0.90 and p.z < 1.36:
        return "interior"
    return "interior.head" if p.z > 1.31 else "interior"


def wall_bar(P, cab, a, b, off=0.045, r=0.014, mat="interior.metal", inset=0.035):
    """A grab bar standing off the lining's left wall from (x, z) a to b, on two posts."""
    pa, na = cab.wall(a[0], a[1], 1)
    pb, nb = cab.wall(b[0], b[1], 1)
    qa, qb = pa + na * off, pb + nb * off
    P[mat].tube(qa, qb, r, 10)
    for p, n, q in ((pa, na, qa.lerp(qb, inset / (qb - qa).length)),
                    (pb, nb, qb.lerp(qa, inset / (qb - qa).length))):
        foot = p + (q - p - n * (q - p).dot(n))
        P[mat].tube(foot - n * 0.004, q, r * 0.75, 8)
        P["interior.gloss"].cyl(foot - n * 0.004, 0.008, r * 1.6, 10, axis=tuple(n))


def wall_bolts(g, cab, pts, lift, r=0.0065, h=0.0035):
    """Bolt heads on the lining's left wall at (x, z) points, lift off it."""
    for x, z in pts:
        p, n = cab.wall(x, z, 1)
        bolt(g, p + n * lift, n, r, h)


def glass_trim(g, cab, outline, center, w=(-0.015, 0.03, 0.08), lift=0.006, n=60, anchors=None):
    """A moulding round a window's edge from inside: a band laid on the lining and the glass
    along a polyline of the glass panel's outline (outline), reaching from w[0] outside it to
    w[-1] in toward center (the frame's width and a little of the glass), so the reveal's
    rays never show ragged at a grazing pane. anchors: laid on the lining only at that many
    stations, straight between them (a header over a lumpy lining)."""
    pts = [V3(p) for p in outline]
    L = [0.0]
    for a, b in zip(pts, pts[1:]):
        L.append(L[-1] + (b - a).length)
    rows = []
    for k in range(n + 1):
        s = L[-1] * k / n
        i = max(0, min(len(pts) - 2, next((j for j in range(len(L) - 1) if L[j + 1] >= s), 0)))
        q = pts[i].lerp(pts[i + 1], (s - L[i]) / max(L[i + 1] - L[i], 1e-9))
        inw = (V3(center) - q).normalized()
        row = []
        for t in w:
            p = q + inw * t
            o = cab._from(p)
            hit, nrm = cab.at(o, p - o)
            if hit is None:
                hit, nrm = p, (o - p).normalized()
            row.append(hit + nrm * (lift if t not in (w[0], w[-1]) else lift * 0.3))
        rows.append(row)
    if anchors:
        ks = [round(n * a / (anchors - 1)) for a in range(anchors)]
        for a, b in zip(ks, ks[1:]):
            for k in range(a + 1, b):
                t = (k - a) / (b - a)
                rows[k] = [p.lerp(q, t) for p, q in zip(rows[a], rows[b])]
    m = len(w)
    g.add([p for r in rows for p in r],
          [(i * m + j, i * m + j + 1, (i + 1) * m + j + 1, (i + 1) * m + j)
           for i in range(n) for j in range(m - 1)])


def extinguisher(P, c, h=0.40, r=0.055):
    """A fire extinguisher standing at c (its foot) in a strapped bracket."""
    c = V3(c)
    P["seat.red"].lathe([(0.0, 0.001), (0.0, r - 0.006), (0.006, r), (h - 0.07, r),
                         (h - 0.04, r * 0.7), (h - 0.03, 0.016), (h - 0.03, 0.001)], 20,
                        axis='z', at=tuple(c))
    P["interior.gloss"].cyl(c + V3((0, 0, h - 0.035)), 0.05, 0.018, 12)
    P["interior.metal"].box(c + V3((0.012, 0, h + 0.022)), (0.07, 0.012, 0.008),
                            rot=Matrix.Rotation(rad(-12), 3, 'Y'))
    P["interior.gloss"].pipe([c + V3((-0.012, 0, h + 0.01)), c + V3((-0.05, 0, h - 0.02)),
                              c + V3((-0.062, 0, h - 0.18))], 0.006, 8, up=(0, 1, 0))
    for z in (0.10, h - 0.12):
        P["interior.metal"].ring(c + V3((0, 0, z)), 'z', r + 0.004, sec=(0.022, 0.004), n=20)
    K.text_flat(P["screen.white"], "FIRE", 0.022, c + V3((-r - 0.0012, 0, h * 0.55)),
                (0, -1, 0), (0, 0, 1))


def roof_console(cab, x0, x1, w, deep=0.10, text=None):
    """An overhead console under the headliner from x0 (rear) to x1: a steel box whose sloped
    rear face carries a row of toggles (the last under a red guard) and whose underside a
    radio with a lit dial window and knobs, bolted at its corners."""
    zt = min(cab.roof(x, 0.0)[0].z for x in (x0, x1, (x0 + x1) / 2)) + 0.012
    P = C._Parts()
    xr = x0 + 0.08                                  # the foot of the sloped face
    P["interior"].prism([(x1, -w / 2, zt), (x1, -w / 2, zt - deep + 0.03),
                         (x1 - 0.03, -w / 2, zt - deep), (xr, -w / 2, zt - deep),
                         (x0, -w / 2, zt)], (0, w, 0))
    a, b = V3((xr, 0, zt - deep)), V3((x0, 0, zt))
    t = (b - a).normalized()
    nrm = V3((t.z, 0, -t.x))
    if nrm.x > 0:
        nrm = -nrm
    R = C._rot((0, 1, 0), t, nrm)
    m = a.lerp(b, 0.48) + nrm * 0.002
    P["interior.gloss"].box(m, (w - 0.05, 0.05, 0.004), rot=R)
    n = 6
    for k in range(n):
        y = -(w - 0.10) / 2 + (w - 0.10) * k / (n - 1)
        q = m + V3((0, y, 0)) + nrm * 0.004
        P["interior.metal"].box(q, (0.012, 0.016, 0.006), rot=R)
        P["interior.metal"].tube(q, q + nrm * 0.022 + t * 0.006, 0.0028, 6)
        P["screen.white" if k < n - 1 else "screen.warn"].box(q + t * 0.016, (0.010, 0.003, 0.0012),
                                                                rot=R)
    q = m + V3((0, (w - 0.10) / 2, 0)) + nrm * 0.004            # the guard over the last
    P["seat.red"].box(q + nrm * 0.016, (0.034, 0.03, 0.003), rot=R)
    # the radio on the underside
    xm = (xr + x1 - 0.03) / 2
    zb = zt - deep - 0.0015
    P["interior.gloss"].box((xm, 0, zb), (x1 - 0.03 - xr - 0.04, w - 0.06, 0.003))
    P["screen.lit"].box((xm + 0.02, 0.05, zb - 0.0018), (0.05, 0.12, 0.0008))
    for y in (-0.10, -0.05):
        P["interior.metal"].cyl((xm + 0.02, y, zb - 0.001), 0.018, 0.013, 14, axis=(0, 0, -1))
    if text:
        K.text_flat(P["screen.white"], text, 0.011, V3((xm - 0.03, 0.05, zb - 0.0018)),
                    (0, -1, 0), (1, 0, 0))
    for x in (xr + 0.02, x1 - 0.05):
        for y in (-w / 2 + 0.02, w / 2 - 0.02):
            bolt(P["interior.metal"], (x, y, zt - deep), (0, 0, -1), 0.006, 0.003)
    cab._emit("console_roof", P)


def build_interior():
    """The crew cab (vehicles/cabin.py): a work truck's cab lined from the cowl to a wall just
    inside the cab's back, a rubber floor with ribbed mats, four tough upright seats in tan
    vinyl with orange stitching (two buckets and a rear bench for two), a hard grey dash with
    an orange band and HAULER on a bolted plate, the gauge hood and a small screen, a
    four-spoke wheel on a truck's raked column, a lever on the console, door cards with
    bolted steel kick plates and bar pulls, grab bars on the A and B pillars, an overhead
    console of toggles and a radio, a fire extinguisher by the mate's feet, a smoked rear
    window behind its frame; the interior views cab_*."""
    C.materials(carpet=(0.030, 0.031, 0.034), head=(0.30, 0.30, 0.29), soft=(0.07, 0.072, 0.078),
                trim=(0.78, 0.33, 0.006), trim_metal=0.0, trim_rough=0.45,
                metal=(0.50, 0.51, 0.52), accent=(0.075, 0.04, 0.02),
                piping=(0.78, 0.33, 0.006), mat=(0.016, 0.016, 0.018),
                ambient=(1.0, 0.55, 0.12), ambient_strength=4.0)
    sb = next(n for n in K.MAT["seat"].node_tree.nodes if n.type == 'BSDF_PRINCIPLED')
    sb.inputs["Roughness"].default_value = 0.72             # a work vinyl, not a gloss
    sb.inputs["Specular IOR Level"].default_value = 0.3
    # the spine on to 20 cm of each end: with the module's 0.45 m the footwells lay in the
    # front pole's fan, and a pole near the upright windshield's base saw its sides grazing
    cab = C.Cabin(CAB_X0, CAB_X1, CFLOOR, style="brakk", cap=0.20,
                  rear_window=(0.50, 1.44, 1.68))
    cab.step = 0.03         # the lining's grid at detail 2's 30 mm (the seats stay at detail 1):
    #                         the reveals round the upright windshield came out ragged at 40 mm
    lin = cab.lining(smooth=5, zone=cab_zone, wall="interior.head")
    for v in lin.data.vertices:         # held under the cowl, which the windshield's base meets
        if v.co.x > 0.95 and v.co.z > 1.08:
            v.co = cab.keep(v.co, margin=0.03, wells=False)
    cab.seat((0.10, 0.40, CFLOOR + 0.38), driver=True, rake=17, back=0.60, bolster=0.55)
    cab.seat((0.10, -0.40, CFLOOR + 0.38), rake=17, back=0.60, bolster=0.55)
    cab.seat((-0.58, 0.0, CFLOOR + 0.37), places=2, width=1.30, rake=15, back=0.54)
    d = cab.dash(depth=0.38, fascia=0.15, knee=0.12)
    cab.cluster()
    cab.screen(graphics="map")
    cab.wheel(tilt=34, r=0.19)
    cab.pedals()
    cab.console(w=0.24, h=0.24, cups=2, switches=5)
    cab.door(0.06, 0.90, tag="door_f", sill_text="HAULER", pull="bar", speaker=False)
    cab.door(-0.76, -0.10, tag="door_r", sill=False, pull="bar", speaker=False)
    cab.roof_kit()
    cab.mats()
    # the brand's hardware: grab bars up the A pillars and on the B pillars, steel kick
    # plates bolted on the door cards, the overhead console, the extinguisher
    P = C._Parts()
    wall_bar(P, cab, (1.00, 1.33), (0.83, 1.70), off=0.05)
    wall_bar(P, cab, (-0.08, 1.02), (-0.08, 1.52), off=0.05)
    for xa, xb in ((0.06, 0.90), (-0.76, -0.10)):
        xm = (xa + xb) / 2
        cab.pad(P["interior.metal"], 'y', (xm, CFLOOR + 0.11), xb - xa - 0.10, 0.12, r=0.01,
                lift=0.026, n=2, rings=())
        wall_bolts(P["interior.gloss"], cab, [(xm + s * (xb - xa - 0.16) / 2, CFLOOR + 0.11 + t)
                                              for s in (-1, 1) for t in (-0.04, 0.04)], 0.027)
    # a moulding round the windshield's sides and top (its reveal at the grazing glass)
    glass_trim(P["interior"], cab, [(1.03, 0.80, 1.22), (1.02, 0.80, 1.28), (0.74, 0.76, 1.78),
                                    (0.77, 0.66, 1.80)], (0.93, 0.0, 1.52),
               w=(-0.07, -0.03, 0.03, 0.085), n=40)
    glass_trim(P["interior"], cab, [(0.77, 0.70, 1.79), (0.78, 0.60, 1.80), (0.78, 0.0, 1.80)],
               (0.93, 0.0, 1.52), w=(-0.15, -0.09, -0.02, 0.06), n=40, lift=0.014, anchors=4)
    cab._emit("hardware", P, mirror=True)
    roof_console(cab, 0.30, 0.62, 0.38, text="CH 19")
    P = C._Parts()
    extinguisher(P, (0.74, -(cab.half(0.74, CFLOOR + 0.25) - 0.09), CFLOOR + 0.002))
    cab._emit("extinguisher", P, one_sided=True)
    # HAULER on a bolted plate over the glovebox
    P = C._Parts()
    c, nrm, up = d["face"](-0.36, 0.30)
    sd = up.cross(nrm).normalized()
    P["interior.metal"].box(c + nrm * 0.004, (0.17, 0.046, 0.004), rot=C._rot(sd, up, nrm))
    K.text_flat(P["interior.gloss"], "HAULER", 0.022, c + nrm * 0.0064, -sd if sd.y > 0 else sd,
                up, spacing=1.2)
    for s in (-1, 1):
        bolt(P["interior.gloss"], c + nrm * 0.006 + sd * (s * 0.074), nrm, 0.004, 0.002)
    cab._emit("plate", P, one_sided=True)
    cab.views(exposure=0.5, outside=3.0, daylight=14.0)
    cab.report()
    K.meant("symmetry", *cab.one_sided, "interior.roof.*", "interior.console_roof.*")


# ---------------------------------------------------------------------------------------
# views of its own, and the build
# ---------------------------------------------------------------------------------------
K.VIEWS["hero"].update(dir=(1.0, 0.66, 0.17), lens=58, focus=(1.9, 0.9, 0.8),
                        target=(0, 0, 0.81))
K.VIEWS["rear"].update(dir=(-1.0, -0.74, 0.42), focus=(-1.9, -0.8, 0.9))
K.VIEWS["back"].update(dir=(-1.0, 0.0, 0.16))
K.VIEWS.update(
    wheel=dict(dir=(0.55, 1.0, 0.12), lens=85, target=(FA_X, 0.9, 0.5), fit=("tire.fl",),
               margin=0.0),
    nose=dict(dir=(1.0, 0.5, 0.16), lens=85, target=(2.3, 0.4, 0.85), dist=4.2),
    bed=dict(dir=(-1.0, 0.45, 0.55), lens=70, target=(-1.8, 0, 1.1), dist=5.5),
)


def main():
    K.materials(paint=(0.78, 0.33, 0.006), paint_finish=(0.0, 0.40, 0.5),
                paint2=(0.035, 0.038, 0.042), paint2_finish=(0.35, 0.52, 0.0),
                dust=(0.24, 0.19, 0.13), dust_amount=0.6, dust_z=(0.42, 0.95),   # a truck:
                glass=(0.33, 0.37, 0.39),                           # the dust climbs higher
                led_front=(1.0, 0.86, 0.62), led_accent=(1.0, 0.42, 0.03),
                caliper=(0.50, 0.02, 0.015), seat=(0.13, 0.065, 0.03),
                decal=(0.012, 0.012, 0.013), screen=(1.0, 0.55, 0.12))
    K.pbr("plate", (0.22, 0.225, 0.23), 1.0, 0.5)           # bare tread plate
    K.pbr("liner", (0.03, 0.03, 0.032), 0.0, 0.85)          # the bed's sprayed lining
    K.pbr("mark", (0.78, 0.33, 0.006), 0.0, 0.5)             # markings on the dark parts
    K.pbr("tiremark", (0.085, 0.085, 0.085), 0.0, 0.6)
    build_hull()
    K.log("hull and bed")
    build_fenders()
    build_lights()
    build_bumpers()
    build_nose()
    build_cab()
    build_bed()
    build_bolts()
    build_lettering()
    build_chassis()
    build_interior()
    K.log("details")
    for side, s in ((1, "l"), (-1, "r")):
        build_wheel("f" + s, FA_X, side)
        build_wheel("r" + s, RA_X, side)
    # the spare stands in the bed against its front wall, under a strap
    build_wheel("spare", 0, 1, loc=(-1.13 - T_W / 2 - 0.03, 0, BFLOOR + T_R + 0.004), yaw=pi / 2)
    g = Geo()
    xs = -1.13 - T_W - 0.035
    g.sweep([(-1.12, 0, RAIL - 0.02), (-1.13, 0, BFLOOR + 2 * T_R + 0.012),
             (xs, 0, BFLOOR + 2 * T_R + 0.012), (xs - 0.02, 0, BFLOOR + 0.01)],
            [(-0.004, -0.03), (0.004, -0.03), (0.004, 0.03), (-0.004, 0.03)], up=(0, 1, 0))
    g.obj("spare.strap", "mark", bevel=0.001)
    K.log("wheels")
    # one-sided by design (the cabin's own: build_interior), both wipers parked to
    # the left, the antenna on the left, the winch hook hung off its rollers, the tread
    # plate's lozenges leaning in turn
    K.meant("symmetry", "antenna", "wipers", "wiper.blades", "hooks", "winch.rollers",
            "bed.tread")
    K.shoot()


main()
