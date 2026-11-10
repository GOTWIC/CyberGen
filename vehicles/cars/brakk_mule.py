"""Brakk Mule: a six-wheeled cargo van of flat plates (both names made up), on
vehicles/carkit.py.

Run (always through the wrapper, one Blender job at a time on this machine):
    vehicles/blender.sh vehicles/cars/brakk_mule.py --out DIR --preview
    vehicles/blender.sh vehicles/cars/brakk_mule.py --out DIR --sheet

The third Brakk, sibling of the Hauler and the Bastion (family cues:
docs/progress/AG18/brakk_hauler/README.md): plates and 45 degree chamfers, the wheels outside
the hull under bolted fender plates, light pylons on the chamfered corners, a bar over the
windshield, the ribbed slab face, fasteners in rows, stencils, the Brakk wheel with the
Bastion's hub motors. Its own ideas: a narrow cab-over wedge cab that stands between its front
wheels, joined by a bellows collar on a turntable to a container-like cargo box wider than the
cab (corrugated walls between rails, corner castings, lock rods on the barn doors, a roller
door on the left shown two thirds open over lit crates, a cooling unit over the cab, roof
hatches), the rear pair of wheels on a walking beam, battery cases, air tanks, under-run bars
and a ladder between the axles, tall marker pylons on the box's corners.

Pieces: the cab hull (eight lines over eight stations, every edge sharp) and plates, bars and
tubes for the rest. The helpers tube, bolt, plate, stencil, chevrons, pylon, coil and the
wheel are the Hauler's and the Bastion's.
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
FA_X, RA1_X, RA2_X = 2.20, -1.29, -2.53         # one axle in front, a pair behind
BOGIE_X = (RA1_X + RA2_X) / 2
T_R, T_W, T_RIM, T_OUT = 0.475, 0.34, 0.25, 1.15        # tire radius, width, rim, outer face
MOTOR_Y = T_OUT - T_W - 0.085                   # a hub motor's inner face
FEN_Z, FEN_T = 1.04, 0.03                       # fender plates: top height, thickness
SILL, BELT = 1.50, 1.10                         # the cab: window sill, foot of the door
BX0, BX1 = 1.02, -3.14                          # the box: front, rear
BZ0, BZF, BZC, BZ1 = 1.08, 1.16, 2.32, 2.50     # underside, floor, ceiling, top
BW, BWALL = 1.10, 1.07                          # half width over the rails, the wall's plane
POST = 0.14                                     # the corner posts' chamfer in plan
DOOR_X0, DOOR_X1, DOOR_Z = 0.62, -1.02, 1.90    # the roller door's opening, its bar's height
NUM = "63"


def roof_z(x):
    """The cab's roof plate: it rises a little toward the collar."""
    return 2.16 + (2.68 - x) * 0.058


# ---------------------------------------------------------------------------------------
# the family's helpers (from the Hauler and the Bastion)
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
    o, r, u = V3(origin), V3(right).normalized(), V3(up).normalized()
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


def zcyl(g, c, r, h, n=16, r2=None):
    """An upright cylinder (or cone) standing on the point c."""
    c = V3(c)
    tube(g, c, c + V3((0, 0, h)), r, n, r2=r2)


def yz_prism(g, poly, x0, x1):
    """A (y, z) polygon from x0 to x1."""
    g.prism([(x0, y, z) for y, z in poly], (x1 - x0, 0, 0))


def xy_prism(g, poly, z0, z1):
    """An (x, y) polygon from z0 to z1."""
    g.prism([(x, y, z0) for x, y in poly], (0, 0, z1 - z0))


def xz_prism(g, poly, y0, y1):
    """An (x, z) polygon from y0 to y1."""
    g.prism([(x, y0, z) for x, z in poly], (0, y1 - y0, 0))


def ring(g, c, r0=0.030, r1=0.050, t=0.009, n=14, rot=None):
    xf = Matrix.Translation(c)
    if rot is not None:
        xf = xf @ rot
    g.lathe([(-t, r0), (-t, r1), (t, r1), (t, r0)], n, xf=xf)


# ---------------------------------------------------------------------------------------
# the cab: a wedge that stands between its front wheels
# ---------------------------------------------------------------------------------------
LINES = "CRHWGUFB"
#        C top centerline, R roof plate edge, H foot of the roof chamfer (glass top),
#        W window sill, G foot of the door (the cab's widest line), U foot of the undercut,
#        F floor edge, B floor centerline
ORDER = ["P0", "P1", "N2", "N3", "W1", "D1", "D2", "D3"]
PT = {}


def cab_row(x):
    r = roof_z(x)
    return [(x, 0, r), (x, .60, r), (x, .72, r - .12), (x, .80, SILL), (x, .80, BELT),
            (x, .60, .92), (x, .56, .62), (x, 0, .58)]


def hull_stations():
    T = {
        "P0": [(3.14, 0, 1.38), (3.14, .30, 1.38), (3.14, .56, 1.38), (3.14, .56, 1.32),
               (3.14, .56, BELT), (3.14, .56, .86), (3.14, .44, .70), (3.14, 0, .70)],
        "P1": [(3.02, 0, 1.50), (3.02, .34, 1.50), (3.02, .68, 1.50), (3.02, .68, 1.44),
               (3.02, .68, BELT), (3.02, .68, .86), (3.02, .54, .66), (3.02, 0, .62)],
        # the nose block ends ahead of the wheel: the hull steps in to let it steer
        "N2": [None, None, None, None, (2.82, .740, BELT), (2.82, .740, .86), (2.82, .60, .64),
               (2.82, 0, .60)],
        "N3": [None, None, None, None, (2.78, .752, BELT), (2.78, .60, .92), (2.78, .56, .62),
               (2.78, 0, .58)],
        "W1": [(2.68, 0, 2.16), (2.68, .58, 2.16), (2.62, .72, 2.04), (2.62, .80, SILL),
               (2.62, .80, BELT), (2.62, .60, .92), (2.62, .56, .62), (2.62, 0, .58)],
        "D1": cab_row(2.50), "D2": cab_row(1.52), "D3": cab_row(1.30),
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
            ("glass_ws", "glass_ws", "glass_q", "nose_side", "nose_side"),
            ("glass_ws", "glass_ws", "glass_q", "nose_side", "nose_side"),
            ("glass_ws", "glass_ws", "glass_q", "nose_side", "under"),
            ("roof", "roof_edge", "pillar_a", "cowl_side", "under"),
            ("roof", "roof_edge", "glass_d", "door", "under"),
            ("roof", "roof_edge", "pillar_b", "cab_rear", "under"))[i][j]


HULL_MAT = dict(nose_top="paint", nose_corner="paint", glass_ws="glass", glass_q="glass",
                nose_side="paint", under="paint2", roof="paint", roof_edge="paint",
                pillar_a="paint", cowl_side="paint", glass_d="glass", door="paint",
                pillar_b="gloss_black", cab_rear="paint", sill="cladding", floor="underbody",
                trim="cladding", nose="cladding", back="cladding")


def build_hull():
    K.build_body(hull_stations(), hull_panel, HULL_MAT, 1.0, 1.0, name="hull",
                 front=dict(kind="flat", panel="nose"), rear=dict(kind="flat", panel="back"),
                 glass=[("glass_ws", 0.055), ("glass_q", 0.045), ("glass_d", 0.05)],
                 subdiv=2, gap=0.004, bevel=0.008)


# ---------------------------------------------------------------------------------------
# fender plates, lights
# ---------------------------------------------------------------------------------------
BOLTS = Geo()           # bolt heads on the left side and the middle, mirrored at the end
BOLTS_L = Geo()         # bolt heads on one side only
F_FEN = [(2.86, 0.80), (2.66, FEN_Z), (1.74, FEN_Z), (1.56, 0.84)]
R_FEN = [(-0.63, 0.84), (-0.81, FEN_Z), (-2.98, FEN_Z), (-3.13, 0.86)]


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


