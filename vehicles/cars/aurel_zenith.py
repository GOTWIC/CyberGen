"""Aurel Zenith: a formal four-seat hover grand tourer, the third Aurel (both names made
up), built on vehicles/carkit.py.

Run (always through the wrapper, one Blender job at a time on this machine):
    vehicles/blender.sh vehicles/cars/aurel_zenith.py --out DIR --preview
    vehicles/blender.sh vehicles/cars/aurel_zenith.py --out DIR --sheet

The Prelate's and the Regent's sibling with nothing under it. The same monolith: slab nose
and tail, the lozenge of light slots folded over the nose's top edge, the razor shoulder,
blades at the corners, the folded dark canopy in a polished frame. But no wheel and no arch:
each flank is one surface from blade to blade. The fluted plinth is a piece of its own here,
stepped back all round under the hull, and it is the lift system: light stands between its
flutes, a skirt of light runs round its foot, and under it lie four pleated discs (the
family's wheel disc laid flat, light in every pleat), a lozenge of light slots along the
belly and four slim landing feet folded into their slots. The tail is long and falls away.
Eight character lines over twelve stations; every detail hangs on the body as built.
"""
import os
import sys
from math import atan2, tan

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import bpy                                                          # noqa: E402
import carkit as K                                                  # noqa: E402
from carkit import (Geo, Matrix, V3, cos, on_body, pi, rad, ribbon, sin,       # noqa: E402
                    text_flat, text_on_body)

# ---------------------------------------------------------------------------------------
# dimensions
# ---------------------------------------------------------------------------------------
NOSE_X, TAIL_X = 2.70, -2.70        # the slabs at shoulder height
Z_SH, Z_SHT = 1.065, 0.905          # the shoulder at the nose and at the tail: it falls aft
Z_SILL = 0.50                       # the hull's lower edge
Z_P0 = 0.30                         # the plinth's foot: the ride height
Z_FL0, Z_FL1 = 0.320, 0.486         # the flutes' foot and head
Z_STRIP = 0.5075                    # the bright strip on the sill line
REC = 0.065                         # the plinth stands back this far under the hull
PITCH = 0.022                       # the plinth's flutes
W = 0.045                           # wider than the Prelate on each side
PAINT = (0.0075, 0.0070, 0.0068)    # show color: obsidian lacquer
LIFT = (1.0, 0.58, 0.19)            # the lift system's light
EMIT = ((1.70, 0.49), (-1.70, 0.49), (1.70, -0.49), (-1.70, -0.49))    # the four discs


def nose_x(z):
    """The nose slab leans forward: its top is ahead of its foot."""
    return NOSE_X - (Z_SH - z) * 0.07


def tail_x(z):
    """The tail slab leans back the same way: both ends overhang the plinth."""
    return TAIL_X + (Z_SHT - z) * 0.06


# ---------------------------------------------------------------------------------------
# body: stations and character lines
# ---------------------------------------------------------------------------------------
LINES = "CHGSULFB"
#        C centerline top, H hood flow line / A-pillar / roof edge, G hood edge / glass base,
#        S the razor shoulder, U widest line, L the sill line (the hull's lower edge),
#        F under the hull, B the hull's floor centerline
ORDER = ["N0", "N1", "A1", "A2", "W0", "W1", "RM", "CP", "RR", "RG", "DK", "T0"]
PT = {}


def low(x, sz, w=0.0, zu=0.77):
    """The five lower lines of a station: shoulder, widest, sill, under, floor."""
    w += W
    return [(x, .95 + w, sz), (x, .98 + w, zu), (x, .97 + w, Z_SILL), (x, .90, Z_SILL),
            (x, 0, Z_SILL)]


def stations():
    def end(fx, zs, ys):
        return [(fx(z), y, z) for z, y in zip(zs, ys)]
    T = {
        "N0": end(nose_x, (1.120, 1.117, 1.100, Z_SH, .77, Z_SILL, Z_SILL, Z_SILL),
                  (0, .625, .885, .970, 1.000, .990, .90, 0)),
        "N1": [(2.40, 0, 1.130), (2.40, .665, 1.127), (2.40, .910, 1.107)] + low(2.40, 1.067, -.003),
        "A1": [(1.90, 0, 1.140), (1.90, .725, 1.137), (1.90, .920, 1.112)] + low(1.90, 1.069),
        "A2": [(1.45, 0, 1.150), (1.45, .785, 1.145), (1.45, .925, 1.115)] + low(1.45, 1.070),
        "W0": [(1.02, 0, 1.160), (.91, .845, 1.130), (.89, .923, 1.113)] + low(.94, 1.070),
        "W1": [(.52, 0, 1.488), (.46, .785, 1.456), (.48, .930, 1.110)] + low(.48, 1.069),
        "RM": [(-.60, 0, 1.500), (-.60, .790, 1.466), (-.60, .930, 1.104)] + low(-.60, 1.063),
        # the pillar leans with the rear glass: a band of one width from roof to shoulder
        "CP": [(-1.08, 0, 1.488), (-1.08, .785, 1.454), (-1.47, .930, 1.090)]
              + low(-1.20, 1.050),
        "RR": [(-1.40, 0, 1.455), (-1.37, .780, 1.424), (-1.66, .930, 1.076)]
              + low(-1.56, 1.036, zu=.760),
        "RG": [(-1.92, 0, 1.090), (-1.85, .845, 1.076), (-1.83, .920, 1.054)]
              + low(-1.86, 1.012, zu=.750),
        "DK": [(-2.35, 0, 1.035), (-2.35, .705, 1.030), (-2.35, .905, .998)]
              + low(-2.35, .958, -.006, zu=.725),
        "T0": end(tail_x, (.970, .967, .945, Z_SHT, .70, Z_SILL, Z_SILL, Z_SILL),
                  (0, .645, .875, .960, .990, .980, .90, 0)),
    }
    S = K.fill([T[k] for k in ORDER])
    PT.update(K.table(ORDER, LINES, S))
    return S


