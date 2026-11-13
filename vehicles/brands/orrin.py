"""Orrin's shared helpers: points and bands on the body by nearest point (snap, strip), the
pebble beads, the lune slots and lid wheel openings cut into the shell, the perforated dot
fields, lettering seen along an axis, the smooth stones of the cabins and the turbine disc
wheel.

Lifted from the Lumen, the Pebble and the Aria (the Aria's copies, the newest): snap, strip,
ring, lune, lid_cutter, pebble, both, text_proj, dot_field, stone, rim_at, disc (was
build_disc). Differences kept by parameters:

- snap: the Aria turns the normal toward the given point (its default); the Lumen and the
  Pebble turned it away from an axis segment instead (x clamped to +-half, at height z).
  setup(axis=(half, z)) picks that rule for the whole car, so strip and pebble, which snap
  inside, follow it too.
- ring: each car's station row has its own lines (8 on the Aria, 9 on the others), so the
  points between C and B are given as many as the car has: ring(x, c, *rows, b).
- lid_cutter: the Aria's defaults (a=0.425, y0=0.92); the Lumen 0.41 and 0.89, the Pebble
  0.322, z0=0.27 and 0.648.
- pebble: the Lumen's had no up (the default (0, 0, 1) is the same).
- rim_at: the car's PT and ORDER (pt, order); the Pebble measures along the U line (line),
  at 0.4 between edge and shoulder (at), no push off the skin (push=None), 0.018 under it
  (depth); the Aria passes its liner's own surface as tree.
- disc: the tire's sizes were the car's R, W, RIM; vanes, r_in (the vanes' inner radius),
  hub (three radii of the hub's face), sweep (the vanes' turn, degrees) and cap (the
  center ring) set the face, size=DISC_SMALL the Pebble's slimmer face throughout.

Added for the Pebble's step B: lune_cut (the Lumen's lune_cut, slots told to the checks),
NARROW (a narrow tire's tread, disc(tread=NARROW)).

Added for the Aria's step B, the Pebble's light channel parts (the Pebble keeps its own
copies): on_skin, taper_width, along, band, chop, seated (the Pebble's pebble on a seat
taken before the cuts) and channel_lamp (a ribbon's lens, lit face and sleeve in its
channel).

Covered by the kit: spline is carkit's spline() (the same code), re-exported. The kit's
snap() and strip() are newer, more general ones (objs, out), but snap's turn of the normal
differs from both Orrin rules, so the Orrin pair stays here.

Left in the cars: each hull's stations, probe (the Lumen's and the Pebble's differ, each
reads its own hull), the Aria's mir.
"""
import bpy
import carkit as K
from carkit import Geo, Matrix, V3, cos, on_body, pi, rad, sin

spline = K.spline

_AXIS = [None]          # setup()'s axis for snap's normals (None: toward the point)


def setup(axis=None):
    """How snap() turns its normals for this car: None toward the point given (give points
    a little outside the skin); axis=(half, z) away from the segment x in [-half, half] at
    height z on the centerline (a body round that segment)."""
    _AXIS[0] = axis


def snap(p, tree=None):
    """The nearest surface point to p (of every body piece, or of tree) and its normal,
    turned out of the body as setup() says."""
    if tree is None:
        if K._BVH[0] is None:
            K.body_bvh()
        tree = K._BVH[0]
    p = V3(p)
    loc, n, _, _ = tree.find_nearest(p)
    if _AXIS[0] is None:
        if (p - loc).length > 1e-5 and n.dot(p - loc) < 0:
            n = -n
    else:
        half, z = _AXIS[0]
        if n.dot(loc - V3((max(-half, min(half, loc.x)), 0, z))) < 0:
            n = -n
    return loc, n


def strip(g, ctrl, w, lift=0.0026, sink=-0.0003, taper=(0.0, 0.0), n=12):
    """A band of width w lying on the surface along a curve near it, its ends drawn out to
    points over the taper lengths. It stays above the skin (a light under it would shine
    into the shell, which has no thickness)."""
    P, N = [], []
    for q in spline(ctrl, n):
        loc, nn = snap(q)
        if not P or (loc - P[-1]).length > 1e-4:
            P.append(loc)
            N.append(nn)
    s = [0.0]
    for a, b in zip(P, P[1:]):
        s.append(s[-1] + (b - a).length)
    vs = []
    for i in range(len(P)):
        t = (P[min(i + 1, len(P) - 1)] - P[max(i - 1, 0)]).normalized()
        sd = N[i].cross(t).normalized()
        k = 1.0
        if taper[0]:
            k = min(k, (s[i] / taper[0]) ** 0.6)
        if taper[1]:
            k = min(k, ((s[-1] - s[i]) / taper[1]) ** 0.6)
        h = w * max(k, 0.06) / 2
        vs += [P[i] - N[i] * sink + sd * h, P[i] + N[i] * lift + sd * h,
               P[i] + N[i] * lift - sd * h, P[i] - N[i] * sink - sd * h]
    m = len(P)
    faces = [(4 * i + j, 4 * i + (j + 1) % 4, 4 * i + 4 + (j + 1) % 4, 4 * i + 4 + j)
             for i in range(m - 1) for j in range(4)]
    faces += [(0, 1, 2, 3), tuple(4 * (m - 1) + j for j in range(4))]
    g.add(vs, faces)