def build_fenders():
    g, gb, gk = Geo(), Geo(), Geo()
    y1 = T_OUT + 0.012
    for pts, y0, brackets in ((F_FEN, 0.72, (2.50, 1.90)), (R_FEN, 0.68, (-1.05, BOGIE_X, -2.78))):
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
        for x in brackets:                              # gussets under the plate
            gk.prism([(x - 0.012, y0 - 0.02, FEN_Z - FEN_T), (x - 0.012, y0 + 0.26, FEN_Z - FEN_T),
                      (x - 0.012, y0 - 0.02, FEN_Z - 0.22)], (0.024, 0, 0))
    # the front plate is the step to the cab's door: tread ribs across it
    sec = [(-0.016, 0.0), (0.016, 0.0), (0.008, 0.009), (-0.008, 0.009)]
    for k in range(15):
        x = 2.60 - k * 0.057
        g.sweep([(x, 0.84, FEN_Z - 0.002), (x, 1.10, FEN_Z - 0.002)], sec, up=(0, 0, 1))
    g.obj("fender.plates", "paint2", bevel=0.006, mirror=True)
    gk.obj("fender.gussets", "cladding", bevel=0.003, mirror=True)
    gb.obj("fender.bolts", "rim_bright", mirror=True)
    g = Geo()                                           # mud flaps behind the wheels
    g.box((1.585, 0.97, 0.63), (0.014, 0.36, 0.42))
    g.box((-3.09, 0.97, 0.62), (0.014, 0.36, 0.44))
    g.obj("mudflaps", "rubber", bevel=0.003, mirror=True)
    g = Geo()                                           # markers on the folded edges
    y = y1 + 0.001
    g.box((2.20, y, FEN_Z - 0.04), (0.18, 0.006, 0.03))
    for x in (-1.04, BOGIE_X):
        g.box((x, y, FEN_Z - 0.04), (0.14, 0.006, 0.03))
    g.obj("led.markers", "led_accent", mirror=True)
    g = Geo()
    g.box((-2.72, y, FEN_Z - 0.04), (0.18, 0.006, 0.03))
    g.obj("led.markers_r", "led_rear", mirror=True)


def build_lights():
    g, gf, gr, ga = Geo(), Geo(), Geo(), Geo()
    pylon(g, gf, ga, 3.08, 0.62, 0.84, 1.34, 45)                    # the cab's face
    pylon(g, gr, ga, BX1 + POST / 2, BW - POST / 2, 1.34, 2.26, 135)  # the box's tail posts
    pylon(g, ga, ga, BX0 - POST / 2, BW - POST / 2, 1.46, 2.26, 45)   # markers beside the cab
    ga.obj("led.turn", "led_accent", mirror=True)
    g.obj("pylons", "cladding", bevel=0.004, mirror=True)
    gf.obj("led.front", "led_front", mirror=True)
    gr.obj("led.rear", "led_rear", mirror=True)
    # a blade of light across the face, from pylon to pylon
    g = Geo()
    g.box((3.144, 0, 1.325), (0.014, 1.04, 0.05))
    g.obj("face.blade.housing", "cladding", bevel=0.003)
    g = Geo()
    g.box((3.152, 0, 1.325), (0.006, 1.00, 0.022))
    g.obj("led.blade", "led_front")
    # the bar over the windshield: a housing on the roof's front edge, eight cells
    g = Geo()
    g.prism([(2.75, -0.56, 2.13), (2.75, -0.56, 2.225), (2.61, -0.56, 2.225),
             (2.55, -0.56, 2.155)], (0, 1.12, 0))
    for k in range(9):
        y = -0.51 + 1.02 * k / 8
        g.box((2.754, y, 2.185), (0.012, 0.016, 0.06))
    g.obj("roofbar", "cladding", bevel=0.004)
    g = Geo()
    g.box((2.751, 0, 2.185), (0.006, 1.01, 0.04))
    g.obj("led.roofbar", "led_front")
    g = Geo()                                           # amber clearance lamps at its ends
    g.box((2.68, 0.564, 2.188), (0.07, 0.006, 0.03))
    g.obj("led.clear", "led_accent", mirror=True)
    g = Geo()                                           # a stop strip over the barn doors
    g.box((BX1 - 0.006, 0, 2.415), (0.012, 1.30, 0.04))
    g.obj("stop.housing", "cladding", bevel=0.003)
    g = Geo()
    g.box((BX1 - 0.0135, 0, 2.415), (0.004, 1.24, 0.018))
    g.obj("led.stop", "led_rear")


# ---------------------------------------------------------------------------------------
# the face, the bumper, the cab's hardware
# ---------------------------------------------------------------------------------------
def build_nose():
    g = Geo()                                           # the ribbed slab
    for z, hw in ((0.80, 0.42), (0.875, 0.45), (0.95, 0.45), (1.025, 0.45), (1.10, 0.45)):
        g.prism([(3.138, -hw, z - 0.028), (3.17, -hw, z - 0.013), (3.17, -hw, z + 0.013),
                 (3.138, -hw, z + 0.028)], (0, 2 * hw, 0))
    g.box((3.146, 0, 1.215), (0.016, 0.60, 0.07))
    g.obj("nose.ribs", "paint", bevel=0.004)
    g = Geo()
    for y in (0.27, -0.27):
        for z in (1.195, 1.235):
            bolt(g, (3.154, y, z), (1, 0, 0), 0.007, 0.004)
    g.obj("nose.bolts", "rim_bright")
    # the bumper: a beam with a flat tip and swept, rising ends that are the first step
    g = Geo()
    g.prism([(3.29, -0.20, 0.46), (3.29, 0.20, 0.46), (3.23, 0.62, 0.46), (3.12, 0.62, 0.46),
             (3.12, -0.62, 0.46), (3.23, -0.62, 0.46)], (0, 0, 0.21))
    for s in (1, -1):
        g.hexa([(3.23, s * 0.62, 0.46), (3.06, s * 1.13, 0.57), (2.96, s * 1.13, 0.57),
                (3.12, s * 0.62, 0.46), (3.23, s * 0.62, 0.67), (3.06, s * 1.13, 0.73),
                (2.96, s * 1.13, 0.73), (3.12, s * 0.62, 0.67)])
        g.box((3.09, s * 0.30, 0.685), (0.10, 0.08, 0.05))          # brackets to the hull
    g.obj("bumper.front", "paint2", bevel=0.007)
    g = Geo()                                           # a tow pin in a pocket, two shackles
    g.box((3.293, 0, 0.565), (0.008, 0.26, 0.11))
    g.obj("tow.plate", "rim_bright", bevel=0.002)
    g = Geo()
    g.box((3.2975, 0, 0.565), (0.004, 0.16, 0.06))
    g.obj("tow.slot", "void")
    g = Geo()
    tube(g, (3.305, 0, 0.52), (3.305, 0, 0.61), 0.014, 10)
    for s in (1, -1):
        g.box((3.265, s * 0.42, 0.565), (0.06, 0.03, 0.075), rot=Matrix.Rotation(rad(s * 8), 3, 'Z'))
        ring(g, (3.292, s * 0.424, 0.53), rot=Matrix.Rotation(rad(s * 8), 4, 'Z'))
    g.obj("hooks", "caliper", bevel=0.003)
    g = Geo()                                           # step pads on the bumper's ends
    for s in (1, -1):
        d = V3((-0.165, s * 0.51, 0.06))
        for k in range(6):
            c = V3((3.175, s * 0.62, 0.674)) + d * (0.20 + 0.125 * k)
            g.box(c, (0.085, 0.016, 0.008), rot=Matrix.Rotation(rad(s * 18), 3, 'Z'))
    g.obj("step.pads", "rim_bright", bevel=0.001)
    g = Geo()                                           # a skid plate under the nose
    g.prism([(3.10, -0.42, 0.60), (2.86, -0.42, 0.53), (1.70, -0.42, 0.53), (1.70, -0.42, 0.555),
             (2.86, -0.42, 0.555), (3.10, -0.42, 0.625)], (0, 0.84, 0))
    for y in (-0.28, -0.14, 0.0, 0.14, 0.28):
        g.prism([(3.06, y - 0.02, 0.57), (2.86, y - 0.02, 0.512), (1.84, y - 0.02, 0.512),
                 (1.84, y - 0.02, 0.535), (2.86, y - 0.02, 0.535), (3.06, y - 0.02, 0.59)],
                (0, 0.04, 0))
    g.obj("skid", "rim", bevel=0.003)


