"""Prop variant generators (scope 5.4): a mesh per M6 prop kind, district style and variant
index, in the prop's own frame (x along its yaw, y to its left, z up from its position, as
M6 places it and the blockout's prototypes are drawn).

Each generator draws its parameters (heights, arm and head types, profiles, colors) from a
blake2b hash of (kind, style, index), from a shortlist of forms that style allows, and builds
the mesh from AG7's integer millimeter kit. Variant k of a style takes form k of its
shortlist first (so a family's members differ in form before they differ in size), then
sizes and colors by hash.

Frames per kind (where M6's placement fixes them):
- facade props (`ac_unit`, `wall_light`, `bracket`): x out of the wall; the wall at
  x = -REACH (M6 puts them that far out), `bracket` a unit length along -x from 0, scaled to
  the gap the brief measures;
- `awning`: a unit awning (x along the facade, -0.5 to 0.5; the wall at y = +0.5, the outer
  edge at y = -0.5; top at the wall at z = 0), scaled to the unit's length and depth;
- `bus_stop`: x along the curb, the back wall at +y;
- `boat`: the waterline at z = 0, scaled as M6 scales it;
- everything else stands on z = 0.
"""

from __future__ import annotations

from citygen import dmath as M

from . import styles as ST
from .shapes import (Mesh, arcs, beam, blk, catenary, extrude, fan, lathe, obb, quad_out, ring,
                     sheet, tube)

REACH = {"ac_unit": 0.3, "wall_light": 0.2}
GENERATORS: dict = {}


def gen(kind: str):
    def wrap(fn):
        GENERATORS[kind] = fn
        return fn
    return wrap


class D:
    """The draws of one variant: D(kind, style, k)."""

    def __init__(self, kind: str, style: str, k: int):
        self.key = ("ag8", kind, style, k)
        self.style, self.k = style, k

    def u(self, *p) -> float:
        return ST.u(*self.key, *p)

    def r(self, lo: float, hi: float, *p) -> float:
        return ST.rng(lo, hi, *self.key, *p)

    def c(self, seq, *p):
        return ST.choice(seq, *self.key, *p)

    def form(self, forms):
        """Form k of the style's shortlist, then by hash past its length."""
        return forms[self.k] if self.k < len(forms) else self.c(forms, "form")


def make(kind: str, style: str, k: int) -> Mesh:
    m = Mesh((0.0, 0.0))
    GENERATORS[kind](m, D(kind, style, k))
    return m


# ---------------------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------------------

def pole(m: Mesh, slot: str, h: float, r0: float, r1: float, n: int = 8,
         base: tuple | None = None) -> None:
    """A tapered pole from 0 to h, an optional base (radius, height)."""
    prof = []
    if base:
        br, bh = base
        prof += [(br, 0.0), (br, bh * 0.8), (r0 * 1.15, bh)]
    else:
        prof += [(r0, 0.0)]
    prof += [(r1, h)]
    lathe(m, slot, prof, n)


def lamp_head(m: Mesh, slot: str, lens: str, x0: float, x1: float, w: float, z: float,
              h: float, taper: float = 0.0) -> None:
    """A luminaire: a body from x0 to x1 (w wide, h high, its bottom at z; its top falling
    toward x1 by `taper`), the lens a glowing panel just under it."""
    if taper > 0.0:
        lo, hi = (x0, x1)
        extrude(m, slot, [(lo, z), (hi, z), (hi, z + h * (1.0 - taper)),
                          (lo + (hi - lo) * 0.3, z + h), (lo, z + h)], "y", -w / 2.0, w / 2.0)
    else:
        blk(m, slot, x0, x1, -w / 2.0, w / 2.0, z, z + h)
    m.poly(lens, [(x0 + 0.04, -w / 2.0 + 0.03), (x1 - 0.04, -w / 2.0 + 0.03),
                  (x1 - 0.04, w / 2.0 - 0.03), (x0 + 0.04, w / 2.0 - 0.03)], z=z - 0.006,
           up=False)


def lantern(m: Mesh, frame: str, glow: str, cx: float, cy: float, z: float, s: float,
            sides: int = 6) -> None:
    """A lantern: a glowing body under a cap and over a base, s high."""
    lathe(m, frame, [(s * 0.18, z), (s * 0.3, z + s * 0.08)], sides, cx, cy)
    lathe(m, glow, [(s * 0.3, z + s * 0.08), (s * 0.34, z + s * 0.55), (s * 0.26, z + s * 0.78)],
          sides, cx, cy)
    lathe(m, frame, [(s * 0.4, z + s * 0.78), (s * 0.12, z + s * 0.95), (0.0, z + s)], sides,
          cx, cy)


def wheel(m: Mesh, x: float, y0: float, y1: float, r: float, rim: str) -> None:
    """A wheel round an axis along y from y0 to y1, its tire and hub."""
    tube(m, "rubber", [(x, y0, r), (x, y1, r)], r, 10)
    ye = y0 if abs(y0) > abs(y1) else y1
    out = (0.0, 1.0 if ye > 0 else -1.0, 0.0)
    pts = [(x + r * 0.62 * c, ye + out[1] * 0.006, r + r * 0.62 * sn) for c, sn in ring(8)]
    fan(m, rim, (x, ye + out[1] * 0.006, r), pts, out)


def leaf_blob(m: Mesh, slot: str, cx: float, cy: float, z0: float, r: float, h: float,
              key, n: int = 10) -> None:
    """A lumpy dome of foliage (shrubs in planters and on stalls)."""
    prof = []
    for i in range(6):
        t = i / 5.0
        a = t * M.PI / 2.0
        rr = r * M.cos(a) * (0.9 + 0.2 * ST.u(*key, "lump", i))
        prof.append((max(rr, 0.0 if i == 5 else 0.01), z0 + h * M.sin(a)))
    prof[-1] = (0.0, z0 + h)
    lathe(m, slot, prof, n, cx, cy)


# ---------------------------------------------------------------------------------------
# street lights
# ---------------------------------------------------------------------------------------

LIGHT_FORMS = {"sleek": ("blade", "curve", "halo", "double_blade", "blade", "curve"),
               "civic": ("cobra", "davit", "double_cobra", "post_top", "cobra", "davit"),
               "heavy": ("box", "twin_box", "mast", "box", "twin_box", "mast"),
               "neon": ("cobra_ring", "curve_ring", "string", "cobra_ring", "curve_ring",
                        "string"),
               "old": ("swan", "post_lantern", "double_lantern", "crook", "swan",
                       "post_lantern")}


@gen("street_light")
def street_light(m: Mesh, d: D) -> None:
    st = d.style
    form = d.form(LIGHT_FORMS[st])
    h = d.r(7.4, 9.0, "h") if form not in ("post_top", "post_lantern") else d.r(4.2, 5.2, "h")
    arm = d.r(1.2, 2.0, "arm")
    pslot = {"sleek": d.c(("metal.white", "metal.galv", "metal.dark"), "pc"),
             "civic": d.c(("metal.galv", "metal.dark", "metal.green"), "pc"),
             "heavy": "metal.galv", "neon": d.c(("metal.black", "metal.dark", "metal.red"), "pc"),
             "old": d.c(("metal.green", "metal.black"), "pc")}[st]
    lens = {"heavy": "light.sodium", "old": "light.warm"}.get(st, "light.cool" if st == "sleek"
                                                              else "light.warm")
    if st == "old":
        lathe(m, pslot, [(0.24, 0.0), (0.24, 0.35), (0.16, 0.5), (0.13, 1.2), (0.1, 1.3),
                         (0.085, 1.4), (0.07, h - 0.3), (0.09, h - 0.2), (0.06, h)], 10)
    elif st == "heavy":
        blk(m, "concrete", -0.35, 0.35, -0.35, 0.35, 0.0, 0.5)
        pole(m, pslot, h, 0.17, 0.11, 8)
    elif st == "sleek":
        pole(m, pslot, h, 0.085, 0.055, 12)
    else:
        pole(m, pslot, h, 0.12, 0.07, 10, base=(0.18, 0.6))
    if form in ("blade", "double_blade"):
        for sgn in ((1.0,) if form == "blade" else (1.0, -1.0)):
            beam(m, pslot, (0.0, 0.0, h - 0.1), (sgn * arm * 0.6, 0.0, h + 0.02), 0.06)
            x0, x1 = sorted((sgn * arm * 0.35, sgn * (arm + 0.3)))
            lamp_head(m, pslot, lens, x0, x1, 0.16, h - 0.02, 0.06)
    elif form in ("curve", "curve_ring"):
        pts = []
        for i in range(9):
            a = M.PI / 2.0 * i / 8
            pts.append((arm * 0.6 * (1.0 - M.cos(a)), 0.0, h - 0.8 + 0.8 * M.sin(a)))
        pts.append((arm, 0.0, h))
        tube(m, pslot, [(0.0, 0.0, h - 1.2)] + pts, 0.05, 6)
        lamp_head(m, pslot, lens, arm - 0.2, arm + 0.45, 0.22, h - 0.05, 0.08)
    elif form == "halo":
        tube(m, pslot, [(0.0, 0.0, h), (0.0, 0.0, h + 0.4)], 0.05, 8)
        rr = d.r(0.45, 0.7, "halo")
        pts = [(rr * c, rr * s, h + 0.25) for c, s in ring(16)]
        tube(m, lens, pts + [pts[0]], 0.035, 5, caps=False)
        for c, s in ring(4):
            beam(m, pslot, (0.0, 0.0, h + 0.25), (rr * c, rr * s, h + 0.25), 0.03)
    elif form in ("cobra", "double_cobra", "cobra_ring"):
        for sgn in ((1.0, -1.0) if form == "double_cobra" else (1.0,)):
            beam(m, pslot, (0.0, 0.0, h - 0.25), (sgn * arm, 0.0, h + 0.15), 0.08, 0.1)
            hx = sgn * arm
            x0, x1 = sorted((hx - sgn * 0.1, hx + sgn * 0.7))
            lamp_head(m, pslot, lens, x0, x1, 0.32, h + 0.05, 0.12, taper=0.4)
    elif form == "davit":
        pts = [(0.0, 0.0, h - 1.0)]
        for i in range(9):
            a = M.PI * i / 8
            pts.append((arm * 0.5 * (1.0 - M.cos(a)), 0.0, h - 0.4 + 0.4 * M.sin(a)))
        tube(m, pslot, pts, 0.055, 6)
        lathe(m, pslot, [(0.3, h - 0.66), (0.28, h - 0.62), (0.05, h - 0.45)], 10, arm, 0.0)
        m.poly(lens, [(arm + 0.26 * c, 0.26 * s) for c, s in ring(10)], z=h - 0.665, up=False)
    elif form == "post_top":
        lathe(m, pslot, [(0.06, h), (0.25, h + 0.05), (0.25, h + 0.1)], 12)
        lathe(m, lens, [(0.24, h + 0.1), (0.22, h + 0.5)], 12)
        lathe(m, pslot, [(0.27, h + 0.5), (0.27, h + 0.56), (0.0, h + 0.6)], 12)
    elif form in ("box", "twin_box"):
        for sgn in ((1.0, -1.0) if form == "twin_box" else (1.0,)):
            beam(m, pslot, (0.0, 0.0, h - 0.15), (sgn * arm, 0.0, h - 0.15), 0.12)
            x0, x1 = sorted((sgn * (arm - 0.15), sgn * (arm + 0.55)))
            lamp_head(m, "metal.dark", lens, x0, x1, 0.4, h - 0.3, 0.22)
    elif form == "mast":
        blk(m, pslot, -0.12, 0.12, -0.6, 0.6, h, h + 0.12)
        for y in (-0.42, 0.42):
            blk(m, "metal.dark", 0.05, 0.55, y - 0.16, y + 0.16, h - 0.25, h - 0.05)
            m.poly(lens, [(0.09, y - 0.13), (0.51, y - 0.13), (0.51, y + 0.13), (0.09, y + 0.13)],
                   z=h - 0.256, up=False)
        beam(m, pslot, (0.0, 0.0, h - 0.1), (0.3, 0.0, h - 0.1), 0.1)
    elif form == "string":
        beam(m, pslot, (0.0, 0.0, h - 0.2), (arm, 0.0, h - 0.2), 0.07)
        lamp_head(m, pslot, lens, arm - 0.3, arm + 0.3, 0.25, h - 0.35, 0.15)
        for j in range(5):
            lathe(m, d.c(("neon.ff2a6d", "neon.05d9e8", "neon.ffb000"), "bulb", j),
                  [(0.0, h - 1.2 - j * 0.5), (0.06, h - 1.15 - j * 0.5), (0.0, h - 1.08 - j * 0.5)],
                  6, 0.18, 0.0)
        tube(m, "metal.black", [(0.18, 0.0, h - 0.2), (0.18, 0.0, h - 3.2)], 0.008, 4)
    elif form in ("swan", "crook"):
        pts = [(0.0, 0.0, h - 0.6)]
        for i in range(10):
            a = M.PI * i / 9
            pts.append((0.45 * (1.0 - M.cos(a)), 0.0, h - 0.2 + 0.45 * M.sin(a)))
        pts.append((0.92, 0.0, h - 0.35))
        tube(m, pslot, pts, 0.035, 6)
        lantern(m, pslot, lens, 0.92, 0.0, h - 1.05, 0.7, 6 if form == "swan" else 8)
    elif form in ("post_lantern", "double_lantern"):
        if form == "double_lantern":
            beam(m, pslot, (-0.55, 0.0, h - 0.1), (0.55, 0.0, h - 0.1), 0.05)
            for x in (-0.55, 0.55):
                lantern(m, pslot, lens, x, 0.0, h - 0.1, 0.65, 6)
        else:
            lantern(m, pslot, lens, 0.0, 0.0, h, 0.75, 6)
    if form.endswith("_ring") or (st == "neon" and form == "string"):
        col = d.c(("neon.ff2a6d", "neon.05d9e8", "neon.b967ff", "neon.39ff8a"), "ring")
        for j in range(2):
            z = 2.6 + j * 0.5
            pts = [(0.13 * c, 0.13 * s, z) for c, s in ring(10)]
            tube(m, col, pts + [pts[0]], 0.02, 4, caps=False)


