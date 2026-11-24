"""Caldera Strand: an electric multiple-unit car for elevated and underground city lines,
with a whole interior to walk through (maker Caldera Transit Works, operator Skein Metro:
every name made up), built on vehicles/carkit.py.

Run (always through the wrapper, one Blender job at a time on this machine):
    vehicles/blender.sh vehicles/trains/caldera_strand.py --out DIR --preview
    vehicles/blender.sh vehicles/trains/caldera_strand.py --out DIR --sheet
    ... --views aisle,vestibule,bay,cab,gangway --res 1920 1080 --samples 96
    CYBERGEN_VARIANT=mid ... --preview      the middle car (a gangway at both ends)
    CYBERGEN_SHUT=1 ...                     every door shut in every view

Frame: x forward along the track, y left, z up, meters, the origin on the rail top under
the car's middle. The body is 20.0 m over its ends and 3.0 m wide, its underframe at
z = 0.85, the passenger floor at z = 1.15, three double plug doors a side at x = -6.667,
0 and +6.667 (each 1.4 m wide). The end car has a cab and a nose at +x and a gangway at
-x; the middle car a gangway at both ends.

How it is built:
  * the outer skin is one build_body tube of thirteen lines (a tumblehome section, creased
    at the cant rail, the glazing band, the stripe band and the sole bar), open at both
    ends; the nose's face is a second piece, a sheet whose outline is the tube's front ring;
  * the glazing band is glass from end to end (the kit's frit borders); behind it stand
    slabs with the window openings, black outside and lined inside, so the wall has its
    real thickness and nothing shows the skin's back;
  * the door leaves are panels of the tube, joined with their inner linings into one
    object a leaf (door.<l|r><1|2|3>.<a|b>), slid open on the left in some views;
  * the interior (interior.*), the cab (cab.*), the bogies (bogie.<f|r>.*, an object an
    axle) and the track (track.*, in the studio's collection) are plain solids.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import bmesh                                                        # noqa: E402
import bpy                                                          # noqa: E402
import carkit as K                                                  # noqa: E402
from carkit import Geo, Matrix, V3, atan2, cos, hypot, pi, rad, sin  # noqa: E402

MID = os.environ.get("CYBERGEN_VARIANT", "").lower() == "mid"
SHUT = bool(os.environ.get("CYBERGEN_SHUT"))

# ---------------------------------------------------------------------------------------
# dimensions
# ---------------------------------------------------------------------------------------
XE = 10.0                           # half the body's length over its ends
Z_UF, Z_FLOOR = 0.85, 1.15          # underframe bottom, passenger floor
DOORS = (-6.667, 0.0, 6.667)        # door middles
DHW = 0.70                          # half a doorway
ZC, ZK, ZH, ZG, ZV, ZW, ZS = 3.98, 3.62, 3.22, 2.02, 1.90, 1.78, 1.12
#   roof crown, cant rail, glazing band top (door top), its foot, stripe band top and foot,
#   sole bar (the door leaves' foot)
X_CAB = 7.60                        # the cab's back wall (its saloon face)
X_P1 = 8.75                         # where the nose leaves the constant section
WALL = 0.075                        # skin to lining
Y_IN = 1.40                         # the lining's face below the windows
Z_CEIL = 3.50                       # the ceiling over the aisle
GD = 0.010                          # what stands behind the glass starts this far in
CAR_NO = "4107" if not MID else "4108"


def upper_y(z):
    """The skin's y on the leaning plane between the stripe band and the cant rail."""
    return 1.50 - (z - ZV) * (0.115 / (ZK - ZV))


def skin_y(z):
    """The skin's y at a height on the flank (the built section between the creases)."""
    if z >= ZV:
        return upper_y(z)
    if z >= ZW:
        return 1.50
    return 1.50 - (ZW - z) * (0.038 / (ZW - ZS))


LINES = "CQRKHGVWSFPOB"
#        C roof crown, Q, R roof, K cant rail, H glazing band top, G its foot, V stripe
#        band top, W its foot, S sole bar, F floor edge, P, O floor, B floor centerline
SEC = [(0.0, ZC), (0.62, 3.955), (1.14, 3.86), (1.385, ZK), (upper_y(ZH), ZH),
       (upper_y(ZG), ZG), (1.50, ZV), (1.50, ZW), (1.462, ZS), (1.445, Z_UF), (1.05, Z_UF),
       (0.55, Z_UF), (0.0, Z_UF)]
JK, JH, JG, JV, JW, JS, JF = 3, 4, 5, 6, 7, 8, 9


# ---------------------------------------------------------------------------------------
# small helpers
# ---------------------------------------------------------------------------------------
def lerp_pts(pts, t):
    """Piecewise linear through (t, value) pairs."""
    if t <= pts[0][0]:
        (a, va), (b, vb) = pts[0], pts[1]
    elif t >= pts[-1][0]:
        (a, va), (b, vb) = pts[-2], pts[-1]
    else:
        for (a, va), (b, vb) in zip(pts, pts[1:]):
            if a <= t <= b:
                break
    return va + (vb - va) * (t - a) / (b - a)


def rrect(u0, v0, u1, v1, r, n=5):
    """A rounded rectangle's outline, counterclockwise from the bottom edge."""
    out = []
    for cx, cy, a0 in ((u1 - r, v0 + r, -pi / 2), (u1 - r, v1 - r, 0.0), (u0 + r, v1 - r, pi / 2),
                       (u0 + r, v0 + r, pi)):
        for k in range(n + 1):
            a = a0 + (pi / 2) * k / n
            out.append((cx + r * cos(a), cy + r * sin(a)))
    return out


class Plate:
    """A rectangle (0..w by 0..h) with rounded rectangular holes, as cells: emit() lays it
    through a map f(u, v, d) as a slab d thick: its front, its back, the holes' reveals and
    its outer edge each into a Geo of their own (or none)."""

    def __init__(self, w, h, holes=(), n=5, ub=(), vb=()):
        self.w, self.h, self.n = w, h, n
        self.holes = [tuple(q) for q in holes]
        us = {0.0, w} | set(ub)
        vs = {0.0, h} | set(vb)
        for (u0, v0, u1, v1, r) in self.holes:
            us |= {u0, u0 + r, u1 - r, u1}
            vs |= {v0, v0 + r, v1 - r, v1}
        us = sorted(x for x in us if -1e-9 <= x <= w + 1e-9)
        vs = sorted(x for x in vs if -1e-9 <= x <= h + 1e-9)
        us = [x for k, x in enumerate(us) if k == 0 or x - us[k - 1] > 1e-7]
        vs = [x for k, x in enumerate(vs) if k == 0 or x - vs[k - 1] > 1e-7]
        self.cells = []
        for ua, ub_ in zip(us, us[1:]):
            for va, vb_ in zip(vs, vs[1:]):
                cu, cv = (ua + ub_) / 2, (va + vb_) / 2
                poly = [(ua, va), (ub_, va), (ub_, vb_), (ua, vb_)]
                for (u0, v0, u1, v1, r) in self.holes:
                    if not (u0 < cu < u1 and v0 < cv < v1):
                        continue
                    if u0 + r < cu < u1 - r or v0 + r < cv < v1 - r:
                        poly = None
                        break
                    ox = u0 if cu < u0 + r else u1          # the hole's corner
                    oy = v0 if cv < v0 + r else v1
                    ix = u0 + r if cu < u0 + r else u1 - r  # the arc's middle
                    iy = v0 + r if cv < v0 + r else v1 - r
                    a0 = atan2(oy - iy, 0.0)
                    a1 = atan2(0.0, ox - ix)
                    da = (a1 - a0 + pi) % (2 * pi) - pi
                    arc = [(ix + r * cos(a0 + da * k / n), iy + r * sin(a0 + da * k / n))
                           for k in range(n + 1)]
                    poly = [[(ox, oy), arc[k], arc[k + 1]] for k in range(n)]
                    break
                if poly is None:
                    continue
                self.cells += poly if isinstance(poly[0], list) else [poly]

    def emit(self, f, th, front=None, back=None, rev=None, edge=None):
        for g, d in ((front, 0.0), (back, th)):
            if g is None:
                continue
            idx, vs, fs = {}, [], []
            for poly in self.cells:
                face = []
                for (u, v) in poly:
                    key = (round(u, 6), round(v, 6))
                    if key not in idx:
                        idx[key] = len(vs)
                        vs.append(f(u, v, d))
                    face.append(idx[key])
                fs.append(tuple(face))
            g.add(vs, fs)
        if rev is not None:
            for (u0, v0, u1, v1, r) in self.holes:
                loop = rrect(u0, v0, u1, v1, r, self.n)
                m = len(loop)
                vs = [f(u, v, 0.0) for u, v in loop] + [f(u, v, th) for u, v in loop]
                rev.add(vs, [(k, (k + 1) % m, m + (k + 1) % m, m + k) for k in range(m)])
        if edge is not None:
            loop = [(0, 0), (self.w, 0), (self.w, self.h), (0, self.h)]
            vs = [f(u, v, 0.0) for u, v in loop] + [f(u, v, th) for u, v in loop]
            edge.add(vs, [(k, (k + 1) % 4, 4 + (k + 1) % 4, 4 + k) for k in range(4)])


def icon(g, strokes, o, u, v, s=1.0, th=0.0015):
    """A pictogram as flat solids on a plane (origin o, u to its right, v up, s its
    scale): lines (a, b, width), dots (center, radius), rings (center, radius, width[,
    from and to in degrees]) and polygons."""
    o, u, v = V3(o), V3(u).normalized(), V3(v).normalized()
    n = u.cross(v)

    count = [0]

    def solid(q):
        m = len(q)
        count[0] += 1
        t = th + count[0] * 0.00004
        g.add([o + u * (a * s) + v * (b * s) for a, b in q]
              + [o + u * (a * s) + v * (b * s) + n * t for a, b in q],
              [tuple(range(m)), tuple(range(m, 2 * m))]
              + [(k, (k + 1) % m, m + (k + 1) % m, m + k) for k in range(m)])
    for st in strokes:
        if st[0] == "line":
            (a, b, w) = st[1:]
            du, dv = b[0] - a[0], b[1] - a[1]
            ln = hypot(du, dv)
            nu, nv = -dv / ln * w / 2, du / ln * w / 2
            solid([(a[0] + nu, a[1] + nv), (b[0] + nu, b[1] + nv), (b[0] - nu, b[1] - nv),
                   (a[0] - nu, a[1] - nv)])
        elif st[0] == "dot":
            c, r = st[1:]
            solid([(c[0] + r * cos(2 * pi * k / 14), c[1] + r * sin(2 * pi * k / 14))
                   for k in range(14)])
        elif st[0] == "ring":
            c, r, w = st[1:4]
            a0, a1 = (rad(st[4]), rad(st[5])) if len(st) > 4 else (0.0, 2 * pi)
            m = max(6, int(abs(a1 - a0) / rad(15)))
            for k in range(m):
                b0, b1 = a0 + (a1 - a0) * k / m, a0 + (a1 - a0) * (k + 1) / m
                solid([(c[0] + q * cos(t), c[1] + q * sin(t))
                       for q, t in ((r - w / 2, b0), (r + w / 2, b0), (r + w / 2, b1),
                                    (r - w / 2, b1))])
        else:
            solid(list(st[1]))


WHEELCHAIR = [("ring", (0.0, -0.07), 0.15, 0.035, 100, 380), ("dot", (-0.07, 0.25), 0.045),
              ("line", (-0.07, 0.19), (-0.05, 0.02), 0.045), ("line", (-0.05, 0.03), (0.10, 0.03), 0.04),
              ("line", (0.10, 0.03), (0.16, -0.13), 0.04), ("line", (0.16, -0.13), (0.23, -0.13), 0.035),
              ("line", (-0.06, 0.12), (0.06, 0.12), 0.03)]


_TXT = {}


def text_mesh(txt, size, spacing=1.0, align=None, res=2):
    """The kit's lettering with coarser curves (a third of the triangles), kept per word."""
    key = (txt, round(size, 5), spacing, align)
    if key not in _TXT:
        K.text_mesh("I", 0.01)                  # the kit loads its font
        cu = bpy.data.curves.new("txt", 'FONT')
        cu.body = txt
        cu.size = size
        cu.space_character = spacing
        cu.resolution_u = res
        cu.align_x = 'CENTER'
        cu.align_y = 'BOTTOM_BASELINE' if align == "baseline" else 'CENTER'
        if K._FONT[0]:
            cu.font = K._FONT[0]
        ob = bpy.data.objects.new("txt", cu)
        K.SCN.collection.objects.link(ob)
        me = K.evaluated_mesh(ob)
        _TXT[key] = ([v.co.copy() for v in me.vertices], [tuple(q.vertices) for q in me.polygons])
        bpy.data.objects.remove(ob)
        bpy.data.meshes.remove(me)
        bpy.data.curves.remove(cu)
    return _TXT[key]


def text_flat(g, txt, size, origin, right, up, spacing=1.0, align=None):
    """Lettering on a plane: its middle at origin, reading along right."""
    vs, fs = text_mesh(txt, size, spacing, align)
    o, r, u = V3(origin), V3(right), V3(up)
    g.add([o + r * q.x + u * q.y for q in vs], fs)


def flank(x, z, sy=1, out=0.0):
    """A point on the skin's flank (out off it)."""
    return V3((x, sy * (skin_y(z) + out), z))


def flank_text(g, txt, size, x, z, sy, lift=0.0012, **kw):
    """Lettering on the flank, read from outside, its middle at (x, z)."""
    vs, fs = text_mesh(txt, size, **kw)
    g.add([flank(x - sy * q.x, z + q.y, sy, lift) for q in vs], fs)


def flank_plate(g, x0, x1, z0, z1, sy, lift=0.004, sink=0.002):
    g.hexa([flank(x, z, sy, d) for d in (-sink, lift) for x, z in ((x0, z0), (x1, z0), (x1, z1),
                                                                    (x0, z1))])


def frame(o, u, v):
    """A plate's map on a plane: origin o, u and v its axes, d against u x v."""
    o, u, v = V3(o), V3(u).normalized(), V3(v).normalized()
    n = u.cross(v).normalized()
    return lambda a, b, d: o + u * a + v * b - n * d


def wall_map(x0, z0, side=1, off=0.0):
    """A plate's map on the flank: u runs back from x0 (toward -x), v up from z0, d into
    the car from the skin (plus off); side -1 is the right flank."""
    return lambda a, b, d: V3((x0 - a, side * (skin_y(z0 + b) - off - d), z0 + b))


def join(name, objs, sharp=30.0):
    """One mesh object from several, modifiers applied, a material slot each: the objects
    themselves are removed."""
    bpy.context.view_layer.update()
    dg = bpy.context.evaluated_depsgraph_get()
    mats, vs, fs, mi, smooth = [], [], [], [], []
    for ob in objs:
        ev = ob.evaluated_get(dg)
        me = ev.to_mesh()
        mw = ob.matrix_world
        slot = []
        for m in me.materials:
            m = m.original if m is not None else None
            if m not in mats:
                mats.append(m)
            slot.append(mats.index(m))
        o = len(vs)
        vs += [tuple(mw @ v.co) for v in me.vertices]
        for p in me.polygons:
            fs.append(tuple(o + i for i in p.vertices))
            mi.append(slot[p.material_index] if slot else 0)
            smooth.append(p.use_smooth)
        ev.to_mesh_clear()
    for ob in objs:
        old = ob.data
        if ob in K.BODY:
            K.BODY.remove(ob)
        bpy.data.objects.remove(ob)
        if old.users == 0:
            bpy.data.meshes.remove(old)
    me = bpy.data.meshes.new(name)
    me.from_pydata(vs, [], fs)
    for m in mats:
        me.materials.append(m)
    me.polygons.foreach_set("material_index", mi)
    me.polygons.foreach_set("use_smooth", smooth)
    me.update()
    if sharp is not None:
        me.set_sharp_from_angle(angle=rad(sharp))
    ob = bpy.data.objects.new(name, me)
    K.CAR.objects.link(ob)
    return ob


def split_side(ob, name_l, name_r):
    """A mirrored panel as two objects, the left and the right half."""
    new = ob.copy()
    new.data = ob.data.copy()
    K.CAR.objects.link(new)
    ob.name, new.name = name_l, name_r
    for o, keep in ((ob, 1.0), (new, -1.0)):
        bm = bmesh.new()
        bm.from_mesh(o.data)
        bmesh.ops.delete(bm, geom=[f for f in bm.faces if f.calc_center_median().y * keep < 0],
                         context='FACES')
        bm.to_mesh(o.data)
        bm.free()
    return ob, new


# ---------------------------------------------------------------------------------------
# the skin: a tube of thirteen lines, and the nose's face
# ---------------------------------------------------------------------------------------
FACE_PROFILE = [(0.87, 9.62), (ZS, 9.74), (ZW, 10.0), (ZV, 10.0), (ZG, 9.94), (3.66, 9.36),
                (3.80, 9.31)]


def face_x(y, z):
    """The nose's face: raked back above the beak, undercut below, a little bowed in plan."""
    return lerp_pts(FACE_PROFILE, z) - 0.12 * y * y


# the face's outline (the tube's front ring), (y, z) by line
N0_YZ = [(0.0, 3.66), (0.32, 3.655), (0.62, 3.63), (0.80, 3.54), (0.86, ZH), (0.93, ZG),
         (0.94, ZV), (0.94, ZW), (0.90, ZS), (0.86, 0.88), (0.58, 0.87), (0.29, 0.87),
         (0.0, 0.87)]
# the ring where the flank's long facet turns into the face
N1 = [(9.18, 0.0, 3.82), (9.175, 0.46, 3.81), (9.16, 0.84, 3.75), (9.20, 1.07, 3.57),
      (9.36, 1.125, ZH), (9.78, 1.215, ZG), (9.845, 1.225, ZV), (9.845, 1.225, ZW),
      (9.59, 1.185, ZS), (9.48, 1.14, 0.86), (9.50, 0.80, Z_UF), (9.52, 0.42, Z_UF),
      (9.53, 0.0, Z_UF)]
N0 = [(face_x(y, z), y, z) for y, z in N0_YZ]
BODY = {}
TAGS = []                           # the tube's intervals by name, front to rear
XS = []                             # its stations' x (None in the nose)


def ring(x):
    return [(x, y, z) for y, z in SEC]


def tube_stations():
    st, tags, xs = [], [], []

    def add(x, tag=None):
        st.append(ring(x))
        xs.append(x)
        if tag:
            tags.append(tag)

    if MID:
        add(XE, "post")
        add(XE - 0.25, "front")
    else:
        st.extend([N0, N1])
        xs.extend([None, None])
        tags.extend(["nose1", "nose2"])
        add(X_P1, "cab")
    for k in (3, 2, 1):
        c = DOORS[k - 1]
        add(c + DHW, "d%da" % k)
        add(c, "d%db" % k)
        add(c - DHW, ("bay2", "bay1", "rear")[3 - k])
    add(-XE + 0.25, "post")
    add(-XE)
    return st, tags, xs


def tube_panel(i, j):
    tag = TAGS[i]
    if j >= JF:
        return "floor"
    if j == JS:
        return "skirt"
    if tag.startswith("nose"):
        return ("brow", "brow", "brow", "mask", "visor", "subsill", "nband", "prow")[j]
    if j <= 2:
        return "roof"
    if j == JK:
        return "cant"
    if tag[0] == "d":
        return ("g" if j == JH else "p") + tag[1:]
    if tag == "post":
        return "cant" if j == JH else ("subsill", "stripe", "lower")[j - JG] if j < JS \
            else "lower"
    return ("ribbon", "subsill", "stripe", "lower")[j - JH]


