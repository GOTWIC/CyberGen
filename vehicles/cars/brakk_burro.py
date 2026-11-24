"""Brakk Burro: a compact two-door 4x4 of flat plates (both names made up), on
vehicles/carkit.py.

Run (always through the wrapper, one Blender job at a time on this machine):
    vehicles/blender.sh vehicles/cars/brakk_burro.py --out DIR --preview
    vehicles/blender.sh vehicles/cars/brakk_burro.py --out DIR --sheet

Brakk's smallest machine, the Hauler's, the Bastion's and the Mule's sibling (family cues:
docs/progress/AG18/brakk_hauler/README.md): plates and 45 degree chamfers, the wheels outside
the hull under bolted fender plates, light pylons on the chamfered corners, a bar of light
over the windshield, the ribbed slab face, fasteners in rows, stencils, the Brakk wheel. Its
own ideas: it is as tall as it is wide and barely two wheels longer than its wheelbase; the
windshield leans forward under a brow that carries the light bar; the hood's chamfer runs on
as the doors' shoulder; behind the two-seat cab stands a roll hoop, and from it a pack rack
slopes down over a short load tub with the spare strapped flat on it, like the load on a
donkey's back; a nudge bar with two round lamps stands over the winch, a raised intake
climbs the left pillar and an exhaust stack the hoop's right leg.

Pieces: the hull (nose, hood and cab: eight lines over eight stations, every edge sharp), the
tub (its walls are stations of their own), and plates, bars and tubes for the rest. Step B's
kit: the lamps are pockets in housings under lenses (the brand's pylons, LED modules behind
one lens in the brow, reflectors in the round lamps, marker blades cut into the pillars under
amber lenses); the door handles' recesses, the filler flaps and the cab's rear window are cut
through the skin (cutters()); the rear pane has a frit border; the hull's panes are whole
flat plates, shaded flat, in thick bolted frames of the car's own (frame()). The brand's
helpers (plates, bolts, stencils, stripes, the pylon, the coil, the wheel) are in
vehicles/brands/brakk.py.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import carkit as K                                                  # noqa: E402
from functools import partial                                       # noqa: E402
from brands import brakk                                            # noqa: E402
from brands.brakk import (bolt, chevrons, coil, lamp_pylon, on_plane, on_side,  # noqa: E402
                          plate, ring, stencil, tube)
from carkit import Geo, Matrix, V3, cos, hypot, on_body, pi, rad, sin   # noqa: E402

# ---------------------------------------------------------------------------------------
# dimensions
# ---------------------------------------------------------------------------------------
FA_X, RA_X = 1.27, -1.23            # axles: wheelbase 2.5
T_R, T_W, T_RIM, T_OUT = 0.43, 0.28, 0.215, 0.95       # tire radius, width, rim, outer face
HOOD, BELT, SHO, H_Z, ROOF = 1.17, 1.24, 1.10, 1.68, 1.80
#     hood top, window sill, foot of the shoulder, glass top, roof
RAIL, TFLOOR = 1.12, 0.76           # tub rail and tub floor
TUB_Y = 0.60                        # tub half width
TUB_X0, TUB_X1 = -0.70, -1.76       # the tub's front and tail
FEN_Z, FEN_T = 0.99, 0.03           # fender plates: top height, thickness
HOOP_X, HOOP_Y, HOOP_Z = -0.725, 0.54, 1.84             # the roll hoop behind the cab
RACK_A = V3((-0.76, 0.54, 1.54))    # the pack rack's side rail: at the hoop
RACK_B = V3((-1.71, 0.40, 1.30))    # ... and on the tail post
SPARE_X = RA_X                      # the spare lies over the rear axle
NUM = "14"
GAP = 0.00175                       # shut lines 3.5 mm
FLAP = (-0.55, 0.875, 0.10, 0.12)   # the filler flap on the quarter: middle x, z, width, height
GRIP = (-0.27, 1.062, 0.19, 0.05)   # the door handle's recess
MARK = (-0.55, 1.46, 0.036, 0.22)   # the marker blade on the pillar
WIN = (1.455, 0.86, 0.30)           # the cab's rear window: middle z, width, height

# the Brakk wheel (vehicles/brands/brakk.py) at this car's sizes
build_wheel = partial(brakk.wheel, motor=False, R=T_R, w=T_W, rim=T_RIM, out=T_OUT, lugs=20,
                      text="BRAKK  TRAKTOR  A/T   34 X 11 R17   ", seg=88,
                      dish=brakk.DISH_SMALL)


def side_y(z):
    """The cab's side at height z: the door plate, the shoulder, the glass."""
    if z <= SHO:
        return 0.73 + 0.03 * (z - 0.66) / (SHO - 0.66)
    if z <= BELT:
        return 0.76 - 0.06 * (z - SHO) / (BELT - SHO)
    return 0.70 - 0.06 * (z - BELT) / (H_Z - BELT)


def rack_at(x):
    """The pack rack's plane (the rails' middles) at x: its height and the rails' y."""
    t = (x - RACK_A.x) / (RACK_B.x - RACK_A.x)
    return RACK_A.z + (RACK_B.z - RACK_A.z) * t, RACK_A.y + (RACK_B.y - RACK_A.y) * t


RACK_K = (RACK_A.z - RACK_B.z) / (RACK_A.x - RACK_B.x)      # the rack's slope
RACK_N = V3((-RACK_K, 0, 1)).normalized()                   # its way up
RACK_T = V3((1, 0, RACK_K)).normalized()                    # along it, forward
SPARE_C = V3((SPARE_X, 0, rack_at(SPARE_X)[0])) + RACK_N * (0.024 + T_W / 2 + 0.006)


# ---------------------------------------------------------------------------------------
# hull: nose, hood and cab
# ---------------------------------------------------------------------------------------
LINES = "CRHWGUFB"
#        C top centerline, R roof plate edge / windshield edge / hood top, H foot of the roof
#        chamfer (glass top) / hood edge, W window sill / middle of the hood chamfer,
#        G foot of the shoulder / of the hood chamfer, U foot of the side plate, F floor
#        edge, B floor centerline
ORDER = ["N0", "N1", "A0", "W0", "W1", "W2", "BP", "CB"]
PT = {}


def cab_row(x):
    return [(x, 0, ROOF), (x, .52, ROOF), (x, .64, H_Z), (x, .70, BELT), (x, .76, SHO),
            (x, .73, .66), (x, .58, .50), (x, 0, .48)]


def hull_stations():
    h1, h2 = HOOD - 0.06, HOOD - 0.12
    T = {
        "N0": [(1.74, 0, h2), (1.74, .22, h2), (1.74, .30, h2), (1.74, .35, h2 - .05),
               (1.74, .40, h2 - .10), (1.74, .40, .74), (1.74, .30, .62), (1.74, 0, .62)],
        "N1": [(1.62, 0, HOOD), (1.62, .24, HOOD), (1.62, .40, HOOD), (1.62, .46, h1),
               (1.62, .52, h2), (1.62, .50, .74), (1.62, .38, .54), (1.62, 0, .52)],
        "A0": [(.92, 0, HOOD), (.92, .24, HOOD), (.92, .40, HOOD), (.91, .46, h1),
               (.90, .52, h2), (.88, .50, .74), (.88, .38, .54), (.88, 0, .50)],
        # the windshield's foot: it leans forward to its top (W1), its corner post a chamfer
        "W0": [(.80, 0, BELT - .01), (.80, .56, BELT - .01), (.72, .68, BELT - .01),
               (.70, .70, BELT), (.74, .76, SHO), (.74, .73, .66), (.74, .58, .50),
               (.74, 0, .48)],
        "W1": [(.86, 0, 1.71), (.86, .52, 1.71), (.76, .64, H_Z), (.66, .70, BELT),
               (.66, .76, SHO), (.66, .73, .66), (.66, .58, .50), (.66, 0, .48)],
        "W2": [(.84, 0, ROOF), (.84, .52, ROOF), (.74, .64, H_Z), (.64, .70, BELT),
               (.64, .76, SHO), (.64, .73, .66), (.64, .58, .50), (.64, 0, .48)],
        "BP": cab_row(-.44), "CB": cab_row(-.66),
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
            ("hood", "hood", "nose_side", "nose_side", "nose_side"),
            ("cowl", "cowl_side", "cowl_side", "cowl_side", "cowl_side"),
            ("glass_ws", "pillar_a", "pillar_a", "cowl_side", "cowl_side"),
            ("brow", "roof_edge", "pillar_a", "door", "door"),
            ("roof", "roof_edge", "glass_s", "door", "door"),
            ("roof", "roof_edge", "pillar_b", "quarter", "quarter"))[i][j]


HULL_MAT = dict(nose_top="paint", nose_corner="paint", hood="paint", nose_side="paint",
                cowl="cladding", cowl_side="paint", glass_ws="glass", pillar_a="paint",
                door="paint", brow="paint", glass_s="glass", roof="paint", roof_edge="paint",
                pillar_b="paint", quarter="paint", sill="cladding", floor="underbody",
                nose="cladding", cabback="paint", cut="void",
                press="paint", recess="cladding", lamp_m="lamp_housing", lens_m="lens_amber")
