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
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import bmesh                                                        # noqa: E402
import carkit as K                                                  # noqa: E402
from carkit import Geo, Matrix, V3, cos, hypot, on_body, pi, rad, sin, stud    # noqa: E402

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

# ---------------------------------------------------------------------------------------
# small helpers of this car
# ---------------------------------------------------------------------------------------


def tube(g, a, b, r, n=8, r2=None, phase=0.0):
    """A straight bar of n sides from a to b (n = 4 with phase pi / 4: a box tube)."""
    a, b = V3(a), V3(b)
    t = (b - a).normalized()
    ref = V3((0, 0, 1)) if abs(t.z) < 0.9 else V3((1, 0, 0))
    u = t.cross(ref).normalized()
    v = t.cross(u)
    r2 = r if r2 is None else r2
    ring = [(u * cos(phase + 2 * pi * k / n) + v * sin(phase + 2 * pi * k / n)) for k in range(n)]
    pts = [a + d * r for d in ring] + [b + d * r2 for d in ring]
    faces = [tuple(range(n)), tuple(range(n, 2 * n))]
    faces += [(k, (k + 1) % n, n + (k + 1) % n, n + k) for k in range(n)]
    g.add(pts, faces)


def bolt(g, loc, n, r=0.012, h=0.006):
    """A hex bolt head on a surface point."""
    stud(g, loc, V3(n).normalized(), [(-0.001, 0.001), (-0.001, r), (h, r), (h, 0.001)], 6)


def under(pts, th):
    """An (x, z) polyline running front to rear, moved th toward the wheel under it."""
    ns = []
    for a, b in zip(pts, pts[1:]):
        dx, dz = b[0] - a[0], b[1] - a[1]
        L = hypot(dx, dz)
        ns.append((-dz / L, dx / L))
    out = []
    for i, p in enumerate(pts):
        if i == 0:
            n = ns[0]
        elif i == len(pts) - 1:
            n = ns[-1]
        else:
            a, b = ns[i - 1], ns[i]
            k = 1 + a[0] * b[0] + a[1] * b[1]
            n = ((a[0] + b[0]) / k, (a[1] + b[1]) / k)
        out.append((p[0] + n[0] * th, p[1] + n[1] * th))
    return out


def plate(g, pts, th, y0, y1):
    """A bent plate: the (x, z) polyline pts, th thick, from y0 to y1."""
    lo = under(pts, th)
    poly = [(x, y0, z) for x, z in pts] + [(x, y0, z) for x, z in lo[::-1]]
    g.prism(poly, (0, y1 - y0, 0))


def on_side(x0, z0, side):
    """place() for lettering on the body's flank, middle at (x0, z0)."""
    proj = 'y' if side > 0 else 'Y'

    def place(px, py, lift):
        loc, n = on_body(x0 - side * px, z0 + py, proj)
        return None if loc is None else loc + n * lift
    return place


def on_plane(origin, right, up):
    """place() for lettering on a plane, reading along right."""
    o, r, u = V3(origin), V3(right), V3(up)
    n = r.cross(u).normalized()
    return lambda px, py, lift: o + r * px + u * py + n * lift


HCUT = set("TIY1")


def cut_glyph(vs, fs, axis, lo, hi):
    """A flat glyph without the band lo..hi along axis (0 across, 1 up): a stencil's bridge."""
    out_v, out_f = [], []
    for low in (True, False):
        bm = bmesh.new()
        bv = [bm.verts.new(v) for v in vs]
        for f in fs:
            bm.faces.new([bv[i] for i in f])
        co, no = V3(), V3()
        co[axis] = lo if low else hi
        no[axis] = 1.0
        bmesh.ops.bisect_plane(bm, geom=bm.verts[:] + bm.edges[:] + bm.faces[:], plane_co=co,
                               plane_no=no, clear_outer=low, clear_inner=not low)
        bm.verts.index_update()
        o = len(out_v)
        out_v += [v.co.copy() for v in bm.verts]
        out_f += [tuple(o + v.index for v in f.verts) for f in bm.faces]
        bm.free()
    return out_v, out_f