def tube_line_crease(i, j):
    tag = TAGS[i]
    if tag == "nose1":
        return 1.0 if j in (JH, JG, JV, JW, JS) else 0.0
    if j in (JH, JG, JV, JW, JS, JF):
        return 1.0
    return 0.5 if j == JK else 0.0


def tube_station_crease(i, j):
    x = XS[i]
    if x is None:
        return 0.35 if i == 1 else 0.0
    if not MID and abs(x - X_P1) < 1e-6:
        return 0.45
    if any(abs(abs(x - c) - DHW) < 1e-6 or abs(x - c) < 1e-6 for c in DOORS):
        return 1.0 if JH <= j < JF else 0.0
    if abs(abs(x) - (XE - 0.25)) < 1e-6:
        return 1.0 if j == JH else 0.0
    return 0.0


FACE_COLS = (0.0, 0.34, 0.68)       # shares of the face's half width
FACE_ROWS = (None, ZH, ZG, ZV, ZW, ZS, None)


def face_stations():
    """The face as rows (top to bottom) of points from the centerline out to its edge."""
    top = [N0[0], N0[1], N0[2], N0[3]]
    bot = [N0[12], N0[11], N0[10], N0[9]]
    rows = [top]
    for r, j in ((1, JH), (2, JG), (3, JV), (4, JW), (5, JS)):
        e = N0[j]
        rows.append([(face_x(e[1] * s, e[2]), e[1] * s, e[2]) for s in FACE_COLS] + [e])
    rows.append(bot)
    return rows


def face_panel(i, j):
    return ("fmask", "screen", "fsill", "fband", "fprow", "valance")[i]


def build_skin():
    st, tags, xs = tube_stations()
    TAGS[:] = tags
    XS[:] = xs
    pmat = dict(roof="paint_dark", cant="paint", ribbon="glass", frit="frit",
                subsill="blackglass", stripe="paint2", lower="paint", skirt="skirt",
                floor="underbody", brow="paint_dark", mask="blackglass", nband="blackglass",
                prow="paint2", visor="glass")
    glass = [("ribbon", 0.055, "frit", "frit")]
    for k in (1, 2, 3):
        for s in "ab":
            pmat["g%d%s" % (k, s)] = "glass"
            pmat["f%d%s" % (k, s)] = "frit"
            pmat["p%d%s" % (k, s)] = "paint_dark"
            glass.append(("g%d%s" % (k, s), 0.07, "f%d%s" % (k, s), "frit"))
    body = K.build_body(st, tube_panel, pmat, tube_line_crease, tube_station_crease,
                        name="body", front=None, rear=None, glass=glass, subdiv=3,
                        gap=0.0015)
    BODY["tube"] = body
    if MID:
        return body
    face = K.build_body(face_stations(), face_panel,
                        dict(fmask="blackglass", screen="glass",
                             fsill="blackglass", fband="blackglass", fprow="paint2",
                             valance="skirt"),
                        line_crease=0.0,
                        station_crease=lambda i, j: 1.0 if 1 <= i <= 5 else 0.0,
                        name="face", front=None, rear=None, subdiv=3, gap=0.0015)
    for ob in face.parts.values():          # the sheet's faces look forward
        me = ob.data
        if sum((p.normal.x * p.area for p in me.polygons)) < 0:
            me.flip_normals()
    BODY["face"] = face
    return body


# ---------------------------------------------------------------------------------------
# the saloon's envelope: what stands behind the glazing band, the lining, floor, ceiling
# ---------------------------------------------------------------------------------------
XA = -XE + 0.08                     # the rear end wall's saloon face
XB = XE - 0.08 if MID else X_CAB    # the front one: an end wall, or the cab's back wall
BAND_Z0, BAND_H = 1.98, 1.30        # the slabs behind the glazing band
WIN_V = (0.12, 1.16)                # a window's opening in them (z 2.10 to 3.14)
WIN_W, PILLAR, PIER = 1.449, 0.30, 0.16
Z_LINTEL = 3.20                     # the doorways' clear top
SEGS = []                           # the wall's stretches: (front x, rear x, windows)


def gbox(g, x0, x1, y0, y1, z0, z1, **kw):
    g.box(((x0 + x1) / 2, (y0 + y1) / 2, (z0 + z1) / 2),
          (abs(x1 - x0), abs(y1 - y0), abs(z1 - z0)), **kw)


def wall_segments():
    """The stretches of wall between the doorways and the ends, each with its windows as
    (u0, u1) measured back from its front end."""
    three = [(PILLAR + k * (WIN_W + PIER), PILLAR + k * (WIN_W + PIER) + WIN_W) for k in range(3)]
    end_len = DOORS[0] - DHW - XA
    segs = []
    if MID:
        segs.append((XB, DOORS[2] + DHW, [(end_len - PILLAR - WIN_W, end_len - PILLAR)]))
    else:
        segs.append((XB, DOORS[2] + DHW, []))
    segs.append((DOORS[2] - DHW, DOORS[1] + DHW, three))
    segs.append((DOORS[1] - DHW, DOORS[0] + DHW, three))
    segs.append((DOORS[0] - DHW, XA, [(PILLAR, PILLAR + WIN_W)]))
    SEGS[:] = segs


def lining_y(z):
    """The lining's face at a height: upright below the windows, with the skin above."""
    return Y_IN if z < 2.0 else upper_y(z) - GD - WALL


def build_envelope():
    wall_segments()
    g_blk, g_in, g_rev, g_low, g_dado, g_kick = Geo(), Geo(), Geo(), Geo(), Geo(), Geo()
    for sy in (1, -1):
        for (x1, x0, wins) in SEGS:
            holes = [(a, WIN_V[0], b, WIN_V[1], 0.08) for a, b in wins]
            pl = Plate(x1 - x0, BAND_H, holes)
            pl.emit(wall_map(x1, BAND_Z0, sy, off=GD), WALL, front=g_blk, back=g_in, rev=g_rev,
                    edge=g_in)
            gbox(g_low, x0, x1, sy * Y_IN, sy * (Y_IN + 0.055), Z_FLOOR - 0.02, 2.0)
            gbox(g_dado, x0, x1, sy * (Y_IN - 0.012), sy * (Y_IN + 0.05), 1.975, 2.012)
            gbox(g_kick, x0, x1, sy * (Y_IN - 0.006), sy * (Y_IN + 0.02), Z_FLOOR, Z_FLOOR + 0.11)
    g_blk.obj("interior.band.back", "blackplastic")
    g_in.obj("interior.wall.band", "lining")
    g_rev.obj("interior.window.reveals", "trim_in", sharp=40)
    g_low.obj("interior.wall.lower", "lining_low")
    g_dado.obj("interior.wall.dado", "paint2", bevel=0.004)
    g_kick.obj("interior.wall.kick", "steel", bevel=0.003)

    # window gaskets: a rubber lip round each opening, on the lining
    g = Geo()
    for sy in (1, -1):
        for (x1, x0, wins) in SEGS:
            f = wall_map(x1, BAND_Z0, sy, off=GD + WALL)
            for a, b in wins:
                path = [f(u, v, 0.0) for u, v in rrect(a, WIN_V[0], b, WIN_V[1], 0.08)]
                g.sweep(path, [(-0.012, -0.004), (0.016, -0.004), (0.016, 0.006), (-0.012, 0.006)],
                        up=(0, -sy, 0), closed=True)
    g.obj("interior.window.gaskets", "seal", sharp=40)

    # the floor, with the doorways' sills out to the skin
    g, gs, gy, gt = Geo(), Geo(), Geo(), Geo()
    gbox(g, XA - 0.03, XB + (0.03 if MID else 0.06), -Y_IN - 0.02, Y_IN + 0.02, Z_FLOOR - 0.06,
         Z_FLOOR)
    for c in DOORS:
        for sy in (1, -1):
            gbox(gs, c - DHW, c + DHW, sy * 1.26, sy * 1.445, 1.00, Z_FLOOR + 0.003)
            gbox(gy, c - DHW, c + DHW, sy * 1.17, sy * 1.26, Z_FLOOR - 0.01, Z_FLOOR + 0.002)
            for k in range(6):                      # tactile ribs across the sill
                y = 1.285 + 0.024 * k
                gbox(gt, c - DHW + 0.03, c + DHW - 0.03, sy * (y - 0.006), sy * (y + 0.006),
                     Z_FLOOR, Z_FLOOR + 0.0065)
    g.obj("interior.floor", "floor_in")
    gs.obj("interior.sills", "tread", bevel=0.002)
    gy.obj("interior.doorzone", "yellow")
    gt.obj("interior.sill.ribs", "tread", bevel=0.0015)

    # the ceiling over the aisle, the coves down to the walls, the lintels over the doorways
    g, gc, gl, gv, gn = Geo(), Geo(), Geo(), Geo(), Geo()
    gbox(g, XA - 0.02, XB + 0.02, -0.80, 0.80, Z_CEIL, Z_CEIL + 0.05)
    cove = [(0.78, Z_CEIL), (0.96, 3.418), (1.15, 3.318), (1.326, Z_LINTEL), (1.39, Z_LINTEL),
            (1.365, 3.42), (0.78, Z_CEIL + 0.06)]
    for sy in (1, -1):
        gc.prism([(XA - 0.02, sy * y, z) for y, z in cove], (XB - XA + 0.04, 0, 0))
        gbox(gl, XA + 0.02, XB - 0.02, sy * 0.575, sy * 0.665, Z_CEIL - 0.004, Z_CEIL + 0.01)
        gbox(gv, XA + 0.02, XB - 0.02, sy * 0.715, sy * 0.745, Z_CEIL - 0.001, Z_CEIL + 0.01)
        for c in DOORS:
            gbox(gn, c - DHW - 0.01, c + DHW + 0.01, sy * 1.30, sy * 1.39, Z_LINTEL, 3.30)
    g.obj("interior.ceiling", "ceil")
    gc.obj("interior.cove", "ceil")
    gl.obj("interior.lights", "light")
    gv.obj("interior.vents", "void")
    gn.obj("interior.lintels", "lining")


def end_outline(x_end, pull=0.004):
    """The skin's section at an end of the tube as built: (y, z) round the car."""
    pts = []
    for ob in BODY["tube"].parts.values():
        for v in ob.data.vertices:
            if abs(v.co.x - x_end) < 0.004:
                pts.append((v.co.y, v.co.z))
    cz = 2.4
    pts.sort(key=lambda p: atan2(p[1] - cz, p[0]))
    out = []
    for p in pts:
        if not out or hypot(p[0] - out[-1][0], p[1] - out[-1][1]) > 0.004:
            out.append(p)
    res = []
    for (y, z) in out:
        d = hypot(y, z - cz)
        res.append((y * (1 - pull / d), cz + (z - cz) * (1 - pull / d)))
    return res


GW_HW, GW_TOP = 0.60, Z_LINTEL      # the gangway's passage: 1.2 m wide, 2.05 m high


def build_end(sg):
    """An end with a gangway: sg -1 the rear end, +1 the front end of a middle car."""
    tag = "rear" if sg < 0 else "front"
    xin = sg * (XE - 0.08)              # the wall's saloon face
    xout = sg * (XE - 0.03)             # its outer face, a little inside the skin's end
    # a wall across the whole section with the passage: lined inside, painted outside
    ga, gb, gr, ge = bulkhead(xin, xout, rrect(-GW_HW, 1.10, GW_HW, GW_TOP, 0.05), pull=0.006)
    ga.obj("interior.endwall." + tag, "lining")
    gb.obj("body.endwall." + tag, "paint_dark")
    gr.obj("interior.gangway.reveal." + tag, "trim_in", sharp=40)
    # outside: the car's number, two reflectors
    gt, gx = Geo(), Geo()
    text_flat(gt, CAR_NO, 0.10, (xout + sg * 0.0015, sg * 1.02, 3.05), (0, sg, 0), (0, 0, 1), spacing=1.08)
    for sy in (1, -1):
        gx.cyl((xout, sy * 1.18, 1.75), 0.008, 0.045, 20, axis=(sg, 0, 0))
    gt.obj("lettering.end." + tag, "sign_white")
    gx.obj("reflectors." + tag, "sign_red", sharp=40)
    # the bellows: folds round the passage out to half the gap between two cars
    g = Geo()
    nf, depth = 10, 0.47
    rings = []
    for k in range(nf + 1):
        a = 0.055 if k % 2 else 0.0
        o = rrect(-GW_HW - 0.13 - a, 1.00 - a, GW_HW + 0.13 + a, GW_TOP + 0.13 + a, 0.16 + a, 6)
        rings.append([(xout + sg * depth * k / nf, y, z) for y, z in o])
    m = len(rings[0])
    vs = [p for r in rings for p in r]
    fs = [(k * m + j, k * m + (j + 1) % m, (k + 1) * m + (j + 1) % m, (k + 1) * m + j)
          for k in range(nf) for j in range(m)]
    g.add(vs, fs)
    ob = g.obj("gangway.bellows." + tag, "bellows")
    md = ob.modifiers.new("solid", 'SOLIDIFY')
    md.thickness = 0.006
    ob.data.shade_smooth()
    ob.data.set_sharp_from_angle(angle=rad(50))
    g, gp, gt = Geo(), Geo(), Geo()
    xe = xout + sg * depth
    o1 = rrect(-GW_HW - 0.20, 0.94, GW_HW + 0.20, GW_TOP + 0.20, 0.20, 6)
    o2 = rrect(-GW_HW - 0.10, 1.03, GW_HW + 0.10, GW_TOP + 0.10, 0.13, 6)
    for xa, xb in ((xe, xe + sg * 0.03), (xout - sg * 0.004, xout + sg * 0.025)):
        m = len(o1)
        vs = ([(xa, y, z) for y, z in o1] + [(xb, y, z) for y, z in o1]
              + [(xa, y, z) for y, z in o2] + [(xb, y, z) for y, z in o2])
        fs = []
        for j in range(m):
            j2 = (j + 1) % m
            fs += [(j, j2, m + j2, m + j), (2 * m + j, 2 * m + j2, 3 * m + j2, 3 * m + j),
                   (j, j2, 2 * m + j2, 2 * m + j), (m + j, m + j2, 3 * m + j2, 3 * m + j)]
        g.add(vs, fs)
    g.obj("gangway.frame." + tag, "skirt", sharp=40)
    # the floor plates across the gap, treads on them, a hinged flap at the wall
    gbox(gp, xin - sg * 0.02, xe + sg * 0.03, -GW_HW - 0.02, GW_HW + 0.02, Z_FLOOR - 0.035,
         Z_FLOOR)
    for k in range(9):
        x = xin + sg * (0.06 + k * 0.06)
        gbox(gt, x - 0.012, x + 0.012, -GW_HW + 0.05, GW_HW - 0.05, Z_FLOOR, Z_FLOOR + 0.004)
    gp.obj("gangway.floor." + tag, "tread", bevel=0.003)
    gt.obj("gangway.floor.ribs." + tag, "tread")
    # grab handles each side of the passage, on the saloon's wall
    g = Geo()
    for sy in (1, -1):
        y = sy * (GW_HW + 0.14)
        x = xin - sg * 0.055
        g.pipe([(xin, y, 2.05), (x, y, 2.05), (x, y, 2.75), (xin, y, 2.75)], 0.015, 10)
        for z in (2.05, 2.75):
            g.cyl((xin - sg * 0.006, y, z), 0.012, 0.03, 12, axis='x')
    g.obj("interior.gangway.handles." + tag, "steel", sharp=40)


# ---------------------------------------------------------------------------------------
# the doors: a leaf is its panels of the skin and its lining, one object
# ---------------------------------------------------------------------------------------
LEAVES = {}
LEAF_Z0 = 1.16                      # the lining's foot, clear of the sill
OPEN_VIEWS = ("hero", "side", "door", "doorway")
SLIDE, PLUG = 0.705, 0.055


def leaf_parts(k, s, x1, x0, sy):
    """The inside of one leaf (front edge x1, rear edge x0) on side sy, and what it wears
    outside: its lining with the window, a kick plate, the seal at its meeting edge, a
    light strip along that edge, the button on the b leaf."""
    c = DOORS[k - 1]
    w = x1 - x0 - 0.024
    f = wall_map(x1 - 0.012, LEAF_Z0, sy, off=0.012)
    pl = Plate(w, Z_LINTEL - 0.004 - LEAF_Z0, [(0.066, 2.10 - LEAF_Z0, w - 0.066, 3.14 - LEAF_Z0, 0.09)],
               vb=(ZV - LEAF_Z0, ZW - LEAF_Z0))
    gf, gb, gr, ge = Geo(), Geo(), Geo(), Geo()
    pl.emit(f, 0.036, front=gf, back=gb, rev=gr, edge=ge)
    out = [gf.obj("t", "blackplastic"), gb.obj("t", "doorlining"),
           gr.obj("t", "seal", sharp=40), ge.obj("t", "seal")]
    g = Geo()                                   # the kick plate
    g.hexa([f(u, v, d) for d in (0.036, 0.039) for u, v in ((0.02, 0.02), (w - 0.02, 0.02),
                                                             (w - 0.02, 0.30), (0.02, 0.30))])
    out.append(g.obj("t", "steel"))
    g = Geo()                                   # a pull bar across the lining
    za = 1.86 - LEAF_Z0
    p = [f(0.10, za, 0.036), f(0.10, za, 0.066), f(w - 0.10, za, 0.066), f(w - 0.10, za, 0.036)]
    g.pipe(p, 0.011, 8)
    out.append(g.obj("t", "steel", sharp=40))
    # outside: the light strip on the meeting edge, lit green while the doors are released
    um = (w - 0.030) if s == "a" else 0.030     # the meeting edge is the a leaf's rear edge
    fo = wall_map(x1 - 0.012, LEAF_Z0, sy, off=0.0)
    g = Geo()
    g.hexa([fo(um + du, v, d) for d in (0.001, -0.0025)
            for du, v in ((-0.007, 2.14 - LEAF_Z0), (0.007, 2.14 - LEAF_Z0),
                          (0.007, 3.10 - LEAF_Z0), (-0.007, 3.10 - LEAF_Z0))])
    out.append(g.obj("t", "led_door"))
    g = Geo()                                   # and the same edge inside
    g.hexa([f(um + du, v, d) for d in (0.034, 0.0385)
            for du, v in ((-0.006, 2.14 - LEAF_Z0), (0.006, 2.14 - LEAF_Z0),
                          (0.006, 3.10 - LEAF_Z0), (-0.006, 3.10 - LEAF_Z0))])
    out.append(g.obj("t", "led_door"))
    if s == "b":                                # the button outside, under the glass
        loc = V3((c - 0.12, sy * skin_y(1.955), 1.955))
        n = V3((0, sy, 0))
        g, gl = Geo(), Geo()
        K.stud(g, loc, n, [(-0.002, 0.001), (-0.002, 0.036), (0.006, 0.036), (0.009, 0.031),
                           (0.009, 0.001)], 24)
        K.stud(gl, loc, n, [(0.008, 0.001), (0.008, 0.020), (0.0115, 0.018), (0.0115, 0.001)], 20)
        out += [g.obj("t", "steel", sharp=40), gl.obj("t", "led_door")]
    return out


