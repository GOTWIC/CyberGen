"""Aurel Prelate: a formal 2 + 2 coupe, the first Aurel (both names made up), built on
vehicles/carkit.py.

Run (always through the wrapper, one Blender job at a time on this machine):
    vehicles/blender.sh vehicles/cars/aurel_prelate.py --out DIR --preview
    vehicles/blender.sh vehicles/cars/aurel_prelate.py --out DIR --sheet

A monolith on a fluted plinth: a slab nose and a slab tail, one razor shoulder crease from
blade light to blade light, a very long hood, an upright glass house set far back, a short
deck, the glass one folded canopy with a single leaning pillar in body color. The
"grille" is no opening: slots of light let into the slab, hanging from its top edge in a
lozenge that folds over the edge onto the hood.
Ten character lines over twelve stations; every detail hangs on the body as built.

The lamps are cut into the skin while the hull stands uncut (cutters()): every slot of the
lozenge is a channel under a flush lens with a light guide right under it, each corner
blade a pocket under one lens with a lit guide between stacked reflector facets and two
bright liners, the hairline round each corner a channel of its own. The door pulls are
recesses, the charge flaps cut through the quarters. The brand's helpers (the slab frame,
the crest, the disc wheel, the studio's light links, the serif) are in
vehicles/brands/aurel.py.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import carkit as K                                                  # noqa: E402
from functools import partial                                       # noqa: E402
from brands import aurel                                            # noqa: E402
from brands.aurel import Slab, crest                                # noqa: E402
from carkit import (Geo, Matrix, V3, cos, on_body, pi, rad, ribbon, sin,       # noqa: E402
                    text_flat, text_on_body)

# ---------------------------------------------------------------------------------------
# dimensions
# ---------------------------------------------------------------------------------------
FA_X, RA_X = 1.84, -1.36            # axles: wheelbase 3.20
T_R, T_W, T_RIM = 0.40, 0.270, 0.315    # tire radius, width, rim radius
OUT_Y = 0.958                       # outer face of the tires
ARCH_R = 0.448
ARCH = tuple(range(-20, 201, 5))
NOSE_X, TAIL_X = 2.585, -2.585      # the slabs at shoulder height
PITCH = 0.022                       # the plinth's flutes
Z_STRIP = 0.3225                    # the bright strip on the sill line
Z_FL0, Z_FL1 = 0.185, 0.305         # the flutes' foot and head
GAP = 0.00175                       # shut lines 3.5 mm
SLOT_W, SLOT_D = 0.010, 0.010       # a light slot's channel: width and depth
BLADE_W, BLADE_D = 0.034, 0.030     # a corner blade's pocket: width and depth
LAMP = {}                           # the lamps' channels and pockets on the uncut skin
SLABS = {}                          # the end slabs' frames, taken on the uncut hull

build_wheel = partial(aurel.wheel, R=T_R, w=T_W, rim=T_RIM, out=OUT_Y)


def nose_x(z):
    """The nose slab leans forward: its top is ahead of its foot."""
    return NOSE_X - (0.89 - z) * 0.07


def tail_x(z):
    """The tail slab leans back the same way: both ends overhang the plinth."""
    return TAIL_X + (0.865 - z) * 0.06


# ---------------------------------------------------------------------------------------
# body: stations and character lines
# ---------------------------------------------------------------------------------------
LINES = "CHGSULKRFB"
#        C centerline top, H hood flow line / A-pillar / roof edge, G hood edge / glass base,
#        S the razor shoulder, U widest line, L sill line, K foot of the sill step,
#        R plinth bottom, F floor edge, B floor centerline
ORDER = ["N0", "N1", "A1", "A2", "W0", "W1", "RM", "CP", "RR", "RG", "DK", "T0"]
PT = {}


def low(x, sz, w=0.0, zf=0.15):
    """The six lower lines of a station: shoulder, widest, sill, step, plinth, floor."""
    return [(x, .95 + w, sz), (x, .98 + w, .60), (x, .97 + w, .33), (x, .95 + w, .315),
            (x, .94 + w, .17), (x, .80, zf), (x, 0, zf)]


def stations():
    def end(fx, zs, ys):
        return [(fx(z), y, z) for z, y in zip(zs, ys)]
    T = {
        "N0": end(nose_x, (.945, .942, .925, .89, .60, .33, .315, .17, .15, .15),
                  (0, .58, .84, .925, .955, .945, .925, .915, .78, 0)),
        "N1": [(2.30, 0, .955), (2.30, .62, .952), (2.30, .865, .932)] + low(2.30, .892, -.003),
        "A1": [(1.78, 0, .965), (1.78, .68, .962), (1.78, .875, .940)] + low(1.78, .894),
        "A2": [(1.20, 0, .975), (1.20, .74, .970), (1.20, .880, .943)] + low(1.20, .895),
        "W0": [(.38, 0, .985), (.27, .80, .955), (.25, .878, .940)] + low(.30, .895),
        "W1": [(-.04, 0, 1.305), (-.10, .74, 1.275), (-.08, .885, .937)] + low(-.08, .895),
        "RM": [(-.85, 0, 1.325), (-.85, .745, 1.290), (-.85, .885, .934)] + low(-.85, .893),
        # the pillar leans with the rear glass: a band of one width from roof to shoulder
        "CP": [(-1.45, 0, 1.318), (-1.45, .74, 1.283), (-1.78, .885, .928)] + low(-1.50, .890),
        "RR": [(-1.80, 0, 1.295), (-1.77, .735, 1.262), (-1.95, .885, .925)] + low(-1.85, .886),
        "RG": [(-2.16, 0, .958), (-2.10, .80, .945), (-2.09, .875, .925)] + low(-2.12, .882),
        "DK": [(-2.38, 0, .948), (-2.38, .66, .943), (-2.38, .86, .913)] + low(-2.38, .873, -.006),
        "T0": end(tail_x, (.930, .927, .905, .865, .60, .33, .315, .18, .16, .16),
                  (0, .60, .83, .915, .945, .935, .915, .905, .78, 0)),
    }
    S = K.fill([T[k] for k in ORDER])
    PT.update(K.table(ORDER, LINES, S))
    return S


PMAT = dict(hood="paint", fender="paint", door="paint", quarter="paint", deck="paint",
            canopy="glass", glass_side="glass",
            trim_ws="gloss_black", trim_b="bright", sill="flute", floor="underbody",
            well="well", pull="gloss_black", cut="void")


def panel_of(i, j):
    if j >= 7:
        return "floor"
    if j >= 5:
        return "sill"
    if j == 0:
        return "hood" if i <= 3 else "deck" if i >= 9 else "canopy"
    if j == 1:
        return ("hood", "hood", "hood", "hood", "glass_side", "glass_side", "glass_side",
                "quarter", "quarter", "deck", "deck")[i]
    if j == 2 and i <= 3:
        return "hood"               # a clamshell: its cut hides in the shoulder crease
    if j == 2 and i >= 9:
        return "deck"
    return "fender" if i <= 3 else "door" if i <= 5 else "quarter"


def line_crease(i, j):
    """Crease of the edge along line j from station i to i + 1."""
    if j == 1:
        return 1.0 if 4 <= i <= 8 else 0.0
    if j == 2:                      # glass base; on the hood and deck the chamfer's inner edge
        return 1.0
    if j in (3, 5, 6, 7, 8):
        return 1.0
    return 0.0


def station_crease(i, j):
    """Crease of the edge on station i between lines j and j + 1."""
    if i in (0, 11):
        return 1.0
    if i in (4, 9):
        return 1.0 if j <= 1 else 0.0
    if i in (5, 8):
        return 1.0 if j == 0 else 0.0
    if i == 7:
        return 1.0 if j == 1 else 0.0
    return 0.0


# ---------------------------------------------------------------------------------------
# what is cut into the hull: the lozenges' slots, the blades, the pulls, the flaps, room
# round the tires
# ---------------------------------------------------------------------------------------
def lozenge_cuts(gs, gh, sl, key, kmax, z0, sx, lmax, pitch=0.030, ztop=1.0):
    """The Aurel grille (brands.aurel.lozenge's layout) with its slots cut: every lit slot
    a channel in the slab hanging from its top edge and one on the hood (the deck) running
    back from it, the edge itself left whole between them (the slab's cutters in gs, the
    hood's in gh). The unlit hairline flutes between the slots are kept for later, laid on
    the body as built."""
    proj = 'x' if sx > 0 else 'X'
    LAMP[key] = []
    LAMP[key + ".flutes"] = []

    def edge(y):                            # the slab's top edge over a slot
        z = ztop
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
            LAMP[key].append(K.groove(gs, [sl.at(y, zb), sl.at(y, z1)], width=SLOT_W,
                                      depth=SLOT_D, step=0.04))
            LAMP[key].append(K.groove(gh, [(xs, y), (xe, y)], 'z', width=SLOT_W,
                                      depth=SLOT_D, step=0.04))
        else:
            LAMP[key + ".flutes"].append((y, zb, z1, xs, xe))

    for k in range(-kmax, kmax + 1):
        slot(k * pitch, True)
        if k < kmax:
            slot((k + 1 / 3) * pitch, False)
            slot((k + 2 / 3) * pitch, False)


def blade_cut(g, sl, key, y, z0, z1):
    """A corner blade's pocket: a slim slot from z0 to z1 in the slab, under one lens."""
    proj = 'x' if sl.n.x > 0 else 'X'
    LAMP[key] = (K.pocket(g, K.rounded(y, (z0 + z1) / 2, BLADE_W, z1 - z0 + 0.03, 0.006), proj,
                          depth=BLADE_D, mirror=True), y, z0, z1)


def cutters():
    """Everything cut into the hull, laid on it while it stands uncut."""
    wells, room = Geo(), Geo()
    K.well_cutter(wells, FA_X, T_R, ARCH_R, 0.62, ARCH)
    K.well_cutter(wells, RA_X, T_R, ARCH_R, 0.62, ARCH)
    # room for the steered front wheels inside the skin: the well a little wider and deeper
    # in behind the arch, which keeps its line
    K.well_cutter(room, FA_X, T_R, 0.468, 0.51, ARCH, depth=0.36)
    sl, st = Slab('x', 0.60), Slab('X', 0.60)
    SLABS["f"], SLABS["r"] = sl, st
    front, rear, hood, deck = Geo(), Geo(), Geo(), Geo()
    lozenge_cuts(front, hood, sl, "loz_f", 25, 0.385, 1, 0.52)
    lozenge_cuts(rear, deck, st, "loz_r", 17, 0.50, -1, 0.24)
    blade_cut(front, sl, "blade_f", 0.878, 0.385, 0.855)
    blade_cut(rear, st, "blade_r", 0.868, 0.385, 0.835)
    # the hairline of light round each corner, on the flank beside its slab: a slot under
    # its own lens (a pocket: a groove there left slivers that the panel's rim pushed out)
    for g, x, z0, z1, key in ((front, 2.516, 0.40, 0.84, "side_f"),
                              (rear, -2.510, 0.40, 0.815, "side_r")):
        K.pocket(g, K.rounded(x, (z0 + z1) / 2, SLOT_W, z1 - z0), 'y', depth=SLOT_D,
                 mirror=True)
        LAMP[key] = K.trace([(x, z0), (x, z1)], 'y', step=0.03)
    # the door pulls: a recess under the shoulder with a bright bar in it
    pulls = Geo()
    LAMP["pull"] = K.pocket(pulls, K.rounded(-0.67, 0.800, 0.21, 0.030), 'y', depth=0.014,
                            mirror=True)
    # the charge flaps: the crest's outline cut through each rear quarter
    cut = Geo()
    K.groove(cut, [(-2.30, 0.745), (-2.335, 0.69), (-2.30, 0.635), (-2.265, 0.69)], 'y',
             closed=True, mirror=True)
    # the lamps' channels and pockets are recesses in the panel they are cut into, its own
    # surface run down into them (no edge of a panel round each, which a game pack's far
    # LODs must keep: as panels of their own the 172 slots held its LOD3 at twice its
    # budget); their lenses are built apart, the body's gap all round (a lens cut from the
    # skin keeps the boolean's slivers)
    return [(wells, "well"), (room, "well"), (front, "fender", "into"), (hood, "hood", "into"),
            (rear, "quarter", "into"), (deck, "deck", "into"), (pulls, "pull"),
            (cut, "cut", "drop")]


def shrink(bm, d):
    """The kit's shrink() (a panel's open boundary pulled in by d, in the surface, for the
    gaps) with each face's way in taken from its neighbors where the face is a sliver the
    cuts left (under 4 mm2: its own normal is noise, and its edge was pushed out of the
    surface as a fin or over a lamp's channel), and every move kept in the surface."""
    bm.normal_update()

    def fnorm(f):
        if f.calc_area() > 4e-6:
            return f.normal
        acc = V3()
        for v in f.verts:
            for g in v.link_faces:
                if g is not f and g.calc_area() > 4e-6:
                    acc += g.normal * g.calc_area()
        return acc.normalized() if acc.length > 1e-12 else f.normal

    mv, vn = {}, {}
    for f in bm.faces:
        fn = None
        for lp in f.loops:
            if len(lp.edge.link_faces) != 1:
                continue
            fn = fn or fnorm(f)
            a, b = lp.vert, lp.link_loop_next.vert
            inw = fn.cross(b.co - a.co).normalized()
            mv.setdefault(a, []).append(inw)
            mv.setdefault(b, []).append(inw)
    for v in mv:
        acc = V3()
        for g in v.link_faces:
            if g.calc_area() > 4e-6:
                acc += g.normal * g.calc_area()
        vn[v] = acc.normalized() if acc.length > 1e-12 else None
    for v, ns in mv.items():
        if len(ns) == 2:
            o = (ns[0] + ns[1]) / max(1 + ns[0].dot(ns[1]), 0.3)
        else:
            o = sum(ns, V3()) / len(ns)
        n = vn[v]
        if n is not None:
            o -= n * o.dot(n)
        v.co += o * d


def unflip(ob):
    """Turns back the few sliver faces a cut leaves facing into the car where the panel's
    gap shrinks them past a fold (a few square millimeters at a channel's edge): the panel's
    rim would push them out through the paint as fins."""
    import bmesh
    bm = bmesh.new()
    bm.from_mesh(ob.data)
    n0 = len(bm.faces)
    bmesh.ops.dissolve_degenerate(bm, dist=0.001, edges=bm.edges[:])
    bm.normal_update()
    bad = []
    for f in bm.faces:
        nb = [g for e in f.edges for g in e.link_faces if g is not f]
        if not nb:
            continue
        avg = sum((g.normal * g.calc_area() for g in nb), V3())
        if (avg.length > 1e-12 and f.calc_area() < avg.length * 0.5
                and f.normal.dot(avg) < -0.5 * avg.length):
            bad.append(f)
    if bad:
        bmesh.ops.reverse_faces(bm, faces=bad)
    if bad or len(bm.faces) != n0:
        bm.to_mesh(ob.data)
        K.log("%s: %d sliver faces dissolved, %d turned back" % (ob.name, n0 - len(bm.faces),
                                                              len(bad)))
    bm.free()


def build_hull():
    K.shrink = shrink                   # this car's gaps round the many cuts (above)
    body = K.build_body(
        stations(), panel_of, PMAT, line_crease, station_crease,
        front=dict(kind="flat", panel="fender"), rear=dict(kind="flat", panel="quarter"),
        glass=[("canopy", 0.022, "trim_ws", "frame"), ("glass_side", 0.014, "trim_b", "frame")],
        cutters=cutters, subdiv=3, gap=GAP)
    for pn in ("hood", "fender", "door", "quarter", "deck", "sill"):
        if pn in body.parts:
            unflip(body.parts[pn])


# ---------------------------------------------------------------------------------------
# the lamps in their channels and pockets
# ---------------------------------------------------------------------------------------
def inset(tr, d):
    """A traced path [(point, way out)] with d taken off both ends."""
    P = [q for q, _ in tr]
    if len(P) < 2:
        return tr
    a = P[0] + (P[1] - P[0]).normalized() * d
    b = P[-1] + (P[-2] - P[-1]).normalized() * d
    mid = [(q, n) for q, n in tr[1:-1] if (q - P[0]).length > d and (q - P[-1]).length > d]
    return [(a, tr[0][1])] + mid + [(b, tr[-1][1])]


def guide_in(L, tr, w, top=0.0032, h=0.002, sleeve=0.003):
    """A channel's flush lens (the body's gap all round it) and a light guide under it: its
    lit face right under the lens, as wide as it, and a frosted sleeve behind it."""
    lens = inset(tr, GAP)
    if len(lens) < 2:
        return
    P, N = [q for q, _ in lens], [n for _, n in lens]
    hl = w / 2 - GAP
    L.glass.sweep(P, [(-hl, -0.003), (hl, -0.003), (hl, 0.0), (-hl, 0.0)], up=N)
    tr = inset(tr, GAP + 0.0005)
    P, N = [q for q, _ in tr], [n for _, n in tr]
    hw = (w - 2 * GAP - 0.0005) / 2
    L.emit().sweep(P, [(-hw, -top - h), (hw, -top - h), (hw, -top), (-hw, -top)], up=N)
    if sleeve:
        hs = hw * 0.8
        L.optic.sweep(P, [(-hs, -top - h - sleeve), (hs, -top - h - sleeve), (hs, -top - h),
                          (-hs, -top - h)], up=N)


def tilted(sl, tilt):
    """A frame on a slab turned about its width: n and the up vector tipped by tilt."""
    c, s = cos(rad(tilt)), sin(rad(tilt))
    n = sl.n * c + sl.eu * s
    u = sl.eu * c - sl.n * s
    return Matrix((n, sl.ey, u)).transposed()


def blade_lamp(L, sl, y, z0, z1):
    """Inside a blade's pocket, under its lens: a lit guide down the middle right under
    the lens in a frosted sleeve, stacked reflector facets either side of it, a bright
    liner on each long wall (the brand's two bright edges) and a bright cap at each end."""
    zc, H = (z0 + z1) / 2, z1 - z0
    out = K.rounded(y, zc, BLADE_W - 2 * GAP, H + 0.03 - 2 * GAP, 0.006 - GAP)
    L.glass.prism([sl.at(u, v) for u, v in out], -sl.n * 0.003)
    sl.box(L.emit(), y, zc, -0.0052, (0.004, 0.0055, H))
    sl.box(L.optic, y, zc, -0.0110, (0.0076, 0.0082, H + 0.004))
    rot = tilted(sl, 32)
    z = z0 - 0.004
    while z <= z1 + 0.004:
        for s in (-1, 1):
            L.chrome.box(sl.at(y + s * 0.0098, z, -0.0115), (0.017, 0.0094, 0.0009), rot=rot)
        z += 0.0115
    for s in (-1, 1):
        sl.box(L.chrome, y + s * 0.0158, zc, -0.0150, (0.026, 0.0008, H + 0.026))
    for z in (z0 - 0.011, z1 + 0.011):
        sl.box(L.chrome, y, z, -0.0150, (0.026, 0.031, 0.0012))


def build_lamps():
    for key, lit in (("f", "led_front"), ("r", "led_rear")):
        sl = SLABS[key]
        # the lozenge: a guide in every slot
        lens = "lens_clear" if key == "f" else "lens_red"
        L = K.Lamp("lamp.lozenge_" + key, lit=lit, glass=lens)
        for tr in LAMP["loz_" + key]:
            guide_in(L, tr, SLOT_W, sleeve=0)
        L.obj()
        # the corner blades
        pk, y, z0, z1 = LAMP["blade_" + key]
        if pk is not None:
            L = K.Lamp("lamp.blade_" + key, lit=lit, glass=lens)
            blade_lamp(L, sl, y, z0, z1)
            L.obj(mirror=True)
        # the hairline round the corner
        L = K.Lamp("lamp.side_" + key, lit=lit, glass=lens)
        guide_in(L, LAMP["side_" + key], SLOT_W)
        L.obj(mirror=True)
        # the bright hairline flutes between the slots, on the body as built
        gv = Geo()
        for y, zb, z1, xs, xe in LAMP["loz_%s.flutes" % key]:
            sl.box(gv, y, (zb + z1) / 2, 0.0006, (0.0012, 0.0025, z1 - zb))
            ribbon(gv, [(xs, y), (xe, y)], 'z', 0.0025, lift=0.0006)
        gv.obj("lozenge.flutes." + key, "bright")


# ---------------------------------------------------------------------------------------
# the ends: the plinth across them, the crest, the wordmark, the plate
# ---------------------------------------------------------------------------------------
def build_slabs():
    sl, st = SLABS["f"], SLABS["r"]
    # ---- the plinth across both ends: a dark band, its flutes, the bright strip
    for s, tag, hw in ((sl, "f", 0.905), (st, "r", 0.895)):
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
    p, n = on_body(1.94, 0.0, 'z')
    crest(gb, gd, p + n * 0.0005, (0, 1, 0), (1, 0, 0), 0.046)
    gb.obj("crest", "bright", bevel=0.0006)
    gd.obj("crest.inlay", "gloss_black")
    g = Geo()
    text_flat(g, "A U R E L", 0.046, st.at(0.57, 0.60, 0.0015), st.right, st.eu, spacing=1.2)
    text_flat(g, "PRELATE", 0.027, st.at(-0.57, 0.60, 0.0015), st.right, st.eu, spacing=1.5)
    g.obj("wordmark", "bright")
    # ---- plate
    g = Geo()
    st.box(g, 0, 0.400, 0.004, (0.008, 0.30, 0.085))
    g.obj("plate", "gloss_black", bevel=0.002)
    g = Geo()
    text_flat(g, "AU 1-077", 0.045, st.at(0, 0.400, 0.0088), st.right, st.eu, spacing=1.15)
    g.obj("plate.glyphs", "decal")


# ---------------------------------------------------------------------------------------
# the plinth along the flanks, trims, small details
# ---------------------------------------------------------------------------------------
def flank_runs():
    """The stretches of the flank between the slabs and the wheel arches."""
    e = ARCH_R + 0.012
    return [(2.52, FA_X + e), (FA_X - e, RA_X + e), (RA_X - e, -2.52)]


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
            if lo is None or hi is None or lo.y < 0.8 or hi.y < 0.8:
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
            if p is not None and p.y > 0.8:
                path.append(V3((x, p.y + 0.003, Z_STRIP)))
        gs.sweep(path, [(-0.007, -0.0065), (0.007, -0.0065), (0.007, 0.0065), (-0.007, 0.0065)],
                 up=(0, 0, 1))
    g.obj("plinth.flutes", "flute", mirror=True)
    gs.obj("plinth.strip", "bright", bevel=0.0015, mirror=True)


def build_details():
    # ---- the spear: a bright hairline from the crest down the hood
    g = Geo()
    ribbon(g, [(1.885, 0.0), (0.33, 0.0)], 'z', 0.010, lift=0.0012)
    g.obj("spear", "bright")
    # ---- door pull: a bright bar in its recess, under the shoulder
    pk = LAMP["pull"]
    if pk is not None:
        a, b = pk.on(-0.58, 0.800, back=0.006), pk.on(-0.76, 0.800, back=0.006)
        if a is not None and b is not None:
            g = Geo()
            g.sweep([a, b], [(-0.004, -0.005), (0.004, -0.005), (0.004, 0.005), (-0.004, 0.005)],
                    up=(0, 0, 1))
            g.obj("pull", "bright", bevel=0.0015, mirror=True)
    # ---- mirrors: a camera blade on a bright stalk at the foot of the A-pillar
    g = Geo()
    g.sweep([(0.18, 0.905, 0.925), (0.165, 0.990, 0.955)],
            [(-0.022, -0.004), (0.022, -0.004), (0.022, 0.004), (-0.022, 0.004)], up=(0, 0, 1))
    g.obj("mirror.stalk", "bright", bevel=0.0015, mirror=True)
    g = Geo()
    g.hexa([(0.225, 0.972, 0.938), (0.225, 1.000, 0.938), (0.085, 1.008, 0.932),
            (0.085, 0.966, 0.932), (0.215, 0.974, 0.985), (0.215, 0.998, 0.985),
            (0.085, 1.004, 0.992), (0.085, 0.968, 0.992)])
    g.obj("mirror.pod", "paint", bevel=0.004, mirror=True)
    g = Geo()
    g.box((0.0835, 0.986, 0.962), (0.004, 0.030, 0.046))
    g.obj("mirror.lens", "gloss_black", mirror=True)
    # ---- crest on the pillar, model name low on the fender
    gb, gd = Geo(), Geo()
    p, n = on_body(-1.775, 1.10, 'y')
    right = V3((-1, 0, 0))
    up = n.cross(right).normalized()
    if up.z < 0:
        up = -up
    crest(gb, gd, p + n * 0.0005, right, up, 0.034)
    gb.obj("crest.pillar", "bright", bevel=0.0006, mirror=True)
    gd.obj("crest.pillar.inlay", "gloss_black", mirror=True)
    g = Geo()
    for side in (1, -1):
        text_on_body(g, "PRELATE", 0.024, 1.06, 0.385, side, spacing=1.5)
    g.obj("lettering", "bright")
    # ---- parking sensors in the plinth's strip zone, front and rear
    g = Geo()
    for proj in ('x', 'X'):
        for y in (-0.70, -0.30, 0.30, 0.70):
            p, n = on_body(y, 0.352, proj)
            K.stud(g, p, n, [(0.0, 0.001), (0.0, 0.011), (0.002, 0.011), (0.002, 0.001)], 16)
    g.obj("sensors", "gloss_black")
    # ---- a slim stop light under the rear glass's top edge
    g = Geo()
    p, n = on_body(-1.86, 0.0, 'z')
    g.box(p + n * 0.004, (0.010, 0.44, 0.006), rot=Matrix.Rotation(rad(-44), 3, 'Y'))
    g.obj("led.stop", "led_rear")
    # ---- wipers parked under the hood's trailing edge: only their dark slot shows
    g = Geo()
    ribbon(g, [(0.325, 0.0), (0.315, 0.31), (0.305, 0.62)], 'z', 0.016)
    g.obj("cowl.slot", "void", mirror=True)


# ---------------------------------------------------------------------------------------
# interior: 2 + 2
# ---------------------------------------------------------------------------------------
CAB_DX = -0.13


def shift(g):
    """The cabin was laid out 0.13 m farther forward."""
    for p in g.v:
        p.x += CAB_DX


def build_interior():
    g = Geo()
    g.box((-0.10, 0, 0.175), (1.30, 1.80, 0.03))                        # floor, and between
    g.box((-1.35, 0, 0.175), (1.20, 1.04, 0.03))                        # the rear wheels
    g.prism([(0.54, -0.86, 0.16), (0.54, -0.86, 0.905), (0.30, -0.86, 0.925),
             (0.13, -0.86, 0.86), (0.15, -0.86, 0.62), (0.30, -0.86, 0.46),
             (0.30, -0.86, 0.16)], (0, 1.72, 0))                        # firewall and dash
    g.box((-0.55, 0, 0.36), (1.70, 0.20, 0.36))                         # console
    g.box((-1.80, 0, 0.895), (0.40, 1.74, 0.03))                        # shelf under the glass
    g.box((-1.99, 0, 0.54), (0.04, 1.74, 0.74))                         # rear bulkhead
    for s in (1, -1):
        # door cards, ending ahead of the rear arch (they showed in its well)
        g.box((-0.09, s * 0.862, 0.535), (1.26, 0.04, 0.72))
        # the rear wells' inner walls inboard of the tires, a shelf over the arches
        g.box((-1.40, s * 0.56, 0.535), (1.30, 0.08, 0.72))
        g.box((-1.40, s * 0.745, 0.877), (1.30, 0.29, 0.036))
    shift(g)
    g.obj("interior.tub", "interior", bevel=0.006)
    g = Geo()
    t1 = Matrix.Rotation(rad(-19), 3, 'Y')
    t2 = Matrix.Rotation(rad(-15), 3, 'Y')
    for y in (0.42, -0.42):
        g.box((-0.26, y, 0.33), (0.52, 0.50, 0.13))
        g.box((-0.60, y, 0.66), (0.12, 0.48, 0.60), rot=t1)
        g.box((-0.715, y, 1.02), (0.075, 0.24, 0.15), rot=t1)
        for s in (-1, 1):
            g.box((-0.26, y + s * 0.245, 0.36), (0.48, 0.05, 0.16))
            g.box((-0.585, y + s * 0.235, 0.62), (0.15, 0.05, 0.48), rot=t1)
    for y in (0.34, -0.34):
        g.box((-1.20, y, 0.37), (0.44, 0.44, 0.12))
        g.box((-1.47, y, 0.66), (0.11, 0.44, 0.50), rot=t2)
        g.box((-1.56, y, 0.955), (0.07, 0.22, 0.12), rot=t2)
    shift(g)
    g.obj("interior.seats", "seat", bevel=0.014, segs=3)
    g = Geo()
    wheel = (Matrix.Translation((0.03, 0.42, 0.80)) @ Matrix.Rotation(rad(-68), 4, 'Y')
             @ Matrix.Rotation(pi / 2, 4, 'X'))
    g.lathe([(-0.012, 0.165), (0.0, 0.177), (0.012, 0.165), (0.0, 0.153)], 28, xf=wheel)
    g.box((0.03, 0.42, 0.80), (0.03, 0.32, 0.04), rot=Matrix.Rotation(rad(-22), 3, 'Y'))
    g.box((0.11, 0.42, 0.77), (0.17, 0.05, 0.05))
    shift(g)
    g.obj("interior.wheel", "interior", sharp=40)
    g = Geo()
    scr = Matrix.Rotation(rad(-14), 3, 'Y')
    g.box((0.125, 0.0, 0.835), (0.008, 1.50, 0.060), rot=scr)           # pillar to pillar
    g.box((-0.02, 0.0, 0.555), (0.26, 0.15, 0.006))                     # on the console
    shift(g)
    g.obj("interior.screens", "screen")
    g = Geo()
    for s in (1, -1):
        g.box((-0.09, s * 0.838, 0.76), (1.16, 0.006, 0.010))           # a bright line on the doors
    g.box((-0.55, 0, 0.545), (1.60, 0.012, 0.006))
    shift(g)
    g.obj("interior.trim", "bright")


# ---------------------------------------------------------------------------------------
# the build
# ---------------------------------------------------------------------------------------
K.VIEWS.update(
    nose=dict(dir=(1.0, 0.42, 0.12), lens=85, target=(2.4, 0.3, 0.55), dist=3.6),
    tail=dict(dir=(-1.0, -0.42, 0.14), lens=85, target=(-2.4, -0.3, 0.6), dist=3.6),
    wheel=dict(dir=(0.45, 1.0, 0.10), lens=85, target=(FA_X, 0.9, 0.42), dist=2.6),
)


def main():
    K.materials(paint=(0.038, 0.0022, 0.0065), paint_finish=(0.10, 0.08, 1.0), dust_amount=0.10,
                glass=(0.13, 0.14, 0.155), led_front=(1.0, 0.86, 0.62),
                led_rear=(1.0, 0.02, 0.012), seat=(0.50, 0.40, 0.28),
                interior=(0.030, 0.024, 0.022), screen=(1.0, 0.72, 0.38),
                decal=(0.75, 0.75, 0.72))
    K.emit("led_front", (1.0, 0.80, 0.50), 16.0)            # dimmer than the kit's: the slots
    K.emit("led_rear", (1.0, 0.02, 0.012), 12.0)            # keep their color under the bloom
    K.pbr("bright", (0.88, 0.88, 0.86), 1.0, 0.06)          # polished trim
    K.pbr("flute", (0.085, 0.085, 0.09), 1.0, 0.28)         # dark machined metal
    K.pbr("platinum", (0.36, 0.36, 0.375), 1.0, 0.24)        # the wheel discs
    aurel.serif()
    build_hull()
    K.log("hull")
    build_lamps()
    build_slabs()
    build_plinth()
    build_details()
    build_interior()
    K.log("details")
    for side, s in ((1, "l"), (-1, "r")):
        build_wheel("f" + s, FA_X, side)
        build_wheel("r" + s, RA_X, side)
    K.log("wheels")
    K.meant("symmetry", "interior.wheel")
    aurel.studio({"top": ["body.canopy"]})
    K.shoot(extra="top")


main()
