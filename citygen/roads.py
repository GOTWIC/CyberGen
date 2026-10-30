"""Stage 4, the primary road network: highways, arterials (avenues), bridges, off-map exits.

Everything is routed on a 25 m cost raster of the built city and then fitted as real road
geometry:

1. **Raster.** Each cell is land, canal-scale water (separation channels, canals, creeks,
   inlets, marinas), river-scale water (rivers, delta branches) or sea-scale water (sea, sea
   channels, harbor basins: the port approaches). Megasite reserves, spaceport flight cones and
   open land (marsh, park) are closed; cells next to a quay cost extra so roads keep clear of
   the quays. Water costs per meter and once per entry (sea far more than river, river more
   than canal), so routes cross where the water is narrow and major bridges stay few.
2. **Routing.** A* (point to point) or Dijkstra (region to region) over 16 neighbors. Later
   routes may reuse earlier roads at a discount; only their new parts are added, joined to the
   old roads at T-junctions.
3. **Crossings.** Every water run of a route is replaced by the shortest straight crossing
   between the two banks near it (the narrowest point), with straight approaches at both ends.
4. **Fitting.** Land runs are simplified (Douglas-Peucker) and every corner becomes a circular
   arc (a fillet). Radii start at the preferred radius of the class and shrink only to fit the
   tangent lengths; a corner that cannot keep the minimum radius is removed (its neighbors are
   joined) when the shortcut stays clear of closed cells and adds no water.

Highways follow `highways.pattern` (ring, ring_plus_spine, spine, grid, radial, coastal, none)
and run to the `exits`; named routes follow their stops. Arterials, in order: axis boulevards
(rotated grids), ring roads (transit hubs, around central parks), waterfront avenues at a
setback from major water, avenues on the land boundaries between districts, and coverage
chords at the district grid angle until no point of a district is farther than half its
archetype spacing from a road. Then named bridges, then connectors until every landmass with a
district is reachable, then extra river and canal crossings by `water.bridges.density`.
"""

from __future__ import annotations

import heapq
import math
from dataclasses import dataclass, field

import numpy as np
import shapely
from shapely.geometry import LineString, MultiLineString, Point, Polygon
from shapely.ops import nearest_points, unary_union

from . import dmath as M
from . import geom as G
from . import presets
from . import relations as R
from .spec import CitySpec

CELL_M = 25.0
NONE, CANAL, RIVER, SEA = 0, 1, 2, 3
WATER_CLASS = {CANAL: "canal", RIVER: "river", SEA: "sea"}
WATER_M_COST = {NONE: 1.0, CANAL: 4.0, RIVER: 8.0, SEA: 14.0}
WATER_ENTRY = {NONE: 0.0, CANAL: 60.0, RIVER: 300.0, SEA: 1500.0}
REUSE = 0.25
BRIDGE_JOIN = 8000.0       # joining or crossing an existing bridge on the water
QUAY_COST = 1.5
OUTSIDE_COST = 1.25        # land without a district (still allowed)
SLOPE_FREE = 0.04          # M13: ground up to this steep costs nothing extra
SLOPE_COST = 40.0          # M13: extra cost per unit of slope over SLOPE_FREE

# Cross-sections and alignment (scope 5.1). Radii in meters.
CLASSES = {
    "highway": {"lanes": (3, 3), "lane": 3.6, "median": 3.0, "sidewalk": (0.0, 0.0),
                "width": 30.0, "r_pref": 420.0, "r_min": 150.0, "dp": 30.0, "approach": 45.0,
                "min_len": 60.0},
    "avenue": {"lanes": (2, 2), "lane": 3.3, "median": 4.0, "sidewalk": (5.0, 5.0),
               "width": 28.0, "r_pref": 160.0, "r_min": 40.0, "dp": 12.0, "approach": 18.0,
               "min_len": 40.0},
}
BOULEVARD = {"lanes": (3, 3), "median": 6.0, "sidewalk": (6.0, 6.0), "width": 38.0}

CLEARANCE_M = {"sea": 25.0, "river": (10.0, 15.0), "canal": (3.0, 4.0)}
DECK_M = 1.5
RAMP_GRADE = 0.06
WATERFRONT_SETBACK_M = 50.0
EDGE_KEEP_M = 40.0          # roads stay this far from the map edge, exits aside
JUNCTION_SKIP_M = {"highway": 60.0, "avenue": 25.0}  # junction area (see checks)
OPTIONAL_ROLES = ("waterfront", "boundary", "chord", "crossing", "ring_road", "axis_boulevard")
DANGLE_M = 120.0
SPACING_M = {
    "corporate_core": 350.0, "transit_hub": 350.0, "entertainment_market": 400.0,
    "midtown_mixed": 400.0, "megablock_residential": 450.0, "old_town": 500.0,
    "residential_heights": 500.0, "research_campus": 550.0, "industrial_port": 600.0,
    "spaceport": 700.0,
}
BRIDGE_SPACING_M = {RIVER: 650.0, CANAL: 450.0}

