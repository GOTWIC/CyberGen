"""Aurel's shared helpers: the end slabs' frame (Slab), the lozenge grille of light slots,
the corner blades, the crest, the pleated disc wheel cover with the crest on its cap, the
serif wordmark and the studio's light links that keep the raked glass clear.

Lifted from the Prelate, the Regent and the Zenith: Slab, lozenge, blade, crest (all three),
wheel (was build_wheel: the Prelate and the Regent), studio (was each car's build_studio
wrapper), serif (was the SERIFS loop in each main()). Differences kept by parameters:

- lozenge: ztop, the height its search for the slab's top edge starts from, was 1.0 on the
  Prelate, 1.10 on the Regent and 1.30 (the default) on the Zenith.
- wheel: the tire's sizes were the car's globals (R, w, rim, out).
- studio(unlit, strips): unlit maps a studio light to the objects it does not light (the
  Prelate kept only the top box off the canopy); strips < 1 dims the two low strip lights
  (the Zenith's black lacquer, 0.45). It is built on the kit's unlit() and after_studio(),
  which do what the cars' wrappers did, so it needs no wrapper round K.build_studio.
- serif(): the kit's FONT_SETS["serif"] (the same files the cars listed) as the car's
  default font.

Left in the cars: each hull's stations, panels and creases, nose_x and tail_x (the same
code on the Regent and the Zenith, but each the shape of its own hull), the plinth, and the
Zenith's walk and outline (one car; the kit's walk() now does the same job).
"""
import carkit as K
from carkit import Geo, Matrix, V3, cos, on_body, pi, ribbon, sin


class Slab:
    """Coordinates on an end slab: at(y, z, d) is the point at height z, d off the slab."""

    def __init__(self, proj, zc):
        self.o, self.n = on_body(0.0, zc, proj)
        self.ey = V3((0, 1, 0))
        self.eu = self.n.cross(self.ey).normalized()
        if self.eu.z < 0:
            self.eu = -self.eu
        self.rot = Matrix((self.n, self.ey, self.eu)).transposed()
        # a reader's right hand when facing the slab
        self.right = V3((0, 1, 0)) if proj == 'x' else V3((0, -1, 0))

    def at(self, y, z, d=0.0):
        return self.o + self.ey * y + self.eu * ((z - self.o.z) / self.eu.z) + self.n * d

    def box(self, g, y, z, d, size):
        """size: (depth, width, height); d is the middle of its depth off the slab."""
        g.box(self.at(y, z, d), size, rot=self.rot)


def lozenge(sl, tag, kmax, z0, led, sx, lmax, pitch=0.030, w=0.008, ztop=1.30):
    """The Aurel grille: no opening, only slots of light let into the slab, in a field of
    bright hairline flutes. They hang from the slab's top edge, the middle one longest, and go on
    over the edge along the hood (the deck) the same way: the crest's lozenge, folded over
    the edge. ztop is a height over the slab's top edge, where the search for it starts."""
    proj = 'x' if sx > 0 else 'X'
    gl, gd, gv = Geo(), Geo(), Geo()

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
            sl.box(gd, y, (zb + z1) / 2, 0.001, (0.002, w + 0.007, z1 - zb + 0.007))
            sl.box(gl, y, (zb + z1) / 2, 0.002, (0.004, w, z1 - zb))
            ribbon(gd, [(xs + sx * 0.002, y), (xe - sx * 0.002, y)], 'z', w + 0.004, lift=0.0006)
            ribbon(gl, [(xs, y), (xe, y)], 'z', w, lift=0.0014)
        else:
            sl.box(gv, y, (zb + z1) / 2, 0.0006, (0.0012, 0.0025, z1 - zb))
            ribbon(gv, [(xs, y), (xe, y)], 'z', 0.0025, lift=0.0006)

    for k in range(-kmax, kmax + 1):
        slot(k * pitch, True)
        if k < kmax:
            slot((k + 1 / 3) * pitch, False)
            slot((k + 2 / 3) * pitch, False)
    gd.obj("lozenge.slots." + tag, "gloss_black")
    gv.obj("lozenge.flutes." + tag, "bright")
    gl.obj("lozenge.light." + tag, led)


def blade(sl, tag, y, z0, z1, led):
    """A slim vertical light at a corner of a slab, in a dark slot with a bright edge."""
    zc, H = (z0 + z1) / 2, z1 - z0
    g = Geo()
    sl.box(g, y, zc, 0.004, (0.010, 0.040, H + 0.03))
    g.obj("blade.house." + tag, "gloss_black", bevel=0.002, mirror=True)
    g = Geo()
    sl.box(g, y, zc, 0.009, (0.006, 0.016, H))
    g.obj("blade.light." + tag, led, mirror=True)
    g = Geo()
    for dy in (-0.022, 0.022):
        sl.box(g, y + dy, zc, 0.006, (0.014, 0.004, H + 0.034))
    g.obj("blade.edge." + tag, "bright", mirror=True)