PMAT = dict(hood="paint", fender="paint", door="paint", quarter="paint", deck="paint",
            canopy="glass", glass_side="glass",
            trim_ws="gloss_black", trim_b="bright", floor="underbody")


def panel_of(i, j):
    if j >= 5:
        return "floor"
    if j == 0:
        return "hood" if i <= 3 else "deck" if i >= 9 else "canopy"
    if j == 1:
        return ("hood", "hood", "hood", "hood", "glass_side", "glass_side", "glass_side",
                "quarter", "quarter", "deck", "deck")[i]
    if j == 2 and i <= 3:
        return "hood"               # a clamshell: its cut hides in the shoulder crease
    if j == 2 and i >= 9:
        return "deck"
    # no wheel, no arch: a fender, one long door and a quarter are all a flank has
    return "fender" if i <= 3 else "door" if i <= 5 else "quarter"


def line_crease(i, j):
    """Crease of the edge along line j from station i to i + 1."""
    if j == 1:
        return 1.0 if 4 <= i <= 8 else 0.0
    if j in (2, 3, 5):              # glass base and chamfer, the razor, the sill line
        return 1.0
    return 0.0


def station_crease(i, j):
    """Crease of the edge on station i between lines j and j + 1."""
    if i in (0, 11):
        return 1.0
    if i in (4, 9):
        return 1.0 if j <= 1 else 0.0
    if i in (5, 8):
        return 1.0 if j == 0 else 0.0
    if i == 7:
        return 1.0 if j == 1 else 0.0
    return 0.0


def build_hull():
    K.build_body(
        stations(), panel_of, PMAT, line_crease, station_crease,
        front=dict(kind="flat", panel="fender"), rear=dict(kind="flat", panel="quarter"),
        glass=[("canopy", 0.022, "trim_ws"), ("glass_side", 0.014, "trim_b")], subdiv=3)


# ---------------------------------------------------------------------------------------
# the slabs: a frame on each end, the lozenge of light, the blades
# ---------------------------------------------------------------------------------------
class Slab:
    """Coordinates on an end slab: at(y, z, d) is the point at height z, d off the slab."""

    def __init__(self, proj, zc):
        self.o, self.n = on_body(0.0, zc, proj)
        self.ey = V3((0, 1, 0))
        self.eu = self.n.cross(self.ey).normalized()
        if self.eu.z < 0:
            self.eu = -self.eu
        self.rot = Matrix((self.n, self.ey, self.eu)).transposed()
        # a reader's right hand when facing the slab
        self.right = V3((0, 1, 0)) if proj == 'x' else V3((0, -1, 0))

    def at(self, y, z, d=0.0):
        return self.o + self.ey * y + self.eu * ((z - self.o.z) / self.eu.z) + self.n * d

    def box(self, g, y, z, d, size):
        """size: (depth, width, height); d is the middle of its depth off the slab."""
        g.box(self.at(y, z, d), size, rot=self.rot)


