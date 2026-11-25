"""Tanager Linnet: a compact five-door hatchback, the car most people in the city drive
(both names made up), built on vehicles/carkit.py.

Run (always through the wrapper, one Blender job at a time on this machine):
    vehicles/blender.sh vehicles/cars/tanager_linnet.py --out DIR --preview
    vehicles/blender.sh vehicles/cars/tanager_linnet.py --out DIR --sheet

The Mino's longer, lower sibling (docs/progress/AG18/tanager_linnet/README.md): the family's
soft box with the wheels at its corners, but a two-box hatchback: a hood that falls to a
leaning nose, a cab-forward windshield 45 degrees off upright with a quarter light in each
front door's sail, a roof that arches a little and ends in a spoiler, a glass hatch leaning
47 degrees over a short ledge and an upright tail. A soft shoulder runs under the belt from
the front fender to the tail lamps and the doors are drawn in a little under it, so the
flanks are not slabs. Tanager's cues are all here: flat glass in rounded openings with fat
seals and a frit border, a visor across each end (one light bar between two rounded lamps
and a dot-matrix display, under a clear lens), squircle arches in grained cladding with a
bump strip, steel wheels under slotted covers, a white cap roof with its gear, a roundel and
service lettering.

The body is twelve lines over twenty stations. The windows are holes cut through the skin
with the glass and its seal laid behind them on the skin as built; everything else cut into
the skin is laid on the hull as it stands uncut (cutters()). The brand's helpers are in
vehicles/brands/tanager.py.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import bmesh                                                        # noqa: E402
import carkit as K                                                  # noqa: E402
import cabin as C                                                   # noqa: E402
from functools import partial                                       # noqa: E402
from brands import tanager                                          # noqa: E402
from brands.tanager import (GD, GLYPH, badge, banner, bar_on, dots, grain, pad,   # noqa: E402
                            rect, rrect, sheet, text_proj)
from carkit import Geo, Matrix, V3, cos, hypot, rad, stud              # noqa: E402

# ---------------------------------------------------------------------------------------
# dimensions
# ---------------------------------------------------------------------------------------
FA_X, RA_X = 1.40, -1.34            # axles: wheelbase 2.74
T_R, T_W, T_RIM, T_OUT = 0.335, 0.205, 0.22, 0.855     # tire radius, width, rim, outer face
ARCH = (0.395, 0.39, 0.34, 3.2)    # squircle arch: half width, rise, center height, exponent
ARCH_A = ARCH[0]
WELL_Y = 0.50                       # the wells' inner walls
BELT, HEAD = 0.96, 1.44            # belt line and glass header
NUM = "24"
GAP = 0.00175                       # shut lines 3.5 mm
FRIT = 0.04                         # the frit border on the glass, from its edge
HULL_ONLY = bool(os.environ.get("LINNET_HULL"))

arch_pts = partial(tanager.arch_pts, arch=ARCH)
TREAD = dict(grooves=(-0.17, 0.0, 0.17), gw=(0.010, 0.006), gd=0.008, mod=4, shift=2,
             inset=(0.002, 0.006), seg=144)
"""A road tread for a 0.205 m tire: the kit's "road" grooves (0.24 of the width out, 12 mm
half wide) reach past such a tire's crown, its profile folds and the blocks stand 7 mm under
the ground; these three grooves stay on the crown."""
build_wheel = partial(tanager.wheel, R=T_R, w=T_W, rim=T_RIM, out=T_OUT, tread=TREAD)
LATE = {}                           # what cutters() lays inside the cuts, made after the build


class BODY:                         # the hull's panels, once built
    parts = {}

FAR = {'x': lambda p: p.x < 0.3, 'X': lambda p: p.x > -1.2, 'y': lambda p: p.y < 0.3,
       'Y': lambda p: p.y > -0.3, 'z': lambda p: False}
_skin = tanager.skin


def skin(u, v, proj):
    """The brand's skin(), but a ray that slips through a shut line and meets the inside of
    the body far behind it looks beside it, as one that misses does. Set as the brand
    module's own, so its pads use it too."""
    for du, dv in ((0, 0), (0, 0.004), (0, -0.004), (0.004, 0), (-0.004, 0), (0, 0.009),
                   (0, -0.009), (0.009, 0), (-0.009, 0)):
        loc, n = K.on_body(u + du, v + dv, proj)
        if loc is not None and not FAR[proj](loc):
            return loc, n
    return _skin(u, v, proj)


tanager.skin = skin


def nose_x(z):
    """The nose is one plane, leaning back five degrees."""
    return 2.085 - (z - 0.31) * 0.09


def tail_x(z):
    """The tail under the hatch's ledge is one plane, leaning forward three degrees."""
    return -2.07 + (z - 0.31) * 0.055


class LWin(tanager.Win):
    """The Linnet's windows: its body's cutter planes, and flat glass with a frit border
    (the glass's own thickness, no gap between them)."""

    CUT = dict(y=(0.55, 0.6), x=(0.55, 1.1), X=(-1.40, -1.0))

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
LINES = "CQRHGSKUVMFB"
#        C top centerline, Q roof / hood inner, R roof edge, H glass header / fender crown,
#        G belt, S shoulder (the widest line, a soft crease), K the scallop under it (drawn
#        in along the doors), U foot of the paint, V top of the cladding (a step out),
#        M rocker, F floor edge, B floor centerline
ORDER = ["NC", "N0", "N1", "N2", "A1", "W0", "WS", "RF", "RG", "D1", "DM", "D2", "RA", "RH",
         "HT", "HG", "HB", "T1", "T0", "TC"]
#        NC and TC are rings inside the nose and tail faces (their outlines N0 and T0 drawn
#        in by a fifth), so the faces stay flat and full size out to their rounded edges.
#        The shut lines' stations (W0, D1, D2) stand midway between their neighbors on every
#        line, so subdivision builds them where they stand, creased or not.
PT = {}
SCALLOP = 0.020                     # how far the doors are drawn in under the shoulder


def low(x, k=1.0):
    """The flank under the belt at x: belt, shoulder, scallop (k: its share), the
    cladding's step, rocker, floor."""
    return [(x, .822, BELT), (x, .866, .84), (x, .8645 - k * SCALLOP, .68), (x, .862, .52),
            (x, .875, .505), (x, .862, .27), (x, .72, .18), (x, 0, .18)]


