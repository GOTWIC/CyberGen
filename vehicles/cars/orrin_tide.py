"""Orrin Tide: a five-seat crossover estate poured as one long-roofed drop (both names made
up), built on vehicles/carkit.py.

Run (always through the wrapper, one Blender job at a time on this machine):
    vehicles/blender.sh vehicles/cars/orrin_tide.py --out DIR --preview
    vehicles/blender.sh vehicles/cars/orrin_tide.py --out DIR --sheet [--night]

The body is nine lines over fifteen ring stations with no crease anywhere, the rings closing
on a small pole at the nose and at the tail as on the Lumen: the two lines nearest the top
are the glass canopy, pole to pole, over a nose deck, two rows of seats and a load deck. The
front fenders stand higher than the glass between them; between the wheels the widest line
dives low and comes up again over the rear wheel (the wave). Everything under the tide line,
from under the nose to the tailgate's lower edge, is the keel: a darker panel with a hair of
light along its top between the wheels. A hoop of the body crosses the glass behind the rear
doors, its feet lying down on the haunches; the tailgate (the glass behind the hoop, the tail
and its ribbon) is cut down each quarter with groove() to the keel's corner. The light
ribbons are channels cut into the skin over each wheel and round each pole, a light guide in
each under a lens; the crescent head and stop lamps are pockets under lenses cut from the
skin; the door pulls, the charge flaps, the wake crescents and the wheel openings are cut
too (cutters(), on the hull as it stands uncut). skin(u, v) is the built surface in the
cage's own coordinates: what lies on the body is laid out in them. The brand's helpers are
in vehicles/brands/orrin.py. TIDE_PROBE=1 prints the skin's position round the wheels and
what skin() is off by.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import carkit as K                                                  # noqa: E402
from brands import orrin                                            # noqa: E402
from brands.orrin import (both, dot_field, lune_cut, ring, snap, spline, stone,   # noqa: E402
                          strip, text_proj)
from carkit import Geo, Matrix, V3, cos, on_body, pi, rad, sin, text_flat   # noqa: E402

orrin.setup(axis=(1.9, 0.80))       # normals turned away from the car's axis
PROBE = bool(os.environ.get("TIDE_PROBE"))
PAINT = (0.30, 0.115, 0.06)         # ember copper

# ---------------------------------------------------------------------------------------
# dimensions
# ---------------------------------------------------------------------------------------
FA_X, RA_X = 1.51, -1.51            # axles: wheelbase 3.02
R, W, RIM = 0.39, 0.25, 0.31        # tire radius, width, rim radius
F_OUT, R_OUT = 0.936, 0.934         # outer face of the tires
LID_A, LID_TOP, LID_Z0 = 0.44, 0.81, 0.33       # the wheel openings: half width, top, waist
NOSE = V3((2.385, 0, 0.66))         # the poles the rings close on
TAIL = V3((-2.395, 0, 0.84))

# ---------------------------------------------------------------------------------------
# body: stations (rings) and lines
# ---------------------------------------------------------------------------------------
LINES = "CGESHULRB"
#        C top centerline, G canopy crown, E canopy edge, S shoulder, H haunch, U widest,
#        L tide line (lower flank), R rocker, B floor centerline
ORDER = ["P0", "N1", "N2", "A1", "FA", "D1", "M1", "D2", "M2", "D3", "RA", "R3", "T2", "T1",
         "T0"]
IX = {k: i for i, k in enumerate(ORDER)}
PT = {}
SG = []                             # the cage as built: rows of points


def stations():
    T = {
        "N1": [(2.350, 0, .815), (2.349, .060, .814), (2.348, .120, .810), (2.337, .330, .775),
               (2.326, .445, .725), (2.318, .500, .660), (2.326, .450, .560),
               (2.339, .285, .475), (2.347, 0, .445)],
        "N2": [(2.215, 0, .925), (2.212, .150, .918), (2.205, .300, .895), (2.180, .550, .905),
               (2.158, .725, .830), (2.148, .800, .675), (2.158, .760, .500),
               (2.180, .570, .350), (2.195, 0, .300)],
        # the front fenders stand higher than the glass between them (a valley on the E line)
        "A1": ring(1.96, 1.00, (.215, .988), (.43, .945), (.71, 1.01), (.895, .905),
                   (.955, .68), (.925, .45), (.76, .262), .222),
        "FA": ring(FA_X, 1.075, (.28, 1.06), (.55, .985), (.82, 1.085), (.966, .945),
                   (.994, .685), (.968, .432), (.835, .215), .195),
        # the door cuts fan like petals: forward at the top, upright, back at the top
        "D1": ring((1.02, 1.02, 1.01, .995, .96, .915, .88, .87, .87), 1.215, (.40, 1.195),
                   (.715, 1.04), (.85, 1.04), (.94, .89), (.964, .645), (.94, .438),
                   (.84, .20), .19),
        # between the wheels the widest line dives low and the flank draws in (the wave)
        "M1": ring(0.44, 1.535, (.545, 1.445), (.795, 1.065), (.862, 1.012), (.922, .85),
                   (.948, .575), (.922, .445), (.84, .20), .19),
        "D2": ring(-0.10, 1.62, (.60, 1.53), (.82, 1.085), (.868, 1.03), (.92, .85),
                   (.946, .555), (.915, .45), (.84, .20), .19),
        "M2": ring(-0.64, 1.63, (.61, 1.545), (.82, 1.105), (.868, 1.05), (.922, .865),
                   (.948, .575), (.918, .45), (.84, .20), .19),
        "D3": ring((-1.28, -1.28, -1.29, -1.27, -1.225, -1.18, -1.15, -1.14, -1.14), 1.605,
                   (.59, 1.52), (.805, 1.135), (.862, 1.09), (.94, .91), (.968, .65),
                   (.94, .445), (.84, .20), .19),
        # the rear haunch: the shoulder rises over the wheel
        "RA": ring(RA_X, 1.56, (.57, 1.475), (.775, 1.16), (.855, 1.15), (.958, .965),
                   (.988, .705), (.96, .46), (.83, .215), .20),
        "R3": ring(-1.92, 1.42, (.465, 1.345), (.635, 1.16), (.735, 1.12), (.845, .96),
                   (.887, .745), (.867, .545), (.70, .33), .275),
        "T2": [(-2.215, 0, 1.175), (-2.21, .28, 1.142), (-2.20, .41, 1.085),
               (-2.185, .505, 1.035), (-2.165, .595, .935), (-2.155, .642, .805),
               (-2.165, .612, .655), (-2.185, .45, .50), (-2.20, 0, .445)],
        "T1": [(-2.362, 0, .96), (-2.361, .065, .958), (-2.359, .13, .952), (-2.35, .26, .92),
               (-2.342, .33, .885), (-2.335, .37, .84), (-2.342, .335, .765),
               (-2.352, .22, .69), (-2.358, 0, .66)],
    }
    for name, src, pole in (("P0", "N1", NOSE), ("T0", "T1", TAIL)):
        T[name] = [(pole.x, p[1] * 0.22, pole.z + (p[2] - pole.z) * 0.22) for p in T[src]]
        for j in (1, 2):                 # the glass drawn to a fine tip, under the pebble
            x, y, z = T[name][j]
            T[name][j] = (x, y * 0.4, z)
    S = K.fill([T[k] for k in ORDER])
    PT.update(K.table(ORDER, LINES, S))
    SG[:] = [[V3(p) for p in row] for row in S]
    return S


def _bw(t):
    return ((1 - t) ** 3 / 6, (3 * t ** 3 - 6 * t * t + 4) / 6,
            (-3 * t ** 3 + 3 * t * t + 3 * t + 1) / 6, t ** 3 / 6)


def skin(u, v):
    """The built surface at station u (1 at N1 to 13 at T1) and line v (0 at C to 8 at B;
    2 is the glass edge): where no edge is creased, the subdivided cage is a uniform bicubic
    B-spline of its points."""
    n, m = len(SG), len(SG[0])
    u = min(max(u, 1.0), n - 2.0)
    v = min(max(v, 0.0), m - 1.0)
    i, j = min(int(u), n - 3), min(int(v), m - 2)
    bu, bv = _bw(u - i), _bw(v - j)
    p = V3()
    for a in range(4):
        row = SG[i - 1 + a]
        for b in range(4):
            jj = j - 1 + b
            q = row[jj] if 0 <= jj < m else row[1] if jj < 0 else row[m - 2]
            if not 0 <= jj < m:
                q = V3((q.x, -q.y, q.z))
            p += q * (bu[a] * bv[b])
    return p


def curve(uv, n=10):
    """Points of the skin along a smooth curve through (u, v) pairs."""
    return [skin(q.x, q.y) for q in spline([(a, b, 0) for a, b in uv], n)]


PMAT = dict(front="paint", door_f="paint", door_r="paint", keel="keel", rear="paint",
            glass="glass_dome", floor="underbody", well="well", slot="void", cut="void",
            lamp_f="lamp_housing", lamp_r="lamp_housing", lamp_k="lamp_housing",
            lamp_h="lamp_housing", lens_h="lens_clear", lamp_t="lamp_housing",
            lens_t="lens_red", hoop="paint", pull="lamp_housing")
GAP = 0.0012                        # 2.4 mm shut lines, the Orrins'
TREAD = dict(K.TREADS["road"], seg=88)      # the triangle budget: a 0.3 mm chord on its round
LAMP = {}                           # the channels on the skin: key -> (path, width function)
RIB_W, RIB_D, RIB_TIP = 0.018, 0.010, 0.005     # a ribbon channel's width, depth, end width
CHAN_STEP, LAMP_STEP = 0.016, 0.02
LENS_SINK = 0.0012                  # the lenses under the skin: a flush lens's edges stand
                                    # proud where the skin curves tightly across the channel


def panel_of(i, j):
    if j <= 1:                           # the canopy: from the nose pole to the tail pole
        return "glass"
    if j >= 6 and IX["N2"] <= i < IX["T2"]:      # under the tide line, from under the nose
        return "keel" if j == 6 else "floor"     # to the tailgate's lower edge: the keel
    if i < IX["D1"]:                     # one piece from the nose to the front door
        return "front"
    if i < IX["D2"]:
        return "door_f"
    if i < IX["D3"]:
        return "door_r"
    return "rear"


# ---------------------------------------------------------------------------------------
# what is cut into the hull
# ---------------------------------------------------------------------------------------
def lid_pts(cx, a=LID_A, top=LID_TOP, z0=LID_Z0, n=2.6, m=32):
    b = top - z0
    pts = []
    for k in range(m + 1):
        t = pi * k / m
        c, s = cos(t), sin(t)
        pts.append((cx + a * (abs(c) ** (2 / n)) * (1 if c >= 0 else -1),
                    z0 + b * (s ** (2 / n))))
    return pts


def lid(g, cx, y0, y1):
    """A wheel opening and its well in one: a tunnel from y0 out through the skin whose
    section has straight sides and a flattened arch for a top (a superellipse), the brand's
    eyelid drawn clear of the tire. Its edge on the skin is told to the checks."""
    pts = lid_pts(cx)
    tree = K._tree(None)
    for sgn in (1, -1):
        poly = ([V3((pts[0][0], sgn * y0, -0.3))] + [V3((x, sgn * y0, z)) for x, z in pts]
                + [V3((pts[-1][0], sgn * y0, -0.3))])
        g.prism(poly, (0, sgn * (y1 - y0), 0))
        Q = []
        for x, z in pts:
            hit = tree.ray_cast(V3((x, sgn * 1.5, z)), V3((0, -sgn, 0)), 1.0)[0]
            if hit is not None:
                Q.append(hit)
        if len(Q) > 1:
            K.CUTS.append(Q)


def mirrored(tr):
    return [(V3((q.x, -q.y, q.z)), V3((n.x, -n.y, n.z))) for q, n in tr]


def channel(g, key, ctrl, taper, mirror, w=RIB_W, depth=RIB_D, tip=RIB_TIP):
    """A ribbon's channel cut along the curve through ctrl, its path kept in LAMP[key] (and
    key + "_r" for the mirror image) with its width function."""
    dense = orrin.on_skin(ctrl)
    pts = [dense[0]]                    # a point every CHAN_STEP: sections closer than that
    for q in dense[1:-1]:               # fold over each other and the boolean empties the hull
        if (q - pts[-1]).length >= CHAN_STEP and (q - dense[-1]).length >= CHAN_STEP:
            pts.append(q)
    pts.append(dense[-1])
    ln = sum((b - a).length for a, b in zip(pts, pts[1:]))

    def wf(t, ln=ln):
        return orrin.taper_width(t, ln, w, tip, taper)
    LAMP[key] = (K.groove(g, pts, width=wf, depth=depth, step=CHAN_STEP, mirror=mirror), wf)
    if mirror:
        LAMP[key + "_r"] = (mirrored(LAMP[key][0]), wf)


# the ribbons in the cage's coordinates (u, v): from the tip over the wheel to the pole
RIB_F = [(4.80, 4.24), (4.5, 4.2), (4.0, 4.2), (3.5, 4.3), (3.0, 4.45), (2.5, 4.6),
         (2.0, 4.75), (1.5, 4.88), (1.0, 5.0)]
RIB_RS = [(9.15, 4.24), (9.5, 4.2), (10.0, 4.2), (10.5, 4.27), (11.18, 4.40)]
RIB_RC = [(11.52, 4.52), (12.0, 4.7), (12.5, 4.86), (13.0, 5.0)]
# the tailgate's cut: from the glass edge behind the hoop's foot down the quarter, across
# the ribbon's line to the keel's corner; the keel's edge under the tail is its lower edge
GATE = [(10.45, 1.994), (10.8, 3.1), (11.35, 4.5), (11.72, 5.4), (12.012, 6.025)]
PORT = (1.24, 1.0, 0.042)           # the charge flap on each front fender: x, z, radius


def lamp_outline(u0, u1, v0, v1, h, m=14):
    """A crescent lamp's outline on the skin: its upper edge from (u0, v0) to (u1, v1), its
    lower edge bowed h (in v) under it."""
    top = [(u0 + (u1 - u0) * k / m, v0 + (v1 - v0) * k / m) for k in range(m + 1)]
    low = [(a, b + h * sin(pi * k / m) ** 0.75) for k, (a, b) in enumerate(top)]
    return top, low


def cutters():
    """Everything cut into the hull, laid on it while it stands uncut."""
    wells, slots, cut, pulls = Geo(), Geo(), Geo(), Geo()
    lid(wells, FA_X, 0.52, 1.3)
    lid(wells, RA_X, 0.60, 1.3)
    # ---- a crescent slot in the wake of each front wheel
    a, b = snap((FA_X - 0.465, 1.0, 0.49))[0], snap((FA_X - 0.295, 1.0, 0.775))[0]
    lune_cut(slots, a, b, (0, 1, 0), (-0.875, 0, 0.484), 0.075, 0.048, depth=0.05,
             flare=0.016)
    # ---- the ribbons: channels over each wheel and round each pole; the pebbles' seats
    LAMP["peb.front"] = snap((NOSE.x + 0.05, 0, NOSE.z + 0.03))
    LAMP["peb.rear"] = snap((TAIL.x - 0.05, 0, TAIL.z + 0.03))
    cf, cr, ck = Geo(), Geo(), Geo()
    # (one channel across the nose pole emptied the hull in the boolean: each side's ends
    # 12 mm short of the centerline, under the pebble)
    half = [skin(*q) for q in RIB_F] + [V3((NOSE.x + 0.01, 0.012, NOSE.z + 0.006))]
    channel(cf, "front", half, (0.45, 0.0), True)
    channel(cr, "rs", [skin(*q) for q in RIB_RS], (0.40, 0.06), True)
    half = [skin(*q) for q in RIB_RC] + [V3((TAIL.x - 0.01, 0, TAIL.z + 0.008))]
    channel(cr, "rc", both(half), (0.06, 0.06), False)
    # ---- the tide line: a hair of light along the keel's top, from arch to arch
    channel(ck, "keel", [skin(4.80 + (8.74 - 4.80) * k / 24, 6.075) for k in range(25)],
            (0.25, 0.25), True, w=0.009, depth=0.007, tip=0.004)
    # ---- the head lamps and the stop lamps: crescent pockets under lenses of the skin
    hl, tl = Geo(), Geo()
    top, low = lamp_outline(1.45, 2.74, 5.60, 5.36, 0.36)
    LAMP["head"] = (K.pocket(hl, [skin(*q) for q in top + low[-2:0:-1]], depth=0.046,
                             mirror=True), top, low)
    top, low = lamp_outline(12.76, 11.90, 5.38, 5.20, 0.40)
    LAMP["stop"] = (K.pocket(tl, [skin(*q) for q in top + low[-2:0:-1]], depth=0.030,
                             mirror=True), top, low)
    # ---- the tailgate, the charge flaps
    K.groove(cut, curve(GATE, 10), mirror=True)
    c, n = on_body(PORT[0], PORT[1], 'y')
    t1 = (V3((1, 0, 0)) - n * n.x).normalized()
    t2 = n.cross(t1)
    K.groove(cut, [c + n * 0.004 + (t1 * cos(rad(a)) + t2 * sin(rad(a))) * PORT[2]
                   for a in range(0, 360, 10)], closed=True, mirror=True)
    LAMP["port"] = []                   # the light ring round each flap, on the uncut skin
    for sgn in (1, -1):
        seats = []
        for a in range(0, 361, 10):
            q = c + n * 0.004 + (t1 * cos(rad(a)) + t2 * sin(rad(a))) * (PORT[2] + 0.011)
            seats.append(snap((q.x, sgn * q.y, q.z)))
        LAMP["port"].append(seats)
    # ---- door pulls: small crescent recesses under the shoulder
    for x0, z0 in ((0.15, 0.955), (-1.00, 0.985)):
        top = [(x0 - 0.15 * k / 10, z0 + 0.001 + 0.017 * 4 * (k / 10) * (1 - k / 10))
               for k in range(11)]
        low = [(x0 - 0.15 * k / 10, z0 - 0.001 + 0.006 * 4 * (k / 10) * (1 - k / 10))
               for k in range(9, 0, -1)]
        K.pocket(pulls, top + [(x0 - 0.15, z0)] + low + [(x0, z0)], 'y', depth=0.014,
                 mirror=True)
    return [(wells, "well"), (slots, "slot"), (cf, "lamp_f"), (cr, "lamp_r"),
            (ck, "lamp_k"), (hl, "lamp_h", "skin", "lens_h"), (tl, "lamp_t", "skin", "lens_t"),
            (pulls, "pull"), (cut, "cut", "drop")]


CORE = []                               # the hull's panels: what the liner snaps to


def tidy(body):
    """Takes the folded slivers off the panels' edges. Where a cut runs along the mesh's
    rows (a ribbon toward its pole, where the rows crowd together) the boolean leaves
    triangles thinner than the kit's gap; the gap then pulls their outer corners past their
    inner ones, they turn over, and the panel's rim stands on them: flakes a millimeter
    proud all along the channel."""
    import bmesh
    gone = 0
    for pn, ob in body.parts.items():
        if pn in body.raw:
            continue
        bm = bmesh.new()
        bm.from_mesh(ob.data)
        bm.normal_update()
        dots = []
        for f in bm.faces:
            n = body.skin.find_nearest(f.calc_center_median())[1]
            dots.append(f.normal.dot(n) if n is not None else 1.0)
        sgn = 1.0 if sum(dots) >= 0 else -1.0
        bad = [f for f, d in zip(bm.faces, dots) if d * sgn < 0.3]
        if bad:
            gone += len(bad)
            bmesh.ops.delete(bm, geom=bad, context='FACES')
            bm.to_mesh(ob.data)
            ob.data.update()
        bm.free()
    K.log("tidied %d folded slivers off the panels" % gone)


def build_hull():
    body = K.build_body(stations(), panel_of, PMAT, 0.0, 0.0,
                        front=dict(kind="flat", panel="front", crease=0.0),
                        rear=dict(kind="flat", panel="rear", crease=0.0),
                        cutters=cutters, subdiv=4, thick=0.004, gap=GAP, bevel=0.002)
    if PROBE:
        print("parts:", " ".join("%s %d" % (pn, len(ob.data.vertices))
                                 for pn, ob in body.parts.items()))
    tidy(body)
    CORE.extend(ob for pn, ob in body.parts.items()
                if pn in ("front", "door_f", "door_r", "rear", "glass", "keel", "floor"))
    for pn, keys in (("lamp_f", ("front", "front_r")), ("lamp_r", ("rs", "rs_r", "rc")),
                     ("lamp_k", ("keel", "keel_r"))):
        ob = body.parts.get(pn)         # the channels' walls: 4.5 cm pieces of a 1 mm sheet
        if ob is None:                  # (the Pebble's way: a game pack drops them cleanly)
            continue
        for key in keys:
            if key in LAMP:
                orrin.chop(ob, LAMP[key][0])
        md = ob.modifiers.new("solid", 'SOLIDIFY')
        md.thickness = 0.001
        md.offset = 0.0
    return body


# ---------------------------------------------------------------------------------------
# the hoop: a band of the body over the glass behind the rear doors (the basket's handle),
# its feet sinking into the rear haunches; the tailgate hinges under its rear edge
# ---------------------------------------------------------------------------------------
HOOP_X, HOOP_SWEEP = -1.44, 0.13    # x on the roof's middle; how far back the feet stand
#        y     lift    half width, half thickness
HOOP = [(0.00, 0.001, .070, .017),
        (0.20, 0.001, .070, .017),
        (0.40, 0.001, .071, .017),
        (0.56, 0.001, .073, .017),
        (0.68, 0.000, .077, .017),
        (0.775, -0.002, .085, .017),
        (0.845, -0.004, .097, .016),
        (0.900, -0.006, .104, .014)]
#        z (on the flank under the shoulder), lift, half width, half thickness: the foot
#        thins and narrows to a point as it sinks under the skin, above the ribbon
FOOT = [(0.985, -0.006, .084, .011),
        (0.940, -0.009, .044, .008)]
HOOP_OBS = []


def hoop_x(y):
    return HOOP_X - HOOP_SWEEP * (y / 0.9) ** 2


def hoop_hw(y):
    y = abs(y)
    for (y0, _, w0, _), (y1, _, w1, _) in zip(HOOP, HOOP[1:]):
        if y <= y1:
            return w0 + (w1 - w0) * (y - y0) / (y1 - y0)
    return HOOP[-1][2]


def build_hoop():
    tree = K.body_bvh(CORE, default=False)
    P, N = [], []
    for y, lift, _, _ in HOOP:
        for dy in (0.0, 0.004, -0.004):     # a ray may fall into a panel gap
            loc, n, _, _ = tree.ray_cast(V3((hoop_x(y), y + dy, 3.0)), V3((0, 0, -1)))
            if loc is not None:
                break
        n = n if n.z > 0 else -n
        if y == 0:
            n = V3((n.x, 0, n.z)).normalized()
        P.append(loc + n * lift)
        N.append(n)
    x = hoop_x(HOOP[-1][0])
    for k, (z, lift, _, _) in enumerate(FOOT):
        loc, n = on_body(x - 0.012 * (k + 1), z, 'y', objs=tree)
        P.append(loc + n * lift)
        N.append(n)
    S = []
    for i, (_, _, hw, ht) in enumerate(HOOP + FOOT):
        t = (P[min(i + 1, len(P) - 1)] - P[max(i - 1, 0)]).normalized()
        if i == 0:
            t = V3((0, 1, 0))
        w = t.cross(N[i]).normalized()
        n = w.cross(t).normalized()
        ringp = []
        for k in range(8):
            a = 2 * pi * k / 8
            c, s_ = cos(a), sin(a)
            p = (P[i] + w * (hw * abs(c) ** 0.6 * (1 if c >= 0 else -1))
                 + n * (ht * abs(s_) ** 0.6 * (1 if s_ >= 0 else -1)))
            ringp.append((p.x, 0.0 if i == 0 else p.y, p.z))
        S.append(ringp)
    c = P[-1]
    pole = c + (P[-1] - P[-2]).normalized() * 0.05 - N[-1] * 0.03
    S.append([tuple(pole + (V3(q) - c) * 0.25) for q in S[-1]])
    body = K.build_body(S, lambda i, j: "hoop", PMAT, 0.0, 0.0, name="hoop", front=None,
                        rear=dict(kind="flat", panel="hoop", crease=0.0), wrap=True,
                        subdiv=3, thick=0.004, gap=GAP, project=False)
    HOOP_OBS.extend(body.parts.values())


def probe():
    for cx, out in ((FA_X, F_OUT), (RA_X, R_OUT)):
        for dx in (-0.44, -0.3, 0.0, 0.3, 0.44):
            row = []
            for z in (0.25, 0.40, 0.55, 0.70, 0.82, 0.90):
                loc, _ = on_body(cx + dx, z, 'y')
                row.append("%.3f" % loc.y if loc else " none")
            print("skin y at x %+.2f (tire face %.3f): %s" % (cx + dx, out, " ".join(row)))
    for x in (2.2, 1.9, 1.48, 1.0, 0.4, -0.1, -0.6, -1.2, -1.47, -1.9, -2.2):
        loc, _ = on_body(x, 0.0, 'z')
        print("top z at x %+.2f: %.3f" % (x, loc.z))
    worst = 0.0
    for u in (1.0, 1.5, 2.3, 5.5, 7.2, 8.4, 11.4, 12.6, 13.0):
        for v in (0.0, 1.0, 2.0, 3.3, 4.5):
            p = skin(u, v)
            worst = max(worst, (K.snap(p)[0] - p).length)
    print("skin(u, v) off the built surface by at most %.4f m" % worst)
    for name, uv in (("gate", GATE), ("rib_f", RIB_F), ("rib_rs", RIB_RS), ("rib_rc", RIB_RC)):
        print(name, " ".join("(%.2f %.2f %.2f)" % tuple(skin(a, b)) for a, b in uv))


# ---------------------------------------------------------------------------------------
# the lamps, things lying on the surface as built
# ---------------------------------------------------------------------------------------
def fair(tr, wf):
    """A channel's path with its normals taken from the skin on both sides of the channel
    (the path's own are those of the facets it was traced on, up to 5 degrees off where the
    skin curves tightly: a flat lens then stands proud along one edge and sunk along the
    other)."""
    out = []
    S = [0.0]
    for a, b in zip(tr, tr[1:]):
        S.append(S[-1] + (b[0] - a[0]).length)
    for i, (q, n) in enumerate(tr):
        tg = (tr[min(i + 1, len(tr) - 1)][0] - tr[max(i - 1, 0)][0]).normalized()
        sd = tg.cross(n).normalized()
        h = wf(S[i] / S[-1]) / 2 + 0.003
        a = K.snap(q + sd * h + n * 0.004)[0]
        b = K.snap(q - sd * h + n * 0.004)[0]
        ac = a - b
        if ac.length < 1e-4 or abs(ac.length - 2 * h) > h:      # an end, a neighbor cut
            out.append((q, n))
            continue
        ac.normalize()
        n2 = ac.cross(tg).normalized()
        if n2.dot(n) < 0:
            n2 = -n2
        out.append((b + ac * (q - b).dot(ac), n2))
    return out


def ribbon_lamp(name, tr, w, depth, lit, lens):
    """A ribbon in its channel (path tr, width w(share)): a lens with the body's gap each
    side, a light guide's lit face right under it and as wide as it, a frosted sleeve behind.
    (orrin.channel_lamp tucks a wider lit face under the paint; here it showed through the
    gap between the paint and the channel as bright dashes beside the ribbon.)"""
    if len(tr) < 2:
        return
    ln = sum((b[0] - a[0]).length for a, b in zip(tr, tr[1:]))
    fr = orrin.along(tr, 0.003, ln - 0.003, LAMP_STEP)

    def wf(f):
        return w(f[4])
    s0 = LENS_SINK
    L = K.Lamp(name, lit=lit, glass=lens)
    orrin.band(L.glass, fr, lambda f: wf(f) - 2 * GAP, lambda f: s0, lambda f: s0 + 0.003)
    orrin.band(L.emit(), fr, lambda f: wf(f) - 2 * GAP - 0.0006, lambda f: s0 + 0.0032,
               lambda f: s0 + 0.0032 + wf(f) * 0.18)
    orrin.band(L.optic, fr, lambda f: wf(f) * 0.70, lambda f: s0 + 0.0032 + wf(f) * 0.18,
               lambda f: depth - 0.0005)
    L.obj()


def build_lights():
    """The ribbons and the tide line: in each channel under its flush lens a light guide's
    lit face over a frosted sleeve (ribbon_lamp); the lit pebbles on the poles, seated
    on the skin as it stood before the cuts; projectors in the head lamps' pockets, a lit
    blade over bright fins in the stop lamps'."""
    for key, lit, lens, depth in (
            ("front", "led_front", "lens_clear", RIB_D),
            ("front_r", "led_front", "lens_clear", RIB_D), ("rs", "led_rear", "lens_red", RIB_D),
            ("rs_r", "led_rear", "lens_red", RIB_D), ("rc", "led_rear", "lens_red", RIB_D),
            ("keel", "led_accent", "lens_clear", 0.007),
            ("keel_r", "led_accent", "lens_clear", 0.007)):
        if key not in LAMP:
            continue
        tr, wf = LAMP[key]
        tr = fair(tr, wf)
        ribbon_lamp("lamp." + key, tr, wf, depth, lit, lens)
    g = Geo()
    orrin.seated(g, LAMP["peb.front"], 0.056, 0.040, 0.010)
    g.obj("led.front", "led_front", sharp=50)
    g = Geo()
    orrin.seated(g, LAMP["peb.rear"], 0.054, 0.040, 0.010)
    g.obj("led.rear", "led_rear", sharp=50)
    # ---- head lamps: three small projectors in a row, a light guide along the lower edge
    pk, top, low = LAMP["head"]
    if pk is not None:
        L = K.Lamp("lamp.head", lit="led_front")
        out = -pk.d
        for k in (4, 7, 10):
            mid = skin(top[k][0], (top[k][1] + low[k][1]) / 2)
            L.projector(pk.at(mid, lift=0.032), out, r=0.0135, depth=0.030, seg=20)
        path = [pk.at(skin(a, b - 0.07), lift=0.010) for a, b in low[2:-2]]
        L.guide(path, r=0.0028, sleeve=1.6, up=out)
        L.obj(mirror=True)
    # ---- stop lamps: a lit blade standing on the floor, bright fins across it
    pk, top, low = LAMP["stop"]
    if pk is not None:
        L = K.Lamp("lamp.stop", lit="led_rear")
        out = -pk.d
        path = [pk.at(skin(a, (b + low[k + 2][1]) / 2), lift=0.009)
                for k, (a, b) in enumerate(top[2:-2])]
        L.bar(path, 0.012, 0.014, up=out)
        for q0, q1 in zip(path[1::2], path[2::2]):
            t = (q1 - q0).normalized()
            sd = t.cross(out).normalized()
            L.chrome.box(q0 - out * 0.004, (0.002, 0.034, 0.008),
                         rot=Matrix((t, sd, out)).transposed())
        L.obj(mirror=True)