def lozenge(sl, tag, kmax, z0, led, sx, lmax, pitch=0.030, w=0.008, ztop=1.30):
    """The Aurel grille: no opening, only slots of light let into the slab, in a field of
    bright hairline flutes. They hang from the slab's top edge, the middle one longest, and go on
    over the edge along the hood (the deck) the same way: the crest's lozenge, folded over
    the edge."""
    proj = 'x' if sx > 0 else 'X'
    gl, gd, gv = Geo(), Geo(), Geo()

    def edge(y):                            # the slab's top edge over a slot
        z = ztop
        while z > z0:
            p, _ = on_body(y, z, proj)
            if p is not None and abs(p.x - sl.at(y, z).x) < 0.02:
                break
            z -= 0.002
        return z

    def slot(y, lit):
        f = 1 - abs(y / pitch) / (kmax + 1)
        zt = edge(y)
        z1 = zt - 0.016
        zb = z1 - (z1 - z0) * f
        xs = sl.at(y, zt).x - sx * 0.016
        xe = xs - sx * lmax * f
        if lit:
            sl.box(gd, y, (zb + z1) / 2, 0.001, (0.002, w + 0.007, z1 - zb + 0.007))
            sl.box(gl, y, (zb + z1) / 2, 0.002, (0.004, w, z1 - zb))
            ribbon(gd, [(xs + sx * 0.002, y), (xe - sx * 0.002, y)], 'z', w + 0.004, lift=0.0006)
            ribbon(gl, [(xs, y), (xe, y)], 'z', w, lift=0.0014)
        else:
            sl.box(gv, y, (zb + z1) / 2, 0.0006, (0.0012, 0.0025, z1 - zb))
            ribbon(gv, [(xs, y), (xe, y)], 'z', 0.0025, lift=0.0006)

    for k in range(-kmax, kmax + 1):
        slot(k * pitch, True)
        if k < kmax:
            slot((k + 1 / 3) * pitch, False)
            slot((k + 2 / 3) * pitch, False)
    gd.obj("lozenge.slots." + tag, "gloss_black")
    gv.obj("lozenge.flutes." + tag, "bright")
    gl.obj("lozenge.light." + tag, led)


def blade(sl, tag, y, z0, z1, led):
    """A slim vertical light at a corner of a slab, in a dark slot with a bright edge."""
    zc, H = (z0 + z1) / 2, z1 - z0
    g = Geo()
    sl.box(g, y, zc, 0.004, (0.010, 0.040, H + 0.03))
    g.obj("blade.house." + tag, "gloss_black", bevel=0.002, mirror=True)
    g = Geo()
    sl.box(g, y, zc, 0.009, (0.006, 0.016, H))
    g.obj("blade.light." + tag, led, mirror=True)
    g = Geo()
    for dy in (-0.022, 0.022):
        sl.box(g, y + dy, zc, 0.006, (0.014, 0.004, H + 0.034))
    g.obj("blade.edge." + tag, "bright", mirror=True)


def crest(gb, gd, o, right, up, s):
    """Aurel's crest: a tall lozenge, a dark lozenge within, a bright bar down its middle."""
    o, right, up = V3(o), V3(right).normalized(), V3(up).normalized()
    out = right.cross(up).normalized()

    def loz(k, d0, d1, g):
        poly = [o + up * (0.82 * s * k) + out * d0, o + right * (0.5 * s * k) + out * d0,
                o - up * (0.82 * s * k) + out * d0, o - right * (0.5 * s * k) + out * d0]
        g.prism(poly, out * (d1 - d0))
    loz(1.0, 0.0, 0.003, gb)
    loz(0.72, 0.003, 0.0042, gd)
    gb.prism([o + up * (0.5 * s) + right * (0.035 * s) + out * 0.004,
              o + up * (0.5 * s) - right * (0.035 * s) + out * 0.004,
              o - up * (0.5 * s) - right * (0.035 * s) + out * 0.004,
              o - up * (0.5 * s) + right * (0.035 * s) + out * 0.004], out * 0.0015)


def build_slabs():
    # ---- nose: the lozenge folds a long way over the hood
    sl = Slab('x', 0.77)
    lozenge(sl, "f", 25, 0.560, "led_front", 1, 0.60)
    blade(sl, "f", 0.923, 0.560, 1.028, "led_front")
    # ---- tail: the same lozenge, smaller and red, its fold long on the long deck
    st = Slab('X', 0.70)
    lozenge(st, "r", 19, 0.625, "led_rear", -1, 0.46)
    blade(st, "r", 0.913, 0.560, 0.870, "led_rear")
    # ---- the bright strip on the sill line across both ends
    for s, tag, hw in ((sl, "f", 0.950), (st, "r", 0.940)):
        g = Geo()
        s.box(g, 0, Z_STRIP, 0.005, (0.014, 2 * hw + 0.07, 0.013))
        g.obj("sill.strip." + tag, "bright", bevel=0.0015)
    # ---- the crest behind the lozenge's point, the wordmark and the model on the tail
    gb, gd = Geo(), Geo()
    p, n = on_body(1.975, 0.0, 'z')
    crest(gb, gd, p + n * 0.0005, (0, 1, 0), (1, 0, 0), 0.046)
    gb.obj("crest", "bright", bevel=0.0006)
    gd.obj("crest.inlay", "gloss_black")
    g = Geo()
    text_flat(g, "A U R E L", 0.046, st.at(0.60, 0.672, 0.0015), st.right, st.eu, spacing=1.2)
    text_flat(g, "ZENITH", 0.027, st.at(-0.60, 0.672, 0.0015), st.right, st.eu, spacing=1.5)
    g.obj("wordmark", "bright")
    # ---- plate
    g = Geo()
    st.box(g, 0, 0.572, 0.004, (0.008, 0.30, 0.080))
    g.obj("plate", "gloss_black", bevel=0.002)
    g = Geo()
    text_flat(g, "AU 1-309", 0.043, st.at(0, 0.572, 0.0088), st.right, st.eu, spacing=1.15)
    g.obj("plate.glyphs", "decal")


