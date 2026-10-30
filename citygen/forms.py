"""Building forms (M21): towers, slabs and mid-rises that are not prisms on a podium.

A tower's shaft stands on its podium on a base plate (`massing.Plate`: a rectangle with sharp,
cut or rounded corners, a circle or a four-centre oval), in one of these forms:

| Form | Shaft |
|---|---|
| box | the plate extruded (M3's tower) |
| chamfer, rounded | the plate with cut or rounded corners |
| setback | three or four tiers stepping in |
| round, oval | a circle (in drums stepping in) or an oval |
| taper | bands of two or three floors, each smaller than the one under it |
| twist | a band a floor (two over 48 floors), each turned up to 3 degrees from the one under it |
| lean | bands moved further one way the higher they stand |
| stack | three to five blocks of their own size, turned and offset |
| cantilever | a slimmer shaft with one or two blocks reaching out over the podium |
| split | two shafts of two heights with a slot between them, bridged by links |
| garden | a shaft with sky gardens cut through it: a core and corner columns, open round |
| gate | a shaft with a void through its upper floors under a lintel |
| exo | a shaft in an exoskeleton frame (columns standing off the facade, belts) |
| pods | a core with capsule pods on its faces |

and a crown: flat, tiers (an inset top), sloped or cut (the top floors cut back along a line or
a diagonal), halo (a ring over the roof on struts), mast or spire. A district's `variety` sets
which forms its towers draw (box and the mild forms where it is low, the bold ones where it is
high) and how far they go (twist, taper, lean). Every mass of a form is a prism of the model,
so every check and consumer reads it as it is; the bands of a twisted, tapered or leaning
shaft carry their turn, scale and shift from the base plate, and `Building.form` the form,
its pivot and parameters, so stage 2 can draw them as one surface.

Slabs depart too where the archetype allows: curved (an annular sector, its arcs exact) or
stepped (falling in steps along the street).

Determinism: shapes come from `Plate` (dmath angles, grid points), choices from the lot's or
the complex's own generators, fits from exact predicates (`covers`) on grid geometry.
"""

from __future__ import annotations

import math

from shapely.geometry import Polygon

from . import dmath as M
from . import geom as G
from . import massing as MS

q = G.q

FORMS = ("box", "chamfer", "rounded", "setback", "round", "oval", "taper", "twist", "lean",
         "stack", "cantilever", "split", "garden", "gate", "exo", "pods")
MILD = ("box", "chamfer", "rounded", "setback", "round", "taper")
# the least variety a bold form needs
BOLD_MIN = {"oval": 0.25, "stack": 0.3, "cantilever": 0.35, "garden": 0.35, "exo": 0.35,
            "twist": 0.45, "split": 0.45, "lean": 0.5, "gate": 0.5, "pods": 0.5}
# forms a complex's towers take (their skybridges need facing facades, which bands lack)
COMPLEX_FORMS = ("box", "chamfer", "rounded", "setback")
# forms of a tower on an odd plate (no rectangle fits: the region itself)
POLY_FORMS = ("box", "setback", "taper", "terrace", "wedge")
FORM_INDEX = {f: i for i, f in enumerate(FORMS + ("terrace", "wedge"))}   # generator salts
CROWNS = ("flat", "tiers", "sloped", "cut", "halo", "mast", "spire")
SHAFT_ROLES = ("tower", "band", "tier", "crown", "block", "link", "core", "column", "frame", "pod",
               "halo", "strut", "mast", "spire")
ACCESSORY = ("spire", "mast", "halo", "strut")     # above the roof, not floors
MAX_TWIST_DEG = 3.0
BAND_FORMS = ("taper", "twist", "lean")            # shafts in bands


def weights(v: float, allowed=FORMS) -> list:
    """Draw weights of the forms a district of variety v allows."""
    out = []
    for f in allowed:
        if f == "box":
            w = 0.35 + 2.2 * (1.0 - v)
        elif f in MILD or f in ("terrace", "wedge"):
            w = 0.7 + 0.5 * v
        else:
            if v < BOLD_MIN.get(f, 1.0):
                continue
            w = 0.4 + 2.6 * v * v
        out.append((f, w))
    return out


def order(v: float, rng, allowed=FORMS) -> list[str]:
    """The forms a district of variety v allows, in a weighted order drawn without
    replacement (the first is the tower's own choice, the rest its fallbacks)."""
    ws = weights(v, allowed)
    out = []
    while ws:
        f = MS.pick(rng, ws)
        out.append(f)
        ws = [(k, w) for k, w in ws if k != f]
    if "box" not in out:
        out.append("box")
    return out


def put(b, plate, z0: float, z1: float, role: str = "tower", turn: float = 0.0,
        scale: float = 1.0, shift=(0.0, 0.0), roof: bool = True, poly=None,
        shape: str = "prism") -> int:
    """A mass of a plate (or a polygon cut from it) with its arcs and its turn, scale and
    shift; its index in the building's masses, or -1."""
    p = plate.polygon() if poly is None else poly
    arcs = plate.arcs() if poly is None and plate is not None else []
    meta = {"arcs": arcs, "turn": q(turn) if turn else 0.0, "scale": round(scale, 4) + 0.0,
            "shift": (q(shift[0]), q(shift[1]))}
    n = len(b.masses)
    b.add(p, z0, z1, role, shape=shape, roof=roof, meta=meta)
    return n if len(b.masses) > n else -1