def build_doors():
    body = BODY["tube"]
    for k in (1, 2, 3):
        c = DOORS[k - 1]
        for s, (x1, x0) in (("a", (c + DHW, c)), ("b", (c, c - DHW))):
            halves = [split_side(body.parts.pop("%s%d%s" % (kind, k, s)), "t.l", "t.r")
                      for kind in "gfp"]
            for side, sy, i in (("l", 1, 0), ("r", -1, 1)):
                objs = [h[i] for h in halves] + leaf_parts(k, s, x1, x0, sy)
                LEAVES["%s%d%s" % (side, k, s)] = join("door.%s%d.%s" % (side, k, s), objs)
    K.body_bvh()
    if SHUT:
        return
    for k in (1, 2, 3):                         # the left side's doors stand open in some views
        for s, sg in (("a", 1), ("b", -1)):
            grp = K.Group("rig.door.l%d.%s" % (k, s), [LEAVES["l%d%s" % (k, s)]])
            grp.pose_for(OPEN_VIEWS, loc=(sg * SLIDE, PLUG, 0))


# ---------------------------------------------------------------------------------------
# seating: shells on a beam along the wall, a facing bay, tip-up seats, a wheelchair bay
# ---------------------------------------------------------------------------------------
SP = 0.469                          # a seat's pitch along a bench
SEAT_D = 0.468                      # how far a seat reaches from the wall
SCR = 0.25                          # a draught screen stands this far from its doorway
POLE_Y = 0.95                       # the poles at the screens and the bench fronts
RAIL_Z = 3.05                       # the grab rails, 1.90 m over the floor
SHELL = [(-0.050, 0.880), (-0.066, 0.720), (-0.092, 0.560), (-0.112, 0.470), (-0.150, 0.432),
         (-0.300, 0.430), (-0.420, 0.448), (-0.458, 0.444), (-0.468, 0.425), (-0.455, 0.408),
         (-0.300, 0.402), (-0.160, 0.402), (-0.110, 0.425), (-0.070, 0.500), (-0.040, 0.720),
         (-0.022, 0.870), (-0.030, 0.892), (-0.044, 0.893)]
PAD_SEAT = [(-0.165, 0.436), (-0.300, 0.434), (-0.415, 0.452), (-0.418, 0.470), (-0.300, 0.455),
            (-0.165, 0.455)]
PAD_BACK = [(-0.070, 0.800), (-0.080, 0.720), (-0.104, 0.565), (-0.122, 0.560), (-0.099, 0.720),
            (-0.088, 0.805)]
PAD_BAND = [(-0.064, 0.846), (-0.069, 0.814), (-0.088, 0.818), (-0.082, 0.850)]
PROTO = {}
COUNT = {"seats": 0, "tipups": 0, "loops": 0}
SEATED = []                         # every seat placed: (kind, x, y)


def seat_proto(kind):
    """One seat as a mesh shared by all of its kind: 'std', 'prio' (a priority seat's
    cloth), 'high' (a facing bay's taller back)."""
    if kind in PROTO:
        return PROTO[kind]
    k = 1.14 if kind == "high" else 1.0

    def tall(poly):                 # a taller back: what is above the seat stretched
        return [(y, z if z < 0.48 else 0.48 + (z - 0.48) * k) for y, z in poly]
    g, gp, gb = Geo(), Geo(), Geo()
    g.prism([(-0.2225, y, z) for y, z in tall(SHELL)], (0.445, 0, 0))
    gp.prism([(-0.19, y, z) for y, z in PAD_SEAT], (0.38, 0, 0))
    gp.prism([(-0.19, y, z) for y, z in tall(PAD_BACK)], (0.38, 0, 0))
    gb.prism([(-0.19, y, z) for y, z in tall(PAD_BAND)], (0.38, 0, 0))
    objs = [g.obj("t", "shell", bevel=0.007, segs=2),
            gp.obj("t", "fabric_p" if kind == "prio" else "fabric", bevel=0.005, segs=2),
            gb.obj("t", "yellow" if kind == "prio" else "paint2", bevel=0.003)]
    ob = join("interior.seat.proto." + kind, objs)
    PROTO[kind] = ob.data
    bpy.data.objects.remove(ob)
    return PROTO[kind]


def place(me, name, loc, rz=0.0):
    ob = bpy.data.objects.new(name, me)
    K.CAR.objects.link(ob)
    ob.location = loc
    ob.rotation_euler = (0, 0, rz)
    return ob


def seat(kind, x, y, face):
    """A seat whose back stands at (x, y), facing 'l' (-y... toward the aisle from the left
    wall), 'r', 'f' (+x) or 'b' (-x)."""
    COUNT["seats"] += 1
    rz = {"l": 0.0, "r": pi, "f": pi / 2, "b": -pi / 2}[face]
    SEATED.append((kind, x, y))
    return place(seat_proto(kind), "interior.seat.%02d" % COUNT["seats"], (x, y, Z_FLOOR), rz)


def bench(x0, n, sy, g_beam, g_base, g_glow, prio=0, prio_end=1):
    """n seats along the wall from x0 forward on side sy; prio of them at one end are
    priority seats. Their beam, the heater box under it, its light."""
    for k in range(n):
        kind = "prio" if (k < prio if prio_end < 0 else k >= n - prio) else "std"
        seat(kind, x0 + (k + 0.5) * SP, sy * Y_IN, "l" if sy > 0 else "r")
    x1 = x0 + n * SP
    gbox(g_beam, x0 + 0.01, x1 - 0.01, sy * Y_IN, sy * (Y_IN - 0.36), Z_FLOOR + 0.33, Z_FLOOR + 0.40)
    gbox(g_base, x0 + 0.01, x1 - 0.01, sy * Y_IN, sy * (Y_IN - 0.15), Z_FLOOR, Z_FLOOR + 0.33)
    gbox(g_glow, x0 + 0.04, x1 - 0.04, sy * (Y_IN - 0.335), sy * (Y_IN - 0.35), Z_FLOOR + 0.318,
         Z_FLOOR + 0.331)


def build_seating():
    g_beam, g_base, g_glow = Geo(), Geo(), Geo()
    gs, gg, gp, gt = Geo(), Geo(), Geo(), Geo()       # screens: panels, glass, poles, top rails
    g_rail, g_col = Geo(), Geo()
    runs = []                                         # (x0, x1, sy): where a grab rail runs
    d1, d2, d3 = DOORS

    def screen(x, sy):
        gbox(gs, x - 0.016, x + 0.016, sy * Y_IN, sy * (POLE_Y + 0.01), Z_FLOOR, Z_FLOOR + 0.92)
        gbox(gg, x - 0.005, x + 0.005, sy * (Y_IN - 0.02), sy * (POLE_Y + 0.012), Z_FLOOR + 0.94,
             Z_FLOOR + 1.84)
        gp.cyl((x, sy * POLE_Y, Z_FLOOR), Z_CEIL - Z_FLOOR - 0.085, 0.017, 16)
        gt.tube((x, sy * POLE_Y, Z_FLOOR + 1.86), (x, sy * (lining_y(3.01) - 0.002), Z_FLOOR + 1.86),
                0.012, 10)
        gt.tube((x, sy * POLE_Y, Z_FLOOR + 0.93), (x, sy * Y_IN, Z_FLOOR + 0.93), 0.012, 10)
        for z in (Z_FLOOR + 0.012, Z_FLOOR + 0.93, Z_FLOOR + 1.86, RAIL_Z):
            g_col.cyl((x, sy * POLE_Y, z - 0.012), 0.024, 0.023, 16)

    def stanchion(x, sy):
        gp.cyl((x, sy * POLE_Y, Z_FLOOR), RAIL_Z - Z_FLOOR, 0.017, 16)
        g_col.cyl((x, sy * POLE_Y, Z_FLOOR), 0.02, 0.026, 16)

    # the stretches between the screens, front to rear, each side
    spans = []
    if MID:
        spans.append((d3 + DHW + SCR, XB - 0.34, "end"))
    spans += [(d2 + DHW + SCR, d3 - DHW - SCR, "bay2"), (d1 + DHW + SCR, d2 - DHW - SCR, "bay1"),
              (XA + 0.34, d1 - DHW - SCR, "end")]
    for (x0, x1, kind) in spans:
        for sy in (1, -1):
            for x in (x0, x1):
                if abs(x - (XA + 0.34)) > 1e-6 and abs(x - (XB - 0.34)) > 1e-6:
                    screen(x, sy)
            a = x0 + 0.036 if abs(x0 - (XA + 0.34)) > 1e-6 else x0 + 0.02
            if kind == "end":
                n = 4
                a = (x0 + 0.02) if x0 < 0 else (x1 - 0.036 - n * SP)
                bench(a, n, sy, g_beam, g_base, g_glow)
            elif (kind == "bay1" and sy < 0) or (kind == "bay2" and sy > 0):
                # ten along the wall, the three by the middle doorway priority seats
                bench(a, 10, sy, g_beam, g_base, g_glow, prio=3, prio_end=1 if kind == "bay1" else -1)
                stanchion(a + 3 * SP, sy)
                stanchion(a + 7 * SP, sy)
            elif kind == "bay1":
                # three, a bay of two pairs facing each other, three
                bench(a, 3, sy, g_beam, g_base, g_glow)
                bench(a + 7 * SP, 3, sy, g_beam, g_base, g_glow)
                xb0, xb1 = a + 3 * SP + 0.085, a + 7 * SP - 0.085
                for xb, face, sg in ((xb0, "f", 1), (xb1, "b", -1)):
                    for q in (0, 1):
                        seat("high", xb, sy * (Y_IN - 0.235 - q * SP), face)
                    gbox(g_base, xb + sg * 0.09, xb + sg * 0.34, sy * Y_IN, sy * (Y_IN - 0.86),
                         Z_FLOOR, Z_FLOOR + 0.40)
                    gbox(g_base, xb - sg * 0.004, xb - sg * 0.03, sy * Y_IN, sy * (Y_IN - 0.93),
                         Z_FLOOR + 0.05, Z_FLOOR + 1.02)
                    # a grab handle on the aisle corner of the pair's back
                    ya = sy * (Y_IN - 0.95)
                    g_rail.pipe([(xb + sg * 0.012, ya + sy * 0.10, Z_FLOOR + 1.02),
                                 (xb + sg * 0.012, ya + sy * 0.10, Z_FLOOR + 1.11),
                                 (xb + sg * 0.012, ya - sy * 0.005, Z_FLOOR + 1.11),
                                 (xb + sg * 0.012, ya - sy * 0.005, Z_FLOOR + 0.92)], 0.013, 10)
            else:
                build_access_bay(a, sy, g_beam, g_base, g_glow, g_rail)
            runs.append((x0 if abs(x0 - (XA + 0.34)) > 1e-6 else x0 - 0.02,
                         x1 if abs(x1 - (XB - 0.34)) > 1e-6 else x1 + 0.02, sy))
    g_beam.obj("interior.seat.beams", "lining_low", bevel=0.006)
    g_base.obj("interior.seat.bases", "trim_in", bevel=0.004)
    g_glow.obj("interior.seat.glow", "accent")
    gs.obj("interior.screen.panels", "lining", bevel=0.005)
    ob = gg.obj("interior.screen.glass", "glass_in", bevel=0.002)
    gt.obj("interior.screen.rails", "steel", sharp=40)

    # grab rails over the bench fronts, hung from the coves, hand loops along them
    g_hang = Geo()
    loop = loop_proto()
    for (x0, x1, sy) in runs:
        y = sy * POLE_Y
        g_rail.tube((x0, y, RAIL_Z), (x1, y, RAIL_Z), 0.016, 14)
        n = max(1, int((x1 - x0) / 1.6))
        for k in range(n):
            x = x0 + (x1 - x0) * (k + 0.5) / n
            g_hang.tube((x, y, RAIL_Z), (x, y, 3.43), 0.011, 10)
            g_col.cyl((x, y, 3.405), 0.02, 0.03, 12)
        m = int((x1 - x0 - 0.5) / SP)
        for k in range(m):
            COUNT["loops"] += 1
            place(loop, "interior.loop.%02d" % COUNT["loops"],
                  (x0 + (x1 - x0 - (m - 1) * SP) / 2 + k * SP, y, RAIL_Z))
    # the poles in the doorways' middles (not in the middle one: a wheelchair turns there):
    # each opens into three between hand and head height
    for c in (d1, d3):
        gp.cyl((c, 0, Z_FLOOR), 0.93, 0.02, 16)
        gp.cyl((c, 0, Z_FLOOR + 1.87), Z_CEIL - Z_FLOOR - 1.87, 0.02, 16)
        for k in range(3):
            a = 2 * pi * k / 3 + pi / 2
            ex, ey = 0.115 * cos(a), 0.115 * sin(a)
            g_rail.pipe([(c, 0, Z_FLOOR + 0.93), (c + ex * 0.6, ey * 0.6, Z_FLOOR + 1.00),
                         (c + ex, ey, Z_FLOOR + 1.12), (c + ex, ey, Z_FLOOR + 1.68),
                         (c + ex * 0.6, ey * 0.6, Z_FLOOR + 1.80), (c, 0, Z_FLOOR + 1.87)], 0.016, 12)
        for z in (Z_FLOOR, Z_FLOOR + 0.905, Z_FLOOR + 1.845, Z_CEIL - 0.03):
            g_col.cyl((c, 0, z), 0.05 if z in (Z_FLOOR, Z_CEIL - 0.03) else 0.03, 0.036, 20)
    # over the middle doorway two short rails high up instead, 2.05 m over the floor
    for sy in (1, -1):
        y = sy * 0.70
        g_rail.tube((d2 - 0.45, y, 3.216), (d2 + 0.45, y, 3.216), 0.016, 14)
        for x in (d2 - 0.40, d2 + 0.40):
            g_hang.tube((x, y, 3.216), (x, y, Z_CEIL), 0.011, 10)
    gp.obj("interior.poles", "steel", sharp=40)
    g_rail.obj("interior.rails", "steel", sharp=40)
    g_hang.obj("interior.rail.hangers", "steel", sharp=40)
    g_col.obj("interior.pole.collars", "paint2", sharp=40)


def loop_proto():
    """A hand loop: a strap round the rail and a ring under it."""
    g, gr = Geo(), Geo()
    g.ring((0, 0, 0), 'x', 0.021, sec=(0.032, 0.004), n=16)
    gbox(g, -0.016, 0.016, -0.003, 0.003, -0.115, -0.018)
    gr.ring((0, 0, -0.165), 'y', 0.048, r=0.009, n=20, m=8)
    ob = join("interior.loop.proto", [g.obj("t", "strap"), gr.obj("t", "shell", sharp=40)])
    me = ob.data
    bpy.data.objects.remove(ob)
    return me


def build_access_bay(a, sy, g_beam, g_base, g_glow, g_rail):
    """The right side's front bay: a wheelchair space by the middle doorway (a backrest to
    lean on, a belt, a rail along the wall), three tip-up seats where bikes and luggage
    stand, then three seats."""
    w = sy * Y_IN
    # the wheelchair space: 1.45 m from the screen
    xr = a + 1.45                                   # the backrest's face
    g, gpad, gbelt, gx = Geo(), Geo(), Geo(), Geo()
    gbox(g, xr + 0.03, xr + 0.07, w, w - sy * 0.46, Z_FLOOR, Z_FLOOR + 1.38)
    gbox(gpad, xr, xr + 0.035, w - sy * 0.05, w - sy * 0.43, Z_FLOOR + 0.52, Z_FLOOR + 1.30)
    g_rail.pipe([(a + 0.10, w, Z_FLOOR + 0.86), (a + 0.10, w - sy * 0.07, Z_FLOOR + 0.86),
                 (xr - 0.12, w - sy * 0.07, Z_FLOOR + 0.86), (xr - 0.12, w, Z_FLOOR + 0.86)], 0.016, 12)
    gbox(gx, xr - 0.075, xr - 0.005, w - sy * 0.01, w - sy * 0.075, Z_FLOOR + 0.60, Z_FLOOR + 0.70)
    gbox(gbelt, xr - 0.06, xr - 0.02, w - sy * 0.075, w - sy * 0.081, Z_FLOOR + 0.20, Z_FLOOR + 0.62)
    gbox(gx, xr - 0.07, xr - 0.01, w - sy * 0.07, w - sy * 0.095, Z_FLOOR + 0.13, Z_FLOOR + 0.21)
    g.obj("interior.wheelchair.post", "lining", bevel=0.006)
    gpad.obj("interior.wheelchair.backrest", "fabric_p", bevel=0.012, segs=3)
    gbelt.obj("interior.wheelchair.belt", "strap")
    gx.obj("interior.wheelchair.reel", "blackplastic", bevel=0.004)
    # the floor's marks: the wheelchair's field, the bike and luggage zone
    gm, gw = Geo(), Geo()
    zc = Z_FLOOR + 0.0015
    cx, cy = a + 0.72, w - sy * 0.52
    gbox(gm, cx - 0.42, cx + 0.42, cy - 0.42, cy + 0.42, Z_FLOOR - 0.01, zc)
    icon(gw, WHEELCHAIR, (cx, cy, zc), (sy, 0, 0), (0, sy, 0), 1.9)
    gm.obj("interior.wheelchair.field", "sign_blue")
    gw.obj("interior.wheelchair.mark", "sign_white")
    # tip-up seats: pads on the wall, the seats folded up under them
    xt = xr + 0.16
    gs, gf, gh = Geo(), Geo(), Geo()
    for k in range(3):
        x = xt + (k + 0.5) * SP
        COUNT["tipups"] += 1
        gbox(gf, x - 0.19, x + 0.19, w - sy * 0.012, w - sy * 0.05, Z_FLOOR + 0.56, Z_FLOOR + 0.84)
        gbox(gs, x - 0.20, x + 0.20, w - sy * 0.055, w - sy * 0.105, Z_FLOOR + 0.10, Z_FLOOR + 0.52)
        gbox(gf, x - 0.17, x + 0.17, w - sy * 0.105, w - sy * 0.122, Z_FLOOR + 0.14, Z_FLOOR + 0.48)
        for dx in (-0.21, 0.21):
            gbox(gh, x + dx - 0.012, x + dx + 0.012, w, w - sy * 0.11, Z_FLOOR + 0.06, Z_FLOOR + 0.16)
    gs.obj("interior.tipup.seats", "shell", bevel=0.01, segs=2)
    gf.obj("interior.tipup.pads", "fabric", bevel=0.008, segs=2)
    gh.obj("interior.tipup.hinges", "steel", bevel=0.003)
    gz, gzt = Geo(), Geo()
    x0, x1 = xt + 0.02, xt + 3 * SP - 0.02
    y0, y1 = w - sy * 0.16, w - sy * 0.86
    for (xa, xb, ya, yb) in ((x0, x1, y0, y0 - sy * 0.035), (x0, x1, y1 + sy * 0.035, y1),
                             (x0, x0 + 0.035, y0, y1), (x1 - 0.035, x1, y0, y1)):
        gbox(gz, xa, xb, ya, yb, Z_FLOOR - 0.01, zc)
    text_flat(gzt, "BIKES  LUGGAGE", 0.085, ((x0 + x1) / 2, (y0 + y1) / 2, zc + 0.0005),
                (sy, 0, 0), (0, sy, 0), spacing=1.1)
    gz.obj("interior.zone.frame", "yellow")
    gzt.obj("interior.zone.text", "yellow")
    bench(xt + 3 * SP + 0.20, 3, sy, g_beam, g_base, g_glow)



