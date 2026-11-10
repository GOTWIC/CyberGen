"""Tanager Cab: a driverless city taxi, a one-box people carrier for four (both names made
up), built on vehicles/carkit.py.

Run (always through the wrapper, one Blender job at a time on this machine):
    vehicles/blender.sh vehicles/cars/tanager_cab.py --out DIR --preview
    vehicles/blender.sh vehicles/cars/tanager_cab.py --out DIR --sheet

The Mino's bigger sibling (docs/progress/AG18/tanager_mino/README.md lists the family's
cues, all repeated here): the soft tall box, holes for windows with flat glass and a fat
seal, the gloss visor with a light bar between two lamp rings and a dot-matrix display,
squircle arches, stepped grained cladding with a bump strip, steel wheels under slotted
covers, a cap roof with its gear on two rails, roundel and small print, a round badge.

Its own job: one box with no hood and no driver (a sensor bar over the windshield), four
seats facing each other in pairs across a low flat floor, one big sliding door each side on
a visible track (the left one built open, over a fold-out step), a luggage hatch, and a
roof sign that is a dot-matrix band all round.

The body is ten lines over fourteen stations. The windows are holes cut through the skin;
the left door's panels, glass and details are objects of their own, slid back at the end.
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
FA_X, RA_X = 1.50, -1.50            # axles: wheelbase 3.0
T_R, T_W, T_RIM, T_OUT = 0.33, 0.205, 0.225, 0.888     # tire radius, width, rim, outer face
ARCH_A, ARCH_B, ARCH_ZC, ARCH_N = 0.39, 0.395, 0.335, 3.4   # squircle arch: half width, rise
BELT, HEAD, ROOF = 1.00, 1.67, 1.78  # belt line, glass header, roof
STEP = 0.53                         # the cladding's step
D_F, D_R = 0.64, -0.62              # the sliding door's front and rear edges as built
D_FC, D_RC = 0.772, -0.748          # their stations in the cage: subdivision draws an edge
#                                     toward its neighbors, (prev + 4 x + next) / 6
SLIDE = V3((-1.27, 0.09, 0.0))      # how far the open door has gone
FLOOR = 0.30                        # the cabin floor
GD = 0.011                          # how far the glass lies behind the skin
NUM = "31"
DOOR = []                           # objects that slide with the left door


def tail_x(z):
    """The tail is one plane, leaning forward six degrees."""
    return -2.25 + (z - 0.32) * 0.105


# ---------------------------------------------------------------------------------------
# the family's helpers (from the Mino): outlines, things laid on the skin as built
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


# ---------------------------------------------------------------------------------------
# helpers of this car: the sliding door
# ---------------------------------------------------------------------------------------
def door_obj(g, name, mat, glass=False, **kw):
    """A part of the sliding doors, drawn on the left: the left one will slide with its
    door, the right one is its mirror image."""
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


# ---------------------------------------------------------------------------------------
# body: stations and character lines
# ---------------------------------------------------------------------------------------
LINES = "CQRHGUVMFB"
#        C top centerline, Q roof inner, R roof edge, H glass header / brow corner,
#        G belt, U foot of the paint, V top of the cladding (a step out), M rocker,
#        F floor edge, B floor centerline
ORDER = ["NC", "N0", "N1", "W0", "WS", "RF", "RG", "D1", "D2", "RA", "T2", "T1", "T0", "TC"]
#        NC and TC are rings inside the nose and tail faces, so the faces stay flat and
#        full size out to their rounded edges; W0 is the cowl: there is no hood
PT = {}


def cabin(x, zc=ROOF):
    return [(x, 0, zc), (x, .50, zc - .002), (x, .71, zc - .023), (x, .815, HEAD),
            (x, .90, BELT), (x, .90, STEP + .015), (x, .913, STEP), (x, .905, .29),
            (x, .77, .225), (x, 0, .225)]


NOSE = [(0, .96), (.44, .96), (.64, .945), (.725, .90), (.765, .79), (.772, STEP + .015),
        (.782, STEP), (.745, .37), (.60, .32), (0, .32)]
TAIL = [(0, 1.715), (.47, 1.715), (.665, 1.698), (.75, 1.63), (.785, BELT), (.79, STEP + .015),
        (.80, STEP), (.76, .375), (.615, .32), (0, .32)]


def inner(pts, zc, s=0.8, zlow=STEP):
    """A face's outline drawn in toward its middle (below the cladding's step toward zlow,
    so the step stays level across the face)."""
    return [(y * s, (zc if j < 5 else zlow) + (z - (zc if j < 5 else zlow)) * s)
            for j, (y, z) in enumerate(pts)]


def stations():
    def ring(x, pts):
        return [(x(z) if callable(x) else x, y, z) for (y, z) in pts]
    T = {
        "NC": ring(2.25, inner(NOSE, .70)),
        "N0": ring(2.25, NOSE),
        "N1": [(2.205, 0, 1.012), (2.205, .47, 1.012), (2.19, .695, .998), (2.165, .795, .945),
               (2.14, .853, .82), (2.14, .858, STEP + .015), (2.145, .871, STEP),
               (2.155, .835, .33), (2.18, .66, .26), (2.20, 0, .26)],
        "W0": [(2.13, 0, 1.055), (2.13, .50, 1.055), (2.11, .72, 1.048), (2.06, .835, 1.03),
               (1.96, .90, BELT), (1.96, .90, STEP + .015), (1.96, .913, STEP),
               (1.96, .905, .29), (1.96, .77, .225), (1.96, 0, .225)],
        "WS": [(1.745, 0, 1.70), (1.745, .50, 1.698), (1.725, .705, 1.68), (1.685, .80, 1.61)]
        + [None] * 6,
        "RF": [(1.69, 0, 1.768), (1.69, .50, 1.766), (1.67, .70, 1.745), (1.625, .812, 1.668)]
        + [None] * 6,
        "RG": [(1.50, 0, ROOF), (1.50, .50, ROOF - .002), (1.50, .71, ROOF - .023),
               (1.50, .815, HEAD)] + [None] * 6,
        "D1": cabin(D_FC), "D2": cabin(D_RC), "RA": cabin(RA_X, ROOF - .003),
        "T2": [(-1.96, 0, 1.768), (-1.96, .50, 1.766), (-1.965, .705, 1.745),
               (-1.98, .812, 1.662), (-2.08, .897, BELT), (-2.08, .90, STEP + .015),
               (-2.08, .913, STEP), (-2.08, .903, .30), (-2.08, .76, .235), (-2.08, 0, .235)],
        "T1": [(-2.06, 0, 1.752), (-2.06, .49, 1.750), (-2.065, .70, 1.730),
               (-2.08, .80, 1.652), (-2.14, .868, BELT), (-2.185, .872, STEP + .015),
               (-2.19, .885, STEP), (-2.20, .845, .33), (-2.215, .67, .265), (-2.22, 0, .265)],
        "T0": ring(tail_x, TAIL),
        "TC": ring(tail_x, inner(TAIL, 1.05)),
    }
    S = K.fill([T[k] for k in ORDER])
    PT.update(K.table(ORDER, LINES, S))
    return S


def panel_of(i, j):
    if i in (0, 12):                    # the faces: body color, the bumper pads lie on them
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
    if i in (0, 12):                    # uncreased, the belt far above pulls it up
        return 0.0
    if j == 8:                          # the floor edge
        return 1.0 if 2 <= i <= 10 else 0.4
    if j == 7:
        return 0.5 if 2 <= i <= 10 else 0.2
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


W_FQ = Win([(1.80, 1.055), (1.535, 1.585), (.77, 1.585), (.77, 1.055)], [.06, .08, .08, .08],
           'y')
W_DOOR = Win(rect(0.01, 1.32, .50, .265), .08, 'y')
W_RQ = Win([(-.75, 1.055), (-.75, 1.585), (-1.885, 1.585), (-1.935, 1.055)], .08, 'y')
W_FRONT = Win([(-.67, 1.125), (.67, 1.125), (.63, 1.60), (-.63, 1.60)], .09, 'x')
W_REAR = Win(rect(0, 1.335, .60, .215), .085, 'X')
WINS = [W_FQ, W_DOOR, W_RQ, W_FRONT, W_REAR]


def build_hull():
    wells, wins = Geo(), Geo()
    for cx in (FA_X, RA_X):
        for sg in (1, -1):
            pts = arch_pts(cx)
            poly = [(pts[0][0], sg * 0.60, -0.3)] + [(x, sg * 0.60, z) for x, z in pts]
            poly.append((pts[-1][0], sg * 0.60, -0.3))
            wells.prism(poly, (0, sg * 0.5, 0))
    for w in WINS:
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
# glass, seals, wipers
# ---------------------------------------------------------------------------------------
def build_glass():
    for w in WINS:
        w.fit()
    g, gs = Geo(), Geo()
    for w in (W_FQ, W_RQ):
        w.glass(g)
        w.seal(gs)
    sheet(g, "glass.side", mirror=True)
    gs.obj("seal.side", "rubber", bevel=0.0012, mirror=True)
    g, gs = Geo(), Geo()
    W_DOOR.glass(g)
    W_DOOR.seal(gs)
    door_obj(g, "glass.door", "glass", glass=True)
    door_obj(gs, "seal.door", "rubber", bevel=0.0012)
    g, gs = Geo(), Geo()
    for w in (W_FRONT, W_REAR):
        w.glass(g)
        w.seal(gs)
    sheet(g, "glass.ends")
    gs.obj("seal.ends", "rubber", bevel=0.0012)
    # one big wiper in front, a small one behind
    g = Geo()
    for w, piv, a, b in ((W_FRONT, (-.05, 1.092), (-.14, 1.165), (.58, 1.195)),
                         (W_REAR, (0.0, 1.085), (.03, 1.145), (.42, 1.168))):
        p0 = w.at(*piv, 0.004)
        pa, pb = w.at(*a, -GD + 0.009), w.at(*b, -GD + 0.009)
        g.tube(pa, pb, 0.006, 8)
        g.tube(pa.lerp(pb, 0.1) + w.n * 0.004, pa.lerp(pb, 0.9) + w.n * 0.004, 0.004, 6)
        mid = pa.lerp(pb, 0.45) + w.n * 0.012
        g.tube(p0 + w.n * 0.014, mid, 0.005, 8)
        stud(g, p0, w.n, [(-0.004, 0.001), (-0.004, 0.017), (0.016, 0.014), (0.02, 0.001)], 14)
    g.obj("wipers", "cladding", bevel=0.0008)


# ---------------------------------------------------------------------------------------
# the visors: light bar, lamp rings, display; bumpers, plates, badges, the luggage hatch
# ---------------------------------------------------------------------------------------
def build_ends():
    for proj, tag, cv, zb, lit, hw in (('x', "front", 0.80, 0.455, "led_front", 0.745),
                                       ('X', "rear", 0.90, 0.455, "led_rear", 0.765)):
        sg = -1.0 if proj == 'X' else 1.0       # the car's left as this view's u
        ly = hw - 0.105                         # the lamp rings
        g = Geo()
        pad(g, 0, cv, hw, 0.09, 0.055, proj, lift=0.004)
        g.obj("visor." + tag, "visor", bevel=0.002)
        gl, gk, gd = Geo(), Geo(), Geo()
        for y in (ly, -ly):
            pad(gl, y, cv, 0.082, 0.062, 0.032, proj, lift=0.0075)
            pad(gk, y, cv, 0.063, 0.043, 0.02, proj, lift=0.0085)
            pad(gl, y, cv, 0.022, 0.015, 0.009, proj, lift=0.0095)
        bar_on(gl, [(-ly + 0.09, cv + 0.037), (ly - 0.09, cv + 0.037)], proj, 0.017, 0.0075)
        gl.obj("led." + tag, lit, bevel=0.001)
        # the display, on the car's left under the bar: charge in front, the next stop behind
        rows = banner("z 64%" if tag == "front" else "NEXT>QUAY 6")
        wd = len(rows[0]) * 0.0072 / 2 + 0.022
        du = sg * (ly - 0.105 - wd)
        pad(gd, du, cv - 0.03, wd, 0.036, 0.012, proj, lift=0.006)
        gd.obj("display." + tag, "panel", bevel=0.001)
        gk.obj("lamp.cores." + tag, "gloss_black", bevel=0.001)
        gp = Geo()
        dots(gp, rows, du, cv - 0.03, 0.0072, proj, 0.0068, 0.0052)
        gp.obj("pixels." + tag, "pixel" if tag == "front" else "pixel_r")
        # bumper: a grained pad, rubber guards on its corners, sensors
        bw = 0.75 if tag == "front" else 0.77
        g = Geo()
        pad(g, 0, zb, bw, 0.118, 0.058, proj, lift=0.012, nv=10, step=0.02)
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
    for y in (0.54, -0.54):
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
            xf=Matrix.Translation((2.25, -0.40, 0.285)) @ Matrix.Rotation(pi / 2, 4, 'Z'))
    g.box((2.205, -0.40, 0.285), (0.07, 0.014, 0.014))
    g.obj("tow.eye", "caliper", sharp=40)
    g = Geo()                                   # the forward radar, a gloss plate
    pad(g, 0.40, 0.50, 0.07, 0.03, 0.012, 'x', lift=0.0135)
    g.obj("radar", "visor", bevel=0.001)
    g = Geo()
    text_proj(g, "tanager", 0.034, 0.0, 0.925, 'x', spacing=1.08)
    g.obj("lettering.front", "decal")

    # ---- rear: the luggage hatch's shut line and pull, reflectors, plate, lettering
    g = Geo()
    K.ribbon(g, rrect(0.0, 1.11, 0.715, 0.545, 0.10), 'X', 0.006, closed=True)
    g.obj("hatch.line", "void")
    g, gp = Geo(), Geo()
    pad(g, 0.0, 0.598, 0.10, 0.02, 0.018, 'X', lift=0.0008, sink=0.001)
    pad(gp, 0.0, 0.606, 0.09, 0.009, 0.008, 'X', lift=0.008)
    g.obj("hatch.pocket", "void")
    gp.obj("hatch.pull", "paint", bevel=0.002)
    g = Geo()
    for y in (0.52, -0.52):
        pad(g, y, 0.475, 0.095, 0.018, 0.012, 'X', lift=0.0135)
    g.obj("reflectors", "reflector", bevel=0.001)
    g = Geo()
    pad(g, 0.0, 0.375, 0.065, 0.016, 0.01, 'X', lift=0.0135)
    g.obj("reverse", "lamp", bevel=0.001)
    plate('X', 0.0, 0.688)
    g = Geo()
    bar_on(g, [(-0.20, 1.605), (0.20, 1.605)], 'X', 0.012, 0.004)
    g.obj("led.stop", "led_rear")
    g = Geo()
    text_proj(g, "CAB", 0.066, 0.46, 0.735, 'X', spacing=1.1)
    text_proj(g, "tanager", 0.032, -0.46, 0.745, 'X', spacing=1.05)
    text_proj(g, "CITY CAB  E-6  DRIVERLESS", 0.014, -0.46, 0.708, 'X', spacing=1.15)
    text_proj(g, "UNIT " + NUM, 0.017, 0.46, 0.682, 'X', spacing=1.2)
    text_proj(g, "LUGGAGE  40 KG", 0.012, 0.0, 0.636, 'X', spacing=1.2)
    g.obj("lettering.rear", "decal")
    badge('X', 0.0, 0.772, 0.032)
    badge('z', 2.172, 0.0, 0.036)


def plate(proj, u, v):
    g = Geo()
    lift = 0.0125 if v < 0.57 else 0.0
    pad(g, u, v, 0.15, 0.037, 0.008, proj, lift=lift + 0.004)
    g.obj("plate." + proj, "plate", bevel=0.001)
    g = Geo()
    text_proj(g, "VB 31-204", 0.042, u, v, proj, lift=lift + 0.0052, spacing=1.1)
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
# the flanks: arches, strips, checker bands, door gear, markings
# ---------------------------------------------------------------------------------------
def on_door(x):
    return D_R + 0.02 < x < D_F - 0.02


def by_door(x, m=0.025):
    return abs(x - D_F) < m or abs(x - D_R) < m


def build_sides():
    # ---- squircle arch trims in the cladding's plastic
    g = Geo()
    for cx in (FA_X, RA_X):
        n = 31
        ring = [(x, y, z) for y in (0.872, 0.927)
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
        g.box((cx - ARCH_A - 0.012, 0.80, 0.235), (0.012, 0.19, 0.23))
    g.obj("mudflaps", "rubber", bevel=0.003, mirror=True)

    # ---- bump strip with two rubber lines: fixed pieces, and the door's own
    zs = 0.405
    g, gl, gd, gdl = Geo(), Geo(), Geo(), Geo()
    for a, b in ((1.03, D_F + 0.03), (D_R - 0.03, -1.03)):
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

    # ---- the taxi's checker, twice: molded into the cladding, and in the fleet's
    #      lettering color under the belt
    g, gd, gm, gmd = Geo(), Geo(), Geo(), Geo()
    s = 0.022
    k, x = 0, 1.035
    while x > -1.04:
        if not by_door(x, 0.03):
            for r, z in enumerate((0.468, 0.468 + s)):
                if (k + r) % 2 == 0:
                    tile(gmd if on_door(x) else gm, x, z, s / 2, s / 2, 'y', 0.003)
        x -= s
        k += 1
    s = 0.03
    k, x = 0, 1.87
    while x > -2.0:
        if not by_door(x, 0.035):
            for r, z in enumerate((0.874, 0.874 + s)):
                if (k + r) % 2 == 0:
                    tile(gd if on_door(x) else g, x, z, s / 2, s / 2, 'y', 0.0014, None)
        x -= s
        k += 1
    gm.obj("checker.molded", "plastic", bevel=0.0008, mirror=True)
    door_obj(gmd, "checker.molded.door", "plastic", bevel=0.0008)
    g.obj("checker.band", "decal", mirror=True)
    door_obj(gd, "checker.band.door", "decal")

    # ---- the door's track along the rear quarter, and its roller arm on the door
    g, gb = Geo(), Geo()
    pad(g, -1.29, 0.966, 0.655, 0.013, 0.012, 'y', lift=0.0008, sink=0.001)
    g.obj("track", "void", mirror=True)
    for z in (0.983, 0.949):
        bar_on(gb, [(-0.645, z), (-1.94, z)], 'y', 0.006, 0.004)
    gb.obj("track.lips", "rim_bright", mirror=True)
    g = Geo()
    loc, n = skin(D_R + 0.035, 0.966, 'y')
    g.box(loc + V3((-0.045, -0.004, 0)), (0.13, 0.02, 0.022))
    door_obj(g, "track.arm", "steel", bevel=0.003)

    # ---- door handle (an upright pull in a pocket), lock, the roundel
    g, gp, gr = Geo(), Geo(), Geo()
    pad(g, 0.515, 0.715, 0.024, 0.085, 0.022, 'y', lift=0.0008, sink=0.001)
    pad(gp, 0.523, 0.715, 0.0095, 0.075, 0.009, 'y', lift=0.010)
    pad(gr, 0.17, 0.705, 0.118, 0.118, 0.118, 'y', lift=0.0025, nc=12, nv=8)
    door_obj(g, "handle.pocket", "void")
    door_obj(gp, "handle.pull", "paint", bevel=0.002)
    door_obj(gr, "roundel", "paint2", bevel=0.001)
    for side, tag in ((1, ".l"), (-1, ".r")):
        g, gw = Geo(), Geo()
        K.text_on_body(g, NUM, 0.135, 0.17, 0.705, side, lift=0.0036)
        K.text_on_body(gw, "CAB", 0.092, -0.29, 0.735, side, spacing=1.12)
        K.text_on_body(gw, "TANAGER CITY CAB", 0.022, -0.29, 0.655, side, spacing=1.2)
        K.text_on_body(gw, "UNIT 31   ZONE 4   TAP TO RIDE", 0.012, -0.29, 0.618, side,
                       spacing=1.2)
        K.text_on_body(gw, "SLIDING DOOR  STAND CLEAR", 0.010, 0.0, 0.565, side, spacing=1.25)
        a, b = g.obj("roundel.number" + tag, "mark"), gw.obj("lettering.door" + tag, "decal")
        if side > 0:
            DOOR.extend((a, b))
        # fixed small print: tire pressures, jack points, the track's warning
        gw = Geo()
        K.text_on_body(gw, "2.6 BAR", 0.014, RA_X, 0.825, side, spacing=1.15)
        K.text_on_body(gw, "2.6 BAR", 0.014, FA_X, 0.825, side, spacing=1.15)
        K.text_on_body(gw, "KEEP TRACK CLEAR", 0.010, -1.75, 0.932, side, spacing=1.25)
        proj = 'y' if side > 0 else 'Y'
        for x in (0.86, -0.84):
            tri = [skin(x + dx, 0.345 + dz, proj) for dx, dz in ((-0.016, 0.014), (0.016, 0.014),
                                                                 (0.0, -0.014))]
            gw.add([p + n * 0.0015 for p, n in tri], [(0, 1, 2)])
        gw.obj("lettering.side" + tag, "decal")

    # ---- the payment pad on the pillar ahead of each door
    g, gp, gk = Geo(), Geo(), Geo()
    pad(g, 0.705, 1.235, 0.03, 0.075, 0.014, 'y', lift=0.005)
    pad(gk, 0.705, 1.205, 0.017, 0.017, 0.017, 'y', lift=0.0062, nc=6)
    dots(gp, [".###.", "#...#", "#.#.#", "#...#", ".###."], 0.705, 1.205, 0.005, 'y', 0.0068,
         0.0036)
    dots(gp, ["#.#.#.#"], 0.705, 1.275, 0.005, 'y', 0.0058, 0.0036)
    g.obj("pay.pad", "visor", bevel=0.0015, mirror=True)
    gk.obj("pay.field", "panel", mirror=True)
    gp.obj("pay.pixels", "pixel", mirror=True)

    # ---- corner cameras where a driver's mirrors would be, turn lamps
    g, gm, ga = Geo(), Geo(), Geo()
    g.tube((1.90, 0.875, 1.005), (1.90, 0.95, 1.035), 0.012, 8)
    g.obj("camera.stalks", "plastic", mirror=True)
    gm.box((1.90, 0.972, 1.045), (0.10, 0.05, 0.05))
    gm.obj("camera.pods", "visor", bevel=0.014, segs=3, mirror=True)
    ga.box((1.953, 0.972, 1.045), (0.004, 0.034, 0.012))
    ga.box((1.847, 0.972, 1.045), (0.004, 0.034, 0.012))
    pad(ga, 1.92, 0.925, 0.03, 0.011, 0.008, 'y', lift=0.003)
    pad(ga, -2.03, 0.925, 0.03, 0.011, 0.008, 'y', lift=0.003)
    ga.obj("led.turn", "led_accent", mirror=True)

    # ---- charge door on the left front quarter: outline, a lit bolt, a label
    g, gp, gt = Geo(), Geo(), Geo()
    K.ribbon(g, rrect(0.87, 0.70, 0.078, 0.054, 0.022), 'y', 0.004, closed=True)
    K.ribbon(g, [(0.80, 0.675), (0.80, 0.725)], 'y', 0.006)
    g.obj("charge.door", "void")
    dots(gp, GLYPH["z"], 0.885, 0.703, 0.006, 'y', 0.001, 0.0045)
    gp.obj("charge.bolt", "pixel")
    K.text_on_body(gt, "CHARGE 22 KW", 0.011, 0.87, 0.628, 1, spacing=1.2)
    gt.obj("charge.label", "decal")


# ---------------------------------------------------------------------------------------
# the roof: rails, the sign band, the sensor bar, antenna, number
# ---------------------------------------------------------------------------------------
PUCK = [(0.0, 0.002), (0.0, 0.060), (0.007, 0.068), (0.015, 0.068), (0.015, 0.064),
        (0.027, 0.064), (0.027, 0.068), (0.035, 0.062), (0.039, 0.03), (0.039, 0.002)]


def build_roof():
    def zr(x, y):
        return skin(x, y, 'z')[0].z
    RY = 0.54
    g = Geo()
    for y in (RY, -RY):
        za, zb = zr(1.30, y) + 0.045, zr(-1.72, y) + 0.045
        g.tube((1.30, y, za), (-1.72, y, zb), 0.014, 10)
        for x in (1.22, 0.25, -0.70, -1.64):
            z = zr(x, y)
            g.hexa([(x - 0.06, y - 0.022, z - 0.004), (x + 0.06, y - 0.022, z - 0.004),
                    (x + 0.06, y + 0.022, z - 0.004), (x - 0.06, y + 0.022, z - 0.004),
                    (x - 0.03, y - 0.014, z + 0.045), (x + 0.03, y - 0.014, z + 0.045),
                    (x + 0.03, y + 0.014, z + 0.045), (x - 0.03, y + 0.014, z + 0.045)])
    g.obj("roof.rails", "plastic", bevel=0.004)

    # ---- the sign: a hollow band all round, dot matrix on its four faces
    cx, a, b, r, t = 0.20, 0.34, 0.60, 0.15, 0.05
    z0 = zr(cx, RY) + 0.052
    z1 = z0 + 0.118
    out = rpoly(rect(cx, 0, a, b), r, 8)
    inn = rpoly(rect(cx, 0, a - t, b - t), r - t, 8)
    m = len(out)
    vs = ([(x, y, z0) for x, y in out] + [(x, y, z1) for x, y in out]
          + [(x, y, z0) for x, y in inn] + [(x, y, z1) for x, y in inn])
    fs = []
    for k in range(m):
        k2 = (k + 1) % m
        fs += [(k, k2, m + k2, m + k), (2 * m + k, 2 * m + k2, 3 * m + k2, 3 * m + k),
               (m + k, m + k2, 3 * m + k2, 3 * m + k), (k, k2, 2 * m + k2, 2 * m + k)]
    g = Geo()
    g.add(vs, fs)
    g.obj("sign.band", "visor", bevel=0.004)
    g = Geo()                                   # its feet on the rails, a bright cap line
    for x in (cx - 0.17, cx + 0.17):
        for y in (RY, -RY):
            g.box((x, y, z0 - 0.012), (0.07, 0.05, 0.03))
    g.obj("sign.feet", "plastic", bevel=0.004)
    gp = Geo()
    zm, e = (z0 + z1) / 2, 0.0012
    free = banner("h FREE h")
    dots_flat(gp, free, (cx + a + e, 0, zm), (0, 1, 0), (0, 0, 1), 0.0125, 0.0092)
    dots_flat(gp, free, (cx - a - e, 0, zm), (0, -1, 0), (0, 0, 1), 0.0125, 0.0092)
    gp.obj("sign.pixels", "pixel")
    gp = Geo()
    side = banner("CAB 31")
    dots_flat(gp, side, (cx, b + e, zm), (-1, 0, 0), (0, 0, 1), 0.0105, 0.0076)
    dots_flat(gp, side, (cx, -b - e, zm), (1, 0, 0), (0, 0, 1), 0.0105, 0.0076)
    gp.obj("sign.pixels.side", "pixel_r")

    # ---- the sensor bar over the windshield: a bright bar across the rails, a lidar puck
    #      on each end, camera lenses and a lit strip along its face
    g, gb, gl, gk = Geo(), Geo(), Geo(), Geo()
    xb = 1.18
    zb = zr(xb, RY) + 0.036
    gb.box((xb, 0, zb + 0.012), (0.11, 1.42, 0.036))
    gl.box((xb + 0.0555, 0, zb + 0.012), (0.004, 1.02, 0.008))
    for y in (0.63, -0.63):
        up = (Matrix.Translation((xb, y, zb + 0.028)) @ Matrix.Rotation(pi / 2, 4, 'X')
              @ Matrix.Scale(1.25, 4))
        g.lathe(PUCK, 32, xf=up)
        gl.lathe([(0.0155, 0.060), (0.0155, 0.0655), (0.0265, 0.0655), (0.0265, 0.060)], 32, xf=up)
    for y in (0.40, -0.40):                     # its feet on the rails' line
        g.box((xb, y * 1.35, zb - 0.02), (0.07, 0.05, 0.04))
    for y in (-0.30, -0.15, 0.15, 0.30):
        gk.lathe([(0.0, 0.002), (0.0, 0.015), (0.004, 0.013), (0.004, 0.002)], 14,
                 xf=(Matrix.Translation((xb + 0.0555, y, zb + 0.012))
                     @ Matrix.Rotation(pi / 2, 4, 'Z')))
    gb.obj("sensor.bar", "visor", bevel=0.012, segs=3)
    g.obj("sensor.pods", "plastic", bevel=0.003)
    gl.obj("sensor.band", "pixel")
    gk.obj("sensor.lenses", "rim_bright")
    g = Geo()                                   # a puck at the back too, and the antenna
    z = zr(-1.80, 0.0)
    up = Matrix.Translation((-1.80, 0, z + 0.004)) @ Matrix.Rotation(pi / 2, 4, 'X')
    g.lathe(PUCK, 28, xf=up)
    gl = Geo()
    gl.lathe([(0.0155, 0.060), (0.0155, 0.0655), (0.0265, 0.0655), (0.0265, 0.060)], 28, xf=up)
    gl.obj("sensor.band.rear", "pixel")
    z = zr(-1.72, -0.30)
    g.prism([(-1.66, -0.306, z - 0.004), (-1.75, -0.306, z + 0.055), (-1.79, -0.306, z + 0.055),
             (-1.80, -0.306, z - 0.004)], (0, 0.012, 0))
    g.obj("antenna", "plastic", bevel=0.003)
    g = Geo()
    K.text_on_body(g, NUM, 0.40, -0.92, 0.0, 1, proj='z', turn=90)
    K.text_on_body(g, "T-" + NUM, 0.055, 0.86, 0.0, 1, proj='z', turn=90, spacing=1.15)
    g.obj("roof.number", "mark")


# ---------------------------------------------------------------------------------------
# the cabin: a low flat floor, two pairs of seats facing each other, rails, screens
# ---------------------------------------------------------------------------------------
def build_interior():
    g = Geo()
    g.box((0.0, 0, FLOOR - 0.015), (2.20, 1.70, 0.03))             # the floor between the arches
    for x in (1.48, -1.48):
        g.box((x, 0, FLOOR - 0.015), (0.80, 1.16, 0.03))
    for x, top in ((1.19, 1.03), (-1.19, 1.0)):                    # bulkheads behind the seats
        g.box((x, 0, 0.53), (0.03, 1.16, 0.46))
        g.box((x, 0, (0.76 + top) / 2), (0.03, 1.62, top - 0.76))
    g.box((1.625, 0, 1.02), (0.87, 1.60, 0.02))                      # the shelf under the screen
    g.box((-1.655, 0, 0.99), (0.93, 1.60, 0.02))                     # the luggage cover
    for y in (0.872, -0.872):                                       # wall cards
        for x in (0.87, -0.855):
            g.box((x, y, 0.655), (0.43, 0.02, 0.67))
    g.box((0.01, -0.872, 0.655), (1.22, 0.02, 0.67))                # the right door's card
    for x in (D_F + 0.04, D_R - 0.04):                              # door pillars' linings
        for y in (0.845, -0.845):
            g.box((x, y, 0.655), (0.075, 0.05, 0.69))
    for x in (0.77, -0.77):                                         # seat plinths
        g.box((x, 0, 0.44), (0.38, 1.22, 0.28))
    g.obj("interior.tub", "interior", bevel=0.006)
    g = Geo()
    g.box((0.01, 0.872, 0.655), (1.22, 0.02, 0.67))
    g.box((0.01, 0.868, 0.80), (0.50, 0.03, 0.035))                 # its pull
    DOOR.append(g.obj("interior.card.l", "interior", bevel=0.006))
    g = Geo()
    g.box((0.0, 0, 1.735), (2.3, 1.36, 0.012))
    g.obj("interior.headliner", "liner", bevel=0.004)
    g = Geo()                                                       # the floor's rubber mat
    g.box((0.0, 0, FLOOR + 0.003), (1.22, 1.62, 0.006))
    g.obj("interior.mat", "mat")
    g = Geo()
    for k in range(13):
        g.box((0.0, -0.72 + 0.12 * k, FLOOR + 0.0075), (1.16, 0.012, 0.003))
    g.obj("interior.mat.ribs", "rubber")

    # ---- seats: the front pair rides backward
    g = Geo()
    for sx, lean in ((1.0, 12), (-1.0, -12)):
        tf = Matrix.Rotation(rad(lean), 3, 'Y')
        for y in (0.335, -0.335):
            g.box((sx * 0.75, y, 0.655), (0.46, 0.52, 0.13))
            g.box((sx * 1.015, y, 1.02), (0.11, 0.50, 0.62), rot=tf)
            g.box((sx * 1.095, y, 1.415), (0.075, 0.27, 0.17), rot=tf)
    g.obj("interior.seats", "seat", bevel=0.024, segs=3)
    g = Geo()                                                       # armrests between them
    for sx in (0.78, -0.78):
        g.box((sx, 0, 0.80), (0.36, 0.09, 0.07))
    g.obj("interior.armrests", "interior", bevel=0.015, segs=3)
    g = Geo()                                                       # belts
    for sx in (1.0, -1.0):
        for y in (0.335, -0.335):
            o = 0.20 if y > 0 else -0.20
            g.hexa([(sx * 0.95, y + o - 0.02, 0.74), (sx * 0.95, y + o + 0.02, 0.74),
                    (sx * 1.05, y + o + 0.02, 1.33), (sx * 1.05, y + o - 0.02, 1.33),
                    (sx * 0.945, y + o - 0.02, 0.742), (sx * 0.945, y + o + 0.02, 0.742),
                    (sx * 1.045, y + o + 0.02, 1.332), (sx * 1.045, y + o - 0.02, 1.332)])
    g.obj("interior.belts", "mark")

    # ---- grab rails: a post each side of each door, one along the ceiling
    g = Geo()
    for x in (D_F - 0.06, D_R + 0.06):
        for y in (0.74, -0.74):
            g.tube((x, y, FLOOR), (x, y, 1.66), 0.016, 12)
    g.tube((0.52, 0, 1.66), (-0.52, 0, 1.66), 0.014, 10)
    for x in (0.52, 0.0, -0.52):
        g.tube((x, 0, 1.66), (x, 0, 1.735), 0.010, 8)
    g.obj("interior.rails", "caliper", sharp=40)

    # ---- thresholds: tread plate with a bright nosing, the lower track's slot
    g, gn, gv = Geo(), Geo(), Geo()
    for y in (0.835, -0.835):
        g.box((0.01, y, FLOOR + 0.004), (1.22, 0.11, 0.008))
        gn.box((0.01, y + (0.05 if y > 0 else -0.05), FLOOR + 0.007), (1.22, 0.022, 0.012))
        gv.box((0.01, y - (0.02 if y > 0 else -0.02), FLOOR + 0.0085), (1.18, 0.012, 0.002))
    g.obj("threshold", "rim_bright", bevel=0.002)
    gn.obj("threshold.nosing", "caliper", bevel=0.002)
    gv.obj("threshold.slot", "void")

    # ---- the fold-out step under the open door, on two arms, a lit edge
    g, gl, gr = Geo(), Geo(), Geo()
    g.box((0.01, 1.035, 0.165), (1.06, 0.23, 0.022))
    for x in (0.38, -0.36):
        g.hexa([(x - 0.02, 0.80, 0.215), (x + 0.02, 0.80, 0.215), (x + 0.02, 0.96, 0.160),
                (x - 0.02, 0.96, 0.160), (x - 0.02, 0.80, 0.235), (x + 0.02, 0.80, 0.235),
                (x + 0.02, 0.96, 0.178), (x - 0.02, 0.96, 0.178)])
    for k in range(9):
        gr.box((0.01, 0.945 + 0.0225 * k, 0.178), (1.0, 0.008, 0.004))
    gl.box((0.01, 1.151, 0.165), (1.0, 0.004, 0.010))
    g.obj("step", "steel", bevel=0.004)
    gr.obj("step.ribs", "rubber")
    gl.obj("step.light", "pixel")

    # ---- screens: one on each bulkhead between the headrests, a strip behind the windshield
    g, gs = Geo(), Geo()
    for sx in (1.0, -1.0):
        g.box((sx * 1.16, 0, 1.24), (0.03, 0.40, 0.24))
        gs.box((sx * 1.143, 0, 1.24), (0.004, 0.36, 0.20))
    gs.box((1.99, 0, 1.065), (0.006, 0.62, 0.05), rot=Matrix.Rotation(rad(-20), 3, 'Y'))
    g.box((1.975, 0, 1.055), (0.03, 0.66, 0.07), rot=Matrix.Rotation(rad(-20), 3, 'Y'))
    g.box((1.55, 0, 1.065), (0.40, 0.50, 0.07))                     # the computer's hump
    g.obj("interior.screen.frames", "interior", bevel=0.006)
    g, gp = Geo(), Geo()                        # the destination strip under the header
    g.box((1.725, 0, 1.548), (0.02, 0.86, 0.088))
    for y in (0.30, -0.30):
        g.box((1.725, y, 1.625), (0.014, 0.03, 0.075))
    dots_flat(gp, banner("CAB 31 >QUAY 6"), (1.7365, 0, 1.548), (0, 1, 0), (0, 0, 1), 0.0088,
              0.0064)
    g.obj("interior.destination", "visor", bevel=0.004)
    gp.obj("interior.destination.pixels", "pixel")
    gs.obj("interior.screens", "screen")
    g = Geo()                                   # ceiling lights, so the cabin reads
    for x in (0.62, -0.62):
        g.box((x, 0, 1.727), (0.50, 0.20, 0.006))
    for y in (0.60, -0.60):
        g.box((0.0, y, 1.727), (1.10, 0.03, 0.006))
    g.obj("interior.dome", "dome")
    g = Geo()                                   # a welcome strip over each doorway
    for y in (0.775, -0.775):
        g.box((0.01, y, 1.655), (1.10, 0.012, 0.012))
    g.obj("interior.welcome", "pixel")
    for x, sx, w in ((0.0, 1.6, 45.0), (1.55, 0.5, 14.0), (-1.6, 0.5, 14.0)):
        L = bpy.data.lights.new("cabin", 'AREA')        # and real light under the headliner
        L.shape = 'RECTANGLE'
        L.size, L.size_y = sx, 0.9
        L.energy = w
        L.color = (1.0, 0.94, 0.84)
        o = bpy.data.objects.new("cabin.light", L)
        K.STUDIO.objects.link(o)
        o.location = (x, 0.0, 1.715)
    # the permit behind the windshield, on the right
    w = W_FRONT
    c = w.at(-0.50, 1.19, -GD - 0.012)
    g, gt, gs = Geo(), Geo(), Geo()
    q = [c + w.eu * a + w.ev * b for a, b in ((-0.045, -0.03), (0.045, -0.03), (0.045, 0.03),
                                                (-0.045, 0.03))]
    g.hexa([p - w.n * 0.002 for p in q] + q)
    g.obj("permit", "plate")
    K.text_flat(gt, "CAB", 0.022, c + w.n * 0.0008 + w.ev * 0.008 - w.eu * 0.016, w.eu, w.ev)
    K.text_flat(gt, "ZONE 4  0204", 0.0075, c + w.n * 0.0008 - w.ev * 0.019, w.eu, w.ev,
                spacing=1.15)
    gt.obj("permit.text", "mark")
    q = [c + w.n * 0.0008 + w.eu * a + w.ev * b for a, b in ((0.014, -0.006), (0.038, -0.006),
                                                               (0.038, 0.022), (0.014, 0.022))]
    gs.add(q, [(0, 1, 2, 3)])
    gs.obj("permit.mark", "pixel")


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
K.VIEWS["hero"].update(dir=(1.0, 0.92, 0.30))
K.VIEWS.update(
    nose=dict(dir=(1.0, 0.45, 0.14), lens=85, target=(2.1, 0.25, 0.75), dist=3.6),
    tail=dict(dir=(-1.0, -0.45, 0.16), lens=85, target=(-2.1, -0.2, 0.9), dist=3.8),
    door=dict(dir=(0.55, 1.0, 0.22), lens=70, target=(-0.1, 0.8, 0.85), dist=4.2),
    sign=dict(dir=(1.0, 0.6, 0.35), lens=85, target=(0.6, 0.2, 1.75), dist=3.4),
)


def main():
    K.materials(paint=(0.37, 0.003, 0.16), paint_finish="gloss",
                paint2=(0.80, 0.78, 0.72), paint2_finish="gloss",
                dust_amount=0.3, glass=(0.60, 0.66, 0.68),
                led_front=(1.0, 0.90, 0.72), led_accent=(1.0, 0.42, 0.03),
                caliper=(0.95, 0.62, 0.03), seat=(0.40, 0.36, 0.28),
                interior=(0.13, 0.135, 0.14), decal=(0.86, 0.85, 0.80),
                screen=(0.30, 0.95, 0.70))
    grain("plastic", (0.040, 0.042, 0.046))
    K.pbr("steel", (0.035, 0.036, 0.04), 0.9, 0.45)
    K.pbr("cover", (0.60, 0.61, 0.62), 0.0, 0.38, **{"Coat Weight": 0.4})
    K.pbr("plate", (0.82, 0.82, 0.78), 0.0, 0.45)
    K.pbr("mark", (0.03, 0.032, 0.036), 0.0, 0.5)
    K.pbr("visor", (0.006, 0.006, 0.008), 0.0, 0.12)        # gloss black with no coat
    K.pbr("panel", (0.018, 0.026, 0.034), 0.0, 0.28)
    K.pbr("liner", (0.42, 0.42, 0.40), 0.0, 0.8)
    K.pbr("mat", (0.075, 0.08, 0.085), 0.0, 0.7)
    K.pbr("reflector", (0.55, 0.01, 0.008), 0.0, 0.15, **{"Coat Weight": 1.0})
    K.emit("dome", (1.0, 0.93, 0.82), 50.0)
    K.emit("pixel", (0.30, 1.0, 0.72), 36.0)
    K.emit("pixel_r", (1.0, 0.50, 0.08), 36.0)
    body = build_hull()
    K.log("hull")
    if os.environ.get("CAB_HULL"):          # the bare hull, to judge the form
        return K.shoot()
    build_glass()
    build_ends()
    build_sides()
    build_roof()
    build_interior()
    K.log("details")
    if not os.environ.get("CAB_SHUT"):      # CAB_SHUT=1: both doors closed
        open_door(body)
    for side, s in ((1, "l"), (-1, "r")):
        build_wheel("f" + s, FA_X, side)
        build_wheel("r" + s, RA_X, side)
    K.log("wheels")
    K.shoot(preview=("hero", "rear", "side", "front"),
            extra=dict(view="rear", size=(940, 528), corner="tl"))


main()