class Shaft:
    """What a tower form builds with: the building, its base plate, the shaft's foot P and
    the building's top H, the district's variety, where the shaft may stand (`inner`) and
    where anything over the podium may reach (`room`), both prepared."""

    def __init__(self, b, plate, P: float, H: float, v: float, inner, room, rng, hi: float):
        self.b, self.plate, self.P, self.H, self.v = b, plate, float(P), float(H), float(v)
        self.inner, self.room, self.rng, self.hi = inner, room, rng, float(hi)
        self.fh = b.fh
        self.params: dict = {}
        self.first = len(b.masses)
        self.crown = "flat"

    def u(self, lo: float, hi: float) -> float:
        return MS.uniform(self.rng, lo, hi)

    def r(self) -> float:
        return float(self.rng.random())

    def fits(self, poly) -> bool:
        return poly.is_valid and self.inner.covers(poly)

    def floor(self, z: float) -> float:
        """z down to the floor grid over P."""
        return q(self.P + max(0, int((z - self.P) / self.fh + 1e-9)) * self.fh)


# ---------------------------------------------------------------------------
# Crowns
# ---------------------------------------------------------------------------

def _crowns(S: Shaft, form: str, plate) -> list:
    sharp = plate is not None and plate.r <= 0.0 and not plate.oval
    out = [("flat", 1.0), ("tiers", 0.8)]
    if sharp and form not in ("exo",):
        out += [("sloped", 0.5 + S.v), ("cut", 0.4 + S.v)]
    if plate is not None and min(plate.hw, plate.hd) >= 8.0 and form not in ("exo", "pods"):
        out.append(("halo", 0.3 + 0.8 * S.v))
    if S.H >= 90.0:
        out.append(("mast", 0.5 + 0.4 * S.v))
    if S.H > 120.0 and S.H > 0.75 * S.hi:
        out.append(("spire", 0.9))
    if form in ("stack", "cantilever", "split", "pods", "gate", "garden", "exo"):
        out = [(c, w) for c, w in out if c in ("flat", "mast", "spire", "halo")]
    return out


def crown_reserve(S: Shaft, crown: str) -> float:
    """Height the crown takes above the shaft's roof."""
    H = S.H
    if crown == "spire":
        return q(min(H * 0.12, 40.0))
    if crown == "mast":
        return q(min(max(H * 0.1, 8.0), 30.0))
    if crown == "halo":
        return 5.0
    return 0.0


def crown_floors(S: Shaft, crown: str, floors: int) -> int:
    """Floors of the shaft's top the crown takes (tiers, sloped, cut)."""
    if crown == "tiers":
        return max(2, int(floors * S.u(0.08, 0.16)))
    if crown in ("sloped", "cut"):
        return max(3, min(8, int(floors * S.u(0.1, 0.2))))
    return 0


def crown_in(S: Shaft, crown: str, plate, z0: float, z1: float, turn: float = 0.0,
             shift=(0.0, 0.0)) -> bool:
    """The crown's floors from z0 to the shaft's roof z1 on the top plate."""
    b, fh = S.b, S.fh
    if crown == "tiers":
        c = plate.grown(-S.u(2.5, 4.5))
        if min(c.hw, c.hd) < 4.0:
            put(b, plate, z0, z1, "crown", turn=turn, shift=shift)
        else:
            put(b, c, z0, z1, "crown", turn=turn, shift=shift)
        return True
    if crown in ("sloped", "cut"):
        n = max(1, int(round((z1 - z0) / fh)))
        poly = plate.polygon()
        k = int(S.r() * 4)
        f = plate.fr.turned(k * M.HALF_PI + (M.PI / 4.0 if crown == "cut" else 0.0))
        lo, _, hi, _ = f.bounds(poly)
        depth = (hi - lo) * S.u(0.45, 0.75)
        z = z0
        for j in range(n):
            lim = hi - depth * (j + 1) / n
            part = G.parts(G.inter(poly, MS.halfplane(f, u_max=lim)))
            if not part or G.area1(part[0]) < 30.0:
                break
            za = z1 if j == n - 1 else q(z + fh)
            put(b, None, z, za, "crown", poly=part[0])
            z = za
        S.params["crown_slope_m"] = q(depth)
        return True
    return False


