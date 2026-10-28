"""M9 tunnels: road tunnels at the end of M1b, their parts, metro tunnels and pedestrian
underpasses at the end of M3 (scope, After v1).

Road tunnels are a negative level of the road network (M7 viaducts are the positive ones):

- A **tunnel window** lies on a corridor: road segments of one class joined straight on
  through the nodes. Its profile is a graded envelope of depth needs: z(s) = -max(0,
  max_i(d_i - g dist(s, I_i))) at the design grade g (5%), then the vertical curves of M7 (a
  40 m moving average). A need is an interval I_i of the corridor and the depth d_i its road
  surface must reach there:
  - under water, the water bed (by class: canal 3, river 7, sea 12 m) plus 1.5 m of
    backfill, the tube roof (1.5 m) and the clear height (5.5 m), 10 m past each bank;
  - under a road that crosses the corridor at a node inside the window, the clear height,
    the roof (1 m) and 1 m of cover: the node goes (the crossing road passes over, its two
    legs joined into one segment, `attrs.over_tunnel_at`), like the overpasses of M7;
  - for a cut-and-cover tunnel under a district (`highways.tunnels.under`), the covered
    stretch inside the district, at that same depth.
  The fit adds the needs of the water and the nodes the envelope reaches until nothing new
  comes in; a node that cannot be passed under (a tee, a fork, an exit, a highway) within
  20 m of the sunk stretch, or a corridor end, means the tunnel does not fit.
- **Immersed tubes** replace bridges (`highways.tunnels.water`, a named crossing's
  `tunnel`); the bridge rows go, the window's segments become one segment (level -1,
  `tunnel`, `tunnel_ids`), whose profile solve_grades keeps (`_tunnel_prof`).
- **Parts**: portals where the roof meets the ground (road 6.5 m down), the open approach
  ramp from there to the ground (a walled trench), ventilation buildings over the box near
  each portal of a tunnel over 300 m (and every 800 m along a long one), on the lid away
  from the roads that cross it.

The metro (M5) runs in tunnels between its station boxes: its track is lowered under the
water bed, the road tunnels and the building foundations at the metro grade. Pedestrian
underpasses take walkways under at-grade highways between the frontage streets.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import shapely
from shapely.geometry import LineString, Point

from . import dmath as M
from . import geom as G

GRADE = 0.05                    # design grade of the approaches (M7's)
STEEP_GRADE = 0.058             # where the design grade does not fit (under the maximum)
MAX_GRADE = 0.06                # road class maximum (scope)
CLEAR_M = 5.5                   # clear height over the road
ROOF_M = 1.0                    # cut-and-cover roof slab
TUBE_ROOF_M = 1.5               # immersed tube roof
FLOOR_M = 1.0                   # slab under the road
WALL_M = 1.0                    # side walls
COVER_M = 1.0                   # soil over a roof (under a road over it, past the portal zone)
BED_COVER_M = 1.5               # backfill over a tube under the water bed
BED_M = {"canal": 3.0, "river": 7.0, "sea": 12.0}   # water depth to the bed
BANK_M = 10.0                   # full depth past each bank (quay walls)
FLAT_M = 20.0                   # at grade between a node and the start of a descent
PORTAL_ZONE_M = 40.0            # cover grows from 0 at a portal over this length
PAD_M = 0.3                     # depth margin for the vertical curves
STEP_M = 5.0
CURVE_M = 40.0
MIN_COVERED_M = 120.0           # shortest covered stretch of a cut-and-cover tunnel
WIDE_SEA_M = 600.0              # 'auto': a sea crossing wider than this gets a tube
MAX_LEN_M = 4000.0
STRAIGHT_COS = 0.819            # a corridor goes on through a node within 35 degrees
SKEW_SIN = 0.574                # and a road crosses over it at 35 degrees or more
VENT_MIN_M = 300.0              # covered length that gets ventilation buildings
VENT_STEP_M = 800.0
VENT_LEN_M = 16.0               # along the tunnel
VENT_H_M = 12.0
VENT_GAP_M = 12.0               # from a road crossing over the lid
TEE_GAP_M = 8.0                 # a road that met the tunnel road ends this far off the box
TEE_MIN_M = 40.0                # shorter than this after the trim: the leg goes

PORTAL_Z = -(CLEAR_M + ROOF_M)                  # road at a portal (roof top at the ground)
COVERED_NEED = CLEAR_M + ROOF_M + COVER_M       # road depth under a road over the lid


def roof_of(kind: str) -> float:
    return TUBE_ROOF_M if kind == "immersed_tube" else ROOF_M


def portal_z(kind: str) -> float:
    return -(CLEAR_M + roof_of(kind))


def covered_need(kind: str) -> float:
    return CLEAR_M + roof_of(kind) + COVER_M


def water_need(cls: str) -> float:
    return BED_M[cls] + BED_COVER_M + TUBE_ROOF_M + CLEAR_M


def box_width(road_w: float) -> float:
    return G.q(road_w + 2.0 * WALL_M)


def _d(a, b) -> float:
    return M.hypot(b[0] - a[0], b[1] - a[1])


# ---------------------------------------------------------------------------
# Corridors
# ---------------------------------------------------------------------------

@dataclass
class Corridor:
    segs: list                  # [(row, reversed)]
    nodes: list                 # n0..nk
    kinds: list                 # per node: end | plain | cross | block
    pts: list = field(default_factory=list)
    cum: list = field(default_factory=list)
    s_nodes: list = field(default_factory=list)

    def build(self) -> None:
        from .elevated import _cum

        pts: list = []
        s_nodes = [0.0]
        for sg, rev in self.segs:
            cl = [tuple(p) for p in sg["centerline"]]
            if rev:
                cl = cl[::-1]
            pts += cl if not pts else cl[1:]
            s_nodes.append(_cum(pts)[-1])
        self.pts, self.cum, self.s_nodes = pts, _cum(pts), s_nodes

    @property
    def L(self) -> float:
        return self.cum[-1]

    def ids(self) -> list[str]:
        return [s["id"] for s, _ in self.segs]


class Net:
    """Graph helpers on M1b's rows."""

    def __init__(self, net):
        self.net = net
        self.pos = {n["id"]: (n["position"][0], n["position"][1]) for n in net.nodes}
        self.node = {n["id"]: n for n in net.nodes}
        self.inc: dict[str, list] = {}
        for s in net.segments:
            for n in (s["start"], s["end"]):
                self.inc.setdefault(n, []).append(s)
        for n in self.inc:
            self.inc[n].sort(key=lambda s: s["id"])

    def other(self, s, n) -> str:
        return s["end"] if s["start"] == n else s["start"]

    def leg_dir(self, s, n) -> tuple[float, float]:
        cl = [tuple(p) for p in s["centerline"]]
        pts = cl if s["start"] == n else cl[::-1]
        p0 = pts[0]
        for b in pts[1:]:
            if _d(p0, b) >= 20.0 or b == pts[-1]:
                L = _d(p0, b)
                if L > 0:
                    return ((b[0] - p0[0]) / L, (b[1] - p0[1]) / L)
        return (1.0, 0.0)

    def through(self, s, n, used: set) -> tuple[str, dict | None]:
        """At node n, coming along s: the segment the corridor goes on with (same class,
        straightest within 35 degrees) and what n is for a tunnel through it: plain (nothing
        else meets there), cross (one road crosses straight over, at 35 degrees or more:
        it can pass over the tunnel), tee (one avenue meets it at 35 degrees or more: it ends
        beside the lid), block, or end."""
        if self.node[n]["attrs"].get("kind") in ("exit", "edge", "end"):
            return "end", None
        u = self.leg_dir(s, n)
        best = None
        for t in self.inc.get(n, []):
            if t["id"] == s["id"] or t["road_class"] != s["road_class"] or t["id"] in used:
                continue
            if "pinned" in t["attrs"] or t["start"] == t["end"]:
                continue
            v = self.leg_dir(t, n)
            c = u[0] * v[0] + u[1] * v[1]
            if c <= -STRAIGHT_COS and (best is None or (round(c, 9), t["id"]) < best[0]):
                best = ((round(c, 9), t["id"]), t)
        if best is None:
            return "end", None
        t = best[1]
        others = [o for o in self.inc[n] if o["id"] not in (s["id"], t["id"])]
        if not others:
            return "plain", t
        if len(others) == 1:
            o = others[0]
            v = self.leg_dir(o, n)
            if o["road_class"] != "highway" and "pinned" not in o["attrs"] and \
                    o["start"] != o["end"] and abs(u[0] * v[1] - u[1] * v[0]) >= SKEW_SIN:
                return "tee", t
            return "block", t
        if len(others) != 2 or any(o["road_class"] == "highway" or "pinned" in o["attrs"]
                                   or o["start"] == o["end"] for o in others):
            return "block", t
        if others[0]["id"] == others[1]["id"]:
            return "block", t
        vs = [self.leg_dir(o, n) for o in others]
        straight = vs[0][0] * vs[1][0] + vs[0][1] * vs[1][1] <= -STRAIGHT_COS
        sides = [u[0] * v[1] - u[1] * v[0] > 0 for v in vs]
        skew = min(abs(u[0] * v[1] - u[1] * v[0]) for v in vs)
        if straight and sides[0] != sides[1] and skew >= SKEW_SIN:
            return "cross", t
        return "block", t

    def corridor(self, seed, used: set, reach: float = MAX_LEN_M) -> Corridor:
        """The corridor through segment `seed`, at most `reach` on from it each way."""
        def walk(n):
            """From the seed through node n: nodes [n, ...], segments between them, the
            kind of every node but the last (an end)."""
            nodes, segs, kinds = [n], [], []
            s, seen, acc = seed, {seed["id"]}, 0.0
            while acc < reach:
                kind, t = self.through(s, n, used)
                if t is None or t["id"] in seen:
                    break
                seen.add(t["id"])
                kinds.append(kind)
                n = self.other(t, n)
                segs.append(t)
                nodes.append(n)
                acc += t["attrs"].get("length_m", 0.0)
                s = t
            return nodes, segs, kinds

        bn, bs, bk = walk(seed["start"])
        fn, fs, fk = walk(seed["end"])
        # back part reversed: it runs from its far end to the seed's start
        nodes = bn[::-1] + fn
        kinds = ["end"] + bk[::-1] + fk + ["end"]
        segs = [(t, t["start"] != bn[i + 1]) for i, t in reversed(list(enumerate(bs)))]
        segs.append((seed, False))
        segs += [(t, t["start"] != fn[i]) for i, t in enumerate(fs)]
        cor = Corridor(segs, nodes, kinds)
        cor.build()
        return cor