# ---------------------------------------------------------------------------------------
# facade props
# ---------------------------------------------------------------------------------------

WALL_FORMS = {"sleek": ("bar", "cube", "disc", "bar", "cube"),
              "civic": ("sconce", "gooseneck", "bulkhead", "sconce", "gooseneck"),
              "heavy": ("bulkhead", "cage", "flood", "bulkhead", "flood"),
              "neon": ("gooseneck", "cage", "tube", "sconce", "tube"),
              "old": ("lantern", "gooseneck", "lantern", "cage", "lantern")}


@gen("wall_light")
def wall_light(m: Mesh, d: D) -> None:
    w = -REACH["wall_light"]
    form = d.form(WALL_FORMS[d.style])
    met = {"sleek": "metal.white", "old": "metal.black"}.get(d.style, "metal.dark")
    lens = {"heavy": "light.sodium", "sleek": "light.cool"}.get(d.style, "light.warm")
    blk(m, met, w, w + 0.03, -0.09, 0.09, -0.12, 0.12)
    if form == "bar":
        blk(m, met, w, w + 0.12, -0.45, 0.45, -0.05, 0.05)
        m.poly(lens, [(w + 0.01, -0.43), (w + 0.11, -0.43), (w + 0.11, 0.43), (w + 0.01, 0.43)],
               z=-0.056, up=False)
    elif form == "cube":
        blk(m, met, w, w + 0.18, -0.09, 0.09, -0.18, 0.0)
        m.poly(lens, [(w + 0.02, -0.07), (w + 0.16, -0.07), (w + 0.16, 0.07), (w + 0.02, 0.07)],
               z=-0.186, up=False)
    elif form == "disc":
        lathe(m, met, [(0.0, -0.04), (0.16, -0.03), (0.16, 0.02)], 12, w + 0.18, 0.0)
        m.poly(lens, [(w + 0.18 + 0.14 * c, 0.14 * s) for c, s in ring(12)], z=-0.046, up=False)
        beam(m, met, (w, 0.0, 0.0), (w + 0.1, 0.0, 0.0), 0.03)
    elif form in ("sconce", "bulkhead"):
        x1 = w + (0.14 if form == "sconce" else 0.12)
        blk(m, met, w, x1, -0.12, 0.12, -0.2, 0.05)
        quad_out(m, lens, (x1 + 0.004, -0.09, -0.16), (x1 + 0.004, 0.09, -0.16),
                 (x1 + 0.004, 0.09, 0.01), (x1 + 0.004, -0.09, 0.01), (1.0, 0.0, 0.0))
    elif form == "gooseneck":
        pts = [(w, 0.0, 0.0)]
        for i in range(8):
            a = M.PI / 2.0 * i / 7
            pts.append((w + 0.45 * M.sin(a), 0.0, 0.25 * (1.0 - M.cos(a)) + 0.1 * M.sin(a)))
        tube(m, met, pts, 0.018, 5)
        lathe(m, met, [(0.18, 0.0), (0.17, 0.03), (0.03, 0.2)], 10, w + 0.45, 0.0)
        m.poly(lens, [(w + 0.45 + 0.16 * c, 0.16 * s) for c, s in ring(10)], z=-0.004, up=False)
    elif form in ("cage", "tube"):
        beam(m, met, (w, 0.0, 0.0), (w + 0.18, 0.0, 0.0), 0.04)
        if form == "cage":
            lathe(m, lens, [(0.0, -0.2), (0.07, -0.16), (0.07, -0.04), (0.0, 0.0)], 8,
                  w + 0.2, 0.0)
            for c, s in ring(4):
                tube(m, met, [(w + 0.2 + 0.09 * c, 0.09 * s, -0.22),
                              (w + 0.2 + 0.09 * c, 0.09 * s, 0.0)], 0.006, 3)
        else:
            col = d.c(("neon.ff2a6d", "neon.05d9e8", "neon.b967ff"), "tube")
            tube(m, col, [(w + 0.12, -0.4, -0.1), (w + 0.12, 0.4, -0.1)], 0.025, 6)
    elif form == "flood":
        beam(m, met, (w, 0.0, 0.0), (w + 0.25, 0.0, -0.05), 0.04)
        obb(m, met, (w + 0.32, 0.0, -0.12), (0.7071, 0.0, -0.7071), (0.0, 1.0, 0.0),
            (0.7071, 0.0, 0.7071), 0.05, 0.16, 0.12)
        quad_out(m, lens, (w + 0.39, -0.14, -0.2), (w + 0.39, 0.14, -0.2),
                 (w + 0.28, 0.14, -0.28), (w + 0.28, -0.14, -0.28), (0.7, 0.0, -0.7))
    elif form == "lantern":
        pts = [(w, 0.0, 0.0), (w + 0.25, 0.0, 0.0), (w + 0.3, 0.0, 0.05)]
        tube(m, met, pts, 0.015, 5)
        lantern(m, met, lens, w + 0.32, 0.0, -0.55, 0.6, 6)


AC_FORMS = {"sleek": ("split", "slim", "split", "slim", "split", "slim", "split", "slim"),
            "civic": ("fan", "split", "window", "fan", "twin", "split", "fan", "window"),
            "heavy": ("fan", "twin", "cage", "louver", "fan", "twin", "cage", "louver"),
            "neon": ("fan", "window", "twin", "cage", "fan", "rust", "window", "twin"),
            "old": ("rust", "window", "cage", "fan", "rust", "twin", "window", "cage")}


@gen("ac_unit")
def ac_unit(m: Mesh, d: D) -> None:
    w = -REACH["ac_unit"]
    form = d.form(AC_FORMS[d.style])
    body = {"rust": "metal.rust", "slim": "metal.white"}.get(
        form, d.c(("metal.white", "plastic.white", "metal.galv", "plastic.grey"), "body"))
    dep = d.r(0.32, 0.5, "dep")
    wid = d.r(0.7, 0.95, "wid")
    hgt = d.r(0.5, 0.7, "hgt")
    units = 2 if form == "twin" else 1
    for j in range(units):
        z0 = j * (hgt + 0.08)
        x1 = w + dep
        blk(m, body, w + 0.02, x1, -wid / 2.0, wid / 2.0, z0, z0 + hgt)
        if form in ("fan", "twin", "rust", "cage", "split"):
            r = min(hgt, wid) * 0.36
            cy = -wid * 0.12 if form != "split" else 0.0
            pts = [(x1 + 0.004, cy + r * c, z0 + hgt / 2.0 + r * s) for c, s in ring(12)]
            fan(m, "metal.black", (x1 + 0.004, cy, z0 + hgt / 2.0), pts, (1.0, 0.0, 0.0))
            for k in range(3):
                zz = z0 + hgt / 2.0 + (k - 1) * r * 0.55
                beam(m, "metal.galv", (x1 + 0.012, cy - r * 0.9, zz), (x1 + 0.012, cy + r * 0.9, zz),
                     0.012)
        elif form in ("window", "louver"):
            for k in range(6):
                zz = z0 + 0.08 + k * (hgt - 0.16) / 5.0
                obb(m, "metal.dark", (x1 + 0.01, 0.0, zz), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0),
                    (0.0, 0.0, 1.0), 0.012, wid * 0.42, 0.012)
        elif form == "slim":
            blk(m, "metal.galv", x1, x1 + 0.01, -wid * 0.4, wid * 0.4, z0 + 0.06, z0 + 0.12)
    if form == "cage":
        for y in (-wid / 2.0 - 0.02, wid / 2.0 + 0.02):
            for zz in (0.02, hgt - 0.02):
                beam(m, "metal.galv", (w, y, zz), (w + dep + 0.05, y, zz), 0.02)
            beam(m, "metal.galv", (w + dep + 0.05, y, 0.02), (w + dep + 0.05, y, hgt - 0.02), 0.02)
    # brackets under the unit, and a drip pipe on the shabbier ones
    for y in (-wid * 0.35, wid * 0.35):
        beam(m, "metal.galv", (w, y, -0.03), (w + dep, y, -0.03), 0.04)
        beam(m, "metal.galv", (w, y, -0.35), (w + dep * 0.8, y, -0.04), 0.03)
    if form in ("rust", "fan", "window") and d.u("drip") < 0.6:
        tube(m, "plastic.grey", [(w + 0.05, wid * 0.45, 0.05), (w + 0.05, wid * 0.45, -1.2)],
             0.012, 4)


@gen("bracket")
def bracket(m: Mesh, d: D) -> None:
    """A standoff from a facade prop back to its wall: a unit length along -x (scaled to the
    gap), two arms and a wall plate."""
    met = {"sleek": "metal.white", "old": "metal.black", "heavy": "metal.galv"}.get(d.style,
                                                                                    "metal.dark")
    for y in (-0.25, 0.25):
        beam(m, met, (-1.0, y, 0.0), (0.0, y, 0.0), 0.04 + 0.01 * (d.k % 2))
    beam(m, met, (-1.0, 0.0, -0.3), (-0.05, 0.0, -0.02), 0.03)
    blk(m, met, -1.0, -0.99, -0.32, 0.32, -0.35, 0.06)


