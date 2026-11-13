"""Tanager Mino: a four-seat city car, a friendly tall box (both names made up), built on
vehicles/carkit.py.

Run (always through the wrapper, one Blender job at a time on this machine):
    vehicles/blender.sh vehicles/cars/tanager_mino.py --out DIR --preview
    vehicles/blender.sh vehicles/cars/tanager_mino.py --out DIR --sheet

The first Tanager, so it sets the family's cues (docs/progress/AG18/tanager_mino/README.md):
a soft tall box with the wheels at its corners, flat glass in rounded-rectangle openings with
fat black seals and a frit border, a visor across each end: a hole under a clear lens in a
gloss black surround holding one light bar between two rounded-rectangle lamps (a lit ring round a row of LED
cups) and a dot-matrix display under its own smoked lens; squircle wheel arches in grained
plastic cladding with a bump strip, steel wheels under slotted covers, a white cap roof with
its gear, a fleet roundel and service lettering.

The body is ten lines over sixteen stations with no hard edge but the cladding's step. The
windows are not panels of the cage: cutters open rounded holes in the skin, and the glass and
its seal are laid behind each hole on the skin as built. Everything else cut into the skin
(the visors, the side repeaters, the handle recesses and the charge door) is laid on the
hull as it stands uncut (cutters()). The brand's helpers
(outlines, pads, bars, dot matrices, windows, plate, badge, arch, wheel) are in
vehicles/brands/tanager.py.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import bmesh                                                        # noqa: E402
import carkit as K                                                  # noqa: E402
from functools import partial                                       # noqa: E402
from brands import tanager                                          # noqa: E402
from brands.tanager import (GD, GLYPH, badge, banner, bar_on, dots, grain, pad,   # noqa: E402
                            rect, rrect, sheet, text_proj)
from carkit import Geo, Matrix, V3, cos, hypot, pi, rad, sin, stud    # noqa: E402

# ---------------------------------------------------------------------------------------
# dimensions
# ---------------------------------------------------------------------------------------
FA_X, RA_X = 1.225, -1.225          # axles: wheelbase 2.45
T_R, T_W, T_RIM, T_OUT = 0.28, 0.165, 0.19, 0.752      # tire radius, width, rim, outer face
ARCH = (0.335, 0.34, 0.285, 3.4)    # squircle arch: half width, rise, center height, exponent
ARCH_A = ARCH[0]
WELL_Y = 0.45                       # the wells' inner walls (0.50 before: room to steer)
BELT, HEAD = 0.95, 1.457            # belt line and glass header
NUM = "07"
GAP = 0.00175                       # shut lines 3.5 mm
FRIT = 0.04                         # the frit border on the glass, from its edge
VIS = dict(front=('x', 0.69, "led_front", "pixel", "z 82%"),      # the visors: projection,
           rear=('X', 0.885, "led_rear", "pixel_r", "FREE h"))     # middle height, lights

arch_pts = partial(tanager.arch_pts, arch=ARCH)
build_wheel = partial(tanager.wheel, R=T_R, w=T_W, rim=T_RIM, out=T_OUT, tread=tanager.NARROW)
LATE = {}                           # what cutters() lays inside the cuts, made after the build


FAR = {'x': lambda p: p.x < 0.5, 'X': lambda p: p.x > -1.0, 'y': lambda p: p.y < 0.3,
       'Y': lambda p: p.y > -0.3, 'z': lambda p: False}
_skin = tanager.skin


def skin(u, v, proj):
    """The brand's skin(), but a ray that slips through a shut line at the edge of a face
    (3.5 mm wide now) and meets the inside of the body far behind it looks beside it, as
    one that misses does. Set as the brand module's own, so its pads use it too."""
    for du, dv in ((0, 0), (0, 0.004), (0, -0.004), (0.004, 0), (-0.004, 0), (0, 0.009),
                   (0, -0.009), (0.009, 0), (-0.009, 0)):
        loc, n = K.on_body(u + du, v + dv, proj)
        if loc is not None and not FAR[proj](loc):
            return loc, n
    return _skin(u, v, proj)