# ---------------------------------------------------------------------------------------
# the plinth: a piece of its own, stepped back all round under the hull. It is the lift
# system: light between its flutes, a skirt of light round its foot
# ---------------------------------------------------------------------------------------
def outline(d, r=0.10):
    """The plinth's plan: the hull's sill line taken in by d, its four corners rounded.
    Counterclockwise seen from above, as (x, y) pairs."""
    left = [(PT[s]["L"].x, PT[s]["L"].y - d) for s in ORDER]
    left[0] = (left[0][0] - d, left[0][1])
    left[-1] = (left[-1][0] + d, left[-1][1])
    poly = left + [(x, -y) for x, y in reversed(left)]
    out = []
    n = len(poly)
    for i in range(n):
        p, a, b = V3((*poly[i], 0)), V3((*poly[i - 1], 0)), V3((*poly[(i + 1) % n], 0))
        d1, d2 = (p - a).normalized(), (b - p).normalized()
        th = atan2(d1.x * d2.y - d1.y * d2.x, d1.dot(d2))
        if abs(th) < rad(20):
            out.append((p.x, p.y))
            continue
        t = r * tan(th / 2)
        c = p - d1 * t + V3((-d1.y, d1.x, 0)) * r
        v = p - d1 * t - c
        for k in range(13):
            f = th * k / 12
            out.append((c.x + v.x * cos(f) - v.y * sin(f), c.y + v.x * sin(f) + v.y * cos(f)))
    return out


def walk(path, step):
    """Points every step along a closed plan path (the step fitted to its length): each with
    its tangent and its outward normal."""
    pts = [V3((x, y, 0)) for x, y in path]
    segs = list(zip(pts, pts[1:] + pts[:1]))
    total = sum((b - a).length for a, b in segs)
    n = int(round(total / step))
    out, k, s0 = [], 0, 0.0
    for a, b in segs:
        ln = (b - a).length
        t = (b - a).normalized()
        while k < n and (k + 0.5) * total / n <= s0 + ln:
            out.append((a + t * ((k + 0.5) * total / n - s0), t, V3((t.y, -t.x, 0))))
            k += 1
        s0 += ln
    return out


def build_plinth():
    P = outline(REC)
    g = Geo()
    g.prism([(x, y, Z_P0) for x, y in P], (0, 0, Z_SILL + 0.012 - Z_P0))
    g.obj("plinth", "flute", bevel=0.003)
    # ---- light stands in the band behind the flutes
    zc, hh = (Z_FL0 + Z_FL1) / 2, (Z_FL1 - Z_FL0) / 2
    g = Geo()
    g.sweep([(x, y, zc) for x, y in P], [(-0.002, -hh), (0.0015, -hh), (0.0015, hh), (-0.002, hh)],
            up=(0, 0, 1), closed=True)
    g.obj("plinth.light", "lift_band")
    # ---- the flutes, round all four sides and the corners without a break
    g = Geo()
    a, b, h = 0.0078, 0.0035, 0.0075
    for p, t, n in walk(P, PITCH):
        q = p + n * 0.0005
        ring = [q - t * a, q + t * a, q + t * b + n * h, q - t * b + n * h]
        g.hexa([V3((v.x, v.y, Z_FL0)) for v in ring] + [V3((v.x, v.y, Z_FL1)) for v in ring])
    g.obj("plinth.flutes", "flute")
    # ---- a bright hairline at the plinth's foot and head
    g = Geo()
    for z in (Z_P0 + 0.008, Z_FL1 + 0.008):
        g.sweep([(x, y, z) for x, y in P],
                [(-0.001, -0.004), (0.0045, -0.004), (0.0045, 0.004), (-0.001, 0.004)],
                up=(0, 0, 1), closed=True)
    g.obj("plinth.rails", "bright", bevel=0.001)
    # ---- the skirt: a line of light under the foot, all round
    g = Geo()
    g.sweep([(x, y, Z_P0 - 0.002) for x, y in outline(REC + 0.030, 0.085)],
            [(-0.013, -0.003), (0.013, -0.003), (0.013, 0.003), (-0.013, 0.003)],
            up=(0, 0, 1), closed=True)
    g.obj("plinth.skirt", "lift_skirt")
    # ---- the bright strip on the hull's lower edge, along the flanks
    gs = Geo()
    x0, x1 = nose_x(Z_STRIP) - 0.03, tail_x(Z_STRIP) + 0.03
    path = []
    m = int((x0 - x1) / 0.08)
    for k in range(m + 1):
        x = x0 + (x1 - x0) * k / m
        p, _ = on_body(x, Z_STRIP, 'y')
        if p is not None and p.y > 0.9:
            path.append(V3((x, p.y + 0.003, Z_STRIP)))
    gs.sweep(path, [(-0.007, -0.0065), (0.007, -0.0065), (0.007, 0.0065), (-0.007, 0.0065)],
             up=(0, 0, 1))
    gs.obj("sill.strip", "bright", bevel=0.0015, mirror=True)