POCKET = {}


def cutters():
    """Cut into the hull as it stands uncut: the filler flap on each quarter (its outline a
    shut line through the plate), the recess behind each door's grab bar, a marker blade in
    each pillar under an amber lens, the cab's rear window (a hole through its back wall)."""
    cut = Geo()
    x, z, w, h = FLAP
    K.groove(cut, K.rounded(x, z, w, h, 0.014), 'y', closed=True, mirror=True)
    grip = Geo()
    x, z, w, h = GRIP
    K.pocket(grip, K.rounded(x, z, w, h, 0.016), 'y', depth=0.03, mirror=True)
    mark = Geo()
    x, z, w, h = MARK
    POCKET["mark"] = K.pocket(mark, K.rounded(x, z, w, h, 0.012), 'y', depth=0.026,
                              mirror=True)
    win = Geo()
    z, w, h = WIN
    K.pocket(win, K.rounded(0, z, w, h, 0.05), 'X', depth=0.03)
    return [(cut, "cut", "drop"), (grip, "recess"), (mark, "lamp_m", "skin", "lens_m"),
            (win, "cut", "drop")]


def tub_row(x, yo, top, yi=None):
    """A tub station: over a wall (top) its inner points lie on the rail, else on the floor."""
    yi = yo - 0.08 if yi is None else yi
    zc = RAIL if top else TFLOOR
    return [(x, 0, zc), (x, yi - 0.02 if top else yi, zc), (x, yo - 0.08, RAIL),
            (x, yo - 0.04, RAIL), (x, yo, RAIL - 0.04), (x, yo, 0.82), (x, yo - 0.14, 0.66),
            (x, 0, 0.64)]


def tub_panel(i, j):
    if j == 6:
        return "floor"
    if j == 5:
        return "tubsill"
    if j >= 3:
        return "corner" if i >= 3 else "tubside"
    if j == 2:
        return "rail"
    if i in (0, 5):
        return "rail"
    if i in (1, 4) or j == 1:
        return "tubwall"
    return "tubfloor"


TUB_MAT = dict(floor="underbody", tubsill="cladding", corner="paint", tubside="paint",
               rail="cladding", tubwall="liner", tubfloor="plate", tubfront="paint",
               tailgate="paint")


def build_hull():
    # plates want a broad edge; the pillar with the marker's small window a fine one (a
    # broad bevel folds round a hole that small)
    bev = {pn: 0.008 for pn, mt in HULL_MAT.items() if not mt.startswith(("glass", "void"))}
    bev["pillar_b"] = 0.0025
    hull = K.build_body(hull_stations(), hull_panel, HULL_MAT, 1.0, 1.0, name="hull",
                        front=dict(kind="flat", panel="nose"),
                        rear=dict(kind="flat", panel="cabback"),
                        recesses=[(5, 4, 0.075, 0.012, "press", "press")],
                        cutters=cutters, subdiv=2, gap=GAP, bevel=bev)
    # the panes are flat plates: shaded flat (smooth, a pane's thickness bends its normals
    # toward its rim and the studio's reflections into a bright ring round it). Their thick
    # frames are bars of the car's own (build_frames): the kit's frame is a ring of long
    # quads whose corners fold over the pane's when the cage is subdivided
    for pn in ("glass_ws", "glass_s"):
        hull.parts[pn].data.shade_flat()
    y = TUB_Y
    rows = [tub_row(TUB_X0, y, True), tub_row(TUB_X0 - 0.05, y, True),
            tub_row(TUB_X0 - 0.07, y, False), tub_row(TUB_X1 + 0.15, y, False),
            tub_row(TUB_X1 + 0.12, y - 0.03, False, y - 0.11),
            tub_row(TUB_X1 + 0.10, y - 0.05, True, y - 0.11),
            tub_row(TUB_X1, y - 0.13, True, y - 0.19)]
    K.build_body(rows, tub_panel, TUB_MAT, 1.0, 1.0, name="tub",
                 front=dict(kind="flat", panel="tubfront"),
                 rear=dict(kind="flat", panel="tailgate"), subdiv=2, gap=GAP, bevel=0.008)


# ---------------------------------------------------------------------------------------
# fender plates, lights
# ---------------------------------------------------------------------------------------
BOLTS = Geo()           # bolt heads on the left side and the middle, mirrored at the end
F_FEN = [(1.76, 0.80), (1.62, FEN_Z), (0.96, FEN_Z), (0.82, 0.80)]
R_FEN = [(-0.76, 0.80), (-0.90, FEN_Z), (-1.58, FEN_Z), (-1.72, 0.78)]


def build_fenders():
    g, gb, gk = Geo(), Geo(), Geo()
    y1 = T_OUT + 0.012
    for pts, y0, yr, brackets in ((F_FEN, 0.54, 0.665, (1.50, 1.08)),
                                  (R_FEN, TUB_Y + 0.02, TUB_Y + 0.02, (-1.02, -1.46))):
        # the rear slope of the front plate is cut back round the cab's shoulder
        plate(g, pts[:3], FEN_T, y0, y1)
        plate(g, pts[2:], FEN_T, yr, y1)
        plate(g, pts, 0.075, y1 - 0.028, y1)            # the outer edge folded down
        plate(g, pts[:3], 0.06, y0, y0 + 0.02)          # the mounting flange
        for a, b in zip(pts, pts[1:]):
            L = hypot(b[0] - a[0], b[1] - a[1])
            n = (-(b[1] - a[1]) / L, 0, (b[0] - a[0]) / L)
            n = (-n[0], 0, -n[2]) if n[2] < 0 else n
            k = max(2, int(L / 0.115))
            ya = yr if (b is pts[-1] and yr > y0) else y0
            for i in range(k):
                t = (i + 0.5) / k
                x, z = a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t
                for y in (ya + 0.045, y1 - 0.06):
                    bolt(gb, (x, y, z), n)
        for x in brackets:                              # gussets to the body
            gk.prism([(x - 0.012, y0 - 0.02, FEN_Z - FEN_T), (x - 0.012, y0 + 0.22, FEN_Z - FEN_T),
                      (x - 0.012, y0 - 0.02, FEN_Z - 0.20)], (0.024, 0, 0))
    sec = [(-0.022, 0.0), (0.022, 0.0), (0.012, 0.01), (-0.012, 0.01)]
    for (xa, xb), ys in (((1.57, 1.01), (0.66, 0.76, 0.86)), ((-0.95, -1.53), (0.72, 0.80, 0.88))):
        for y in ys:
            g.sweep([(xa, y, FEN_Z - 0.002), (xb, y, FEN_Z - 0.002)], sec, up=(0, 0, 1))
    g.obj("fender.plates", "paint2", bevel=0.006, mirror=True)
    gk.obj("fender.gussets", "cladding", bevel=0.003, mirror=True)
    gb.obj("fender.bolts", "rim_bright", mirror=True)
    g = Geo()                                           # mud flaps behind the rear wheels
    g.box((-1.728, 0.80, 0.60), (0.014, 0.30, 0.36))
    g.obj("mudflaps", "rubber", bevel=0.003, mirror=True)
    g = Geo()                                           # markers on the folded edges
    y = y1 + 0.001
    g.box((1.46, y, FEN_Z - 0.04), (0.16, 0.006, 0.03))
    g.box((-1.04, y, FEN_Z - 0.04), (0.10, 0.006, 0.03))
    g.obj("led.markers", "led_accent", mirror=True)
    g = Geo()
    g.box((-1.46, y, FEN_Z - 0.04), (0.16, 0.006, 0.03))
    g.obj("led.markers_r", "led_rear", mirror=True)


def round_lamp(tag, c, d, r, lit, depth=0.085, guard=True, mirror=True):
    """A round lamp at c shining along d (a unit axis vector): a bowl housing with a bolted
    bezel, a faceted reflector round its emitter, a clear lens, a cross guard."""
    c, d = V3(c), V3(d).normalized()
    g = Geo()
    g.lathe([(-depth, 0.0006), (-depth, r * 0.42), (-depth * 0.72, r * 0.78), (-0.02, r * 1.06),
             (0.006, r * 1.06), (0.006, r * 0.93), (-depth * 0.8, r * 0.62),
             (-depth * 0.8, 0.0006)], 24, axis=d, at=c)
    g.obj("eye.%s" % tag, "cladding", bevel=0.002, mirror=mirror)
    g = Geo()
    g.lathe([(0.002, r * 0.90), (0.002, r * 1.10), (0.011, r * 1.10), (0.014, r * 1.04),
             (0.014, r * 0.90)], 24, axis=d, at=c)
    g.obj("eye.%s.bezel" % tag, "paint2", bevel=0.001, mirror=mirror)
    ref = V3((0, 0, 1)) if abs(d.z) < 0.9 else V3((1, 0, 0))
    u = d.cross(ref).normalized()
    v = d.cross(u)
    g = Geo()
    for k in range(6):
        a = 2 * pi * (k + 0.5) / 6
        bolt(g, c + d * 0.014 + (u * cos(a) + v * sin(a)) * r, d, 0.0045, 0.003)
    g.obj("eye.%s.bolts" % tag, "rim_bright", mirror=mirror)
    L = K.Lamp("lamp.eye_" + tag, lit=lit)
    L.reflector(c + d * 0.0, d, r=r * 0.88, depth=depth * 0.62, seg=16, led=r * 0.26)
    L.glass.lathe([(0.0, 0.0006), (0.0, r * 0.92), (0.004, r * 0.92), (0.009, r * 0.5),
                   (0.010, 0.0006)], 24, axis=d, at=c + d * 0.002)
    L.obj(mirror=mirror)
    if guard:
        g = Geo()
        for w in (u, v):
            a, b = c + d * 0.026 - w * r * 1.02, c + d * 0.026 + w * r * 1.02
            tube(g, a, b, 0.0035, 8)
            for q in (a, b):
                tube(g, q, q - d * 0.016, 0.0035, 8)
        g.obj("eye.%s.guard" % tag, "rim", mirror=mirror)


