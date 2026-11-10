"""Tanager Porter: a parcel delivery van, two seats and a hold (all names made up), built
on vehicles/carkit.py.

Run (always through the wrapper, one Blender job at a time on this machine):
    vehicles/blender.sh vehicles/cars/tanager_porter.py --out DIR --preview
    vehicles/blender.sh vehicles/cars/tanager_porter.py --out DIR --sheet

The third Tanager, after the Mino and the Cab (docs/progress/AG18/tanager_mino/README.md
lists the family's cues, all repeated here): the soft tall box, holes for windows with flat
glass and a fat seal, the gloss visor with a light bar between two lamp rings and a
dot-matrix display, squircle arches, stepped grained cladding with a bump strip, steel
wheels under slotted covers, a cap roof with its gear on two rails, roundel and small
print, a round badge.

Its own job: a walk-through cab under a low roof and a tall hold behind it, the step
between them a brow with a third visor (the route display); a sliding cab door each side
(the kerb side one built open over a low step); a bank of parcel lockers with a kiosk let
into the kerb flank (some lit, one open); a roller door at the back, part open over the
parcels; a roof rack with a ladder, a drone dock and its drone; a hand truck clipped to
the off side sill; mirrors with kerb cameras under them.

The body is ten lines over seventeen stations. Windows, the roller door and the open
locker are holes cut through the skin; the left door's panels, glass and details are
objects of their own, slid back at the end.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import bmesh                                                        # noqa: E402
import bpy                                                          # noqa: E402
import carkit as K                                                  # noqa: E402
from carkit import (Geo, Matrix, V3, atan2, cos, hypot, on_body, pi, rad, sin,    # noqa: E402
                    stud)

# ---------------------------------------------------------------------------------------
# dimensions
# ---------------------------------------------------------------------------------------
FA_X, RA_X = 1.70, -1.70            # axles: wheelbase 3.4
T_R, T_W, T_RIM, T_OUT = 0.34, 0.215, 0.232, 0.918     # tire radius, width, rim, outer face
ARCH_A, ARCH_B, ARCH_ZC, ARCH_N = 0.40, 0.405, 0.345, 3.4   # squircle arch: half width, rise
BELT, HEAD, CROOF, ROOF = 1.00, 1.93, 2.05, 2.35    # belt, cab glass header, cab roof, hold
STEP = 0.545                        # the cladding's step
D_F, D_R = 1.17, 0.33               # the cab door's front and rear edges as built
RG_X, FD = 1.85, 0.07               # the station ahead of the door; the brow's run
# their stations in the cage: subdivision draws an edge toward its neighbors,
# (prev + 4 x + next) / 6, and the brow's top stands FD behind the door's rear edge
D_RC = (4 * (6 * D_R + FD) - (6 * D_F - RG_X)) / 19.0
D_FC = 6 * D_R + FD - 5 * D_RC
SLIDE = V3((-0.88, 0.085, 0.0))     # how far the open door has gone
CFLOOR, HFLOOR = 0.42, 0.77         # the cab's floor, the hold's
GD = 0.011                          # how far the glass lies behind the skin
NUM, ROUTE = "58", "12"
OPEN_Z = 1.40                       # the roller door's lower edge
DOOR = []                           # objects that slide with the left door
LOCK_X = (-1.015, -1.37, -1.725, -2.08)     # the lockers: columns, rows, half sizes
LOCK_Z = (1.605, 1.30, 0.995)
LW, LH = 0.16, 0.135
LOCK_OPEN = (1, 1)                  # (row, column) of the open one
LOCK_LIT = ("g.ag", "..g.", "ag.g")         # g ready, a held, . dark


def tail_x(z):
    """The tail is one plane, leaning forward three degrees."""
    return -2.65 + (z - 0.32) * 0.052


def side_y(z):
    """The flank is one plane from the belt to the roof's corner."""
    return 0.93 - (z - BELT) * 0.049


# ---------------------------------------------------------------------------------------
# the family's helpers (from the Mino and the Cab): outlines, things laid on the skin
# ---------------------------------------------------------------------------------------
def rpoly(corners, r, n=6, normals=False):
    """A polygon with its corners rounded off (radius r, or one per corner); with normals
    also each point's outward direction (a convex polygon)."""
    m = len(corners)
    rs = r if isinstance(r, (list, tuple)) else [r] * m
    out, nrm = [], []
    for k in range(m):
        p = V3((*corners[k], 0))
        d1 = (V3((*corners[k - 1], 0)) - p).normalized()
        d2 = (V3((*corners[(k + 1) % m], 0)) - p).normalized()
        half = d1.angle(d2) / 2
        t = rs[k] / max(1e-6, abs(sin(half) / cos(half)))
        c = p + (d1 + d2).normalized() * (rs[k] / sin(half))
        a, b = p + d1 * t - c, p + d2 * t - c
        a0 = atan2(a.y, a.x)
        da = (atan2(b.y, b.x) - a0 + pi) % (2 * pi) - pi
        for i in range(n + 1):
            ang = a0 + da * i / n
            out.append((c.x + rs[k] * cos(ang), c.y + rs[k] * sin(ang)))
            nrm.append((cos(ang), sin(ang)))
    return (out, nrm) if normals else out


def rect(cu, cv, a, b):
    return [(cu + a, cv - b), (cu + a, cv + b), (cu - a, cv + b), (cu - a, cv - b)]


def rrect(cu, cv, a, b, r, n=6):
    return rpoly(rect(cu, cv, a, b), r, n)


AXIS_U = {'y': V3((1, 0, 0)), 'Y': V3((1, 0, 0)), 'x': V3((0, 1, 0)), 'X': V3((0, 1, 0)),
          'z': V3((1, 0, 0))}


def skin(u, v, proj):
    """The skin under (u, v); a ray that slips through a panel gap looks beside it."""
    for du, dv in ((0, 0), (0, 0.004), (0, -0.004), (0.004, 0), (-0.004, 0), (0, 0.009),
                   (0, -0.009), (0.009, 0), (-0.009, 0)):
        loc, n = on_body(u + du, v + dv, proj)
        if loc is not None:
            return loc, n
    raise ValueError("nothing under (%.3f, %.3f) seen along %s" % (u, v, proj))


def pad(g, cu, cv, a, b, r, proj, lift=0.004, sink=0.003, nv=4, nc=5, step=0.03):
    """A rounded-rectangle plate lying on the skin, following it: half sizes a (along u)
    and b, corner radius r, its face lift over the skin."""
    r = min(r, a, b)
    cols = []
    for k in range(nc, 0, -1):
        t = rad(90.0 * k / nc)
        cols.append((-(a - r) - r * sin(t), b - r + r * cos(t)))
    ns = max(1, int(2 * (a - r) / step + 0.999)) if a - r > 1e-6 else 0
    for k in range(ns + 1):
        cols.append((-(a - r) + (2 * (a - r) * k / ns if ns else 0.0), b))
    for k in range(1, nc + 1):
        t = rad(90.0 * k / nc)
        cols.append(((a - r) + r * sin(t), b - r + r * cos(t)))
    top, bot = [], []
    for (du, h) in cols:
        h = max(h, 0.0012)
        for j in range(nv + 1):
            loc, n = skin(cu + du, cv + h * (2.0 * j / nv - 1.0), proj)
            top.append(loc + n * lift)
            bot.append(loc - n * sink)
    nn, m = len(cols), nv + 1
    N = nn * m
    fs = []
    for i in range(nn - 1):
        for j in range(nv):
            q = (i * m + j, (i + 1) * m + j, (i + 1) * m + j + 1, i * m + j + 1)
            fs += [q, tuple(N + k for k in q)]
        for j in (0, nv):
            fs.append((i * m + j, (i + 1) * m + j, N + (i + 1) * m + j, N + i * m + j))
    for i in (0, nn - 1):
        for j in range(nv):
            fs.append((i * m + j, i * m + j + 1, N + i * m + j + 1, N + i * m + j))
    g.add(top + bot, fs)


def bar_on(g, pts, proj, w, h, lift=0.0, step=0.02):
    """A bar of width w and height h lying on the skin along a path given in projection."""
    P, U = [], []
    for a, b in zip(pts, pts[1:]):
        n = max(1, int(hypot(b[0] - a[0], b[1] - a[1]) / step))
        for k in range(n + (1 if b is pts[-1] else 0)):
            t = k / n
            loc, nr = skin(a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t, proj)
            P.append(loc + nr * lift)
            U.append(nr)
    g.sweep(P, [(-w / 2, -0.002), (w / 2, -0.002), (w / 2, h), (-w / 2, h)], up=U)


def tile(g, cu, cv, a, b, proj, lift, sink=0.001):
    """A small rectangle on the skin: a flat mark (sink None) or a raised block."""
    q = [skin(cu + du, cv + dv, proj) for du, dv in ((-a, -b), (a, -b), (a, b), (-a, b))]
    top = [p + n * lift for p, n in q]
    if sink is None:
        g.add(top, [(0, 1, 2, 3)])
    else:
        g.hexa([p - n * sink for p, n in q] + top)


def text_proj(g, txt, size, u0, v0, proj, lift=0.0012, spacing=1.0):
    """Lettering on the nose ('x') or the tail ('X'), read from outside, its middle at
    (u0, v0) = (y, z)."""
    vs, fs = K.text_mesh(txt, size, spacing)
    sg = -1.0 if proj == 'X' else 1.0
    out = []
    for p in vs:
        loc, n = on_body(u0 + sg * p.x, v0 + p.y, proj)
        if loc is None:
            return
        out.append(loc + n * lift)
    g.add(out, fs)


GLYPH = {
    "A": (".###.", "#...#", "#...#", "#####", "#...#", "#...#", "#...#"),
    "B": ("####.", "#...#", "#...#", "####.", "#...#", "#...#", "####."),
    "C": (".###.", "#...#", "#....", "#....", "#....", "#...#", ".###."),
    "E": ("#####", "#....", "#....", "####.", "#....", "#....", "#####"),
    "F": ("#####", "#....", "#....", "####.", "#....", "#....", "#...."),
    "N": ("#...#", "##..#", "#.#.#", "#.#.#", "#..##", "#...#", "#...#"),
    "Q": (".###.", "#...#", "#...#", "#...#", "#.#.#", "#..#.", ".##.#"),
    "R": ("####.", "#...#", "#...#", "####.", "#.#..", "#..#.", "#...#"),
    "T": ("#####", "..#..", "..#..", "..#..", "..#..", "..#..", "..#.."),
    "U": ("#...#", "#...#", "#...#", "#...#", "#...#", "#...#", ".###."),
    "X": ("#...#", "#...#", ".#.#.", "..#..", ".#.#.", "#...#", "#...#"),
    "Y": ("#...#", "#...#", ".#.#.", "..#..", "..#..", "..#..", "..#.."),
    "1": ("..#..", ".##..", "..#..", "..#..", "..#..", "..#..", ".###."),
    "3": ("####.", "....#", "....#", ".###.", "....#", "....#", "####."),
    "4": ("...#.", "..##.", ".#.#.", "#..#.", "#####", "...#.", "...#."),
    "6": (".###.", "#....", "#....", "####.", "#...#", "#...#", ".###."),
    "%": ("##..#", "##.#.", "...#.", "..#..", ".#...", ".#.##", "#..##"),
    "z": ("...#.", "..##.", ".##..", "#####", "..##.", ".##..", ".#..."),      # a bolt
    "h": (".#.#.", "#####", "#####", "#####", ".###.", "..#..", "....."),      # a heart
    ">": ("#....", ".#...", "..#..", "...#.", "..#..", ".#...", "#...."),
    " ": ("..", "..", "..", "..", "..", "..", ".."),
}