def build_details():
    I = IX
    # ---- frit: the black border printed round the canopy's edge
    g = Geo()
    us = [1.25 + 11.5 * k / 96 for k in range(97)]
    for sgn in (1, -1):
        ctrl = []
        for u in us:
            e, q = skin(u, 2.0), skin(u, 1.9)
            p = e + (q - e).normalized() * 0.0145
            ctrl.append(V3((p.x, sgn * p.y, p.z)))
        strip(g, ctrl, 0.026, lift=0.0009, sink=-0.0002, taper=(0.12, 0.12), n=2)
    g.obj("glass.frit", "frit", sharp=50)
    # ---- petal doors: hairlines over the glass on the door cuts, joined along the canopy
    g = Geo()
    for sgn in (1, -1):
        def m(pts):
            return [V3((p.x, sgn * p.y, p.z)) for p in pts]
        for st in ("D1", "D2", "D3"):
            strip(g, m([skin(I[st], 2.0 - k / 8) for k in range(9)]), 0.005, lift=0.0012, n=3)
        strip(g, m([skin(I["D1"] + 4.0 * k / 24, 1.0) for k in range(25)]), 0.005,
              lift=0.0012, n=3)
    g.obj("glass.lines", "gloss_black", sharp=50)
    # ---- the charge ports: a ring of light round each flap (cutters())
    g = Geo()
    for seats in LAMP.get("port", ()):
        vs = []
        for i, (q, n) in enumerate(seats):
            t = (seats[(i + 1) % (len(seats) - 1)][0] - seats[i - 1][0]).normalized()
            sd = n.cross(t).normalized() * 0.0025
            vs += [q + n * 0.0003 + sd, q + n * 0.0012 + sd, q + n * 0.0012 - sd,
                   q + n * 0.0003 - sd]
        k = len(seats)
        g.add(vs, [(4 * i + j, 4 * i + (j + 1) % 4, 4 * i + 4 + (j + 1) % 4, 4 * i + 4 + j)
                   for i in range(k - 1) for j in range(4)])
    g.obj("led.port", "led_accent", sharp=50)
    # ---- where it breathes: dot lenses under both poles
    g = Geo()
    dot_field(g, 'x', 0.0, 0.535, 0.27, 0.036)
    dot_field(g, 'X', 0.0, 0.725, 0.21, 0.032)
    for proj in ('y', 'Y'):             # and low on the keel behind each front wheel
        dot_field(g, proj, 0.52, 0.335, 0.40, 0.045)
    g.obj("dots", "void")
    # ---- lettering: one small word each
    g = Geo()
    for side in (1, -1):
        text_proj(g, "tide", 0.036, 0.62, 0.50, 'y' if side > 0 else 'Y', spacing=1.3)
    text_proj(g, "orrin", 0.030, 0.0, 0.635, 'X', spacing=1.4)
    g.obj("lettering", "decal")
    # ---- camera pods where mirrors would be, sensors round the nose and the tail
    g, gl = Geo(), Geo()
    for sgn in (1, -1):
        loc, n = snap((0.90, sgn * 1.0, 1.04))
        fwd = V3((1, 0, 0.05)).normalized()
        xf = (Matrix.Translation(loc + n * 0.008)
              @ V3((0, 1, 0)).rotation_difference(fwd).to_matrix().to_4x4())
        prof = [(-0.11 * cos(rad(a)), 0.028 * sin(rad(a)) ** 0.8 + 0.0005)
                for a in range(0, 181, 12)]
        g.lathe(prof, 24, xf=xf)
        gl.lathe([(-0.111, 0.001), (-0.111, 0.011), (-0.107, 0.013), (-0.107, 0.001)], 16,
                 xf=xf)
    g.obj("cameras", "paint", sharp=40)
    for y, z, proj in ((0.34, 0.49, 'x'), (-0.34, 0.49, 'x'), (0.30, 0.69, 'X'),
                       (-0.30, 0.69, 'X')):
        loc, n = on_body(y, z, proj)
        if loc is not None:
            K.stud(gl, loc, n, [(-0.002, 0.001), (-0.002, 0.010), (0.0012, 0.010),
                                (0.0012, 0.001)], 14)
    gl.obj("camera.lens", "gloss_black")
    # ---- the third stop light: a hair of red along the hoop's rear edge
    g = Geo()
    ctrl = []
    for k in range(-12, 13):
        y = 0.50 * k / 12
        loc, n = on_body(hoop_x(y) - hoop_hw(y) + 0.016, y, 'z', objs=HOOP_OBS)
        ctrl.append(loc + n * 0.002)
    K.strip(g, ctrl, 0.007, taper=(0.05, 0.05), n=3, objs=HOOP_OBS)
    g.obj("led.hoop", "led_rear", sharp=50)
    # ---- the wiper, parked along the foot of the screen
    g, gb = Geo(), Geo()
    K.wiper(g, gb, on_body(1.10, 0.17, 'z')[0], on_body(1.045, -0.07, 'z')[0],
            on_body(1.00, 0.60, 'z')[0])
    g.obj("wiper", "cladding", bevel=0.0012)
    gb.obj("wiper.blade", "rubber")