AWNING_FORMS = {"sleek": ("glass", "flat", "glass", "flat", "glass", "flat", "glass", "flat"),
                "civic": ("slope", "flat", "barrel", "slope", "flat", "slope", "barrel", "flat"),
                "heavy": ("corrugated", "flat", "slope", "corrugated", "flat", "slope",
                          "corrugated", "flat"),
                "neon": ("slope", "neon", "barrel", "neon", "slope", "corrugated", "neon",
                         "barrel"),
                "old": ("slope", "tiled", "corrugated", "slope", "tiled", "barrel",
                        "corrugated", "slope")}
FABRICS = ("fabric.red", "fabric.green", "fabric.blue", "fabric.orange", "fabric.cream",
           "fabric.black", "fabric.purple")


@gen("awning")
def awning(m: Mesh, d: D) -> None:
    """A unit awning: x -0.5 to 0.5, wall at y = 0.5, outer edge at y = -0.5, z 0 at the
    wall's top (scaled per unit to its length and depth)."""
    form = d.form(AWNING_FORMS[d.style])
    fab = d.c(FABRICS, "fab")
    drop = d.r(0.25, 0.45, "drop")
    if form in ("slope", "neon"):
        quad_out(m, fab, (-0.5, 0.5, 0.0), (0.5, 0.5, 0.0), (0.5, -0.5, -drop),
                 (-0.5, -0.5, -drop), (0.0, -0.4, 1.0))
        quad_out(m, fab, (-0.5, 0.5, -0.004), (0.5, 0.5, -0.004), (0.5, -0.5, -drop - 0.004),
                 (-0.5, -0.5, -drop - 0.004), (0.0, 0.4, -1.0))
        val = d.r(0.15, 0.25, "val")
        quad_out(m, fab, (-0.5, -0.5, -drop), (0.5, -0.5, -drop), (0.5, -0.5, -drop - val),
                 (-0.5, -0.5, -drop - val), (0.0, -1.0, 0.0))
        quad_out(m, fab, (-0.5, -0.496, -drop), (0.5, -0.496, -drop), (0.5, -0.496, -drop - val),
                 (-0.5, -0.496, -drop - val), (0.0, 1.0, 0.0))
        for x, s in ((-0.5, -1.0), (0.5, 1.0)):
            fan(m, fab, (x, 0.2, -drop * 0.55), [(x, 0.5, 0.0), (x, -0.5, -drop),
                                                 (x, -0.5, -drop - val), (x, 0.5, -0.02)],
                (s, 0.0, 0.0))
        if form == "neon":
            col = d.c(("neon.ff2a6d", "neon.05d9e8", "neon.b967ff", "neon.ffb000"), "neon")
            blk(m, col, -0.5, 0.5, -0.52, -0.5, -drop - val - 0.02, -drop - val)
    elif form == "flat":
        blk(m, fab, -0.5, 0.5, -0.5, 0.5, -0.06, 0.0)
        blk(m, "metal.dark", -0.5, 0.5, -0.52, -0.46, -0.12, 0.0)
        for x in (-0.45, 0.45):
            beam(m, "metal.dark", (x, 0.5, -0.4), (x, -0.45, -0.06), 0.02)
    elif form == "glass":
        blk(m, "glass.prop", -0.5, 0.5, -0.5, 0.5, -0.03, 0.0)
        blk(m, "metal.chrome", -0.5, 0.5, -0.52, -0.48, -0.06, 0.01)
        for x in (-0.4, 0.0, 0.4):
            beam(m, "metal.chrome", (x, -0.45, 0.0), (x, 0.5, 0.45), 0.012)
    elif form == "barrel":
        pts = []
        for i in range(9):
            a = M.PI / 2.0 * i / 8
            pts.append((0.5 - 1.0 * M.sin(a), -drop + (drop + 0.15) * M.cos(a) - 0.15))
        rows = [[(x, y, z) for y, z in pts] for x in (-0.5, 0.5)]
        uvs = [[(x, v) for v in arcs(pts)] for x in (-0.5, 0.5)]
        m.grid(fab, rows, uvs, flip=True)
        m.grid(fab, [[(x, y, z - 0.004) for y, z in pts] for x in (-0.5, 0.5)], uvs)
        for x, s in ((-0.5, -1.0), (0.5, 1.0)):
            fan(m, fab, (x, 0.5, -drop - 0.1), [(x, y, z) for y, z in pts] + [(x, 0.5, -drop)],
                (s, 0.0, 0.0))
    elif form == "corrugated":
        mat = d.c(("metal.galv", "metal.rust", "fabric.tarp", "plastic.green"), "sheet")
        n = 10
        for i in range(n):
            x0 = -0.5 + i / n
            x1 = x0 + 0.5 / n
            x2 = x0 + 1.0 / n
            sheet(m, mat, (x0, 0.5, 0.0), (x1, 0.5, 0.012), (x1, -0.5, -drop + 0.012),
                  (x0, -0.5, -drop), (0.0, -0.3, 1.0))
            sheet(m, mat, (x1, 0.5, 0.012), (x2, 0.5, 0.0), (x2, -0.5, -drop),
                  (x1, -0.5, -drop + 0.012), (0.0, -0.3, 1.0))
        for x in (-0.45, 0.45):
            beam(m, "wood", (x, 0.5, -drop - 0.3), (x, -0.4, -drop + 0.02), 0.04)
    elif form == "tiled":
        sheet(m, "wood.red", (-0.5, 0.5, 0.0), (0.5, 0.5, 0.0), (0.5, -0.5, -drop),
              (-0.5, -0.5, -drop), (0.0, -0.4, 1.0))
        for i in range(8):
            x = -0.5 + (i + 0.5) / 8
            tube(m, "concrete.dark", [(x, 0.5, 0.03), (x, -0.5, -drop + 0.03)], 0.03, 4)
        blk(m, "concrete.dark", -0.52, 0.52, -0.55, -0.45, -drop - 0.02, -drop + 0.06)
        for x in (-0.45, 0.45):
            beam(m, "wood", (x, 0.5, -drop - 0.25), (x, -0.4, -drop), 0.05)


# ---------------------------------------------------------------------------------------
# ground furniture
# ---------------------------------------------------------------------------------------

SIGNAL_FORMS = {"sleek": ("slim", "slim_cam", "slim", "slim_cam"),
                "civic": ("three", "three_ped", "three", "three_ped"),
                "heavy": ("twin", "three", "twin", "three_ped"),
                "neon": ("three_screen", "three", "three_screen", "three_ped"),
                "old": ("ornate", "three", "ornate", "three_ped")}


@gen("traffic_signal")
def traffic_signal(m: Mesh, d: D) -> None:
    form = d.form(SIGNAL_FORMS[d.style])
    met = {"sleek": "metal.white", "old": "metal.green", "heavy": "metal.galv"}.get(
        d.style, "metal.dark")
    h = d.r(4.6, 5.6, "h")
    if form == "ornate":
        lathe(m, met, [(0.18, 0.0), (0.18, 0.3), (0.1, 0.45), (0.08, h - 0.2), (0.1, h - 0.1),
                       (0.0, h)], 8)
    else:
        pole(m, met, h, 0.09 if form.startswith("slim") else 0.11, 0.07, 8)
    heads = 2 if form == "twin" else 1
    for j in range(heads):
        z0 = h - 1.3 - j * 1.2
        hx = 0.32
        if form.startswith("slim"):
            blk(m, "metal.black", hx - 0.09, hx + 0.09, -0.11, 0.11, z0, z0 + 1.1)
            for k, col in enumerate(("light.red", "light.amber", "light.green")):
                zz = z0 + 0.88 - k * 0.33
                for s in (-1.0, 1.0):
                    quad_out(m, col, (hx - 0.07, s * 0.112, zz - 0.1), (hx + 0.07, s * 0.112, zz - 0.1),
                             (hx + 0.07, s * 0.112, zz + 0.1), (hx - 0.07, s * 0.112, zz + 0.1),
                             (0.0, s, 0.0))
        else:
            blk(m, "metal.black", hx - 0.15, hx + 0.15, -0.14, 0.14, z0, z0 + 1.0)
            blk(m, "metal.black", hx - 0.26, hx + 0.26, -0.01, 0.01, z0 - 0.08, z0 + 1.08)
            for k, col in enumerate(("light.red", "light.amber", "light.green")):
                zz = z0 + 0.82 - k * 0.32
                for s in (-1.0, 1.0):
                    pts = [(hx + 0.1 * c, s * 0.145, zz + 0.1 * sn) for c, sn in ring(10)]
                    fan(m, col, (hx, s * 0.145, zz), pts, (0.0, s, 0.0))
                    sheet(m, "metal.black", (hx - 0.13, s * 0.145, zz + 0.12),
                          (hx + 0.13, s * 0.145, zz + 0.12),
                          (hx + 0.13, s * 0.3, zz + 0.12), (hx - 0.13, s * 0.3, zz + 0.12),
                          (0.0, 0.0, 1.0))
        beam(m, met, (0.0, 0.0, z0 + 0.5), (hx - 0.1, 0.0, z0 + 0.5), 0.06)
    if form.endswith("ped") or form == "three_screen":
        z = 2.5
        blk(m, "metal.black", -0.36, -0.1, -0.13, 0.13, z, z + 0.42)
        col = "screen.cyan" if form == "three_screen" else "light.amber"
        quad_out(m, col, (-0.364, -0.1, z + 0.06), (-0.364, 0.1, z + 0.06), (-0.364, 0.1, z + 0.36),
                 (-0.364, -0.1, z + 0.36), (-1.0, 0.0, 0.0))
        blk(m, "metal.galv", -0.12, -0.08, -0.06, 0.06, 1.0, 1.25)
    if form == "slim_cam":
        beam(m, met, (0.0, 0.0, h - 0.1), (-0.4, 0.0, h - 0.1), 0.04)
        blk(m, "metal.white", -0.62, -0.38, -0.07, 0.07, h - 0.28, h - 0.14)


CAN_FORMS = {"sleek": ("steel", "slot", "steel", "slot", "steel"),
             "civic": ("dome", "square", "twin", "dome", "square"),
             "heavy": ("concrete", "drum", "concrete", "drum", "square"),
             "neon": ("plastic", "dome", "twin", "plastic", "drum"),
             "old": ("cast", "basket", "cast", "basket", "drum")}