def cabin(x, zc, k=1.0):
    return [(x, 0, zc), (x, .42, zc - .008), (x, .62, zc - .038), (x, .725, HEAD)] + low(x, k)


NOSE = [(0, .84), (.44, .838), (.63, .822), (.705, .785), (.742, .715), (.755, .63),
        (.757, .575), (.755, .52), (.765, .505), (.725, .37), (.59, .31), (0, .31)]
TAIL = [(0, .965), (.42, .965), (.62, .95), (.705, .91), (.745, .84), (.76, .74), (.762, .63),
        (.76, .52), (.77, .505), (.73, .37), (.59, .31), (0, .31)]


def inner(pts, zc, s=0.8, zlow=0.5125):
    """A face's outline drawn in toward its middle (below the cladding's step toward zlow,
    so the step stays level across the face)."""
    return [(y * s, (zc if j < 7 else zlow) + (z - (zc if j < 7 else zlow)) * s)
            for j, (y, z) in enumerate(pts)]


def stations():
    def ring(x, pts):
        return [(x(z), y, z) for (y, z) in pts]
    T = {
        "NC": ring(nose_x, inner(NOSE, .69)),
        "N0": ring(nose_x, NOSE),
        "N1": [(2.015, 0, .872), (2.015, .44, .869), (2.005, .64, .852), (1.995, .725, .815),
               (1.985, .785, .75), (1.98, .815, .665), (1.982, .814, .59), (1.985, .81, .52),
               (1.99, .823, .505), (2.0, .79, .33), (2.01, .63, .25), (2.015, 0, .25)],
        "N2": [(1.88, 0, .904), (1.88, .44, .892), (1.88, .64, .877), (1.88, .76, .843),
               (1.88, .835, .80), (1.88, .864, .735), (1.88, .863, .63), (1.88, .86, .52),
               (1.88, .873, .505), (1.88, .855, .28), (1.88, .71, .19), (1.88, 0, .19)],
        "A1": [(FA_X, 0, 1.0), (FA_X, .44, .98), (FA_X, .64, .968), (FA_X, .775, .93),
               (FA_X, .838, .885), (FA_X, .866, .825)] + low(FA_X, 0.0)[2:],
        "W0": [(1.22, 0, 1.035), (1.22, .46, 1.029), (1.212, .64, 1.02), (1.15, .80, .995),
               (.93, .822, .95)] + low(.93)[1:],
        "WS": [(.80, 0, 1.46), (.80, .46, 1.457), (.792, .62, 1.438), (.72, .722, 1.375)]
        + low(.46),
        "RF": [(.72, 0, 1.52), (.72, .44, 1.515), (.71, .615, 1.49), (.66, .724, 1.428)]
        + low(.36),
        "RG": cabin(.26, 1.535),
        "D1": cabin(-.12, 1.548), "DM": cabin(-.50, 1.55), "D2": cabin(-.88, 1.542),
        "RA": cabin(-1.26, 1.525, 0.3),
        "RH": [(-1.40, 0, 1.508), (-1.40, .42, 1.501), (-1.40, .615, 1.473),
               (-1.40, .72, 1.415)] + [None] * 8,
        "HT": [(-1.49, 0, 1.475), (-1.49, .42, 1.47), (-1.485, .61, 1.447),
               (-1.47, .715, 1.39)] + [None] * 8,
        "HG": [(-1.56, 0, 1.418), (-1.56, .44, 1.415), (-1.552, .605, 1.40),
               (-1.53, .71, 1.345)] + [None] * 8,
        "HB": [(-1.975, 0, 1.03), (-1.975, .46, 1.03), (-1.967, .62, 1.022), (-1.92, .74, 1.0),
               (-1.87, .815, .945), (-1.87, .858, .835), (-1.87, .856, .68), (-1.87, .852, .52),
               (-1.87, .865, .505), (-1.87, .85, .28), (-1.87, .71, .19), (-1.87, 0, .19)],
        "T1": [(-2.04, 0, .995), (-2.04, .42, .995), (-2.035, .63, .985), (-2.02, .725, .955),
               (-2.0, .79, .90), (-1.99, .825, .80), (-1.995, .823, .66), (-2.0, .82, .52),
               (-2.005, .833, .505), (-2.015, .80, .33), (-2.02, .64, .25), (-2.025, 0, .25)],
        "T0": ring(tail_x, TAIL),
        "TC": ring(tail_x, inner(TAIL, .75)),
    }
    S = K.fill([T[k] for k in ORDER])
    PT.update(K.table(ORDER, LINES, S))
    return S


NS = len(ORDER)
I = {k: i for i, k in enumerate(ORDER)}


def panel_of(i, j):
    if i in (0, NS - 2) and j < 7:      # the faces: body color down to the cladding's step
        return "nose" if i == 0 else "gate"
    if j == 10 and i not in (0, NS - 2):
        return "floor"
    if j >= 7:
        return ("clad_f" if i < I["W0"] else "clad_d1" if i < I["D1"] else
                "clad_d2" if i < I["D2"] else "clad_r")
    if i == 1:
        return "nose"
    if i == NS - 3:
        return "gate"
    if i < I["W0"]:
        return "hood" if j <= 1 else "fender"
    if j <= 2:
        if i < I["RF"]:
            return "screen"
        if i < I["HT"]:
            return "roof"
        return "gate" if j <= 1 else "quarter"
    return "door_f" if i < I["D1"] else "door_r" if i < I["D2"] else "quarter"


PMAT = dict(nose="paint", hood="paint", fender="paint", screen="paint", roof="paint2",
            door_f="paint", door_r="paint", quarter="paint", gate="paint",
            clad_f="plastic", clad_d1="plastic", clad_d2="plastic", clad_r="plastic",
            floor="underbody", well="well", wincut="void",
            visor_f="void", visor_r="void", rep_h="void", slot="plastic", cut="void")