def banner(txt):
    """Seven rows of dots for a line of glyphs, a column between them."""
    return [".".join(GLYPH[ch][r] for ch in txt) for r in range(7)]


def dots(g, rows, u0, v0, pitch, proj, lift, size, ch="#"):
    """Lit dots of a dot-matrix display lying on the skin, its middle at (u0, v0)."""
    sg = -1.0 if proj == 'X' else 1.0
    W, H = len(rows[0]), len(rows)
    for r, row in enumerate(rows):
        for c, x in enumerate(row):
            if x != ch:
                continue
            loc, n = skin(u0 + sg * (c - (W - 1) / 2) * pitch, v0 + ((H - 1) / 2 - r) * pitch,
                          proj)
            e1 = (AXIS_U[proj] - n * AXIS_U[proj].dot(n)).normalized()
            e2 = n.cross(e1)
            p, s = loc + n * lift, size / 2
            g.add([p - e1 * s - e2 * s, p + e1 * s - e2 * s, p + e1 * s + e2 * s,
                   p - e1 * s + e2 * s], [(0, 1, 2, 3)])


def dots_flat(g, rows, c, right, up, pitch, size):
    """Lit dots on a plane: the display's middle at c, reading along right."""
    c, right, up = V3(c), V3(right), V3(up)
    W, H, s = len(rows[0]), len(rows), size / 2
    for r, row in enumerate(rows):
        for k, x in enumerate(row):
            if x == "#":
                p = c + right * ((k - (W - 1) / 2) * pitch) + up * (((H - 1) / 2 - r) * pitch)
                g.add([p - right * s - up * s, p + right * s - up * s, p + right * s + up * s,
                       p - right * s + up * s], [(0, 1, 2, 3)])


class Win:
    """A window: a hole of a rounded outline cut through the skin along a projection, then
    flat glass and a fat seal laid behind and round it on the skin as built."""

    def __init__(self, corners, r, proj):
        o, nr = rpoly(corners, r, normals=True)
        self.o, self.nr, self.proj = [], [], proj
        for k in range(len(o)):             # points along the straights too: the seal
            a, b = o[k], o[(k + 1) % len(o)]            # follows a skin that is not flat
            n = max(1, int(hypot(b[0] - a[0], b[1] - a[1]) / 0.04))
            for i in range(n):
                self.o.append((a[0] + (b[0] - a[0]) * i / n, a[1] + (b[1] - a[1]) * i / n))
                self.nr.append(nr[k] if i == 0 else nr[(k + 1) % len(o)])

    def cut(self, g):
        if self.proj == 'y':
            for sg in (1, -1):
                g.prism([(u, sg * 0.55, v) for u, v in self.o], (0, sg * 0.6, 0))
        elif self.proj == 'x':
            g.prism([(1.45, u, v) for u, v in self.o], (1.2, 0, 0))
        else:
            g.prism([(-1.60, u, v) for u, v in self.o], (-1.0, 0, 0))

    def fit(self):
        def ring(d):
            return [skin(u + a * d, v + b * d, self.proj)
                    for (u, v), (a, b) in zip(self.o, self.nr)]
        self.P = [p for p, _ in ring(0.010)]
        self.N = [n for _, n in ring(0.010)]
        self.D = []                         # inward along the skin, square to the outline
        for p, n, (q, _) in zip(self.P, self.N, ring(0.024)):
            d = p - q
            self.D.append((d - n * d.dot(n)).normalized())
        self.c = sum(self.P, V3()) / len(self.P)
        self.n = sum(self.N, V3()).normalized()
        self.eu = (AXIS_U[self.proj] - self.n * AXIS_U[self.proj].dot(self.n)).normalized()
        self.ev = self.n.cross(self.eu)
        if self.ev.z < 0:
            self.ev = -self.ev
        return self

    def at(self, u, v, off=0.0):
        """The point of the window's plane under (u, v), off out of it."""
        (axis, a, b), far, d = K._RAYS[self.proj]
        o = V3()
        o[axis], o[a], o[b] = far, u, v
        d = V3(d)
        return o + d * ((self.c - o).dot(self.n) / d.dot(self.n)) + self.n * off

    def glass(self, g):
        """One flat pane, GD behind the skin."""
        g.add([p - self.n * ((p - self.c).dot(self.n) + GD) for p in self.P],
              [tuple(range(len(self.P)))])

    def seal(self, g):
        m = len(self.P)
        sec = [(-0.007, -0.002), (-0.007, 0.0035), (0.017, 0.0035), (0.017, -GD)]
        vs = []
        for k in range(m):
            vs += [self.P[k] + self.D[k] * a + self.N[k] * b for a, b in sec]
        s = len(sec)
        g.add(vs, [(k * s + j, k * s + (j + 1) % s, ((k + 1) % m) * s + (j + 1) % s,
                    ((k + 1) % m) * s + j) for k in range(m) for j in range(s)])


def sheet(g, name, **kw):
    """Glass from a Geo of fans: thin, smooth."""
    ob = g.obj(name, "glass", **kw)
    md = ob.modifiers.new("solid", 'SOLIDIFY')
    md.thickness = 0.004
    md.offset = -1.0
    return ob


def grain(name, color, rough=0.62, scale=300.0, strength=0.5):
    """Molded plastic: a fine pebbled grain."""
    m, b = K.pbr(name, color, 0.0, rough)
    nt = m.node_tree
    tc = nt.nodes.new('ShaderNodeTexCoord')
    nz = nt.nodes.new('ShaderNodeTexNoise')
    nz.inputs["Scale"].default_value = scale
    nz.inputs["Detail"].default_value = 3.0
    bp = nt.nodes.new('ShaderNodeBump')
    bp.inputs["Strength"].default_value = strength
    bp.inputs["Distance"].default_value = 0.002
    nt.links.new(tc.outputs["Object"], nz.inputs["Vector"])
    nt.links.new(nz.outputs["Fac"], bp.inputs["Height"])
    nt.links.new(bp.outputs["Normal"], b.inputs["Normal"])



GLYPH.update({
    "P": ("####.", "#...#", "#...#", "####.", "#....", "#....", "#...."),
    "K": ("#...#", "#..#.", "#.#..", "##...", "#.#..", "#..#.", "#...#"),
    "O": (".###.", "#...#", "#...#", "#...#", "#...#", "#...#", ".###."),
    "D": ("####.", "#...#", "#...#", "#...#", "#...#", "#...#", "####."),
    "L": ("#....", "#....", "#....", "#....", "#....", "#....", "#####"),
    "I": (".###.", "..#..", "..#..", "..#..", "..#..", "..#..", ".###."),
    "V": ("#...#", "#...#", "#...#", "#...#", "#...#", ".#.#.", "..#.."),
    "G": (".###.", "#...#", "#....", "#.###", "#...#", "#...#", ".###."),
    "S": (".####", "#....", "#....", ".###.", "....#", "....#", "####."),
    "2": (".###.", "#...#", "....#", "...#.", "..#..", ".#...", "#####"),
    "5": ("#####", "#....", "####.", "....#", "....#", "#...#", ".###."),
    "7": ("#####", "....#", "...#.", "..#..", "..#..", "..#..", "..#.."),
    "8": (".###.", "#...#", "#...#", ".###.", "#...#", "#...#", ".###."),
    "p": ("#####", "#.#.#", "#####", "#...#", "#...#", "#####", "....."),      # a parcel
})


class PWin(Win):
    """The Porter's holes: side windows on both flanks or one, the windshield, the tail."""

    def cut(self, g, sides=(1, -1)):
        if self.proj == 'y':
            for sg in sides:
                g.prism([(u, sg * 0.55, v) for u, v in self.o], (0, sg * 0.6, 0))
        elif self.proj == 'x':
            g.prism([(1.92, u, v) for u, v in self.o], (1.0, 0, 0))
        else:
            g.prism([(-2.30, u, v) for u, v in self.o], (-0.6, 0, 0))


# ---------------------------------------------------------------------------------------
# helpers of this car: the sliding door, parcels
# ---------------------------------------------------------------------------------------
def door_obj(g, name, mat, glass=False, **kw):
    """A part of the cab doors, drawn on the left: the left one will slide with its door,
    the right one is its mirror image."""
    make = sheet if glass else (lambda gg, nm, **k: gg.obj(nm, mat, **k))
    DOOR.append(make(g, name + ".l", **kw))
    make(g, name + ".r", flip_y=True, **kw)


def split_left(ob):
    """The left half of a mirrored panel as an object of its own."""
    new = ob.copy()
    new.data = ob.data.copy()
    new.name = ob.name + ".l"
    K.CAR.objects.link(new)
    for o, keep in ((ob, -1.0), (new, 1.0)):
        bm = bmesh.new()
        bm.from_mesh(o.data)
        bmesh.ops.delete(bm, geom=[f for f in bm.faces if f.calc_center_median().y * keep < 0],
                         context='FACES')
        bm.to_mesh(o.data)
        bm.free()
    return new


BOX = {}                            # parcels by material, tape, labels


def parcel(x, y, z0, sx, sy, sz, yaw=0.0, mat="kraft", label=(-1, 0)):
    """A parcel standing on z0: a carton, a band of tape over it, an address label on the
    face that looks along label."""
    R = Matrix.Rotation(rad(yaw), 3, 'Z')
    c = V3((x, y, z0 + sz / 2))
    BOX.setdefault(mat, Geo()).box(c, (sx, sy, sz), rot=R)
    t = BOX.setdefault("tape", Geo())
    t.box(c + V3((0, 0, sz / 2)), (sx + 0.003, 0.05, 0.003), rot=R)
    for s in (1, -1):
        t.box(c + R @ V3((s * sx / 2, 0, sz / 2 - 0.03)), (0.003, 0.05, 0.06), rot=R)
    lx, ly = label
    d = R @ V3((lx * (sx / 2 + 0.001), ly * (sy / 2 + 0.001), 0.0))
    o = R @ V3((ly * 0.22 * sx, lx * 0.24 * sy, -0.05 * sz))
    size = (0.002, 0.10, 0.065) if lx else (0.10, 0.002, 0.065)
    BOX.setdefault("label", Geo()).box(c + d + o, size, rot=R)
    BOX.setdefault("ink", Geo()).box(c + d * 1.002 + o + V3((0, 0, -0.012)),
                                     (0.003, 0.07, 0.012) if lx else (0.07, 0.003, 0.012), rot=R)


def parcels_out(name):
    for mat, g in BOX.items():
        g.obj(name + "." + mat, mat, bevel=0.004 if mat in ("kraft", "carton") else 0.0)
    BOX.clear()


# ---------------------------------------------------------------------------------------
# body: stations and character lines
# ---------------------------------------------------------------------------------------
LINES = "CQRHGUVMFB"
#        C top centerline, Q roof inner, R roof edge, H glass header / roof corner,
#        G belt, U foot of the paint, V top of the cladding (a step out), M rocker,
#        F floor edge, B floor centerline
ORDER = ["NC", "N0", "N1", "W0", "WS", "RF", "RG", "D1", "D2", "F2", "F3", "HA", "RA", "T2",
         "T1", "T0", "TC"]