def build_lights():
    # the corner pylons (the brand's step B pylon): white in front, red behind
    lamp_pylon("f", 1.68, 0.46, 0.64, 1.13, 45, "led_front", "lens_clear")
    lamp_pylon("r", TUB_X1 + 0.05, TUB_Y - 0.09, 0.74, 1.19, 135, "led_rear", "lens_red")
    # the brow: the roof's front edge run out over the windshield as a thick plate, the
    # light bar in its face (eight cells of LED modules behind one clear lens between
    # dividers), a bolted top, amber lamps at its ends
    xf, x1, y1, yh = 0.975, 1.0, 0.495, 0.54
    zb, zt, ztop, zu = ROOF + 0.014, ROOF + 0.056, ROOF + 0.072, ROOF - 0.004
    g = Geo()
    g.prism([(xf, -yh, zu), (xf, -yh, ztop), (0.64, -yh, ztop), (0.56, -yh, zu)],
            (0, 2 * yh, 0))
    g.box(((xf + x1) / 2, 0, (zt + ztop) / 2), (x1 - xf, 2 * yh, ztop - zt))
    g.box(((xf + x1) / 2, 0, (zb + zu) / 2), (x1 - xf, 2 * yh, zb - zu))
    for sg in (1, -1):
        g.box(((xf + x1) / 2, sg * (y1 + yh) / 2, (zb + zt) / 2), (x1 - xf, yh - y1, zt - zb))
    for k in range(1, 8):
        y = -y1 + 2 * y1 * k / 8
        g.box(((xf + x1) / 2 + 0.003, y, (zb + zt) / 2), (x1 - xf + 0.006, 0.014, zt - zb))
    g.obj("roofbar", "cladding", bevel=0.003)
    g = Geo()                                           # gussets under the brow's ends
    for s in (1, -1):
        g.prism([(0.965, s * 0.50 - 0.008, zu), (0.865, s * 0.50 - 0.008, zu),
                 (0.862, s * 0.50 - 0.008, ROOF - 0.085)], (0, 0.016, 0))
    g.obj("roofbar.gussets", "cladding", bevel=0.002)
    g = Geo()
    for k in range(9):
        y = -0.48 + 0.96 * k / 8
        bolt(g, (0.985, y, ztop), (0, 0, 1), 0.006, 0.0035)
        bolt(g, (0.70, y, ztop), (0, 0, 1), 0.006, 0.0035)
    g.obj("roofbar.bolts", "rim_bright")
    L = K.Lamp("lamp.roofbar", lit="led_front")
    L.chrome.box((xf + 0.002, 0, (zb + zt) / 2), (0.004, 2 * y1, zt - zb))
    for k in range(8):
        yc = -y1 + 2 * y1 * (k + 0.5) / 8
        L.leds((xf + 0.015, yc - 0.042, (zb + zt) / 2), (xf + 0.015, yc + 0.042, (zb + zt) / 2), 3,
               (1, 0, 0), r=0.013)
    L.glass.box((x1 - 0.0045, 0, (zb + zt) / 2), (0.003, 2 * y1, zt - zb))
    L.obj()
    # its amber end lamps: a window in a bolted end plate, a reflector in the pocket behind
    g = Geo()
    xa, xb, za, zc = 0.86, 0.93, ROOF + 0.018, ROOF + 0.052
    for (xl, xr), (z0, z2) in (((0.80, xa), (zu, ztop)), ((xb, x1), (zu, ztop)),
                               ((xa, xb), (zu, za)), ((xa, xb), (zc, ztop))):
        g.box(((xl + xr) / 2, yh + 0.011, (z0 + z2) / 2), (xr - xl, 0.022, z2 - z0))
    g.obj("roofbar.ends", "paint2", bevel=0.0015, mirror=True)
    A = K.Lamp("lamp.roofbar_end", lit="led_accent", glass="lens_amber")
    A.reflector(((xa + xb) / 2, yh + 0.0155, (za + zc) / 2), (0, 1, 0), r=0.016, depth=0.012)
    A.glass.box(((xa + xb) / 2, yh + 0.0195, (za + zc) / 2), (xb - xa, 0.003, zc - za))
    A.obj(mirror=True)
    # the marker blades in the pillars: an amber bar on a bright plate in each pocket
    P = POCKET.get("mark")
    if P is not None:
        x, z, w, h = MARK
        M = K.Lamp("lamp.marker", lit="led_accent", glass="lens_amber")
        a, b = P.at(x, z - h / 2 + 0.02, lift=0.006), P.at(x, z + h / 2 - 0.02, lift=0.006)
        if a is not None and b is not None:
            M.bar([a, b], 0.012, 0.006, up=P.n)
            q0, q1 = P.at(x, z - h / 2 + 0.008, lift=0.001), P.at(x, z + h / 2 - 0.008, lift=0.001)
            M.chrome.sweep([q0, q1], [(-0.013, -0.001), (0.013, -0.001), (0.013, 0.001),
                                      (-0.013, 0.001)], up=P.n)
        M.obj(mirror=True)
    # the eyes: two round lamps on the nudge bar, two work lamps on the hoop facing the tub
    round_lamp("f", (1.905, 0.16, 1.168), (1, 0, 0), 0.06, "led_front", depth=0.075)
    round_lamp("w", (HOOP_X - 0.07, 0.25, HOOP_Z + 0.062), (-1, 0, -0.34), 0.043, "lamp",
               depth=0.06)
    # the stop lamp under the hoop's top bar: eight LEDs behind a red lens in a slim housing
    S = K.Lamp("lamp.stop", lit="led_rear", glass="lens_red")
    xs, zs = HOOP_X - 0.035, HOOP_Z - 0.052
    for (y0, y2), (z0, z2) in (((-0.20, 0.20), (zs - 0.022, zs - 0.0125)),
                               ((-0.20, 0.20), (zs + 0.0125, zs + 0.017)),
                               ((-0.20, -0.18), (zs - 0.0125, zs + 0.0125)),
                               ((0.18, 0.20), (zs - 0.0125, zs + 0.0125))):
        S.housing.box((xs - 0.014, (y0 + y2) / 2, (z0 + z2) / 2), (0.028, y2 - y0, z2 - z0))
    S.housing.box((xs - 0.002, 0, zs), (0.004, 0.36, 0.025))
    S.leds((xs - 0.012, -0.17, zs), (xs - 0.012, 0.17, zs), 8, (-1, 0, 0), r=0.0095)
    S.glass.box((xs - 0.0245, 0, zs), (0.003, 0.36, 0.025))
    S.obj()


