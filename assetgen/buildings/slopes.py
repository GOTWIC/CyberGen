"""Buildings on M13's slopes (scope 14.6, AG5): stepped plinths from the ground up to the
base, retaining walls where the hill stands against the building, entrances at grade.

A building stands on its base (`floor_grid.base_m`, the ground at its main entrance: mass z
0); the ground round it rises and falls. The brief carries the ground along every edge of a
mass on the base (`terrain.grade`, every metre, 0.3 m out). Per exterior facade of such a
mass:

- **steps**: the facade cut into runs of `STEP_LEN` (merged where they come out level), each
  at the lowest ground along it rounded down to `RISE` (a stair riser), so the plinth's
  foot follows the hill in steps;
- **plinth**: under every step whose ground is below the base, a closed piece of the
  facade's plinth wall `T` deep behind the facade (mitred at the facade's ends), from
  `BURY` under its step up to the base, in its own slot (`plinth`); the band's cap closes
  it at the base;
- **openings at grade**: a shopfront or a door the street front cuts down to the pavement
  on a stretch whose ground lies `DOWN` or more under the base is lowered to the ground
  there (`zf`): its band opening stays as it was and the plinth is cut under it (the door
  or shopfront reaches from the ground through both), or, where it would end under the
  base, it moves into the plinth whole (a lower ground floor) and the band puts windows in
  its place; one on a stretch whose ground lies `UP` or more over the base is raised onto
  the ground (a sill at grade, `SILL_UP` over it);
- **lower storeys**: where a step lies `LOWER` or more under the base, the plinth carries a
  row of windows (frames by the genome, glass behind them);
- **retaining walls**: where the ground stands over the base against a facade, a concrete
  skirt from under it to `SKIRT` over it (`retaining`), stopping at the raised openings;
  the street front's ground-row windows that would sit under it are left out.

Everything is a closed piece on integer millimetres; the facade's own band (AG3) is not
changed in its geometry, only in which openings it cuts and where its doors stand.
"""

from __future__ import annotations

import math

from ..triangulate import TriangulationError, area2, triangulate
from . import parts as PT
from . import rings as RG

STEP_LEN = 4000          # the plinth's steps at least this long (mm) where the ground falls
RISE = 150               # step levels on this grid (a riser)
BURY = 300               # the plinth's foot this far under its step's lowest ground
T = 450                  # the plinth wall's depth behind the facade
DOWN = 300               # an opening this far over its ground is lowered to it
UP = 200                 # an opening this far under its ground is raised onto it
SILL_UP = 150            # (a raised opening's sill over the ground)
RAISED_MIN = 1800        # (and its height at least, under what M6 mounts over it)
LOWER = 2700             # a step this far under the base carries a lower storey's windows
SKIRT = 200              # a retaining skirt this far over the ground it holds
SKIRT_T = 120            # and this thick (proud of the wall: "flush")
MITER_MAX = 3            # a mitre longer than this many plinth depths (round a reflex
                         # corner) is cut square
WIN_GAP = 400            # lower-storey windows keep this from the openings and the ends