# ---------------------------------------------------------------------------
# Profiles
# ---------------------------------------------------------------------------

def _stations(L: float, needs) -> list[float]:
    n = max(int(L / STEP_M), 1)
    return [i * L / n for i in range(n + 1)]


def envelope(L: float, needs: list[tuple[float, float, float]], g: float = GRADE
             ) -> list[tuple[float, float]]:
    """z(s) = -max(0, max_i(d_i - g dist(s, [a_i, b_i]))) on 5 m stations, then the vertical
    curves (a 40 m moving average); [(s, z)]."""
    from .elevated import smooth

    ss = _stations(L, needs)
    raw = []
    for s in ss:
        d = 0.0
        for a, b, need in needs:
            dist = a - s if s < a else (s - b if s > b else 0.0)
            d = max(d, need - g * dist)
        raw.append(-d)
    step = L / max(len(ss) - 1, 1)
    zs = smooth(raw, CURVE_M, step) if step > 0 else raw
    return [(G.q(s), G.q(min(z, 0.0))) for s, z in zip(ss, zs)]


def z_at(prof, s: float) -> float:
    from .elevated import _z_at

    return _z_at(prof, s)


def sunk(prof, eps: float = 0.005) -> tuple[float, float] | None:
    """First and last station below the ground."""
    idx = [i for i, (_, z) in enumerate(prof) if z < -eps]
    if not idx:
        return None
    i0, i1 = idx[0], idx[-1]
    return prof[max(i0 - 1, 0)][0], prof[min(i1 + 1, len(prof) - 1)][0]


def crossing_at(prof, z: float) -> tuple[float, float] | None:
    """Where the profile first reaches depth z going in, and last leaves it."""
    idx = [i for i, (_, zz) in enumerate(prof) if zz <= z + 1e-9]
    if not idx:
        return None

    def interp(i, j):
        (s0, z0), (s1, z1) = prof[i], prof[j]
        return s0 if abs(z1 - z0) < 1e-12 else s0 + (s1 - s0) * (z - z0) / (z1 - z0)

    i0, i1 = idx[0], idx[-1]
    a = prof[i0][0] if i0 == 0 else interp(i0 - 1, i0)
    b = prof[i1][0] if i1 == len(prof) - 1 else interp(i1, i1 + 1)
    return G.q(a), G.q(b)


# ---------------------------------------------------------------------------
# Fitting
# ---------------------------------------------------------------------------

@dataclass
class Window:
    kind: str                   # immersed_tube | cut_and_cover
    cor: Corridor
    prof: list                  # [(s, z)] along the corridor
    lo: float                   # sunk stretch
    hi: float
    ia: int                     # node index where the window starts
    ib: int
    needs: list
    waters: list                # water ids under it
    name: str | None = None
    bridge_ids: list = field(default_factory=list)
    district: str | None = None