# ---------------------------------------------------------------------------------------
# bumpers, winch, nudge bar, skid, sliders
# ---------------------------------------------------------------------------------------
def build_bumpers():
    # front: a beam with swept, rising ends, the winch in a housing in its middle
    g = Geo()
    g.prism([(1.93, -0.46, 0.50), (1.93, 0.46, 0.50), (1.76, 0.46, 0.50), (1.76, -0.46, 0.50)],
            (0, 0, 0.20))
    for s in (1, -1):
        g.hexa([(1.93, s * 0.46, 0.50), (1.80, s * 0.95, 0.61), (1.745, s * 0.95, 0.61),
                (1.76, s * 0.46, 0.50), (1.93, s * 0.46, 0.70), (1.80, s * 0.95, 0.70),
                (1.745, s * 0.95, 0.70), (1.76, s * 0.46, 0.70)])
    g.prism([(1.93, -0.22, 0.515), (1.975, -0.22, 0.53), (1.99, -0.22, 0.565), (1.99, -0.22, 0.635),
             (1.975, -0.22, 0.67), (1.93, -0.22, 0.685)], (0, 0.44, 0))
    g.obj("bumper.front", "paint2", bevel=0.007)
    g = Geo()                                           # fairlead, rollers, hook
    g.box((1.993, 0, 0.60), (0.008, 0.27, 0.085))
    g.obj("winch.fairlead", "rim_bright", bevel=0.002)
    g = Geo()
    g.box((1.9975, 0, 0.60), (0.004, 0.19, 0.036))
    g.obj("winch.slot", "void")
    g = Geo()
    for z in (0.578, 0.622):
        tube(g, (2.0, -0.10, z), (2.0, 0.10, z), 0.011, 10)
    tube(g, (2.0, 0, 0.60), (2.015, 0.02, 0.585), 0.007, 8)
    g.obj("winch.rollers", "rim", bevel=0.001)
    g = Geo()                                           # the hook, shackles on tabs
    g.lathe([(-0.008, 0.022), (-0.008, 0.040), (0.008, 0.040), (0.008, 0.022)], 12, a0=rad(-200),
            a1=rad(60),
            xf=Matrix.Translation((2.035, 0.02, 0.555)) @ Matrix.Rotation(pi / 2, 4, 'Z'))
    for s in (1, -1):
        g.box((1.945, s * 0.36, 0.60), (0.05, 0.03, 0.075))
        ring(g, (1.957, s * 0.36, 0.565))
        g.box((TUB_X1 - 0.155, s * 0.30, 0.52), (0.04, 0.03, 0.07))
        ring(g, (TUB_X1 - 0.165, s * 0.30, 0.475))
    g.obj("hooks", "caliper", bevel=0.003)
    # the nudge bar: a hoop of tube on the bumper, the eyes' brackets on its top bar
    g = Geo()
    xn, yb, zt = 1.895, 0.30, 1.065
    g.pipe([(xn, -yb, 0.695), (xn, -yb, zt - 0.07), (xn, -yb + 0.07, zt), (xn, yb - 0.07, zt),
            (xn, yb, zt - 0.07), (xn, yb, 0.695)], 0.021, 10, up=(1, 0, 0))
    for s in (1, -1):
        g.box((xn, s * yb, 0.706), (0.10, 0.075, 0.012))
        g.box((xn - 0.01, s * 0.16, zt + 0.026), (0.045, 0.04, 0.03))
        tube(g, (xn, s * yb, 0.90), (1.75, s * 0.345, 0.96), 0.012, 8)       # stays to the nose
    g.obj("nudge", "paint2", bevel=0.002)
    g = Geo()
    for s in (1, -1):
        for dx in (-0.03, 0.03):
            bolt(g, (xn + dx, s * yb + s * 0.025, 0.712), (0, 0, 1), 0.007, 0.004)
    g.obj("nudge.bolts", "rim_bright")
    g = Geo()                                           # skid plate under the nose
    g.prism([(1.82, -0.36, 0.505), (1.56, -0.36, 0.44), (0.96, -0.36, 0.44), (0.96, -0.36, 0.462),
             (1.56, -0.36, 0.462), (1.82, -0.36, 0.527)], (0, 0.72, 0))
    for y in (-0.24, -0.12, 0.0, 0.12, 0.24):
        g.prism([(1.78, y - 0.02, 0.492), (1.56, y - 0.02, 0.427), (1.08, y - 0.02, 0.427),
                 (1.08, y - 0.02, 0.445), (1.56, y - 0.02, 0.445), (1.78, y - 0.02, 0.51)],
                (0, 0.04, 0))
    g.obj("skid", "rim", bevel=0.003)
    # rear: a step beam with a hitch
    g = Geo()
    x0 = TUB_X1
    g.prism([(x0, -0.88, 0.46), (x0, 0.88, 0.46), (x0 - 0.08, 0.88, 0.46),
             (x0 - 0.14, 0.78, 0.46), (x0 - 0.14, -0.78, 0.46), (x0 - 0.08, -0.88, 0.46)],
            (0, 0, 0.16))
    g.box((x0 - 0.13, 0, 0.445), (0.10, 0.11, 0.09))
    g.obj("bumper.rear", "paint2", bevel=0.007)
    g = Geo()
    g.box((x0 - 0.182, 0, 0.445), (0.006, 0.062, 0.05))
    g.obj("hitch.hole", "void")
    g = Geo()
    for y in (0.58, -0.58):                             # step pads
        for k in range(7):
            g.box((x0 - 0.07, y - 0.12 + k * 0.04, 0.6215), (0.10, 0.014, 0.005))
    g.obj("step.pads", "rim_bright", bevel=0.001)
    # rock sliders under the doors: a tube rail on stand-offs, a tread plate step on it
    g = Geo()
    ys, zs = 0.87, 0.50
    g.pipe([(0.67, 0.70, 0.545), (0.56, ys, zs), (-0.56, ys, zs), (-0.67, 0.70, 0.545)], 0.026, 10)
    for x in (0.34, -0.34):
        tube(g, (x, 0.68, 0.56), (x, ys, zs), 0.02, 4, phase=pi / 4)
    g.box((0.0, ys - 0.045, zs + 0.03), (0.62, 0.13, 0.012))
    g.obj("sliders", "paint2", bevel=0.003, mirror=True)
    g = Geo()
    for k in range(12):
        g.box((0.275 - k * 0.05, ys - 0.045, zs + 0.038), (0.014, 0.10, 0.005))
    g.obj("slider.ribs", "rim_bright", mirror=True)


# ---------------------------------------------------------------------------------------
# the face and the hood
# ---------------------------------------------------------------------------------------
def build_nose():
    g = Geo()                                           # the ribbed slab
    for z in (0.70, 0.775, 0.85, 0.925):
        g.prism([(1.738, -0.33, z - 0.028), (1.77, -0.33, z - 0.013), (1.77, -0.33, z + 0.013),
                 (1.738, -0.33, z + 0.028)], (0, 0.66, 0))
    g.box((1.746, 0, 0.995), (0.016, 0.44, 0.058))      # the badge plate
    g.obj("nose.ribs", "paint", bevel=0.004)
    g = Geo()
    for y in (0.195, -0.195):
        for z in (0.978, 1.012):
            bolt(g, (1.754, y, z), (1, 0, 0), 0.006, 0.0035)
    g.obj("nose.bolts", "rim_bright")
    # hood: a bolted access plate with louvres, two rubber latches
    g = Geo()
    g.box((1.29, 0, HOOD + 0.004), (0.54, 0.50, 0.012))
    g.obj("hood.plate", "paint", bevel=0.004)
    g = Geo()
    for x in (1.525, 1.055):
        for y in (0.21, 0.07, -0.07, -0.21):
            bolt(g, (x, y, HOOD + 0.01), (0, 0, 1), 0.008, 0.0045)
    for y in (0.215, -0.215):
        for x in (1.37, 1.21):
            bolt(g, (x, y, HOOD + 0.01), (0, 0, 1), 0.008, 0.0045)
    g.obj("hood.bolts", "rim_bright")
    g = Geo()
    for x in (1.50, 1.04):
        g.box((x, 0.35, HOOD + 0.006), (0.09, 0.03, 0.016))
        g.box((x, 0.43, HOOD - 0.03), (0.045, 0.028, 0.10), rot=Matrix.Rotation(rad(45), 3, 'X'))
    g.obj("hood.latches", "rubber", bevel=0.003, mirror=True)
    # cowl: louvres under the windshield
    g = Geo()
    zc = BELT - 0.01
    g.louvers((0.905, 0.035, HOOD + 0.006), (0.905, 0.225, HOOD + 0.006),
              (0.815, 0.225, zc + 0.004), (0.815, 0.035, zc + 0.004), 6, 0.022, 0.005, rad(30),
              out=(0.4, 0, 1), margin=0.04)
    g.obj("cowl.louvres", "grille", bevel=0.0015, mirror=True)


# ---------------------------------------------------------------------------------------
# cab details
# ---------------------------------------------------------------------------------------
def frame(g, gb, pts, w=0.05, inset=0.015, out=0.012, back=0.004, pitch=0.16):
    """A thick mitred frame bolted over a flat pane's edge: pts the pane's corners in order,
    the bar w wide, its middle inset from the edge, standing out proud of the glass; bolt
    heads along it into gb."""
    P = [V3(p) for p in pts]
    c = sum(P, V3()) / len(P)
    n = (P[1] - P[0]).cross(P[2] - P[1]).normalized()
    path = []
    for i, v in enumerate(P):
        e1, e2 = (v - P[i - 1]).normalized(), (P[(i + 1) % len(P)] - v).normalized()
        n1, n2 = n.cross(e1), n.cross(e2)
        if n1.dot(c - v) < 0:
            n1, n2 = -n1, -n2
        path.append(v + (n1 + n2) / (1 + n1.dot(n2)) * inset)
    if n.dot(c - V3((0, 0, c.z))) < 0:      # the way out of the cab
        n = -n
    g.sweep(path, [(-w / 2, -back), (w / 2, -back), (w / 2, out), (-w / 2, out)], up=n,
            closed=True)
    for a, b in zip(path, path[1:] + path[:1]):
        k = max(1, int((b - a).length / pitch))
        for j in range(k):
            bolt(gb, a.lerp(b, (j + 0.5) / k) + n * out, n, 0.006, 0.0035)