def crown_up(S: Shaft, crown: str, plate, top: float, turn: float = 0.0,
             shift=(0.0, 0.0)) -> str:
    """The crown above the roof at `top`, up to the building's top: a halo on struts, a
    mast or a spire on the plate's middle; the crown it built."""
    b, H = S.b, S.H
    if H - top < 1.0:
        return "flat"
    cx, cy = plate.fr.ox, plate.fr.oy
    if crown == "halo":
        z0 = q(top + 3.0)
        ring_o, ring_i = plate.grown(1.5), plate.grown(-2.5)
        hole = ring_i.polygon()
        outer = ring_o.polygon()
        halo = Polygon(outer.exterior.coords, [hole.exterior.coords])
        if halo.is_valid and S.room.covers(outer):
            n = put(b, None, z0, H, "halo", poly=halo, roof=False)
            if n >= 0:
                b.masses[n] = b.masses[n][:5] + ({"arcs": ring_o.arcs() + ring_i.arcs(),
                                                  "turn": q(turn), "scale": 1.0,
                                                  "shift": (q(shift[0]), q(shift[1]))},)
            for du, dv in ((plate.hw - 1.0, 0.0), (0.0, plate.hd - 1.0),
                           (1.0 - plate.hw, 0.0), (0.0, 1.0 - plate.hd)):
                c = plate.fr.moved(du, dv)
                put(b, None, top, z0, "strut", roof=False, poly=c.rect(-0.5, -0.5, 0.5, 0.5))
            return "halo"
        crown = "mast"
    if crown == "mast":
        m = MS.Plate(MS.Frame(cx, cy, plate.fr.angle), 1.3, 1.3, 1.3)
        put(b, m, top, H, "mast", roof=False)
        return "mast"
    f = MS.Frame(cx, cy, plate.fr.angle)
    put(b, None, top, H, "spire", roof=False, poly=f.rect(-1.5, -1.5, 1.5, 1.5))
    return "spire"


# ---------------------------------------------------------------------------
# Shafts: each builds from P to z1 (the crown's foot) and returns its top plate with its
# turn and shift, or None when it does not fit
# ---------------------------------------------------------------------------

def _bands(S: Shaft, z1: float, nb: int) -> list[tuple[float, float]]:
    out = []
    z = S.P
    while z < z1 - 1e-6:
        za = min(z1, q(z + nb * S.fh))
        if z1 - za < S.fh - 1e-6:
            za = z1
        out.append((z, za))
        z = za
    return out


def f_box(S: Shaft, z1: float):
    put(S.b, S.plate, S.P, z1)
    return S.plate, 0.0, (0.0, 0.0)


def f_chamfer(S: Shaft, z1: float):
    p = S.plate
    c = min(max(S.u(0.12, 0.22) * 2.0 * min(p.hw, p.hd), 2.0), 7.0)
    S.plate = MS.Plate(p.fr, p.hw, p.hd, c=c)
    S.params["chamfer_m"] = q(c)
    return f_box(S, z1)


def f_rounded(S: Shaft, z1: float):
    p = S.plate
    r = S.u(0.25, 0.6) * min(p.hw, p.hd)
    S.plate = p.rounded(r)
    S.params["corner_r_m"] = q(r)
    return f_box(S, z1)


def f_setback(S: Shaft, z1: float):
    p = S.plate
    n = 4 if (z1 - S.P) >= 40 * S.fh else 3
    step = S.u(2.0, 4.0)
    if min(p.hw, p.hd) - (n - 1) * step < 6.0:
        n = 3
        step = (min(p.hw, p.hd) - 6.0) / 2.0
        if step < 1.5:
            return None
    if S.r() < 0.4:
        p = S.plate = MS.Plate(p.fr, p.hw, p.hd, c=min(4.0, 0.15 * min(p.hw, p.hd)))
    fracs = (0.45, 0.7, 0.87, 1.0) if n == 4 else (0.55, 0.82, 1.0)
    z = S.P
    top = p
    for i, fz in enumerate(fracs):
        za = z1 if i == n - 1 else S.floor(S.P + (z1 - S.P) * fz)
        if za <= z:
            continue
        top = p.grown(-step * i)
        put(S.b, top, z, za, "tower" if i == 0 else "tier")
        z = za
    S.params["setback_m"] = q(step)
    return top, 0.0, (0.0, 0.0)


def f_round(S: Shaft, z1: float):
    p = S.plate
    R = min(p.hw, p.hd)
    if R < 8.0:
        return None
    base = MS.Plate(p.fr, R, R, R)
    S.plate = base
    drums = (R >= 13.0 and S.r() < 0.55)
    if not drums:
        put(S.b, base, S.P, z1)
        return base, 0.0, (0.0, 0.0)
    za = S.floor(S.P + (z1 - S.P) * S.u(0.5, 0.65))
    zb = S.floor(za + (z1 - za) * S.u(0.5, 0.7))
    put(S.b, base, S.P, za)
    mid = base.grown(-1.8)
    if zb <= za or zb >= z1:
        put(S.b, mid, za, z1, "tier")
        return mid, 0.0, (0.0, 0.0)
    put(S.b, mid, za, zb, "tier")
    top = base.grown(-3.6)
    put(S.b, top, zb, z1, "tier")
    S.params["drums"] = 3.0
    return top, 0.0, (0.0, 0.0)


def f_oval(S: Shaft, z1: float):
    p = S.plate
    a, c = max(p.hw, p.hd), min(p.hw, p.hd)
    if c < 8.0:
        return None
    if a < 1.15 * c:
        c = max(8.0, a * S.u(0.62, 0.78))
    hw, hd = (a, c) if p.hw >= p.hd else (c, a)
    S.plate = MS.Plate(p.fr, hw, hd, oval=True)
    return f_box(S, z1)


