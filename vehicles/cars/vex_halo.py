"""Vex Halo: a two-seat hubless roadster (both names made up), on vehicles/carkit.py.

Run (always through the wrapper, one Blender job at a time on this machine):
    vehicles/blender.sh vehicles/cars/vex_halo.py --out DIR --preview
    vehicles/blender.sh vehicles/cars/vex_halo.py --out DIR --sheet

The second Vex, the Wraith's sibling (docs/progress/AG18/vex_wraith has the family's cues):
pods that never touch, weave below and a color cap above the widest line, the raw metal
spine inlaid on every pod and jumping the gaps as the drilled beam, mechanicals in plain
sight, three-dot clusters on stalks, hairline strips on blade edges, race numbers and
sponsor-like plates. Its own idea: four hubless, rim-driven wheels. Each is an open ring (a
tire on a rotating rim, a fixed inner ring with the stator, a light line and the brake
pads) held from the inboard side by a crescent on one A-blade, so the middle of every wheel
is air; the body is a drop between them (a low bow pod on the keel beam, the tub, a dart of
a tail that passes over the rear rings), and the X of four arms is the whole chassis.
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
FA_X, RA_X = 1.38, -1.32                    # axles: wheelbase 2.70
R, RR, OUT_Y = 0.40, 0.325, 0.975           # tire radius, rim radius, the tires' outer face
F_W, R_W = 0.24, 0.28
RING_O, RING_I = RR - 0.021, 0.240          # the fixed ring: the hole is 0.48 m across
ARC_R = 0.272                               # the crescents' middle radius
PIT_Z = 0.18
NUM = "63"

PT = {}


# ---------------------------------------------------------------------------------------
# helpers (the family's, from the Wraith)
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


def side_pt(x, z, default=None):
    """The outermost body surface on the left at (x, z)."""
    p = on_body(x, z, 'y')[0]
    return p if p is not None else V3(default)


def top_z(x, y, default=0.5):
    loc = on_body(x, y, 'z')[0]
    return loc.z if loc is not None else default


def text_top(g, txt, size, x0, y0, right=(-1, 0), lift=0.0012, spacing=1.0):
    """Text on the top of the body, its middle at (x0, y0), reading along right."""
    vs, fs = K.text_mesh(txt, size, spacing)
    rx, ry = right
    ux, uy = -ry, rx
    out = []
    for p in vs:
        loc, n = on_body(x0 + rx * p.x + ux * p.y, y0 + ry * p.x + uy * p.y, 'z')
        if loc is None:
            return
        out.append(loc + n * lift)
    g.add(out, fs)


def block(g, gt, txt, size, x0, z0, side, pad=0.012, spacing=1.05, wide=None):
    """A sponsor-like block on a flank: a plate in g, its word in gt."""
    w = wide if wide is not None else size * 0.62 * len(txt) * spacing + 2 * pad
    ribbon(g, [(x0 - w / 2, z0), (x0 + w / 2, z0)], 'y' if side > 0 else 'Y', size + 2 * pad)
    text_on_body(gt, txt, size, x0, z0, side, lift=0.0022, spacing=spacing)


def damper(g, gs, a, b, r=0.020):
    """A coil-over from a to b: a body in g, the spring's coils in gs."""
    a, b = V3(a), V3(b)
    d = (b - a)
    L = d.length
    xf = Matrix.Translation(a) @ V3((0, 1, 0)).rotation_difference(d.normalized()).to_matrix().to_4x4()
    g.lathe([(0, 0.002), (0, r * 0.55), (L * 0.45, r * 0.55), (L * 0.45, r * 0.8), (L, r * 0.8),
             (L, 0.002)], 10, xf=xf)
    for k in range(7):
        y = L * (0.10 + 0.105 * k)
        gs.lathe([(y, r * 0.95), (y, r * 1.3), (y + L * 0.045, r * 1.3), (y + L * 0.045, r * 0.95)],
                 10, xf=xf)


def cluster(g, gl, root, head, facing, mat_r=0.013):
    """A stalk from root to a three-dot cluster at head, facing along x (1 or -1)."""
    root, head = V3(root), V3(head)
    tube(g, [root, root.lerp(head, 0.6) + V3((0, 0, 0.02)), head], 0.007)
    g.box(head, (0.05, 0.118, 0.040))
    for k in (-1, 0, 1):
        c = head + V3((facing * 0.026, k * 0.036, 0))
        xf = Matrix.Translation(c) @ Matrix.Rotation(pi / 2, 4, 'Z')
        gl.lathe([(-0.004, 0.001), (-0.004, mat_r), (0.004, mat_r), (0.004, 0.001)], 12, xf=xf)


def smooth(pts, n=6):
    """A Catmull-Rom curve through pts, n steps a span."""
    P = [V3(p) for p in pts]
    P = [P[0] * 2 - P[1]] + P + [P[-1] * 2 - P[-2]]
    out = []
    for i in range(1, len(P) - 2):
        for k in range(n):
            t = k / n
            out.append(0.5 * ((2 * P[i]) + (-P[i - 1] + P[i + 1]) * t
                              + (2 * P[i - 1] - 5 * P[i] + 4 * P[i + 1] - P[i + 2]) * t * t
                              + (-P[i - 1] + 3 * P[i] - 3 * P[i + 1] + P[i + 2]) * t ** 3))
    out.append(P[-2])
    return out


def arc_pt(cx, y, a, r=ARC_R):
    """A point on a wheel's circle: a in degrees from forward over the top."""
    return V3((cx + r * cos(rad(a)), y, R + r * sin(rad(a))))