class Ctx:
    def __init__(self, ctx, net):
        self.ctx = ctx
        self.net = net
        self.N = Net(net)
        self.used: set[str] = set()
        self.notes: list[str] = []

    def water_spans(self, cor: Corridor) -> list[tuple[float, float, float, str]]:
        """(a, b, need, water id) of the corridor's stretches over water."""
        from .elevated import _project
        from .roads import G_lines, WATER_CLASS

        ln = LineString(cor.pts)
        out = []
        for w in self.ctx.waters:
            if not ln.intersects(w.polygon):
                continue
            inter = G_lines(ln.intersection(w.polygon))
            for part in inter:
                if part.length < 0.5:
                    continue
                cs = list(part.coords)
                a = _project(cor.pts, cor.cum, cs[0])[0]
                b = _project(cor.pts, cor.cum, cs[-1])[0]
                a, b = min(a, b), max(a, b)
                out.append((G.q(a - BANK_M), G.q(b + BANK_M),
                            water_need(WATER_CLASS[w.cls]) + PAD_M, w.id))
        out.sort(key=lambda t: (t[0], t[1], -t[2], t[3]))
        return out

    def fit(self, cor: Corridor, needs0: list, kind: str) -> tuple[Window | None, str]:
        """The tunnel window on corridor `cor` that meets needs0 (and what it reaches) at the
        design grade, else a little steeper; or (None, why)."""
        win, why = self._fit(cor, needs0, kind, GRADE)
        if win is None:
            win2, _ = self._fit(cor, needs0, kind, STEEP_GRADE)
            if win2 is not None:
                return win2, ""
        return win, why

    def _fit(self, cor: Corridor, needs0: list, kind: str, g: float
             ) -> tuple[Window | None, str]:
        water = self.water_spans(cor)
        needs = list(needs0)
        waters: set[str] = set()
        L = cor.L
        prof = None
        for _ in range(24):
            prof = envelope(L, needs, g)
            ext = sunk(prof)
            if ext is None:
                return None, "nothing to sink"
            lo, hi = ext
            if lo - FLAT_M < 0.0 or hi + FLAT_M > L:
                return None, "runs out of its corridor (an end, a turn or a highway node)"
            if hi - lo > MAX_LEN_M:
                return None, "longer than 4 km"
            changed = False
            for a, b, need, wid in water:
                if b >= lo - FLAT_M and a <= hi + FLAT_M and (a, b, need) not in needs:
                    needs.append((a, b, need))
                    waters.add(wid)
                    changed = True
                elif b >= lo - FLAT_M and a <= hi + FLAT_M:
                    waters.add(wid)
            for k in range(1, len(cor.nodes) - 1):
                sk = cor.s_nodes[k]
                if not lo - FLAT_M <= sk <= hi + FLAT_M:
                    continue
                if cor.kinds[k] not in ("plain", "cross", "tee"):
                    return None, f"a junction it cannot pass under ({cor.nodes[k]})"
                if cor.kinds[k] == "plain":
                    continue
                w = max(o["width_m"] for o in self.N.inc[cor.nodes[k]]
                        if o["id"] not in (cor.segs[k - 1][0]["id"], cor.segs[k][0]["id"]))
                a, b = G.q(sk - w / 2.0 - 3.0), G.q(sk + w / 2.0 + 3.0)
                nd = (a, b, covered_need(kind) + PAD_M)
                if nd not in needs:
                    needs.append(nd)
                    changed = True
            if not changed:
                # the needs are met after the vertical curves (else deeper margins)
                short = [(a, b, need) for a, b, need in needs
                         if max(z_at(prof, a), z_at(prof, b), z_at(prof, (a + b) / 2.0))
                         > -(need - PAD_M) + 0.005]
                if short:
                    needs = [(a, b, need + 0.3 if (a, b, need) in short else need)
                             for a, b, need in needs]
                    changed = True
            if not changed:
                break
        else:
            return None, "no stable fit"
        ia = max(k for k in range(len(cor.nodes)) if cor.s_nodes[k] <= lo - FLAT_M + 1e-6)
        ib = min(k for k in range(len(cor.nodes)) if cor.s_nodes[k] >= hi + FLAT_M - 1e-6)
        ids = cor.ids()[ia:ib]
        if set(ids) & self.used:
            return None, "overlaps another tunnel"
        # nothing crosses the open approaches without a node, and they stay on dry land
        por = crossing_at(prof, portal_z(kind))
        if por is None:
            return None, "too shallow for a portal"
        from .elevated import _sub

        for a, b in ((lo, por[0]), (por[1], hi)):
            if b - a < 1.0:
                continue
            piece = LineString(_sub(cor.pts, cor.cum, a, b))
            if piece.intersects(self.ctx.wet):
                return None, "an open approach over water"
            mine = set(cor.ids())
            for s in self.net.segments:
                if s["id"] in mine:
                    continue
                if piece.distance(LineString(s["centerline"])) < s["width_m"] / 2.0 + 2.0:
                    return None, f"another road over an open approach ({s['id']})"
        why = self.cuts_off(cor, ia, ib)
        if why:
            return None, why
        # no bridge approach reaches its descents (solve_grades lifts the nodes it reaches)
        from .elevated import APPROACH_GRADE

        own = {b["id"] for b in self.net.bridges if set(b.get("segment_ids") or []) & set(ids)}
        lift = self.lifts(own)
        for k, run in ((ia, lo - cor.s_nodes[ia]), (ib, cor.s_nodes[ib] - hi)):
            if lift.get(cor.nodes[k], 0.0) > APPROACH_GRADE * run - 0.05:
                return None, f"a bridge approach reaches its descent ({cor.nodes[k]})"
        win = Window(kind, cor, prof, lo, hi, ia, ib, needs, sorted(waters))
        return win, ""

    def lifts(self, skip: set) -> dict:
        """Node heights the bridge approaches reach (solve_grades' envelope), without the
        bridges in `skip`."""
        import heapq

        from .elevated import APPROACH_GRADE, _cum

        Ls = {s["id"]: _cum(s["centerline"])[-1] for s in self.net.segments}
        by = {s["id"]: s for s in self.net.segments}
        val: dict = {}
        heap: list = []
        for b in self.net.bridges:
            if b["id"] in skip or not b.get("segment_ids"):
                continue
            s = by.get(b["segment_ids"][0])
            if s is None:
                continue
            z = b["line"][0][2]
            for n, d in ((s["start"], b["s0"]), (s["end"], Ls[s["id"]] - b["s1"])):
                v = z - APPROACH_GRADE * d
                if v > val.get(n, 0.0):
                    val[n] = v
                    heapq.heappush(heap, (-v, n))
        while heap:
            v, n = heapq.heappop(heap)
            v = -v
            if v < val.get(n, 0.0):
                continue
            for s in self.N.inc.get(n, []):
                m = self.N.other(s, n)
                w = v - APPROACH_GRADE * Ls[s["id"]]
                if w > val.get(m, 0.0) + 1e-9:
                    val[m] = w
                    heapq.heappush(heap, (-w, m))
        return val

    def cuts_off(self, cor: Corridor, ia: int, ib: int) -> str:
        """Whether the network falls apart with this window: its inner nodes go, the roads
        crossing over join through, the tees end beside the lid."""
        parent: dict = {}

        def find(a):
            while parent.setdefault(a, a) != a:
                parent[a] = parent[parent[a]]
                a = parent[a]
            return a

        def union(a, b):
            ra, rb = find(a), find(b)
            if ra != rb:
                parent[max(ra, rb)] = min(ra, rb)

        inner = {cor.nodes[k]: k for k in range(ia + 1, ib)}
        win = set(cor.ids()[ia:ib])
        for s in self.net.segments:
            ends = []
            for n in (s["start"], s["end"]):
                if n not in inner or s["id"] in win:
                    ends.append(("n", n))
                elif cor.kinds[inner[n]] == "cross":
                    ends.append(("x", n))
                else:
                    ends.append(("t", s["id"], n))      # a tee leg's own end
            union(ends[0], ends[1])
        roots = {find(("n", n["id"])) for n in self.net.nodes if n["id"] not in inner}
        if len(roots) > self._components():
            return "it would cut the road network apart"
        return ""

    def _components(self) -> int:
        if not hasattr(self, "_ncomp"):
            parent: dict = {}

            def find(a):
                while parent.setdefault(a, a) != a:
                    parent[a] = parent[parent[a]]
                    a = parent[a]
                return a

            for s in self.net.segments:
                ra, rb = find(s["start"]), find(s["end"])
                if ra != rb:
                    parent[max(ra, rb)] = min(ra, rb)
            self._ncomp = len({find(n["id"]) for n in self.net.nodes})
        return self._ncomp


# ---------------------------------------------------------------------------
# Choosing
# ---------------------------------------------------------------------------

def _named_tunnels(spec) -> dict:
    return {nb.name: nb.tunnel for nb in spec.water.bridges.named}


