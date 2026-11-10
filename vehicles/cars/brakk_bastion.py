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
tubes for the rest. The helpers tube, bolt, plate, stencil, chevrons, pylon, coil and the
wheel are the Hauler's.
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
FA_X, RA_X = 1.58, -1.52            # axles: wheelbase 3.1
T_R, T_W, T_RIM, T_OUT = 0.475, 0.34, 0.25, 1.10       # tire radius, width, rim, outer face
ROOF, BELT = 1.86, 1.02
H_Z, W_Z = 1.74, 1.40               # the slit windows: top and sill
FEN_Z, FEN_T = 1.07, 0.03           # fender plates: top height, thickness
TAIL_X = -2.14
SPARE_X, SPARE_Z = TAIL_X - 0.07 - T_W / 2, 1.10
NUM = "41"
HOOD_K = 0.306                      # the hood's slope: 17 degrees


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
# the family's helpers (from the Hauler)
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
                floor="underbody", trim="cladding", nose="cladding", hatch="paint")


def build_hull():
    K.build_body(hull_stations(), hull_panel, HULL_MAT, 1.0, 1.0, name="hull",
                 front=dict(kind="flat", panel="nose"), rear=dict(kind="flat", panel="hatch"),
                 glass=[("glass_ws", 0.055), ("glass_f", 0.05), ("glass_r", 0.05),
                        ("glass_h", 0.085)],
                 subdiv=2, gap=0.004, bevel=0.008)


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
    pylon(g, gf, ga, 2.34, 0.52, 0.66, 1.20, 45)
    pylon(g, gr, ga, -2.09, 0.565, 0.74, 1.24, 135)
    ga.obj("led.turn", "led_accent", mirror=True)
    g.obj("pylons", "cladding", bevel=0.004, mirror=True)
    gf.obj("led.front", "led_front", mirror=True)
    gr.obj("led.rear", "led_rear", mirror=True)
    # a blade of light across the prow, from pylon to pylon
    g = Geo()
    g.box((2.404, 0, 1.042), (0.014, 0.66, 0.05))
    g.obj("prow.blade.housing", "cladding", bevel=0.003)
    g = Geo()
    g.box((2.412, 0, 1.042), (0.006, 0.62, 0.022))
    g.obj("led.blade", "led_front")
    # the bar over the windshield: a housing on the roof's front edge, eight cells
    g = Geo()
    g.prism([(0.63, -0.56, ROOF - 0.03), (0.63, -0.56, ROOF + 0.065), (0.49, -0.56, ROOF + 0.065),
             (0.43, -0.56, ROOF - 0.005)], (0, 1.12, 0))
    for k in range(9):
        y = -0.51 + 1.02 * k / 8
        g.box((0.634, y, ROOF + 0.025), (0.012, 0.016, 0.06))
    g.obj("roofbar", "cladding", bevel=0.004)
    g = Geo()
    g.box((0.631, 0, ROOF + 0.025), (0.006, 1.01, 0.04))
    g.obj("led.roofbar", "led_front")
    g = Geo()                                           # amber clearance lamps at its ends
    g.box((0.56, 0.564, ROOF + 0.028), (0.07, 0.006, 0.03))
    g.obj("led.clear", "led_accent", mirror=True)
    g = Geo()                                           # a stop strip over the hatch
    g.box((-1.405, 0, ROOF + 0.014), (0.03, 0.56, 0.028))
    g.obj("stop.housing", "cladding", bevel=0.003)
    g = Geo()
    g.box((-1.4215, 0, ROOF + 0.014), (0.004, 0.50, 0.016))
    g.obj("led.stop", "led_rear")


