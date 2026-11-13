"""Tanager's shared helpers: rounded outlines, things laid on the skin (pads, bars, tiles,
dot-matrix displays in 5 x 7 glyphs, lettering), the windows cut through the skin with
their glass and fat seals, the sliding door's parts, the plate and the round badge, the
grained plastic, the squircle wheel arch and the slotted wheel cover.

Lifted from the Mino, the Cab and the Porter (the Porter's copies, the newest): rpoly,
rect, rrect, AXIS_U, GD, skin, pad, bar_on, tile, text_proj, GLYPH, banner, dots,
dots_flat, Win, sheet, grain, door_obj, split_left, open_door, plate, badge, arch_pts,
wheel (was build_wheel). Differences kept by parameters:

- skin: the Mino's looked beside a missed point in fewer places (7 against 9); where its
  first seven all miss it raised, so it builds the same with the longer search.
- GLYPH: every glyph of the three cars (no two disagree); a car adds its own with
  GLYPH.update.
- Win: its cutters' planes were numbers in cut(); they are the class's CUT (the Mino's
  smaller body: class MinoWin(Win) with its own CUT). sheet: the Mino's took mirror
  only, the same through **kw.
- door_obj and open_door: the car's DOOR list and SLIDE were globals (door, slide).
- plate: the number on it (text) and the height under which it stands off the bumper
  (low, the Mino 0.55).
- arch_pts: the car's ARCH_A, ARCH_B, ARCH_ZC, ARCH_N (arch).
- wheel: the tire's sizes were the car's globals (R, w, rim, out); the cover's slots and
  rings grow with the rim from the Mino's 0.19 m.

Left in the cars: each hull's stations, cabin, inner, tail_x and creases, the Porter's PWin
(its own cutters, a subclass of Win), the parcels and the drone.
"""
import bmesh
import carkit as K
from carkit import Geo, V3, atan2, cos, hypot, on_body, pi, rad, sin

AXIS_U = {'y': V3((1, 0, 0)), 'Y': V3((1, 0, 0)), 'x': V3((0, 1, 0)), 'X': V3((0, 1, 0)),
          'z': V3((1, 0, 0))}
GD = 0.011                          # how far the glass lies behind the skin


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
    """A rectangle's corners: middle (cu, cv), half sizes a and b."""
    return [(cu + a, cv - b), (cu + a, cv + b), (cu - a, cv + b), (cu - a, cv - b)]


def rrect(cu, cv, a, b, r, n=6):
    """A rounded rectangle's outline."""
    return rpoly(rect(cu, cv, a, b), r, n)


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