# ---------------------------------------------------------------------------------------
# print and displays: boards, lettering, dot matrix, pictograms, each color one object
# ---------------------------------------------------------------------------------------
FONT = {
    "A": "0E11111F111111", "B": "1E11111E11111E", "C": "0E11101010110E", "D": "1E11111111111E",
    "E": "1F10101E10101F", "F": "1F10101E101010", "G": "0E11101711110F", "H": "1111111F111111",
    "I": "0E04040404040E", "J": "0702020202120C", "K": "11121418141211", "L": "1010101010101F",
    "M": "111B1515111111", "N": "11191513111111", "O": "0E11111111110E", "P": "1E11111E101010",
    "Q": "0E11111115120D", "R": "1E11111E141211", "S": "0F10100E01011E", "T": "1F040404040404",
    "U": "1111111111110E", "V": "11111111110A04", "W": "1111111515150A", "X": "11110A040A1111",
    "Y": "11110A04040404", "Z": "1F01020408101F", "0": "0E11131519110E", "1": "040C040404040E",
    "2": "0E11010204081F", "3": "1E01010E01011E", "4": "02060A121F0202", "5": "1F101E0101110E",
    "6": "0608101E11110E", "7": "1F010204080808", "8": "0E11110E11110E", "9": "0E11110F01020C",
    " ": "00000000000000", "-": "0000001F000000", ">": "10080402040810", ".": "00000000000C0C",
    ":": "000C0C000C0C00", "/": "01010204081010"}
LAY = {}                            # print by material, gathered into one object each
STATIONS = ["PORT VARO", "CINDER GATE", "MARROW STREET", "TALLOW YARD", "NINEFOLD", "GLASSWATER",
            "OLD FOUNDRY", "KILN ROW", "HOLLOW QUAY", "EMBERLINE", "VANTRY CROSS", "SALT TERRACE"]
NEXT = 8                            # the next stop: Hollow Quay


def lay(mat):
    return LAY.setdefault(mat, Geo())


def flush(prefix):
    """What was laid so far becomes objects, one a material."""
    for mat, g in LAY.items():
        g.obj(prefix + mat, mat, sharp=40)
    LAY.clear()


def dot_rows(txt):
    rows = [""] * 7
    for ch in txt:
        code = FONT[ch]
        for r in range(7):
            bits = int(code[2 * r:2 * r + 2], 16)
            rows[r] += "".join("#" if bits & (16 >> c) else "." for c in range(5)) + "."
    return [r[:-1] for r in rows]


def dots(g, txt, c, u, v, pitch, size):
    """Lit dots of a dot-matrix line, its middle at c, reading along u."""
    rows = dot_rows(txt)
    c, u, v = V3(c), V3(u).normalized(), V3(v).normalized()
    wd, h = len(rows[0]), 7
    for r, row in enumerate(rows):
        for k, x in enumerate(row):
            if x == "#":
                q = c + u * ((k - (wd - 1) / 2) * pitch) + v * (((h - 1) / 2 - r) * pitch)
                a, b = u * (size / 2), v * (size / 2)
                g.add([q - a - b, q + a - b, q + a + b, q - a + b], [(0, 1, 2, 3)])
    return wd * pitch


class Board:
    """A flat board: its middle c (on the surface it hangs on), u to its right, v up; it
    stands th off that surface, and print is laid on its face."""

    def __init__(self, c, u, v, w, h, th=0.012):
        self.u, self.v = V3(u).normalized(), V3(v).normalized()
        self.n = self.u.cross(self.v)
        self.c = V3(c) + self.n * (th / 2)
        self.w, self.h, self.th = w, h, th

    def at(self, a, b, lift=0.0):
        return self.c + self.u * a + self.v * b + self.n * (self.th / 2 + lift)

    def body(self, mat, grow=0.0):
        hw, hh = self.w / 2 + grow, self.h / 2 + grow
        q = ((-hw, -hh), (hw, -hh), (hw, hh), (-hw, hh))
        lay(mat).hexa([self.c + self.u * a + self.v * b + self.n * d
                       for d in (-self.th / 2, self.th / 2) for a, b in q])
        return self

    def field(self, mat, a0, b0, a1, b1, lift=0.0005):
        lay(mat).add([self.at(a0, b0, lift), self.at(a1, b0, lift), self.at(a1, b1, lift),
                      self.at(a0, b1, lift)], [(0, 1, 2, 3)])

    def text(self, mat, txt, size, a=0.0, b=0.0, lift=0.0011, turn=0.0, **kw):
        c, s_ = cos(rad(turn)), sin(rad(turn))
        text_flat(lay(mat), txt, size, self.at(a, b, lift), self.u * c + self.v * s_,
                    self.v * c - self.u * s_, **kw)

    def dots(self, mat, txt, a, b, pitch, size=None, lift=0.0011):
        return dots(lay(mat), txt, self.at(a, b, lift), self.u, self.v, pitch, size or pitch * 0.72)

    def icon(self, mat, strokes, a, b, s, lift=0.0008):
        icon(lay(mat), strokes, self.at(a, b, lift), self.u, self.v, s, 0.0008)


def wall_board(x, z, sy, w, h, th=0.012):
    """A board on the lining at (x, z) of side sy, read from the aisle."""
    if z >= 2.0:
        k = 0.115 / (ZK - ZV)
        v = V3((0, -sy * k, 1.0))
    else:
        v = V3((0, 0, 1))
    return Board((x, sy * lining_y(z), z), (sy, 0, 0), v, w, h, th)


def cove_board(x, sy, w, h=0.33, th=0.014):
    """A board on the cove over the windows and doorways, leaning down to the aisle."""
    return Board((x, sy * 1.14, 3.317), (sy, 0, 0), (0, -sy * 0.860, 0.510), w, h, th)


PERSON = [("dot", (0.0, 0.16), 0.035), ("line", (0.0, 0.11), (0.0, -0.03), 0.07),
          ("line", (-0.018, -0.03), (-0.022, -0.17), 0.03), ("line", (0.018, -0.03), (0.022, -0.17), 0.03)]
CANE = PERSON + [("line", (0.05, 0.05), (0.075, -0.17), 0.014)]
CROSS = [("line", (-0.1, 0.0), (0.1, 0.0), 0.06), ("line", (0.0, -0.1), (0.0, 0.1), 0.06)]
BOLT = [("poly", [(0.02, 0.14), (-0.06, -0.01), (-0.005, -0.01), (-0.03, -0.14), (0.06, 0.03),
                  (0.005, 0.03)])]
FLAME = [("poly", [(0.0, 0.15), (0.07, 0.02), (0.06, -0.08), (0.0, -0.13), (-0.06, -0.08),
                   (-0.07, 0.0), (-0.03, 0.05), (-0.02, 0.0)])]
CAMERA = [("poly", [(-0.11, -0.05), (0.05, -0.05), (0.05, 0.05), (-0.11, 0.05)]),
          ("poly", [(0.05, -0.01), (0.12, -0.05), (0.12, 0.05), (0.05, 0.01)])]
NOSMOKE = [("ring", (0.0, 0.0), 0.12, 0.025), ("line", (-0.085, 0.085), (0.085, -0.085), 0.025),
           ("line", (-0.07, -0.01), (0.05, -0.01), 0.03)]
STRANDS = [("line", (-0.12, 0.06 - 0.06 * k), (-0.04, 0.09 - 0.06 * k), 0.022) for k in range(3)] \
    + [("line", (-0.04, 0.09 - 0.06 * k), (0.04, 0.03 - 0.06 * k), 0.022) for k in range(3)] \
    + [("line", (0.04, 0.03 - 0.06 * k), (0.12, 0.06 - 0.06 * k), 0.022) for k in range(3)]
ADS = [("ad_red", "lit_warm", "NOVA NOODLE", "LEVEL 9  OPEN ALL NIGHT", ("ring", (0.0, 0.0), 0.10, 0.03)),
       ("ad_blue", "lit_white", "DROWSE", "SLEEP PODS BY THE HOUR", ("ring", (0.0, 0.0), 0.10, 0.03, 200, 420)),
       ("ad_yel", "sign_dark", "ORBIT COURIER", "ANY LEVEL IN 20 MINUTES", ("line", (-0.1, -0.08), (0.1, 0.08), 0.04)),
       ("ad_mag", "lit_white", "MIRA", "SYNTH EYEWEAR  SEE MORE", ("ring", (0.0, 0.0), 0.085, 0.05)),
       ("ad_teal", "lit_white", "TIDEWATER", "YOUR CREDIT UNBROKEN", ("line", (-0.1, 0.0), (0.1, 0.0), 0.05))]


def line_map(x, sy):
    """The line's map over a doorway: the stops as lamps on a bar, the next one green."""
    b = cove_board(x, sy, 1.34, 0.335).body("blackplastic")
    b.field("paint2", -0.67, 0.105, 0.67, 0.1675)
    b.text("sign_white", "7   EMBER LINE", 0.036, -0.46, 0.136, spacing=1.15)
    b.text("sign_white", "SKEIN METRO", 0.022, 0.52, 0.136, spacing=1.2)
    n = len(STATIONS)
    b.field("paint2", -0.60, -0.118, 0.60, -0.104)
    for k, name in enumerate(STATIONS):
        a = -0.60 + 1.20 * k / (n - 1)
        mat = "led_off" if k < NEXT else "led_door" if k == NEXT else "led_amber"
        b.icon("sign_white", [("ring", (0, 0), 0.016, 0.006)], a, -0.111, 1.0)
        b.icon(mat, [("dot", (0, 0), 0.0105)], a, -0.111, 1.0, lift=0.0012)
        b.text("sign_white" if k >= NEXT else "ink_grey", name, 0.0185, a + 0.012, -0.088, turn=38,
               align="baseline", spacing=1.08)
    b.icon("led_door", [("poly", [(-0.02, -0.012), (0.02, 0.0), (-0.02, 0.012)])],
           -0.60 + 1.20 * (NEXT - 0.5) / (n - 1), -0.142, 1.0)
    b.text("ink_grey", "NEXT STOP", 0.013, -0.60 + 1.20 * NEXT / (n - 1), -0.146, spacing=1.2)


def advert(x, sy, k, w=1.16):
    bg, ink, head, sub, mark = ADS[k % len(ADS)]
    b = cove_board(x, sy, w, 0.30).body("trim_in")
    b.field(bg, -w / 2 + 0.012, -0.138, w / 2 - 0.012, 0.138)
    b.text(ink, head, 0.105 if len(head) < 10 else 0.082, 0.09, 0.025, spacing=1.05)
    b.text(ink, sub, 0.031, 0.09, -0.085, spacing=1.15)
    b.icon(ink, [mark], -w / 2 + 0.13, 0.0, 0.8)


def build_print():
    d1, d2, d3 = DOORS
    # over every doorway the line's map, a warning lamp on the lintel; ads over the windows
    for sy in (1, -1):
        for c in DOORS:
            line_map(c, sy)
            lay("led_red").box((c, sy * 1.297, Z_LINTEL + 0.045), (0.16, 0.006, 0.03))
            lay("blackplastic").box((c, sy * 1.30, Z_LINTEL + 0.045), (0.20, 0.008, 0.05))
        k = 0 if sy > 0 else 2
        for (x1, x0, wins) in SEGS:
            for (a, b_) in wins:
                advert(x1 - (a + b_) / 2, sy, k)
                k += 1
    # the doorways' posts: buttons on the one ahead, the emergency release on the one behind
    for sy in (1, -1):
        for c in DOORS:
            xf = c + DHW + (0.115 if (not MID and c == d3) else 0.13)
            b = wall_board(xf, 2.34, sy, 0.085, 0.20, 0.022).body("blackplastic")
            for dz, mat in ((0.045, "led_door"), (-0.045, "led_blue")):
                K.stud(lay("steel"), b.at(0, dz), b.n, [(0.0, 0.001), (0.0, 0.03), (0.005, 0.03),
                                                         (0.007, 0.026), (0.007, 0.001)], 20)
                K.stud(lay(mat), b.at(0, dz), b.n, [(0.006, 0.001), (0.006, 0.019), (0.0095, 0.017),
                                                     (0.0095, 0.001)], 16)
            xr = c - DHW - 0.13
            b = wall_board(xr, 2.58, sy, 0.15, 0.25, 0.045).body("sign_red")
            b.field("blackplastic", -0.058, -0.055, 0.058, 0.105, lift=0.0004)
            lay("sign_red").tube(b.at(-0.035, 0.03, 0.012), b.at(0.035, 0.03, 0.012), 0.012, 10)
            lay("steel").tube(b.at(0.0, 0.03, 0.0), b.at(0.0, 0.03, 0.012), 0.008, 8)
            b.text("sign_white", "EMERGENCY", 0.017, 0.0, -0.078, spacing=1.1)
            b.text("sign_white", "DOOR RELEASE", 0.0125, 0.0, -0.103, spacing=1.1)
            b2 = wall_board(xr, 2.86, sy, 0.15, 0.17, 0.003).body("sign_white")
            b2.icon("sign_red", NOSMOKE, -0.035, 0.03, 0.22)
            b2.icon("sign_dark", CAMERA, 0.035, 0.03, 0.22)
            b2.text("sign_dark", "NO SMOKING  CCTV", 0.0105, 0.0, -0.025, spacing=1.1)
            b2.text("sign_dark", "CAR " + CAR_NO, 0.016, 0.0, -0.055, spacing=1.15)
    # priority seats: a sign on the wall over each group, between the windows
    for sy, x in ((-1, d2 - DHW - PILLAR - WIN_W - PIER / 2), (1, d2 + DHW + PILLAR + WIN_W + PIER / 2)):
        b = wall_board(x, 2.62, sy, 0.125, 0.36, 0.003).body("sign_blue")
        b.icon("sign_white", CANE, 0.0, 0.085, 0.42)
        b.text("sign_white", "PRIORITY", 0.0175, 0.0, -0.04, spacing=1.05)
        b.text("sign_white", "SEATS", 0.0175, 0.0, -0.066, spacing=1.05)
        b.text("sign_white", "PLEASE OFFER", 0.0098, 0.0, -0.105)
        b.text("sign_white", "THESE SEATS", 0.0098, 0.0, -0.122)
    # screens hung over the aisle in the middle of each bay, read from both ways
    for x in ((d1 + d2) / 2, (d2 + d3) / 2):
        lay("blackplastic").box((x, 0, Z_CEIL - 0.095), (0.06, 0.90, 0.19))
        for sg in (1, -1):
            b = Board((x - sg * 0.03, 0, Z_CEIL - 0.095), (0, -sg, 0), (0, 0, 1), 0.84, 0.17, 0.002)
            b.field("pis_bg", -0.42, -0.085, 0.42, 0.085)
            b.field("paint2", -0.40, -0.06, -0.28, 0.06, lift=0.0008)
            b.text("lit_white", "7", 0.085, -0.34, 0.0, lift=0.0014)
            b.text("lit_white", "NEXT", 0.026, -0.17, 0.048, spacing=1.2)
            b.text("lit_white", STATIONS[NEXT], 0.058, 0.07, -0.012, spacing=1.05)
            b.text("lit_amber", "23:41", 0.03, 0.33, 0.05, spacing=1.1)
            b.dots("lit_amber", "DOORS OPEN LEFT", 0.07, -0.062, 0.0052)
    # the ceiling: panel joints, speakers, camera domes
    nj = int((XB - XA) / 1.6)
    for k in range(1, nj):
        lay("void").box((XA + k * (XB - XA) / nj, 0, Z_CEIL), (0.004, 1.12, 0.002))
    for x in (-8.6, -5.0, -1.7, 1.7, 5.0) + ((8.6,) if MID else ()):
        lay("trim_in").cyl((x, 0, Z_CEIL - 0.004), 0.006, 0.085, 28)
        lay("steel").ring((x, 0, Z_CEIL - 0.004), 'z', 0.09, sec=(0.008, 0.008), n=28)
        for r_, m in ((0.02, 6), (0.042, 12), (0.064, 18)):
            for q in range(m):
                a = 2 * pi * q / m
                lay("void").cyl((x + r_ * cos(a), r_ * sin(a), Z_CEIL - 0.0055), 0.002, 0.006, 6)
    for x in (d1 + 0.95, d2 - 0.95, d2 + 0.95, d3 - 0.95):
        lay("steel").cyl((x, 0, Z_CEIL - 0.012), 0.014, 0.07, 24)
        prof = [(0.0, 0.0)] + [(-0.058 * sin(rad(a)), 0.058 * cos(rad(a))) for a in range(0, 91, 15)]
        lay("blackglass").lathe(prof, 20, axis='z', at=(x, 0, Z_CEIL - 0.012))
    # the help point by the wheelchair space: a speaker, a call button, a lamp
    b = wall_board(d2 + DHW + 0.13, 2.80, -1, 0.11, 0.20, 0.018).body("sign_yellowgreen")
    for r in range(4):
        for q in range(5):
            lay("void").cyl(b.at(-0.03 + 0.015 * q, 0.07 - 0.014 * r, -0.001), 0.002, 0.0045, 6,
                            axis=tuple(b.n))
    K.stud(lay("sign_red"), b.at(0.0, -0.03), b.n, [(0.0, 0.001), (0.0, 0.02), (0.008, 0.018),
                                                    (0.008, 0.001)], 16)
    b.text("sign_dark", "HELP POINT", 0.0125, 0.0, -0.072, spacing=1.05)
    K.stud(lay("led_door"), b.at(0.035, 0.085), b.n, [(0.0, 0.001), (0.0, 0.005), (0.003, 0.005),
                                                      (0.003, 0.001)], 10)
    build_lockers()
    flush("interior.print.")