def stencil(g, txt, size, place, gap=0.13, cut=0.085):
    """Stencilled capitals: every letter is cut through by a bridge of width cut * size
    (upright, or level for T, I, Y, 1); cut 0 leaves small print whole."""
    glyphs = []
    x = 0.0
    for ch in txt:
        if ch == " ":
            x += size * 0.36
            continue
        vs, fs = K.text_mesh(ch, size)
        x0, x1 = min(v.x for v in vs), max(v.x for v in vs)
        if cut and ch != "-":
            if ch in HCUT:
                cy = (min(v.y for v in vs) + max(v.y for v in vs)) / 2
                vs, fs = cut_glyph(vs, fs, 1, cy - size * cut / 2, cy + size * cut / 2)
            else:
                xm, hb = (x0 + x1) / 2, size * cut / 2
                vs, fs = cut_glyph(vs, fs, 0, xm - hb, xm + hb)
        glyphs.append((vs, fs, x - x0))
        x += (x1 - x0) + size * gap
    W = x - size * gap
    for vs, fs, dx in glyphs:
        pts = [place(v.x + dx - W / 2, v.y, 0.0012) for v in vs]
        if all(p is not None for p in pts):
            g.add(pts, fs)
    return W


def chevrons(g, place, W, H, n, lean):
    """Hazard stripes: n leaning bars over a W x H field."""
    pitch = (W - abs(lean)) / n
    for k in range(n):
        u0 = -W / 2 + k * pitch + max(0.0, -lean)
        q = [(u0, -H / 2), (u0 + pitch / 2, -H / 2), (u0 + pitch / 2 + lean, H / 2),
             (u0 + lean, H / 2)]
        g.add([place(u, v, 0.0015) for u, v in q], [(0, 1, 2, 3)])


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
                trim="cladding", nose="cladding", cabback="paint")


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


def build_hull():
    hull = K.build_body(hull_stations(), hull_panel, HULL_MAT, 1.0, 1.0, name="hull",
                        front=dict(kind="flat", panel="nose"),
                        rear=dict(kind="flat", panel="cabback"),
                        glass=[("glass_ws", 0.055), ("glass_f", 0.05), ("glass_r", 0.05)],
                        subdiv=2, gap=0.004)
    rows = [bed_row(-1.06, BED_Y, True), bed_row(-1.11, BED_Y, True),
            bed_row(-1.13, BED_Y, False), bed_row(-2.57, BED_Y, False),
            bed_row(-2.60, BED_Y - 0.03, False, 0.59), bed_row(-2.62, BED_Y - 0.05, True, 0.59),
            bed_row(-2.70, BED_Y - 0.13, True, 0.51)]
    bed = K.build_body(rows, bed_panel, BED_MAT, 1.0, 1.0, name="bed",
                       front=dict(kind="flat", panel="bedfront"),
                       rear=dict(kind="flat", panel="tailgate"), subdiv=2, gap=0.004)
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
                      (x - 0.012, y0 - 0.03, FEN_Z - 0.22)], (0.024, 0, 0))
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


def pylon(g, gl, ga, x, y, z0, z1, yaw):
    """A light pylon on a chamfered corner: a housing, its bar and an amber cell at the
    bar's foot, facing yaw (degrees)."""
    R = Matrix.Rotation(rad(yaw), 3, 'Z')
    n = R @ V3((1, 0, 0))
    c = V3((x, y, (z0 + z1) / 2))
    g.box(c + n * 0.018, (0.06, 0.10, z1 - z0), rot=R)
    gl.box(c + n * 0.050 + V3((0, 0, 0.045)), (0.012, 0.05, z1 - z0 - 0.16), rot=R)
    ga.box(V3((x, y, z0 + 0.07)) + n * 0.050, (0.012, 0.05, 0.06), rot=R)
    for z in (z0 + 0.018, z1 - 0.018):
        for s in (-0.03, 0.03):
            p = c + n * 0.048 + (R @ V3((0, s, 0)))
            p.z = z
            bolt(BOLTS, p, n, 0.007, 0.004)


