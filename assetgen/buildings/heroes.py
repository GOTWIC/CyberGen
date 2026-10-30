"""Hero landmarks (scope 5.1.5, 13.2 U2, 14.6: AG5): a generator for every landmark kind with
a detail budget of its own (`asset_checks` class "hero") and a unique mask texture baked per
building.

Every landmark is first the general shell of its masses (AG1 to AG4: tiers, crown, podium,
facade systems, street front); its hero generator then adds, by kind
(`building.landmark.<kind>`):

| kind | hero |
|---|---|
| megatower | light seams up every arm tip (the landmark's accent), aviation lights on the tips of every tier, sky gardens (planters, glass balustrades) on every setback, a crown halo, a needle spire with its rings and beacon |
| spire | light seams at the octagon's corners, a collar of lights at every tier, terraces with planters, the needle |
| arcology | planted terraces on every step, glass balustrades, the atrium under a glazed space frame, a communications mast with dishes on its crown |
| ferris_wheel (and M3's megasite wheel, `building.ferris_wheel`) | a twin rim tied by cross members, spokes, the hub and axle on a crossbeam between lattice legs, capsules round the rim, a light along each rim |
| any other | seams and terraces as a tower's |

The accent is the landmark's own (the asset spec's landmark palette, its most saturated
colour; else the district's neon). It colours the seams, halo and rim lights through a
material of the building's own (`hero_materials`).

**U2 bake** (`bake`): a 512 x 512 mask unique to the building, in three channels: grime
(from the ground, under every setback), leaks (streaks down from the sills of its own
windows, at their places) and wear (at its corners and roof edges). It maps by the hero UV
(`hero_uv`: u along each mass's facades, its perimeter coordinate over the longest
perimeter, v the height over the building's), written on UV1 of every slot of a hero's
shell but glass (whose UV1 is its pane's), so the masters darken, streak and wear the
building where its own geometry says. Integer-hash noise and elementwise arithmetic
(`materials.noise`): the same pixels on every machine.
"""

from __future__ import annotations

import math

import numpy as np

from citygen import dmath as M

from . import articulate as AR
from . import genome as GN
from . import parts as PT
from . import rings as RG
from . import roofs as RF
from . import systems as SY
from . import typeparts as TP
from .roofparts import bar
from .types import _count, _wall_free, facades, frame_of, put, put_on

HERO_KINDS = ("megatower", "spire", "arcology", "ferris_wheel")
MASK_PX = 512
SEAM_W = 500


def _u(key: str, purpose: str) -> float:
    return GN.u(key, purpose, "ag5.hero")


def is_hero(brief: dict) -> bool:
    """A landmark, or M3's megasite wheel."""
    b = brief["building"]
    return bool(b["landmark"]) or b["type"] == "building.ferris_wheel"


def is_hero_type(btype: str) -> bool:
    """A landmark's type, or the wheel's (a record's view of `is_hero`)."""
    return btype.startswith("building.landmark.") or btype == "building.ferris_wheel"


def kind_of(brief: dict) -> str:
    t = brief["building"]["type"]
    if t == "building.ferris_wheel":
        return "ferris_wheel"
    return t.rsplit(".", 1)[1] if t.startswith("building.landmark.") else "tower"


def accent(brief: dict, gm: dict) -> str:
    """The hero's accent colour: its landmark palette's most saturated, else the district's
    first neon, else a neon of the era's."""
    pal = list((brief["spec"].get("landmark") or {}).get("palette") or [])

    def sat(c):
        r, g, b = (int(c[1 + 2 * k:3 + 2 * k], 16) for k in range(3))
        return max(r, g, b) - min(r, g, b)
    if pal:
        return max(pal, key=lambda c: (sat(c), c))
    neon = list((brief["spec"].get("district") or {}).get("neon_palette") or [])
    if neon:
        return neon[0]
    return "#" + GN.pick(brief["id"], "accent", SY.NEONS, None, "ag5.hero")


