"""Brakk's shared helpers: plates, bars and bolts, stencilled lettering, hazard stripes, the
corner light pylon, the damper coil and the Brakk wheel (a lugged tire on a dished steel
rim with a bolted bead ring, a finned hub motor behind it when asked).

Lifted from the Hauler, the Bastion and the Mule (the Mule's copies, the newest):
tube, bolt, under, plate, on_side, on_plane, cut_glyph, stencil, chevrons, zcyl, ring,
pylon, coil, wheel. Differences between the copies, kept by parameters:

- on_plane: the Hauler's copy did not normalize right and up; every call it made passed
  unit vectors, so the normalizing copy builds it the same.
- pylon: the bolt heads went into the car's global BOLTS; pass it as bolts=.
- wheel (was build_wheel): the tire's sizes, lug count and sidewall text were the car's
  globals (R, w, rim, out, lugs, text); seg is the tire's lathe segments (the Hauler 88);
  dish the rim's dish and hub sizes (DISH_SMALL is the Hauler's); motor=False leaves the
  hub motor out (the Hauler, the Bastion's spare) and shows a dark void through the dish.

Step B's lamp pylon (lamp_pylon, with lbox and lpt) is the Hauler's step B pylon as its own
copy builds it (housings of plates round pockets, an LED bar in a reflector V and an amber
cell under lenses, bolted bezels, a guard); the Hauler keeps its copy, the Bastion uses this
one; the older pylon above stays for the cars not yet redone.

Left in the cars: the Mule's yz_prism, xy_prism and xz_prism (one car; the kit's
Geo.prism_on now lays a polygon on any named plane), the hulls' rows and the cars' own
parts. The kit's Geo.cyl, Geo.ring and bolt_row are newer, more general helpers but do
not build the same meshes as zcyl, ring and bolt, so those stay here.
"""
import bmesh
import carkit as K
from carkit import Geo, Matrix, V3, cos, hypot, on_body, pi, rad, sin, stud


def tube(g, a, b, r, n=8, r2=None, phase=0.0):
    """A straight bar of n sides from a to b (n = 4 with phase pi / 4: a box tube)."""
    a, b = V3(a), V3(b)
    t = (b - a).normalized()
    ref = V3((0, 0, 1)) if abs(t.z) < 0.9 else V3((1, 0, 0))
    u = t.cross(ref).normalized()
    v = t.cross(u)
    r2 = r if r2 is None else r2
    ring = [(u * cos(phase + 2 * pi * k / n) + v * sin(phase + 2 * pi * k / n)) for k in range(n)]
    pts = [a + d * r for d in ring] + [b + d * r2 for d in ring]
    faces = [tuple(range(n)), tuple(range(n, 2 * n))]
    faces += [(k, (k + 1) % n, n + (k + 1) % n, n + k) for k in range(n)]
    g.add(pts, faces)


def bolt(g, loc, n, r=0.012, h=0.006):
    """A hex bolt head on a surface point."""
    stud(g, loc, V3(n).normalized(), [(-0.001, 0.001), (-0.001, r), (h, r), (h, 0.001)], 6)


def under(pts, th):
    """An (x, z) polyline running front to rear, moved th toward the wheel under it."""
    ns = []
    for a, b in zip(pts, pts[1:]):
        dx, dz = b[0] - a[0], b[1] - a[1]
        L = hypot(dx, dz)
        ns.append((-dz / L, dx / L))
    out = []
    for i, p in enumerate(pts):
        if i == 0:
            n = ns[0]
        elif i == len(pts) - 1:
            n = ns[-1]
        else:
            a, b = ns[i - 1], ns[i]
            k = 1 + a[0] * b[0] + a[1] * b[1]
            n = ((a[0] + b[0]) / k, (a[1] + b[1]) / k)
        out.append((p[0] + n[0] * th, p[1] + n[1] * th))
    return out


def plate(g, pts, th, y0, y1):
    """A bent plate: the (x, z) polyline pts, th thick, from y0 to y1."""
    lo = under(pts, th)
    poly = [(x, y0, z) for x, z in pts] + [(x, y0, z) for x, z in lo[::-1]]
    g.prism(poly, (0, y1 - y0, 0))