def build_lockers():
    """At an end with a gangway: an equipment locker each side of the passage, the fire
    extinguisher on one, the car's number and a display over the passage."""
    for sg in ((-1, 1) if MID else (-1,)):
        tag = "rear" if sg < 0 else "front"
        xin = sg * (XE - 0.08)
        xf = xin - sg * 0.32                    # the lockers' fronts
        g = Geo()
        for sy in (1, -1):
            g.prism([(xin, sy * y, z) for y, z in ((0.95, Z_FLOOR), (Y_IN, Z_FLOOR), (Y_IN, 2.0),
                                                   (lining_y(3.2), 3.2), (1.15, 3.33), (0.95, 3.43))],
                    (xf - xin, 0, 0))
            # the front: two doors, locks, a vent, a label
            b = Board((xf, sy * 1.175, 2.25), (0, -sg, 0), (0, 0, 1), 0.45, 2.2, 0.0)
            for (a0, b0, a1, b1) in ((-0.20, -1.06, 0.20, -0.02), (-0.20, 0.02, 0.20, 0.86)):
                for q in ((a0, b0, a1, b0 + 0.004), (a0, b1 - 0.004, a1, b1), (a0, b0, a0 + 0.004, b1),
                          (a1 - 0.004, b0, a1, b1)):
                    b.field("void", *q, lift=0.0006)
            for bz in (-0.50, 0.44):
                K.stud(lay("steel"), b.at(-sy * sg * 0.165, bz), b.n,
                       [(0.0, 0.001), (0.0, 0.016), (0.004, 0.014), (0.004, 0.001)], 14)
            for q in range(6):
                b.field("void", -0.12, 0.68 + 0.022 * q, 0.12, 0.692 + 0.022 * q, lift=0.0006)
            lab = Board(b.at(0.0, 0.52), b.u, b.v, 0.22, 0.10, 0.002).body("sign_yellow")
            lab.icon("sign_dark", BOLT, -0.07, 0.0, 0.3)
            lab.text("sign_dark", "EQUIPMENT", 0.02, 0.03, 0.015)
            lab.text("sign_dark", ("B" if sy > 0 else "A") + ("2" if sg > 0 else "1") + "  750 V",
                     0.014, 0.03, -0.018)
        g.obj("interior.lockers." + tag, "lining", bevel=0.006)
        # the extinguisher on the left locker's aisle face, in a bracket, a sign over it
        xm = (xin + xf) / 2
        ge, gb, gk = Geo(), Geo(), Geo()
        y0 = 0.95 - 0.078
        prof = [(0.0, 0.0), (0.0, 0.060), (0.30, 0.060), (0.345, 0.045), (0.365, 0.022), (0.40, 0.022),
                (0.40, 0.0)]
        ge.lathe(prof, 20, axis='z', at=(xm, y0, 1.62))
        gk.box((xm, y0, 2.04), (0.05, 0.03, 0.04))
        gk.tube((xm, y0, 2.055), (xm + 0.085, y0 - 0.02, 2.085), 0.007, 8)
        gk.tube((xm, y0, 2.045), (xm + 0.07, y0 - 0.02, 2.03), 0.006, 8)
        gk.pipe([(xm - 0.02, y0, 2.03), (xm - 0.075, y0, 2.0), (xm - 0.082, y0, 1.80),
                 (xm - 0.07, y0, 1.72)], 0.009, 8)
        gb.ring((xm, y0, 1.80), 'z', 0.064, sec=(0.03, 0.004), n=20)
        gb.box((xm, 0.94, 1.80), (0.10, 0.02, 0.36))
        gb.box((xm, y0, 1.61), (0.13, 0.15, 0.012))
        ge.obj("interior.extinguisher." + tag, "sign_red", sharp=40)
        gk.obj("interior.extinguisher.head." + tag, "blackplastic", sharp=40)
        gb.obj("interior.extinguisher.bracket." + tag, "steel", bevel=0.002)
        b = Board((xm, 0.95, 2.36), (1, 0, 0), (0, 0, 1), 0.18, 0.22, 0.003).body("sign_red")
        b.icon("sign_white", FLAME, 0.0, 0.035, 0.5)
        b.text("sign_white", "FIRE", 0.022, 0.0, -0.055)
        b.text("sign_white", "EXTINGUISHER", 0.0125, 0.0, -0.082)
        b = Board((xm, -0.95, 2.36), (-1, 0, 0), (0, 0, 1), 0.18, 0.22, 0.003).body("sign_green")
        b.icon("sign_white", CROSS, 0.0, 0.035, 0.36)
        b.text("sign_white", "FIRST AID", 0.018, 0.0, -0.055)
        b.text("sign_white", "INSIDE", 0.0125, 0.0, -0.082)
        # over the passage: a dot-matrix display, the car's number, the maker's plate
        b = Board((xin, 0, 3.345), (0, -sg, 0), (0, 0, 1), 1.10, 0.15, 0.03).body("blackplastic")
        b.dots("lit_amber", "NEXT " + STATIONS[NEXT], 0.0, 0.0, 0.0105)
        for sy in (1, -1):
            b = Board((xin, sy * 0.775, 3.00), (0, -sg, 0), (0, 0, 1), 0.20, 0.14, 0.003).body("sign_white")
            if sy * sg < 0:
                b.text("sign_dark", "CAR", 0.016, 0.0, 0.04, spacing=1.2)
                b.text("sign_dark", CAR_NO, 0.05, 0.0, -0.012, spacing=1.05)
            else:
                b.icon("paint2", STRANDS, 0.0, 0.03, 0.5)
                b.text("sign_dark", "SKEIN METRO", 0.014, 0.0, -0.02, spacing=1.1)
                b.text("sign_dark", "CALDERA TRANSIT WORKS", 0.0075, 0.0, -0.042)
                b.text("sign_dark", "STRAND S-20   BUILT 2087", 0.0075, 0.0, -0.055)



# ---------------------------------------------------------------------------------------
# outside: lights, displays, lettering, beads along the flanks, the roof's gear
# ---------------------------------------------------------------------------------------
def outer_stretches():
    """The flank between the doorways: (front x, rear x)."""
    d1, d2, d3 = DOORS
    return [((XE - 0.30) if MID else (X_P1 - 0.06), d3 + DHW + 0.03), (d3 - DHW - 0.03, d2 + DHW + 0.03),
            (d2 - DHW - 0.03, d1 + DHW + 0.03), (d1 - DHW - 0.03, -XE + 0.30)]


def face_dots(g, txt, y0, z0, pitch, size, lift=0.0015):
    """A dot-matrix line on the nose's face, read from in front, its middle at (y0, z0)."""
    rows = dot_rows(txt)
    wd = len(rows[0])
    for r, row in enumerate(rows):
        for k, x in enumerate(row):
            if x != "#":
                continue
            loc, n = K.on_body(y0 + (k - (wd - 1) / 2) * pitch, z0 + (3 - r) * pitch, 'x')
            if loc is None:
                continue
            e1 = (V3((0, 1, 0)) - n * n.y).normalized()
            e2 = n.cross(e1)
            q = loc + n * lift
            g.add([q - e1 * size / 2 - e2 * size / 2, q + e1 * size / 2 - e2 * size / 2,
                   q + e1 * size / 2 + e2 * size / 2, q - e1 * size / 2 + e2 * size / 2], [(0, 1, 2, 3)])


def build_outside():
    d1, d2, d3 = DOORS
    g_bead, g_run, g_plate, g_dot, g_txt, g_ink, g_hatch, g_amb, g_sill, g_cam = (Geo() for _ in range(10))
    sec = [(-0.011, -0.001), (-0.006, 0.0055), (0.006, 0.0055), (0.011, -0.001)]
    for sy in (1, -1):
        for (x1, x0) in outer_stretches():
            for z in (1.30, 1.42, 1.54):                    # three beads along the lower flank
                g_bead.sweep([flank(x1 - 0.05, z, sy), flank(x0 + 0.05, z, sy)], sec, up=(0, sy, 0))
            for (xa, xb, za, zb) in ((x1 - 0.5, x1 - 1.3, 0.89, 1.08), (x0 + 1.3, x0 + 0.5, 0.89, 1.08)):
                if xa - xb < 0.3 or xa > x1 or xb < x0:
                    continue
                for q in ((xa, xb, za, za + 0.005), (xa, xb, zb - 0.005, zb), (xa, xa - 0.005, za, zb),
                          (xb + 0.005, xb, za, zb)):
                    flank_plate(g_hatch, q[0], q[1], q[2], q[3], sy, 0.003, 0.0)
                for xq in (xa - 0.1, xb + 0.1):
                    K.stud(g_cam, flank(xq, zb - 0.03, sy), V3((0, sy, 0)),
                           [(0.0, 0.001), (0.0, 0.011), (0.003, 0.009), (0.003, 0.001)], 10)
        # the running light under the cant rail, end to end
        xa = (XE - 0.3) if MID else X_P1 - 0.1
        flank_plate(g_run, xa, -XE + 0.3, 3.575, 3.587, sy, 0.0025, 0.001)
        # destination signs on the cant panel over the bays
        for xc in ((d1 + d2) / 2, (d2 + d3) / 2):
            flank_plate(g_plate, xc + 0.56, xc - 0.56, 3.335, 3.50, sy, 0.005, 0.002)
            dots(g_dot, "7 " + STATIONS[-1], flank(xc, 3.4175, sy, 0.0062), (-sy, 0, 0),
                 (0, -sy * 0.0667, 0.9978), 0.0128, 0.0092)
        # a lamp over every doorway (lit while it is released), a step lip under it
        for c in DOORS:
            flank_plate(g_amb, c + 0.06, c - 0.06, 3.30, 3.325, sy, 0.006, 0.002)
            g_sill.hexa([V3((x, sy * y, z)) for z in (1.085, 1.117) for x, y in
                         ((c - DHW, 1.455), (c + DHW, 1.455), (c + DHW, 1.492), (c - DHW, 1.492))])
        # lettering: the car's number at both ends, the operator's mark, the maker's line
        xn = [(-XE + 1.25)] + [(XE - 1.25) if MID else (X_P1 - 0.36)]
        for x in xn:
            flank_text(g_txt, CAR_NO, 0.19, x, 1.64, sy, spacing=1.08)
        xo = (d1 + d2) / 2
        icon(g_txt, STRANDS, flank(xo + sy * 0.86, 1.64, sy, 0.0012), (-sy, 0, 0), (0, 0, 1), 1.0, 0.0008)
        flank_text(g_txt, "SKEIN METRO", 0.16, xo - sy * 0.30, 1.64, sy, spacing=1.12)
        flank_text(g_ink, "CALDERA TRANSIT WORKS   STRAND S-20   CAR " + CAR_NO + "   TARE 34.6 T",
                   0.022, -XE + 1.6, 1.20, sy, spacing=1.2)
        flank_text(g_ink, "LIFT HERE", 0.02, d1 + 1.5, 1.17, sy, spacing=1.2)
        flank_text(g_ink, "LIFT HERE", 0.02, d3 - 1.5, 1.17, sy, spacing=1.2)
        for x in (d1 + 1.5, d3 - 1.5):
            icon(g_amb, [("poly", [(-0.03, 0.03), (0.03, 0.03), (0.0, -0.03)])], flank(x, 1.105, sy, 0.001),
                 (-sy, 0, 0), (0, 0, 1), 1.0, 0.0008)
    g_bead.obj("body.beads", "paint", sharp=40)
    g_run.obj("light.running", "led_run")
    g_plate.obj("sign.side.plates", "blackglass", bevel=0.002)
    g_dot.obj("sign.side.dots", "lit_amber")
    g_txt.obj("lettering.flank", "sign_dark")
    g_ink.obj("lettering.small", "sign_dark")
    g_hatch.obj("body.hatches", "void")
    g_cam.obj("body.latches", "steel", sharp=40)
    g_amb.obj("light.door.lamps", "led_amber")
    g_sill.obj("body.door.steps", "tread", bevel=0.003)
    build_roof()
    if not MID:
        build_nose_detail()


def build_roof():
    """Two air-conditioning units, the cable ducts between them, aerials, a walk strip."""
    g, gd, gf, gb, gs, ga = Geo(), Geo(), Geo(), Geo(), Geo(), Geo()
    zt = 4.37
    centers = (-4.6, 4.6) if MID else (-4.9, 3.4)
    for xc in centers:
        prof = [(-1.75, 3.80), (-1.75, 4.16), (-1.50, zt), (1.50, zt), (1.75, 4.16), (1.75, 3.80)]
        g.prism([(xc + a, -0.97, z) for a, z in prof], (0, 1.94, 0))
        for xf in (xc - 0.72, xc + 0.72):                       # two condenser fans
            gf.cyl((xf, 0, zt - 0.006), 0.012, 0.36, 28)
            gb.ring((xf, 0, zt + 0.004), 'z', 0.37, sec=(0.02, 0.03), n=28)
            gb.cyl((xf, 0, zt), 0.02, 0.07, 14)
            for k in range(7):
                a = 2 * pi * k / 7
                gb.box((xf + 0.2 * cos(a), 0.2 * sin(a), zt + 0.008), (0.30, 0.05, 0.006),
                       rot=Matrix.Rotation(a, 3, 'Z') @ Matrix.Rotation(rad(22), 3, 'X'))
            for q in range(5):                                  # a guard over it
                gs.ring((xf, 0, zt + 0.02), 'z', 0.07 + 0.07 * q, sec=(0.006, 0.006), n=28)
            for q in range(4):
                a = pi * q / 4
                gs.box((xf, 0, zt + 0.021), (0.74, 0.008, 0.006), rot=Matrix.Rotation(a, 3, 'Z'))
        for sy in (1, -1):                                      # louvres down each side
            for k in range(14):
                x = xc - 1.30 + 0.20 * k
                gd.box((x, sy * 0.972, 4.00), (0.15, 0.012, 0.22))
        gb.box((xc, 0, zt + 0.01), (0.5, 0.9, 0.02))            # the lid between the fans
    # cable ducts along the roof, clear of the units, and a walk strip down the middle
    xs = sorted(centers)
    runs = [(-XE + 0.5, xs[0] - 1.85), (xs[0] + 1.85, xs[1] - 1.85), (xs[1] + 1.85, (XE - 0.5) if MID else 8.3)]
    for (xa, xb) in runs:
        if xb - xa < 0.3:
            continue
        for sy in (1, -1):
            gd.box(((xa + xb) / 2, sy * 0.74, 3.955), (xb - xa, 0.16, 0.11))
            n = max(1, int((xb - xa) / 1.2))
            for k in range(n + 1):
                gs.box((xa + (xb - xa) * k / n, sy * 0.74, 3.96), (0.03, 0.18, 0.125))
        ga.box(((xa + xb) / 2, 0, 3.972), (xb - xa - 0.2, 0.40, 0.012))
    # aerials: a fin, a puck, a whip
    xa0 = 1.2 if MID else 6.6
    ga.prism([(xa0 - 0.16, -0.012, 3.96), (xa0 + 0.14, -0.012, 3.96), (xa0 - 0.02, -0.012, 4.14),
              (xa0 - 0.14, -0.012, 4.14)], (0, 0.024, 0))
    ga.cyl((xa0 - 0.8, 0.0, 3.955), 0.07, 0.11, 24)
    ga.cyl((xa0 - 1.5, 0.3, 3.95), 0.03, 0.03, 12)
    gs.tube((xa0 - 1.5, 0.3, 3.96), (xa0 - 1.55, 0.3, 4.42), 0.004, 6)
    g.obj("roof.hvac", "paint_dark", bevel=0.02, segs=3)
    gd.obj("roof.ducts", "skirt", bevel=0.006)
    gf.obj("roof.fan.wells", "void")
    gb.obj("roof.fans", "bogie", bevel=0.002)
    gs.obj("roof.guards", "steel", sharp=40)
    ga.obj("roof.aerials", "blackplastic", bevel=0.004)


LAMP_UNITS = ((0.36, 0.52, "head"), (0.58, 0.74, "head"), (0.80, 0.90, "tail"))
LAMP_Z = (ZW + 0.014, ZW + 0.076)


def lamp_holes():
    """Openings for the lamp units in the nose's light band: the panel's faces there are
    taken out (its rim then stands round each opening). Returns (side, kind, the four
    corners: inner low, outer low, outer high, inner high) per unit."""
    ob = BODY["face"].parts["fband"]
    bm = bmesh.new()
    bm.from_mesh(ob.data)
    units = []
    for sy in (1, -1):
        for (ya, yb, kind) in LAMP_UNITS:
            fs = []
            for f in bm.faces:
                c = f.calc_center_median()
                if ya < sy * c.y < yb and LAMP_Z[0] < c.z < LAMP_Z[1]:
                    fs.append(f)
            pts = [V3(q) for q in {tuple(v.co) for f in fs for v in f.verts}]
            units.append((sy, kind, [max(pts, key=lambda q, a=a, b=b: a * sy * q.y + b * q.z).copy()
                                     for a, b in ((-1, -1), (1, -1), (1, 1), (-1, 1))]))
            bmesh.ops.delete(bm, geom=fs, context='FACES')
    bm.to_mesh(ob.data)
    bm.free()
    return units


def build_nose_detail():
    """The nose: a light band round the beak, lamps and tail markers in it, the sign in the
    mask, the wiper, the coupler's hatch, the pilot under the chin."""
    zl = ZV - 0.02                              # the light line, over the lamp units
    g, gk = Geo(), Geo()
    units = lamp_holes()

    def mid(r):
        return (V3(r[JV]) + V3(r[JW])) / 2
    # the band's light line: across the face and round each corner to the flank
    for sy in (1, -1):
        m0, m1 = mid(N0), mid(N1)
        ctrl = [V3((face_x(0.0, zl), 0.0, zl)), V3((face_x(0.5, zl), sy * 0.5, zl)),
                V3((m0.x, sy * m0.y, zl)), V3((m1.x, sy * m1.y, zl)),
                V3((X_P1 + 0.35, sy * 1.42, zl)), V3((X_P1 - 0.02, sy * 1.50, zl))]
        K.strip(g, ctrl, 0.014, lift=0.003)
    # the lamp units in their openings: a housing behind the skin, a projector and a
    # reflector in each headlamp, a row of emitters in each tail marker, a lens over them
    head = K.Lamp("light.head", lit="lamp_head")
    tail = K.Lamp("light.tail", lit="led_tail", glass="lens_red")
    for (sy, kind, c) in units:
        lamp = head if kind == "head" else tail
        u, v = (c[1] - c[0]).normalized(), (c[3] - c[0]).normalized()
        n = u.cross(v)
        n = -n if n.x < 0 else n
        w = (c[1] - c[0]).length
        mid_ = sum(c, V3()) / 4
        back = [q - n * 0.066 for q in c]
        lamp.housing.add(list(c) + back, [(4, 5, 6, 7), (0, 1, 5, 4), (1, 2, 6, 5), (2, 3, 7, 6),
                                          (3, 0, 4, 7)])
        ins = [q.lerp(mid_, 0.012) for q in c]
        lamp.glass.hexa([q - n * 0.0045 for q in ins] + [q - n * 0.0015 for q in ins])
        at = mid_ - n * 0.013
        if kind == "head":
            lamp.projector(at - u * (w * 0.23), n, r=0.0205, depth=0.046)
            lamp.reflector(at + u * (w * 0.21), n, r=0.024, depth=0.022, seg=14, led=0.011)
            lamp.chrome.box(at - n * 0.02, (0.04, 0.004, 0.056),
                            rot=Matrix((n, u, v)).transposed())
        else:
            lamp.leds(at - u * (w * 0.36), at + u * (w * 0.36), 3, n, r=0.012)
    head.obj()
    tail.obj()
    gd = Geo()
    face_dots(gd, "7 " + STATIONS[-1], 0.0, 3.40, 0.0172, 0.0124)
    g.obj("light.band", "led_front")
    gd.obj("sign.front.dots", "lit_amber")
    # the wiper, parked low across the driver's half of the glass
    gw = Geo()
    def on(y, z, off):
        loc, n = K.on_body(y, z, 'x')
        return loc + n * off
    piv = on(-0.05, ZG + 0.035, 0.006)
    a, b = on(-0.02, ZG + 0.10, 0.012), on(0.74, ZG + 0.13, 0.012)
    gw.tube(a, b, 0.007, 8)
    gw.tube(a.lerp(b, 0.08) + V3((0.006, 0, 0)), a.lerp(b, 0.92) + V3((0.006, 0, 0)), 0.005, 6)
    gw.tube(piv + V3((0.012, 0, 0)), a.lerp(b, 0.5) + V3((0.016, 0, 0)), 0.007, 8)
    K.stud(gw, piv, V3((1, 0, 0.3)).normalized(), [(-0.004, 0.001), (-0.004, 0.022), (0.02, 0.018),
                                                    (0.024, 0.001)], 14)
    gw.obj("wiper", "blackplastic", sharp=40)
    # the prow: the coupler's hatch, the number, a row of rubbing ribs on the valance
    gh, gt = Geo(), Geo()
    K.ribbon(gh, K.rounded(0.0, 1.40, 0.62, 0.36, 0.05), 'x', 0.006, closed=True)
    K.ribbon(gh, [(-0.31, 1.22), (-0.31, 1.58)], 'x', 0.006)
    for y in (-0.20, 0.20):
        loc, n = K.on_body(y, 1.25, 'x')
        K.stud(gk, loc, n, [(0.0, 0.001), (0.0, 0.016), (0.004, 0.013), (0.004, 0.001)], 12)
    K.text_on_body(gt, CAR_NO, 0.11, 0.62, 1.47, 1, proj='x', spacing=1.08)
    K.text_on_body(gt, "SKEIN", 0.05, -0.64, 1.47, 1, proj='x', spacing=1.15)
    gh.obj("nose.hatch", "void")
    gk.obj("nose.hatch.studs", "steel", sharp=40)
    gt.obj("lettering.nose", "sign_dark")
    # the pilot: a plough under the chin, and a guard iron ahead of each front wheel
    gp = Geo()
    for sy in (1, -1):
        gp.hexa([(9.66, 0.0, 0.42), (9.26, sy * 0.96, 0.42), (9.20, sy * 0.96, 0.42), (9.60, 0.0, 0.42),
                 (9.56, 0.0, 0.86), (9.16, sy * 1.06, 0.86), (9.10, sy * 1.06, 0.86), (9.50, 0.0, 0.86)])
        gp.box((BOGIE_X + AXLE_DX + 0.52, sy * 0.755, 0.30), (0.03, 0.09, 0.42))
    gp.obj("nose.pilot", "skirt", bevel=0.01)


