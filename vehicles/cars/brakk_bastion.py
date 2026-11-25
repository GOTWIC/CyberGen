"""Brakk Bastion: an armored utility vehicle of flat plates (both names made up), on
vehicles/carkit.py.

Run (always through the wrapper, one Blender job at a time on this machine):
    vehicles/blender.sh vehicles/cars/brakk_bastion.py --out DIR --preview
    vehicles/blender.sh vehicles/cars/brakk_bastion.py --out DIR --sheet

The second Brakk, the Hauler's sibling (family cues: docs/progress/AG18/brakk_hauler/README.md):
plates and 45 degree chamfers, the wheels outside the hull under bolted fender plates, light
pylons on the chamfered corners, a bar over the windshield, the ribbed slab face, fasteners in
rows, stencils, the Brakk wheel. Its own ideas: one hull that is a wedge at both ends (a
sloped hood and windshield, a sloped glass hatch), a citadel between the wheels whose doors
bulge out to a belt crease and lean in above and below it, a shallow V floor, slit windows
(the rear ones behind armor louvres, a sensor band on the tail), hub motors in the open
wheels, a drone on a roof pad, a folding sensor mast, fold-down steps and the spare on a
swing arm.

Pieces: the hull (eight lines over fourteen stations, every edge sharp) and plates, bars and
tubes for the rest. The lamps are pockets in housings of plates under lenses: the brand's
step B pylon on each corner (an LED bar in a reflector V, an amber cell, bolted bezels, a
guard), a framed LED blade across the prow, LED modules behind one lens in the roof bar with
amber end lamps, work lamps on the rack and a stop lamp over the hatch; the charge ports'
flaps are cut through the nose sides (cutters()). The brand's helpers (plates, bolts,
stencils, stripes, the pylon, the coil, the wheel) are in vehicles/brands/brakk.py.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import carkit as K                                                  # noqa: E402
import cabin as C                                                   # noqa: E402
from functools import partial                                       # noqa: E402
from brands import brakk                                            # noqa: E402
from brands.brakk import (bolt, chevrons, coil, lamp_pylon, on_plane, on_side,  # noqa: E402
                          plate, ring, stencil, tube, zcyl)
from carkit import Geo, Matrix, V3, cos, hypot, on_body, pi, rad, sin, stud    # noqa: E402

# ---------------------------------------------------------------------------------------
# dimensions
# ---------------------------------------------------------------------------------------
FA_X, RA_X = 1.58, -1.52            # axles: wheelbase 3.1
T_R, T_W, T_RIM, T_OUT = 0.475, 0.34, 0.25, 1.10       # tire radius, width, rim, outer face
ROOF, BELT = 1.86, 1.02
H_Z, W_Z = 1.74, 1.40               # the slit windows: top and sill
FEN_Z, FEN_T = 1.07, 0.03           # fender plates: top height, thickness
TAIL_X = -2.14
SPARE_X, SPARE_Z = TAIL_X - 0.07 - T_W / 2, 1.10
NUM = "41"
HOOD_K = 0.306                      # the hood's slope: 17 degrees
GAP = 0.00175                       # shut lines 3.5 mm
PORT = (1.50, 1.17, 0.075)          # the charge port's flap on the nose side: x, z, radius

# the Brakk wheel (vehicles/brands/brakk.py) at this car's sizes, as its own copy built it
build_wheel = partial(brakk.wheel, R=T_R, w=T_W, rim=T_RIM, out=T_OUT, lugs=24,
                      text="BRAKK  TRAKTOR  E/T    38 X 13.5 R20    ", seg=96, dish=brakk.DISH)


def hood_z(x):
    """The hood's top plate: it rises from the prow to the windshield."""
    return 1.18 + (2.28 - x) * HOOD_K


def hatch_z(x):
    """The sloped hatch behind the roof."""
    return ROOF + (x + 1.40) * (0.50 / 0.64)


def side_y(z):
    """The citadel's side: widest on the belt crease, leaning in above and below it."""
    if z >= BELT:
        return 0.90 - 0.22 * (z - BELT) / (H_Z - BELT)
    return 0.80 + 0.10 * (z - 0.72) / (BELT - 0.72)


# ---------------------------------------------------------------------------------------
# hull: a wedge nose, the citadel between the wheels, a wedge tail
# ---------------------------------------------------------------------------------------
LINES = "CRHWGUFB"
#        C top centerline, R roof plate edge / hood top, H foot of the roof chamfer (glass
#        top) / hood edge, W window sill / foot of the hood chamfer, G the belt crease,
#        U foot of the door plate, F floor edge, B floor centerline (a shallow V)
ORDER = ["P0", "P1", "A", "W0", "W1", "W2", "D1", "D2", "D3", "D4", "T0", "T1", "T2", "T3"]
PT = {}


def cab_row(x):
    return [(x, 0, ROOF), (x, .56, ROOF), (x, .68, H_Z), (x, side_y(W_Z), W_Z), (x, .90, BELT),
            (x, .80, .72), (x, .62, .52), (x, 0, .44)]


def tail_row(x):
    return [(x, 0, ROOF), (x, .46, ROOF), (x, .58, H_Z), (x, .618, W_Z), (x, .66, BELT),
            (x, .62, .74), (x, .50, .56), (x, 0, .50)]


def hull_stations():
    T = {
        "P0": [(2.40, 0, 1.08), (2.40, .23, 1.08), (2.40, .34, 1.08), (2.40, .46, .98),
               (2.40, .46, .88), (2.40, .46, .76), (2.40, .34, .60), (2.40, 0, .60)],
        "P1": [(2.28, 0, 1.18), (2.28, .23, 1.18), (2.28, .46, 1.18), (2.28, .58, 1.06),
               (2.28, .58, .90), (2.28, .58, .76), (2.28, .44, .60), (2.28, 0, .54)],
        "A": [(1.30, 0, hood_z(1.30)), (1.30, .23, hood_z(1.30)), (1.30, .46, hood_z(1.30)),
              (1.14, .58, hood_z(1.14) - 0.12), (1.14, .58, 1.0), (1.14, .58, .74),
              (1.14, .44, .58), (1.14, 0, .50)],
        "W0": [(1.26, 0, 1.49), (1.26, .46, 1.49), (.96, .76, 1.47), (.86, .80, W_Z),
               (.84, .90, BELT), (.84, .80, .72), (.84, .62, .52), (.84, 0, .44)],
        "W1": [(.66, 0, 1.79), (.66, .54, 1.79), (.56, .68, H_Z), (.56, side_y(W_Z), W_Z),
               (.56, .90, BELT), (.56, .80, .72), (.56, .62, .52), (.56, 0, .44)],
        "W2": [(.56, 0, ROOF), (.56, .56, ROOF), (.50, .68, H_Z), (.50, side_y(W_Z), W_Z),
               (.50, .90, BELT), (.50, .80, .72), (.50, .62, .52), (.50, 0, .44)],
        "D1": cab_row(.04), "D2": cab_row(-.08), "D3": cab_row(-.62), "D4": cab_row(-.80),
        "T0": tail_row(-1.00), "T1": tail_row(-1.40),
        "T2": [(-2.04, 0, 1.36), (-2.04, .4756, 1.36), (-2.04, .5956, 1.24),
               (-2.04, .6078, 1.13), (-2.04, .62, BELT), (-2.04, .59, .76), (-2.04, .47, .60),
               (-2.04, 0, .56)],
        "T3": [(TAIL_X, 0, 1.26), (TAIL_X, .38, 1.26), (TAIL_X, .50, 1.14), (TAIL_X, .51, 1.08),
               (TAIL_X, .52, BELT), (TAIL_X, .49, .78), (TAIL_X, .39, .66), (TAIL_X, 0, .66)],
    }
    S = K.fill([T[k] for k in ORDER])
    PT.update(K.table(ORDER, LINES, S))
    return S


def hull_panel(i, j):
    if j == 6:
        return "floor"
    if j == 5:
        return "sill"
    return (("nose_top", "nose_top", "nose_corner", "nose_corner", "nose_corner"),
            ("hood", "hood", "hood_ch", "nose_side", "nose_side"),
            ("cowl", "cowl", "cowl_side", "cowl_side", "cowl_side"),
            ("glass_ws", "glass_ws", "pillar_a", "door_f", "door_f"),
            ("brow", "brow", "glass_f", "door_f", "door_f"),
            ("roof", "roof_edge", "glass_f", "door_f", "door_f"),
            ("roof", "roof_edge", "pillar_b", "door_r", "door_r"),
            ("roof", "roof_edge", "glass_r", "door_r", "door_r"),
            ("roof", "roof_edge", "pillar_c", "door_r", "door_r"),
            ("roof", "roof_edge", "band_q", "quarter", "quarter"),
            ("roof", "roof_edge", "sensor", "tail_side", "tail_side"),
            ("glass_h", "hatch_edge", "tail_side", "tail_side", "tail_side"),
            ("tail_ring",) * 5)[i][j]


HULL_MAT = dict(nose_top="paint", nose_corner="paint", hood="paint", hood_ch="paint",
                nose_side="paint", cowl="cladding", cowl_side="paint", glass_ws="glass",
                pillar_a="paint", door_f="paint", brow="paint", glass_f="glass", roof="paint",
                roof_edge="paint", pillar_b="cladding", door_r="paint", glass_r="glass",
                pillar_c="cladding", band_q="cladding", quarter="paint", sensor="gloss_black",
                tail_side="paint",
                glass_h="glass", hatch_edge="paint", tail_ring="paint", sill="cladding",
                floor="underbody", trim="cladding", nose="cladding", hatch="paint", cut="void")