def build_frames():
    """The glass's thick frames: bars bolted over the edges of the windshield and of each
    side window."""
    g, gb = Geo(), Geo()
    a, b = PT["W0"]["R"], PT["W1"]["R"]
    frame(g, gb, [a, b, K.my(b), K.my(a)], w=0.055)
    g.obj("frame.ws", "cladding", bevel=0.003)
    gb.obj("frame.ws.bolts", "rim_bright")
    g, gb = Geo(), Geo()
    frame(g, gb, [PT["W2"]["W"], PT["W2"]["H"], PT["BP"]["H"], PT["BP"]["W"]])
    g.obj("frame.side", "cladding", bevel=0.003, mirror=True)
    gb.obj("frame.side.bolts", "rim_bright", mirror=True)



def build_cab():
    # a rub strip along the doors' foot, ribs in the pressed panel, hinges, the grab bars
    g = Geo()
    sec = [(-0.016, 0.0), (0.016, 0.0), (0.009, 0.014), (-0.009, 0.014)]
    for x0, x1 in ((0.61, -0.41), (-0.47, -0.63)):
        z = 0.70
        y = side_y(z) - 0.002
        g.sweep([(x0, y, z), (x1, y, z)], sec, up=(0, 1, 0))
    g.obj("rubstrips", "cladding", bevel=0.002, mirror=True)
    g = Geo()                               # three ribs pressed out of the panel's rear half
    sec = [(-0.02, 0.0), (0.02, 0.0), (0.011, 0.011), (-0.011, 0.011)]
    for z in (0.775, 0.84):
        y = side_y(z) - 0.0125
        g.sweep([(0.53, y, z), (-0.33, y, z)], sec, up=(0, 1, 0))
    g.obj("door.ribs", "paint", bevel=0.003, mirror=True)
    g = Geo()
    x, z, w, h = GRIP                       # the grab bar across its recess
    y = side_y(z)
    tube(g, (x - w / 2 + 0.012, y - 0.006, z), (x + w / 2 - 0.012, y - 0.006, z), 0.0085, 10)
    for dx in (-w / 2 + 0.02, w / 2 - 0.02):
        g.box((x + dx, y - 0.016, z), (0.016, 0.026, 0.02))
    for zz in (0.80, 1.03):                 # hinges on the door's front edge
        yy = side_y(zz)
        g.box((0.645, yy + 0.006, zz), (0.07, 0.024, 0.08))
        tube(g, (0.645, yy + 0.02, zz - 0.048), (0.645, yy + 0.02, zz + 0.048), 0.011, 8)
    x, z, w, h = FLAP                       # the filler flap's hinge on its front edge
    tube(g, (x + w / 2 - 0.004, side_y(z) + 0.004, z - 0.03),
         (x + w / 2 - 0.004, side_y(z) + 0.004, z + 0.03), 0.0055, 8)
    g.obj("door.hardware", "cladding", bevel=0.003, mirror=True)
    # mirrors: a plate on a tube frame off the pillar
    g = Geo()
    tube(g, (0.69, 0.70, 1.30), (0.72, 0.895, 1.36), 0.011)
    tube(g, (0.725, 0.655, 1.58), (0.72, 0.895, 1.56), 0.011)
    tube(g, (0.72, 0.895, 1.34), (0.72, 0.895, 1.60), 0.011)
    g.box((0.715, 0.93, 1.47), (0.035, 0.09, 0.24))
    g.obj("mirrors", "cladding", bevel=0.004, mirror=True)
    g = Geo()
    g.box((0.696, 0.93, 1.47), (0.004, 0.075, 0.215))
    g.obj("mirror.glass", "rim_bright", mirror=True)
    # wipers at rest on the glass, both parked to the left (the kit's wiper)
    g, gr = Geo(), Geo()
    for y0 in (0.06, -0.40):
        piv = on_body(y0 + 0.02, BELT + 0.075, 'x')[0]
        a, b = on_body(y0, BELT + 0.10, 'x')[0], on_body(y0 + 0.38, BELT + 0.36, 'x')[0]
        if piv is not None and a is not None and b is not None:
            K.wiper(g, gr, piv, a, b)
    gr.obj("wiper.blades", "rubber")
    g.obj("wipers", "cladding", bevel=0.001)
    g = Geo()                               # the antenna
    tube(g, (-0.50, -0.42, ROOF), (-0.55, -0.42, ROOF + 0.16), 0.006, 6, r2=0.003)
    g.box((-0.50, -0.42, ROOF + 0.008), (0.06, 0.06, 0.02))
    g.obj("antenna", "cladding", bevel=0.001)
    # roof ribs
    g = Geo()
    sec = [(-0.03, 0.0), (0.03, 0.0), (0.018, 0.012), (-0.018, 0.012)]
    for y in (-0.36, -0.18, 0.0, 0.18, 0.36):
        g.sweep([(0.50, y, ROOF - 0.002), (-0.58, y, ROOF - 0.002)], sec, up=(0, 0, 1))
    g.obj("roof.ribs", "paint", bevel=0.003)
    # the rear window: a pane bonded over the hole in the back wall, a frit border printed
    # on it, two guard bars against the load
    z, w, h = WIN
    xw = -0.66
    g = Geo()
    g.add([(xw - 0.002, y, zz) for y, zz in K.rounded(0, z, w + 0.07, h + 0.07, 0.07)]
          + [(xw - 0.008, y, zz) for y, zz in K.rounded(0, z, w + 0.07, h + 0.07, 0.07)],
          [tuple(range(24))[::-1], tuple(range(24, 48))]
          + [(i, (i + 1) % 24, 24 + (i + 1) % 24, 24 + i) for i in range(24)])
    g.obj("rearwin.glass", "glass", sharp=30)
    g = Geo()
    out = K.rounded(0, z, w + 0.068, h + 0.068, 0.069)
    inn = K.rounded(0, z, w - 0.012, h - 0.012, 0.044)
    n = len(out)
    g.add([(xw - 0.0085, y, zz) for y, zz in out] + [(xw - 0.0085, y, zz) for y, zz in inn]
          + [(xw - 0.0015, y, zz) for y, zz in out] + [(xw - 0.0015, y, zz) for y, zz in inn],
          [(i, (i + 1) % n, n + (i + 1) % n, n + i) for i in range(n)]
          + [(2 * n + i, 3 * n + i, 3 * n + (i + 1) % n, 2 * n + (i + 1) % n) for i in range(n)])
    g.obj("rearwin.frit", "frit")
    g = Geo()
    for zz in (z - 0.075, z + 0.075):
        tube(g, (xw - 0.03, -w / 2 - 0.05, zz), (xw - 0.03, w / 2 + 0.05, zz), 0.008, 8)
    for s in (1, -1):
        g.box((xw - 0.018, s * (w / 2 + 0.05), z), (0.036, 0.022, 0.21))
    g.obj("rearwin.guard", "cladding", bevel=0.002)


def build_snorkel():
    """The raised intake on the left pillar: a duct off the hood's chamfer, up the corner
    post, a head over the brow facing forward."""
    g = Geo()
    sec = [(-0.026, -0.034), (0.026, -0.034), (0.026, 0.034), (-0.026, 0.034)]
    path = [V3((1.10, 0.47, HOOD - 0.04)), V3((0.87, 0.585, HOOD + 0.005)),
            V3((0.795, 0.655, BELT + 0.05)), V3((0.86, 0.607, 1.66)), V3((0.88, 0.607, 1.86))]
    g.sweep(path, sec, up=[V3((0, 0.7, 0.7)), V3((0.3, 0.7, 0.5)), V3((0.7, 0.7, 0)),
                           V3((0.7, 0.7, 0)), V3((0.7, 0.7, 0))])
    g.box((1.15, 0.47, HOOD - 0.045), (0.13, 0.07, 0.075), rot=Matrix.Rotation(rad(-45), 3, 'X'))
    g.obj("snorkel", "cladding", bevel=0.004)
    g = Geo()                               # its flange on the hood's chamfer, four bolts
    R45 = Matrix.Rotation(rad(-45), 3, 'X')
    o = V3((1.15, 0.46, HOOD - 0.06))
    g.box(o + R45 @ V3((0, 0, 0.004)), (0.18, 0.105, 0.008), rot=R45)
    g.obj("snorkel.flange", "paint2", bevel=0.002)
    g = Geo()
    for dx in (-0.075, 0.075):
        for dy in (-0.04, 0.04):
            bolt(g, o + R45 @ V3((dx, dy, 0.008)), R45 @ V3((0, 0, 1)), 0.006, 0.0035)
    g.obj("snorkel.bolts", "rim_bright")
    g = Geo()                               # the head: a box with a mesh mouth, a rain cap
    c = V3((0.90, 0.607, 1.87))
    g.hexa([(c.x - 0.07, c.y - 0.055, c.z - 0.055), (c.x + 0.085, c.y - 0.05, c.z - 0.05),
            (c.x + 0.085, c.y + 0.05, c.z - 0.05), (c.x - 0.07, c.y + 0.055, c.z - 0.055),
            (c.x - 0.07, c.y - 0.055, c.z + 0.05), (c.x + 0.085, c.y - 0.05, c.z + 0.04),
            (c.x + 0.085, c.y + 0.05, c.z + 0.04), (c.x - 0.07, c.y + 0.055, c.z + 0.05)])
    g.obj("snorkel.head", "paint2", bevel=0.004)
    g = Geo()
    g.louvers((c.x + 0.087, c.y - 0.04, c.z - 0.04), (c.x + 0.087, c.y - 0.04, c.z + 0.03),
              (c.x + 0.087, c.y + 0.04, c.z + 0.03), (c.x + 0.087, c.y + 0.04, c.z - 0.04),
              5, 0.012, 0.003, rad(25), out=(1, 0, 0), margin=0.05)
    g.obj("snorkel.mesh", "grille")
    g = Geo()                               # clamps to the pillar
    for q in (path[2].lerp(path[3], 0.25), path[2].lerp(path[3], 0.8)):
        g.box(q, (0.02, 0.10, 0.03), rot=Matrix.Rotation(rad(-45), 3, 'Z'))
    g.obj("snorkel.clamps", "rim", bevel=0.002)


