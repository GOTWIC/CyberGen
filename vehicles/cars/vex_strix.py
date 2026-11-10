"""Vex Strix: a tandem two-seat track hypercar (both names made up), on vehicles/carkit.py.

Run (always through the wrapper, one Blender job at a time on this machine):
    vehicles/blender.sh vehicles/cars/vex_strix.py --out DIR --preview
    vehicles/blender.sh vehicles/cars/vex_strix.py --out DIR --sheet

The third Vex and the family's closed car. A fuselage barely wider than its two occupants,
one behind the other under a canopy the spine runs over; a needle nose pod ahead of it, the
gap between them jumped by the drilled beam. Each wheel lives in a fender pod of its own
that stands 0.3 m clear of the fuselage and is held only by two wing-section arms (the
front pair's fore arms are the car's canards), so the ground shows between fuselage and
fenders from above and from the front. Behind the cabin nothing is skinned: the motor, its
frame and cables sit in the open over two venturi tunnels that end in a tall diffuser, and
the spine goes on as a drilled fin to a high wing. Family helpers (drilled, cluster, block,
tube, blade, ring) are the Wraith's.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import bpy                                                          # noqa: E402
import carkit as K                                                  # noqa: E402
from carkit import (Geo, Matrix, V3, cos, on_body, pi, rad, ribbon,        # noqa: E402
                    sin, stud, text_flat, text_on_body)

# ---------------------------------------------------------------------------------------
# dimensions
# ---------------------------------------------------------------------------------------
FA_X, RA_X = 1.45, -1.45                    # axles: wheelbase 2.90
F_R, F_W, F_RIM, OUT_Y = 0.36, 0.27, 0.25, 1.0
R_R, R_W, R_RIM = 0.37, 0.33, 0.25
F_YC, R_YC = OUT_Y - F_W / 2, OUT_Y - R_W / 2
F_IN, R_IN = OUT_Y - F_W, OUT_Y - R_W       # the tires' inner faces
FLOOR_Z0, FLOOR_Z1 = 0.055, 0.075
FEN_F = dict(ax=FA_X, yi=0.635, yo=1.020)   # fender pods: inner and outer walls
FEN_R = dict(ax=RA_X, yi=0.600, yo=1.020)
NUM = "81"

PT = {}


# ---------------------------------------------------------------------------------------
# helpers of this car (the family's, from the Wraith)
# ---------------------------------------------------------------------------------------
def _up_for(pts):
    segs = [(V3(b) - V3(a)).normalized() for a, b in zip(pts, pts[1:])]
    best = None
    for c in ((0, 0, 1), (1, 0, 0), (0, 1, 0)):
        m = max(abs(s.dot(V3(c))) for s in segs)
        if best is None or m < best[0]:
            best = (m, c)
    return best[1]


def tube(g, pts, r, n=8):
    """A round tube along a path."""
    sec = [(r * cos(2 * pi * k / n), r * sin(2 * pi * k / n)) for k in range(n)]
    g.sweep(pts, sec, up=_up_for(pts))


def blade(g, pts, w, t, up=(0, 0, 1)):
    """A flat blade along a path: w across, t along up."""
    g.sweep(pts, [(-w / 2, -t / 2), (w / 2, -t / 2), (w / 2, t / 2), (-w / 2, t / 2)], up=up)


def ring(g, c, axis, r_out, r_in, t, n=20):
    xf = Matrix.Translation(V3(c)) @ V3((0, 1, 0)).rotation_difference(
        V3(axis).normalized()).to_matrix().to_4x4()
    g.lathe([(-t / 2, r_in), (-t / 2, r_out), (t / 2, r_out), (t / 2, r_in)], n, xf=xf)


def drilled(g, a, b, h, t, axis=(0, 1, 0), fl=0.012, flw=0.05, hole=0.60):
    """The Vex beam: from a to b, h deep, a web of rings (real holes, light comes through)
    between two flanges; axis is the holes' direction."""
    a, b = V3(a), V3(b)
    d = b - a
    L = d.length
    d.normalize()
    ax = V3(axis).normalized()
    n = ax.cross(d).normalized()
    ro = h / 2 - fl * 0.4
    k = max(1, int(L / (2 * ro) + 0.999))
    step = L / k
    for i in range(k):
        ring(g, a + d * (step * (i + 0.5)), ax, ro, ro * hole, t)
    for s in (-1, 1):
        o = n * (s * (h / 2 - fl / 2))
        g.sweep([a + o, b + o], [(-flw / 2, -fl / 2), (flw / 2, -fl / 2), (flw / 2, fl / 2),
                                 (-flw / 2, fl / 2)], up=n)


def ball(g, c, r=0.016):
    """A rod end: a short fat disc."""
    g.lathe([(-r * 0.6, 0.002), (-r * 0.6, r), (r * 0.6, r), (r * 0.6, 0.002)], 10,
            xf=Matrix.Translation(V3(c)))


def side_pt(x, z, objs=None):
    """The outermost body surface on the left at (x, z)."""
    return on_body(x, z, 'y', objs)[0]


def top_z(x, y, default=0.5):
    loc = on_body(x, y, 'z')[0]
    return loc.z if loc is not None else default


def block(g, gt, txt, size, x0, z0, side, pad=0.012, spacing=1.05, wide=None, objs=None):
    """A sponsor-like block on a flank: a plate in g, its word in gt."""
    w = wide if wide is not None else size * 0.62 * len(txt) * spacing + 2 * pad
    ribbon(g, [(x0 - w / 2, z0), (x0 + w / 2, z0)], 'y' if side > 0 else 'Y', size + 2 * pad,
           objs=objs)
    text_on_body(gt, txt, size, x0, z0, side, lift=0.0022, spacing=spacing, objs=objs)


def wing_sec(c, t):
    """A wing section for the arms: (forward, up) offsets, chord c, thickness t."""
    return [(0.50 * c, 0.0), (0.36 * c, 0.42 * t), (0.10 * c, 0.50 * t), (-0.25 * c, 0.30 * t),
            (-0.50 * c, 0.04 * t), (-0.25 * c, -0.16 * t), (0.10 * c, -0.34 * t),
            (0.36 * c, -0.30 * t)]


def arm(g, gf, a, b, c, t, c2=None):
    """A wing-section arm from a (inboard) to b (outboard) on the left, a bolted root
    fitting at each end in gf."""
    a, b = V3(a), V3(b)
    m = a.lerp(b, 0.5)
    c2 = c2 or c * 0.82
    # two spans, so the chord can taper toward the fender
    g.sweep([a, m], wing_sec(c, t), up=(0, 0, 1))
    g.sweep([m, b], wing_sec((c + c2) / 2, t * 0.9), up=(0, 0, 1))
    for (p, cc) in ((a, c), (b, c2)):
        gf.box(p, (cc * 0.86, 0.022, t * 1.5))
        for k in (-1, 1):
            gf.box(p + V3((k * cc * 0.30, 0, 0)), (0.02, 0.03, t * 1.5 + 0.012))