def line_crease(i, j):
    """Crease of the edge along line j from station i to i + 1."""
    if j in (7, 8):
        return 1.0                      # the cladding's step, also across the two faces
    if i in (0, NS - 2):
        return 0.0
    mid = 2 <= i <= NS - 4
    if j == 10:                         # the floor edge
        return 1.0 if mid else 0.4
    if j == 9:
        return 0.5 if mid else 0.2
    if j == 5:                          # the shoulder
        return 0.3 if 3 <= i <= NS - 5 else 0.1
    if j == 4:
        return 0.35 if i >= I["W0"] and i < I["HB"] else 0.2
    if j == 3:
        return 0.5 if i >= I["W0"] and i < I["HB"] else 0.3
    if j == 2:
        return 0.25 if i >= I["W0"] and i < I["HB"] else 0.0
    return 0.0


def station_crease(i, j):
    """Crease of the edge on station i between lines j and j + 1."""
    if i in (0, NS - 1):                # the faces' inner rings: the cladding's step held
        return 1.0 if j == 7 else 0.0   # where it ends (its end rose 3 cm in a hook)
    if i == I["W0"]:
        return 0.7 if j <= 2 else 0.0   # the cowl
    if i == I["RF"]:
        return 0.3 if j <= 1 else 0.0   # the windshield's header
    if i == I["HB"]:
        return 0.6 if j <= 2 else 0.0   # the foot of the hatch's glass
    if i == I["HT"]:
        return 0.3 if j <= 1 else 0.0
    return 0.0


W_SIDE = [LWin([(1.04, 1.0), (.735, 1.28), (.90, 1.0)], [.03, .02, .03], 'y'),
          LWin([(.84, 1.0), (.62, 1.37), (-.07, 1.37), (-.07, 1.0)], [.05, .07, .07, .07],
               'y'),
          LWin(rect(-.50, 1.185, .33, .185), .07, 'y'),
          LWin([(-.93, 1.0), (-.93, 1.37), (-1.32, 1.37), (-1.73, 1.0)],
               [.07, .07, .10, .05], 'y')]
W_FRONT = LWin([(-.60, 1.09), (.60, 1.09), (.56, 1.425), (-.56, 1.425)], .075, 'x')
W_REAR = LWin([(-.57, 1.10), (.57, 1.10), (.53, 1.378), (-.53, 1.378)], .075, 'X')


# ---------------------------------------------------------------------------------------
# the cuts, laid on the hull as it stands uncut, and what stands inside them
# ---------------------------------------------------------------------------------------
VIS = dict(front=('x', 0.70, "led_front", "pixel", "z 76%"),      # the visors: projection,
           rear=('X', 0.835, "led_rear", "pixel_r", "CLUB 24"))     # middle height, lights
VW, VH = 0.70, 0.076                # a visor's half width and half height
LAMP_U = 0.585                      # the lamps' middles


def frame_on(g, outline, proj, w, z0, z1):
    """A wall w thick along a closed outline on the skin, from z0 to z1 over it."""
    P, U = under(dense(outline), proj, 0.0)
    g.sweep(P, [(-w / 2, z0), (w / 2, z0), (w / 2, z1), (-w / 2, z1)], up=U, closed=True)


def visor(tag):
    """A visor: a hole across the face (the paint's own 14 mm rim its walls, a gloss black
    back plate closing it 14 mm in), a gloss black surround standing 9.5 mm proud round its
    edge and a clear lens in it, all laid on the skin as it stands uncut. The lamps stand in
    the hole with their lit faces 2 to 4 mm proud of the skin, under the lens (the Mino's
    way, which a game pack's far LOD keeps). At each end a lamp of a chrome plate, a lit
    ring of light guide and two reflector cups side by side on a dark tray; the light bar
    between them, a guide on a chrome strip; the display on the car's left, a screen with its
    lit dots under a smoked lens of its own."""
    proj, cv, lit, pix, msg = VIS[tag]
    t = tag[0]
    sg = -1.0 if proj == 'X' else 1.0          # the car's left as this view's u
    g, lens = Geo(), Geo()
    K.pocket(g, K.rounded(0.0, cv, 2 * VW + 0.004, 2 * VH + 0.012, 0.05), proj, depth=0.03)
    frame_on(lens, rrect(0, cv, VW - 0.0015, VH + 0.0035, 0.0485), proj, 0.008, -0.004, 0.0095)
    glass = Geo()
    pad(glass, 0, cv, VW - 0.005, VH, 0.045, proj, lift=0.009, sink=-0.006, nv=10, nc=8,
        step=0.01)
    back = Geo()
    pad(back, 0, cv, VW + 0.007, VH + 0.012, 0.052, proj, lift=-0.0140, sink=0.0175, nv=6)
    # the lamps at each end (the left one, mirrored)
    E = K.Lamp("lamp.%s" % tag, lit=lit, optic="lens_red" if t == "r" else "optic")
    pad(E.chrome, LAMP_U, cv, 0.094, 0.060, 0.030, proj, lift=-0.003, sink=0.004)
    P, U = under(dense(rrect(LAMP_U, cv, 0.083, 0.049, 0.024)), proj, -0.0005)
    E.guide(P, r=0.0034, sleeve=1.6, closed=True, up=U)
    pad(E.housing, LAMP_U, cv, 0.070, 0.037, 0.018, proj, lift=-0.002, sink=0.0029)
    for u in (LAMP_U - 0.033, LAMP_U + 0.033):
        loc, n = skin(u, cv, proj)
        E.reflector(loc + n * 0.0025, n, r=0.0245, depth=0.011, seg=20, led=0.008)
    # the light bar: a guide on a chrome strip
    bw = LAMP_U - 0.118
    B = K.Lamp("lamp.%s_bar" % tag, lit=lit, optic="lens_red" if t == "r" else "optic")
    P, U = under(dense([(-bw, cv + 0.036), (bw, cv + 0.036)], 0.02, closed=False), proj, 0.0)
    B.guide(P, r=0.0038, sleeve=1.45, up=U)
    pad(B.chrome, 0, cv + 0.036, bw + 0.002, 0.0115, 0.008, proj, lift=-0.004, sink=0.005)
    # the display under its own smoked lens
    du, dv = sg * 0.26, cv - 0.026
    sc, px, ln = Geo(), Geo(), Geo()
    pad(sc, du, dv, 0.141, 0.038, 0.016, proj, lift=0.001, sink=0.004)
    dots(px, banner(msg), du, dv, 0.0062, proj, 0.002, 0.0045)
    pad(ln, du, dv, 0.139, 0.036, 0.015, proj, lift=0.0047, sink=-0.0035)
    LATE[tag] = (lens, glass, back, E, B, sc, px, ln, pix)
    return g