def build_stack():
    """The exhaust stack up the hoop's right leg: a pipe out from under the cab, a slotted
    heat shield, a slant-cut mouth with a rain flap."""
    x, y = HOOP_X - 0.005, -(HOOP_Y + 0.085)
    g = Geo()
    g.pipe([(-0.50, -0.50, 0.56), (x, -0.56, 0.60), (x, y, 0.72), (x, y, 1.20)], 0.026, 10)
    tube(g, (x, y, 1.20), (x, y, 1.80), 0.03, 12)
    g.lathe([(0.0, 0.03), (0.075, 0.03), (0.045, 0.024), (0.0, 0.024)], 12, axis='z',
            at=(x, y, 1.80))
    g.obj("stack", "rim", bevel=0.002)
    g = Geo()                               # the heat shield: a sleeve of slats on two bands
    for k in range(10):
        a = 2 * pi * k / 10
        c = V3((x + 0.046 * cos(a), y + 0.046 * sin(a), 1.45))
        g.box(c, (0.004, 0.02, 0.44), rot=Matrix.Rotation(a, 3, 'Z'))
    for z in (1.25, 1.65):
        g.lathe([(-0.012, 0.044), (-0.012, 0.05), (0.012, 0.05), (0.012, 0.044)], 16, axis='z',
                at=(x, y, z))
    for z in (1.30, 1.60):                  # brackets to the hoop
        g.box((x, y + 0.045, z), (0.03, 0.06, 0.02))
    g.obj("stack.shield", "cladding", bevel=0.001)
    g = Geo()
    g.box((x - 0.012, y, 1.868), (0.075, 0.066, 0.004), rot=Matrix.Rotation(rad(-24), 3, 'Y'))
    g.obj("stack.flap", "rim", bevel=0.001)


# ---------------------------------------------------------------------------------------
# the tub
# ---------------------------------------------------------------------------------------
def build_tub():
    # a corrugated band on the sides over the fender plates, ribs on the tailgate
    g = Geo()
    x = TUB_X0 - 0.10
    while x > TUB_X1 + 0.18:
        g.prism([(x - 0.026, TUB_Y - 0.002, 1.0), (x - 0.013, TUB_Y + 0.015, 1.008),
                 (x + 0.013, TUB_Y + 0.015, 1.008), (x + 0.026, TUB_Y - 0.002, 1.0)],
                (0, 0, 0.078))
        x -= 0.078
    g.obj("tub.ribs", "paint", bevel=0.003, mirror=True)
    g = Geo()
    xt = TUB_X1
    for z in (0.735, 1.05):
        g.prism([(xt + 0.002, -0.40, z - 0.03), (xt - 0.022, -0.40, z - 0.014),
                 (xt - 0.022, -0.40, z + 0.014), (xt + 0.002, -0.40, z + 0.03)], (0, 0.80, 0))
    g.obj("tailgate.ribs", "paint", bevel=0.003)
    g = Geo()
    for y in (0.36, -0.36):
        g.box((xt - 0.008, y, 1.05), (0.03, 0.10, 0.03))
        g.box((xt - 0.006, y, 0.69), (0.03, 0.09, 0.05))
        tube(g, (xt - 0.016, y - 0.05, 0.675), (xt - 0.016, y + 0.05, 0.675), 0.011, 8)
    g.obj("tailgate.latches", "cladding", bevel=0.003)
    # tread plate: raised lozenges, each row leaning the other way
    g = Geo()
    kx = 0
    x = TUB_X0 - 0.11
    while x > TUB_X1 + 0.17:
        ky = 0
        y = -0.485
        while y < 0.49:
            a = rad(45 if (kx + ky) % 2 else -45)
            g.box((x, y, TFLOOR + 0.0015), (0.034, 0.011, 0.005), rot=Matrix.Rotation(a, 3, 'Z'))
            y += 0.045
            ky += 1
        x -= 0.045
        kx += 1
    g.obj("tub.tread", "plate")
    # tie-down rings on the walls
    g = Geo()
    for x in (-0.95, -1.45):
        g.box((x, TUB_Y - 0.088, 1.035), (0.05, 0.016, 0.03))
        g.lathe([(-0.005, 0.022), (-0.005, 0.033), (0.005, 0.033), (0.005, 0.022)], 12,
                xf=Matrix.Translation((x, TUB_Y - 0.094, 0.998)))
    g.obj("tub.rings", "rim_bright", bevel=0.0015, mirror=True)
    # two fuel cans strapped against the tub's front wall
    g, gc, gs = Geo(), Geo(), Geo()
    xc = TUB_X0 - 0.07 - 0.095
    for y in (0.27, -0.27):
        g.prism([(xc - 0.08, y - 0.17, TFLOOR + 0.004), (xc + 0.08, y - 0.17, TFLOOR + 0.004),
                 (xc + 0.08, y - 0.17, TFLOOR + 0.40), (xc + 0.035, y - 0.17, TFLOOR + 0.46),
                 (xc - 0.08, y - 0.17, TFLOOR + 0.46)], (0, 0.34, 0))
        for dy in (-0.09, 0.0, 0.09):                   # the three-bar handle
            yy, zh = y + dy, TFLOOR + 0.495
            tube(gc, (xc - 0.06, yy, TFLOOR + 0.46), (xc - 0.06, yy, zh), 0.008, 6)
            tube(gc, (xc - 0.06, yy, zh), (xc + 0.01, yy, zh), 0.008, 6)
            tube(gc, (xc + 0.01, yy, zh), (xc + 0.02, yy, TFLOOR + 0.47), 0.008, 6)
        nrm = V3((0.8, 0, 0.6))
        K.stud(gc, V3((xc + 0.058, y + 0.10, TFLOOR + 0.43)), nrm,
               [(0.0, 0.001), (0.0, 0.026), (0.022, 0.026), (0.028, 0.02), (0.028, 0.001)], 10)
        gs.box((xc, y, TFLOOR + 0.30), (0.172, 0.35, 0.035))
        for sx in (1, -1):                              # the pressed cross on both faces
            for a in (35, -35):
                g.box((xc + sx * 0.08, y, TFLOOR + 0.20), (0.008, 0.26, 0.022),
                      rot=Matrix.Rotation(rad(a), 3, 'X'))
    g.obj("cans", "can", bevel=0.012, segs=3)
    gc.obj("cans.caps", "cladding", bevel=0.002)
    gs.obj("cans.strap", "hazard", bevel=0.001)


# ---------------------------------------------------------------------------------------
# the roll hoop, the pack rack and the spare on it
# ---------------------------------------------------------------------------------------
def build_rack():
    g = Geo()
    x, y, zt = HOOP_X, HOOP_Y, HOOP_Z
    g.sweep([(x, -y, RAIL - 0.01), (x, -y, zt - 0.14), (x, -y + 0.14, zt), (x, y - 0.14, zt),
             (x, y, zt - 0.14), (x, y, RAIL - 0.01)],
            [(-0.03, -0.035), (0.03, -0.035), (0.03, 0.035), (-0.03, 0.035)], up=(1, 0, 0))
    for s in (1, -1):
        g.box((x, s * y, RAIL + 0.004), (0.12, 0.09, 0.012))
        # corner webs in the hoop's bends
        g.prism([(x - 0.006, s * (y - 0.03), zt - 0.20), (x - 0.006, s * (y - 0.03), zt - 0.03),
                 (x - 0.006, s * (y - 0.20), zt - 0.03)], (0.012, 0, 0))
    g.obj("hoop", "paint2", bevel=0.005)
    g = Geo()
    for s in (1, -1):
        for dx in (-0.04, 0.04):
            bolt(g, (x + dx, s * y, RAIL + 0.01), (0, 0, 1), 0.007, 0.004)
        for zz in (1.30, 1.50, 1.68):
            bolt(g, (x - 0.035, s * y, zz), (-1, 0, 0), 0.007, 0.004)
    g.obj("hoop.bolts", "rim_bright")
    g, gw = Geo(), Geo()
    for s in (1, -1):
        a = V3((RACK_A.x, s * RACK_A.y, RACK_A.z))
        b = V3((RACK_B.x, s * RACK_B.y, RACK_B.z))
        tube(g, a + RACK_T * 0.02, b, 0.022, 10)
        tube(g, b, (b.x, b.y, RAIL - 0.01), 0.022, 10)
        g.box((b.x, b.y, RAIL + 0.004), (0.09, 0.09, 0.012))
        tube(g, b + V3((0, 0, 0.014)), b - V3((0, 0, 0.014)), 0.03, 10)
        # a web plate in the corner between the hoop's leg and the rail
        d = (b - a).normalized()
        p0, p1, p2 = a + d * 0.03 - V3((0, 0, 0.026)), a + d * 0.03 - V3((0, 0, 0.30)), \
            a + d * 0.46 - V3((0, 0, 0.024))
        side = V3((0, s, 0))
        gw.prism([p0 - side * 0.005, p1 - side * 0.005, p2 - side * 0.005], side * 0.01)
    for dx in (0.25, -0.25):                            # the cradle's cross bars
        xc = SPARE_X + dx * RACK_T.x
        z, yr = rack_at(xc)
        tube(g, (xc, -yr, z), (xc, yr, z), 0.022, 10)
    for sy in (-0.12, 0.12):                            # two bearers under the hub
        a = V3((SPARE_X + 0.25 * RACK_T.x, sy, rack_at(SPARE_X + 0.25 * RACK_T.x)[0]))
        b = V3((SPARE_X - 0.25 * RACK_T.x, sy, rack_at(SPARE_X - 0.25 * RACK_T.x)[0]))
        tube(g, a, b, 0.016, 4, phase=pi / 4)
    g.obj("rack", "paint2", bevel=0.002)
    gw.obj("rack.webs", "paint", bevel=0.002)