def f_taper(S: Shaft, z1: float):
    p = S.plate
    floors = int(round((z1 - S.P) / S.fh))
    nb = 2 if floors <= 36 else 3
    s_top = 1.0 - (0.18 + 0.32 * S.v) * S.u(0.8, 1.0)
    if min(p.hw, p.hd) * s_top < 6.0:
        s_top = 6.0 / min(p.hw, p.hd)
        if s_top >= 0.95:
            return None
    if S.r() < 0.5:
        p = S.plate = p.rounded(S.u(0.15, 0.35) * min(p.hw, p.hd))
    bands = _bands(S, z1, nb)
    n = len(bands)
    top = p
    for k, (z, za) in enumerate(bands):
        f = 1.0 - (1.0 - s_top) * (k / (n - 1) if n > 1 else 0.0)
        top = p.scaled(f)
        put(S.b, top, z, za, "band", scale=f)
    S.params.update({"taper": round(s_top, 4), "band_floors": float(nb)})
    return top, 0.0, (0.0, 0.0)


def f_twist(S: Shaft, z1: float):
    p = S.plate
    s = min(p.hw, p.hd)
    d = s * (1.0 if S.r() < 0.6 else S.u(0.75, 0.9))
    hw, hd = (s, d) if p.hw >= p.hd else (d, s)
    corner = S.u(0.15, 0.4) * min(hw, hd)
    base = MS.Plate(p.fr, hw, hd, r=corner) if S.r() < 0.7 else \
        MS.Plate(p.fr, hw, hd, c=min(0.3 * min(hw, hd), 6.0))
    rate = min(MAX_TWIST_DEG, 0.6 + 2.6 * S.v) * S.u(0.75, 1.0)
    sign = 1.0 if S.r() < 0.5 else -1.0
    floors = int(round((z1 - S.P) / S.fh))
    nb = 1 if floors <= 48 else 2
    total = min(rate * floors, 180.0)
    rate = total / max(floors, 1)
    bands = _bands(S, z1, nb)
    for _ in range(4):
        disc = MS.circle(base.fr.ox, base.fr.oy, base.reach + 0.05)
        ok = S.fits(disc) or all(
            S.fits(base.turned(sign * float(M.radians(rate * (z - S.P) / S.fh))).polygon())
            for z, _ in bands)
        if ok:
            break
        base = base.scaled(0.9)
        if min(base.hw, base.hd) < 7.0:
            return None
    else:
        return None
    S.plate = base
    top, turn = base, 0.0
    for z, za in bands:
        turn = sign * rate * (z - S.P) / S.fh
        top = base.turned(float(M.radians(turn)))
        put(S.b, top, z, za, "band", turn=turn)
    S.params.update({"twist_deg_per_floor": round(sign * rate, 4),
                     "twist_deg": round(sign * rate * floors, 4), "band_floors": float(nb)})
    return top, turn, (0.0, 0.0)


def _slide(S: Shaft, plate, ux: float, uy: float, step: float = 0.5,
           limit: int = 80) -> tuple[float, float]:
    """How far the plate moves along (ux, uy) back and forth inside `inner`."""
    lo = hi = 0.0
    for k in range(1, limit + 1):
        if not S.fits(plate.shifted(ux * k * step, uy * k * step).polygon()):
            break
        hi = k * step
    for k in range(1, limit + 1):
        if not S.fits(plate.shifted(-ux * k * step, -uy * k * step).polygon()):
            break
        lo = -k * step
    return lo, hi


def f_lean(S: Shaft, z1: float):
    p = S.plate
    if S.r() < 0.4:
        p = S.plate = p.rounded(S.u(0.15, 0.4) * min(p.hw, p.hd))
    theta = float(M.radians((2.5 + 6.0 * S.v) * S.u(0.8, 1.0)))
    want = (z1 - S.P) * float(M.tan(theta))
    best = None
    k0 = int(S.r() * 4)
    for k in range(4):
        a = p.fr.angle + ((k0 + k) % 4) * M.HALF_PI
        ux, uy = float(M.cos(a)), float(M.sin(a))
        lo, hi = _slide(S, p, ux, uy)
        L = min(hi - lo, want)
        if best is None or L > best[0] + 1e-9:
            best = (L, ux, uy, lo)
    L, ux, uy, lo = best
    if L < 5.0:
        return None
    floors = int(round((z1 - S.P) / S.fh))
    nb = 2 if floors <= 40 else 3
    bands = _bands(S, z1, nb)
    n = len(bands)
    top, sh = p, (0.0, 0.0)
    for k, (z, za) in enumerate(bands):
        d = lo + L * (k / (n - 1) if n > 1 else 0.0)
        sh = (q(ux * d), q(uy * d))
        top = p.shifted(*sh)
        if not S.fits(top.polygon()):
            return None
        put(S.b, top, z, za, "band", shift=sh)
    S.params.update({"lean_m": q(L), "lean_deg": round(float(M.degrees(M.atan2(
        L, z1 - S.P))), 4), "band_floors": float(nb)})
    return top, 0.0, sh