PULLS = (0.02, -0.75)               # the door pulls' middles
PULL_Z = 0.905
FLAP = (1.135, 0.862, 0.068, 0.043)     # the charge door: middle, half sizes


def cutters():
    """Everything cut into the hull: the wheel wells, the windows (holes), the visors
    (housings under lenses), the handle recesses and the charge door (a shut line)."""
    wells, wins = Geo(), Geo()
    for cx in (FA_X, RA_X):
        for sg in (1, -1):
            pts = arch_pts(cx)
            poly = [(pts[0][0], sg * WELL_Y, -0.3)] + [(x, sg * WELL_Y, z) for x, z in pts]
            poly.append((pts[-1][0], sg * WELL_Y, -0.3))
            wells.prism(poly, (0, sg * 0.5, 0))
    for w in W_SIDE + [W_FRONT, W_REAR]:
        w.cut(wins)
    if HULL_ONLY:
        return [(wells, "well"), (wins, "wincut", "drop")]
    vf, vr = visor("front"), visor("rear")
    build_ends()                        # on the faces before they are split into panels
    # handle recesses: a cup under each pull, the pull's ends on the skin past it
    pulls, gp = Geo(), Geo()
    for x in PULLS:
        K.pocket(pulls, K.rounded(x, PULL_Z - 0.012, 0.10, 0.042, 0.018), 'y', depth=0.014,
                 mirror=True)
        pad(gp, x, PULL_Z, 0.060, 0.0095, 0.009, 'y', lift=0.009)
    LATE["pulls"] = gp
    # a shut line: the charge door on the left front fender
    cut = Geo()
    K.groove(cut, rrect(FLAP[0], FLAP[1], FLAP[2], FLAP[3], 0.02), 'y', closed=True)
    return [(wells, "well"), (wins, "wincut", "drop"), (vf, "visor_f", "drop"),
            (vr, "visor_r", "drop"), (pulls, "slot"), (cut, "cut", "drop")]


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
    if HULL_ONLY:
        return body
    paint = [pn for pn, mt in PMAT.items() if mt.startswith("paint") and pn in body.parts]
    folds = {pn: unfold(body.parts[pn]) for pn in paint}
    K.log("folds taken out: %s" % {k: v for k, v in folds.items() if v})
    for pn, n in (("nose", V3((1.0, 0.0, 0.09)).normalized()),
                  ("gate", V3((-1.0, 0.0, 0.055)).normalized())):
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
    LATE["pulls"].obj("handle.pulls", "paint", bevel=0.002, mirror=True)
    BODY.parts = body.parts
    return body


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
    for k, w in enumerate(W_SIDE):
        w.panes(g, gf, 0.022 if k == 0 else FRIT)
        w.seal(gs)
    sheet(g, "glass.side", mirror=True)
    frit(gf, "frit.side", mirror=True)
    gs.obj("seal.side", "rubber", bevel=0.0012, mirror=True)
    g, gf, gs = Geo(), Geo(), Geo()
    for w in (W_FRONT, W_REAR):
        w.panes(g, gf, 0.05)
        w.seal(gs)
    ends = sheet(g, "glass.ends")
    frit(gf, "frit.ends")
    gs.obj("seal.ends", "rubber", bevel=0.0012)
    if HULL_ONLY:
        return
    # one big wiper in front, a small one behind (the kit's, laid on the glass as built)
    arm, blade = Geo(), Geo()
    on = [ends, BODY.parts["screen"], BODY.parts["gate"]]
    for w, piv, a, b in ((W_FRONT, (-.06, 1.068), (-.17, 1.128), (.50, 1.152)),
                         (W_REAR, (0.0, 1.078), (.04, 1.13), (.37, 1.15))):
        K.wiper(arm, blade, w.at(*piv, 0.003), w.at(*a, -GD + 0.003), w.at(*b, -GD + 0.003),
                objs=on, out=w.n)
    arm.obj("wipers", "cladding", bevel=0.0008)
    blade.obj("wipers.blades", "rubber")


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
    """What lies on the nose and the tail. Called from cutters(), while the hull stands
    uncut and whole: the bumper pads lie across the faces' panels (the paint above the
    cladding's step, the plastic below it), and a ray that fell into the gap between two
    panels would dent them."""
    ZB = 0.43                                   # the bumper pads' middle height
    for proj, tag, fx, fn in (('x', "front", nose_x, V3((1.0, 0.0, 0.09)).normalized()),
                              ('X', "rear", tail_x, V3((-1.0, 0.0, 0.055)).normalized())):
        # bumper: a grained pad (a plate in the face's own plane: laid on the skin its end
        # would kink over the cladding's step), rubber guards on its corners, sensors
        g = Geo()
        g.prism([V3((fx(z), y, z)) - fn * 0.004 for y, z in rrect(0, ZB, 0.69, 0.118, 0.024)],
                fn * 0.016)
        g.obj("bumper." + tag, "plastic", bevel=0.004)
        g = Geo()
        for y in (0.615, -0.615):
            pad(g, y, ZB, 0.028, 0.075, 0.02, proj, lift=0.019)
        g.obj("bumper.guards." + tag, "rubber", bevel=0.004)
        g = Geo()
        for y in (0.22, 0.54, -0.22, -0.54):
            loc, n = skin(y, ZB + 0.066, proj)
            stud(g, loc + n * 0.012, n, [(-0.002, 0.001), (-0.002, 0.011), (0.0015, 0.011),
                                         (0.0015, 0.001)], 12)
        g.obj("sensors." + tag, "gloss_black")

    # ---- front: intake slot with slats, plate, fog lamps, tow eye cover, badge
    g, gs = Geo(), Geo()
    pad(g, 0, 0.368, 0.40, 0.034, 0.03, 'x', lift=0.0124)
    g.obj("intake", "void")
    for z in (0.349, 0.368, 0.387):
        bar_on(gs, [(-0.375, z), (0.375, z)], 'x', 0.009, 0.0035, lift=0.0124)
    gs.obj("intake.slats", "plastic", bevel=0.001)
    small_lamp("lamp.fog", 'x', 0.535, 0.378, 0.052, 0.023, 0.012, 2, 0.0105, mirror=True)
    tanager.plate('x', 0.0, 0.475, "VB 24-309", low=0.55)
    g = Geo()
    loc, n = skin(-0.40, 0.475, 'x')
    stud(g, loc + n * 0.012, n, [(-0.001, 0.001), (-0.001, 0.026), (0.003, 0.024), (0.003, 0.001)],
         20)
    g.obj("tow.cover", "plastic", bevel=0.001)
    badge('x', 0.0, 0.578, 0.031)

    # ---- rear: reflectors, reverse lamp, plate, lettering
    g = Geo()
    for y in (0.50, -0.50):
        pad(g, y, 0.45, 0.085, 0.018, 0.012, 'X', lift=0.0135)
    g.obj("reflectors", "reflector", bevel=0.001)
    small_lamp("lamp.reverse", 'X', 0.0, 0.352, 0.058, 0.0145, 0.009, 3, 0.0085)
    tanager.plate('X', 0.0, 0.455, "VB 24-309", low=0.55)
    g = Geo()
    text_proj(g, "LINNET", 0.058, 0.43, 0.655, 'X', spacing=1.12)
    text_proj(g, "tanager", 0.030, -0.44, 0.668, 'X', spacing=1.05)
    text_proj(g, "DRIVE CLUB  E-5", 0.014, -0.44, 0.632, 'X', spacing=1.15)
    g.obj("lettering.rear", "decal")
    badge('X', 0.0, 0.652, 0.034)
    # the hatch's grip over the plate (a lit pad in a dark cup), the reversing camera
    g, gl = Geo(), Geo()
    pad(g, 0.0, 0.566, 0.085, 0.014, 0.012, 'X', lift=0.006)
    g.obj("hatch.grip", "plastic", bevel=0.002)
    pad(gl, 0.0, 0.566, 0.030, 0.005, 0.004, 'X', lift=0.0068, sink=-0.004)
    gl.obj("hatch.grip.light", "pixel_r")
    g = Geo()
    loc, n = skin(0.155, 0.566, 'X')
    stud(g, loc, n, [(-0.002, 0.001), (-0.002, 0.014), (0.006, 0.012), (0.008, 0.006),
                     (0.008, 0.001)], 16)
    g.obj("hatch.camera", "gloss_black")