def build_spare():
    """The spare lies on the rack's cross bars, its face up and to the rear, held down by a
    hand wheel on a stud through its hub and a strap across."""
    n0 = len(K.CAR.objects)
    build_wheel("spare", 0, 1, loc=tuple(SPARE_C))
    # the wheel's axle (its own y, the outer face) onto the rack's way up
    R = V3((0, 1, 0)).rotation_difference(RACK_N).to_matrix()
    for ob in list(K.CAR.objects)[n0:]:
        ob.rotation_euler = R.to_euler()
    hw = T_W / 2
    g = Geo()
    top = SPARE_C + RACK_N * (hw - 0.06)
    tube(g, SPARE_C - RACK_N * (hw + 0.02), top + RACK_N * 0.05, 0.012, 8)
    K.stud(g, top + RACK_N * 0.012, RACK_N,
           [(0.0, 0.002), (0.0, 0.07), (0.01, 0.075), (0.02, 0.07), (0.02, 0.03), (0.036, 0.022),
            (0.036, 0.002)], 6)
    g.obj("spare.clamp", "caliper", bevel=0.002)
    g = Geo()                               # the strap: over the tire, down to both rails
    z, yr = rack_at(SPARE_X)
    h1, h2 = 0.024 + 0.006 + T_W + 0.012, 0.10
    base = V3((SPARE_X, 0, z))
    pts = []
    for sy, h in ((-yr, 0.0), (-T_R - 0.03, h2), (-T_R + 0.02, h1), (T_R - 0.02, h1),
                  (T_R + 0.03, h2), (yr, 0.0)):
        pts.append(base + V3((0, sy, 0)) + RACK_N * h)
    g.sweep(pts, [(-0.002, -0.022), (0.002, -0.022), (0.002, 0.022), (-0.002, 0.022)],
            up=[RACK_T] * len(pts))
    g.obj("spare.strap", "hazard", bevel=0.0008)
    g = Geo()
    q = base + V3((0, T_R + 0.012, 0)) + RACK_N * (h2 + 0.07)
    g.box(q, (0.05, 0.018, 0.06))
    g.obj("spare.ratchet", "rim", bevel=0.003)


# ---------------------------------------------------------------------------------------
# bolts and lettering
# ---------------------------------------------------------------------------------------
def build_bolts():
    """Rows of bolt heads on the body as built."""
    def row(pts, proj, r=0.012, h=0.006):
        for u, v in pts:
            loc, n = on_body(u, v, proj)
            if loc is not None:
                bolt(BOLTS, loc, n, r, h)
    row([(1.56 - k * 0.15, 0.345) for k in range(5)], 'z')               # hood edges
    row([(1.585, 0.07 + k * 0.13) for k in range(2)], 'z')
    row([(1.55 - k * 0.14, 1.02) for k in range(5)], 'y')                # nose side plate
    row([(0.44 - k * 0.20, 0.47) for k in range(6)], 'z')                # roof plate
    row([(-0.60, 0.07 + k * 0.14) for k in range(3)], 'z')
    row([(0.56 - k * 0.155, 0.58) for k in range(8)], 'y')               # sill
    row([(-0.615, 0.74 + k * 0.12) for k in range(3)], 'y')              # quarter
    row([(-0.475, 0.98), (-0.475, 1.04)], 'y')
    row([(0.725, 0.80 + k * 0.12) for k in range(3)], 'y')               # hinge post
    row([(-0.48, 1.30 + k * 0.105) for k in range(4)], 'y', 0.009, 0.005)   # pillar
    row([(-0.62, 1.30 + k * 0.105) for k in range(4)], 'y', 0.009, 0.005)
    row([(0.70 + 0.022 * k, 1.34 + 0.1 * k) for k in range(4)], 'y', 0.009, 0.005)  # corner post
    row([(0.43, 0.72 + k * 0.12) for k in range(4)], 'X')                # tailgate edges
    row([(TUB_X0 - 0.14 - k * 0.20, TUB_Y - 0.06) for k in range(5)], 'z')     # tub rail
    row([(0.60, 1.30 + k * 0.10) for k in range(4)], 'X', 0.009, 0.005)  # cab back
    row([(0.20 + k * 0.20, 0.80) for k in range(2)], 'X')
    BOLTS.obj("bolts", "rim_bright", mirror=True)


def build_lettering():
    g = Geo()                               # light stencils on the paint
    for side in (1, -1):
        stencil(g, NUM, 0.215, on_side(0.33, 0.93, side))
        stencil(g, "BURRO", 0.08, on_side(-0.13, 0.945, side))
        stencil(g, "BRAKK INDUSTRIAL", 0.026, on_side(-0.13, 0.885, side), gap=0.2, cut=0)
        d = (V3((RACK_B.x, side * RACK_B.y, RACK_B.z)) - V3((RACK_A.x, side * RACK_A.y, RACK_A.z)))
        d.z = 0
        d.normalize()
        o = V3((RACK_A.x, side * RACK_A.y, RACK_A.z)) + d * 0.165 + V3((0, side * 0.0056, -0.125))
        stencil(g, "B-" + NUM, 0.075, on_plane(o, d if side > 0 else -d, (0, 0, 1)))
        stencil(g, "FILL", 0.02, on_side(FLAP[0], FLAP[1] + 0.085, side), gap=0.2, cut=0)
    stencil(g, "BRAKK", 0.17, on_plane((TUB_X1 - 0.0008, 0, 0.895), (0, -1, 0), (0, 0, 1)),
            gap=0.16)
    stencil(g, NUM, 0.26, on_plane((1.29, 0, HOOD + 0.0105), (0, 1, 0), (-1, 0, 0)))
    g.obj("lettering", "decal")
    g = Geo()                               # light markings on the dark parts
    stencil(g, "BRAKK", 0.05, on_plane((1.7545, 0, 0.995), (0, 1, 0), (0, 0, 1)), gap=0.2)
    stencil(g, "WINCH 3T", 0.028, on_plane((1.9305, 0.34, 0.672), (0, 1, 0), (0, 0, 1)),
            gap=0.2, cut=0)
    stencil(g, "BK 2-1409", 0.05, on_plane((TUB_X1 - 0.1405, 0, 0.585), (0, -1, 0), (0, 0, 1)),
            gap=0.18, cut=0)
    upf = V3((-0.14, 0, 0.19)).normalized()
    for s in (1, -1):                       # the unit number on the front fender slopes
        stencil(g, NUM, 0.15, on_plane(V3((1.69, s * 0.77, 0.895)) + V3((0.80, 0, 0.59)) * 0.001,
                                       (0, 1, 0), upf))
    g.obj("markings", "mark")
    g = Geo()                               # hazard stripes on the bumpers
    for s in (1, -1):
        d = V3((-0.13, s * 0.49, 0)).normalized()
        chevrons(g, on_plane((1.865, s * 0.705, 0.652), d * s, (0, 0, 1)), 0.40, 0.065, 5,
                 s * 0.05)
        chevrons(g, on_plane((TUB_X1 - 0.1405, s * 0.59, 0.54), (0, -1, 0), (0, 0, 1)), 0.34,
                 0.10, 5, -s * 0.07)
    g.obj("chevrons", "hazard")