def cutters():
    """Cut into the hull as it stands uncut: the charge port's flap on each side of the nose,
    an octagon whose outline is a shut line through the plate (the flap the plate inside)."""
    cut = Geo()
    x, z, r = PORT
    K.groove(cut, K.ngon(x, z, r, 8, 22.5), 'y', closed=True, mirror=True)
    return [(cut, "cut", "drop")]


def build_hull():
    K.build_body(hull_stations(), hull_panel, HULL_MAT, 1.0, 1.0, name="hull",
                 front=dict(kind="flat", panel="nose"), rear=dict(kind="flat", panel="hatch"),
                 glass=[("glass_ws", 0.055, "trim", "frame"), ("glass_f", 0.05, "trim", "frame"),
                        ("glass_r", 0.05, "trim", "frame"), ("glass_h", 0.085, "trim", "frame")],
                 cutters=cutters, subdiv=2, gap=GAP, bevel=0.008)


# ---------------------------------------------------------------------------------------
# fender plates, lights
# ---------------------------------------------------------------------------------------
BOLTS = Geo()           # bolt heads on the left side and the middle, mirrored at the end
F_FEN = [(2.15, 0.82), (1.95, FEN_Z), (1.22, FEN_Z), (1.05, 0.85)]
R_FEN = [(-0.97, 0.86), (-1.15, FEN_Z), (-1.89, FEN_Z), (-2.09, 0.82)]


def build_fenders():
    g, gb, gk = Geo(), Geo(), Geo()
    y1 = T_OUT + 0.012
    for pts, y0, brackets in ((F_FEN, 0.585, (1.82, 1.34)), (R_FEN, 0.652, (-1.28, -1.76))):
        plate(g, pts, FEN_T, y0, y1)
        plate(g, pts, 0.08, y1 - 0.028, y1)             # the outer edge folded down
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
            gk.prism([(x - 0.012, y0 - 0.02, FEN_Z - FEN_T), (x - 0.012, y0 + 0.30, FEN_Z - FEN_T),
                      (x - 0.012, y0 - 0.02, FEN_Z - 0.24)], (0.024, 0, 0))
    sec = [(-0.022, 0.0), (0.022, 0.0), (0.012, 0.01), (-0.012, 0.01)]
    for (xa, xb), ys in (((1.90, 1.27), (0.70, 0.80, 0.90, 1.0)), ((-1.20, -1.84), (0.78, 0.89, 1.0))):
        for y in ys:
            g.sweep([(xa, y, FEN_Z - 0.002), (xb, y, FEN_Z - 0.002)], sec, up=(0, 0, 1))
    g.obj("fender.plates", "paint2", bevel=0.006, mirror=True)
    gk.obj("fender.gussets", "cladding", bevel=0.003, mirror=True)
    gb.obj("fender.bolts", "rim_bright", mirror=True)
    g = Geo()                                           # mud flaps behind every wheel
    g.box((1.043, 0.92, 0.67), (0.014, 0.34, 0.36))
    g.box((-2.098, 0.93, 0.63), (0.014, 0.33, 0.38))
    g.obj("mudflaps", "rubber", bevel=0.003, mirror=True)
    g = Geo()                                           # markers on the folded edges
    y = y1 + 0.001
    g.box((1.80, y, FEN_Z - 0.04), (0.18, 0.006, 0.03))
    g.box((-1.30, y, FEN_Z - 0.04), (0.12, 0.006, 0.03))
    g.obj("led.markers", "led_accent", mirror=True)
    g = Geo()
    g.box((-1.76, y, FEN_Z - 0.04), (0.18, 0.006, 0.03))
    g.obj("led.markers_r", "led_rear", mirror=True)


def build_lights():
    # the corner pylons (the brand's step B pylon): white in front, red behind
    lamp_pylon("f", 2.34, 0.52, 0.66, 1.20, 45, "led_front", "lens_clear")
    lamp_pylon("r", -2.09, 0.565, 0.74, 1.24, 135, "led_rear", "lens_red")
    # a blade of light across the prow, from pylon to pylon: a frame of plates proud of the
    # nose round one long window, an LED bar right under its lens on a reflector plate
    x0, x1, yb, yw, zb, zt = 2.40, 2.436, 0.33, 0.30, 1.015, 1.07
    zc = (zb + zt) / 2
    g = Geo()
    for (ya, yc), (za, zd) in (((-yb, yb), (zb, zc - 0.015)), ((-yb, yb), (zc + 0.015, zt)),
                               ((-yb, -yw), (zb, zt)), ((yw, yb), (zb, zt))):
        g.box(((x0 + x1) / 2, (ya + yc) / 2, (za + zd) / 2), (x1 - x0, yc - ya, zd - za))
    g.obj("prow.blade.housing", "cladding", bevel=0.003)
    g = Geo()
    for y in (-0.315, 0.315):
        for z in (zb + 0.009, zt - 0.009):
            bolt(g, (x1, y, z), (1, 0, 0), 0.0045, 0.003)
    g.obj("prow.blade.bolts", "rim_bright")
    B = K.Lamp("lamp.blade", lit="led_front")
    B.chrome.box((x0 + 0.006, 0, zc), (0.012, 2 * yw, 0.03))
    B.bar([(2.424, -yw + 0.01, zc), (2.424, yw - 0.01, zc)], 0.008, 0.018)
    B.glass.box((2.4315, 0, zc), (0.003, 2 * yw, 0.03))
    B.obj()
    # the bar over the windshield: a housing on the roof's front edge, eight cells of LED
    # modules behind one clear lens between dividers, a bolted top, amber lamps at its ends
    xf, x1, y1, yh = 0.63, 0.655, 0.515, 0.56
    zb, zt, ztop = ROOF + 0.008, ROOF + 0.05, ROOF + 0.065
    g = Geo()
    g.prism([(xf, -yh, ROOF - 0.03), (xf, -yh, ztop), (0.49, -yh, ztop),
             (0.43, -yh, ROOF - 0.005)], (0, 2 * yh, 0))
    g.box(((xf + x1) / 2, 0, (zt + ztop) / 2), (x1 - xf, 2 * yh, ztop - zt))
    g.box(((xf + x1) / 2, 0, (zb + ROOF - 0.03) / 2), (x1 - xf, 2 * yh, zb - ROOF + 0.03))
    for sg in (1, -1):
        g.box(((xf + x1) / 2, sg * (y1 + yh) / 2, (zb + zt) / 2), (x1 - xf, yh - y1, zt - zb))
    for k in range(1, 8):
        y = -y1 + 2 * y1 * k / 8
        g.box(((xf + x1) / 2 + 0.003, y, (zb + zt) / 2), (x1 - xf + 0.006, 0.014, zt - zb))
    g.obj("roofbar", "cladding", bevel=0.003)
    g = Geo()
    for k in range(9):
        y = -0.50 + 1.0 * k / 8
        bolt(g, (0.64, y, ztop), (0, 0, 1), 0.006, 0.0035)
    g.obj("roofbar.bolts", "rim_bright")
    L = K.Lamp("lamp.roofbar", lit="led_front")
    L.chrome.box((xf + 0.002, 0, (zb + zt) / 2), (0.004, 2 * y1, zt - zb))
    for k in range(8):
        yc = -y1 + 2 * y1 * (k + 0.5) / 8
        L.leds((0.645, yc - 0.045, (zb + zt) / 2), (0.645, yc + 0.045, (zb + zt) / 2), 3,
               (1, 0, 0), r=0.013)
    L.glass.box((0.6505, 0, (zb + zt) / 2), (0.003, 2 * y1, zt - zb))
    L.obj()
    # its amber end lamps: a window in a bolted end plate, a reflector in the pocket behind
    g = Geo()
    xa, xb, za, zc = 0.53, 0.60, ROOF + 0.012, ROOF + 0.046
    for (xl, xr), (z0, z2) in (((0.47, xa), (ROOF - 0.02, ztop)), ((xb, x1), (ROOF - 0.03, ztop)),
                               ((xa, xb), (ROOF - 0.025, za)), ((xa, xb), (zc, ztop))):
        g.box(((xl + xr) / 2, yh + 0.011, (z0 + z2) / 2), (xr - xl, 0.022, z2 - z0))
    g.obj("roofbar.ends", "paint2", bevel=0.0015, mirror=True)
    A = K.Lamp("lamp.roofbar_end", lit="led_accent", glass="lens_amber")
    A.reflector(((xa + xb) / 2, yh + 0.0155, (za + zc) / 2), (0, 1, 0), r=0.016, depth=0.012)
    A.glass.box(((xa + xb) / 2, yh + 0.0195, (za + zc) / 2), (xb - xa, 0.003, zc - za))
    A.obj(mirror=True)
    # work lamps on the rack's rear bar, facing back: a pocket each, two reflectors, a guard
    zr = ROOF + 0.085
    g, gg = Geo(), Geo()
    zc, x0, x2, ym = zr + 0.065, -1.355, -1.298, 0.40
    for (y0, y2), (z0, z2) in (((ym - 0.055, ym + 0.055), (zc - 0.04, zc - 0.028)),
                               ((ym - 0.055, ym + 0.055), (zc + 0.028, zc + 0.04)),
                               ((ym - 0.055, ym - 0.042), (zc - 0.028, zc + 0.028)),
                               ((ym + 0.042, ym + 0.055), (zc - 0.028, zc + 0.028))):
        g.box(((x0 + x2) / 2, (y0 + y2) / 2, (z0 + z2) / 2), (x2 - x0, y2 - y0, z2 - z0))
    g.box((x2 + 0.002, ym, zc), (0.004, 0.11, 0.08))
    g.box((-1.30, ym, (zr + zc - 0.04) / 2), (0.03, 0.03, zc - 0.04 - zr + 0.012))   # a stalk
    for y in (ym - 0.02, ym + 0.02):
        tube(gg, (x0 - 0.008, y, zc - 0.034), (x0 - 0.008, y, zc + 0.034), 0.003, 8)
    g.obj("work.lamps", "cladding", bevel=0.002, mirror=True)
    gg.obj("work.guards", "rim", mirror=True)
    W = K.Lamp("lamp.work", lit="lamp")
    for y in (ym - 0.02, ym + 0.02):
        W.reflector((x0 + 0.03, y, zc), (-1, 0, 0), r=0.019, depth=0.014)
    W.glass.box((x0 + 0.0075, ym, zc), (0.003, 0.084, 0.056))
    W.obj(mirror=True)
    # the stop lamp over the hatch: eight LEDs behind a red lens in a slim housing
    S = K.Lamp("lamp.stop", lit="led_rear", glass="lens_red")
    zs = ROOF + 0.017
    for (y0, y2), (z0, z2) in (((-0.24, 0.24), (ROOF - 0.02, zs - 0.0125)),
                               ((-0.24, 0.24), (zs + 0.0125, zs + 0.0225)),
                               ((-0.24, -0.22), (zs - 0.0125, zs + 0.0125)),
                               ((0.22, 0.24), (zs - 0.0125, zs + 0.0125))):
        S.housing.box((-1.405, (y0 + y2) / 2, (z0 + z2) / 2), (0.028, y2 - y0, z2 - z0))
    S.housing.box((-1.393, 0, zs), (0.004, 0.44, 0.025))
    S.leds((-1.403, -0.21, zs), (-1.403, 0.21, zs), 8, (-1, 0, 0), r=0.0105)
    S.glass.box((-1.4155, 0, zs), (0.003, 0.44, 0.025))
    S.obj()