def on_side(x0, z0, side):
    """place() for lettering on the body's flank, middle at (x0, z0)."""
    proj = 'y' if side > 0 else 'Y'

    def place(px, py, lift):
        loc, n = on_body(x0 - side * px, z0 + py, proj)
        return None if loc is None else loc + n * lift
    return place


def on_plane(origin, right, up):
    """place() for lettering on a plane, reading along right."""
    o, r, u = V3(origin), V3(right).normalized(), V3(up).normalized()
    n = r.cross(u).normalized()
    return lambda px, py, lift: o + r * px + u * py + n * lift


HCUT = set("TIY1")      # letters whose stencil bridge runs level


def cut_glyph(vs, fs, axis, lo, hi):
    """A flat glyph without the band lo..hi along axis (0 across, 1 up): a stencil's bridge."""
    out_v, out_f = [], []
    for low in (True, False):
        bm = bmesh.new()
        bv = [bm.verts.new(v) for v in vs]
        for f in fs:
            bm.faces.new([bv[i] for i in f])
        co, no = V3(), V3()
        co[axis] = lo if low else hi
        no[axis] = 1.0
        bmesh.ops.bisect_plane(bm, geom=bm.verts[:] + bm.edges[:] + bm.faces[:], plane_co=co,
                               plane_no=no, clear_outer=low, clear_inner=not low)
        bm.verts.index_update()
        o = len(out_v)
        out_v += [v.co.copy() for v in bm.verts]
        out_f += [tuple(o + v.index for v in f.verts) for f in bm.faces]
        bm.free()
    return out_v, out_f


def stencil(g, txt, size, place, gap=0.13, cut=0.085):
    """Stencilled capitals: every letter is cut through by a bridge of width cut * size
    (upright, or level for T, I, Y, 1); cut 0 leaves small print whole. place(px, py, lift)
    puts a point of the line (its middle at 0, 0) on the car: on_side, on_plane. Returns
    the line's width."""
    glyphs = []
    x = 0.0
    for ch in txt:
        if ch == " ":
            x += size * 0.36
            continue
        vs, fs = K.text_mesh(ch, size)
        x0, x1 = min(v.x for v in vs), max(v.x for v in vs)
        if cut and ch != "-":
            if ch in HCUT:
                cy = (min(v.y for v in vs) + max(v.y for v in vs)) / 2
                vs, fs = cut_glyph(vs, fs, 1, cy - size * cut / 2, cy + size * cut / 2)
            else:
                xm, hb = (x0 + x1) / 2, size * cut / 2
                vs, fs = cut_glyph(vs, fs, 0, xm - hb, xm + hb)
        glyphs.append((vs, fs, x - x0))
        x += (x1 - x0) + size * gap
    W = x - size * gap
    for vs, fs, dx in glyphs:
        pts = [place(v.x + dx - W / 2, v.y, 0.0012) for v in vs]
        if all(p is not None for p in pts):
            g.add(pts, fs)
    return W


def chevrons(g, place, W, H, n, lean):
    """Hazard stripes: n leaning bars over a W x H field."""
    pitch = (W - abs(lean)) / n
    for k in range(n):
        u0 = -W / 2 + k * pitch + max(0.0, -lean)
        q = [(u0, -H / 2), (u0 + pitch / 2, -H / 2), (u0 + pitch / 2 + lean, H / 2),
             (u0 + lean, H / 2)]
        g.add([place(u, v, 0.0015) for u, v in q], [(0, 1, 2, 3)])


def zcyl(g, c, r, h, n=16, r2=None):
    """An upright cylinder (or cone) standing on the point c."""
    c = V3(c)
    tube(g, c, c + V3((0, 0, h)), r, n, r2=r2)


def ring(g, c, r0=0.030, r1=0.050, t=0.009, n=14, rot=None):
    """A flat washer about y at c (r0 to r1, 2 t thick), turned by rot (a 4 x 4 matrix)."""
    xf = Matrix.Translation(c)
    if rot is not None:
        xf = xf @ rot
    g.lathe([(-t, r0), (-t, r1), (t, r1), (t, r0)], n, xf=xf)