def build_cab():
    # the door: a rub strip, a bar handle, hinges, a grab rail behind it
    g = Geo()
    sec = [(-0.016, 0.0), (0.016, 0.0), (0.009, 0.014), (-0.009, 0.014)]
    g.sweep([(2.46, 0.798, 1.145), (1.56, 0.798, 1.145)], sec, up=(0, 1, 0))
    g.obj("rubstrips", "cladding", bevel=0.002, mirror=True)
    g = Geo()
    g.box((1.66, 0.835, 1.40), (0.17, 0.022, 0.034))
    for dx in (-0.07, 0.07):
        g.box((1.66 + dx, 0.814, 1.40), (0.022, 0.03, 0.03))
    for z in (1.18, 1.44, 1.72, 1.98):
        y = 0.80 - 0.08 * max(0.0, z - SILL) / 0.58
        g.box((2.495, y + 0.006, z), (0.06, 0.024, 0.085))
        tube(g, (2.495, y + 0.02, z - 0.05), (2.495, y + 0.02, z + 0.05), 0.011, 8)
    tube(g, (1.41, 0.84, 1.18), (1.41, 0.80, 1.92), 0.014, 8)        # the grab rail
    for z, y in ((1.20, 0.838), (1.90, 0.80)):
        tube(g, (1.41, y - 0.05, z), (1.41, y, z), 0.011, 8)
    g.obj("door.hardware", "cladding", bevel=0.003, mirror=True)
    # camera pods where mirrors would be: a strut and a faceted pod with a lens
    g = Geo()
    tube(g, (2.60, 0.78, 1.60), (2.62, 1.00, 1.68), 0.014, 4, phase=pi / 4)
    g.hexa([(2.70, 0.96, 1.64), (2.70, 1.05, 1.64), (2.55, 1.045, 1.655), (2.55, 0.965, 1.655),
            (2.70, 0.96, 1.72), (2.70, 1.05, 1.72), (2.55, 1.045, 1.735), (2.55, 0.965, 1.735)])
    g.obj("campods", "cladding", bevel=0.004, mirror=True)
    g = Geo()
    g.box((2.548, 1.005, 1.695), (0.004, 0.06, 0.05))
    g.obj("campod.lens", "gloss_black", mirror=True)
    g = Geo()
    g.box((2.702, 1.005, 1.675), (0.004, 0.06, 0.012))
    g.obj("led.campod", "led_accent", mirror=True)
    # the sensor band: the rear pillar is dark glass with lit cells and a lens
    g = Geo()
    for k in range(5):
        loc, n = on_body(1.47 - k * 0.03, 1.80, 'y')
        if loc is not None:
            g.box(loc + n * 0.003, (0.010, 0.006, 0.44 - 0.07 * (k % 2)))
    g.obj("led.sensor", "sensor", mirror=True)
    g = Geo()
    loc, n = on_body(1.41, 1.44, 'y')
    stud(g, loc, n, [(-0.001, 0.001), (-0.001, 0.04), (0.012, 0.04), (0.018, 0.03), (0.018, 0.001)], 16)
    g.obj("sensor.lens", "cladding", bevel=0.002, mirror=True)
    g = Geo()
    stud(g, loc + n * 0.018, n, [(0.0, 0.001), (0.0, 0.024), (0.002, 0.024), (0.002, 0.001)], 16)
    g.obj("sensor.eye", "gloss_black", mirror=True)
    # a sensor brow under the bar, across the top of the windshield
    g = Geo()
    for k in range(13):
        loc, n = on_body(-0.42 + 0.07 * k, 2.09, 'x')
        if loc is not None:
            g.box(loc + n * 0.004, (0.006, 0.04 if k % 3 else 0.055, 0.012),
                  rot=Matrix.Rotation(rad(-26), 3, 'Y'))
    g.obj("led.brow", "sensor")
    # wipers
    g = Geo()
    for y0 in (0.04, -0.40):
        blade = []
        for k in range(7):
            t = k / 6
            loc, n = on_body(y0 + 0.34 * t, 1.60 + 0.34 * t, 'x')
            blade.append(loc + n * 0.016)
        g.sweep(blade, [(-0.005, -0.009), (0.005, -0.009), (0.005, 0.007), (-0.005, 0.007)],
                up=(1, 0, 1))
        piv, n = on_body(y0 + 0.01, 1.555, 'x')
        tube(g, piv + n * 0.012, blade[3] + n * 0.012, 0.006, 6)
    g.obj("wipers", "cladding", bevel=0.001)
    # roof: ribs, a bolted hatch plate, a whip
    g = Geo()
    sec = [(-0.03, 0.0), (0.03, 0.0), (0.018, 0.012), (-0.018, 0.012)]
    for yy in (-0.42, -0.28, 0.28, 0.42):
        g.sweep([(2.44, yy, roof_z(2.44) - 0.002), (1.40, yy, roof_z(1.40) - 0.002)], sec,
                up=(0, 0, 1))
    g.obj("roof.ribs", "paint", bevel=0.003)
    g = Geo()
    c = V3((1.92, 0, roof_z(1.92)))
    g.box(c + V3((0, 0, 0.006)), (0.62, 0.36, 0.014), rot=Matrix.Rotation(rad(-3.3), 3, 'Y'))
    tube(g, (1.42, 0.50, roof_z(1.42)), (1.36, 0.50, roof_z(1.42) + 0.42), 0.006, 6, r2=0.003)
    g.box((1.42, 0.50, roof_z(1.42) + 0.008), (0.06, 0.06, 0.02))
    g.obj("roof.hatch", "paint2", bevel=0.004)


# ---------------------------------------------------------------------------------------
# the collar: a bellows between the cab and the box, on a turntable, with its hoses
# ---------------------------------------------------------------------------------------
def build_collar():
    g = Geo()
    for k in range(6):
        x = 1.275 - k * 0.042
        d = 0.07 * (k % 2)
        yz_prism(g, [(-0.64 + d, 1.14 + d), (0.64 - d, 1.14 + d), (0.64 - d, 1.96 - d),
                     (0.54 - d, 2.08 - d), (-0.54 + d, 2.08 - d), (-0.64 + d, 1.96 - d)],
                 x + 0.019, x - 0.019)
    g.obj("collar.bellows", "rubber", bevel=0.006)
    g = Geo()                                           # the frame bolted to the box's front
    yz_prism(g, [(-0.70, 1.10), (0.70, 1.10), (0.70, 2.00), (0.58, 2.14), (-0.58, 2.14),
                 (-0.70, 2.00)], BX0 + 0.022, BX0)
    g.obj("collar.frame", "paint2", bevel=0.004)
    g = Geo()
    for k in range(8):
        for s in (1, -1):
            bolt(g, (BX0 + 0.022, s * 0.67, 1.18 + k * 0.11), (1, 0, 0))
    for k in range(9):
        bolt(g, (BX0 + 0.022, -0.48 + k * 0.12, 2.11), (1, 0, 0))
    g.obj("collar.bolts", "rim_bright")
    g = Geo()                                           # the turntable under it
    zcyl(g, (1.16, 0, 0.86), 0.40, 0.05, 28)
    zcyl(g, (1.16, 0, 0.91), 0.32, 0.05, 28)
    zcyl(g, (1.16, 0, 0.96), 0.44, 0.03, 28)
    g.obj("collar.turntable", "rim", bevel=0.003)
    g = Geo()
    for k in range(14):
        a = 2 * pi * k / 14
        bolt(g, (1.16 + 0.37 * cos(a), 0.37 * sin(a), 0.91), (0, 0, 1), 0.012, 0.007)
    g.obj("collar.tablebolts", "rim_bright")
    g, gc = Geo(), Geo()                                # hoses and a cable across the gap
    for y, z, r, gg in ((0.70, 1.30, 0.016, gc), (0.70, 1.40, 0.012, g), (-0.70, 1.30, 0.016, gc),
                        (-0.70, 1.40, 0.012, g), (-0.70, 1.50, 0.012, g)):
        s = 1 if y > 0 else -1
        pts = [V3((1.31, y - s * 0.02, z)), V3((1.26, y + s * 0.03, z - 0.02)),
               V3((1.16, y + s * 0.05, z - 0.07)), V3((1.07, y + s * 0.03, z - 0.02)),
               V3((BX0, y - s * 0.02, z))]
        for a, b in zip(pts, pts[1:]):
            tube(gg, a, b, r, 8)
    g.obj("collar.hoses", "rubber", bevel=0.002)
    gc.obj("collar.cables", "cable", bevel=0.003)


# ---------------------------------------------------------------------------------------
# the box: a container on the frame (rails, corrugated walls, corner castings)
# ---------------------------------------------------------------------------------------
def rib_xs(x0, x1, pitch=0.15):
    n = int((x0 - x1) / pitch)
    off = ((x0 - x1) - n * pitch) / 2
    return [x0 - off - k * pitch for k in range(n + 1)]