def f_stack(S: Shaft, z1: float):
    p = S.plate
    floors = int(round((z1 - S.P) / S.fh))
    n = min(5, max(3, int(round(floors / 10.0))))
    if floors < 3 * n:
        return None
    cuts = sorted(S.u(0.2, 0.8) for _ in range(n - 1))
    tops = []
    for i in range(n - 1):
        f = (i + 1 + cuts[i] - 0.5) / n
        tops.append(S.floor(S.P + (z1 - S.P) * f))
    tops.append(z1)
    z = S.P
    prev = None
    top = p
    turn = 0.0
    sh = (0.0, 0.0)
    for i, za in enumerate(tops):
        if za <= z:
            continue
        wide = (i % 2 == 0) == (S.r() < 0.75)
        fw, fd = (S.u(0.95, 1.25), S.u(0.62, 0.85)) if wide else \
            (S.u(0.62, 0.85), S.u(0.95, 1.25))
        t = (S.u(-1.0, 1.0) * (4.0 + 16.0 * S.v)) if i else 0.0
        du, dv = (S.u(-1.0, 1.0) * 4.0, S.u(-1.0, 1.0) * 4.0) if i else (0.0, 0.0)
        blk = None
        for _ in range(5):
            cand = MS.Plate(p.fr.moved(du, dv).turned(float(M.radians(t))), p.hw * fw,
                            p.hd * fd)
            poly = cand.polygon()
            if S.fits(poly) and (prev is None or G.area1(G.inter(poly, prev)) >=
                                 0.35 * G.area1(poly)):
                blk = cand
                break
            fw, fd, du, dv, t = fw * 0.92, fd * 0.92, du * 0.5, dv * 0.5, t * 0.6
        if blk is None or min(blk.hw, blk.hd) < 5.0:
            return None
        put(S.b, blk, z, za, "block" if i else "tower")
        prev = blk.polygon()
        top, turn = blk, t
        sh = (q(blk.fr.ox - p.fr.ox), q(blk.fr.oy - p.fr.oy))
        z = za
    S.params["blocks"] = float(n)
    return top, turn, sh


def f_cantilever(S: Shaft, z1: float):
    p = S.plate
    shaft = p.scaled(0.82)
    if min(shaft.hw, shaft.hd) < 7.0:
        return None
    put(S.b, shaft, S.P, z1)
    b, fh = S.b, S.fh
    k0 = int(S.r() * 4)
    done = 0
    for f_lo, f_hi in ((0.42, 0.62), (0.72, 0.86)):
        if done and S.r() < 0.4:
            break
        nf = 3 + int(S.r() * 4)
        z = S.floor(S.P + (z1 - S.P) * S.u(f_lo, f_hi))
        za = q(z + nf * fh)
        if za > z1 - 2 * fh or z <= S.P + 2 * fh:
            continue
        for j in range(4):
            k = (k0 + j + done) % 4
            f = shaft.fr.turned(k * M.HALF_PI)
            hw, hd = (shaft.hw, shaft.hd) if k % 2 == 0 else (shaft.hd, shaft.hw)
            w = hd * S.u(0.6, 1.0)
            reach = 6.0 + 10.0 * S.v
            blk = None
            while reach >= 5.0:
                r = f.rect(hw, -w, hw + reach, w)
                if r.is_valid and S.room.covers(r):
                    blk = r
                    break
                reach -= 1.5
            if blk is not None:
                put(b, None, z, za, "block", poly=blk)
                S.params[f"cantilever{done + 1}_m"] = q(reach)
                done += 1
                break
    if not done:
        return None
    return shaft, 0.0, (0.0, 0.0)


def f_split(S: Shaft, z1: float):
    p = S.plate
    along_u = p.hw >= p.hd
    hw, hd = (p.hw, p.hd) if along_u else (p.hd, p.hw)
    f = p.fr if along_u else p.fr.turned(M.HALF_PI)
    g = 4.0 + 4.0 * S.v
    half = (hw - g / 2.0) / 2.0
    if half < 4.5 or hd < 6.0:
        return None
    b, fh = S.b, S.fh
    zb = S.floor(S.P + (z1 - S.P) * S.u(0.72, 0.9))
    if zb - S.P < 8 * fh:
        return None
    r = S.u(0.0, 0.35) * min(half, hd) if S.v >= 0.6 and S.r() < 0.5 else 0.0
    A = MS.Plate(f.moved(-(g / 2.0 + half), 0.0), half, hd, r=r)
    B = MS.Plate(f.moved(g / 2.0 + half, 0.0), half, hd, r=r)
    tall, short = (A, B) if S.r() < 0.5 else (B, A)
    put(b, tall, S.P, z1)
    put(b, short, S.P, zb)
    zl = S.floor(S.P + (zb - S.P) * S.u(0.45, 0.6))
    nl = 2 + int(S.r() * 2)
    dl = min(hd * S.u(0.45, 0.75), hd - r)    # on the straight of both facades
    ext = g / 2.0
    put(b, None, zl, q(zl + nl * fh), "link", poly=f.rect(-ext, -dl, ext, dl))
    if zb - (zl + nl * fh) >= 8 * fh:
        put(b, None, q(zb - 2 * fh), zb, "link", poly=f.rect(-ext, -dl, ext, dl))
    S.params.update({"slot_m": q(g), "short_m": q(zb)})
    return tall, 0.0, (q(tall.fr.ox - p.fr.ox), q(tall.fr.oy - p.fr.oy))