# ---------------------------------------------------------------------------------------
# the pods: nose, fuselage, four fenders
# ---------------------------------------------------------------------------------------
PMAT = dict(spine="alloy", cap="paint", flank="carbon", belly="carbon", bulk="alloy",
            tip="alloy", glass="glass", trim="gloss_black", open="void", band="weave")

# nose pod: C top centerline, D the spine strip's edge, S cap edge, W widest, L lower, B keel
NOSE = [
    [(2.42, 0, .322), (2.42, .012, .322), (2.42, .024, .319), (2.415, .036, .300),
     (2.42, .024, .282), (2.42, 0, .278)],
    [(2.12, 0, .400), (2.12, .030, .400), (2.12, .080, .392), (2.12, .122, .330),
     (2.12, .078, .252), (2.12, 0, .242)],
    [(1.74, 0, .472), (1.74, .034, .472), (1.74, .122, .462), (1.74, .178, .365),
     (1.74, .112, .218), (1.74, 0, .202)],
]
# fuselage: C, D, K the canopy's knuckle, S the sill, W widest, L lower, B keel
FUSE = [
    [(1.50, 0, .500), (1.50, .034, .500), (1.50, .095, .494), (1.50, .150, .478),
     (1.50, .208, .372), (1.50, .135, .205), (1.50, 0, .185)],
    [(0.95, 0, .595), (0.95, .036, .595), (0.95, .135, .585), (0.95, .225, .560),
     (0.95, .300, .430), (0.95, .210, .170), (0.95, 0, .140)],
    [(0.48, 0, .865), (0.48, .036, .865), (0.48, .188, .838), (0.48, .280, .620),
     (0.48, .335, .460), (0.48, .235, .155), (0.48, 0, .125)],
    [(0.00, 0, .970), (0.00, .036, .970), (0.00, .206, .936), (0.00, .292, .660),
     (0.00, .340, .470), (0.00, .235, .150), (0.00, 0, .120)],
    [(-.55, 0, .975), (-.55, .036, .975), (-.55, .202, .942), (-.55, .288, .680),
     (-.55, .335, .480), (-.55, .235, .160), (-.55, 0, .130)],
    [(-1.0, 0, .885), (-1.0, .036, .885), (-1.0, .168, .855), (-1.0, .255, .675),
     (-1.0, .300, .490), (-1.0, .215, .225), (-1.0, 0, .200)],
    [(-1.24, 0, .800), (-1.24, .034, .800), (-1.24, .120, .770), (-1.24, .205, .660),
     (-1.24, .250, .500), (-1.24, .180, .280), (-1.24, 0, .255)],
]
# fenders: rows of (dx from the axle, top, shoulder, inner bottom, split, outer bottom, the
# inner wall's pinch, the outer wall's): a wedge with a straight top line from a knife tip
# to a peak behind the axle, then level to an open back with a lip
FEN_ROWS_F = [(0.72, .365, .355, .335, .345, .335, .170, .050),
              (0.50, .520, .475, .300, .400, .300, .060, .010),
              (0.28, .665, .610, .460, .530, .400, .000, .000),
              (0.06, .800, .740, .530, .625, .560, .000, .000),
              (-.16, .805, .745, .540, .630, .570, .000, .000),
              (-.38, .818, .762, .520, .622, .500, .000, .000)]
FEN_ROWS_R = [(0.90, .365, .355, .335, .345, .335, .150, .050),
              (0.62, .510, .465, .300, .395, .300, .050, .010),
              (0.30, .680, .625, .470, .540, .410, .000, .000),
              (0.06, .815, .755, .540, .635, .570, .000, .000),
              (-.16, .822, .762, .550, .640, .580, .000, .000),
              (-.40, .838, .782, .520, .632, .500, .000, .000)]
FEN_LOUV = 3                                    # the station interval the louvres are in


def fender_cage(f, rows):
    S = []
    for (dx, zt, zs, zi, zm, zo, pi_, po) in rows:
        x, yi, yo = f["ax"] + dx, f["yi"] + pi_, f["yo"] - po
        ins = 0.100 if po < 0.03 else 0.050
        S.append([(x, yi, zi), (x, yi, zs), (x, yi + ins, zt), (x, yo - ins, zt),
                  (x, yo, zs), (x, yo, zm), (x, yo, zo)])
    return S


def fender_panel(i, j):
    if j == 2:                                  # a bare band down the top, the louvres in it
        return "open" if i == FEN_LOUV else "band"
    return "flank" if j in (0, 5) else "cap"


def build_pods():
    def lc(i, j):                               # creases along the lines
        return (0.0, 1.0, 0.45, 1.0, 0.35, 0.0)[j]

    S = K.fill(NOSE)
    PT["nose"] = S
    K.build_body(S, lambda i, j: ("spine", "cap", "cap", "flank", "belly")[j], PMAT, lc, 0.0,
                 name="nose", front=dict(kind="flat", panel="tip"),
                 rear=dict(kind="flat", panel="bulk"))

    def fuse_panel(i, j):
        if j in (1, 2) and 1 <= i <= 4:
            return "glass"
        return ("spine", "cap", "cap", "cap", "flank", "belly")[j]

    def flc(i, j):
        if j == 2:
            return 1.0 if 1 <= i <= 4 else 0.6
        return (0.0, 1.0, 0.0, 0.85, 1.0, 0.4, 0.0)[j]

    S = K.fill(FUSE)
    PT["fuse"] = S
    K.build_body(S, fuse_panel, PMAT, flc,
                 lambda i, j: 1.0 if i in (1, 5) and j in (1, 2) else 0.0, name="fuse",
                 front=dict(kind="flat", panel="bulk"), rear=dict(kind="flat", panel="bulk"),
                 glass=[("glass", 0.022)])

    fen = {}
    for key, f, rows in (("fenf", FEN_F, FEN_ROWS_F), ("fenr", FEN_R, FEN_ROWS_R)):
        S = K.fill(fender_cage(f, rows))
        PT[key] = S
        n = len(S)
        body = K.build_body(
            S, fender_panel, PMAT,
            lambda i, j: (1.0, 0.6, 1.0, 1.0, 0.6, 1.0, 1.0)[j],
            lambda i, j, n=n: 1.0 if i in (0, n - 1) else 0.55 if i == 3 else 0.0,
            name=key, wrap=False, thick=0.012, project=False)
        # project=False: on_body() with no objects sees the nose and the fuselage only, so
        # pickups, roots and lettering never land on a fender's outer wall
        op = body.parts.pop("open", None)           # the louvred opening is a real hole
        if op is not None:
            me = op.data
            bpy.data.objects.remove(op)
            bpy.data.meshes.remove(me)
        fen[key] = list(body.parts.values())
    return fen