def choose(spec, ctx, net) -> list[Window]:
    """The tunnel windows of this network: immersed tubes for the crossings that get one,
    then cut-and-cover tunnels under the districts the spec names."""
    T = Ctx(ctx, net)
    mode = spec.highways.tunnels.water
    asked = _named_tunnels(spec)
    by_seg = {s["id"]: s for s in net.segments}
    seeds = []
    for b in net.bridges:
        if b.get("bridge_class") == "pedestrian" or not b.get("segment_ids"):
            continue
        s = by_seg.get(b["segment_ids"][0])
        # highways only for now: an avenue in a tube would keep its sidewalks, parking and
        # crossings up at the ground (an open item)
        if s is None or s["road_class"] != "highway" or "pinned" in s["attrs"]:
            continue
        if s["attrs"].get("causeway"):
            continue
        wc = b["attrs"]["water_class"]
        pref = asked.get(b.get("name")) if b.get("name") else None
        if pref is False or (b.get("name") and pref is not True):
            continue      # a named crossing is a bridge unless it asks for a tunnel
        want = pref is True or (mode == "prefer" and wc in ("river", "sea")) or \
            (mode == "auto" and wc == "sea" and b["attrs"]["span_m"] >= WIDE_SEA_M)
        if not want:
            continue
        seeds.append(((pref is not True, -b["attrs"]["span_m"], b["id"]), b, s))
    wins: list[Window] = []
    taken: set[str] = set()
    for _, b, s in sorted(seeds, key=lambda t: t[0]):
        if b["id"] in taken:
            continue
        cor = T.N.corridor(s, T.used)
        from .elevated import _project

        bl = [(x, y) for x, y, _ in b["line"]]
        a0 = _project(cor.pts, cor.cum, bl[0])[0]
        a1 = _project(cor.pts, cor.cum, bl[-1])[0]
        spans = [w for w in T.water_spans(cor) if w[1] >= min(a0, a1) and w[0] <= max(a0, a1)]
        if not spans:
            continue
        win, why = T.fit(cor, [(a, b_, need) for a, b_, need, _ in spans], "immersed_tube")
        label = f"bridge {b['id']}" + (f" '{b['name']}'" if b.get("name") else "")
        if win is None:
            if b.get("name") and asked.get(b["name"]):
                T.notes.append(f"tunnel for {label} does not fit: {why}; built as a bridge")
            elif mode == "prefer":
                T.notes.append(f"no tube for {label}: {why}")
            continue
        win.name = b.get("name")
        ids = set(cor.ids()[win.ia:win.ib])
        win.bridge_ids = sorted(x["id"] for x in net.bridges
                                if set(x.get("segment_ids") or []) & ids)
        taken |= set(win.bridge_ids)
        T.used |= ids
        wins.append(win)
    for name in spec.highways.tunnels.under:
        win = _under(T, name)
        if win is not None:
            T.used |= set(win.cor.ids()[win.ia:win.ib])
            win.bridge_ids = sorted(x["id"] for x in net.bridges
                                    if set(x.get("segment_ids") or []) &
                                    set(win.cor.ids()[win.ia:win.ib]))
            wins.append(win)
    ctx.notes += T.notes
    return wins


def _under(T: Ctx, name: str) -> Window | None:
    """The longest cut-and-cover tunnel a highway corridor can take under district `name`
    (its covered stretch inside the district, between the nodes it cannot pass under)."""
    from .elevated import _project

    poly = T.ctx.polygons.get(name)
    if poly is None:
        T.notes.append(f"cut-and-cover under '{name}': no such district")
        return None
    inner = G.qpoly(poly.buffer(-20.0))
    seen: set = set()
    best = None
    descent = (COVERED_NEED + PAD_M) / GRADE + 15.0
    hw = sorted((s for s in T.net.segments if s["road_class"] == "highway" and
                 "pinned" not in s["attrs"] and s["id"] not in T.used and
                 LineString(s["centerline"]).intersects(inner)), key=lambda s: s["id"])
    for seed in hw:
        if seed["id"] in seen:
            continue
        cor = T.N.corridor(seed, T.used)
        seen |= set(cor.ids())
        ln = LineString(cor.pts)
        from .roads import G_lines

        stretches = []
        for part in G_lines(ln.intersection(inner)):
            cs = list(part.coords)
            a = _project(cor.pts, cor.cum, cs[0])[0]
            b = _project(cor.pts, cor.cum, cs[-1])[0]
            stretches.append((min(a, b), max(a, b)))
        blocks = [cor.s_nodes[k] for k in range(len(cor.nodes))
                  if cor.kinds[k] not in ("plain", "cross")]
        cands = []
        for a, b in sorted(stretches):
            for p, q in zip(blocks, blocks[1:]):
                ca, cb = max(a, p + FLAT_M + descent), min(b, q - FLAT_M - descent)
                if cb - ca >= MIN_COVERED_M:
                    cands.append((-(cb - ca), ca, cb))
        for _, ca, cb in sorted(cands):
            # a node too near a descent: shrink the covered stretch by 40 m steps
            for k in range(12):
                a2, b2 = ca + 20.0 * k, cb - 20.0 * k
                if b2 - a2 < MIN_COVERED_M:
                    break
                win, why = T.fit(cor, [(G.q(a2), G.q(b2), COVERED_NEED + PAD_M)],
                                 "cut_and_cover")
                if win is not None:
                    covered = b2 - a2
                    if best is None or covered > best[0] + 1e-6:
                        win.district = name
                        best = (covered, win)
                    break
            if best is not None:
                break
    if best is None:
        T.notes.append(f"cut-and-cover under '{name}': no highway stretch fits between its "
                       "interchanges")
        return None
    return best[1]


# ---------------------------------------------------------------------------
# Re-noding
# ---------------------------------------------------------------------------