# ---------------------------------------------------------------------------------------
# the pods: a bow on the keel, the tub, the tail dart
# ---------------------------------------------------------------------------------------
PMAT = dict(spine="alloy", cap="paint", flank="carbon", belly="carbon", bulk="alloy",
            tip="alloy", pit="interior")

# lines: C top centerline, D the spine strip's edge, R the shoulder, W widest, L lower, B keel
BOW = [
    [(2.14, 0, .178), (2.14, .008, .178), (2.14, .016, .176), (2.135, .024, .160),
     (2.14, .016, .144), (2.14, 0, .142)],
    [(2.00, 0, .228), (2.00, .024, .228), (2.00, .070, .221), (2.00, .104, .170),
     (2.00, .066, .116), (2.00, 0, .106)],
    [(1.86, 0, .245), (1.86, .028, .245), (1.86, .092, .237), (1.86, .132, .176),
     (1.86, .084, .108), (1.86, 0, .098)],
    [(1.74, 0, .236), (1.74, .028, .236), (1.74, .084, .228), (1.74, .120, .176),
     (1.74, .076, .114), (1.74, 0, .106)],
]
TUB = [
    [(1.13, 0, .190), (1.13, .014, .190), (1.13, .030, .187), (1.125, .045, .150),
     (1.13, .030, .112), (1.13, 0, .108)],
    [(0.95, 0, .315), (0.95, .030, .315), (0.95, .135, .300), (0.945, .200, .205),
     (0.95, .150, .112), (0.95, 0, .098)],
    [(0.70, 0, .455), (0.70, .034, .455), (0.70, .300, .440), (0.70, .380, .290),
     (0.70, .320, .118), (0.70, 0, .092)],
    [(0.42, 0, .580), (0.42, .036, .580), (0.42, .430, .568), (0.42, .500, .370),
     (0.42, .440, .125), (0.42, 0, .090)],
    [(0.10, 0, .625), (0.10, .036, .625), (0.10, .495, .613), (0.10, .560, .405),
     (0.10, .500, .135), (0.10, 0, .090)],
    [(-.45, 0, .640), (-.45, .036, .640), (-.45, .470, .628), (-.45, .535, .425),
     (-.45, .475, .140), (-.45, 0, .092)],
    [(-.80, 0, .700), (-.80, .036, .700), (-.80, .360, .685), (-.80, .425, .470),
     (-.80, .360, .200), (-.80, 0, .150)],
]
TAIL = [
    [(-.98, 0, .740), (-.98, .034, .740), (-.98, .200, .728), (-.98, .270, .655),
     (-.98, .190, .545), (-.98, 0, .525)],
    [(-1.30, 0, .745), (-1.30, .032, .745), (-1.30, .145, .736), (-1.30, .195, .690),
     (-1.30, .135, .628), (-1.30, 0, .615)],
    [(-1.70, 0, .735), (-1.70, .026, .735), (-1.70, .075, .730), (-1.70, .105, .705),
     (-1.70, .070, .672), (-1.70, 0, .665)],
    [(-2.10, 0, .712), (-2.10, .008, .712), (-2.10, .014, .711), (-2.095, .020, .703),
     (-2.10, .014, .695), (-2.10, 0, .694)],
]
# the cockpit's opening from above (left half, front to rear); one pit, the spine crosses it
PIT = [(0.36, 0.0), (0.345, 0.16), (0.29, 0.30), (0.17, 0.385), (0.0, 0.40), (-0.45, 0.39),
       (-0.58, 0.34), (-0.64, 0.22), (-0.64, 0.0)]


def pod_panel(i, j):
    return ("spine", "cap", "cap", "flank", "belly")[j]


def tub_w(x):
    """The tub's widest line (y, z) at x, from its cage."""
    for a, b in zip(TUB, TUB[1:]):
        if b[3][0] <= x <= a[3][0]:
            t = (a[3][0] - x) / (a[3][0] - b[3][0])
            return a[3][1] + (b[3][1] - a[3][1]) * t, a[3][2] + (b[3][2] - a[3][2]) * t
    return TUB[-1][3][1], TUB[-1][3][2]


def build_pods():
    def lc(i, j):                               # creases along the lines: smoother than the
        return (0.0, 1.0, 0.20, 1.0, 0.15, 0.0)[j]      # Wraith, the cap's edge still sharp

    S = K.fill(BOW)
    PT["bow"] = S
    K.build_body(S, pod_panel, PMAT, lc, 0.0, name="bow",
                 front=dict(kind="flat", panel="tip"), rear=dict(kind="flat", panel="bulk"))
    pit = Geo()
    poly = PIT + [(x, -y) for (x, y) in PIT[-2:0:-1]]
    pit.prism([(x, y, PIT_Z) for (x, y) in poly], (0, 0, 1.2))
    S = K.fill(TUB)
    PT["tub"] = S
    K.build_body(S, pod_panel, PMAT, lc, 0.0, name="tub",
                 front=dict(kind="flat", panel="tip"), rear=dict(kind="flat", panel="bulk"),
                 cutters=[(pit, "pit")])
    S = K.fill(TAIL)
    PT["tail"] = S
    K.build_body(S, pod_panel, PMAT, lc, 0.0, name="tail",
                 front=dict(kind="flat", panel="bulk"), rear=dict(kind="flat", panel="tip"))