def build_fender_details(fen):
    gs, gl, gb = Geo(), Geo(), Geo()
    for key, f in (("fenf", FEN_F), ("fenr", FEN_R)):
        S = PT[key]
        i = FEN_LOUV
        a, b, c, d = S[i][2], S[i + 1][2], S[i + 1][3], S[i][3]
        dz = V3((0, 0, -0.012))
        gs.louvers(a + dz, b + dz, c + dz, d + dz, 6, 0.040, 0.005, rad(-34), out=(0, 0, 1),
                   margin=0.05)
        # a raw metal lip round the hole, a wear strip along the knife edge
        loop = [p + V3((0, 0, 0.002)) for p in (a, b, c, d)]
        blade(gl, loop + [loop[0], loop[1]], 0.012, 0.004)
        n0 = [S[0][2] + V3((0.004, 0, 0)), S[0][3] + V3((0.004, 0, 0))]
        blade(gl, n0, 0.006, 0.020, up=(1, 0, 0))
        # fasteners along the color split, outside
        prof = [(-0.002, 0.001), (-0.002, 0.006), (0.002, 0.006), (0.002, 0.001)]
        for k in range(1, len(S) - 1):
            for t in (0.25, 0.75):
                p = S[k][5].lerp(S[k + 1][5], t) if k < len(S) - 1 else S[k][5]
                loc, n = on_body(p.x, p.z + 0.018, 'y', fen[key])
                if loc is not None:
                    stud(gb, loc, n, prof, 6)
    gg = Geo()
    for key, f, x0 in (("fenf", FEN_F, FA_X - 0.20), ("fenr", FEN_R, RA_X - 0.25)):
        for k in range(4):
            x = x0 - 0.035 * k
            ribbon(gg, [(x + 0.016, 0.728), (x - 0.016, 0.662)], 'y', 0.011, objs=fen[key])
    gg.obj("fender.gills", "ink", mirror=True)
    gs.obj("fender.slats", "alloy", bevel=0.0012, mirror=True)
    gl.obj("fender.lips", "alloy", bevel=0.001, mirror=True)
    gb.obj("fender.bolts", "alloy", mirror=True)


# ---------------------------------------------------------------------------------------
# the arms: wing sections from fuselage to fenders, the fore pair the car's canards
# ---------------------------------------------------------------------------------------
ARMS = dict(
    f1=((2.035, 0.105, 0.322), (1.955, FEN_F["yi"] + 0.066, 0.350), 0.24, 0.030, 0.19),
    f2=((1.130, 0.215, 0.530), (1.170, FEN_F["yi"] + 0.004, 0.615), 0.17, 0.026, 0.14),
    r1=((-0.950, 0.305, 0.505), (-0.985, FEN_R["yi"] + 0.028, 0.455), 0.21, 0.030, 0.17),
    r2=((-1.640, 0.110, 0.705), (-1.700, FEN_R["yi"] + 0.004, 0.665), 0.17, 0.026, 0.14),
)


def build_arms():
    g, gf, gl = Geo(), Geo(), Geo()
    for key, (a, b, c, t, c2) in ARMS.items():
        a = V3(a)
        if key in ("f1", "f2", "r1"):                   # roots on the body as built
            p = side_pt(a.x, a.z)
            if p is not None:
                a = V3((a.x, p.y - 0.004, a.z))
        arm(g, gf, a, b, c, t, c2)
        ARMS[key] = (a, V3(b), c, t, c2)
    # the canards' hairlines, along their leading edges
    a, b, c, t, c2 = ARMS["f1"]
    blade(gl, [a + V3((c * 0.5 + 0.002, 0.03, 0.0)), b + V3((c2 * 0.5 + 0.002, -0.03, 0.0))],
          0.006, 0.006)
    g.obj("arms", "weave", bevel=0.0015, mirror=True)
    gf.obj("arms.roots", "alloy", bevel=0.002, mirror=True)
    gl.obj("led.canard", "led_front", mirror=True)


# ---------------------------------------------------------------------------------------
# spine: the front jump, the fin and its plate, the wing
# ---------------------------------------------------------------------------------------
FIN_A, FIN_B, FIN_H = V3((-1.235, 0, 0.730)), V3((-2.20, 0, 0.870)), 0.15
WING_Z = 0.935


def fin_top(x):
    t = (FIN_A.x - x) / (FIN_A.x - FIN_B.x)
    return FIN_A.z + (FIN_B.z - FIN_A.z) * t + FIN_H / 2


def airfoil(x0, z0, c, th=1.0):
    """A downforce section: leading edge at x0, chord c toward the rear, the tail kicked up."""
    return [(x0, z0 + 0.020 * th), (x0 - 0.12 * c, z0 + 0.040 * th),
            (x0 - 0.55 * c, z0 + 0.046 * th), (x0 - c, z0 + 0.105 * th),
            (x0 - 0.96 * c, z0 + 0.075 * th), (x0 - 0.55 * c, z0 + 0.012 * th),
            (x0 - 0.18 * c, z0)]