def apply(spec, ctx, net, wins: list[Window]) -> None:
    """The network with each window's segments joined into one tunnel segment, the roads
    crossing over it joined through the nodes that go, its bridges gone; renumbered as
    M1b numbers (nodes by coordinate, segments by class and ends); `net.tunnels` rows."""
    from .elevated import Edge, _join, _rows, _slice, _sub, _tuples
    from . import roads as RD

    if not wins:
        net.tunnels = []
        return
    N = Net(net)
    in_win: dict[str, int] = {}
    for wi, w in enumerate(wins):
        for sid in w.cor.ids()[w.ia:w.ib]:
            in_win[sid] = wi
    edges: dict[str, Edge] = {}
    owner: dict[str, str] = {}
    for s in net.segments:
        if s["id"] in in_win:
            continue
        edges[s["id"]] = Edge([tuple(p) for p in s["centerline"]], _tuples(s["z_profile"]),
                              s, s["id"])
        owner[s["id"]] = s["id"]
    out: list[Edge] = []
    tunnels = []
    gone_bridges: set[str] = set()
    for wi, w in enumerate(wins):
        tid = f"tn{wi + 1:02d}"
        cor = w.cor
        under = []
        for k in range(w.ia + 1, w.ib):
            n = cor.nodes[k]
            on = {cor.segs[k - 1][0]["id"], cor.segs[k][0]["id"]}
            legs = [s for s in N.inc[n] if s["id"] not in on]
            p = N.pos[n]
            if len(legs) == 1:
                # a tee: the leg ends beside the lid (or goes when that leaves it too short)
                kk = owner[legs[0]["id"]]
                e = edges[kk].oriented_to_end(p)
                cut = e.L - (box_width(cor.segs[k][0]["width_m"]) / 2.0 + TEE_GAP_M)
                if cut < TEE_MIN_M:
                    del edges[kk]
                    for sid, k_ in list(owner.items()):
                        if k_ == kk:
                            owner[sid] = None
                    continue
                from .elevated import _cum as _c

                pts_ = _sub(e.pts, _c(e.pts), 0.0, cut)
                edges[kk] = Edge(pts_, _slice(e.prof, 0.0, cut), e.row, e.key, True,
                                 [], {**e.extra, "trim": e.extra.get("trim", []) +
                                      [G.qpoint(p)]})
                under.append(G.qpoint(p))
                continue
            if len(legs) != 2:
                continue
            k1, k2 = owner[legs[0]["id"]], owner[legs[1]["id"]]
            if k1 == k2:
                continue
            e = _join(edges[k1], edges[k2], p)
            e.extra["over"] = e.extra.get("over", []) + [p]
            del edges[k1], edges[k2]
            for sid, kk in list(owner.items()):
                if kk in (k1, k2):
                    owner[sid] = e.key
            edges[e.key] = e
            under.append(G.qpoint(p))
        sa, sb = cor.s_nodes[w.ia], cor.s_nodes[w.ib]
        pts = _sub(cor.pts, cor.cum, sa, sb)
        prof = _slice(w.prof, sa, sb)
        src = cor.segs[w.ia][0]
        row = dict(src)
        segs_in = [s for s, _ in cor.segs[w.ia:w.ib]]
        row["district_ids"] = sorted({d for s in segs_in for d in s["district_ids"]})
        names = [s.get("name") for s in segs_in if s.get("name")]
        row["name"] = w.name or (names[0] if names else None)
        attrs = dict(src["attrs"])
        attrs.pop("grade_separated_with", None)
        attrs["tunnel"] = tid
        attrs["_tunnel_prof"] = [(G.q(s), G.q(z)) for s, z in prof]
        if under:
            attrs["underpass_at"] = [list(p) for p in under]
        row["attrs"] = attrs
        row["tunnel"] = True
        row["tunnel_ids"] = [tid]
        gone_bridges |= set(w.bridge_ids)
        out.append(Edge(pts, prof, row, "+".join(s["id"] for s in segs_in), True))
        tunnels.append((tid, w))
    for kk in sorted(edges):
        out.append(edges[kk])
    # nodes by coordinate, segments by class and ends (as assemble numbers them)
    old = {(G.q(n["position"][0]), G.q(n["position"][1])): n for n in net.nodes}
    deg: dict = {}
    for e in out:
        for p in (tuple(e.pts[0]), tuple(e.pts[-1])):
            deg[p] = deg.get(p, 0) + 1
    order = sorted(deg)
    nid = {c: f"rn{i + 1:04d}" for i, c in enumerate(order)}
    nodes = []
    for c in order:
        o = old.get(c) or {"position": (c[0], c[1], 0.0), "level": 0,
                           "attrs": {"kind": "end", "tunnel_end": True}}
        attrs = dict(o["attrs"])
        attrs["degree"] = deg[c]
        if attrs.get("kind") not in ("exit", "edge"):
            attrs["kind"] = "end" if deg[c] == 1 else "junction"
        nodes.append({**o, "id": nid[c], "attrs": attrs})
    from .elevated import _cum

    out.sort(key=lambda e: (e.row["road_class"] != "highway", tuple(e.pts[0]),
                            tuple(e.pts[-1]), round(_cum(e.pts)[-1], 2)))
    segs = []
    remap: dict[str, str] = {}
    for i, e in enumerate(out):
        row = dict(e.row)
        attrs = dict(row.get("attrs", {}))
        attrs.pop("grade_separated_with", None)
        attrs["length_m"] = G.q(_cum(e.pts)[-1])
        if e.joined:
            attrs["split_of"] = f"m1b:{e.key}"
        if e.extra.get("over"):
            attrs["over_tunnel_at"] = [list(G.qpoint(p)) for p in e.extra["over"]]
        sid = f"rs{i + 1:04d}"
        for old_id in e.key.split("+"):
            remap[old_id] = sid
        if e.extra.get("trim"):
            attrs["ends_at_tunnel"] = [list(p) for p in e.extra["trim"]]
        row.update({"id": sid, "start": nid[tuple(e.pts[0])], "end": nid[tuple(e.pts[-1])],
                    "centerline": [tuple(p) for p in e.pts],
                    "z_profile": _rows(_compress(e.prof)) if e.joined else row["z_profile"],
                    "attrs": attrs})
        segs.append(row)
    # bridges: the tunnels' go, the rest onto the segments that carry them now
    from .elevated import _project

    by_id = {s["id"]: s for s in segs}
    bridges = []
    for b in net.bridges:
        if b["id"] in gone_bridges:
            continue
        if b.get("segment_ids"):
            if b["segment_ids"][0] not in remap:
                continue       # on a tee leg that went
            sid = remap[b["segment_ids"][0]]
            sg = by_id[sid]
            cl = sg["centerline"]
            cum = _cum(cl)
            bl = [(x, y) for x, y, _ in b["line"]]
            s0 = _project(cl, cum, bl[0])[0]
            s1 = _project(cl, cum, bl[-1])[0]
            b["s0"], b["s1"] = G.q(min(s0, s1)), G.q(max(s0, s1))
            b["segment_ids"] = [sid]
        bridges.append(b)
    for sg in segs:
        sg["bridge_ids"] = sorted(b["id"] for b in bridges if sg["id"] in
                                  (b.get("segment_ids") or []))
        sg["bridge"] = bool(sg["bridge_ids"])
        sg["clearance_m"] = max((b["clearance_m"] for b in bridges
                                 if b["id"] in sg["bridge_ids"]), default=None)
    net.nodes, net.segments, net.bridges = nodes, segs, bridges
    # crossings without a node again (the tunnels and the roads over them)
    for sg in segs:
        sg["attrs"].pop("grade_separated_with", None)
    RD._grade_separations(ctx, net)
    net.tunnels = [_tunnel_row(spec, ctx, tid, w) for tid, w in tunnels]


def _compress(prof):
    from .elevated import compress

    return compress(prof)


def _tunnel_row(spec, ctx, tid: str, w: Window) -> dict:
    """The model row of a road tunnel (its segment ids are filled in after M7)."""
    from .elevated import _at, _sub

    cor = w.cor
    road_w = max(s["width_m"] for s, _ in cor.segs[w.ia:w.ib])
    # the road surface at the profile's stations and the corridor's vertices
    ss = sorted({G.q(s) for s, _ in w.prof if w.lo <= s <= w.hi} |
                {G.q(s) for s in cor.cum if w.lo < s < w.hi} | {G.q(w.lo), G.q(w.hi)})
    line = []
    for s in ss:
        p, _ = _at(cor.pts, cor.cum, s)
        q = (G.q(p[0]), G.q(p[1]), G.q(z_at(w.prof, s)))
        if not line or q[:2] != line[-1][:2]:
            line.append(q)
    kind = "immersed_tube" if w.waters and w.kind == "immersed_tube" else "cut_and_cover"
    por = crossing_at(w.prof, portal_z(kind))
    portals = []
    for s, inward, open_m in ((por[0], 1.0, por[0] - w.lo), (por[1], -1.0, w.hi - por[1])):
        p, u = _at(cor.pts, cor.cum, s)
        ux, uy = u[0] * inward, u[1] * inward
        portals.append({"position": (G.q(p[0]), G.q(p[1]), G.q(z_at(w.prof, s))),
                        "heading_deg": G.q(M.degrees(M.atan2(uy, ux)) % 360.0),
                        "open_m": G.q(open_m)})
    crosses = list(w.waters)
    if w.district:
        crosses.append(ctx.did[w.district])
    name = w.name
    if name is None and w.district:
        name = f"{w.district} Tunnel"
    elif name is None:
        wn = {x.id: x.name for x in ctx.waters}
        named = [wn[i] for i in w.waters if wn.get(i)]
        name = f"{named[0]} Tube" if named else None
    return {"id": tid, "type": f"tunnel.{kind}", "kind": kind, "name": name,
            "segment_ids": [], "crosses": crosses, "line": line,
            "width_m": box_width(road_w), "clear_m": CLEAR_M,
            "roof_m": TUBE_ROOF_M if kind == "immersed_tube" else ROOF_M,
            "floor_m": FLOOR_M, "portals": portals, "vent_ids": [],
            "attrs": {"length_m": G.q(w.hi - w.lo),
                      "covered_m": G.q(por[1] - por[0]),
                      "under_water_m": G.q(sum(min(b, w.hi) - max(a, w.lo)
                                               for a, b, need in w.needs
                                               if need > COVERED_NEED + PAD_M + 1.0)),
                      "deepest_m": G.q(min(z for _, z in w.prof)),
                      "district": ctx.did.get(w.district) if w.district else None,
                      "replaces": list(w.bridge_ids)}}


# ---------------------------------------------------------------------------
# After M7 (the network renumbered again)
# ---------------------------------------------------------------------------

def attach(net) -> None:
    """Tunnel rows onto the segments that run through them now; level -1, the private
    profile copy dropped."""
    rows = {t["id"]: t for t in getattr(net, "tunnels", [])}
    for t in rows.values():
        t["segment_ids"] = []
    for s in net.segments:
        s["attrs"].pop("_tunnel_prof", None)
        tid = s["attrs"].get("tunnel")
        if tid is None:
            continue
        s["tunnel"] = True
        s["tunnel_ids"] = [tid]
        s["level"] = -1
        if tid in rows:
            rows[tid]["segment_ids"].append(s["id"])


