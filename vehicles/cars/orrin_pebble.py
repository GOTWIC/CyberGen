"""Orrin Pebble: a two-seat city pod, a river stone held in four soft paws (both names made
up), built on vehicles/carkit.py. The Lumen's little sibling.

Run (always through the wrapper, one Blender job at a time on this machine):
    vehicles/blender.sh vehicles/cars/orrin_pebble.py --out DIR --preview
    vehicles/blender.sh vehicles/cars/orrin_pebble.py --out DIR --sheet [--night]

The body is nine lines over eleven ring stations with no crease anywhere. As on the Lumen the
rings close on a small pole at the nose and at the tail, and the three lines nearest the top
are the glass: one dome leaf from pole to pole. Here the glass edge dips low at the doors and
the four fenders rise round it, so the stone sits in them like a gem in its claws. The dome
forward of the hinge ring (over the rear axle) lifts as the door; the glass behind it is
fixed over the luggage shelf. One light ribbon runs all the way round the waist, white ahead
of the flank pebbles and red behind, swelling into a lit pebble on each pole and on each
flank (the left one is the charge port). The ribbon is channels cut into the skin along the
widest line (round the nose, round the tail, along each petal to the flank flap the pebble
sits on, each stopping short of the shut lines), a light guide in each under a flush lens;
the crescent slots, the grab recess, the flaps and the lidded wheel wells are cut too
(cutters(), on the hull as it stands uncut). The view "open" (the sheet's fifth tile)
renders with the leaf lifted about its hinge. The brand's helpers are in
vehicles/brands/orrin.py. PEBBLE_PROBE=1 builds the bare hull and prints the skin's
position round the wheels (room for tires and cavities).
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import bpy                                                          # noqa: E402
import carkit as K                                                  # noqa: E402
from brands import orrin                                            # noqa: E402
from brands.orrin import (both, dot_field, lune_cut, ring, snap, spline, stone,   # noqa: E402
                          strip, text_proj)
from carkit import Geo, Matrix, V3, cos, on_body, pi, rad, sin, stud, text_flat   # noqa: E402

orrin.setup(axis=(0.8, 0.7))        # normals turned away from the car's axis

PROBE = bool(os.environ.get("PEBBLE_PROBE"))

# ---------------------------------------------------------------------------------------
# dimensions
# ---------------------------------------------------------------------------------------
FA_X, RA_X = 0.90, -0.88            # axles: wheelbase 1.78
R, W, RIM = 0.295, 0.185, 0.232     # tire radius, width, rim radius
OUT = 0.660                         # outer face of the tires
CAV = 0.320                         # wheel cavity radius
F_LID, R_LID = 0.350, 0.335         # top of the wheel openings: the body lids the wheels
NOSE = V3((1.40, 0, 0.55))          # the poles the rings close on
TAIL = V3((-1.40, 0, 0.60))
FLANK = (-0.30, 0.558)              # where white turns red: the flank pebbles (x, z)

# ---------------------------------------------------------------------------------------
# body: stations (rings) and lines
# ---------------------------------------------------------------------------------------
LINES = "CGKESULRB"
#        C top centerline, G dome crown, K dome side, E glass edge, S fender shoulder,
#        U widest (the ribbon), L lower flank, R rocker, B floor centerline
ORDER = ["P0", "N1", "N2", "FA", "D1", "M", "D2", "RA", "T2", "T1", "T0"]
PT = {}


def stations():
    T = {
        "N1": [(1.37, 0, .70), (1.369, .08, .698), (1.367, .17, .69), (1.363, .26, .675),
               (1.35, .39, .635), (1.34, .46, .55), (1.358, .46, .44), (1.368, .30, .378),
               (1.370, 0, .365)],
        "N2": [(1.25, 0, .915), (1.247, .18, .907), (1.24, .35, .878), (1.23, .47, .84),
               (1.205, .665, .755), (1.19, .765, .555), (1.232, .775, .34), (1.258, .64, .215),
               (1.265, 0, .20)],
        # over the wheels the fenders rise beside the glass (the paws) and the flank comes
        # straight down round the tires
        "FA": ring(FA_X, 1.235, (.33, 1.205), (.555, 1.065), (.625, .955), (.755, .86),
                   (.815, .565), (.80, .30), (.70, .15), .145),
        # the two petal cuts fan: forward at the top, back at the top; between them the
        # glass edge dips to the waist, the low sill you step over
        "D1": ring((.46, .46, .46, .45, .43, .40, .36, .345, .345), 1.46, (.39, 1.42),
                   (.675, 1.09), (.75, .77), (.79, .69), (.80, .56), (.78, .30),
                   (.66, .15), .14),
        "M": ring(0.0, 1.548, (.42, 1.498), (.715, 1.115), (.78, .68), (.795, .628),
                  (.80, .555), (.775, .295), (.65, .15), .14),
        "D2": ring((-.46, -.46, -.46, -.45, -.43, -.40, -.36, -.345, -.345), 1.495,
                   (.40, 1.455), (.685, 1.105), (.75, .78), (.79, .695), (.80, .565),
                   (.78, .305), (.66, .15), .14),
        "RA": ring(RA_X, 1.29, (.35, 1.255), (.57, 1.09), (.625, .975), (.755, .875),
                   (.815, .575), (.80, .305), (.70, .155), .15),
        "T2": [(-1.25, 0, .97), (-1.247, .19, .96), (-1.24, .36, .93),
               (-1.23, .47, .885), (-1.205, .675, .785), (-1.19, .775, .585),
               (-1.232, .785, .365), (-1.258, .65, .24), (-1.265, 0, .225)],
        "T1": [(-1.37, 0, .75), (-1.369, .08, .748), (-1.367, .17, .74), (-1.363, .26, .725),
               (-1.35, .39, .685), (-1.34, .46, .60), (-1.358, .46, .49),
               (-1.368, .30, .428), (-1.370, 0, .415)],
    }
    for name, src, pole in (("P0", "N1", NOSE), ("T0", "T1", TAIL)):
        T[name] = [(pole.x, p[1] * 0.22, pole.z + (p[2] - pole.z) * 0.22) for p in T[src]]
    S = K.fill([T[k] for k in ORDER])
    PT.update(K.table(ORDER, LINES, S))
    return S


PMAT = dict(front="paint", petal="paint", rear="paint", glass="glass_dome", glass_t="glass_dome",
            floor="underbody", well="well", slot="void", cut="void", lamp_f="lamp_housing",
            lamp_r="lamp_housing")
GAP = 0.00175                       # 3.5 mm shut lines
LAMP = {}                           # the ribbons' channels on the skin: [(point, way out)]
RIB_W, RIB_D = 0.017, 0.014         # a ribbon channel's width and depth, drawn out to RIB_TIP
RIB_TIP, RIB_TAPER = 0.005, 0.05    # at its ends (at the flaps) over RIB_TAPER meters
FLAP = (0.070, 0.050)               # the flank flaps' half sizes round the flank pebbles
D_U, SHUT_M = 0.40, 0.03            # the petal cuts' |x| on the ribbon's line; the channels
                                    # stop SHUT_M short of them


def panel_of(i, j):
    if j == 7 and 2 <= i <= 7:           # the belly is painted where it turns up at both ends
        return "floor"
    if j <= 2:                           # the dome: the leaf that lifts, and the fixed tail
        return "glass" if i <= 6 else "glass_t"
    if i <= 3:
        return "front"
    return "petal" if i <= 5 else "rear"


def ribbon_halves():
    """The left halves of the ribbon's channels: round the nose from beside the front petal
    cut, round the tail from beside the rear one, and along the petal from beside its front
    cut to the flank flap. Each stops SHUT_M short of a shut line, so no panel is cut in
    two (a game pack's far LOD collapses two strips of paint apart, tearing them)."""
    P = PT
    fx, fz = FLANK
    e = FLAP[0] + 0.020                 # the channel stops short of the flap
    front = [(D_U + SHUT_M, .80, .5575), (FA_X, .81, .563), P["N2"]["U"], P["N1"]["U"],
             (NOSE.x, 0, NOSE.z + 0.012)]
    rear = [(-D_U - SHUT_M, .80, .567), (-0.60, .80, .566), (RA_X, .81, .575), P["T2"]["U"],
            P["T1"]["U"], (TAIL.x, 0, TAIL.z + 0.012)]
    mid = [(D_U - SHUT_M, .80, .5575), (0.10, .80, .556), (fx + e, .80, fz - 0.0005)]
    return front, rear, mid


def on_skin(ctrl, n=12, lift=0.004):
    """The smooth curve through ctrl laid on the skin, each point lift outside it (so the
    kit's trace() turns its normals out)."""
    out = []
    for q in spline(ctrl, n):
        loc, nn = snap(q)
        if not out or (loc - out[-1][0]).length > 1e-4:
            out.append((loc, nn))
    return [q + nn * lift for q, nn in out]


def width_at(t, ln):
    """A ribbon's channel width at share t of its run, ln long: drawn out at both ends."""
    k = min(1.0, (t * ln / RIB_TAPER) ** 0.6, ((1 - t) * ln / RIB_TAPER) ** 0.6)
    return RIB_TIP + (RIB_W - RIB_TIP) * max(0.0, k)


def cutters():
    """Everything cut into the hull, laid on it while it stands uncut: the wheel wells and
    lids, the crescent slots and the grab recess, the ribbons' light channels, the flank
    flaps."""
    ang = list(range(-25, 206, 10))
    cav, cav2, cav3, lids, slots = Geo(), Geo(), Geo(), Geo(), Geo()
    for cx, top in ((FA_X, F_LID), (RA_X, R_LID)):
        K.well_cutter(cav, cx, R, CAV, 0.45, ang, depth=0.155)
        K.well_cutter(cav2, cx, R, R + 0.008, 0.60, ang, depth=OUT + 0.004 - 0.60)
        # room beside the tires' sidewalls under the eyelids, inside the skin
        K.well_cutter(cav3, cx, R, R + 0.018, 0.60, ang, depth=OUT + 0.030 - 0.60)
        orrin.lid_cutter(lids, cx, top, a=0.322, z0=0.27, y0=0.648)
    # crescents: a pair under the ribbon at each end, and one beside each wheel lid, facing
    # each other across the petal like a pair of brackets
    lune_cut(slots, (1.378, .15, .470), (1.298, .50, .460), (0.80, 0.55, -0.30), (0, 0, -1),
             0.040, 0.019, depth=0.04, flare=0.012)
    lune_cut(slots, (-1.378, .15, .520), (-1.298, .50, .510), (-0.80, 0.55, -0.30),
             (0, 0, -1), 0.040, 0.019, depth=0.04, flare=0.012)
    for cx, sx in ((FA_X, 1), (RA_X, -1)):
        xe = cx - sx * 0.322                # the lid's edge toward the middle
        lune_cut(slots, (xe - sx * 0.052, .690, .25), (xe - sx * 0.028, .792, .48),
                 (0, 1, -0.2), (-sx, 0, 0), 0.040, 0.018, depth=0.05, flare=0.016)
    # the grab recess: a crescent under the glass where it dips lowest, to lift the leaf by
    lune_cut(slots, (0.30, .792, .636), (0.06, .792, .630), (0, 1, 0.12), (0, 0, -1), 0.024,
             0.007, depth=0.035, flare=0.010)
    # the pebbles' seats on the skin as it stands uncut
    fx, fz = FLANK
    LAMP["peb.front"] = snap((NOSE.x + 0.05, 0, NOSE.z + 0.030))
    LAMP["peb.rear"] = snap((TAIL.x - 0.05, 0, TAIL.z + 0.030))
    LAMP["peb.flank"] = [snap((fx, sgn * 0.85, fz)) for sgn in (1, -1)]
    # the ribbon: a channel round each end and one along each petal, each under its lens
    fh, rh, mh = ribbon_halves()
    chans = {}
    for key, pts, mirror in (("front", on_skin(both(fh)), False),
                             ("rear", on_skin(both(rh)), False), ("mid", on_skin(mh), True)):
        ln = sum((b - a).length for a, b in zip(pts, pts[1:]))
        g = Geo()
        LAMP[key] = K.groove(g, pts, width=lambda t, ln=ln: width_at(t, ln), depth=RIB_D,
                             step=0.012, mirror=mirror)
        chans[key] = g
    LAMP["mid_r"] = [(V3((q.x, -q.y, q.z)), V3((n.x, -n.y, n.z))) for q, n in LAMP["mid"]]
    chans["front"].add(chans["mid"].v, chans["mid"].f)
    # the flank flaps (the left one the charge port's): an oval cut round each flank pebble
    cut = Geo()
    K.groove(cut, [(fx + FLAP[0] * cos(rad(a)), fz + FLAP[1] * sin(rad(a)))
                   for a in range(5, 365, 10)], 'y', closed=True, mirror=True, round=2)
    return [(cav, "well"), (cav2, "well"), (cav3, "well"), (lids, "well"), (slots, "slot"),
            (chans["front"], "lamp_f"), (chans["rear"], "lamp_r"), (cut, "cut", "drop")]


def build_hull():
    body = K.build_body(stations(), panel_of, PMAT, 0.0, 0.0,
                        front=dict(kind="flat", panel="front", crease=0.0),
                        rear=dict(kind="flat", panel="rear", crease=0.0),
                        cutters=[] if PROBE else cutters, subdiv=4, thick=0.003, gap=GAP)
    for pn, keys in (("lamp_f", ("front", "mid", "mid_r")), ("lamp_r", ("rear",))):
        ob = body.parts.get(pn)
        if ob is None:
            continue
        for key in keys:
            chop(ob, LAMP[key])
        # the channels' walls a sheet 1 mm thick, a panel of the body: a game pack keeps them
        # as they are (a bare sheet, it bakes them down onto the guide)
        md = ob.modifiers.new("solid", 'SOLIDIFY')
        md.thickness = 0.001
        md.offset = 0.0


def chop(ob, tr, step=0.09):
    """A channel's walls cut into loose pieces step long across its path tr (the same
    surface): a game pack's far LOD leaves such small pieces out, where the whole wall,
    1.8 m of thin sheet round the nose, collapsed into dark shards over the paint."""
    import bmesh
    bm = bmesh.new()
    bm.from_mesh(ob.data)
    xf = ob.matrix_world.inverted()
    P = [xf @ q for q, _ in tr]
    ln = sum((b - a).length for a, b in zip(P, P[1:]))
    s, last, cuts = 0.0, 0.0, set()
    for a, b in zip(P, P[1:]):
        s += (b - a).length
        if s - last < step or s > ln - step / 2:
            continue
        last = s
        geom = list(bm.verts) + list(bm.edges) + list(bm.faces)
        res = bmesh.ops.bisect_plane(bm, geom=geom, plane_co=b, plane_no=(b - a).normalized(),
                                     dist=1e-6)
        for e in res["geom_cut"]:          # only the cut across the channel here
            if isinstance(e, bmesh.types.BMEdge) and all((v.co - b).length < 0.05
                                                          for v in e.verts):
                cuts.add(e)
    bmesh.ops.split_edges(bm, edges=[e for e in cuts if e.is_valid])
    bm.to_mesh(ob.data)
    bm.free()
    ob.data.update()


def probe():
    """PEBBLE_PROBE=1: the skin where the tires and the wheel cavities need room."""
    for cx in (FA_X, RA_X):
        for dx in (-0.31, -0.29, -0.25, 0.0, 0.25, 0.29, 0.31):
            row = []
            for z in (0.20, 0.25, 0.30, 0.35, 0.40, 0.45, 0.50, 0.60):
                loc, _ = on_body(cx + dx, z, 'y')
                row.append("%.3f" % loc.y if loc else " none")
            print("skin y at x %+.2f (tire face %.3f): %s" % (cx + dx, OUT, " ".join(row)))
        row = []
        for y in (0.45, 0.55, 0.62, 0.68):
            loc, _ = on_body(cx, y, 'z')
            row.append("%.3f" % loc.z)
        print("skin z over the axle at x %.2f: %s" % (cx, " ".join(row)))
    for x in (0.54, 0.3, 0.0, -0.3, -0.54):
        row = []
        for z in (0.25, 0.32, 0.48, 0.56, 0.64, 0.70, 0.76):
            loc, _ = on_body(x, z, 'y')
            row.append("%.3f" % loc.y if loc else " none")
        print("flank y at x %+.2f: %s" % (x, " ".join(row)))
    for y in (0.0, 0.15, 0.3, 0.5):
        row = []
        for z in (0.40, 0.45, 0.50, 0.55, 0.62, 0.70):
            loc, _ = on_body(y, z, 'x')
            row.append("%.3f" % loc.x if loc else " none")
        print("nose x at y %.2f: %s" % (y, " ".join(row)))
    for st in ORDER[1:-1]:
        print("glass edge near %s: %s" % (st, tuple(round(c, 3) for c in snap(PT[st]["E"])[0])))


# ---------------------------------------------------------------------------------------
# things lying on the surface as built
# ---------------------------------------------------------------------------------------
def along(tr, s0=0.0, s1=None, step=0.03):
    """Frames every step along a traced path between the lengths s0 and s1:
    [(point, normal, tangent, side, share)], side = tangent x normal, share of the run."""
    P = [q for q, _ in tr]
    S = [0.0]
    for a, b in zip(P, P[1:]):
        S.append(S[-1] + (b - a).length)
    s1 = S[-1] if s1 is None else min(s1, S[-1])
    n = max(1, int(round((s1 - s0) / step)))
    out, i = [], 0
    for k in range(n + 1):
        s = s0 + (s1 - s0) * k / n
        while i < len(S) - 2 and S[i + 1] < s:
            i += 1
        t = (s - S[i]) / max(S[i + 1] - S[i], 1e-9)
        tg = (P[i + 1] - P[i]).normalized()
        nn = tr[i][1].lerp(tr[i + 1][1], t).normalized()
        out.append((P[i].lerp(P[i + 1], t), nn, tg, tg.cross(nn).normalized(), s / S[-1]))
    return out


def band(g, fr, w, z0, z1):
    """A bar inside a channel along frames fr: w(frame) wide, from z0(frame) to z1(frame)
    under the skin, its section changing along it."""
    vs = []
    for f in fr:
        q, n, _, sd, _ = f
        h, a, b = w(f) / 2, z0(f), z1(f)
        vs += [q - n * a - sd * h, q - n * a + sd * h, q - n * b + sd * h, q - n * b - sd * h]
    m = len(fr)
    faces = [(4 * i + j, 4 * i + (j + 1) % 4, 4 * i + 4 + (j + 1) % 4, 4 * i + 4 + j)
             for i in range(m - 1) for j in range(4)]
    faces += [(3, 2, 1, 0), tuple(4 * (m - 1) + j for j in range(4))]
    g.add(vs, faces)


def pebble(g, seat, a, b, h, seg=40, up=(0, 0, 1)):
    """orrin.pebble() on a seat (point, normal) taken before the cuts: a low oval bead a
    wide, b high, h proud."""
    loc, n = seat
    t1 = V3(up).cross(n).normalized()
    t2 = n.cross(t1)
    rings = [(1.0, -0.003), (1.0, 0.0), (0.95, h * 0.42), (0.80, h * 0.76), (0.52, h * 0.95),
             (0.2, h)]
    o = len(g.v)
    for r, z in rings:
        g.v += [loc + n * z + t1 * (a * r * cos(2 * pi * k / seg))
                + t2 * (b * r * sin(2 * pi * k / seg)) for k in range(seg)]
    for i in range(len(rings) - 1):
        g.f += [(o + i * seg + k, o + i * seg + (k + 1) % seg, o + (i + 1) * seg + (k + 1) % seg,
                 o + (i + 1) * seg + k) for k in range(seg)]
    g.f.append(tuple(o + (len(rings) - 1) * seg + k for k in range(seg)))


def build_lights():
    """The ribbon: in each channel under its flush lens a light guide, its lit face as wide
    as the lens right under it over a frosted sleeve; the tail's face cut into cells. The
    pebbles stay lit beads: on each pole over the lens, on each flank on its flap."""
    for key, lit, lens, cell in (("front", "led_front", "lens_clear", 0.0),
                                 ("mid", "led_front", "lens_clear", 0.0),
                                 ("mid_r", "led_front", "lens_clear", 0.0),
                                 ("rear", "led_rear", "lens_red", 0.022)):
        tr = LAMP[key]
        if len(tr) < 2:
            continue
        ln = sum((b[0] - a[0]).length for a, b in zip(tr, tr[1:]))
        fr = along(tr, 0.003, ln - 0.003, 0.008)

        def w(f):
            return width_at(f[4], ln)
        L = K.Lamp("lamp." + key, lit=lit, glass=lens)
        # the lens: flush with the skin, the body's gap on both sides (a lens cut from the
        # skin itself keeps the boolean's slivers, and its reflections zigzag)
        band(L.glass, fr, lambda f: w(f) - 2 * GAP, lambda f: 0.0, lambda f: 0.003)
        face = (lambda f: w(f) - 2 * GAP - 0.0005, lambda f: 0.0032,
                lambda f: 0.0032 + w(f) * 0.18)
        if not cell:
            band(L.emit(), fr, *face)
        else:                           # cells, the dark channel between them
            s0, rib = 0.003, 0.0022
            while s0 < ln - 0.003 - rib:
                s1 = min(s0 + cell - rib, ln - 0.003)
                band(L.emit(), along(tr, s0, s1, 0.008), *face)
                s0 = s1 + rib
        band(L.optic, fr, lambda f: w(f) * 0.70, lambda f: 0.0032 + w(f) * 0.18,
             lambda f: RIB_D - 0.003)
        L.obj()
    g = Geo()
    pebble(g, LAMP["peb.front"], 0.066, 0.043, 0.011)
    g.obj("led.front", "led_front", sharp=50)
    g = Geo()
    pebble(g, LAMP["peb.rear"], 0.066, 0.043, 0.011)
    g.obj("led.rear", "led_rear", sharp=50)
    # the flank pebbles, where white turns red, each on its flap: the left one the charge port
    g = Geo()
    for seat in LAMP["peb.flank"]:
        pebble(g, seat, 0.050, 0.031, 0.011)
    g.obj("led.flank", "led_flank", sharp=50)


def build_details():
    P = PT
    # ---- the hinge of the leaf: a hairline over the glass on the hinge ring, two knuckles
    g = Geo()
    half = [P["RA"][k] for k in "ESKGC"][1:]
    half = [P["RA"]["E"].lerp(P["RA"]["K"], 0.08)] + half[1:]
    strip(g, both(half), 0.007, lift=0.0014, n=10)
    g.obj("glass.hinge", "gloss_black", sharp=50)
    g = Geo()
    for sgn in (1, -1):
        c = P["RA"]["C"].lerp(P["RA"]["G"], 0.62)
        orrin.pebble(g, (c.x, sgn * c.y, c.z), 0.036, 0.015, 0.008, up=(0, 1, 0))
    g.obj("hinge", "wheel_vane", sharp=50)
    # ---- where it breathes: dot fields under both poles
    g = Geo()
    dot_field(g, 'x', 0.0, 0.468, 0.115, 0.030)
    dot_field(g, 'X', 0.0, 0.518, 0.115, 0.030)
    for sgn in (1, -1):                     # and a small lens on each rear paw, over the motors
        dot_field(g, 'z', -0.80, sgn * 0.705, 0.085, 0.030, pitch=0.011, rmax=0.0038)
    g.obj("dots", "void")
    # ---- lettering: one small word each
    g = Geo()
    for side in (1, -1):
        text_proj(g, "pebble", 0.030, 0.0, 0.335, 'y' if side > 0 else 'Y', spacing=1.3)
    text_proj(g, "orrin", 0.026, 0.0, 0.452, 'X', spacing=1.4)
    g.obj("lettering", "decal")
    # ---- camera pods on the front paws, sensors round both ends
    g = Geo()
    gl = Geo()
    for sgn in (1, -1):
        loc, n = snap((0.60, sgn * 0.80, 0.76))
        fwd = V3((1, 0, 0.10)).normalized()
        xf = (Matrix.Translation(loc + n * 0.004)
              @ V3((0, 1, 0)).rotation_difference(fwd).to_matrix().to_4x4())
        prof = [(-0.075 * cos(rad(a)), 0.021 * sin(rad(a)) ** 0.8 + 0.0005)
                for a in range(0, 181, 12)]
        g.lathe(prof, 24, xf=xf)
        gl.lathe([(-0.076, 0.001), (-0.076, 0.009), (-0.072, 0.011), (-0.072, 0.001)], 16,
                 xf=xf)
    g.obj("cameras", "paint", sharp=40)
    gl.obj("camera.lens", "gloss_black")
    g = Geo()
    for y, z, proj in ((0.26, 0.50, 'x'), (-0.26, 0.50, 'x'), (0.26, 0.552, 'X'),
                       (-0.26, 0.552, 'X')):
        loc, n = on_body(y, z, proj)
        if loc is not None:
            stud(g, loc, n, [(-0.002, 0.001), (-0.002, 0.009), (0.0012, 0.009),
                             (0.0012, 0.001)], 14)
    g.obj("sensors", "gloss_black")


# ---------------------------------------------------------------------------------------
# interior: a liner under the dome (nose deck, tub, luggage shelf), two seats of stones
# ---------------------------------------------------------------------------------------
def build_interior():
    # the liner: rows of (x, floor height); None follows the glass edge (a deck under it)
    rows = [(1.385, None, .006), (1.31, None, .012), (1.16, None, .03), (FA_X, None, .045),
            (0.64, .80, 0),
            (0.56, .80, 0), (0.53, .225, 0), (0.30, .225, 0), (0.0, .225, 0), (-0.30, .225, 0),
            (-0.52, .225, 0), (-0.555, .735, 0), (-0.70, .74, 0), (RA_X, None, .12),
            (-1.16, None, .045), (-1.31, None, .012), (-1.385, None, .006)]
    S, rims = [], []
    for x, zf, drop in rows:
        rm = orrin.rim_at(x, pt=PT, order=ORDER, line="U", at=0.4, push=None, depth=0.018)
        rims.append(rm)
        zf = rm.z - drop if zf is None else zf
        deep = rm.z - zf > 0.2
        S.append([tuple(rm), (rm.x, rm.y * 0.95, zf + (rm.z - zf) * 0.45),
                  (rm.x, rm.y * (0.80 if deep else 0.86), zf), (rm.x, 0.0, zf)])
    hold = {4: 0.5, 5: 0.75, 6: 0.75, 10: 0.75, 11: 0.75, 12: 0.4}
    K.build_body(S, lambda i, j: "liner", dict(liner="interior"), 0.0,
                 lambda i, j: hold.get(i, 0.0), name="liner", project=False, subdiv=3)
    # ---- a hair of light under the glass, round both tongues of the dome
    g = Geo()
    sec = [(-0.0025, -0.002), (0.0025, -0.002), (0.0025, 0.002), (-0.0025, 0.002)]
    for part in (rims[:4], rims[:-5:-1]):
        half = [V3((p.x, p.y - 0.012, p.z - 0.004)) for p in part[::-1]]
        tip = part[0]
        half.append(V3((tip.x + (0.004 if tip.x > 0 else -0.004), 0, tip.z - 0.006)))
        g.sweep(spline(both(half), 8), sec, up=(0, 0, 1))
    a, b = V3((rims[2].x, 0, rims[2].z - 0.03)), V3((rims[3].x, 0, rims[3].z - 0.045))
    up = (b - a).normalized()
    text_flat(g, "orrin", 0.036, a.lerp(b, 0.42) + V3((0, 0, 0.022)), (0, 1, 0), up,
              spacing=1.5)
    g.obj("led.cabin", "led_accent")
    # ---- two seats, each three stones on a foot
    g, gi = Geo(), Geo()
    back = Matrix.Rotation(rad(-15), 3, 'Y')
    for y in (0.345, -0.345):
        stone(g, (-0.07, y, 0.415), (0.255, 0.265, 0.085), Matrix.Rotation(rad(-6), 3, 'Y'),
              n=3.0)
        stone(g, (-0.375, y, 0.76), (0.075, 0.245, 0.30), back, n=3.0)
        stone(g, (-0.455, y, 1.105), (0.050, 0.115, 0.078), back, n=2.6)
        stone(gi, (-0.10, y, 0.285), (0.19, 0.20, 0.07), n=3.0)
    g.obj("interior.seats", "seat", sharp=60)
    # ---- dash: one long stone, a screen let into it, a yoke
    stone(gi, (0.615, 0, 0.815), (0.085, 0.60, 0.042), Matrix.Rotation(rad(12), 3, 'Y'), n=3.2)
    stone(gi, (-0.02, 0, 0.30), (0.26, 0.055, 0.085), n=3.0)             # the tunnel between
    yoke = (Matrix.Translation((0.47, 0.345, 0.80)) @ Matrix.Rotation(rad(-66), 4, 'Y')
            @ Matrix.Rotation(pi / 2, 4, 'X'))
    gi.lathe([(-0.010, 0.140), (0.0, 0.150), (0.010, 0.140), (0.0, 0.130)], 28, xf=yoke)
    gi.tube((0.50, 0.345, 0.79), (0.60, 0.345, 0.81), 0.018)
    gi.obj("interior.fittings", "interior", sharp=60)
    g = Geo()
    stone(g, (0.535, 0, 0.822), (0.012, 0.50, 0.024), Matrix.Rotation(rad(12), 3, 'Y'), n=4)
    g.obj("interior.screen", "screen", sharp=60)
    # ---- the luggage shelf behind the seats: a case and a soft bag, strapped, and a rail
    g, gs = Geo(), Geo()
    stone(g, (-0.86, 0.17, 0.865), (0.20, 0.235, 0.115), Matrix.Rotation(rad(4), 3, 'Z'), n=5)
    for dx in (-0.09, 0.09):
        stone(gs, (-0.86 + dx, 0.17, 0.865), (0.014, 0.239, 0.119),
              Matrix.Rotation(rad(4), 3, 'Z'), n=5)
    g.obj("luggage.case", "luggage", sharp=60)
    g = Geo()
    stone(g, (-0.83, -0.24, 0.835), (0.16, 0.15, 0.09), Matrix.Rotation(rad(-12), 3, 'Z'), n=2.3)
    g.obj("luggage.bag", "luggage2", sharp=60)
    stone(gs, (-0.83, -0.24, 0.84), (0.012, 0.153, 0.092), Matrix.Rotation(rad(-12), 3, 'Z'),
          n=2.3)
    gs.obj("luggage.straps", "interior", sharp=60)
    g = Geo()
    rail = [(-0.60, y, 0.775 + 0.035 * (1 - (y / 0.56) ** 2)) for y in
            (-0.56, -0.42, -0.2, 0, 0.2, 0.42, 0.56)]
    g.sweep(spline(rail, 6), [(0.007 * cos(rad(a)), 0.007 * sin(rad(a)))
                              for a in range(0, 360, 45)], up=(0, 0, 1))
    g.obj("luggage.rail", "wheel_vane", sharp=60)


# ---------------------------------------------------------------------------------------
# views of its own, and the build
# ---------------------------------------------------------------------------------------
K.VIEWS["hero"].update(dir=(1.0, 1.1, 0.30), focus=(0.9, 0.8, 0.5))
K.VIEWS.update(
    # the leaf lifted (render_view below turns it about its hinge for this view alone)
    open=dict(dir=(1.0, 1.35, 0.20), lens=70, target=(0.2, 0, 1.08), dist=8.4),
    nose=dict(dir=(1.0, 0.4, 0.4), lens=85, target=(1.2, 0.1, 0.55), dist=2.2),
    tail=dict(dir=(-1.0, -0.5, 0.45), lens=85, target=(-1.0, -0.1, 0.8), dist=2.6),
    wheel=dict(dir=(0.45, 1.0, 0.10), lens=85, target=(FA_X, 0.7, 0.36), dist=2.0),
    cabin=dict(dir=(0.3, 1.0, 0.75), lens=85, target=(-0.1, 0.1, 0.8), dist=3.4),
    flank=dict(dir=(0.1, 1.0, 0.15), lens=85, target=(-0.1, 0.8, 0.55), dist=2.0),
)


LEAF_UP = 34.0                      # degrees the leaf lifts in the "open" view
_render_view = K.render_view


def render_view(name, path, res, samples, margin=None):
    """The kit's render_view; for the view "open" the leaf is lifted about its hinge."""
    leaf = bpy.data.objects.get("body.glass") if name == "open" else None
    if leaf is not None:
        h, _ = snap(PT["RA"]["C"])
        leaf.matrix_world = (Matrix.Translation(h) @ Matrix.Rotation(rad(-LEAF_UP), 4, 'Y')
                             @ Matrix.Translation(-h))
    _render_view(name, path, res, samples, margin)
    if leaf is not None:
        leaf.matrix_world = Matrix.Identity(4)


K.render_view = render_view


def main():
    K.materials(paint=(0.105, 0.030, 0.205), paint_finish=(0.72, 0.36, 0.7), dust_amount=0.10,
                glass=(0.56, 0.54, 0.58), led_front=(0.90, 0.95, 1.0),
                led_rear=(1.0, 0.035, 0.03), led_accent=(1.0, 0.56, 0.16),
                led_wheel=(1.0, 0.56, 0.16), seat=(0.50, 0.42, 0.31),
                interior=(0.034, 0.030, 0.036), screen=(1.0, 0.62, 0.25))
    K.pbr("wheel_face", (0.19, 0.195, 0.20), 1.0, 0.30)
    K.pbr("wheel_vane", (0.24, 0.245, 0.25), 1.0, 0.26)
    K.emit("led_rear", (1.0, 0.004, 0.002), 7.0)        # deeper than the kit's: a real red
    K.emit("led_flank", (1.0, 0.36, 0.04), 10.0)
    # the dome's glass with a coating: the kit's glass mirrors the studio all over a dome
    K.pbr("glass_dome", (0.56, 0.54, 0.58), 0.0, 0.0,
          **{"Transmission Weight": 1.0, "IOR": 1.14})
    K.pbr("luggage", (0.36, 0.17, 0.05), 0.0, 0.55)
    K.pbr("luggage2", (0.16, 0.19, 0.17), 0.0, 0.75)
    build_hull()
    K.log("hull")
    if PROBE:
        probe()
        K.shoot()
        return
    build_lights()
    build_details()
    build_interior()
    K.log("details")
    for side, s in ((1, "l"), (-1, "r")):     # turbine discs (vehicles/brands/orrin.py)
        for tag, cx in (("f" + s, FA_X), ("r" + s, RA_X)):
            orrin.disc(tag, cx, OUT, side, vanes=44, R=R, W=W, rim=RIM, r_in=0.108,
                       hub=(0.094, 0.066, 0.035), sweep=34, cap=(0.024, 0.032),
                       size=orrin.DISC_SMALL, tread=orrin.NARROW)
    K.log("wheels")
    K.shoot(extra=dict(view="open", size=(900, 560), corner="tl"))


main()