# ---------------------------------------------------------------------------------------
# bumpers, winch, skids, steps
# ---------------------------------------------------------------------------------------
def build_bumpers():
    # front: a ram with a flat tip for the fairlead and swept, rising ends
    g = Geo()
    g.prism([(2.54, -0.18, 0.44), (2.54, 0.18, 0.44), (2.46, 0.60, 0.44), (2.34, 0.60, 0.44),
             (2.34, -0.60, 0.44), (2.46, -0.60, 0.44)], (0, 0, 0.20))
    for s in (1, -1):
        g.hexa([(2.46, s * 0.60, 0.44), (2.30, s * 1.05, 0.56), (2.22, s * 1.05, 0.56),
                (2.34, s * 0.60, 0.44), (2.46, s * 0.60, 0.64), (2.30, s * 1.05, 0.71),
                (2.22, s * 1.05, 0.71), (2.34, s * 0.60, 0.64)])
    g.obj("bumper.front", "paint2", bevel=0.007)
    g = Geo()
    g.box((2.543, 0, 0.54), (0.008, 0.28, 0.085))
    g.obj("winch.fairlead", "rim_bright", bevel=0.002)
    g = Geo()
    g.box((2.5475, 0, 0.54), (0.004, 0.20, 0.036))
    g.obj("winch.slot", "void")
    g = Geo()
    for z in (0.518, 0.562):
        tube(g, (2.55, -0.105, z), (2.55, 0.105, z), 0.011, 10)
    tube(g, (2.55, 0, 0.54), (2.565, 0.02, 0.525), 0.007, 8)
    g.obj("winch.rollers", "rim", bevel=0.001)
    g = Geo()                                           # hook and shackles, signal orange
    g.lathe([(-0.008, 0.022), (-0.008, 0.040), (0.008, 0.040), (0.008, 0.022)], 12, a0=rad(-200),
            a1=rad(60), xf=Matrix.Translation((2.585, 0.02, 0.495)) @ Matrix.Rotation(pi / 2, 4, 'Z'))
    for s in (1, -1):
        g.box((2.495, s * 0.40, 0.55), (0.06, 0.03, 0.075),
              rot=Matrix.Rotation(rad(s * 11), 3, 'Z'))
        ring(g, (2.522, s * 0.405, 0.515), rot=Matrix.Rotation(rad(s * 11), 4, 'Z'))
        g.box((-2.25, s * 0.33, 0.55), (0.05, 0.03, 0.07))
        ring(g, (-2.285, s * 0.33, 0.505))
    g.obj("hooks", "caliper", bevel=0.003)
    # skid plates under the nose and the tail, ribs on them
    g = Geo()
    g.prism([(2.42, -0.40, 0.50), (2.10, -0.40, 0.42), (1.22, -0.40, 0.42), (1.22, -0.40, 0.445),
             (2.10, -0.40, 0.445), (2.42, -0.40, 0.525)], (0, 0.80, 0))
    for y in (-0.28, -0.14, 0.0, 0.14, 0.28):
        g.prism([(2.38, y - 0.02, 0.475), (2.10, y - 0.02, 0.405), (1.36, y - 0.02, 0.405),
                 (1.36, y - 0.02, 0.425), (2.10, y - 0.02, 0.425), (2.38, y - 0.02, 0.495)],
                (0, 0.04, 0))
    g.prism([(-1.20, -0.40, 0.44), (-1.95, -0.40, 0.44), (-2.20, -0.40, 0.54), (-2.20, -0.40, 0.565),
             (-1.95, -0.40, 0.465), (-1.20, -0.40, 0.465)], (0, 0.80, 0))
    g.prism([(0.80, -0.30, 0.405), (-0.80, -0.30, 0.405), (-0.80, -0.30, 0.43),
             (0.80, -0.30, 0.43)], (0, 0.60, 0))        # the belly plate under the V
    g.obj("skid", "rim", bevel=0.003)
    # rear: a step beam with a hitch
    g = Geo()
    g.prism([(-2.12, -0.82, 0.46), (-2.12, 0.82, 0.46), (-2.21, 0.82, 0.46), (-2.27, 0.72, 0.46),
             (-2.27, -0.72, 0.46), (-2.21, -0.82, 0.46)], (0, 0, 0.16))
    g.box((-2.26, 0, 0.445), (0.10, 0.11, 0.09))
    g.obj("bumper.rear", "paint2", bevel=0.007)
    g = Geo()
    g.box((-2.312, 0, 0.445), (0.006, 0.062, 0.05))
    g.obj("hitch.hole", "void")
    g = Geo()
    for y in (0.58, -0.58):                             # step pads
        for k in range(7):
            g.box((-2.20, y - 0.12 + k * 0.04, 0.6215), (0.10, 0.014, 0.005))
    g.obj("step.pads", "rim_bright", bevel=0.001)


def build_steps():
    """A fold-down step under each door: a tread plate on two arms hinged at the sill."""
    g, gr, gh = Geo(), Geo(), Geo()
    for xc in (0.44, -0.44):
        g.box((xc, 0.995, 0.405), (0.56, 0.19, 0.028))
        g.box((xc, 1.085, 0.42), (0.56, 0.012, 0.055))          # a kick lip
        for dx in (-0.21, 0.21):
            tube(g, (xc + dx, 0.735, 0.60), (xc + dx, 0.93, 0.415), 0.022, 4, phase=pi / 4)
            gh.box((xc + dx, 0.735, 0.61), (0.07, 0.05, 0.06))
            tube(gh, (xc + dx - 0.045, 0.745, 0.60), (xc + dx + 0.045, 0.745, 0.60), 0.016, 8)
        for k in range(11):
            gr.box((xc - 0.25 + k * 0.05, 0.995, 0.4215), (0.014, 0.15, 0.005))
    g.obj("steps", "paint2", bevel=0.004, mirror=True)
    gh.obj("step.hinges", "cladding", bevel=0.003, mirror=True)
    gr.obj("step.ribs", "rim_bright", mirror=True)