# ---------------------------------------------------------------------------------------
# under the plinth: four pleated discs, the belly's lozenge of light, the landing feet
# ---------------------------------------------------------------------------------------
def build_emitters():
    """Where the wheels would be: the family's pleated disc laid flat, light in every pleat,
    inside a polished ring, a dark cap with the crest."""
    N = 96
    M = 2 * N
    r0, r1 = 0.095, 0.345
    zo, zi = Z_P0 - 0.016, Z_P0 - 0.008           # a shallow dish, deepest at the hub
    gp, gl, gr, gc, gb, gd = Geo(), Geo(), Geo(), Geo(), Geo(), Geo()
    for cx, cy in EMIT:
        vs, fs = [], []
        for k in range(M):
            a = 2 * pi * k / M
            d = 0.0022 if k % 2 else -0.0022
            for r, z in ((r1, zo + d), (r0, zi + d * 0.45), (r0, zi + 0.008), (r1, zo + 0.016)):
                vs.append((cx + r * cos(a), cy + r * sin(a), z))
        for k in range(M):
            k2 = (k + 1) % M
            for j in range(4):
                j2 = (j + 1) % 4
                fs.append((4 * k + j, 4 * k + j2, 4 * k2 + j2, 4 * k2 + j))
        gp.add(vs, fs)
        # light in the pleats: a sliver along every valley
        da = 0.27 * 2 * pi / M
        for k in range(1, M, 2):
            a = 2 * pi * k / M
            q = []
            for r, z in ((r0 + 0.012, zi + 0.0003), (r1 - 0.010, zo + 0.0009)):
                q += [(cx + r * cos(a - da), cy + r * sin(a - da), z),
                      (cx + r * cos(a + da), cy + r * sin(a + da), z)]
            gl.add(q, [(0, 1, 3, 2)])
        xf = Matrix.Translation((cx, cy, 0)) @ Matrix.Rotation(pi / 2, 4, 'X')
        gr.lathe([(zo + 0.016, r1 - 0.001), (zo - 0.005, r1 - 0.001), (zo - 0.010, r1 + 0.005),
                  (zo - 0.010, r1 + 0.036), (zo + 0.016, r1 + 0.036)], 96, xf=xf)
        gr.lathe([(zi + 0.008, r0), (zi - 0.012, r0), (zi - 0.012, r0 + 0.010),
                  (zi + 0.008, r0 + 0.010)], 64, xf=xf)
        gl.lathe([(Z_P0 + 0.001, r1 + 0.044), (Z_P0 - 0.004, r1 + 0.044),
                  (Z_P0 - 0.004, r1 + 0.056), (Z_P0 + 0.001, r1 + 0.056)], 96, xf=xf)
        gc.lathe([(zi + 0.008, 0.004), (zi + 0.008, r0), (zi - 0.010, r0),
                  (zi - 0.016, r0 - 0.016), (zi - 0.016, 0.004)], 64, xf=xf)
        crest(gb, gd, (cx, cy, zi - 0.0162), (0, 1, 0), (1, 0, 0), 0.062)
    gp.obj("emitter.disc", "platinum")
    gl.obj("emitter.light", "lift")
    gr.obj("emitter.ring", "bright", bevel=0.0015)
    gc.obj("emitter.cap", "gloss_black", sharp=30)
    gb.obj("emitter.crest", "bright")
    gd.obj("emitter.crest.in", "gloss_black")