# ---------------------------------------------------------------------------------------
# interior: a liner under the long glass (nose deck, tub, load deck), five seats of stones
# ---------------------------------------------------------------------------------------
def build_interior():
    tree = K.body_bvh(CORE, default=False)
    #       x     floor (None: under the rim by drop)  drop   floor edge (share of the rim's y)
    rows = [(2.30, None, .006, .86), (2.15, None, .016, .86), (1.90, None, .035, .86),
            (FA_X, None, .050, .86), (1.20, None, .058, .86), (1.06, None, .060, .86),
            (1.01, .24, 0, .86), (0.92, .24, 0, .86), (0.44, .24, 0, .86),
            (-0.10, .24, 0, .86), (-0.60, .24, 0, .80), (-0.90, .24, 0, .70),
            (-1.07, .24, 0, .70), (-1.12, .83, 0, .86), (-1.30, .83, 0, .86),
            (RA_X, .83, 0, .86), (-1.80, .845, 0, .86), (-2.05, None, .16, .86),
            (-2.20, None, .07, .86), (-2.31, None, .012, .86)]
    S, rims = [], []
    for x, zf, drop, fe in rows:
        rm = orrin.rim_at(x, tree, pt=PT, order=ORDER)
        rims.append(rm)
        zf = rm.z - drop if zf is None else zf
        S.append([tuple(rm), (rm.x, rm.y * 0.96, zf + (rm.z - zf) * 0.45),
                  (rm.x, rm.y * fe, zf), (rm.x, 0.0, zf)])
    hold = {5: 0.6, 6: 0.75, 7: 0.5, 11: 0.4, 12: 0.75, 13: 0.75, 14: 0.4}
    K.build_body(S, lambda i, j: "liner", dict(liner="liner"), 0.0,
                 lambda i, j: hold.get(i, 0.0), name="liner", project=False, subdiv=2)
    # ---- a hair of light under the glass round both tongues, the word under the nose glass
    g = Geo()
    sec = [(-0.0025, -0.002), (0.0025, -0.002), (0.0025, 0.002), (-0.0025, 0.002)]
    for part in (rims[:6], rims[:-5:-1]):
        half = [V3((p.x, p.y - 0.014, p.z - 0.004)) for p in part[::-1]]
        tip = part[0]
        half.append(V3((tip.x + (0.004 if tip.x > 0 else -0.004), 0, tip.z - 0.006)))
        g.sweep(spline(both(half), 8), sec, up=(0, 0, 1))
    a, b = V3((rims[2].x, 0, rims[2].z - 0.033)), V3((rims[3].x, 0, rims[3].z - 0.048))
    text_flat(g, "orrin", 0.050, a.lerp(b, 0.45) + V3((0, 0, 0.012)), (0, 1, 0),
              (b - a).normalized(), spacing=1.5)
    g.obj("led.cabin", "led_accent")
    # ---- seats, each three stones: two in front, three across behind
    g, gi = Geo(), Geo()
    back = Matrix.Rotation(rad(-20), 3, 'Y')
    for x0, places in ((0.20, ((0.375, 0.235), (-0.375, 0.235))),
                       (-0.69, ((0.44, 0.215), (-0.44, 0.215), (0.0, 0.185)))):
        for y, hw in places:
            mid = y == 0.0
            stone(g, (x0, y, 0.455 + (0.012 if mid else 0)), (0.25, hw, 0.07),
                  Matrix.Rotation(rad(-8), 3, 'Y'), n=3.0)
            stone(g, (x0 - 0.325, y, 0.80), (0.065, hw - 0.015, 0.31 if not mid else 0.28),
                  back, n=3.0)
            stone(g, (x0 - 0.455, y, 1.165 if not mid else 1.11), (0.045, 0.105, 0.068), back,
                  n=2.6)
            stone(gi, (x0 - 0.02, y, 0.33), (0.20, hw - 0.04, 0.07), n=3.0, seg=20, rows=10)
    g.obj("interior.seats", "seat", sharp=60)
    # ---- the dash (one stone and a strip of screen), the yoke, a spine between the seats
    stone(gi, (0.955, 0, 0.955), (0.095, 0.66, 0.045), Matrix.Rotation(rad(12), 3, 'Y'), n=3.2)
    stone(gi, (0.25, 0, 0.36), (0.52, 0.065, 0.11), n=3.0, seg=20, rows=10)
    yoke = (Matrix.Translation((0.70, 0.375, 0.905)) @ Matrix.Rotation(rad(-66), 4, 'Y')
            @ Matrix.Rotation(pi / 2, 4, 'X'))
    gi.lathe([(-0.010, 0.150), (0.0, 0.161), (0.010, 0.150), (0.0, 0.139)], 28, xf=yoke)
    gi.tube((0.73, 0.375, 0.895), (0.89, 0.375, 0.945), 0.02)
    gi.obj("interior.fittings", "interior", sharp=60)
    g = Geo()
    stone(g, (0.862, 0, 0.962), (0.012, 0.50, 0.026), Matrix.Rotation(rad(12), 3, 'Y'), n=4)
    g.obj("interior.screen", "screen", sharp=60)
    # ---- on the load deck: a case, a soft bag and a roll, a rail across behind the seats
    g = Geo()
    g.box((-1.60, 0.20, 0.962), (0.56, 0.40, 0.25))
    g.obj("load.case", "case", bevel=0.03, segs=4)
    g = Geo()
    for y in (0.08, 0.32):
        g.box((-1.60, y, 0.962), (0.572, 0.035, 0.262))
    g.obj("load.straps", "interior", bevel=0.004)
    g = Geo()
    g.pipe(spline([(-1.67, 0.20, 1.085), (-1.66, 0.20, 1.109), (-1.60, 0.20, 1.121),
                   (-1.54, 0.20, 1.109), (-1.53, 0.20, 1.085)], 4), 0.008, up=(0, 1, 0))
    g.obj("load.handle", "interior", sharp=60)
    g = Geo()
    stone(g, (-1.66, -0.27, 0.955), (0.25, 0.16, 0.11), Matrix.Rotation(rad(14), 3, 'Z'),
          n=2.4)
    g.tube((-1.36, -0.50, 0.905), (-1.36, -0.05, 0.905), 0.062, n=20)
    g.obj("load.bag", "bag", sharp=60)
    g = Geo()
    g.tube((-1.235, -0.72, 0.90), (-1.235, 0.72, 0.90), 0.012)
    g.obj("load.rail", "rim_bright", sharp=60)