tanager.skin = skin


def tail_x(z):
    """The tail is one plane, leaning forward six degrees."""
    return -1.70 + (z - 0.30) * 0.1026


class MinoWin(tanager.Win):
    """The Mino's windows: its smaller body's cutter planes, and flat glass with a frit
    border (the glass's own thickness, no gap between them)."""

    CUT = dict(y=(0.42, 0.6), x=(0.45, 1.6), X=(-1.15, -0.8))

    def panes(self, gp, gf, w=FRIT):
        def flat(p):
            return p - self.n * ((p - self.c).dot(self.n) + GD)
        O = [flat(p) for p in self.P]
        In = [flat(p + d * w) for p, d in zip(self.P, self.D)]
        m = len(O)
        gp.add(In, [tuple(range(m))])
        gf.add(O + In, [(k, (k + 1) % m, m + (k + 1) % m, m + k) for k in range(m)])


def dense(pts, step=0.015, closed=True):
    """A polyline with a point at least every step."""
    out = []
    segs = list(zip(pts, pts[1:] + pts[:1])) if closed else list(zip(pts, pts[1:]))
    for a, b in segs:
        n = max(1, int(hypot(b[0] - a[0], b[1] - a[1]) / step + 0.999))
        out += [(a[0] + (b[0] - a[0]) * k / n, a[1] + (b[1] - a[1]) * k / n) for k in range(n)]
    if not closed:
        out.append(pts[-1])
    return out


def under(pts, proj, depth):
    """Points of a path in projection carried onto the skin and depth under it, with the
    skin's normals."""
    P, U = [], []
    for u, v in pts:
        loc, n = skin(u, v, proj)
        P.append(loc - n * depth)
        U.append(n)
    return P, U


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
            floor="underbody", well="well", wincut="void",
            visor_f="void", visor_r="void", rep_h="void", slot="plastic", cut="void")


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


W_SIDE = [MinoWin([(.93, .99), (.76, 1.365), (.10, 1.365), (.10, .99)], [.055, .07, .07, .07],
                  'y'),
          MinoWin(rect(-.43, 1.1775, .37, .1875), .07, 'y'),
          MinoWin([(-.92, .99), (-.92, 1.365), (-1.375, 1.365), (-1.415, .99)], .07, 'y')]
W_FRONT = MinoWin([(-.56, 1.065), (.56, 1.065), (.53, 1.44), (-.53, 1.44)], .075, 'x')
W_REAR = MinoWin(rect(0, 1.2075, .52, .1625), .075, 'X')


# ---------------------------------------------------------------------------------------
# the cuts, laid on the hull as it stands uncut, and what stands inside them
# ---------------------------------------------------------------------------------------
def frame_on(g, outline, proj, w, z0, z1):
    """A wall w thick along a closed outline on the skin, from z0 to z1 over it."""
    P, U = under(dense(outline), proj, 0.0)
    g.sweep(P, [(-w / 2, z0), (w / 2, z0), (w / 2, z1), (-w / 2, z1)], up=U, closed=True)