def f_garden(S: Shaft, z1: float):
    p = S.plate
    if min(p.hw, p.hd) < 10.0:
        return None
    b, fh = S.b, S.fh
    floors = int(round((z1 - S.P) / S.fh))
    if floors < 14:
        return None
    voids = (S.u(0.4, 0.5), S.u(0.68, 0.78)) if floors >= 40 else (S.u(0.45, 0.65),)
    core = p.scaled(0.42)
    cs = min(max(0.12 * 2.0 * min(p.hw, p.hd), 2.0), 3.5)
    z = S.P
    for fz in voids:
        zv = S.floor(S.P + (z1 - S.P) * fz)
        nv = 2 + int(S.r() * 2)
        zt = q(zv + nv * fh)
        if zv <= z + 2 * fh or zt >= z1 - 2 * fh:
            continue
        put(b, p, z, zv)
        put(b, core, zv, zt, "core")
        cols = []
        for su, sv in ((1, 1), (-1, 1), (-1, -1), (1, -1)):
            c = p.fr.rect(su * p.hw - (cs if su > 0 else 0.0), sv * p.hd - (cs if sv > 0 else 0.0),
                          su * p.hw + (0.0 if su > 0 else cs), sv * p.hd + (0.0 if sv > 0 else cs))
            put(b, None, zv, zt, "column", poly=c, roof=False)
            cols.append(c)
        garden = G.parts(G.diff(p.polygon(), G.union([core.polygon()] + cols)))
        if garden:
            b.roofs.append((garden[0], q(zv), "garden"))
        z = zt
    if z == S.P:
        return None
    put(b, p, z, z1)
    S.params["gardens"] = float(len(voids))
    return p, 0.0, (0.0, 0.0)


def f_gate(S: Shaft, z1: float):
    p = S.plate
    along_u = p.hw >= p.hd
    hw, hd = (p.hw, p.hd) if along_u else (p.hd, p.hw)
    f = p.fr if along_u else p.fr.turned(M.HALF_PI)
    if hw < 11.0:
        return None
    b, fh = S.b, S.fh
    floors = int(round((z1 - S.P) / fh))
    nv = 3 + int(S.r() * 3)
    zg = S.floor(S.P + (z1 - S.P) * S.u(0.66, 0.78))
    zt = q(zg + nv * fh)
    if floors < 16 or zt > z1 - 3 * fh:
        return None
    ws = max(6.0, 2.0 * hw * S.u(0.3, 0.42))
    leg = hw - ws / 2.0
    if leg < 6.0:
        return None
    put(b, p, S.P, zg)
    put(b, None, zg, zt, poly=f.rect(-hw, -hd, -ws / 2.0, hd))
    put(b, None, zg, zt, poly=f.rect(ws / 2.0, -hd, hw, hd))
    put(b, p, zt, z1)
    S.params.update({"void_m": q(ws), "void_floors": float(nv)})
    return p, 0.0, (0.0, 0.0)


def f_exo(S: Shaft, z1: float):
    p = S.plate
    if S.r() < 0.4:
        p = S.plate = MS.Plate(p.fr, p.hw, p.hd, c=min(3.0, 0.12 * min(p.hw, p.hd)))
    b, fh = S.b, S.fh
    e, cs = 2.2, 1.4
    out = MS.Plate(p.fr, p.hw + e + cs / 2.0, p.hd + e + cs / 2.0)
    if not S.room.covers(out.polygon()):
        return None
    frame_top = q(z1 + 3.0) if S.crown in ACCESSORY else q(S.H)   # (the frame tops out)
    if frame_top > S.H + 1e-6:
        return None
    put(b, p, S.P, z1)
    hw, hd = p.hw + e, p.hd + e
    pts = []
    for L, axis in ((hw, "u"), (hd, "v")):
        n = max(1, int(round(2.0 * L / 14.0)))
        for i in range(n + 1):
            t = -L + 2.0 * L * i / n
            if axis == "u":
                pts += [(t, -hd), (t, hd)]
            else:
                pts += [(-hw, t), (hw, t)]
    seen = []
    for u, v in pts:
        key = (round(u, 3), round(v, 3))
        if key in seen:
            continue
        seen.append(key)
        put(b, None, S.P, frame_top, "frame", roof=False,
            poly=p.fr.rect(u - cs / 2.0, v - cs / 2.0, u + cs / 2.0, v + cs / 2.0))
    step = (8 + int(S.r() * 5)) * fh
    belt = Polygon(out.polygon().exterior.coords, [p.polygon().exterior.coords])
    z = S.P + step
    nbelt = 0
    while z < z1 - 2 * fh:
        put(b, None, q(z - 1.5), q(z), "frame", poly=belt, roof=False)
        z += step
        nbelt += 1
    put(b, None, z1, frame_top, "frame", poly=belt, roof=False)
    S.params.update({"frame_offset_m": e, "belts": float(nbelt + 1)})
    return p, 0.0, (0.0, 0.0)