# ---------------------------------------------------------------------------------------
# views of its own, and the build
# ---------------------------------------------------------------------------------------
K.VIEWS["hero"].update(dir=(1.0, 1.02, 0.25))    # side-on enough to show the long roof
K.VIEWS.update(
    nose=dict(dir=(1.0, 0.45, 0.30), lens=85, target=(2.1, 0.35, 0.62), dist=2.8),
    tail=dict(dir=(-1.0, -0.5, 0.30), lens=85, target=(-2.1, -0.2, 0.8), dist=3.2),
    wheel=dict(dir=(0.45, 1.0, 0.12), lens=85, target=(FA_X, 0.9, 0.45), dist=2.8),
    cabin=dict(dir=(0.3, 1.0, 0.75), lens=85, target=(-0.3, 0.2, 1.0), dist=4.6),
    hoop=dict(dir=(-0.6, 1.0, 0.45), lens=85, target=(-1.6, 0.5, 1.1), dist=3.2),
    gate=dict(dir=(-1.0, 0.9, 0.25), lens=85, target=(-2.0, 0.6, 0.85), dist=2.6),
    door=dict(dir=(0.25, 1.0, 0.22), lens=85, target=(-0.1, 0.95, 0.80), dist=2.4),
    fender=dict(dir=(0.5, 1.0, 0.5), lens=85, target=(1.25, 0.9, 0.85), dist=1.9),
    cowl=dict(dir=(1.0, 0.25, 0.9), lens=85, target=(1.02, 0.25, 1.2), dist=1.6),
    tip=dict(dir=(1.0, 0.3, 0.45), lens=85, target=(2.33, 0.05, 0.70), dist=1.3),
    keel=dict(dir=(0.2, 1.0, 0.1), lens=85, target=(0.5, 0.95, 0.38), dist=1.8),
)