# ---------------------------------------------------------------------------------------
# the face and the hood
# ---------------------------------------------------------------------------------------
def build_nose():
    g = Geo()                                           # the ribbed slab
    for z, hw in ((0.68, 0.37), (0.755, 0.40), (0.83, 0.40), (0.905, 0.40)):
        g.prism([(2.398, -hw, z - 0.028), (2.43, -hw, z - 0.013), (2.43, -hw, z + 0.013),
                 (2.398, -hw, z + 0.028)], (0, 2 * hw, 0))
    g.box((2.406, 0, 0.975), (0.016, 0.56, 0.062))
    g.obj("nose.ribs", "paint", bevel=0.004)
    g = Geo()
    for y in (0.25, -0.25):
        for z in (0.956, 0.994):
            bolt(g, (2.414, y, z), (1, 0, 0), 0.007, 0.004)
    g.obj("nose.bolts", "rim_bright")
    # hood: a bolted access plate, louvres by the cowl, two lifting eyes
    up = V3((-1, 0, HOOD_K)).normalized()
    nrm = V3((HOOD_K, 0, 1)).normalized()
    g = Geo()
    c = V3((1.84, 0, hood_z(1.84)))
    g.add([c + up * a + V3((0, b, 0)) + nrm * h for h in (0.0, 0.012)
           for a, b in ((-0.34, -0.30), (0.34, -0.30), (0.34, 0.30), (-0.34, 0.30))],
          [(0, 1, 2, 3), (4, 5, 6, 7), (0, 1, 5, 4), (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)])
    g.obj("hood.plate", "paint", bevel=0.004)
    g = Geo()
    for a, b in [(sa * 0.30, y) for sa in (-1, 1) for y in (-0.24, -0.08, 0.08, 0.24)] + \
                [(a, sb * 0.26) for a in (-0.12, 0.12) for sb in (-1, 1)]:
        bolt(g, c + up * a + V3((0, b, 0)) + nrm * 0.012, nrm, 0.009, 0.005)
    g.obj("hood.bolts", "rim_bright")
    g = Geo()
    for s in (1, -1):
        a = (1.58, s * 0.10, hood_z(1.58) + 0.003)
        b = (1.58, s * 0.40, hood_z(1.58) + 0.003)
        d = (1.38, s * 0.10, hood_z(1.38) + 0.003)
        cc = (1.38, s * 0.40, hood_z(1.38) + 0.003)
        g.louvers(a, b, cc, d, 7, 0.03, 0.006, rad(30), out=(HOOD_K, 0, 1), margin=0.03)
    g.obj("hood.louvres", "grille", bevel=0.0015)
    g = Geo()
    for x in (2.12, 1.46):
        p = V3((x, 0.395, hood_z(x)))
        g.box(p + nrm * 0.006, (0.07, 0.05, 0.012), rot=Matrix.Rotation(rad(-17), 3, 'Y'))
        ring(g, p + nrm * 0.035, 0.016, 0.028, 0.006, 12, rot=Matrix.Rotation(rad(-17), 4, 'Y'))
    g.obj("hood.eyes", "cladding", bevel=0.002, mirror=True)


# ---------------------------------------------------------------------------------------
# the citadel's sides, glass, hatch
# ---------------------------------------------------------------------------------------
def build_cab():
    # rub strips low on the doors, bar handles, hinges
    g = Geo()
    sec = [(-0.016, 0.0), (0.016, 0.0), (0.009, 0.014), (-0.009, 0.014)]
    for x0, x1 in ((0.80, 0.07), (-0.11, -0.77)):
        for z in (0.80, 0.865):
            y = side_y(z) - 0.002
            g.sweep([(x0, y, z), (x1, y, z)], sec, up=(0, 1, -0.33))
    g.obj("rubstrips", "cladding", bevel=0.002, mirror=True)
    g = Geo()
    for x in (0.15, -0.69):
        z = 1.10
        y = side_y(z)
        g.box((x, y + 0.035, z), (0.17, 0.022, 0.034))
        for dx in (-0.07, 0.07):
            g.box((x + dx, y + 0.014, z), (0.022, 0.03, 0.03))
    for x in (0.795, -0.035):
        for z in (0.86, 1.14, 1.32):
            y = side_y(z)
            g.box((x, y + 0.006, z), (0.06, 0.024, 0.085))
            tube(g, (x, y + 0.02, z - 0.05), (x, y + 0.02, z + 0.05), 0.011, 8)
    g.obj("door.hardware", "cladding", bevel=0.003, mirror=True)
    # camera pods where mirrors would be: a strut and a faceted pod with a lens
    g = Geo()
    tube(g, (0.74, 0.80, 1.36), (0.76, 0.99, 1.43), 0.013, 4, phase=pi / 4)
    g.hexa([(0.83, 0.96, 1.40), (0.83, 1.04, 1.40), (0.70, 1.035, 1.415), (0.70, 0.965, 1.415),
            (0.83, 0.96, 1.46), (0.83, 1.04, 1.46), (0.70, 1.035, 1.475), (0.70, 0.965, 1.475)])
    g.obj("campods", "cladding", bevel=0.004, mirror=True)
    g = Geo()
    g.box((0.698, 1.0, 1.445), (0.004, 0.05, 0.04))
    g.obj("campod.lens", "gloss_black", mirror=True)
    g = Geo()
    g.box((0.832, 1.0, 1.43), (0.004, 0.05, 0.012))
    g.obj("led.campod", "led_accent", mirror=True)
    # armor louvres over the rear doors' windows, on a frame
    g = Geo()
    y0, y1 = side_y(W_Z) + 0.035, side_y(H_Z) + 0.035
    g.louvers((-0.13, y0, W_Z + 0.03), (-0.13, y1, H_Z - 0.03), (-0.57, y1, H_Z - 0.03),
              (-0.57, y0, W_Z + 0.03), 4, 0.075, 0.010, rad(-38), out=(0, 1, 0.3), margin=0.02)
    for x in (-0.115, -0.585):
        g.hexa([(x - 0.014, y0 - 0.04, W_Z + 0.005), (x + 0.014, y0 - 0.04, W_Z + 0.005),
                (x + 0.014, y0 + 0.03, W_Z + 0.005), (x - 0.014, y0 + 0.03, W_Z + 0.005),
                (x - 0.014, y1 - 0.04, H_Z - 0.005), (x + 0.014, y1 - 0.04, H_Z - 0.005),
                (x + 0.014, y1 + 0.03, H_Z - 0.005), (x - 0.014, y1 + 0.03, H_Z - 0.005)])
    g.obj("shutters", "paint2", bevel=0.003, mirror=True)
    # the sensor band on the tail: lit cells behind dark glass, a lens
    g = Geo()
    for k in range(7):
        x = -1.07 - k * 0.04
        loc, n = on_body(x, 1.57, 'y')
        if loc is not None:
            g.box(loc + n * 0.003, (0.012, 0.006, 0.16 - 0.03 * (k % 2)))
    g.obj("led.sensor", "sensor", mirror=True)
    g = Geo()
    loc, n = on_body(-1.34, 1.52, 'y')
    stud(g, loc, n, [(-0.001, 0.001), (-0.001, 0.04), (0.012, 0.04), (0.018, 0.03), (0.018, 0.001)], 16)
    g.obj("sensor.lens", "cladding", bevel=0.002, mirror=True)
    g = Geo()
    stud(g, loc + n * 0.018, n, [(0.0, 0.001), (0.0, 0.024), (0.002, 0.024), (0.002, 0.001)], 16)
    g.obj("sensor.eye", "gloss_black", mirror=True)
    # the charge ports' flaps are cut through the nose sides (cutters()): a hinge on each
    # flap's top edge, a touch pad by each front door's handle
    g = Geo()
    x, z, r = PORT
    zh = z + r * cos(rad(22.5)) - 0.008
    tube(g, (x - 0.028, 0.585, zh), (x + 0.028, 0.585, zh), 0.0055, 8)
    g.obj("port.hinges", "cladding", bevel=0.001, mirror=True)
    g = Geo()
    g.box((0.30, side_y(1.10) + 0.004, 1.10), (0.05, 0.008, 0.075),
          rot=Matrix.Rotation(rad(-16), 3, 'X'))
    g.obj("door.pad", "gloss_black", bevel=0.002, mirror=True)
    g = Geo()
    g.box((0.30, side_y(1.115) + 0.009, 1.115), (0.03, 0.003, 0.012),
          rot=Matrix.Rotation(rad(-16), 3, 'X'))
    g.obj("led.pad", "sensor", mirror=True)
    # wipers at rest on the glass, both parked to the left (the kit's wiper)
    g, gr = Geo(), Geo()
    for y0 in (0.03, -0.37):
        piv = on_body(y0 + 0.01, 1.505, 'x')[0]
        a, b = on_body(y0, 1.525, 'x')[0], on_body(y0 + 0.34, 1.715, 'x')[0]
        if piv is not None and a is not None and b is not None:
            K.wiper(g, gr, piv, a, b)
    gr.obj("wiper.blades", "rubber")
    g.obj("wipers", "cladding", bevel=0.001)


def build_hatch():
    # armor louvres over the hatch glass, hinges on the roof's rear edge, a handle
    g = Geo()
    lift = V3((-0.616, 0, 0.788)) * 0.04
    a = V3((-1.50, -0.36, hatch_z(-1.50))) + lift
    b = V3((-1.95, -0.36, hatch_z(-1.95))) + lift
    d = V3((-1.50, 0.36, hatch_z(-1.50))) + lift
    c = V3((-1.95, 0.36, hatch_z(-1.95))) + lift
    g.louvers(a, b, c, d, 5, 0.07, 0.010, rad(-35), out=(-0.6, 0, 0.8), margin=0.02)
    for y in (-0.375, 0.375):
        tube(g, (-1.46, y, hatch_z(-1.46) + 0.02), (-1.99, y, hatch_z(-1.99) + 0.02), 0.018, 4,
             phase=pi / 4)
    g.obj("hatch.louvres", "paint2", bevel=0.003)
    g = Geo()
    for y in (0.30, -0.30):
        g.box((-1.40, y, ROOF + 0.006), (0.10, 0.07, 0.016))
        tube(g, (-1.42, y - 0.045, ROOF + 0.012), (-1.42, y + 0.045, ROOF + 0.012), 0.014, 8)
    g.obj("hatch.hinges", "cladding", bevel=0.003)