def build_box():
    xa, xb = BX0 - POST, BX1 + POST
    g = Geo()
    yz_prism(g, [(-BW, BZC), (BW, BZC), (BW, BZ1 - 0.12), (BW - 0.12, BZ1), (-BW + 0.12, BZ1),
                 (-BW, BZ1 - 0.12)], BX0, BX1)                          # the roof
    g.box(((BX0 + BX1) / 2, 0, (BZ0 + BZF) / 2), (BX0 - BX1, 2 * BW, BZF - BZ0))   # the floor
    zm, zh = (BZF + BZC) / 2, BZC - BZF
    g.box(((xa + xb) / 2, -(BWALL - 0.02), zm), (xa - xb, 0.04, zh))    # the right wall
    g.box(((xa + DOOR_X0) / 2, BWALL - 0.02, zm), (xa - DOOR_X0, 0.04, zh))
    g.box(((DOOR_X1 + xb) / 2, BWALL - 0.02, zm), (DOOR_X1 - xb, 0.04, zh))
    g.box((BX0 - 0.02, 0, zm), (0.04, 2 * (BW - 0.20), zh))             # the front wall
    for s in (1, -1):                                   # corner posts, chamfered in plan
        xy_prism(g, [(xb, s * BW), (BX1, s * (BW - POST)), (BX1, s * (BW - 0.22)),
                     (xb, s * (BW - 0.22))], BZ0, BZC)
        xy_prism(g, [(xa, s * BW), (BX0, s * (BW - POST)), (BX0, s * (BW - 0.22)),
                     (xa, s * (BW - 0.22))], BZ0, BZC)
        for z in (BZF + 0.03, BZC - 0.02):              # the rails that frame the ribs
            g.box(((xa + xb) / 2, s * (BW - 0.015), z), (xa - xb, 0.03, 0.06 if z < 2 else 0.04))
    g.obj("box.shell", "paint", bevel=0.006)
    # corrugation: upright trapezoid ribs between the rails
    g = Geo()
    z0, z1 = BZF + 0.06, BZC - 0.04

    def rib(x, s):
        y = s * (BWALL - 0.002)
        xy_prism(g, [(x - 0.045, y), (x + 0.045, y), (x + 0.022, s * BW), (x - 0.022, s * BW)],
                 z0, z1)
    for x in rib_xs(xa - 0.03, xb + 0.03):
        rib(x, -1)
    for x in rib_xs(xa - 0.03, DOOR_X0 + 0.02) + rib_xs(DOOR_X1 - 0.03, xb + 0.03):
        rib(x, 1)
    for s in (1, -1):                                   # two on the front wall beside the cab
        g.box((BX0 + 0.012, s * 0.80, 1.72), (0.028, 0.09, 0.98))
    g.obj("box.ribs", "paint", bevel=0.004)
    # corner castings, an oval hole in each face
    g, gv = Geo(), Geo()
    for s in (1, -1):
        for x, e in ((BX0 - 0.085, 1), (BX1 + 0.085, -1)):
            for z in (BZ0 + 0.055, BZ1 - 0.075):
                g.box((x, s * (BW - 0.075), z), (0.19, 0.17, 0.17))
                gv.box((x, s * (BW + 0.011), z), (0.09, 0.004, 0.05))
                gv.box((x + e * 0.096, s * (BW - 0.075), z), (0.004, 0.08, 0.05))
    g.obj("box.castings", "paint2", bevel=0.008)
    gv.obj("box.castholes", "void")
    # the roller door on the left: guides, the curtain's slats, its bar, a tread sill
    g = Geo()
    for x in (DOOR_X0 - 0.03, DOOR_X1 + 0.03):
        g.box((x, BW - 0.03, zm), (0.06, 0.06, zh))
    cx, cw = (DOOR_X0 + DOOR_X1) / 2, DOOR_X0 - DOOR_X1
    g.box((cx, BW - 0.10, BZC - 0.055), (cw, 0.16, 0.11))               # the roller's case
    g.obj("door.guides", "paint2", bevel=0.004)
    g = Geo()
    z = BZC - 0.145
    while z > DOOR_Z + 0.07:
        yz_prism(g, [(1.03, z - 0.0325), (1.045, z - 0.0325), (1.062, z - 0.014), (1.062, z + 0.014),
                     (1.045, z + 0.0325), (1.03, z + 0.0325)], DOOR_X0 - 0.05, DOOR_X1 + 0.05)
        z -= 0.065
    g.obj("door.curtain", "paint", bevel=0.003)
    g = Geo()
    g.box((cx, 1.048, DOOR_Z), (cw - 0.12, 0.05, 0.10))
    g.box((cx, 1.048, DOOR_Z - 0.06), (cw - 0.14, 0.03, 0.03))
    for dx in (-0.30, 0.30):
        g.box((cx + dx, 1.082, DOOR_Z), (0.03, 0.03, 0.04))
    tube(g, (cx - 0.34, 1.10, DOOR_Z), (cx + 0.34, 1.10, DOOR_Z), 0.013, 8)
    g.obj("door.bar", "paint2", bevel=0.003)
    g = Geo()
    for k in range(24):
        g.box((DOOR_X0 - 0.10 - k * 0.062, BW - 0.03, BZF + 0.003), (0.03, 0.055, 0.006))
    g.obj("door.sill", "rim_bright", bevel=0.001)
    # the tail: barn doors with lock rods, hinges, a header plate
    g, gh, gr = Geo(), Geo(), Geo()
    xd = BX1 - 0.012
    for s in (1, -1):
        g.box((xd, s * 0.445, zm), (0.03, 0.87, zh - 0.02))
        for y in (0.15, 0.73):
            tube(gr, (xd - 0.034, s * y, BZ0 + 0.02), (xd - 0.034, s * y, BZC + 0.06), 0.015, 10)
            for z in (BZ0 + 0.035, BZC + 0.045):        # the cams' keepers
                gh.box((xd - 0.022, s * y, z), (0.05, 0.08, 0.05))
            for z in (1.36, 1.74, 2.14):                # guides
                gh.box((xd - 0.028, s * y, z), (0.03, 0.06, 0.05))
            # a handle on each rod, in its catch
            tube(gr, (xd - 0.05, s * y, 1.55), (xd - 0.05, s * (y + (0.25 if y < 0.4 else -0.25)), 1.53),
                 0.011, 8)
            gh.box((xd - 0.03, s * (y + (0.21 if y < 0.4 else -0.21)), 1.53), (0.045, 0.05, 0.06))
        for z in (1.30, 1.62, 1.94, 2.22):              # hinges on the posts
            gh.box((xd - 0.012, s * 0.885, z), (0.04, 0.10, 0.10))
            tube(gh, (xd - 0.03, s * 0.885, z - 0.06), (xd - 0.03, s * 0.885, z + 0.06), 0.014, 8)
    g.obj("tail.doors", "paint", bevel=0.005)
    gh.obj("tail.hardware", "cladding", bevel=0.003)
    gr.obj("tail.rods", "rim_bright", bevel=0.002)
    # bolts: along the rails, round the door, on the posts
    for x in rib_xs(xa - 0.105, xb + 0.105):
        for z in (BZF + 0.03, BZC - 0.02):
            bolt(BOLTS, (x, BW, z), (0, 1, 0))
    for k in range(9):
        z = BZF + 0.12 + k * 0.125
        for x in (DOOR_X0 - 0.03, DOOR_X1 + 0.03):
            bolt(BOLTS_L, (x, BW, z), (0, 1, 0))
        bolt(BOLTS, (BX1 - 0.001, BW - 0.18, z), (-1, 0, 0))
        bolt(BOLTS, (BX0 + 0.001, BW - 0.18, z), (1, 0, 0))