# ---------------------------------------------------------------------------------------
# the cab: a lining a wall's thickness inside the nose, the back wall and its door, the desk
# ---------------------------------------------------------------------------------------
Z_CAB = 3.40                        # the cab's ceiling
X_CABF = X_CAB + 0.06               # the back wall's cab face
CI = [(0.0, Z_CAB), (0.55, Z_CAB), (1.02, Z_CAB), (upper_y(Z_CAB) - GD - WALL, Z_CAB),
      (upper_y(ZH) - GD - WALL, ZH), (upper_y(ZG) - GD - WALL, ZG), (Y_IN, Z_FLOOR),
      (0.95, Z_FLOOR), (0.50, Z_FLOOR), (0.0, Z_FLOOR)]
#     the lining's section: ceiling (three lines), cornice, window head, window foot, floor


def cab_face_x(y, z):
    return face_x(y, z) - 0.085


def cab_rings():
    n1h = V3(N1[JH]) + V3((-0.048, -0.064, 0))
    n1g = V3(N1[JG]) + V3((-0.048, -0.064, 0))
    n1k = V3(N1[JK]).lerp(V3(N1[JH]), (N1[JK][2] - Z_CAB) / (N1[JK][2] - ZH)) + V3((-0.048, -0.064, 0))
    n1s = V3((N1[JS][0] - 0.05, N1[JS][1] - 0.065, Z_FLOOR))
    r1 = [(n1k.x + 0.02, 0.0, Z_CAB), (n1k.x + 0.02, 0.46, Z_CAB), (n1k.x + 0.012, 0.82, Z_CAB),
          (n1k.x, n1k.y, Z_CAB), tuple(n1h), tuple(n1g), tuple(n1s),
          (n1s.x + 0.02, 0.78, Z_FLOOR), (n1s.x + 0.03, 0.42, Z_FLOOR), (n1s.x + 0.04, 0.0, Z_FLOOR)]
    ys = (0.0, 0.30, 0.58)
    r0 = [(cab_face_x(y, Z_CAB), y, Z_CAB) for y in ys]
    r0 += [(cab_face_x(0.83, Z_CAB), 0.83, Z_CAB), (N0[JH][0] - 0.085, N0[JH][1], ZH),
           (N0[JG][0] - 0.085, N0[JG][1], ZG), (cab_face_x(0.90, Z_FLOOR), 0.90, Z_FLOOR)]
    r0 += [(cab_face_x(y, Z_FLOOR), y, Z_FLOOR) for y in (0.60, 0.30, 0.0)]
    return r0, r1


CABR = {}


def build_cab_lining():
    r0, r1 = cab_rings()
    CABR["r0"] = r0
    st = [r0, r1, [(X_P1, y, z) for y, z in CI], [(X_CABF, y, z) for y, z in CI]]

    def panel(i, j):
        return ("cceil", "cceil", "cceil", "cwall", "hole", "cwall", "cfloor", "cfloor", "cfloor")[j]

    def lcrease(i, j):
        if j in (4, 5):
            return 1.0
        return 1.0 if j in (3, 6) and i > 0 else 0.0
    pm = dict(cceil="cab_lining", cwall="cab_lining", cfloor="floor_in", hole="void")
    tube = K.build_body(st, panel, pm, lcrease,
                        lambda i, j: (0.35, 0.45)[i - 1] if i in (1, 2) else 0.0,
                        name="cab.lining", front=None, rear=None, subdiv=3, gap=0.0, thick=0.072,
                        project=False, bevel=0.0)
    rows = [r0[0:4]]
    for j in (4, 5):
        e = r0[j]
        rows.append([(cab_face_x(e[1] * s, e[2]), e[1] * s, e[2]) for s in FACE_COLS] + [e])
    rows.append([r0[9], r0[8], r0[7], r0[6]])
    sheet = K.build_body(rows, lambda i, j: ("cwall", "hole", "cwall")[i], pm, 0.0,
                         lambda i, j: 1.0 if i in (1, 2) else 0.0, name="cab.front",
                         front=None, rear=None, subdiv=3, gap=0.0, thick=0.072, project=False,
                         bevel=0.0)
    for piece, inward in ((tube, None), (sheet, V3((-1, 0, 0)))):
        ob = piece.parts.pop("hole")
        me = ob.data
        bpy.data.objects.remove(ob)
        bpy.data.meshes.remove(me)
        for ob in piece.parts.values():         # the lining faces into the cab, its rim
            me = ob.data                        # goes out to the skin
            if inward is None:
                s = sum(p.area * (p.normal.y * (1 if p.center.y > 0 else -1)
                                  + p.normal.z * (1 if p.center.z > 2.3 else -1))
                        for p in me.polygons)
            else:
                s = -sum(p.area * p.normal.dot(inward) for p in me.polygons)
            if s > 0:
                me.flip_normals()
            me.shade_smooth()
            me.set_sharp_from_angle(angle=rad(35))
    del K.PIECES["cab.lining"], K.PIECES["cab.front"]


def bulkhead(x0, x1, hole, pull=0.012):
    """A wall across the whole section from x0 to x1 with a doorway: its two faces, the
    doorway's reveal, its rim against the skin."""
    from mathutils.geometry import tessellate_polygon
    outer = end_outline(-XE, pull)
    tris = [tuple(t) for t in tessellate_polygon([[V3((y, z, 0)) for y, z in outer],
                                                   [V3((y, z, 0)) for y, z in hole]])]
    allp = outer + hole
    ga, gb, gr, ge = Geo(), Geo(), Geo(), Geo()
    ga.add([(x0, y, z) for y, z in allp], tris)
    gb.add([(x1, y, z) for y, z in allp], tris)
    for g, loop in ((gr, hole), (ge, outer)):
        m = len(loop)
        g.add([(x0, y, z) for y, z in loop] + [(x1, y, z) for y, z in loop],
              [(k, (k + 1) % m, m + (k + 1) % m, m + k) for k in range(m)])
    return ga, gb, gr, ge


CAB_DOOR_HW = 0.34


def build_cab():
    build_cab_lining()
    hole = rrect(-CAB_DOOR_HW, Z_FLOOR - 0.05, CAB_DOOR_HW, 3.17, 0.04)
    ga, gb, gr, ge = bulkhead(X_CAB, X_CABF, hole)
    ga.obj("interior.cabwall", "lining")
    gb.obj("cab.backwall", "cab_lining")
    gr.obj("cab.doorframe", "trim_in", sharp=40)
    ge.obj("cab.backwall.rim", "blackplastic")
    # the door: a leaf in the frame with a small window, a handle each side
    w, h = 2 * CAB_DOOR_HW - 0.016, 3.17 - Z_FLOOR - 0.016
    pl = Plate(w, h, [(0.19, 1.22, w - 0.19, 1.70, 0.05)])
    f = frame((X_CAB + 0.012, CAB_DOOR_HW - 0.008, Z_FLOOR + 0.008), (0, -1, 0), (0, 0, 1))
    g1, g2, g3, g4 = Geo(), Geo(), Geo(), Geo()
    pl.emit(f, 0.036, front=g1, back=g2, rev=g3, edge=g4)
    gg, gh, gt = Geo(), Geo(), Geo()
    gg.hexa([f(u, v, d) for d in (0.015, 0.021) for u, v in ((0.18, 1.21), (w - 0.18, 1.21),
                                                             (w - 0.18, 1.71), (0.18, 1.71))])
    for d0, d1 in ((0.0, -0.05), (0.036, 0.086)):
        gh.pipe([f(w - 0.07, 0.95, d0), f(w - 0.07, 0.95, d1), f(w - 0.07, 1.13, d1),
                 f(w - 0.07, 1.13, d0)], 0.011, 10)
    text_flat(gt, "STAFF ONLY", 0.034, f(w / 2, 1.86, -0.0012), (0, -1, 0), (0, 0, 1), spacing=1.1)
    text_flat(gt, "DRIVING CAB  " + CAR_NO, 0.016, f(w / 2, 1.80, -0.0012), (0, -1, 0), (0, 0, 1),
                spacing=1.15)
    door = join("cab.door", [g1.obj("t", "doorlining"), g2.obj("t", "cab_lining"),
                             g3.obj("t", "seal", sharp=40), g4.obj("t", "seal"),
                             gg.obj("t", "glass_in"), gh.obj("t", "steel", sharp=40),
                             gt.obj("t", "sign_dark")])
    door["hinge"] = (X_CAB + 0.03, -CAB_DOOR_HW, Z_FLOOR)
    # the wall's saloon side: a screen left of the door, the rules of the line right of it
    b = Board((X_CAB, 0.87, 2.82), (0, -1, 0), (0, 0, 1), 0.66, 0.38, 0.03).body("blackplastic")
    b.field("pis_bg", -0.31, -0.17, 0.31, 0.17)
    b.field("paint2", -0.29, 0.075, -0.19, 0.155, lift=0.0008)
    b.text("lit_white", "7", 0.07, -0.24, 0.115, lift=0.0014)
    b.text("lit_white", "EMBER LINE", 0.034, 0.02, 0.118, spacing=1.1)
    b.text("lit_amber", "23:41", 0.026, 0.245, 0.12)
    b.text("lit_white", "NEXT   " + STATIONS[NEXT], 0.040, 0.0, 0.025, spacing=1.05)
    for k in range(4):
        a = -0.24 + 0.16 * k
        b.icon("lit_amber" if k else "led_door", [("dot", (0, 0), 0.012)], a, -0.075, 1.0)
        b.text("lit_white", STATIONS[NEXT + k], 0.013, a, -0.105)
    b.field("lit_white", -0.24, -0.077, 0.24, -0.073)
    b.dots("lit_amber", "MIND THE GAP", 0.0, -0.142, 0.0046)
    b = Board((X_CAB, -0.87, 2.68), (0, -1, 0), (0, 0, 1), 0.50, 0.66, 0.004).body("sign_white")
    b.field("paint2", -0.25, 0.25, 0.25, 0.33)
    b.text("sign_white", "TRAVEL SAFELY", 0.036, 0.0, 0.29, spacing=1.1)
    rules = ((NOSMOKE, "sign_red", "NO SMOKING OR VAPING"), (CAMERA, "sign_dark", "CCTV RECORDS THIS CAR"),
             (CANE, "sign_blue", "OFFER PRIORITY SEATS"), (FLAME, "sign_red", "EXTINGUISHER AT CAR END"),
             (BOLT, "sign_dark", "DO NOT TOUCH EQUIPMENT"), (CROSS, "sign_green", "HELP POINT BY DOOR 2"))
    for k, (pic, mat, txt) in enumerate(rules):
        z = 0.185 - 0.078 * k
        b.icon(mat, pic, -0.19, z, 0.21)
        b.text("sign_dark", txt, 0.0185, 0.055, z, spacing=1.08)
    b.text("sign_dark", "SKEIN METRO  CONDITIONS OF CARRIAGE APPLY  CAR " + CAR_NO, 0.0095, 0.0, -0.295)
    flush("interior.cabwall.")
    build_cab_fit()
    flush("cab.print.")


def build_cab_fit():
    """The cab's fittings: the desk and what stands on it, the seats, the blind."""
    # the desk: a console across the front, a wing each side, on a plinth
    xw = cab_face_x(0.0, 1.95)                       # the lining at desk height, in the middle
    g, gt, gk = Geo(), Geo(), Geo()
    sec = [(8.98, 1.88), (9.02, 1.95), (9.36, 2.03), (xw - 0.08, 2.03), (xw - 0.12, 1.80),
           (9.50, 1.55), (9.20, 1.55), (9.02, 1.78)]
    g.prism([(x, -0.62, z) for x, z in sec], (0, 1.24, 0))
    for sy in (1, -1):
        wing = [(8.62, sy * 0.66), (9.42, sy * 0.60), (xw - 0.03, sy * 0.62), (xw - 0.12, sy * 1.06),
                (9.25, sy * 1.26), (8.62, sy * 1.32)]
        g.prism([(x, y, 1.80) for x, y in wing], (0, 0, 0.115))
        gbox(gk, 8.70, 9.40, sy * 0.72, sy * 1.22, Z_FLOOR, 1.80)
    gbox(gk, 9.22, 9.56, -0.60, 0.60, Z_FLOOR, 1.56)
    g.obj("cab.desk", "desk", bevel=0.012, segs=3)
    gk.obj("cab.desk.plinth", "cab_lining", bevel=0.006)
    # screens: three on the console, leaning to the driver; a camera screen on each wing
    gf = Geo()
    tilt = Matrix.Rotation(rad(-58), 3, 'Y')

    def glass_of(c, rot, wdt, hgt):
        """A screen's face as a board to draw on."""
        b = Board(c + rot @ V3((0, 0, 0.011)), rot @ V3((0, -1, 0)), rot @ V3((1, 0, 0)), wdt, hgt, 0.002)
        b.field("cab_scr", -wdt / 2, -hgt / 2, wdt / 2, hgt / 2)
        return b
    for y, wdt in ((0.0, 0.34), (0.39, 0.30), (-0.39, 0.30)):
        c = V3((9.215, y, 2.01))
        gf.box(c, (0.25, wdt + 0.03, 0.022), rot=tilt)
        b = glass_of(c, tilt, wdt - 0.01, 0.215)
        if y == 0.0:                            # speed, power and brake
            b.icon("lit_white", [("ring", (0, 0), 0.07, 0.008, -40, 220)], -0.05, -0.01, 1.0)
            b.icon("led_door", [("ring", (0, 0), 0.07, 0.008, 95, 220)], -0.05, -0.01, 1.0, lift=0.0012)
            b.text("lit_white", "42", 0.05, -0.05, -0.012)
            b.text("lit_amber", "KM/H", 0.011, -0.05, -0.058)
            for k in range(6):
                b.field("led_door" if k < 4 else "ink_grey", 0.07, -0.075 + 0.026 * k, 0.10, -0.055 + 0.026 * k)
                b.field("lit_amber" if k < 1 else "ink_grey", 0.115, -0.075 + 0.026 * k, 0.145,
                        -0.055 + 0.026 * k)
            b.text("lit_white", "PWR  BRK", 0.009, 0.108, 0.092)
        elif y > 0:                             # the line ahead
            b.text("lit_white", "7  EMBER LINE", 0.016, 0.0, 0.085)
            b.field("lit_white", -0.12, 0.028, 0.12, 0.031)
            for k in range(5):
                b.icon("led_door" if k == 1 else "lit_amber", [("dot", (0, 0), 0.008)], -0.12 + 0.06 * k, 0.0295, 1.0)
            b.text("lit_white", "NEXT  " + STATIONS[NEXT], 0.013, 0.0, -0.01)
            b.text("lit_amber", "ARR 23:43   +00:40", 0.011, 0.0, -0.04)
            b.dots("lit_amber", "ATO READY", 0.0, -0.08, 0.0035)
        else:                                   # the train: doors, brakes, faults
            for k in range(4):
                b.field("led_door", -0.125 + 0.064 * k, 0.03, -0.07 + 0.064 * k, 0.06)
                b.field("pis_bg", -0.119 + 0.064 * k, 0.036, -0.076 + 0.064 * k, 0.054, lift=0.0009)
            b.text("lit_white", "DOORS CLOSED AND LOCKED", 0.0105, 0.0, 0.085)
            b.text("lit_white", "BRAKES  RELEASED", 0.0105, 0.0, -0.005)
            b.text("lit_white", "LINE  750 V   HVAC  AUTO", 0.0105, 0.0, -0.03)
            b.text("led_door", "NO FAULTS", 0.014, 0.0, -0.07)
    for sy in (1, -1):
        c = V3((9.36, sy * 0.92, 1.99))
        rot = Matrix.Rotation(rad(sy * 28), 3, 'Z') @ Matrix.Rotation(rad(-62), 3, 'Y')
        gf.box(c, (0.21, 0.30, 0.022), rot=rot)
        b = glass_of(c, rot, 0.265, 0.18)
        b.field("cam_feed", -0.125, -0.082, 0.125, 0.082, lift=0.0008)        # the platform camera
        b.field("pis_bg", -0.125, -0.082, -0.04 * sy - 0.06, 0.0, lift=0.0011)
        b.field("lit_amber", -0.04 * sy - 0.062, -0.082, -0.04 * sy - 0.056, 0.082, lift=0.0013)
        b.text("lit_white", "CAM " + ("L" if sy > 0 else "R"), 0.01, 0.09, 0.07, lift=0.0015)
    gf.obj("cab.screen.frames", "blackplastic", bevel=0.004)
    # trims: a post over the lining's seam each side of the windshield, one outside on the glass
    gq, go = Geo(), Geo()
    r0 = CABR["r0"]
    gq.pipe([V3(r0[3]) + V3((-0.01, 0, 0)), V3(r0[4]) + V3((-0.012, 0, 0)), V3(r0[5]) + V3((-0.012, 0, 0)),
             V3(r0[6]) + V3((-0.01, 0, 0))], 0.032, 8)
    go.sweep([V3(N0[JK]) + V3((0.003, 0, 0)), V3(N0[JH]) + V3((0.003, 0, 0)), V3(N0[JG]) + V3((0.003, 0, 0)),
              V3(N0[JV]) + V3((0.003, 0, 0))],
             [(-0.022, -0.004), (0.022, -0.004), (0.022, 0.005), (-0.022, 0.005)], up=(1, 0, 0.3))
    gq.obj("cab.posts", "blackplastic", mirror=True, sharp=40)
    go.obj("nose.posts", "blackglass", mirror=True, sharp=40)
    # the master controller on the left wing: a quadrant and a T handle; a horn pull
    gc, gm, gb, gr, gl = Geo(), Geo(), Geo(), Geo(), Geo()
    gbox(gc, 8.80, 9.06, 0.74, 0.92, 1.915, 1.935)
    gm.lathe([(-0.022, 0.0), (-0.022, 0.055), (0.022, 0.055), (0.022, 0.0)], 20, a0=0.0, a1=pi,
             at=(8.93, 0.83, 1.925))
    gm.tube((8.93, 0.83, 1.93), (8.905, 0.83, 2.075), 0.011, 10)
    gm.tube((8.905, 0.775, 2.08), (8.905, 0.885, 2.08), 0.017, 12)
    # switches, lamps and an emergency stop on the right wing; a row under the screens
    for k in range(6):
        for r in range(2):
            p = (8.80 + r * 0.075, -0.76 - k * 0.062, 1.915)
            gb.cyl(p, 0.012, 0.016, 12)
            (gl if (k + r) % 3 == 0 else gb).cyl((p[0], p[1], 1.927), 0.004, 0.011, 12)
    gr.cyl((9.02, -0.80, 1.915), 0.03, 0.036, 20)
    gr.cyl((9.02, -0.80, 1.945), 0.018, 0.05, 20)
    gbox(gc, 8.96, 9.08, -0.86, -0.74, 1.914, 1.922)
    for k in range(9):
        gb.cyl((8.995, -0.40 + k * 0.10, 1.925), 0.010, 0.013, 12, axis=(0.6, 0, 0.8))
    gbox(gc, 9.10, 9.17, -1.14, -0.94, 1.915, 1.96)             # the radio handset's cradle
    gm.tube((9.135, -1.12, 1.975), (9.135, -0.96, 1.975), 0.02, 12)
    gc.obj("cab.desk.plates", "tread", bevel=0.002)
    gm.obj("cab.controller", "blackplastic", sharp=40)
    gb.obj("cab.switches", "steel", sharp=40)
    gl.obj("cab.switch.lamps", "led_door")
    gr.obj("cab.estop", "sign_red", sharp=40)
    # the driver's seat on a pedestal, a tip-up seat on the back wall for a second person
    g, gp, gs = Geo(), Geo(), Geo()
    xs = 8.42
    g.prism([(xs - y, -0.235, Z_FLOOR + 0.07 + z * 1.12) for y, z in SHELL], (0, 0.47, 0))
    gp.prism([(xs - y, -0.20, Z_FLOOR + 0.07 + z * 1.12) for y, z in PAD_SEAT], (0, 0.40, 0))
    gp.prism([(xs - y, -0.20, Z_FLOOR + 0.07 + z * 1.12) for y, z in PAD_BACK], (0, 0.40, 0))
    gbox(gp, xs + 0.035, xs + 0.08, -0.13, 0.13, Z_FLOOR + 1.02, Z_FLOOR + 1.24)   # a head rest
    gs.cyl((xs + 0.24, 0, Z_FLOOR), 0.47, 0.045, 16)
    gs.cyl((xs + 0.24, 0, Z_FLOOR), 0.03, 0.24, 24)
    for sy in (1, -1):
        gs.pipe([(xs + 0.06, sy * 0.26, Z_FLOOR + 0.55), (xs + 0.06, sy * 0.26, Z_FLOOR + 0.74),
                 (xs + 0.34, sy * 0.26, Z_FLOOR + 0.74)], 0.02, 10)
    g.obj("cab.seat.shell", "blackplastic", bevel=0.008, segs=2)
    gp.obj("cab.seat.pads", "fabric", bevel=0.006, segs=2)
    gs.obj("cab.seat.base", "steel", sharp=40)
    g, gp = Geo(), Geo()
    gbox(g, X_CABF, X_CABF + 0.05, -1.16, -0.72, Z_FLOOR + 0.42, Z_FLOOR + 0.86)
    gbox(gp, X_CABF + 0.05, X_CABF + 0.075, -1.13, -0.75, Z_FLOOR + 0.45, Z_FLOOR + 0.83)
    gbox(gp, X_CABF, X_CABF + 0.03, -1.13, -0.75, Z_FLOOR + 0.95, Z_FLOOR + 1.30)
    g.obj("cab.jumpseat", "blackplastic", bevel=0.008, segs=2)
    gp.obj("cab.jumpseat.pads", "fabric", bevel=0.006, segs=2)
    # the blind over the windshield (drawn a hand down on the driver's side), a foot rest,
    # the destination sign's box under the ceiling, a lamp
    g, gb, gl = Geo(), Geo(), Geo()
    for y0, y1, drop in ((-0.78, -0.02, 0.10), (0.02, 0.78, 0.30)):
        xa = cab_face_x(0.5, ZH) - 0.035
        gbox(g, xa - 0.05, xa + 0.02, y0, y1, ZH - 0.01, ZH + 0.06)
        xb = cab_face_x(0.5, ZH - drop) - 0.03
        gb.hexa([(xa - 0.008, y0 + 0.01, ZH - 0.01), (xa - 0.008, y1 - 0.01, ZH - 0.01),
                 (xa - 0.002, y1 - 0.01, ZH - 0.01), (xa - 0.002, y0 + 0.01, ZH - 0.01),
                 (xb - 0.008, y0 + 0.01, ZH - drop), (xb - 0.008, y1 - 0.01, ZH - drop),
                 (xb - 0.002, y1 - 0.01, ZH - drop), (xb - 0.002, y0 + 0.01, ZH - drop)])
    gbox(g, 9.02, 9.26, -0.25, 0.25, Z_FLOOR, Z_FLOOR + 0.06)
    gbox(gl, 8.05, 8.75, -0.30, 0.30, Z_CAB - 0.012, Z_CAB + 0.01)
    K.cabin_light((8.5, 0.0, Z_CAB - 0.06), power=62.0, size=1.0)
    K.cabin_light((9.0, 0.0, Z_CAB - 0.15), power=30.0, size=0.6, target=(9.3, 0.0, 1.9))
    gbox(g, X_CABF, X_CABF + 0.30, 0.80, 1.36, Z_FLOOR, Z_FLOOR + 1.9)       # a locker by the door
    for z in (1.9, 2.6):
        K.stud(gl, V3((X_CABF + 0.30, 0.88, z)), V3((1, 0, 0)), [(0.0, 0.001), (0.0, 0.006), (0.002, 0.006),
                                                                 (0.002, 0.001)], 8)
    g.obj("cab.fittings", "blackplastic", bevel=0.005)
    gb.obj("cab.blind", "blind")
    gl.obj("cab.light", "light_cab")