def build_spine():
    g = Geo()
    # the front jump: nose pod to fuselage, its top flange in line with the inlaid strips
    drilled(g, (1.755, 0, 0.412), (1.485, 0, 0.440), 0.115, 0.022, flw=0.066)
    tube(g, [(1.755, 0, 0.232), (1.485, 0, 0.222)], 0.016)
    tube(g, [(1.74, 0, 0.360), (1.62, 0, 0.230)], 0.011)
    tube(g, [(1.62, 0, 0.230), (1.50, 0, 0.385)], 0.011)
    # the fin: the beam from the cabin's bulkhead to the wing
    drilled(g, FIN_A, FIN_B, FIN_H, 0.022, flw=0.066)
    # a swan neck over the wing
    drilled(g, (-2.165, 0, 0.930), (-2.30, 0, 1.055), 0.085, 0.016, fl=0.008, flw=0.034)
    g.box((-2.26, 0, 0.985), (0.10, 0.05, 0.014))
    g.obj("spine", "alloy", bevel=0.0025)
    # the fin's plate: a weave blade from the canopy's crown to the swan neck
    g = Geo()
    zc = top_z(-0.62, 0.0, 0.97)
    zb = top_z(-1.20, 0.0, 0.80)
    g.prism([(-0.62, -0.006, zc - 0.004), (-2.33, -0.006, 1.070), (-2.36, -0.006, 1.020),
             (-2.19, -0.006, fin_top(-2.19) - 0.002), (-1.25, -0.006, fin_top(-1.25) - 0.002),
             (-1.20, -0.006, zb - 0.003), (-0.90, -0.006, top_z(-0.90, 0.0, 0.9) - 0.004)],
            (0, 0.012, 0))
    g.obj("fin", "weave", bevel=0.002)
    g = Geo()                                   # a raw strip on the fin's top edge
    blade(g, [(-0.62, 0, zc + 0.002), (-2.33, 0, 1.074)], 0.020, 0.006)
    g.obj("fin.cap", "alloy", bevel=0.001)
    # the inlaid strips' fasteners, two rows
    g = Geo()
    prof = [(-0.002, 0.001), (-0.002, 0.0065), (0.0022, 0.0065), (0.0022, 0.001)]
    for x in [2.32 - 0.11 * k for k in range(6)] + [1.44 - 0.105 * k for k in range(20)]:
        loc, n = on_body(x, 0.020, 'z')
        if loc is not None:
            stud(g, loc, n, prof, 6)
    g.obj("spine.bolts", "gloss_black", mirror=True)

    # ---- the wing: one deep plane under the swan neck, a flap, endplates
    g = Geo()
    g.prism([(x, -0.80, z) for (x, z) in airfoil(-2.04, WING_Z, 0.40)], (0, 1.60, 0))
    g.prism([(x, -0.80, z) for (x, z) in airfoil(-2.40, WING_Z + 0.105, 0.075, 0.5)],
            (0, 1.60, 0))
    for s in (1, -1):
        g.prism([(-1.96, s * 0.806 - 0.006, 0.900), (-2.02, s * 0.806 - 0.006, 1.075),
                 (-2.485, s * 0.806 - 0.006, 1.075), (-2.485, s * 0.806 - 0.006, 0.800),
                 (-2.30, s * 0.806 - 0.006, 0.745), (-2.10, s * 0.806 - 0.006, 0.790)],
                (0, 0.012, 0))
    g.obj("wing.rear", "weave", bevel=0.002)
    g = Geo()
    g.box((-2.488, 0.45, WING_Z + 0.150), (0.006, 0.68, 0.007))
    g.box((-2.488, 0.806, 0.935), (0.005, 0.008, 0.25))
    g.obj("led.wing.rear", "led_rear", mirror=True)
    g = Geo()                                   # stays from the endplates down to the fin
    for s in (1, -1):
        tube(g, [(-2.16, s * 0.795, 0.800), (-2.12, s * 0.035, fin_top(-2.12) - 0.07)], 0.008)
    g.obj("wing.rear.stays", "alloy")
    gt = Geo()
    for s in (1, -1):
        text_flat(gt, "VEX", 0.105, (-2.25, s * 0.8135, 0.965), (-s, 0, 0), (0, 0, 1),
                  spacing=1.15)
        text_flat(gt, NUM, 0.07, (-2.37, s * 0.8135, 0.835), (-s, 0, 0), (0, 0, 1))
        text_flat(gt, NUM, 0.105, (-1.78, s * 0.0075, 0.958), (-s, 0, 0), (0, 0, 1))
        text_flat(gt, "STRIX", 0.050, (-1.34, s * 0.0075, 0.918), (-s, 0, 0), (0, 0, 1),
                  spacing=1.25)
    gt.obj("wing.lettering", "decal")


# ---------------------------------------------------------------------------------------
# floor, tunnels, diffuser, splitter
# ---------------------------------------------------------------------------------------
def build_floor():
    z0, dz = FLOOR_Z0, FLOOR_Z1 - FLOOR_Z0
    g = Geo()
    # the plank under the fuselage: narrow, so the ground shows beside it
    g.prism([(x, y, z0) for (x, y) in ((1.30, -0.20), (1.30, 0.20), (1.02, 0.50),
                                         (-1.10, 0.50), (-1.10, -0.50), (1.02, -0.50))],
            (0, 0, dz))
    # the tunnels' mouths: the leading edge kicked up either side of the keel
    for s in (1, -1):
        g.prism([(1.30, s * 0.20, z0), (1.30, s * 0.20, z0 + dz), (1.48, s * 0.22, 0.135),
                 (1.48, s * 0.22, 0.118)], (0, s * 0.01, 0))
        y0, y1 = (0.21, 0.50) if s > 0 else (-0.50, -0.21)
        g.prism([(1.02, y0, z0), (1.02, y0, z0 + dz), (1.30, y0, 0.150), (1.30, y0, 0.132)],
                (0, y1 - y0, 0))
        # the tunnels' fences
        g.prism([(1.30, s * 0.50 - 0.005, 0.132), (1.30, s * 0.50 - 0.005, 0.205),
                 (0.95, s * 0.50 - 0.005, 0.125), (-1.10, s * 0.50 - 0.005, 0.125),
                 (-1.10, s * 0.50 - 0.005, z0), (1.02, s * 0.50 - 0.005, z0)], (0, 0.010, 0))
    g.obj("floor", "plank", bevel=0.002)
    # splitter under the nose pod, on two drilled pylons
    g = Geo()
    g.prism([(x, y, 0.070) for (x, y) in ((2.45, -0.10), (2.45, 0.10), (2.26, 0.36),
                                            (1.78, 0.30), (1.78, -0.30), (2.26, -0.36))],
            (0, 0, 0.016))
    for s in (1, -1):
        g.prism([(2.26, s * 0.36 - 0.005, 0.070), (2.30, s * 0.36 - 0.005, 0.170),
                 (1.92, s * 0.36 - 0.005, 0.170), (1.78, s * 0.36 - 0.005, 0.070)],
                (0, 0.010, 0))
    g.obj("splitter", "weave", bevel=0.002)
    g = Geo()
    for y in (0.055, -0.055):
        drilled(g, (2.16, y, 0.090), (2.13, y, 0.262), 0.095, 0.010, fl=0.008, flw=0.022)
    g.obj("splitter.pylons", "alloy", bevel=0.0015)

    # ---- the diffuser: two tunnels' roof ramping up between the rear wheels, tall strakes
    g = Geo()
    X0, X1, Z1 = -1.10, -2.42, 0.430
    g.prism([(X0, -0.565, z0), (X0, -0.565, z0 + dz), (X1, -0.565, Z1 + 0.018),
             (X1, -0.565, Z1)], (0, 1.13, 0))
    for y in (-0.375, -0.19, 0.19, 0.375):
        g.prism([(X0 - 0.10, y - 0.005, 0.072), (X1, y - 0.005, Z1 + 0.005),
                 (X1 - 0.03, y - 0.005, 0.105), (-1.55, y - 0.005, 0.045)], (0, 0.010, 0))
    for y in (-0.56, 0.56):                             # the outer pair: fins under the roof
        g.prism([(X0 - 0.10, y - 0.005, 0.072), (X1, y - 0.005, Z1 + 0.005),
                 (X1 - 0.03, y - 0.005, 0.245), (-1.75, y - 0.005, 0.105)], (0, 0.010, 0))
    # the keel between the tunnels, a blade that carries the rain light
    g.prism([(-1.30, -0.008, 0.075), (X1, -0.008, Z1 + 0.005), (X1 - 0.06, -0.008, 0.30),
             (X1 - 0.06, -0.008, 0.075), (-1.60, -0.008, 0.040)], (0, 0.016, 0))
    g.obj("diffuser", "plank", bevel=0.002)
    g = Geo()
    for s in (1, -1):
        blade(g, [(0.93, s * 0.506, 0.125), (-1.08, s * 0.506, 0.125)], 0.006, 0.016)
    g.obj("floor.edge", "alloy", bevel=0.001)
    # the fuselage and nose stand off the floor on drilled rings
    g = Geo()
    for x in (0.85, 0.25, -0.35, -0.90):
        for y in (0.13, -0.13):
            ring(g, (x, y, FLOOR_Z1 + 0.030), (0, 1, 0), 0.036, 0.021, 0.012)
    ring(g, (2.02, 0, 0.165), (0, 1, 0), 0.078, 0.048, 0.012)
    g.obj("standoffs", "alloy", bevel=0.002)


