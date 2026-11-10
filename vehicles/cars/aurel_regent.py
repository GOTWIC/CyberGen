"""Aurel Regent: a formal four-seat limousine, the second Aurel (both names made up), built
on vehicles/carkit.py.

Run (always through the wrapper, one Blender job at a time on this machine):
    vehicles/blender.sh vehicles/cars/aurel_regent.py --out DIR --preview
    vehicles/blender.sh vehicles/cars/aurel_regent.py --out DIR --sheet

The Prelate's sibling, turned round: there the hood is the point, here the rear cabin. The
same monolith on a fluted plinth, slab nose and tail, lozenge of light slots, razor shoulder
and blade lights; but the hood is short, the driver sits under a folded glass canopy, and
behind a division pillar with a blade of light the owners sit in a vault: a solid roof a
step higher than the glass, a privacy panel with the crest where a quarter light would be,
a slit for a rear window, a rear-hinged door a good quarter longer than the front one.
Ten character lines over thirteen stations; every detail hangs on the body as built.
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
FA_X, RA_X = 2.20, -1.55            # axles: wheelbase 3.75
T_R, T_W, T_RIM = 0.40, 0.270, 0.315    # tire radius, width, rim radius
W = 0.03                            # 3 cm wider than the Prelate on each side
OUT_Y = 0.958 + W                   # outer face of the tires
ARCH_R = 0.452
ARCH = tuple(range(-20, 201, 5))
NOSE_X, TAIL_X = 2.95, -2.95        # the slabs at shoulder height
Z_SH, Z_SHT = 0.957, 0.930          # the shoulder at the nose and at the tail
PAINT = (0.040, 0.0060, 0.066)       # show color: imperial amethyst
PITCH = 0.022                       # the plinth's flutes
Z_STRIP = 0.3225                    # the bright strip on the sill line
Z_FL0, Z_FL1 = 0.185, 0.305         # the flutes' foot and head
DIV0, DIV1 = 0.20, 0.05             # the division pillar between the two cabins
VAULT_X = -1.18                     # where the rear door's glass ends and the vault's panel begins


def nose_x(z):
    """The nose slab leans forward: its top is ahead of its foot."""
    return NOSE_X - (Z_SH - z) * 0.07


def tail_x(z):
    """The tail slab leans back the same way: both ends overhang the plinth."""
    return TAIL_X + (Z_SHT - z) * 0.06


# ---------------------------------------------------------------------------------------
# body: stations and character lines
# ---------------------------------------------------------------------------------------
LINES = "CHGSULKRFB"
#        C centerline top, H hood flow line / A-pillar / roof edge, G hood edge / glass base,
#        S the razor shoulder, U widest line, L sill line, K foot of the sill step,
#        R plinth bottom, F floor edge, B floor centerline
ORDER = ["N0", "N1", "A1", "A2", "W0", "W1", "D0", "D1", "VP", "RR", "RG", "DK", "T0"]
PT = {}


def low(x, sz, w=0.0, zf=0.15):
    """The six lower lines of a station: shoulder, widest, sill, step, plinth, floor."""
    w += W
    return [(x, .95 + w, sz), (x, .98 + w, .62), (x, .97 + w, .33), (x, .95 + w, .315),
            (x, .94 + w, .17), (x, .80 + W, zf), (x, 0, zf)]


def stations():
    def end(fx, zs, ys):
        return [(fx(z), y, z) for z, y in zip(zs, ys)]
    T = {
        "N0": end(nose_x, (1.012, 1.009, .992, Z_SH, .62, .33, .315, .17, .15, .15),
                  (0, .61, .87, .955, .985, .975, .955, .945, .81, 0)),
        "N1": [(2.66, 0, 1.022), (2.66, .65, 1.019), (2.66, .895, .998)] + low(2.66, .958, -.003),
        "A1": [(2.15, 0, 1.032), (2.15, .71, 1.028), (2.15, .905, 1.004)] + low(2.15, .960),
        "A2": [(1.72, 0, 1.040), (1.72, .77, 1.035), (1.72, .910, 1.006)] + low(1.72, .961),
        "W0": [(1.36, 0, 1.050), (1.26, .83, 1.022), (1.24, .908, 1.005)] + low(1.28, .961),
        "W1": [(.86, 0, 1.418), (.80, .806, 1.388), (.82, .912, 1.003)] + low(.82, .961),
        # the division: the solid roof behind it stands a step above the glass ahead of it.
        # The side glass leans in 15 degrees: at 20 it mirrored the sky over the studio's wall
        "D0": [(DIV0, 0, 1.424), (DIV0, .804, 1.394), (DIV0, .912, 1.002)] + low(DIV0, .961),
        "D1": [(DIV1, 0, 1.474), (DIV1, .812, 1.442), (DIV1, .912, 1.002)] + low(DIV1, .961),
        "VP": [(VAULT_X, 0, 1.474), (VAULT_X, .812, 1.442), (VAULT_X, .912, .998)]
              + low(VAULT_X, .959),
        "RR": [(-2.04, 0, 1.461), (-2.02, .805, 1.430), (-2.24, .910, .994)] + low(-2.12, .955),
        "RG": [(-2.38, 0, 1.022), (-2.33, .83, 1.008), (-2.32, .902, .990)] + low(-2.34, .950),
        "DK": [(-2.70, 0, 1.010), (-2.70, .69, 1.005), (-2.70, .888, .975)]
              + low(-2.70, .940, -.006),
        "T0": end(tail_x, (.992, .989, .967, Z_SHT, .62, .33, .315, .18, .16, .16),
                  (0, .63, .86, .945, .975, .965, .945, .935, .81, 0)),
    }
    S = K.fill([T[k] for k in ORDER])
    PT.update(K.table(ORDER, LINES, S))
    return S


PMAT = dict(hood="paint", fender="paint", door_f="paint", door_r="paint", quarter="paint",
            vault="paint_vault", deck="paint", canopy="glass", glass_f="glass", glass_r="glass",
            trim_ws="gloss_black", sill="flute", floor="underbody",
            well="well")


def panel_of(i, j):
    if j >= 7:
        return "floor"
    if j >= 5:
        return "sill"
    if j == 0:
        return "hood" if i <= 3 else "canopy" if i <= 5 else "deck" if i >= 10 else "vault"
    if j == 1:
        # the canopy wraps round the windshield pillar's corner; the vault (the division
        # pillar, the solid roof, the privacy panel, the rear face) is one matte panel
        return ("hood", "hood", "hood", "hood", "canopy", "glass_f", "vault", "glass_r",
                "vault", "vault", "deck", "deck")[i]
    if j == 2 and i <= 3:
        return "hood"               # a clamshell: its cut hides in the shoulder crease
    if j == 2 and i >= 10:
        return "deck"
    return "fender" if i <= 3 else "door_f" if i <= 5 else "door_r" if i <= 7 else "quarter"


def line_crease(i, j):
    """Crease of the edge along line j from station i to i + 1."""
    if j == 1:
        return 1.0 if 4 <= i <= 9 else 0.0
    if j == 2:                      # glass base; on the hood and deck the chamfer's inner edge
        return 1.0
    if j in (3, 5, 6, 7, 8):
        return 1.0
    return 0.0


def station_crease(i, j):
    """Crease of the edge on station i between lines j and j + 1."""
    if i in (0, 12):
        return 1.0
    if i in (4, 10, 6, 7, 9):
        return 1.0 if j <= 1 else 0.0
    if i == 5:
        return 1.0 if j == 0 else 0.0
    if i == 8:
        return 1.0 if j == 1 else 0.0
    return 0.0


def glass_frame(tag, corners, w=0.016, proud=0.004):
    """A polished frame of four mitred bars on a flat pane, its corners given clockwise as
    seen from outside."""
    c = [V3(q) for q in corners]
    n = (c[1] - c[0]).cross(c[3] - c[0]).normalized()
    if n.y < 0:
        n = -n
    inner = []
    for i in range(4):
        d1 = (c[(i + 1) % 4] - c[i]).normalized()
        d2 = (c[i - 1] - c[i]).normalized()
        inner.append(c[i] + (d1 + d2) * (w / d1.cross(d2).length))
    g = Geo()
    for i in range(4):
        j = (i + 1) % 4
        g.prism([q - n * 0.003 for q in (c[i], c[j], inner[j], inner[i])], n * (0.003 + proud))
    g.obj("frame." + tag, "bright", bevel=0.001, mirror=True)


def build_hull():
    wells = Geo()
    K.well_cutter(wells, FA_X, T_R, ARCH_R, 0.65, ARCH)
    K.well_cutter(wells, RA_X, T_R, ARCH_R, 0.65, ARCH)
    K.build_body(
        stations(), panel_of, PMAT, line_crease, station_crease,
        front=dict(kind="flat", panel="fender"), rear=dict(kind="flat", panel="quarter"),
        glass=[("canopy", 0.022, "trim_ws")],
        cutters=[(wells, "well")], subdiv=3)
    # each side pane is one quad of the cage. The kit's frame (an inset of the pane) came out
    # of the subdivision as an oval of glass in a frame with filled corners, so the panes stay
    # whole and their polished frames are laid on them
    glass_frame("f", [PT["W1"]["H"], PT["D0"]["H"], PT["D0"]["G"], PT["W1"]["G"]])
    glass_frame("r", [PT["D1"]["H"], PT["VP"]["H"], PT["VP"]["G"], PT["D1"]["G"]])


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
        z = 1.10
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
    # ---- nose: the lozenge is taller than the Prelate's and folds a shorter way over the hood
    sl = Slab('x', 0.62)
    lozenge(sl, "f", 26, 0.385, "led_front", 1, 0.44)
    blade(sl, "f", 0.905, 0.385, 0.920, "led_front")
    # ---- tail: the same lozenge, smaller and red
    st = Slab('X', 0.62)
    lozenge(st, "r", 18, 0.545, "led_rear", -1, 0.30)
    blade(st, "r", 0.895, 0.385, 0.895, "led_rear")
    # ---- the plinth across both ends: a dark band, its flutes, the bright strip
    for s, tag, hw in ((sl, "f", 0.935), (st, "r", 0.925)):
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
    p, n = on_body(2.40, 0.0, 'z')
    crest(gb, gd, p + n * 0.0005, (0, 1, 0), (1, 0, 0), 0.046)
    gb.obj("crest", "bright", bevel=0.0006)
    gd.obj("crest.inlay", "gloss_black")
    g = Geo()
    text_flat(g, "A U R E L", 0.046, st.at(0.60, 0.50, 0.0015), st.right, st.eu, spacing=1.2)
    text_flat(g, "REGENT", 0.027, st.at(-0.60, 0.50, 0.0015), st.right, st.eu, spacing=1.5)
    g.obj("wordmark", "bright")
    # ---- plate
    g = Geo()
    st.box(g, 0, 0.420, 0.004, (0.008, 0.30, 0.085))
    g.obj("plate", "gloss_black", bevel=0.002)
    g = Geo()
    text_flat(g, "AU 1-001", 0.045, st.at(0, 0.420, 0.0088), st.right, st.eu, spacing=1.15)
    g.obj("plate.glyphs", "decal")


# ---------------------------------------------------------------------------------------
# the plinth along the flanks, trims, small details
# ---------------------------------------------------------------------------------------
def flank_runs():
    """The stretches of the flank between the slabs and the wheel arches."""
    e = ARCH_R + 0.012
    return [(NOSE_X - 0.065, FA_X + e), (FA_X - e, RA_X + e), (RA_X - e, TAIL_X + 0.065)]


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
            if lo is None or hi is None or lo.y < 0.84 or hi.y < 0.84:
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
            if p is not None and p.y > 0.84:
                path.append(V3((x, p.y + 0.003, Z_STRIP)))
        gs.sweep(path, [(-0.007, -0.0065), (0.007, -0.0065), (0.007, 0.0065), (-0.007, 0.0065)],
                 up=(0, 0, 1))
    g.obj("plinth.flutes", "flute", mirror=True)
    gs.obj("plinth.strip", "bright", bevel=0.0015, mirror=True)


def side_frame(x, z):
    """A point of the left flank with its normal and the directions aft and up on it."""
    p, n = on_body(x, z, 'y')
    right = V3((-1, 0, 0))
    up = n.cross(right).normalized()
    if up.z < 0:
        up = -up
    return p, n, right, up


def pull(tag, x0, x1, z):
    """A door pull: a bright bar in a dark slot, under the shoulder."""
    g = Geo()
    ribbon(g, [(x0 + 0.01, z), (x1 - 0.01, z)], 'y', 0.026)
    g.obj("pull.slot." + tag, "gloss_black", mirror=True)
    g = Geo()
    a, n = on_body(x0, z, 'y')
    b, _ = on_body(x1, z, 'y')
    g.sweep([a + n * 0.005, b + n * 0.005],
            [(-0.004, -0.005), (0.004, -0.005), (0.004, 0.005), (-0.004, 0.005)], up=(0, 0, 1))
    g.obj("pull." + tag, "bright", bevel=0.0015, mirror=True)


def build_details():
    # ---- the spear: a bright hairline from the crest down the hood
    g = Geo()
    ribbon(g, [(2.345, 0.0), (1.39, 0.0)], 'z', 0.010, lift=0.0012)
    g.obj("spear", "bright")
    # ---- door pulls: the doors open like a book from the division, both pulls beside it
    pull("f", 0.42, 0.26, 0.868)
    pull("r", 0.14, -0.06, 0.868)
    # ---- the division: a blade of light down the pillar, a bright band over the roof's step
    gd, gl, gb = Geo(), Geo(), Geo()
    xm = (DIV0 + DIV1) / 2
    ribbon(gd, [(xm, 1.035), (xm, 1.385)], 'y', 0.040, lift=0.0008)
    ribbon(gl, [(xm, 1.045), (xm, 1.375)], 'y', 0.014, lift=0.0020)
    for dx in (-0.022, 0.022):
        ribbon(gb, [(xm + dx, 1.032), (xm + dx, 1.388)], 'y', 0.004, lift=0.0024)
    gd.obj("division.slot", "gloss_black", mirror=True)
    gl.obj("division.blade", "led_front", mirror=True)
    gb.obj("division.edge", "bright", mirror=True)
    g = Geo()
    ribbon(g, [(xm, -0.74), (xm, 0.74)], 'z', 0.016, lift=0.0016)
    g.obj("division.band", "bright")
    # ---- mirrors: a camera blade on a bright stalk at the foot of the A-pillar
    dx, dy, dz = 0.99, W, 0.066
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
    # ---- the privacy panel: bright hairline flutes hang from the roof's edge, the middle one
    # longest (the lozenge again), and the crest in a lozenge of light at their heart
    gb, gd, gl, gs = Geo(), Geo(), Geo(), Geo()
    cx, cz, s = (VAULT_X - 2.10) / 2, 1.215, 0.060
    p, n, right, up = side_frame(cx, cz)
    crest(gb, gd, p + n * 0.0005, right, up, s)
    k = 1.75
    hw, hh = 0.5 * s * k, 0.82 * s * k
    loz = [(cx, cz + hh), (cx - hw, cz), (cx, cz - hh), (cx + hw, cz)]
    ribbon(gs, loz, 'y', 0.012, lift=0.0006, closed=True, step=0.004)
    ribbon(gl, loz, 'y', 0.005, lift=0.0014, closed=True, step=0.004)
    gb.obj("crest.vault", "bright", bevel=0.0006, mirror=True)
    gd.obj("crest.vault.inlay", "gloss_black", mirror=True)
    gs.obj("crest.vault.slot", "gloss_black", mirror=True)
    gl.obj("crest.vault.light", "led_front", mirror=True)
    g = Geo()
    KX, pitch, zt, zb = 11, 0.028, 1.398, 1.035
    for kx in range(-KX, KX + 1):
        x = cx + kx * pitch
        z0 = zt - (zt - zb) * (1 - abs(kx) / (KX + 1))
        d = abs(kx) * pitch
        if d < hw + 0.012:                      # round the crest's lozenge
            h = hh * (1 - d / (hw + 0.012)) + 0.016
            runs = [(zt, cz + h), (cz - h, z0)]
        else:
            runs = [(zt, z0)]
        for za, zc in runs:
            if za - zc > 0.01:
                ribbon(g, [(x, za), (x, zc)], 'y', 0.0032, lift=0.0016)
    g.obj("vault.flutes", "bright", mirror=True)
    # ---- charge flap, model name low on the fender
    g = Geo()
    loz = [(-2.56, 0.775), (-2.525, 0.72), (-2.56, 0.665), (-2.595, 0.72)]
    ribbon(g, loz, 'y', 0.003, closed=True)
    g.obj("flap", "void")
    g = Geo()
    for side in (1, -1):
        text_on_body(g, "REGENT", 0.024, 1.46, 0.385, side, spacing=1.5)
    g.obj("lettering", "bright")
    # ---- the blades turn the corners: a hairline of light on each flank beside its slab
    for x, z0, z1, led, tag in ((NOSE_X - 0.085, 0.40, 0.905, "led_front", "f"),
                                (TAIL_X + 0.080, 0.40, 0.880, "led_rear", "r")):
        gd, gl = Geo(), Geo()
        ribbon(gd, [(x, z0 - 0.006), (x, z1 + 0.006)], 'y', 0.016, lift=0.0006)
        ribbon(gl, [(x, z0), (x, z1)], 'y', 0.006, lift=0.0014)
        gd.obj("blade.side.slot." + tag, "gloss_black", mirror=True)
        gl.obj("blade.side." + tag, led, mirror=True)
    # ---- parking sensors in the plinth's strip zone, front and rear
    g = Geo()
    for proj, sgn in (('x', 1), ('X', -1)):
        for y in (-0.72, -0.30, 0.30, 0.72):
            p, n = on_body(y, 0.352, proj)
            K.stud(g, p, n, [(0.0, 0.001), (0.0, 0.011), (0.002, 0.011), (0.002, 0.001)], 16)
    g.obj("sensors", "gloss_black")
    # ---- the vault's rear face: a slit of glass in a bright frame, a stop light over it
    g = Geo()
    ribbon(g, [(-0.56, 1.235), (0.56, 1.235)], 'X', 0.135, lift=0.002)
    g.obj("slit", "gloss_black")
    g = Geo()
    ribbon(g, [(-0.565, 1.165), (0.565, 1.165), (0.565, 1.305), (-0.565, 1.305)], 'X', 0.009,
           lift=0.0032, closed=True)
    g.obj("slit.frame", "bright")
    g = Geo()
    ribbon(g, [(-0.34, 1.375), (0.34, 1.375)], 'X', 0.011, lift=0.002)
    g.obj("led.stop", "led_rear")
    # ---- wipers parked under the hood's trailing edge: only their dark slot shows
    g = Geo()
    ribbon(g, [(1.285, -0.64), (1.305, 0.0), (1.285, 0.64)], 'z', 0.016)
    g.obj("cowl.slot", "void")
    # ---- a finial at each front corner: a polished staff with a lozenge of light at its tip
    gb, gl = Geo(), Geo()
    p, n = on_body(2.80, 0.868, 'z')
    K.stud(gb, p, n, [(0.0, 0.001), (0.0, 0.019), (0.004, 0.019), (0.009, 0.011),
                      (0.030, 0.007), (0.034, 0.010), (0.038, 0.007), (0.038, 0.001)], 24)
    top = p + V3((0, 0, 0.215))
    gb.tube(p + V3((0, 0, 0.03)), top, 0.0042, 12)
    c = top + V3((0, 0, 0.030))
    sx, sz = 0.016, 0.034
    for g, kk, hy in ((gb, 1.0, 0.0035), (gl, 0.74, 0.0062)):
        g.prism([c + V3((0, -hy, sz * kk)), c + V3((sx * kk, -hy, 0)), c + V3((0, -hy, -sz * kk)),
                 c + V3((-sx * kk, -hy, 0))], V3((0, 2 * hy, 0)))
    gb.obj("finial", "bright", bevel=0.0008, mirror=True)
    gl.obj("finial.light", "led_front", mirror=True)


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
# interior: a driver's cabin under glass, the division, the rear cabin
# ---------------------------------------------------------------------------------------
def build_interior():
    hy = 0.89
    g = Geo()
    g.box((-0.40, 0, 0.175), (3.56, 2 * hy, 0.03))                      # floor
    g.prism([(1.39, -hy, 0.16), (1.39, -hy, 0.968), (1.15, -hy, 0.988),
             (0.98, -hy, 0.92), (1.00, -hy, 0.68), (1.15, -hy, 0.50),
             (1.15, -hy, 0.16)], (0, 2 * hy, 0))                        # firewall and dash
    g.box((0.66, 0, 0.36), (0.86, 0.20, 0.36))                          # front console
    xm = (DIV0 + DIV1) / 2
    g.box((xm, 0, 0.575), (0.07, 2 * hy, 0.80))                         # the division's wall
    g.box((-1.42, 0, 0.43), (1.06, 0.22, 0.50))                         # the rear console
    g.box((-0.55, 0, 0.26), (0.70, 0.22, 0.16))                         # its foot to the division
    g.box((-2.20, 0, 0.62), (0.04, 2 * hy, 0.88))                       # rear bulkhead
    g.box((-0.95, 0, 1.405), (2.14, 1.56, 0.012))                       # headliner
    for s in (1, -1):
        g.box((0.72, s * (hy + 0.005), 0.56), (1.02, 0.04, 0.76))       # door cards
        g.box((-0.52, s * (hy + 0.005), 0.56), (1.10, 0.04, 0.76))
        g.box((-1.62, s * 0.78, 0.56), (1.12, 0.26, 0.76))              # over the rear wells
    g.obj("interior.tub", "interior", bevel=0.006)
    g = Geo()
    t1 = Matrix.Rotation(rad(-19), 3, 'Y')
    t2 = Matrix.Rotation(rad(-22), 3, 'Y')
    t3 = Matrix.Rotation(rad(14), 3, 'Y')
    for y in (0.42, -0.42):                                             # the driver's cabin
        g.box((0.69, y, 0.35), (0.52, 0.50, 0.13))
        g.box((0.36, y, 0.68), (0.11, 0.48, 0.60), rot=t1)
        g.box((0.25, y, 1.04), (0.07, 0.24, 0.15), rot=t1)
        for s in (-1, 1):
            g.box((0.69, y + s * 0.245, 0.38), (0.48, 0.05, 0.16))
            g.box((0.375, y + s * 0.235, 0.64), (0.14, 0.05, 0.48), rot=t1)
    for y in (0.375, -0.375):                                           # the owners' chairs
        g.box((-1.52, y, 0.40), (0.60, 0.50, 0.15))
        g.box((-1.90, y, 0.76), (0.14, 0.50, 0.68), rot=t2)
        g.box((-2.04, y, 1.13), (0.09, 0.30, 0.17), rot=t2)
        for s in (-1, 1):                                               # wings and bolsters
            g.box((-1.52, y + s * 0.245, 0.44), (0.56, 0.05, 0.19))
            g.box((-1.885, y + s * 0.240, 0.74), (0.18, 0.05, 0.56), rot=t2)
            g.box((-2.00, y + s * 0.165, 1.13), (0.13, 0.04, 0.16), rot=t2)
        g.box((-1.08, y, 0.37), (0.34, 0.44, 0.06), rot=t3)             # leg rest
        g.box((-0.20, y, 0.27), (0.30, 0.42, 0.05), rot=Matrix.Rotation(rad(-24), 3, 'Y'))
    g.box((-1.50, 0, 0.705), (0.62, 0.20, 0.05))                        # the console's armrest
    g.obj("interior.seats", "seat", bevel=0.014, segs=3)
    g = Geo()
    wheel = (Matrix.Translation((0.96, 0.42, 0.85)) @ Matrix.Rotation(rad(-68), 4, 'Y')
             @ Matrix.Rotation(pi / 2, 4, 'X'))
    g.lathe([(-0.012, 0.165), (0.0, 0.177), (0.012, 0.165), (0.0, 0.153)], 28, xf=wheel)
    g.box((0.96, 0.42, 0.85), (0.03, 0.32, 0.04), rot=Matrix.Rotation(rad(-22), 3, 'Y'))
    g.box((1.04, 0.42, 0.82), (0.17, 0.05, 0.05))
    g.obj("interior.wheel", "interior", sharp=40)
    g = Geo()
    scr = Matrix.Rotation(rad(-14), 3, 'Y')
    g.box((0.975, 0.0, 0.895), (0.008, 1.50, 0.060), rot=scr)           # pillar to pillar
    g.box((0.80, 0.0, 0.555), (0.26, 0.15, 0.006))                      # on the front console
    for y in (0.42, -0.42):                                             # on the division, aft
        g.box((xm - 0.039, y, 0.76), (0.006, 0.52, 0.27))
    g.box((-1.08, 0.0, 0.683), (0.18, 0.13, 0.006))                     # on the rear console
    g.obj("interior.screens", "screen")
    g = Geo()
    g.box((xm, 0, 1.165), (0.012, 2 * hy - 0.10, 0.39))                 # the division's glass
    g.obj("interior.partition", "partition")
    g = Geo()
    for s in (1, -1):
        g.box((0.72, s * (hy - 0.018), 0.80), (1.00, 0.006, 0.010))     # a bright line on the doors
        g.box((-0.52, s * (hy - 0.018), 0.80), (1.08, 0.006, 0.010))
    g.box((xm, 0, 0.978), (0.085, 2 * hy - 0.06, 0.012))                # the division's rail
    g.box((-1.42, 0, 0.683), (1.04, 0.012, 0.006))
    for y in (0.085, -0.085):                                           # two flutes in a cooler
        g.lathe([(-0.045, 0.004), (-0.045, 0.024), (0.045, 0.024), (0.045, 0.004)], 16,
                xf=Matrix.Translation((-0.80, y, 0.73)) @ Matrix.Rotation(pi / 2, 4, 'X'))
    g.obj("interior.trim", "bright")
    # ---- the lit ceiling: slots of light along the vault, the middle one longest
    g = Geo()
    for k in range(-7, 8):
        ln = 1.56 * (1 - abs(k) / 9.5)
        g.box((-0.92, k * 0.062, 1.397), (ln, 0.020, 0.006))
    g.obj("interior.ceiling", "ceiling")


# ---------------------------------------------------------------------------------------
# the build
# ---------------------------------------------------------------------------------------
_studio = K.build_studio
SIDE_GLASS = ("body.glass_f", "body.glass_r")
UNLIT = dict(top=("body.canopy",) + SIDE_GLASS, key=SIDE_GLASS, strip=SIDE_GLASS,
             strip2=SIDE_GLASS)


def build_studio():
    """The kit's studio with some links changed. The top soft box does not light the canopy:
    from the hero's side it was mirrored whole in the near half of the windshield, a white
    pane over the cabin. The side glass leans in 20 degrees and mirrored the top box, the key
    and the strips from behind and from above: it takes none of them. The paint and
    everything else still take every light."""
    _studio()
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

K.VIEWS["hero"].update(dir=(0.86, 1.0, 0.34))
K.VIEWS.update(
    vault3q=dict(dir=(-1.0, 0.78, 0.22), lens=70),
    nose=dict(dir=(1.0, 0.42, 0.12), lens=85, target=(2.75, 0.3, 0.6), dist=3.8),
    tail=dict(dir=(-1.0, -0.42, 0.14), lens=85, target=(-2.75, -0.3, 0.65), dist=3.8),
    vault=dict(dir=(-0.55, 1.0, 0.16), lens=70, target=(-1.2, 0.9, 0.95), dist=4.6),
)


def main():
    K.materials(paint=PAINT, paint_finish=(0.10, 0.08, 1.0), dust_amount=0.08,
                glass=(0.19, 0.19, 0.21), led_front=(1.0, 0.86, 0.62),
                led_rear=(1.0, 0.02, 0.012), seat=(0.60, 0.56, 0.50),
                interior=(0.030, 0.022, 0.034), screen=(1.0, 0.72, 0.38),
                decal=(0.75, 0.75, 0.72))
    K.emit("led_front", (1.0, 0.80, 0.50), 16.0)            # dimmer than the kit's: the slots
    K.emit("led_rear", (1.0, 0.02, 0.012), 12.0)            # keep their color under the bloom
    K.emit("ceiling", (1.0, 0.78, 0.52), 300.0)
    K.pbr("paint_vault", tuple(c * 0.50 for c in PAINT), 0.0, 0.78,
          **{"Specular IOR Level": 0.08})                   # the vault: a matte skin
    K.pbr("bright", (0.88, 0.88, 0.86), 1.0, 0.06)          # polished trim
    K.pbr("flute", (0.085, 0.085, 0.09), 1.0, 0.28)         # dark machined metal
    K.pbr("platinum", (0.36, 0.36, 0.375), 1.0, 0.24)       # the wheel discs
    K.pbr("partition", (0.80, 0.80, 0.82), 0.0, 0.0, **{"Transmission Weight": 1.0, "IOR": 1.5})
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
    K.shoot(extra=dict(view="vault3q", size=(960, 460)))


main()