def build_cargo():
    """What the open door shows: a lit hold, lashing rails, crates, drums."""
    g = Geo()
    g.box((-0.20, 0.30, BZC - 0.008), (2.40, 0.07, 0.014))
    g.box((-2.20, 0.0, BZC - 0.008), (1.20, 0.07, 0.014))
    g.obj("led.hold", "worklight")
    g = Geo()
    for z in (1.52, 1.92):
        g.box((-1.05, -(BWALL - 0.05), z), (3.6, 0.02, 0.05))
        g.box((0.94, 0, z), (0.02, 1.6, 0.05))
    g.obj("hold.rails", "rim", bevel=0.002)
    g = Geo()
    for z in (1.52, 1.92):
        for k in range(24):
            g.box((0.68 - k * 0.15, -(BWALL - 0.061), z), (0.06, 0.004, 0.02))
    g.obj("hold.slots", "void")
    ga, gb, gc, gs, gd, gm = Geo(), Geo(), Geo(), Geo(), Geo(), Geo()

    def crate(gg, c, size, ribs=True):
        c = V3(c)
        gg.box(c, size)
        if ribs:
            for sx in (-1, 1):
                for sy in (-1, 1):
                    gg.box(c + V3((sx * (size[0] / 2 - 0.03), sy * (size[1] / 2 - 0.03), 0)),
                           (0.075, 0.075, size[2] + 0.02))
            for dz in (-1, 1):
                gg.box(c + V3((0, 0, dz * (size[2] / 2 - 0.035))), (size[0] + 0.016, size[1] + 0.016, 0.05))

    crate(ga, (0.18, 0.56, BZF + 0.27), (0.66, 0.78, 0.54))
    crate(gb, (0.20, 0.62, BZF + 0.54 + 0.13), (0.50, 0.56, 0.26), ribs=False)
    crate(gc, (-0.58, 0.52, BZF + 0.33), (0.60, 0.86, 0.66))
    crate(ga, (0.10, -0.50, BZF + 0.45), (0.90, 0.90, 0.90))
    crate(gc, (-1.60, 0.40, BZF + 0.30), (0.80, 1.10, 0.60))
    crate(ga, (-1.62, 0.40, BZF + 0.60 + 0.22), (0.60, 0.80, 0.44))
    for x, y in ((-0.72, -0.34), (-0.72, -0.86), (-1.26, -0.60)):      # drums
        zcyl(gd, (x, y, BZF), 0.24, 0.78, 20)
        for z in (0.18, 0.56):
            zcyl(gm, (x, y, BZF + z), 0.25, 0.03, 20)
    for y in (0.40, 0.72):                                              # straps
        gs.box((0.18, y, BZF + 0.27), (0.672, 0.05, 0.552))
    gs.box((0.20, 0.62, BZF + 0.67), (0.512, 0.06, 0.272))
    for x in (-0.76, -0.40):
        gs.box((x, 0.52, BZF + 0.33), (0.05, 0.872, 0.672))
    ga.obj("cargo.crates", "crate_a", bevel=0.006)
    gb.obj("cargo.case", "hazard", bevel=0.008)
    gc.obj("cargo.boxes", "crate_c", bevel=0.006)
    gd.obj("cargo.drums", "paint2", bevel=0.006)
    gm.obj("cargo.drumbands", "hazard", bevel=0.002)
    gs.obj("cargo.straps", "rubber", bevel=0.001)
    g = Geo()
    stencil(g, "BRAKK PARTS", 0.07, on_plane((0.18, 0.9512, BZF + 0.30), (-1, 0, 0), (0, 0, 1)), gap=0.16)
    stencil(g, "THIS SIDE UP", 0.035, on_plane((0.18, 0.9512, BZF + 0.20), (-1, 0, 0), (0, 0, 1)),
            gap=0.2, cut=0)
    stencil(g, "LOT 0417", 0.06, on_plane((-0.58, 0.9512, BZF + 0.36), (-1, 0, 0), (0, 0, 1)), gap=0.16)
    g.obj("cargo.marks", "mark")


def build_roof():
    # the cooling unit: a case on the roof's front that hangs over the collar, louvres, fans
    g = Geo()
    g.box((0.70, 0, BZ1 + 0.075), (0.78, 1.36, 0.15))
    g.box((1.085, 0, 2.47), (0.15, 1.36, 0.36))
    g.obj("cooler", "paint2", bevel=0.008)
    g = Geo()
    for s in (1, -1):
        a = (1.166, s * 0.08, 2.33)
        b = (1.166, s * 0.62, 2.33)
        d = (1.166, s * 0.08, 2.61)
        c = (1.166, s * 0.62, 2.61)
        g.louvers(a, d, c, b, 6, 0.045, 0.008, rad(32), out=(1, 0, 0), margin=0.03)
    g.obj("cooler.louvres", "grille", bevel=0.0015)
    g, gv, gk = Geo(), Geo(), Geo()
    for s in (1, -1):
        fc = V3((0.70, s * 0.34, BZ1 + 0.15))
        up = Matrix.Translation(fc) @ Matrix.Rotation(pi / 2, 4, 'X')
        g.lathe([(0.0, 0.215), (0.0, 0.26), (-0.03, 0.26), (-0.03, 0.215)], 32, xf=up)
        gv.lathe([(-0.004, 0.002), (-0.004, 0.215), (0.0, 0.215), (0.0, 0.002)], 32, xf=up)
        zcyl(g, fc, 0.05, 0.03, 12)
        for k in range(7):
            R = Matrix.Rotation(2 * pi * k / 7 + s * 0.3, 3, 'Z')
            gk.box(fc + R @ V3((0.125, 0, 0.012)), (0.17, 0.055, 0.004),
                   rot=R @ Matrix.Rotation(rad(20), 3, 'X'))
        for k in range(3):                              # a guard of three bars
            R = Matrix.Rotation(pi * k / 3, 3, 'Z')
            g.box(fc + V3((0, 0, 0.034)), (0.50, 0.012, 0.008), rot=R)
    g.obj("cooler.fans", "cladding", bevel=0.002)
    gv.obj("cooler.wells", "void")
    gk.obj("cooler.blades", "rim_bright")
    g = Geo()
    for k in range(10):
        x = 0.36 + k * 0.075
        for s in (1, -1):
            bolt(g, (x, s * 0.65, BZ1 + 0.15), (0, 0, 1), 0.009, 0.005)
    g.obj("cooler.bolts", "rim_bright")
    # two hatches: a bolted plate, ribs, hinges, a handle
    g, gh, gb = Geo(), Geo(), Geo()
    for x in (-0.50, -2.30):
        g.box((x, 0, BZ1 + 0.012), (0.90, 1.00, 0.024))
        for y in (-0.30, -0.10, 0.10, 0.30):
            g.box((x, y, BZ1 + 0.03), (0.70, 0.07, 0.012))
        for y in (-0.32, 0.32):
            gh.box((x + 0.45, y, BZ1 + 0.02), (0.08, 0.10, 0.03))
            tube(gh, (x + 0.47, y - 0.06, BZ1 + 0.03), (x + 0.47, y + 0.06, BZ1 + 0.03), 0.014, 8)
        tube(gh, (x - 0.40, -0.12, BZ1 + 0.05), (x - 0.40, 0.12, BZ1 + 0.05), 0.011, 8)
        for y in (-0.12, 0.12):
            tube(gh, (x - 0.40, y, BZ1 + 0.02), (x - 0.40, y, BZ1 + 0.05), 0.009, 8)
        for k in range(7):
            for y in (-0.46, 0.46):
                bolt(gb, (x - 0.39 + k * 0.13, y, BZ1 + 0.024), (0, 0, 1), 0.009, 0.005)
    g.obj("roof.hatches", "paint2", bevel=0.004)
    gh.obj("roof.hinges", "cladding", bevel=0.002)
    gb.obj("roof.bolts", "rim_bright")
    # lashing rails along the roof's edges, ribs between the hatches, a whip
    g = Geo()
    zr = BZ1 + 0.085
    tube(g, (0.20, 0.86, zr), (-3.00, 0.86, zr), 0.018, 10)
    for k in range(7):
        x = 0.14 - k * 0.515
        tube(g, (x, 0.86, BZ1 - 0.004), (x, 0.86, zr), 0.014, 8)
        g.box((x, 0.86, BZ1 + 0.005), (0.08, 0.05, 0.012))
    g.obj("rack.rails", "cladding", bevel=0.002, mirror=True)
    g = Geo()
    sec = [(-0.03, 0.0), (0.03, 0.0), (0.018, 0.012), (-0.018, 0.012)]
    for yy in (-0.60, -0.36, -0.12, 0.12, 0.36, 0.60):
        g.sweep([(-2.84, yy, BZ1 - 0.002), (-3.06, yy, BZ1 - 0.002)], sec, up=(0, 0, 1))
    g.obj("box.roofribs", "paint", bevel=0.003)
    g = Geo()
    tube(g, (-2.98, -0.60, BZ1), (-3.04, -0.60, BZ1 + 0.26), 0.006, 6, r2=0.003)
    g.box((-2.98, -0.60, BZ1 + 0.008), (0.06, 0.06, 0.02))
    g.obj("whip", "cladding", bevel=0.002)