@gen("trash_can")
def trash_can(m: Mesh, d: D) -> None:
    form = d.form(CAN_FORMS[d.style])
    h = d.r(0.82, 1.0, "h")
    r = d.r(0.24, 0.3, "r")
    if form in ("steel", "slot"):
        lathe(m, "metal.chrome", [(r, 0.0), (r, h - 0.08), (r * 0.9, h)], 14)
        lathe(m, "metal.black", [(r * 0.9, h), (r * 0.5, h + 0.02), (0.0, h + 0.03)], 14)
        if form == "slot":
            blk(m, "metal.black", r - 0.01, r + 0.003, -0.12, 0.12, h - 0.3, h - 0.18)
    elif form == "dome":
        body = d.c(("metal.green", "metal.dark", "metal.blue"), "body")
        lathe(m, body, [(r, 0.0), (r * 1.05, h * 0.85)], 12)
        lathe(m, body, [(r * 1.08, h * 0.85), (r * 1.08, h * 0.9), (r * 0.7, h), (0.0, h + 0.04)], 12)
    elif form in ("square", "twin"):
        cols = (d.c(("plastic.green", "plastic.grey", "metal.dark"), "c0"),
                d.c(("plastic.blue", "plastic.yellow", "plastic.orange"), "c1"))
        n = 2 if form == "twin" else 1
        for j in range(n):
            y0 = -0.3 * n + j * 0.6
            blk(m, cols[j], -0.28, 0.28, y0 + 0.02, y0 + 0.58, 0.0, h)
            blk(m, "plastic.black", -0.3, 0.3, y0, y0 + 0.6, h, h + 0.04)
    elif form == "concrete":
        blk(m, "concrete", -0.35, 0.35, -0.35, 0.35, 0.0, h * 0.9)
        lathe(m, "metal.galv", [(0.24, h * 0.9), (0.26, h * 0.95), (0.0, h * 0.96)], 10)
    elif form == "drum":
        col = d.c(("metal.blue", "metal.rust", "metal.red", "metal.green"), "drum")
        lathe(m, col, [(0.29, 0.0), (0.3, 0.05), (0.3, 0.85), (0.29, 0.88), (0.0, 0.88)], 12)
    elif form == "plastic":
        col = d.c(("plastic.orange", "plastic.blue", "plastic.green", "plastic.red"), "pl")
        lathe(m, col, [(r * 0.85, 0.0), (r, h * 0.92)], 12)
        lathe(m, "plastic.black", [(r * 1.04, h * 0.92), (r * 1.04, h), (0.0, h + 0.02)], 12)
    elif form == "cast":
        lathe(m, "metal.black", [(r * 0.8, 0.0), (r, 0.08), (r * 0.9, 0.16), (r, h * 0.8),
                                 (r * 1.1, h * 0.85), (r * 0.6, h), (0.0, h + 0.08)], 12)
        for c, s in ring(6):
            tube(m, "metal.bronze", [(r * 1.0 * c, r * 1.0 * s, 0.2),
                                     (r * 1.02 * c, r * 1.02 * s, h * 0.78)], 0.012, 3)
    elif form == "basket":
        for c, s in ring(10):
            tube(m, "metal.galv", [(r * 0.8 * c, r * 0.8 * s, 0.0), (r * c, r * s, h)], 0.01, 3)
        for z in (0.02, h * 0.5, h):
            k = 0.8 + 0.2 * z / h
            pts = [(r * k * c, r * k * s, z) for c, s in ring(10)]
            tube(m, "metal.galv", pts + [pts[0]], 0.012, 3, caps=False)
        m.poly("bag.black", [(r * 0.75 * c, r * 0.75 * s) for c, s in ring(10)], z=0.04)


SHELTER_FORMS = {"sleek": ("curve", "flat", "curve", "flat"),
                 "civic": ("flat", "slope", "flat", "curve"),
                 "heavy": ("slab", "slope", "slab", "flat"),
                 "neon": ("flat", "curve", "slope", "flat"),
                 "old": ("pagoda", "slope", "pagoda", "slope")}


@gen("bus_stop")
def bus_stop(m: Mesh, d: D) -> None:
    form = d.form(SHELTER_FORMS[d.style])
    met = {"sleek": "metal.white", "old": "metal.green", "heavy": "concrete"}.get(
        d.style, "metal.dark")
    L = d.r(3.8, 4.4, "L")
    hx = L / 2.0
    top = d.r(2.45, 2.65, "top")
    posts = [(-hx + 0.08, 0.62), (hx - 0.08, 0.62)]
    if form != "slab":
        posts += [(-hx + 0.08, -0.55), (hx - 0.08, -0.55)] if d.u("p4") < 0.5 else []
    for x, y in posts:
        if met == "concrete":
            blk(m, met, x - 0.1, x + 0.1, y - 0.1, y + 0.1, 0.0, top)
        else:
            tube(m, met, [(x, y, 0.0), (x, y, top)], 0.05, 6)
    if form == "flat":
        blk(m, met if met != "concrete" else "metal.dark", -hx - 0.1, hx + 0.1, -0.85, 0.8,
            top, top + 0.1)
    elif form == "slope":
        sheet(m, met if met != "concrete" else "metal.galv", (-hx - 0.1, 0.8, top + 0.2),
              (hx + 0.1, 0.8, top + 0.2), (hx + 0.1, -0.9, top), (-hx - 0.1, -0.9, top),
              (0.0, 0.1, 1.0))
        blk(m, "metal.dark", -hx - 0.1, hx + 0.1, -0.92, -0.86, top - 0.08, top + 0.02)
    elif form == "curve":
        pts = []
        for i in range(9):
            a = M.PI * i / 8
            pts.append((0.85 * M.cos(a) * -1.0, top + 0.25 * M.sin(a)))
        rows = [[(x, y, z) for y, z in pts] for x in (-hx - 0.1, hx + 0.1)]
        uvs = [[(x, v) for v in arcs(pts)] for x in (-hx - 0.1, hx + 0.1)]
        # the arc runs from -y to +y, so the top faces up unflipped and its underside flipped
        m.grid("glass.prop" if d.style == "sleek" else met, rows, uvs)
        m.grid(met, [[(x, y, z - 0.01) for y, z in pts] for x in (-hx - 0.1, hx + 0.1)], uvs,
               flip=True)
    elif form == "slab":
        blk(m, "concrete", -hx - 0.3, hx + 0.3, -1.0, 0.85, top, top + 0.3)
        blk(m, "concrete", -hx, -hx + 0.25, 0.4, 0.85, 0.0, top)
    elif form == "pagoda":
        quad_out(m, "wood.red", (-hx - 0.4, 0.1, top + 0.6), (hx + 0.4, 0.1, top + 0.6),
                 (hx + 0.5, -1.0, top), (-hx - 0.5, -1.0, top), (0.0, -0.5, 1.0))
        quad_out(m, "wood.red", (-hx - 0.4, 0.1, top + 0.6), (hx + 0.4, 0.1, top + 0.6),
                 (hx + 0.5, 1.0, top), (-hx - 0.5, 1.0, top), (0.0, 0.5, 1.0))
        tube(m, "concrete.dark", [(-hx - 0.5, 0.1, top + 0.62), (hx + 0.5, 0.1, top + 0.62)],
             0.07, 6)
        m.poly("wood", [(-hx - 0.5, -1.0), (hx + 0.5, -1.0), (hx + 0.5, 1.0), (-hx - 0.5, 1.0)],
               z=top - 0.002, up=False)
    # back wall of glass, bench, ad panel
    blk(m, "glass.prop", -hx + 0.15, hx - 0.15, 0.6, 0.64, 0.1, top - 0.15)
    blk(m, met if met != "concrete" else "metal.dark", -hx + 0.15, hx - 0.15, 0.58, 0.66,
        top - 0.2, top - 0.12)
    seat = "wood" if d.style in ("old", "civic") else "metal.galv"
    blk(m, seat, -hx * 0.7, hx * 0.7, 0.2, 0.58, 0.44, 0.5)
    for x in (-hx * 0.6, hx * 0.6):
        blk(m, "metal.dark", x - 0.03, x + 0.03, 0.3, 0.5, 0.0, 0.44)
    ad = d.c(("screen.white", "screen.cyan", "screen.magenta", "screen.amber"), "ad")
    blk(m, "metal.dark", hx - 0.12, hx + 0.02, -0.55, 0.55, 0.3, 2.1)
    quad_out(m, ad, (hx + 0.024, -0.48, 0.38), (hx + 0.024, 0.48, 0.38), (hx + 0.024, 0.48, 2.02),
             (hx + 0.024, -0.48, 2.02), (1.0, 0.0, 0.0))
    quad_out(m, ad, (hx - 0.124, -0.48, 0.38), (hx - 0.124, 0.48, 0.38),
             (hx - 0.124, 0.48, 2.02), (hx - 0.124, -0.48, 2.02), (-1.0, 0.0, 0.0))
    if d.style == "neon":
        col = d.c(("neon.ff2a6d", "neon.05d9e8", "neon.b967ff"), "edge")
        blk(m, col, -hx - 0.1, hx + 0.1, -0.88, -0.85, top - 0.03, top + 0.02)


HYDRANT_FORMS = {"sleek": ("post", "box", "post", "box"), "civic": ("classic", "squat", "classic", "squat"),
                 "heavy": ("squat", "standpipe", "squat", "standpipe"),
                 "neon": ("classic", "squat", "classic", "standpipe"),
                 "old": ("ornate", "classic", "ornate", "classic")}


@gen("hydrant")
def hydrant(m: Mesh, d: D) -> None:
    form = d.form(HYDRANT_FORMS[d.style])
    col = {"sleek": "metal.white", "heavy": "metal.yellow", "old": "metal.green"}.get(
        d.style, d.c(("metal.red", "metal.yellow", "metal.red"), "col"))
    if form == "post":
        lathe(m, col, [(0.11, 0.0), (0.11, 0.85), (0.0, 0.88)], 12)
        blk(m, "metal.chrome", 0.1, 0.14, -0.06, 0.06, 0.55, 0.67)
        return
    if form == "box":
        blk(m, col, -0.15, 0.15, -0.12, 0.12, 0.0, 0.7)
        blk(m, "light.red", 0.15, 0.152, -0.08, 0.08, 0.58, 0.64)
        return
    if form == "standpipe":
        lathe(m, col, [(0.12, 0.0), (0.09, 0.05), (0.09, 1.0), (0.12, 1.05), (0.0, 1.06)], 10)
        tube(m, col, [(0.0, 0.0, 0.8), (0.0, 0.25, 0.8)], 0.05, 6)
        return
    tall = 0.82 if form != "squat" else 0.62
    prof = [(0.18, 0.0), (0.18, 0.06), (0.12, 0.09), (0.12, tall * 0.75), (0.15, tall * 0.8),
            (0.13, tall * 0.88), (0.06, tall), (0.03, tall + 0.04), (0.0, tall + 0.05)]
    if form == "ornate":
        prof = [(0.2, 0.0), (0.2, 0.08), (0.11, 0.12), (0.13, 0.3), (0.11, tall * 0.7),
                (0.16, tall * 0.78), (0.1, tall * 0.92), (0.05, tall + 0.05), (0.0, tall + 0.1)]
    lathe(m, col, prof, 10)
    for s in (-1.0, 1.0):
        tube(m, col, [(0.0, s * 0.1, tall * 0.62), (0.0, s * 0.2, tall * 0.62)], 0.045, 6)
    tube(m, col, [(0.1, 0.0, tall * 0.55), (0.22, 0.0, tall * 0.55)], 0.06, 6)


BOLLARD_FORMS = {"sleek": ("led", "steel", "led", "square", "steel"),
                 "civic": ("band", "steel", "band", "post", "steel"),
                 "heavy": ("pipe", "block", "pipe", "block", "pipe"),
                 "neon": ("neon", "band", "neon", "pipe", "band"),
                 "old": ("cast", "ball", "cast", "ball", "cast")}