# ---------------------------------------------------------------------------------------
# the track (the studio's): a slab, two rails on fastenings, a third rail on the right
# ---------------------------------------------------------------------------------------
RAIL_Y = 0.7545                     # the rails' middles (1435 mm between their heads)
TRACK_L = 11.0
SLAB_Z = -0.20                      # the slab's top
FLOOR_Z = -0.44                     # the studio's floor, lowered to the slab's foot


def build_track():
    S = K.STUDIO
    g = Geo()
    prof = [(-0.075, -0.172), (0.075, -0.172), (0.075, -0.160), (0.012, -0.138),
            (0.009, -0.045), (0.036, -0.032), (0.036, -0.004), (0.030, 0.0), (-0.030, 0.0),
            (-0.036, -0.004), (-0.036, -0.032), (-0.009, -0.045), (-0.012, -0.138),
            (-0.075, -0.160)]
    for sy in (1, -1):
        g.prism([(-TRACK_L, sy * RAIL_Y + a, b) for a, b in prof], (2 * TRACK_L, 0, 0))
    g.obj("track.rails", "railsteel", coll=S)
    g, gc, gp = Geo(), Geo(), Geo()
    n = int(2 * TRACK_L / 0.65)
    for k in range(n):
        x = -TRACK_L + 0.33 + k * 0.65
        for sy in (1, -1):
            g.box((x, sy * RAIL_Y, -0.186), (0.20, 0.40, 0.028))       # the baseplate
            for dy in (0.13, -0.13):
                gc.box((x, sy * RAIL_Y + dy, -0.158), (0.05, 0.07, 0.03))
                gc.cyl((x, sy * RAIL_Y + dy * 1.25, -0.172), 0.045, 0.012, 8)
            gp.box((x, sy * RAIL_Y, -0.21), (0.30, 0.62, 0.02))        # its pad on the slab
    g.obj("track.plates", "railsteel", bevel=0.003, coll=S)
    gc.obj("track.clips", "bogie", coll=S)
    gp.obj("track.pads", "rubber", coll=S)
    g = Geo()
    g.box((0, 0, (SLAB_Z + FLOOR_Z) / 2 - 0.01), (2 * TRACK_L, 2.70, SLAB_Z - FLOOR_Z - 0.02))
    g.box((0, 0, FLOOR_Z + 0.03), (2 * TRACK_L, 3.3, 0.06))
    g.obj("track.slab", "concrete", bevel=0.012, coll=S)
    g = Geo()                                   # a drain channel down the middle
    g.box((0, 0, SLAB_Z - 0.004), (2 * TRACK_L, 0.26, 0.012))
    g.obj("track.drain", "void", coll=S)
    # the third rail on the right, on insulators, under a cover board
    g, gi, gb = Geo(), Geo(), Geo()
    y3 = -1.42
    g.box((0, y3, 0.135), (2 * TRACK_L, 0.07, 0.09))
    for k in range(int(2 * TRACK_L / 2.6) + 1):
        x = -TRACK_L + 0.4 + k * 2.6
        gi.cyl((x, y3, SLAB_Z), 0.29, 0.045, 12)
        gi.box((x, y3 - 0.10, 0.19), (0.06, 0.05, 0.16))
        gi.box((x, y3 - 0.06, SLAB_Z + 0.02), (0.16, 0.22, 0.04))
    gb.box((0, y3 - 0.02, 0.265), (2 * TRACK_L, 0.20, 0.018))
    gb.box((0, y3 - 0.115, 0.215), (2 * TRACK_L, 0.016, 0.10))
    g.obj("track.thirdrail", "railsteel", coll=S)
    gi.obj("track.insulators", "insulator", coll=S)
    gb.obj("track.coverboard", "coverboard", bevel=0.004, coll=S)


# ---------------------------------------------------------------------------------------
# the bogies
# ---------------------------------------------------------------------------------------
BOGIE_X = 6.70
WHEEL_R = 0.42
AXLE_DX = 1.10


def build_bogie(tag, bx):
    """A two-axle motor bogie: an H frame outside the wheels on rubber springs over the
    axle boxes, air springs up to the body, a motor and a gearbox an axle, brake units on
    the treads, a collector shoe each side. Each wheelset is an object about its axle."""
    nm = "bogie.%s." % tag
    for k, dx in enumerate((AXLE_DX, -AXLE_DX)):
        g = Geo()
        # a wheel's section (axial from the back of the flange outward, radius)
        prof = [(-0.070, 0.10), (-0.070, 0.448), (-0.058, 0.449), (-0.040, 0.424),
                (0.060, 0.418), (0.065, 0.412), (0.065, 0.365), (0.040, 0.350), (0.040, 0.30),
                (0.052, 0.29), (0.052, 0.20), (0.030, 0.19), (0.030, 0.16), (0.075, 0.14),
                (0.075, 0.10)]
        for sy in (1, -1):
            xf = Matrix.Translation((0, sy * 0.7175, 0)) @ Matrix.Scale(sy, 4, (0, 1, 0))
            g.lathe(prof, 40, xf=xf)
            for q in range(8):                  # the brake disc's bolts on the wheel's web
                a_ = 2 * pi * q / 8
                g.tube((0.245 * cos(a_), sy * 0.765, 0.245 * sin(a_)),
                       (0.245 * cos(a_), sy * 0.776, 0.245 * sin(a_)), 0.012, 6)
        g.lathe([(-1.02, 0.075), (1.02, 0.075), (1.02, 0.0), (-1.02, 0.0)], 20)
        g.obj(nm + "axle%d" % (k + 1), "wheelsteel", loc=(bx + dx, 0, WHEEL_R), sharp=35)
    g, gr, gd, ga, gm, gb, gs, gi, gc = (Geo() for _ in range(9))
    beam = [(-1.45, 0.76), (-0.80, 0.76), (-0.55, 0.60), (0.55, 0.60), (0.80, 0.76), (1.45, 0.76),
            (1.45, 0.63), (0.84, 0.63), (0.60, 0.42), (-0.60, 0.42), (-0.84, 0.63), (-1.45, 0.63)]
    for sy in (1, -1):
        g.prism([(bx + x, sy * 0.96, z) for x, z in beam], (0, sy * 0.14, 0))
        for dx in (AXLE_DX, -AXLE_DX):
            sg = 1 if dx > 0 else -1
            x = bx + dx
            g.box((x, sy * 1.03, WHEEL_R), (0.26, 0.18, 0.24))                 # the axle box
            K.stud(gs, V3((x, sy * 1.12, WHEEL_R)), V3((0, sy, 0)),
                   [(0.0, 0.001), (0.0, 0.095), (0.012, 0.095), (0.022, 0.07), (0.022, 0.001)], 20)
            for q in range(6):
                a_ = 2 * pi * q / 6
                K.stud(gs, V3((x + 0.075 * cos(a_), sy * 1.132, WHEEL_R + 0.075 * sin(a_))),
                       V3((0, sy, 0)), [(0.0, 0.001), (0.0, 0.009), (0.006, 0.009), (0.006, 0.001)], 6)
            for q in range(3):                                                # the rubber spring
                gr.cyl((x, sy * 1.03, 0.54 + 0.03 * q), 0.024, 0.10 - 0.008 * q, 20)
            gd.tube((x + sg * 0.20, sy * 1.125, 0.34), (x + sg * 0.20, sy * 1.125, 0.72), 0.026, 12)
            gd.tube((x + sg * 0.20, sy * 1.125, 0.34), (x + sg * 0.20, sy * 1.125, 0.52), 0.034, 12)
            g.box((x + sg * 0.20, sy * 1.10, 0.73), (0.07, 0.06, 0.05))
            g.box((x + sg * 0.17, sy * 1.10, 0.34), (0.10, 0.06, 0.05))
            # a brake unit on the tread, inboard of the wheel
            gb.box((x - sg * 0.50, sy * 0.7175, 0.44), (0.17, 0.15, 0.22))
            gb.box((x - sg * 0.435, sy * 0.7175, 0.44), (0.03, 0.10, 0.20))
            g.box((x - sg * 0.56, sy * 0.86, 0.50), (0.08, 0.22, 0.08))
        # the air spring on the frame's low middle, its plate under the body
        ga.lathe([(0.0, 0.0), (0.0, 0.21), (0.03, 0.255), (0.09, 0.255), (0.115, 0.215), (0.14, 0.255),
                  (0.20, 0.255), (0.23, 0.21), (0.23, 0.0)], 28, axis='z', at=(bx, sy * 1.03, 0.60))
        g.cyl((bx, sy * 1.03, 0.825), 0.03, 0.27, 28)
        gd.tube((bx + 0.42, sy * 1.135, 0.50), (bx + 0.42, sy * 1.135, 0.84), 0.028, 12)
        gd.tube((bx + 0.42, sy * 1.135, 0.50), (bx + 0.42, sy * 1.135, 0.66), 0.036, 12)
        # the shoe gear: a beam between the axle boxes, the shoe on its arm, its cable
        gi.box((bx, sy * 1.17, 0.265), (2.0, 0.06, 0.09))
        for dx in (AXLE_DX, -AXLE_DX):
            g.box((bx + dx, sy * 1.15, 0.30), (0.10, 0.10, 0.16))
        gs.box((bx, sy * 1.29, 0.225), (0.34, 0.24, 0.03))
        gs.box((bx, sy * 1.415, 0.196), (0.30, 0.10, 0.032))
        gc.pipe([(bx + 0.10, sy * 1.25, 0.24), (bx + 0.22, sy * 1.25, 0.34), (bx + 0.30, sy * 1.20, 0.60),
                 (bx + 0.30, sy * 1.18, 0.84)], 0.017, 8)
    for dx in (0.34, -0.34):                                                  # the transoms
        g.box((bx + dx, 0, 0.51), (0.16, 1.94, 0.15))
    g.box((bx, 0, 0.72), (0.56, 0.62, 0.24))                                  # the bolster
    g.cyl((bx, 0, 0.60), 0.25, 0.11, 16)
    gd.tube((bx - 0.2, 0.16, 0.66), (bx - 0.2, 0.92, 0.66), 0.028, 12)        # lateral damper
    g.tube((bx + 0.05, -0.30, 0.56), (bx + 0.95, -0.30, 0.64), 0.03, 10)      # traction rod
    for dx, sy in ((AXLE_DX, 1), (-AXLE_DX, -1)):                             # motors, gearboxes
        sg = 1 if dx > 0 else -1
        x = bx + dx
        gm.lathe([(-0.30, 0.0), (-0.30, 0.19), (-0.26, 0.225), (0.24, 0.225), (0.28, 0.19), (0.28, 0.0)],
                 24, at=(x - sg * 0.50, sy * 0.10, 0.45))
        for q in range(9):
            gm.ring((x - sg * 0.50, sy * (0.10 - 0.20 + 0.05 * q), 0.45), 'y', 0.232, sec=(0.012, 0.016), n=24)
        gm.lathe([(-0.07, 0.0), (-0.07, 0.27), (0.07, 0.27), (0.07, 0.0)], 24, at=(x, -sy * 0.28, WHEEL_R))
        gm.lathe([(-0.07, 0.0), (-0.07, 0.15), (0.07, 0.15), (0.07, 0.0)], 20, at=(x - sg * 0.50, -sy * 0.28, 0.45))
        gm.box((x - sg * 0.25, -sy * 0.28, 0.435), (0.50, 0.14, 0.28))
        gc.pipe([(x - sg * 0.50, sy * 0.42, 0.52), (x - sg * 0.50, sy * 0.52, 0.66), (x - sg * 0.50, sy * 0.52, 0.84)],
                0.022, 8)
    g.obj(nm + "frame", "bogie", bevel=0.012, segs=2)
    gr.obj(nm + "springs", "rubber", sharp=40)
    gd.obj(nm + "dampers", "damper", sharp=40)
    ga.obj(nm + "airsprings", "rubber", sharp=40)
    gm.obj(nm + "motors", "under_eq", sharp=40)
    gb.obj(nm + "brakes", "under_eq", bevel=0.008)
    gs.obj(nm + "shoes", "wheelsteel", sharp=40)
    gi.obj(nm + "shoebeams", "insulator", bevel=0.006)
    gc.obj(nm + "cables", "cable", sharp=40)


