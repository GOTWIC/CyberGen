"""Tanager Cab: a driverless city taxi, a one-box people carrier for four (both names made
up), built on vehicles/carkit.py.

Run (always through the wrapper, one Blender job at a time on this machine):
    vehicles/blender.sh vehicles/cars/tanager_cab.py --out DIR --preview
    vehicles/blender.sh vehicles/cars/tanager_cab.py --out DIR --sheet

The Mino's bigger sibling (docs/progress/AG18/tanager_mino/README.md lists the family's
cues, all repeated here): the soft tall box, holes for windows with flat glass, a fat seal
and a frit border, the visor across each end (a hole under a clear lens in a gloss black
surround holding one light bar between two lamp rings, and a dot-matrix display under a
smoked lens of its own), squircle arches, stepped grained cladding with a bump strip, steel
wheels under slotted covers, a cap roof with its gear on two rails, roundel and small print,
a round badge.

Its own job: one box with no hood and no driver (a sensor bar over the windshield), four
seats facing each other in pairs across a low flat floor, one big sliding door each side on
a visible track (the left one shown open in the sheet's views of its side, over a fold-out
step), a luggage hatch cut into the tail, and a roof sign that is a dot-matrix band all
round.

The body is ten lines over fourteen stations. The windows are holes cut through the skin;
everything else cut into it (the visors, the side repeaters, the handle cups, the hatch and
the charge door) is laid on the hull as it stands uncut (cutters()). The car stands with
both doors shut; the left door and its step hang on groups that slide them open for the
views of its side (CAB_SHUT=1: shut in every view). The brand's helpers (outlines, pads,
bars, dot matrices, windows, door parts, plate, badge, arch, wheel) are in
vehicles/brands/tanager.py.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import bmesh                                                        # noqa: E402
import bpy                                                          # noqa: E402
import carkit as K                                                  # noqa: E402
from functools import partial                                       # noqa: E402
from brands import tanager                                          # noqa: E402
from brands.tanager import (GD, GLYPH, badge, banner, bar_on, dots, dots_flat, grain,  # noqa: E402
                            pad, rect, rpoly, rrect, sheet, split_left, text_proj, tile)
from carkit import Geo, Matrix, V3, cos, hypot, pi, rad, stud       # noqa: E402

# ---------------------------------------------------------------------------------------
# dimensions
# ---------------------------------------------------------------------------------------
FA_X, RA_X = 1.50, -1.50            # axles: wheelbase 3.0
T_R, T_W, T_RIM, T_OUT = 0.33, 0.205, 0.225, 0.888     # tire radius, width, rim, outer face
ARCH = (0.39, 0.395, 0.335, 3.4)    # squircle arch: half width, rise, center height, exponent
ARCH_A = ARCH[0]
WELL_Y = 0.48                       # the wells' inner walls (0.60 before: room to steer)
BELT, HEAD, ROOF = 1.00, 1.67, 1.78  # belt line, glass header, roof
STEP = 0.53                         # the cladding's step
D_F, D_R = 0.64, -0.62              # the sliding door's front and rear edges as built
D_FC, D_RC = 0.772, -0.748          # their stations in the cage: subdivision draws an edge
#                                     toward its neighbors, (prev + 4 x + next) / 6
SLIDE = V3((-1.27, 0.09, 0.0))      # how far the open door has gone
STEP_OUT = V3((0.0, 0.30, 0.0))     # how far the fold-out step comes out from under the sill
OPEN_VIEWS = ("hero", "side", "top", "door", "low")    # the left door open in these
FLOOR = 0.30                        # the cabin floor
NUM = "31"
GAP = 0.00175                       # shut lines 3.5 mm
FRIT = 0.04                         # the frit border on the glass, from its edge
VIS = dict(front=('x', 0.80, 0.7435, "led_front", "pixel", "z 64%"),      # the visors:
           rear=('X', 0.90, 0.7635, "led_rear", "pixel_r", "NEXT>QUAY 6"))  # projection,
#                                     middle height, half width, lights, display
DOOR = []                           # objects that slide with the left door
STEPS = []                          # objects of the left step
LATE = {}                           # what cutters() lays inside the cuts, made after the build

arch_pts = partial(tanager.arch_pts, arch=ARCH)
build_wheel = partial(tanager.wheel, R=T_R, w=T_W, rim=T_RIM, out=T_OUT, tread=tanager.NARROW)
door_obj = partial(tanager.door_obj, door=DOOR)

FAR = {'x': lambda p: p.x < 1.0, 'X': lambda p: p.x > -1.0, 'y': lambda p: p.y < 0.4,
       'Y': lambda p: p.y > -0.4, 'z': lambda p: False}
_skin = tanager.skin


def skin(u, v, proj):
    """The brand's skin(), but a ray that slips through a shut line at the edge of a face
    (3.5 mm wide now) or past a face's rounded edge and meets the inside of the body far
    behind it (the rear bumper's guards once reached the front wheel wells) looks beside
    it, as one that misses does. Set as the brand module's own, so its pads use it too."""
    for du, dv in ((0, 0), (0, 0.004), (0, -0.004), (0.004, 0), (-0.004, 0), (0, 0.009),
                   (0, -0.009), (0.009, 0), (-0.009, 0)):
        loc, n = K.on_body(u + du, v + dv, proj)
        if loc is not None and not FAR[proj](loc):
            return loc, n
    return _skin(u, v, proj)


tanager.skin = skin


def tail_x(z):
    """The tail is one plane, leaning forward six degrees."""
    return -2.25 + (z - 0.32) * 0.105


class CabWin(tanager.Win):
    """The Cab's windows: its body's cutter planes, and flat glass with a frit border (the
    glass's own thickness, no gap between them)."""

    CUT = dict(y=(0.55, 0.6), x=(1.45, 1.2), X=(-1.60, -1.0))

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
            floor="underbody", well="well", wincut="void",
            visor_f="void", visor_r="void", rep_h="void", slot="plastic", hslot="plastic",
            cut="void")


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