class Grade:
    """The ground along a building's base edges (mm over the base), from its brief."""

    def __init__(self, brief: dict):
        t = brief["terrain"]
        self.step = int(round(float(t["step_m"]) * 1000))
        self.edges = {}
        for j, row in enumerate(t["grade"]):
            if row is None:
                continue
            e = brief["edges"][j]
            a = (e["a"][0] * 1000.0, e["a"][1] * 1000.0)
            b = (e["b"][0] * 1000.0, e["b"][1] * 1000.0)
            L = math.hypot(b[0] - a[0], b[1] - a[1])
            if L <= 0:
                continue
            self.edges[j] = (a, ((b[0] - a[0]) / L, (b[1] - a[1]) / L), L,
                             [int(round(v * 1000)) for v in row])

    def on_edge(self, j: int, s: float) -> int | None:
        e = self.edges.get(j)
        if e is None:
            return None
        _, _, L, row = e
        s = min(max(s, 0.0), L)
        k = int(s // self.step)
        if k >= len(row) - 1:
            return row[-1]
        s0 = k * self.step
        s1 = min((k + 1) * self.step, L)
        f = 0.0 if s1 <= s0 else (s - s0) / (s1 - s0)
        return int(round(row[k] + (row[k + 1] - row[k]) * f))

    def at(self, x: float, y: float) -> int | None:
        """The ground near (x, y) mm: on the nearest base edge."""
        best = None
        for j in sorted(self.edges):
            a, u, L, _ = self.edges[j]
            s = min(max((x - a[0]) * u[0] + (y - a[1]) * u[1], 0.0), L)
            d = math.hypot(a[0] + u[0] * s - x, a[1] + u[1] * s - y)
            if best is None or d < best[0] - 1e-6:
                best = (d, j, s)
        return None if best is None else self.on_edge(best[1], best[2])


def of(brief: dict) -> Grade | None:
    t = brief.get("terrain")
    return Grade(brief) if t and any(r is not None for r in t["grade"]) else None


def facade_grade(sb, fa) -> list[tuple[int, int]]:
    """(s, ground) along a facade every metre and at its end (mm)."""
    G = sb.slope
    n = max(1, -(-fa.L // 1000))
    out = []
    for k in range(n + 1):
        s = min(k * 1000, fa.L)
        g = G.on_edge(fa.j, s + fa.soff) if fa.j is not None and fa.j in G.edges else None
        if g is None:
            x, y, _ = fa.P(s, 0)
            g = G.at(x - fa.nx * 300, y - fa.ny * 300)
        out.append((s, 0 if g is None else g))
    return out


def ground_over(gs, a: int, b: int, how=min) -> int:
    """The lowest (or highest) ground of a facade's stations between a and b (and at
    them)."""
    vals = [_interp(gs, a), _interp(gs, b)] + [g for s, g in gs if a < s < b]
    return how(vals)


def _interp(gs, s: int) -> int:
    for (s0, g0), (s1, g1) in zip(gs, gs[1:]):
        if s0 <= s <= s1:
            return g0 if s1 == s0 else int(round(g0 + (g1 - g0) * (s - s0) / (s1 - s0)))
    return gs[-1][1] if s > gs[-1][0] else gs[0][1]


def steps(gs, L: int) -> list[tuple[int, int, int]]:
    """(s0, s1, level) of a facade's steps: runs of about `STEP_LEN` at their lowest ground,
    rounded down to `RISE`, level runs merged."""
    n = max(1, int(round(L / STEP_LEN)))
    out: list[list[int]] = []
    for k in range(n):
        s0, s1 = L * k // n, L * (k + 1) // n
        lv = (ground_over(gs, s0, s1) // RISE) * RISE
        if out and out[-1][2] == lv:
            out[-1][1] = s1
        else:
            out.append([s0, s1, lv])
    return [tuple(x) for x in out]


# ---------------------------------------------------------------------------
# The street front's openings at grade (called by `fronts.Band.plan`)
# ---------------------------------------------------------------------------

def adjust(band, fa, taken: list) -> list:
    """The band's doors and shopfronts on one facade, set at grade: lowered ones keep their
    band opening and get `zf` (or leave the band for the plinth, `sb.lowered`), raised ones
    start over the ground. Returns what the band keeps."""
    sb = band.sb
    if fa.j is None and not sb.slope.edges:
        return taken
    gs = facade_grade(sb, fa)
    fa.grade = gs
    mounts = band._mounts(fa)
    keep = []
    for op in taken:
        if op.kind not in ("shop", "door") or op.lo > band.z0 or op.info.get("dock"):
            keep.append(op)
            continue
        mid = (op.a + op.b) // 2
        g = _interp(gs, mid)
        if g <= -DOWN:
            zf = int(g // 10) * 10
            top = zf + (op.hi - op.lo)
            op.info["zf"] = zf
            sb.stats["openings_lowered"] = sb.stats.get("openings_lowered", 0) + 1
            if top + 300 <= band.z0 and op.depth > 0:
                op.lo, op.hi = zf, top          # (a lower ground floor's: into the plinth)
                op.info["plinth"] = True
                sb.lowered.setdefault(id(fa), []).append(op)
                continue
            if op.depth > 0:
                sb.lowered.setdefault(id(fa), []).append(op)
            keep.append(op)
            continue
        hi_g = ground_over(gs, op.a, op.b, max)
        if hi_g >= UP:
            fit = _raise(band, gs, mounts, op.a, op.b, op.hi)
            if fit is None:
                # (the hill rises across it: the stretch of it that can be raised, at least
                # NARROW_MIN wide, nearest its middle)
                fit = _narrowed(band, gs, mounts, op)
                if fit is not None:
                    sb.stats["openings_narrowed"] = sb.stats.get("openings_narrowed", 0) + 1
            if fit is not None:
                op.a, op.b, op.lo, op.hi = fit
                op.info["raised"] = True
                sb.stats["openings_raised"] = sb.stats.get("openings_raised", 0) + 1
            else:
                sb.stats["openings_buried"] = sb.stats.get("openings_buried", 0) + 1
        keep.append(op)
    return keep


NARROW_MIN = {"shop": 2400, "door": 1100}
NARROW_STEP = 250


def _raise(band, gs, mounts, a: int, b: int, hi0: int):
    """(a, b, lo, hi) of an opening over a..b raised onto the ground, or None when its head
    cannot rise RAISED_MIN over its sill (the band's top, what is mounted over it)."""
    hi_g = ground_over(gs, a, b, max)
    zr = int((hi_g + SILL_UP + 9) // 10) * 10
    # (its head may rise to the band's top, under anything mounted over it)
    cap = band.zb - 150
    for m0, m1, za, _ in mounts:
        if m0 < b and m1 > a and za > zr + 1000:
            cap = min(cap, za - 50)
    hi = max(hi0, min(cap, zr + RAISED_MIN + 400))
    if hi - zr < RAISED_MIN:
        return None
    return a, b, zr, hi


def _narrowed(band, gs, mounts, op):
    w_min = NARROW_MIN.get(op.kind, 1100)
    W = op.b - op.a
    mid = (op.a + op.b) // 2
    w = W - NARROW_STEP
    while w >= w_min:
        best = None
        for a in range(op.a, op.b - w + 1, NARROW_STEP):
            fit = _raise(band, gs, mounts, a, a + w, op.hi)
            if fit is not None:
                d = abs(a + w // 2 - mid)
                if best is None or d < best[0]:
                    best = (d, fit)
        if best is not None:
            return best[1]
        w -= NARROW_STEP
    return None


def windows_clear(band, fa, ops: list) -> list:
    """The band's ground-row windows that stand clear of the ground (uphill)."""
    gs = getattr(fa, "grade", None)
    if not gs:
        return ops
    out = []
    for op in ops:
        if op.kind == "win" and op.lo < ground_over(gs, op.a, op.b, max) + SKIRT + 100:
            band.sb.stats["windows_buried"] = band.sb.stats.get("windows_buried", 0) + 1
            continue
        out.append(op)
    return out


# ---------------------------------------------------------------------------
# The plinth of a mass on the base
# ---------------------------------------------------------------------------

def _inner_end(fa, d_other, at_start: bool, depth: int):
    """The plinth's inner corner at a facade's end: where its inner line meets the
    neighbor facade's (a mitre), or square where the mitre runs long."""
    a = fa.a if at_start else fa.b
    n0 = (fa.nx, fa.ny)
    n1 = (d_other[1], -d_other[0])
    # points p with (p - a) . n = -depth on both lines
    det = n0[0] * n1[1] - n0[1] * n1[0]
    sq = (int(round(a[0] - fa.nx * depth)), int(round(a[1] - fa.ny * depth)))
    if abs(det) < 1e-6:
        return sq
    c0 = -depth + a[0] * n0[0] + a[1] * n0[1]
    c1 = -depth + a[0] * n1[0] + a[1] * n1[1]
    x = (c0 * n1[1] - c1 * n0[1]) / det
    y = (n0[0] * c1 - n1[0] * c0) / det
    d0_, d1_ = (d_other, (fa.ux, fa.uy)) if at_start else ((fa.ux, fa.uy), d_other)
    convex = d0_[0] * d1_[1] - d0_[1] * d1_[0] > 0
    if not convex and math.hypot(x - a[0], y - a[1]) > MITER_MAX * depth:
        return sq
    return (int(round(x)), int(round(y)))


def _piece(sb, fa, s0: int, s1: int, z0: int, z1: int, d0: int, d1: int, slot: str,
           front: str | None = None, ring_ms=None) -> None:
    """A closed piece of the plinth wall from s0 to s1 along the facade, z0 to z1, from d0
    to d1 behind it (mitred at the facade's ends when d0 is 0); its front face in `front`."""
    if s1 - s0 < 5 or z1 - z0 < 5 or d1 - d0 < 5:
        return
    P = fa.P
    o0, o1 = P(s0, 0)[:2], P(s1, 0)[:2]

    def square(s, d):
        x, y, _ = P(s, 0)
        return (int(round(x - fa.nx * d)), int(round(y - fa.ny * d)))

    def back(s, d):
        pts = []
        if d0 == 0 and s == 0:
            pts.append(_inner_end(fa, fa.d_in, True, d))
        elif d0 == 0 and s == fa.L:
            pts.append(_inner_end(fa, fa.d_nx, False, d))
        pts += [square(s, d), square(s, d // 2), square(s, d // 4)]
        if ring_ms is None:
            return pts[0]
        # (never past the mass's walls: a mitre against a sliver edge can land outside)
        return next((q for q in pts if RG.in_poly(q, [ring_ms]) >= 0), pts[-1])
    if d0 > 0:
        o0 = (int(round(o0[0] - fa.nx * d0)), int(round(o0[1] - fa.ny * d0)))
        o1 = (int(round(o1[0] - fa.nx * d0)), int(round(o1[1] - fa.ny * d0)))
    ring = None
    while d1 - d0 >= 40:
        i1, i0 = back(s1, d1), back(s0, d1)
        ring = [o0, o1, i1, i0]
        if not _ok(ring):
            # (a short piece at a corner whose mitre folds: a triangle to the mitre point)
            ring = [o0, o1, i0] if d0 == 0 and s0 == 0 else (
                [o0, o1, i1] if d0 == 0 and s1 == fa.L else ring)
        if _ok(ring) and (ring_ms is None or
                          all(RG.in_poly(q, [ring_ms]) >= 0 for q in ring)):
            break
        ring = None
        d1 = d0 + (d1 - d0) // 2           # (a sliver of the footprint behind: thinner)
    if ring is None:
        sb.stats["plinth_skipped"] = sb.stats.get("plinth_skipped", 0) + 1
        return
    buf = sb.buf
    buf.layer = 1
    buf.new_part()
    _prism(buf, ring, z0, z1, slot, {0: front} if front else {}, fa.u0 + s0 / 1000.0)
    buf.layer = 0


def _ok(ring) -> bool:
    return len(set(ring)) == len(ring) and area2(ring) > 0 and RG.is_simple(ring)


def _prism(buf, ring, z0: int, z1: int, slot: str, faces: dict, u0: float = 0.0) -> bool:
    """A closed vertical prism of a counterclockwise ring (side k from ring[k] to
    ring[k+1] in `faces.get(k, slot)`)."""
    try:
        tris = triangulate(ring, [], keep_straight=True)
    except TriangulationError:
        tris = []
    if not tris:
        return False
    top = buf.plane((0.0, 0.0, 1.0), (0, 0, z1), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0))
    bot = buf.plane((0.0, 0.0, -1.0), (0, 0, z0), (1.0, 0.0, 0.0), (0.0, -1.0, 0.0))
    buf.add(slot, top, [(p[0], p[1], z1) for p in ring], [i for t in tris for i in t])
    buf.add(slot, bot, [(p[0], p[1], z0) for p in ring],
            [i for t in tris for i in (t[0], t[2], t[1])])
    n = len(ring)
    for k in range(n):
        p, q = ring[k], ring[(k + 1) % n]
        if p == q:
            continue
        dx, dy = q[0] - p[0], q[1] - p[1]
        L = math.hypot(dx, dy)
        nrm = (dy / L, -dx / L, 0.0)            # outward: right of the edge
        pl = buf.plane(nrm, (p[0], p[1], 0), (dx / L, dy / L, 0.0), (0.0, 0.0, 1.0),
                       u0 if k == 0 else 0.0, 0.0)
        buf.quad(faces.get(k, slot), pl, (p[0], p[1], z0), (q[0], q[1], z0),
                 (q[0], q[1], z1), (p[0], p[1], z1))
    return True


def plinth(sb, ms: dict, band) -> bool:
    """The stepped plinth under a mass on the base (its exterior facades), with the band's
    lowered openings, lower-storey windows and retaining skirts. False where nothing of it
    lies under the base."""
    made = False
    z0 = ms["z0"]
    g = band.g
    rm = ms["rings"][0]
    win_style = sb.gm["genes"].get(f"{g}.frame", "casement") if band.sysname else "fixed"
    for fa, r, i, ok in band.facades:
        if r != 0 or fa.L < 300:
            continue
        gs = getattr(fa, "grade", None) or facade_grade(sb, fa)
        fa.grade = gs
        st = steps(gs, fa.L)
        gaps = sorted(sb.lowered.get(id(fa), []), key=lambda o: o.a)
        depth = T
        for op in gaps:
            depth = max(depth, op.depth + 200)
        # lower-storey windows on the deep steps (clear of the gaps and the ends)
        wins = []
        if ok and band.sysname:
            for s0, s1, lv in st:
                if lv > z0 - LOWER:
                    continue
                sill, head = lv + 900, min(lv + 2400, z0 - 400)
                if head - sill < 900:
                    continue
                bay = max(band.bay, 2400)
                a = s0 + WIN_GAP + (0 if s0 else fa.c0)
                e = s1 - WIN_GAP - (0 if s1 < fa.L else fa.c1)
                n = (e - a) // bay
                for k in range(max(n, 0)):
                    c = a + bay * k + bay // 2
                    w = PT.q(min(bay * 55 // 100, 1800))
                    wa, wb = c - w // 2, c + w // 2
                    if any(wa < o.b + WIN_GAP and wb > o.a - WIN_GAP for o in gaps):
                        continue
                    wins.append((wa, wb, sill, head))
        cuts = [(o.a, o.b, o.lo, min(o.hi, z0), o.depth, o.back or "storefront")
                for o in gaps]
        cuts += [(a_, b_, lo, hi, 150, "glass") for a_, b_, lo, hi in wins]
        cuts.sort()
        xs = sorted({0, fa.L} | {s for s0, s1, _ in st for s in (s0, s1)} |
                    {x for c in cuts for x in (c[0], c[1])})
        xs = [x for x in xs if 0 <= x <= fa.L]

        def level_at(s):
            for s0, s1, lv in st:
                if s0 <= s <= s1:
                    return lv
            return st[-1][2]
        run = None          # (s0, s1, foot) of solid wall waiting to be built
        for xa, xb in zip(xs, xs[1:]):
            if xb - xa <= 0:
                continue
            mid = (xa + xb) // 2
            lv = min(level_at(xa), level_at(xb - 1))
            if lv >= z0:
                if run:
                    _piece(sb, fa, run[0], run[1], run[2], z0, 0, depth, "plinth", ring_ms=rm)
                    made = True
                    run = None
                continue
            foot = lv - BURY
            cut = next((c for c in cuts if c[0] <= mid < c[1]), None)
            if cut is None:
                if run and run[2] == foot and run[1] == xa:
                    run = (run[0], xb, foot)
                else:
                    if run:
                        _piece(sb, fa, run[0], run[1], run[2], z0, 0, depth, "plinth", ring_ms=rm)
                        made = True
                    run = (xa, xb, foot)
                continue
            if run:
                _piece(sb, fa, run[0], run[1], run[2], z0, 0, depth, "plinth", ring_ms=rm)
                made = True
                run = None
            a_, b_, lo, hi, d, back = cut
            lo = max(lo, foot + 50)
            _piece(sb, fa, xa, xb, foot, lo, 0, depth, "plinth", ring_ms=rm)
            if hi < z0:
                _piece(sb, fa, xa, xb, hi, z0, 0, depth, "plinth", ring_ms=rm)
            if depth - d >= 20:
                _piece(sb, fa, xa, xb, lo, hi, d, depth, "plinth", front=back, ring_ms=rm)
            made = True
        if run:
            _piece(sb, fa, run[0], run[1], run[2], z0, 0, depth, "plinth", ring_ms=rm)
            made = True
        # what fills the openings: the band's doors and shopfronts moved here whole, the
        # lower storey's window frames
        key = f"{sb.bid}|{ms['k']}|{fa.j}|{fa.a}"
        for k, op in enumerate(gaps):
            if op.info.get("plinth"):
                band._fill(fa, op, key, 500 + k, 0, 0)
                sb.stats["openings_in_plinth"] = sb.stats.get("openings_in_plinth", 0) + 1
        fw, fd = _frame(win_style)
        for a_, b_, lo, hi in wins:
            p = {"w": PT.q(b_ - a_), "h": PT.q(hi - lo), "r": 150, "fw": fw, "fd": fd,
                 "style": win_style}
            sb.parts.on(fa, "window", p, (a_ + b_) // 2, lo)
            sb.stats["plinth_windows"] = sb.stats.get("plinth_windows", 0) + 1
        # retaining skirts where the ground stands over the base (stopping at raised
        # openings and the band's other cuts down to the pavement)
        stops = [(o.a, o.b) for o in band_ops(band, fa)]
        _skirts(sb, fa, gs, stops, z0, band.zb)
        if made:
            sb.stats["plinth_facades"] = sb.stats.get("plinth_facades", 0) + 1
    if made:
        ms["stepped"] = True
    return made


def _frame(style: str):
    from .shell import FRAMES
    return FRAMES.get(style, (60, 70))


def band_ops(band, fa) -> list:
    """The band's openings on a facade (as `Band.emit` cut them)."""
    return getattr(fa, "band_ops", [])


def _skirts(sb, fa, gs, stops, z0: int, zb: int) -> None:
    n = max(1, int(round(fa.L / STEP_LEN)))
    for k in range(n):
        s0, s1 = fa.L * k // n, fa.L * (k + 1) // n
        top = ground_over(gs, s0, s1, max)
        if top < UP:
            continue
        zt = min(top + SKIRT, zb - 300)
        if zt - z0 < 200:
            continue
        xs = [s0]
        for a, b in sorted(stops):
            if a < s1 and b > s0:
                xs += [max(a, s0), min(b, s1)]
        xs.append(s1)
        for xa, xb in zip(xs[::2], xs[1::2]):
            xa = max(xa, 60 if xa == 0 else xa)
            xb = min(xb, fa.L - 60 if xb == fa.L else xb)
            if xb - xa < 400:
                continue
            _skirt(sb, fa, xa, xb, z0 - BURY, zt)
            sb.stats["retaining_skirts"] = sb.stats.get("retaining_skirts", 0) + 1


def _skirt(sb, fa, s0: int, s1: int, z0: int, z1: int) -> None:
    """A retaining skirt: a slab `SKIRT_T` proud of the facade from s0 to s1, z0 to z1."""
    P = fa.P
    a, b = P(s0, 0)[:2], P(s1, 0)[:2]
    o = (int(round(fa.nx * SKIRT_T)), int(round(fa.ny * SKIRT_T)))
    ring = [(a[0] + o[0], a[1] + o[1]), (b[0] + o[0], b[1] + o[1]), b, a]
    buf = sb.buf
    buf.layer = 1
    buf.new_part()
    _prism(buf, ring, z0, z1, "retaining", {})
    buf.layer = 0