# ---------------------------------------------------------------------------------------
# the roof: rack rails, a drone on its pad, a case, a folding sensor mast
# ---------------------------------------------------------------------------------------
def build_roof():
    zr = ROOF + 0.085
    g = Geo()
    tube(g, (0.30, 0.44, zr), (-1.30, 0.44, zr), 0.018, 10)
    for x in (0.22, -0.28, -0.80, -1.24):
        tube(g, (x, 0.44, ROOF - 0.004), (x, 0.44, zr), 0.014, 8)
        g.box((x, 0.44, ROOF + 0.005), (0.08, 0.05, 0.012))
    g.obj("rack.rails", "cladding", bevel=0.002, mirror=True)
    g = Geo()
    for x in (0.30, -1.30):
        tube(g, (x, -0.44, zr), (x, 0.44, zr), 0.018, 10)
    g.obj("rack.bars", "cladding", bevel=0.002)
    # the drone's pad: an octagon bolted to the roof, a ring to land on
    pc = V3((-0.24, 0, ROOF))
    g = Geo()
    oct_ = [(pc.x + 0.37 * cos(rad(22.5 + 45 * k)), 0.37 * sin(rad(22.5 + 45 * k)), ROOF - 0.002)
            for k in range(8)]
    g.prism(oct_, (0, 0, 0.016))
    g.obj("drone.pad", "paint2", bevel=0.004)
    g = Geo()
    g.lathe([(0.0, 0.25), (0.0, 0.275), (0.002, 0.275), (0.002, 0.25)], 40,
            xf=Matrix.Translation(pc + V3((0, 0, 0.0145))) @ Matrix.Rotation(pi / 2, 4, 'X'))
    for k in range(4):
        R = Matrix.Rotation(rad(45 + 90 * k), 3, 'Z')
        g.box(pc + R @ V3((0.31, 0, 0.0152)), (0.07, 0.022, 0.002), rot=R)
    g.obj("drone.padmark", "hazard")
    g = Geo()
    for k in range(8):
        a = rad(45 * k)
        bolt(g, pc + V3((0.335 * cos(a), 0.335 * sin(a), 0.014)), (0, 0, 1), 0.008, 0.005)
    g.obj("drone.padbolts", "rim_bright")
    # the drone: a faceted body, four arms, ducted rotors
    zb = ROOF + 0.075
    g, gd, gk = Geo(), Geo(), Geo()
    g.hexa([(pc.x - 0.15, -0.06, zb - 0.03), (pc.x + 0.13, -0.05, zb - 0.03),
            (pc.x + 0.13, 0.05, zb - 0.03), (pc.x - 0.15, 0.06, zb - 0.03),
            (pc.x - 0.13, -0.075, zb + 0.03), (pc.x + 0.17, -0.055, zb + 0.022),
            (pc.x + 0.17, 0.055, zb + 0.022), (pc.x - 0.13, 0.075, zb + 0.03)])
    for sx in (1, -1):
        for sy in (1, -1):
            rc = V3((pc.x + sx * 0.215, sy * 0.215, zb + 0.012))
            tube(gd, (pc.x + sx * 0.09, sy * 0.05, zb + 0.005), rc, 0.011, 6)
            gd.lathe([(-0.02, 0.112), (-0.02, 0.128), (0.02, 0.128), (0.02, 0.112)], 24,
                     xf=Matrix.Translation(rc) @ Matrix.Rotation(pi / 2, 4, 'X'))
            zcyl(gd, rc - V3((0, 0, 0.022)), 0.022, 0.044, 10)
            R = Matrix.Rotation(rad(30 + 50 * sx * sy), 3, 'Z')
            gk.box(rc + V3((0, 0, 0.024)), (0.215, 0.022, 0.004), rot=R)
            zcyl(gd, rc - V3((0.0, 0, 0.062)), 0.008, 0.04, 6)          # a leg
    g.obj("drone.body", "drone", bevel=0.004)
    gd.obj("drone.frame", "cladding", bevel=0.0015)
    gk.obj("drone.blades", "rim_bright")
    g = Geo()
    g.box((pc.x + 0.172, 0, zb - 0.002), (0.004, 0.07, 0.022))
    g.obj("drone.eye", "gloss_black")
    g = Geo()
    g.box((pc.x - 0.152, 0, zb), (0.004, 0.06, 0.012))
    g.box((pc.x, 0, zb + 0.0305), (0.07, 0.012, 0.002))
    g.obj("led.drone", "led_accent")
    # an equipment case strapped across the rails
    g = Geo()
    g.box((-0.92, 0, ROOF + 0.10), (0.36, 0.70, 0.17))
    for y in (-0.24, -0.08, 0.08, 0.24):
        g.box((-0.92, y, ROOF + 0.19), (0.30, 0.05, 0.012))
    g.obj("case", "paint2", bevel=0.008)
    g = Geo()
    for y in (-0.30, 0.30):
        g.box((-0.92, y, ROOF + 0.105), (0.372, 0.04, 0.182))
    g.obj("case.straps", "hazard", bevel=0.001)
    g = Geo()
    for y in (-0.16, 0.16):
        g.box((-0.737, y, ROOF + 0.13), (0.01, 0.06, 0.035))
    g.obj("case.latches", "rim_bright", bevel=0.002)
    # the sensor mast: a turret, two arms folded to a Z, a head with a lens and a dish
    y = 0.27
    base = V3((-1.22, y, ROOF))
    elbow = V3((-1.36, y, ROOF + 0.20))
    head = V3((-1.14, y, ROOF + 0.29))
    g = Geo()
    zcyl(g, base, 0.075, 0.03, 12)
    zcyl(g, base + V3((0, 0, 0.03)), 0.05, 0.04, 12, r2=0.035)
    tube(g, base + V3((0, 0, 0.06)), elbow, 0.022, 4, phase=pi / 4)
    tube(g, elbow, head, 0.018, 4, phase=pi / 4)
    for p in (base + V3((0, 0, 0.07)), elbow, head):
        tube(g, p - V3((0, 0.035, 0)), p + V3((0, 0.035, 0)), 0.03, 10)
    tube(g, base + V3((-0.03, 0.03, 0.05)), elbow + V3((0.02, 0.03, -0.05)), 0.008, 6)   # a ram
    g.hexa([(head.x - 0.07, y - 0.055, head.z + 0.01), (head.x + 0.09, y - 0.045, head.z + 0.01),
            (head.x + 0.09, y + 0.045, head.z + 0.01), (head.x - 0.07, y + 0.055, head.z + 0.01),
            (head.x - 0.07, y - 0.055, head.z + 0.10), (head.x + 0.07, y - 0.045, head.z + 0.10),
            (head.x + 0.07, y + 0.045, head.z + 0.10), (head.x - 0.07, y + 0.055, head.z + 0.10)])
    g.lathe([(-0.004, 0.002), (-0.004, 0.022), (0.014, 0.042), (0.018, 0.042), (0.002, 0.02),
             (0.002, 0.002)], 14,
            xf=Matrix.Translation((head.x - 0.02, y, head.z + 0.115)) @ Matrix.Rotation(rad(25), 4, 'X'))
    tube(g, (-1.18, -0.36, ROOF), (-1.24, -0.36, ROOF + 0.26), 0.006, 6, r2=0.003)   # a whip
    g.box((-1.18, -0.36, ROOF + 0.008), (0.06, 0.06, 0.02))
    g.obj("mast", "cladding", bevel=0.003)
    g = Geo()
    g.box((head.x + 0.086, y, head.z + 0.055), (0.004, 0.07, 0.05))
    g.obj("mast.eye", "gloss_black")
    g = Geo()
    g.box((head.x + 0.088, y, head.z + 0.092), (0.004, 0.05, 0.008))
    g.obj("led.mast", "sensor")
    # roof ribs ahead of the pad
    g = Geo()
    sec = [(-0.03, 0.0), (0.03, 0.0), (0.018, 0.012), (-0.018, 0.012)]
    for yy in (-0.30, -0.15, 0.0, 0.15, 0.30):
        g.sweep([(0.40, yy, ROOF - 0.002), (0.18, yy, ROOF - 0.002)], sec, up=(0, 0, 1))
    g.obj("roof.ribs", "paint", bevel=0.003)


# ---------------------------------------------------------------------------------------
# bolts and lettering
# ---------------------------------------------------------------------------------------
def build_bolts():
    """Rows of bolt heads on the body as built."""
    def row(pts, proj):
        for u, v in pts:
            loc, n = on_body(u, v, proj)
            if loc is not None:
                bolt(BOLTS, loc, n)
    row([(2.20 - k * 0.15, 0.415) for k in range(7)], 'z')              # hood edges
    row([(2.22, 0.07 + k * 0.14) for k in range(3)], 'z')
    row([(2.20 - k * 0.15, hood_z(2.20 - k * 0.15) - 0.17) for k in range(7)], 'y')   # nose side
    row([(0.42 - k * 0.20, 0.52) for k in range(10)], 'z')               # roof plate
    row([(-1.33, 0.07 + k * 0.13) for k in range(3)], 'z')
    row([(0.78 - k * 0.15, 0.755) for k in range(11)], 'y')              # the doors' foot
    row([(0.78 - k * 0.15, BELT + 0.03) for k in range(11)], 'y')        # over the belt
    row([(0.52 - k * 0.12, W_Z - 0.04) for k in range(4)], 'y')          # under the windows
    row([(-0.10 - k * 0.12, W_Z - 0.04) for k in range(5)], 'y')
    row([(0.84 - 0.08 * k, 1.455 + 0.055 * k) for k in range(4)], 'y')   # the pillar gusset
    row([(-0.02, 1.46 + k * 0.08) for k in range(4)], 'y')               # B pillar
    row([(-0.71, 1.46 + k * 0.08) for k in range(4)], 'y')               # C pillar
    row([(-1.05 - k * 0.14, BELT + 0.20) for k in range(7)], 'y')        # tail plate
    row([(-1.50 - k * 0.13, hatch_z(-1.50 - k * 0.13) - 0.20) for k in range(4)], 'y')
    row([(-2.08, 0.80 + k * 0.10) for k in range(3)], 'y')
    row([(0.44, 0.74 + k * 0.105) for k in range(5)], 'X')               # hatch edges
    BOLTS.obj("bolts", "rim_bright", mirror=True)