def pylon(g, gl, ga, x, y, z0, z1, yaw, bolts):
    """A light pylon on a chamfered corner: a housing (into g), its bar (gl) and an amber
    cell at the bar's foot (ga), facing yaw (degrees); its four bolt heads go into bolts."""
    R = Matrix.Rotation(rad(yaw), 3, 'Z')
    n = R @ V3((1, 0, 0))
    c = V3((x, y, (z0 + z1) / 2))
    g.box(c + n * 0.018, (0.06, 0.10, z1 - z0), rot=R)
    gl.box(c + n * 0.050 + V3((0, 0, 0.045)), (0.012, 0.05, z1 - z0 - 0.16), rot=R)
    ga.box(V3((x, y, z0 + 0.07)) + n * 0.050, (0.012, 0.05, 0.06), rot=R)
    for z in (z0 + 0.018, z1 - 0.018):
        for s in (-0.03, 0.03):
            p = c + n * 0.048 + (R @ V3((0, s, 0)))
            p.z = z
            bolt(bolts, p, n, 0.007, 0.004)


def coil(g, gs, a, b, r=0.02):
    """A damper from a to b with a spring (into gs) round its upper two thirds."""
    a, b = V3(a), V3(b)
    tube(g, a, b, r, 10)
    tube(g, a.lerp(b, 0.25), a.lerp(b, 0.30), 0.055, 12)
    tube(g, a.lerp(b, 0.90), a.lerp(b, 0.94), 0.055, 12)
    for k in range(8):
        t = 0.32 + 0.57 * k / 8
        tube(gs, a.lerp(b, t), a.lerp(b, t + 0.035), 0.05, 12)


# the rim's dish: (its inner radius, the hub cap's radius, the cap's lip, the dish windows'
# radius, the radius of the hub's bolt circle)
DISH = (0.108, 0.112, 0.096, 0.029, 0.072)
DISH_SMALL = (0.105, 0.108, 0.092, 0.027, 0.07)