W_FQ = CabWin([(1.80, 1.055), (1.535, 1.585), (.77, 1.585), (.77, 1.055)],
              [.06, .08, .08, .08], 'y')
W_DOOR = CabWin(rect(0.01, 1.32, .50, .265), .08, 'y')
W_RQ = CabWin([(-.75, 1.055), (-.75, 1.585), (-1.885, 1.585), (-1.935, 1.055)], .08, 'y')
W_FRONT = CabWin([(-.67, 1.125), (.67, 1.125), (.63, 1.60), (-.63, 1.60)], .09, 'x')
W_REAR = CabWin(rect(0, 1.335, .60, .215), .085, 'X')
WINS = [W_FQ, W_DOOR, W_RQ, W_FRONT, W_REAR]


# ---------------------------------------------------------------------------------------
# the cuts, laid on the hull as it stands uncut, and what stands inside them
# ---------------------------------------------------------------------------------------
def frame_on(g, outline, proj, w, z0, z1):
    """A wall w thick along a closed outline on the skin, from z0 to z1 over it."""
    P, U = under(dense(outline), proj, 0.0)
    g.sweep(P, [(-w / 2, z0), (w / 2, z0), (w / 2, z1), (-w / 2, z1)], up=U, closed=True)


def visor(tag):
    """A visor, as the Mino's: a hole across the face (the paint's own 14 mm rim its walls,
    a gloss black back plate closing it 14 mm in), a gloss black surround standing 9.5 mm
    proud round its edge and a clear lens in it. The lamps stand in the hole with their lit
    faces 2 to 4 mm proud of the skin, under the lens (the game pack's far LOD draws the
    face across the hole), and nothing in it is a small ring (that LOD fills one into a
    lid). At each end a lamp of a chrome plate, a lit ring of light guide and a row of three
    LED cups on a dark tray, larger than the Mino's; the light bar between them, a guide on
    a chrome strip; the display on the car's left, a screen with its lit dots under a
    smoked lens of its own: the charge in front, the next stop behind."""
    proj, cv, hw, lit, pix, msg = VIS[tag]
    t = tag[0]
    vh = 0.0885
    sg = -1.0 if proj == 'X' else 1.0          # the car's left as this view's u
    ly = hw - 0.1035                            # the lamps
    g, lens = Geo(), Geo()
    K.pocket(g, K.rounded(0.0, cv, 2 * hw + 0.003, 2 * vh + 0.003, 0.055), proj, depth=0.03)
    frame_on(lens, rrect(0, cv, hw, vh, 0.0535), proj, 0.008, -0.004, 0.0095)
    glass = Geo()
    pad(glass, 0, cv, hw - 0.0035, vh - 0.0035, 0.05, proj, lift=0.009, sink=-0.006, nv=10,
        nc=8, step=0.01)
    back = Geo()
    pad(back, 0, cv, hw + 0.0085, vh + 0.0085, 0.057, proj, lift=-0.0140, sink=0.0175, nv=6)
    # the lamps at each end (the left one, mirrored)
    E = K.Lamp("lamp.%s" % tag, lit=lit, optic="lens_red" if t == "r" else "optic")
    pad(E.chrome, ly, cv, 0.081, 0.062, 0.032, proj, lift=-0.003, sink=0.004)
    P, U = under(dense(rrect(ly, cv, 0.0695, 0.0505, 0.024)), proj, -0.0005)
    E.guide(P, r=0.0035, sleeve=1.6, closed=True, up=U)
    pad(E.housing, ly, cv, 0.057, 0.039, 0.018, proj, lift=-0.002, sink=0.0029)
    for u in (ly - 0.036, ly, ly + 0.036):
        loc, n = skin(u, cv, proj)
        E.reflector(loc + n * 0.002, n, r=0.014, depth=0.006, seg=16, led=0.006)
    # the light bar: a guide on a chrome strip
    L = ly - 0.09
    B = K.Lamp("lamp.%s_bar" % tag, lit=lit, optic="lens_red" if t == "r" else "optic")
    P, U = under(dense([(-L, cv + 0.037), (L, cv + 0.037)], 0.02, closed=False), proj, 0.0)
    B.guide(P, r=0.0042, sleeve=1.45, up=U)
    pad(B.chrome, 0, cv + 0.037, L + 0.002, 0.0125, 0.008, proj, lift=-0.004, sink=0.005)
    # the display under its own smoked lens
    rows = banner(msg)
    wd = len(rows[0]) * 0.0072 / 2 + 0.022
    du, dv = sg * (ly - 0.105 - wd), cv - 0.03
    sc, px, ln = Geo(), Geo(), Geo()
    pad(sc, du, dv, wd, 0.036, 0.012, proj, lift=0.001, sink=0.004)
    dots(px, rows, du, dv, 0.0072, proj, 0.002, 0.0052)
    pad(ln, du, dv, wd - 0.002, 0.034, 0.011, proj, lift=0.0047, sink=-0.0035)
    LATE[tag] = (lens, glass, back, E, B, sc, px, ln, pix)
    return g