# ---------------------------------------------------------------------------------------
# suspension and driveline
# ---------------------------------------------------------------------------------------
def build_chassis():
    g, gs = Geo(), Geo()
    x = FA_X
    yu = T_OUT - T_W + 0.05                 # the upright, inside the rim
    # front: double wishbones, upright, tie rod, half shaft
    for xi in (x - 0.18, x + 0.18):
        tube(g, (xi, 0.30, 0.50), (x, yu - 0.005, 0.335), 0.022, 4, phase=pi / 4)
        tube(g, (xi - 0.04 * (1 if xi < x else -1), 0.45, 0.66), (x, yu - 0.015, 0.525), 0.019, 4,
             phase=pi / 4)
    g.box((x, yu, 0.43), (0.09, 0.05, 0.26))
    tube(g, (x + 0.09, 0.36, 0.55), (x + 0.07, yu - 0.03, 0.47), 0.011)      # tie rod
    tube(g, (x, 0.30, 0.48), (x, yu, T_R), 0.022, 10)
    tube(g, (x, 0.36, 0.475), (x, 0.44, 0.465), 0.042, 10, r2=0.026)
    coil(g, gs, (x, 0.585, 0.39), (x, 0.50, 0.965), 0.018)
    g.box((x, 0, 0.50), (0.50, 0.62, 0.07))             # the subframe
    # rear: a beam axle with its housing, trailing links, dampers
    x = RA_X
    tube(g, (x, 0.0, T_R), (x, yu, T_R), 0.05, 10)
    tube(g, (-0.62, 0.44, 0.54), (x, 0.52, 0.40), 0.026, 4, phase=pi / 4)
    tube(g, (-0.66, 0.24, 0.60), (x, 0.20, 0.51), 0.02, 4, phase=pi / 4)
    coil(g, gs, (x - 0.03, 0.47, 0.44), (x + 0.07, 0.40, 0.72), 0.018)
    g.obj("chassis", "rim", bevel=0.003, mirror=True)
    gs.obj("springs", "caliper", bevel=0.004, mirror=True)
    g = Geo()
    g.lathe([(-0.12, 0.05), (-0.085, 0.13), (0.085, 0.13), (0.12, 0.05)], 10,
            xf=Matrix.Translation((x, 0, T_R)))
    g.lathe([(-0.01, 0.004), (-0.01, 0.10), (0.03, 0.09), (0.05, 0.055), (0.05, 0.004)], 10,
            xf=Matrix.Translation((x - 0.12, 0, T_R)) @ Matrix.Rotation(pi / 2, 4, 'Z'))
    tube(g, (x + 0.11, 0, T_R + 0.01), (-0.50, 0, 0.55), 0.028, 10)
    g.obj("driveline", "rim", bevel=0.004)


# ---------------------------------------------------------------------------------------
# interior
# ---------------------------------------------------------------------------------------
def build_interior():
    g = Geo()
    g.box((0.04, 0, 0.545), (1.32, 1.20, 0.04))
    g.prism([(0.735, -0.66, 0.90), (0.735, -0.66, BELT - 0.03), (0.60, -0.66, BELT - 0.015),
             (0.50, -0.66, 1.13), (0.54, -0.66, 0.90)], (0, 1.32, 0))
    g.box((0.05, 0, 0.70), (0.80, 0.20, 0.28))
    g.obj("interior.tub", "interior", bevel=0.006)
    g = Geo()
    tf = Matrix.Rotation(rad(-12), 3, 'Y')
    for y in (0.37, -0.37):
        g.box((0.0, y, 0.83), (0.48, 0.48, 0.14))
        g.box((-0.285, y, 1.17), (0.12, 0.46, 0.62), rot=tf)
        g.box((-0.365, y, 1.575), (0.08, 0.25, 0.17), rot=tf)
        for s in (-1, 1):
            g.box((0.0, y + s * 0.245, 0.86), (0.44, 0.05, 0.16))
            g.box((-0.265, y + s * 0.225, 1.15), (0.14, 0.05, 0.50), rot=tf)
    g.obj("interior.seats", "seat", bevel=0.014, segs=3)
    g = Geo()
    wheel = (Matrix.Translation((0.40, 0.37, 1.20)) @ Matrix.Rotation(rad(-62), 4, 'Y')
             @ Matrix.Rotation(pi / 2, 4, 'X'))
    g.lathe([(-0.014, 0.175), (0.0, 0.19), (0.014, 0.175), (0.0, 0.16)], 24, xf=wheel)
    g.box((0.49, 0.37, 1.16), (0.22, 0.06, 0.06), rot=Matrix.Rotation(rad(-28), 3, 'Y'))
    for a in (30, 150, 270):
        tube(g, wheel @ V3((0, -0.02, 0)), wheel @ V3((0.17 * cos(rad(a)), 0, 0.17 * sin(rad(a)))),
             0.012, 6)
    tube(g, (0.20, 0.05, 0.84), (0.26, 0.05, 1.06), 0.012, 8)       # the shifter and its knob
    tube(g, (0.26, 0.05, 1.05), (0.265, 0.05, 1.10), 0.024, 8)
    tube(g, (0.02, -0.05, 0.84), (-0.12, -0.05, 0.96), 0.012, 8)    # the hand brake
    g.obj("interior.wheel", "interior", sharp=40)
    g = Geo()
    scr = Matrix.Rotation(rad(-22), 3, 'Y')
    g.box((0.535, 0.0, 1.185), (0.008, 0.30, 0.14), rot=scr)
    g.box((0.565, 0.37, 1.245), (0.008, 0.22, 0.06), rot=scr)
    g.obj("interior.screens", "screen")


# ---------------------------------------------------------------------------------------
# views of its own, and the build
# ---------------------------------------------------------------------------------------
K.VIEWS["hero"].update(dir=(1.0, 0.72, 0.24), lens=58, focus=(1.4, 0.8, 0.8))
K.VIEWS["rear"].update(dir=(-1.0, -0.74, 0.42), focus=(-1.4, -0.7, 0.9))
K.VIEWS["back"].update(dir=(-1.0, 0.0, 0.16))
K.VIEWS.update(
    nose=dict(dir=(1.0, 0.5, 0.16), lens=85, target=(1.6, 0.3, 0.95), dist=3.6),
    cab=dict(dir=(0.9, 1.0, 0.25), lens=85, target=(0.4, 0.5, 1.35), dist=4.0),
    tail=dict(dir=(-1.0, 0.6, 0.5), lens=70, target=(-1.2, 0, 1.2), dist=4.5),
    rack=dict(dir=(-0.4, 1.0, 0.35), lens=85, target=(-1.1, 0.3, 1.25), dist=4.2),
    rside=dict(dir=(-0.3, -1.0, 0.2), lens=85, target=(-0.4, -0.5, 1.2), dist=4.0),
)


def main():
    K.materials(paint=(0.18, 0.025, 0.015), paint_finish=(0.0, 0.42, 0.4),
                paint2=(0.035, 0.038, 0.042), paint2_finish=(0.35, 0.52, 0.0),
                dust=(0.25, 0.20, 0.15), dust_amount=0.42, dust_z=(0.40, 0.92),
                glass=(0.33, 0.37, 0.39),
                led_front=(1.0, 0.88, 0.66), led_accent=(1.0, 0.42, 0.03),
                caliper=(0.86, 0.52, 0.02), seat=(0.17, 0.12, 0.07),
                decal=(0.80, 0.78, 0.70), screen=(1.0, 0.62, 0.16))
    K.pbr("plate", (0.22, 0.225, 0.23), 1.0, 0.5)           # bare tread plate
    K.pbr("liner", (0.03, 0.03, 0.032), 0.0, 0.85)          # the tub's sprayed lining
    K.pbr("mark", (0.80, 0.78, 0.70), 0.0, 0.5)             # markings on the dark parts
    K.pbr("hazard", (0.86, 0.52, 0.02), 0.0, 0.5)           # hazard stripes, straps
    K.pbr("can", (0.16, 0.17, 0.10), 0.0, 0.55)             # the fuel cans
    K.pbr("tiremark", (0.085, 0.085, 0.085), 0.0, 0.6)
    build_hull()
    K.log("hull and tub")
    build_fenders()
    build_lights()
    build_bumpers()
    build_nose()
    build_frames()
    build_cab()
    build_snorkel()
    build_stack()
    build_tub()
    build_rack()
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
    # one-sided by design: the raised intake, the exhaust stack and the antenna, the driver's
    # wheel, levers and screens, both wipers parked to the left, the winch hook hung off its
    # rollers, the spare's parts (its lettering and lugs run one way round), its clamp, strap
    # and ratchet, the cans' caps, the tread plate's lozenges leaning in turn
    K.meant("symmetry", "snorkel*", "stack*", "antenna", "interior.wheel", "interior.screens",
            "wipers", "wiper.blades", "hooks", "winch.rollers", "tub.tread", "tire.spare",
            "tiretext.spare", "rim.spare", "rimholes.spare", "hub.spare", "drum.spare",
            "spare.*", "cans.caps")
    K.cabin_light((0.0, 0, 1.70), power=5.0, size=0.4)
    K.shoot(extra=[dict(view="rear", size=(900, 430), corner="tl"),
                   dict(view="top", size=(820, 390), corner="tr")])


main()