# ---------------------------------------------------------------------------------------
# suspension: blades, rods, rockers and dampers in plain sight
# ---------------------------------------------------------------------------------------
def damper(g, gs, a, b, r=0.020):
    """A coil-over from a to b: a body in g, the spring's coils in gs."""
    a, b = V3(a), V3(b)
    d = (b - a)
    L = d.length
    xf = Matrix.Translation(a) @ V3((0, 1, 0)).rotation_difference(
        d.normalized()).to_matrix().to_4x4()
    g.lathe([(0, 0.002), (0, r * 0.55), (L * 0.45, r * 0.55), (L * 0.45, r * 0.8), (L, r * 0.8),
             (L, 0.002)], 10, xf=xf)
    for k in range(7):
        y = L * (0.10 + 0.105 * k)
        gs.lathe([(y, r * 0.95), (y, r * 1.3), (y + L * 0.045, r * 1.3), (y + L * 0.045, r * 0.95)],
                 10, xf=xf)


def my_(p):
    return V3((p.x, -p.y, p.z))


def rear_rail(z0, z1):
    return V3((-1.245, 0.215, z0)), V3((-1.86, 0.150, z1))


def build_suspension():
    gb, ga, gs = Geo(), Geo(), Geo()                # weave blades, alloy, springs
    # ---- front: pickups on the nose pod and the fuselage as built
    yo = F_IN - 0.035
    up_o, lo_o = V3((FA_X, yo, 0.470)), V3((FA_X, yo, 0.180))
    for (o, z) in ((up_o, 0.405), (lo_o, 0.240)):
        for x in (1.84, 1.26):
            p = side_pt(x, z) or V3((x, 0.14, z))
            blade(gb, [p + V3((0, -0.01, 0)), o], 0.052, 0.011)
            ga.box(p, (0.07, 0.03, 0.035))
        ball(ga, o, 0.022)
    rk = V3((FA_X - 0.06, 0.100, top_z(FA_X - 0.06, 0.100) + 0.035))
    tube(ga, [lo_o + V3((0, -0.05, 0.03)), rk], 0.010)                      # pushrod
    ga.prism([rk + V3((0.05, -0.006, -0.03)), rk + V3((-0.05, -0.006, -0.03)),
              rk + V3((-0.02, -0.006, 0.035)), rk + V3((0.03, -0.006, 0.035))], (0, 0.012, 0))
    ring(ga, rk, (0, 1, 0), 0.016, 0.006, 0.02, 10)
    e = V3((FA_X - 0.36, 0.090, top_z(FA_X - 0.36, 0.090) + 0.030))
    damper(ga, gs, e, rk + V3((-0.02, 0, 0.02)))
    tp = side_pt(1.40, 0.335) or V3((1.40, 0.2, 0.335))
    tube(ga, [tp, (FA_X + 0.11, yo, 0.335)], 0.008)                         # steering rod
    ga.box((FA_X, yo + 0.012, F_R - 0.03), (0.10, 0.045, 0.34))             # the upright
    ga.box((FA_X + 0.08, yo, 0.335), (0.09, 0.03, 0.04))
    ga.lathe([(yo - 0.01, 0.002), (yo - 0.01, 0.045), (F_IN + 0.05, 0.045), (F_IN + 0.05, 0.002)],
             12, xf=Matrix.Translation((FA_X, 0, F_R)))

    # ---- rear: a tube frame round the motor carries the pickups
    frame = Geo()
    ua, ub = rear_rail(0.640, 0.640)
    la, lb = rear_rail(0.300, 0.300)
    for (a, b) in ((ua, ub), (la, lb)):
        tube(frame, [a, b], 0.014)
    for t in (0.36, 1.0):
        tube(frame, [ua.lerp(ub, t), la.lerp(lb, t)], 0.011)
    tube(frame, [ua.lerp(ub, 0.0), la.lerp(lb, 0.36)], 0.010)
    tube(frame, [ua.lerp(ub, 0.36), la.lerp(lb, 1.0)], 0.010)
    tube(frame, [ub, (ub.x - 0.10, 0.03, fin_top(ub.x - 0.10) - FIN_H + 0.01)], 0.011)
    tube(frame, [ua.lerp(ub, 0.36), (-1.50, 0.03, fin_top(-1.50) - FIN_H + 0.01)], 0.011)
    tube(frame, [lb, (lb.x - 0.02, 0.19, 0.180)], 0.010)          # down to the diffuser
    frame.obj("frame.rear", "alloy", mirror=True)
    frame = Geo()
    tube(frame, [lb, my_(lb)], 0.012)
    tube(frame, [ub, my_(ub)], 0.012)
    frame.obj("frame.rear.cross", "alloy")

    yo = R_IN - 0.03
    up_o, lo_o = V3((RA_X, yo, 0.490)), V3((RA_X, yo, 0.205))
    for (o, a, b) in ((up_o, ua, ub), (lo_o, la, lb)):
        for t in (0.04, 0.90):
            p = a.lerp(b, t)
            blade(gb, [p, o], 0.052, 0.011)
            ga.box(p, (0.06, 0.035, 0.035))
        ball(ga, o, 0.022)
    rk = V3((RA_X + 0.02, 0.085, fin_top(RA_X + 0.02) - FIN_H - 0.035))
    tube(ga, [lo_o + V3((0, -0.05, 0.03)), rk], 0.010)
    ga.prism([rk + V3((0.05, -0.006, -0.03)), rk + V3((-0.05, -0.006, -0.03)),
              rk + V3((-0.03, -0.006, 0.035)), rk + V3((0.02, -0.006, 0.035))], (0, 0.012, 0))
    ring(ga, rk, (0, 1, 0), 0.016, 0.006, 0.02, 10)
    e = V3((RA_X - 0.34, 0.085, fin_top(RA_X - 0.34) - FIN_H - 0.030))
    damper(ga, gs, e, rk + V3((-0.02, 0, 0.0)))
    ga.box((RA_X, yo + 0.01, R_R - 0.02), (0.10, 0.045, 0.36))
    ga.lathe([(0.17, 0.004), (0.17, 0.021), (R_IN + 0.05, 0.021), (R_IN + 0.05, 0.045),
              (R_IN + 0.06, 0.045), (R_IN + 0.06, 0.004)], 12,
             xf=Matrix.Translation((RA_X, 0, R_R)))                          # the half shaft
    for y in (0.21, yo - 0.07):
        ga.lathe([(y - 0.035, 0.022), (y, 0.040), (y + 0.035, 0.022)], 12,
                 xf=Matrix.Translation((RA_X, 0, R_R)))
    gb.obj("wishbones", "carbon", bevel=0.0025, mirror=True)
    ga.obj("suspension", "alloy", bevel=0.002, mirror=True)
    gs.obj("springs", "paint", mirror=True)