# ---------------------------------------------------------------------------------------
# the spine: inlaid on the pods, a drilled beam in every gap and across the cockpit
# ---------------------------------------------------------------------------------------
def build_spine():
    g = Geo()
    # the keel jump, low between the front rings: bow pod to the tub's tip
    drilled(g, (1.745, 0, 0.170), (1.125, 0, 0.150), 0.080, 0.020, flw=0.056)
    # across the cockpit, between the two seats
    za, zb = top_z(0.40, 0, 0.58) - 0.058, top_z(-0.68, 0, 0.67) - 0.058
    drilled(g, (0.372, 0, za), (-0.652, 0, zb), 0.105, 0.022, flw=0.066)
    # the tail jump
    za, zb = top_z(-0.78, 0, 0.69) - 0.058, top_z(-1.0, 0, 0.74) - 0.058
    drilled(g, (-0.795, 0, za), (-0.985, 0, zb), 0.105, 0.022, flw=0.066)
    g.obj("spine", "alloy", bevel=0.0025)
    # the tail rides on two stays from the tub's bulkhead: a truss you can see through
    g = Geo()
    tube(g, [(-0.80, 0.25, 0.30), (-1.10, 0.085, 0.585)], 0.012)
    tube(g, [(-0.80, 0.25, 0.60), (-1.00, 0.16, 0.60)], 0.010)
    g.box((-0.805, 0.25, 0.30), (0.02, 0.07, 0.06))
    g.box((-0.805, 0.25, 0.60), (0.02, 0.06, 0.05))
    g.obj("tail.stays", "alloy", bevel=0.002, mirror=True)
    # the inlaid strips' fasteners, two rows
    g = Geo()
    prof = [(-0.002, 0.001), (-0.002, 0.0065), (0.0022, 0.0065), (0.0022, 0.001)]
    xs = ([2.08 - 0.10 * k for k in range(4)] + [1.06 - 0.105 * k for k in range(7)]
          + [-0.70, -0.77] + [-1.03 - 0.105 * k for k in range(10)])
    for x in xs:
        loc, n = on_body(x, 0.019 if x > -1.6 else 0.011, 'z')
        if loc is not None and loc.z > 0.15:
            stud(g, loc, n, prof, 6)
    g.obj("spine.bolts", "gloss_black", mirror=True)


# ---------------------------------------------------------------------------------------
# the wheels: open rings
# ---------------------------------------------------------------------------------------
def build_ring_wheel(tag, cx, w, side, brake_at):
    """A hubless wheel: the kit's tire on a rotating rim with a brake lip; inside it the
    fixed ring (stator segments in a channel, a light line, fins inboard), pads on the lip."""
    hw = w / 2
    flip = side < 0
    loc = (cx, side * (OUT_Y - hw), R)
    K.build_wheel(tag, cx, R, w, RR, OUT_Y, side, rim=None, ring=None, caliper=None)
    drum = bpy.data.objects.get("drum." + tag)          # the kit closes a wheel's middle
    if drum is not None:
        me = drum.data
        bpy.data.objects.remove(drum)
        bpy.data.meshes.remove(me)

    # the rotating rim: a barrel under the tire, its outer lip the brake's rotor
    g = Geo()
    g.lathe([(-hw + 0.02, RR - 0.002), (hw - 0.014, RR - 0.002), (hw - 0.014, RR + 0.003),
             (hw - 0.004, RR + 0.003), (hw - 0.004, RR - 0.027), (hw - 0.014, RR - 0.027),
             (hw - 0.014, RR - 0.013), (-hw + 0.02, RR - 0.013)], 96)
    g.obj("rim." + tag, "rotor", flip_y=flip, loc=loc, sharp=35)
    g = Geo()
    for k in range(24):
        a = 2 * pi * (k + 0.5) / 24
        g.lathe([(hw - 0.006, 0.001), (hw - 0.006, 0.0048), (hw - 0.0015, 0.0048),
                 (hw - 0.0015, 0.001)], 6,
                xf=Matrix.Translation(((RR - 0.011) * cos(a), 0, (RR - 0.011) * sin(a))))
    g.obj("rim.bolts." + tag, "gloss_black", flip_y=flip, loc=loc)

    # the fixed ring
    yi, yo, ys = -hw + 0.035, hw - 0.004, hw - 0.022
    g = Geo()
    g.lathe([(yi, RING_I + 0.030), (yi, RING_O), (ys, RING_O), (ys, 0.2935), (yo, 0.2935),
             (yo, 0.2885), (yo - 0.013, 0.2885), (yo - 0.013, 0.2615), (yo, 0.2615),
             (yo, 0.2535), (yo - 0.004, 0.2535), (yo - 0.004, 0.2445), (yo, 0.2445),
             (yo, RING_I), (yo - 0.030, RING_I)], 96)
    for k in range(48):                                 # cooling fins on the inboard face
        a = rad(7.5 * k)
        g.lathe([(yi - 0.014, 0.274), (yi - 0.014, 0.299), (yi + 0.001, 0.299),
                 (yi + 0.001, 0.274)], 1, a0=a, a1=a + rad(3.0))
    g.obj("ring." + tag, "alloy", flip_y=flip, loc=loc, sharp=35)
    g = Geo()                                           # 36 stator segments in the channel
    for k in range(36):
        a = rad(10 * k + 1.5)
        g.lathe([(yo - 0.012, 0.2635), (yo - 0.012, 0.2865), (yo - 0.003, 0.2865),
                 (yo - 0.003, 0.2635)], 2, a0=a, a1=a + rad(7.0))
    g.obj("stator." + tag, "copper", flip_y=flip, loc=loc, bevel=0.0012)
    g = Geo()                                           # the halo: a line on the face, one
    g.lathe([(yo - 0.0035, 0.2450), (yo - 0.0035, 0.2530), (yo + 0.0008, 0.2530),      # in
             (yo + 0.0008, 0.2450)], 96)                                           # the bore
    g.lathe([(yo - 0.022, RING_I - 0.0012), (yo - 0.022, RING_I + 0.002),
             (yo - 0.014, RING_I + 0.002), (yo - 0.014, RING_I - 0.0012)], 96)
    g.obj("halo." + tag, "led_wheel", flip_y=flip, loc=loc, sharp=35)
    # brake pads in their carriers, clamped on the lip
    g, gb = Geo(), Geo()
    for a in brake_at:
        g.lathe([(hw - 0.032, 0.268), (hw - 0.032, 0.3185), (hw + 0.010, 0.3185),
                 (hw + 0.010, 0.268)], 4, a0=rad(a - 13), a1=rad(a + 13))
        for da in (-8, 8):
            c = Matrix.Translation((0.280 * cos(rad(a + da)), 0, 0.280 * sin(rad(a + da))))
            gb.lathe([(hw + 0.009, 0.001), (hw + 0.009, 0.0065), (hw + 0.014, 0.0065),
                      (hw + 0.014, 0.001)], 6, xf=c)
    g.obj("caliper." + tag, "caliper", bevel=0.004, flip_y=flip, loc=loc)
    gb.obj("caliper.bolts." + tag, "alloy", flip_y=flip, loc=loc)