def visor(tag):
    """A visor: a hole across the face (the paint's own 14 mm rim its walls, a gloss black
    back plate closing it 14 mm in), a gloss black surround standing 9.5 mm proud round its
    edge and a clear lens in it, all laid on the skin as it stands uncut (the skin cut out
    as a lens zigzagged at the face's rounded ends). The lamps stand in the hole with their
    lit faces 2 to 4 mm proud of the skin, under the lens: the game pack's far LOD draws
    the nose's flat face across the hole, and lit faces behind it would be lost; nothing in
    it is a small ring, which that LOD fills into a lid. At each end a lamp of a chrome
    plate, a lit ring of light guide and a row of three LED cups on a dark tray; the light
    bar between them, a guide on a chrome strip; the display on the car's left, a screen
    with its lit dots under a smoked lens of its own."""
    proj, cv, lit, pix, msg = VIS[tag]
    t = tag[0]
    sg = -1.0 if proj == 'X' else 1.0          # the car's left as this view's u
    g, lens = Geo(), Geo()
    K.pocket(g, K.rounded(0.0, cv, 1.25, 0.17, 0.05), proj, depth=0.03)
    frame_on(lens, rrect(0, cv, 0.6235, 0.0835, 0.0485), proj, 0.008, -0.004, 0.0095)
    glass = Geo()
    pad(glass, 0, cv, 0.620, 0.080, 0.045, proj, lift=0.009, sink=-0.006, nv=10, nc=8,
        step=0.01)
    back = Geo()
    pad(back, 0, cv, 0.632, 0.092, 0.052, proj, lift=-0.0140, sink=0.0175, nv=6)
    # the lamps at each end (the left one, mirrored)
    E = K.Lamp("lamp.%s" % tag, lit=lit, optic="lens_red" if t == "r" else "optic")
    pad(E.chrome, 0.52, cv, 0.072, 0.055, 0.028, proj, lift=-0.003, sink=0.004)
    P, U = under(dense(rrect(0.52, cv, 0.0615, 0.0445, 0.021)), proj, -0.0005)
    E.guide(P, r=0.0032, sleeve=1.6, closed=True, up=U)
    pad(E.housing, 0.52, cv, 0.050, 0.034, 0.016, proj, lift=-0.002, sink=0.0029)
    for u in (0.488, 0.52, 0.552):
        loc, n = skin(u, cv, proj)
        E.reflector(loc + n * 0.002, n, r=0.0125, depth=0.0055, seg=16, led=0.0055)
    # the light bar: a guide on a chrome strip
    B = K.Lamp("lamp.%s_bar" % tag, lit=lit, optic="lens_red" if t == "r" else "optic")
    P, U = under(dense([(-0.44, cv + 0.034), (0.44, cv + 0.034)], 0.02, closed=False), proj,
                 0.0)
    B.guide(P, r=0.0038, sleeve=1.45, up=U)
    pad(B.chrome, 0, cv + 0.034, 0.442, 0.0115, 0.008, proj, lift=-0.004, sink=0.005)
    # the display under its own smoked lens
    du, dv = sg * 0.235, cv - 0.03
    sc, px, ln = Geo(), Geo(), Geo()
    pad(sc, du, dv, 0.141, 0.040, 0.016, proj, lift=0.001, sink=0.004)
    dots(px, banner(msg), du, dv, 0.0072, proj, 0.002, 0.0052)
    pad(ln, du, dv, 0.139, 0.038, 0.015, proj, lift=0.0047, sink=-0.0035)
    LATE[tag] = (lens, glass, back, E, B, sc, px, ln, pix)
    return g