# ---------------------------------------------------------------------------------------
# the flanks: arches, strips, mirrors, markings
# ---------------------------------------------------------------------------------------
def build_sides():
    # ---- squircle arch trims in the cladding's plastic
    g = Geo()
    for cx in (FA_X, RA_X):
        n = 31
        ring = [(x, y, z) for y in (0.835, 0.889)
                for grow in (-0.006, 0.048) for (x, z) in arch_pts(cx, grow)]
        fs = []
        for k in range(n - 1):
            i0, i1, o0, o1 = k, k + 1, n + k, n + k + 1
            fs += [(i0, i1, o1, o0), (2 * n + i0, 2 * n + i1, 2 * n + o1, 2 * n + o0),
                   (i0, i1, 2 * n + i1, 2 * n + i0), (o0, o1, 2 * n + o1, 2 * n + o0)]
        fs += [(0, n, 3 * n, 2 * n), (n - 1, 2 * n - 1, 4 * n - 1, 3 * n - 1)]
        g.add(ring, fs)
    g.obj("arch.trims", "plastic", bevel=0.005, mirror=True)
    # ---- bump strips on the doors' cladding (one a door), mud flaps
    g, gl = Geo(), Geo()
    for x0, x1 in ((0.885, -0.10), (-0.14, -0.845)):
        bar_on(g, [(x0, 0.395), (x1, 0.395)], 'y', 0.06, 0.011)
        for z in (0.382, 0.408):
            bar_on(gl, [(x0 - 0.02, z), (x1 + 0.02, z)], 'y', 0.004, 0.0125)
    g.obj("bump.strip", "plastic", bevel=0.004, mirror=True)
    gl.obj("bump.lines", "rubber", mirror=True)
    g = Geo()
    for cx in (FA_X, RA_X):
        g.box((cx - ARCH_A - 0.012, 0.775, 0.225), (0.012, 0.17, 0.23))
    g.obj("mudflaps", "rubber", bevel=0.003, mirror=True)
    # ---- mirrors on the doors under the quarter lights: a foot, an arm, a pod with its
    # glass and a repeater
    g, gm, ga, gt = Geo(), Geo(), Geo(), Geo()
    loc, n = skin(1.0, 0.953, 'y')
    foot = loc + n * 0.003
    g.hexa([foot + V3(d) for d in ((0.062, -0.012, -0.024), (-0.062, -0.012, -0.024),
                                    (-0.062, -0.012, 0.024), (0.062, -0.012, 0.024),
                                    (0.045, 0.022, -0.016), (-0.040, 0.022, -0.016),
                                    (-0.040, 0.022, 0.018), (0.045, 0.022, 0.018))])
    g.hexa([foot + V3(d) for d in ((0.040, 0.012, -0.014), (-0.030, 0.012, -0.014),
                                    (-0.030, 0.012, 0.016), (0.040, 0.012, 0.016),
                                    (0.030, 0.060, 0.030), (-0.034, 0.060, 0.030),
                                    (-0.034, 0.060, 0.062), (0.030, 0.060, 0.062))])
    g.obj("mirror.feet", "plastic", bevel=0.005, mirror=True)
    pc = foot + V3((-0.002, 0.098, 0.088))      # the pod's middle
    gm.hexa([pc + V3(d) for d in ((-0.040, -0.086, -0.058), (-0.040, 0.086, -0.052),
                                   (-0.040, 0.086, 0.056), (-0.040, -0.086, 0.060),
                                   (0.052, -0.080, -0.044), (0.026, 0.074, -0.036),
                                   (0.026, 0.074, 0.038), (0.052, -0.080, 0.046))])
    gm.obj("mirror.pods", "paint", bevel=0.020, segs=3, mirror=True)
    ga.box(pc + V3((-0.0405, 0.0, 0.002)), (0.004, 0.136, 0.082))
    ga.obj("mirror.glass", "mirror", bevel=0.001, mirror=True)
    gt.box(pc + V3((0.036, 0.0, -0.024)), (0.014, 0.10, 0.010),
           rot=Matrix.Rotation(rad(-9), 3, 'Z'))
    gt.obj("led.turn", "led_accent", mirror=True)
    # ---- fleet roundel on the front doors, lettering
    g = Geo()
    pad(g, 0.48, 0.715, 0.105, 0.105, 0.105, 'y', lift=0.0025, nc=12, nv=8)
    g.obj("roundel", "paint2", bevel=0.001, mirror=True)
    g, gw = Geo(), Geo()
    for side in (1, -1):
        K.text_on_body(g, NUM, 0.125, 0.48, 0.715, side, lift=0.0036)
        K.text_on_body(gw, "LINNET", 0.070, -0.50, 0.745, side, spacing=1.12)
        K.text_on_body(gw, "TANAGER DRIVE CLUB", 0.021, -0.50, 0.678, side, spacing=1.2)
        K.text_on_body(gw, "UNIT 24   ZONE 2   BOOK BY THE HOUR", 0.012, -0.50, 0.644, side,
                       spacing=1.2)
        K.text_on_body(gw, "2.5 BAR", 0.013, RA_X, 0.815, side, spacing=1.15)
        K.text_on_body(gw, "2.3 BAR", 0.013, FA_X, 0.815, side, spacing=1.15)
        proj = 'y' if side > 0 else 'Y'
        for x in (0.80, -0.78):                 # jack points on the cladding
            tri = [skin(x + dx, 0.46 + dz, proj) for dx, dz in ((-0.016, 0.014), (0.016, 0.014),
                                                                (0.0, -0.014))]
            gw.add([p + n * 0.0015 for p, n in tri], [(0, 1, 2)])
    g.obj("roundel.number", "mark")
    gw.obj("lettering.side", "decal")
    # ---- the charge door (cut in cutters()): a lit bolt, a label
    gp, gt = Geo(), Geo()
    dots(gp, GLYPH["z"], FLAP[0] + 0.012, FLAP[1] + 0.002, 0.006, 'y', 0.001, 0.0045)
    gp.obj("charge.bolt", "pixel")
    K.text_on_body(gt, "CHARGE 22 KW", 0.011, FLAP[0], FLAP[1] - FLAP[3] - 0.018, 1,
                   spacing=1.2)
    gt.obj("charge.label", "decal")
    # ---- the cowl's grille under the wipers, washer jets
    g, gv = Geo(), Geo()
    bar_on(g, [(1.268, -0.50), (1.268, 0.50)], 'z', 0.052, 0.004)
    for k in range(-10, 11):
        y = k * 0.045
        bar_on(gv, [(1.250, y), (1.286, y + 0.004)], 'z', 0.022, 0.0046)
    g.obj("cowl.grille", "plastic", bevel=0.0015)
    gv.obj("cowl.slots", "void")
    g = Geo()
    for y in (0.24, -0.24):
        loc, n = skin(1.34, y, 'z')
        stud(g, loc, n, [(-0.001, 0.001), (-0.001, 0.007), (0.006, 0.005), (0.007, 0.001)], 12)
    g.obj("washer.jets", "gloss_black")