def build_lights():
    g, gf, gr, ga = Geo(), Geo(), Geo(), Geo()
    pylon(g, gf, ga, 2.44, 0.50, 0.71, 1.17, 45)
    pylon(g, gr, ga, -2.635, BED_Y - 0.065, 0.90, 1.37, 135)
    ga.obj("led.turn", "led_accent", mirror=True)
    g.obj("pylons", "cladding", bevel=0.004, mirror=True)
    gf.obj("led.front", "led_front", mirror=True)
    gr.obj("led.rear", "led_rear", mirror=True)
    # the bar over the windshield: a housing on the roof's front edge, eight cells
    g = Geo()
    g.prism([(0.70, -0.70, ROOF - 0.01), (0.70, -0.70, ROOF + 0.065), (0.56, -0.70, ROOF + 0.065),
             (0.50, -0.70, ROOF - 0.01)], (0, 1.40, 0))
    for k in range(9):
        y = -0.64 + 1.28 * k / 8
        g.box((0.704, y, ROOF + 0.028), (0.012, 0.016, 0.05))
    g.obj("roofbar", "cladding", bevel=0.004)
    g = Geo()
    g.box((0.701, 0, ROOF + 0.028), (0.006, 1.27, 0.036))
    g.obj("led.roofbar", "led_front")
    g = Geo()                                           # amber clearance lamps at its ends
    g.box((0.63, 0.704, ROOF + 0.03), (0.07, 0.006, 0.03))
    g.obj("led.clear", "led_accent", mirror=True)
    # work lamps on the sail frame's crossbar, a stop strip over the rear window
    g = Geo()
    for y in (0.34, -0.34):
        g.box((-1.165, y, ROOF - 0.005), (0.008, 0.13, 0.05))
    g.obj("led.work", "lamp")
    g = Geo()
    g.box((-1.012, 0, 1.795), (0.012, 0.50, 0.022))
    g.obj("led.stop", "led_rear")


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
    g = Geo()
    for y0 in (0.07, -0.43):
        blade = []
        for k in range(7):
            t = k / 6
            loc, n = on_body(y0 + 0.40 * t, 1.345 + 0.33 * t, 'x')
            blade.append(loc + n * 0.016)
        g.sweep(blade, [(-0.005, -0.009), (0.005, -0.009), (0.005, 0.007), (-0.005, 0.007)],
                up=(1, 0, 0.5))
        piv, n = on_body(y0 + 0.02, 1.30, 'x')
        tube(g, piv + n * 0.012, blade[3] + n * 0.012, 0.006, 6)
    tube(g, (-0.70, 0.50, ROOF), (-0.76, 0.50, ROOF + 0.20), 0.006, 6, r2=0.003)
    g.box((-0.70, 0.50, ROOF + 0.008), (0.06, 0.06, 0.02))
    g.obj("wipers", "cladding", bevel=0.001)
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
    row([(-0.925, 0.92 + k * 0.10) for k in range(4)], 'y')              # quarter
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
def coil(g, gs, a, b, r=0.02):
    """A damper from a to b with a spring round its upper two thirds."""
    a, b = V3(a), V3(b)
    tube(g, a, b, r, 10)
    tube(g, a.lerp(b, 0.25), a.lerp(b, 0.30), 0.055, 12)
    tube(g, a.lerp(b, 0.90), a.lerp(b, 0.94), 0.055, 12)
    for k in range(8):
        t = 0.32 + 0.57 * k / 8
        tube(gs, a.lerp(b, t), a.lerp(b, t + 0.035), 0.05, 12)