# ---------------------------------------------------------------------------
# Hooks
# ---------------------------------------------------------------------------

def pre(sb) -> None:
    if not is_hero(sb.br):
        return
    sb.hero = {"kind": kind_of(sb.br), "accent": accent(sb.br, sb.gm)}


def mass(sb, ms) -> bool:
    """A hero's masses built its own way: a wheel's ring and legs, a needle for a spire
    mass."""
    if getattr(sb, "hero", None) is None:
        return False
    if ms["shape"] == "ring" or (sb.hero["kind"] == "ferris_wheel" and ms["role"] == "leg"):
        return wheel_mass(sb, ms)
    if ms["role"] in ("spire", "mast") and ms["shape"] == "prism":
        return _needle(sb, ms)
    return False


def post(sb) -> None:
    h = getattr(sb, "hero", None)
    if h is None:
        return
    k = h["kind"]
    if k == "ferris_wheel":
        _wheel_extras(sb)
        return
    _seams(sb)
    _terraces(sb, arcology=k == "arcology")
    if k == "megatower":
        _beacons(sb)
        _halo(sb)
    elif k == "spire":
        _collars(sb)
    elif k == "arcology":
        _atrium(sb)
        _crown_mast(sb)
    else:
        _beacons(sb)


# ---------------------------------------------------------------------------
# Towers
# ---------------------------------------------------------------------------

def _tiers(sb) -> list:
    return [ms for ms in sb.masses if ms["shape"] == "prism" and
            SY.role_group(ms["role"]) in ("body", "top") and ms["z1"] - ms["z0"] >= 6000 and
            ms["role"] not in ("spire", "mast")]