# ---------------------------------------------------------------------------------------
# the roof: rails, a glass panel, the spoiler with its stop lamp, antenna
# ---------------------------------------------------------------------------------------
def build_roof():
    def zr(x, y):
        return skin(x, y, 'z')[0].z
    # low rails lying on the roof's edges, their ends drawn down
    g = Geo()
    for y in (0.535, -0.535):
        P, U = [], []
        n = 40
        for k in range(n + 1):
            x = 0.42 - 1.72 * k / n
            loc, nr = skin(x, y, 'z')
            P.append(loc)
            U.append(nr)
        h = [0.030 * min(1.0, k / 4.0, (n - k) / 4.0) ** 0.5 + 0.002 for k in range(n + 1)]
        vs, fs = [], []
        for k in range(n + 1):
            sd = V3((0, 1, 0))
            vs += [P[k] - sd * 0.019 - U[k] * 0.003, P[k] + sd * 0.019 - U[k] * 0.003,
                   P[k] + sd * 0.013 + U[k] * h[k], P[k] - sd * 0.013 + U[k] * h[k]]
        for k in range(n):
            fs += [(4 * k + j, 4 * k + (j + 1) % 4, 4 * k + 4 + (j + 1) % 4, 4 * k + 4 + j)
                   for j in range(4)]
        fs += [(0, 1, 2, 3), tuple(4 * n + j for j in range(4))]
        g.add(vs, fs)
    g.obj("roof.rails", "plastic", bevel=0.004)
    # the glass panel: a dark pane lying in the roof
    g, gf = Geo(), Geo()
    pad(g, -0.34, 0.0, 0.50, 0.40, 0.09, 'z', lift=0.0035, sink=0.002, nv=8, nc=8)
    g.obj("roof.glass", "roofglass", bevel=0.0015)
    frame_on(gf, rrect(-0.34, 0.0, 0.508, 0.408, 0.096), 'z', 0.012, -0.002, 0.0045)
    gf.obj("roof.glass.seal", "rubber", bevel=0.001)
    # the spoiler: the roof's line run on past the hatch's hinge, part of the hatch (its
    # front edge stands along the gap between the roof and the hatch)
    YS, n = 0.59, 28
    vs, fs, tips = [], [], []
    for k in range(n + 1):
        y = -YS + 2 * YS * k / n
        e = abs(y) / YS
        x0 = -1.4915 + 0.006 * e * e            # the gap, as the cage builds it
        xt = -1.655 + 0.085 * e ** 3            # the tip, drawn forward toward the sides
        a, na = skin(x0 + 0.012, y, 'z')
        za = a.z - 0.0045
        zt = za - 0.13 * (x0 - xt)
        b, nb = skin(-1.548 + 0.035 * e ** 3, y, 'z')
        vs += [V3((x0, y, za)), V3((xt, y, zt)), V3((xt - 0.004, y, zt - 0.007)),
               V3((xt + 0.006, y, zt - 0.014)), b - nb * 0.006, V3((x0, y, za - 0.035))]
        tips.append(V3((xt - 0.0045, y, zt - 0.0072)))
    m = 6
    for k in range(n):
        fs += [(m * k + j, m * k + (j + 1) % m, m * k + m + (j + 1) % m, m * k + m + j)
               for j in range(m)]
    fs += [tuple(range(m)), tuple(m * n + j for j in range(m))]
    g = Geo()
    g.add(vs, fs)
    g.obj("spoiler", "paint", bevel=0.0035)
    S = K.Lamp("lamp.stop", lit="led_rear", glass="lens_red")
    mid = [p for p in tips if abs(p.y) < 0.23]
    S.bar(mid, 0.004, 0.008, up=(1, 0, 0))
    S.obj()
    # the antenna: a fin
    g = Geo()
    z = zr(-1.22, 0.0)
    fin = [(-1.10, z - 0.004), (-1.20, z + 0.036), (-1.265, z + 0.064), (-1.292, z + 0.062),
           (-1.30, z - 0.006)]
    wy = (0.017, 0.006, 0.004, 0.004, 0.017)
    g.add([(x, sg * w, zz) for sg in (-1, 1) for (x, zz), w in zip(fin, wy)],
          [(0, 1, 2, 3, 4), (5, 6, 7, 8, 9)] + [(k, (k + 1) % 5, 5 + (k + 1) % 5, 5 + k)
                                                for k in range(5)])
    g.obj("antenna", "plastic", bevel=0.003, segs=2)
    # the sensor brow over the windshield: a gloss black bar, three lenses, a lit status band
    g, gl, gp = Geo(), Geo(), Geo()
    pad(g, 0.615, 0.0, 0.040, 0.25, 0.022, 'z', lift=0.024, sink=0.003, nv=8)
    g.obj("sensor.brow", "visor", bevel=0.006, segs=3)
    for y in (-0.15, 0.0, 0.15):
        loc, n = skin(0.615, y, 'z')
        c = loc + n * 0.012 + V3((0.0405, 0, 0))
        gl.lathe([(-0.002, 0.0006), (-0.002, 0.012), (0.003, 0.012), (0.005, 0.008),
                  (0.005, 0.0006)], 16, axis='x', at=c)
    gl.obj("sensor.lenses", "lens_smoke", sharp=40)
    for y0, y1 in ((-0.115, -0.035), (0.035, 0.115)):
        P = []
        for k in range(5):
            loc, n = skin(0.615, y0 + (y1 - y0) * k / 4, 'z')
            P.append(loc + n * 0.012 + V3((0.0408, 0, 0)))
        gp.sweep(P, [(-0.0025, -0.001), (0.0025, -0.001), (0.0025, 0.001), (-0.0025, 0.001)],
                 up=(1, 0, 0))
    gp.obj("sensor.band", "pixel")
    g = Geo()
    K.text_on_body(g, "T-" + NUM, 0.05, 0.50, 0.0, 1, proj='z', turn=90, spacing=1.15)
    g.obj("roof.number", "mark")