@gen("bollard")
def bollard(m: Mesh, d: D) -> None:
    form = d.form(BOLLARD_FORMS[d.style])
    h = d.r(0.8, 1.0, "h")
    if form in ("led", "steel"):
        lathe(m, "metal.chrome" if form == "steel" else "metal.white",
              [(0.1, 0.0), (0.1, h - 0.03), (0.0, h)], 12)
        if form == "led":
            lathe(m, "light.cool", [(0.102, h - 0.18), (0.102, h - 0.1)], 12, caps=False)
    elif form == "square":
        blk(m, "metal.dark", -0.08, 0.08, -0.08, 0.08, 0.0, h)
    elif form in ("band", "post"):
        lathe(m, "metal.black", [(0.1, 0.0), (0.1, h - 0.03), (0.0, h)], 10)
        lathe(m, "paint.white" if form == "band" else "metal.yellow",
              [(0.102, h - 0.22), (0.102, h - 0.14)], 10, caps=False)
    elif form == "pipe":
        lathe(m, "metal.yellow", [(0.14, 0.0), (0.14, h), (0.0, h + 0.05)], 10)
    elif form == "block":
        blk(m, "concrete", -0.25, 0.25, -0.25, 0.25, 0.0, h * 0.7)
    elif form == "neon":
        lathe(m, "metal.black", [(0.1, 0.0), (0.1, h), (0.0, h + 0.02)], 10)
        col = d.c(("neon.ff2a6d", "neon.05d9e8", "neon.b967ff", "neon.39ff8a"), "ring")
        lathe(m, col, [(0.104, h - 0.1), (0.104, h - 0.04)], 10, caps=False)
    elif form == "cast":
        lathe(m, "metal.black", [(0.14, 0.0), (0.14, 0.06), (0.1, 0.1), (0.09, h - 0.15),
                                 (0.12, h - 0.1), (0.1, h - 0.05), (0.0, h + 0.02)], 10)
    elif form == "ball":
        lathe(m, "metal.black", [(0.12, 0.0), (0.09, 0.08), (0.08, h - 0.15)], 10)
        prof = [(0.0, h - 0.18)] + [(0.11 * M.sin(M.PI * i / 6), h - 0.07 - 0.11 * M.cos(M.PI * i / 6))
                                     for i in range(1, 6)] + [(0.0, h + 0.04)]
        lathe(m, "metal.black", prof, 10, caps=False)


BENCH_FORMS = {"sleek": ("block_top", "steel", "floating", "block_top", "steel", "floating"),
               "civic": ("slats_back", "slats", "slats_back", "mesh", "slats", "slats_back"),
               "heavy": ("concrete", "slats", "concrete", "block_top", "slats", "concrete"),
               "neon": ("slats", "mesh", "neon", "slats_back", "neon", "mesh"),
               "old": ("cast", "slats_back", "cast", "stone", "slats_back", "stone")}


@gen("bench")
def bench(m: Mesh, d: D) -> None:
    form = d.form(BENCH_FORMS[d.style])
    L = d.r(1.6, 2.0, "L")
    hx = L / 2.0
    wood = d.c(("wood", "wood.light"), "wood")
    if form in ("slats", "slats_back", "cast", "neon"):
        legm = {"cast": "metal.black"}.get(form, "metal.dark")
        for x in (-hx * 0.8, hx * 0.8):
            if form == "cast":
                extrude(m, legm, [(-0.25, 0.0), (0.25, 0.0), (0.22, 0.44), (0.25, 0.9 if True else 0),
                                  (0.18, 0.9), (0.15, 0.48), (-0.22, 0.44)], "x", x - 0.03, x + 0.03)
            else:
                blk(m, legm, x - 0.03, x + 0.03, -0.22, 0.22, 0.0, 0.42)
        for k in range(4):
            y = -0.2 + k * 0.12
            blk(m, wood, -hx, hx, y, y + 0.09, 0.42, 0.46)
        if form in ("slats_back", "cast"):
            for k in range(3):
                z = 0.55 + k * 0.12
                blk(m, wood, -hx, hx, 0.22 + k * 0.01, 0.25 + k * 0.01, z, z + 0.09)
        if form == "neon":
            col = d.c(("neon.ff2a6d", "neon.05d9e8", "neon.b967ff"), "n")
            blk(m, col, -hx + 0.05, hx - 0.05, -0.15, 0.15, 0.06, 0.08)
    elif form == "steel":
        blk(m, "metal.chrome", -hx, hx, -0.22, 0.22, 0.42, 0.46)
        for x in (-hx * 0.85, hx * 0.85):
            blk(m, "metal.chrome", x - 0.02, x + 0.02, -0.2, 0.2, 0.0, 0.42)
    elif form == "floating":
        blk(m, "concrete", -0.2, 0.2, -0.15, 0.15, 0.0, 0.38)
        blk(m, "wood.light", -hx, hx, -0.25, 0.25, 0.38, 0.46)
    elif form == "block_top":
        blk(m, "concrete" if d.style == "heavy" else "stone", -hx, hx, -0.25, 0.25, 0.0, 0.4)
        blk(m, wood, -hx + 0.05, hx - 0.05, -0.22, 0.22, 0.4, 0.45)
    elif form == "concrete":
        blk(m, "concrete", -hx, hx, -0.3, 0.3, 0.0, 0.45)
        blk(m, "concrete", -hx, hx, 0.18, 0.3, 0.45, 0.85)
    elif form == "mesh":
        col = d.c(("metal.green", "metal.blue", "metal.red", "metal.dark"), "c")
        for k in range(8):
            y = -0.22 + k * 0.06
            blk(m, col, -hx, hx, y, y + 0.03, 0.42, 0.45)
        for x in (-hx * 0.85, hx * 0.85):
            blk(m, col, x - 0.03, x + 0.03, -0.22, 0.22, 0.0, 0.42)
        blk(m, col, -hx, hx, 0.24, 0.27, 0.5, 0.85)
    elif form == "stone":
        blk(m, "stone", -hx, hx, -0.27, 0.27, 0.0, 0.42)


@gen("kiosk")
def kiosk(m: Mesh, d: D) -> None:
    forms = {"sleek": ("pod", "glass", "pod", "glass"), "civic": ("news", "glass", "news", "coffee"),
             "heavy": ("container", "news", "container", "news"),
             "neon": ("neon", "news", "neon", "coffee"), "old": ("pavilion", "news", "pavilion", "news")}
    form = d.form(forms[d.style])
    wall = {"sleek": "metal.white", "heavy": "metal.galv", "old": "wood.red"}.get(
        d.style, d.c(("metal.green", "metal.dark", "metal.blue"), "w"))
    blk(m, wall, -1.05, 1.05, -1.05, 1.05, 0.0, 1.0)
    blk(m, wall, -1.05, 1.05, -1.05, 1.05, 2.0, 2.45)
    for x, y in ((-1.0, -1.0), (1.0, -1.0), (-1.0, 1.0), (1.0, 1.0)):
        blk(m, wall, x - 0.05, x + 0.05, y - 0.05, y + 0.05, 1.0, 2.0)
    blk(m, "glass.prop" if form in ("glass", "pod") else "metal.dark", -0.98, 0.98, -0.98, 0.98,
        1.0, 2.0)
    blk(m, "wood", 1.05, 1.3, -0.95, 0.95, 0.95, 1.02)
    if form == "pavilion":
        for s in (-1.0, 1.0):
            sheet(m, "wood.red", (-1.4, 0.0, 3.0), (1.4, 0.0, 3.0), (1.5, s * 1.5, 2.45),
                  (-1.5, s * 1.5, 2.45), (0.0, s * 0.5, 1.0))
        lantern(m, "metal.black", "light.red", 1.2, 0.0, 1.9, 0.5)
    else:
        blk(m, wall, -1.3, 1.3, -1.3, 1.3, 2.45, 2.6)
    band = {"neon": d.c(("neon.ff2a6d", "neon.05d9e8", "neon.b967ff"), "b"),
            "coffee": "screen.amber", "news": "screen.white"}.get(form, "light.cool")
    for s in (-1.0, 1.0):
        quad_out(m, band, (1.304, s * -1.1, 2.47), (1.304, s * 1.1, 2.47), (1.304, s * 1.1, 2.58),
                 (1.304, s * -1.1, 2.58), (1.0, 0.0, 0.0))
        del s
        break
    if form in ("news", "neon"):
        for k in range(4):
            y = -0.9 + k * 0.45
            blk(m, d.c(("screen.white", "screen.magenta", "screen.cyan", "screen.amber"), "mag", k),
                -1.08, -1.06, y, y + 0.35, 1.1, 1.6)


VEND_FORMS = {"sleek": ("screen", "drinks", "screen", "drinks", "lockers", "screen"),
              "civic": ("drinks", "snacks", "drinks", "ticket", "snacks", "drinks"),
              "heavy": ("snacks", "drinks", "ticket", "snacks", "drinks", "ticket"),
              "neon": ("drinks", "noodle", "capsule", "drinks", "noodle", "snacks"),
              "old": ("capsule", "drinks", "snacks", "capsule", "drinks", "noodle")}
VEND_COLORS = ("metal.red", "metal.blue", "metal.white", "metal.yellow", "metal.dark",
               "metal.green", "plastic.orange")


@gen("vending_machine")
def vending_machine(m: Mesh, d: D) -> None:
    form = d.form(VEND_FORMS[d.style])
    body = d.c(VEND_COLORS, "body") if d.style != "sleek" else d.c(("metal.white", "metal.dark"),
                                                                   "body")
    w, dep, h = 1.0, 0.8, 1.9
    if form == "capsule":
        for j in range(2):
            y = -0.25 + j * 0.5
            blk(m, body, -0.2, 0.2, y - 0.2, y + 0.2, 0.0, 0.9)
            lathe(m, "glass.prop", [(0.18, 0.9), (0.2, 1.1), (0.15, 1.3), (0.0, 1.35)], 10, 0.0, y)
        return
    blk(m, body, -dep / 2.0, dep / 2.0, -w / 2.0, w / 2.0, 0.0, h)
    fx = dep / 2.0 + 0.004
    if form in ("drinks", "snacks", "noodle"):
        lit = d.c(("screen.white", "screen.cyan", "screen.amber", "screen.magenta"), "lit")
        quad_out(m, "glass.dark" if form == "snacks" else lit, (fx, -0.42, 0.75), (fx, 0.2, 0.75),
                 (fx, 0.2, 1.8), (fx, -0.42, 1.8), (1.0, 0.0, 0.0))
        if form == "snacks":
            for k in range(5):
                blk(m, lit, fx - 0.05, fx - 0.01, -0.4, 0.18, 0.85 + k * 0.19, 0.87 + k * 0.19)
        quad_out(m, "metal.black", (fx, 0.25, 1.2), (fx, 0.43, 1.2), (fx, 0.43, 1.6),
                 (fx, 0.25, 1.6), (1.0, 0.0, 0.0))
        blk(m, "metal.black", fx - 0.02, fx + 0.03, -0.42, 0.2, 0.25, 0.45)
        if form == "noodle":
            blk(m, d.c(("neon.ff2a6d", "neon.05d9e8"), "n"), fx, fx + 0.02, -0.48, 0.48, 1.84, 1.88)
    elif form in ("screen", "ticket"):
        quad_out(m, "screen.cyan", (fx, -0.3, 1.0), (fx, 0.3, 1.0), (fx, 0.3, 1.55),
                 (fx, -0.3, 1.55), (1.0, 0.0, 0.0))
        blk(m, "metal.black", fx - 0.02, fx + 0.08, -0.35, 0.35, 0.85, 0.95)
    elif form == "lockers":
        for i in range(3):
            for j in range(4):
                y0 = -0.48 + i * 0.32
                z0 = 0.05 + j * 0.46
                quad_out(m, "metal.galv", (fx, y0 + 0.01, z0), (fx, y0 + 0.31, z0),
                         (fx, y0 + 0.31, z0 + 0.44), (fx, y0 + 0.01, z0 + 0.44), (1.0, 0.0, 0.0))