def main():
    K.materials(paint=PAINT, paint_finish=(0.62, 0.34, 0.7), dust_amount=0.10,
                glass=(0.50, 0.55, 0.57), led_front=(0.90, 0.95, 1.0),
                led_rear=(1.0, 0.035, 0.03), led_accent=(1.0, 0.72, 0.40),
                led_wheel=(1.0, 0.72, 0.40), seat=(0.55, 0.47, 0.36),
                interior=(0.030, 0.030, 0.032), screen=(1.0, 0.72, 0.40))
    K.pbr("wheel_face", (0.19, 0.195, 0.20), 1.0, 0.30)
    K.pbr("wheel_vane", (0.24, 0.245, 0.25), 1.0, 0.26)
    K.pbr("keel", (0.045, 0.044, 0.043), 0.5, 0.46)
    K.pbr("liner", (0.014, 0.014, 0.016), 0.0, 0.30)
    K.pbr("case", (0.40, 0.24, 0.10), 0.0, 0.55)
    K.pbr("bag", (0.03, 0.10, 0.10), 0.0, 0.7)
    # the canopy's glass with a coating: the kit's glass mirrors the studio all over a dome
    K.pbr("glass_dome", (0.32, 0.35, 0.37), 0.0, 0.0,
          **{"Transmission Weight": 1.0, "IOR": 1.14})
    build_hull()
    build_hoop()
    K.log("hull")
    if PROBE:
        probe()
    build_lights()
    build_details()
    build_interior()
    K.log("details")
    for side, s in ((1, "l"), (-1, "r")):     # turbine discs (vehicles/brands/orrin.py)
        for tag, cx, out in (("f" + s, FA_X, F_OUT), ("r" + s, RA_X, R_OUT)):
            orrin.disc(tag, cx, out, side, vanes=54, R=R, W=W, rim=RIM, r_in=0.145,
                       hub=(0.126, 0.090, 0.048), sweep=34, cap=(0.032, 0.042), tread=TREAD)
    K.log("wheels")
    K.cabin_light((-0.3, 0.0, 1.28), power=9.0)
    K.unlit("rim", "body.glass")        # the rim light stood in the canopy as a white shard
    K.meant("symmetry", "interior.fittings", "load.*", "wiper*", "lettering", "led.cabin")
    K.shoot(extra=[dict(view="rear", size=(1040, 585), corner="tl"),
                   dict(view="top", size=(900, 420), corner="tr")])


main()