GLYPH = {           # 5 x 7 dot-matrix glyphs ('#' lit), and a few signs
    "A": (".###.", "#...#", "#...#", "#####", "#...#", "#...#", "#...#"),
    "B": ("####.", "#...#", "#...#", "####.", "#...#", "#...#", "####."),
    "C": (".###.", "#...#", "#....", "#....", "#....", "#...#", ".###."),
    "D": ("####.", "#...#", "#...#", "#...#", "#...#", "#...#", "####."),
    "E": ("#####", "#....", "#....", "####.", "#....", "#....", "#####"),
    "F": ("#####", "#....", "#....", "####.", "#....", "#....", "#...."),
    "G": (".###.", "#...#", "#....", "#.###", "#...#", "#...#", ".###."),
    "I": (".###.", "..#..", "..#..", "..#..", "..#..", "..#..", ".###."),
    "K": ("#...#", "#..#.", "#.#..", "##...", "#.#..", "#..#.", "#...#"),
    "L": ("#....", "#....", "#....", "#....", "#....", "#....", "#####"),
    "N": ("#...#", "##..#", "#.#.#", "#.#.#", "#..##", "#...#", "#...#"),
    "O": (".###.", "#...#", "#...#", "#...#", "#...#", "#...#", ".###."),
    "P": ("####.", "#...#", "#...#", "####.", "#....", "#....", "#...."),
    "Q": (".###.", "#...#", "#...#", "#...#", "#.#.#", "#..#.", ".##.#"),
    "R": ("####.", "#...#", "#...#", "####.", "#.#..", "#..#.", "#...#"),
    "S": (".####", "#....", "#....", ".###.", "....#", "....#", "####."),
    "T": ("#####", "..#..", "..#..", "..#..", "..#..", "..#..", "..#.."),
    "U": ("#...#", "#...#", "#...#", "#...#", "#...#", "#...#", ".###."),
    "V": ("#...#", "#...#", "#...#", "#...#", "#...#", ".#.#.", "..#.."),
    "X": ("#...#", "#...#", ".#.#.", "..#..", ".#.#.", "#...#", "#...#"),
    "Y": ("#...#", "#...#", ".#.#.", "..#..", "..#..", "..#..", "..#.."),
    "1": ("..#..", ".##..", "..#..", "..#..", "..#..", "..#..", ".###."),
    "2": (".###.", "#...#", "....#", "...#.", "..#..", ".#...", "#####"),
    "3": ("####.", "....#", "....#", ".###.", "....#", "....#", "####."),
    "4": ("...#.", "..##.", ".#.#.", "#..#.", "#####", "...#.", "...#."),
    "5": ("#####", "#....", "####.", "....#", "....#", "#...#", ".###."),
    "6": (".###.", "#....", "#....", "####.", "#...#", "#...#", ".###."),
    "7": ("#####", "....#", "...#.", "..#..", "..#..", "..#..", "..#.."),
    "8": (".###.", "#...#", "#...#", ".###.", "#...#", "#...#", ".###."),
    "%": ("##..#", "##.#.", "...#.", "..#..", ".#...", ".#.##", "#..##"),
    "z": ("...#.", "..##.", ".##..", "#####", "..##.", ".##..", ".#..."),      # a bolt
    "h": (".#.#.", "#####", "#####", "#####", ".###.", "..#..", "....."),      # a heart
    "p": ("#####", "#.#.#", "#####", "#...#", "#...#", "#####", "....."),      # a parcel
    ">": ("#....", ".#...", "..#..", "...#.", "..#..", ".#...", "#...."),
    "|": ("#", "#", "#", "#", "#", "#", "#"),                                  # a bar
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
    flat glass and a fat seal laid behind and round it on the skin as built. CUT holds the
    cutters' planes: for 'y' (both flanks) the cutter's inner y and its depth, for 'x' (the
    windshield) and for any other proj (the tail) its x and its depth along x."""

    CUT = dict(y=(0.55, 0.6), x=(1.45, 1.2), X=(-1.60, -1.0))

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
            y0, d = self.CUT['y']
            for sg in (1, -1):
                g.prism([(u, sg * y0, v) for u, v in self.o], (0, sg * d, 0))
        elif self.proj == 'x':
            x0, d = self.CUT['x']
            g.prism([(x0, u, v) for u, v in self.o], (d, 0, 0))
        else:
            x0, d = self.CUT['X']
            g.prism([(x0, u, v) for u, v in self.o], (d, 0, 0))

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


def door_obj(g, name, mat, glass=False, *, door, **kw):
    """A part of the cab doors, drawn on the left: the left one goes into door (the car's
    list of what slides with its door), the right one is its mirror image."""
    make = sheet if glass else (lambda gg, nm, **k: gg.obj(nm, mat, **k))
    door.append(make(g, name + ".l", **kw))
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


def open_door(body, *, door, slide):
    """The left sliding door shown open: its panels (slider, sclad) split off the body
    and every object in door moved by slide."""
    for pn in ("slider", "sclad"):
        door.append(split_left(body.parts[pn]))
    for ob in door:
        ob.location = V3(ob.location) + slide


def plate(proj, u, v, text, low=0.57):
    """The number plate on the nose ('x') or the tail ('X'), its middle at (u, v); under
    low it stands off the bumper."""
    g = Geo()
    lift = 0.0125 if v < low else 0.0
    pad(g, u, v, 0.15, 0.037, 0.008, proj, lift=lift + 0.004)
    g.obj("plate." + proj, "plate", bevel=0.001)
    g = Geo()
    text_proj(g, text, 0.042, u, v, proj, lift=lift + 0.0052, spacing=1.1)
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


def arch_pts(cx, grow=0.0, n=30, *, arch):
    """The squircle arch about an axle, front to rear over the top, as (x, z); arch is the
    car's (half width, rise, center height, exponent)."""
    A, B, ZC, N = arch
    a, b = A + grow, B + grow
    out = []
    for k in range(n + 1):
        t = pi * k / n
        c, s = cos(t), sin(t)
        e = 2.0 / N
        out.append((cx + a * (1 if c >= 0 else -1) * abs(c) ** e, ZC + b * abs(s) ** e))
    return out


NARROW = dict(grooves=(-0.11, 0.11), gw=(0.009, 0.005), gd=0.008, mod=4, shift=2,
              inset=(0.002, 0.006), seg=144)
"""A road tread for a tire under 0.185 m wide: the kit's "road" grooves (a quarter of the
width out) fall outside such a tire's crown, its profile folds back and its blocks stand
out of the tire (7 mm under the ground on a 0.165 m tire)."""


def wheel(tag, cx, side, *, R, w, rim, out, tread="road"):
    """The kit's tire (radius R, width w, rim radius rim, its outer face at y out; tread a
    kit tread or NARROW) on a steel rim under Tanager's slotted cover: six rounded slots, a
    ring, a cap of the paint's color, a valve."""
    T_R, T_W, T_RIM, T_OUT = R, w, rim, out
    K.build_wheel(tag, cx, T_R, T_W, T_RIM, T_OUT, side, rim=None, ring=None, caliper=None,
                  tread=tread)
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