@gen("food_stall")
def food_stall(m: Mesh, d: D) -> None:
    forms = {"sleek": ("cart", "booth", "cart", "booth", "cart", "booth"),
             "civic": ("cart", "canopy", "cart", "canopy", "booth", "cart"),
             "heavy": ("container", "canopy", "container", "canopy", "container", "canopy"),
             "neon": ("canopy", "neon", "canopy", "neon", "cart", "neon"),
             "old": ("lantern", "canopy", "lantern", "canopy", "lantern", "canopy")}
    form = d.form(forms[d.style])
    wood = d.c(("wood", "wood.light", "wood.red"), "w")
    fab = d.c(FABRICS, "fab")
    if form == "container":
        blk(m, d.c(("metal.blue", "metal.rust", "metal.green"), "c"), -1.5, 1.5, -1.0, 1.0, 0.0, 2.5)
        blk(m, "metal.dark", 1.5, 1.52, -0.8, 0.8, 0.95, 2.0)
        sheet(m, "metal.galv", (1.5, -1.0, 2.5), (1.5, 1.0, 2.5), (2.4, 1.0, 2.2),
              (2.4, -1.0, 2.2), (0.3, 0.0, 1.0))
        blk(m, "screen.amber", 1.51, 1.53, -0.9, 0.9, 2.1, 2.4)
        return
    blk(m, wood, -1.4, 1.4, -0.9, 0.9, 0.2, 1.0)
    blk(m, "metal.galv", -1.45, 1.45, -0.95, 0.95, 1.0, 1.05)
    blk(m, "metal.dark", -0.6, 0.6, -0.5, 0.2, 1.05, 1.25)
    if form == "cart":
        for x in (-1.0, 1.0):
            wheel(m, x, -0.98, -0.88, 0.2, "metal.galv")
            wheel(m, x, 0.88, 0.98, 0.2, "metal.galv")
        for x, y in ((-1.3, -0.8), (1.3, -0.8), (-1.3, 0.8), (1.3, 0.8)):
            tube(m, "metal.galv", [(x, y, 1.05), (x, y, 2.3)], 0.025, 5)
        lathe(m, fab, [(1.9, 2.3), (0.05, 2.75)], 12)
        lathe(m, fab, [(0.0, 2.29), (1.9, 2.296)], 12, caps=False)    # its underside, facing down
    elif form == "booth":
        blk(m, d.c(("metal.white", "metal.galv"), "b"), -1.4, 1.4, -0.9, 0.9, 1.25, 2.4)
        blk(m, "glass.prop", -1.38, 1.38, -0.92, -0.9, 1.3, 2.1)
        blk(m, "screen.cyan", -1.2, 1.2, -0.95, -0.92, 2.15, 2.35)
    else:
        for x, y in ((-1.4, -0.9), (1.4, -0.9), (-1.4, 0.9), (1.4, 0.9)):
            tube(m, "metal.galv" if form != "lantern" else "wood", [(x, y, 0.0), (x, y, 2.5)],
                 0.04, 5)
        for s in (-1.0, 1.0):
            quad_out(m, fab, (-1.7, 0.0, 2.9), (1.7, 0.0, 2.9), (1.7, s * 1.25, 2.4),
                     (-1.7, s * 1.25, 2.4), (0.0, s * 0.5, 1.0))
            quad_out(m, fab, (-1.7, 0.0, 2.896), (1.7, 0.0, 2.896), (1.7, s * 1.25, 2.396),
                     (-1.7, s * 1.25, 2.396), (0.0, -s * 0.5, -1.0))
        if form in ("lantern", "neon", "canopy"):
            n = 5
            for j in range(n):
                x = -1.5 + 3.0 * j / (n - 1)
                col = "light.red" if form == "lantern" else d.c(
                    ("light.warm", "neon.ff2a6d", "neon.05d9e8", "neon.ffb000"), "bulb", j)
                lathe(m, col, [(0.0, 2.05), (0.12 if form == "lantern" else 0.06, 2.15),
                               (0.0, 2.32 if form == "lantern" else 2.25)], 8, x, -1.2)
            tube(m, "metal.black", [(-1.6, -1.2, 2.38), (1.6, -1.2, 2.38)], 0.006, 3)
        if form == "neon":
            col = d.c(("neon.ff2a6d", "neon.05d9e8", "neon.b967ff", "neon.39ff8a"), "sign")
            blk(m, "sign.back", -1.0, 1.0, -0.94, -0.9, 1.3, 1.9)
            for k in range(3):
                tube(m, col, [(-0.8 + k * 0.6, -0.96, 1.4), (-0.6 + k * 0.6, -0.96, 1.8),
                              (-0.4 + k * 0.6, -0.96, 1.4)], 0.02, 4)
    for x in (-1.0, 0.0, 1.0):
        lathe(m, "metal.dark", [(0.03, 0.0), (0.03, 0.62)], 6, x, -1.4)
        lathe(m, "plastic.red", [(0.18, 0.62), (0.18, 0.67), (0.0, 0.68)], 8, x, -1.4)


@gen("planter")
def planter(m: Mesh, d: D) -> None:
    forms = {"sleek": ("square", "round", "long", "square", "round"),
             "civic": ("square", "round", "wood", "square", "round"),
             "heavy": ("square", "corten", "square", "corten", "round"),
             "neon": ("round", "wood", "square", "round", "corten"),
             "old": ("urn", "wood", "urn", "stone", "wood")}
    form = d.form(forms[d.style])
    h = d.r(0.55, 0.7, "h")
    if form in ("square", "corten", "wood", "stone", "long"):
        mat = {"corten": "metal.rust", "wood": "wood", "stone": "stone"}.get(
            form, "concrete" if d.style != "sleek" else "metal.white")
        hx = 0.6 if form != "long" else 0.9
        blk(m, mat, -hx, hx, -0.55, 0.55, 0.0, h)
        m.poly("soil", [(-hx + 0.05, -0.5), (hx - 0.05, -0.5), (hx - 0.05, 0.5), (-hx + 0.05, 0.5)],
               z=h + 0.002)
    elif form == "round":
        lathe(m, "concrete" if d.style != "sleek" else "metal.white",
              [(0.5, 0.0), (0.6, h), (0.55, h + 0.02)], 14)
    elif form == "urn":
        lathe(m, "stone", [(0.25, 0.0), (0.25, 0.1), (0.12, 0.2), (0.15, 0.3), (0.45, h * 0.8),
                           (0.5, h), (0.45, h + 0.02)], 12)
    leaf = d.c(("foliage.boxwood", "foliage.scrub", "foliage.sedum"), "leaf")
    leaf_blob(m, leaf, 0.0, 0.0, h - 0.05, d.r(0.4, 0.55, "br"), d.r(0.35, 0.7, "bh"),
              (*d.key, "blob"))


# ---------------------------------------------------------------------------------------
# vehicles and boats
# ---------------------------------------------------------------------------------------

CAR_FORMS = {"sleek": ("wedge", "sedan", "pod", "wedge", "sedan", "pod", "wedge", "suv",
                       "sedan", "pod", "wedge", "sedan"),
             "civic": ("sedan", "hatch", "suv", "taxi", "van", "sedan", "hatch", "suv",
                       "sedan", "taxi", "hatch", "pickup"),
             "heavy": ("van", "pickup", "box", "sedan", "van", "pickup", "box", "suv",
                       "van", "pickup", "sedan", "box"),
             "neon": ("kei", "taxi", "hatch", "kei", "wedge", "taxi", "kei", "sedan",
                      "hatch", "taxi", "kei", "wedge"),
             "old": ("kei", "tuk", "hatch", "van", "kei", "tuk", "sedan", "kei", "hatch",
                     "tuk", "van", "kei")}
CAR_PAINT = ("car.red", "car.white", "car.black", "car.silver", "car.blue", "car.teal",
             "car.olive", "car.white", "car.silver", "car.black")


@gen("parked_vehicle")
def parked_vehicle(m: Mesh, d: D) -> None:
    form = d.form(CAR_FORMS[d.style])
    paint = "car.yellow" if form == "taxi" else d.c(CAR_PAINT, "paint")
    L = {"kei": 3.4, "tuk": 2.8, "pod": 3.0, "van": 4.8, "box": 5.6, "pickup": 5.0,
         "suv": 4.7}.get(form, 4.5)
    W = {"kei": 1.5, "tuk": 1.4, "pod": 1.6, "box": 2.1, "van": 1.95}.get(form, 1.82)
    hx, hy = L / 2.0, W / 2.0
    r = 0.32 if form not in ("kei", "tuk", "pod") else 0.26
    z0 = 0.22
    if form == "tuk":
        extrude(m, paint, [(-hx, z0), (hx * 0.7, z0), (hx, 0.6), (hx * 0.85, 1.0), (hx * 0.4, 1.6),
                           (-hx, 1.65)], "y", -hy, hy)
        blk(m, "fabric.black", -hx, hx * 0.4, -hy - 0.02, hy + 0.02, 1.65, 1.72)
        for x, y0, y1 in ((hx * 0.65, -0.06, 0.06), (-hx * 0.6, -hy, -hy + 0.15),
                          (-hx * 0.6, hy - 0.15, hy)):
            wheel(m, x, y0, y1, 0.24, "metal.galv")
        return
    if form in ("van", "box"):
        body = [(-hx, z0), (hx, z0), (hx, 1.0), (hx - 0.25, 1.9 if form == "van" else 2.2),
                (-hx, 1.95 if form == "van" else 2.6)]
        extrude(m, paint if form == "van" else "metal.white", body, "y", -hy, hy)
        if form == "box":
            extrude(m, paint, [(hx - 1.4, z0 + 0.4), (hx, z0 + 0.4), (hx, 1.2), (hx - 0.3, 2.0),
                               (hx - 1.4, 2.05)], "y", -hy + 0.02, hy - 0.02)
        quad_out(m, "glass.dark", (hx + 0.004, -hy + 0.12, 1.15), (hx + 0.004, hy - 0.12, 1.15),
                 (hx - 0.2, hy - 0.12, 1.8), (hx - 0.2, -hy + 0.12, 1.8), (1.0, 0.0, 0.3))
    else:
        low_top = {"wedge": 0.85, "pod": 1.0, "suv": 1.05, "pickup": 1.0}.get(form, 0.9)
        cab_top = {"wedge": 1.25, "pod": 1.55, "suv": 1.75, "kei": 1.6, "pickup": 1.75,
                   "hatch": 1.48, "taxi": 1.45}.get(form, 1.42)
        extrude(m, paint, [(-hx, z0 + 0.1), (-hx + 0.1, z0), (hx - 0.15, z0), (hx, z0 + 0.15),
                           (hx, low_top - 0.1), (hx - 0.3, low_top), (-hx + 0.1, low_top),
                           (-hx, low_top - 0.12)], "y", -hy, hy)
        if form == "pickup":
            cab = [(0.0, low_top), (hx * 0.62, low_top), (hx * 0.4, cab_top), (0.15, cab_top)]
        elif form in ("hatch", "kei", "pod"):
            cab = [(-hx + 0.05, low_top), (hx * 0.55, low_top), (hx * 0.25, cab_top),
                   (-hx + 0.15, cab_top)]
        elif form == "wedge":
            cab = [(-hx * 0.7, low_top), (hx * 0.45, low_top), (-hx * 0.05, cab_top),
                   (-hx * 0.55, cab_top)]
        else:
            cab = [(-hx * 0.62, low_top), (hx * 0.4, low_top), (hx * 0.12, cab_top),
                   (-hx * 0.45, cab_top)]
        extrude(m, "glass.dark", cab, "y", -hy + 0.1, hy - 0.1)
        (xa, _), (xb, _), (xc, zc), (xd, _) = cab
        blk(m, paint, xd, xc, -hy + 0.1, hy - 0.1, cab_top, cab_top + 0.04)
        if form == "taxi":
            blk(m, "screen.amber", (xc + xd) / 2.0 - 0.25, (xc + xd) / 2.0 + 0.25, -0.12, 0.12,
                cab_top + 0.04, cab_top + 0.22)
        if form == "pickup":
            blk(m, paint, -hx, 0.0, -hy, hy, low_top, low_top + 0.35)
            blk(m, "metal.black", -hx + 0.05, -0.05, -hy + 0.06, hy - 0.06, low_top + 0.05,
                low_top + 0.36)
    # lights and wheels
    for s in (-1.0, 1.0):
        blk(m, "light.warm", hx - 0.02, hx + 0.005, s * (hy - 0.35) - 0.15, s * (hy - 0.35) + 0.15,
            0.62, 0.72)
        blk(m, "light.red", -hx - 0.005, -hx + 0.02, s * (hy - 0.3) - 0.15, s * (hy - 0.3) + 0.15,
            0.7, 0.8)
    wx = hx - (0.85 if form not in ("kei", "pod") else 0.6)
    for x in (wx, -wx + (0.3 if form == "box" else 0.0)):
        for y0, y1 in ((-hy - 0.01, -hy + 0.2), (hy - 0.2, hy + 0.01)):
            wheel(m, x, y0, y1, r, "metal.galv")
    if d.style == "neon" and d.u("glow") < 0.5:
        col = d.c(("neon.ff2a6d", "neon.05d9e8", "neon.b967ff"), "under")
        blk(m, col, -hx * 0.6, hx * 0.6, -hy + 0.1, hy - 0.1, 0.08, 0.1)