# ---------------------------------------------------------------------------------------
# the four arms: an A-blade to a crescent on the ring's inboard face, nothing in the hole
# ---------------------------------------------------------------------------------------
def build_arm(tag, cx, w, mid, picks, rocker, damp_to, feed, steer=None):
    """mid: the crescent's middle (180: the body is behind the wheel, 0: ahead of it)."""
    gb, ga, gs, gc, gk, gd = Geo(), Geo(), Geo(), Geo(), Geo(), Geo()
    yc = OUT_Y - w - 0.006                              # the crescent's middle plane
    sg = 1 if mid == 0 else -1
    xf = Matrix.Translation((cx, 0, R))
    ga.lathe([(yc - 0.013, ARC_R - 0.026), (yc - 0.013, ARC_R + 0.026),
              (yc + 0.013, ARC_R + 0.026), (yc + 0.013, ARC_R - 0.026)], 28,
             a0=rad(mid - 84), a1=rad(mid + 84), xf=xf)
    prof = [(-0.002, 0.001), (-0.002, 0.007), (0.004, 0.007), (0.004, 0.001)]
    for da in range(-70, 71, 20):
        stud(gk, arc_pt(cx, yc - 0.013, mid + da), V3((0, -1, 0)), prof, 6)
    for da in (-84, 84):                                # the kingpin's two ends
        c = arc_pt(cx, yc + 0.020, mid + da * 0.97)
        ga.box(c, (0.055, 0.050, 0.055))
        ball(ga, c + V3((0, -0.045, 0)), 0.020)
    T = arc_pt(cx, yc - 0.030, mid, ARC_R + 0.004)
    ga.box(T + V3((0, 0.008, 0)), (0.075, 0.045, 0.13))
    P = [side_pt(x, z, d) for (x, z, d) in picks]
    n = (P[0] - T).cross(P[1] - T).normalized()
    if n.z < 0:
        n = -n
    for p in P:
        blade(gb, [p + V3((0, -0.012, 0)), T], 0.085, 0.016, up=n)
        ga.box(p, (0.10, 0.04, 0.055))
    gb.prism([T - n * 0.006, T.lerp(P[0], 0.36) - n * 0.006, T.lerp(P[1], 0.36) - n * 0.006],
             n * 0.012)
    tube(ga, [T.lerp(P[0], 0.64), T.lerp(P[1], 0.64)], 0.009)
    # pushrod from the crescent's top to a rocker on the body, the coil-over lying on it
    q = arc_pt(cx, yc - 0.020, mid + sg * 68)
    rk = V3(rocker)
    ball(ga, q, 0.020)
    tube(ga, [q, rk], 0.010)
    ga.prism([rk + V3((0.05, -0.006, -0.03)), rk + V3((-0.05, -0.006, -0.03)),
              rk + V3((-0.025, -0.006, 0.035)), rk + V3((0.025, -0.006, 0.035))], (0, 0.012, 0))
    ring(ga, rk, (0, 1, 0), 0.016, 0.006, 0.02, 10)
    damper(ga, gs, damp_to, rk + V3((sg * 0.02, 0, 0.02)))
    if steer is not None:
        e = arc_pt(cx, yc - 0.02, mid + 38)
        tube(ga, [side_pt(*steer), e], 0.008)
        ball(ga, e, 0.016)
    # the feed: three phase cables along the far blade and round the crescent to a gland
    far = P[1]
    s = n.cross((T - far).normalized())
    gland = arc_pt(cx, yc + 0.012, mid + sg * 40, ARC_R - 0.004)
    for k in (-1, 0, 1):
        o = n * 0.016 + s * (k * 0.021)
        pts = [V3(p) + V3((0, 0, k * 0.022)) for p in feed]
        pts += [far.lerp(T, 0.12) + o, far.lerp(T, 0.55) + o, far.lerp(T, 0.90) + o * 0.8]
        pts += [arc_pt(cx, yc - 0.024, mid + sg * a, ARC_R + k * 0.013) for a in (12, 24)]
        pts.append(arc_pt(cx, yc - 0.012, mid + sg * 36, ARC_R - 0.004 + k * 0.013))
        tube(gc, pts, 0.0085)
    gd.box(gland, (0.075, 0.03, 0.075), rot=Matrix.Rotation(rad(-(mid + sg * 40)), 3, 'Y'))
    for t in (0.25, 0.60):
        gk.box(far.lerp(T, t) + n * 0.018, (0.018, 0.085, 0.022),
               rot=V3((1, 0, 0)).rotation_difference(s).to_matrix())
    gb.obj("arm.blades." + tag, "carbon", bevel=0.0025, mirror=True)
    ga.obj("arm." + tag, "alloy", bevel=0.002, mirror=True)
    gs.obj("springs." + tag, "paint", mirror=True)
    gc.obj("cables." + tag, "cable", sharp=60, mirror=True)
    gk.obj("arm.bits." + tag, "gloss_black", mirror=True)
    gd.obj("arm.gland." + tag, "alloy_dark", bevel=0.003, mirror=True)