# ---------------------------------------------------------------------------------------
# power unit, radiators, cables: nothing skinned behind the cabin
# ---------------------------------------------------------------------------------------
def build_power():
    g = Geo()
    c = Matrix.Translation((RA_X, 0, R_R))
    prof = [(-0.17, 0.004), (-0.17, 0.105)]
    for k in range(12):                                 # a finned casing
        y = -0.150 + 0.025 * k
        prof += [(y, 0.105), (y, 0.134), (y + 0.012, 0.134), (y + 0.012, 0.105)]
    prof += [(0.17, 0.105), (0.17, 0.004)]
    g.lathe(prof, 28, xf=c)
    g.box((RA_X - 0.20, 0, 0.365), (0.16, 0.26, 0.18))                      # reduction gear
    for k in range(5):
        g.box((RA_X - 0.20, -0.10 + 0.05 * k, 0.365), (0.172, 0.012, 0.194))
    g.box((RA_X, 0, 0.535), (0.14, 0.09, 0.07))                             # hanger
    g.obj("motor", "alloy_dark", bevel=0.0025)
    g = Geo()
    back = Matrix.Translation((RA_X - 0.282, 0, 0.365)) @ Matrix.Rotation(pi / 2, 4, 'Z')
    g.lathe([(0.0, 0.004), (0.0, 0.074), (0.012, 0.074), (0.018, 0.060), (0.018, 0.004)], 20,
            xf=back)
    for k in range(8):
        a = 2 * pi * k / 8
        g.lathe([(0.010, 0.001), (0.010, 0.0065), (0.017, 0.0065), (0.017, 0.001)], 6,
                xf=back @ Matrix.Translation((0.066 * cos(a), 0, 0.066 * sin(a))))
    for s in (1, -1):
        g.lathe([(s * 0.172, 0.03), (s * 0.172, 0.085), (s * 0.19, 0.07), (s * 0.19, 0.03)],
                6, xf=c)
    g.obj("motor.cover", "alloy", bevel=0.0015)
    # the inverter on the bulkhead: a ribbed box with lit seams
    g, ge = Geo(), Geo()
    g.box((-1.305, 0, 0.455), (0.11, 0.34, 0.22))
    for k in range(5):
        g.box((-1.305, -0.13 + 0.065 * k, 0.455), (0.122, 0.020, 0.232))
    ge.box((-1.305, 0, 0.455), (0.114, 0.31, 0.012))
    g.obj("inverter", "alloy_dark", bevel=0.003)
    ge.obj("inverter.glow", "ember")
    # three orange phases to the motor, the loom clipped along the fin
    g = Geo()
    for y in (-0.07, 0.0, 0.07):
        tube(g, [(-1.36, y, 0.520), (-1.40, y * 1.1, 0.565), (-1.45, y * 1.2, 0.580),
                 (-1.50, y * 1.2, 0.560), (-1.52, y * 1.2, 0.500)], 0.011)
    g.obj("cables.hv", "cable", sharp=60)
    g = Geo()
    zb = lambda x: fin_top(x) - FIN_H / 2                   # noqa: E731
    for s in (1, -1):
        tube(g, [(-1.25, s * 0.10, 0.70), (-1.32, s * 0.038, zb(-1.32) + 0.02),
                 (-2.10, s * 0.038, zb(-2.10) + 0.02), (-2.18, s * 0.03, 0.90)], 0.006)
        # coolant lines: radiator cores to the motor, bright tube
        tube(g, [(-1.105, s * 0.40, 0.300), (-1.20, s * 0.34, 0.285), (-1.34, s * 0.25, 0.285),
                 (-1.40, s * 0.18, 0.330)], 0.013)
        tube(g, [(-1.105, s * 0.40, 0.585), (-1.20, s * 0.30, 0.600), (-1.34, s * 0.17, 0.560),
                 (-1.42, s * 0.12, 0.490)], 0.010)
    g.obj("lines", "alloy", sharp=60)
    g = Geo()
    for x in (-1.45, -1.70, -1.95):                         # clips holding the loom
        g.box((x, 0, zb(x) + 0.02), (0.016, 0.094, 0.02))
    g.obj("clips", "gloss_black")
    # radiator cores, bare, standing in the gaps beside the bulkhead
    g, gf = Geo(), Geo()
    X = -1.115
    poly = [(0.300, 0.300), (0.545, 0.300), (0.545, 0.590), (0.300, 0.590)]
    g.honeycomb(poly, X, 0.013, 0.0024, 0.030, 1)
    loop = [(X + 0.015, y, z) for (y, z) in poly]
    blade(gf, loop + [loop[0], loop[1]], 0.040, 0.012, up=(1, 0, 0))
    tube(gf, [(X + 0.015, 0.300, 0.52), (-1.20, 0.235, 0.52)], 0.008)
    tube(gf, [(X + 0.015, 0.300, 0.36), (-1.20, 0.215, 0.36)], 0.008)
    g.obj("rad.core", "copper", mirror=True)
    gf.obj("rad.frame", "alloy", bevel=0.0015, mirror=True)


# ---------------------------------------------------------------------------------------
# lights: three-dot clusters on stalks
# ---------------------------------------------------------------------------------------
def cluster(g, gl, root, head, facing, mat_r=0.013):
    """A stalk from root to a three-dot cluster at head, facing along x (1 or -1)."""
    root, head = V3(root), V3(head)
    tube(g, [root, root.lerp(head, 0.6) + V3((0, 0, 0.02)), head], 0.007)
    g.box(head, (0.05, 0.118, 0.040))
    for k in (-1, 0, 1):
        c = head + V3((facing * 0.026, k * 0.036, 0))
        xf = Matrix.Translation(c) @ Matrix.Rotation(pi / 2, 4, 'Z')
        gl.lathe([(-0.004, 0.001), (-0.004, mat_r), (0.004, mat_r), (0.004, 0.001)], 12, xf=xf)