# ---------------------------------------------------------------------------------------
# bumpers, winch, skids, steps
# ---------------------------------------------------------------------------------------
def ring(g, c, r0=0.030, r1=0.050, t=0.009, n=14, rot=None):
    xf = Matrix.Translation(c)
    if rot is not None:
        xf = xf @ rot
    g.lathe([(-t, r0), (-t, r1), (t, r1), (t, r0)], n, xf=xf)


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
    # a charge port on the nose's left side, a touch pad by each front door's handle
    g, gb = Geo(), Geo()
    pc = V3((1.50, 0.58, 1.205))
    g.prism([(pc.x + 0.085 * cos(rad(22.5 + 45 * k)), 0.578, pc.z + 0.085 * sin(rad(22.5 + 45 * k)))
             for k in range(8)], (0, 0.012, 0))
    g.box((pc.x, 0.594, pc.z + 0.074), (0.07, 0.014, 0.022))            # its hinge
    for k in range(4):
        a = rad(45 + 90 * k)
        bolt(gb, pc + V3((0.062 * cos(a), 0.01, 0.062 * sin(a))), (0, 1, 0), 0.007, 0.004)
    g.obj("port.cover", "paint2", bevel=0.003)
    gb.obj("port.bolts", "rim_bright")
    g = Geo()
    g.box((0.30, side_y(1.10) + 0.004, 1.10), (0.05, 0.008, 0.075),
          rot=Matrix.Rotation(rad(-16), 3, 'X'))
    g.obj("door.pad", "gloss_black", bevel=0.002, mirror=True)
    g = Geo()
    g.box((0.30, side_y(1.115) + 0.009, 1.115), (0.03, 0.003, 0.012),
          rot=Matrix.Rotation(rad(-16), 3, 'X'))
    g.obj("led.pad", "sensor", mirror=True)
    # wipers
    g = Geo()
    for y0 in (0.03, -0.37):
        blade = []
        for k in range(7):
            t = k / 6
            loc, n = on_body(y0 + 0.34 * t, 1.525 + 0.19 * t, 'x')
            blade.append(loc + n * 0.016)
        g.sweep(blade, [(-0.005, -0.009), (0.005, -0.009), (0.005, 0.007), (-0.005, 0.007)],
                up=(1, 0, 1))
        piv, n = on_body(y0 + 0.01, 1.505, 'x')
        tube(g, piv + n * 0.012, blade[3] + n * 0.012, 0.006, 6)
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
    tube(g, (-1.30, -0.36, ROOF), (-1.36, -0.36, ROOF + 0.26), 0.006, 6, r2=0.003)   # a whip
    g.box((-1.30, -0.36, ROOF + 0.008), (0.06, 0.06, 0.02))
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
    stencil(g, "HV 800V", 0.03, on_plane((1.33, 0.5812, 1.185), (-1, 0, 0), (0, 0, 1)),
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
def build_interior():
    g = Geo()
    g.box((-0.20, 0, 0.60), (2.30, 1.22, 0.04))
    g.box((-1.36, 0, 1.0), (0.04, 1.04, 0.84))
    g.prism([(0.98, -0.68, 0.90), (0.98, -0.68, 1.43), (0.86, -0.68, 1.43), (0.74, -0.68, 1.32),
             (0.78, -0.68, 0.90)], (0, 1.36, 0))
    g.prism([(1.20, -0.44, 1.0), (1.20, -0.44, 1.45), (0.97, -0.44, 1.45), (0.97, -0.44, 1.0)],
            (0, 0.88, 0))
    g.box((-0.10, 0, 0.76), (1.5, 0.20, 0.30))
    g.obj("interior.tub", "interior", bevel=0.006)
    g = Geo()
    tf = Matrix.Rotation(rad(-12), 3, 'Y')
    for y in (0.40, -0.40):
        for xs in (0.22, -0.60):
            g.box((xs, y, 0.86), (0.48, 0.50, 0.14))
            g.box((xs - 0.295, y, 1.21), (0.12, 0.48, 0.64), rot=tf)
            g.box((xs - 0.375, y, 1.62), (0.08, 0.26, 0.17), rot=tf)
            for s in (-1, 1):
                g.box((xs, y + s * 0.255, 0.89), (0.44, 0.05, 0.16))
    g.obj("interior.seats", "seat", bevel=0.014, segs=3)
    g = Geo()
    wheel = (Matrix.Translation((0.62, 0.40, 1.24)) @ Matrix.Rotation(rad(-62), 4, 'Y')
             @ Matrix.Rotation(pi / 2, 4, 'X'))
    g.lathe([(-0.014, 0.175), (0.0, 0.19), (0.014, 0.175), (0.0, 0.16)], 8, xf=wheel)
    g.box((0.72, 0.40, 1.20), (0.22, 0.06, 0.06), rot=Matrix.Rotation(rad(-28), 3, 'Y'))
    for a in (30, 150, 270):
        tube(g, wheel @ V3((0, -0.02, 0)), wheel @ V3((0.17 * cos(rad(a)), 0, 0.17 * sin(rad(a)))),
             0.012, 6)
    g.obj("interior.wheel", "interior", sharp=40)
    g = Geo()
    scr = Matrix.Rotation(rad(-22), 3, 'Y')
    g.box((0.762, 0.0, 1.36), (0.008, 0.40, 0.16), rot=scr)
    g.box((0.80, 0.40, 1.44), (0.008, 0.26, 0.07), rot=scr)
    g.box((0.762, -0.40, 1.36), (0.008, 0.22, 0.12), rot=scr)
    g.obj("interior.screens", "screen")


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
    K.shoot(extra=dict(view="top", size=(900, 430), corner="tl"))


main()