def build_arms():
    z = top_z(0.80, 0.105, 0.42)
    build_arm("f", FA_X, F_W, 180,
              [(0.90, 0.270, (0.90, 0.20, 0.27)), (0.42, 0.40, (0.42, 0.50, 0.40))],
              (0.80, 0.105, z + 0.036), (0.52, 0.098, top_z(0.52, 0.098, 0.54) + 0.028),
              [side_pt(0.30, 0.46, (0.30, 0.52, 0.46)) + V3((0, -0.01, 0))],
              steer=(0.80, 0.215, (0.80, 0.30, 0.215)))
    z = top_z(-1.22, 0.07, 0.74)
    build_arm("r", RA_X, R_W, 0,
              [(-0.42, 0.42, (-0.42, 0.53, 0.42)), (-0.74, 0.42, (-0.74, 0.44, 0.42))],
              (-1.22, 0.07, z + 0.036), (-1.56, 0.050, top_z(-1.56, 0.05, 0.73) + 0.026),
              [(-0.865, 0.255, 0.365), (-0.865, 0.33, 0.375), (-0.80, 0.42, 0.40)])


# ---------------------------------------------------------------------------------------
# the inverter on the tub's bulkhead (the motors are in the rings), the front glands
# ---------------------------------------------------------------------------------------
def build_power():
    g, ge = Geo(), Geo()
    g.box((-0.865, 0, 0.365), (0.115, 0.50, 0.21))
    for k in range(7):
        g.box((-0.865, -0.21 + 0.07 * k, 0.365), (0.127, 0.020, 0.222))
    ge.box((-0.865, 0, 0.365), (0.119, 0.47, 0.012))
    g.box((-0.865, 0, 0.215), (0.07, 0.30, 0.09))               # its mount, coolant below
    g.obj("inverter", "alloy_dark", bevel=0.003)
    ge.obj("inverter.glow", "ember")
    g = Geo()
    for s in (1, -1):
        tube(g, [(-0.90, s * 0.10, 0.25), (-0.94, s * 0.12, 0.30), (-0.97, s * 0.12, 0.45),
                 (-1.00, s * 0.09, 0.56)], 0.011)
    g.obj("lines", "alloy", sharp=60)
    g = Geo()                                                   # where the front feeds leave
    p = side_pt(0.30, 0.46, (0.30, 0.52, 0.46))
    g.box(p, (0.10, 0.04, 0.095))
    g.obj("glands", "alloy_dark", bevel=0.003, mirror=True)


# ---------------------------------------------------------------------------------------
# whiskers on the bow, a feather on the tail: the only blades, each with its hairline
# ---------------------------------------------------------------------------------------
def build_blades():
    g, gl, gt = Geo(), Geo(), Geo()
    sec = [(2.050, 0.158), (2.030, 0.168), (1.960, 0.172), (1.885, 0.180), (1.890, 0.170),
           (1.960, 0.160), (2.030, 0.154)]
    for s in (1, -1):
        y0, y1 = (0.085, 0.80) if s > 0 else (-0.80, -0.085)
        g.prism([(x, y0, z) for (x, z) in sec], (0, y1 - y0, 0))
        g.prism([(2.055, s * 0.80 - 0.005, 0.105), (2.055, s * 0.80 - 0.005, 0.205),
                 (1.965, s * 0.80 - 0.005, 0.250), (1.875, s * 0.80 - 0.005, 0.250),
                 (1.865, s * 0.80 - 0.005, 0.105)], (0, 0.010, 0))
        gl.box((2.0515, s * 0.445, 0.160), (0.005, 0.69, 0.006))
        gl.box((2.0575, s * 0.80, 0.155), (0.005, 0.007, 0.095))
        text_flat(gt, NUM, 0.060, (1.955, s * 0.8065, 0.180), (-s, 0, 0), (0, 0, 1))
    g.obj("whiskers", "weave", bevel=0.002)
    gl.obj("led.whiskers", "led_front")
    # the feather: a flat delta through the tail's tip
    g, gl = Geo(), Geo()
    zf = 0.697
    g.prism([(-1.86, 0, zf), (-1.985, 0.46, zf), (-2.115, 0.46, zf), (-2.115, -0.46, zf),
             (-1.985, -0.46, zf)], (0, 0, 0.012))
    for s in (1, -1):
        g.prism([(-1.955, s * 0.46 - 0.005, zf - 0.05), (-1.985, s * 0.46 - 0.005, zf + 0.075),
                 (-2.125, s * 0.46 - 0.005, zf + 0.075), (-2.125, s * 0.46 - 0.005, zf - 0.05)],
                (0, 0.010, 0))
        gl.box((-2.1175, s * 0.245, zf + 0.006), (0.005, 0.41, 0.006))
        gl.box((-2.1275, s * 0.46, zf + 0.0125), (0.005, 0.007, 0.125))
        text_flat(gt, "VEX", 0.062, (-2.035, s * 0.24, zf + 0.0128), (0, -1, 0), (1, 0, 0),
                  spacing=1.15)
        text_flat(gt, NUM, 0.050, (-2.045, s * 0.4665, zf + 0.022), (-s, 0, 0), (0, 0, 1))
    g.obj("feather", "weave", bevel=0.002)
    gl.obj("led.feather", "led_rear")
    gt.obj("blade.lettering", "decal")
    g = Geo()                                   # the rain light on the tail's tip
    g.box((-2.108, 0, 0.7035), (0.012, 0.026, 0.030))
    g.obj("led.rain", "led_rear")