#        NC and TC are rings inside the nose and tail faces; W0 is the cowl; D2 is the
#        door's rear edge and the brow's foot, F2 the brow's top: the hold stands taller
LAST = len(ORDER) - 2               # the tail face's row of quads
PT = {}


def cabin(x, zc=CROOF, head=HEAD):
    return [(x, 0, zc), (x, .52, zc - .002), (x, .755, zc - .025), (x, side_y(head), head),
            (x, .93, BELT), (x, .93, STEP + .015), (x, .943, STEP), (x, .935, .29),
            (x, .80, .225), (x, 0, .225)]


def hold(x, zc=ROOF):
    return cabin(x, zc, zc - .125)


NOSE = [(0, 1.0), (.46, 1.0), (.665, .985), (.755, .94), (.795, .80), (.802, STEP + .015),
        (.812, STEP), (.775, .37), (.63, .32), (0, .32)]
TAIL = [(0, 2.285), (.50, 2.285), (.70, 2.268), (.785, 2.20), (.815, BELT), (.82, STEP + .015),
        (.83, STEP), (.79, .375), (.645, .32), (0, .32)]


def inner(pts, zc, s=0.8, zlow=STEP):
    """A face's outline drawn in toward its middle (below the cladding's step toward zlow,
    so the step stays level across the face)."""
    return [(y * s, (zc if j < 5 else zlow) + (z - (zc if j < 5 else zlow)) * s)
            for j, (y, z) in enumerate(pts)]


def stations():
    def ring(x, pts):
        return [(x(z) if callable(x) else x, y, z) for (y, z) in pts]
    xb = D_RC - FD
    T = {
        "NC": ring(2.65, inner(NOSE, .72)),
        "N0": ring(2.65, NOSE),
        "N1": [(2.605, 0, 1.052), (2.605, .49, 1.052), (2.59, .725, 1.038), (2.565, .825, .985),
               (2.54, .883, .83), (2.54, .888, STEP + .015), (2.545, .901, STEP),
               (2.555, .865, .33), (2.58, .69, .26), (2.60, 0, .26)],
        "W0": [(2.53, 0, 1.095), (2.53, .52, 1.095), (2.51, .75, 1.088), (2.46, .865, 1.07),
               (2.36, .93, BELT), (2.36, .93, STEP + .015), (2.36, .943, STEP),
               (2.36, .935, .29), (2.36, .80, .225), (2.36, 0, .225)],
        "WS": [(2.145, 0, 1.96), (2.145, .52, 1.958), (2.125, .74, 1.938), (2.085, .868, 1.865)]
        + [None] * 6,
        "RF": [(2.085, 0, 2.036), (2.085, .52, 2.034), (2.065, .75, 2.012), (2.02, .88, 1.93)]
        + [None] * 6,
        "RG": cabin(RG_X)[:4] + [None] * 6,
        "D1": cabin(D_FC), "D2": cabin(D_RC),
        "F2": [(xb, 0, 2.295), (xb, .52, 2.293), (xb, .755, 2.27), (xb, .872, 2.18)]
        + cabin(xb)[4:],
        "F3": hold(D_RC - 0.24), "HA": hold(-0.80), "RA": hold(RA_X, ROOF - .003),
        "T2": [(-2.36, 0, 2.338), (-2.36, .50, 2.336), (-2.365, .74, 2.312),
               (-2.38, .867, 2.222), (-2.48, .927, BELT), (-2.48, .93, STEP + .015),
               (-2.48, .943, STEP), (-2.48, .933, .30), (-2.48, .79, .235), (-2.48, 0, .235)],
        "T1": [(-2.49, 0, 2.322), (-2.49, .49, 2.320), (-2.495, .73, 2.297),
               (-2.51, .852, 2.212), (-2.56, .898, BELT), (-2.585, .902, STEP + .015),
               (-2.59, .915, STEP), (-2.60, .875, .33), (-2.615, .70, .265), (-2.62, 0, .265)],
        "T0": ring(tail_x, TAIL),
        "TC": ring(tail_x, inner(TAIL, 1.30)),
    }
    S = K.fill([T[k] for k in ORDER])
    PT.update(K.table(ORDER, LINES, S))
    return S


def panel_of(i, j):
    if i in (0, LAST):                  # the faces: body color, the bumper pads lie on them
        return "nose" if i == 0 else "gate"
    if j == 8:
        return "floor"
    if j >= 5:                          # the door takes its cladding with it
        return "sclad" if i == 7 and j <= 6 else "clad"
    if i == 1:
        return "nose"
    if i == 2:
        return "nose" if j <= 1 else "fender"
    if j <= 2:
        return "screen" if i <= 4 else "roof"
    return "fender" if i <= 6 else "slider" if i == 7 else "quarter"


PMAT = dict(nose="paint", fender="paint", screen="paint", roof="paint2", slider="paint",
            quarter="paint", gate="paint", clad="plastic", sclad="plastic",
            floor="underbody", well="well", wincut="void")


def line_crease(i, j):
    """Crease of the edge along line j from station i to i + 1."""
    if j in (5, 6):
        return 1.0                      # the cladding's step, also across the two faces:
    if i in (0, LAST):                  # uncreased, the belt far above pulls it up
        return 0.0
    if j == 8:                          # the floor edge
        return 1.0 if 2 <= i <= LAST - 2 else 0.4
    if j == 7:
        return 0.5 if 2 <= i <= LAST - 2 else 0.2
    if j == 4:
        return 0.35 if i >= 3 else 0.2
    if j == 3:
        return 0.5 if i >= 3 else 0.3
    if j == 2:
        return 0.25 if i >= 3 else 0.0
    return 0.0


def station_crease(i, j):
    """Crease of the edge on station i between lines j and j + 1."""
    if i == 3:
        return 0.6 if j <= 2 else 0.0   # the cowl
    if i == 5:
        return 0.3 if j <= 1 else 0.0   # the windshield's header
    if i == 8:
        return 0.85 if j <= 2 else 0.0  # the brow's foot
    if i == 9:
        return 0.45 if j <= 2 else 0.0  # and its top
    return 0.0


def arch_pts(cx, grow=0.0, n=30):
    """The squircle arch about an axle, front to rear over the top, as (x, z)."""
    a, b = ARCH_A + grow, ARCH_B + grow
    out = []
    for k in range(n + 1):
        t = pi * k / n
        c, s = cos(t), sin(t)
        e = 2.0 / ARCH_N
        out.append((cx + a * (1 if c >= 0 else -1) * abs(c) ** e, ARCH_ZC + b * abs(s) ** e))
    return out


W_FQ = PWin([(2.20, 1.06), (1.935, 1.845), (1.30, 1.845), (1.30, 1.06)], [.06, .08, .08, .08],
            'y')
W_DOOR = PWin(rect(0.75, 1.4525, .31, .3925), .08, 'y')
W_FRONT = PWin([(-.70, 1.17), (.70, 1.17), (.665, 1.87), (-.665, 1.87)], .09, 'x')
W_ROLL = PWin(rect(0, 1.415, .64, .625), .05, 'X')          # the roller door's opening
W_LOCK = PWin(rect(LOCK_X[LOCK_OPEN[1]], LOCK_Z[LOCK_OPEN[0]], LW - .012, LH - .012), .028, 'y')
WINS = [W_FQ, W_DOOR, W_FRONT, W_ROLL, W_LOCK]


def build_hull():
    wells, wins = Geo(), Geo()
    for cx in (FA_X, RA_X):
        for sg in (1, -1):
            pts = arch_pts(cx)
            poly = [(pts[0][0], sg * 0.60, -0.3)] + [(x, sg * 0.60, z) for x, z in pts]
            poly.append((pts[-1][0], sg * 0.60, -0.3))
            wells.prism(poly, (0, sg * 0.5, 0))
    for w in WINS:
        if w is W_LOCK:
            w.cut(wins, sides=(1,))
        else:
            w.cut(wins)
    body = K.build_body(stations(), panel_of, PMAT, line_crease, station_crease,
                        front=dict(kind="flat", panel="nose", crease=0.0),
                        rear=dict(kind="flat", panel="gate", crease=0.0),
                        cutters=[(wells, "well"), (wins, "wincut")], subdiv=3)
    ob = body.parts.pop("wincut")           # the holes stay, their walls go
    me = ob.data
    bpy.data.objects.remove(ob)
    bpy.data.meshes.remove(me)
    return body


# ---------------------------------------------------------------------------------------
# glass, seals, wipers, the roller door, the open locker
# ---------------------------------------------------------------------------------------
def build_glass():
    for w in WINS:
        w.fit()
    g, gs = Geo(), Geo()
    W_FQ.glass(g)
    W_FQ.seal(gs)
    sheet(g, "glass.side", mirror=True)
    gs.obj("seal.side", "rubber", bevel=0.0012, mirror=True)
    g, gs = Geo(), Geo()
    W_DOOR.glass(g)
    W_DOOR.seal(gs)
    door_obj(g, "glass.door", "glass", glass=True)
    door_obj(gs, "seal.door", "rubber", bevel=0.0012)
    g, gs = Geo(), Geo()
    W_FRONT.glass(g)
    for w in (W_FRONT, W_ROLL, W_LOCK):
        w.seal(gs)
    sheet(g, "glass.front")
    gs.obj("seal.ends", "rubber", bevel=0.0012)
    # two wipers on the tall windshield, parked toward the middle
    g = Geo()
    w = W_FRONT
    for sg in (1, -1):
        p0 = w.at(sg * 0.33, 1.135, 0.004)
        pa, pb = w.at(sg * 0.30, 1.215, -GD + 0.009), w.at(sg * -0.30, 1.245, -GD + 0.009)
        g.tube(pa, pb, 0.006, 8)
        g.tube(pa.lerp(pb, 0.1) + w.n * 0.004, pa.lerp(pb, 0.9) + w.n * 0.004, 0.004, 6)
        g.tube(p0 + w.n * 0.014, pa.lerp(pb, 0.45) + w.n * 0.012, 0.005, 8)
        stud(g, p0, w.n, [(-0.004, 0.001), (-0.004, 0.017), (0.016, 0.014), (0.02, 0.001)], 14)
    g.obj("wipers", "cladding", bevel=0.0008)