def build_chassis():
    g, gs = Geo(), Geo()
    x = FA_X
    # front: double wishbones, upright, tie rod, half shaft
    for xi in (x - 0.19, x + 0.19):
        tube(g, (xi, 0.38, 0.50), (x, 0.80, 0.33), 0.024, 4, phase=pi / 4)
        tube(g, (xi - 0.03 * (1 if xi < x else -1), 0.50, 0.86), (x, 0.79, 0.63), 0.02, 4,
             phase=pi / 4)
    g.box((x, 0.805, 0.47), (0.10, 0.05, 0.36))
    tube(g, (x + 0.16, 0.40, 0.60), (x + 0.15, 0.79, 0.52), 0.012)
    tube(g, (x, 0.36, 0.50), (x, 0.80, 0.45), 0.026, 10)
    tube(g, (x, 0.42, 0.495), (x, 0.50, 0.485), 0.05, 10, r2=0.03)
    coil(g, gs, (x, 0.66, 0.39), (x, 0.56, 1.0))
    # rear: a beam axle with its housing, trailing links, dampers, the shaft
    x = RA_X
    tube(g, (x, 0.0, T_R), (x, 0.80, T_R), 0.055, 10)
    tube(g, (-0.95, 0.52, 0.52), (x, 0.60, 0.40), 0.026, 4, phase=pi / 4)
    tube(g, (-0.95, 0.30, 0.60), (x, 0.24, 0.52), 0.02, 4, phase=pi / 4)
    coil(g, gs, (x - 0.02, 0.675, 0.43), (x + 0.10, 0.665, 0.99), 0.018)
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
# wheels: a lugged tire on a dished steel rim with a bolted bead ring
# ---------------------------------------------------------------------------------------
N_LUG = 22
TIRE_TEXT = "BRAKK  TRAKTOR  M/T    37 X 12.5 R19    "