def cutters():
    """Everything cut into the hull: the wheel wells, the windows (holes), the visors and
    the side repeaters (housings under lenses), the handle recesses and the charge door
    (a shut line)."""
    wells, wins = Geo(), Geo()
    for cx in (FA_X, RA_X):
        for sg in (1, -1):
            pts = arch_pts(cx)
            poly = [(pts[0][0], sg * WELL_Y, -0.3)] + [(x, sg * WELL_Y, z) for x, z in pts]
            poly.append((pts[-1][0], sg * WELL_Y, -0.3))
            wells.prism(poly, (0, sg * 0.5, 0))
    for w in W_SIDE + [W_FRONT, W_REAR]:
        w.cut(wins)
    vf, vr = visor("front"), visor("rear")
    # the side repeaters on the front fenders: an amber cell under an amber lens
    # (a hole like the visors': the paint's rim its walls, a back plate, a flush lens)
    rep = Geo()
    K.pocket(rep, K.rounded(1.09, 0.80, 0.064, 0.022), 'y', depth=0.012, mirror=True)
    R = K.Lamp("lamp.repeater", lit="led_accent", glass="lens_amber")
    pad(R.housing, 1.09, 0.80, 0.0355, 0.0145, 0.012, 'y', lift=-0.0140, sink=0.016)
    pad(R.chrome, 1.09, 0.80, 0.031, 0.0105, 0.009, 'y', lift=-0.0085, sink=0.0139)
    pad(R.emit(), 1.09, 0.80, 0.025, 0.006, 0.005, 'y', lift=-0.0045, sink=0.0065)
    pad(R.glass, 1.09, 0.80, 0.032, 0.011, 0.011, 'y', lift=0.0, sink=0.003)
    LATE["rep"] = R
    # handle recesses: a cup under each pull, the pull's ends on the skin past it
    pulls, gp = Geo(), Geo()
    for x in (0.17, -0.71):
        K.pocket(pulls, K.rounded(x, 0.886, 0.096, 0.040, 0.018), 'y', depth=0.014,
                 mirror=True)
        pad(gp, x, 0.899, 0.056, 0.0095, 0.009, 'y', lift=0.009)
    LATE["pulls"] = gp
    # a shut line: the charge door on the left front fender
    cut = Geo()
    K.groove(cut, rrect(1.33, 0.775, 0.075, 0.052, 0.022), 'y', closed=True)
    return [(wells, "well"), (wins, "wincut", "drop"), (vf, "visor_f", "drop"),
            (vr, "visor_r", "drop"), (rep, "rep_h", "drop"), (pulls, "slot"),
            (cut, "cut", "drop")]


def unfold(ob):
    """Takes out the faces the boolean and the gap's shrink folded back over their
    neighbors (slivers along a cut through a face's fan of quads): their normals point
    into the body, and the panel's weighted normals scatter round them in stars."""
    bm = bmesh.new()
    bm.from_mesh(ob.data)
    bad = []
    for f in bm.faces:
        nb = [g for e in f.edges for g in e.link_faces if g is not f]
        if nb and f.normal.dot(sum((g.normal * g.calc_area() for g in nb), V3())) < 0:
            bad.append(f)
    if bad:
        bmesh.ops.delete(bm, geom=bad, context='FACES')
        bm.to_mesh(ob.data)
    bm.free()
    return len(bad)


def flatten(ob, n, deg=1.5):
    """Flat shading on the faces of a panel that lie in its face's plane (normal n): the
    cuts leave long thin triangles there from the cut's edge to the face's far corners, and
    smooth shading carried the rim's normals at the cut along them in stars."""
    c = cos(rad(deg))
    k = 0
    for p in ob.data.polygons:
        if p.normal.dot(n) > c:
            p.use_smooth = False
            k += 1
    return k


def build_hull():
    body = K.build_body(stations(), panel_of, PMAT, line_crease, station_crease,
                        front=dict(kind="flat", panel="nose", crease=0.0),
                        rear=dict(kind="flat", panel="gate", crease=0.0),
                        cutters=cutters, subdiv=3, gap=GAP)
    folds = {pn: unfold(body.parts[pn]) for pn in ("nose", "gate")}
    K.log("folds taken out: %s" % {k: v for k, v in folds.items() if v})
    tail_n = V3((-1.0, 0.0, 0.1026)).normalized()
    for pn, n in (("nose", V3((1, 0, 0))), ("gate", tail_n)):
        K.log("%s: %d faces flat" % (pn, flatten(body.parts[pn], n)))
    for tag in ("front", "rear"):
        rim, lens, back, E, B, sc, px, ln, pix = LATE[tag]
        rim.obj("visor.rim." + tag, "visor", bevel=0.0015)
        lens.obj("visor.lens." + tag, "lens_clear", sharp=40)
        back.obj("visor.back." + tag, "visor", bevel=0.002)
        E.obj(mirror=True)
        B.obj()
        sc.obj("display." + tag, "panel", bevel=0.001)
        px.obj("pixels." + tag, pix)
        ln.obj("display.lens." + tag, "lens_smoke")
    LATE["rep"].obj(mirror=True)
    LATE["pulls"].obj("handle.pulls", "paint", bevel=0.002, mirror=True)