def relink(tunnels: list[dict], segments: list[dict]) -> list[dict]:
    """Tunnel rows with the segment ids of M2's network (it splits and renumbers M1b's
    roads); a piece of a tunnel road that stays at the ground is not in the tunnel."""
    out = []
    for t in tunnels:
        t = dict(t)
        t["segment_ids"] = []
        out.append(t)
    rows = {t["id"]: t for t in out}
    for s in segments:
        # M2 pieces keep only the crossing points that lie on them
        for key in ("over_tunnel_at", "underpass_at", "ends_at_tunnel"):
            if key in s["attrs"]:
                ln = LineString(s["centerline"])
                keep = [p for p in s["attrs"][key] if ln.distance(Point(p)) < 1.0]
                if keep:
                    s["attrs"][key] = keep
                else:
                    del s["attrs"][key]
        if not s.get("tunnel"):
            continue
        if not any(z["z"] < -0.005 for z in s["z_profile"]):
            s["tunnel"], s["tunnel_ids"], s["level"] = False, [], 0
            continue
        for tid in s["tunnel_ids"]:
            if tid in rows:
                rows[tid]["segment_ids"].append(s["id"])
    return out


# ---------------------------------------------------------------------------
# M3 end: parts, metro tunnels, pedestrian underpasses
# ---------------------------------------------------------------------------

METRO_W_M = 10.0                # twin-track box (transit WIDTH_M)
METRO_CLEAR_M = 5.0
METRO_ROOF_M = 1.0
METRO_H = METRO_CLEAR_M + METRO_ROOF_M
METRO_GRADE = 0.03              # design grade (the check allows 4%)
METRO_MAX_GRADE = 0.04
METRO_GAP_M = 2.0               # under a foundation, a road tunnel or another metro
UND_Z = -4.0                    # pedestrian underpass floor (walkway)
UND_CLEAR_M = 3.0
UND_ROOF_M = 0.5
UND_W_M = 4.0
UND_STAIR_M = 6.5               # stair run from the sidewalk down to the passage
UND_STEP_M = 350.0              # at most one underpass this often along a highway
UND_REACH_M = 30.0              # a sidewalk this far off the highway edge


def foundation_m(height_m: float) -> float:
    """Depth of a building's basement and raft under the ground, by its height (M9): low
    buildings one level, mid-rises two, towers three, supertalls four with a deep raft."""
    if height_m < 20.0:
        return 4.0
    if height_m < 60.0:
        return 7.0
    if height_m < 150.0:
        return 12.0
    return 18.0


def water_bodies(m) -> list[tuple]:
    """(polygon, class, id) of every water body (the classes roads use)."""
    P = G.from_model_poly
    out = []
    for e in m.seas:
        out += [(P(p), "sea", e.id) for p in e.polygons]
    out += [(P(e.polygon), "river", e.id) for e in m.rivers]
    out += [(P(e.polygon), "sea" if e.kind == "sea_channel" else
             "canal" if e.kind == "separation" else "river", e.id) for e in m.channels]
    out += [(P(e.polygon), "sea" if e.kind == "basin" else "canal", e.id)
            for e in m.waterways]
    return out


@dataclass
class Out:
    rows: dict
    notes: list
    info: dict


def _strip(pts, w: float):
    return G.qpoly(LineString(pts).buffer(w / 2.0, cap_style="flat", join_style="mitre",
                                          mitre_limit=2.0))


def _rect(c, u, along: float, across: float):
    hx, hy = u[0] * along / 2.0, u[1] * along / 2.0
    nx, ny = -u[1] * across / 2.0, u[0] * across / 2.0
    from shapely.geometry import Polygon

    return G.qpoly(Polygon([(c[0] - hx - nx, c[1] - hy - ny), (c[0] + hx - nx, c[1] + hy - ny),
                            (c[0] + hx + nx, c[1] + hy + ny), (c[0] - hx + nx, c[1] - hy + ny)]))


def build(spec, m) -> Out:
    """The tunnel parts after M3 and transit: road tunnel portals, open approaches and
    ventilation buildings; the metro lowered under water, road tunnels and foundations and
    its tunnels between the station boxes; pedestrian underpasses under the highways."""
    notes: list[str] = []
    structures: list[dict] = []
    tunnels = [t.model_dump(mode="json") for t in m.tunnels if t.kind in
               ("immersed_tube", "cut_and_cover")]
    for t in tunnels:
        _road_parts(m, t, structures, notes)
    lines, stations, metro = _metro(m, tunnels, notes)
    walks, under, ustruct = _underpasses(spec, m, notes)
    structures += ustruct
    rows = {
        "tunnels": tunnels + metro + under,
        "structures": sorted([*m.structures, *structures],
                             key=lambda s: s.id if hasattr(s, "id") else s["id"]),
        "transit_lines": lines, "stations": stations, "walkways": walks,
    }
    info = {"road_tunnels": len(tunnels), "metro_tunnels": len(metro),
            "underpasses": len(under), "vents": sum(len(t["vent_ids"]) for t in tunnels)}
    return Out(rows, notes, info)