def build_lights():
    g, gl, gr = Geo(), Geo(), Geo()
    p = side_pt(2.00, 0.36) or V3((2.00, 0.11, 0.36))
    cluster(g, gl, p, (2.10, 0.375, 0.455), 1)
    cluster(g, gr, (-2.14, 0.03, fin_top(-2.14) - 0.10), (-2.30, 0.33, 0.700), -1)
    g.obj("stalks", "carbon", bevel=0.002, mirror=True)
    gl.obj("led.front", "lamp", mirror=True)
    gr.obj("led.rear", "led_rear", mirror=True)
    g = Geo()                                   # the rain light on the diffuser's keel
    g.box((-2.488, 0, 0.215), (0.012, 0.022, 0.15))
    g.obj("led.rain", "led_rear")
    g = Geo()                                   # amber markers on the rear fenders' noses
    S = PT["fenr"]
    a, b = S[0][2].lerp(S[0][3], 0.3), S[0][2].lerp(S[0][3], 0.7)
    blade(g, [a + V3((0.006, 0, 0.004)), b + V3((0.006, 0, 0.004))], 0.008, 0.006)
    g.obj("led.marker", "led_accent", mirror=True)


# ---------------------------------------------------------------------------------------
# the cabin: two seats in tandem under the canopy
# ---------------------------------------------------------------------------------------
def build_cabin():
    g = Geo()
    g.box((0.10, 0, 0.158), (2.10, 0.42, 0.016))                    # floor
    g.box((-1.10, 0, 0.50), (0.02, 0.44, 0.60))                     # rear wall
    g.prism([(1.02, -0.20, 0.30), (1.02, -0.20, 0.555), (0.86, -0.22, 0.60),
             (0.74, -0.22, 0.56), (0.80, -0.20, 0.30)], (0, 0.42, 0))       # dash
    for s in (1, -1):                                               # sill liners
        g.box((-0.05, s * 0.268, 0.36), (1.75, 0.012, 0.36))
    g.obj("cabin.tub", "interior", bevel=0.004)
    gsh, gp, gbelt, gi, gscr, ga = Geo(), Geo(), Geo(), Geo(), Geo(), Geo()
    tilt = Matrix.Rotation(rad(-26), 3, 'Y')
    for (x, w) in ((0.36, 0.36), (-0.44, 0.34)):
        gsh.box((x, 0, 0.205), (0.48, w + 0.04, 0.03))
        gsh.box((x - 0.305, 0, 0.455), (0.035, w + 0.04, 0.56), rot=tilt)
        for s in (-1, 1):
            gsh.box((x - 0.03, s * (w / 2 + 0.01), 0.245), (0.42, 0.022, 0.10))
            gsh.box((x - 0.28, s * (w / 2 + 0.01), 0.47), (0.11, 0.022, 0.46), rot=tilt)
        gp.box((x + 0.01, 0, 0.232), (0.40, w - 0.04, 0.04))
        gp.box((x - 0.275, 0, 0.445), (0.04, w - 0.04, 0.42), rot=tilt)
        gp.box((x - 0.405, 0, 0.725), (0.055, 0.20, 0.13), rot=tilt)
        for s in (-1, 1):
            gbelt.box((x - 0.250, s * 0.065, 0.47), (0.008, 0.045, 0.40), rot=tilt)
        gbelt.box((x - 0.01, 0, 0.256), (0.05, w - 0.06, 0.008))
    # the driver's yoke and screen, the passenger's screen and grab bar on the hoop
    yk = Matrix.Translation((0.70, 0, 0.505)) @ Matrix.Rotation(rad(-24), 4, 'Y')
    gi.box((0, 0, 0), (0.028, 0.26, 0.035), xf=yk)
    for s in (-1, 1):
        gi.box((0, s * 0.13, 0.04), (0.032, 0.032, 0.11), xf=yk)
    tube(gi, [(0.705, 0, 0.50), (0.84, 0, 0.47)], 0.014)
    scr = Matrix.Rotation(rad(-22), 3, 'Y')
    gscr.box((0.795, 0, 0.600), (0.006, 0.30, 0.070), rot=scr)
    gscr.box((-0.105, 0, 0.560), (0.006, 0.22, 0.080), rot=Matrix.Rotation(rad(-26), 3, 'Y'))
    # the hoop between the two: a drilled post each side, an arch under the canopy
    arch = [(-0.16, 0.262, 0.30), (-0.16, 0.258, 0.640), (-0.16, 0.165, 0.845),
            (-0.16, 0.0, 0.915), (-0.16, -0.165, 0.845), (-0.16, -0.258, 0.640),
            (-0.16, -0.262, 0.30)]
    ga.sweep(arch, [(-0.016, -0.018), (0.016, -0.018), (0.016, 0.018), (-0.016, 0.018)],
             up=(1, 0, 0))
    for s in (1, -1):
        tube(ga, [(-0.165, s * 0.20, 0.80), (-0.80, s * 0.10, 0.80)], 0.011)
        ring(ga, (-0.16, s * 0.15, 0.80), (1, 0, 0), 0.045, 0.027, 0.012, 14)
    tube(gi, [(-0.185, -0.14, 0.52), (-0.185, 0.14, 0.52)], 0.010)
    gsh.obj("seat.shells", "carbon", bevel=0.004)
    gp.obj("seat.pads", "seat", bevel=0.012, segs=3)
    gbelt.obj("seat.belts", "belt")
    gi.obj("cabin.trim", "interior", bevel=0.003)
    gscr.obj("cabin.screens", "screen")
    ga.obj("hoop", "alloy", bevel=0.004, segs=2)
    # canopy hardware: hinges along the right sill, a release on the left, mirrors on stalks
    g, gm = Geo(), Geo()
    for x in (0.35, -0.45):
        p = on_body(x, 0.655, 'Y')[0]
        if p is not None:
            g.box(p + V3((0, -0.006, 0)), (0.085, 0.016, 0.030))
    p = on_body(0.20, 0.60, 'y')[0]
    if p is not None:
        g.box(p + V3((0, 0.004, 0)), (0.11, 0.010, 0.022))
    g.obj("canopy.hardware", "alloy", bevel=0.002)
    g = Geo()
    root = side_pt(0.86, 0.50) or V3((0.86, 0.28, 0.50))
    head = V3((0.80, 0.50, 0.640))
    tube(g, [root, root.lerp(head, 0.55) + V3((0, 0, 0.03)), head], 0.006)
    g.hexa([head + V3(o) for o in ((0.035, -0.055, -0.03), (0.035, 0.055, -0.03),
                                    (-0.012, 0.06, -0.034), (-0.012, -0.06, -0.034),
                                    (0.035, -0.055, 0.03), (0.035, 0.055, 0.03),
                                    (-0.012, 0.06, 0.034), (-0.012, -0.06, 0.034))])
    gm.box(head + V3((-0.0135, 0, 0)), (0.003, 0.105, 0.055))
    g.obj("mirrors", "weave", bevel=0.003, mirror=True)
    gm.obj("mirror.glass", "mirror", mirror=True)