# ---------------------------------------------------------------------------------------
# under the box: frame, the walking beams, cases, tanks, under-run bars, a ladder, the tail
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
    g, gs, gc = Geo(), Geo(), Geo()
    # the frame: two rails from the turntable to the tail, cross members, bearers under the floor
    g.box((-0.78, 0.40, 0.90), (4.66, 0.10, 0.18))
    g.obj("frame.rails", "rim", bevel=0.004, mirror=True)
    g = Geo()
    for x in (1.50, 0.60, -0.40, BOGIE_X, -3.02):
        g.box((x, 0, 0.90), (0.10, 0.74, 0.14))
    for k in range(9):
        g.box((0.80 - k * 0.47, 0, 1.035), (0.07, 2.06, 0.09))
    g.box((1.42, 0, 0.74), (0.30, 0.70, 0.22))                         # the cab's hitch block
    g.obj("frame.cross", "rim", bevel=0.003)
    # front: double wishbones, a damper and its spring, the motor's cable
    g = Geo()
    x, f, yo = FA_X, 1, MOTOR_Y
    for xi in (x - 0.20, x + 0.20):
        tube(g, (xi, 0.34, 0.56), (x, yo - 0.01, 0.31), 0.026, 4, phase=pi / 4)
        tube(g, (xi - 0.03 * (1 if xi < x else -1), 0.50, 0.86), (x, yo - 0.02, 0.655), 0.021,
             4, phase=pi / 4)
    g.box((x, yo - 0.015, 0.48), (0.11, 0.05, 0.40))
    tube(g, (x + f * 0.17, 0.40, 0.62), (x + f * 0.16, yo - 0.01, 0.53), 0.012)       # tie rod
    coil(g, gs, (x - f * 0.13, 0.655, 0.37), (x - f * 0.10, 0.63, 0.98))
    g.box((x, 0, 0.53), (0.56, 0.74, 0.08))
    pts = [V3((x + f * 0.10, 0.55, 0.84)), V3((x + f * 0.12, 0.64, 0.80)),
           V3((x + f * 0.13, 0.69, 0.72)), V3((x + f * 0.10, yo + 0.02, 0.62))]
    for a, b in zip(pts, pts[1:]):
        tube(gc, a, b, 0.013, 8)
    # rear: a walking beam each side, pivoted on a trunnion under the frame, a motor at each end
    gw, gp = Geo(), Geo()
    bx = BOGIE_X
    xz_prism(gw, [(RA1_X + 0.15, 0.40), (RA1_X + 0.15, 0.55), (bx + 0.17, 0.63), (bx + 0.08, 0.74),
                  (bx - 0.08, 0.74), (bx - 0.17, 0.63), (RA2_X - 0.15, 0.55), (RA2_X - 0.15, 0.40),
                  (bx - 0.20, 0.45), (bx + 0.20, 0.45)], 0.575, 0.675)
    for xr in (RA1_X, RA2_X):
        tube(gw, (xr, 0.66, T_R), (xr, yo + 0.005, T_R), 0.085, 14)
        zcyl(g, (xr + (0.10 if xr == RA1_X else -0.10), 0.625, 0.55), 0.075, 0.22, 14)   # air springs
        zcyl(g, (xr + (0.10 if xr == RA1_X else -0.10), 0.625, 0.77), 0.09, 0.04, 14)
        pts = [V3((xr, 0.46, 0.88)), V3((xr + 0.02, 0.56, 0.84)), V3((xr + 0.03, 0.70, 0.74)),
               V3((xr, yo + 0.02, 0.62))]
        for a, b in zip(pts, pts[1:]):
            tube(gc, a, b, 0.013, 8)
    for y in (0.535, 0.715):                                            # the trunnion's cheeks
        xz_prism(g, [(bx + 0.30, 0.98), (bx - 0.30, 0.98), (bx - 0.085, 0.52), (bx + 0.085, 0.52)],
                 y - 0.016, y + 0.016)
    g.box((bx, 0.625, 0.95), (0.62, 0.22, 0.05))
    tube(gp, (bx, 0.50, 0.60), (bx, 0.80, 0.60), 0.05, 14)
    for y in (0.497, 0.79):
        tube(gp, (bx, y - 0.012, 0.60), (bx, y + 0.012, 0.60), 0.07, 6)
    g.obj("chassis", "rim", bevel=0.003, mirror=True)
    gs.obj("springs", "caliper", bevel=0.004, mirror=True)
    gc.obj("cables", "cable", bevel=0.003, mirror=True)
    gw.obj("walkbeam", "caliper", bevel=0.006, mirror=True)
    gp.obj("walkbeam.pins", "rim_bright", bevel=0.003, mirror=True)


def build_under():
    # battery cases behind the front wheels: ribs, a bolted lid, a cable up to the frame
    g, gl, gb, gc = Geo(), Geo(), Geo(), Geo()
    g.box((0.93, 0.80, 0.745), (1.00, 0.50, 0.47))
    for k in range(7):
        x = 1.32 - k * 0.13
        xy_prism(g, [(x - 0.035, 1.048), (x + 0.035, 1.048), (x + 0.018, 1.072), (x - 0.018, 1.072)],
                 0.55, 0.80)
    for xh in (1.40, 0.46):                              # hangers up to the floor bearers
        g.box((xh, 0.80, 1.00), (0.05, 0.44, 0.06))
    gl.box((0.93, 1.056, 0.895), (0.90, 0.012, 0.13))
    for k in range(8):
        for z in (0.85, 0.94):
            bolt(gb, (1.335 - k * 0.116, 1.062, z), (0, 1, 0), 0.009, 0.005)
    pts = [V3((0.52, 0.72, 0.98)), V3((0.50, 0.66, 1.02)), V3((0.50, 0.50, 1.00)), V3((0.50, 0.44, 0.94))]
    for a, b in zip(pts, pts[1:]):
        tube(gc, a, b, 0.016, 8)
    g.obj("battery", "paint2", bevel=0.006, mirror=True)
    gl.obj("battery.lid", "paint", bevel=0.003, mirror=True)
    gb.obj("battery.bolts", "rim_bright", mirror=True)
    gc.obj("battery.cables", "cable", bevel=0.003, mirror=True)
    # air tanks under the frame's sides
    g, gk = Geo(), Geo()
    for z, y in ((0.74, 0.70), (0.50, 0.66)):
        tube(g, (0.28, y, z), (-0.62, y, z), 0.115, 18)
        for x in (0.30, -0.64):
            tube(g, (x, y, z), (x + (0.035 if x > 0 else -0.035), y, z), 0.115, 18, r2=0.07)
        for x in (0.05, -0.40):
            tube(gk, (x - 0.02, y, z), (x + 0.02, y, z), 0.122, 18)
    g.obj("tanks", "rim", bevel=0.002, mirror=True)
    gk.obj("tank.straps", "cladding", bevel=0.002, mirror=True)
    # right side: under-run bars; left side: a ladder under the roller door
    g = Geo()
    for z in (0.50, 0.74):
        tube(g, (0.30, -1.07, z), (-0.64, -1.07, z), 0.032, 4, phase=pi / 4)
    for x in (0.16, -0.50):
        tube(g, (x, -1.04, 0.47), (x, -1.04, BZ0), 0.028, 4, phase=pi / 4)
    g.obj("underrun", "paint2", bevel=0.004)
    g, gr = Geo(), Geo()
    for z, y in ((0.80, 1.00), (0.52, 1.04)):
        g.box((-0.20, y, z), (0.64, 0.20, 0.028))
        g.box((-0.20, y + 0.094, z + 0.016), (0.64, 0.012, 0.05))
        for k in range(12):
            gr.box((-0.475 + k * 0.05, y, z + 0.0165), (0.014, 0.16, 0.005))
    for x in (-0.50, 0.10):
        tube(g, (x, 0.96, BZ0), (x, 0.99, 0.80), 0.02, 4, phase=pi / 4)
        tube(g, (x, 0.99, 0.80), (x, 1.03, 0.52), 0.02, 4, phase=pi / 4)
    g.obj("ladder", "paint2", bevel=0.004)
    gr.obj("ladder.ribs", "rim_bright")
    # the tail: an under-run beam on hangers, a hitch, a fold-up step, a plate
    g = Geo()
    g.prism([(BX1 + 0.05, -1.08, 0.50), (BX1 + 0.05, 1.08, 0.50), (BX1 - 0.03, 1.08, 0.50),
             (BX1 - 0.09, 0.98, 0.50), (BX1 - 0.09, -0.98, 0.50), (BX1 - 0.03, -1.08, 0.50)],
            (0, 0, 0.16))
    for s in (1, -1):
        g.box((BX1 + 0.01, s * 0.40, 0.84), (0.08, 0.10, 0.48))
        g.box((BX1 + 0.01, s * 0.86, 0.87), (0.06, 0.06, 0.42))
    g.box((BX1 - 0.06, 0, 0.47), (0.12, 0.12, 0.09))
    g.box((BX1 - 0.07, 0, 0.36), (0.20, 0.56, 0.028))                  # the step
    for s in (1, -1):
        tube(g, (BX1 - 0.02, s * 0.25, 0.50), (BX1 - 0.07, s * 0.25, 0.37), 0.018, 4, phase=pi / 4)
    g.obj("bumper.rear", "paint2", bevel=0.006)
    g = Geo()
    g.box((BX1 - 0.122, 0, 0.47), (0.006, 0.07, 0.05))
    g.obj("hitch.hole", "void")
    g = Geo()
    for s in (1, -1):
        g.box((BX1 - 0.06, s * 0.33, 0.52), (0.05, 0.03, 0.07))
        ring(g, (BX1 - 0.10, s * 0.33, 0.50))
    g.obj("hooks.rear", "caliper", bevel=0.003)
    g = Geo()
    for k in range(9):
        g.box((BX1 - 0.07, -0.24 + k * 0.06, 0.3765), (0.16, 0.014, 0.005))
    g.obj("tail.steppads", "rim_bright")
    g = Geo()                                           # reversing lamps and a plate lamp
    for s in (1, -1):
        g.box((BX1 - 0.092, s * 0.80, 0.58), (0.006, 0.16, 0.05))
    g.obj("led.reverse", "led_front")