def wheel(tag, cx, side, loc=None, yaw=0.0, motor=True, *, R, w, rim, out, lugs, text,
          seg=96, dish=DISH):
    """The Brakk wheel at axle x cx on side (1 left, -1 right): a lugged tire (radius R,
    width w, lugs shoulder lugs round it, text twice round the sidewall), a dished steel rim
    (radius rim, the tire's outer face at y out) with eight windows and a bolted bead ring,
    a drum, and with motor a finned hub motor whose copper shows through the windows. loc
    and yaw put a wheel off any axle (a spare). Bind the car's sizes once with partial."""
    Rr = rim
    hw = w / 2
    flip = side < 0
    loc = (cx, side * (out - hw), R) if loc is None else loc
    n0 = len(K.CAR.objects)
    Rb = R - 0.024
    half = [(0.0, Rb), (hw - 0.035, Rb), (hw - 0.008, Rb - 0.018), (hw + 0.010, R - 0.057),
            (hw + 0.018, R - 0.08), (hw + 0.018, Rr + 0.07), (hw + 0.010, Rr + 0.032),
            (hw + 0.004, Rr + 0.012), (hw - 0.010, Rr + 0.004), (hw - 0.03, Rr - 0.006)]
    g = Geo()
    g.lathe([(-y, r) for y, r in half[:0:-1]] + half, seg)

    def pt(th, t, y, r):
        a = th + t / R
        return (r * cos(a), y, r * sin(a))
    for k in range(lugs):
        th = 2 * pi * k / lugs
        for sg, off in ((1, 0.0), (-1, 0.5)):                   # shoulder lugs with side biters
            t0 = (off - 0.30) * 2 * pi * R / lugs
            t1 = t0 + 0.085
            sk = 0.035
            yi, yo = sg * 0.042, sg * (hw + 0.006)
            ys = sg * (hw + 0.024)
            g.hexa([pt(th, t0, yi, Rb - 0.01), pt(th, t1, yi, Rb - 0.01),
                    pt(th, t1 - sk, ys, R - 0.085), pt(th, t0 - sk, ys, R - 0.085),
                    pt(th, t0, yi, R), pt(th, t1, yi, R),
                    pt(th, t1 - sk, yo, R - 0.012), pt(th, t0 - sk, yo, R - 0.012)])
        for off in (0.22, 0.72):                                # the middle row
            t0 = (off - 0.2) * 2 * pi * R / lugs
            t1 = t0 + 0.045
            g.hexa([pt(th, t0, -0.03, Rb - 0.01), pt(th, t1, -0.03, Rb - 0.01),
                    pt(th, t1 + 0.012, 0.03, Rb - 0.01), pt(th, t0 + 0.012, 0.03, Rb - 0.01),
                    pt(th, t0, -0.03, R), pt(th, t1, -0.03, R),
                    pt(th, t1 + 0.012, 0.03, R), pt(th, t0 + 0.012, 0.03, R)])
    ob = g.obj("tire." + tag, "rubber", flip_y=flip, loc=loc)
    ob.data.shade_smooth()
    ob.data.set_sharp_from_angle(angle=rad(30))
    # sidewall lettering, reading the right way round on both sides
    g = Geo()
    rt = (R - 0.08 + Rr + 0.07) / 2
    sgn = 1 if not flip else -1
    a = rad(90) - sgn * 0.5
    for rep in range(2):
        for ch in text:
            if ch == " ":
                a += sgn * 0.022 / rt
                continue
            vs, fs = K.text_mesh(ch, 0.062)
            x0, x1 = min(v.x for v in vs), max(v.x for v in vs)
            adv = (x1 - x0) + 0.008
            am = a + sgn * (adv / 2) / rt
            rad_ = V3((cos(am), 0, sin(am)))
            rgt = V3((-sin(am), 0, cos(am))) * sgn
            o = rad_ * rt + V3((0, hw + 0.0195, 0))
            g.add([o + rgt * (v.x - (x0 + x1) / 2) + rad_ * v.y for v in vs], fs)
            a += sgn * adv / rt
        a = rad(270) - sgn * 0.5
    g.obj("tiretext." + tag, "tiremark", flip_y=flip, loc=loc)
    # rim: barrel, a deep dish with eight round windows, the hub
    r_dish, r_cap, r_lip, r_win, r_bolt = dish
    g = Geo()
    g.lathe([(-hw + 0.03, Rr), (hw - 0.012, Rr), (hw - 0.012, Rr - 0.014),
             (-hw + 0.03, Rr - 0.014)], 56)
    y_a, r_a, y_b, r_b = hw - 0.045, Rr - 0.014, hw - 0.115, r_dish
    g.lathe([(y_a, r_a), (y_b, r_b), (y_b - 0.014, r_b), (y_a - 0.014, r_a)], 56)
    g.lathe([(hw - 0.135, 0.004), (hw - 0.135, r_cap), (hw - 0.092, r_cap), (hw - 0.08, r_lip),
             (hw - 0.08, 0.004)], 16)
    g.obj("rim." + tag, "rim", bevel=0.004, flip_y=flip, loc=loc)
    gv, gbr = Geo(), Geo()
    L = hypot(y_b - y_a, r_b - r_a)
    ny, nr = -(r_b - r_a) / L, (y_b - y_a) / L                  # the dish's normal, outward
    for k in range(8):
        a = 2 * pi * (k + 0.5) / 8
        s = 0.47
        y, r = y_a + (y_b - y_a) * s, r_a + (r_b - r_a) * s
        stud(gv, V3((r * cos(a), y, r * sin(a))), V3((nr * cos(a), ny, nr * sin(a))).normalized(),
             [(-0.004, 0.001), (-0.004, r_win), (0.0012, r_win), (0.0012, 0.001)], 14)
        an = 2 * pi * k / 8
        gbr.lathe([(hw - 0.081, 0.002), (hw - 0.081, 0.0125), (hw - 0.06, 0.0125),
                   (hw - 0.06, 0.002)], 6,
                  xf=Matrix.Translation((r_bolt * cos(an), 0, r_bolt * sin(an))))
    gv.obj("rimholes." + tag, "stator" if motor else "void", flip_y=flip, loc=loc)
    gbr.lathe([(hw - 0.081, 0.004), (hw - 0.081, 0.048), (hw - 0.04, 0.044), (hw - 0.032, 0.03),
               (hw - 0.032, 0.004)], 8)
    gbr.lathe([(hw - 0.016, Rr - 0.032), (hw - 0.016, Rr + 0.015), (hw + 0.001, Rr + 0.015),
               (hw + 0.001, Rr - 0.032)], 56)
    for k in range(16):
        a = 2 * pi * (k + 0.5) / 16
        rr = Rr - 0.009
        gbr.lathe([(hw, 0.001), (hw, 0.0085), (hw + 0.007, 0.0085), (hw + 0.007, 0.001)], 6,
                  xf=Matrix.Translation((rr * cos(a), 0, rr * sin(a))))
    gbr.obj("hub." + tag, "rim_bright", bevel=0.0015, flip_y=flip, loc=loc)
    g = Geo()
    g.lathe([(-hw + 0.05, 0.004), (-hw + 0.05, Rr - 0.014), (-hw + 0.035, Rr - 0.014),
             (-hw + 0.035, 0.004)], 32)
    g.obj("drum." + tag, "well", flip_y=flip, loc=loc)
    if motor:
        # the hub motor: a finned can on the wheel's inner face, a bolted end plate
        g = Geo()
        y0 = -hw - 0.085
        prof = [(y0, 0.004), (y0, 0.15), (y0 + 0.012, 0.15), (y0 + 0.012, 0.178)]
        for k in range(5):
            ya = y0 + 0.016 + k * 0.019
            prof += [(ya, 0.178), (ya, 0.205), (ya + 0.008, 0.205), (ya + 0.008, 0.178)]
        prof += [(-hw + 0.04, 0.178), (-hw + 0.04, 0.004)]
        g.lathe(prof, 40)
        g.obj("motor." + tag, "rim", bevel=0.0015, flip_y=flip, loc=loc)
        g = Geo()
        for k in range(10):
            a = 2 * pi * k / 10
            g.lathe([(y0 - 0.006, 0.001), (y0 - 0.006, 0.009), (y0, 0.009), (y0, 0.001)], 6,
                    xf=Matrix.Translation((0.125 * cos(a), 0, 0.125 * sin(a))))
        g.obj("motorbolts." + tag, "rim_bright", flip_y=flip, loc=loc)
        g = Geo()
        g.lathe([(y0 + 0.0125, 0.151), (y0 + 0.0125, 0.177), (y0 + 0.0155, 0.177),
                 (y0 + 0.0155, 0.151)], 40)
        g.obj("motorband." + tag, "stator", flip_y=flip, loc=loc)
    for ob in list(K.CAR.objects)[n0:]:
        ob.rotation_euler = (0, 0, yaw)