def ring(x, c, *rows):
    """A station at one x (or one x per line): z of C, (y, z) of each line between, z of B
    (the last argument)."""
    *mid, b = rows
    pts = [(0.0, c)] + list(mid) + [(0.0, b)]
    xs = x if isinstance(x, (list, tuple)) else [x] * len(pts)
    return [(xs[k], p[0], p[1]) for k, p in enumerate(pts)]


def lid_cutter(g, cx, top, a=0.425, z0=0.31, n=2.6, y0=0.92, depth=0.4):
    """A wheel opening: straight sides and a flattened arch for a top (a superellipse), so
    the body comes down over the tire like an eyelid."""
    b = top - z0
    pts = []
    for k in range(29):
        t = pi * k / 28
        c, s = cos(t), sin(t)
        pts.append((cx + a * (abs(c) ** (2 / n)) * (1 if c >= 0 else -1),
                    z0 + b * (s ** (2 / n))))
    for sgn in (1, -1):
        poly = ([V3((pts[0][0], sgn * y0, -0.3))] + [V3((x, sgn * y0, z)) for x, z in pts]
                + [V3((pts[-1][0], sgn * y0, -0.3))])
        g.prism(poly, (0, sgn * depth, 0))


def lune(g, a, b, d, toward, far, near, out=0.2, depth=0.04, flare=0.02, n=16):
    """A crescent slot for the cutters: the chord a to b seen about along d, both edges bowed
    toward `toward` (by far and by near), cut from outside to depth behind the chord. The
    slot widens by flare on its way in, so the panels' rims stay behind its walls."""
    a, b, d = V3(a), V3(b), V3(d).normalized()
    u = b - a
    ln = u.length
    u.normalize()
    d = (d - u * d.dot(u)).normalized()     # cut square to the chord: both tips on the skin
    v = d.cross(u).normalized()
    if v.dot(V3(toward)) < 0:
        v = -v
    ts = [k / n for k in range(n + 1)]
    hi = [a + u * ln * t + v * far * 4 * t * (1 - t) for t in ts]
    lo = [a + u * ln * t + v * near * 4 * t * (1 - t) for t in ts[1:-1]]
    hi2 = [p + v * flare * (4 * t * (1 - t)) ** 0.5 for p, t in zip(hi, ts)]
    lo2 = [p - v * flare * (4 * t * (1 - t)) ** 0.5 for p, t in zip(lo, ts[1:-1])]
    for sgn in (1, -1):
        dd = V3((d.x, sgn * d.y, d.z))
        rim = [V3((p.x, sgn * p.y, p.z)) for p in hi + lo[::-1]]      # lo[k] sits at 2n - k
        rim2 = [V3((p.x, sgn * p.y, p.z)) for p in hi2 + lo2[::-1]]
        m = 2 * n
        faces = [(k, (k + 1) % m, m + (k + 1) % m, m + k) for k in range(m)]
        for o in (0, m):                    # caps as a strip of quads between the two edges
            faces.append((o, o + 1, o + m - 1))
            faces += [(o + k, o + k + 1, o + m - k - 1, o + m - k) for k in range(1, n - 1)]
            faces.append((o + n - 1, o + n, o + n + 1))
        g.add([p + dd * out for p in rim] + [p - dd * depth for p in rim2], faces)