# ---------------------------------------------------------------------------------------
# bolts and lettering
# ---------------------------------------------------------------------------------------
def build_bolts():
    """Rows of bolt heads on the cab as built."""
    def row(pts, proj):
        for u, v in pts:
            loc, n = on_body(u, v, proj)
            if loc is not None:
                bolt(BOLTS, loc, n)
    row([(2.42 - k * 0.15, 0.56) for k in range(8)], 'z')               # roof plate
    row([(1.36, 0.08 + k * 0.14) for k in range(4)], 'z')
    row([(2.44 - k * 0.14, BELT + 0.035) for k in range(8)], 'y')       # the door's foot
    row([(2.44 - k * 0.14, SILL - 0.04) for k in range(8)], 'y')        # under the window
    row([(2.56, 1.16 + k * 0.085) for k in range(4)], 'y')              # the cowl side
    row([(2.96 - k * 0.11, BELT + 0.035) for k in range(3)], 'y')       # the nose side
    row([(2.96 - k * 0.11, 0.90) for k in range(2)], 'y')
    row([(2.99, 1.16 + k * 0.085) for k in range(3)], 'y')
    row([(1.35, 1.14 + k * 0.085) for k in range(4)], 'y')              # the cab's rear edge
    row([(2.58, 1.58 + k * 0.10) for k in range(5)], 'y')               # the front pillar
    BOLTS.obj("bolts", "rim_bright", mirror=True)
    BOLTS_L.obj("bolts.left", "rim_bright")


def diamond(g, gi, c, right, up, r):
    """A hazard placard: a square on its corner, a dark border inside it."""
    c, right, up = V3(c), V3(right).normalized(), V3(up).normalized()
    n = right.cross(up).normalized()
    for gg, k, lift in ((g, 1.0, 0.0012), (gi, 0.86, 0.0018), (g, 0.80, 0.0024)):
        gg.add([c + n * lift + right * (a * r * k) + up * (b * r * k)
                for a, b in ((1, 0), (0, 1), (-1, 0), (0, -1))], [(0, 1, 2, 3)])


def build_lettering():
    g, gm, gh, gd = Geo(), Geo(), Geo(), Geo()
    # number plates bolted over the ribs: the left one behind the roller door, the right one long
    gp, gb = Geo(), Geo()
    gp.box((-2.03, BW + 0.008, 1.78), (1.56, 0.016, 0.82))
    gp.box((-1.00, -(BW + 0.008), 1.78), (2.70, 0.016, 0.82))
    for x0, w, s in ((-2.03, 1.56, 1), (-1.00, 2.70, -1)):
        n = int(w / 0.18)
        for k in range(n + 1):
            for z in (1.41, 2.15):
                bolt(gb, (x0 - w / 2 + 0.04 + k * (w - 0.08) / n, s * (BW + 0.016), z), (0, s, 0))
    gp.obj("box.plates", "paint2", bevel=0.004)
    gb.obj("box.platebolts", "rim_bright")
    yl, yr = BW + 0.016, -(BW + 0.016)
    L, R, U = (-1, 0, 0), (1, 0, 0), (0, 0, 1)
    stencil(gm, NUM, 0.50, on_plane((-1.80, yl, 1.80), L, U))
    stencil(gm, "UNIT", 0.05, on_plane((-1.80, yl, 2.085), L, U), gap=0.3, cut=0)
    diamond(gh, gd, (-2.50, yl, 1.82), L, U, 0.20)
    stencil(gd, "3", 0.15, on_plane((-2.50, yl + 0.003, 1.82), L, U), cut=0)
    chevrons(gh, on_plane((-2.03, yl, 1.455), L, U), 1.44, 0.07, 14, 0.06)
    stencil(gm, "MULE " + NUM, 0.46, on_plane((-1.22, yr, 1.79), R, U))
    stencil(gm, "BRAKK INDUSTRIAL", 0.05, on_plane((-0.62, yr, 2.085), R, U), gap=0.22, cut=0)
    stencil(gm, "MAX LOAD 4200 KG  -  GVW 9800 KG", 0.035, on_plane((-1.72, yr, 2.085), R, U),
            gap=0.2, cut=0)
    diamond(gh, gd, (0.08, yr, 1.81), R, U, 0.20)
    stencil(gd, "3", 0.15, on_plane((0.08, yr - 0.003, 1.81), R, U), cut=0)
    chevrons(gh, on_plane((-1.00, yr, 1.455), R, U), 2.58, 0.07, 26, 0.06)
    # the cab's doors
    for side in (1, -1):
        stencil(g, NUM, 0.25, on_side(2.20, 1.305, side))
        stencil(g, "MULE", 0.10, on_side(1.84, 1.315, side))
        stencil(g, "BRAKK INDUSTRIAL", 0.030, on_side(1.84, 1.255, side), gap=0.2, cut=0)
        stencil(g, "GVW 9800 KG", 0.024, on_side(1.84, 1.21, side), gap=0.2, cut=0)
    # the box's roof, the tail
    stencil(g, NUM, 0.62, on_plane((-1.40, 0, BZ1 + 0.0005), (-1, 0, 0), (0, -1, 0)))
    xt = BX1 - 0.027
    B = (0, -1, 0)
    stencil(g, "MULE", 0.17, on_plane((xt, 0.44, 2.00), B, U))
    stencil(g, "B-" + NUM, 0.17, on_plane((xt, -0.44, 2.00), B, U))
    stencil(g, "KEEP CLEAR", 0.045, on_plane((xt, 0.44, 1.90), B, U), gap=0.2, cut=0)
    stencil(g, "LOCK BOTH RODS", 0.045, on_plane((xt, -0.44, 1.90), B, U), gap=0.2, cut=0)
    for s in (1, -1):
        chevrons(gh, on_plane((xt, s * 0.44, 1.27), B, U), 0.50, 0.12, 5, -s * 0.08)
        chevrons(gh, on_plane((BX1 - 0.0905, s * 0.56, 0.58), B, U), 0.26, 0.10, 3, -s * 0.07)
        d = V3((-0.17, s * 0.51, 0)).normalized()
        chevrons(gh, on_plane((3.155, s * 0.86, 0.645), d * s, U), 0.44, 0.07, 5, s * 0.05)
    chevrons(gh, on_plane(((DOOR_X0 + DOOR_X1) / 2, 1.0735, DOOR_Z + 0.022), L, U), 1.40, 0.04, 18, 0.03)
    # on the dark parts
    stencil(gm, "BRAKK", 0.058, on_plane((3.1545, 0, 1.19), (0, 1, 0), U), gap=0.2)
    stencil(gm, "TOW 12T", 0.028, on_plane((3.2905, 0, 0.635), (0, 1, 0), U), gap=0.2, cut=0)
    stencil(gm, "BK 9-6310", 0.05, on_plane((BX1 - 0.0905, 0, 0.585), B, U), gap=0.18, cut=0)
    stencil(gm, "CRYO-2", 0.07, on_plane((0.70, 0.6805, BZ1 + 0.04), L, U), gap=0.18)
    stencil(gm, "CRYO-2", 0.07, on_plane((0.70, -0.6805, BZ1 + 0.04), R, U), gap=0.18)
    for s, rt in ((1, L), (-1, R)):
        stencil(gm, "HV 800V", 0.05, on_plane((0.93, s * 1.0625, 0.875), rt, U), gap=0.2, cut=0)
    upf = V3((-0.20, 0, 0.24)).normalized()
    for s in (1, -1):                       # the unit number on the front fender slopes
        stencil(gm, NUM, 0.16, on_plane(V3((2.775, s * 0.95, 0.865)) + V3((0.77, 0, 0.64)) * 0.001,
                                        (0, 1, 0), upf))
    g.obj("lettering", "decal")
    gm.obj("markings", "mark")
    gh.obj("chevrons", "hazard")
    gd.obj("placard.ink", "ink")


# ---------------------------------------------------------------------------------------
# wheels: the Brakk wheel (a lugged tire on a dished steel rim with a bolted bead ring),
# here with a finned hub motor behind it and its copper showing through the dish's windows
# ---------------------------------------------------------------------------------------
N_LUG = 24
TIRE_TEXT = "BRAKK  TRAKTOR  E/T    38 X 13.5 R20    "