def cutters():
    """Everything cut into the hull: the wheel wells, the windows (holes), the visors and
    the front side repeaters (housings under lenses), the handle cups (the sliding doors'
    and the hatch's) and the shut lines of the luggage hatch and the charge door."""
    wells, wins = Geo(), Geo()
    for cx in (FA_X, RA_X):
        for sg in (1, -1):
            pts = arch_pts(cx)
            poly = [(pts[0][0], sg * WELL_Y, -0.3)] + [(x, sg * WELL_Y, z) for x, z in pts]
            poly.append((pts[-1][0], sg * WELL_Y, -0.3))
            wells.prism(poly, (0, sg * 0.5, 0))
    for w in WINS:
        w.cut(wins)
    vf, vr = visor("front"), visor("rear")
    # the side repeaters ahead of the front arches: an amber cell under an amber lens
    rep = Geo()
    K.pocket(rep, K.rounded(1.92, 0.925, 0.066, 0.024), 'y', depth=0.012, mirror=True)
    R = K.Lamp("lamp.repeater", lit="led_accent", glass="lens_amber")
    pad(R.housing, 1.92, 0.925, 0.0365, 0.0155, 0.012, 'y', lift=-0.0140, sink=0.016)
    pad(R.chrome, 1.92, 0.925, 0.032, 0.0115, 0.009, 'y', lift=-0.0085, sink=0.0139)
    pad(R.emit(), 1.92, 0.925, 0.026, 0.0065, 0.005, 'y', lift=-0.0045, sink=0.0065)
    pad(R.glass, 1.92, 0.925, 0.033, 0.012, 0.011, 'y', lift=0.0, sink=0.003)
    LATE["rep"] = R
    # handle cups: an upright one on each sliding door (it goes with the door), a long one
    # under the luggage hatch; each pull's ends on the skin past its cup
    hs, gp = Geo(), Geo()
    K.pocket(hs, K.rounded(0.515, 0.715, 0.050, 0.172, 0.018), 'y', depth=0.014, mirror=True)
    pad(gp, 0.515, 0.715, 0.0095, 0.096, 0.009, 'y', lift=0.010)
    LATE["pulls"] = gp
    hp, gh = Geo(), Geo()
    K.pocket(hp, K.rounded(0.0, 0.621, 0.17, 0.040, 0.018), 'X', depth=0.014)
    pad(gh, 0.0, 0.623, 0.105, 0.0095, 0.009, 'X', lift=0.009)
    LATE["hatch"] = gh
    # shut lines: the luggage hatch's top and foot across the tail face (its sides are the
    # face's own shut lines at its edges: a line cut beside them on the rounded edge left
    # stars in the paint), the charge door on the left
    cut = Geo()
    K.groove(cut, [(-0.76, 0.588), (0.76, 0.588)], 'X')
    K.groove(cut, [(-0.69, 1.655), (0.69, 1.655)], 'X')
    K.groove(cut, rrect(0.87, 0.70, 0.078, 0.054, 0.022), 'y', closed=True)
    return [(wells, "well"), (wins, "wincut", "drop"), (vf, "visor_f", "drop"),
            (vr, "visor_r", "drop"), (rep, "rep_h", "drop"), (hs, "hslot"), (hp, "slot"),
            (cut, "cut", "drop")]