def lune_cut(g, a, b, d, toward, far, near, n=16, **kw):
    """lune(), and its outline on the skin told to the checks (K.CUTS: a slot cut on purpose,
    not a hole). Call it from build_body's cutters function, while the hull stands uncut.
    (The Lumen keeps a copy of its own.)"""
    lune(g, a, b, d, toward, far, near, n=n, **kw)
    a, b, d = V3(a), V3(b), V3(d).normalized()
    u = b - a
    ln = u.length
    u.normalize()
    d = (d - u * d.dot(u)).normalized()
    v = d.cross(u).normalized()
    if v.dot(V3(toward)) < 0:
        v = -v
    ts = [k / n for k in range(n + 1)]
    rim = ([a + u * ln * t + v * far * 4 * t * (1 - t) for t in ts]
           + [a + u * ln * t + v * near * 4 * t * (1 - t) for t in ts[-2:0:-1]])
    tree = K._tree(None)
    for sgn in (1, -1):
        dd = V3((d.x, sgn * d.y, d.z))
        Q = []
        for p in rim:
            p = V3((p.x, sgn * p.y, p.z))
            hit = tree.ray_cast(p + dd * 0.2, -dd, 0.4)[0]
            Q.append(hit if hit is not None else p)
        K.CUTS.append(Q + [Q[0]])


def pebble(g, at, a, b, h, seg=40, up=(0, 0, 1)):
    """A low oval bead on the surface at the point nearest `at`: a wide, b high, h proud."""
    loc, n = snap(at)
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


def both(half):
    """A left-side curve ending on the centerline, carried on round the right side."""
    half = [V3(p) for p in half]
    return half + [V3((p.x, -p.y, p.z)) for p in half[-2::-1]]


def text_proj(g, txt, size, u0, v0, proj, lift=0.0012, spacing=1.0):
    """Lettering on the body seen along proj (as carkit.on_body), reading left to right."""
    vs, fs = K.text_mesh(txt, size, spacing)
    sx = {'y': -1, 'Y': 1, 'x': 1, 'X': -1}[proj]
    out = []
    for p in vs:
        loc, n = on_body(u0 + sx * p.x, v0 + p.y, proj)
        if loc is None:
            return
        out.append(loc + n * lift)
    g.add(out, fs)


def dot_field(g, proj, u0, v0, hu, hv, pitch=0.0125, rmax=0.0044):
    """Perforations: a lens of dots that shrink toward its rim (seen along proj)."""
    rows = int(hv / (pitch * 0.866)) + 1
    for r in range(-rows, rows + 1):
        v = r * pitch * 0.866
        cols = int(hu / pitch) + 1
        for c in range(-cols, cols + 1):
            u = (c + (0.5 if r % 2 else 0.0)) * pitch
            f = 1.0 - (u / hu) ** 2 - (v / hv) ** 2
            if f <= 0.08:
                continue
            loc, n = on_body(u0 + u, v0 + v, proj)
            if loc is None:
                continue
            rad_ = rmax * min(1.0, f * 1.6) ** 0.5
            t = n.cross(V3((0, 0, 1)))
            t = t.normalized() if t.length > 1e-3 else V3((0, 1, 0))
            b = n.cross(t)
            o = len(g.v)
            g.v += [loc + n * 0.0009 + (t * cos(rad(a)) + b * sin(rad(a))) * rad_
                    for a in range(0, 360, 60)]
            g.f.append(tuple(range(o, o + 6)))


def stone(g, c, r, rot=None, n=2.6, seg=32, rows=16):
    """A smooth stone: a superellipsoid at c with half sizes r, turned by rot (a matrix)."""
    e = 2.0 / n

    def pw(v):
        return (abs(v) ** e) * (1 if v >= 0 else -1)

    xf = Matrix.Translation(V3(c)) @ (rot.to_4x4() if rot is not None else Matrix.Identity(4))
    vs = [(0, 0, -r[2])]
    for i in range(1, rows):
        ph = -pi / 2 + pi * i / rows
        for k in range(seg):
            th = 2 * pi * k / seg
            vs.append((r[0] * pw(cos(ph)) * pw(cos(th)), r[1] * pw(cos(ph)) * pw(sin(th)),
                       r[2] * pw(sin(ph))))
    vs.append((0, 0, r[2]))
    fs = [(0, 1 + (k + 1) % seg, 1 + k) for k in range(seg)]
    for i in range(rows - 2):
        a, b = 1 + i * seg, 1 + (i + 1) * seg
        fs += [(a + k, a + (k + 1) % seg, b + (k + 1) % seg, b + k) for k in range(seg)]
    top, a = len(vs) - 1, 1 + (rows - 2) * seg
    fs += [(a + k, a + (k + 1) % seg, top) for k in range(seg)]
    g.add(vs, fs, xf=xf)