# ---------------------------------------------------------------------------------------
# interior
# ---------------------------------------------------------------------------------------
def zone(label, p, n):
    """The lining's material where the module's rule (head over the belt, trim under it,
    face by face) would make a saw: the belt (1.02) runs across the cowl under the raked
    windshield and along the door glass's sills, where the 40 mm faces lean, and the two
    colors alternated face by face in spikes. So the footwells are carpet up over the wheel
    wells (as their covers are), the cowl and the pillars' feet the dash's dark trim, and
    the walls change from trim to headliner 0.9 m up, behind the door cards' upper pads."""
    if label == "fill":         # behind a wheel well (the module's default there is trim,
        return "interior.carpet"    # and its faces peeked round the covers in grey)
    if p is None or n is None or label in ("floor", "fire", "well"):
        return None
    if p.x > 0.80 and p.z < 0.82:
        return "interior.carpet"
    if p.x > 0.86 and p.z < 1.16:
        return "interior"
    return "interior.head" if p.z > 0.90 else "interior"


def build_interior():
    """The cabin (vehicles/cabin.py): a lined box from the firewall to the hatch (the rear
    wheel wells come up beside the boot, covered), two front seats, a rear bench for three,
    a parcel shelf over the boot, a plain dash in dark grey with a marigold inlay (the
    paint's), charcoal seat inserts with marigold piping, a two-spoke wheel, door cards
    front and rear with LINNET on the sills, the roof's kit; the interior views cab_*."""
    C.materials(head=(0.30, 0.30, 0.29), soft=(0.12, 0.12, 0.125),
                trim=(0.80, 0.37, 0.0), carpet=(0.025, 0.025, 0.028),
                accent=(0.055, 0.055, 0.06), piping=(0.85, 0.42, 0.02),
                ambient=(1.0, 0.58, 0.18))
    # the firewall at the cowl, just ahead of the windshield's base (behind it, the plane cut
    # the glass's reveal into spikes); the spine runs on to 4 cm from it: with the module's
    # 0.45 m the windshield's base, the A-pillars' feet and the footwells all lay in the
    # front pole's fan, 9 degrees a ray, and came out torn
    cab = C.Cabin(-2.0, 1.21, 0.25, rear="body", style="tanager", shell=("visor.back.*",),
                  cap=0.04)
    cab.step = 0.03         # the lining's grid at detail 2's 30 mm (seats stay at detail 1):
    #                         the narrow pillar between the quarter light and the door glass
    cab.lining(smooth=5, zone=zone)
    cab.seat((0.12, 0.37, 0.60), driver=True)
    cab.seat((0.12, -0.37, 0.60))
    cab.seat((-0.74, 0.0, 0.60), places=3, width=1.30)
    cab.dash(tuck=0.0)                  # the top pad meets the raked glass, no strip of cowl
    cab.cluster()
    cab.screen()
    cab.wheel(tilt=30)
    cab.pedals(x=0.92)
    cab.console(h=0.14)
    cab.door(-0.10, 0.90, tag="door_f", sill_text="LINNET")
    cab.door(-0.86, -0.14, tag="door_r", sill=False)
    cab.shelf(-1.95, -1.12, 0.94)
    cab.roof_kit()
    cab.mats()
    # a trim over the narrow pillar between the quarter light and the door glass (the
    # lining there is a sliver between two reveals, with gaps)
    g = Geo()
    a, b = V3((0.872, 0, 0.985)), V3((0.636, 0, 1.40))
    ax = (b - a).normalized()
    ac = V3((ax.z, 0, -ax.x))
    rows = []
    for k in range(9):
        c = a.lerp(b, k / 8)
        row = []
        for t in (-0.026, -0.018, 0.018, 0.026):
            q = c + ac * t
            p, n = cab.wall(q.x, q.z, 1)
            row.append(p + n * (0.004 if abs(t) > 0.02 else 0.009))
        rows.append(row)
    g.add([p for r in rows for p in r], [(i * 4 + j, i * 4 + j + 1, i * 4 + j + 5, i * 4 + j + 4)
                                        for i in range(8) for j in range(3)])
    cab._obj(g, "pillar_trim", "interior.head", mirror=True)
    cab.views(exposure=-0.4, outside=2.0, daylight=8.0)
    cab.report()
    K.meant("symmetry", *cab.one_sided, "interior.seat2.*")     # a bench for three: its belts
    # the parking permit behind the windshield, on the right
    w = W_FRONT
    c = w.at(-0.43, 1.15, -GD - 0.012)
    g, gt, gs = Geo(), Geo(), Geo()
    q = [c + w.eu * a + w.ev * b for a, b in ((-0.045, -0.03), (0.045, -0.03), (0.045, 0.03),
                                                (-0.045, 0.03))]
    g.hexa([p - w.n * 0.002 for p in q] + q)
    g.obj("permit", "plate")
    K.text_flat(gt, "P2", 0.026, c + w.n * 0.0008 + w.ev * 0.008 - w.eu * 0.018, w.eu, w.ev)
    K.text_flat(gt, "ZONE 2  0309", 0.0075, c + w.n * 0.0008 - w.ev * 0.019, w.eu, w.ev,
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
    doors=dict(dir=(0.25, 1.0, 0.18), lens=85, target=(-0.3, 0.8, 0.85), dist=4.6),
    nose=dict(dir=(1.0, 0.45, 0.14), lens=85, target=(1.9, 0.25, 0.65), dist=3.6),
    tail=dict(dir=(-1.0, 0.45, 0.16), lens=85, target=(-1.9, 0.2, 0.8), dist=3.8),
    wheel=dict(dir=(0.5, 1.0, 0.12), lens=85, target=(FA_X, 0.8, 0.5), dist=2.8),
    glass=dict(dir=(1.0, 0.7, 0.3), lens=85, target=(0.9, 0.3, 1.15), dist=3.8),
    quarter=dict(dir=(-1.0, 0.8, 0.3), lens=85, target=(-1.55, 0.5, 1.05), dist=3.8),
    roofv=dict(dir=(-0.6, 0.5, 0.6), lens=85, target=(-0.9, 0.0, 1.45), dist=4.4),
)