_MOVES = []
for _dx, _dy in [(1, 0), (0, 1), (-1, 0), (0, -1), (1, 1), (1, -1), (-1, 1), (-1, -1),
                 (2, 1), (1, 2), (-1, 2), (-2, 1), (-2, -1), (-1, -2), (1, -2), (2, -1)]:
    if abs(_dx) + abs(_dy) == 3:  # knight move: passes the two cells beside its middle
        mids = [(_dx // 2 if abs(_dx) == 2 else 0, _dy // 2 if abs(_dy) == 2 else 0),
                (_dx // 2 if abs(_dx) == 2 else _dx, _dy // 2 if abs(_dy) == 2 else _dy)]
    elif _dx and _dy:
        mids = [(_dx, 0), (0, _dy)]
    else:
        mids = []
    _MOVES.append((_dx, _dy, math.sqrt(_dx * _dx + _dy * _dy), mids))


# ---------------------------------------------------------------------------
# Records
# ---------------------------------------------------------------------------

@dataclass
class Road:
    cls: str
    line: LineString
    role: str
    name: str | None = None
    district: str | None = None
    causeway: bool = False
    pin: dict | None = None       # a traced road (role "pinned"): kept as drawn


@dataclass
class NamedRoute:
    name: str
    kind: str
    line: LineString
    ends: tuple[str, str]
    crosses: str | None
    causeway: bool


@dataclass
class Water:
    id: str
    cls: int
    kind: str
    name: str | None
    polygon: object
    river: str | None = None  # the river or sea channel a delta branch belongs to


@dataclass
class RoadNet:
    nodes: list[dict] = field(default_factory=list)
    segments: list[dict] = field(default_factory=list)
    bridges: list[dict] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    exits: dict[str, tuple[float, float]] = field(default_factory=dict)
    variant: int = 0
    elevated: dict = field(default_factory=dict)
    tunnels: list[dict] = field(default_factory=list)
    terrain: object = None     # M13: (natural Field, Levels, stats) when the spec has terrain


# ---------------------------------------------------------------------------
# Raster and router
# ---------------------------------------------------------------------------

class Grid:
    def __init__(self, canvas, waters: list[Water], closed, quays, district_land,
                 marsh_parks):
        minx, miny, maxx, maxy = canvas.bounds
        self.x0, self.y0 = minx, miny
        self.nx = int(math.ceil((maxx - minx) / CELL_M))
        self.ny = int(math.ceil((maxy - miny) / CELL_M))
        ii, jj = np.meshgrid(np.arange(self.nx), np.arange(self.ny))
        self.xs = (minx + (ii.ravel() + 0.5) * CELL_M)
        self.ys = (miny + (jj.ravel() + 0.5) * CELL_M)
        n = self.nx * self.ny
        wc = np.zeros(n, dtype=np.int8)
        for w in waters:
            inside = shapely.contains_xy(w.polygon, self.xs, self.ys)
            wc = np.where(inside & (wc < w.cls), np.int8(w.cls), wc)
        self.wcls = wc
        base = np.where(wc > 0, np.array([WATER_M_COST[k] for k in range(4)])[wc], 1.0)
        on_city = shapely.contains_xy(district_land, self.xs, self.ys) \
            if not district_land.is_empty else np.zeros(n, bool)
        base = np.where((wc == 0) & ~on_city, OUTSIDE_COST, base)
        if quays is not None and not quays.is_empty:
            near_q = shapely.contains_xy(quays.buffer(15.0), self.xs, self.ys)
            base = np.where(near_q & (wc == 0), base + QUAY_COST, base)
        # Closed areas are widened by most of a cell, so fitted curves between cell centers
        # stay out of them.
        pad = 0.8 * CELL_M
        self.closed = shapely.contains_xy(closed.buffer(pad), self.xs, self.ys) \
            if closed is not None and not closed.is_empty else np.zeros(n, bool)
        self.marsh = shapely.contains_xy(marsh_parks.buffer(pad), self.xs, self.ys) \
            if marsh_parks is not None and not marsh_parks.is_empty else np.zeros(n, bool)
        self.base = base
        self.on_city = on_city
        self.reuse = np.zeros(n, dtype=bool)
        self.reuse_hw = np.zeros(n, dtype=bool)

    def slope_cost(self, terrain) -> None:
        """M13: steep land costs more, so roads go round hills and climb along the slope."""
        sl = terrain.slope_many(self.xs, self.ys)
        extra = 1.0 + SLOPE_COST * np.maximum(sl - SLOPE_FREE, 0.0)
        self.base = np.where(self.wcls == 0, self.base * extra, self.base)

    def idx(self, p) -> int:
        i = min(max(int((p[0] - self.x0) // CELL_M), 0), self.nx - 1)
        j = min(max(int((p[1] - self.y0) // CELL_M), 0), self.ny - 1)
        return j * self.nx + i

    def xy(self, k: int) -> tuple[float, float]:
        return (float(self.xs[k]), float(self.ys[k]))

    def deep(self) -> np.ndarray:
        """Land at least two cells from any water."""
        return ~self._widen((self.wcls > 0).reshape(self.ny, self.nx))

    def near(self, highway: bool = False) -> np.ndarray:
        """The network (all roads or highways) widened by two cells."""
        return self._widen((self.reuse_hw if highway else self.reuse).reshape(self.ny,
                                                                                self.nx))

    def _widen(self, m) -> np.ndarray:
        out = m.copy()
        for dy in range(-2, 3):
            for dx in range(-2, 3):
                sh = np.zeros_like(m)
                ys = slice(max(dy, 0), self.ny + min(dy, 0))
                yd = slice(max(-dy, 0), self.ny + min(-dy, 0))
                xs = slice(max(dx, 0), self.nx + min(dx, 0))
                xd = slice(max(-dx, 0), self.nx + min(-dx, 0))
                sh[yd, xd] = m[ys, xs]
                out |= sh
        return out.ravel()

    def mark(self, line: LineString, highway: bool) -> None:
        """Cells on a road (for reuse by later routes)."""
        if line is None or line.is_empty:
            return
        pts = G.resample(line, CELL_M / 2)
        for x, y in pts:
            k = self.idx((x, y))
            self.reuse[k] = True
            if highway:
                self.reuse_hw[k] = True

    def costs(self, reuse: str | None, causeway: bool = False, shore: float = 1.0
              ) -> list[float]:
        c = self.base.copy()
        if shore != 1.0:
            if not hasattr(self, "_deep"):
                self._deep = self.deep()
            c = np.where((self.wcls == 0) & ~self._deep, c * shore, c)
        if reuse == "all":
            c = np.where(self.reuse, c * REUSE, c)
        elif reuse == "highway":
            c = np.where(self.reuse_hw, c * REUSE, c)
        closed = self.closed if causeway else (self.closed | self.marsh)
        c = np.where(closed, np.inf, c)
        return c.tolist()

    def free(self, causeway: bool = False) -> np.ndarray:
        closed = self.closed if causeway else (self.closed | self.marsh)
        return ~closed

    def search(self, sources: list[int], targets: set[int], reuse: str | None = None,
               causeway: bool = False, heuristic: bool = True,
               block=None, shore: float = 1.0) -> list[int] | None:
        cost = self.costs(reuse, causeway, shore)
        if block is not None:
            for k in np.nonzero(block)[0].tolist():
                cost[k] = math.inf
        wc = self.wcls.tolist()
        # Joining, leaving or crossing an existing bridge out on the water is not allowed in
        # practice (no junctions on bridges; grade separation is M7): it costs a lot.
        on = self.reuse.tolist()
        wn = (self.reuse & (self.wcls > 0)).tolist()
        nx, ny = self.nx, self.ny
        sources = [s for s in dict.fromkeys(sources) if cost[s] != math.inf] or sources[:1]
        if not targets:
            return None
        tlist = sorted(targets)
        single = heuristic and len(tlist) == 1
        if single:
            tx, ty = tlist[0] % nx, tlist[0] // nx
            hk = REUSE if reuse else 1.0
        g = {s: 0.0 for s in sources}
        came: dict[int, int] = {}
        heap = []
        cnt = 0
        for s in sources:
            h0 = hk * math.sqrt((s % nx - tx) ** 2 + (s // nx - ty) ** 2) * CELL_M if single \
                else 0.0
            heap.append((h0, cnt, s))
            cnt += 1
        heapq.heapify(heap)
        done = set()
        while heap:
            _, _, u = heapq.heappop(heap)
            if u in done:
                continue
            done.add(u)
            if u in targets:
                path = [u]
                while path[-1] in came:
                    path.append(came[path[-1]])
                return path[::-1]
            ux, uy = u % nx, u // nx
            gu = g[u]
            cu = cost[u]
            wu = wc[u]
            for dx, dy, length, mids in _MOVES:
                vx, vy = ux + dx, uy + dy
                if vx < 0 or vy < 0 or vx >= nx or vy >= ny:
                    continue
                v = vy * nx + vx
                cv = cost[v]
                if cv == math.inf:
                    continue
                total, k, wmax = cu + cv, 2, max(wu, wc[v])
                blocked = False
                for mx, my in mids:
                    m = (uy + my) * nx + ux + mx
                    cm = cost[m]
                    if cm == math.inf:
                        blocked = True
                        break
                    total += cm
                    k += 1
                    wmax = max(wmax, wc[m])
                if blocked:
                    continue
                step = length * CELL_M * total / k
                if wmax > wu:
                    step += WATER_ENTRY[wmax] - WATER_ENTRY[wu]
                if (wn[v] and not on[u]) or (wn[u] and not on[v]):
                    step += BRIDGE_JOIN
                nd = gu + step
                if nd < g.get(v, math.inf):
                    g[v] = nd
                    came[v] = u
                    h = hk * math.sqrt((vx - tx) ** 2 + (vy - ty) ** 2) * CELL_M \
                        if single else 0.0
                    heapq.heappush(heap, (nd + h, cnt, v))
                    cnt += 1
        return None


# ---------------------------------------------------------------------------
# Geometry fitting
# ---------------------------------------------------------------------------

class Fitter:
    """Turns raster paths into road alignments (straight crossings, fillet curves)."""

    def __init__(self, ctx: "Ctx"):
        self.ctx = ctx

    def crossing(self, a: tuple[float, float], b: tuple[float, float],
                 causeway: bool = False, run: list[tuple] | None = None,
                 cls: str = "avenue") -> tuple[tuple, tuple]:
        """Shortest straight crossing between the bank near `a` and the bank near `b` that
        passes where the raster path crossed (`run`, its water cells)."""
        ctx = self.ctx
        dry = ctx.dry
        bank = ctx.dry_boundary

        def cands(p):
            pt = Point(p)
            near = bank.intersection(pt.buffer(110.0))
            out = [p]
            for ln in G_lines(near):
                n = max(int(ln.length / 8.0), 1)
                for k in range(n + 1):
                    q = ln.interpolate(k / n, normalized=True)
                    out.append((q.x, q.y))
            if not dry.contains(pt):  # an exit on water: keep the point itself only
                return [p]
            return out

        ca, cb = cands(a), cands(b)
        best, best_cost = None, math.inf
        lines = []
        meta = []
        for p in ca:
            for r in cb:
                if p == r:
                    continue
                lines.append(LineString([p, r]))
                meta.append((p, r))
        if not lines:
            return None
        arr = np.array(lines, dtype=object)
        inner = ctx.dry_inner
        # a bridge may pass over a small land tip or islet (up to 40 m of land)
        touch = shapely.intersects(arr, inner)
        ok = ~touch
        clips = np.zeros(len(lines), bool)
        if touch.any():
            idx = np.nonzero(touch)[0]
            ok[idx] = shapely.length(shapely.intersection(arr[idx], inner)) <= 40.0
            # last choice: a span over the tip of a district's land (another road would meet
            # it out on the water there)
            dl = ctx.district_land.buffer(-3.0)
            for i in idx:
                if ok[i]:
                    p, r = meta[i]
                    tip = shapely.intersection(arr[i], dl)
                    clips[i] = not tip.is_empty and tip.length > 1.0 and \
                        tip.distance(Point(p)) > 1.0 and tip.distance(Point(r)) > 1.0
        if ctx.closed is not None and not ctx.closed.is_empty:
            closed = ctx.closed if causeway else ctx.closed_all
            ok &= ~shapely.intersects(arr, closed)
        if run:
            zone = (LineString(run) if len(run) > 1 else Point(run[0])).buffer(CELL_M * 0.75)
            ok &= shapely.intersects(arr, zone)
        # room on the bridge axis past both banks for the straight approach and the start of
        # the turn after it (a landing beside a port slip or a reserve kinks at the bank)
        cramped = np.zeros(len(lines), bool)
        if ok.any():
            need = CLASSES[cls]["approach"] + 0.25 * CLASSES[cls]["r_min"]
            if not hasattr(ctx, "_wet_closed"):
                ctx._wet_closed = unary_union([ctx.wet, ctx.closed_all])
            stop = ctx.wet if causeway else ctx._wet_closed
            idx = np.nonzero(ok)[0]
            rays = []
            for i in idx:
                (px, py), (rx, ry) = meta[i]
                ux, uy = _unit(rx - px, ry - py)
                rays.append(LineString([(px - ux * 2.0, py - uy * 2.0),
                                        (px - ux * need, py - uy * need)]))
                rays.append(LineString([(rx + ux * 2.0, ry + uy * 2.0),
                                        (rx + ux * need, ry + uy * need)]))
            hit = shapely.intersects(np.array(rays, dtype=object), stop).reshape(-1, 2)
            # an end on the water (an exit) has no approach to keep
            wet_a, wet_b = not dry.contains(Point(a)), not dry.contains(Point(b))
            for i, (h0, h1) in zip(idx, hit):
                cramped[i] = (h0 and not wet_a) or (h1 and not wet_b)
        for good, tight, clip, ln, (p, r) in zip(ok, cramped, clips, lines, meta):
            if not good:
                continue
            da = M.hypot(p[0] - a[0], p[1] - a[1])
            if da > M.hypot(p[0] - b[0], p[1] - b[1]) or \
                    M.hypot(r[0] - b[0], r[1] - b[1]) > M.hypot(r[0] - a[0], r[1] - a[1]):
                continue
            c = ln.length + 0.12 * (M.hypot(p[0] - a[0], p[1] - a[1])
                                    + M.hypot(r[0] - b[0], r[1] - b[1])) + 1e6 * tight \
                + 1e6 * clip
            if c < best_cost:
                best_cost, best = c, (p, r)
        return best

    def path_chain(self, grid: Grid, path: list[int], start=None, end=None,
                   causeway: bool = False, cls: str = "avenue"):
        """Raster path -> vertex chain where every water run is a straight crossing between
        the banks (shortest near the raster crossing) with straight approaches of the class
        approach length on both sides: ... A, bank, bank, B ... all fixed and collinear, so
        no curve ever starts on a bridge. Returns (points, fixed index set)."""
        pts = [grid.xy(k) for k in path]
        wet = [int(grid.wcls[k]) > 0 for k in path]
        # an exit lies on the map border, which `contains` leaves out: `covers`
        if start is not None:
            pts[0] = start
            wet[0] = not self.ctx.dry.covers(Point(start))
        if end is not None:
            pts[-1] = end
            wet[-1] = not self.ctx.dry.covers(Point(end))
        a_len = CLASSES[cls]["approach"]
        n = len(pts)
        out: list[tuple] = []
        fixed: set[int] = set()
        i = 0
        while i < n:
            if not wet[i]:
                out.append(pts[i])
                i += 1
                continue
            j = i
            while j < n and wet[j]:
                j += 1
                # a land tip of up to two cells between two waters: one crossing over it
                if j < n and not wet[j]:
                    k2 = j
                    while k2 < n and not wet[k2] and k2 - j < 3:
                        k2 += 1
                    if k2 < n and wet[k2] and k2 - j < 3:
                        j = k2
            # water run pts[i:j]; banks near the last land point before and the first after
            a = out[-1] if out else pts[0]
            b = pts[j] if j < n else pts[-1]
            run = pts[i:j]
            if out:
                cr = self.crossing(a, b, causeway, run, cls) if j < n else (a, b)
            else:
                cr = self.crossing(pts[0], b, causeway, run, cls) if j < n \
                    else (pts[0], pts[-1])
                cr = (pts[0], cr[1]) if cr is not None else None
            if cr is None:
                # no clear straight crossing: keep the raster course over the water
                out += run
                fixed.add(len(out) - 1)
                i = j
                continue
            pa, pb = cr
            u = _unit(pb[0] - pa[0], pb[1] - pa[1])
            # approach lengths: the straight plus the tangent of the turn that follows, so
            # the curve keeps the class minimum radius and never starts on the bridge
            before = next((q for q in reversed(out[:-1] if out else [])
                           if M.hypot(q[0] - pa[0], q[1] - pa[1]) > 150.0),
                          out[0] if out else None)
            after = next((q for q in pts[j:] if M.hypot(q[0] - pb[0], q[1] - pb[1]) > 150.0),
                         pts[-1] if j < n else None)
            len_a = self._approach(pa, (-u[0], -u[1]), before, cls, causeway) if out else 0.0
            len_b = self._approach(pb, u, after, cls, causeway) if j < n else 0.0
            if out:
                # drop land points that the approach covers or that lie past it
                a_len = len_a
                ax, ay = pa[0] - u[0] * a_len, pa[1] - u[1] * a_len
                while len(out) > 1 and (
                        M.hypot(out[-1][0] - pa[0], out[-1][1] - pa[1]) < a_len + CELL_M
                        or ((out[-1][0] - ax) * u[0] + (out[-1][1] - ay) * u[1] > -1.0 and
                            M.hypot(out[-1][0] - pa[0], out[-1][1] - pa[1])
                            < a_len + 3 * CELL_M)):
                    out.pop()
                if len(out) == 1 and M.hypot(out[0][0] - pa[0], out[0][1] - pa[1]) < a_len:
                    out.pop()
                if out:
                    out.append((ax, ay))
                    fixed.add(len(out) - 1)
            out.append(pa)
            fixed.add(len(out) - 1)
            if pb != pa:
                out.append(pb)
                fixed.add(len(out) - 1)
            if j >= n:
                break
            a_len = len_b
            bx, by = pb[0] + u[0] * a_len, pb[1] + u[1] * a_len
            k = j
            while k < n - 1 and not wet[k] and (
                    M.hypot(pts[k][0] - pb[0], pts[k][1] - pb[1]) < a_len + CELL_M
                    or ((pts[k][0] - bx) * u[0] + (pts[k][1] - by) * u[1] < 1.0 and
                        M.hypot(pts[k][0] - pb[0], pts[k][1] - pb[1]) < a_len + 3 * CELL_M)):
                k += 1
            if k < n and (k < n - 1 or M.hypot(pts[k][0] - pb[0], pts[k][1] - pb[1]) > a_len):
                out.append((bx, by))
                fixed.add(len(out) - 1)
            i = k
        if out:
            fixed |= {0, len(out) - 1}
            out, fixed = self._edge_entry(out, fixed, start, cls, causeway, 0)
            out, fixed = self._edge_entry(out, fixed, end, cls, causeway, -1)
        return out, fixed

    def _edge_entry(self, out: list[tuple], fixed: set[int], p, cls: str, causeway: bool,
                    end: int):
        """A chain that starts (or ends) at a point on the map edge (an exit) enters the map
        square to the edge: a fixed straight of the class approach plus the tangent of the
        turn that follows, as at a bridge bank. Without it the first leg can run along the
        edge and the road hooks where it leaves the map."""
        ctx = self.ctx
        if p is None or len(out) < 2 or tuple(out[end]) != tuple(p):
            return out, fixed
        if ctx.canvas.exterior.distance(Point(p)) > 0.5:
            return out, fixed
        minx, miny, maxx, maxy = ctx.canvas.bounds
        sides = [(p[0] - minx, (1.0, 0.0)), (maxx - p[0], (-1.0, 0.0)),
                 (p[1] - miny, (0.0, 1.0)), (maxy - p[1], (0.0, -1.0))]
        u = min(sides, key=lambda t: t[0])[1]
        if not ctx.dry.contains(Point(p[0] + u[0] * 3.0, p[1] + u[1] * 3.0)):
            return out, fixed           # an exit on a bridge: the crossing sets the axis
        pts = out if end == 0 else out[::-1]
        fx = set(fixed) if end == 0 else {len(out) - 1 - f for f in fixed}
        toward = next((q for q in pts[1:] if M.hypot(q[0] - p[0], q[1] - p[1]) > 150.0),
                      pts[-1])
        L = self._approach(p, u, toward, cls, causeway)
        ax, ay = p[0] + u[0] * L, p[1] + u[1] * L
        k = 1
        while k < len(pts) - 1 and k not in fx and (
                M.hypot(pts[k][0] - p[0], pts[k][1] - p[1]) < L + CELL_M or
                (pts[k][0] - ax) * u[0] + (pts[k][1] - ay) * u[1] < 1.0):
            k += 1
        if M.hypot(pts[k][0] - p[0], pts[k][1] - p[1]) <= L + 1.0:
            return out, fixed           # the chain is shorter than the entry
        new = [pts[0], (ax, ay)] + pts[k:]
        nfx = {0, 1} | {f - k + 2 for f in fx if f >= k}
        if end == -1:
            new = new[::-1]
            nfx = {len(new) - 1 - f for f in nfx}
        return new, nfx

    def _approach(self, bank, u, toward, cls: str, causeway: bool) -> float:
        """Straight approach length from a bank point inland along u (the bridge axis): the
        class approach plus the tangent of the turn toward `toward`, capped where the axis
        meets water or a closed area."""
        c = CLASSES[cls]
        need = c["approach"]
        if toward is not None:
            v = _unit(toward[0] - bank[0], toward[1] - bank[1])
            cos = max(-1.0, min(1.0, u[0] * v[0] + u[1] * v[1]))
            th = float(M.acos(cos))
            need += 1.15 * c["r_min"] * M.tan(min(th, M.radians(120.0)) / 2)
        need = min(need, 280.0)
        ray = LineString([(bank[0] + u[0] * 2.0, bank[1] + u[1] * 2.0),
                          (bank[0] + u[0] * need, bank[1] + u[1] * need)])
        if not hasattr(self.ctx, "_wet_closed"):
            self.ctx._wet_closed = unary_union([self.ctx.wet, self.ctx.closed_all])
        stop = self.ctx.wet if causeway else self.ctx._wet_closed
        hit = ray.intersection(stop)
        if not hit.is_empty:
            t = min(ray.project(Point(q)) for q in shapely.get_coordinates(hit)) + 2.0
            need = max(min(need, t - 10.0), min(c["approach"], t - 5.0), 5.0)
        return need

    def simplify(self, pts: list[tuple], fixed: set[int], tol: float):
        """Douglas-Peucker on the runs between fixed vertices (which all survive)."""
        if len(pts) < 3 or tol <= 0:
            return list(pts), set(fixed) | {0, len(pts) - 1}
        keep = sorted(set(fixed) | {0, len(pts) - 1})
        out: list[tuple] = [tuple(pts[0])]
        new_fixed = {0}
        for a, b in zip(keep, keep[1:]):
            run = pts[a:b + 1]
            s = list(LineString(run).simplify(tol, preserve_topology=False).coords) \
                if len(run) > 2 else run
            out += [tuple(p) for p in s[1:]]
            new_fixed.add(len(out) - 1)
        return out, new_fixed

    def valid_shortcut(self, p, q, old: list[tuple], causeway: bool) -> bool:
        ctx = self.ctx
        seg = LineString([p, q])
        closed = ctx.closed if causeway else ctx.closed_all
        if closed is not None and not closed.is_empty and seg.intersects(closed):
            return False
        if not ctx.canvas_inner.contains(seg) and not (ctx.canvas.contains(seg)):
            return False
        wet_new = seg.intersection(ctx.wet).length
        wet_old = LineString(old).intersection(ctx.wet).length
        return wet_new <= wet_old + 2.0

    def fillet(self, pts: list[tuple], fixed: set[int], cls: str, closed_ring: bool = False,
               causeway: bool = False) -> tuple[LineString, float]:
        """Arcs at every corner. Returns the line and the smallest radius used."""
        # aim a little above the class minimum: arcs are polylines, measured on chords
        r_pref, r_min = CLASSES[cls]["r_pref"], 1.06 * CLASSES[cls]["r_min"]
        pts = [tuple(p) for p in pts]
        fixed = set(fixed)
        if closed_ring and pts[0] == pts[-1]:
            pts = pts[:-1]
        for _ in range(400):
            n = len(pts)
            if n < 3:
                break
            radii, tans = _fillet_radii(pts, r_pref, closed_ring, r_min)
            bad = [i for i in range(n) if radii[i] is not None and radii[i] < r_min - 1e-6
                   and (closed_ring or 0 < i < n - 1)]
            if not bad:
                break
            changed = False
            for i in sorted(bad, key=lambda k: (radii[k], k)):
                for k in (i, i - 1, i + 1, i - 2, i + 2):
                    if not closed_ring and (k <= 0 or k >= n - 1):
                        continue
                    k %= n
                    if k in fixed or n <= 3:
                        continue
                    prv, nxt = pts[(k - 1) % n], pts[(k + 1) % n]
                    if self.valid_shortcut(prv, nxt, [prv, pts[k], nxt], causeway):
                        del pts[k]
                        fixed = {f - 1 if f > k else f for f in fixed}
                        changed = True
                        break
                if changed:
                    break
            if not changed:
                break
        radii, tans = _fillet_radii(pts, r_pref, closed_ring, r_min)
        line = _arc_line(pts, radii, tans, closed_ring)
        used = [r for r in radii if r is not None]
        return line, (min(used) if used else math.inf)


def _new_runs(path: list[int], on, near=None) -> list[list[int]]:
    """Stretches of a path off the network, each with the network cell it starts or ends on.
    A short stretch that leaves the network and rejoins it while staying next to it (`near`:
    the network widened by two cells) is a shadow of an existing road and is dropped."""
    runs, cur = [], []
    for k in path:
        if on[k]:
            if cur:
                runs.append(cur + [k])
            cur = [k]
        else:
            cur.append(k)
    if len(cur) > 1:
        runs.append(cur)
    out = []
    for r in runs:
        if all(on[k] for k in r):
            continue
        if near is not None and on[r[0]] and on[r[-1]] and len(r) <= 12 and \
                all(near[k] for k in r):
            continue
        out.append(r)
    return out


def G_lines(g) -> list[LineString]:
    if g is None or g.is_empty:
        return []
    if isinstance(g, LineString):
        return [g]
    out = []
    for x in getattr(g, "geoms", []):
        out += G_lines(x)
    return out


def _turn(a, b, c) -> float:
    """Deflection angle at b (radians, 0 = straight)."""
    ux, uy = b[0] - a[0], b[1] - a[1]
    vx, vy = c[0] - b[0], c[1] - b[1]
    nu, nv = M.hypot(ux, uy), M.hypot(vx, vy)
    if nu < 1e-9 or nv < 1e-9:
        return 0.0
    cos = (ux * vx + uy * vy) / (nu * nv)
    return float(M.acos(max(-1.0, min(1.0, cos))))


def _fillet_radii(pts, r_pref: float, closed_ring: bool, r_min: float = 0.0):
    n = len(pts)
    th = [0.0] * n
    rng = range(n) if closed_ring else range(1, n - 1)
    for i in rng:
        th[i] = _turn(pts[i - 1], pts[i], pts[(i + 1) % n])
    th = [t if t > M.radians(0.5) else 0.0 for t in th]
    ht = [M.tan(t / 2) if t else 0.0 for t in th]
    want = [r_pref * h for h in ht]
    seglen = [M.hypot(pts[(i + 1) % n][0] - pts[i][0], pts[(i + 1) % n][1] - pts[i][1])
              for i in range(n)]
    low = [r_min * h for h in ht]
    tans = list(want)
    nseg = n if closed_ring else n - 1
    for s in range(nseg):
        a, b = s, (s + 1) % n
        L = seglen[s]
        if want[a] + want[b] <= L:
            continue
        if low[a] + low[b] <= L:
            # each corner gets its minimum-radius tangent, the rest is shared by demand
            extra = (L - low[a] - low[b])
            ea, eb = want[a] - low[a], want[b] - low[b]
            tot = ea + eb
            ta = low[a] + (extra * ea / tot if tot > 0 else 0.0)
            tb = low[b] + (extra * eb / tot if tot > 0 else 0.0)
        else:
            f = L / (want[a] + want[b])
            ta, tb = want[a] * f, want[b] * f
        tans[a] = min(tans[a], ta)
        tans[b] = min(tans[b], tb)
    radii = [tans[i] / ht[i] if ht[i] else None for i in range(n)]
    return radii, tans


def _arc_line(pts, radii, tans, closed_ring: bool) -> LineString:
    n = len(pts)
    out: list[tuple] = []
    idx = range(n) if closed_ring else range(n)
    for i in idx:
        p = pts[i]
        r = radii[i]
        if r is None or (not closed_ring and (i == 0 or i == n - 1)):
            out.append(p)
            continue
        a, c = pts[i - 1], pts[(i + 1) % n]
        t = tans[i]
        ua = _unit(p[0] - a[0], p[1] - a[1])
        uc = _unit(c[0] - p[0], c[1] - p[1])
        t0 = (p[0] - ua[0] * t, p[1] - ua[1] * t)
        t1 = (p[0] + uc[0] * t, p[1] + uc[1] * t)
        cross = ua[0] * uc[1] - ua[1] * uc[0]
        side = 1.0 if cross > 0 else -1.0
        nx, ny = -ua[1] * side, ua[0] * side
        cx, cy = t0[0] + nx * r, t0[1] + ny * r
        a0 = M.atan2(t0[1] - cy, t0[0] - cx)
        th = _turn(a, p, c)
        steps = max(int(math.ceil(max(M.degrees(th) / 6.0, r * th / 12.0))), 1)
        for k in range(steps + 1):
            ang = a0 + side * th * k / steps
            out.append((cx + r * M.cos(ang), cy + r * M.sin(ang)))
        out[-steps - 1] = t0
        out[-1] = t1
    if closed_ring:
        out.append(out[0])
    clean = [out[0]]
    for p in out[1:]:
        if M.hypot(p[0] - clean[-1][0], p[1] - clean[-1][1]) > 0.05:
            clean.append(p)
    return LineString(clean) if len(clean) > 1 else LineString()


def _unit(x, y):
    n = M.hypot(x, y)
    return (x / n, y / n) if n > 1e-12 else (1.0, 0.0)


# ---------------------------------------------------------------------------
# Context
# ---------------------------------------------------------------------------

# Road variants: (ring radius as a share of the mainland radius, ring sector rotation in
# degrees, highway shore cost). Variant 0 is the default; the build tries the next one only
# when the roads of the previous one fail a check.
ROAD_VARIANTS = [(0.62, 0.0, 2.0), (0.55, 15.0, 3.0), (0.70, -10.0, 1.5), (0.50, 7.5, 2.5)]


class Ctx:
    def __init__(self, spec: CitySpec, h, polygons: dict, district_ids: dict, waterways,
                 sites, open_polys: list, variant: int = 0, terrain=None):
        self.spec = spec
        self.variant = variant
        self.ring_share, self.ring_rot, self.shore = ROAD_VARIANTS[variant % len(ROAD_VARIANTS)]
        self.h = h
        self.canvas = h.canvas
        self.canvas_inner = h.canvas.buffer(-EDGE_KEEP_M)
        self.polygons = polygons
        self.did = district_ids
        self.sites = sites
        waters: list[Water] = []
        sea = G.polygonal(h.sea.intersection(h.water))
        if not sea.is_empty:
            waters.append(Water("sea", SEA, "sea", spec.water.coast.name, sea))
        for b in h.bodies:
            cls = {"river": RIVER, "delta_branch": RIVER, "sea_channel": SEA,
                   "separation": CANAL}[b.kind]
            poly = G.polygonal(b.polygon.intersection(h.water))
            parent = h.body(b.parent_id) if b.parent_id else None
            if not poly.is_empty:
                waters.append(Water(b.id, cls, b.kind, b.name, poly,
                                    parent.name if parent is not None else b.name))
        rest = G.polygonal(h.water.difference(unary_union([w.polygon for w in waters])))
        for k, part in enumerate(G.parts(rest)):
            if part.area < 50.0:
                continue
            near = min(waters, key=lambda w: (w.polygon.distance(part), w.id)) if waters \
                else None
            waters.append(Water(near.id if near else f"water{k}", near.cls if near else RIVER,
                                near.kind if near else "river", near.name if near else None,
                                part))
        for w in waterways.items:
            cls = SEA if w.kind == "basin" else CANAL
            waters.append(Water(w.id, cls, w.kind, w.name, w.polygon))
        self.waters = waters
        self.wet = unary_union([w.polygon for w in waters])
        self.dry = G.polygonal(self.canvas.difference(self.wet))
        self.dry_boundary = self.dry.boundary
        self.dry_inner = self.dry.buffer(-1.0)
        shapely.prepare(self.dry_inner)
        site_polys = [s.polygon.buffer(12.0) for s in sites]
        cones = [s.flight_cone for s in sites if s.flight_cone is not None]
        self.site_zone = unary_union(site_polys) if site_polys else Polygon()
        from . import pinned as PN

        # a pinned island has its traced roads only: routing stays off it
        self.pins = PN.placed_islands(spec, h)
        pin_land = [Polygon(pn.land.exterior) for pn, _ in
                    (self.pins[k] for k in sorted(self.pins))]
        self.pin_land = unary_union(pin_land) if pin_land else Polygon()
        closed = site_polys + cones + pin_land
        self.closed = unary_union(closed) if closed else Polygon()
        self.marsh_parks = unary_union(open_polys) if open_polys else Polygon()
        self.closed_all = unary_union([self.closed, self.marsh_parks])
        shapely.prepare(self.closed_all)
        shapely.prepare(self.wet)
        self.district_land = unary_union(list(polygons.values()))
        quays = unary_union([q.line for q in waterways.quays]) if waterways.quays else None
        self.grid = Grid(self.canvas, waters, self.closed, quays, self.district_land,
                         self.marsh_parks)
        if terrain is not None:
            self.grid.slope_cost(terrain)
        self.fit = Fitter(self)
        self.roads: list[Road] = []
        self.named: list[NamedRoute] = []
        self.notes: list[str] = []
        self.exits: dict[str, tuple[float, float]] = {}
        self.exit_cells: dict[str, int] = {}

    # --- helpers --------------------------------------------------------------------

    def free_cells(self, region=None, causeway: bool = False, land_only: bool = True,
                   inset: float = 0.0) -> np.ndarray:
        g = self.grid
        ok = g.free(causeway)
        if land_only:
            ok &= g.wcls == 0
        if region is not None:
            reg = region.buffer(-inset) if inset else region
            if reg.is_empty:
                reg = region
            ok &= shapely.contains_xy(reg, g.xs, g.ys)
        return np.nonzero(ok)[0]

    def nearest_cell(self, p, region=None, causeway: bool = False, mask=None) -> int | None:
        cells = self.free_cells(region, causeway)
        if mask is not None and mask[cells].any():
            cells = cells[mask[cells]]
        if len(cells) == 0:
            return None
        g = self.grid
        d = (g.xs[cells] - p[0]) ** 2 + (g.ys[cells] - p[1]) ** 2
        return int(cells[int(np.argmin(d))])

    def network_cells(self, highway_only: bool = False) -> set[int]:
        """Cells on roads (on land: routes join roads on land, never on a bridge)."""
        g = self.grid
        m = g.reuse_hw if highway_only else g.reuse
        return set(np.nonzero(m & g.free() & (g.wcls == 0))[0].tolist())

    def network_line(self, highway_only: bool = False):
        ls = [r.line for r in self.roads if not highway_only or r.cls == "highway"]
        return unary_union(ls) if ls else LineString()

    # --- adding roads -----------------------------------------------------------------

    def route(self, sources: list[int], targets: set[int], cls: str, role: str,
              name: str | None = None, reuse: str | None = "all", start=None, end=None,
              causeway: bool = False, district: str | None = None,
              closed_ring: bool = False, block=None) -> LineString | None:
        """Route, keep only the parts off the existing network, fit and add them. Returns the
        full routed polyline (for naming), or None."""
        g = self.grid
        path = g.search(sources, targets, reuse=reuse, causeway=causeway, block=block)
        if path is None or len(path) < 2:
            return None
        full = LineString([g.xy(k) for k in path]) if len(path) > 1 else None
        on = (g.reuse_hw if reuse == "highway" else g.reuse) if reuse else None
        runs = _new_runs(path, on, g.near(reuse == "highway")) if on is not None else [path]
        for run in runs:
            s = start if run[0] == path[0] else None
            e = end if run[-1] == path[-1] else None
            self.add_path(run, cls, role, name, s, e, causeway, district,
                          closed_ring and run is path)
        return full

    def add_path(self, run: list[int], cls: str, role: str, name, start, end, causeway,
                 district, closed_ring: bool = False) -> Road | None:
        if len(run) < 2:
            return None
        pts, fixed = self.fit.path_chain(self.grid, run, start, end, causeway, cls)
        if len(pts) < 2:
            return None
        return self.commit(pts, fixed, cls, role, name, causeway, district, closed_ring)

    def commit(self, pts: list[tuple], fixed: set[int], cls: str, role: str, name=None,
               causeway: bool = False, district=None, closed_ring: bool = False,
               attach: float = 35.0, optional: bool | None = None,
               depth: int = 0) -> Road | None:
        """Join the ends of a raw chain to the network, fit it (simplify, fillets) and add
        it. A fit that cuts into a closed area or adds water is redone with a tighter
        simplification."""
        if optional is None:
            optional = role in OPTIONAL_ROLES
        pts = [tuple(p) for p in pts]
        fixed = set(fixed)
        if not closed_ring:
            pts, fixed = self._attach_chain(pts, fixed, attach)
        if len(pts) < 2 or LineString(pts).length < 5.0:
            return None
        chain = LineString(pts)
        chain_wet = chain.intersection(self.wet).length
        closed = self.closed if causeway else self.closed_all
        tol = CLASSES[cls]["dp"]
        line = None
        for attempt in range(4):
            sp, sf = self.fit.simplify(pts, fixed, tol)
            if closed_ring and sp[0] != sp[-1]:
                sp = sp + [sp[0]]
            line, _ = self.fit.fillet(sp, sf, cls, closed_ring, causeway)
            if line.is_empty:
                return None
            bad = (not closed.is_empty and line.intersection(closed).length > 0.5) or \
                line.intersection(self.wet).length > chain_wet + 5.0
            if not bad:
                break
            tol = tol / 2 if attempt < 2 else 0.0
        line = G.qline(line)
        if line.is_empty or line.length < 5.0:
            return None
        if optional:
            from .checks import min_radius

            base = 10.0 if cls == "avenue" else 20.0
            js = JUNCTION_SKIP_M[cls]
            rad, at = min_radius(line, base, js, js)
            if rad < 0.97 * CLASSES[cls]["r_min"]:
                if role in ("crossing", "connector") or depth >= 2:
                    return None
                # cut the tight spot out and add what is left on both sides
                first = None
                for a, b in ((0.0, at - 60.0), (at + 60.0, line.length)):
                    if b - a < 60.0:
                        continue
                    piece = shapely.ops.substring(line, a, b)
                    pts2 = list(piece.coords)
                    r2 = self.commit(pts2, {0, len(pts2) - 1}, cls, role, name, causeway,
                                     district, False, attach, optional=True, depth=depth + 1)
                    first = first or r2
                return first
        road = Road(cls, line, role, name, district, causeway)
        self.roads.append(road)
        self.grid.mark(line, cls == "highway")
        return road

    def _attach_chain(self, pts: list[tuple], fixed: set[int], tol: float):
        """Ends within `tol` of a road move onto it (a T-junction, preferring an existing
        junction within 40 m); the junction point is inserted into that road."""
        if not self.roads:
            return pts, fixed
        exits = {G.qpoint(e) for e in self.exits.values()}
        for end in (0, -1):
            p = Point(pts[end])
            if G.qpoint(p) in exits:
                continue
            best = None
            for r in self.roads:
                d = r.line.distance(p)
                if d <= tol and (best is None or d < best[0] - 1e-9):
                    q0 = nearest_points(r.line, p)[0]
                    link = LineString([p, q0]) if d > 0.01 else None
                    if link is not None and (link.intersects(self.closed_all) or
                                             link.intersection(self.wet).length > 1.0):
                        continue
                    best = (d, r)
            if best is None:
                continue
            r = best[1]
            q = self._snap_to_junction(r, nearest_points(r.line, p)[0])
            q = Point(G.qpoint(q))
            link = LineString([p, q]) if q.distance(p) > 0.01 else None
            if link is not None and (link.intersects(self.closed_all) or
                                     link.intersection(self.wet).length > 1.0):
                q = Point(G.qpoint(nearest_points(r.line, p)[0]))
            self._insert_vertex(r, q)
            if q.distance(p) < 0.01:
                continue
            # the old end becomes interior: free to move unless it is a bank or exit point
            free_old = self.dry_inner.contains(p)
            if end == 0:
                pts = [(q.x, q.y)] + pts
                fixed = {f + 1 for f in fixed} | {0}
                if free_old:
                    fixed.discard(1)
            else:
                pts = pts + [(q.x, q.y)]
                if free_old:
                    fixed.discard(len(pts) - 2)
                fixed = fixed | {len(pts) - 1}
        return pts, fixed

    def _snap_to_junction(self, road: Road, q: Point) -> Point:
        """Prefer an existing junction (another road's end on this road) within 40 m."""
        best = None
        for r in self.roads:
            if r is road:
                continue
            for c in (r.line.coords[0], r.line.coords[-1]):
                pc = Point(c)
                d = pc.distance(q)
                if d < 40.0 and road.line.distance(pc) < 0.05 and (best is None or d < best[0]):
                    best = (d, pc)
        return best[1] if best else q

    def _insert_vertex(self, road: Road, p: Point) -> None:
        p = Point(G.qpoint(p))
        line = road.line
        if any(abs(x - p.x) < 1e-9 and abs(y - p.y) < 1e-9 for x, y in line.coords):
            return
        d = line.project(p)
        coords = list(line.coords)
        acc = 0.0
        for i in range(len(coords) - 1):
            seg = M.hypot(coords[i + 1][0] - coords[i][0], coords[i + 1][1] - coords[i][1])
            if acc + seg >= d - 1e-9:
                coords.insert(i + 1, (p.x, p.y))
                break
            acc += seg
        road.line = LineString(coords)


# ---------------------------------------------------------------------------
# Exits and highways
# ---------------------------------------------------------------------------

def _resolve(spec: CitySpec, ctx: Ctx, ref: str):
    """Region (polygon) for a district, island, place or megasite name."""
    from .districts import resolve

    if ref.endswith("_exit"):
        return None
    for s in ctx.sites:
        if s.name == ref:
            return ctx.polygons.get(s.district)
    hit = resolve(spec, ref)
    if hit is None:
        return None
    if hit[0] == "island":
        isl = next((i for i in ctx.h.islands if i.name == hit[1]), None)
        return isl.polygon if isl is not None else None
    return ctx.polygons.get(hit[1])


def find_exits(spec: CitySpec, ctx: Ctx) -> None:
    canvas = ctx.canvas
    land = ctx.dry
    center = R.city_center(ctx.district_land)
    named_to = {}
    for nb in spec.water.bridges.named:
        for a, b in (nb.connects, nb.connects[::-1]):
            if b.endswith("_exit"):
                named_to[b[:-5]] = a
    for d in spec.highways.exits or []:
        side = R.edge_side(canvas, d)
        n = max(int(side.length / 10.0), 2)
        pts = [side.interpolate(k / n, normalized=True) for k in range(n + 1)]
        pts = [Point(G.qpoint(p)) for p in pts]
        cx0, cy0 = canvas.centroid.x, canvas.centroid.y

        def inward(p, by=3.0):
            ux, uy = _unit(cx0 - p.x, cy0 - p.y)
            return Point(p.x + ux * by, p.y + uy * by)

        ok = [p for p in pts if land.contains(inward(p)) and land.contains(inward(p, 60.0))
              and not ctx.closed_all.contains(inward(p))]
        # where the highway can enter square to the edge (150 m straight on dry, open land),
        # not squeezed beside a river mouth or a reserve
        nx, ny = -presets.DIRECTION_VECTORS[d][0], -presets.DIRECTION_VECTORS[d][1]
        room = [p for p in ok
                if land.covers(LineString([(p.x + nx * 3.0, p.y + ny * 3.0),
                                           (p.x + nx * 150.0, p.y + ny * 150.0)]))
                and not LineString([(p.x, p.y), (p.x + nx * 150.0, p.y + ny * 150.0)]
                                   ).intersects(ctx.closed_all)]
        ok = room or ok
        target = named_to.get(d)
        region = _resolve(spec, ctx, target) if target else None
        if region is not None:
            cand = ok + [p for p in pts if not land.contains(inward(p))]
            p = min(cand, key=lambda q: (round(q.distance(region), 2), q.x, q.y))
        elif ok:
            ux, uy = presets.DIRECTION_VECTORS[d]
            cx, cy = center
            # nearest land point on that edge to where the center projects on it
            proj = nearest_points(side, Point(cx + ux * 5000, cy + uy * 5000))[0]
            near_city = [q for q in ok if q.distance(ctx.district_land) < 600.0] or ok
            p = min(near_city, key=lambda q: (round(q.distance(proj) + 0.5 * q.distance(
                ctx.district_land), 2), q.x, q.y))
        else:
            p = min(pts, key=lambda q: (round(q.distance(ctx.district_land), 2), q.x, q.y))
            ctx.notes.append(f"exit '{d}': no land on that map edge; the exit leaves on a bridge")
        ctx.exits[d] = (p.x, p.y)
        ctx.exit_cells[d] = ctx.grid.idx((p.x, p.y))


def _principal_axis(cells_x, cells_y) -> tuple[float, float]:
    # math.fsum: correctly rounded sums, whatever summation order a numpy build would pick
    n = max(len(cells_x), 1)
    mx, my = math.fsum(cells_x.tolist()) / n, math.fsum(cells_y.tolist()) / n
    dx, dy = cells_x - mx, cells_y - my
    sxx, syy = math.fsum((dx * dx).tolist()), math.fsum((dy * dy).tolist())
    sxy = math.fsum((dx * dy).tolist())
    ang = 0.5 * M.atan2(2 * sxy, sxx - syy)
    return (M.cos(ang), M.sin(ang))


def _mainland(ctx: Ctx):
    """District land off the islands (offshore, nearshore): where rings and spines run."""
    isl = [i.polygon for i in ctx.h.islands
           if i.polygon is not None and i.setting in ("offshore", "nearshore")]
    land = ctx.district_land
    if isl:
        rest = land.difference(unary_union(isl).buffer(5.0))
        if rest.area > 0.4 * land.area:
            return G.polygonal(rest)
    return land


def _ring_waypoints(ctx: Ctx) -> list[tuple]:
    """Points on free mainland around the city center at about half its radius, one per
    30 degree sector (sectors without land are skipped)."""
    g = ctx.grid
    main = _mainland(ctx)
    cells = ctx.free_cells(main, inset=60.0)
    if len(cells) == 0:
        return []
    cx, cy = R.city_center(main)
    xs, ys = g.xs[cells], g.ys[cells]
    r = ctx.ring_share * math.sqrt(main.area / math.pi)
    ang = M.atan2(ys - cy, xs - cx)
    dist = M.hypot(xs - cx, ys - cy)
    out = []
    for k in range(12):
        a0 = -math.pi + k * math.pi / 6 + M.radians(ctx.ring_rot)
        if a0 >= math.pi:
            a0 -= 2 * math.pi
        sel = (ang >= a0) & (ang < a0 + math.pi / 6) & (dist > 0.6 * r) & (dist < 1.5 * r)
        if not sel.any():
            continue
        idx = np.nonzero(sel)[0]
        mid = a0 + math.pi / 12
        off = np.abs(dist[idx] - r) + 0.5 * r * np.abs(ang[idx] - mid)
        j = int(idx[int(np.argmin(off))])
        out.append((float(xs[j]), float(ys[j])))
    return out


def _waypoint_route(ctx: Ctx, pts: list[tuple], cls: str, role: str, name: str,
                    closed: bool = False, start_exit: str | None = None,
                    reuse: bool = True) -> None:
    """Route through snapped waypoints (consecutive legs). `reuse` False (M12): the route
    gets no discount on earlier highways, so it keeps to its own line and crosses them."""
    g = ctx.grid
    cells = []
    deep = g.deep()
    for p in pts:
        k = ctx.nearest_cell(p, ctx.district_land.buffer(400.0), mask=deep)
        if k is None:
            continue
        if M.hypot(g.xs[k] - p[0], g.ys[k] - p[1]) > 260.0 and len(pts) > 2:
            continue
        if not cells or cells[-1] != k:
            cells.append(k)
    if start_exit:
        ec = ctx.exit_cells[start_exit]
        # waypoints snapped next to the exit (the exit itself moved onto deep land) would make
        # a first leg along the map edge, a hook: the route starts at the exit cell instead
        ex, ey = ctx.exits[start_exit]
        while cells and M.hypot(g.xs[cells[0]] - ex, g.ys[cells[0]] - ey) < 200.0:
            cells = cells[1:]
        cells.insert(0, ec)
    if closed and len(cells) > 2:
        cells.append(cells[0])
    # Legs in turn: each runs to any free cell near the next waypoint (no hairpins at
    # waypoints) and the next starts where it ended; the last leg of a loop closes on the
    # first cell. A spine may reuse earlier highways (only new parts are added). Legs meet end
    # to end and are joined as one curve at assembly.
    free = ctx.free_cells(ctx.district_land.buffer(400.0))
    free = free[g.deep()[free]] if g.deep()[free].any() else free
    fx, fy = g.xs[free], g.ys[free]
    cur = cells[0]
    for i, b in enumerate(cells[1:]):
        last = i == len(cells) - 2
        if last and closed or (last and not closed):
            targets = {b}
        else:
            bx, by = g.xy(b)
            near = (fx - bx) ** 2 + (fy - by) ** 2 < 180.0 ** 2
            targets = set(free[near].tolist()) - {cur} or {b}
        start = ctx.exits[start_exit] if start_exit and i == 0 else None
        path = g.search([cur], targets, reuse=None if closed or not reuse else "highway",
                        heuristic=len(targets) == 1,
                        shore=ctx.shore if cls == "highway" else 1.0)
        if path is None or len(path) < 2:
            ctx.notes.append(f"{name}: no route between two waypoints")
            continue
        # a leg that runs into an earlier highway joins it there (the spine crosses the ring
        # rather than merging into it, which would need an interchange: M7)
        on = g.reuse_hw if not closed else None
        runs = _new_runs(path, on, g.near(True)) if on is not None else [path]
        for run in runs:
            s0 = start if run[0] == path[0] else None
            ctx.add_path(run, cls, role, name, s0, None, False, None)
        cur = path[-1]


def build_highways(spec: CitySpec, ctx: Ctx) -> None:
    hw = spec.highways
    pattern = hw.pattern
    g = ctx.grid
    city = ctx.district_land
    cells = ctx.free_cells(city)
    if len(cells) == 0:
        return
    cx, cy = R.city_center(city)
    exits = list(hw.exits or [])
    named_exit = {}
    for nb in spec.water.bridges.named:
        if nb.kind == "pedestrian":
            continue
        for a, b in (nb.connects, nb.connects[::-1]):
            if b.endswith("_exit") and b[:-5] in ctx.exits:
                named_exit[b[:-5]] = nb
    label = {"ring": "Ring", "spine": "Spine", "grid": "Grid", "radial": "Radial",
             "coastal": "Coastal"}
    # Exits reached over a named bridge come first: the bridge is the start of the highway.
    if pattern != "none":
        for d, nb in sorted(named_exit.items()):
            other = nb.connects[0] if nb.connects[1] == f"{d}_exit" else nb.connects[1]
            region = _resolve(spec, ctx, other)
            if region is None:
                continue
            targets = set(ctx.free_cells(region, inset=60.0).tolist())
            line = ctx.route([ctx.exit_cells[d]], targets, "highway", "exit",
                             name=f"{d.replace('_', ' ').title()} Exit", reuse=None,
                             start=ctx.exits[d], causeway="causeway" in nb.name.lower(),
                             block=_only_land(ctx, ctx.exits[d], region))
            if line is not None:
                ctx.named.append(NamedRoute(nb.name, nb.kind, line, (other, f"{d}_exit"),
                                            nb.crosses, "causeway" in nb.name.lower()))
    xs, ys = g.xs[cells], g.ys[cells]
    if pattern in ("ring", "ring_plus_spine"):
        wps = _ring_waypoints(ctx)
        if len(wps) >= 3:
            _waypoint_route(ctx, wps, "highway", "ring", f"{spec.name} Ring"[:60], closed=True)
    if pattern in ("spine", "ring_plus_spine"):
        if exits:
            e = ctx.exits[exits[0]]
            ux, uy = _unit(cx - e[0], cy - e[1])
            start_exit = exits[0] if exits[0] not in named_exit else None
            first = e
        else:
            ux, uy = _principal_axis(xs, ys)
            proj = (xs - cx) * ux + (ys - cy) * uy
            k = int(np.argmin(proj))
            first = (float(xs[k]), float(ys[k]))
            start_exit = None
        proj = (xs - cx) * ux + (ys - cy) * uy
        side = np.abs((xs - cx) * -uy + (ys - cy) * ux)
        score = proj - 0.6 * side
        k = int(np.argmax(score))
        far = (float(xs[k]) - ux * 120.0, float(ys[k]) - uy * 120.0)
        # stop short of a closed area (a megasite gate) on the axis
        reach = M.hypot(far[0] - cx, far[1] - cy)
        ray = LineString([(cx, cy), (cx + ux * reach, cy + uy * reach)])
        hit = ray.intersection(ctx.closed_all) if not ctx.closed_all.is_empty else ray.intersection(
            Polygon())
        if not hit.is_empty:
            t = min(ray.project(Point(c)) for c in shapely.get_coordinates(hit))
            if t > 200.0:
                far = (cx + ux * (t - 90.0), cy + uy * (t - 90.0))
        wps = [first]
        span = M.hypot(cx - first[0], cy - first[1])
        steps = max(int(span / 700.0), 1)
        for s in range(1, steps):
            t = s / steps
            wps.append((first[0] + (cx - first[0]) * t, first[1] + (cy - first[1]) * t))
        wps.append((cx, cy))
        span2 = M.hypot(far[0] - cx, far[1] - cy)
        steps2 = max(int(span2 / 700.0), 1)
        for s in range(1, steps2 + 1):
            t = s / steps2
            wps.append((cx + (far[0] - cx) * t, cy + (far[1] - cy) * t))
        if start_exit is None and exits and exits[0] in named_exit:
            wps = wps[1:]
        _waypoint_route(ctx, wps, "highway", "spine", f"{spec.name} Spine"[:60],
                        start_exit=start_exit)
    if pattern == "grid":
        ux, uy = _principal_axis(xs, ys)
        for k, (ax, ay) in enumerate(((ux, uy), (-uy, ux))):
            nxv, nyv = -ay, ax
            off = (xs - cx) * nxv + (ys - cy) * nyv
            lo, hi = float(off.min()), float(off.max())
            count = max(int((hi - lo) / 1100.0), 1)
            for j in range(count):
                o = lo + (hi - lo) * (j + 0.5) / count
                along = (xs - cx) * ax + (ys - cy) * ay
                band = np.abs(off - o) < 40.0
                if band.sum() < 4:
                    continue
                a0, a1 = float(along[band].min()), float(along[band].max())
                if a1 - a0 < 800.0:
                    continue
                m = max(int((a1 - a0) / 450.0), 1)
                wps = [(cx + ax * (a0 + (a1 - a0) * t / m) + nxv * o,
                        cy + ay * (a0 + (a1 - a0) * t / m) + nyv * o) for t in range(m + 1)]
                _waypoint_route(ctx, wps, "highway", "grid", f"{spec.name} Grid {k + 1}{j + 1}")
    if pattern == "radial":
        hub = (cx, cy)
        dirs = []
        for d in exits:
            e = ctx.exits[d]
            dirs.append(M.atan2(e[1] - cy, e[0] - cx))
            if d not in named_exit:
                _waypoint_route(ctx, [e, hub], "highway", "radial",
                                f"{spec.name} {d.replace('_', ' ').title()} Radial",
                                start_exit=d)
        ang = M.atan2(ys - cy, xs - cx)
        dist = M.hypot(xs - cx, ys - cy)
        while len(dirs) < 4:
            best = None
            for k in np.argsort(-dist)[:400]:
                a = float(ang[k])
                gap = min((abs((a - d + math.pi) % (2 * math.pi) - math.pi) for d in dirs),
                          default=math.pi)
                if gap >= M.radians(70) and (best is None or dist[k] > best[0]):
                    best = (float(dist[k]), int(k), a)
            if best is None:
                break
            _, k, a = best
            dirs.append(a)
            _waypoint_route(ctx, [hub, (float(xs[k]), float(ys[k]))], "highway", "radial",
                            f"{spec.name} Radial {len(dirs)}")
    if pattern == "coastal":
        coast = ctx.h.coastline
        near = [ln for ln in G_lines(shapely.line_merge(coast)) if ln.distance(city) < 100]
        if near:
            ln = max(near, key=lambda x: (round(x.length, 2), x.coords[0]))
            seg = ln.intersection(city.buffer(300.0))
            pieces = G_lines(seg)
            if pieces:
                ln = max(pieces, key=lambda x: (round(x.length, 2), x.coords[0]))
                n = max(int(ln.length / 300.0), 2)
                wps = []
                for k in range(n + 1):
                    p = ln.interpolate(k / n, normalized=True)
                    d = ln.project(p)
                    a = ln.interpolate(max(d - 20, 0))
                    b = ln.interpolate(min(d + 20, ln.length))
                    tx, ty = _unit(b.x - a.x, b.y - a.y)
                    for sgn in (1, -1):
                        q = (p.x - ty * 180 * sgn, p.y + tx * 180 * sgn)
                        if ctx.dry.contains(Point(q)):
                            wps.append(q)
                            break
                _waypoint_route(ctx, wps, "highway", "coastal", f"{spec.name} Coastal Highway")
    # Named highway routes through their stops.
    for nh in hw.named:
        stops = []
        for ref in nh.route:
            if ref.endswith("_exit") and ref[:-5] in ctx.exits:
                stops.append(ctx.exits[ref[:-5]])
                continue
            reg = _resolve(spec, ctx, ref)
            if reg is not None:
                p = reg.representative_point()
                stops.append((p.x, p.y))
        if len(stops) >= 2:
            _waypoint_route(ctx, stops, "highway", "named", nh.name, reuse=nh.reuse)
            for r in ctx.roads:
                if r.role == "named" and r.name is None:
                    r.name = nh.name
    # Remaining exits join the nearest highway (or wait for the arterials).
    for d in exits:
        if d in named_exit:
            continue
        hw_cells = ctx.network_cells(highway_only=True)
        e_cell = ctx.exit_cells[d]
        if e_cell in hw_cells:
            continue
        cls = "highway" if pattern != "none" else "avenue"
        if not hw_cells:
            if pattern == "none":
                continue
            hw_cells = set(ctx.free_cells(city, inset=150.0).tolist())
        if _exit_stub(ctx, d):
            continue
        ctx.route([e_cell], hw_cells, cls, "exit",
                  name=f"{d.replace('_', ' ').title()} Exit", reuse="highway",
                  start=ctx.exits[d])


def _exit_stub(ctx: Ctx, d: str, max_len: float = 900.0) -> bool:
    """Move the exit to where a highway comes closest to that map edge and join them with a
    straight stub square to the edge (no curve needed). False when no clear stub exists."""
    side = R.edge_side(ctx.canvas, d)
    hw = [r.line for r in ctx.roads if r.cls == "highway"]
    if not hw:
        return False
    ux, uy = presets.DIRECTION_VECTORS[d]
    if abs(ux) > 1e-9 and abs(uy) > 1e-9:
        return False  # diagonal edges: route as usual
    best = None
    for ln in hw:
        for p in G.resample(ln, 20.0):
            q = nearest_points(side, Point(p))[0]
            stub = LineString([tuple(p), (q.x, q.y)])
            if stub.length < CLASSES["highway"]["min_len"] or stub.length > max_len:
                continue
            if best is not None and stub.length >= best[0]:
                continue
            if stub.intersects(ctx.closed_all) or stub.intersection(ctx.wet).length > 0.5:
                continue
            inner = Point(q.x - ux * 3.0, q.y - uy * 3.0)
            if not ctx.dry.contains(inner):
                continue
            # the stub must not run along or across other roads
            others = [r.line for r in ctx.roads if r.line.distance(Point(p)) > 1.0]
            if any(stub.crosses(o) for o in others):
                continue
            best = (stub.length, (q.x, q.y), tuple(p))
    if best is None:
        return False
    _, e, h = best
    ctx.exits[d] = G.qpoint(e)
    ctx.exit_cells[d] = ctx.grid.idx(e)
    ctx.commit([ctx.exits[d], h], {0, 1}, "highway", "exit",
               f"{d.replace('_', ' ').title()} Exit", attach=5.0)
    return True


# ---------------------------------------------------------------------------
# Arterials
# ---------------------------------------------------------------------------

def _longest(geom) -> LineString | None:
    ls = G_lines(geom)
    if not ls:
        return None
    return max(ls, key=lambda x: (round(x.length, 2), x.coords[0]))


def _clip_free(ctx: Ctx, line, keep_edge: bool = False) -> list[LineString]:
    """Parts of a line outside closed areas (with a margin) and away from the map edge."""
    if line is None or line.is_empty:
        return []
    g = line.difference(ctx.closed_all.buffer(30.0)) if not ctx.closed_all.is_empty else line
    if not keep_edge:
        g = g.intersection(ctx.canvas_inner)
    return [x for x in G_lines(shapely.line_merge(g) if not g.is_empty else g)
            if x.length > 40.0]


def _merge_into(ctx: Ctx, line: LineString, role: str, name=None, district=None,
                gap: float = 28.0, min_dup: float = 70.0, cls: str = "avenue") -> int:
    """Add a raw line, minus stretches running along existing roads (within `gap` for more
    than `min_dup` meters). Returns the number of pieces added."""
    closed_ring = line.is_ring and line.length > 200.0
    net = ctx.network_line()
    pieces = [line]
    if not net.is_empty:
        near = line.intersection(net.buffer(gap))
        dup = [x for x in G_lines(shapely.line_merge(near) if not near.is_empty else near)
               if x.length > min_dup]
        if dup:
            closed_ring = False
            cut = unary_union([x.buffer(0.5) for x in dup])
            rest = line.difference(cut)
            pieces = G_lines(shapely.line_merge(rest) if not rest.is_empty else rest)
    added = 0
    for p in pieces:
        if p.length < 40.0:
            continue
        pts = list(p.coords)
        ring = closed_ring and pts[0] == pts[-1]
        if ctx.commit(pts, set() if ring else {0, len(pts) - 1}, cls, role, name,
                      district=district, closed_ring=ring, attach=gap + 12.0) is not None:
            added += 1
    return added


def build_arterials(spec: CitySpec, ctx: Ctx) -> None:
    h = ctx.h
    did = ctx.did
    # 1. Axis boulevards and ring roads (district patterns).
    for d in spec.districts:
        poly = ctx.polygons.get(d.name)
        if poly is None:
            continue
        sites = [s for s in ctx.sites if s.district == d.name]
        if d.street_pattern == "rotated_grid" or d.archetype == "corporate_core":
            ang = M.radians(d.grid_angle_deg or 0.0)
            c = poly.representative_point()
            best = None
            for a in (ang, ang + math.pi / 2):
                ux, uy = M.cos(a), M.sin(a)
                ln = LineString([(c.x - ux * 5000, c.y - uy * 5000),
                                 (c.x + ux * 5000, c.y + uy * 5000)])
                piece = _longest(ln.intersection(poly))
                if piece is not None and (best is None or piece.length > best.length + 1e-6):
                    best = piece
            for piece in _clip_free(ctx, best):
                if piece.length > 250.0:
                    _merge_into(ctx, piece, "axis_boulevard", f"{d.name} Boulevard"[:60],
                                d.name)
        if d.street_pattern in ("radial_ring", "grid_ring_park") or d.archetype in (
                "transit_hub", "midtown_mixed"):
            hub = next((s for s in sites if s.kind in ("transit_nexus", "central_park")), None)
            if hub is not None:
                ring = hub.polygon.buffer(45.0).buffer(60.0).buffer(-60.0).exterior
            else:
                c = poly.representative_point()
                r = min(max(0.45 * math.sqrt(poly.area / math.pi), 150.0), 330.0)
                ring = c.buffer(r, 32).exterior
            ring = LineString(ring.coords)
            inside = ring.intersection(poly.buffer(-20.0))
            if inside.length >= 0.75 * ring.length:
                for piece in _clip_free(ctx, LineString(ring.coords)):
                    _merge_into(ctx, piece, "ring_road", f"{d.name} Ring Road"[:60], d.name)
    # 2. Waterfront avenues: a setback line along major water on every district landmass.
    ports = unary_union([w.polygon for w in ctx.waters if w.kind in ("basin", "marina")])
    wet_major = unary_union([w.polygon for w in ctx.waters
                             if w.kind not in ("canal", "creek", "inlet", "basin", "marina")])
    for k, lm in enumerate(h.landmasses):
        if lm.intersection(ctx.district_land).area < 0.3 * lm.area:
            continue
        body = lm.difference(ports.buffer(5.0)) if not ports.is_empty else lm
        inset = G.polygonal(body.buffer(-WATERFRONT_SETBACK_M))
        for part in G.parts(inset):
            if part.area < 40_000:
                continue
            ring = LineString(part.exterior.coords)
            near = ring.intersection(wet_major.buffer(WATERFRONT_SETBACK_M + 15.0))
            whole = near.length > 0.97 * ring.length
            # a waterfront avenue runs along the shore and never crosses the water
            dry_ring = ring.difference(ctx.wet.buffer(8.0))
            if whole and dry_ring.length > 0.999 * ring.length:
                for piece in _clip_free(ctx, ring):
                    _merge_into(ctx, piece, "waterfront")
                continue
            near = near.difference(ctx.wet.buffer(8.0))
            for ln in G_lines(shapely.line_merge(near) if not near.is_empty else near):
                if ln.length < 200.0:
                    continue
                for piece in _clip_free(ctx, ln):
                    _merge_into(ctx, piece, "waterfront")
    # 3. Avenues on the land boundaries between districts.
    names = sorted(ctx.polygons)
    for i, a in enumerate(names):
        for b in names[i + 1:]:
            pa, pb = ctx.polygons[a], ctx.polygons[b]
            if pa.distance(pb) > 1.0:
                continue
            shared = pa.boundary.intersection(pb.buffer(1.5))
            for ln in G_lines(shapely.line_merge(shared) if not shared.is_empty else shared):
                if ln.length < 150.0:
                    continue
                for piece in _clip_free(ctx, ln):
                    _merge_into(ctx, piece, "boundary")
    # 4. Coverage chords at the district grid angle.
    g = ctx.grid
    for d in spec.districts:
        poly = ctx.polygons.get(d.name)
        if poly is None:
            continue
        spacing = SPACING_M.get(d.archetype, 450.0)
        cells = ctx.free_cells(poly, inset=20.0)
        if len(cells) == 0:
            continue
        pts = shapely.points(g.xs[cells], g.ys[cells])
        ang = M.radians(d.grid_angle_deg or 0.0)
        skip = np.zeros(len(cells), dtype=bool)  # spots no chord could serve
        for _ in range(10):
            net = ctx.network_line()
            dist = shapely.distance(net, pts) if not net.is_empty else np.full(len(cells), 1e9)
            far = (dist > 0.55 * spacing) & ~skip
            if far.sum() < max(3, 0.03 * len(cells)):
                break
            k = int(np.argmax(np.where(skip, -1.0, dist)))
            c = (float(g.xs[cells[k]]), float(g.ys[cells[k]]))
            options = []
            for a in (ang, ang + math.pi / 2):
                ux, uy = M.cos(a), M.sin(a)
                ln = LineString([(c[0] - ux * 5000, c[1] - uy * 5000),
                                 (c[0] + ux * 5000, c[1] + uy * 5000)])
                inside = ln.intersection(poly)
                piece = next((x for x in G_lines(inside) if x.distance(Point(c)) < 1.0), None)
                if piece is None:
                    continue
                gain = int((far & (shapely.distance(piece, pts) < 0.5 * spacing)).sum())
                if gain:
                    options.append((-gain, len(options), piece))
            added = 0
            for _, _, piece in sorted(options):
                # a chord may cross water briefly (a bridge), never run along it
                wet = piece.intersection(ctx.wet)
                long_wet = [w for w in G_lines(wet) if w.length > 60.0]
                if long_wet:
                    piece = piece.difference(unary_union([w.buffer(15.0) for w in long_wet]))
                for part in _clip_free(ctx, piece):
                    added += _merge_into(ctx, part, "chord", district=d.name)
                if added:
                    break
            if not added:
                # nothing could serve this spot: skip it and its surroundings
                skip |= shapely.distance(Point(c), pts) < 0.3 * spacing


def _landmass_of(ctx: Ctx, p) -> int | None:
    if not hasattr(ctx, "_lm_buf"):
        ctx._lm_buf = [lm.buffer(1.0) for lm in ctx.h.landmasses]
        for b in ctx._lm_buf:
            shapely.prepare(b)
    pt = Point(p)
    for k, lm in enumerate(ctx._lm_buf):
        if lm.contains(pt):
            return k
    return None


def _lms_on(ctx: Ctx, ln: LineString) -> set[int]:
    """Landmasses a road runs on (over 45 m of it on dry land), not those whose tip a bridge
    only clips."""
    out = set()
    dry = ln.difference(ctx.wet)
    for run in G_lines(shapely.line_merge(dry) if not dry.is_empty else dry):
        if run.length <= 45.0 and ln.length > 45.0:
            continue
        for p in G.resample(run, 60.0):
            k = _landmass_of(ctx, p)
            if k is not None:
                out.add(k)
    return out


def _district_landmasses(ctx: Ctx) -> set[int]:
    if not hasattr(ctx, "_dlm"):
        ctx._dlm = {k for k, lm in enumerate(ctx.h.landmasses)
                    if lm.intersection(ctx.district_land).area > 0.3 * lm.area}
    return set(ctx._dlm)


def build_named_bridges(spec: CitySpec, ctx: Ctx) -> list[dict]:
    """Road named bridges between two regions; pedestrian ones as plain bridge records."""
    peds = []
    for nb in spec.water.bridges.named:
        if any(c.endswith("_exit") for c in nb.connects):
            continue  # built with the highways
        ra = _resolve(spec, ctx, nb.connects[0])
        rb = _resolve(spec, ctx, nb.connects[1])
        if ra is None or rb is None:
            ctx.notes.append(f"named bridge '{nb.name}': cannot place its ends")
            continue
        causeway = "causeway" in nb.name.lower()
        if nb.kind == "pedestrian":
            peds.append({"name": nb.name, "kind": nb.kind, "ends": (ra, rb),
                         "crosses": nb.crosses})
            continue
        # already joined by a road bridge across the asked water? then name that one
        span = _existing_crossing(ctx, ra, rb, nb.crosses)
        if span is not None:
            ctx.named.append(NamedRoute(nb.name, nb.kind, span, tuple(nb.connects), nb.crosses,
                                        causeway))
            continue
        # ends on the regions' own land, not on a tip another bridge clips
        src = set(ctx.free_cells(ra, causeway=causeway, inset=40.0).tolist())
        dst = set(ctx.free_cells(rb, causeway=causeway, inset=40.0).tolist())
        if not src or not dst:
            ctx.notes.append(f"named bridge '{nb.name}': no free land at one end")
            continue
        g = ctx.grid
        path = g.search(sorted(src), dst, reuse=None, causeway=causeway,
                        block=_only_land(ctx, ra, rb))
        if path is None:
            ctx.notes.append(f"named bridge '{nb.name}': no route")
            continue
        # keep only the stretch from the last cell in A to the first cell in B
        ina = [i for i, k in enumerate(path) if k in src]
        inb = [i for i, k in enumerate(path) if k in dst]
        i0 = max(ina) if ina else 0
        i1 = min(i for i in inb if i >= i0) if inb else len(path) - 1
        run = path[i0:i1 + 1]
        # reach into the network on both sides
        pre = _to_network(ctx, run[0], causeway)
        post = _to_network(ctx, run[-1], causeway)
        full = (pre[::-1][:-1] if pre else []) + run + (post[1:] if post else [])
        line = LineString([g.xy(k) for k in run])
        ctx.named.append(NamedRoute(nb.name, nb.kind, line, tuple(nb.connects), nb.crosses,
                                    causeway))
        # (a road it only crosses out on the water does not split it: no junction there)
        for r in _new_runs(full, g.reuse & (g.wcls == 0)):
            ctx.add_path(r, "avenue", "named_bridge", None, None, None, causeway, None)
    return peds


def _only_land(ctx: Ctx, *regions) -> np.ndarray:
    """Block mask: every land cell outside the landmasses that hold the given points or
    regions (a named bridge crosses straight from one end to the other)."""
    g = ctx.grid
    keep = []
    for reg in regions:
        geom = reg if hasattr(reg, "geom_type") else Point(reg)
        for lm in ctx.h.landmasses:
            if lm.distance(geom) < 30.0 or (geom.geom_type != "Point" and
                                             lm.intersection(geom).area > 0.0):
                keep.append(lm)
    allowed = unary_union(keep) if keep else Polygon()
    on = shapely.contains_xy(allowed.buffer(CELL_M), g.xs, g.ys) if not allowed.is_empty \
        else np.zeros(len(g.xs), bool)
    return (g.wcls == 0) & ~on


def _water_matches(ctx: Ctx, p: Point, crosses: str | None) -> bool:
    if not crosses:
        return True
    for w in ctx.waters:
        if w.polygon.distance(p) < 1.0:
            if crosses in ("sea", "bay"):
                if w.kind in ("sea", "basin"):
                    return True
            elif crosses in (w.name, w.river):
                return True
    return False


def _existing_crossing(ctx: Ctx, ra, rb, crosses: str | None) -> LineString | None:
    """A bridge span already on the network that joins region A and region B over the asked
    water (the longest such span)."""
    za, zb = ra.buffer(80.0), rb.buffer(80.0)
    best = None
    for r in ctx.roads:
        wet = r.line.intersection(ctx.wet)
        dry = r.line.difference(ctx.wet)
        dry_runs = G_lines(shapely.line_merge(dry) if not dry.is_empty else dry)
        ends = [Point(r.line.coords[0]), Point(r.line.coords[-1])]

        def lands(e):
            # the road goes on over the land at this bank (not over a tip it clips)
            # (every land run at the bank, so the order of GEOS's parts does not matter)
            return any(x.distance(e) < 1.0 and (x.length > 45.0 or
                                                any(x.distance(q) < 1.0 for q in ends))
                       for x in dry_runs)

        for piece in G_lines(shapely.line_merge(wet) if not wet.is_empty else wet):
            if piece.length < 3.0:
                continue
            e0, e1 = Point(piece.coords[0]), Point(piece.coords[-1])
            if not ((za.contains(e0) and zb.contains(e1)) or (za.contains(e1) and zb.contains(e0))):
                continue
            if not (lands(e0) and lands(e1)):
                continue
            if not _water_matches(ctx, piece.interpolate(0.5, normalized=True), crosses):
                continue
            if best is None or piece.length > best.length:
                best = piece
    return best


def _to_network(ctx: Ctx, cell: int, causeway: bool) -> list[int] | None:
    net = ctx.network_cells()
    if not net or cell in net:
        return [cell]
    g = ctx.grid
    lm = _landmass_of(ctx, g.xy(cell))
    if lm is not None:
        region = ctx.h.landmasses[lm].buffer(10.0)
        ks = np.array(sorted(net))
        inside = shapely.contains_xy(region, g.xs[ks], g.ys[ks])
        net_lm = set(ks[inside].tolist())
        if net_lm:
            net = net_lm
    return g.search([cell], net, reuse=None, causeway=causeway, heuristic=False)


def _shortest_crossing(ctx: Ctx, ra, rb, avoid=None, gap: float = 150.0) -> LineString | None:
    """Shortest straight line from region A to region B over water only, at least `gap` from
    `avoid` (the road bridges)."""
    best = None
    others = ctx.dry_inner.difference(ra.buffer(2.0)).difference(rb.buffer(2.0))
    for p in _samples(ra.exterior if hasattr(ra, "exterior") else ra.boundary, 15.0):
        q = nearest_points(rb, p)[0]
        ln = LineString([p, q])
        if ln.length < 1.0:
            continue
        if ln.intersects(others):
            continue
        if avoid is not None and not avoid.is_empty and ln.distance(avoid) < gap:
            continue
        if best is None or ln.length < best.length - 1e-6:
            best = ln
    return G.qline(best) if best is not None else None


def place_footbridges(ctx: Ctx, peds: list[dict]) -> list[dict]:
    spans = []
    for r in ctx.roads:
        wet = r.line.intersection(ctx.wet)
        spans += [x for x in G_lines(wet) if x.length > 3.0]
    avoid = unary_union(spans) if spans else None
    out = []
    for p in peds:
        ra, rb = p["ends"]
        line = None
        for gap in (150.0, 100.0, 60.0):
            line = _shortest_crossing(ctx, ra, rb, avoid, gap)
            if line is not None:
                break
        if line is None:
            line = _shortest_crossing(ctx, ra, rb)
            if line is not None:
                ctx.notes.append(f"named bridge '{p['name']}': only crossing is beside a road "
                                 "bridge")
        if line is None:
            ctx.notes.append(f"named bridge '{p['name']}': no crossing found")
            continue
        out.append({"name": p["name"], "kind": p["kind"], "line": line, "crosses": p["crosses"]})
    return out


def _samples(line, step: float) -> list[Point]:
    n = max(int(line.length / step), 1)
    return [line.interpolate(k / n, normalized=True) for k in range(n)]


def _road_groups(ctx: Ctx) -> list[tuple[set[int], set[int]]]:
    """Connected groups of roads: (road indices, landmass indices), largest first."""
    n = len(ctx.roads)
    parent = list(range(n))

    def find(a):
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a

    lines = [r.line for r in ctx.roads]
    tree = shapely.STRtree(lines)
    # roads that cross out on the water do not meet (the assembly grade-separates them)
    inner = ctx.wet.buffer(-3.0)
    for i, ln in enumerate(lines):
        for j in tree.query(ln.buffer(0.05)):
            j = int(j)
            if j > i and lines[j].distance(ln) < 0.05:
                meet = ln.buffer(0.05).intersection(lines[j].buffer(0.05))
                if not inner.covers(meet):
                    parent[find(i)] = find(j)
    groups: dict[int, set[int]] = {}
    for i in range(n):
        groups.setdefault(find(i), set()).add(i)
    out = []
    for g in groups.values():
        lms = set()
        for i in g:
            lms |= _lms_on(ctx, lines[i])
        out.append((g, lms))
    return sorted(out, key=lambda t: (-len(t[1] & _district_landmasses(ctx)), -len(t[0]),
                                      min(t[0])))


def _served_by(ctx: Ctx, idx) -> set[str]:
    """Districts with at least 60 m of avenue (within 25 m) among the roads `idx`."""
    avenues = [ctx.roads[i].line for i in idx if ctx.roads[i].cls == "avenue"]
    if not avenues:
        return set()
    u = unary_union(avenues)
    return {n for n, p in ctx.polygons.items() if u.intersection(p.buffer(25.0)).length >= 60.0}


def _cells_of(ctx: Ctx, roads: list[Road]) -> list[int]:
    g = ctx.grid
    free = g.free()
    out = []
    for r in roads:
        for x, y in G.resample(r.line, CELL_M / 2):
            k = g.idx((x, y))
            # (a traced road on its closed island counts: links start where it leaves)
            if (free[k] or r.pin is not None) and g.wcls[k] == 0:
                out.append(k)
    return sorted(set(out))


def connect_landmasses(spec: CitySpec, ctx: Ctx) -> None:
    """One road network: every landmass with a district joins the main group (by bridge where
    needed); other stray groups join when a link of up to 2 km exists, else they are
    dropped."""
    want = _district_landmasses(ctx)
    g = ctx.grid
    for _ in range(30):
        groups = _road_groups(ctx)
        if not groups:
            return
        main_roads, main_lms = groups[0]
        bare = sorted(want - set().union(*(lm for _, lm in groups)))
        if bare:  # a district landmass without any road yet
            k = bare[0]
            src = sorted(ctx.free_cells(ctx.h.landmasses[k], inset=30.0).tolist()) or \
                sorted(ctx.free_cells(ctx.h.landmasses[k]).tolist())
            dst = set(_cells_of(ctx, [ctx.roads[i] for i in main_roads]))
            path = g.search(src, dst, reuse=None, heuristic=False) if src and dst else None
            if path is None:
                ctx.notes.append(f"landmass lm{k + 1:02d}: cannot be connected")
                want.discard(k)
                continue
            ctx.add_path(path, "avenue", "connector", None, None, None, False, None)
            continue
        if len(groups) == 1:
            return
        roads, lms = groups[1]
        needed_lm = bool((lms & want) - main_lms)
        needed = needed_lm or bool(_served_by(ctx, roads) - _served_by(ctx, main_roads))
        src = _cells_of(ctx, [ctx.roads[i] for i in roads])
        dst = set(_cells_of(ctx, [ctx.roads[i] for i in main_roads]))
        path = g.search(src, dst, reuse=None, heuristic=False) if src and dst else None
        if path is not None and len(path) * CELL_M > 2000.0 and not needed:
            path = None
        if path is not None and not needed_lm and any(g.wcls[k] > 0 for k in path):
            path = None  # a group on a landmass already reached joins over land, or goes
        if path is not None:
            pts, fixed = ctx.fit.path_chain(g, path, cls="avenue")
            if ctx.commit(pts, fixed, "avenue", "connector", optional=False) is None:
                path = None
        if path is None:
            if needed_lm:
                ctx.notes.append("a road group on " + ", ".join(
                    f"lm{k + 1:02d}" for k in sorted(lms)) + " cannot be connected")
                want -= lms
            for i in sorted(roads, reverse=True):
                if ctx.roads[i].pin is None:      # traced roads stay
                    del ctx.roads[i]
            _remark(ctx)


def serve_districts(spec: CitySpec, ctx: Ctx) -> None:
    """A district without an avenue gets one: from its deepest free point to the network."""
    g = ctx.grid
    deep = g.deep()
    for d in spec.districts:
        poly = ctx.polygons.get(d.name)
        if poly is None:
            continue
        avenues = [r.line for r in ctx.roads if r.cls == "avenue"]
        near = unary_union(avenues).intersection(poly.buffer(25.0)).length if avenues else 0.0
        if near >= 60.0:
            continue
        cells = ctx.free_cells(poly, inset=40.0)
        if len(cells) == 0:
            cells = ctx.free_cells(poly)
        if len(cells) == 0:
            ctx.notes.append(f"'{d.name}': no free land for an avenue")
            continue
        if deep[cells].any():
            cells = cells[deep[cells]]
        c = poly.representative_point()
        k = int(cells[int(np.argmin((g.xs[cells] - c.x) ** 2 + (g.ys[cells] - c.y) ** 2))])
        dst = ctx.network_cells() - {k}
        path = g.search([k], dst, reuse=None, heuristic=False) if dst else None
        if path is None or len(path) < 2:
            ctx.notes.append(f"'{d.name}': no avenue could reach it")
            continue
        pts, fixed = ctx.fit.path_chain(g, path, cls="avenue")
        ctx.commit(pts, fixed, "avenue", "access", district=d.name, optional=False)


def _remark(ctx: Ctx) -> None:
    g = ctx.grid
    g.reuse[:] = False
    g.reuse_hw[:] = False
    for r in ctx.roads:
        g.mark(r.line, r.cls == "highway")


def close_highway_ends(ctx: Ctx) -> None:
    """A highway that ends short of an exit continues as an avenue to the nearest road."""
    exits = {G.qpoint(e) for e in ctx.exits.values()}
    for r in [x for x in ctx.roads if x.cls == "highway" and x.pin is None]:
        for c in (r.line.coords[0], r.line.coords[-1]):
            p = Point(c)
            if G.qpoint(c) in exits:
                continue
            if any(o is not r and o.line.distance(p) < 0.05 for o in ctx.roads):
                continue
            others = [o for o in ctx.roads if o is not r]
            dst = set(_cells_of(ctx, others))
            own = set(_cells_of(ctx, [r]))
            dst -= own
            start = ctx.nearest_cell(c)
            if start is None or not dst:
                continue
            path = ctx.grid.search([start], dst, reuse=None, heuristic=False)
            if path is not None and any(ctx.grid.wcls[k] > 0 for k in path):
                path = None  # a short link over land only
            if path is not None and len(path) * CELL_M < 600.0:
                pts, fixed = ctx.fit.path_chain(ctx.grid, path, (p.x, p.y), None, cls="avenue")
                ctx.commit(pts, fixed, "avenue", "connector", optional=False)


def extra_crossings(spec: CitySpec, ctx: Ctx) -> None:
    """More river and canal bridges by `water.bridges.density` (sea crossings stay few)."""
    density = spec.water.bridges.density
    if density <= 0:
        return
    lms = sorted(_district_landmasses(ctx))
    g = ctx.grid
    for w in ctx.waters:
        if w.cls not in BRIDGE_SPACING_M or w.kind in ("canal", "creek", "inlet", "marina"):
            continue
        banks = []
        for k in lms:
            lm = ctx.h.landmasses[k]
            fr = lm.boundary.intersection(w.polygon.buffer(2.0))
            if fr.length > 200.0:
                banks.append((k, fr))
        for i, (ka, fa) in enumerate(banks):
            for kb, fb in banks[i + 1:]:
                if fa.distance(fb) > 200.0:
                    continue
                shared = fa.intersection(fb.buffer(220.0))
                length = shared.length
                if length < 150.0:
                    continue
                want = max(1, int(round(density * length / BRIDGE_SPACING_M[w.cls])))
                have = _bridges_between(ctx, ka, kb)
                cand = _samples(_longest(shapely.line_merge(shared)) or LineString(), 40.0)
                existing = [p for p in have]
                for p in cand:
                    if len(existing) >= want:
                        break
                    if any(p.distance(e) < 0.8 * BRIDGE_SPACING_M[w.cls] for e in existing):
                        continue
                    q = nearest_points(fb, p)[0]
                    if q.distance(p) > 200.0:
                        continue
                    a_cell = g.idx((p.x, p.y))
                    b_cell = g.idx((q.x, q.y))
                    pa = _to_network(ctx, ctx.nearest_cell((p.x, p.y), ctx.h.landmasses[ka])
                                     or a_cell, False)
                    pb = _to_network(ctx, ctx.nearest_cell((q.x, q.y), ctx.h.landmasses[kb])
                                     or b_cell, False)
                    if not pa or not pb:
                        continue
                    if len(pa) * CELL_M > 350.0 or len(pb) * CELL_M > 350.0:
                        continue
                    crossing = g.search([pa[0]], {pb[0]}, reuse=None)
                    if crossing is None:
                        continue
                    if sum(1 for c in crossing if g.wcls[c] >= SEA) > 0:
                        continue
                    full = pa[::-1] + crossing[1:] + pb[1:]
                    for r in _new_runs(full, g.reuse):
                        ctx.add_path(r, "avenue", "crossing", None, None, None, False, None)
                    existing.append(p)


def _bridges_between(ctx: Ctx, ka: int, kb: int) -> list[Point]:
    a = ctx.h.landmasses[ka].buffer(5.0)
    b = ctx.h.landmasses[kb].buffer(5.0)
    out = []
    for r in ctx.roads:
        wet = r.line.intersection(ctx.wet)
        for piece in G_lines(wet):
            if piece.length < 3:
                continue
            e0, e1 = Point(piece.coords[0]), Point(piece.coords[-1])
            if (a.contains(e0) and b.contains(e1)) or (a.contains(e1) and b.contains(e0)):
                out.append(piece.interpolate(0.5, normalized=True))
    return out


# ---------------------------------------------------------------------------
# Assembly: nodes, segments, bridges
# ---------------------------------------------------------------------------

def clearance_for(cls: int, width: float) -> float:
    if cls == SEA:
        return CLEARANCE_M["sea"]
    lo, hi = CLEARANCE_M["river"] if cls == RIVER else CLEARANCE_M["canal"]
    if cls == RIVER:
        t = min(max((width - 40.0) / 110.0, 0.0), 1.0)
    else:
        t = 0.0 if width <= 20.0 else 1.0
    return G.q(lo + (hi - lo) * t)


def _cross_section(cls: str, role: str, pin: dict | None = None) -> dict:
    c = CLASSES[cls]
    lanes, median, side, width = c["lanes"], c["median"], c["sidewalk"], c["width"]
    if pin is not None:
        # a traced road is as wide as drawn and at grade: its lanes, then sidewalks
        width = float(pin["width_m"])
        lanes = (2, 2) if width < 26.0 else (3, 3)
        median = 0.0 if width < 22.0 else 2.0
        s = max(2.0, G.q((width - sum(lanes) * c["lane"] - median) / 2.0 - 0.15))
        side = (s, s)
        # the furniture zone leaves the 1.8 m clear path
        return {"total_width_m": width, "lane_width_m": c["lane"], "lanes_forward": lanes[0],
                "lanes_backward": lanes[1], "median_m": median, "sidewalk_m": side,
                "parking": (False, False), "curb_m": 0.15,
                "furniture_m": G.q(min(1.5, max(0.0, s - 1.8 - 0.15 - 0.1)))}
    if role == "axis_boulevard":
        lanes, median, side, width = (BOULEVARD["lanes"], BOULEVARD["median"],
                                      BOULEVARD["sidewalk"], BOULEVARD["width"])
    return {"total_width_m": width, "lane_width_m": c["lane"], "lanes_forward": lanes[0],
            "lanes_backward": lanes[1], "median_m": median, "sidewalk_m": side,
            "parking": (False, False), "curb_m": 0.15 if cls != "highway" else 0.0}


def assemble(spec: CitySpec, ctx: Ctx, peds: list[dict]) -> RoadNet:
    net = RoadNet(exits=dict(ctx.exits))
    roads = [r for r in ctx.roads if r.line.length > 1.0]
    if not roads:
        return net
    lines = [r.line for r in roads]
    noded = G_lines(shapely.node(MultiLineString(lines)))
    tree = shapely.STRtree(lines)
    rank = {"highway": 2, "avenue": 1}
    pieces = []
    for ln in noded:
        ln = G.qline(ln)
        if ln.is_empty or ln.length < 0.05:
            continue
        mid = ln.interpolate(0.5, normalized=True)
        cands = [int(i) for i in tree.query(mid.buffer(0.05))]
        cands = [i for i in cands if lines[i].distance(mid) < 0.05] or \
            [min(range(len(lines)), key=lambda i: lines[i].distance(mid))]
        src = max(cands, key=lambda i: (rank[roads[i].cls], -i))
        pieces.append((ln, roads[src]))
    # Graph with nodes keyed by grid point.
    keep = set(G.qpoint(p) for p in ctx.exits.values())
    for _ in range(2):
        pieces = _merge_degree2(pieces, ctx.fit)
        pieces = _drop_dangles(pieces, keep, ctx)
        pieces = _merge_degree2(pieces, ctx.fit)
        pieces = _collapse_short(pieces)
    pieces = _merge_degree2(pieces, ctx.fit)
    pieces = _refit(pieces, ctx)
    pieces = _trim_hooks(pieces, keep)
    pieces = _merge_forks(pieces)
    for _ in range(4):  # until nothing changes
        before = sorted((G.qpoint(ln.coords[0]), G.qpoint(ln.coords[-1]), round(ln.length, 2))
                        for ln, _ in pieces)
        pieces = _cut_tight(pieces)
        pieces = _drop_dangles(pieces, keep, ctx)
        pieces = _drop_lenses(pieces)
        pieces = _merge_degree2(pieces, ctx.fit)
        pieces = _refit(pieces, ctx)
        after = sorted((G.qpoint(ln.coords[0]), G.qpoint(ln.coords[-1]), round(ln.length, 2))
                       for ln, _ in pieces)
        if after == before:
            break
    pieces = _unnode_water(pieces, ctx)
    pieces = _main_network(pieces, keep, ctx)
    pieces, edge_pts = _extend_to_edge(pieces, keep, ctx)
    node_ids: dict = {}
    deg: dict = {}
    for ln, _ in pieces:
        for c in (G.qpoint(ln.coords[0]), G.qpoint(ln.coords[-1])):
            deg[c] = deg.get(c, 0) + 1
    order = sorted(deg)
    exit_pts = {G.qpoint(p): d for d, p in ctx.exits.items()}
    for i, c in enumerate(order):
        node_ids[c] = f"rn{i + 1:04d}"
        kind = "exit" if c in exit_pts else ("edge" if c in edge_pts else (
            "end" if deg[c] == 1 else "junction"))
        rec = {"id": node_ids[c], "position": (c[0], c[1], 0.0), "level": 0,
               "attrs": {"kind": kind, "degree": deg[c]}}
        if c in exit_pts:
            rec["attrs"]["exit"] = f"{exit_pts[c]}_exit"
        net.nodes.append(rec)
    # Bridges per piece.
    pieces.sort(key=lambda t: (t[1].cls != "highway", G.qpoint(t[0].coords[0]),
                               G.qpoint(t[0].coords[-1]), round(t[0].length, 2)))
    bridge_n = 0
    seg_rows = []
    for si, (ln, road) in enumerate(pieces):
        sid = f"rs{si + 1:04d}"
        spans = _spans(ctx, ln)
        b_ids = []
        for sp in spans:
            bridge_n += 1
            bid = f"br{bridge_n:03d}"
            sp["id"] = bid
            sp["segment_ids"] = [sid]
            sp["road_class"] = road.cls
            b_ids.append(bid)
            net.bridges.append(sp)
        clearance = max((b["clearance_m"] for b in spans), default=None)
        districts = _served(ctx, ln)
        prof = _z_profile(ln, spans)
        a, b = G.qpoint(ln.coords[0]), G.qpoint(ln.coords[-1])
        row = {
            "id": sid, "type": f"road.{road.cls}", "start": node_ids[a], "end": node_ids[b],
            "centerline": [(x, y) for x, y in ln.coords], "level": 0, "z_profile": prof,
            "cross_section": _cross_section(road.cls, road.role, road.pin),
            "name": road.name, "road_class": road.cls,
            "lanes": sum(_cross_section(road.cls, road.role, road.pin)[k]
                         for k in ("lanes_forward", "lanes_backward")),
            "width_m": _cross_section(road.cls, road.role, road.pin)["total_width_m"],
            "bridge": bool(spans), "bridge_ids": b_ids, "clearance_m": clearance,
            "district_ids": districts,
            "attrs": {"role": road.role, "length_m": G.q(ln.length),
                      "z_profile": "placeholder"},
        }
        if road.causeway:
            row["attrs"]["causeway"] = True
        if road.pin is not None:
            row["attrs"]["pinned"] = dict(road.pin)
        seg_rows.append(row)
    net.segments = seg_rows
    _grade_separations(ctx, net)
    _mark_elevated(spec, ctx, net)
    _name_bridges(spec, ctx, net)
    # M9: immersed tubes and cut-and-cover tunnels (a negative level, before the viaducts)
    from . import tunnels as TN

    TN.apply(spec, ctx, net, TN.choose(spec, ctx, net))
    for k, p in enumerate(peds):
        bridge_n += 1
        span = _spans(ctx, p["line"], whole=True)
        cls_w = max((s["attrs"]["water_class"] for s in span), key=lambda c: (
            {"canal": 1, "river": 2, "sea": 3}[c]), default="sea")
        crosses = span[0]["crosses"] if span else "sea"
        clear = max((s["clearance_m"] for s in span), default=CLEARANCE_M["sea"])
        net.bridges.append({
            "id": f"br{bridge_n:03d}", "type": "bridge.pedestrian", "name": p["name"],
            "bridge_class": "pedestrian", "crosses": crosses, "clearance_m": clear,
            "deck_levels": [0], "line": [(x, y, G.q(clear + DECK_M)) for x, y in
                                         p["line"].coords],
            "segment_ids": [],
            "attrs": {"water_class": cls_w, "span_m": G.q(p["line"].length),
                      "ramp_length_m": G.q((clear + DECK_M) / RAMP_GRADE), "major": True,
                      "named": True, "causeway": False}})
    # M7: viaducts, ramps and interchanges
    from . import elevated as EL

    net.elevated = EL.elevate(spec, ctx, net)
    ctx.notes += net.elevated.pop("notes", [])
    if net.elevated.get("runs"):
        _grade_separations(ctx, net)
    TN.attach(net)
    return net


def _endpoints(pieces):
    deg: dict = {}
    for ln, _ in pieces:
        for c in (G.qpoint(ln.coords[0]), G.qpoint(ln.coords[-1])):
            deg[c] = deg.get(c, 0) + 1
    return deg


def _smooth_joint(fitter, ca: list, cb: list, cls: str) -> LineString:
    """Two pieces joined end to end at an angle: refit the corner (vertices within 80 m of
    it may go) so it becomes a curve."""
    pts = [tuple(p) for p in ca] + [tuple(p) for p in cb[1:]]
    j = len(ca) - 1
    jp = pts[j]
    zone = 250.0 if cls == "highway" else 90.0
    fixed = {i for i, p in enumerate(pts)
             if M.hypot(p[0] - jp[0], p[1] - jp[1]) > zone} | {0, len(pts) - 1}
    line, _ = fitter.fillet(pts, fixed, cls)
    return G.qline(line)


def _on_ends(ln, a, b):
    """The line with its ends exactly at a and b when they lie within 10 cm of them (and
    it keeps at least one point between), else None."""
    if ln.is_empty or len(ln.coords) < 2:
        return None
    c = [tuple(p) for p in ln.coords]
    if M.hypot(c[0][0] - a[0], c[0][1] - a[1]) > 0.1 or \
            M.hypot(c[-1][0] - b[0], c[-1][1] - b[1]) > 0.1:
        return None
    if c[0] == tuple(a) and c[-1] == tuple(b):
        return ln
    inner = c[1:-1]
    if not inner:
        return None
    return G.qline(LineString([tuple(a)] + inner + [tuple(b)]))


def _merge_degree2(pieces, fitter=None):
    """Join pieces that meet end to end at a node of degree 2 (same class); a sharp joint
    is refitted as a curve."""
    changed = True
    while changed:
        changed = False
        deg = _endpoints(pieces)
        for c, d in sorted(deg.items()):
            if d != 2:
                continue
            at = [i for i, (ln, _) in enumerate(pieces)
                  if G.qpoint(ln.coords[0]) == c or G.qpoint(ln.coords[-1]) == c]
            if len(at) != 2:
                continue
            i, j = at
            (la, ra), (lb, rb) = pieces[i], pieces[j]
            if ra.cls != rb.cls or la.equals(lb) or \
                    (ra.role == "pinned") != (rb.role == "pinned"):
                continue
            ca, cb = list(la.coords), list(lb.coords)
            if G.qpoint(ca[0]) == c:
                ca = ca[::-1]
            if G.qpoint(cb[-1]) == c:
                cb = cb[::-1]
            if ca[0] == cb[-1] and G.qpoint(ca[0]) != c:
                continue  # would close a loop on itself; keep the node
            merged = LineString(ca + cb[1:])
            if fitter is not None and ra.role != "pinned" and \
                    _turn(ca[-2], ca[-1], cb[1]) > M.radians(12.0):
                sm = _smooth_joint(fitter, ca, cb, ra.cls if ra.cls == rb.cls else "avenue")
                # the arc's 5 cm cleanup can drop an end point (the line then ends a few cm
                # off its node) or, on pieces a few cm long, every point: put the ends back
                # on the nodes, or keep the plain joint
                sm = _on_ends(sm, ca[0], cb[-1])
                if sm is not None:
                    merged = sm
            keep = ra if la.length >= lb.length else rb
            pieces = [p for k, p in enumerate(pieces) if k not in (i, j)] + [(merged, keep)]
            changed = True
            break
    return pieces


def _drop_dangles(pieces, keep: set, ctx: Ctx):
    """Remove dead-end stubs under 120 m (highways: 300 m; one at a megasite gate or running off
    the map edge stays when it is at least 60 m, or its class minimum, long); self-loops under
    150 m are noding artifacts."""
    gates = ctx.site_zone.buffer(30.0) if not ctx.site_zone.is_empty else None
    edge = ctx.canvas.exterior.buffer(EDGE_KEEP_M + 25.0)
    changed = True
    while changed:
        changed = False
        deg = _endpoints(pieces)
        out = []
        for ln, r in pieces:
            a, b = G.qpoint(ln.coords[0]), G.qpoint(ln.coords[-1])
            if r.role == "pinned":
                out.append((ln, r))
                continue
            if a == b and ln.length < 150.0:
                changed = True
                continue
            dead = [c for c in (a, b) if deg[c] == 1 and c not in keep]
            lone = deg[a] == 1 and deg[b] == 1
            at_gate = gates is not None and any(gates.contains(Point(c)) for c in dead) and \
                ln.length >= CLASSES[r.cls]["min_len"]
            at_edge = any(edge.contains(Point(c)) for c in dead)
            stub = DANGLE_M if r.cls == "avenue" else 300.0
            if dead and not lone and not at_gate and ln.length < stub and not (
                    at_edge and ln.length >= 60.0):
                changed = True
                continue
            out.append((ln, r))
        pieces = out
    return pieces


def _drop_lenses(pieces):
    """Two avenue pieces between the same two nodes (a lens under 200 m): keep the shorter."""
    seen: dict = {}
    drop = set()
    for k, (ln, r) in enumerate(pieces):
        a, b = G.qpoint(ln.coords[0]), G.qpoint(ln.coords[-1])
        if a == b or r.cls != "avenue":
            continue
        key = (min(a, b), max(a, b))
        if key in seen:
            j = seen[key]
            if max(ln.length, pieces[j][0].length) < 200.0:
                worse = k if ln.length > pieces[j][0].length else j
                drop.add(worse)
                seen[key] = j if worse == k else k
        else:
            seen[key] = k
    return [p for k, p in enumerate(pieces) if k not in drop]


def _unnode_water(pieces, ctx: Ctx):
    """Two roads that cross out on the water do not meet: the crossing is grade separated
    (M7 sets the deck levels), so the four pieces join back into two through roads."""
    inner = ctx.wet.buffer(-3.0)
    for _ in range(20):
        deg = _endpoints(pieces)
        hit = None
        for c, d in sorted(deg.items()):
            if d == 4 and inner.contains(Point(c)):
                hit = c
                break
        if hit is None:
            return pieces
        at = [i for i, (ln, _) in enumerate(pieces)
              if hit in (G.qpoint(ln.coords[0]), G.qpoint(ln.coords[-1]))]
        by_src: dict[int, list[int]] = {}
        for i in at:
            by_src.setdefault(id(pieces[i][1]), []).append(i)
        pairs = [v for v in by_src.values() if len(v) == 2]
        if len(pairs) != 2 and len(at) == 4:
            # pieces of more than two roads: the straightest continuations go on together
            def away(i):
                ln = pieces[i][0]
                cs = list(ln.coords)
                q = ln.interpolate(min(10.0, ln.length)) if G.qpoint(cs[0]) == hit else \
                    ln.interpolate(max(ln.length - 10.0, 0.0))
                return _unit(q.x - hit[0], q.y - hit[1])

            u = {i: away(i) for i in at}
            a0 = at[0]
            best = None
            for b0 in at[1:]:
                rest = [i for i in at[1:] if i != b0]
                s = (u[a0][0] * u[b0][0] + u[a0][1] * u[b0][1]
                     + u[rest[0]][0] * u[rest[1]][0] + u[rest[0]][1] * u[rest[1]][1])
                if best is None or s < best[0] - 1e-9:
                    best = (s, [[a0, b0], rest])
            pairs = best[1]
        if len(pairs) != 2:
            return pieces
        new = []
        for i, j in pairs:
            ca, cb = list(pieces[i][0].coords), list(pieces[j][0].coords)
            if G.qpoint(ca[0]) == hit:
                ca = ca[::-1]
            if G.qpoint(cb[-1]) == hit:
                cb = cb[::-1]
            new.append((G.qline(LineString(ca + cb[1:])), pieces[i][1]))
        used = {k for pr in pairs for k in pr}
        pieces = [p for k, p in enumerate(pieces) if k not in used] + new
    return pieces


def _main_network(pieces, keep: set, ctx: Ctx):
    """Drop stray groups (left by the clean-up) that reach no landmass the main group does
    not already reach."""
    parent: dict = {}

    def find(a):
        while parent.setdefault(a, a) != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a

    for ln, _ in pieces:
        parent[find(G.qpoint(ln.coords[0]))] = find(G.qpoint(ln.coords[-1]))
    groups: dict = {}
    for k, (ln, _) in enumerate(pieces):
        groups.setdefault(find(G.qpoint(ln.coords[0])), []).append(k)
    if len(groups) < 2:
        return pieces

    def lms(ks):
        return set().union(*(_lms_on(ctx, pieces[k][0]) for k in ks))

    order = sorted(groups.values(), key=lambda ks: (-sum(pieces[k][0].length for k in ks),
                                                    min(ks)))
    main_l = lms(order[0])
    drop = set()
    for ks in order[1:]:
        has_exit = any(G.qpoint(pieces[k][0].coords[e]) in keep for k in ks for e in (0, -1))
        if not has_exit and not (lms(ks) - main_l):
            drop |= set(ks)
    return [p for k, p in enumerate(pieces) if k not in drop]


def _refit(pieces, ctx: Ctx):
    """Junction to junction, refit every segment whose curves are under the class minimum
    radius: only its ends and its bridge spans (with straight approaches) stay fixed. The new
    alignment is kept when it is better and stays clear of closed areas, water and the other
    roads."""
    from .checks import min_radius

    lines = [ln for ln, _ in pieces]
    tree = shapely.STRtree(lines)
    out = []
    for i, (ln, r) in enumerate(pieces):
        c = CLASSES[r.cls]
        base = 10.0 if r.cls == "avenue" else 20.0
        js = JUNCTION_SKIP_M[r.cls]
        rad, _ = min_radius(ln, base, js, js)
        if rad >= 0.97 * c["r_min"] or ln.length < 3 * base or r.role == "pinned":
            out.append((ln, r))
            continue
        # vertex chain: land runs simplified, bridge spans as fixed straight pieces
        # bridges become straight bank-to-bank spans with straight approaches on their axis
        spans = []
        for sp in _spans(ctx, ln):
            p0 = ln.interpolate(sp["s0"]).coords[0]
            p1 = ln.interpolate(sp["s1"]).coords[0]
            u = _unit(p1[0] - p0[0], p1[1] - p0[1])
            before = ln.interpolate(max(sp["s0"] - 150.0, 0.0)).coords[0]
            after = ln.interpolate(min(sp["s1"] + 150.0, ln.length)).coords[0]
            la = ctx.fit._approach(p0, (-u[0], -u[1]), before, r.cls, r.causeway) \
                if sp["s0"] > 1.0 else 0.0
            lb = ctx.fit._approach(p1, u, after, r.cls, r.causeway) \
                if sp["s1"] < ln.length - 1.0 else 0.0
            a0 = max(sp["s0"] - la, 0.0)
            a1 = min(sp["s1"] + lb, ln.length)
            qa = (p0[0] - u[0] * la, p0[1] - u[1] * la) if la else p0
            qb = (p1[0] + u[0] * lb, p1[1] + u[1] * lb) if lb else p1
            spans.append((a0, a1, [qa, p0, p1, qb]))
        pts, fixed = [], set()
        cursor = 0.0
        for a0, a1, chain in spans + [(ln.length, None, None)]:
            if a0 > cursor:
                land = shapely.ops.substring(ln, cursor, a0)
                run = list(land.simplify(c["dp"], preserve_topology=False).coords) \
                    if land.length > 0 else []
                for q in run:
                    if not pts or q != pts[-1]:
                        pts.append(q)
                fixed.add(len(pts) - 1)
            if chain is None:
                break
            if pts:
                pts.pop()  # the approach point replaces the end of the land run
                fixed.discard(len(pts))
            for q in chain:
                if not pts or q != pts[-1]:
                    pts.append(q)
                fixed.add(len(pts) - 1)
            cursor = a1
        fixed |= {0, len(pts) - 1}
        if len(pts) < 3:
            out.append((ln, r))
            continue
        new, _ = ctx.fit.fillet(pts, fixed, r.cls, causeway=r.causeway)
        new = G.qline(new)
        if new.is_empty or G.qpoint(new.coords[0]) != G.qpoint(ln.coords[0]) or \
                G.qpoint(new.coords[-1]) != G.qpoint(ln.coords[-1]):
            out.append((ln, r))
            continue
        rad2, _ = min_radius(new, base, js, js)
        closed = ctx.closed if r.causeway else ctx.closed_all
        ok = rad2 > rad + 1.0 and \
            (closed.is_empty or new.intersection(closed).length <= 0.5) and \
            new.intersection(ctx.wet).length <= ln.intersection(ctx.wet).length + 2.0
        if ok:
            ends = {G.qpoint(ln.coords[0]), G.qpoint(ln.coords[-1])}
            for j in tree.query(new.buffer(1.0)):
                j = int(j)
                if j == i:
                    continue
                other = lines[j]
                hit_new = {G.qpoint(q) for q in shapely.get_coordinates(new.intersection(other))}
                hit_old = {G.qpoint(q) for q in shapely.get_coordinates(ln.intersection(other))}
                if hit_new - hit_old - ends or new.distance(other) < 0.5 and not hit_new:
                    ok = False
                    break
        if ok:
            lines[i] = new
            out.append((new, r))
        else:
            out.append((ln, r))
    return out


def _is_bridge_edge(others, a, b) -> bool:
    """True when nodes a and b are not connected through the `others` pieces (so removing the
    piece between them would split the network)."""
    if a == b:
        return False
    parent: dict = {}

    def find(x):
        while parent.setdefault(x, x) != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for ln, _ in others:
        parent[find(G.qpoint(ln.coords[0]))] = find(G.qpoint(ln.coords[-1]))
    return find(a) != find(b)


def _cut_tight(pieces):
    """Optional avenues (fill roads, crossings, spare connectors) that still have a curve under
    the minimum radius after the refit lose that stretch (60 m either side)."""
    from .checks import min_radius

    deg = _endpoints(pieces)
    out = []
    todo = list(pieces)
    rounds = 0
    while todo and rounds < 200:
        rounds += 1
        ln, r = todo.pop(0)
        if r.cls != "avenue" or r.role not in OPTIONAL_ROLES + ("connector",):
            out.append((ln, r))
            continue
        a, b = G.qpoint(ln.coords[0]), G.qpoint(ln.coords[-1])
        js = JUNCTION_SKIP_M["avenue"]
        rad, at = min_radius(ln, 10.0, js if deg.get(a, 0) >= 3 else 0.0,
                             js if deg.get(b, 0) >= 3 else 0.0)
        bridge_edge = deg.get(a, 0) >= 2 and deg.get(b, 0) >= 2 and \
            _is_bridge_edge(out + todo, a, b)
        if rad >= 0.97 * CLASSES["avenue"]["r_min"] or bridge_edge:
            out.append((ln, r))
            continue
        for s0, s1 in ((0.0, at - 60.0), (at + 60.0, ln.length)):
            if s1 - s0 >= 40.0:
                todo.append((G.qline(shapely.ops.substring(ln, s0, s1)), r))
    return out + todo


def _merge_forks(pieces):
    """Two primary roads that leave a node together and run side by side (within 25 m for
    150 m or more: a duplicate) become one there: the lesser one (class, then an optional
    role, then the shorter) starts where they part, from a junction on the other."""
    rank = {"highway": 2, "avenue": 1}
    for _ in range(20):
        ends: dict = {}
        for i, (ln, r) in enumerate(pieces):
            for e in (0, -1):
                ends.setdefault(G.qpoint(ln.coords[e]), []).append((i, e))
        hit = None
        for c in sorted(ends):
            for i, _ in ends[c]:
                for j, ej in ends[c]:
                    A, ra = pieces[i]
                    Bl, rb = pieces[j]
                    if i == j or "pinned" in (ra.role, rb.role):
                        continue
                    key = lambda ln, r: (rank[r.cls], r.role not in OPTIONAL_ROLES + (
                        "connector",), round(ln.length, 2))
                    if key(Bl, rb) >= key(A, ra):
                        continue
                    b = Bl if ej == 0 else LineString(list(Bl.coords)[::-1])
                    s = 0.0
                    while s + 10.0 <= b.length and A.distance(b.interpolate(s + 10.0)) < 25.0:
                        s += 10.0
                    if s < 150.0 or s > b.length - 40.0:
                        continue
                    # the junction a little before they part, so the branch leaves at an angle
                    q = G.qpoint(nearest_points(A, b.interpolate(s - 50.0))[0])
                    t = A.project(Point(q))
                    if t < 40.0 or t > A.length - 40.0:
                        continue
                    hit = (i, j, b, s, q, t)
                    break
                if hit:
                    break
            if hit:
                break
        if hit is None:
            return pieces
        i, j, b, s, q, t = hit
        A, ra = pieces[i]
        rb = pieces[j][1]
        a1 = list(shapely.ops.substring(A, 0.0, t).coords)[:-1] + [q]
        a2 = [q] + list(shapely.ops.substring(A, t, A.length).coords)[1:]
        nb = [q] + list(shapely.ops.substring(b, s, b.length).coords)
        new = [(G.qline(LineString(a1)), ra), (G.qline(LineString(a2)), ra),
               (G.qline(LineString(nb)), rb)]
        pieces = [p for k, p in enumerate(pieces) if k not in (i, j)] + new
    return pieces


def _trim_hooks(pieces, keep: set):
    """A dead end that curls (radius under the class minimum within its last 120 m) is cut
    back to before the curl."""
    from .checks import min_radius

    deg = _endpoints(pieces)
    out = []
    for ln, r in pieces:
        rmin = CLASSES[r.cls]["r_min"]
        base = 10.0 if r.cls == "avenue" else 20.0
        for end in (0, -1):
            if r.role == "pinned":
                break
            c = G.qpoint(ln.coords[end])
            if deg.get(c, 0) != 1 or c in keep or ln.length < 60.0:
                continue
            L = ln.length
            for _ in range(6):
                rad, at = min_radius(ln, base)
                if end == -1:
                    if rad >= 0.97 * rmin or at < L - 140.0:
                        break
                    ln = shapely.ops.substring(ln, 0, max(at - 2 * base, 1.0))
                else:
                    if rad >= 0.97 * rmin or at > 140.0:
                        break
                    ln = shapely.ops.substring(ln, min(at + 2 * base, ln.length - 1.0),
                                               ln.length)
                L = ln.length
            ln = G.qline(ln)
        out.append((ln, r))
    return out


def _extend_to_edge(pieces, keep: set, ctx: Ctx):
    """Dead ends near the map edge (long roads that run off the map) reach the edge: the
    road continues beyond the map; it is not a highway exit."""
    deg = _endpoints(pieces)
    near = ctx.canvas.exterior.buffer(EDGE_KEEP_M + 25.0)
    minx, miny, maxx, maxy = ctx.canvas.bounds
    out, edge_pts = [], set()
    for ln, r in pieces:
        cs = list(ln.coords)
        for end in (0, -1):
            c = G.qpoint(cs[end])
            if deg.get(c, 0) != 1 or c in keep or not near.contains(Point(c)):
                continue
            x, y = c
            prev = cs[1] if end == 0 else cs[-2]
            ux, uy = _unit(x - prev[0], y - prev[1])
            ray = LineString([(x, y), (x + ux * 200.0, y + uy * 200.0)])
            hit = ray.intersection(ctx.canvas.exterior)
            if hit.is_empty:
                continue
            q = min(((p[0], p[1]) for p in shapely.get_coordinates(hit)),
                    key=lambda p: M.hypot(p[0] - x, p[1] - y))
            if M.hypot(q[0] - x, q[1] - y) > 120.0:
                continue
            link = LineString([(x, y), q])
            if link.intersects(ctx.closed_all) or link.intersection(ctx.wet).length > 1.0:
                continue
            if end == 0:
                cs.insert(0, q)
            else:
                cs.append(q)
            edge_pts.add(G.qpoint(q))
        out.append((G.qline(LineString(cs)), r))
    return out, edge_pts


def _collapse_short(pieces):
    """A piece shorter than its class minimum between two junctions: both ends move to its
    middle and the piece disappears."""
    for _ in range(50):
        deg = _endpoints(pieces)
        pin_pts = {G.qpoint(ln.coords[e]) for ln, r in pieces if r.role == "pinned"
                   for e in (0, -1)}
        short = None
        for i, (ln, r) in enumerate(pieces):
            a, b = G.qpoint(ln.coords[0]), G.qpoint(ln.coords[-1])
            if a == b or r.role == "pinned" or a in pin_pts or b in pin_pts:
                continue
            if ln.length < CLASSES[r.cls]["min_len"] and deg[a] >= 2 and deg[b] >= 2:
                short = (i, a, b, ln)
                break
        if short is None:
            return pieces
        i, a, b, ln = short
        m = G.qpoint(ln.interpolate(0.5, normalized=True))
        out = []
        for k, (l2, r2) in enumerate(pieces):
            if k == i:
                continue
            cs = list(l2.coords)
            for end in (0, -1):
                if G.qpoint(cs[end]) in (a, b):
                    cs[end] = m
            out.append((G.qline(LineString(cs)), r2))
        pieces = [(lp, rp) for lp, rp in out if not lp.is_empty and lp.length > 0.05]
    return pieces


def _spans(ctx: Ctx, ln: LineString, whole: bool = False) -> list[dict]:
    """Bridge spans of a line: its stretches over water (merged across gaps under 5 m)."""
    wet = ln.intersection(ctx.wet)
    parts = [x for x in G_lines(shapely.line_merge(wet) if not wet.is_empty else wet)
             if x.length > 3.0]
    if not parts:
        return []
    parts.sort(key=lambda x: ln.project(Point(x.coords[0])))
    merged = []
    for p in parts:
        s0, s1 = sorted((ln.project(Point(p.coords[0])), ln.project(Point(p.coords[-1]))))
        if merged and s0 - merged[-1][1] < 45.0:
            merged[-1][1] = max(merged[-1][1], s1)
        else:
            merged.append([s0, s1])
    out = []
    for s0, s1 in merged:
        span = shapely.ops.substring(ln, s0, s1)
        best_cls, best_id, best_len, width = 0, None, -1.0, 0.0
        for w in ctx.waters:
            inter = span.intersection(w.polygon)
            L = inter.length
            if L <= 0.5:
                continue
            if w.cls > best_cls or (w.cls == best_cls and L > best_len):
                best_cls, best_id, best_len = w.cls, w.id, L
                width = L
        if best_id is None:
            continue
        clear = clearance_for(best_cls, width)
        deck = G.q(clear + DECK_M)
        line3 = [(G.q(x), G.q(y), deck) for x, y in span.coords]
        if len(line3) < 2:
            continue
        out.append({"type": "bridge.road", "name": None, "bridge_class": "road",
                    "crosses": best_id, "clearance_m": clear, "deck_levels": [0],
                    "line": line3, "s0": G.q(s0), "s1": G.q(s1),
                    "attrs": {"water_class": WATER_CLASS[best_cls], "span_m": G.q(span.length),
                              "ramp_length_m": G.q((clear + DECK_M) / RAMP_GRADE),
                              "major": best_cls == SEA, "named": False, "causeway": False}})
    return out


def _z_profile(ln: LineString, spans: list[dict]) -> list[dict]:
    L = G.q(ln.length)
    pts = [(0.0, 0.0)]
    for sp in spans:
        deck = sp["line"][0][2]
        ramp = sp["attrs"]["ramp_length_m"]
        pts += [(max(sp["s0"] - ramp, 0.0), 0.0), (sp["s0"], deck), (sp["s1"], deck),
                (min(sp["s1"] + ramp, L), 0.0)]
    pts.append((L, 0.0))
    out = []
    for s, z in sorted(pts):
        if out and abs(out[-1]["s"] - s) < 0.01:
            out[-1] = {"s": G.q(s), "z": max(out[-1]["z"], G.q(z))}
        else:
            out.append({"s": G.q(s), "z": G.q(z)})
    return out


def _served(ctx: Ctx, ln: LineString) -> list[str]:
    out = []
    for name, poly in sorted(ctx.polygons.items()):
        near = ln.intersection(poly.buffer(25.0))
        if near.length >= 30.0:
            out.append(ctx.did[name])
    return sorted(out)


def _grade_separations(ctx: Ctx, net: RoadNet) -> None:
    """Segments that cross without a node (over water) record each other."""
    lines = [LineString(sg["centerline"]) for sg in net.segments]
    tree = shapely.STRtree(lines)
    for i, a in enumerate(lines):
        for j in sorted(int(x) for x in tree.query(a)):
            if j <= i:
                continue
            si, sj = net.segments[i], net.segments[j]
            if {si["start"], si["end"]} & {sj["start"], sj["end"]}:
                continue
            if a.crosses(lines[j]):
                si["attrs"].setdefault("grade_separated_with", []).append(sj["id"])
                sj["attrs"].setdefault("grade_separated_with", []).append(si["id"])


def _mark_elevated(spec: CitySpec, ctx: Ctx, net: RoadNet) -> None:
    """`highways.elevated_share`: mark highway segments planned as viaducts (M7 builds them):
    those over water and through the densest districts first, then the longest."""
    share = spec.highways.elevated_share
    hw = [s for s in net.segments if s["road_class"] == "highway"]
    total = sum(s["attrs"]["length_m"] for s in hw)
    if not hw or share <= 0:
        return
    dense = {ctx.did[d.name]: presets.ARCHETYPES[d.archetype].height_m[1]
             for d in spec.districts if d.name in ctx.polygons}

    def prio(s):
        return (not s["bridge"], -max((dense.get(d, 0) for d in s["district_ids"]), default=0),
                -s["attrs"]["length_m"], s["id"])

    acc, target = 0.0, share * total
    for s in sorted(hw, key=prio):
        L = s["attrs"]["length_m"]
        # take a segment when it brings the total closer to the target
        if abs(acc + L - target) < abs(acc - target):
            s["attrs"]["elevated"] = True
            acc += L
    for s in hw:
        s["attrs"].setdefault("elevated", False)


def _name_bridges(spec: CitySpec, ctx: Ctx, net: RoadNet) -> None:
    by_id = {b["id"]: b for b in net.bridges}
    taken: set[str] = set()
    for nr in ctx.named:
        best = None
        for b in net.bridges:
            if b["id"] in taken:
                continue
            bl = LineString([(x, y) for x, y, _ in b["line"]])
            mid = bl.interpolate(0.5, normalized=True)
            d = nr.line.distance(mid)
            # a bridge that runs along the route first (not one that only crosses it); the
            # route is the raster course, so a long straight span may bow away from it
            along = max(nr.line.distance(Point(bl.coords[0])),
                        nr.line.distance(Point(bl.coords[-1]))) <= 120.0
            if d > 60.0 and not (along and d <= 150.0):
                continue
            rank = (along, {"sea": 3, "river": 2, "canal": 1}[b["attrs"]["water_class"]],
                    b["attrs"]["span_m"])
            if best is None or rank > best[0]:
                best = (rank, b["id"])
        if best is None:
            ctx.notes.append(f"named bridge '{nr.name}': no bridge on its route")
            continue
        b = by_id[best[1]]
        taken.add(b["id"])
        b["name"] = nr.name
        b["bridge_class"] = nr.kind
        b["type"] = f"bridge.{nr.kind}"
        b["attrs"]["named"] = True
        b["attrs"]["major"] = True
        b["attrs"]["causeway"] = nr.causeway
        b["attrs"]["connects"] = list(nr.ends)
        if nr.crosses:
            b["attrs"]["asked_crosses"] = nr.crosses


# ---------------------------------------------------------------------------
# Pinned roads (scope 4.3)
# ---------------------------------------------------------------------------

PIN_SNAP_M = 5.0                # a traced road end this near another traced road joins it
SPOKE_REACH_M = 900.0           # a traced road leaving its island runs on this far to land
SPOKE_JOIN_M = 120.0            # and joins a road this near its landing directly


def add_pinned_roads(spec: CitySpec, ctx: Ctx) -> None:
    """The traced roads of every pinned island, as drawn (role "pinned": the clean-up keeps
    their geometry). An end within PIN_SNAP_M of another traced road joins it there (cut
    where it crosses it)."""
    for name in sorted(ctx.pins):
        pin, dist = ctx.pins[name]
        roads = [[r, list(r.line.coords)] for r in pin.roads]
        for k, (r, cs) in enumerate(roads):
            if r.closed:
                continue
            for end in (0, -1):
                p = Point(cs[end])
                best = None
                for j, (o, oc) in enumerate(roads):
                    if j == k:
                        continue
                    ol = LineString(oc)
                    d = ol.distance(p)
                    if d <= PIN_SNAP_M and (best is None or d < best[0]):
                        best = (d, j)
                if best is None:
                    continue
                ol = LineString(roads[best[1]][1])
                me = LineString(cs)
                hit = [tuple(q) for q in shapely.get_coordinates(me.intersection(ol))]
                if hit:
                    # cut at the crossing nearest this end
                    s_end = 0.0 if end == 0 else me.length
                    q = min(hit, key=lambda q: abs(me.project(Point(q)) - s_end))
                    s = me.project(Point(q))
                    piece = shapely.ops.substring(me, s, me.length) if end == 0 else \
                        shapely.ops.substring(me, 0.0, s)
                    cs = list(piece.coords)
                else:
                    q = nearest_points(ol, p)[0].coords[0]
                    cs = [q] + cs if end == 0 else cs + [q]
                q = G.qpoint(cs[end])
                cs[end] = q
                # the joint is a vertex of the other road
                oc = roads[best[1]][1]
                olq = LineString(oc)
                if not any(G.qpoint(c) == q for c in oc):
                    d = olq.project(Point(q))
                    acc = 0.0
                    for i in range(len(oc) - 1):
                        seg = M.hypot(oc[i + 1][0] - oc[i][0], oc[i + 1][1] - oc[i][1])
                        if acc + seg >= d - 1e-9:
                            oc.insert(i + 1, q)
                            break
                        acc += seg
            roads[k][1] = cs
        for r, cs in roads:
            line = G.qline(LineString(cs))
            road = Road(r.road_class, line, "pinned", None, dist, False,
                        pin={"id": r.id, "island": name, "width_m": r.width_m,
                             "elevated": r.elevated})
            ctx.roads.append(road)
            ctx.grid.mark(line, r.road_class == "highway")


def land_pinned_spokes(ctx: Ctx) -> None:
    """A traced road that ends out on the water (a bridge drawn leaving the island) runs on
    straight to the next land within SPOKE_REACH_M and joins the network there; one that
    finds no land, or would cross a closed area, ends at its island's coast."""
    for name in sorted(getattr(ctx, "pins", {})):
        pin, _ = ctx.pins[name]
        land = pin.land.buffer(1.0)
        for road in [r for r in ctx.roads if r.pin is not None and r.pin["island"] == name]:
            cs = list(road.line.coords)
            if road.line.is_closed or land.contains(Point(cs[-1])):
                continue
            x, y = cs[-1]
            prev = cs[-2]
            ux, uy = _unit(x - prev[0], y - prev[1])
            ray = LineString([(x, y), (x + ux * SPOKE_REACH_M, y + uy * SPOKE_REACH_M)])
            # onto district land (not marsh or a megasite), not back onto the island
            dry = ctx.dry.intersection(ctx.district_land).difference(
                ctx.closed_all.buffer(10.0))
            hit = ray.intersection(dry)
            landing = None
            for part in sorted(G_lines(hit) if not hit.is_empty else [],
                               key=lambda g: ray.project(Point(g.coords[0]))):
                if part.length >= 30.0:
                    landing = part.coords[0]
                    break
            ok = landing is not None
            if ok:
                ext = LineString([(x, y), landing])
                ok = not ext.intersects(ctx.closed_all)
            if not ok:
                # the stretch over the water goes; the road ends at the coast
                inside = road.line.intersection(land)
                keep = max(G_lines(inside), key=lambda g: (g.length, g.coords[0]),
                           default=None) if not inside.is_empty else None
                ctx.notes.append(f"traced road {road.pin['id']} on {name} finds no land to "
                                 "reach; it ends at the coast")
                if keep is None or keep.length < 5.0:
                    ctx.roads.remove(road)
                else:
                    road.line = G.qline(keep)
                continue
            # a road near the landing: straight on to it (a short connector would be a
            # stub); else 60 m onto the land, then the shortest way into the network
            lp = Point(landing)
            near = sorted((G.dist(r.line, lp), k) for k, r in enumerate(ctx.roads)
                          if r.pin is None and G.dist(r.line, lp) <= SPOKE_JOIN_M)
            joined = False
            for _, k in near:
                # (an existing junction within 40 m rather than a short piece beside it)
                q = Point(G.qpoint(ctx._snap_to_junction(
                    ctx.roads[k], nearest_points(ctx.roads[k].line, lp)[0])))
                link = LineString([landing, (q.x, q.y)])
                if link.length > 0.01 and (link.intersects(ctx.closed_all) or
                                           link.intersection(ctx.wet).length > 1.0):
                    continue
                ctx._insert_vertex(ctx.roads[k], q)
                road.line = G.qline(LineString(cs + [landing, (q.x, q.y)]))
                ctx.grid.mark(road.line, road.cls == "highway")
                joined = True
                break
            if joined:
                continue
            foot = (landing[0] + ux * 60.0, landing[1] + uy * 60.0)
            road.line = G.qline(LineString(cs + [landing, foot]))
            ctx.grid.mark(road.line, road.cls == "highway")
            cell = ctx.nearest_cell(foot)
            g = ctx.grid
            net = np.array(sorted(ctx.network_cells()), dtype=np.int64)
            if cell is None or not len(net):
                continue
            pts = shapely.points(g.xs[net], g.ys[net])
            away = ~shapely.contains(land.buffer(60.0), pts) & \
                (shapely.distance(road.line, pts) > 40.0)
            targets = set(net[away].tolist())
            if targets:
                ctx.route([cell], targets, road.cls, "connector", start=G.qpoint(foot))


# ---------------------------------------------------------------------------
# Driver
# ---------------------------------------------------------------------------

def build_roads(spec: CitySpec, h, polygons: dict, district_ids: dict, waterways, sites,
                open_polys: list, variant: int = 0, terrain=None) -> RoadNet:
    ctx = Ctx(spec, h, polygons, district_ids, waterways, sites, open_polys, variant, terrain)
    find_exits(spec, ctx)
    add_pinned_roads(spec, ctx)
    build_highways(spec, ctx)
    build_arterials(spec, ctx)
    land_pinned_spokes(ctx)
    peds = build_named_bridges(spec, ctx)
    connect_landmasses(spec, ctx)
    extra_crossings(spec, ctx)
    close_highway_ends(ctx)
    serve_districts(spec, ctx)
    connect_landmasses(spec, ctx)
    peds = place_footbridges(ctx, peds)
    if spec.highways.pattern == "none":
        for d, cell in sorted(ctx.exit_cells.items()):
            net = ctx.network_cells()
            if cell not in net and net:
                ctx.route([cell], net, "avenue", "exit",
                          name=f"{d.replace('_', ' ').title()} Exit", start=ctx.exits[d])
    net = assemble(spec, ctx, peds)
    net.notes = ctx.notes
    net.variant = variant
    return net