# ---------------------------------------------------------------------------------------
# lettering and small things on the pods as built
# ---------------------------------------------------------------------------------------
def build_details(fen):
    gd, gi, gw = Geo(), Geo(), Geo()                    # plates, dark ink, light ink
    fr = fen["fenr"]
    for side in (1, -1):
        # the number on a light plate on each rear fender, the name on the fuselage
        block(gd, gi, NUM, 0.070, RA_X - 0.02, 0.705, side, pad=0.010, wide=0.15, objs=fr)
        text_on_body(gi, "VEX", 0.028, FA_X - 0.02, 0.690, side, spacing=1.3, objs=fen["fenf"])
        block(gd, gi, NUM, 0.092, -0.14, 0.570, side, pad=0.012, wide=0.19)
        text_on_body(gi, "STRIX", 0.056, 0.36, 0.560, side, spacing=1.25)
        text_on_body(gi, "VEX SKELETAL WORKS", 0.015, 0.36, 0.506, side, spacing=1.3)
        block(gd, gi, "OHMIC", 0.026, -0.62, 0.592, side, pad=0.008)
        block(gd, gi, "NULLWERK", 0.022, -0.63, 0.542, side, pad=0.008)
        text_on_body(gw, "KITE FLUIDS", 0.022, 0.55, 0.330, side, spacing=1.2)
        text_on_body(gw, "LIFT HERE", 0.014, -0.80, 0.360, side, spacing=1.2)
        text_on_body(gi, "S-" + NUM, 0.032, 2.02, 0.365, side, spacing=1.1)
        text_on_body(gw, "TANDEM 1+1", 0.014, 1.20, 0.330, side, spacing=1.2)
    for s in (1, -1):
        text_on_body(gi, NUM, 0.085, 1.28, s * 0.090, s, proj='z')
    gd.obj("decal.plates", "decal")
    gi.obj("decal.ink", "ink")
    gw.obj("decal.light", "decal")
    # fasteners along the fuselage's color split and the nose's
    g = Geo()
    prof = [(-0.002, 0.001), (-0.002, 0.006), (0.002, 0.006), (0.002, 0.001)]
    for x in [1.40 - 0.16 * k for k in range(17)]:
        for dz in (0.016, -0.016):
            t = (1.50 - x) / 2.74
            zw = 0.372 + (0.47 - 0.372) * min(1.0, (1.50 - x) / 1.0) + 0.03 * max(0.0, t - 0.45)
            loc, n = on_body(x, zw + dz, 'y')
            if loc is not None:
                stud(g, loc, n, prof, 6)
    for x in (2.30, 2.16, 2.02, 1.88):
        loc, n = on_body(x, 0.255 - 0.06 * (2.30 - x), 'y')
        if loc is not None:
            stud(g, loc, n, prof, 6)
    g.obj("fasteners", "alloy", mirror=True)
    g = Geo()                                           # a tow eye and a pitot on the nose
    ring(g, (2.435, 0, 0.252), (0, 1, 0), 0.032, 0.019, 0.010, 16)
    tube(g, [(2.41, 0, 0.300), (2.475, 0, 0.300)], 0.004)
    g.obj("nose.bits", "alloy")


# ---------------------------------------------------------------------------------------
# views and the build
# ---------------------------------------------------------------------------------------
for v in K.VIEWS.values():
    v["target"] = (0, 0, 0.45)
K.VIEWS["hero"].update(dir=(1.0, 0.70, 0.36), focus=(1.4, 0.7, 0.4), fstop=11.0)
K.VIEWS["rear"].update(dir=(-1.0, -0.78, 0.36), focus=(-1.5, -0.7, 0.5), fstop=11.0)
K.VIEWS.update(
    through=dict(dir=(1.0, 0.0, 0.95), lens=90, target=(0, 0, 0.35)),
    gap=dict(dir=(0.9, 0.5, 0.5), lens=85, target=(1.3, 0.4, 0.4), dist=4.6),
    tail=dict(dir=(-1.0, 0.6, 0.30), lens=85, target=(-1.5, 0.2, 0.5), dist=4.8),
    cabin=dict(dir=(0.3, 1.0, 0.45), lens=85, target=(-0.1, 0.0, 0.6), dist=4.2),
)


def main():
    col = (0.0, 0.15, 0.235)                                     # arc cyan
    K.materials(paint=col, paint_finish="gloss", dust_amount=0.10, caliper=col,
                seat=(0.035, 0.035, 0.04), rim=(0.22, 0.225, 0.235),
                rim_bright=(0.62, 0.63, 0.65), decal=(0.82, 0.82, 0.80),
                screen=(0.2, 0.8, 1.0), led_front=(0.85, 0.95, 1.0),
                led_accent=(1.0, 0.45, 0.03), ember=(0.10, 0.75, 1.0))
    K.pbr("alloy", (0.56, 0.57, 0.59), 1.0, 0.30)           # raw machined metal
    K.pbr("alloy_dark", (0.16, 0.165, 0.175), 1.0, 0.42)
    K.pbr("copper", (0.70, 0.36, 0.17), 1.0, 0.38)
    K.pbr("cable", (0.95, 0.30, 0.02), 0.0, 0.45)
    K.pbr("belt", (0.80, 0.80, 0.78), 0.0, 0.7)
    K.pbr("ink", (0.012, 0.012, 0.014), 0.0, 0.5)
    K.pbr("mirror", (0.75, 0.77, 0.80), 1.0, 0.03)
    K.pbr("plank", (0.016, 0.016, 0.018), 0.0, 0.62)
    # wings, arms and fin: a dry lay-up (the kit's coated weave turns silver on a flat plane
    # seen at a grazing angle against the studio's rim light)
    _, b = K.carbon("weave")
    b.inputs["Metallic"].default_value = 0.0
    b.inputs["Coat Weight"].default_value = 0.0
    b.inputs["Specular IOR Level"].default_value = 0.12
    mr = b.inputs["Roughness"].links[0].from_node
    mr.inputs["To Min"].default_value = 0.60
    mr.inputs["To Max"].default_value = 0.85
    fen = build_pods()
    K.log("pods")
    build_arms()
    build_spine()
    build_floor()
    K.log("arms, spine, floor")
    build_suspension()
    build_power()
    build_lights()
    build_cabin()
    build_fender_details(fen)
    build_details(fen)
    K.log("details")
    for side, s in ((1, "l"), (-1, "r")):
        K.build_wheel("f" + s, FA_X, F_R, F_W, F_RIM, OUT_Y, side, spokes=9, style="blade",
                      ring=None, rim="rim_bright", bright="rim")
        K.build_wheel("r" + s, RA_X, R_R, R_W, R_RIM, OUT_Y, side, spokes=9, style="blade",
                      ring=None, rim="rim_bright", bright="rim")
    K.log("wheels")
    K.shoot(extra=dict(view="top", size=(1000, 470), corner="tl"))


main()