def rim_at(x, tree=None, *, pt, order, line="S", at=0.35, push=(0, 0.03, 0.03), depth=0.016):
    """A point just under the paint below the glass edge at x: the liner's rim. pt and order
    are the car's station table; the stations are found along line, the point taken at
    between the E line and the S line, pushed by push before it is snapped (onto tree, else
    the body), depth under the skin."""
    xs = [pt[k][line].x for k in order]
    for a, b, xa, xb in zip(order, order[1:], xs, xs[1:]):
        if xb <= x <= xa:
            t = (xa - x) / (xa - xb)
            e = pt[a]["E"].lerp(pt[b]["E"], t)
            s = pt[a]["S"].lerp(pt[b]["S"], t)
            q = e.lerp(s, at)
            if push is not None:
                q = q + V3(push)
            loc, n = snap(q, tree)
            return loc - n * depth
    raise ValueError(x)


NARROW = dict(grooves=(-0.11, 0.11), gw=(0.009, 0.005), gd=0.008, mod=4, shift=2,
              inset=(0.002, 0.006), seg=144)
"""A road tread for a narrow tire (the Pebble's 0.185 m): the kit's "road" grooves fall
outside such a tire's crown, its profile folds back and its blocks stand 7 mm under the
ground. The same as Tanager's NARROW."""


# the disc's face: the profile's offsets (from the rim and from the tire's half width:
# rim1, out1, rim2, out2, rim3, out3, hub_out, back, back_rim, rim_end), the vanes' outer
# radius under the rim, their offset and half section, the rings' offsets
DISC = dict(face=(0.007, 0.012, 0.017, 0.036, 0.022, 0.038, 0.014, 0.08, 0.03, 0.02),
            r_out=0.026, vane_y=0.026, vane=(0.0016, 0.010), rings=(0.0375, 0.033, 0.012, 0.008))
DISC_SMALL = dict(face=(0.006, 0.011, 0.014, 0.032, 0.018, 0.034, 0.013, 0.07, 0.026, 0.018),
                  r_out=0.022, vane_y=0.023, vane=(0.0014, 0.009),
                  rings=(0.0335, 0.029, 0.010, 0.007))


def disc(tag, cx, out_y, side, vanes=60, *, R, W, rim, r_in=0.118, hub=(0.102, 0.072, 0.040),
         sweep=40, cap=(0.026, 0.035), size=DISC, tread="road"):
    """The Orrin turbine disc on the kit's tire (radius R, width W, rim radius rim, its outer
    face at y out_y): a smooth face, vanes curved sweep degrees from r_in out to the rim, a
    lit ring at each end of them. The kit's rim and hub are taken away. tread: a kit tread
    or NARROW."""
    RIM = rim
    K.build_wheel(tag, cx, R, W, RIM, out_y, side, style="disc", ring=None, caliper=None,
                  tread=tread)
    for part in ("rim.", "hub."):
        ob = bpy.data.objects[part + tag]
        me = ob.data
        bpy.data.objects.remove(ob)
        bpy.data.meshes.remove(me)
    hw = W / 2
    flip = side < 0
    loc = (cx, side * (out_y - hw), R)
    f = size["face"]
    r_out = RIM - size["r_out"]
    g = Geo()
    g.lathe([(-hw + 0.03, RIM), (hw - 0.006, RIM), (hw - 0.004, RIM - f[0]),
             (hw - f[1], RIM - f[2]), (hw - f[3], RIM - f[4]), (hw - f[5], r_in - 0.004),
             (hw - f[6], hub[0]), (hw - 0.008, hub[1]), (hw - 0.004, hub[2]), (hw - 0.003, 0.004),
             (hw - f[7], 0.004), (hw - f[7], RIM - f[8]), (-hw + 0.03, RIM - f[9])], 96)
    g.obj("rim." + tag, "wheel_face", flip_y=flip, loc=loc, sharp=35)
    g = Geo()
    vw, vh = size["vane"]
    for k in range(vanes):
        a0 = 2 * pi * k / vanes
        path = []
        for q in range(6):
            fq = q / 5
            a = a0 + rad(sweep) * fq ** 1.3
            r = r_in + (r_out - r_in) * fq
            path.append((r * cos(a), hw - size["vane_y"] + 0.004 * fq, r * sin(a)))
        g.sweep(path, [(-vw, -vh), (vw, -vh), (vw, vh), (-vw, vh)], up=(0, 1, 0))
    g.lathe([(hw - 0.0025, cap[0]), (hw - 0.0025, cap[1]), (hw - 0.0005, cap[1]),
             (hw - 0.0005, cap[0])], 40)
    g.obj("vanes." + tag, "wheel_vane", flip_y=flip, loc=loc, sharp=40)
    g = Geo()
    y0, y1, d_out, d_in = size["rings"]
    g.lathe([(hw - y0, r_out - d_out), (hw - y0, r_out + 0.003),
             (hw - y1, r_out + 0.003), (hw - y1, r_out - d_out)], 96)
    g.lathe([(hw - y0, r_in - 0.003), (hw - y0, r_in + d_in),
             (hw - y1, r_in + d_in), (hw - y1, r_in - 0.003)], 64)
    g.obj("ring." + tag, "led_wheel", flip_y=flip, loc=loc)


