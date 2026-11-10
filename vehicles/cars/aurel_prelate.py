"""Aurel Prelate: a formal 2 + 2 coupe, the first Aurel (both names made up), built on
vehicles/carkit.py.

Run (always through the wrapper, one Blender job at a time on this machine):
    vehicles/blender.sh vehicles/cars/aurel_prelate.py --out DIR --preview
    vehicles/blender.sh vehicles/cars/aurel_prelate.py --out DIR --sheet

A monolith on a fluted plinth: a slab nose and a slab tail, one razor shoulder crease from
blade light to blade light, a very long hood, an upright glass house set far back, a short
deck, the glass one folded canopy with a single leaning pillar in body color. The
"grille" is no opening: slots of light let into the slab, hanging from its top edge in a
lozenge that folds over the edge onto the hood.
Ten character lines over twelve stations; every detail hangs on the body as built.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import bpy                                                          # noqa: E402
import carkit as K                                                  # noqa: E402
from carkit import (Geo, Matrix, V3, cos, on_body, pi, rad, ribbon, sin,       # noqa: E402
                    text_flat, text_on_body)

# ---------------------------------------------------------------------------------------
# dimensions
# ---------------------------------------------------------------------------------------
FA_X, RA_X = 1.84, -1.36            # axles: wheelbase 3.20
T_R, T_W, T_RIM = 0.40, 0.270, 0.315    # tire radius, width, rim radius
OUT_Y = 0.958                       # outer face of the tires
ARCH_R = 0.448
ARCH = tuple(range(-20, 201, 5))
NOSE_X, TAIL_X = 2.585, -2.585      # the slabs at shoulder height
PITCH = 0.022                       # the plinth's flutes
Z_STRIP = 0.3225                    # the bright strip on the sill line
Z_FL0, Z_FL1 = 0.185, 0.305         # the flutes' foot and head


def nose_x(z):
    """The nose slab leans forward: its top is ahead of its foot."""
    return NOSE_X - (0.89 - z) * 0.07


def tail_x(z):
    """The tail slab leans back the same way: both ends overhang the plinth."""
    return TAIL_X + (0.865 - z) * 0.06


# ---------------------------------------------------------------------------------------
# body: stations and character lines
# ---------------------------------------------------------------------------------------
LINES = "CHGSULKRFB"
#        C centerline top, H hood flow line / A-pillar / roof edge, G hood edge / glass base,
#        S the razor shoulder, U widest line, L sill line, K foot of the sill step,
#        R plinth bottom, F floor edge, B floor centerline
ORDER = ["N0", "N1", "A1", "A2", "W0", "W1", "RM", "CP", "RR", "RG", "DK", "T0"]
PT = {}


def low(x, sz, w=0.0, zf=0.15):
    """The six lower lines of a station: shoulder, widest, sill, step, plinth, floor."""
    return [(x, .95 + w, sz), (x, .98 + w, .60), (x, .97 + w, .33), (x, .95 + w, .315),
            (x, .94 + w, .17), (x, .80, zf), (x, 0, zf)]


def stations():
    def end(fx, zs, ys):
        return [(fx(z), y, z) for z, y in zip(zs, ys)]
    T = {
        "N0": end(nose_x, (.945, .942, .925, .89, .60, .33, .315, .17, .15, .15),
                  (0, .58, .84, .925, .955, .945, .925, .915, .78, 0)),
        "N1": [(2.30, 0, .955), (2.30, .62, .952), (2.30, .865, .932)] + low(2.30, .892, -.003),
        "A1": [(1.78, 0, .965), (1.78, .68, .962), (1.78, .875, .940)] + low(1.78, .894),
        "A2": [(1.20, 0, .975), (1.20, .74, .970), (1.20, .880, .943)] + low(1.20, .895),
        "W0": [(.38, 0, .985), (.27, .80, .955), (.25, .878, .940)] + low(.30, .895),
        "W1": [(-.04, 0, 1.305), (-.10, .74, 1.275), (-.08, .885, .937)] + low(-.08, .895),
        "RM": [(-.85, 0, 1.325), (-.85, .745, 1.290), (-.85, .885, .934)] + low(-.85, .893),
        # the pillar leans with the rear glass: a band of one width from roof to shoulder
        "CP": [(-1.45, 0, 1.318), (-1.45, .74, 1.283), (-1.78, .885, .928)] + low(-1.50, .890),
        "RR": [(-1.80, 0, 1.295), (-1.77, .735, 1.262), (-1.95, .885, .925)] + low(-1.85, .886),
        "RG": [(-2.16, 0, .958), (-2.10, .80, .945), (-2.09, .875, .925)] + low(-2.12, .882),
        "DK": [(-2.38, 0, .948), (-2.38, .66, .943), (-2.38, .86, .913)] + low(-2.38, .873, -.006),
        "T0": end(tail_x, (.930, .927, .905, .865, .60, .33, .315, .18, .16, .16),
                  (0, .60, .83, .915, .945, .935, .915, .905, .78, 0)),
    }
    S = K.fill([T[k] for k in ORDER])
    PT.update(K.table(ORDER, LINES, S))
    return S


PMAT = dict(hood="paint", fender="paint", door="paint", quarter="paint", deck="paint",
            canopy="glass", glass_side="glass",
            trim_ws="gloss_black", trim_b="bright", sill="flute", floor="underbody",
            well="well")


def panel_of(i, j):
    if j >= 7:
        return "floor"
    if j >= 5:
        return "sill"
    if j == 0:
        return "hood" if i <= 3 else "deck" if i >= 9 else "canopy"
    if j == 1:
        return ("hood", "hood", "hood", "hood", "glass_side", "glass_side", "glass_side",
                "quarter", "quarter", "deck", "deck")[i]
    if j == 2 and i <= 3:
        return "hood"               # a clamshell: its cut hides in the shoulder crease
    if j == 2 and i >= 9:
        return "deck"
    return "fender" if i <= 3 else "door" if i <= 5 else "quarter"


def line_crease(i, j):
    """Crease of the edge along line j from station i to i + 1."""
    if j == 1:
        return 1.0 if 4 <= i <= 8 else 0.0
    if j == 2:                      # glass base; on the hood and deck the chamfer's inner edge
        return 1.0
    if j in (3, 5, 6, 7, 8):
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
    wells = Geo()
    K.well_cutter(wells, FA_X, T_R, ARCH_R, 0.62, ARCH)
    K.well_cutter(wells, RA_X, T_R, ARCH_R, 0.62, ARCH)
    K.build_body(
        stations(), panel_of, PMAT, line_crease, station_crease,
        front=dict(kind="flat", panel="fender"), rear=dict(kind="flat", panel="quarter"),
        glass=[("canopy", 0.022, "trim_ws"), ("glass_side", 0.014, "trim_b")],
        cutters=[(wells, "well")], subdiv=3)


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


def lozenge(sl, tag, kmax, z0, led, sx, lmax, pitch=0.030, w=0.008):
    """The Aurel grille: no opening, only slots of light let into the slab, in a field of
    bright hairline flutes. They hang from the slab's top edge, the middle one longest, and go on
    over the edge along the hood (the deck) the same way: the crest's lozenge, folded over
    the edge."""
    proj = 'x' if sx > 0 else 'X'
    gl, gd, gv = Geo(), Geo(), Geo()

    def edge(y):                            # the slab's top edge over a slot
        z = 1.0
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
    # ---- nose
    sl = Slab('x', 0.60)
    lozenge(sl, "f", 25, 0.385, "led_front", 1, 0.52)
    blade(sl, "f", 0.878, 0.385, 0.855, "led_front")
    # ---- tail: the same lozenge, smaller and red
    st = Slab('X', 0.60)
    lozenge(st, "r", 17, 0.50, "led_rear", -1, 0.24)
    blade(st, "r", 0.868, 0.385, 0.835, "led_rear")
    # ---- the plinth across both ends: a dark band, its flutes, the bright strip
    for s, tag, hw in ((sl, "f", 0.905), (st, "r", 0.895)):
        g = Geo()
        s.box(g, 0, (Z_FL0 + Z_FL1) / 2 - 0.004, 0.002, (0.004, 2 * hw + 0.02, Z_FL1 - Z_FL0 + 0.03))
        g.obj("plinth.band." + tag, "flute")
        g = Geo()
        n = int(2 * hw / PITCH)
        for k in range(n + 1):
            y = -n * PITCH / 2 + k * PITCH
            p0, p1 = s.at(y, Z_FL0, 0.003), s.at(y, Z_FL1, 0.003)
            a, b, h = 0.008, 0.0035, 0.006
            g.hexa([p0 - s.ey * a, p0 + s.ey * a, p0 + s.ey * b + s.n * h, p0 - s.ey * b + s.n * h,
                    p1 - s.ey * a, p1 + s.ey * a, p1 + s.ey * b + s.n * h, p1 - s.ey * b + s.n * h])
        g.obj("plinth.flutes." + tag, "flute")
        g = Geo()
        s.box(g, 0, Z_STRIP, 0.005, (0.014, 2 * hw + 0.07, 0.013))
        g.obj("plinth.strip." + tag, "bright", bevel=0.0015)
    # ---- the crest behind the lozenge's point, the wordmark and the model on the tail
    gb, gd = Geo(), Geo()
    p, n = on_body(1.94, 0.0, 'z')
    crest(gb, gd, p + n * 0.0005, (0, 1, 0), (1, 0, 0), 0.046)
    gb.obj("crest", "bright", bevel=0.0006)
    gd.obj("crest.inlay", "gloss_black")
    g = Geo()
    text_flat(g, "A U R E L", 0.046, st.at(0.57, 0.60, 0.0015), st.right, st.eu, spacing=1.2)
    text_flat(g, "PRELATE", 0.027, st.at(-0.57, 0.60, 0.0015), st.right, st.eu, spacing=1.5)
    g.obj("wordmark", "bright")
    # ---- plate
    g = Geo()
    st.box(g, 0, 0.400, 0.004, (0.008, 0.30, 0.085))
    g.obj("plate", "gloss_black", bevel=0.002)
    g = Geo()
    text_flat(g, "AU 1-077", 0.045, st.at(0, 0.400, 0.0088), st.right, st.eu, spacing=1.15)
    g.obj("plate.glyphs", "decal")


# ---------------------------------------------------------------------------------------
# the plinth along the flanks, trims, small details
# ---------------------------------------------------------------------------------------
def flank_runs():
    """The stretches of the flank between the slabs and the wheel arches."""
    e = ARCH_R + 0.012
    return [(2.52, FA_X + e), (FA_X - e, RA_X + e), (RA_X - e, -2.52)]


def build_plinth():
    g = Geo()
    gs = Geo()
    for x0, x1 in flank_runs():
        n = int((x0 - x1) / PITCH)
        off = ((x0 - x1) - n * PITCH) / 2
        for k in range(n + 1):
            x = x0 - off - k * PITCH
            lo, _ = on_body(x, Z_FL0, 'y')
            hi, _ = on_body(x, Z_FL1, 'y')
            if lo is None or hi is None or lo.y < 0.8 or hi.y < 0.8:
                continue
            a, b, h = 0.008, 0.0035, 0.006
            g.hexa([(x - a, lo.y - 0.002, Z_FL0), (x + a, lo.y - 0.002, Z_FL0),
                    (x + b, lo.y + h, Z_FL0), (x - b, lo.y + h, Z_FL0),
                    (x - a, hi.y - 0.002, Z_FL1), (x + a, hi.y - 0.002, Z_FL1),
                    (x + b, hi.y + h, Z_FL1), (x - b, hi.y + h, Z_FL1)])
        path = []
        m = max(2, int((x0 - x1) / 0.08))
        for k in range(m + 1):
            x = x0 + (x1 - x0) * k / m
            p, _ = on_body(x, Z_STRIP, 'y')
            if p is not None and p.y > 0.8:
                path.append(V3((x, p.y + 0.003, Z_STRIP)))
        gs.sweep(path, [(-0.007, -0.0065), (0.007, -0.0065), (0.007, 0.0065), (-0.007, 0.0065)],
                 up=(0, 0, 1))
    g.obj("plinth.flutes", "flute", mirror=True)
    gs.obj("plinth.strip", "bright", bevel=0.0015, mirror=True)


def build_details():
    # ---- the spear: a bright hairline from the crest down the hood
    g = Geo()
    ribbon(g, [(1.885, 0.0), (0.33, 0.0)], 'z', 0.010, lift=0.0012)
    g.obj("spear", "bright")
    # ---- door pull: a bright bar in a dark slot, under the shoulder
    g = Geo()
    ribbon(g, [(-0.57, 0.800), (-0.77, 0.800)], 'y', 0.026)
    g.obj("pull.slot", "gloss_black", mirror=True)
    g = Geo()
    a, n = on_body(-0.58, 0.800, 'y')
    b, _ = on_body(-0.76, 0.800, 'y')
    g.sweep([a + n * 0.005, b + n * 0.005],
            [(-0.004, -0.005), (0.004, -0.005), (0.004, 0.005), (-0.004, 0.005)], up=(0, 0, 1))
    g.obj("pull", "bright", bevel=0.0015, mirror=True)
    # ---- mirrors: a camera blade on a bright stalk at the foot of the A-pillar
    g = Geo()
    g.sweep([(0.18, 0.905, 0.925), (0.165, 0.990, 0.955)],
            [(-0.022, -0.004), (0.022, -0.004), (0.022, 0.004), (-0.022, 0.004)], up=(0, 0, 1))
    g.obj("mirror.stalk", "bright", bevel=0.0015, mirror=True)
    g = Geo()
    g.hexa([(0.225, 0.972, 0.938), (0.225, 1.000, 0.938), (0.085, 1.008, 0.932),
            (0.085, 0.966, 0.932), (0.215, 0.974, 0.985), (0.215, 0.998, 0.985),
            (0.085, 1.004, 0.992), (0.085, 0.968, 0.992)])
    g.obj("mirror.pod", "paint", bevel=0.004, mirror=True)
    g = Geo()
    g.box((0.0835, 0.986, 0.962), (0.004, 0.030, 0.046))
    g.obj("mirror.lens", "gloss_black", mirror=True)
    # ---- crest on the pillar, charge flap, model name low on the fender
    gb, gd = Geo(), Geo()
    p, n = on_body(-1.775, 1.10, 'y')
    right = V3((-1, 0, 0))
    up = n.cross(right).normalized()
    if up.z < 0:
        up = -up
    crest(gb, gd, p + n * 0.0005, right, up, 0.034)
    gb.obj("crest.pillar", "bright", bevel=0.0006, mirror=True)
    gd.obj("crest.pillar.inlay", "gloss_black", mirror=True)
    g = Geo()
    loz = [(-2.30, 0.745), (-2.265, 0.69), (-2.30, 0.635), (-2.335, 0.69)]
    ribbon(g, loz, 'y', 0.003, closed=True)
    g.obj("flap", "void")
    g = Geo()
    for side in (1, -1):
        text_on_body(g, "PRELATE", 0.024, 1.06, 0.385, side, spacing=1.5)
    g.obj("lettering", "bright")
    # ---- the blades turn the corners: a hairline of light on each flank beside its slab
    for x, z0, z1, led, tag in ((2.50, 0.40, 0.84, "led_front", "f"),
                                (-2.505, 0.40, 0.815, "led_rear", "r")):
        gd, gl = Geo(), Geo()
        ribbon(gd, [(x, z0 - 0.006), (x, z1 + 0.006)], 'y', 0.016, lift=0.0006)
        ribbon(gl, [(x, z0), (x, z1)], 'y', 0.006, lift=0.0014)
        gd.obj("blade.side.slot." + tag, "gloss_black", mirror=True)
        gl.obj("blade.side." + tag, led, mirror=True)
    # ---- parking sensors in the plinth's strip zone, front and rear
    g = Geo()
    for proj, sgn in (('x', 1), ('X', -1)):
        for y in (-0.70, -0.30, 0.30, 0.70):
            p, n = on_body(y, 0.352, proj)
            K.stud(g, p, n, [(0.0, 0.001), (0.0, 0.011), (0.002, 0.011), (0.002, 0.001)], 16)
    g.obj("sensors", "gloss_black")
    # ---- a slim stop light under the rear glass's top edge, sensors in the plinth strip
    g = Geo()
    p, n = on_body(-1.86, 0.0, 'z')
    g.box(p + n * 0.004, (0.010, 0.44, 0.006), rot=Matrix.Rotation(rad(-44), 3, 'Y'))
    g.obj("led.stop", "led_rear")
    # ---- wipers parked under the hood's trailing edge: only their dark slot shows
    g = Geo()
    ribbon(g, [(0.305, -0.62), (0.325, 0.0), (0.305, 0.62)], 'z', 0.016)
    g.obj("cowl.slot", "void")


# ---------------------------------------------------------------------------------------
# wheels: the kit's tire and rim under a pleated disc
# ---------------------------------------------------------------------------------------
def build_wheel(tag, cx, side):
    K.build_wheel(tag, cx, T_R, T_W, T_RIM, OUT_Y, side, style="disc", ring=None,
                  caliper=None)
    hw = T_W / 2
    loc = (cx, side * (OUT_Y - hw), T_R)
    flip = side < 0
    # the disc: 96 fine pleats from the hub to the rim, a shallow dish
    N = 96
    M = 2 * N
    r0, r1 = 0.088, T_RIM - 0.024
    y0, y1 = hw - 0.036, hw - 0.015
    vs, fs = [], []
    for k in range(M):
        a = 2 * pi * k / M
        d = 0.0018 if k % 2 else -0.0018
        for r, y in ((r1, y1 + d), (r0, y0 + d * 0.45), (r0, y0 - 0.014), (r1, y1 - 0.014)):
            vs.append((r * cos(a), y, r * sin(a)))
    for k in range(M):
        k2 = (k + 1) % M
        for j in range(4):
            j2 = (j + 1) % 4
            fs.append((4 * k + j, 4 * k + j2, 4 * k2 + j2, 4 * k2 + j))
    g = Geo()
    g.add(vs, fs)
    g.obj("cover." + tag, "platinum", flip_y=flip, loc=loc)
    # a bright ring round it, a dark cap with the crest
    g = Geo()
    g.lathe([(y1 - 0.014, r1 - 0.001), (y1 + 0.004, r1 - 0.001), (y1 + 0.007, r1 + 0.004),
             (y1 + 0.007, T_RIM - 0.007), (y1 - 0.014, T_RIM - 0.007)], 96)
    g.lathe([(y0 - 0.014, 0.086), (y0 + 0.019, 0.086), (y0 + 0.019, 0.096), (y0 - 0.014, 0.096)],
            64)
    g.obj("cover.ring." + tag, "bright", bevel=0.0015, flip_y=flip, loc=loc)
    g = Geo()
    g.lathe([(y0 - 0.014, 0.004), (y0 - 0.014, 0.086), (y0 + 0.015, 0.086), (y0 + 0.021, 0.070),
             (y0 + 0.021, 0.004)], 64)
    g.obj("cover.cap." + tag, "gloss_black", flip_y=flip, loc=loc, sharp=30)
    gb, gd = Geo(), Geo()
    crest(gb, gd, (0, y0 + 0.0212, 0), (1, 0, 0), (0, 0, 1), 0.058)
    # the lozenge was laid out for a reader in front of it: out is right x up = -y here
    for gg in (gb, gd):
        gg.v = [V3((p.x, 2 * (y0 + 0.0212) - p.y, p.z)) for p in gg.v]
    gb.obj("cover.crest." + tag, "bright", flip_y=flip, loc=loc)
    gd.obj("cover.crest.in." + tag, "gloss_black", flip_y=flip, loc=loc)


# ---------------------------------------------------------------------------------------
# interior: 2 + 2
# ---------------------------------------------------------------------------------------
CAB_DX = -0.13


def shift(g):
    """The cabin was laid out 0.13 m farther forward."""
    for p in g.v:
        p.x += CAB_DX


def build_interior():
    g = Geo()
    g.box((-0.70, 0, 0.175), (2.50, 1.80, 0.03))                        # floor
    g.prism([(0.54, -0.86, 0.16), (0.54, -0.86, 0.905), (0.30, -0.86, 0.925),
             (0.13, -0.86, 0.86), (0.15, -0.86, 0.62), (0.30, -0.86, 0.46),
             (0.30, -0.86, 0.16)], (0, 1.72, 0))                        # firewall and dash
    g.box((-0.55, 0, 0.36), (1.70, 0.20, 0.36))                         # console
    g.box((-1.80, 0, 0.895), (0.40, 1.74, 0.03))                        # shelf under the glass
    g.box((-1.99, 0, 0.54), (0.04, 1.74, 0.74))                         # rear bulkhead
    for s in (1, -1):
        g.box((-0.16, s * 0.862, 0.535), (1.40, 0.04, 0.72))            # door cards
        g.box((-1.40, s * 0.745, 0.535), (1.30, 0.27, 0.72))            # over the rear wells
    shift(g)
    g.obj("interior.tub", "interior", bevel=0.006)
    g = Geo()
    t1 = Matrix.Rotation(rad(-19), 3, 'Y')
    t2 = Matrix.Rotation(rad(-15), 3, 'Y')
    for y in (0.42, -0.42):
        g.box((-0.26, y, 0.33), (0.52, 0.50, 0.13))
        g.box((-0.60, y, 0.66), (0.12, 0.48, 0.60), rot=t1)
        g.box((-0.715, y, 1.02), (0.075, 0.24, 0.15), rot=t1)
        for s in (-1, 1):
            g.box((-0.26, y + s * 0.245, 0.36), (0.48, 0.05, 0.16))
            g.box((-0.585, y + s * 0.235, 0.62), (0.15, 0.05, 0.48), rot=t1)
    for y in (0.34, -0.34):
        g.box((-1.20, y, 0.37), (0.44, 0.44, 0.12))
        g.box((-1.47, y, 0.66), (0.11, 0.44, 0.50), rot=t2)
        g.box((-1.56, y, 0.955), (0.07, 0.22, 0.12), rot=t2)
    shift(g)
    g.obj("interior.seats", "seat", bevel=0.014, segs=3)
    g = Geo()
    wheel = (Matrix.Translation((0.03, 0.42, 0.80)) @ Matrix.Rotation(rad(-68), 4, 'Y')
             @ Matrix.Rotation(pi / 2, 4, 'X'))
    g.lathe([(-0.012, 0.165), (0.0, 0.177), (0.012, 0.165), (0.0, 0.153)], 28, xf=wheel)
    g.box((0.03, 0.42, 0.80), (0.03, 0.32, 0.04), rot=Matrix.Rotation(rad(-22), 3, 'Y'))
    g.box((0.11, 0.42, 0.77), (0.17, 0.05, 0.05))
    shift(g)
    g.obj("interior.wheel", "interior", sharp=40)
    g = Geo()
    scr = Matrix.Rotation(rad(-14), 3, 'Y')
    g.box((0.125, 0.0, 0.835), (0.008, 1.50, 0.060), rot=scr)           # pillar to pillar
    g.box((-0.02, 0.0, 0.555), (0.26, 0.15, 0.006))                     # on the console
    shift(g)
    g.obj("interior.screens", "screen")
    g = Geo()
    for s in (1, -1):
        g.box((-0.16, s * 0.838, 0.76), (1.30, 0.006, 0.010))           # a bright line on the doors
    g.box((-0.55, 0, 0.545), (1.60, 0.012, 0.006))
    shift(g)
    g.obj("interior.trim", "bright")


# ---------------------------------------------------------------------------------------
# the build
# ---------------------------------------------------------------------------------------
_studio = K.build_studio


def build_studio():
    """The kit's studio, with one link changed: the top soft box does not light the canopy.
    From the hero's side it was mirrored whole in the near half of the windshield, a white
    pane over the cabin; the paint and everything else still take it."""
    _studio()
    top = K.STUDIO.objects.get("top")
    if top is None:
        return
    rec = bpy.data.collections.new("top.receivers")
    for ob in list(K.CAR.objects) + list(K.STUDIO.objects):
        if ob.type == 'MESH' and ob.name != "body.canopy":
            rec.objects.link(ob)
    try:
        top.light_linking.receiver_collection = rec
    except Exception as e:
        print("light linking:", e)


K.build_studio = build_studio

SERIFS = ("/System/Library/Fonts/Supplemental/Didot.ttc",
          "/System/Library/Fonts/Supplemental/Bodoni 72.ttc",
          "/System/Library/Fonts/Supplemental/Times New Roman Bold.ttf",
          "C:/Windows/Fonts/timesbd.ttf")

K.VIEWS.update(
    nose=dict(dir=(1.0, 0.42, 0.12), lens=85, target=(2.4, 0.3, 0.55), dist=3.6),
    tail=dict(dir=(-1.0, -0.42, 0.14), lens=85, target=(-2.4, -0.3, 0.6), dist=3.6),
    wheel=dict(dir=(0.45, 1.0, 0.10), lens=85, target=(FA_X, 0.9, 0.42), dist=2.6),
)


def main():
    K.materials(paint=(0.038, 0.0022, 0.0065), paint_finish=(0.10, 0.08, 1.0), dust_amount=0.10,
                glass=(0.13, 0.14, 0.155), led_front=(1.0, 0.86, 0.62),
                led_rear=(1.0, 0.02, 0.012), seat=(0.50, 0.40, 0.28),
                interior=(0.030, 0.024, 0.022), screen=(1.0, 0.72, 0.38),
                decal=(0.75, 0.75, 0.72))
    K.emit("led_front", (1.0, 0.80, 0.50), 16.0)            # dimmer than the kit's: the slots
    K.emit("led_rear", (1.0, 0.02, 0.012), 12.0)            # keep their color under the bloom
    K.pbr("bright", (0.88, 0.88, 0.86), 1.0, 0.06)          # polished trim
    K.pbr("flute", (0.085, 0.085, 0.09), 1.0, 0.28)         # dark machined metal
    K.pbr("platinum", (0.36, 0.36, 0.375), 1.0, 0.24)        # the wheel discs
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
    build_details()
    build_interior()
    K.log("details")
    for side, s in ((1, "l"), (-1, "r")):
        build_wheel("f" + s, FA_X, side)
        build_wheel("r" + s, RA_X, side)
    K.log("wheels")
    K.shoot(extra="top")


main()