def build_belly():
    # ---- the lozenge again, laid along the keel: slots of light, the middle one longest
    gd, gl = Geo(), Geo()
    KB = 8
    for k in range(-KB, KB + 1):
        y = k * 0.034
        half = 1.24 * (1 - abs(k) / (KB + 1))
        gd.box((0, y, Z_P0 - 0.0015), (2 * half + 0.014, 0.021, 0.004))
        gl.box((0, y, Z_P0 - 0.0035), (2 * half, 0.009, 0.004))
    gd.obj("belly.slots", "gloss_black")
    gl.obj("belly.light", "lift")
    # ---- landing feet: four slim blades folded flat into slots, a lozenge pad on each
    gv, gf, gh = Geo(), Geo(), Geo()
    y = 0.775
    for xr, xe in ((0.20, 0.86), (-0.20, -0.86)):       # hinge, pad
        xm = (xr + xe) / 2
        sg = 1 if xe > xr else -1
        gv.box((xm + sg * 0.04, y, Z_P0 - 0.0008), (abs(xe - xr) + 0.30, 0.084, 0.003))
        gf.box((xm, y, Z_P0 - 0.010), (abs(xe - xr), 0.020, 0.013))
        gf.prism([(xe + 0.10, y, Z_P0 - 0.004), (xe, y + 0.034, Z_P0 - 0.004),
                  (xe - 0.10, y, Z_P0 - 0.004), (xe, y - 0.034, Z_P0 - 0.004)], (0, 0, -0.013))
        gh.tube((xr, y - 0.034, Z_P0 - 0.011), (xr, y + 0.034, Z_P0 - 0.011), 0.011, 16)
        gh.box((xm - sg * 0.10, y, Z_P0 - 0.006), (0.05, 0.036, 0.008))     # the actuator's eye
    gv.obj("foot.slot", "void", mirror=True)
    gf.obj("foot", "bright", bevel=0.002, mirror=True)
    gh.obj("foot.hinge", "flute", bevel=0.001, mirror=True)
    # ---- service plates between the discs, a row of fasteners round each
    g, gs = Geo(), Geo()
    for sx in (1, -1):
        g.box((sx * 1.72, 0, Z_P0 - 0.0015), (0.46, 0.13, 0.003))
        for dx in (-0.20, 0.0, 0.20):
            for dy in (-0.05, 0.05):
                gs.lathe([(Z_P0 - 0.005, 0.0), (Z_P0 - 0.005, 0.006), (Z_P0, 0.006)], 12,
                         xf=Matrix.Translation((sx * 1.72 + dx, dy, 0)) @ Matrix.Rotation(pi / 2, 4, 'X'),
                         closed=False)
    g.obj("belly.plate", "underbody", bevel=0.001)
    gs.obj("belly.screws", "bright")


# ---------------------------------------------------------------------------------------
# trims, small details
# ---------------------------------------------------------------------------------------
def build_details():
    # ---- the spear: a bright hairline from the crest down the hood
    g = Geo()
    ribbon(g, [(1.920, 0.0), (0.97, 0.0)], 'z', 0.010, lift=0.0012)
    g.obj("spear", "bright")
    # ---- door pull: a bright bar in a dark slot, under the shoulder
    g = Geo()
    ribbon(g, [(-0.29, 0.972), (-0.51, 0.972)], 'y', 0.026)
    g.obj("pull.slot", "gloss_black", mirror=True)
    g = Geo()
    a, n = on_body(-0.30, 0.972, 'y')
    b, _ = on_body(-0.50, 0.972, 'y')
    g.sweep([a + n * 0.005, b + n * 0.005],
            [(-0.004, -0.005), (0.004, -0.005), (0.004, 0.005), (-0.004, 0.005)], up=(0, 0, 1))
    g.obj("pull", "bright", bevel=0.0015, mirror=True)
    # ---- mirrors: a camera blade on a bright stalk at the foot of the A-pillar
    dx, dy, dz = 0.64, W, 0.172
    g = Geo()
    g.sweep([(0.18 + dx, 0.905 + dy, 0.925 + dz), (0.165 + dx, 0.990 + dy, 0.955 + dz)],
            [(-0.022, -0.004), (0.022, -0.004), (0.022, 0.004), (-0.022, 0.004)], up=(0, 0, 1))
    g.obj("mirror.stalk", "bright", bevel=0.0015, mirror=True)
    g = Geo()
    g.hexa([(x + dx, y + dy, z + dz) for x, y, z in (
        (0.225, 0.972, 0.938), (0.225, 1.000, 0.938), (0.085, 1.008, 0.932),
        (0.085, 0.966, 0.932), (0.215, 0.974, 0.985), (0.215, 0.998, 0.985),
        (0.085, 1.004, 0.992), (0.085, 0.968, 0.992))])
    g.obj("mirror.pod", "paint", bevel=0.004, mirror=True)
    g = Geo()
    g.box((0.0835 + dx, 0.986 + dy, 0.962 + dz), (0.004, 0.030, 0.046))
    g.obj("mirror.lens", "gloss_black", mirror=True)
    # ---- crest on the pillar, charge flap, model name low on the fender
    gb, gd = Geo(), Geo()
    p, n = on_body(-1.395, 1.27, 'y')
    right = V3((-1, 0, 0))
    up = n.cross(right).normalized()
    if up.z < 0:
        up = -up
    crest(gb, gd, p + n * 0.0005, right, up, 0.034)
    gb.obj("crest.pillar", "bright", bevel=0.0006, mirror=True)
    gd.obj("crest.pillar.inlay", "gloss_black", mirror=True)
    g = Geo()
    loz = [(-2.36, 0.885), (-2.325, 0.83), (-2.36, 0.775), (-2.395, 0.83)]
    ribbon(g, loz, 'y', 0.003, closed=True)
    g.obj("flap", "void")
    g = Geo()
    for side in (1, -1):
        text_on_body(g, "ZENITH", 0.024, 1.80, 0.560, side, spacing=1.5)
    g.obj("lettering", "bright")
    # ---- the blades turn the corners: a hairline of light on each flank beside its slab
    for x, z0, z1, led, tag in ((NOSE_X - 0.088, 0.575, 1.012, "led_front", "f"),
                                (TAIL_X + 0.082, 0.575, 0.853, "led_rear", "r")):
        gd, gl = Geo(), Geo()
        ribbon(gd, [(x, z0 - 0.006), (x, z1 + 0.006)], 'y', 0.016, lift=0.0006)
        ribbon(gl, [(x, z0), (x, z1)], 'y', 0.006, lift=0.0014)
        gd.obj("blade.side.slot." + tag, "gloss_black", mirror=True)
        gl.obj("blade.side." + tag, led, mirror=True)
    # ---- parking sensors low on the slabs, front and rear
    g = Geo()
    for proj in ('x', 'X'):
        for y in (-0.72, -0.30, 0.30, 0.72):
            p, n = on_body(y, 0.522, proj)
            K.stud(g, p, n, [(0.0, 0.001), (0.0, 0.011), (0.002, 0.011), (0.002, 0.001)], 16)
    g.obj("sensors", "gloss_black")
    # ---- a slim stop light under the rear glass's top edge
    g = Geo()
    p, n = on_body(-1.47, 0.0, 'z')
    g.box(p + n * 0.004, (0.010, 0.44, 0.006), rot=Matrix.Rotation(rad(-34), 3, 'Y'))
    g.obj("led.stop", "led_rear")
    # ---- wipers parked under the hood's trailing edge: only their dark slot shows
    g = Geo()
    ribbon(g, [(0.945, -0.66), (0.965, 0.0), (0.945, 0.66)], 'z', 0.016)
    g.obj("cowl.slot", "void")