def build_wheel(tag, cx, side, loc=None, yaw=0.0):
    R, w, Rr = T_R, T_W, T_RIM
    hw = w / 2
    flip = side < 0
    loc = (cx, side * (T_OUT - hw), R) if loc is None else loc
    n0 = len(K.CAR.objects)
    Rb = R - 0.024
    half = [(0.0, Rb), (hw - 0.035, Rb), (hw - 0.008, Rb - 0.018), (hw + 0.010, R - 0.057),
            (hw + 0.018, R - 0.08), (hw + 0.018, Rr + 0.07), (hw + 0.010, Rr + 0.032),
            (hw + 0.004, Rr + 0.012), (hw - 0.010, Rr + 0.004), (hw - 0.03, Rr - 0.006)]
    g = Geo()
    g.lathe([(-y, r) for y, r in half[:0:-1]] + half, 88)

    def pt(th, t, y, r):
        a = th + t / R
        return (r * cos(a), y, r * sin(a))
    for k in range(N_LUG):
        th = 2 * pi * k / N_LUG
        for sg, off in ((1, 0.0), (-1, 0.5)):                   # shoulder lugs with side biters
            t0 = (off - 0.30) * 2 * pi * R / N_LUG
            t1 = t0 + 0.085
            sk = 0.035
            yi, yo = sg * 0.042, sg * (hw + 0.006)
            ys = sg * (hw + 0.024)
            g.hexa([pt(th, t0, yi, Rb - 0.01), pt(th, t1, yi, Rb - 0.01),
                    pt(th, t1 - sk, ys, R - 0.085), pt(th, t0 - sk, ys, R - 0.085),
                    pt(th, t0, yi, R), pt(th, t1, yi, R),
                    pt(th, t1 - sk, yo, R - 0.012), pt(th, t0 - sk, yo, R - 0.012)])
        for off in (0.22, 0.72):                                # the middle row
            t0 = (off - 0.2) * 2 * pi * R / N_LUG
            t1 = t0 + 0.045
            g.hexa([pt(th, t0, -0.03, Rb - 0.01), pt(th, t1, -0.03, Rb - 0.01),
                    pt(th, t1 + 0.012, 0.03, Rb - 0.01), pt(th, t0 + 0.012, 0.03, Rb - 0.01),
                    pt(th, t0, -0.03, R), pt(th, t1, -0.03, R),
                    pt(th, t1 + 0.012, 0.03, R), pt(th, t0 + 0.012, 0.03, R)])
    ob = g.obj("tire." + tag, "rubber", flip_y=flip, loc=loc)
    ob.data.shade_smooth()
    ob.data.set_sharp_from_angle(angle=rad(30))
    # sidewall lettering, reading the right way round on both sides
    g = Geo()
    rt = (R - 0.08 + Rr + 0.07) / 2
    sgn = 1 if not flip else -1
    a = rad(90) - sgn * 0.5
    for rep in range(2):
        for ch in TIRE_TEXT:
            if ch == " ":
                a += sgn * 0.022 / rt
                continue
            vs, fs = K.text_mesh(ch, 0.062)
            x0, x1 = min(v.x for v in vs), max(v.x for v in vs)
            adv = (x1 - x0) + 0.008
            am = a + sgn * (adv / 2) / rt
            rad_ = V3((cos(am), 0, sin(am)))
            rgt = V3((-sin(am), 0, cos(am))) * sgn
            o = rad_ * rt + V3((0, hw + 0.0195, 0))
            g.add([o + rgt * (v.x - (x0 + x1) / 2) + rad_ * v.y for v in vs], fs)
            a += sgn * adv / rt
        a = rad(270) - sgn * 0.5
    g.obj("tiretext." + tag, "tiremark", flip_y=flip, loc=loc)
    # rim: barrel, a deep dish with eight round windows, the hub
    g = Geo()
    g.lathe([(-hw + 0.03, Rr), (hw - 0.012, Rr), (hw - 0.012, Rr - 0.014),
             (-hw + 0.03, Rr - 0.014)], 56)
    y_a, r_a, y_b, r_b = hw - 0.045, Rr - 0.014, hw - 0.115, 0.105
    g.lathe([(y_a, r_a), (y_b, r_b), (y_b - 0.014, r_b), (y_a - 0.014, r_a)], 56)
    g.lathe([(hw - 0.135, 0.004), (hw - 0.135, 0.108), (hw - 0.092, 0.108), (hw - 0.08, 0.092),
             (hw - 0.08, 0.004)], 16)
    g.obj("rim." + tag, "rim", bevel=0.004, flip_y=flip, loc=loc)
    gv, gbr = Geo(), Geo()
    L = hypot(y_b - y_a, r_b - r_a)
    ny, nr = -(r_b - r_a) / L, (y_b - y_a) / L                  # the dish's normal, outward
    for k in range(8):
        a = 2 * pi * (k + 0.5) / 8
        s = 0.47
        y, r = y_a + (y_b - y_a) * s, r_a + (r_b - r_a) * s
        stud(gv, V3((r * cos(a), y, r * sin(a))), V3((nr * cos(a), ny, nr * sin(a))).normalized(),
             [(-0.004, 0.001), (-0.004, 0.027), (0.0012, 0.027), (0.0012, 0.001)], 14)
        an = 2 * pi * k / 8
        gbr.lathe([(hw - 0.081, 0.002), (hw - 0.081, 0.0125), (hw - 0.06, 0.0125),
                   (hw - 0.06, 0.002)], 6,
                  xf=Matrix.Translation((0.07 * cos(an), 0, 0.07 * sin(an))))
    gv.obj("rimholes." + tag, "void", flip_y=flip, loc=loc)
    gbr.lathe([(hw - 0.081, 0.004), (hw - 0.081, 0.048), (hw - 0.04, 0.044), (hw - 0.032, 0.03),
               (hw - 0.032, 0.004)], 8)
    gbr.lathe([(hw - 0.016, Rr - 0.032), (hw - 0.016, Rr + 0.015), (hw + 0.001, Rr + 0.015),
               (hw + 0.001, Rr - 0.032)], 56)
    for k in range(16):
        a = 2 * pi * (k + 0.5) / 16
        rr = Rr - 0.009
        gbr.lathe([(hw, 0.001), (hw, 0.0085), (hw + 0.007, 0.0085), (hw + 0.007, 0.001)], 6,
                  xf=Matrix.Translation((rr * cos(a), 0, rr * sin(a))))
    gbr.obj("hub." + tag, "rim_bright", bevel=0.0015, flip_y=flip, loc=loc)
    g = Geo()
    g.lathe([(-hw + 0.05, 0.004), (-hw + 0.05, Rr - 0.014), (-hw + 0.035, Rr - 0.014),
             (-hw + 0.035, 0.004)], 32)
    g.obj("drum." + tag, "well", flip_y=flip, loc=loc)
    for ob in list(K.CAR.objects)[n0:]:
        ob.rotation_euler = (0, 0, yaw)