def on_skin(ctrl, n=12, lift=0.004):
    """The smooth curve through ctrl laid on the skin, each point lift outside it (so the
    kit's trace() turns its normals out)."""
    out = []
    for q in spline(ctrl, n):
        loc, nn = snap(q)
        if not out or (loc - out[-1][0]).length > 1e-4:
            out.append((loc, nn))
    return [q + nn * lift for q, nn in out]


def taper_width(t, ln, w, tip, taper):
    """A channel's width at share t of its run, ln long: w, drawn out to tip over the
    taper lengths (start, end) at its ends."""
    k = 1.0
    if taper[0]:
        k = min(k, (t * ln / taper[0]) ** 0.6)
    if taper[1]:
        k = min(k, ((1 - t) * ln / taper[1]) ** 0.6)
    return tip + (w - tip) * max(0.0, k)


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


def chop(ob, tr, step=0.045, near=0.06):
    """A channel's walls cut into loose pieces step long across its path tr (the same
    surface): a game pack's LOD2 and LOD3 leave pieces under 5 cm out, where a whole wall
    of thin sheet collapses into dark shards over the paint. Each cut splits only the faces
    within near of its point (the Pebble's copy splits the whole object at every cut)."""
    import bmesh
    bm = bmesh.new()
    bm.from_mesh(ob.data)
    xf = ob.matrix_world.inverted()
    P = [xf @ q for q, _ in tr]
    ln = sum((b - a).length for a, b in zip(P, P[1:]))
    s, last, cuts = 0.0, 0.0, set()
    for a, b in zip(P, P[1:]):
        s += (b - a).length
        if s - last < step or s > ln - 0.01:        # the last piece no longer than step
            continue
        last = s
        # only the faces near this point: a plane through the whole object would split the
        # channel everywhere it crosses it again (the other side, a turn), for nothing
        faces = [f for f in bm.faces if any((v.co - b).length < near for v in f.verts)]
        edges = list({e for f in faces for e in f.edges})
        verts = list({v for f in faces for v in f.verts})
        res = bmesh.ops.bisect_plane(bm, geom=verts + edges + faces, plane_co=b,
                                     plane_no=(b - a).normalized(), dist=1e-6)
        for e in res["geom_cut"]:          # only the cut across the channel here
            if isinstance(e, bmesh.types.BMEdge) and all((v.co - b).length < 0.05
                                                          for v in e.verts):
                cuts.add(e)
    bmesh.ops.split_edges(bm, edges=[e for e in cuts if e.is_valid])
    bm.to_mesh(ob.data)
    bm.free()
    ob.data.update()


def seated(g, seat, a, b, h, seg=40, up=(0, 0, 1)):
    """pebble() on a seat (point, normal) taken before the cuts: a low oval bead a wide, b
    high, h proud."""
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


def channel_lamp(name, tr, w, depth, gap, lit="led_front", lens="lens_clear", step=0.008,
                 sink=0.0):
    """A ribbon in its channel (traced path tr, width w(share)): a flush lens with the
    body's gap each side (a lens cut from the skin keeps the boolean's slivers), a light
    guide's lit face right under it, 3 mm wider than the channel's mouth with its edges
    tucked under the paint (a far LOD that moves the mouth shows light, not a slit), and a
    frosted sleeve behind it. sink: the lens set that far under the skin (a flat lens's
    edges stand proud where the skin curves tightly across the channel)."""
    if len(tr) < 2:
        return
    ln = sum((b[0] - a[0]).length for a, b in zip(tr, tr[1:]))
    fr = along(tr, 0.003, ln - 0.003, step)

    def wf(f):
        return w(f[4])
    L = K.Lamp(name, lit=lit, glass=lens)
    band(L.glass, fr, lambda f: wf(f) - 2 * gap, lambda f: sink, lambda f: sink + 0.003)
    band(L.emit(), fr, lambda f: wf(f) + 0.003, lambda f: sink + 0.0032,
         lambda f: sink + 0.0032 + wf(f) * 0.18)
    band(L.optic, fr, lambda f: wf(f) * 0.70, lambda f: sink + 0.0032 + wf(f) * 0.18,
         lambda f: depth - 0.0005)
    L.obj()