def crest(gb, gd, o, right, up, s):
    """Aurel's crest: a tall lozenge, a dark lozenge within, a bright bar down its middle."""
    o, right, up = V3(o), V3(right).normalized(), V3(up).normalized()
    out = right.cross(up).normalized()

    def loz(k, d0, d1, g):
        poly = [o + up * (0.82 * s * k) + out * d0, o + right * (0.5 * s * k) + out * d0,
                o - up * (0.82 * s * k) + out * d0, o - right * (0.5 * s * k) + out * d0]
        g.prism(poly, out * (d1 - d0))
    loz(1.0, 0.0, 0.003, gb)
    loz(0.72, 0.003, 0.0042, gd)
    gb.prism([o + up * (0.5 * s) + right * (0.035 * s) + out * 0.004,
              o + up * (0.5 * s) - right * (0.035 * s) + out * 0.004,
              o - up * (0.5 * s) - right * (0.035 * s) + out * 0.004,
              o - up * (0.5 * s) + right * (0.035 * s) + out * 0.004], out * 0.0015)


def wheel(tag, cx, side, *, R, w, rim, out):
    """The kit's disc wheel (tire radius R, width w, rim radius rim, tire's outer face at y
    out) under Aurel's cover: 96 fine pleats from the hub to the rim in a shallow dish, a
    bright ring round it, a dark cap with the crest. Bind the sizes once with partial."""
    T_R, T_W, T_RIM, OUT_Y = R, w, rim, out
    K.build_wheel(tag, cx, T_R, T_W, T_RIM, OUT_Y, side, style="disc", ring=None,
                  caliper=None)
    hw = T_W / 2
    loc = (cx, side * (OUT_Y - hw), T_R)
    flip = side < 0
    # the disc: 96 fine pleats from the hub to the rim, a shallow dish
    N = 96
    M = 2 * N
    r0, r1 = 0.088, T_RIM - 0.024
    y0, y1 = hw - 0.036, hw - 0.015
    vs, fs = [], []
    for k in range(M):
        a = 2 * pi * k / M
        d = 0.0018 if k % 2 else -0.0018
        for r, y in ((r1, y1 + d), (r0, y0 + d * 0.45), (r0, y0 - 0.014), (r1, y1 - 0.014)):
            vs.append((r * cos(a), y, r * sin(a)))
    for k in range(M):
        k2 = (k + 1) % M
        for j in range(4):
            j2 = (j + 1) % 4
            fs.append((4 * k + j, 4 * k + j2, 4 * k2 + j2, 4 * k2 + j))
    g = Geo()
    g.add(vs, fs)
    g.obj("cover." + tag, "platinum", flip_y=flip, loc=loc)
    # a bright ring round it, a dark cap with the crest
    g = Geo()
    g.lathe([(y1 - 0.014, r1 - 0.001), (y1 + 0.004, r1 - 0.001), (y1 + 0.007, r1 + 0.004),
             (y1 + 0.007, T_RIM - 0.007), (y1 - 0.014, T_RIM - 0.007)], 96)
    g.lathe([(y0 - 0.014, 0.086), (y0 + 0.019, 0.086), (y0 + 0.019, 0.096), (y0 - 0.014, 0.096)],
            64)
    g.obj("cover.ring." + tag, "bright", bevel=0.0015, flip_y=flip, loc=loc)
    g = Geo()
    g.lathe([(y0 - 0.014, 0.004), (y0 - 0.014, 0.086), (y0 + 0.015, 0.086), (y0 + 0.021, 0.070),
             (y0 + 0.021, 0.004)], 64)
    g.obj("cover.cap." + tag, "gloss_black", flip_y=flip, loc=loc, sharp=30)
    gb, gd = Geo(), Geo()
    crest(gb, gd, (0, y0 + 0.0212, 0), (1, 0, 0), (0, 0, 1), 0.058)
    # the lozenge was laid out for a reader in front of it: out is right x up = -y here
    for gg in (gb, gd):
        gg.v = [V3((p.x, 2 * (y0 + 0.0212) - p.y, p.z)) for p in gg.v]
    gb.obj("cover.crest." + tag, "bright", flip_y=flip, loc=loc)
    gd.obj("cover.crest.in." + tag, "gloss_black", flip_y=flip, loc=loc)


def studio(unlit, strips=1.0):
    """Aurel's studio: the kit's, with the lights in unlit ({light: objects}) kept off those
    objects (the top box off the canopy, which it mirrored whole in a raked windshield; the
    side glass, which leans in, off the boxes behind and above), and the two low strip
    lights at strips times their power. Call it once, before shoot()."""
    for name, skip in unlit.items():
        K.unlit(name, *skip)
    if strips != 1.0:
        def dim():
            for name in ("strip", "strip2"):
                light = K.STUDIO.objects.get(name)
                if light is not None:
                    light.data.energy *= strips
        K.after_studio(dim)


def serif():
    """The serif wordmark face (the kit's FONT_SETS["serif"]) as the car's default font;
    the kit's own stays where none of its files is found."""
    font = K.load_font("serif")
    if font is not None:
        K._FONT[0] = font