def _seams(sb) -> None:
    """Light seams up every sharp convex corner of the tiers (an arm's tips)."""
    n = 0
    for ms in _tiers(sb):
        for fa in facades(sb, ms):
            if fa.L < 2500 or fa.j is None:
                continue
            d = fa.d_in
            turn = d[0] * fa.uy - d[1] * fa.ux
            cosv = d[0] * fa.ux + d[1] * fa.uy
            if turn <= 0.34 or cosv > (0.75 if sb.hero["kind"] == "spire" else 0.5):
                continue                     # (a real convex corner only; a spire's octagon)
            s = max(min(fa.c0 // 2, 600), SEAM_W // 2 + 60)
            z0 = ms["z0"] + (600 if ms["z0"] > 50 else 4500)
            h = PT.q(ms["z1"] - z0 - 600)
            if h < 3000 or not _wall_free(sb, fa, s - SEAM_W // 2 - 40, s + SEAM_W // 2 + 40,
                                          z0, z0 + h):
                continue
            if put_on(sb, fa, "seam", {"w": SEAM_W, "h": h, "d": 140}, s, z0, "light_seam"):
                n += 1
    sb.stats["hero_seams"] = sb.stats.get("hero_seams", 0) + n


def _terraces(sb, arcology: bool = False) -> None:
    """Sky gardens on every setback: planters along the open roof edges of a tier with a
    tier on it, glass balustrades at those edges."""
    made = 0
    for ms in _tiers(sb) + [m for m in sb.masses if m["role"] == "podium"]:
        if AR._is_top(sb, ms) or ms.get("roof"):
            continue
        ring = RG.clean(ms["rings"][0])
        nr = len(ring)
        for i in range(nr):
            a, b = ring[i], ring[(i + 1) % nr]
            if sb._covered_above(ms, a, b):
                continue
            ux, uy, L = AR._unit(a, b)
            if L < 3500:
                continue
            put(sb, "terrace_rail", {"L": PT.q(L - 1200), "h": 1100, "style": "glass"},
                int(round(a[0] + ux * 600 - uy * 200)), int(round(a[1] + uy * 600 + ux * 200)),
                ms["z1"], ux, uy, "sky_balustrade")
            k = int((L - 1200) // 2800)
            for m in range(k):
                s = 900 + 2800 * m + 700
                x = int(round(a[0] + ux * s - uy * 1100))
                y = int(round(a[1] + uy * s + ux * 1100))
                if not RF._free(RF._bbox(x, y, ux, uy, 1600, 800), RF._taken(sb, ms)):
                    continue
                g = 700 if arcology else 450
                if put(sb, "garden", {"w": 1400, "d": 700, "h": 550, "g": g}, x, y, ms["z1"],
                       ux, uy, "sky_garden"):
                    made += 1
    sb.stats["sky_gardens"] = sb.stats.get("sky_gardens", 0) + made


def _beacons(sb) -> None:
    """Aviation lights on the roof at every tier's convex corners."""
    for ms in _tiers(sb):
        ring = RG.clean(ms["rings"][0])
        n = len(ring)
        for i in range(n):
            p0, p, p1 = ring[i - 1], ring[i], ring[(i + 1) % n]
            ax, ay, _ = AR._unit(p0, p)
            bx, by, _ = AR._unit(p, p1)
            if ax * by - ay * bx <= 0.34:
                continue
            ix, iy = (bx - ax), (by - ay)
            L = math.hypot(ix, iy) or 1.0
            x = int(round(p[0] + ix / L * 700))
            y = int(round(p[1] + iy / L * 700))
            if RG.in_poly((x, y), ms["rings"]) == 1:
                put(sb, "beacon", {"s": 250}, x, y, ms["z1"], bx, by, "beacon")


def _halo(sb) -> None:
    crown = next((ms for ms in sorted(sb.masses, key=lambda m: (-m["z1"], m["k"]))
                  if ms["role"] == "crown" and ms["shape"] == "prism"), None)
    if crown is None:
        return
    ring = RG.clean(crown["rings"][0])
    c, u, v, W, D = frame_of(ring)
    r1 = min(W, D) // 2 + 800
    p = {"r0": r1 - 900, "r1": r1, "t": 500, "n": 6, "post": 3500}
    if not put(sb, "halo", p, c[0], c[1], crown["z1"], u[0], u[1], "halo"):
        p["r1"], p["r0"] = r1 - 700, r1 - 1600
        put(sb, "halo", p, c[0], c[1], crown["z1"], u[0], u[1], "halo")


def _collars(sb) -> None:
    """A lit collar at the top of every tier of a spire (a band of the accent under its
    parapet, on every facade)."""
    for ms in _tiers(sb):
        z = ms["z1"] - 900
        for fa in facades(sb, ms):
            if fa.L < 2500 or fa.j is None:
                continue
            L = PT.q(fa.L - fa.c0 - fa.c1)
            if L >= 1500 and _wall_free(sb, fa, fa.c0, fa.c0 + L, z, z + 300):
                put_on(sb, fa, "neon_strip", {"L": L, "h": 300, "d": 100,
                                              "slot": "hero_light"}, fa.c0, z, "collar")


def _needle(sb, ms) -> bool:
    """A spire mass as a needle: tapering lengths with rings and a beacon on top."""
    ring = RG.clean(ms["rings"][0])
    if len(ring) < 3:
        return False
    c, u, v, W, D = frame_of(ring)
    h = PT.q(ms["z1"] - ms["z0"])
    r = max(min(W, D) // 2 - 100, 300)
    if not put(sb, "needle", {"h": h, "r": PT.q(r)}, c[0], c[1], ms["z0"], u[0], u[1],
               "needle"):
        return False
    sb.mass_info.append({"mass": ms["k"], "group": "structure", "system": None, "rows": 0,
                         "openings": 0, "needle": True})
    return True


def _crown_mast(sb) -> None:
    crown = next((ms for ms in sorted(sb.masses, key=lambda m: (-m["z1"], m["k"]))
                  if ms["shape"] == "prism"), None)
    if crown is None:
        return
    c, u, v, W, D = frame_of(crown["rings"][0])
    w0 = PT.q(min(W, D) * 55 // 100)
    put(sb, "lattice", {"w0": w0, "w1": PT.q(w0 // 3), "h": 18000, "bays": 6,
                        "slot": "mast"}, c[0], c[1], crown["z1"], u[0], u[1], "comm_mast")
    for k in range(3):
        a = 2.0 * M.PI * k / 3
        x = int(round(c[0] + float(M.cos(a)) * w0 * 0.3))
        y = int(round(c[1] + float(M.sin(a)) * w0 * 0.3))
        RF._place(sb, "antenna", {"h": 4000, "style": "dish"}, x, y, crown["z1"], u[0], u[1])


def _atrium(sb) -> None:
    """The atrium under a glazed space frame: over every court of a tier, at its top, a
    glass deck on a grid of members."""
    for ms in _tiers(sb):
        if len(ms["rings"]) < 2:
            continue
        for hole in ms["rings"][1:]:
            h = RG.clean(hole)[::-1]           # (a court runs clockwise; the roof's ring ccw)
            if len(h) < 3:
                continue
            sb.buf.new_part()
            if sb._extrude(h, None, ms["z1"] + 200, ms["z1"] + 320, "atrium_glass"):
                c, u, v, W, D = frame_of(h)
                for k in range(1, max(2, W // 4000)):
                    x0 = -W // 2 + W * k // max(2, W // 4000)
                    a = (int(round(c[0] + u[0] * x0 - v[0] * D // 2)),
                         int(round(c[1] + u[1] * x0 - v[1] * D // 2)), ms["z1"] + 120)
                    b = (int(round(c[0] + u[0] * x0 + v[0] * D // 2)),
                         int(round(c[1] + u[1] * x0 + v[1] * D // 2)), ms["z1"] + 120)
                    if RG.in_poly(a[:2], [h]) >= 0 and RG.in_poly(b[:2], [h]) >= 0:
                        sb.buf.new_part()
                        bar(sb.buf, "atrium_frame", a, b, 160, 200)
                _count(sb, "atrium_roof")


# ---------------------------------------------------------------------------
# Wheels
# ---------------------------------------------------------------------------

RIM_IN = 4200          # the rim's centreline this far inside the wheel's outer circle
RIM_GAP = 1100         # the two rims this far either side of the wheel's plane


def _wheel_frame(ms):
    """(centre, along, across, radius, hub z) of a ring mass: the wheel's plane along the
    footprint's longest edge (as AG1's wheel)."""
    ring = RG.clean(ms["rings"][0])
    n0 = len(ring)
    cx = sum(p[0] for p in ring) / n0
    cy = sum(p[1] for p in ring) / n0
    k = max(range(n0), key=lambda i: ((ring[(i + 1) % n0][0] - ring[i][0]) ** 2 +
                                      (ring[(i + 1) % n0][1] - ring[i][1]) ** 2, -i))
    ux, uy, _ = AR._unit(ring[k], ring[(k + 1) % n0])
    zc = ms["z0"] + (ms["z1"] - ms["z0"]) / 2.0
    R = (ms["z1"] - ms["z0"]) / 2.0
    return (cx, cy), (ux, uy), (-uy, ux), R, zc


def wheel_mass(sb, ms) -> bool:
    if ms["shape"] == "ring":
        return _wheel(sb, ms)
    if ms["role"] == "leg":
        return _leg(sb, ms)
    return False


def _wheel(sb, ms) -> bool:
    (cx, cy), (ux, uy), (vx, vy), R, zc = _wheel_frame(ms)
    r = R - RIM_IN
    if r < 5000:
        return False
    buf = sb.buf
    n = 48

    def pt(t, off, rr=None):
        rr = r if rr is None else rr
        c, s = float(M.cos(t)), float(M.sin(t))
        return (cx + ux * rr * c + vx * off, cy + uy * rr * c + vy * off, zc + rr * s)
    for side in (-RIM_GAP, RIM_GAP):
        pts = [pt(2.0 * M.PI * k / n, side) for k in range(n)]
        for k in range(n):
            _beam_slot(sb, "wheel_steel", pts[k], pts[(k + 1) % n], 700, 900, ux, uy)
        # (a light along the rim's outer face)
        lit = [pt(2.0 * M.PI * k / n, side, r + 520) for k in range(n)]
        for k in range(n):
            _beam_slot(sb, "hero_light", lit[k], lit[(k + 1) % n], 160, 160, ux, uy)
    for k in range(0, n, 2):
        t = 2.0 * M.PI * k / n
        _beam_slot(sb, "wheel_steel", pt(t, -RIM_GAP), pt(t, RIM_GAP), 260, 260, ux, uy)
        for side in (-RIM_GAP, RIM_GAP):
            _beam_slot(sb, "wheel_steel", (cx + vx * side * 0.35, cy + vy * side * 0.35, zc),
                       pt(t, side), 120, 120, ux, uy)
    # the hub along the axle
    hub = 1500
    _beam_slot(sb, "wheel_steel", (cx - vx * (RIM_GAP + 600), cy - vy * (RIM_GAP + 600), zc),
               (cx + vx * (RIM_GAP + 600), cy + vy * (RIM_GAP + 600), zc), hub * 2, hub * 2,
               ux, uy)
    sb.wheel = {"c": (cx, cy), "u": (ux, uy), "v": (vx, vy), "r": r, "zc": zc}
    # capsules round the rim, hanging from pivots just outside it
    caps = 32 if r >= 18000 else 24
    gr = 1100
    for k in range(caps):
        t = 2.0 * M.PI * (k + 0.5) / caps
        x, y, z = pt(t, 0.0, r + 900)
        sb.parts.add("gondola", {"r": gr, "h": 2300}, int(round(x)), int(round(y)),
                     int(round(z)), ux, uy)
    _count(sb, "gondolas", caps)
    sb.mass_info.append({"mass": ms["k"], "group": "structure", "system": None, "rows": 0,
                         "openings": 0, "wheel": True})
    sb.used["glass"] = True
    return True


def _beam_slot(sb, slot: str, a, b, w: int, h: int, ux: float, uy: float) -> None:
    """`shell._beam` in a slot of its own."""
    from .typeparts import quad
    d = (b[0] - a[0], b[1] - a[1], b[2] - a[2])
    L = math.sqrt(d[0] * d[0] + d[1] * d[1] + d[2] * d[2])
    if L < 10:
        return
    e = (d[0] / L, d[1] / L, d[2] / L)
    p = (-uy, ux, 0.0)
    if abs(e[0] * p[0] + e[1] * p[1]) > 0.95:
        p = (ux, uy, 0.0)
    q = (e[1] * p[2] - e[2] * p[1], e[2] * p[0] - e[0] * p[2], e[0] * p[1] - e[1] * p[0])
    ql = math.sqrt(q[0] * q[0] + q[1] * q[1] + q[2] * q[2]) or 1.0
    q = (q[0] / ql, q[1] / ql, q[2] / ql)
    p = (q[1] * e[2] - q[2] * e[1], q[2] * e[0] - q[0] * e[2], q[0] * e[1] - q[1] * e[0])
    hw, hh = w / 2.0, h / 2.0

    def c(base, sp, sq):
        return tuple(int(round(base[k] + p[k] * sp + q[k] * sq)) for k in range(3))
    A = [c(a, -hw, -hh), c(a, hw, -hh), c(a, hw, hh), c(a, -hw, hh)]
    B = [c(b, -hw, -hh), c(b, hw, -hh), c(b, hw, hh), c(b, -hw, hh)]
    mid = tuple((a[k] + b[k]) / 2.0 for k in range(3))
    sb.buf.new_part()
    for f in ((A[0], A[3], A[2], A[1]), (B[0], B[1], B[2], B[3]), (A[0], A[1], B[1], B[0]),
              (A[1], A[2], B[2], B[1]), (A[2], A[3], B[3], B[2]), (A[3], A[0], B[0], B[3])):
        cf = tuple(sum(v[k] for v in f) / 4.0 for k in range(3))
        hint = (cf[0] - mid[0], cf[1] - mid[1], cf[2] - mid[2])
        quad(sb.buf, slot, f[0], f[1], f[2], f[3], hint)


def _leg(sb, ms) -> bool:
    """A wheel's leg as a lattice tower inside its mass."""
    ring = RG.clean(ms["rings"][0])
    if len(ring) < 3:
        return False
    c, u, v, W, D = frame_of(ring)
    w0 = PT.q(min(W, D) - 200)
    h = PT.q(ms["z1"] - ms["z0"])
    if w0 < 800 or h < 3000:
        return False
    if not put(sb, "lattice", {"w0": w0, "w1": PT.q(w0 * 6 // 10), "h": h,
                               "bays": max(3, h // 6000)}, c[0], c[1], ms["z0"], u[0], u[1],
               "wheel_leg"):
        return False
    sb.wheel_legs = getattr(sb, "wheel_legs", []) + [(c, ms["z1"])]
    sb.mass_info.append({"mass": ms["k"], "group": "structure", "system": None, "rows": 0,
                         "openings": 0, "leg": True})
    return True


def _wheel_extras(sb) -> None:
    """The crossbeam between the legs at the hub's height and the axle from it to the hub."""
    w = getattr(sb, "wheel", None)
    legs = getattr(sb, "wheel_legs", [])
    if w is None or len(legs) < 2:
        return
    (l0, z0), (l1, z1) = legs[0], legs[1]
    zt = min(z0, z1) - 800
    ux, uy = w["u"]
    _beam_slot(sb, "wheel_steel", (l0[0], l0[1], zt), (l1[0], l1[1], zt), 1200, 1600, ux, uy)
    mx, my = (l0[0] + l1[0]) / 2.0, (l0[1] + l1[1]) / 2.0
    cx, cy = w["c"]
    _beam_slot(sb, "wheel_steel", (mx, my, zt), (cx, cy, w["zc"]), 900, 900, ux, uy)
    _count(sb, "wheel_axle")


# ---------------------------------------------------------------------------
# The hero UV and the U2 bake
# ---------------------------------------------------------------------------

def uv_scale(sb) -> tuple[float, float]:
    """(longest mass perimeter, building height) in meters: the hero UV's extents."""
    per = 0.0
    for ms in sb.masses:
        for ring in ms["rings"][:1]:
            n = len(ring)
            L = 0.0
            for i in range(n):
                a, b = ring[i], ring[(i + 1) % n]
                L += math.hypot(b[0] - a[0], b[1] - a[1])
            per = max(per, L / 1000.0)
    H = max(float(sb.br["building"]["height_m"]), 1.0)
    return round(max(per, 1.0), 3), round(H, 3)


def bake(sb) -> np.ndarray | None:
    """The hero's U2 mask (MASK_PX square, uint8 RGB: grime, leaks, wear) in its hero UV."""
    if getattr(sb, "hero", None) is None:
        return None
    from ..materials import noise as N
    P, H = uv_scale(sb)
    n = MASK_PX
    seed = N.seed_of("ag5.hero", sb.bid)
    gx, gy = N.grid(n)
    v = (np.float32(1.0) - gy).astype(np.float32)            # v up (rows from the top)
    z_m = v * np.float32(H)
    # grime: from the ground up 12 m, and streaks washed down 16 m under every setback
    grime = N.smooth(12.0, 0.0, z_m) * np.float32(0.75)
    tops = sorted({ms["z1"] / 1000.0 for ms in sb.masses if ms["z1"] / 1000.0 < H - 1.0})
    col = np.arange(n, dtype=np.int64)
    cv = N.unit(N.hash2(col // 3, np.zeros(n, dtype=np.int64), seed + 5)).astype(np.float32)
    cv = (np.float32(0.25) + np.float32(0.75) * cv * cv)[None, :]
    for t in tops:
        d = (np.float32(t) - z_m).astype(np.float32)
        band = N.smooth(-0.2, 0.0, d) * N.smooth(16.0, 0.0, d) * cv
        grime = np.maximum(grime, (band * np.float32(0.6)).astype(np.float32))
    grime = np.clip(grime + (N.fbm(n, 8, seed, 4) - np.float32(0.5)) * np.float32(0.3), 0, 1)
    # leaks: streaks down from the sills of its windows (their u and the row's sill)
    leak = np.zeros((n, n), dtype=np.float32)
    cols = np.zeros(n, dtype=np.float32)
    starts = np.full(n, -1.0, dtype=np.float32)
    lens = np.zeros(n, dtype=np.float32)
    fac = {}
    for fa, ms in sb.all_facades:
        if fa.j is not None:
            fac.setdefault(fa.j, []).append(fa)
    for j in sorted(sb.opened):
        for s0, s1, lo, hi in sb.opened[j]:
            fa = next((f for f in fac.get(j, ()) if f.soff - 1 <= s0 <= f.soff + f.L + 1),
                      None)
            if fa is None or lo < 1000:
                continue
            u_m = fa.u0 + ((s0 + s1) / 2.0 - fa.soff) / 1000.0
            col = int((u_m / P) * n) % n
            h = N.unit(N.hash2(np.array([col]), np.array([int(lo // 100)]), seed))[0]
            if h > 0.35:
                continue
            row_v = lo / 1000.0 / H
            if row_v > starts[col]:
                starts[col] = row_v
                lens[col] = (1.0 + 5.0 * float(h) / 0.35) / H
                cols[col] = 1.0
    for c in range(n):
        if cols[c] <= 0:
            continue
        t = (np.float32(starts[c]) - v[:, c]).astype(np.float32)
        streak = N.smooth(-0.002, 0.0, t) * N.smooth(np.float32(lens[c]), 0.0, t)
        leak[:, c] = np.maximum(leak[:, c], streak.astype(np.float32))
    leak = np.maximum(leak, N.blur(leak, 1) * np.float32(0.8))
    leak = np.clip(leak * (np.float32(0.6) + np.float32(0.4) * N.fbm(n, 16, seed + 1, 3)), 0, 1)
    # wear: at the facades' ends (their corners) and under the roofs' edges
    wear = np.zeros((n, n), dtype=np.float32)
    corners = sorted({int(((fa.u0 * 1000.0) / (P * 1000.0)) * n) % n
                      for fa, ms in sb.all_facades})
    for c in corners:
        for dc in (-2, -1, 0, 1, 2):
            wear[:, (c + dc) % n] = np.maximum(wear[:, (c + dc) % n],
                                               np.float32(0.7 - 0.15 * abs(dc)))
    for t in tops + [H]:
        d = (np.float32(t) - z_m).astype(np.float32)
        wear = np.maximum(wear, N.smooth(-0.1, 0.0, d) * N.smooth(1.2, 0.0, d) *
                          np.float32(0.8))
    wear = np.clip(wear * (np.float32(0.5) + np.float32(0.5) * N.fbm(n, 32, seed + 2, 3)), 0,
                   1)
    img = np.stack([grime, leak, wear], axis=2)
    return np.clip(np.floor(img * np.float32(255.0) + np.float32(0.5)), 0,
                   255).astype(np.uint8)


def hero_uv(arrs_pos: np.ndarray, uv0: np.ndarray, P: float, H: float) -> np.ndarray:
    """The hero UV of vertices (positions in mm, their UV0 in meters): u the UV0's u over
    the longest perimeter, v the height over the building's (clamped)."""
    u = uv0[:, 0] / P
    v = np.clip(arrs_pos[:, 2].astype(np.float64) / 1000.0 / H, 0.0, 1.0)
    return np.stack([u, v], axis=1)


def hero_materials(rec_hero: dict) -> dict:
    """The accent material a hero's light slots take (its colour), by slot."""
    return {"hero_light": rec_hero["accent"], "halo_light": rec_hero["accent"]}