def build_lettering():
    g = Geo()                               # light stencils on the paint
    up = V3((-1, 0, HOOD_K))
    for side in (1, -1):
        stencil(g, NUM, 0.27, on_side(0.47, 1.215, side))
        stencil(g, "BASTION", 0.10, on_side(-0.34, 1.27, side))
        stencil(g, "BRAKK INDUSTRIAL", 0.032, on_side(-0.34, 1.175, side), gap=0.2, cut=0)
        stencil(g, "GVW 5200 KG", 0.025, on_side(-0.34, 1.13, side), gap=0.2, cut=0)
        stencil(g, "B-" + NUM, 0.15, on_side(-1.49, 1.33, side))
    stencil(g, NUM, 0.36, on_plane(V3((1.84, 0, hood_z(1.84))) + V3((HOOD_K, 0, 1)) * 0.0125,
                                   (0, 1, 0), up))
    for s_ in (1, -1):
        stencil(g, "HV 800V", 0.03, on_plane((1.30, s_ * 0.5812, 1.17), (-s_, 0, 0), (0, 0, 1)),
                gap=0.2, cut=0)
    g.obj("lettering", "decal")
    g = Geo()                               # on the dark parts
    stencil(g, "BRAKK", 0.058, on_plane((2.4145, 0, 0.975), (0, 1, 0), (0, 0, 1)), gap=0.2)
    stencil(g, "WINCH 6T", 0.028, on_plane((2.5405, 0, 0.61), (0, 1, 0), (0, 0, 1)),
            gap=0.2, cut=0)
    stencil(g, "BK 7-4108", 0.05, on_plane((-2.2705, 0, 0.575), (0, -1, 0), (0, 0, 1)),
            gap=0.18, cut=0)
    upf = V3((-0.20, 0, 0.25)).normalized()
    for s in (1, -1):                       # the unit number on the front fender slopes
        stencil(g, NUM, 0.17, on_plane(V3((2.05, s * 0.85, 0.945)) + V3((0.78, 0, 0.625)) * 0.001,
                                       (0, 1, 0), upf))
    g.obj("markings", "mark")
    g = Geo()                               # hazard stripes on the bumpers
    for s in (1, -1):
        d = V3((-0.16, s * 0.45, 0)).normalized()
        chevrons(g, on_plane((2.38, s * 0.825, 0.605), d * s, (0, 0, 1)), 0.42, 0.07, 5, s * 0.05)
        chevrons(g, on_plane((-2.2705, s * 0.565, 0.54), (0, -1, 0), (0, 0, 1)), 0.27, 0.10, 4,
                 -s * 0.07)
    g.obj("chevrons", "hazard")


# ---------------------------------------------------------------------------------------
# suspension: double wishbones at every corner, no axles (the motors are in the hubs)
# ---------------------------------------------------------------------------------------
def build_chassis():
    g, gs, gc = Geo(), Geo(), Geo()
    yo = T_OUT - T_W - 0.085                # the motor's inner face
    for x, f in ((FA_X, 1), (RA_X, -1)):
        for xi in (x - 0.20, x + 0.20):
            tube(g, (xi, 0.34, 0.50), (x, yo - 0.01, 0.31), 0.026, 4, phase=pi / 4)
            tube(g, (xi - 0.03 * (1 if xi < x else -1), 0.50, 0.84), (x, yo - 0.02, 0.655), 0.021,
                 4, phase=pi / 4)
        g.box((x, yo - 0.015, 0.48), (0.11, 0.05, 0.40))
        tube(g, (x + f * 0.17, 0.40, 0.60), (x + f * 0.16, yo - 0.01, 0.53), 0.012)      # tie rod
        coil(g, gs, (x - f * 0.13, 0.615, 0.37), (x - f * 0.10, 0.60, 1.0))
        g.box((x, 0, 0.50), (0.56, 0.74, 0.10))             # the subframe
        # the motor's cable: out of the hull, a loop, into the motor's gland
        pts = [V3((x + f * 0.10, 0.52, 0.80)), V3((x + f * 0.12, 0.62, 0.78)),
               V3((x + f * 0.13, 0.66, 0.70)), V3((x + f * 0.10, yo + 0.02, 0.62))]
        for a, b in zip(pts, pts[1:]):
            tube(gc, a, b, 0.013, 8)
    g.obj("chassis", "rim", bevel=0.003, mirror=True)
    gs.obj("springs", "caliper", bevel=0.004, mirror=True)
    gc.obj("cables", "cable", bevel=0.003, mirror=True)


# ---------------------------------------------------------------------------------------
# wheels: the Brakk wheel (a lugged tire on a dished steel rim with a bolted bead ring),
# here with a finned hub motor behind it and its copper showing through the dish's windows
# ---------------------------------------------------------------------------------------
def build_spare():
    """The spare on a swing arm: hinged on the right tail corner, latched on the left."""
    build_wheel("spare", 0, 1, loc=(SPARE_X, 0, SPARE_Z), yaw=pi / 2, motor=False)
    xh = TAIL_X - 0.035
    g = Geo()
    tube(g, (xh, -0.47, 0.76), (xh, -0.47, 1.22), 0.022, 10)                    # the hinge post
    for z in (0.80, 1.18):
        g.box((TAIL_X - 0.012, -0.47, z), (0.03, 0.09, 0.07))
    tube(g, (xh, -0.47, 1.17), (xh - 0.01, 0.10, SPARE_Z + 0.06), 0.022, 4, phase=pi / 4)
    tube(g, (xh, -0.47, 0.81), (xh - 0.01, 0.10, SPARE_Z - 0.06), 0.022, 4, phase=pi / 4)
    tube(g, (xh - 0.01, 0.10, SPARE_Z), (xh, 0.47, SPARE_Z), 0.022, 4, phase=pi / 4)
    g.box((xh - 0.012, 0.02, SPARE_Z), (0.02, 0.26, 0.26))                     # the carrier
    g.box((TAIL_X - 0.012, 0.47, SPARE_Z), (0.03, 0.07, 0.09))                 # the latch
    tube(g, (xh - 0.02, 0.47, SPARE_Z), (xh - 0.09, 0.47, SPARE_Z - 0.06), 0.009, 6)
    g.obj("spare.arm", "paint2", bevel=0.004)
    g = Geo()                                   # the nut plate over the spare's hub
    xo = SPARE_X - T_W / 2 + 0.075
    g.lathe([(0.0, 0.002), (0.0, 0.05), (0.014, 0.05), (0.022, 0.03), (0.022, 0.002)], 6,
            xf=Matrix.Translation((xo, 0, SPARE_Z)) @ Matrix.Rotation(pi / 2, 4, 'Z'))
    g.obj("spare.nut", "caliper", bevel=0.002)


# ---------------------------------------------------------------------------------------
# interior
# ---------------------------------------------------------------------------------------
CFLOOR = 0.62                       # the floor's top over the V hull
CAB_X0, CAB_X1 = -1.99, 1.24        # a wall inside the tail plate, the firewall just behind the
#                                     windshield's base (ahead of it the fill reached over the cowl)


def cab_zone(label, p, n):
    """The lining's material: rubber up the footwells, the cowl and the pillars' feet in the
    dash's hard trim under the raked windshield, the walls in the grey spall liner (the
    headliner's) from the slit windows' sills up, the hard trim under them."""
    if label == "fill":
        return "interior.carpet"
    if p is None or n is None or label in ("floor", "fire", "rear", "well"):
        return None
    if p.x > 0.85 and p.z < 1.02:
        return "interior.carpet"
    if p.x > 0.95 and p.z < 1.52:
        return "interior"
    return "interior.head" if p.z > 1.37 else "interior"


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


def slit_frame(P, xc, hw, depth=0.075, flange=0.045, back=0.02, bolts=5):
    """A thick frame round a slit window of the citadel's leaning side (its glass inset
    0.05 in its panel): a sleeve from the glass's visible edge (hw: half its length, xc its
    middle) in square to the glass, a flange of flange round it at depth, its outer face
    back to back inside the glass's plane (sunk into the lining), bolt heads on the
    flange. The left side; the hardware is mirrored."""
    ya, yb = side_y(W_Z), 0.68
    up = V3((0, yb - ya, H_Z - W_Z))
    hh = up.length / 2 - 0.046
    up.normalize()
    n = V3((0, -up.z, up.y))                    # square to the glass, into the cabin
    c = V3((xc, (ya + yb) / 2, (W_Z + H_Z) / 2))
    u = V3((1, 0, 0))

    def ring(a, b, d):
        return [c + u * (sa * a) + up * (sb * b) + n * d
                for sa, sb in ((1, 1), (-1, 1), (-1, -1), (1, -1))]
    R = [ring(hw, hh, 0.004), ring(hw, hh, depth), ring(hw + flange, hh + flange, depth),
         ring(hw + flange, hh + flange, back), ring(hw + 0.006, hh + 0.006, 0.004)]
    vs = [p for r in R for p in r]
    fs = [(i * 4 + j, i * 4 + (j + 1) % 4, ((i + 1) % 5) * 4 + (j + 1) % 4, ((i + 1) % 5) * 4 + j)
          for i in range(5) for j in range(4)]
    P["interior"].add(vs, fs)
    a, b = hw + flange / 2, hh + flange / 2     # bolt heads round the flange
    pts = [(-a + 2 * a * k / (bolts - 1), sb * b) for k in range(bolts) for sb in (-1, 1)]
    pts += [(sa * a, 0.0) for sa in (-1, 1)]
    for x, y in pts:
        bolt(P["interior.metal"], c + u * x + up * y + n * depth, n, 0.0065, 0.003)