def _road_parts(m, t: dict, out: list, notes: list) -> None:
    from .elevated import _at, _cum, _project, _sub

    pts = [(p[0], p[1]) for p in t["line"]]
    cum = _cum(pts)
    prof = [(s, p[2]) for s, p in zip(cum, t["line"])]
    L = cum[-1]
    w = t["width_m"]
    tid = t["id"]
    sp = sorted(_project(pts, cum, p["position"][:2])[0] for p in t["portals"])
    s_a, s_b = sp[0], sp[-1]
    for tag, a, b, s_p in (("a", 0.0, s_a, s_a), ("b", s_b, L, s_b)):
        if b - a > 0.5:
            seg = _sub(pts, cum, a, b)
            zmin = min(z_at(prof, x) for x in (a, b, (a + b) / 2.0))
            out.append({"id": f"{tid}.ramp{tag}", "type": "structure.tunnel_approach",
                        "kind": "trench", "footprint": G.to_model_poly(_strip(seg, w)),
                        "z0_m": G.q(zmin - t["floor_m"]), "z1_m": 1.0,
                        "supports": list(t["segment_ids"]),
                        "attrs": {"tunnel": tid, "role": "open_approach",
                                  "length_m": G.q(b - a)}})
        seg = _sub(pts, cum, max(s_p - 1.5, 0.0), min(s_p + 1.5, L))
        out.append({"id": f"{tid}.portal{tag}", "type": "structure.tunnel_portal",
                    "kind": "portal", "footprint": G.to_model_poly(_strip(seg, w + 1.0)),
                    "z0_m": G.q(z_at(prof, s_p) - t["floor_m"]), "z1_m": 1.0,
                    "supports": list(t["segment_ids"]),
                    "attrs": {"tunnel": tid, "role": "portal"}})
    covered = s_b - s_a
    if covered < VENT_MIN_M:
        return
    spots = [s_a + 40.0, s_b - 40.0]
    k = int(covered // VENT_STEP_M)
    spots += [s_a + covered * (i + 1) / (k + 1) for i in range(k) if k > 0]
    mine = set(t["segment_ids"])
    axis = LineString(pts)
    # roads over the lid keep the vents 12 m off; the others (frontage streets beside the
    # tunnel) only their own carriageway
    rows = [(LineString(s.centerline).buffer(
        s.width_m / 2.0 + (VENT_GAP_M if LineString(s.centerline).crosses(axis) else 1.0),
        cap_style="flat"), s) for s in m.road_segments if s.id not in mine]
    tree = shapely.STRtree([r[0] for r in rows]) if rows else None
    wet = G.union([poly for poly, _, _ in water_bodies(m)])
    placed = []
    for s0 in sorted(spots):
        ok = None
        for d in (0.0, 20.0, -20.0, 40.0, -40.0, 60.0, -60.0, 80.0, -80.0):
            s = s0 + d
            if not s_a + 15.0 <= s <= s_b - 15.0:
                continue
            c, u = _at(pts, cum, s)
            foot = _rect(c, u, VENT_LEN_M, max(w - 4.0, 8.0))
            hits = [] if tree is None else [int(i) for i in tree.query(foot,
                                                                     predicate="intersects")]
            if hits or foot.intersects(wet) or any(abs(s - x) < 60.0 for x in placed):
                continue
            ok = (s, foot)
            break
        if ok is None:
            notes.append(f"tunnel {tid}: no room on the lid for a ventilation building near "
                         f"{s0:.0f} m")
            continue
        s, foot = ok
        placed.append(s)
        vid = f"{tid}.vent{len(placed)}"
        out.append({"id": vid, "type": "structure.tunnel_vent", "kind": "vent",
                    "footprint": G.to_model_poly(foot), "z0_m": 0.0, "z1_m": VENT_H_M,
                    "supports": [], "attrs": {"tunnel": tid, "role": "ventilation",
                                              "at_m": G.q(s)}})
        t["vent_ids"].append(vid)


def _graded_min(cum, caps, g: float, loop: bool) -> list[float]:
    """z_i = min_j(cap_j + g |s_i - s_j|) (a loop measures both ways round)."""
    L = cum[-1]
    out = []
    deep = [(j, c) for j, c in enumerate(caps)]
    for i, si in enumerate(cum):
        z = caps[i]
        for j, c in deep:
            d = abs(si - cum[j])
            if loop:
                d = min(d, L - d)
            v = c + g * d
            if v < z:
                z = v
        out.append(G.q(z))
    return out


def _metro(m, road_tunnels: list, notes: list) -> tuple[list, list, list]:
    """Metro lines lowered (at the metro grade) under the water bed, the road tunnels, the
    building foundations and the metro lines before them; their tunnels between the station
    boxes."""
    from .elevated import _cum

    lines = [t.model_dump(mode="json") for t in m.transit_lines]
    stations = [s.model_dump(mode="json") for s in m.stations]
    st_by = {s["id"]: s for s in stations}
    water = water_bodies(m)
    wpolys = [G.qpoly(p.buffer(BANK_M)) for p, _, _ in water]
    wtree = shapely.STRtree(wpolys) if wpolys else None
    blds = [(G.from_model_poly(b.footprint).buffer(METRO_W_M / 2.0 + METRO_GAP_M),
             foundation_m(b.height_m), b.id) for b in m.buildings if b.footprint is not None]
    btree = shapely.STRtree([b[0] for b in blds]) if blds else None
    rts = [(LineString([p[:2] for p in t["line"]]), t) for t in road_tunnels]
    done: list = []                    # (line 2D, pts, zs) of the metro lines before
    tunnels = []
    k = 0
    for ln in lines:
        if ln["mode"] != "metro" or len(ln["path"]) < 2:
            continue
        pts = [(p[0], p[1]) for p in ln["path"]]
        z0 = min(p[2] for p in ln["path"])
        cum = _cum(pts)
        arr = shapely.points(pts)
        caps = [z0] * len(pts)
        why = [None] * len(pts)
        if wtree is not None:
            ip, ig = wtree.query(arr, predicate="intersects")
            for i, j in zip(ip.tolist(), ig.tolist()):
                need = -(BED_M[water[j][1]] + BED_COVER_M + METRO_H)
                if need < caps[i]:
                    caps[i], why[i] = need, "water"
        if btree is not None:
            ip, ig = btree.query(arr, predicate="intersects")
            for i, j in zip(ip.tolist(), ig.tolist()):
                need = -(blds[j][1] + METRO_GAP_M + METRO_H)
                if need < caps[i]:
                    caps[i], why[i] = need, "foundation"
        for rl, t in rts:
            reach = t["width_m"] / 2.0 + METRO_W_M / 2.0 + METRO_GAP_M
            from .elevated import _cum as _c, _project

            tp = [(p[0], p[1]) for p in t["line"]]
            tc = _c(tp)
            tprof = [(s, p[2]) for s, p in zip(tc, t["line"])]
            for i in shapely.dwithin(arr, rl, reach).nonzero()[0].tolist():
                zr = z_at(tprof, _project(tp, tc, pts[i])[0])
                need = zr - t["floor_m"] - METRO_GAP_M - METRO_H
                if need < caps[i]:
                    caps[i], why[i] = need, "road tunnel"
        for dl, dpts, dzs in done:
            dc = _cum(dpts)
            from .elevated import _project

            for i in shapely.dwithin(arr, dl, METRO_W_M + METRO_GAP_M).nonzero()[0].tolist():
                zo = z_at(list(zip(dc, dzs)), _project(dpts, dc, pts[i])[0])
                if abs(zo - caps[i]) < METRO_H + 1.0 + METRO_GAP_M:
                    need = zo - 1.0 - METRO_GAP_M - METRO_H
                    if need < caps[i]:
                        caps[i], why[i] = need, "metro"
        loop = bool(ln["loop"]) and pts[0] == pts[-1]
        # M13: graded on the ground (ground + z), then measured from the ground again
        from . import terrain as TE

        gr = TE.on_ground(m, pts)
        zs = _graded_min(cum, [c + g for c, g in zip(caps, gr)], METRO_GRADE, loop)
        za = list(zs)                  # on the ground (M13; the same on a flat city)
        zs = [G.q(z - g) for z, g in zip(zs, gr)]
        ln["path"] = [[x, y, z] for (x, y), z in zip(pts, zs)]
        deep = min(zs)
        ln["attrs"] = {**ln["attrs"], "tunnel_deepest_m": deep,
                       "lowered_for": sorted({w for w in why if w})}
        if deep < z0 - 0.005:
            notes.append(f"metro {ln['name']}: lowered to {deep:g} m under "
                         f"{', '.join(sorted({w for w in why if w}))}")
        # stations at the track's height there
        foots = []
        for sid in ln["station_ids"]:
            st = st_by[sid]
            p = st["position"]
            from .elevated import _project

            s_at = _project(pts, cum, p[:2])[0]
            zt = z_at(list(zip(cum, za)), s_at) - TE.on_ground(m, [p[:2]])[0]
            st["attrs"] = {**st["attrs"], "track_z_m": G.q(zt)}
            if st.get("footprint"):
                foots.append((s_at, G.from_model_poly(st["footprint"]), sid))
        done.append((LineString(pts), pts, zs))
        # tunnels between the station boxes
        line2 = LineString(pts)
        box = G.union([f for _, f, _ in foots]) if foots else None
        rest = line2 if box is None else line2.difference(box)
        from .roads import G_lines
        from .elevated import _project

        parts = sorted((p for p in G_lines(rest) if p.length > 5.0),
                       key=lambda p: (round(_project(pts, cum, p.coords[0])[0], 2),
                                      round(p.length, 2)))
        order = sorted(foots, key=lambda f: (round(f[0], 2), f[2]))
        for part in parts:
            cs = [G.qpoint(c) for c in part.coords]
            sa = _project(pts, cum, cs[0])[0]
            sb = _project(pts, cum, cs[-1])[0]
            if sb < sa:
                cs, sa, sb = cs[::-1], sb, sa
            prof = list(zip(cum, za))
            gc = TE.on_ground(m, cs)
            l3 = [(x, y, G.q(z_at(prof, _project(pts, cum, (x, y))[0]) - g))
                  for (x, y), g in zip(cs, gc)]
            k += 1
            before = [f[2] for f in order if f[0] <= sa + 1.0]
            after = [f[2] for f in order if f[0] >= sb - 1.0]
            tunnels.append({"id": f"tm{k:02d}", "type": "tunnel.metro", "kind": "metro",
                            "name": ln["name"], "segment_ids": [], "line_id": ln["id"],
                            "walkway_ids": [], "crosses": [], "line": l3,
                            "width_m": METRO_W_M, "clear_m": METRO_CLEAR_M,
                            "roof_m": METRO_ROOF_M, "floor_m": FLOOR_M, "portals": [],
                            "vent_ids": [],
                            "attrs": {"length_m": G.q(sb - sa),
                                      "deepest_m": G.q(min(p[2] for p in l3)),
                                      "from_station": before[-1] if before else None,
                                      "to_station": after[0] if after else None}})
    return lines, stations, tunnels


def _underpasses(spec, m, notes: list) -> tuple[list, list, list]:
    """Pedestrian underpasses under the at-grade highways, from a sidewalk on one side to a
    sidewalk on the other (frontage streets): stairs down 6.5 m from each sidewalk, a
    passage 4 m under the highway; at most one every 350 m along a highway, none within
    80 m of a node or 120 m of a street that crosses it."""
    from .buildout import _foot, _ground, _neighbors, _split
    from .elevated import _at, _cum

    walks = [w.model_dump(mode="json") for w in m.walkways]
    share = spec.highways.tunnels.underpasses
    if share <= 0:
        return walks, [], []
    gi = [i for i in _ground(walks) if walks[i]["kind"] == "sidewalk"]
    if not gi:
        return walks, [], []
    glines = [LineString([p[:2] for p in walks[i]["line"]]) for i in gi]
    gtree = shapely.STRtree(glines)
    crossers = [LineString(s.centerline) for s in m.road_segments
                if s.attrs.get("role") in ("underpass", "over_tunnel")
                or s.attrs.get("over_tunnel_at")]
    blocked = [G.from_model_poly(b.footprint) for b in m.buildings if b.footprint is not None]
    blocked += [G.from_model_poly(s.footprint) for s in m.structures if s.footprint is not None]
    blocked += [G.from_model_poly(j.polygon) for j in m.junctions]
    btree = shapely.STRtree(blocked) if blocked else None
    roads = [(LineString(s.centerline), s) for s in m.road_segments]
    rtree = shapely.STRtree([r[0] for r in roads])
    wet = G.union([poly for poly, _, _ in water_bodies(m)])
    cands = []
    for s in sorted(m.road_segments, key=lambda s: s.id):
        if s.road_class != "highway" or s.bridge or s.tunnel or s.attrs.get("elevated") or \
                s.attrs.get("role") == "ramp" or any(abs(z.z) > 0.05 for z in s.z_profile):
            continue
        pts = [tuple(p) for p in s.centerline]
        cum = _cum(pts)
        L = cum[-1]
        hw = s.width_m / 2.0
        x = 80.0
        while x <= L - 80.0:
            here = x
            x += 20.0
            c, u = _at(pts, cum, here)
            if any(cr.distance(Point(c)) < 120.0 for cr in crossers):
                continue
            nrm = (-u[1], u[0])
            ends = []
            for sg in (1.0, -1.0):
                ray = LineString([(c[0] + nrm[0] * sg * (hw + 1.0), c[1] + nrm[1] * sg * (hw + 1.0)),
                                  (c[0] + nrm[0] * sg * (hw + UND_REACH_M),
                                   c[1] + nrm[1] * sg * (hw + UND_REACH_M))])
                best = None
                for kk in sorted(int(i) for i in gtree.query(ray, predicate="intersects")):
                    hit = ray.intersection(glines[kk])
                    for hp in G_points(hit):
                        d = M.hypot(hp[0] - c[0], hp[1] - c[1])
                        if best is None or (round(d, 3), kk) < best[:2]:
                            best = (round(d, 3), kk, hp)
                if best is None or best[0] - hw < 0.6 * UND_STAIR_M + 0.5:
                    break
                ends.append((sg, best))
            if len(ends) < 2:
                continue
            cands.append((s, here, c, nrm, ends))
    # one every UND_STEP_M along each highway, then `share` of them
    picked: list = []
    for s, here, c, nrm, ends in cands:
        if any(M.hypot(c[0] - p[2][0], c[1] - p[2][1]) < UND_STEP_M for p in picked):
            continue
        feet, ok = [], True
        for sg, (d, kk, hp) in ends:
            f = _foot(glines, walks, gi, kk, hp)
            bot = (G.q(f[0] - nrm[0] * sg * UND_STAIR_M), G.q(f[1] - nrm[1] * sg * UND_STAIR_M))
            well = _rect(((f[0] + bot[0]) / 2.0, (f[1] + bot[1]) / 2.0),
                         (-nrm[0] * sg, -nrm[1] * sg), UND_STAIR_M, 3.2)
            if btree is not None and len(btree.query(well, predicate="intersects")):
                ok = False
                break
            for ri in rtree.query(well, predicate="intersects").tolist():
                if roads[ri][1].id != s.id:
                    ok = False
            feet.append((kk, f, bot, well))
        if not ok:
            continue
        passage = LineString([feet[0][2], feet[1][2]])
        if passage.intersects(wet):
            continue
        others = [roads[ri][1].id for ri in rtree.query(passage, predicate="intersects").tolist()
                  if roads[ri][1].id != s.id]
        if others:
            continue
        picked.append((s, here, c, nrm, feet))
    keep = [p for i, p in enumerate(picked) if math.floor((i + 1) * share) > math.floor(i * share)]
    if not keep:
        return walks, [], []
    splits: dict = {}
    new = []
    tunnels, structures = [], []
    for n_, (s, here, c, nrm, feet) in enumerate(keep):
        tid = f"tp{n_ + 1:02d}"
        (ka, fa, ba, wa), (kb, fb, bb, wb) = feet
        splits.setdefault(ka, []).append(fa)
        splits.setdefault(kb, []).append(fb)
        z = UND_Z
        new.append(("stairs", [(fa[0], fa[1], 0.0), (ba[0], ba[1], z)], 3.0, tid))
        new.append(("underpass", [(ba[0], ba[1], z), (bb[0], bb[1], z)], UND_W_M, tid))
        new.append(("stairs", [(bb[0], bb[1], z), (fb[0], fb[1], 0.0)], 3.0, tid))
        for tag, well in (("a", wa), ("b", wb)):
            structures.append({"id": f"{tid}.stair{tag}", "type": "structure.underpass_stair",
                               "kind": "trench", "footprint": G.to_model_poly(well),
                               "z0_m": G.q(z), "z1_m": 1.1, "supports": [],
                               "attrs": {"tunnel": tid, "role": "underpass_stair"}})
        tunnels.append({"id": tid, "type": "tunnel.pedestrian", "kind": "pedestrian",
                        "name": None, "segment_ids": [], "line_id": None, "walkway_ids": [],
                        "crosses": [s.id], "line": [(ba[0], ba[1], z), (bb[0], bb[1], z)],
                        "width_m": UND_W_M, "clear_m": UND_CLEAR_M, "roof_m": UND_ROOF_M,
                        "floor_m": 0.5, "portals": [], "vent_ids": [],
                        "attrs": {"length_m": G.q(_d(ba, bb)), "highway": s.id}})
    walks = _split(walks, gi, glines, splits)
    k = max(int(w["id"][2:]) for w in walks)
    by_t = {t["id"]: t for t in tunnels}
    for kind, line3, width, tid in new:
        k += 1
        wid = f"wk{k:06d}"
        walks.append({"id": wid, "type": "walkway", "kind": kind,
                      "line": [tuple(G.q(v) for v in p) for p in line3], "width_m": width,
                      "neighbors": [], "attrs": {"tunnel": tid}})
        by_t[tid]["walkway_ids"].append(wid)
    _neighbors(walks)
    notes.append(f"{len(tunnels)} pedestrian underpasses under the highways")
    return walks, tunnels, structures


def G_points(g) -> list[tuple[float, float]]:
    from .elevated import G_points as _gp

    return _gp(g)