def build_lights():
    g, gl, gr = Geo(), Geo(), Geo()
    p = side_pt(1.84, 0.215, (1.84, 0.10, 0.215))
    cluster(g, gl, p, (1.93, 0.345, 0.325), 1)
    p = side_pt(-1.66, 0.715, (-1.66, 0.10, 0.715))
    cluster(g, gr, p, (-1.83, 0.285, 0.800), -1)
    g.obj("stalks", "carbon", bevel=0.002, mirror=True)
    gl.obj("led.front", "lamp", mirror=True)
    gr.obj("led.rear", "led_rear", mirror=True)
    g = Geo()                                   # amber markers on the tub's shoulders
    ribbon(g, [(0.06, 0.535), (-0.06, 0.535)], 'z', 0.010)
    g.obj("led.marker", "led_accent", mirror=True)


# ---------------------------------------------------------------------------------------
# cockpit: one pit, the spine through it, a wraparound screen, a ring behind each head
# ---------------------------------------------------------------------------------------
def build_cockpit():
    # ---- the screen: one arc round the front of the pit and back along its sides
    path = smooth([(0.0, -0.489), (0.14, -0.478), (0.27, -0.44), (0.385, -0.33),
                   (0.44, -0.17), (0.455, 0.0), (0.44, 0.17), (0.385, 0.33), (0.27, 0.44),
                   (0.14, 0.478), (0.0, 0.489)], 5)
    g, gf = Geo(), Geo()
    rows = []
    for p in path:
        u = min(1.0, abs(p.y) / 0.489)
        tside = max(0.0, (0.30 - p.x) / 0.30)           # 0 round the front, 1 at the ends
        zb = top_z(p.x, p.y, 0.60) - 0.006
        h = 0.235 * (1 - 0.30 * u * u) * (1 - tside) ** 0.8 + 0.012
        d = V3((-0.15 - p.x, -p.y, 0))
        d.normalize()
        b = V3((p.x, p.y, zb))
        rows.append((b, b + d * (h * (0.50 - 0.36 * u)) + V3((0, 0, h)), d))
    vs, fs = [], []
    for (b, t, d) in rows:
        vs += [b, t, t + d * 0.006, b + d * 0.006]
    N = len(rows) - 1
    for k in range(N):
        o = 4 * k
        fs += [(o + j, o + (j + 1) % 4, o + 4 + (j + 1) % 4, o + 4 + j) for j in range(4)]
    fs += [(0, 1, 2, 3), tuple(4 * N + j for j in range(4))]
    g.add(vs, fs)
    g.obj("screen", "visor", sharp=40)                  # sharp edges, or the slab is a lens
    blade(gf, [b + V3((0, 0, 0.004)) - d * 0.003 for (b, t, d) in rows], 0.018, 0.012)
    tube(gf, [t + d * 0.003 + V3((0, 0, 0.002)) for (b, t, d) in rows], 0.0045, 6)
    gf.obj("screen.rail", "alloy", bevel=0.0015)
    g = Geo()                                           # the spine's post up the screen
    b, t, d = rows[N // 2]
    blade(g, [b + V3((0.006, 0, 0)), t + V3((0.006, 0, 0.004))], 0.014, 0.022, up=(0, 1, 0))
    g.obj("screen.post", "alloy", bevel=0.0015)

    # ---- mirrors on stalks, by the screen's ends
    g, gm = Geo(), Geo()
    root = V3((0.30, 0.455, top_z(0.30, 0.455, 0.58)))
    head = V3((0.27, 0.655, 0.715))
    tube(g, [root, root.lerp(head, 0.55) + V3((0, 0, 0.03)), head], 0.006)
    g.hexa([head + V3(o) for o in ((0.035, -0.055, -0.03), (0.035, 0.055, -0.03),
                                    (-0.012, 0.06, -0.034), (-0.012, -0.06, -0.034),
                                    (0.035, -0.055, 0.03), (0.035, 0.055, 0.03),
                                    (-0.012, 0.06, 0.034), (-0.012, -0.06, 0.034))])
    gm.box(head + V3((-0.0135, 0, 0)), (0.003, 0.105, 0.055))
    g.obj("mirrors", "weave", bevel=0.003, mirror=True)
    gm.obj("mirror.glass", "mirror", mirror=True)

    # ---- seats: weave shells, pads, belts
    gsh, gp, gbelt, gi, gscr = Geo(), Geo(), Geo(), Geo(), Geo()
    tilt = Matrix.Rotation(rad(-24), 3, 'Y')
    z0 = PIT_Z
    for y in (0.215, -0.215):
        gsh.box((-0.19, y, z0 + 0.028), (0.50, 0.35, 0.03))
        gsh.box((-0.475, y, z0 + 0.315), (0.035, 0.35, 0.62), rot=tilt)
        for s in (-1, 1):
            gsh.box((-0.22, y + s * 0.17, z0 + 0.07), (0.44, 0.022, 0.10))
            gsh.box((-0.445, y + s * 0.17, z0 + 0.31), (0.11, 0.022, 0.48), rot=tilt)
        gp.box((-0.18, y, z0 + 0.054), (0.42, 0.29, 0.04))
        gp.box((-0.447, y, z0 + 0.30), (0.04, 0.29, 0.44), rot=tilt)
        gp.box((-0.565, y, z0 + 0.60), (0.055, 0.19, 0.13), rot=tilt)
        for s in (-1, 1):
            gbelt.box((-0.427, y + s * 0.062, z0 + 0.33), (0.008, 0.045, 0.42), rot=tilt)
        gbelt.box((-0.20, y, z0 + 0.078), (0.05, 0.29, 0.008))
        # a screen each on the pit's front wall
        gscr.box((0.262, y, 0.505), (0.006, 0.24, 0.075), rot=Matrix.Rotation(rad(-18), 3, 'Y'))
        gi.box((0.282, y, 0.505), (0.02, 0.29, 0.10), rot=Matrix.Rotation(rad(-18), 3, 'Y'))
    # the driver's yoke on the left, on a column
    yk = Matrix.Translation((0.085, 0.215, 0.515)) @ Matrix.Rotation(rad(-24), 4, 'Y')
    gi.box((0, 0, 0), (0.028, 0.27, 0.035), xf=yk)
    for s in (-1, 1):
        gi.box((0, s * 0.135, 0.04), (0.032, 0.032, 0.11), xf=yk)
    tube(gi, [(0.09, 0.215, 0.51), (0.275, 0.215, 0.455)], 0.014)
    # a padded roll round the pit's rim, heel plates, pedals
    gr, gh = Geo(), Geo()
    loop = [V3((x, y, top_z(x * 1.0, y, 0.62) + 0.004)) for (x, y) in
            [(0.375, 0.05), (0.36, 0.16), (0.305, 0.31), (0.18, 0.40), (0.0, 0.415),
             (-0.45, 0.405), (-0.59, 0.355), (-0.655, 0.225), (-0.655, 0.05)]]
    tube(gr, loop, 0.012)
    for s in (1, -1):
        gh.box((0.17, s * 0.215, z0 + 0.008), (0.24, 0.30, 0.006))
    for k, wd in enumerate((0.05, 0.07)):
        gh.box((0.27, 0.15 + 0.13 * k, z0 + 0.065), (0.012, wd, 0.10),
               rot=Matrix.Rotation(rad(-20), 3, 'Y'))
    gh.box((0.26, -0.215, z0 + 0.04), (0.012, 0.28, 0.07), rot=Matrix.Rotation(rad(-30), 3, 'Y'))
    gr.obj("cockpit.roll", "interior", sharp=50, mirror=True)
    gh.obj("cockpit.plates", "alloy", bevel=0.002)
    gsh.obj("seat.shells", "carbon", bevel=0.004)
    gp.obj("seat.pads", "seat", bevel=0.012, segs=3)
    gbelt.obj("seat.belts", "belt")
    gi.obj("cockpit.trim", "interior", bevel=0.003)
    gscr.obj("cockpit.screens", "screen")

    # ---- the halos: a ring behind each head, stays to the tail
    g, gs = Geo(), Geo()
    for s in (1, -1):
        zc = top_z(-0.715, s * 0.215, 0.68) + 0.168
        c = V3((-0.715, s * 0.215, zc))
        ring(g, c, (1, 0, 0), 0.180, 0.146, 0.040, 40)
        for a in range(0, 360, 30):
            p = c + V3((-0.0205, 0.163 * cos(rad(a)), 0.163 * sin(rad(a))))
            stud(gs, p, V3((-1, 0, 0)), [(-0.002, 0.001), (-0.002, 0.006), (0.003, 0.006),
                                         (0.003, 0.001)], 6)
        tube(gs, [c + V3((-0.02, -s * 0.06, 0.150)),
                  (-1.10, s * 0.034, top_z(-1.10, s * 0.034, 0.74) - 0.004)], 0.011)
        gs.box(c + V3((0, 0, -0.165)), (0.07, 0.13, 0.02))
    g.obj("halos", "alloy", bevel=0.005, segs=3)
    gs.obj("halo.stays", "alloy_dark", bevel=0.0015)


# ---------------------------------------------------------------------------------------
# lettering and small things on the pods as built
# ---------------------------------------------------------------------------------------
def build_details():
    gd, gi, gw = Geo(), Geo(), Geo()                    # plates, dark ink, light ink
    for side in (1, -1):
        block(gd, gi, NUM, 0.105, 0.14, 0.512, side, pad=0.014, wide=0.21)
        text_on_body(gw, "HALO", 0.044, -0.20, 0.538, side, spacing=1.3)
        text_on_body(gw, "VEX SKELETAL WORKS", 0.016, -0.20, 0.488, side, spacing=1.3)
        block(gd, gi, "OHMIC", 0.024, -0.50, 0.545, side, pad=0.008)
        block(gd, gi, "NULLWERK", 0.020, -0.505, 0.497, side, pad=0.008)
        text_on_body(gw, "KITE FLUIDS", 0.022, 0.10, 0.27, side, spacing=1.2)
        text_on_body(gw, "RIM DRIVE 4 x 90 KW", 0.015, -0.42, 0.30, side, spacing=1.25)
        text_on_body(gi, "H-" + NUM, 0.030, 0.80, 0.335, side, spacing=1.1)
        text_on_body(gw, "VEX", 0.030, -1.16, 0.648, side, spacing=1.2)
    for s in (1, -1):
        ribbon(gd, [(-0.07, s * 0.462), (-0.27, s * 0.458)], 'z', 0.046)
        text_top(gi, "STEP", 0.020, -0.17, s * 0.460, right=(-s, 0), lift=0.0022, spacing=1.3)
    text_top(gi, NUM, 0.115, 0.66, 0.155)
    text_top(gi, NUM, 0.115, 0.66, -0.155, right=(1, 0))
    for s in (1, -1):
        text_top(gi, "LIFT HERE", 0.013, -0.725, s * 0.385, right=(-s, 0), spacing=1.2)
        text_top(gi, "HALO", 0.026, -1.15, s * 0.115, right=(-s, 0), spacing=1.2)
    gd.obj("decal.plates", "decal")
    gi.obj("decal.ink", "ink")
    gw.obj("decal.light", "decal")
    # fasteners along the caps' edge, a filler on the scuttle
    g = Geo()
    prof = [(-0.002, 0.001), (-0.002, 0.006), (0.002, 0.006), (0.002, 0.001)]
    for k in range(13):
        x = 0.92 - 0.135 * k
        for dz in (0.026, -0.030):
            loc, n = on_body(x, tub_w(x)[1] + dz, 'y')
            if loc is not None:
                stud(g, loc, n, prof, 6)
    for x in (-1.06, -1.22, -1.38, -1.54):
        loc, n = on_body(x, 0.668 + 0.03 * (-1.06 - x), 'y')
        if loc is not None:
            stud(g, loc, n, prof, 6)
    for x in (2.02, 1.92, 1.82):
        loc, n = on_body(x, 0.192, 'y')
        if loc is not None:
            stud(g, loc, n, prof, 6)
    g.obj("fasteners", "alloy", mirror=True)
    g = Geo()
    loc, n = on_body(0.56, 0.10, 'z')
    if loc is not None:
        stud(g, loc, n, [(-0.002, 0.002), (-0.002, 0.026), (0.006, 0.026), (0.008, 0.020),
                         (0.008, 0.002)], 12)
    g.obj("filler", "gloss_black")
    # a tow eye under the bow's tip, a pitot on it
    g = Geo()
    ring(g, (2.15, 0, 0.118), (0, 1, 0), 0.030, 0.018, 0.010, 16)
    tube(g, [(2.135, 0, 0.165), (2.172, 0, 0.165)], 0.004)
    g.obj("bow.bits", "alloy")


# ---------------------------------------------------------------------------------------
# views and the build
# ---------------------------------------------------------------------------------------
K.VIEWS["hero"].update(dir=(1.0, 0.86, 0.27), focus=(1.3, 0.8, 0.4), fstop=11.0)
K.VIEWS["rear"].update(dir=(-1.0, -0.80, 0.34), focus=(-1.3, -0.7, 0.5), fstop=11.0)
K.VIEWS.update(
    wheel=dict(dir=(0.45, 1.0, 0.16), lens=85, target=(1.30, 0.85, 0.40), dist=3.0),
    inboard=dict(dir=(-0.2, -1.0, 0.35), lens=85, target=(1.25, 0.6, 0.40), dist=3.2),
    cabin=dict(dir=(0.3, 1.0, 0.60), lens=85, target=(-0.1, 0.1, 0.5), dist=4.0),
    tail=dict(dir=(-1.0, 0.7, 0.30), lens=85, target=(-1.2, 0.2, 0.5), dist=4.6),
)


def main():
    violet = (0.085, 0.0, 0.30)
    K.materials(paint=violet, paint_finish="gloss", dust_amount=0.10,
                caliper=violet, seat=(0.035, 0.035, 0.04),
                decal=(0.82, 0.82, 0.80), screen=(0.75, 0.45, 1.0),
                led_front=(0.85, 0.95, 1.0), led_accent=(1.0, 0.45, 0.03),
                led_wheel=(0.80, 0.62, 1.0), ember=(0.70, 0.25, 1.0))
    K.pbr("alloy", (0.56, 0.57, 0.59), 1.0, 0.30)           # raw machined metal
    K.pbr("alloy_dark", (0.16, 0.165, 0.175), 1.0, 0.42)
    K.pbr("rotor", (0.34, 0.345, 0.36), 1.0, 0.22)          # the rims' brake lips
    K.pbr("copper", (0.70, 0.36, 0.17), 1.0, 0.38)
    K.pbr("cable", (0.95, 0.30, 0.02), 0.0, 0.45)
    K.pbr("belt", (0.80, 0.42, 0.02), 0.0, 0.7)
    K.pbr("ink", (0.012, 0.012, 0.014), 0.0, 0.5)
    K.pbr("mirror", (0.75, 0.77, 0.80), 1.0, 0.03)
    # blades: a dry lay-up (the kit's coated weave turns silver on a flat plane seen at a
    # grazing angle against the studio's rim light)
    _, b = K.carbon("weave")
    b.inputs["Metallic"].default_value = 0.0
    b.inputs["Coat Weight"].default_value = 0.0
    b.inputs["Specular IOR Level"].default_value = 0.12
    mr = b.inputs["Roughness"].links[0].from_node
    mr.inputs["To Min"].default_value = 0.60
    mr.inputs["To Max"].default_value = 0.85
    K.pbr("visor", (0.30, 0.26, 0.34), 0.0, 0.0, **{"Transmission Weight": 1.0, "IOR": 1.5})
    build_pods()
    K.log("pods")
    build_spine()
    build_blades()
    build_arms()
    build_power()
    K.log("spine, blades, arms")
    build_lights()
    build_cockpit()
    build_details()
    K.log("details")
    for side, s in ((1, "l"), (-1, "r")):
        build_ring_wheel("f" + s, FA_X, F_W, side, (58, 238))
        build_ring_wheel("r" + s, RA_X, R_W, side, (122, 302))
    K.log("wheels")
    K.shoot(extra="top")


main()