def screen_frame(P, depth=0.06, flange=0.07, back=0.02):
    """The windshield's frame from inside, as the slit windows': a sleeve from the glass's
    visible edge (its 0.055 frame in) square into the cabin, a flange round it, its outer
    face back inside the glass's plane; up the corner facet's side from the dash and across
    the header to the middle (the left half; mirrored). Bolt heads on the flange."""
    nc = V3((-0.5, 0, -1)).normalized()                 # the middle facet, into the cabin
    nk = V3((-0.427, -0.507, -0.749)).normalized()      # the corner facet
    path = [V3((0.93, 0.70, 1.52)), V3((0.628, 0.642, 1.728)), V3((0.71, 0.525, 1.765)),
            V3((0.709, 0.0, 1.765))]
    ns = [nk, nk, (nk + nc).normalized(), nc]
    mid = V3((0.96, 0.0, 1.62))
    outs = []                                           # each stretch's outward direction
    for i in range(len(path) - 1):
        t = (path[i + 1] - path[i]).normalized()
        o = t.cross((ns[i] + ns[i + 1]).normalized())
        if o.dot((path[i] + path[i + 1]) / 2 - mid) < 0:
            o = -o
        outs.append(o.normalized())
    offs = [outs[0]]
    for o1, o2 in zip(outs, outs[1:]):                  # mitred
        s_ = o1 + o2
        offs.append(s_ * (2.0 / s_.length_squared))
    offs.append(outs[-1])
    sec = [(0.0, 0.004), (0.0, depth), (flange, depth), (flange, back), (0.006, 0.004)]
    m = len(sec)
    vs = [p + o * a + n * d for p, o, n in zip(path, offs, ns) for a, d in sec]
    fs = [(i * m + j, i * m + (j + 1) % m, (i + 1) * m + (j + 1) % m, (i + 1) * m + j)
          for i in range(len(path) - 1) for j in range(m)]
    fs.append(tuple(reversed(range(m))))                # the foot's cap, in the dash
    P["interior"].add(vs, fs)
    for i in range(len(path) - 1):
        L = (path[i + 1] - path[i]).length
        k = max(1, int(L / 0.12))
        for q in range(k):
            t = (q + 0.5) / k
            p = path[i].lerp(path[i + 1], t)
            o = offs[i].lerp(offs[i + 1], t)
            n = ns[i].lerp(ns[i + 1], t).normalized()
            bolt(P["interior.metal"], p + o * (flange * 0.55) + n * depth, n, 0.0065, 0.003)


def rack_box(P, c, size, mat="interior", face=None, lit=None, knobs=0):
    """A box of comms gear or a case on a rack: c its middle, size; face: the way its front
    looks (a unit x or y vector), with a lit strip and knobs on it."""
    c = V3(c)
    P[mat].box(c, size)
    if face is None:
        return
    f = V3(face)
    half = abs(f.x) * size[0] / 2 + abs(f.y) * size[1] / 2
    side = V3((-f.y, f.x, 0))
    wide = abs(f.x) * size[1] + abs(f.y) * size[0]
    front = c + f * (half + 0.0012)
    if lit:
        P[lit].box(front + side * (-wide * 0.18) + V3((0, 0, size[2] * 0.18)),
                   (0.002 + abs(f.y) * wide * 0.4, 0.002 + abs(f.x) * wide * 0.4, size[2] * 0.22))
    for k in range(knobs):
        q = front + side * (wide * (0.12 + 0.13 * k)) + V3((0, 0, -size[2] * 0.12))
        P["interior.metal"].cyl(q, 0.016, 0.011, 12, axis=tuple(f))