def unfold(ob):
    """Takes out the faces the boolean and the gap's shrink folded back over their
    neighbors (slivers along a cut through a face's fan of quads)."""
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
    cuts leave long thin triangles there, and smooth shading carried the rim's normals at
    the cut along them in stars."""
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
    tail_n = V3((-1.0, 0.0, 0.105)).normalized()
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
    door_obj(LATE["pulls"], "handle.pull", "paint", bevel=0.002)
    LATE["hatch"].obj("hatch.pull", "paint", bevel=0.002)
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
    for w in WINS:
        w.fit()
    g, gf, gs = Geo(), Geo(), Geo()
    for w in (W_FQ, W_RQ):
        w.panes(g, gf)
        w.seal(gs)
    sheet(g, "glass.side", mirror=True)
    frit(gf, "frit.side", mirror=True)
    gs.obj("seal.side", "rubber", bevel=0.0012, mirror=True)
    g, gf, gs = Geo(), Geo(), Geo()
    W_DOOR.panes(g, gf)
    W_DOOR.seal(gs)
    door_obj(g, "glass.door", "glass", glass=True)
    DOOR.append(frit(gf, "frit.door.l"))
    frit(gf, "frit.door.r", flip_y=True)
    door_obj(gs, "seal.door", "rubber", bevel=0.0012)
    g, gf, gs = Geo(), Geo(), Geo()
    for w in (W_FRONT, W_REAR):
        w.panes(g, gf, 0.05)
        w.seal(gs)
    sheet(g, "glass.ends")
    frit(gf, "frit.ends")
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
# the ends: bumpers, fog, reverse and stop lamps, plates, badges, lettering
# ---------------------------------------------------------------------------------------
def small_lamp(name, proj, u, v, a, b, r, cups, cup_r, lit="lamp", glass="lens_clear",
               base=0.012, mirror=False):
    """A lamp standing on a bumper pad (its face base over the skin), as the Mino's: a dark
    housing plate, a chrome back, LED cups and a block of clear lens over them."""
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
    for proj, tag, zb in (('x', "front", 0.455), ('X', "rear", 0.455)):
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
    small_lamp("lamp.fog", 'x', 0.54, 0.39, 0.052, 0.025, 0.013, 2, 0.011, mirror=True)
    tanager.plate('x', 0.0, 0.50, "VB 31-204")
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

    # ---- rear: reflectors, reverse lamp, plate, the high stop lamp, lettering (the
    #      luggage hatch's shut line and its handle cup are cut in cutters())
    g = Geo()
    for y in (0.52, -0.52):
        pad(g, y, 0.475, 0.095, 0.018, 0.012, 'X', lift=0.0135)
    g.obj("reflectors", "reflector", bevel=0.001)
    small_lamp("lamp.reverse", 'X', 0.0, 0.375, 0.062, 0.0145, 0.009, 3, 0.0085)
    tanager.plate('X', 0.0, 0.688, "VB 31-204")
    # the high stop lamp over the rear window: a dark plate on the skin, a lit bar on a
    # chrome strip in a block of red lens
    S = K.Lamp("lamp.stop", lit="led_rear", glass="lens_red")
    pad(S.housing, 0, 1.605, 0.214, 0.0155, 0.012, 'X', lift=0.0012, sink=0.002)
    pad(S.chrome, 0, 1.605, 0.208, 0.011, 0.009, 'X', lift=0.0018, sink=0.0)
    P, U = under(dense([(-0.20, 1.605), (0.20, 1.605)], 0.02, closed=False), 'X', -0.0035)
    S.bar(P, 0.012, 0.003, up=U)
    pad(S.glass, 0, 1.605, 0.210, 0.0125, 0.010, 'X', lift=0.0068, sink=-0.0019)
    S.obj()
    g = Geo()
    text_proj(g, "CAB", 0.066, 0.46, 0.735, 'X', spacing=1.1)
    text_proj(g, "tanager", 0.032, -0.46, 0.745, 'X', spacing=1.05)
    text_proj(g, "CITY CAB  E-6  DRIVERLESS", 0.014, -0.46, 0.708, 'X', spacing=1.15)
    text_proj(g, "UNIT " + NUM, 0.017, 0.46, 0.682, 'X', spacing=1.2)
    text_proj(g, "LUGGAGE  40 KG", 0.012, 0.46, 0.660, 'X', spacing=1.2)
    g.obj("lettering.rear", "decal")
    badge('X', 0.0, 0.772, 0.032)
    badge('z', 2.172, 0.0, 0.036)


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

    # ---- the roundel and the lettering (the handle's cup and pull are made with the hull)
    gr = Geo()
    pad(gr, 0.17, 0.705, 0.118, 0.118, 0.118, 'y', lift=0.0025, nc=12, nv=8)
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

    # ---- corner cameras where a driver's mirrors would be, with a turn lamp each end;
    #      amber markers at the rear corners (a lit bar under a lens on a dark plate)
    g, gm, ga = Geo(), Geo(), Geo()
    g.tube((1.90, 0.875, 1.005), (1.90, 0.95, 1.035), 0.012, 8)
    g.obj("camera.stalks", "plastic", mirror=True)
    gm.box((1.90, 0.972, 1.045), (0.10, 0.05, 0.05))
    gm.obj("camera.pods", "visor", bevel=0.014, segs=3, mirror=True)
    ga.box((1.953, 0.972, 1.045), (0.004, 0.034, 0.012))
    ga.box((1.847, 0.972, 1.045), (0.004, 0.034, 0.012))
    ga.obj("led.turn", "led_accent", mirror=True)
    M = K.Lamp("lamp.marker", lit="led_accent", glass="lens_amber")
    pad(M.housing, -2.03, 0.925, 0.034, 0.014, 0.010, 'y', lift=0.0012, sink=0.002)
    pad(M.emit(), -2.03, 0.925, 0.026, 0.0065, 0.005, 'y', lift=0.0030, sink=-0.0005)
    pad(M.glass, -2.03, 0.925, 0.030, 0.0115, 0.009, 'y', lift=0.0060, sink=-0.0015)
    M.obj(mirror=True)

    # ---- the charge door (cut in cutters()) on the left front quarter: a lit bolt, a label
    gp, gt = Geo(), Geo()
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
    """The cabin tub, kept inside the hull and out of the wheel wells (their walls at
    WELL_Y, their arches up to 0.73 m): over the wells only its middle reaches down."""
    yi = WELL_Y - 0.01
    g = Geo()
    g.box((0.0, 0, FLOOR - 0.015), (2.20, 1.70, 0.03))             # the floor between the arches
    for x in (1.48, -1.48):
        g.box((x, 0, FLOOR - 0.015), (0.80, 2 * yi, 0.03))
    for x, top in ((1.19, 1.03), (-1.19, 1.0)):                    # bulkheads behind the seats
        g.box((x, 0, 0.53), (0.03, 2 * yi, 0.46))
        g.box((x, 0, (0.76 + top) / 2), (0.03, 1.62, top - 0.76))
    g.box((1.625, 0, 1.02), (0.87, 1.60, 0.02))                      # the shelf under the screen
    g.box((-1.655, 0, 0.99), (0.93, 1.60, 0.02))                     # the luggage cover
    for y in (0.872, -0.872):                                       # wall cards
        for x in (0.87, -0.855):
            g.box((x, y, 0.655), (0.43, 0.02, 0.67))
    for x in (D_F + 0.04, D_R - 0.04):                              # door pillars' linings
        for y in (0.845, -0.845):
            g.box((x, y, 0.655), (0.075, 0.05, 0.69))
    for x in (0.77, -0.77):                                         # seat plinths
        g.box((x, 0, 0.44), (0.38, 1.22, 0.28))
    g.obj("interior.tub", "interior", bevel=0.006)
    g = Geo()                                                       # the doors' cards
    g.box((0.01, 0.872, 0.655), (1.22, 0.02, 0.67))
    g.box((0.01, 0.868, 0.80), (0.50, 0.03, 0.035))                 # its pull
    door_obj(g, "interior.card", "interior", bevel=0.006)
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

    # ---- a fold-out step under each door, on two arms, a lit edge: built stowed under
    #      the sill, the left one comes out with its door
    g, gl, gr = Geo(), Geo(), Geo()
    dy = -STEP_OUT.y
    g.box((0.01, 1.035 + dy, 0.165), (1.06, 0.23, 0.022))
    for x in (0.38, -0.36):
        g.hexa([(x - 0.02, 0.80 + dy, 0.215), (x + 0.02, 0.80 + dy, 0.215),
                (x + 0.02, 0.96 + dy, 0.160), (x - 0.02, 0.96 + dy, 0.160),
                (x - 0.02, 0.80 + dy, 0.235), (x + 0.02, 0.80 + dy, 0.235),
                (x + 0.02, 0.96 + dy, 0.178), (x - 0.02, 0.96 + dy, 0.178)])
    for k in range(9):
        gr.box((0.01, 0.945 + dy + 0.0225 * k, 0.178), (1.0, 0.008, 0.004))
    gl.box((0.01, 1.151 + dy, 0.165), (1.0, 0.004, 0.010))
    for gg, nm, mat, kw in ((g, "step", "steel", dict(bevel=0.004)),
                            (gr, "step.ribs", "rubber", {}), (gl, "step.light", "pixel", {})):
        STEPS.append(gg.obj(nm + ".l", mat, **kw))
        gg.obj(nm + ".r", mat, flip_y=True, **kw)

    # ---- screens: one on each bulkhead between the headrests, a strip behind the windshield
    g, gs = Geo(), Geo()
    for sx in (1.0, -1.0):
        g.box((sx * 1.16, 0, 1.24), (0.03, 0.40, 0.24))
        gs.box((sx * 1.143, 0, 1.24), (0.004, 0.36, 0.20))
    gs.box((1.99, 0, 1.065), (0.006, 0.62, 0.05), rot=Matrix.Rotation(rad(-20), 3, 'Y'))
    g.box((1.975, 0, 1.055), (0.03, 0.66, 0.07), rot=Matrix.Rotation(rad(-20), 3, 'Y'))
    g.box((1.55, 0, 1.065), (0.40, 0.50, 0.07))                     # the computer's hump
    g.obj("interior.screen.frames", "interior", bevel=0.006)
    g, gp = Geo(), Geo()                        # the destination strip under the header,
    g.box((1.725, 0, 1.488), (0.02, 0.86, 0.088))       # clear of the windshield's frit
    for y in (0.30, -0.30):
        g.box((1.725, y, 1.595), (0.014, 0.03, 0.135))
    dots_flat(gp, banner("CAB 31 >QUAY 6"), (1.7365, 0, 1.488), (0, 1, 0), (0, 0, 1), 0.0088,
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
# the left door and its step slide open in the views of its side
# ---------------------------------------------------------------------------------------
def door_groups(body):
    """The left door's panels (slider, sclad, the handle's cup) split off the body; the door
    and the step hang on groups, shut at rest (the checks, the game pack) and open in
    OPEN_VIEWS unless CAB_SHUT is set."""
    for pn in ("slider", "sclad", "hslot"):
        DOOR.append(split_left(body.parts[pn]))
    if os.environ.get("CAB_SHUT"):
        return
    K.Group("door", DOOR, pivot=(0.0, 0.95, 0.9)).pose_for(OPEN_VIEWS, loc=SLIDE)
    K.Group("step", STEPS, pivot=(0.0, 0.80, 0.2)).pose_for(OPEN_VIEWS, loc=STEP_OUT)


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
    K.need("lamp_housing", "chrome", "lens_clear", "lens_smoke", "lens_red", "lens_amber",
           "optic", "frit")
    K.meant("symmetry", "interior.screen*", "antenna", "tow.*", "wipers", "radar",
            "permit*", "display*", "pixels*", "charge.*", "body.fender")
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
    door_groups(body)
    for side, s in ((1, "l"), (-1, "r")):
        build_wheel("f" + s, FA_X, side)
        build_wheel("r" + s, RA_X, side)
    K.log("wheels")
    K.shoot(preview=("hero", "rear", "side", "front"),
            extra=dict(view="rear", size=(940, 528), corner="tl"))


main()