BOAT_FORMS = {"sleek": ("speed", "cruiser", "speed", "cruiser", "speed", "cruiser"),
              "civic": ("launch", "cruiser", "fishing", "launch", "cruiser", "fishing"),
              "heavy": ("barge", "tug", "fishing", "barge", "tug", "fishing"),
              "neon": ("launch", "party", "speed", "party", "launch", "fishing"),
              "old": ("sampan", "fishing", "sampan", "launch", "sampan", "fishing")}


@gen("boat")
def boat(m: Mesh, d: D) -> None:
    """A boat 8 m long and 3 m wide at its base size, the waterline at z 0."""
    form = d.form(BOAT_FORMS[d.style])
    hull = {"barge": "metal.rust", "tug": "hull.red", "sampan": "wood"}.get(
        form, d.c(("hull.white", "hull.blue", "hull.red", "hull.white"), "hull"))
    L, W = 8.0, 3.0
    deck = 0.6 if form not in ("barge",) else 0.8
    keel = -0.6
    if form == "barge":
        extrude(m, hull, [(-L / 2.0, keel), (L / 2.0 - 0.6, keel), (L / 2.0, deck),
                          (-L / 2.0, deck)], "y", -W / 2.0, W / 2.0)
        for k in range(2):
            blk(m, d.c(("metal.blue", "metal.red", "metal.green"), "cont", k), -2.8 + k * 2.7,
                -0.4 + k * 2.7, -1.1, 1.1, deck, deck + 1.3)
        return
    # stations from stern to bow: half width and keel depth
    rows, uvs = [], []
    n_st = 9
    for i in range(n_st):
        t = i / (n_st - 1)
        x = -L / 2.0 + L * t
        bow = max(0.0, (t - 0.6) / 0.4)
        hw = W / 2.0 * (1.0 - bow * bow * 0.97) * (0.92 if t < 0.05 else 1.0)
        kz = keel * (1.0 - 0.6 * bow) + (0.0 if form != "sampan" else 0.25 * (2 * t - 1) ** 2)
        dz = deck + (0.35 * bow * bow if form not in ("sampan",) else 0.6 * (2 * t - 1) ** 2)
        sec = []
        for j in range(7):
            a = M.PI * j / 6
            sec.append((x, -hw * M.cos(a), kz + (dz - kz) * (1.0 - M.sin(a)) * 0.9
                        + (dz - kz) * 0.1 * (1.0 - M.sin(a))))
        sec[0] = (x, -hw, dz)
        sec[-1] = (x, hw, dz)
        rows.append(sec)
        uvs.append([(x, v) for v in arcs(sec)])
    m.grid(hull, rows, uvs, flip=True)
    deck_ring = [(p[0], p[1]) for p in (r[-1] for r in rows)] + \
        [(p[0], p[1]) for p in (r[0] for r in rows[::-1])]
    m.poly("wood.light" if form != "barge" else "metal.galv", deck_ring, z=deck - 0.05)
    fan(m, hull, (-L / 2.0, 0.0, (deck + keel) / 2.0), [r[j] for r in rows[:1] for j in range(7)],
        (-1.0, 0.0, 0.0))
    if form in ("launch", "cruiser", "party", "tug"):
        cx0, cx1 = (-2.5, 0.8) if form != "tug" else (-1.0, 1.5)
        blk(m, "hull.white" if hull != "hull.white" else "metal.white", cx0, cx1, -1.0, 1.0,
            deck - 0.05, deck + (1.1 if form != "tug" else 1.8))
        blk(m, "glass.dark", cx1 - 0.02, cx1 + 0.005, -0.8, 0.8, deck + 0.4,
            deck + (0.95 if form != "tug" else 1.6))
        if form == "party":
            for k in range(6):
                col = d.c(("neon.ff2a6d", "neon.05d9e8", "neon.ffb000", "neon.b967ff"), "b", k)
                lathe(m, col, [(0.0, deck + 1.3), (0.07, deck + 1.4), (0.0, deck + 1.5)], 6,
                      -2.4 + k * 0.6, 0.0)
        if form == "tug":
            lathe(m, "metal.black", [(0.2, deck + 1.8), (0.2, deck + 2.6)], 8, -0.3, 0.0)
    elif form == "speed":
        quad_out(m, "glass.dark", (-0.2, -1.0, deck), (-0.2, 1.0, deck), (-0.6, 1.0, deck + 0.5),
                 (-0.6, -1.0, deck + 0.5), (1.0, 0.0, 0.6))
        blk(m, "plastic.white", -2.5, -1.0, -1.0, 1.0, deck - 0.05, deck + 0.45)
    elif form == "fishing":
        blk(m, "hull.white", -1.5, 0.2, -0.9, 0.9, deck - 0.05, deck + 1.4)
        tube(m, "metal.galv", [(1.0, 0.0, deck), (1.0, 0.0, deck + 4.0)], 0.06, 6)
        tube(m, "metal.galv", [(1.0, 0.0, deck + 1.5), (-2.8, 0.0, deck + 2.6)], 0.04, 5)
    elif form == "sampan":
        pts = []
        for i in range(9):
            a = M.PI * i / 8
            pts.append((-1.1 * M.cos(a), deck + 0.6 + 0.6 * M.sin(a)))
        rows2 = [[(x, y, z) for y, z in pts] for x in (-2.0, 0.6)]
        m.grid("fabric.cream" if d.u("roof") < 0.5 else "cardboard", rows2,
               [[(x, v) for v in arcs(pts)] for x in (-2.0, 0.6)], flip=True)
        m.grid("cardboard", [[(x, y, z - 0.01) for y, z in pts] for x in (-2.0, 0.6)],
               [[(x, v) for v in arcs(pts)] for x in (-2.0, 0.6)])


# ---------------------------------------------------------------------------------------
# barriers, railings, dumpsters, trash
# ---------------------------------------------------------------------------------------

@gen("barrier")
def barrier(m: Mesh, d: D) -> None:
    forms = {"sleek": ("jersey", "steel", "jersey", "steel"), "civic": ("jersey", "striped", "jersey", "steel"),
             "heavy": ("jersey", "steel", "jersey", "striped"),
             "neon": ("striped", "plastic", "jersey", "plastic"),
             "old": ("jersey", "plastic", "striped", "jersey")}
    form = d.form(forms[d.style])
    prof = [(-0.3, 0.0), (0.3, 0.0), (0.3, 0.08), (0.21, 0.3), (0.08, 0.81), (-0.08, 0.81),
            (-0.21, 0.3), (-0.3, 0.08)]
    if form == "jersey":
        extrude(m, "concrete", prof, "x", -1.98, 1.98)
    elif form == "striped":
        for k in range(4):
            extrude(m, "plastic.red" if k % 2 == 0 else "paint.white", prof, "x",
                    -1.98 + k * 0.99, -1.98 + (k + 1) * 0.99 - 0.004)
    elif form == "plastic":
        extrude(m, d.c(("plastic.orange", "plastic.white", "plastic.red"), "c"),
                [(-0.25, 0.0), (0.25, 0.0), (0.2, 0.75), (-0.2, 0.75)], "x", -0.95, 0.95)
        extrude(m, d.c(("plastic.white", "plastic.orange"), "c2"),
                [(-0.25, 0.0), (0.25, 0.0), (0.2, 0.75), (-0.2, 0.75)], "x", 1.0, 1.95)
    elif form == "steel":
        for x in (-1.6, 0.0, 1.6):
            blk(m, "metal.galv", x - 0.05, x + 0.05, -0.05, 0.05, 0.0, 0.75)
        for s in (-1.0, 1.0):
            extrude(m, "metal.galv", [(s * 0.08, 0.45), (s * 0.16, 0.5), (s * 0.08, 0.55),
                                      (s * 0.16, 0.6), (s * 0.08, 0.7), (s * 0.06, 0.7),
                                      (s * 0.06, 0.45)], "x", -2.0, 2.0)


@gen("railing")
def railing(m: Mesh, d: D) -> None:
    forms = {"sleek": ("glass", "steel", "glass", "steel"), "civic": ("steel", "bars", "steel", "bars"),
             "heavy": ("pipe", "chain", "pipe", "chain"), "neon": ("steel", "led", "bars", "led"),
             "old": ("cast", "bars", "cast", "chain")}
    form = d.form(forms[d.style])
    met = {"sleek": "metal.chrome", "old": "metal.black", "heavy": "metal.yellow"}.get(
        d.style, "metal.galv")
    top = 1.05
    posts = (-1.45, 0.0) if form != "chain" else (-1.45,)
    for x in posts:
        if form == "cast":
            lathe(m, met, [(0.05, 0.0), (0.035, 0.1), (0.03, top - 0.05), (0.05, top)], 6, x, 0.0)
        else:
            tube(m, met, [(x, 0.0, 0.0), (x, 0.0, top)], 0.03, 6)
    if form != "chain":
        tube(m, met, [(-1.5, 0.0, top), (1.5, 0.0, top)], 0.03 if form != "glass" else 0.025, 6)
    if form == "glass":
        blk(m, "glass.prop", -1.45, 1.45, -0.01, 0.01, 0.1, top - 0.05)
    elif form in ("steel", "led", "pipe"):
        for z in (0.35, 0.7):
            tube(m, met, [(-1.5, 0.0, z), (1.5, 0.0, z)], 0.018, 5)
        if form == "led":
            col = d.c(("neon.05d9e8", "neon.ff2a6d", "neon.b967ff"), "led")
            blk(m, col, -1.5, 1.5, -0.012, 0.012, top - 0.05, top - 0.03)
    elif form in ("bars", "cast"):
        tube(m, met, [(-1.5, 0.0, 0.08), (1.5, 0.0, 0.08)], 0.015, 4)
        for k in range(20):
            x = -1.425 + k * 0.15
            tube(m, met, [(x, 0.0, 0.08), (x, 0.0, top)], 0.01, 4, caps=False)
    elif form == "chain":
        lathe(m, met, [(0.06, 0.0), (0.06, 0.8), (0.0, 0.85)], 8, -1.45, 0.0)
        tube(m, "metal.galv", catenary((-1.45, 0.0, 0.7), (1.55, 0.0, 0.7), 0.2, 8), 0.012, 4)