def f_pods(S: Shaft, z1: float):
    p = S.plate
    core = p.scaled(0.62)
    if min(core.hw, core.hd) < 6.0:
        return None
    core = core.rounded(0.2 * min(core.hw, core.hd))
    b, fh = S.b, S.fh
    put(b, core, S.P, z1, "core")
    pd = min(3.4, 0.38 * min(p.hw, p.hd) - 0.3)
    pw = S.u(4.0, 5.5)
    if pd < 2.4:
        return None
    n = 0
    z = q(S.P + fh)
    lvl = 0
    while z < z1 - fh - 1e-6 and n < 64:
        for k in range(4):
            f = core.fr.turned(k * M.HALF_PI)
            hw, hd = (core.hw, core.hd) if k % 2 == 0 else (core.hd, core.hw)
            straight = hd - core.r
            slots = int((2.0 * straight) // (pw + 1.0))
            for i in range(slots):
                if S.r() > 0.45 or n >= 64:
                    continue
                c = -straight + (pw + 1.0) * (i + 0.5) + 0.5 * ((lvl + k) % 2)
                if c + pw / 2.0 > straight:
                    continue
                pod = f.rect(hw, c - pw / 2.0, hw + pd, c + pw / 2.0)
                put(b, None, z, q(z + fh), "pod", poly=pod)
                n += 1
        z = q(z + 2 * fh)
        lvl += 1
    S.params["pods"] = float(n)
    return core, 0.0, (0.0, 0.0)


SHAFTS = {"box": f_box, "chamfer": f_chamfer, "rounded": f_rounded, "setback": f_setback,
          "round": f_round, "oval": f_oval, "taper": f_taper, "twist": f_twist, "lean": f_lean,
          "stack": f_stack, "cantilever": f_cantilever, "split": f_split, "garden": f_garden,
          "gate": f_gate, "exo": f_exo, "pods": f_pods}


def _rollback(b, n_masses: int, n_roofs: int) -> None:
    del b.masses[n_masses:]
    del b.roofs[n_roofs:]


def tower(b, form: str, plate, P: float, H: float, v: float, inner, room, rng,
          hi: float, crown: str | None = None) -> bool:
    """The tower's shaft and crown on the podium (masses from P to H) in `form`; False (and
    nothing added) when the form does not fit. Sets `b.form`."""
    n_m, n_r = len(b.masses), len(b.roofs)
    S = Shaft(b, plate, P, H, v, inner, room, rng, hi)
    cs = _crowns(S, form, plate)
    if crown is None:
        crown = MS.pick(rng, cs)
    reserve = crown_reserve(S, crown)
    top = S.floor(H - reserve)
    floors = int(round((top - P) / b.fh))
    if floors < 4:
        crown, reserve, top = "flat", 0.0, S.floor(H)
        floors = int(round((top - P) / b.fh))
        if floors < 2:
            return False
    if crown == "flat" and form != "exo":
        top = q(H)
    elif crown in ("tiers", "sloped", "cut"):
        top = q(H)
    if form == "exo":
        top = S.floor(H - max(reserve, 3.0))
    nc = crown_floors(S, crown, floors) if crown in ("tiers", "sloped", "cut") else 0
    z1 = q(top - nc * b.fh) if nc and floors - nc >= 4 else top
    if z1 >= top:
        nc = 0
    S.crown = crown
    res = SHAFTS[form](S, z1)
    if res is None:
        _rollback(b, n_m, n_r)
        return False
    tp, turn, sh = res
    if nc:
        crown_in(S, crown, tp, z1, top, turn, sh)
    elif crown in ("tiers", "sloped", "cut"):
        crown = "flat"
    if crown in ACCESSORY:
        crown = crown_up(S, crown, tp, top, turn, sh)
    if not b.masses[n_m:]:
        _rollback(b, n_m, n_r)
        return False
    base = S.plate
    b.form = {"kind": form, "crown": crown, "pivot": (q(base.fr.ox), q(base.fr.oy)),
              "masses": list(range(n_m, len(b.masses))),
              "params": {k: v for k, v in sorted(S.params.items())}}
    return True


def tower_poly(b, form: str, poly, P: float, H: float, rng, crown: str | None = None) -> bool:
    """A tower on an odd plate (the region itself, no rectangle fits): box, setback (insets),
    taper (an inset per band), terrace (tiers cut back from one side) or wedge (the upper
    floors cut back one by one, a sloped top)."""
    fh = b.fh
    n_m, n_r = len(b.masses), len(b.roofs)
    floors = int(round((H - P) / fh))
    if floors < 6 and form != "box":
        return False
    if form == "box":
        b.add(poly, P, H, "body")
    elif form == "setback":
        z = P
        for i, fz in enumerate((0.5, 0.78, 1.0)):
            za = q(H) if i == 2 else q(P + int((H - P) * fz / fh) * fh)
            p = MS.inset(poly, 3.0 * i) if i else poly
            if p.is_empty or G.area1(p) < 60.0:
                _rollback(b, n_m, n_r)
                return False
            b.add(p, z, za, "body" if i == 0 else "tier")
            z = za
    elif form in ("terrace", "wedge"):
        # terrace: tiers cut back from one side; wedge: the upper floors cut back a floor at
        # a time along one side (a sloped top)
        k = int(float(rng.random()) * 4)
        f = b.fr.turned(k * M.HALF_PI)
        lo, _, hi, _ = f.bounds(poly)
        D = hi - lo
        if D < 18.0:
            return False
        cuts = []
        if form == "terrace":
            n = 4 if floors >= 16 else 3
            step = D * MS.uniform(rng, 0.12, 0.18)
            fr_z = (0.4, 0.65, 0.85, 1.0) if n == 4 else (0.5, 0.8, 1.0)
            z = P
            for i in range(n):
                za = q(H) if i == n - 1 else q(P + int((H - P) * fr_z[i] / fh) * fh)
                cuts.append((z, za, hi - step * i))
                z = za
        else:
            zb = q(P + int((H - P) * MS.uniform(rng, 0.55, 0.7) / fh) * fh)
            cuts.append((P, zb, hi))
            n = max(2, int(round((H - zb) / fh)))
            depth = D * MS.uniform(rng, 0.35, 0.55)
            z = zb
            for j in range(n):
                za = q(H) if j == n - 1 else q(z + fh)
                cuts.append((z, za, hi - depth * (j + 1) / n))
                z = za
        for z, za, lim in cuts:
            if za <= z:
                continue
            ps = G.parts(G.inter(poly, MS.halfplane(f, u_max=lim))) if lim < hi else [poly]
            if not ps or G.area1(ps[0]) < 60.0:
                _rollback(b, n_m, n_r)
                return False
            b.add(ps[0], z, za, "body" if z <= P else "tier")
    elif form == "taper":
        nb = 2 if floors <= 36 else 3
        z = P
        k = 0
        n = max(1, int(math.ceil(floors / nb)))
        while z < H - 1e-6:
            za = min(q(H), q(z + nb * fh))
            if H - za < fh - 1e-6:
                za = q(H)
            d = 6.0 * k / max(n - 1, 1)
            p = MS.inset(poly, d) if d > 0 else poly
            if p.is_empty or G.area1(p) < 60.0:
                _rollback(b, n_m, n_r)
                return False
            b.add(p, z, za, "body")
            z = za
            k += 1
    else:
        return False
    b.form = {"kind": form, "crown": crown or "flat", "pivot": G.centroid(poly),
              "masses": list(range(n_m, len(b.masses))), "params": {}}
    return True


# ---------------------------------------------------------------------------
# Slabs
# ---------------------------------------------------------------------------

SLAB_FORMS = ("curved", "stepped")


def slab_form(b, bar, region, H: float, v: float, rng) -> bool:
    """A slab of variety v that departs from its bar: curved (an annular sector bulging to
    the street or bowed back from it) or stepped (falling in three steps along the
    street). False when neither fits or the draw keeps the bar."""
    if v < 0.3 or float(rng.random()) >= 0.25 + 0.6 * (v - 0.3):
        return False
    fr = b.fr
    u0, v0, u1, v1 = fr.bounds(bar)
    W, D = u1 - u0, v1 - v0
    kind = "curved" if float(rng.random()) < 0.6 else "stepped"
    if kind == "curved" and W >= 24.0:
        s = W * MS.uniform(rng, 0.08, 0.16)
        bulge = float(rng.random()) < 0.6
        cu = (u0 + u1) / 2.0
        if bulge:   # the outer arc through the middle of the front, the ends receding
            Ro = (W * W / 4.0 + s * s) / (2.0 * s)
            Ri = Ro - D
            cv = v0 + Ro
            a = float(M.atan2(W / 2.0, math.sqrt(max(Ro * Ro - W * W / 4.0, 0.0))))
            a0 = -M.HALF_PI - a
        else:       # the inner arc through the front's ends, its middle bowed back
            Ri = (W * W / 4.0 + s * s) / (2.0 * s)
            Ro = Ri + D
            cv = v0 - math.sqrt(max(Ri * Ri - W * W / 4.0, 0.0))
            a = float(M.atan2(W / 2.0, math.sqrt(max(Ri * Ri - W * W / 4.0, 0.0))))
            a0 = M.HALF_PI - a
        if Ri > 8.0:
            x, y = fr.world(cu, cv)
            for f in (1.0, 0.9, 0.8):
                poly, arcs = MS.sector(x, y, Ri, Ro, fr.angle + a0 + 2.0 * a * (1.0 - f) / 2.0,
                                       2.0 * a * f)
                if poly.is_valid and region.covers(poly):
                    b.add(poly, 0.0, H, "slab", meta={"arcs": arcs})
                    b.form = {"kind": "curved", "crown": "flat", "pivot": (q(x), q(y)),
                              "masses": [len(b.masses) - 1],
                              "params": {"radius_m": q(Ro), "sagitta_m": q(s),
                                         "bulge": "out" if bulge else "in"}}
                    return True
    if W >= 30.0 and H >= 4 * b.fh:
        n = 3
        dirn = 1.0 if float(rng.random()) < 0.5 else -1.0
        first = len(b.masses)
        for i in range(n):
            a_, c_ = u0 + W * i / n, u0 + W * (i + 1) / n
            f = 1.0 - 0.22 * (i if dirn > 0 else n - 1 - i)
            Hi = max(2 * b.fh, q(int(H * f / b.fh + 1e-9) * b.fh))
            b.add(fr.rect(a_ - (0.0 if i == 0 else 0.0), v0, c_, v1), 0.0, Hi, "slab")
        b.form = {"kind": "stepped", "crown": "flat", "pivot": G.centroid(bar),
                  "masses": list(range(first, len(b.masses))), "params": {"steps": float(n)}}
        return True
    return False