def main():
    K.materials(paint=(0.88, 0.43, 0.0), paint_finish="gloss",
                paint2=(0.80, 0.78, 0.72), paint2_finish="gloss",
                dust_amount=0.3, glass=(0.42, 0.47, 0.50),
                led_front=(1.0, 0.90, 0.72), led_accent=(1.0, 0.42, 0.03),
                caliper=(0.95, 0.62, 0.03), seat=(0.30, 0.29, 0.265),
                interior=(0.05, 0.05, 0.055), decal=(0.045, 0.045, 0.05),
                screen=(0.30, 0.95, 0.70))
    grain("plastic", (0.040, 0.042, 0.046))
    K.pbr("steel", (0.035, 0.036, 0.04), 0.9, 0.45)
    K.pbr("cover", (0.60, 0.61, 0.62), 0.0, 0.38, **{"Coat Weight": 0.4})
    K.pbr("plate", (0.82, 0.82, 0.78), 0.0, 0.45)
    K.pbr("mark", (0.03, 0.032, 0.036), 0.0, 0.5)
    K.pbr("visor", (0.006, 0.006, 0.008), 0.0, 0.12)        # gloss black with no coat
    K.pbr("panel", (0.018, 0.026, 0.034), 0.0, 0.28)
    K.pbr("roofglass", (0.010, 0.012, 0.016), 0.0, 0.04, **{"Coat Weight": 1.0})
    K.pbr("reflector", (0.55, 0.01, 0.008), 0.0, 0.15, **{"Coat Weight": 1.0})
    K.emit("pixel", (0.30, 1.0, 0.72), 36.0)
    K.emit("pixel_r", (1.0, 0.50, 0.08), 36.0)
    K.need("lamp_housing", "chrome", "lens_clear", "lens_smoke", "lens_red", "lens_amber",
           "optic", "frit", "mirror")
    K.meant("symmetry", "tow.*", "wipers*",
            "permit*", "display*", "pixels*", "charge.*", "body.fender", "roof.number",
            "lettering.*", "roundel.number", "plate.glyphs.*", "badge.t.*", "hatch.camera")
    build_hull()
    K.log("hull")
    build_glass()
    if not HULL_ONLY:
        build_sides()
        build_roof()
        build_interior()
        K.log("details")
    for side, s in ((1, "l"), (-1, "r")):
        build_wheel("f" + s, FA_X, side)
        build_wheel("r" + s, RA_X, side)
    K.log("wheels")
    # the studio: the top box is not mirrored whole in the leaning glass, nor the key light
    # in the flanks' panes from behind; a soft lamp in the cabin shows the seats from the side
    K.unlit("top", "glass.ends", "roof.glass", "sensor.brow")
    K.unlit(("key", "fill"), "glass.side")
    K.cabin_light((-0.35, 0.0, 1.33), power=14.0)
    K.shoot(extra=dict(view="rear", size=(940, 528), corner="tl"))


main()