def build_wheel(tag, cx, side, loc=None, yaw=0.0, motor=True):
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
    g.lathe([(-y, r) for y, r in half[:0:-1]] + half, 96)

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
    y_a, r_a, y_b, r_b = hw - 0.045, Rr - 0.014, hw - 0.115, 0.108
    g.lathe([(y_a, r_a), (y_b, r_b), (y_b - 0.014, r_b), (y_a - 0.014, r_a)], 56)
    g.lathe([(hw - 0.135, 0.004), (hw - 0.135, 0.112), (hw - 0.092, 0.112), (hw - 0.08, 0.096),
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
             [(-0.004, 0.001), (-0.004, 0.029), (0.0012, 0.029), (0.0012, 0.001)], 14)
        an = 2 * pi * k / 8
        gbr.lathe([(hw - 0.081, 0.002), (hw - 0.081, 0.0125), (hw - 0.06, 0.0125),
                   (hw - 0.06, 0.002)], 6,
                  xf=Matrix.Translation((0.072 * cos(an), 0, 0.072 * sin(an))))
    gv.obj("rimholes." + tag, "stator" if motor else "void", flip_y=flip, loc=loc)
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
    if motor:
        # the hub motor: a finned can on the wheel's inner face, a bolted end plate
        g = Geo()
        y0 = -hw - 0.085
        prof = [(y0, 0.004), (y0, 0.15), (y0 + 0.012, 0.15), (y0 + 0.012, 0.178)]
        for k in range(5):
            ya = y0 + 0.016 + k * 0.019
            prof += [(ya, 0.178), (ya, 0.205), (ya + 0.008, 0.205), (ya + 0.008, 0.178)]
        prof += [(-hw + 0.04, 0.178), (-hw + 0.04, 0.004)]
        g.lathe(prof, 40)
        g.obj("motor." + tag, "rim", bevel=0.0015, flip_y=flip, loc=loc)
        g = Geo()
        for k in range(10):
            a = 2 * pi * k / 10
            g.lathe([(y0 - 0.006, 0.001), (y0 - 0.006, 0.009), (y0, 0.009), (y0, 0.001)], 6,
                    xf=Matrix.Translation((0.125 * cos(a), 0, 0.125 * sin(a))))
        g.obj("motorbolts." + tag, "rim_bright", flip_y=flip, loc=loc)
        g = Geo()
        g.lathe([(y0 + 0.0125, 0.151), (y0 + 0.0125, 0.177), (y0 + 0.0155, 0.177),
                 (y0 + 0.0155, 0.151)], 40)
        g.obj("motorband." + tag, "stator", flip_y=flip, loc=loc)
    for ob in list(K.CAR.objects)[n0:]:
        ob.rotation_euler = (0, 0, yaw)


# ---------------------------------------------------------------------------------------
# interior
# ---------------------------------------------------------------------------------------
def build_interior():
    g = Geo()
    g.box((2.12, 0, 0.94), (1.70, 1.14, 0.04))
    g.box((1.36, 0, 1.52), (0.04, 1.40, 1.20))
    g.prism([(3.00, -0.62, 1.10), (3.00, -0.62, 1.46), (2.80, -0.66, 1.49), (2.66, -0.70, 1.40),
             (2.70, -0.70, 1.10)], (0, 1.32, 0))
    g.box((2.05, 0, 1.06), (0.9, 0.16, 0.24))
    g.obj("interior.tub", "interior", bevel=0.006)
    g = Geo()
    tf = Matrix.Rotation(rad(-10), 3, 'Y')
    for y in (0.37, -0.37):
        xs = 1.98
        g.box((xs, y, 1.14), (0.48, 0.48, 0.14))
        g.box((xs - 0.30, y, 1.50), (0.12, 0.46, 0.66), rot=tf)
        g.box((xs - 0.37, y, 1.91), (0.08, 0.26, 0.17), rot=tf)
        for s in (-1, 1):
            g.box((xs, y + s * 0.245, 1.17), (0.44, 0.05, 0.16))
        g.box((xs, y, 1.01), (0.20, 0.20, 0.12))
    g.obj("interior.seats", "seat", bevel=0.014, segs=3)
    g = Geo()
    wheel = (Matrix.Translation((2.50, 0.37, 1.50)) @ Matrix.Rotation(rad(-68), 4, 'Y')
             @ Matrix.Rotation(pi / 2, 4, 'X'))
    g.lathe([(-0.014, 0.185), (0.0, 0.20), (0.014, 0.185), (0.0, 0.17)], 8, xf=wheel)
    g.box((2.60, 0.37, 1.45), (0.24, 0.06, 0.06), rot=Matrix.Rotation(rad(-22), 3, 'Y'))
    for a in (30, 150, 270):
        tube(g, wheel @ V3((0, -0.02, 0)), wheel @ V3((0.18 * cos(rad(a)), 0, 0.18 * sin(rad(a)))),
             0.012, 6)
    g.obj("interior.wheel", "interior", sharp=40)
    g = Geo()
    scr = Matrix.Rotation(rad(-24), 3, 'Y')
    g.box((2.69, 0.0, 1.53), (0.008, 0.44, 0.17), rot=scr)
    g.box((2.72, 0.37, 1.60), (0.008, 0.28, 0.07), rot=scr)
    g.box((2.69, -0.37, 1.53), (0.008, 0.24, 0.13), rot=scr)
    g.obj("interior.screens", "screen")


# ---------------------------------------------------------------------------------------
# views of its own, and the build
# ---------------------------------------------------------------------------------------
K.VIEWS["hero"].update(dir=(1.0, 1.12, 0.17), lens=58, focus=(2.4, 0.9, 1.0))
K.VIEWS["rear"].update(dir=(-1.0, -0.86, 0.30), focus=(-2.6, -0.9, 1.2))
K.VIEWS["back"].update(dir=(-1.0, 0.0, 0.10))
K.VIEWS.update(
    door=dict(dir=(0.25, 1.0, 0.10), lens=70, target=(-0.2, 1.1, 1.6), dist=6.0),
    bogie=dict(dir=(-0.5, 1.0, 0.08), lens=85, target=(BOGIE_X, 1.0, 0.6), dist=6.0),
    nose=dict(dir=(1.0, 0.5, 0.12), lens=85, target=(3.0, 0.4, 1.2), dist=6.0),
    roof=dict(dir=(0.5, 0.8, 0.8), lens=60, target=(-0.6, 0, 2.5), dist=8.0),
)


def main():
    K.materials(paint=(0.115, 0.135, 0.040), paint_finish=(0.0, 0.42, 0.4),
                paint2=(0.035, 0.038, 0.042), paint2_finish=(0.35, 0.52, 0.0),
                dust=(0.24, 0.21, 0.17), dust_amount=0.45, dust_z=(0.45, 1.25),
                glass=(0.32, 0.36, 0.34),
                led_front=(0.86, 0.94, 1.0), led_accent=(1.0, 0.42, 0.03),
                caliper=(0.95, 0.20, 0.01), seat=(0.09, 0.05, 0.02),
                decal=(0.76, 0.76, 0.72), screen=(0.30, 0.85, 0.75))
    K.pbr("mark", (0.76, 0.76, 0.72), 0.0, 0.5)             # white markings on the dark parts
    K.pbr("hazard", (0.95, 0.36, 0.01), 0.0, 0.5)           # hazard stripes, cases, bands
    K.pbr("ink", (0.02, 0.02, 0.022), 0.0, 0.5)
    K.pbr("cable", (0.95, 0.22, 0.01), 0.0, 0.45)           # high voltage
    K.pbr("stator", (0.72, 0.27, 0.07), 1.0, 0.32)          # the motors' copper
    K.pbr("tiremark", (0.085, 0.085, 0.085), 0.0, 0.6)
    K.pbr("crate_a", (0.36, 0.38, 0.36), 0.0, 0.55)
    K.pbr("crate_c", (0.30, 0.20, 0.10), 0.0, 0.7)
    K.emit("sensor", (0.15, 0.85, 1.0), 14.0)
    K.emit("worklight", (1.0, 0.86, 0.66), 9.0)
    build_hull()
    K.log("hull")
    build_fenders()
    build_lights()
    build_nose()
    build_cab()
    build_collar()
    build_box()
    build_cargo()
    build_roof()
    build_chassis()
    build_under()
    build_bolts()
    build_lettering()
    build_interior()
    K.log("details")
    for side, s in ((1, "l"), (-1, "r")):
        build_wheel("f" + s, FA_X, side)
        build_wheel("m" + s, RA1_X, side)
        build_wheel("r" + s, RA2_X, side)
    K.log("wheels")
    K.shoot(extra=dict(view="rear", size=(840, 400), corner="tl"))


main()