# ---------------------------------------------------------------------------------------
# interior: four seats
# ---------------------------------------------------------------------------------------
def build_interior():
    hy = 0.905
    g = Geo()
    g.box((-0.20, 0, 0.515), (2.50, 2 * hy, 0.03))                      # floor
    g.prism([(1.05, -hy, 0.50), (1.05, -hy, 1.078), (0.81, -hy, 1.098),
             (0.64, -hy, 1.03), (0.66, -hy, 0.79), (0.81, -hy, 0.66),
             (0.81, -hy, 0.50)], (0, 2 * hy, 0))                        # firewall and dash
    g.box((-0.12, 0, 0.64), (1.80, 0.20, 0.28))                         # console
    g.box((-1.56, 0, 1.055), (0.56, 2 * hy - 0.04, 0.03))               # shelf under the glass
    g.box((-1.32, 0, 0.78), (0.04, 2 * hy - 0.04, 0.56))                # rear bulkhead
    for s in (1, -1):
        g.box((-0.18, s * (hy + 0.012), 0.78), (2.30, 0.04, 0.56))      # door and side cards
    g.obj("interior.tub", "interior", bevel=0.006)
    g = Geo()
    t1 = Matrix.Rotation(rad(-19), 3, 'Y')
    for x in (0.38, -0.60):                                             # two rows alike
        for y in (0.42, -0.42):
            g.box((x, y, 0.575), (0.52, 0.50, 0.13))
            g.box((x - 0.34, y, 0.905), (0.12, 0.48, 0.60), rot=t1)
            g.box((x - 0.455, y, 1.265), (0.075, 0.24, 0.15), rot=t1)
            for s in (-1, 1):
                g.box((x, y + s * 0.245, 0.605), (0.48, 0.05, 0.16))
                g.box((x - 0.325, y + s * 0.235, 0.865), (0.15, 0.05, 0.48), rot=t1)
    g.obj("interior.seats", "seat", bevel=0.014, segs=3)
    g = Geo()
    wheel = (Matrix.Translation((0.54, 0.42, 0.975)) @ Matrix.Rotation(rad(-68), 4, 'Y')
             @ Matrix.Rotation(pi / 2, 4, 'X'))
    g.lathe([(-0.012, 0.165), (0.0, 0.177), (0.012, 0.165), (0.0, 0.153)], 28, xf=wheel)
    g.box((0.54, 0.42, 0.975), (0.03, 0.32, 0.04), rot=Matrix.Rotation(rad(-22), 3, 'Y'))
    g.box((0.62, 0.42, 0.945), (0.17, 0.05, 0.05))
    g.obj("interior.wheel", "interior", sharp=40)
    g = Geo()
    scr = Matrix.Rotation(rad(-14), 3, 'Y')
    g.box((0.635, 0.0, 1.008), (0.008, 1.50, 0.060), rot=scr)           # pillar to pillar
    g.box((0.49, 0.0, 0.783), (0.26, 0.15, 0.006))                      # on the console
    g.box((-0.52, 0.0, 0.783), (0.20, 0.13, 0.006))                     # and for the rear row
    g.obj("interior.screens", "screen")
    g = Geo()
    for s in (1, -1):
        g.box((-0.18, s * (hy - 0.012), 1.00), (2.20, 0.006, 0.010))    # a bright line on the cards
    g.box((-0.12, 0, 0.783), (1.70, 0.012, 0.006))
    g.obj("interior.trim", "bright")
    g = Geo()
    for s in (1, -1):
        g.box((-0.18, s * (hy - 0.011), 0.93), (2.20, 0.004, 0.008))    # a line of light under it
    g.obj("interior.light", "cabin_led")