# ---------------------------------------------------------------------------------------
# step B's lamp pylon (the Hauler's own copy, which it keeps; the Bastion builds on this one)
# ---------------------------------------------------------------------------------------
def lbox(g, o, R, a, b, z):
    """A box in a lamp's own frame: o its foot on the body, R its turn, a its range along
    the way out, b across, z up (absolute)."""
    c = V3(o) + R @ V3(((a[0] + a[1]) / 2, (b[0] + b[1]) / 2, 0))
    c.z = (z[0] + z[1]) / 2
    g.box(c, (a[1] - a[0], b[1] - b[0], z[1] - z[0]), rot=R)


def lpt(o, R, a, b, z):
    """A point in a lamp's own frame (as lbox)."""
    p = V3(o) + R @ V3((a, b, 0))
    p.z = z
    return p


def lamp_pylon(key, x, y, z0, z1, yaw, lit, lens, face=0.05, lens_at=0.044, sw=0.03,
               sink=0.03, guard=4):
    """Step B's light pylon on a chamfered corner, facing yaw (degrees): a housing of plates
    sunk sink into the corner, a tall window over an LED bar right under its lens in a V of
    reflector plates and an amber cell at its foot under an amber lens, each in a bolted
    bezel, a guard of guard bars over the tall one (0: none). face is how far the plates
    stand off the corner, lens_at where the lenses lie, sw half a window's width. Made on
    the left side and mirrored: objects pylon.<key>, .bezel, .bolts, .guard,
    lamp.pylon_<key> and lamp.pylon_<key>_turn."""
    R = Matrix.Rotation(rad(yaw), 3, 'Z')
    o = V3((x, y, 0))
    n = R @ V3((1, 0, 0))
    wb, wt = z0 + 0.135, z1 - 0.035            # the tall window
    ab, at = z0 + 0.04, z0 + 0.105             # the amber cell's window
    g = Geo()
    lbox(g, o, R, (-sink, 0.0), (-0.05, 0.05), (z0, z1))
    for sg in (1, -1):
        lbox(g, o, R, (0.0, face), sorted((sg * sw, sg * 0.05)), (z0, z1))
    for zz in ((wt, z1), (at, wb), (z0, ab)):
        lbox(g, o, R, (0.0, face), (-sw, sw), zz)
    g.obj("pylon." + key, "cladding", bevel=0.003, mirror=True)
    gb, gn = Geo(), Geo()
    for lo, hi in ((wb, wt), (ab, at)):
        for sg in (1, -1):
            lbox(gb, o, R, (face, face + 0.006), sorted((sg * (sw - 0.005), sg * (sw + 0.012))),
                 (lo - 0.012, hi + 0.012))
        for zz in ((hi - 0.005, hi + 0.012), (lo - 0.012, lo + 0.005)):
            lbox(gb, o, R, (face, face + 0.006), (-sw + 0.005, sw - 0.005), zz)
        for zz in (lo - 0.006, hi + 0.006):
            for b in (-sw - 0.0035, sw + 0.0035):
                bolt(gn, lpt(o, R, face + 0.006, b, zz), n, 0.0045, 0.003)
    gb.obj("pylon.%s.bezel" % key, "paint2", bevel=0.0015, mirror=True)
    gn.obj("pylon.%s.bolts" % key, "rim_bright", mirror=True)
    if guard:
        gg = Geo()
        for i in range(guard):
            zz = wb + (wt - wb) * (i + 0.5) / guard
            tube(gg, lpt(o, R, face + 0.016, -sw - 0.006, zz),
                 lpt(o, R, face + 0.016, sw + 0.006, zz), 0.0035, 8)
        for b in (-sw - 0.006, sw + 0.006):
            lbox(gg, o, R, (face + 0.004, face + 0.02), (b - 0.004, b + 0.004),
                 (wb - 0.004, wt + 0.004))
        gg.obj("pylon.%s.guard" % key, "rim", bevel=0.001, mirror=True)
    L = K.Lamp("lamp.pylon_" + key, lit=lit, glass=lens)
    lbox(L.housing, o, R, (0.0, 0.012), (-sw, sw), (wb, wt))
    for sg in (1, -1):                         # the reflector's two leaves
        L.chrome.add([lpt(o, R, 0.012, sg * 0.004, z) for z in (wb, wt)]
                     + [lpt(o, R, 0.036, sg * sw, z) for z in (wt, wb)]
                     + [lpt(o, R, 0.012, sg * 0.006, z) for z in (wb, wt)]
                     + [lpt(o, R, 0.034, sg * sw, z) for z in (wt, wb)],
                     [(0, 1, 2, 3), (7, 6, 5, 4), (0, 4, 5, 1), (1, 5, 6, 2), (2, 6, 7, 3),
                      (3, 7, 4, 0)])
    L.bar([lpt(o, R, 0.036, 0, wb + 0.008), lpt(o, R, 0.036, 0, wt - 0.008)], 0.018, 0.008,
          up=n)
    lbox(L.housing, o, R, (0.012, 0.032), (-0.006, 0.006), (wb, wt))     # the bar's spine
    lbox(L.glass, o, R, (lens_at - 0.003, lens_at), (-sw, sw), (wb, wt))
    L.obj(mirror=True)
    A = K.Lamp("lamp.pylon_%s_turn" % key, lit="led_accent", glass="lens_amber")
    lbox(A.chrome, o, R, (0.0, 0.026), (-sw, sw), (ab, at))
    A.bar([lpt(o, R, 0.034, -sw + 0.007, (ab + at) / 2), lpt(o, R, 0.034, sw - 0.007, (ab + at) / 2)],
          0.012, at - ab - 0.016, up=V3((0, 0, 1)))
    lbox(A.glass, o, R, (lens_at - 0.003, lens_at), (-sw, sw), (ab, at))
    A.obj(mirror=True)