# ---------------------------------------------------------------------------------------
# glass, seals, wipers
# ---------------------------------------------------------------------------------------
def frit(g, name, **kw):
    ob = g.obj(name, "frit", **kw)
    md = ob.modifiers.new("solid", 'SOLIDIFY')
    md.thickness = 0.004
    md.offset = -1.0
    return ob


def build_glass():
    for w in W_SIDE + [W_FRONT, W_REAR]:
        w.fit()
    g, gf, gs = Geo(), Geo(), Geo()
    for w in W_SIDE:
        w.panes(g, gf)
        w.seal(gs)
    sheet(g, "glass.side", mirror=True)
    frit(gf, "frit.side", mirror=True)
    gs.obj("seal.side", "rubber", bevel=0.0012, mirror=True)
    g, gf, gs = Geo(), Geo(), Geo()
    for w in (W_FRONT, W_REAR):
        w.panes(g, gf, 0.05)
        w.seal(gs)
    sheet(g, "glass.ends")
    frit(gf, "frit.ends")
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
# the ends: bumpers, fog and reverse lamps, plates, badges
# ---------------------------------------------------------------------------------------
def small_lamp(name, proj, u, v, a, b, r, cups, cup_r, lit="lamp", glass="lens_clear",
               base=0.012, mirror=False):
    """A lamp standing on a bumper pad (its face base over the skin): a dark housing plate,
    a chrome back, LED cups and a block of clear lens over them (no ring of a bezel, which
    a game pack's far LOD fills into a lid)."""
    L = K.Lamp(name, lit=lit, glass=glass)
    pad(L.housing, u, v, a + 0.004, b + 0.004, r + 0.004, proj, lift=base - 0.0005,
        sink=-(base - 0.003))
    pad(L.chrome, u, v, a, b, r, proj, lift=base + 0.0005, sink=-(base - 0.002))
    for k in range(cups):
        cu = u + (2 * a - 2.6 * cup_r) * ((k + 0.5) / cups - 0.5)
        loc, n = skin(cu, v, proj)
        L.reflector(loc + n * (base + 0.0045), n, r=cup_r, depth=cup_r * 0.45, seg=16,
                    led=cup_r * 0.55)
    pad(L.glass, u, v, a, b, r, proj, lift=base + 0.0065, sink=-(base + 0.0006))
    L.obj(mirror=mirror)


def build_ends():
    for proj, tag, zb in (('x', "front", 0.42), ('X', "rear", 0.415)):
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
    small_lamp("lamp.fog", 'x', 0.455, 0.375, 0.047, 0.023, 0.012, 2, 0.0105, mirror=True)
    tanager.plate('x', 0.0, 0.475, "VB 07-717", low=0.55)
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

    # ---- rear: reflectors, reverse lamp, plate, lettering
    g = Geo()
    for y in (0.44, -0.44):
        pad(g, y, 0.445, 0.085, 0.018, 0.012, 'X', lift=0.0135)
    g.obj("reflectors", "reflector", bevel=0.001)
    small_lamp("lamp.reverse", 'X', 0.0, 0.352, 0.058, 0.0145, 0.009, 3, 0.0085)
    tanager.plate('X', 0.0, 0.655, "VB 07-717", low=0.55)
    # the high stop lamp over the rear window: a dark plate on the skin, a lit bar on a
    # chrome strip in a block of red lens (a pocket here, where the tail rolls into the roof,
    # left stars in the paint's shading)
    S = K.Lamp("lamp.stop", lit="led_rear", glass="lens_red")
    pad(S.housing, 0, 1.418, 0.174, 0.0155, 0.012, 'X', lift=0.0012, sink=0.002)
    pad(S.chrome, 0, 1.418, 0.168, 0.011, 0.009, 'X', lift=0.0018, sink=0.0)
    P, U = under(dense([(-0.16, 1.418), (0.16, 1.418)], 0.02, closed=False), 'X', -0.0035)
    S.bar(P, 0.012, 0.003, up=U)
    pad(S.glass, 0, 1.418, 0.170, 0.0125, 0.010, 'X', lift=0.0068, sink=-0.0019)
    S.obj()
    g = Geo()
    text_proj(g, "MINO", 0.062, 0.40, 0.735, 'X', spacing=1.1)
    text_proj(g, "tanager", 0.030, -0.42, 0.75, 'X', spacing=1.05)
    text_proj(g, "CITY SHARE  E-4", 0.014, -0.42, 0.715, 'X', spacing=1.15)
    text_proj(g, "UNIT 07", 0.016, 0.40, 0.685, 'X', spacing=1.2)
    g.obj("lettering.rear", "decal")
    badge('X', 0.0, 0.757, 0.034)
    badge('z', 1.615, 0.0, 0.034)