def build_roller():
    """The roller door: slats down to OPEN_Z, a bottom bar with a pull, guides."""
    w = W_ROLL
    g, gb, gr, gy = Geo(), Geo(), Geo(), Geo()
    h, top = 0.072, 2.045

    def slab(g_, u0, u1, z0, z1, a, b):
        q = [w.at(u0, z0, a), w.at(u1, z0, a), w.at(u1, z1, a), w.at(u0, z1, a)]
        g_.hexa(q + [p + w.n * (b - a) for p in q])
    n = int((top - OPEN_Z) / h + 0.999)
    for k in range(n):
        z0 = OPEN_Z + k * h
        slab(g, -0.632, 0.632, z0 + 0.004, z0 + h - 0.004, -0.050, -0.036)
        slab(gr, -0.632, 0.632, z0 - 0.004, z0 + 0.004, -0.050, -0.041)
    slab(gb, -0.632, 0.632, OPEN_Z - 0.075, OPEN_Z, -0.056, -0.028)
    slab(gr, -0.632, 0.632, OPEN_Z - 0.095, OPEN_Z - 0.075, -0.052, -0.032)
    slab(gy, -0.11, 0.11, OPEN_Z - 0.052, OPEN_Z - 0.03, -0.028, -0.014)     # the pull
    for sg in (1, -1):
        slab(gb, sg * 0.632 - 0.012, sg * 0.632 + 0.012, 0.795, top, -0.06, -0.024)
    g.obj("roller.slats", "paint2", bevel=0.003)
    gb.obj("roller.frame", "steel", bevel=0.003)
    gr.obj("roller.seals", "rubber")
    gy.obj("roller.pull", "caliper", bevel=0.004)
    g = Geo()
    for z in (OPEN_Z + 0.25, OPEN_Z + 0.39):
        K.text_flat(g, "pakko" if z > OPEN_Z + 0.3 else "KEEP CLEAR OF DOOR",
                    0.16 if z > OPEN_Z + 0.3 else 0.022, w.at(0, z, -0.0355), -w.eu, w.ev,
                    spacing=1.0 if z > OPEN_Z + 0.3 else 1.25)
    g.obj("roller.lettering", "decal")


def build_locker():
    """The open locker: its cell, a light, a parcel, its hatch swung out."""
    cx, cz = LOCK_X[LOCK_OPEN[1]], LOCK_Z[LOCK_OPEN[0]]
    a, b = LW - 0.012, LH - 0.012
    y0, y1 = side_y(cz) - 0.012, 0.54
    vs = [(cx + sx * a, y, cz + sz * b) for y in (y0, y1)
          for sx, sz in ((-1, -1), (1, -1), (1, 1), (-1, 1))]
    g = Geo()
    g.add(vs, [(0, 1, 5, 4), (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7), (4, 5, 6, 7)])
    g.obj("locker.cell", "cell")
    g = Geo()
    g.box((cx, (y0 + y1) / 2, cz + b - 0.006), (2 * a - 0.04, 0.24, 0.006))
    g.obj("locker.cell.light", "dome")
    parcel(cx - 0.01, 0.74, cz - b + 0.002, 0.20, 0.25, 0.13, 8, "kraft", (0, 1))
    parcels_out("locker.parcel")
    g, gi = Geo(), Geo()                    # the hatch, hinged on its rear edge
    th = rad(100)
    R = Matrix.Rotation(th, 3, 'Z')
    hinge = V3((cx - LW, side_y(cz) + 0.012, cz))
    d = V3((cos(th), sin(th), 0))
    g.box(hinge + d * LW, (2 * LW, 0.012, 2 * LH), rot=R)
    gi.box(hinge + d * LW + R @ V3((0, 0.008, 0)), (2 * LW - 0.05, 0.006, 2 * LH - 0.05), rot=R)
    for z in (cz - 0.08, cz + 0.08):
        gi.tube(hinge + V3((0, -0.01, z - cz - 0.02)), hinge + V3((0, -0.01, z - cz + 0.02)),
                0.008, 8)
    g.obj("locker.hatch.open", "paint2", bevel=0.004)
    gi.obj("locker.hatch.liner", "steel", bevel=0.002)


# ---------------------------------------------------------------------------------------
# the visors: light bar, lamp rings, display; bumpers, plates, badges; the brow
# ---------------------------------------------------------------------------------------
def build_ends():
    for proj, tag, cv, zb, lit, hw in (('x', "front", 0.80, 0.455, "led_front", 0.775),
                                       ('X', "rear", 0.665, 0.445, "led_rear", 0.795)):
        sg = -1.0 if proj == 'X' else 1.0       # the car's left as this view's u
        vh = 0.09 if tag == "front" else 0.08
        ly = hw - 0.105                         # the lamp rings
        g = Geo()
        pad(g, 0, cv, hw, vh, 0.055, proj, lift=0.004)
        g.obj("visor." + tag, "visor", bevel=0.002)
        gl, gk, gd = Geo(), Geo(), Geo()
        for y in (ly, -ly):
            pad(gl, y, cv, 0.082, vh - 0.028, 0.032, proj, lift=0.0075)
            pad(gk, y, cv, 0.063, vh - 0.047, 0.02, proj, lift=0.0085)
            pad(gl, y, cv, 0.022, 0.015, 0.009, proj, lift=0.0095)
        bar_on(gl, [(-ly + 0.09, cv + vh - 0.053), (ly - 0.09, cv + vh - 0.053)], proj, 0.017,
               0.0075)
        gl.obj("led." + tag, lit, bevel=0.001)
        # the display, on the car's left under the bar: charge in front, the job behind
        rows = banner("z 78%" if tag == "front" else "DELIVERING")
        wd = len(rows[0]) * 0.0072 / 2 + 0.022
        du = sg * (ly - 0.105 - wd)
        pad(gd, du, cv - 0.03, wd, 0.036, 0.012, proj, lift=0.006)
        gd.obj("display." + tag, "panel", bevel=0.001)
        gk.obj("lamp.cores." + tag, "gloss_black", bevel=0.001)
        gp = Geo()
        dots(gp, rows, du, cv - 0.03, 0.0072, proj, 0.0068, 0.0052)
        gp.obj("pixels." + tag, "pixel" if tag == "front" else "pixel_r")
        # bumper: a grained pad, rubber guards on its corners, sensors
        bw = hw + 0.005
        g = Geo()
        pad(g, 0, zb, bw, 0.115, 0.058, proj, lift=0.012, nv=10, step=0.02)
        g.obj("bumper." + tag, "plastic", bevel=0.004)
        g = Geo()
        for y in (bw - 0.065, -bw + 0.065):
            pad(g, y, zb, 0.03, 0.08, 0.02, proj, lift=0.019)
        g.obj("bumper.guards." + tag, "rubber", bevel=0.004)
        g = Geo()
        for y in (0.24, 0.56, -0.24, -0.56):
            loc, n = skin(y, zb + 0.068, proj)
            stud(g, loc + n * 0.012, n, [(-0.002, 0.001), (-0.002, 0.012), (0.0015, 0.012),
                                         (0.0015, 0.001)], 12)
        g.obj("sensors." + tag, "gloss_black")

    # ---- front: intake slot with slats, radar plate, plate, fog lamps, tow eye
    g, gs = Geo(), Geo()
    pad(g, 0, 0.385, 0.42, 0.036, 0.03, 'x', lift=0.0124)
    g.obj("intake", "void")
    for z in (0.365, 0.385, 0.405):
        bar_on(gs, [(-0.395, z), (0.395, z)], 'x', 0.009, 0.0035, lift=0.0124)
    gs.obj("intake.slats", "plastic", bevel=0.001)
    g = Geo()
    for y in (0.56, -0.56):
        pad(g, y, 0.39, 0.055, 0.028, 0.015, 'x', lift=0.0135)
    g.obj("fog", "lamp", bevel=0.001)
    plate('x', 0.0, 0.50)
    g = Geo()
    loc, n = skin(-0.40, 0.50, 'x')
    stud(g, loc + n * 0.012, n, [(-0.001, 0.001), (-0.001, 0.026), (0.003, 0.024), (0.003, 0.001)],
         20)
    g.obj("tow.cover", "plastic", bevel=0.001)
    g = Geo()                                   # the eye itself, low under the lip
    g.lathe([(-0.006, 0.030), (0.0, 0.036), (0.006, 0.030), (0.0, 0.024)], 20,
            xf=Matrix.Translation((2.65, -0.40, 0.285)) @ Matrix.Rotation(pi / 2, 4, 'Z'))
    g.box((2.605, -0.40, 0.285), (0.07, 0.014, 0.014))
    g.obj("tow.eye", "caliper", sharp=40)
    g = Geo()                                   # the forward radar, a gloss plate
    pad(g, 0.40, 0.50, 0.07, 0.03, 0.012, 'x', lift=0.0135)
    g.obj("radar", "visor", bevel=0.001)
    g = Geo()
    text_proj(g, "tanager", 0.036, 0.0, 0.94, 'x', spacing=1.08)
    g.obj("lettering.front", "decal")

    # ---- the brow over the cab: a third visor, the route in dots
    g, gp, gl = Geo(), Geo(), Geo()
    pad(g, 0, 2.185, 0.63, 0.07, 0.05, 'x', lift=0.004)
    g.obj("visor.brow", "visor", bevel=0.002)
    dots(gp, banner("PAKKO  ROUTE " + ROUTE), 0, 2.185, 0.0112, 'x', 0.0052, 0.0082)
    gp.obj("pixels.brow", "pixel_r")
    for y in (0.70, -0.70):                     # clearance lamps beside it
        pad(gl, y, 2.185, 0.022, 0.014, 0.01, 'x', lift=0.004)
    gl.obj("led.clearance", "led_accent", bevel=0.001)

    # ---- rear: reflectors, reverse lamp, plate, the header's stop lamp and lettering
    g = Geo()
    for y in (0.58, -0.58):
        pad(g, y, 0.475, 0.095, 0.018, 0.012, 'X', lift=0.0135)
    g.obj("reflectors", "reflector", bevel=0.001)
    g = Geo()
    pad(g, 0.0, 0.372, 0.065, 0.016, 0.01, 'X', lift=0.0135)
    g.obj("reverse", "lamp", bevel=0.001)
    plate('X', 0.0, 0.475)
    g = Geo()
    bar_on(g, [(-0.22, 2.185), (0.22, 2.185)], 'X', 0.012, 0.004)
    for y in (0.72, -0.72):
        pad(g, y, 2.125, 0.014, 0.03, 0.01, 'X', lift=0.003)
    g.obj("led.stop", "led_rear")
    g = Geo()
    text_proj(g, "PORTER", 0.05, 0.42, 2.115, 'X', spacing=1.1)
    text_proj(g, "tanager", 0.034, -0.42, 2.118, 'X', spacing=1.05)
    text_proj(g, "LOAD 900 KG   SILL 0.77", 0.012, 0.0, 0.762, 'X', spacing=1.2)
    g.obj("lettering.rear", "decal")
    badge('X', 0.0, 2.118, 0.034)
    badge('z', 2.572, 0.0, 0.036)
    g, gk = Geo(), Geo()                        # the reversing camera over the door
    loc, n = skin(0.0, 2.235, 'X')
    g.box(loc + n * 0.012, (0.04, 0.09, 0.03))
    stud(gk, loc + n * 0.03, n, [(0.0, 0.001), (0.0, 0.011), (0.004, 0.009), (0.004, 0.001)], 14)
    g.obj("camera.rear", "visor", bevel=0.006)
    gk.obj("camera.rear.lens", "rim_bright")


def plate(proj, u, v):
    g = Geo()
    lift = 0.0125 if v < 0.57 else 0.0
    pad(g, u, v, 0.15, 0.037, 0.008, proj, lift=lift + 0.004)
    g.obj("plate." + proj, "plate", bevel=0.001)
    g = Geo()
    text_proj(g, "VB 58-112", 0.042, u, v, proj, lift=lift + 0.0052, spacing=1.1)
    g.obj("plate.glyphs." + proj, "mark")