# ---------------------------------------------------------------------------------------
# the build
# ---------------------------------------------------------------------------------------
_studio = K.build_studio
UNLIT = dict(top=("body.canopy", "body.glass_side"), key=("body.glass_side",),
             rim=("body.canopy",),
             strip=("body.glass_side",), strip2=("body.glass_side",))


def build_studio():
    """The kit's studio with some links changed, as on the Regent. The top soft box does not
    light the canopy: from the hero's side it was mirrored whole in the near half of the
    windshield, a white pane over the cabin. The side glass leans in and mirrored the top
    box, the key and the strips: it takes none of them. The paint and everything else still
    take every light."""
    _studio()
    for name in ("strip", "strip2"):        # black lacquer: the strips less bright in the flanks
        light = K.STUDIO.objects.get(name)
        if light is not None:
            light.data.energy *= 0.45
    for name, skip in UNLIT.items():
        light = K.STUDIO.objects.get(name)
        if light is None:
            continue
        rec = bpy.data.collections.new(name + ".receivers")
        for ob in list(K.CAR.objects) + list(K.STUDIO.objects):
            if ob.type == 'MESH' and ob.name not in skip:
                rec.objects.link(ob)
        try:
            light.light_linking.receiver_collection = rec
        except Exception as e:
            print("light linking:", e)


K.build_studio = build_studio

SERIFS = ("/System/Library/Fonts/Supplemental/Didot.ttc",
          "/System/Library/Fonts/Supplemental/Bodoni 72.ttc",
          "/System/Library/Fonts/Supplemental/Times New Roman Bold.ttf",
          "C:/Windows/Fonts/timesbd.ttf")

K.VIEWS["hero"].update(dir=(1.0, 0.86, 0.25))
K.VIEWS.update(
    nose=dict(dir=(1.0, 0.42, 0.10), lens=85, target=(2.5, 0.3, 0.70), dist=3.8),
    tail=dict(dir=(-1.0, -0.42, 0.14), lens=85, target=(-2.5, -0.3, 0.72), dist=3.8),
    skirt=dict(dir=(0.5, 1.0, 0.04), lens=85, target=(1.9, 0.9, 0.45), dist=2.8),
    belly=dict(dir=(0.25, 0.5, -1.0), lens=60, target=(0.9, 0.3, 0.3), dist=3.2, no_floor=True),
)


def main():
    K.materials(paint=PAINT, paint_finish=(0.10, 0.08, 1.0), dust_amount=0.04,
                dust_z=(0.25, 0.70), glass=(0.20, 0.165, 0.12), led_front=(1.0, 0.86, 0.62),
                led_rear=(1.0, 0.02, 0.012), seat=(0.36, 0.17, 0.07),
                interior=(0.030, 0.024, 0.020), screen=(1.0, 0.72, 0.38),
                decal=(0.75, 0.75, 0.72))
    # black lacquer under a bright studio: a thinner coat mirrors the floor and the wall at
    # about half the strength, so the slabs and the hood read black, not grey
    lac = next(n for n in K.MAT["paint"].node_tree.nodes if n.type == 'BSDF_PRINCIPLED')
    lac.inputs["Coat IOR"].default_value = 1.36
    lac.inputs["Specular IOR Level"].default_value = 0.35
    K.emit("led_front", (1.0, 0.80, 0.50), 16.0)            # dimmer than the kit's: the slots
    K.emit("led_rear", (1.0, 0.02, 0.012), 12.0)            # keep their color under the bloom
    K.emit("lift", LIFT, 13.0)                              # pleats, belly slots, disc rings
    K.emit("lift_band", LIFT, 7.5)                         # between the plinth's flutes
    K.emit("lift_skirt", LIFT, 220.0)                       # the line under the foot
    K.emit("cabin_led", (1.0, 0.80, 0.55), 30.0)
    K.pbr("bright", (0.88, 0.88, 0.86), 1.0, 0.06)          # polished trim
    K.pbr("flute", (0.085, 0.085, 0.09), 1.0, 0.28)         # dark machined metal
    K.pbr("platinum", (0.36, 0.36, 0.375), 1.0, 0.24)       # the discs
    for p in SERIFS:                                        # a serif for the wordmark
        if os.path.exists(p):
            try:
                K._FONT[0] = bpy.data.fonts.load(p)
                break
            except Exception as e:
                print("font:", p, e)
    build_hull()
    K.log("hull")
    build_slabs()
    build_plinth()
    build_emitters()
    build_belly()
    K.log("lift")
    build_details()
    build_interior()
    K.log("details")
    K.shoot(extra=dict(view="under", size=(1000, 400)))


main()