# ---------------------------------------------------------------------------------------
# the flanks: arches, strips, mirrors, markings
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
    # ---- the charge door (cut in cutters()): a lit bolt, a label
    gp, gt = Geo(), Geo()
    dots(gp, GLYPH["z"], 1.345, 0.778, 0.006, 'y', 0.001, 0.0045)
    gp.obj("charge.bolt", "pixel")
    K.text_on_body(gt, "CHARGE 11 KW", 0.011, 1.33, 0.708, 1, spacing=1.2)
    gt.obj("charge.label", "decal")
    # ---- washer jets in front of the windshield
    g = Geo()
    for y in (0.20, -0.20):
        loc, n = skin(1.215, y, 'z')
        stud(g, loc, n, [(-0.001, 0.001), (-0.001, 0.007), (0.006, 0.005), (0.007, 0.001)], 12)
    g.obj("washer.jets", "gloss_black")


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
    """The cabin tub, kept inside the hull and out of the wheel wells (the wells' walls
    at WELL_Y, their arches up to 0.625 m): over the wells only its middle reaches down."""
    g = Geo()
    yi = WELL_Y - 0.01
    g.box((-0.20, 0, 0.255), (2.62, 2 * yi, 0.03))                  # floor, its middle
    dash = [(1.10, 0.27), (1.10, 0.985), (0.84, 0.995), (0.70, 0.93), (0.74, 0.27)]
    g.prism([(x, -yi, z) for x, z in dash], (0, 2 * yi, 0))        # dash
    dash_out = [(1.10, 0.66), (1.10, 0.985), (0.84, 0.995), (0.70, 0.93), (0.74, 0.27),
                (0.86, 0.27), (0.86, 0.66)]
    for sg in (1, -1):
        y0 = sg * yi
        g.box((0.0, sg * (yi + 0.70) / 2, 0.255), (1.72, 0.70 - yi, 0.03))      # floor
        g.prism([(x, y0, z) for x, z in dash_out], (0, sg * (0.70 - yi), 0))  # dash
        g.box((-1.085, sg * (yi + 0.68) / 2, 0.795), (0.03, 0.68 - yi, 0.27))  # boot wall
        g.box((0.0, sg * 0.715, 0.615), (1.72, 0.02, 0.65))         # door cards
        g.box((-1.15, sg * 0.715, 0.80), (0.58, 0.02, 0.28))        # quarter cards
        g.box((0.93, sg * 0.715, 0.80), (0.14, 0.02, 0.28))
    g.box((-1.30, 0, 0.93), (0.44, 1.36, 0.02))                     # parcel shelf
    g.box((-1.085, 0, 0.60), (0.03, 2 * yi, 0.66))                  # the boot's wall
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
    K.need("lamp_housing", "chrome", "lens_clear", "lens_smoke", "lens_red", "lens_amber",
           "optic", "frit")
    K.meant("symmetry", "interior.wheel", "interior.screens", "antenna", "tow.*", "wipers",
            "permit*", "display*", "pixels*", "charge.*", "body.fender")
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