def badge(proj, u, v, r):
    """The round badge: a bright ring, a disc of the second color, a T."""
    g, gd, gt = Geo(), Geo(), Geo()
    pad(g, u, v, r, r, r, proj, lift=0.004, nc=8, nv=6)
    g.obj("badge.ring." + proj, "rim_bright", bevel=0.001)
    pad(gd, u, v, r * 0.80, r * 0.80, r * 0.80, proj, lift=0.0052, nc=8, nv=6)
    gd.obj("badge.disc." + proj, "paint2", bevel=0.0008)
    if proj == 'z':
        K.text_on_body(gt, "T", r * 1.05, u, v, 1, lift=0.0062, proj='z', turn=-90)
    else:
        text_proj(gt, "T", r * 1.05, u, v, proj, lift=0.0062)
    gt.obj("badge.t." + proj, "mark")


# ---------------------------------------------------------------------------------------
# the flanks: arches, strips, door gear, the locker bank, the courier's lettering, mirrors
# ---------------------------------------------------------------------------------------
def build_sides():
    # ---- squircle arch trims in the cladding's plastic
    g = Geo()
    for cx in (FA_X, RA_X):
        n = 31
        ring = [(x, y, z) for y in (0.902, 0.957)
                for grow in (-0.006, 0.05) for (x, z) in arch_pts(cx, grow)]
        fs = []
        for k in range(n - 1):
            i0, i1, o0, o1 = k, k + 1, n + k, n + k + 1
            fs += [(i0, i1, o1, o0), (2 * n + i0, 2 * n + i1, 2 * n + o1, 2 * n + o0),
                   (i0, i1, 2 * n + i1, 2 * n + i0), (o0, o1, 2 * n + o1, 2 * n + o0)]
        fs += [(0, n, 3 * n, 2 * n), (n - 1, 2 * n - 1, 4 * n - 1, 3 * n - 1)]
        g.add(ring, fs)
    g.obj("arch.trims", "plastic", bevel=0.005, mirror=True)
    g = Geo()
    for cx in (FA_X, RA_X):
        g.box((cx - ARCH_A - 0.012, 0.83, 0.235), (0.012, 0.19, 0.23))
    g.obj("mudflaps", "rubber", bevel=0.003, mirror=True)

    # ---- bump strip with two rubber lines: fixed pieces, and the door's own
    zs = 0.415
    g, gl, gd, gdl = Geo(), Geo(), Geo(), Geo()
    for a, b in ((D_R - 0.03, RA_X + ARCH_A + 0.08), (RA_X - ARCH_A - 0.08, -2.40)):
        bar_on(g, [(a, zs), (b, zs)], 'y', 0.06, 0.011)
        for z in (zs - 0.013, zs + 0.013):
            bar_on(gl, [(a - 0.02, z), (b + 0.02, z)], 'y', 0.004, 0.0125)
    bar_on(gd, [(D_F - 0.03, zs), (D_R + 0.03, zs)], 'y', 0.06, 0.011)
    for z in (zs - 0.013, zs + 0.013):
        bar_on(gdl, [(D_F - 0.05, z), (D_R + 0.05, z)], 'y', 0.004, 0.0125)
    g.obj("bump.strip", "plastic", bevel=0.004, mirror=True)
    gl.obj("bump.lines", "rubber", mirror=True)
    door_obj(gd, "bump.strip.door", "plastic", bevel=0.004)
    door_obj(gdl, "bump.lines.door", "rubber")

    # ---- the door's track along the hold under the belt, and its roller arm on the door
    g, gb = Geo(), Geo()
    pad(g, -0.14, 0.966, 0.44, 0.013, 0.012, 'y', lift=0.0008, sink=0.001)
    g.obj("track", "void", mirror=True)
    for z in (0.983, 0.949):
        bar_on(gb, [(0.295, z), (-0.575, z)], 'y', 0.006, 0.004)
    gb.obj("track.lips", "rim_bright", mirror=True)
    g = Geo()
    loc, n = skin(D_R + 0.035, 0.966, 'y')
    g.box(loc + V3((-0.045, -0.004, 0)), (0.13, 0.02, 0.022))
    door_obj(g, "track.arm", "steel", bevel=0.003)

    # ---- door handle (an upright pull in a pocket), the roundel, lettering
    g, gp, gr = Geo(), Geo(), Geo()
    pad(g, 1.085, 0.80, 0.024, 0.085, 0.022, 'y', lift=0.0008, sink=0.001)
    pad(gp, 1.093, 0.80, 0.0095, 0.075, 0.009, 'y', lift=0.010)
    pad(gr, 0.88, 0.775, 0.108, 0.108, 0.108, 'y', lift=0.0025, nc=12, nv=8)
    door_obj(g, "handle.pocket", "void")
    door_obj(gp, "handle.pull", "paint", bevel=0.002)
    door_obj(gr, "roundel", "paint2", bevel=0.001)
    for side, tag in ((1, ".l"), (-1, ".r")):
        g, gw = Geo(), Geo()
        K.text_on_body(g, NUM, 0.125, 0.88, 0.775, side, lift=0.0036)
        K.text_on_body(gw, "PORTER", 0.062, 0.565, 0.80, side, spacing=1.1)
        K.text_on_body(gw, "TANAGER PARCEL VAN", 0.0165, 0.565, 0.735, side, spacing=1.2)
        K.text_on_body(gw, "UNIT 58   ROUTE 12", 0.012, 0.565, 0.705, side, spacing=1.2)
        K.text_on_body(gw, "SLIDING DOOR  STAND CLEAR", 0.010, 0.75, 0.615, side, spacing=1.25)
        a, b = g.obj("roundel.number" + tag, "mark"), gw.obj("lettering.door" + tag, "decal")
        if side > 0:
            DOOR.extend((a, b))
        # fixed small print: tire pressures, jack points, the track's warning
        gw = Geo()
        K.text_on_body(gw, "3.4 BAR", 0.014, RA_X, 0.835, side, spacing=1.15)
        K.text_on_body(gw, "3.4 BAR", 0.014, FA_X, 0.835, side, spacing=1.15)
        K.text_on_body(gw, "KEEP TRACK CLEAR", 0.010, -0.16, 0.932, side, spacing=1.25)
        proj = 'y' if side > 0 else 'Y'
        for x in (0.18, -1.16):
            tri = [skin(x + dx, 0.345 + dz, proj) for dx, dz in ((-0.016, 0.014), (0.016, 0.014),
                                                                 (0.0, -0.014))]
            gw.add([p + n * 0.0015 for p, n in tri], [(0, 1, 2)])
        gw.obj("lettering.side" + tag, "decal")

    # ---- the kerb flank: a bank of parcel lockers and its kiosk
    g, gs, gg, ga, gv, gt = Geo(), Geo(), Geo(), Geo(), Geo(), Geo()
    k = 0
    for r, cz in enumerate(LOCK_Z):
        for c, cx in enumerate(LOCK_X):
            k += 1
            if (r, c) == LOCK_OPEN:
                continue
            pad(g, cx, cz, LW, LH, 0.034, 'y', lift=0.007)
            lit = LOCK_LIT[r][c]
            pad({"g": gg, "a": ga, ".": gs}[lit], cx, cz + LH - 0.032, LW - 0.045, 0.011, 0.008,
                'y', lift=0.0082)
            pad(gv, cx - LW + 0.034, cz - 0.02, 0.008, 0.045, 0.007, 'y', lift=0.0076, sink=0.0)
            K.text_on_body(gt, "%02d" % k, 0.085, cx + 0.03, cz - 0.02, 1, lift=0.0084)
    g.obj("locker.hatches", "paint2", bevel=0.003)
    gs.obj("locker.status.off", "panel")
    gg.obj("locker.status.ready", "pixel")
    ga.obj("locker.status.held", "pixel_r")
    gv.obj("locker.pulls", "void")
    gt.obj("locker.numbers", "decal")
    g, gs, gp, gk, gl = Geo(), Geo(), Geo(), Geo(), Geo()
    kx = -0.71
    pad(g, kx, 1.30, 0.11, 0.44, 0.04, 'y', lift=0.006)
    pad(gs, kx, 1.50, 0.085, 0.13, 0.014, 'y', lift=0.0072)
    dots(gp, [r[::-1] for r in banner("SCAN")], kx, 1.585, 0.0058, 'y', 0.0078, 0.0042)
    code = ["#######.#.#######", "#.....#.##.#.....#", "#.###.#..#.#.###.#", "#.###.#.#..#.###.#",
            "#.....#.##.#.....#", "#######.#.#######", "........##.......", "#.##.###..#.##.#.",
            ".#..#..##.##..##.", "#######..#.#.#..#", "#.....#.##..##.#.", "#.###.#.#.#.#..##",
            "#.....#..##.#.#.#", "#######.#..##.##."]
    dots(gp, [row[:17].ljust(17, ".") for row in code], kx, 1.47, 0.0062, 'y', 0.0078, 0.005)
    for i in range(12):                         # the keypad
        tile(gk, kx - 0.036 + 0.036 * (i % 3), 1.265 - 0.036 * (i // 3), 0.013, 0.013, 'y', 0.0085)
    pad(gk, kx, 1.045, 0.07, 0.006, 0.005, 'y', lift=0.0078, sink=0.0)       # the card slot
    pad(gl, kx, 0.925, 0.085, 0.01, 0.008, 'y', lift=0.0074)
    stud(gl, skin(kx, 1.69, 'y')[0] + V3((0, 0.006, 0)), V3((0, 1, 0)),
         [(0.0, 0.001), (0.0, 0.016), (0.003, 0.014), (0.003, 0.001)], 16)
    g.obj("kiosk", "visor", bevel=0.002)
    gs.obj("kiosk.screen", "panel", bevel=0.001)
    gp.obj("kiosk.pixels", "pixel")
    gk.obj("kiosk.keys", "plastic", bevel=0.001)
    gl.obj("kiosk.light", "pixel")

    # ---- the courier's name: above the lockers, and large on the off side
    g, gr, gt, gd = Geo(), Geo(), Geo(), Geo()
    K.text_on_body(g, "pakko", 0.30, -1.62, 1.985, 1, lift=0.0014)
    K.text_on_body(g, "24 H PARCEL LOCKERS   SCAN   OPEN   TAKE", 0.03, -1.55, 1.787, 1,
                   spacing=1.2)
    pad(gr, -0.84, 1.985, 0.215, 0.07, 0.07, 'y', lift=0.0025)
    K.text_on_body(gt, "ROUTE " + ROUTE, 0.074, -0.84, 1.985, 1, lift=0.0036, spacing=1.05)
    pad(gd, -1.085, 1.92, 0.035, 0.035, 0.035, 'y', lift=0.002, nc=8)
    g.obj("courier.l", "decal")
    gr.obj("route.pill.l", "paint2", bevel=0.001)
    gt.obj("route.text.l", "mark")
    gd.obj("courier.dot.l", "pop")
    g, gt = Geo(), Geo()
    K.text_on_body(g, "pakko", 0.70, -1.08, 1.60, -1, lift=0.0014)
    K.text_on_body(g, "PARCELS BY THE HOUR", 0.062, -1.08, 1.115, -1, spacing=1.25)
    K.text_on_body(gt, "ROUTE " + ROUTE, 0.074, -0.30, 2.06, -1, lift=0.0036, spacing=1.05)
    g.obj("courier.r", "decal")
    gt.obj("route.text.r", "mark")
    gr, gd = Geo(), Geo()                       # drawn on the left, built on the right
    pad(gr, -0.30, 2.06, 0.215, 0.07, 0.07, 'y', lift=0.0025)
    pad(gd, -0.02, 1.46, 0.075, 0.075, 0.075, 'y', lift=0.002, nc=10, nv=6)
    gr.obj("route.pill.r", "paint2", bevel=0.001, flip_y=True)
    gd.obj("courier.dot.r", "pop", flip_y=True)

    # ---- charge door on the off side behind the cab door: outline, a lit bolt, a label
    g, gp, gt = Geo(), Geo(), Geo()
    K.ribbon(g, rrect(-0.20, 0.76, 0.078, 0.054, 0.022), 'y', 0.004, closed=True)
    K.ribbon(g, [(-0.27, 0.735), (-0.27, 0.785)], 'y', 0.006)
    g.obj("charge.door", "void", flip_y=True)
    dots(gp, GLYPH["z"], -0.185, 0.763, 0.006, 'y', 0.001, 0.0045)
    gp.obj("charge.bolt", "pixel", flip_y=True)
    K.text_on_body(gt, "CHARGE 22 KW", 0.011, -0.20, 0.688, -1, spacing=1.2)
    gt.obj("charge.label", "decal")

    # ---- mirrors on two arms, a kerb camera under each, turn lamps
    g, gm, gh, gc, ga, gk = Geo(), Geo(), Geo(), Geo(), Geo(), Geo()
    g.tube((2.19, 0.905, 1.27), (2.325, 1.06, 1.28), 0.011, 8)
    g.tube((2.09, 0.89, 1.57), (2.325, 1.06, 1.56), 0.011, 8)
    g.tube((2.325, 1.06, 1.25), (2.325, 1.06, 1.59), 0.012, 8)
    gh.box((2.335, 1.115, 1.42), (0.055, 0.16, 0.36))
    gm.box((2.305, 1.115, 1.42), (0.004, 0.13, 0.32))
    gc.box((2.335, 1.115, 1.205), (0.075, 0.075, 0.05))
    gk.lathe([(0.0, 0.002), (0.0, 0.017), (0.006, 0.014), (0.006, 0.002)], 14,
             xf=Matrix.Translation((2.335, 1.115, 1.18)) @ Matrix.Rotation(-pi / 2, 4, 'X'))
    ga.box((2.3635, 1.115, 1.42), (0.004, 0.12, 0.022))
    ga.box((2.335, 1.154, 1.205), (0.04, 0.004, 0.012))
    pad(ga, 2.30, 0.925, 0.03, 0.011, 0.008, 'y', lift=0.003)
    pad(ga, -2.43, 0.925, 0.03, 0.011, 0.008, 'y', lift=0.003)
    g.obj("mirror.arms", "steel", mirror=True)
    gh.obj("mirror.heads", "plastic", bevel=0.02, segs=3, mirror=True)
    gm.obj("mirror.glass", "chrome", mirror=True)
    gc.obj("camera.kerb", "visor", bevel=0.012, segs=3, mirror=True)
    gk.obj("camera.kerb.lens", "rim_bright", mirror=True)
    ga.obj("led.turn", "led_accent", mirror=True)

    # ---- the hand truck, folded flat and clipped to the off side sill
    g, gp, gw, gc = Geo(), Geo(), Geo(), Geo()
    y0 = -0.985
    for z in (0.285, 0.505):
        g.tube((0.22, y0, z), (-0.84, y0, z), 0.011, 10)
        gw.lathe([(-0.016, 0.02), (-0.016, 0.062), (-0.01, 0.07), (0.01, 0.07), (0.016, 0.062),
                  (0.016, 0.02)], 24,
                 xf=Matrix.Translation((-0.86, y0 - 0.055, z + (0.035 if z > 0.4 else -0.035)))
                 @ Matrix.Rotation(pi / 2, 4, 'X'))
    for x in (0.22, -0.12, -0.46, -0.80):
        g.tube((x, y0, 0.285), (x, y0, 0.505), 0.009, 8)
    g.tube((-0.86, y0 - 0.055, 0.24), (-0.86, y0 - 0.055, 0.55), 0.008, 8)
    g.tube((-0.80, y0, 0.395), (-0.86, y0 - 0.055, 0.395), 0.009, 8)
    gp.box((-0.70, y0 - 0.016, 0.395), (0.26, 0.006, 0.30))
    for x in (0.05, -0.60):
        gc.box((x, y0 + 0.02, 0.395), (0.05, 0.05, 0.27))
    g.obj("handtruck.frame", "caliper", sharp=40)
    gp.obj("handtruck.toe", "steel", bevel=0.002)
    gw.obj("handtruck.wheels", "rubber", sharp=40)
    gc.obj("handtruck.clips", "rubber", bevel=0.004)


# ---------------------------------------------------------------------------------------
# the roof: number and beacon on the cab; rails, drone dock, rack and ladder on the hold
# ---------------------------------------------------------------------------------------
def build_roof():
    def zr(x, y):
        return skin(x, y, 'z')[0].z
    RY = 0.56
    zt = zr(-1.2, RY) + 0.045                   # the rails' height
    g = Geo()
    for y in (RY, -RY):
        g.tube((-0.04, y, zt), (-2.43, y, zt), 0.014, 10)
        for x in (-0.12, -0.88, -1.62, -2.35):
            z = zr(x, y)
            g.hexa([(x - 0.06, y - 0.022, z - 0.004), (x + 0.06, y - 0.022, z - 0.004),
                    (x + 0.06, y + 0.022, z - 0.004), (x - 0.06, y + 0.022, z - 0.004),
                    (x - 0.03, y - 0.014, z + 0.045), (x + 0.03, y - 0.014, z + 0.045),
                    (x + 0.03, y + 0.014, z + 0.045), (x - 0.03, y + 0.014, z + 0.045)])
    g.obj("roof.rails", "plastic", bevel=0.004)

    # ---- the rack: cross bars, a guard rail round them, a strapped case
    g, gc, gs = Geo(), Geo(), Geo()
    xs = (-1.14, -1.56, -1.98, -2.40)
    for x in xs:
        g.box((x, 0, zt + 0.026), (0.05, 1.26, 0.024))
    zg = zt + 0.15
    for y in (0.62, -0.62):
        g.tube((xs[0], y, zg), (xs[-1], y, zg), 0.011, 8)
        for x in xs:
            g.tube((x, y, zt + 0.03), (x, y, zg), 0.008, 8)
    for x in (xs[0], xs[-1]):
        g.tube((x, 0.62, zg), (x, -0.62, zg), 0.011, 8)
    gc.box((-1.74, 0.12, zt + 0.10), (0.98, 0.52, 0.12))
    for x in (-1.45, -2.03):
        gs.box((x, 0.12, zt + 0.10), (0.04, 0.526, 0.126))
    g.obj("rack", "alu", sharp=40)
    gc.obj("rack.case", "plastic", bevel=0.02, segs=3)
    gs.obj("rack.straps", "pop")

    # ---- the drone's dock: a gloss pad on the rails, a lit ring, guides
    cx = -0.56
    g, gl, gf = Geo(), Geo(), Geo()
    z0 = zt + 0.016
    g.prism([(x, y, z0) for x, y in rrect(cx, 0, 0.36, 0.42, 0.09)], (0, 0, 0.045))
    zd = z0 + 0.045
    out, inn = rrect(cx, 0, 0.27, 0.30, 0.10, 8), rrect(cx, 0, 0.255, 0.285, 0.085, 8)
    m = len(out)
    gl.add([(x, y, zd + 0.001) for x, y in out] + [(x, y, zd + 0.001) for x, y in inn],
           [(k, (k + 1) % m, m + (k + 1) % m, m + k) for k in range(m)])
    for sx in (1, -1):
        for sy in (1, -1):
            gf.box((cx + sx * 0.30, sy * RY, z0 - 0.012), (0.07, 0.05, 0.03))
            gl.box((cx + sx * 0.325, sy * 0.385, zd + 0.004), (0.022, 0.022, 0.008))
    g.obj("dock", "visor", bevel=0.006)
    gl.obj("dock.ring", "pixel")
    gf.obj("dock.feet", "plastic", bevel=0.004)
    gt = Geo()
    K.text_flat(gt, "D-" + NUM, 0.05, (cx - 0.30, 0, zd + 0.0012), (0, -1, 0), (1, 0, 0),
                spacing=1.1)
    gt.obj("dock.text", "plate")
    build_drone(cx + 0.02, zd)

    # ---- the ladder at the back of the off side, over the roof's corner to the rack
    g = Geo()
    path = [(-1.005, 0.60), (-(side_y(2.20) + 0.07), 2.20), (-0.905, 2.37), (-0.80, zg + 0.02),
            (-0.62, zg + 0.02), (-0.62, zg)]
    for x in (-2.19, -2.43):
        for (ya, za), (yb, zb) in zip(path, path[1:]):
            g.tube((x, ya, za), (x, yb, zb), 0.013, 10)
        for z in (0.68, 1.45, 2.14):
            y = path[0][0] + (path[1][0] - path[0][0]) * (z - 0.60) / 1.60
            g.tube((x, y, z), (x, y + 0.085, z), 0.009, 8)
    z = 0.74
    while z < 2.2:
        y = path[0][0] + (path[1][0] - path[0][0]) * (z - 0.60) / 1.60
        g.tube((-2.19, y, z), (-2.43, y, z), 0.010, 8)
        z += 0.29
    g.tube((-2.19, -0.80, zg + 0.02), (-2.43, -0.80, zg + 0.02), 0.010, 8)
    g.obj("ladder", "alu", sharp=40)

    # ---- the cab's roof: the fleet number, an amber beacon bar, an antenna
    g = Geo()
    K.text_on_body(g, NUM, 0.46, 1.02, 0.0, 1, proj='z', turn=90)
    K.text_on_body(g, "T-" + NUM, 0.055, 0.52, 0.0, 1, proj='z', turn=90, spacing=1.15)
    g.obj("roof.number", "mark")
    g, gl = Geo(), Geo()
    xb = 1.66
    zb = zr(xb, 0.0)
    g.box((xb, 0, zb + 0.022), (0.10, 0.86, 0.05))
    for y in (0.30, -0.30):
        gl.box((xb, y, zb + 0.03), (0.104, 0.22, 0.026))
    gl.box((xb + 0.051, 0, zb + 0.03), (0.004, 0.30, 0.012))
    z = zr(1.86, -0.34)
    g.prism([(1.92, -0.346, z - 0.004), (1.83, -0.346, z + 0.055), (1.79, -0.346, z + 0.055),
             (1.78, -0.346, z - 0.004)], (0, 0.012, 0))
    g.obj("beacon", "visor", bevel=0.008, segs=3)
    gl.obj("led.beacon", "led_accent", bevel=0.004)


def build_drone(cx, z):
    """A small delivery drone sitting on its dock, the family's face in small, a parcel in
    its claws."""
    g, gp, gd, gv, gl, gb = Geo(), Geo(), Geo(), Geo(), Geo(), Geo()
    zb = z + 0.185
    g.box((cx, 0, zb), (0.30, 0.22, 0.075))
    gv.box((cx - 0.01, 0, zb + 0.045), (0.19, 0.15, 0.03))
    gv.box((cx + 0.151, 0, zb), (0.006, 0.19, 0.042))
    for y in (0.065, -0.065):
        gl.box((cx + 0.1555, y, zb), (0.002, 0.032, 0.024))
        gb.box((cx + 0.157, y, zb), (0.002, 0.016, 0.01))
    gl.box((cx + 0.1555, 0, zb + 0.008), (0.002, 0.07, 0.005))
    for sx in (1, -1):
        for sy in (1, -1):
            c = V3((cx + sx * 0.235, sy * 0.225, zb + 0.012))
            gd.tube((cx + sx * 0.12, sy * 0.09, zb), c, 0.012, 8)
            up = Matrix.Translation(c) @ Matrix.Rotation(pi / 2, 4, 'X')
            gd.lathe([(-0.022, 0.106), (-0.022, 0.118), (0.024, 0.122), (0.024, 0.108)], 28, xf=up)
            gd.lathe([(-0.018, 0.002), (-0.018, 0.02), (0.02, 0.016), (0.02, 0.002)], 12, xf=up)
            gl.lathe([(0.0245, 0.110), (0.0245, 0.120), (0.0265, 0.120), (0.0265, 0.110)], 28,
                     xf=up)
            for k in range(3):
                a = rad(120 * k + 25 * sx * sy)
                gb.box(c + V3((cos(a) * 0.055, sin(a) * 0.055, 0.008)), (0.10, 0.018, 0.003),
                       rot=Matrix.Rotation(a, 3, 'Z'))
            gd.tube((cx + sx * 0.11, sy * 0.085, zb - 0.03), (cx + sx * 0.15, sy * 0.15, z + 0.008),
                    0.006, 8)
            gd.box((cx + sx * 0.15, sy * 0.15, z + 0.005), (0.04, 0.04, 0.008))
    for sy in (1, -1):
        gd.box((cx, sy * 0.076, z + 0.105), (0.05, 0.008, 0.09))
    parcel(cx, 0, z + 0.03, 0.17, 0.145, 0.10, 0, "kraft", (1, 0))
    parcels_out("drone.parcel")
    g.obj("drone.body", "paint2", bevel=0.022, segs=3)
    gv.obj("drone.visor", "visor", bevel=0.006)
    gd.obj("drone.frame", "plastic", sharp=40)
    gb.obj("drone.blades", "mark")
    gl.obj("drone.lights", "pixel")


# ---------------------------------------------------------------------------------------
# inside: a walk-through cab with a low step, the driver on the off side; the hold
# ---------------------------------------------------------------------------------------
def build_interior():
    g = Geo()
    g.box((1.24, -0.135, CFLOOR - 0.015), (2.12, 1.47, 0.03))       # the cab's floor, less the
    g.box((1.75, 0.735, CFLOOR - 0.015), (1.10, 0.27, 0.03))        # step well by the door
    g.box((0.25, 0.735, CFLOOR - 0.015), (0.14, 0.27, 0.03))
    g.box((0.75, 0.605, 0.355), (0.86, 0.012, 0.13))                # the well's riser, its ends
    for x in (0.325, 1.175):
        g.box((x, 0.745, 0.355), (0.012, 0.29, 0.13))
    for y in (0.735, -0.735):                                       # wheel housings
        g.box((FA_X, y, 0.50), (0.90, 0.33, 0.60))
    g.box((2.20, 0, 0.93), (0.42, 1.66, 0.30))                      # the dash
    g.box((2.27, 0, 0.62), (0.20, 1.20, 0.36))
    g.box((0.16, 0.60, 1.21), (0.03, 0.54, 1.58))                   # the bulkhead, a doorway
    g.box((0.16, -0.60, 1.21), (0.03, 0.54, 1.58))                  # through its middle
    g.box((0.16, 0, 1.94), (0.03, 0.66, 0.12))
    g.box((0.25, 0, 0.52), (0.20, 0.66, 0.20))                      # a step up to the hold
    g.box((0.75, -0.90, 0.68), (0.82, 0.02, 0.70))                  # the off side door's card
    for y in (0.90, -0.90):
        g.box((1.80, y, 0.90), (1.10, 0.02, 0.20))
    g.box((1.02, -0.45, 0.52), (0.40, 0.42, 0.20))                  # the seat's pedestal
    g.obj("interior.tub", "interior", bevel=0.006)
    g = Geo()
    g.box((0.75, 0.90, 0.68), (0.82, 0.02, 0.70))
    g.box((0.75, 0.894, 0.86), (0.40, 0.03, 0.035))                 # its pull
    DOOR.append(g.obj("interior.card.l", "interior", bevel=0.006))
    g = Geo()
    g.box((1.10, 0, 2.003), (1.86, 1.40, 0.012))
    g.box((-1.33, 0, 2.288), (2.54, 1.44, 0.012))
    for y in (0.845, -0.845):                                       # the hold's walls
        g.box((-1.24, y, 1.50), (2.72, 0.02, 1.46))
    for y in (0.60, -0.60):                                         # its front, behind the brow
        g.box((0.13, y, 1.38), (0.02, 0.50, 1.22))
        g.box((-0.05, y, 2.13), (0.02, 0.50, 0.30))
    g.obj("interior.liner", "liner", bevel=0.004)
    g = Geo()                                                       # the floors' rubber
    g.box((1.24, -0.135, CFLOOR + 0.003), (2.08, 1.43, 0.006))
    g.box((-1.24, 0, HFLOOR - 0.012), (2.74, 1.70, 0.03))
    g.obj("interior.mat", "mat")
    g = Geo()
    for k in range(11):
        g.box((1.24, -0.82 + 0.13 * k, CFLOOR + 0.0075), (2.0, 0.012, 0.003))
    for k in range(13):
        g.box((-1.30, -0.72 + 0.12 * k, HFLOOR + 0.0045), (2.5, 0.012, 0.003))
    g.obj("interior.mat.ribs", "rubber")

    # ---- seats: the driver's on the off side, a mate's seat facing back over the near
    #      wheel housing
    g = Geo()
    tf, tb = Matrix.Rotation(rad(-12), 3, 'Y'), Matrix.Rotation(rad(10), 3, 'Y')
    g.box((1.04, -0.45, 0.675), (0.48, 0.50, 0.12))
    g.box((0.795, -0.45, 1.03), (0.11, 0.48, 0.62), rot=tf)
    g.box((0.725, -0.45, 1.42), (0.075, 0.27, 0.17), rot=tf)
    g.box((1.60, 0.70, 0.85), (0.42, 0.34, 0.10))
    g.box((1.855, 0.70, 1.13), (0.09, 0.34, 0.48), rot=tb)
    g.obj("interior.seats", "seat", bevel=0.024, segs=3)
    g = Geo()                                                       # belts
    g.hexa([(0.86, -0.67, 0.75), (0.86, -0.63, 0.75), (0.74, -0.63, 1.34), (0.74, -0.67, 1.34),
            (0.865, -0.67, 0.752), (0.865, -0.63, 0.752), (0.745, -0.63, 1.342),
            (0.745, -0.67, 1.342)])
    g.obj("interior.belts", "mark")

    # ---- the wheel on its column, two screens on the dash
    g, gs, gw = Geo(), Geo(), Geo()
    g.tube((2.0, -0.45, 1.0), (1.64, -0.45, 1.075), 0.022, 10)
    tw = (Matrix.Translation((1.63, -0.45, 1.078)) @ Matrix.Rotation(rad(-12), 4, 'Y')
          @ Matrix.Rotation(pi / 2, 4, 'Z'))
    gw.lathe([(-0.013, 0.178), (-0.013, 0.204), (0.013, 0.204), (0.013, 0.178)], 28, xf=tw)
    gw.lathe([(-0.012, 0.002), (-0.012, 0.045), (0.016, 0.04), (0.016, 0.002)], 14, xf=tw)
    gw.box((0, 0, 0), (0.016, 0.36, 0.03), xf=tw)
    g.box((2.03, -0.45, 1.14), (0.04, 0.36, 0.15), rot=Matrix.Rotation(rad(-15), 3, 'Y'))
    gs.box((2.008, -0.45, 1.143), (0.004, 0.32, 0.115), rot=Matrix.Rotation(rad(-15), 3, 'Y'))
    g.box((2.03, 0.02, 1.17), (0.03, 0.30, 0.21), rot=Matrix.Rotation(rad(-15), 3, 'Y'))
    gs.box((2.012, 0.02, 1.173), (0.004, 0.27, 0.18), rot=Matrix.Rotation(rad(-15), 3, 'Y'))
    g.obj("interior.dash.gear", "interior", bevel=0.006)
    gw.obj("interior.wheel", "mark", sharp=40)
    gs.obj("interior.screens", "screen")

    # ---- grab posts each side of each doorway, yellow nosings, the step's tread
    g, gn, gt, gr, gl = Geo(), Geo(), Geo(), Geo(), Geo()
    for x in (D_F - 0.05, D_R + 0.05):
        for y in (0.80, -0.80):
            g.tube((x, y, CFLOOR), (x, y, 2.0), 0.016, 12)
    for y in (0.36, -0.36):
        g.tube((0.19, y, 0.62), (0.19, y, 1.86), 0.014, 10)
    g.obj("interior.rails", "caliper", sharp=40)
    gt.box((0.75, 0.765, 0.294), (0.82, 0.31, 0.012))
    gn.box((0.75, 0.915, 0.296), (0.82, 0.024, 0.016))
    gn.box((0.75, 0.596, CFLOOR + 0.004), (0.82, 0.024, 0.014))
    gn.box((0.36, 0, CFLOOR + 0.204), (0.024, 0.62, 0.012))
    gn.box((0.115, 0, HFLOOR + 0.006), (0.024, 0.62, 0.012))
    for k in range(9):
        gr.box((0.75, 0.64 + 0.03 * k, 0.3015), (0.78, 0.008, 0.003))
    gl.box((0.75, 0.609, 0.40), (0.76, 0.004, 0.012))               # the step's light
    gt.box((-2.53, 0, HFLOOR + 0.008), (0.16, 1.24, 0.012))          # the tail's sill plate
    gn.box((-2.60, 0, HFLOOR + 0.01), (0.024, 1.24, 0.016))
    gt.obj("threshold", "rim_bright", bevel=0.002)
    gn.obj("threshold.nosing", "caliper", bevel=0.002)
    gr.obj("step.ribs", "rubber")
    gl.obj("step.light", "pixel")

    # ---- the hold: the lockers' cabinet on the near wall, shelves on the far one, parcels
    g, gs = Geo(), Geo()
    g.box((-1.42, 0.51, 1.30), (1.72, 0.02, 0.94))
    g.box((-1.42, 0.68, 1.775), (1.72, 0.34, 0.02))
    g.box((-1.42, 0.68, 0.835), (1.72, 0.34, 0.02))
    for x in (-0.57, -2.27):
        g.box((x, 0.68, 1.30), (0.02, 0.34, 0.94))
    g.obj("hold.cabinet", "cell", bevel=0.003)
    for z in (1.28, 1.76):
        gs.box((-1.25, -0.66, z), (2.3, 0.36, 0.02))
    for x in (-0.12, -1.25, -2.38):
        gs.box((x, -0.50, 1.50), (0.03, 0.03, 1.46))
    gs.obj("hold.shelves", "steel", bevel=0.002)
    for p in ((-2.42, -0.40, HFLOOR, .30, .40, .30, 4, "kraft"),
              (-2.43, 0.04, HFLOOR, .28, .42, .40, -3, "kraft"),
              (-2.41, 0.45, HFLOOR, .30, .34, .24, 6, "carton"),
              (-2.43, -0.42, HFLOOR + .30, .26, .30, .20, -8, "carton"),
              (-2.44, 0.46, HFLOOR + .24, .24, .30, .22, 2, "kraft"),
              (-2.44, 0.05, HFLOOR + .40, .22, .32, .11, 10, "mint"),
              (-2.02, -0.25, HFLOOR, .46, .50, .56, 0, "kraft"),
              (-2.02, 0.30, HFLOOR, .44, .52, .66, 0, "carton"),
              (-1.50, 0.10, HFLOOR, .50, .60, .45, 5, "kraft"),
              (-2.30, -0.66, 1.29, .30, .30, .22, 0, "kraft"),
              (-1.90, -0.66, 1.29, .36, .30, .30, 3, "carton"),
              (-1.40, -0.66, 1.29, .40, .30, .18, -2, "kraft"),
              (-0.80, -0.66, 1.29, .34, .30, .26, 0, "mint"),
              (-2.20, -0.66, 1.77, .40, .30, .24, 0, "kraft"),
              (-1.20, -0.66, 1.77, .50, .30, .20, 0, "carton")):
        parcel(*p)
    parcels_out("parcels")

    # ---- light: strips under both ceilings, and real lamps so the cab and the hold read
    g = Geo()
    g.box((1.10, 0, 1.995), (0.9, 0.20, 0.006))
    for y in (0.40, -0.40):
        g.box((-1.30, y, 2.28), (2.3, 0.05, 0.006))
    g.obj("interior.dome", "dome")
    g = Geo()
    g.box((0.75, 0.80, 1.90), (0.76, 0.012, 0.012))                 # a strip over the doorway
    g.obj("interior.welcome", "pixel")
    for x, sx, w in ((1.15, 1.4, 42.0), (-1.0, 1.6, 30.0), (-2.2, 0.6, 26.0)):
        L = bpy.data.lights.new("cabin", 'AREA')
        L.shape = 'RECTANGLE'
        L.size, L.size_y = sx, 0.9
        L.energy = w
        L.color = (1.0, 0.94, 0.84)
        o = bpy.data.objects.new("cabin.light", L)
        K.STUDIO.objects.link(o)
        o.location = (x, 0.0, 1.985 if x > 0 else 2.27)
    # the permit behind the windshield, on the near side
    w = W_FRONT
    c = w.at(0.52, 1.25, -GD - 0.012)
    g, gt, gs = Geo(), Geo(), Geo()
    q = [c + w.eu * a + w.ev * b for a, b in ((-0.05, -0.034), (0.05, -0.034), (0.05, 0.034),
                                                (-0.05, 0.034))]
    g.hexa([p - w.n * 0.002 for p in q] + q)
    g.obj("permit", "plate")
    K.text_flat(gt, "pakko", 0.03, c + w.n * 0.0008 + w.ev * 0.008 - w.eu * 0.014, w.eu, w.ev)
    K.text_flat(gt, "ROUTE 12  LOADING", 0.0075, c + w.n * 0.0008 - w.ev * 0.021, w.eu, w.ev,
                spacing=1.15)
    gt.obj("permit.text", "mark")
    q = [c + w.n * 0.0008 + w.eu * a + w.ev * b for a, b in ((0.022, -0.006), (0.043, -0.006),
                                                               (0.043, 0.024), (0.022, 0.024))]
    gs.add(q, [(0, 1, 2, 3)])
    gs.obj("permit.mark", "pop")


# ---------------------------------------------------------------------------------------
# wheels: a steel rim under a slotted cover
# ---------------------------------------------------------------------------------------
def build_wheel(tag, cx, side):
    K.build_wheel(tag, cx, T_R, T_W, T_RIM, T_OUT, side, rim=None, ring=None, caliper=None)
    hw, Rr = T_W / 2, T_RIM
    k = Rr / 0.19                           # the Mino's cover, grown with the rim
    flip = side < 0
    loc = (cx, side * (T_OUT - hw), T_R)
    g = Geo()
    g.lathe([(-hw + 0.03, Rr), (hw - 0.004, Rr), (hw - 0.004, Rr - 0.008), (hw - 0.03, Rr - 0.014),
             (hw - 0.05, Rr - 0.05), (hw - 0.05, 0.004), (hw - 0.062, 0.004),
             (hw - 0.062, Rr - 0.045), (-hw + 0.03, Rr - 0.012)], 56)
    g.obj("rim." + tag, "steel", flip_y=flip, loc=loc, sharp=40)
    g = Geo()
    g.lathe([(hw + 0.017, 0.004), (hw + 0.017, 0.036 * k), (hw + 0.009, 0.046 * k),
             (hw + 0.009, 0.135 * k), (hw + 0.003, 0.160 * k), (hw - 0.008, Rr - 0.005),
             (hw - 0.018, Rr - 0.003), (hw - 0.024, Rr - 0.010), (hw - 0.012, 0.150 * k),
             (hw - 0.004, 0.11 * k), (hw - 0.004, 0.004)], 64)
    g.obj("cover." + tag, "cover", flip_y=flip, loc=loc, sharp=35)
    g, gb = Geo(), Geo()
    slot = rrect(0.097 * k, 0.0, 0.028 * k, 0.019 * k, 0.012 * k, 4)
    for i in range(6):
        a = 2 * pi * (i + 0.5) / 6
        c, s = cos(a), sin(a)
        g.prism([(u * c - v * s, hw + 0.004, u * s + v * c) for u, v in slot], (0, 0.0058, 0))
    g.lathe([(hw + 0.004, 0.139 * k), (hw + 0.0096, 0.139 * k), (hw + 0.0096, 0.139 * k + 0.004),
             (hw + 0.004, 0.139 * k + 0.004)], 64)
    g.obj("cover.slots." + tag, "void", flip_y=flip, loc=loc)
    gb.lathe([(hw + 0.0172, 0.004), (hw + 0.0172, 0.028 * k), (hw + 0.019, 0.026 * k),
              (hw + 0.019, 0.004)], 24)
    gb.obj("cover.cap." + tag, "paint", flip_y=flip, loc=loc)
    g = Geo()
    g.tube((Rr - 0.03, hw - 0.012, 0.0), (Rr - 0.022, hw + 0.014, 0.0), 0.004, 6)
    g.obj("valve." + tag, "rubber", flip_y=flip, loc=loc)


# ---------------------------------------------------------------------------------------
# the left door slides open
# ---------------------------------------------------------------------------------------
def open_door(body):
    for pn in ("slider", "sclad"):
        DOOR.append(split_left(body.parts[pn]))
    for ob in DOOR:
        ob.location = V3(ob.location) + SLIDE


# ---------------------------------------------------------------------------------------
# views of its own, and the build
# ---------------------------------------------------------------------------------------
K.VIEWS["hero"].update(dir=(1.0, 1.02, 0.30))
K.VIEWS.update(
    nose=dict(dir=(1.0, 0.45, 0.14), lens=85, target=(2.4, 0.25, 0.9), dist=4.2),
    tail=dict(dir=(-1.0, -0.45, 0.16), lens=85, target=(-2.5, -0.2, 1.2), dist=5.0),
    door=dict(dir=(0.55, 1.0, 0.22), lens=70, target=(0.6, 0.8, 1.0), dist=4.6),
    lockers=dict(dir=(0.35, 1.0, 0.16), lens=70, target=(-1.3, 0.9, 1.4), dist=4.4),
    drone=dict(dir=(1.0, 0.7, 0.42), lens=85, target=(-0.5, 0.0, 2.5), dist=3.6),
)


def main():
    K.materials(paint=(0.07, 0.56, 0.37), paint_finish="gloss",
                paint2=(0.80, 0.78, 0.72), paint2_finish="gloss",
                dust_amount=0.3, glass=(0.60, 0.66, 0.68),
                led_front=(1.0, 0.90, 0.72), led_accent=(1.0, 0.42, 0.03),
                caliper=(0.95, 0.62, 0.03), seat=(0.36, 0.32, 0.25),
                interior=(0.13, 0.135, 0.14), decal=(0.012, 0.06, 0.055),
                screen=(0.30, 0.95, 0.70))
    grain("plastic", (0.040, 0.042, 0.046))
    K.pbr("steel", (0.035, 0.036, 0.04), 0.9, 0.45)
    K.pbr("alu", (0.62, 0.63, 0.65), 0.9, 0.38)
    K.pbr("chrome", (0.85, 0.86, 0.88), 1.0, 0.04)
    K.pbr("cover", (0.60, 0.61, 0.62), 0.0, 0.38, **{"Coat Weight": 0.4})
    K.pbr("plate", (0.82, 0.82, 0.78), 0.0, 0.45)
    K.pbr("label", (0.86, 0.86, 0.82), 0.0, 0.5)
    K.pbr("mark", (0.03, 0.032, 0.036), 0.0, 0.5)
    K.pbr("ink", (0.03, 0.032, 0.036), 0.0, 0.5)
    K.pbr("pop", (0.95, 0.42, 0.04), 0.0, 0.42)
    K.pbr("visor", (0.006, 0.006, 0.008), 0.0, 0.12)        # gloss black with no coat
    K.pbr("panel", (0.018, 0.026, 0.034), 0.0, 0.28)
    K.pbr("liner", (0.42, 0.42, 0.40), 0.0, 0.8)
    K.pbr("cell", (0.50, 0.51, 0.50), 0.0, 0.6)
    K.pbr("mat", (0.075, 0.08, 0.085), 0.0, 0.7)
    K.pbr("kraft", (0.42, 0.27, 0.13), 0.0, 0.85)
    K.pbr("carton", (0.72, 0.70, 0.64), 0.0, 0.8)
    K.pbr("mint", (0.30, 0.66, 0.50), 0.0, 0.7)
    K.pbr("tape", (0.80, 0.36, 0.05), 0.0, 0.45)
    K.pbr("reflector", (0.55, 0.01, 0.008), 0.0, 0.15, **{"Coat Weight": 1.0})
    K.emit("dome", (1.0, 0.93, 0.82), 50.0)
    K.emit("pixel", (0.30, 1.0, 0.72), 36.0)
    K.emit("pixel_r", (1.0, 0.50, 0.08), 36.0)
    body = build_hull()
    K.log("hull")
    if os.environ.get("PORTER_HULL"):       # the bare hull, to judge the form
        return K.shoot()
    build_glass()
    build_roller()
    build_locker()
    build_ends()
    build_sides()
    build_roof()
    build_interior()
    K.log("details")
    if not os.environ.get("PORTER_SHUT"):   # PORTER_SHUT=1: both cab doors closed
        open_door(body)
    for side, s in ((1, "l"), (-1, "r")):
        build_wheel("f" + s, FA_X, side)
        build_wheel("r" + s, RA_X, side)
    K.log("wheels")
    K.shoot(preview=("hero", "rear", "side", "front"),
            extra=dict(view="rear", size=(940, 528), corner="tl"))


main()