def build_underfloor():
    """The gear between the bogies: converter, battery, compressor and air tanks, brake
    control, trunking; each case on brackets under the frame."""
    g, gf, gv, gl, gt, gp, gk = (Geo() for _ in range(7))
    zt = Z_UF + 0.01
    cases = [(0.55, 2.75, -1.27, 1.27, 0.30, "TRACTION CONVERTER"), (-2.75, -0.75, -1.24, 1.24, 0.34, "BATTERY 110 V"),
             (3.15, 4.45, 0.22, 1.24, 0.33, "COMPRESSOR"), (-4.45, -3.15, -1.24, -0.22, 0.36, "BRAKE CONTROL"),
             (-4.45, -3.35, 0.30, 1.24, 0.46, "AUX SUPPLY")]
    for (x0, x1, y0, y1, z0, name) in cases:
        gbox(g, x0, x1, y0, y1, z0, zt)
        for x in (x0 + 0.12, x1 - 0.12):
            for y in (y0, y1):
                gbox(gk, x - 0.05, x + 0.05, y - 0.02, y + 0.02, zt - 0.14, zt)
        for sy, y in ((1, y1), (-1, y0)):
            if abs(y) < 1.2:
                continue
            xm = (x0 + x1) / 2
            b = Board((xm + sy * (x1 - x0) / 2 - sy * 0.22, y, z0 + 0.10), (-sy, 0, 0), (0, 0, 1), 0.30, 0.10, 0.002)
            b.body("sign_yellow")
            b.text("sign_dark", name, 0.02 if len(name) < 14 else 0.015, 0.0, 0.012)
            b.text("sign_dark", "750 V  ISOLATE BEFORE OPENING", 0.008, 0.0, -0.022)
            # an access door's outline and two latches
            for q in ((x0 + 0.08, x1 - 0.50, z0 + 0.06, z0 + 0.066), (x0 + 0.08, x1 - 0.50, zt - 0.10, zt - 0.094),
                      (x0 + 0.08, x0 + 0.086, z0 + 0.06, zt - 0.094), (x1 - 0.506, x1 - 0.50, z0 + 0.06, zt - 0.094)):
                gbox(gv, q[0], q[1], y, y + sy * 0.0015, q[2], q[3])
            for x in (x0 + 0.25, x1 - 0.67):
                K.stud(gl, V3((x, y, zt - 0.14)), V3((0, sy, 0)), [(0.0, 0.001), (0.0, 0.02), (0.012, 0.016),
                                                                    (0.012, 0.001)], 12)
    for k in range(22):                                 # the converter's cooling fins, left
        gbox(gf, 0.70 + 0.045 * k, 0.72 + 0.045 * k, 1.27, 1.31, 0.36, 0.78)
    for k in range(7):                                  # the battery box's vents, right
        gbox(gv, -2.55, -1.75, -1.2415, -1.24, 0.42 + 0.04 * k, 0.435 + 0.04 * k)
    for y in (-0.52, -0.95):                            # air tanks beside the compressor
        gt.lathe([(-0.66, 0.0), (-0.66, 0.12), (-0.60, 0.17), (0.60, 0.17), (0.66, 0.12), (0.66, 0.0)], 24,
                 axis='x', at=(3.80, y, 0.60))
        for x in (3.40, 4.20):
            gk.ring((x, y, 0.60), 'x', 0.174, sec=(0.04, 0.008), n=24)
            gbox(gk, x - 0.02, x + 0.02, y - 0.03, y + 0.03, 0.76, zt)
    gbox(gp, -5.0, 5.0, -0.16, 0.16, 0.75, zt)          # trunking and two pipes along the frame
    for y in (-0.42, 0.42):
        gp.tube((-5.2, y, 0.80), (5.2, y, 0.80), 0.026, 10)
    g.obj("underfloor.cases", "under_eq", bevel=0.012, segs=2)
    gf.obj("underfloor.fins", "tread")
    gv.obj("underfloor.vents", "void")
    gl.obj("underfloor.latches", "steel", sharp=40)
    gt.obj("underfloor.tanks", "under_eq", sharp=40)
    gp.obj("underfloor.trunking", "bogie", sharp=40)
    gk.obj("underfloor.brackets", "bogie", bevel=0.004)
    flush("underfloor.print.")


def build_end_gear(sg):
    """Under and beside a gangway: the bar coupler, jumper cables, hand rails."""
    tag = "rear" if sg < 0 else "front"
    g, gc, gs = Geo(), Geo(), Geo()
    xw = sg * (XE - 0.03)
    xo = sg * (XE + 0.47)
    g.tube((sg * (XE - 0.9), 0, 0.60), (xo, 0, 0.60), 0.065, 14, )
    g.box((xo, 0, 0.60), (0.07, 0.36, 0.30))
    g.box((sg * (XE - 0.55), 0, 0.72), (0.5, 0.5, 0.26))
    for sy in (1, -1):
        for k, y in enumerate((1.00, 1.15)):
            gs.box((xw + sg * 0.03, sy * y, 1.42), (0.06, 0.10, 0.12))
            gc.pipe([(xw + sg * 0.05, sy * y, 1.40), (xw + sg * 0.22, sy * y, 1.22 - 0.05 * k),
                     (xw + sg * 0.42, sy * y, 1.18 - 0.05 * k), (xo + sg * 0.02, sy * y, 1.26 - 0.05 * k)], 0.024, 8)
        gs.pipe([(xw, sy * 1.25, 1.9), (xw + sg * 0.07, sy * 1.25, 1.9), (xw + sg * 0.07, sy * 1.25, 2.9),
                 (xw, sy * 1.25, 2.9)], 0.014, 8)
    g.obj("coupler." + tag, "bogie", bevel=0.01)
    gc.obj("coupler.jumpers." + tag, "rubber", sharp=40)
    gs.obj("coupler.fittings." + tag, "steel", sharp=40)


# ---------------------------------------------------------------------------------------
# studio: a lower floor under the track, lights for a twenty meter car, views
# ---------------------------------------------------------------------------------------
def studio():
    S = K.STUDIO.objects
    S["cyc"].location.z = FLOOR_Z

    def put(name, loc, target, size, watts):
        o = S[name]
        o.location = loc
        K.aim(o, target)
        o.data.size, o.data.size_y = size
        o.data.energy = watts
        o.visible_camera = False                # a lamp seen through the windows from inside
        o.visible_transmission = False          # is a white hole in the picture
    put("top", (0.0, 0, 11.0), (0, 0, 0), (8.5, 24.0), 4000)
    put("key", (15.0, 9.0, 6.5), (8.0, 0, 2.0), (7.0, 4.0), 1500)
    put("rim", (-15.0, -8.0, 8.0), (-6.0, 0, 2.5), (9.0, 2.5), 1700)
    put("fill", (16.0, -7.0, 3.0), (9.0, 0, 2.0), (5.0, 3.0), 380)
    put("strip", (0.0, 8.0, 2.2), (0, 0, 2.2), (24.0, 0.8), 450)
    put("strip2", (0.0, -8.0, 2.2), (0, 0, 2.2), (24.0, 0.8), 450)


K.VIEWS["hero"].update(dir=(1.0, 0.60, 0.17), lens=40, focus=None, center=True)
K.VIEWS["rear"].update(dir=(-1.0, -0.62, 0.22), lens=40, focus=None, center=True)
K.VIEWS["side"].update(ortho=True)
K.VIEWS["top"].update(ortho=True)


def speckle(name, color, fleck, rough):
    """A floor: flecks in the color, a fine grain, darker where feet have worn it."""
    m, b = K.pbr(name, color, 0.0, rough)
    nt = m.node_tree
    tc = nt.nodes.new('ShaderNodeTexCoord')
    nz = nt.nodes.new('ShaderNodeTexNoise')
    nz.inputs["Scale"].default_value = 260.0
    nz.inputs["Detail"].default_value = 2.0
    mr = nt.nodes.new('ShaderNodeMapRange')
    mr.inputs["From Min"].default_value = 0.62
    mr.inputs["From Max"].default_value = 0.68
    big = nt.nodes.new('ShaderNodeTexNoise')
    big.inputs["Scale"].default_value = 1.3
    big.inputs["Detail"].default_value = 5.0
    wr = nt.nodes.new('ShaderNodeMapRange')
    wr.inputs["From Min"].default_value = 0.35
    wr.inputs["From Max"].default_value = 0.75
    wr.inputs["To Min"].default_value = 0.72
    wr.inputs["To Max"].default_value = 1.12
    mix = nt.nodes.new('ShaderNodeMixRGB')
    mix.inputs["Color1"].default_value = (*color, 1)
    mix.inputs["Color2"].default_value = (*fleck, 1)
    mul = nt.nodes.new('ShaderNodeMixRGB')
    mul.blend_type = 'MULTIPLY'
    mul.inputs["Fac"].default_value = 1.0
    bp = nt.nodes.new('ShaderNodeBump')
    bp.inputs["Strength"].default_value = 0.35
    bp.inputs["Distance"].default_value = 0.001
    for a_, b_ in ((tc.outputs["Object"], nz.inputs["Vector"]), (tc.outputs["Object"], big.inputs["Vector"]),
                   (nz.outputs["Fac"], mr.inputs["Value"]), (big.outputs["Fac"], wr.inputs["Value"]),
                   (mr.outputs["Result"], mix.inputs["Fac"]), (mix.outputs["Color"], mul.inputs["Color1"]),
                   (wr.outputs["Result"], mul.inputs["Color2"]), (mul.outputs["Color"], b.inputs["Base Color"]),
                   (nz.outputs["Fac"], bp.inputs["Height"]), (bp.outputs["Normal"], b.inputs["Normal"])):
        nt.links.new(a_, b_)


def weave(name, color):
    """Seat cloth: a fine grain."""
    m, b = K.pbr(name, color, 0.0, 0.9)
    nt = m.node_tree
    tc = nt.nodes.new('ShaderNodeTexCoord')
    nz = nt.nodes.new('ShaderNodeTexNoise')
    nz.inputs["Scale"].default_value = 700.0
    bp = nt.nodes.new('ShaderNodeBump')
    bp.inputs["Strength"].default_value = 0.5
    bp.inputs["Distance"].default_value = 0.001
    nt.links.new(tc.outputs["Object"], nz.inputs["Vector"])
    nt.links.new(nz.outputs["Fac"], bp.inputs["Height"])
    nt.links.new(bp.outputs["Normal"], b.inputs["Normal"])


INSIDE_VIEWS = ("aisle", "gangway", "vestibule", "bay", "cab", "access")


def daylight(name, before):
    """Inside views look out at a brighter studio, so the windows are not black."""
    if name not in INSIDE_VIEWS:
        return
    k = 1.0 if before else 0.0
    bg = next(n for n in K.SCN.world.node_tree.nodes if n.type == 'BACKGROUND')
    bg.inputs["Strength"].default_value = 0.30 + 1.2 * k
    for n in K.MAT["floor"].node_tree.nodes:
        if n.type == 'MAP_RANGE':
            n.inputs["To Max"].default_value = 0.22 + 1.3 * k


def inside(eye, look, lens):
    """A view from a point: where the eye is, what it looks at."""
    d = V3(eye) - V3(look)
    return dict(dir=tuple(d.normalized()), lens=lens, target=tuple(look), dist=d.length)


K.VIEWS.update(
    aisle=inside((-9.3, 0.12, 2.75), (0.0, 0.0, 2.45), 18),
    gangway=inside((-6.2, 0.2, 2.75), (-10.0, 0.0, 2.25), 20),
    vestibule=inside((1.05, -0.75, 2.75), (-0.1, 1.4, 2.35), 18),
    bay=inside((-1.5, -0.6, 2.6), (-3.6, 1.2, 1.95), 22),
    cab=inside((7.82, -0.62, 3.02), (9.70, 0.22, 2.10), 16),
    doorway=inside((1.2, 5.2, 2.5), (0.0, 1.0, 2.2), 35),
    access=inside((0.15, 0.6, 2.7), (2.3, -1.25, 1.9), 20),
    nose=dict(dir=(1.0, 0.55, 0.10), lens=50, target=(9.2, 0.0, 2.3), dist=9.0),
    door=dict(dir=(0.35, 1.0, 0.10), lens=50, target=(0.0, 1.4, 2.2), dist=7.0),
    bogie=dict(dir=(0.3, 1.0, 0.04), lens=60, target=(6.7, 1.2, 0.55), dist=5.5),
    tail=dict(dir=(-1.0, 0.45, 0.12), lens=50, target=(-9.6, 0.0, 2.3), dist=9.0),
)


def main():
    K.materials(paint=(0.56, 0.57, 0.58), paint_finish=(0.9, 0.36, 0.15),
                paint2=(0.86, 0.20, 0.02), paint2_finish="gloss",
                dust_amount=0.0, dust_z=(0.0, 0.5),
                glass=(0.42, 0.46, 0.48), glass_ior=1.25,
                led_front=(0.90, 0.96, 1.0), led_front_strength=150.0, led_accent=(0.20, 0.95, 0.80),
                seat=(0.10, 0.12, 0.16), interior=(0.50, 0.51, 0.52), decal=(0.80, 0.80, 0.78),
                screen=(0.30, 0.85, 0.95), floor=(0.10, 0.10, 0.11))
    K.paint("paint_dark", (0.045, 0.048, 0.055), (0.55, 0.42, 0.3), dust_amount=0.0)
    K.pbr("blackglass", (0.006, 0.006, 0.008), 0.0, 0.07)
    K.pbr("skirt", (0.035, 0.037, 0.04), 0.4, 0.5)
    K.pbr("railsteel", (0.30, 0.27, 0.24), 0.9, 0.42)
    K.pbr("wheelsteel", (0.33, 0.32, 0.31), 0.95, 0.35)
    K.pbr("bogie", (0.055, 0.057, 0.06), 0.5, 0.55)
    K.pbr("concrete", (0.36, 0.36, 0.35), 0.0, 0.85)
    K.pbr("insulator", (0.42, 0.20, 0.10), 0.0, 0.35)
    K.pbr("coverboard", (0.80, 0.62, 0.05), 0.0, 0.6)
    K.pbr("blackplastic", (0.012, 0.012, 0.014), 0.0, 0.4)
    K.pbr("lining", (0.60, 0.61, 0.61), 0.0, 0.55)
    K.pbr("lining_low", (0.33, 0.34, 0.36), 0.0, 0.5)
    K.pbr("doorlining", (0.52, 0.53, 0.54), 0.0, 0.45)
    K.pbr("trim_in", (0.16, 0.165, 0.17), 0.0, 0.45)
    K.pbr("ceil", (0.70, 0.70, 0.68), 0.0, 0.6)
    K.pbr("steel", (0.62, 0.62, 0.63), 1.0, 0.30)
    K.pbr("tread", (0.50, 0.50, 0.51), 0.9, 0.45)
    K.pbr("yellow", (0.85, 0.60, 0.02), 0.0, 0.5)
    speckle("floor_in", (0.075, 0.085, 0.10), (0.42, 0.44, 0.46), 0.60)
    K.pbr("under_eq", (0.16, 0.165, 0.17), 0.3, 0.55)
    K.pbr("damper", (0.55, 0.42, 0.04), 0.2, 0.4)
    K.pbr("cable", (0.85, 0.25, 0.02), 0.0, 0.5)
    K.pbr("bellows", (0.03, 0.03, 0.033), 0.0, 0.6)
    K.pbr("shell", (0.50, 0.51, 0.53), 0.0, 0.38)
    weave("fabric", (0.045, 0.06, 0.10))
    weave("fabric_p", (0.02, 0.22, 0.24))
    K.pbr("strap", (0.05, 0.05, 0.055), 0.0, 0.6)
    K.glass("glass_in", (0.55, 0.72, 0.70), 1.3)
    K.pbr("sign_blue", (0.02, 0.10, 0.45), 0.0, 0.5)
    K.pbr("sign_white", (0.82, 0.82, 0.80), 0.0, 0.5)
    K.pbr("sign_red", (0.65, 0.02, 0.015), 0.0, 0.4)
    K.pbr("sign_dark", (0.03, 0.03, 0.035), 0.0, 0.5)
    K.pbr("cab_lining", (0.22, 0.225, 0.23), 0.0, 0.6)
    K.pbr("desk", (0.05, 0.052, 0.056), 0.0, 0.45)
    K.pbr("cab_scr", (0.02, 0.04, 0.10), 0.0, 0.3,
          **{"Emission Color": (0.05, 0.16, 0.42, 1.0), "Emission Strength": 2.2})
    K.pbr("blind", (0.02, 0.02, 0.022), 0.0, 0.8)
    K.pbr("sign_yellow", (0.85, 0.66, 0.03), 0.0, 0.5)
    K.pbr("sign_yellowgreen", (0.70, 0.74, 0.05), 0.0, 0.5)
    K.pbr("sign_green", (0.02, 0.36, 0.14), 0.0, 0.5)
    K.pbr("ink_grey", (0.22, 0.22, 0.23), 0.0, 0.5)
    for nm, col, st in (("led_red", (1.0, 0.05, 0.03), 5.0), ("led_blue", (0.15, 0.45, 1.0), 6.0),
                        ("led_amber", (1.0, 0.55, 0.08), 7.0), ("lit_amber", (1.0, 0.55, 0.08), 6.0),
                        ("lit_white", (0.95, 0.97, 1.0), 4.5), ("lit_warm", (1.0, 0.85, 0.45), 4.5),
                        ("pis_bg", (0.02, 0.05, 0.16), 0.9), ("ad_red", (0.75, 0.05, 0.03), 0.8),
                        ("ad_blue", (0.03, 0.08, 0.55), 0.8), ("ad_yel", (0.95, 0.72, 0.05), 0.9),
                        ("ad_mag", (0.75, 0.04, 0.42), 0.8), ("ad_teal", (0.02, 0.42, 0.42), 0.8)):
        K.pbr(nm, tuple(c * 0.6 for c in col), 0.0, 0.4,
              **{"Emission Color": (*col, 1.0), "Emission Strength": st})
    K.pbr("led_run", (0.02, 0.02, 0.02), 0.0, 0.3,
          **{"Emission Color": (0.75, 0.92, 1.0, 1.0), "Emission Strength": 4.0})
    K.pbr("led_tail", (0.10, 0.004, 0.003), 0.0, 0.25,
          **{"Emission Color": (1.0, 0.03, 0.015, 1.0), "Emission Strength": 5.0})
    K.pbr("cam_feed", (0.02, 0.02, 0.02), 0.0, 0.4,
          **{"Emission Color": (0.35, 0.40, 0.42, 1.0), "Emission Strength": 1.6})
    K.pbr("lamp_head", (0.02, 0.02, 0.02), 0.0, 0.3,
          **{"Emission Color": (0.92, 0.96, 1.0, 1.0), "Emission Strength": 120.0})
    K.pbr("led_off", (0.05, 0.05, 0.055), 0.0, 0.3)
    K.pbr("accent", (0.02, 0.02, 0.02), 0.0, 0.3,
          **{"Emission Color": (0.15, 0.95, 0.85, 1.0), "Emission Strength": 6.0})
    K.pbr("light_cab", (0.02, 0.02, 0.02), 0.0, 0.3,
          **{"Emission Color": (1.0, 0.92, 0.80, 1.0), "Emission Strength": 30.0})
    K.pbr("light", (0.02, 0.02, 0.02), 0.0, 0.3,
          **{"Emission Color": (1.0, 0.96, 0.90, 1.0), "Emission Strength": 30.0})
    K.pbr("led_door", (0.02, 0.02, 0.02), 0.0, 0.3,
          **{"Emission Color": (0.25, 1.0, 0.45, 1.0), "Emission Strength": 8.0})
    build_skin()
    K.log("skin")
    build_envelope()
    build_end(-1)
    if MID:
        build_end(1)
    build_doors()
    K.log("envelope")
    build_seating()
    build_print()
    if not MID:
        build_cab()
    K.log("fittings")
    build_outside()
    K.log("outside")
    for tag, bx in (("f", BOGIE_X), ("r", -BOGIE_X)):
        build_bogie(tag, bx)
    build_underfloor()
    build_end_gear(-1)
    if MID:
        build_end_gear(1)
    K.log("running gear")
    build_track()
    K.after_studio(studio)
    K.on_view(daylight)
    # the wheels' flanges reach under the rail top; the layout inside is one-sided by
    # design (a facing bay left, the wheelchair space right, the extinguisher, the driver's
    # controller), and so are the motors, the traction rod, the cases under the floor, the
    # third rail's side of the track, the wiper and the aerials
    K.meant("ground", "bogie.*")
    K.meant("symmetry", "interior.*", "cab.*", "underfloor.*", "bogie.*", "roof.*", "wiper",
            "lettering.*", "sign.*", "nose.*", "door.*", "coupler.*")
    # what the open gangway and the doorways show of the inside is meant to be seen
    K.meant("through", "interior.*", "cab.*", "gangway.*")
    K.log("seats %d and %d tip-up, hand loops %d" % (COUNT["seats"], COUNT["tipups"], COUNT["loops"]))
    K.shoot(preview=("hero", "rear", "side", "front"),
            extra=dict(view="rear", size=(1000, 420), corner="br"))


main()