@gen("dumpster")
def dumpster(m: Mesh, d: D) -> None:
    forms = {"sleek": ("bin", "closed", "bin", "closed", "bin"),
             "civic": ("bin", "lidded", "bin", "lidded", "closed"),
             "heavy": ("skip", "lidded", "skip", "bin", "lidded"),
             "neon": ("bin", "lidded", "open", "bin", "lidded"),
             "old": ("open", "lidded", "skip", "open", "bin")}
    form = d.form(forms[d.style])
    col = d.c(("plastic.green", "metal.blue", "plastic.grey", "metal.rust", "metal.yellow",
               "metal.dark"), "c")
    if form == "skip":
        extrude(m, col, [(-1.0, 0.0), (1.0, 0.0), (1.25, 1.1), (-1.25, 1.1)], "y", -0.65, 0.65)
        m.poly("bag.black", [(-1.15, -0.6), (1.15, -0.6), (1.15, 0.6), (-1.15, 0.6)], z=0.95)
        return
    extrude(m, col, [(-0.6, 0.12), (0.6, 0.12), (0.65, 1.25), (-0.68, 1.25)], "x", -1.0, 1.0)
    for x in (-0.8, 0.8):
        for y in (-0.45, 0.45):
            lathe(m, "rubber", [(0.08, 0.0), (0.08, 0.12)], 6, x, y)
    for s in (-1.0, 1.0):
        blk(m, col, -0.75, 0.75, s * 0.66 - 0.04, s * 0.66 + 0.04, 0.6, 0.75)
    if form in ("lidded", "closed", "bin"):
        lid = "plastic.black" if form != "closed" else col
        sheet(m, lid, (-1.02, -0.7, 1.25), (1.02, -0.7, 1.25), (1.02, 0.7, 1.32),
              (-1.02, 0.7, 1.32), (0.0, -0.1, 1.0))
        if form == "bin":
            sheet(m, "plastic.black", (-0.98, 0.7, 1.32), (0.98, 0.7, 1.32), (0.98, 1.1, 1.9),
                  (-0.98, 1.1, 1.9), (0.0, -0.8, 0.6))
    elif form == "open":
        m.poly("bag.black", [(-0.95, -0.6), (0.95, -0.6), (0.95, 0.62), (-0.95, 0.62)], z=1.1)
        for k in range(3):
            leaf_blob(m, "bag.black", -0.6 + k * 0.6, 0.0, 1.1, 0.35, 0.3, (*d.key, "bag", k), 7)


@gen("trash")
def trash(m: Mesh, d: D) -> None:
    """Variants 0 to 3 bags, 4 to 7 boxes, 8 to 11 cans (M6's `attrs.item`)."""
    item = ("bag", "box", "can")[min(d.k // 4, 2)]
    if item == "bag":
        n = 1 + d.k % 3
        for j in range(n):
            col = d.c(("bag.black", "bag.black", "plastic.green", "plastic.blue"), "c", j)
            a = 2.0 * M.PI * ST.u(*d.key, "a", j)
            cx, cy = 0.2 * j * M.cos(a), 0.2 * j * M.sin(a)
            leaf_blob(m, col, cx, cy, 0.0, d.r(0.22, 0.3, "r", j), d.r(0.35, 0.5, "h", j),
                      (*d.key, "lump", j), 8)
            lathe(m, col, [(0.04, d.r(0.35, 0.5, "h", j) - 0.02), (0.02, d.r(0.35, 0.5, "h", j) + 0.1)],
                  5, cx, cy)
    elif item == "box":
        n = 1 + d.k % 2
        for j in range(n):
            s = d.r(0.3, 0.5, "s", j)
            x0 = -0.25 + j * 0.3
            blk(m, "cardboard", x0, x0 + s, -s / 2.0, s / 2.0, j * 0.02, j * 0.02 + s * 0.7)
            quad_out(m, "cardboard", (x0, -s / 2.0, s * 0.7 + j * 0.02), (x0 + s, -s / 2.0, s * 0.7 + j * 0.02),
                     (x0 + s, -s / 2.0 - 0.2, s * 0.9), (x0, -s / 2.0 - 0.2, s * 0.9), (0.0, -0.5, 1.0))
    else:
        for j in range(3 + d.k % 3):
            a = 2.0 * M.PI * ST.u(*d.key, "a", j)
            cx, cy = 0.15 * M.cos(a) * (j % 3), 0.15 * M.sin(a) * (j % 3)
            col = d.c(("metal.red", "metal.galv", "metal.blue", "plastic.green", "glass.prop"),
                      "c", j)
            if ST.u(*d.key, "lie", j) < 0.6:
                tube(m, col, [(cx - 0.06 * M.cos(a), cy - 0.06 * M.sin(a), 0.033),
                              (cx + 0.06 * M.cos(a), cy + 0.06 * M.sin(a), 0.033)], 0.033, 6)
            else:
                lathe(m, col, [(0.033, 0.0), (0.033, 0.12), (0.0, 0.125)], 6, cx, cy)


# ---------------------------------------------------------------------------------------
# kinds made per tile (their M6 geometry exactly): cables, scaffolding, gates
# ---------------------------------------------------------------------------------------

def cable(m: Mesh, p: dict, style: str) -> None:
    """An overhead cable bundle across a street: from facade to facade at the prop's height,
    `attrs.sag_m` at its middle (1 to 3 strands, lanterns on some in neon and old districts)."""
    x, y, z = p["position"]
    a = M.radians(p["yaw_deg"])
    c, s = M.cos(a), M.sin(a)
    h = p["scale"][0] / 2.0
    sag = float((p.get("attrs") or {}).get("sag_m", 0.4))
    n = 1 + ST.pick(3, "ag8.cable", p["id"])
    for j in range(n):
        off = (j - (n - 1) / 2.0) * 0.12
        za = z + off * 0.5
        A = (x + c * h - s * off, y + s * h + c * off, za)
        B = (x - c * h - s * off, y - s * h + c * off, za + 0.1 * j)
        tube(m, "metal.black", catenary(A, B, sag * (1.0 + 0.25 * j), 12), 0.012 + 0.004 * (j == 0),
             4)
    if style in ("neon", "old") and ST.u("ag8.lanterns", p["id"]) < 0.5:
        k = 3 + ST.pick(4, "ag8.lan_n", p["id"])
        pts = catenary((x + c * h, y + s * h, z), (x - c * h, y - s * h, z), sag, k + 1)
        for i, q in enumerate(pts[1:-1]):
            col = ("light.red", "light.amber", "neon.ff2a6d", "neon.05d9e8")[
                ST.pick(4, "ag8.lan_c", p["id"], i if style == "neon" else 0)]
            lantern(m, "metal.black", col, q[0], q[1], q[2] - 0.45, 0.42, 6)


def scaffold(m: Mesh, p: dict, wall_sign: float) -> None:
    """Scaffolding along a facade: bays of standards, ledgers, planks, braces and debris
    netting, M6's length (scale x) and height (scale z), 1.2 m deep; `wall_sign` is the
    local side of the wall (+1: +y)."""
    x, y, z0 = p["position"]
    a = M.radians(p["yaw_deg"])
    c, s = M.cos(a), M.sin(a)
    L, H = p["scale"][0], p["scale"][2]
    bays = max(1, int(round(L / 2.4)))
    bw = L / bays
    lifts = max(1, int(H // 2.0))

    def P(u, v, w):
        # u along, v out of the wall (the wall at v = -0.8 + ...), in the world
        vv = -v * wall_sign
        return (x + c * u - s * vv, y + s * u + c * vv, z0 + w)
    back, front = -0.6, 0.6
    for i in range(bays + 1):
        u = -L / 2.0 + i * bw
        for v in (back, front):
            tube(m, "metal.galv", [P(u, v, 0.0), P(u, v, lifts * 2.0 + 1.0)], 0.024, 4)
    for k in range(lifts + 1):
        w = k * 2.0 + (0.0 if k == 0 else 0.0)
        for v in (back, front):
            tube(m, "metal.galv", [P(-L / 2.0, v, w + 0.15), P(L / 2.0, v, w + 0.15)], 0.024, 4)
        if k:
            for i in range(bays):
                u0 = -L / 2.0 + i * bw + 0.05
                u1 = u0 + bw - 0.1
                ring4 = [P(u0, back + 0.05, w + 0.2), P(u1, back + 0.05, w + 0.2),
                         P(u1, front - 0.05, w + 0.2), P(u0, front - 0.05, w + 0.2)]
                sheet(m, "wood.light", *ring4, (0.0, 0.0, 1.0))
            tube(m, "metal.galv", [P(-L / 2.0, front, w + 1.1), P(L / 2.0, front, w + 1.1)], 0.02, 4)
    for i in range(bays):
        u0 = -L / 2.0 + i * bw
        if i % 2 == 0:
            tube(m, "metal.galv", [P(u0, front, 0.1), P(u0 + bw, front, min(2.0 * lifts, 4.0))],
                 0.02, 4)
        if ST.u("ag8.net", p["id"], i) < 0.7:
            quad_out(m, "net.debris", P(u0 + 0.03, front + 0.04, 0.2), P(u0 + bw - 0.03, front + 0.04, 0.2),
                     P(u0 + bw - 0.03, front + 0.04, lifts * 2.0 + 0.9),
                     P(u0 + 0.03, front + 0.04, lifts * 2.0 + 0.9),
                     (s * wall_sign, -c * wall_sign, 0.0))


def gate(m: Mesh, p: dict, style: str, words) -> None:
    """A market gate 8 m wide over the street (M6 scales it to 8 m): columns, beams, a roof
    with upturned ends in old and neon districts (a steel arch elsewhere), the market's name
    on the lintel (`words`: (strokes builder) from signs.py)."""
    x, y, z0 = p["position"]
    a = M.radians(p["yaw_deg"])
    c, s = M.cos(a), M.sin(a)
    W = 8.0 * p["scale"][0] / 8.0

    def P(u, v, w):
        return (x + c * u - s * v, y + s * u + c * v, z0 + w)
    red = "wood.red" if style in ("old", "neon") else "metal.dark"
    for u in (-W / 2.0 + 0.3, W / 2.0 - 0.3):
        tube(m, red, [P(u, 0.0, 0.0), P(u, 0.0, 6.0)], 0.28, 8)
        tube(m, "stone", [P(u, 0.0, 0.0), P(u, 0.0, 0.6)], 0.42, 8)
    tube(m, red, [P(-W / 2.0 - 0.4, 0.0, 5.2), P(W / 2.0 + 0.4, 0.0, 5.2)], 0.22, 6)
    tube(m, red, [P(-W / 2.0 - 0.2, 0.0, 4.2), P(W / 2.0 + 0.2, 0.0, 4.2)], 0.16, 6)
    if style in ("old", "neon"):
        for sv in (-1.0, 1.0):
            sheet(m, "concrete.dark", P(-W / 2.0 - 0.6, 0.0, 6.6), P(W / 2.0 + 0.6, 0.0, 6.6),
                  P(W / 2.0 + 1.0, sv * 1.2, 6.0), P(-W / 2.0 - 1.0, sv * 1.2, 6.0),
                  (-s * sv * 0.5, c * sv * 0.5, 1.0))
        tube(m, "concrete.dark", [P(-W / 2.0 - 1.1, 0.0, 6.9), P(-W / 2.0 - 0.5, 0.0, 6.62),
                                  P(W / 2.0 + 0.5, 0.0, 6.62), P(W / 2.0 + 1.1, 0.0, 6.9)], 0.12, 6)
    else:
        pts = [P(-W / 2.0 + 0.3 + (W - 0.6) * t, 0.0, 6.0 + 1.2 * M.sin(M.PI * t))
               for t in (i / 12 for i in range(13))]
        tube(m, red, pts, 0.15, 6)
    # the name board between the beams, both faces
    if words is not None:
        words(m, P, W)