# ---------------------------------------------------------------------------------------
# interior
# ---------------------------------------------------------------------------------------
def build_interior():
    g = Geo()
    g.box((0.0, 0, 0.535), (1.92, 1.56, 0.04))
    g.box((-0.955, 0, 1.0), (0.04, 1.6, 0.92))
    g.prism([(1.02, -0.82, 0.86), (1.02, -0.82, 1.265), (0.80, -0.82, 1.265), (0.68, -0.82, 1.17),
             (0.72, -0.82, 0.86)], (0, 1.64, 0))
    g.box((0.20, 0, 0.72), (0.9, 0.22, 0.36))
    g.obj("interior.tub", "interior", bevel=0.006)
    g = Geo()
    tf, tr = Matrix.Rotation(rad(-12), 3, 'Y'), Matrix.Rotation(rad(-8), 3, 'Y')
    for y in (0.43, -0.43):
        g.box((0.22, y, 0.83), (0.50, 0.50, 0.14))
        g.box((-0.075, y, 1.18), (0.12, 0.48, 0.64), rot=tf)
        g.box((-0.155, y, 1.60), (0.08, 0.26, 0.17), rot=tf)
        g.box((-0.875, y, 1.585), (0.08, 0.26, 0.17), rot=tr)
        for s in (-1, 1):
            g.box((0.22, y + s * 0.255, 0.86), (0.46, 0.05, 0.16))
    g.box((-0.56, 0, 0.83), (0.46, 1.50, 0.14))
    g.box((-0.82, 0, 1.17), (0.12, 1.50, 0.60), rot=tr)
    g.obj("interior.seats", "seat", bevel=0.014, segs=3)
    g = Geo()
    wheel = (Matrix.Translation((0.60, 0.43, 1.19)) @ Matrix.Rotation(rad(-62), 4, 'Y')
             @ Matrix.Rotation(pi / 2, 4, 'X'))
    g.lathe([(-0.014, 0.185), (0.0, 0.20), (0.014, 0.185), (0.0, 0.17)], 24, xf=wheel)
    g.box((0.70, 0.43, 1.15), (0.22, 0.06, 0.06), rot=Matrix.Rotation(rad(-28), 3, 'Y'))
    for a in (30, 150, 270):
        tube(g, wheel @ V3((0, -0.02, 0)), wheel @ V3((0.18 * cos(rad(a)), 0, 0.18 * sin(rad(a)))),
             0.012, 6)
    g.obj("interior.wheel", "interior", sharp=40)
    g = Geo()
    scr = Matrix.Rotation(rad(-22), 3, 'Y')
    g.box((0.705, 0.0, 1.235), (0.008, 0.34, 0.15), rot=scr)
    g.box((0.745, 0.43, 1.30), (0.008, 0.24, 0.07), rot=scr)
    g.obj("interior.screens", "screen")


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
    K.shoot()


main()