def build_interior():
    """The citadel (vehicles/cabin.py), an armored car's: lined in a grey spall liner from the
    cowl to the tail, every window in a thick bolted steel frame (slit_frame, screen_frame),
    a ribbed rubber floor, four upright seats in brown work vinyl with belts, a hard black
    dash with a small map screen and the gauge hood, a four-spoke wheel, louvred kick
    panels, the console with the lever, door cards of bolted steel, grab bars along the
    roof and up the pillars, an overhead switch and radio console, a round roof hatch with
    its handwheel over the rear seats (under the drone pad), and behind them the bay under
    the glass hatch: an equipment rack of cases on the left, a comms rack of radios on the
    right, tie-down rails, a power panel on the rear wall, a fire extinguisher; the
    interior views cab_*."""
    C.materials(carpet=(0.030, 0.031, 0.034), head=(0.22, 0.225, 0.23), soft=(0.04, 0.042, 0.046),
                trim=(0.006, 0.045, 0.24), trim_metal=0.0, trim_rough=0.45,
                metal=(0.46, 0.47, 0.48), accent=(0.05, 0.03, 0.015),
                piping=(0.95, 0.36, 0.01), belt=(0.30, 0.31, 0.12), mat=(0.016, 0.016, 0.018),
                ambient=(0.15, 0.85, 1.0), ambient_strength=3.0)
    sb = next(n for n in K.MAT["seat"].node_tree.nodes if n.type == 'BSDF_PRINCIPLED')
    sb.inputs["Roughness"].default_value = 0.74             # a work vinyl, not a gloss
    sb.inputs["Specular IOR Level"].default_value = 0.3
    # the spine on to 20 cm of each end (the Hauler's finding: with a pole near the
    # windshield's base its sides were met by grazing rays and tore), a 30 mm grid
    cab = C.Cabin(CAB_X0, CAB_X1, CFLOOR, style="brakk", cap=0.20)
    cab.step = 0.03
    lin = cab.lining(smooth=5, zone=cab_zone, wall="interior.head", belt=W_Z,
                     reveal="interior")      # the reveals dark inside the slit frames
    for v in lin.data.vertices:         # held under the cowl, which the windshield's base meets
        if v.co.x > 1.10 and v.co.z > 1.25:
            v.co = cab.keep(v.co, margin=0.03, wells=False)
    import bmesh                        # a sliver of the cowl's lining stood up as a spike in
    bm = bmesh.new()                    # the footwells (the firewall's plane right behind the
    bm.from_mesh(lin.data)              # windshield's base): nothing of it belongs there
    bmesh.ops.delete(bm, geom=[f for f in bm.faces if (lambda c: 0.55 < c.x < CAB_X1 - 0.03
                     and abs(c.y) < 0.50 and CFLOOR + 0.01 < c.z < 1.05)(f.calc_center_median())],
                     context='FACES')
    bmesh.ops.delete(bm, geom=[v for v in bm.verts if not v.link_faces], context='VERTS')
    bm.to_mesh(lin.data)
    bm.free()
    for y in (0.40, -0.40):
        cab.seat((0.14, y, CFLOOR + 0.38), driver=y > 0, rake=16, back=0.62, bolster=0.6,
                 headrest="post")
        cab.seat((-0.68, y, CFLOOR + 0.38), rake=16, back=0.60, bolster=0.6, width=0.48,
                 headrest="post")
    d = cab.dash(depth=0.42, fascia=0.14, knee=0.12)
    cab.cluster()
    cab.screen(graphics="map")
    cab.wheel(tilt=34, r=0.19)
    cab.pedals()
    cab.console(w=0.24, h=0.26, cups=1, switches=6)
    cab.door(0.08, 0.80, tag="door_f", sill_text="BASTION", pull="bar", speaker=False,
             card="interior.metal", upper="interior")
    cab.door(-0.76, -0.10, tag="door_r", sill=False, pull="bar", speaker=False,
             card="interior.metal", upper="interior")
    cab.roof_kit(grab_x=[0.14, -0.68], dome_x=-1.30, visors=False)   # the dome over the bay;
    #                                    no visors: the slit glass needs none
    cab.mats()
    P = C._Parts()
    # bolts round the door cards' steel, grab bars up the A pillars and on the B pillars,
    # thick frames round the slit windows' reveals
    for xa, xb in ((0.08, 0.80), (-0.76, -0.10)):
        z0, z1 = CFLOOR + 0.07, cab.belt - 0.05
        wall_bolts(P["interior.gloss"], cab, [(xa + 0.05 + (xb - xa - 0.10) * k / 5, z)
                                              for k in range(6) for z in (z0, z1)], 0.016)
    wall_bar(P, cab, (0.98, 1.10), (0.70, 1.62), off=0.05)
    wall_bar(P, cab, (-0.09, 0.98), (-0.09, 1.46), off=0.05)
    # the slit windows in thick frames: a bolted steel box round each, its sleeve down to
    # the glass (the lining's reveals inside it unseen), sunk into the wall round it
    for xa, xb in ((0.56, 0.04), (-0.08, -0.62)):
        slit_frame(P, (xa + xb) / 2, (xa - xb) / 2 - 0.046)
    # a kick panel in each footwell over the fender plate's inner flange (it stands 6 cm
    # through the hull's side there), louvred
    zk = (CFLOOR + 0.95) / 2
    Q = C._Parts()
    Q["interior"].box((1.11, 0.595, zk), (0.22, 0.10, 0.95 - CFLOOR))
    for k in range(5):
        Q["interior.gloss"].box((1.11, 0.5435, zk + 0.06 + 0.035 * (k - 2)), (0.15, 0.003, 0.012))
    for g in Q.g.values():              # held 2 cm in: the hull's side tucks in under it
        g.v = [cab.keep(p, margin=0.02) for p in g.v]
    cab._emit("kick", Q, mirror=True)
    # the windshield in the same steel: up its sides and across its header
    screen_frame(P)
    cab._emit("hardware", P, mirror=True)
    roof_console(cab, -0.12, 0.14, 0.40, deep=0.08, text="NET 4")   # over the seats' backs
    # the roof hatch over the rear seats: a ring, the lid's underside, a handwheel, latches
    P = C._Parts()
    xc = -0.52
    p, n = cab.roof(xc, 0.0)
    for k in range(3):
        P[("interior.metal", "interior", "interior.gloss")[k]].ring(
            p + V3((0, 0, (-0.012, -0.004, -0.024)[k])), 'z', (0.33, 0.30, 0.20)[k],
            sec=((0.03, 0.03), (0.012, 0.012), (0.012, 0.012))[k], n=32)
    P["interior.metal"].ring(p + V3((0, 0, -0.07)), 'z', 0.11, r=0.009, n=24, m=6)
    for k in range(3):
        a = 2 * pi * k / 3
        P["interior.metal"].tube(p + V3((0, 0, -0.03)), p + V3((0.11 * cos(a), 0.11 * sin(a), -0.07)),
                                 0.006, 6)
    for k in range(4):
        a = 2 * pi * (k + 0.5) / 4
        P["seat.red"].box(p + V3((0.30 * cos(a), 0.30 * sin(a), -0.028)), (0.035, 0.03, 0.014),
                          rot=Matrix.Rotation(a, 3, 'Z'))
    cab._emit("roofhatch", P)
    # the bay behind the rear seats: tie-down rails, the racks, the extinguisher
    P = C._Parts()
    xa, xb = -1.94, -1.10
    for y in (0.22, -0.22):
        P["interior.metal"].box(((xa + xb) / 2, y, CFLOOR + 0.006), (xb - xa, 0.03, 0.012))
    for s, kind in ((1, "cases"), (-1, "comms")):
        yw = min(cab.half(x, 1.05) for x in (xa, xb)) - 0.01
        yi = yw - 0.34
        posts = [(x, y) for x in (xa + 0.03, xb - 0.03) for y in (yi, yw - 0.02)]
        for x, y in posts:
            P["interior.metal"].tube((x, s * y, CFLOOR + 0.004), (x, s * y, 1.42), 0.014, 4)
        for z in (CFLOOR + 0.05, 0.98, 1.30):
            P["interior.metal"].box(((xa + xb) / 2, s * (yi + yw - 0.02) / 2, z),
                                    (xb - xa - 0.02, yw - yi - 0.02, 0.016))
        if kind == "cases":
            for (x, z, sx, sz) in ((-1.70, CFLOOR + 0.18, 0.36, 0.24), (-1.30, CFLOOR + 0.16, 0.34, 0.20),
                                   (-1.60, 1.10, 0.48, 0.18), (-1.25, 1.10, 0.18, 0.18)):
                rack_box(P, (x, s * (yi + 0.16), z), (sx, 0.28, sz), mat="hazard" if sz < 0.19 else "interior",
                         face=(0, -s, 0))
        else:
            for (x, z, sx, sz, kn) in ((-1.55, CFLOOR + 0.18, 0.60, 0.24, 0),
                                       (-1.52, 1.07, 0.56, 0.11, 3), (-1.52, 1.20, 0.56, 0.11, 2)):
                rack_box(P, (x, s * (yi + 0.16), z), (sx, 0.28, sz), face=(0, -s, 0),
                         lit="screen.lit" if kn else None, knobs=kn)
            P["interior.gloss"].pipe([(-1.20, s * (yi + 0.01), 1.10), (-1.15, s * (yi - 0.03), 0.95),
                                      (-1.12, s * (yi - 0.01), 0.82)], 0.004, 6)
            pill = C.pill
            pill(P["interior.gloss"], (-1.21, s * (yi - 0.005), 1.13), (0, 0, 1), (1, 0, 0), 0.09, 0.05,
                 0.03, r=0.015, soft=0.5, n=2)
    extinguisher(P, (-1.06, 0.0, CFLOOR + 0.002), h=0.40, r=0.055)
    p, n = cab.on('X', 0.0, 1.02)                     # the power panel on the rear wall
    rack_box(P, p + n * 0.035, (0.07, 0.44, 0.30), face=(1, 0, 0), lit="screen.lit", knobs=4)
    for y in (-0.16, 0.16):
        P["hazard"].box(p + n * 0.072 + V3((0, y, 0.11)), (0.002, 0.07, 0.03))
    cab._emit("bay", P, one_sided=True)
    # BASTION on a bolted plate on the dash's face before the commander
    P = C._Parts()
    c, nrm, up = d["face"](-0.30, 0.20)
    sd = up.cross(nrm).normalized()
    P["interior.metal"].box(c + nrm * 0.004, (0.19, 0.042, 0.004), rot=C._rot(sd, up, nrm))
    K.text_flat(P["interior.gloss"], "BASTION", 0.020, c + nrm * 0.0064, -sd if sd.y > 0 else sd,
                up, spacing=1.2)
    for s in (-1, 1):
        bolt(P["interior.gloss"], c + nrm * 0.006 + sd * (s * 0.085), nrm, 0.004, 0.002)
    cab._emit("plate", P, one_sided=True)
    cab.views(exposure=0.4, outside=3.0, daylight=12.0)
    cab.report()
    K.meant("symmetry", *cab.one_sided, "interior.roof.*", "interior.console_roof.*")


# ---------------------------------------------------------------------------------------
# views of its own, and the build
# ---------------------------------------------------------------------------------------
K.VIEWS["hero"].update(dir=(1.0, 1.08, 0.13), lens=58, focus=(1.7, 0.9, 0.8))
K.VIEWS["rear"].update(dir=(-1.0, -0.74, 0.34), focus=(-1.9, -0.8, 0.9))
K.VIEWS["back"].update(dir=(-1.0, 0.0, 0.14))
K.VIEWS.update(
    wheel=dict(dir=(0.55, 1.0, 0.12), lens=85, target=(FA_X, 0.9, 0.5), fit=("tire.fl",),
               margin=0.0),
    nose=dict(dir=(1.0, 0.5, 0.16), lens=85, target=(2.2, 0.4, 0.85), dist=4.2),
    roof=dict(dir=(-0.5, 0.8, 0.75), lens=70, target=(-0.5, 0, 1.9), dist=5.0),
    tail=dict(dir=(-1.0, 0.55, 0.28), lens=70),
)


def main():
    K.materials(paint=(0.006, 0.045, 0.24), paint_finish=(0.0, 0.40, 0.5),
                paint2=(0.035, 0.038, 0.042), paint2_finish=(0.35, 0.52, 0.0),
                dust=(0.24, 0.21, 0.17), dust_amount=0.45, dust_z=(0.42, 0.95),
                glass=(0.30, 0.36, 0.40),
                led_front=(0.80, 0.93, 1.0), led_accent=(1.0, 0.42, 0.03),
                caliper=(0.95, 0.20, 0.01), seat=(0.10, 0.04, 0.016),
                decal=(0.74, 0.75, 0.74), screen=(0.25, 0.75, 1.0))
    K.pbr("mark", (0.74, 0.75, 0.74), 0.0, 0.5)             # white markings on the dark parts
    K.pbr("hazard", (0.95, 0.36, 0.01), 0.0, 0.5)           # hazard stripes, straps
    K.pbr("cable", (0.95, 0.22, 0.01), 0.0, 0.45)           # high voltage
    K.pbr("stator", (0.72, 0.27, 0.07), 1.0, 0.32)          # the motors' copper
    K.pbr("drone", (0.70, 0.71, 0.72), 0.0, 0.42)
    K.pbr("tiremark", (0.085, 0.085, 0.085), 0.0, 0.6)
    K.emit("sensor", (0.15, 0.85, 1.0), 14.0)
    build_hull()
    K.log("hull")
    build_fenders()
    build_lights()
    build_bumpers()
    build_steps()
    build_nose()
    build_cab()
    build_hatch()
    build_roof()
    build_bolts()
    build_lettering()
    build_chassis()
    build_interior()
    K.log("details")
    for side, s in ((1, "l"), (-1, "r")):
        build_wheel("f" + s, FA_X, side)
        build_wheel("r" + s, RA_X, side)
    build_spare()
    K.log("wheels")
    # one-sided by design: the folding mast and the whip on the left, the driver's wheel and
    # screens, both wipers parked to the left, the spare's swing arm hinged on the right, the
    # winch hook hung off its rollers, the louvres' and rotor blades' lean
    K.meant("symmetry", "mast", "led.mast", "mast.eye",
            "spare.arm", "hooks", "winch.rollers", "wipers", "wiper.blades", "hood.louvres",
            "drone.blades")
    K.shoot(extra=dict(view="top", size=(900, 430), corner="tl"))


main()
