"""Tanager Mino: a four-seat city car, a friendly tall box (both names made up), built on
vehicles/carkit.py.

Run (always through the wrapper, one Blender job at a time on this machine):
    vehicles/blender.sh vehicles/cars/tanager_mino.py --out DIR --preview
    vehicles/blender.sh vehicles/cars/tanager_mino.py --out DIR --sheet

The first Tanager, so it sets the family's cues (docs/progress/AG18/tanager_mino/README.md):
a soft tall box with the wheels at its corners, flat glass in rounded-rectangle openings with
fat black seals, a gloss visor across each end holding one light bar between two
rounded-rectangle lamp rings and a dot-matrix display, squircle wheel arches in grained
plastic cladding with a bump strip, steel wheels under slotted covers, a white cap roof with
its gear, a fleet roundel and service lettering.

The body is ten lines over sixteen stations with no hard edge but the cladding's step. The
windows are not panels of the cage: cutters open rounded holes in the skin (the cut faces
are thrown away), and the glass and its seal are laid behind each hole on the skin as built.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import bpy                                                          # noqa: E402
import carkit as K                                                  # noqa: E402
from carkit import (Geo, Matrix, V3, atan2, cos, hypot, on_body, pi, rad, sin,    # noqa: E402
                    stud)

# ---------------------------------------------------------------------------------------
# dimensions
# ---------------------------------------------------------------------------------------
FA_X, RA_X = 1.225, -1.225          # axles: wheelbase 2.45
T_R, T_W, T_RIM, T_OUT = 0.28, 0.165, 0.19, 0.752      # tire radius, width, rim, outer face
ARCH_A, ARCH_B, ARCH_ZC, ARCH_N = 0.335, 0.34, 0.285, 3.4   # squircle arch: half width, rise
BELT, HEAD = 0.95, 1.457            # belt line and glass header
GD = 0.011                          # how far the glass lies behind the skin
NUM = "07"


def tail_x(z):
    """The tail is one plane, leaning forward six degrees."""
    return -1.70 + (z - 0.30) * 0.1026


# ---------------------------------------------------------------------------------------
# helpers of this car: outlines, things laid on the skin as built
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
                   (0, -0.009)):
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
    "8": (".###.", "#...#", "#...#", ".###.", "#...#", "#...#", ".###."),
    "2": (".###.", "#...#", "....#", "...#.", "..#..", ".#...", "#####"),
    "%": ("##..#", "##.#.", "...#.", "..#..", ".#...", ".#.##", "#..##"),
    "z": ("...#.", "..##.", ".##..", "#####", "..##.", ".##..", ".#..."),      # a bolt
    "F": ("#####", "#....", "#....", "####.", "#....", "#....", "#...."),
    "R": ("####.", "#...#", "#...#", "####.", "#.#..", "#..#.", "#...#"),
    "E": ("#####", "#....", "#....", "####.", "#....", "#....", "#####"),
    "h": (".#.#.", "#####", "#####", "#####", ".###.", "..#..", "....."),      # a heart
    "|": ("#", "#", "#", "#", "#", "#", "#"),
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
                g.prism([(u, sg * 0.42, v) for u, v in self.o], (0, sg * 0.6, 0))
        elif self.proj == 'x':
            g.prism([(0.45, u, v) for u, v in self.o], (1.6, 0, 0))
        else:
            g.prism([(-1.15, u, v) for u, v in self.o], (-0.8, 0, 0))

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


def sheet(g, name, mirror=False):
    """Glass from a Geo of fans: thin, smooth."""
    ob = g.obj(name, "glass", mirror=mirror)
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
# body: stations and character lines
# ---------------------------------------------------------------------------------------
LINES = "CQRHGUVMFB"
#        C top centerline, Q roof / hood inner, R roof edge, H glass header / fender crown,
#        G belt, U foot of the paint, V top of the cladding (a step out), M rocker,
#        F floor edge, B floor centerline
ORDER = ["NC", "N0", "N1", "N2", "A1", "W0", "WS", "RF", "RG", "D1", "D2", "RA", "T2", "T1",
         "T0", "TC"]
#        NC and TC are rings inside the nose and tail faces (their outlines N0 and T0 drawn
#        in by a fifth), so the faces stay flat and full size out to their rounded edges
PT = {}


def cabin(x, zc=1.553):
    return [(x, 0, zc), (x, .42, zc - .002), (x, .60, zc - .021), (x, .688, HEAD),
            (x, .762, BELT), (x, .762, .505), (x, .775, .49), (x, .767, .26), (x, .65, .20),
            (x, 0, .20)]


NOSE = [(0, .83), (.36, .83), (.53, .815), (.60, .775), (.635, .68), (.64, .505), (.648, .495),
        (.615, .345), (.50, .30), (0, .30)]
TAIL = [(0, 1.485), (.40, 1.485), (.565, 1.47), (.635, 1.41), (.665, BELT), (.668, .505),
        (.676, .495), (.64, .35), (.52, .30), (0, .30)]


def inner(pts, zc, s=0.8, zlow=0.50):
    """A face's outline drawn in toward its middle (below the cladding's step toward zlow,
    so the step stays level across the face)."""
    return [(y * s, (zc if j < 5 else zlow) + (z - (zc if j < 5 else zlow)) * s)
            for j, (y, z) in enumerate(pts)]


def stations():
    def ring(x, pts):
        return [(x(z) if callable(x) else x, y, z) for (y, z) in pts]
    T = {
        "NC": ring(1.70, inner(NOSE, .58)),
        "N0": ring(1.70, NOSE),
        "N1": [(1.665, 0, .887), (1.665, .40, .887), (1.65, .59, .875), (1.63, .675, .826),
               (1.61, .722, .71), (1.61, .726, .505), (1.615, .738, .49), (1.625, .705, .30),
               (1.645, .56, .235), (1.66, 0, .235)],
        "N2": [(1.56, 0, .925), (1.56, .42, .925), (1.56, .615, .915), (1.56, .705, .877),
               (1.56, .76, .79), (1.56, .762, .505), (1.56, .775, .49), (1.56, .765, .27),
               (1.56, .64, .20), (1.56, 0, .20)],
        "A1": [(FA_X, 0, 1.0), (FA_X, .42, 1.0), (FA_X, .62, .99), (FA_X, .71, .957),
               (FA_X, .762, .877), (FA_X, .762, .505), (FA_X, .775, .49), (FA_X, .767, .26),
               (FA_X, .65, .20), (FA_X, 0, .20)],
        "W0": [(1.17, 0, 1.017), (1.17, .42, 1.017), (1.15, .62, 1.012), (1.10, .712, .992),
               (1.00, .762, BELT), (1.00, .762, .505), (1.00, .775, .49), (1.00, .767, .26),
               (1.00, .65, .20), (1.00, 0, .20)],
        "WS": [(.945, 0, 1.455), (.945, .42, 1.455), (.925, .605, 1.44), (.885, .692, 1.375)]
        + [None] * 6,
        "RF": [(.905, 0, 1.535), (.905, .42, 1.533), (.885, .60, 1.515), (.84, .688, 1.45)]
        + [None] * 6,
        "RG": [(.76, 0, 1.55), (.76, .42, 1.548), (.76, .60, 1.53), (.76, .688, 1.455)]
        + [None] * 6,
        "D1": cabin(.02), "D2": cabin(-.86), "RA": cabin(RA_X, 1.55),
        "T2": [(-1.45, 0, 1.538), (-1.45, .42, 1.536), (-1.455, .60, 1.518),
               (-1.47, .686, 1.447), (-1.56, .76, BELT), (-1.56, .762, .505),
               (-1.56, .775, .49), (-1.56, .765, .27), (-1.56, .64, .21), (-1.56, 0, .21)],
        "T1": [(-1.535, 0, 1.522), (-1.535, .42, 1.52), (-1.54, .60, 1.502),
               (-1.55, .68, 1.432), (-1.60, .737, BELT), (-1.645, .739, .505),
               (-1.65, .751, .49), (-1.66, .715, .30), (-1.672, .57, .24), (-1.675, 0, .24)],
        "T0": ring(tail_x, TAIL),
        "TC": ring(tail_x, inner(TAIL, .89)),
    }
    S = K.fill([T[k] for k in ORDER])
    PT.update(K.table(ORDER, LINES, S))
    return S


def panel_of(i, j):
    if i in (0, 14):                    # the faces: body color, the bumper pads lie on them
        return "nose" if i == 0 else "gate"
    if j == 8:
        return "floor"
    if j >= 5:
        return "clad"
    if i == 1:
        return "nose"
    if i <= 4:
        return "hood" if j <= 1 else "fender"
    if j <= 2:
        return "screen" if i <= 6 else "roof"
    return "door_f" if i <= 8 else "door_r" if i == 9 else "quarter"


PMAT = dict(nose="paint", hood="paint", fender="paint", screen="paint", roof="paint2",
            door_f="paint", door_r="paint", quarter="paint", gate="paint", clad="plastic",
            floor="underbody", well="well", wincut="void")


def line_crease(i, j):
    """Crease of the edge along line j from station i to i + 1."""
    if j in (5, 6):
        return 1.0                      # the cladding's step, also across the two faces:
    if i in (0, 14):                    # uncreased, the belt far above pulls it up
        return 0.0
    if j == 8:                          # the floor edge
        return 1.0 if 2 <= i <= 12 else 0.4
    if j == 7:
        return 0.5 if 2 <= i <= 12 else 0.2
    if j == 4:
        return 0.35 if i >= 5 else 0.2
    if j == 3:
        return 0.5 if i >= 5 else 0.3
    if j == 2:
        return 0.25 if i >= 5 else 0.0
    return 0.0


def station_crease(i, j):
    """Crease of the edge on station i between lines j and j + 1."""
    if i == 5:
        return 0.7 if j <= 2 else 0.0   # the cowl
    if i == 7:
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


W_SIDE = [Win([(.93, .99), (.76, 1.365), (.10, 1.365), (.10, .99)], [.055, .07, .07, .07],
              'y'),
          Win(rect(-.43, 1.1775, .37, .1875), .07, 'y'),
          Win([(-.92, .99), (-.92, 1.365), (-1.375, 1.365), (-1.415, .99)], .07, 'y')]
W_FRONT = Win([(-.56, 1.065), (.56, 1.065), (.53, 1.44), (-.53, 1.44)], .075, 'x')
W_REAR = Win(rect(0, 1.2075, .52, .1625), .075, 'X')


def build_hull():
    wells, wins = Geo(), Geo()
    for cx in (FA_X, RA_X):
        for sg in (1, -1):
            pts = arch_pts(cx)
            poly = [(pts[0][0], sg * 0.50, -0.3)] + [(x, sg * 0.50, z) for x, z in pts]
            poly.append((pts[-1][0], sg * 0.50, -0.3))
            wells.prism(poly, (0, sg * 0.5, 0))
    for w in W_SIDE + [W_FRONT, W_REAR]:
        w.cut(wins)
    body = K.build_body(stations(), panel_of, PMAT, line_crease, station_crease,
                        front=dict(kind="flat", panel="nose", crease=0.0),
                        rear=dict(kind="flat", panel="gate", crease=0.0),
                        cutters=[(wells, "well"), (wins, "wincut")], subdiv=3)
    ob = body.parts.pop("wincut")           # the holes stay, their walls go
    me = ob.data
    bpy.data.objects.remove(ob)
    bpy.data.meshes.remove(me)


# ---------------------------------------------------------------------------------------
# glass, seals, wipers
# ---------------------------------------------------------------------------------------
def build_glass():
    for w in W_SIDE + [W_FRONT, W_REAR]:
        w.fit()
    g, gs = Geo(), Geo()
    for w in W_SIDE:
        w.glass(g)
        w.seal(gs)
    sheet(g, "glass.side", mirror=True)
    gs.obj("seal.side", "rubber", bevel=0.0012, mirror=True)
    g, gs = Geo(), Geo()
    for w in (W_FRONT, W_REAR):
        w.glass(g)
        w.seal(gs)
    sheet(g, "glass.ends")
    gs.obj("seal.ends", "rubber", bevel=0.0012)
    # one big wiper in front, a small one behind
    g = Geo()
    for w, piv, a, b in ((W_FRONT, (-.05, 1.035), (-.12, 1.10), (.47, 1.125)),
                         (W_REAR, (0.0, 1.022), (.03, 1.075), (.36, 1.095))):
        p0 = w.at(*piv, 0.004)
        pa, pb = w.at(*a, -GD + 0.009), w.at(*b, -GD + 0.009)
        g.tube(pa, pb, 0.006, 8)
        g.tube(pa.lerp(pb, 0.1) + w.n * 0.004, pa.lerp(pb, 0.9) + w.n * 0.004, 0.004, 6)
        mid = pa.lerp(pb, 0.45) + w.n * 0.012
        g.tube(p0 + w.n * 0.014, mid, 0.005, 8)
        stud(g, p0, w.n, [(-0.004, 0.001), (-0.004, 0.017), (0.016, 0.014), (0.02, 0.001)], 14)
    g.obj("wipers", "cladding", bevel=0.0008)


# ---------------------------------------------------------------------------------------
# the visors: light bar, lamp rings, display; bumpers, plates, badges
# ---------------------------------------------------------------------------------------
def build_ends():
    for proj, tag, cv, zb, lit in (('x', "front", 0.69, 0.42, "led_front"),
                                   ('X', "rear", 0.885, 0.415, "led_rear")):
        sg = -1.0 if proj == 'X' else 1.0       # the car's left as this view's u
        g = Geo()
        pad(g, 0, cv, 0.625, 0.085, 0.05, proj, lift=0.004)
        g.obj("visor." + tag, "visor", bevel=0.002)
        gl, gk, gd = Geo(), Geo(), Geo()
        for y in (0.52, -0.52):
            pad(gl, y, cv, 0.075, 0.058, 0.03, proj, lift=0.0075)
            pad(gk, y, cv, 0.057, 0.040, 0.019, proj, lift=0.0085)
            pad(gl, y, cv, 0.020, 0.014, 0.008, proj, lift=0.0095)
        bar_on(gl, [(-0.44, cv + 0.034), (0.44, cv + 0.034)], proj, 0.016, 0.0075)
        gl.obj("led." + tag, lit, bevel=0.001)
        # the display, on the car's left under the bar
        du = sg * 0.235
        pad(gd, du, cv - 0.03, 0.135, 0.034, 0.012, proj, lift=0.006)
        gd.obj("display." + tag, "panel", bevel=0.001)
        gk.obj("lamp.cores." + tag, "gloss_black", bevel=0.001)
        gp = Geo()
        rows = banner("z 82%" if tag == "front" else "FREE h")
        dots(gp, rows, du, cv - 0.03, 0.0072, proj, 0.0068, 0.0052)
        gp.obj("pixels." + tag, "pixel" if tag == "front" else "pixel_r")
        # bumper: a grained pad with a slot, sensors
        g = Geo()
        pad(g, 0, zb, 0.625 if tag == "front" else 0.65, 0.112, 0.055, proj, lift=0.012,
            nv=10, step=0.02)
        g.obj("bumper." + tag, "plastic", bevel=0.004)
        g = Geo()                               # rubber guards on its corners
        for y in (0.56, -0.56) if tag == "front" else (0.585, -0.585):
            pad(g, y, zb, 0.028, 0.075, 0.02, proj, lift=0.019)
        g.obj("bumper.guards." + tag, "rubber", bevel=0.004)
        g = Geo()
        for y in (0.20, 0.47, -0.20, -0.47):
            loc, n = skin(y, zb + 0.062, proj)
            stud(g, loc + n * 0.012, n, [(-0.002, 0.001), (-0.002, 0.011), (0.0015, 0.011),
                                         (0.0015, 0.001)], 12)
        g.obj("sensors." + tag, "gloss_black")

    # ---- front: intake slot with slats, plate, fog lamps, tow eye
    g, gs = Geo(), Geo()
    pad(g, 0, 0.365, 0.36, 0.036, 0.03, 'x', lift=0.0124)
    g.obj("intake", "void")
    for z in (0.345, 0.365, 0.385):
        bar_on(gs, [(-0.335, z), (0.335, z)], 'x', 0.009, 0.0035, lift=0.0124)
    gs.obj("intake.slats", "plastic", bevel=0.001)
    g = Geo()
    for y in (0.455, -0.455):
        pad(g, y, 0.375, 0.05, 0.026, 0.014, 'x', lift=0.0135)
    g.obj("fog", "lamp", bevel=0.001)
    plate('x', 0.0, 0.475)
    g = Geo()
    loc, n = skin(-0.36, 0.475, 'x')
    stud(g, loc + n * 0.012, n, [(-0.001, 0.001), (-0.001, 0.026), (0.003, 0.024), (0.003, 0.001)],
         20)
    g.obj("tow.cover", "plastic", bevel=0.001)
    g = Geo()                                   # the eye itself, low under the lip
    g.lathe([(-0.006, 0.030), (0.0, 0.036), (0.006, 0.030), (0.0, 0.024)], 20,
            xf=Matrix.Translation((1.70, -0.36, 0.262)) @ Matrix.Rotation(pi / 2, 4, 'Z'))
    g.box((1.655, -0.36, 0.262), (0.07, 0.014, 0.014))
    g.obj("tow.eye", "caliper", sharp=40)

    # ---- rear: reflectors, reverse lamp, plate, lettering, stop lamp
    g = Geo()
    for y in (0.44, -0.44):
        pad(g, y, 0.445, 0.085, 0.018, 0.012, 'X', lift=0.0135)
    g.obj("reflectors", "reflector", bevel=0.001)
    g = Geo()
    pad(g, 0.0, 0.352, 0.06, 0.016, 0.01, 'X', lift=0.0135)
    g.obj("reverse", "lamp", bevel=0.001)
    plate('X', 0.0, 0.655)
    g = Geo()
    bar_on(g, [(-0.17, 1.418), (0.17, 1.418)], 'X', 0.012, 0.004)
    g.obj("led.stop", "led_rear")
    g = Geo()
    text_proj(g, "MINO", 0.062, 0.40, 0.735, 'X', spacing=1.1)
    text_proj(g, "tanager", 0.030, -0.42, 0.75, 'X', spacing=1.05)
    text_proj(g, "CITY SHARE  E-4", 0.014, -0.42, 0.715, 'X', spacing=1.15)
    text_proj(g, "UNIT 07", 0.016, 0.40, 0.685, 'X', spacing=1.2)
    g.obj("lettering.rear", "decal")
    badge('X', 0.0, 0.757, 0.034)
    badge('z', 1.615, 0.0, 0.034)


def plate(proj, u, v):
    g = Geo()
    lift = 0.0125 if v < 0.55 else 0.0
    pad(g, u, v, 0.15, 0.037, 0.008, proj, lift=lift + 0.004)
    g.obj("plate." + proj, "plate", bevel=0.001)
    g = Geo()
    text_proj(g, "VB 07-717", 0.042, u, v, proj, lift=lift + 0.0052, spacing=1.1)
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
# the flanks: arches, strips, handles, mirrors, markings
# ---------------------------------------------------------------------------------------
def build_sides():
    # ---- squircle arch trims in the cladding's plastic
    g = Geo()
    for cx in (FA_X, RA_X):
        n = 31
        ring = [(x, y, z) for y in (0.735, 0.787)
                for grow in (-0.006, 0.048) for (x, z) in arch_pts(cx, grow)]
        fs = []
        for k in range(n - 1):
            i0, i1, o0, o1 = k, k + 1, n + k, n + k + 1
            fs += [(i0, i1, o1, o0), (2 * n + i0, 2 * n + i1, 2 * n + o1, 2 * n + o0),
                   (i0, i1, 2 * n + i1, 2 * n + i0), (o0, o1, 2 * n + o1, 2 * n + o0)]
        fs += [(0, n, 3 * n, 2 * n), (n - 1, 2 * n - 1, 4 * n - 1, 3 * n - 1)]
        g.add(ring, fs)
    g.obj("arch.trims", "plastic", bevel=0.005, mirror=True)
    # ---- bump strip along the doors, mud flaps
    g = Geo()
    bar_on(g, [(0.855, 0.385), (-0.855, 0.385)], 'y', 0.06, 0.011)
    g.obj("bump.strip", "plastic", bevel=0.004, mirror=True)
    g = Geo()
    for z in (0.372, 0.398):
        bar_on(g, [(0.83, z), (-0.83, z)], 'y', 0.004, 0.0125)
    g.obj("bump.lines", "rubber", mirror=True)
    g = Geo()
    for cx in (FA_X, RA_X):
        g.box((cx - ARCH_A - 0.012, 0.682, 0.215), (0.012, 0.16, 0.21))
    g.obj("mudflaps", "rubber", bevel=0.003, mirror=True)
    # ---- door handles: a pocket and a pull
    g, gp = Geo(), Geo()
    for x in (0.17, -0.71):
        pad(g, x, 0.89, 0.062, 0.021, 0.02, 'y', lift=0.0008, sink=0.001)
        pad(gp, x, 0.899, 0.056, 0.0095, 0.009, 'y', lift=0.009)
    g.obj("handle.pockets", "void", mirror=True)
    gp.obj("handle.pulls", "paint", bevel=0.002, mirror=True)
    # ---- mirrors
    g, gm, ga = Geo(), Geo(), Geo()
    g.tube((0.985, 0.74, 0.985), (0.985, 0.835, 1.03), 0.013, 8)
    g.obj("mirror.stalks", "plastic", mirror=True)
    gm.box((0.985, 0.868, 1.06), (0.065, 0.135, 0.10))
    gm.obj("mirror.pods", "paint", bevel=0.02, segs=3, mirror=True)
    ga.box((0.951, 0.868, 1.06), (0.004, 0.105, 0.072))
    ga.obj("mirror.glass", "rim_bright", bevel=0.001, mirror=True)
    ga = Geo()
    ga.box((1.0185, 0.875, 1.06), (0.004, 0.09, 0.012))
    pad(ga, 1.09, 0.80, 0.032, 0.011, 0.008, 'y', lift=0.003)
    ga.obj("led.turn", "led_accent", mirror=True)
    # ---- fleet roundel on the front doors, lettering
    g = Geo()
    pad(g, 0.50, 0.735, 0.105, 0.105, 0.105, 'y', lift=0.0025, nc=12, nv=8)
    g.obj("roundel", "paint2", bevel=0.001, mirror=True)
    g, gw = Geo(), Geo()
    for side in (1, -1):
        K.text_on_body(g, NUM, 0.125, 0.50, 0.735, side, lift=0.0036)
        K.text_on_body(gw, "MINO", 0.078, -0.42, 0.745, side, spacing=1.12)
        K.text_on_body(gw, "TANAGER CITY SHARE", 0.021, -0.42, 0.672, side, spacing=1.2)
        K.text_on_body(gw, "UNIT 07   ZONE 4   TAP TO RIDE", 0.012, -0.42, 0.636, side, spacing=1.2)
        K.text_on_body(gw, "2.4 BAR", 0.013, RA_X, 0.735, side, spacing=1.15)
        K.text_on_body(gw, "2.2 BAR", 0.013, FA_X, 0.735, side, spacing=1.15)
        proj = 'y' if side > 0 else 'Y'
        for x in (0.80, -0.78):                 # jack points on the cladding
            tri = [skin(x + dx, 0.44 + dz, proj) for dx, dz in ((-0.016, 0.014), (0.016, 0.014),
                                                                (0.0, -0.014))]
            gw.add([p + n * 0.0015 for p, n in tri], [(0, 1, 2)])
    g.obj("roundel.number", "mark")
    gw.obj("lettering.side", "decal")
    # ---- charge door on the left front fender: outline, a lit bolt, a label
    g, gp, gt = Geo(), Geo(), Geo()
    K.ribbon(g, rrect(1.33, 0.775, 0.075, 0.052, 0.022), 'y', 0.004, closed=True)
    K.ribbon(g, [(1.262, 0.75), (1.262, 0.80)], 'y', 0.006)
    g.obj("charge.door", "void")
    dots(gp, GLYPH["z"], 1.345, 0.778, 0.006, 'y', 0.001, 0.0045)
    gp.obj("charge.bolt", "pixel")
    K.text_on_body(gt, "CHARGE 11 KW", 0.011, 1.33, 0.708, 1, spacing=1.2)
    gt.obj("charge.label", "decal")


# ---------------------------------------------------------------------------------------
# the roof: rails, sensor mast, antenna, number
# ---------------------------------------------------------------------------------------
def build_roof():
    def zr(x, y):
        return skin(x, y, 'z')[0].z
    g, gb = Geo(), Geo()
    for y in (0.47, -0.47):
        za, zb = zr(0.30, y) + 0.045, zr(-1.22, y) + 0.045
        g.tube((0.30, y, za), (-1.22, y, zb), 0.014, 10)
        for x in (0.22, -0.46, -1.14):
            z = zr(x, y)
            g.hexa([(x - 0.06, y - 0.022, z - 0.004), (x + 0.06, y - 0.022, z - 0.004),
                    (x + 0.06, y + 0.022, z - 0.004), (x - 0.06, y + 0.022, z - 0.004),
                    (x - 0.03, y - 0.014, z + 0.045), (x + 0.03, y - 0.014, z + 0.045),
                    (x + 0.03, y + 0.014, z + 0.045), (x - 0.03, y + 0.014, z + 0.045)])
    for x in (0.05, -0.98):
        z = zr(x, 0.47) + 0.058
        gb.box((x, 0, z), (0.05, 1.04, 0.016))
    g.obj("roof.rails", "plastic", bevel=0.004)
    gb.obj("roof.bars", "rim_bright", bevel=0.004)
    # the sensor mast: a foot, a neck, a puck with a lit band
    g, gl = Geo(), Geo()
    pad(g, 0.60, 0.0, 0.085, 0.06, 0.035, 'z', lift=0.012)
    z0 = zr(0.60, 0.0)
    up = Matrix.Translation((0.60, 0, z0)) @ Matrix.Rotation(pi / 2, 4, 'X')
    g.lathe([(0.01, 0.002), (0.01, 0.022), (0.045, 0.018), (0.045, 0.002)], 16, xf=up)
    g.lathe([(0.045, 0.002), (0.045, 0.060), (0.052, 0.068), (0.060, 0.068), (0.060, 0.064),
             (0.072, 0.064), (0.072, 0.068), (0.080, 0.062), (0.084, 0.03), (0.084, 0.002)],
            28, xf=up)
    gl.lathe([(0.0605, 0.060), (0.0605, 0.0655), (0.0715, 0.0655), (0.0715, 0.060)], 28, xf=up)
    g.obj("sensor.mast", "plastic", bevel=0.002)
    gl.obj("sensor.band", "pixel")
    g = Geo()
    z = zr(-1.30, -0.28)
    g.prism([(-1.24, -0.286, z - 0.004), (-1.33, -0.286, z + 0.055), (-1.37, -0.286, z + 0.055),
             (-1.38, -0.286, z - 0.004)], (0, 0.012, 0))
    g.obj("antenna", "plastic", bevel=0.003)
    g = Geo()
    K.text_on_body(g, NUM, 0.34, -0.47, 0.0, 1, proj='z', turn=90)
    K.text_on_body(g, "T-" + NUM, 0.05, 0.34, 0.0, 1, proj='z', turn=90, spacing=1.15)
    g.obj("roof.number", "mark")


# ---------------------------------------------------------------------------------------
# interior
# ---------------------------------------------------------------------------------------
def build_interior():
    g = Geo()
    g.box((-0.20, 0, 0.255), (2.62, 1.40, 0.03))                    # floor
    g.prism([(1.10, -0.70, 0.27), (1.10, -0.70, 0.985), (0.84, -0.70, 0.995),
             (0.70, -0.70, 0.93), (0.74, -0.70, 0.27)], (0, 1.40, 0))   # dash
    g.box((-1.30, 0, 0.93), (0.44, 1.36, 0.02))                     # parcel shelf
    g.box((-1.085, 0, 0.60), (0.03, 1.36, 0.66))                    # the boot's wall
    for y in (0.715, -0.715):                                       # door cards
        g.box((-0.10, y, 0.615), (2.20, 0.02, 0.65))
    g.box((0.30, 0, 0.36), (0.55, 0.16, 0.18))                      # a low console
    g.obj("interior.tub", "interior", bevel=0.006)
    g = Geo()
    tf, tr = Matrix.Rotation(rad(-14), 3, 'Y'), Matrix.Rotation(rad(-12), 3, 'Y')
    for y in (0.36, -0.36):
        g.box((0.30, y, 0.50), (0.48, 0.50, 0.13))
        g.box((0.03, y, 0.86), (0.11, 0.48, 0.62), rot=tf)
        g.box((-0.065, y, 1.245), (0.075, 0.25, 0.16), rot=tf)
        g.box((-0.905, y, 1.225), (0.075, 0.25, 0.15), rot=tr)
    g.box((-0.62, 0, 0.50), (0.46, 1.30, 0.13))
    g.box((-0.855, 0, 0.84), (0.11, 1.30, 0.58), rot=tr)
    g.obj("interior.seats", "seat", bevel=0.022, segs=3)
    g = Geo()
    wheel = (Matrix.Translation((0.66, 0.36, 1.00)) @ Matrix.Rotation(rad(-64), 4, 'Y')
             @ Matrix.Rotation(pi / 2, 4, 'X'))
    g.lathe([(-0.012, 0.165), (0.0, 0.178), (0.012, 0.165), (0.0, 0.152)], 24, xf=wheel)
    for a in (0, 180, 270):
        g.tube(wheel @ V3((0, -0.02, 0)), wheel @ V3((0.16 * cos(rad(a)), 0, 0.16 * sin(rad(a)))),
               0.011, 6)
    g.box((0.75, 0.36, 0.955), (0.20, 0.05, 0.05), rot=Matrix.Rotation(rad(-26), 3, 'Y'))
    g.obj("interior.wheel", "interior", sharp=40)
    g = Geo()
    scr = Matrix.Rotation(rad(-18), 3, 'Y')
    g.box((0.735, 0.0, 1.04), (0.008, 0.26, 0.085), rot=scr)
    g.box((0.765, 0.36, 1.03), (0.008, 0.20, 0.06), rot=scr)
    g.obj("interior.screens", "screen")
    g = Geo()                                   # ceiling lights, so the cabin reads
    for x in (0.25, -0.70):
        g.box((x, 0, 1.49), (0.34, 0.16, 0.008))
    g.obj("interior.dome", "dome")
    # the parking permit behind the windshield, on the right
    w = W_FRONT
    c = w.at(-0.40, 1.125, -GD - 0.012)
    g, gt, gs = Geo(), Geo(), Geo()
    q = [c + w.eu * a + w.ev * b for a, b in ((-0.045, -0.03), (0.045, -0.03), (0.045, 0.03),
                                                (-0.045, 0.03))]
    g.hexa([p - w.n * 0.002 for p in q] + q)
    g.obj("permit", "plate")
    K.text_flat(gt, "P4", 0.026, c + w.n * 0.0008 + w.ev * 0.008 - w.eu * 0.018, w.eu, w.ev)
    K.text_flat(gt, "ZONE 4  0717", 0.0075, c + w.n * 0.0008 - w.ev * 0.019, w.eu, w.ev,
                spacing=1.15)
    gt.obj("permit.text", "mark")
    q = [c + w.n * 0.0008 + w.eu * a + w.ev * b for a, b in ((0.012, -0.006), (0.038, -0.006),
                                                               (0.038, 0.022), (0.012, 0.022))]
    gs.add(q, [(0, 1, 2, 3)])
    gs.obj("permit.mark", "pixel")


# ---------------------------------------------------------------------------------------
# wheels: a steel rim under a slotted cover
# ---------------------------------------------------------------------------------------
def build_wheel(tag, cx, side):
    K.build_wheel(tag, cx, T_R, T_W, T_RIM, T_OUT, side, rim=None, ring=None, caliper=None)
    hw, Rr = T_W / 2, T_RIM
    flip = side < 0
    loc = (cx, side * (T_OUT - hw), T_R)
    g = Geo()
    g.lathe([(-hw + 0.03, Rr), (hw - 0.004, Rr), (hw - 0.004, Rr - 0.008), (hw - 0.03, Rr - 0.014),
             (hw - 0.05, Rr - 0.05), (hw - 0.05, 0.004), (hw - 0.062, 0.004),
             (hw - 0.062, Rr - 0.045), (-hw + 0.03, Rr - 0.012)], 56)
    g.obj("rim." + tag, "steel", flip_y=flip, loc=loc, sharp=40)
    g = Geo()
    g.lathe([(hw + 0.017, 0.004), (hw + 0.017, 0.036), (hw + 0.009, 0.046), (hw + 0.009, 0.135),
             (hw + 0.003, 0.160), (hw - 0.008, Rr - 0.005), (hw - 0.018, Rr - 0.003),
             (hw - 0.024, Rr - 0.010), (hw - 0.012, 0.150), (hw - 0.004, 0.11),
             (hw - 0.004, 0.004)], 64)
    g.obj("cover." + tag, "cover", flip_y=flip, loc=loc, sharp=35)
    g, gb = Geo(), Geo()
    slot = rrect(0.097, 0.0, 0.028, 0.019, 0.012, 4)
    for k in range(6):
        a = 2 * pi * (k + 0.5) / 6
        c, s = cos(a), sin(a)
        g.prism([(u * c - v * s, hw + 0.004, u * s + v * c) for u, v in slot], (0, 0.0058, 0))
    g.lathe([(hw + 0.004, 0.139), (hw + 0.0096, 0.139), (hw + 0.0096, 0.143), (hw + 0.004, 0.143)],
            64)
    g.obj("cover.slots." + tag, "void", flip_y=flip, loc=loc)
    gb.lathe([(hw + 0.0172, 0.004), (hw + 0.0172, 0.028), (hw + 0.019, 0.026), (hw + 0.019, 0.004)],
             24)
    gb.obj("cover.cap." + tag, "paint", flip_y=flip, loc=loc)
    g = Geo()
    g.tube((Rr - 0.03, hw - 0.012, 0.0), (Rr - 0.022, hw + 0.014, 0.0), 0.004, 6)
    g.obj("valve." + tag, "rubber", flip_y=flip, loc=loc)


# ---------------------------------------------------------------------------------------
# views of its own, and the build
# ---------------------------------------------------------------------------------------
K.VIEWS.update(
    nose=dict(dir=(1.0, 0.45, 0.14), lens=85, target=(1.6, 0.25, 0.65), dist=3.2),
    tail=dict(dir=(-1.0, 0.45, 0.16), lens=85, target=(-1.6, 0.2, 0.8), dist=3.4),
    wheel=dict(dir=(0.5, 1.0, 0.12), lens=85, target=(FA_X, 0.8, 0.45), dist=2.6),
    glass=dict(dir=(1.0, 0.7, 0.3), lens=85, target=(0.8, 0.3, 1.15), dist=3.6),
)


def main():
    K.materials(paint=(0.70, 0.050, 0.028), paint_finish="gloss",
                paint2=(0.80, 0.78, 0.72), paint2_finish="gloss",
                dust_amount=0.3, glass=(0.60, 0.66, 0.68),
                led_front=(1.0, 0.90, 0.72), led_accent=(1.0, 0.42, 0.03),
                caliper=(0.95, 0.62, 0.03), seat=(0.36, 0.31, 0.23),
                interior=(0.05, 0.05, 0.055), decal=(0.86, 0.85, 0.80),
                screen=(0.30, 0.95, 0.70))
    grain("plastic", (0.040, 0.042, 0.046))
    K.pbr("steel", (0.035, 0.036, 0.04), 0.9, 0.45)
    K.pbr("cover", (0.60, 0.61, 0.62), 0.0, 0.38, **{"Coat Weight": 0.4})
    K.pbr("plate", (0.82, 0.82, 0.78), 0.0, 0.45)
    K.pbr("mark", (0.03, 0.032, 0.036), 0.0, 0.5)
    K.pbr("visor", (0.006, 0.006, 0.008), 0.0, 0.12)        # gloss black with no coat
    K.pbr("panel", (0.018, 0.026, 0.034), 0.0, 0.28)
    K.pbr("reflector", (0.55, 0.01, 0.008), 0.0, 0.15, **{"Coat Weight": 1.0})
    K.emit("dome", (1.0, 0.93, 0.82), 50.0)
    K.emit("pixel", (0.30, 1.0, 0.72), 36.0)
    K.emit("pixel_r", (1.0, 0.50, 0.08), 36.0)
    build_hull()
    K.log("hull")
    if os.environ.get("MINO_HULL"):         # the bare hull, to judge the form
        return K.shoot()
    build_glass()
    build_ends()
    build_sides()
    build_roof()
    build_interior()
    K.log("details")
    for side, s in ((1, "l"), (-1, "r")):
        build_wheel("f" + s, FA_X, side)
        build_wheel("r" + s, RA_X, side)
    K.log("wheels")
    K.shoot(extra=dict(view="rear", size=(940, 528), corner="tl"))


main()
