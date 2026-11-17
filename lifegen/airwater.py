"""LG7: air and water (scope 6.7; checks, scope 8 "Air and water lanes"): routes for what flies
over the city and what floats on its water, each run to a timetable as LG6's trains are.

Everything that moves runs a **route**: a closed path in 3D (citygen m, z absolute: over sea
level on a terrain city, over the ground datum on a flat one), each point with the heading the
vehicle faces there, a speed profile along it (the kind's cruise, its acceleration and
braking, at most sqrt(lateral R) in a turn, its climb and descent rate on a vertical stretch),
dwells where it lands or berths, sampled every `presets.AW_SAMPLE_S` (the runtime places a
vehicle by the world's time, as LG6's trains). Per hour band a route runs a number of vehicles
evenly round its cycle.

- **The airspace** (`AirSpace`): every building mass, roof item, skybridge, structure (sky
  tubes, decks, beams, pylons), transit line, megasite element and sign standing off a facade
  or over a roof, widened by a margin, on a 4 m raster of 8 m height slabs (a bit each). A
  layer's free cells at a height are those whose slabs there are clear.
- **Flying cars** (`car`): over the avenues and highways and between the towers on layers
  (`presets.AIR["car_layers"]`): a leg's layer by its heading (east-bound on the even layers,
  west-bound on the odd: two ways never meet head on), at least `pad_over_m` over the roofs
  it leaves and lands on; an A* on 8 m cells costing least over the avenues and highways, its
  path pulled straight where that keeps to cells as cheap, its corners rounded. Two kinds of
  routes: a pair of pads (M3's `av_pad` and `helipad` roof items) flown between, landing and
  taking off vertically, two cars a pair at most (one at each pad); circuits round three
  avenue or highway nodes of a district, changing layer at each corner along `ramp_m`.
- **Drones** (`drone`): delivery drones from a hub roof to a drop roof and back, on lower
  layers (`drone_layers`) and the 4 m raster, hovering down onto each roof.
- **Police fliers** (`police`): orbits over each district (its middle, then its gang turfs) by
  its danger; **media fliers** (`media`) orbit the city's landmarks; **aircraft** cross the
  map high over it and turn round off the map; a **shuttle** (`shuttle`) per launch pad of a
  spaceport, in from its flight cone, down onto its pad and up and away again.
- **The water** (`WaterSpace`): M16's water bodies on a 4 m raster less every bank's slope,
  the quays' band, the moored boats (M6, kept as they are), columns and AG7's bridge piers
  standing in it; a depth per cell by M16's bed rule (linear from a bank's toe, never deeper
  than M16's); per kind the cells its hull clears by its margin with its draft under it.
- **Boats** (`boat`) run up and down every river, channel and canal, keeping right (each way
  offset from the middle, a turn round at each end); **water taxis** (`taxi`) call at piers
  derived from M16's quays (the ask `piers`); **ferries** (`ferry`, double-ended) cross the
  rivers between piers derived on their banks where a walkway comes to the shore; **ships**
  (`ship`) come in to the port's berths where the water is deep enough, else lie at them, and
  one passes offshore.
- **Checks** (`checks`): `air_lanes` (every flier's path clear of the airspace's obstacles by
  its margin, read back every 4 m), `air_pads` (every pad flown from reached by its route, the
  pads left out with why), `water_lanes` (every boat on water its hull clears, deep enough,
  under every bridge with room), `airwater_timing` (speeds and turns within the kind's,
  dwells kept, vehicles on a route apart, routes closed), `airwater_budget` (vehicles at
  once).
- `preview_airwater.png` (`preview`): the routes by kind, pads and piers, the vehicles at the
  crowd's hour.
"""

from __future__ import annotations

import bisect
import hashlib
import heapq
import math
from collections import defaultdict
from pathlib import Path

import numpy as np
import shapely
from shapely.geometry import LineString, Point, Polygon, box
from shapely import affinity

from . import presets as P
from .transit import _knots, sample

V = P.AW_VEHICLES
AIRK = P.AIR_KINDS
EVENT_CODES = ("pad", "drop", "pier", "berth", "launch")


def _r(v: float, k: int = 3) -> float:
    r = round(float(v), k)
    return 0.0 if r == 0.0 else r


def _u(*parts) -> float:
    """A draw in [0, 1) from what a thing is (blake2b of its parts)."""
    h = hashlib.blake2b("|".join(str(p) for p in parts).encode("utf-8"), digest_size=8)
    return int.from_bytes(h.digest(), "big") / 2.0 ** 64


def _cell_id(x: float, y: float) -> str:
    return f"{'e' if x >= 0 else 'w'}{abs(int(round(x)))}{'n' if y >= 0 else 's'}{abs(int(round(y)))}"


def _poly(rec) -> Polygon | None:
    if not rec or not rec.get("exterior") or len(rec["exterior"]) < 3:
        return None
    p = Polygon(rec["exterior"], [h for h in rec.get("holes") or [] if len(h) >= 3])
    if not p.is_valid:
        p = p.buffer(0)
    return p if not p.is_empty else None


def _heading(a, b) -> float:
    return math.atan2(b[1] - a[1], b[0] - a[0])


# ---------------------------------------------------------------------------
# The ground (M13) and the raster
# ---------------------------------------------------------------------------

class Ground:
    """The finished ground's height at a point (M13; 0 on a flat city)."""

    def __init__(self, model: dict):
        t = model.get("terrain") or None
        rows = (t or {}).get("ground") or (t or {}).get("natural") or []
        self.g = np.array(rows, dtype=np.float64) if rows else None
        if self.g is not None:
            self.x0, self.y0, self.c = float(t["x0"]), float(t["y0"]), float(t["cell_m"])

    def at(self, xs, ys) -> np.ndarray:
        xs = np.atleast_1d(np.asarray(xs, dtype=np.float64))
        ys = np.atleast_1d(np.asarray(ys, dtype=np.float64))
        if self.g is None:
            return np.zeros(len(xs))
        ny, nx = self.g.shape
        fx = np.clip((xs - self.x0) / self.c, 0, nx - 1.000001)
        fy = np.clip((ys - self.y0) / self.c, 0, ny - 1.000001)
        i, j = fx.astype(int), fy.astype(int)
        tx, ty = fx - i, fy - j
        g = self.g
        return (g[j, i] * (1 - tx) * (1 - ty) + g[j, i + 1] * tx * (1 - ty) +
                g[j + 1, i] * (1 - tx) * ty + g[j + 1, i + 1] * tx * ty)

    def one(self, x: float, y: float) -> float:
        return float(self.at([x], [y])[0])

    @property
    def flat(self) -> bool:
        return self.g is None


class Grid:
    """A raster over the map: cell (j, i) row j from the south, column i from the west."""

    def __init__(self, bounds, cell: float):
        self.x0, self.y0 = float(bounds[0]), float(bounds[1])
        self.c = float(cell)
        self.nx = int(math.ceil((float(bounds[2]) - self.x0) / self.c))
        self.ny = int(math.ceil((float(bounds[3]) - self.y0) / self.c))
        self.xs = self.x0 + (np.arange(self.nx) + 0.5) * self.c
        self.ys = self.y0 + (np.arange(self.ny) + 0.5) * self.c

    def ij(self, x: float, y: float) -> tuple[int, int]:
        j = min(self.ny - 1, max(0, int(math.floor((y - self.y0) / self.c))))
        i = min(self.nx - 1, max(0, int(math.floor((x - self.x0) / self.c))))
        return j, i

    def inside(self, x: float, y: float) -> bool:
        return 0 <= (x - self.x0) < self.nx * self.c and 0 <= (y - self.y0) < self.ny * self.c

    def xy(self, j: int, i: int) -> tuple[float, float]:
        return float(self.xs[i]), float(self.ys[j])

    def window(self, geom):
        minx, miny, maxx, maxy = geom.bounds
        i0 = max(0, int(math.floor((minx - self.x0) / self.c)))
        i1 = min(self.nx, int(math.ceil((maxx - self.x0) / self.c)) + 1)
        j0 = max(0, int(math.floor((miny - self.y0) / self.c)))
        j1 = min(self.ny, int(math.ceil((maxy - self.y0) / self.c)) + 1)
        return j0, j1, i0, i1

    def mask(self, geom):
        """(j0, j1, i0, i1, cells of the window whose middles the geometry covers); a geometry
        no cell's middle falls in marks the cell under its representative point."""
        if geom is None or geom.is_empty:
            return None
        j0, j1, i0, i1 = self.window(geom)
        if j0 >= j1 or i0 >= i1:
            return None
        X, Y = np.meshgrid(self.xs[i0:i1], self.ys[j0:j1])
        m = shapely.contains_xy(geom, X, Y)
        if not m.any():
            p = geom.representative_point()
            if not self.inside(p.x, p.y):
                return None
            j, i = self.ij(p.x, p.y)
            if j0 <= j < j1 and i0 <= i < i1:
                m[j - j0, i - i0] = True
            else:
                return None
        return j0, j1, i0, i1, m

    def paint(self, arr: np.ndarray, geom, value=True) -> None:
        r = self.mask(geom)
        if r is not None:
            j0, j1, i0, i1, m = r
            arr[j0:j1, i0:i1][m] = value


def shift(mask: np.ndarray, dj: int, di: int, fill=False) -> np.ndarray:
    out = np.full_like(mask, fill)
    ny, nx = mask.shape
    sj0, sj1 = max(0, -dj), min(ny, ny - dj)
    si0, si1 = max(0, -di), min(nx, nx - di)
    out[sj0 + dj:sj1 + dj, si0 + di:si1 + di] = mask[sj0:sj1, si0:si1]
    return out


def disk(r: int) -> list[tuple[int, int]]:
    return [(dj, di) for dj in range(-r, r + 1) for di in range(-r, r + 1)
            if dj * dj + di * di <= r * r + r]


def dilate(mask: np.ndarray, r: int) -> np.ndarray:
    if r <= 0:
        return mask.copy()
    out = mask.copy()
    for dj, di in disk(r):
        if dj or di:
            out |= shift(mask, dj, di)
    return out


def erode(mask: np.ndarray, r: int, edge: bool = False) -> np.ndarray:
    """`mask` shrunk by a disk of r cells (`edge`: what lies past the raster's edge)."""
    if r <= 0:
        return mask.copy()
    out = mask.copy()
    for dj, di in disk(r):
        if dj or di:
            out &= shift(mask, dj, di, edge)
    return out


def coarse(blocked: np.ndarray, k: int) -> np.ndarray:
    """A blocked raster on cells k times as large (blocked where any cell under is)."""
    ny, nx = blocked.shape
    my, mx = int(math.ceil(ny / k)), int(math.ceil(nx / k))
    pad = np.ones((my * k, mx * k), dtype=bool)
    pad[:ny, :nx] = blocked
    return pad.reshape(my, k, mx, k).any(axis=(1, 3))


# ---------------------------------------------------------------------------
# A* and the paths
# ---------------------------------------------------------------------------

SQ2 = math.sqrt(2.0)
MOVES = ((0, 1, 1.0), (1, 0, 1.0), (0, -1, 1.0), (-1, 0, 1.0),
         (1, 1, SQ2), (1, -1, SQ2), (-1, 1, SQ2), (-1, -1, SQ2))


def astar(cost: np.ndarray, start: tuple[int, int], goal: tuple[int, int],
          pad: int = 40, limit: int = 600000) -> list[tuple[int, int]] | None:
    """The cheapest 8-connected path of cells from `start` to `goal` (a step's cost its length
    times the mean of its two cells'; inf impassable), searched within their bounding box and
    `pad` cells round it; None without one."""
    ny, nx = cost.shape
    j0 = max(0, min(start[0], goal[0]) - pad)
    j1 = min(ny, max(start[0], goal[0]) + pad + 1)
    i0 = max(0, min(start[1], goal[1]) - pad)
    i1 = min(nx, max(start[1], goal[1]) + pad + 1)
    sub = cost[j0:j1, i0:i1]
    h, w = sub.shape
    c = sub.ravel().tolist()
    s = (start[0] - j0) * w + (start[1] - i0)
    g = (goal[0] - j0) * w + (goal[1] - i0)
    if not math.isfinite(c[s]) or not math.isfinite(c[g]):
        return None
    cmin = float(np.min(sub[np.isfinite(sub)])) if np.isfinite(sub).any() else 1.0
    gj, gi = divmod(g, w)
    INF = float("inf")
    best = [INF] * (h * w)
    par = [-1] * (h * w)
    best[s] = 0.0
    heap = [(0.0, 0, s)]
    n = 0
    while heap:
        f, _, a = heapq.heappop(heap)
        if a == g:
            break
        aj, ai = divmod(a, w)
        ga = best[a]
        dj0, di0 = abs(aj - gj), abs(ai - gi)
        if f > ga + cmin * (max(dj0, di0) + (SQ2 - 1.0) * min(dj0, di0)) + 1e-9:
            continue
        n += 1
        if n > limit:
            return None
        ca = c[a]
        for dj, di, L in MOVES:
            bj, bi = aj + dj, ai + di
            if bj < 0 or bj >= h or bi < 0 or bi >= w:
                continue
            b = bj * w + bi
            cb = c[b]
            if cb == INF:
                continue
            if dj and di and (c[aj * w + bi] == INF or c[bj * w + ai] == INF):
                continue                          # (no corner cutting past a blocked cell)
            nb = ga + L * 0.5 * (ca + cb)
            if nb < best[b] - 1e-12:
                best[b] = nb
                par[b] = a
                ddj, ddi = abs(bj - gj), abs(bi - gi)
                hh = cmin * (max(ddj, ddi) + (SQ2 - 1.0) * min(ddj, ddi))
                heapq.heappush(heap, (nb + hh, n, b))
    if best[g] == INF:
        return None
    out = []
    a = g
    while a != -1:
        aj, ai = divmod(a, w)
        out.append((aj + j0, ai + i0))
        a = par[a]
    out.reverse()
    return out


def _seg_cells(grid: Grid, a, b) -> list[tuple[int, int]]:
    L = math.dist(a[:2], b[:2])
    n = max(1, int(math.ceil(L / (0.4 * grid.c))))
    out = []
    for k in range(n + 1):
        t = k / n
        out.append(grid.ij(a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t))
    return out


def _seg_cost(grid: Grid, cost: np.ndarray, a, b) -> float:
    cells = _seg_cells(grid, a, b)
    vals = [float(cost[j, i]) for j, i in cells]
    return max(vals) if vals else 0.0


def pull(grid: Grid, cost: np.ndarray, cells: list[tuple[int, int]],
         ends: tuple | None = None) -> list[tuple[float, float]]:
    """A cell path pulled into straight runs: from each corner the farthest cell of the path a
    straight line reaches on cells no dearer than the dearest the path crosses between them
    (so a path along an avenue keeps to it), the path's own ends replaced by `ends`."""
    pts = [grid.xy(j, i) for j, i in cells]
    if ends is not None:
        pts[0], pts[-1] = ends[0], ends[1]
    if len(pts) <= 2:
        return pts
    out = [pts[0]]
    k = 0
    n = len(pts)
    while k < n - 1:
        worst = 0.0
        best = k + 1
        for m in range(k + 1, n):
            j, i = cells[m]
            worst = max(worst, float(cost[j, i]))
            if m - k > 1:
                c = _seg_cost(grid, cost, pts[k], pts[m])
                if not math.isfinite(c) or c > worst + 1e-9:
                    if m - best > 6:
                        break
                    continue
            best = m
        out.append(pts[best])
        k = best
    return out


def fillet(pts: list[tuple[float, float]], radius: float, step: float = 4.0,
           ok=None) -> list[tuple[float, float]]:
    """A polyline's corners rounded by arcs of `radius` (less where a leg is short: the arc's
    tangent at most 0.45 of each leg); `ok(points)` false for an arc tries half the radius,
    then a quarter, then leaves the corner sharp."""
    if len(pts) < 3 or radius <= 0:
        return list(pts)
    out = [pts[0]]
    for k in range(1, len(pts) - 1):
        a, b, c = pts[k - 1], pts[k], pts[k + 1]
        l1, l2 = math.dist(a, b), math.dist(b, c)
        if l1 < 1e-6 or l2 < 1e-6:
            continue
        h1, h2 = _heading(a, b), _heading(b, c)
        turn = (h2 - h1 + math.pi) % (2 * math.pi) - math.pi
        if abs(turn) < math.radians(2.0):
            out.append(b)
            continue
        arc = None
        for f in (1.0, 0.5, 0.25):
            r = radius * f
            t = r * math.tan(abs(turn) / 2.0)
            tmax = 0.45 * min(l1, l2)
            if t > tmax:
                t = tmax
                r = t / math.tan(abs(turn) / 2.0)
            p1 = (b[0] - math.cos(h1) * t, b[1] - math.sin(h1) * t)
            sgn = 1.0 if turn > 0 else -1.0
            cx = p1[0] - math.sin(h1) * r * sgn
            cy = p1[1] + math.cos(h1) * r * sgn
            a0 = math.atan2(p1[1] - cy, p1[0] - cx)
            n = max(2, int(math.ceil(abs(turn) * r / step)))
            cand = [(cx + r * math.cos(a0 + turn * q / n), cy + r * math.sin(a0 + turn * q / n))
                    for q in range(n + 1)]
            if ok is None or ok(cand):
                arc = cand
                break
        out.extend(arc if arc is not None else [b])
    out.append(pts[-1])
    return out


def resample(pts, step: float):
    """Points along a polyline no more than `step` apart (its own points kept)."""
    out = [pts[0]]
    for a, b in zip(pts, pts[1:]):
        L = math.dist(a, b)
        n = max(1, int(math.ceil(L / step)))
        for q in range(1, n + 1):
            t = q / n
            out.append(tuple(a[i] + (b[i] - a[i]) * t for i in range(len(a))))
    return out


def offset(pts, d: float):
    """A polyline moved `d` to its left (negative: its right), each point along the mean of
    its two legs' normals (mitred, at most 3 d)."""
    n = len(pts)
    out = []
    for k in range(n):
        hs = []
        if k > 0:
            hs.append(_heading(pts[k - 1], pts[k]))
        if k < n - 1:
            hs.append(_heading(pts[k], pts[k + 1]))
        nx = sum(-math.sin(h) for h in hs)
        ny = sum(math.cos(h) for h in hs)
        L = math.hypot(nx, ny)
        if L < 1e-9:
            nx, ny = -math.sin(hs[0]), math.cos(hs[0])
            L = 1.0
        nx, ny = nx / L, ny / L
        mit = 1.0
        if len(hs) == 2:
            c = math.cos((hs[1] - hs[0]) / 2.0)
            mit = min(3.0, 1.0 / max(1e-3, abs(c)))
        out.append((pts[k][0] + nx * d * mit, pts[k][1] + ny * d * mit))
    return out


def drop_close(pts, tol=0.05):
    out = [pts[0]]
    for p in pts[1:]:
        if math.dist(p, out[-1]) > tol:
            out.append(p)
    return out


# ---------------------------------------------------------------------------
# A route: its path, speeds, dwells and cycle
# ---------------------------------------------------------------------------

def yaws(pts3, fixed: list | None = None) -> list[float]:
    """The heading (degrees counterclockwise from east) a vehicle faces at each point: the mean
    of its legs' headings in plan; a vertical stretch (no way in plan) keeps the heading it came
    with (a climb from a stop the one it leaves on); `fixed[k]` where given."""
    n = len(pts3)
    seg = []
    for a, b in zip(pts3, pts3[1:]):
        L = math.hypot(b[0] - a[0], b[1] - a[1])
        seg.append(_heading(a, b) if L > 0.05 else None)
    out = []
    for k in range(n):
        hs = [h for h in ((seg[k - 1] if k > 0 else None), (seg[k] if k < n - 1 else None))
              if h is not None]
        if len(hs) == 2:
            x = math.cos(hs[0]) + math.cos(hs[1])
            y = math.sin(hs[0]) + math.sin(hs[1])
            out.append(math.atan2(y, x) if math.hypot(x, y) > 1e-6 else hs[1])
        elif hs:
            out.append(hs[0])
        else:
            out.append(None)
    # (a vertical stretch: the heading before it, else after)
    last = None
    for k in range(n):
        if out[k] is None:
            out[k] = last
        else:
            last = out[k]
    nxt = None
    for k in range(n - 1, -1, -1):
        if out[k] is None:
            out[k] = nxt if nxt is not None else 0.0
        else:
            nxt = out[k]
    deg = [math.degrees(h) for h in out]
    if fixed:
        for k, f in enumerate(fixed):
            if f is not None and k < n:
                deg[k] = f
    return [_r(d % 360.0, 2) for d in deg]


class Route:
    """A route under construction: its points (3D), the heading forced at some (`fixed`), its
    stops (point index, dwell s, event code, what it serves)."""

    def __init__(self, rid: str, kind: str, district: str | None = None):
        self.id = rid
        self.kind = kind
        self.district = district
        self.pts: list[tuple[float, float, float]] = []
        self.fixed: list = []
        self.stops: list[tuple[int, float, str, str]] = []
        self.serves: list[str] = []
        self.counts = [0] * 5
        self.model = ""
        self.color = "#ffffff"
        self.margin_ends: list[tuple[float, float, float, float]] = []   # (x, y, z0, z1) columns
        self.water_id = None

    def add(self, pts, yaw=None):
        for p in pts:
            p = (float(p[0]), float(p[1]), float(p[2]))
            if self.pts and math.dist(p, self.pts[-1]) < 0.02:
                if yaw is not None:
                    self.fixed[-1] = yaw
                continue
            self.pts.append(p)
            self.fixed.append(yaw)

    def stop(self, dwell: float, code: str, what: str):
        self.stops.append((len(self.pts) - 1, float(dwell), code, what))


def _turn_radius(a, b, c) -> float:
    """The radius in plan a vehicle turns on at b: its legs' shorter (at most 8 m) as the chord
    of the turn there (a sharp corner between long legs a tight turn; an arc's points its own
    radius); 1e9 straight on or where it climbs or descends in place."""
    l1 = math.hypot(b[0] - a[0], b[1] - a[1])
    l2 = math.hypot(c[0] - b[0], c[1] - b[1])
    if l1 < 0.05 or l2 < 0.05:
        return 1e9
    t = abs((_heading(b, c) - _heading(a, b) + math.pi) % (2 * math.pi) - math.pi)
    if t < 1e-4:
        return 1e9
    return min(l1, l2, 8.0) / (2.0 * math.sin(t / 2.0))


def profile_loop(lim: list[float], stops: list[int], accel: float, brake: float,
                 step: float) -> list[float]:
    """The fastest speeds round a closed grid (the last point the first again): 0 at `stops`,
    at most `lim`, forward at `accel` and backward at `brake`, twice round so a route with no
    stop comes round at its own speed."""
    n = len(lim) - 1
    v = list(lim[:n])
    v[0] = min(v[0], lim[n])
    for i in stops:
        v[i % n] = 0.0
    for _ in range(2):
        for i in range(n):
            j = (i + 1) % n
            v[j] = min(v[j], math.sqrt(v[i] * v[i] + 2.0 * accel * step))
        for i in range(n, 0, -1):
            a, b = (i - 1) % n, i % n
            v[a] = min(v[a], math.sqrt(v[b] * v[b] + 2.0 * brake * step))
    return v + [v[0]]


def finish(rt: Route, spec: dict | None = None) -> dict | None:
    """A route's record: its points closed, headings, the speed profile on a grid of
    `AW_STEP_M`, the cycle with its dwells, sampled every `AW_SAMPLE_S`."""
    k = V[rt.kind] if spec is None else spec
    pts = list(rt.pts)
    fixed = list(rt.fixed)
    if len(pts) < 2:
        return None
    if math.dist(pts[0], pts[-1]) > 0.02:
        pts.append(pts[0])
        fixed.append(fixed[0])
    yw = yaws(pts, fixed)
    cum = [0.0]
    for a, b in zip(pts, pts[1:]):
        cum.append(cum[-1] + math.dist(a, b))
    L = cum[-1]
    if L < 4.0 * P.AW_STEP_M:
        return None
    n = max(4, int(math.ceil(L / P.AW_STEP_M)))
    h = L / n
    # (each grid point's limit: the cruise, a turn's, a climb's or descent's)
    rad = [1e9] * len(pts)
    m = len(pts) - 1
    for q in range(len(pts)):
        a = pts[(q - 1) % m] if q > 0 else pts[m - 1]
        c = pts[(q + 1) % m] if q < m else pts[1]
        rad[q] = _turn_radius(a, pts[q], c)
    lim = []
    seg = 0
    for i in range(n + 1):
        s = i * h
        while seg < len(cum) - 2 and cum[seg + 1] < s:
            seg += 1
        a, b = pts[seg], pts[seg + 1]
        dl = math.dist(a, b)
        dz = abs(b[2] - a[2])
        v = k["cruise"]
        if dl > 0 and dz / dl > 0.7:
            v = min(v, k["vert"] or v)
        R = min(rad[seg], rad[seg + 1])
        if R < 1e8:
            v = min(v, max(0.6, math.sqrt(k["lateral"] * R)))
        lim.append(v)
    stops = []
    for idx, dwell, code, what in rt.stops:
        stops.append((int(round(cum[idx] / h)) % n, dwell, code, what))
    v = profile_loop(lim, [s[0] for s in stops], k["accel"], k["brake"], h)
    t = _knots(v, h, k["accel"])
    knots, events, u = [], [], 0.0
    stop_at = {}
    for s in stops:
        stop_at.setdefault(s[0], s)
    for i in range(n + 1):
        knots.append((u, i * h, v[i]))
        if i in stop_at and i < n:
            _, d, code, what = stop_at[i]
            events.append([_r(u, 3), _r(u + d, 3), EVENT_CODES.index(code), what])
            u += d
            knots.append((u, i * h, v[i]))
        if i < n:
            u += t[i + 1] - t[i]
    R = u
    clean = []
    for kn in knots:
        if clean and abs(kn[0] - clean[-1][0]) < 1e-9:
            clean[-1] = kn
        else:
            clean.append(kn)
    dt = R / max(1, int(math.ceil(R / P.AW_SAMPLE_S)))
    smp = sample(clean, R, dt)
    vmax = max(v)
    return {"id": rt.id, "kind": rt.kind, "district_id": rt.district, "model": rt.model,
            "color": rt.color, "serves": list(rt.serves), "water_id": rt.water_id,
            "points": [[_r(p[0], 2), _r(p[1], 2), _r(p[2], 2), yw[q]]
                       for q, p in enumerate(pts)],
            "length_m": _r(L, 2), "cycle_s": _r(R, 3), "sample_s": _r(dt, 6),
            "samples": [_r(x, 2) for x in smp], "events": events,
            "counts": list(rt.counts), "top_mps": _r(vmax, 2),
            "_lim": lim, "_v": v, "_h": h, "_cum": cum,
            "_columns": [list(c) for c in rt.margin_ends]}


# ---------------------------------------------------------------------------
# The airspace
# ---------------------------------------------------------------------------

def _box(x, y, yaw, L, W) -> Polygon:
    b = box(-L / 2.0, -W / 2.0, L / 2.0, W / 2.0)
    b = affinity.rotate(b, yaw, origin=(0, 0))
    return affinity.translate(b, x, y)


def obstacles(model: dict, ground: Ground) -> list[tuple]:
    """Everything a flier keeps off: (geometry in plan, bottom, top: absolute m, what)."""
    out = []
    for b in model.get("buildings", []):
        base = b.get("base_m")
        if base is None:
            fp = (b.get("footprint") or {}).get("exterior") or [[0, 0]]
            base = ground.one(*np.mean(np.array(fp, dtype=float), axis=0)) if not ground.flat \
                else 0.0
        base = float(base)
        for ms in b.get("masses") or []:
            p = _poly(ms.get("footprint"))
            if p is not None:
                out.append((p, base + float(ms.get("z0_m") or 0.0),
                            base + float(ms.get("z1_m") or 0.0), b["id"]))
        for it in b.get("roof_items") or []:
            if it.get("kind") in ("av_pad", "helipad"):
                continue
            x, y, z = (float(v) for v in it["position"])
            sx, sy, sz = (float(v) for v in it["size"])
            out.append((_box(x, y, float(it.get("yaw_deg") or 0.0), sx, sy), base + z,
                        base + z + sz, b["id"]))
    for s in model.get("skybridges", []):
        line = s.get("line") or []
        if len(line) < 2:
            continue
        g = LineString([p[:2] for p in line]).buffer(float(s.get("width_m") or 4.0) / 2.0,
                                                      cap_style="flat")
        z = float(s.get("z_m") or 0.0) + ground.one(*line[0][:2])
        top = z + float(s.get("levels") or 1) * float(s.get("level_height_m") or 4.0)
        out.append((g, z - 1.0, top + 0.5, s["id"]))
    for s in model.get("structures", []):
        z0, z1 = float(s.get("z0_m") or 0.0), float(s.get("z1_m") or 0.0)
        p = _poly(s.get("footprint"))
        if p is None:
            line = s.get("line") or []
            if len(line) < 2:
                continue
            half = {"tube": 4.0, "beam": 1.5, "deck": 3.5}.get(s.get("kind"), 1.0)
            p = LineString([q[:2] for q in line]).buffer(half)
            g0 = ground.one(*line[0][:2])
        else:
            c = p.representative_point()
            g0 = ground.one(c.x, c.y)
        out.append((p, g0 + z0, g0 + z1, s["id"]))
    for t in model.get("transit_lines", []):
        path = t.get("path") or []
        for q in range(0, len(path) - 1, 8):
            ch = path[q:q + 9]
            if len(ch) < 2:
                continue
            zs = [float(p[2]) if len(p) > 2 else 0.0 for p in ch]
            g0 = ground.one(*ch[0][:2])
            out.append((LineString([p[:2] for p in ch]).buffer(4.0), g0 + min(zs) - 3.5,
                        g0 + max(zs) + 4.5, t["id"]))
    for e in model.get("site_elements", []):
        for ms in e.get("masses") or []:
            p = _poly(ms.get("footprint"))
            if p is None:
                continue
            c = p.representative_point()
            g0 = ground.one(c.x, c.y)
            out.append((p, g0 + float(ms.get("z0_m") or 0.0), g0 + float(ms.get("z1_m") or 0.0),
                        e["id"]))
    for s in model.get("sign_slots", []):
        if s.get("mount") not in ("front", "roof"):
            continue
        x, y, z = (float(v) for v in s["position"])
        w, hh = float(s.get("width_m") or 4.0), float(s.get("height_m") or 4.0)
        out.append((_box(x, y, float(s.get("yaw_deg") or 0.0), w, 1.2), z - hh,
                    z + hh + 0.5, s["id"]))
    return out


class AirSpace:
    """The airspace on a raster: each cell's slabs (8 m, from `zb`) that an obstacle, widened
    by `margin` in plan and `AIR["vmargin_m"]` in height, takes (a bit each)."""

    SLABS = 63

    def __init__(self, model: dict, ground: Ground, margin: float | None = None,
                 cell: float | None = None, obs=None):
        A = P.AIR
        self.grid = Grid(model["bounds"], cell or A["cell_m"])
        self.ground = ground
        self.margin = V["drone"]["margin_m"] if margin is None else margin
        self.slab = A["slab_m"]
        gmin = 0.0 if ground.flat else float(np.min(ground.g))
        self.zb = math.floor(gmin) - self.slab
        self.occ = np.zeros((self.grid.ny, self.grid.nx), dtype=np.uint64)
        obs = obstacles(model, ground) if obs is None else obs
        self.top = 0.0
        geoms = shapely.buffer(np.array([o[0] for o in obs], dtype=object), self.margin,
                               quad_segs=2) if obs else []
        vm = A["vmargin_m"]
        for o, g in zip(obs, geoms):
            shapely.prepare(g)
            r = self.grid.mask(g)
            if r is None:
                continue
            j0, j1, i0, i1, m = r
            bits = np.uint64(self.bits(o[1] - vm, o[2] + vm))
            sub = self.occ[j0:j1, i0:i1]
            sub[m] |= bits
            self.top = max(self.top, o[2])
        self.gr = None if ground.flat else self._ground_raster()
        self.cache = {}

    def _ground_raster(self) -> np.ndarray:
        X, Y = np.meshgrid(self.grid.xs, self.grid.ys)
        return self.ground.at(X.ravel(), Y.ravel()).reshape(X.shape)

    def slab_of(self, z: float) -> int:
        return min(self.SLABS - 1, max(0, int(math.floor((z - self.zb) / self.slab))))

    def bits(self, z0: float, z1: float) -> int:
        a, b = self.slab_of(z0), self.slab_of(z1)
        return ((1 << (b + 1)) - 1) ^ ((1 << a) - 1)

    def blocked(self, z: float, half: float = 2.0) -> np.ndarray:
        """The cells blocked for a flier at height `z` over the ground (absolute on a flat
        city) whose body reaches `half` up and down from it."""
        key = (round(z, 2), half)
        if key in self.cache:
            return self.cache[key]
        if self.gr is None:
            out = (self.occ & np.uint64(self.bits(z - half, z + half))) != 0
        else:
            za = self.gr + z
            lo = np.clip(np.floor((za - half - self.zb) / self.slab), 0, self.SLABS - 1).astype(np.uint64)
            hi = np.clip(np.floor((za + half - self.zb) / self.slab), 0, self.SLABS - 1).astype(np.uint64)
            one = np.uint64(1)
            mask = ((one << (hi + one)) - one) ^ ((one << lo) - one)
            out = (self.occ & mask) != 0
        if len(self.cache) > 48:
            self.cache.clear()
        self.cache[key] = out
        return out

    def hit(self, x: float, y: float, z: float, half: float = 1.0) -> bool:
        """Whether a point (absolute z) meets an obstacle."""
        if not self.grid.inside(x, y):
            return False
        j, i = self.grid.ij(x, y)
        return bool(int(self.occ[j, i]) & self.bits(z - half, z + half))

    def gz(self, x: float, y: float) -> float:
        return 0.0 if self.ground.flat else self.ground.one(x, y)


# ---------------------------------------------------------------------------
# The fliers
# ---------------------------------------------------------------------------

def pads_of(model: dict, ground: Ground) -> list[dict]:
    """M3's av pads and helipads (their top, absolute) and a spaceport's launch pads."""
    out = []
    for b in model.get("buildings", []):
        base = float(b.get("base_m") or 0.0)
        k = 0
        for it in b.get("roof_items") or []:
            if it.get("kind") not in ("av_pad", "helipad"):
                continue
            x, y, z = (float(v) for v in it["position"])
            out.append({"id": f"{b['id']}.pad{k}", "kind": it["kind"], "building_id": b["id"],
                        "district_id": b.get("district_id"),
                        "pos": [_r(x, 2), _r(y, 2), _r(base + z + float(it["size"][2]), 2)],
                        "size_m": _r(max(float(it["size"][0]), float(it["size"][1])), 2)})
            k += 1
    for e in model.get("site_elements", []):
        if e.get("kind") != "launch_pad":
            continue
        p = _poly(e.get("footprint"))
        if p is None:
            continue
        c = p.centroid
        top = max((float(m.get("z1_m") or 0.0) for m in e.get("masses") or []), default=0.0)
        out.append({"id": e["id"], "kind": "launch_pad", "building_id": None,
                    "district_id": None, "megasite_id": e.get("megasite_id"),
                    "pos": [_r(c.x, 2), _r(c.y, 2), _r(ground.one(c.x, c.y) + top, 2)],
                    "size_m": _r(2.0 * float((e.get("attrs") or {}).get("radius_m") or 30.0), 2)})
    out.sort(key=lambda p: p["id"])
    return out


class Air:
    """The fliers' planner: the airspace at the drones' margin (4 m cells) and the cars' (8 m
    cells), the avenues and highways under them, the A* per layer."""

    def __init__(self, model: dict, ground: Ground, obs=None):
        A = P.AIR
        self.model = model
        self.ground = ground
        self.obs = obstacles(model, ground) if obs is None else obs
        self.space = AirSpace(model, ground, V["drone"]["margin_m"], obs=self.obs)
        self.g4 = self.space.grid
        self.k = A["coarse"]
        self.g8 = Grid([self.g4.x0, self.g4.y0, self.g4.x0 + self.g4.nx * self.g4.c,
                        self.g4.y0 + self.g4.ny * self.g4.c], self.g4.c * self.k)
        road = np.zeros((self.g8.ny, self.g8.nx), dtype=bool)
        for s in model.get("road_segments", []):
            if s.get("road_class") not in ("avenue", "highway") or len(s.get("centerline") or []) < 2:
                continue
            self.g8.paint(road, LineString([p[:2] for p in s["centerline"]]).buffer(
                float(s.get("width_m") or 16.0) / 2.0 + 2.0))
        self.road = road
        self.costs = {}

    def blocked(self, kind: str, z: float, coarse_: bool) -> np.ndarray:
        """The cells blocked at height `z` (over the ground) for a kind's margin."""
        key = (kind, round(z, 2), coarse_)
        if key in self.costs:
            return self.costs[key]
        b = self.space.blocked(z, max(1.0, V[kind]["size"][2]))
        extra = V[kind]["margin_m"] - self.space.margin
        if extra > 0:
            b = dilate(b, int(math.ceil(extra / self.g4.c)))
        if coarse_:
            b = coarse(b, self.k)
        if len(self.costs) > 64:
            self.costs.clear()
        self.costs[key] = b
        return b

    def cost(self, kind: str, z: float) -> np.ndarray:
        b = self.blocked(kind, z, True)
        A = P.AIR
        c = np.where(self.road, A["road_cost"], A["open_cost"]).astype(np.float64)
        c[b] = np.inf
        return c

    def free_xyz(self, kind: str, x: float, y: float, z: float, coarse_: bool = False) -> bool:
        g = self.g8 if coarse_ else self.g4
        if not g.inside(x, y):
            return True
        j, i = g.ij(x, y)
        return not bool(self.blocked(kind, z, coarse_)[j, i])

    def column_free(self, x: float, y: float, z0: float, z1: float) -> bool:
        """A vertical climb from `z0` to `z1` (absolute) at (x, y), at the drones' margin,
        from a slab over the roof it stands on."""
        z = z0 + P.AIR["vmargin_m"] + self.space.slab
        while z <= z1:
            if self.space.hit(x, y, z, 0.5):
                return False
            z += self.space.slab / 2.0
        return True

    def over(self, x: float, y: float, z0: float, z1: float) -> str | None:
        """What stands over (x, y) between `z0` and `z1` (absolute) within the drones' margin."""
        pt = Point(x, y)
        for geom, za, zb, what in self.obs:
            if zb > z0 + P.AIR["vmargin_m"] and za < z1 and \
                    geom.distance(pt) < self.space.margin:
                return what
        return None

    def leg(self, kind: str, a, b, z: float, coarse_: bool) -> list[tuple[float, float]] | None:
        """A flight in plan from a to b at height `z` over the ground: A* on the kind's cells,
        pulled straight and its corners rounded; its ends on a and b even where their own cells
        are within the kind's margin of the roof they leave (the drones' margin there)."""
        g = self.g8 if coarse_ else self.g4
        if coarse_:
            c = self.cost(kind, z)
        else:
            bl = self.blocked(kind, z, False)
            c = np.where(bl, np.inf, 1.0)
        ja, ia = g.ij(*a[:2])
        jb, ib = g.ij(*b[:2])
        # (the ends: at the drones' margin within a cell of them)
        for (j, i), p in (((ja, ia), a), ((jb, ib), b)):
            if not math.isfinite(c[j, i]) and self.free_xyz("drone", p[0], p[1], z):
                for dj in (-1, 0, 1):
                    for di in (-1, 0, 1):
                        jj, ii = j + dj, i + di
                        if 0 <= jj < g.ny and 0 <= ii < g.nx:
                            x, y = g.xy(jj, ii)
                            if not math.isfinite(c[jj, ii]) and \
                                    self.free_xyz("drone", x, y, z):
                                c[jj, ii] = P.AIR["open_cost"]
        cells = astar(c, (ja, ia), (jb, ib), pad=max(25, int(0.35 * math.dist(a[:2], b[:2]) / g.c)))
        if cells is None:
            return None
        pts = pull(g, c, cells, ends=(tuple(a[:2]), tuple(b[:2])))
        r = V[kind]["turn_m"]
        ends = (a[:2], b[:2])

        def ok(arc):
            return all(self.free_xyz(kind, x, y, z) or
                       min(math.dist((x, y), e) for e in ends) < 12.0 for x, y in arc)
        return drop_close(fillet(pts, r, 4.0, ok))

    def layer(self, kind: str, heading: float, need: float, hint: int) -> list[float]:
        """The layers a leg on `heading` may take (east-bound the even ones, west-bound the
        odd), at least `need` and from the `hint`-th up."""
        L = P.AIR["car_layers"] if kind != "drone" else P.AIR["drone_layers"]
        par = 0 if math.cos(heading) >= 0 else 1
        out = [z for k, z in enumerate(L) if k % 2 == par and z >= need]
        return out[hint:] + out[:hint] if hint < len(out) else out


def _abs(air: Air, pts2, z: float):
    """Points in plan at `z` over the ground, absolute."""
    return [(x, y, z + air.space.gz(x, y)) for x, y in pts2]


def car_pairs(pads: list[dict], lo: float, hi: float) -> list[tuple[dict, dict]]:
    """M3's pads paired for flights between them (each pad in one pair): in the order of a
    draw from their ids, each with the unpaired pad between `lo` and `hi` away its draw likes
    best, else the nearest beyond `lo` / 2."""
    roof = sorted([p for p in pads if p["kind"] != "launch_pad"], key=lambda p: _u("pad", p["id"]))
    used, out = set(), []
    for a in roof:
        if a["id"] in used:
            continue
        cands = [b for b in roof if b["id"] not in used and b["id"] != a["id"]]
        best = None
        for b in cands:
            d = math.dist(a["pos"][:2], b["pos"][:2])
            if lo <= d <= hi:
                sc = _u("pair", a["id"], b["id"])
                if best is None or sc > best[0]:
                    best = (sc, b)
        if best is None:
            far = [b for b in cands if math.dist(a["pos"][:2], b["pos"][:2]) >= lo / 2.0]
            if far:
                far.sort(key=lambda b: (math.dist(a["pos"][:2], b["pos"][:2]), b["id"]))
                best = (0.0, far[0])
        if best is None:
            continue
        b = best[1]
        used |= {a["id"], b["id"]}
        out.append((a, b))
    return out


def pad_route(air: Air, a: dict, b: dict, hint: int) -> tuple[dict | None, str]:
    """A pair of pads flown between: up from a, over to b on a layer by its heading, down onto
    b, a dwell, up, back on a layer of the other heading, down onto a, a dwell."""
    A = P.AIR
    za, zb = a["pos"][2], b["pos"][2]
    rt = Route(f"air.car.{a['id']}", "car", a.get("district_id"))
    rt.serves = [a["id"], b["id"]]
    legs = []
    for p, q in ((a, b), (b, a)):
        h = _heading(p["pos"], q["pos"])
        ga = air.space.gz(*p["pos"][:2])
        gb = air.space.gz(*q["pos"][:2])
        need = max(p["pos"][2] - ga, q["pos"][2] - gb) + A["pad_over_m"]
        got = None
        for z in air.layer("car", h, need, hint)[:4]:
            if not (air.column_free(*p["pos"][:2], p["pos"][2], z + ga) and
                    air.column_free(*q["pos"][:2], q["pos"][2], z + gb)):
                continue
            pts = air.leg("car", p["pos"], q["pos"], z, True)
            if pts is not None:
                got = (pts, z)
                break
        if got is None:
            return None, f"no flight from {p['id']} to {q['id']} clear on a layer"
        legs.append(got)
    for (pts, z), p, q in zip(legs, (a, b), (b, a)):
        rt.add([tuple(p["pos"])])
        rt.stop(V["car"]["dwell_s"], "pad", p["id"])
        rt.add(_abs(air, pts, z))
        rt.add([tuple(q["pos"])])
        rt.margin_ends += [(p["pos"][0], p["pos"][1], p["pos"][2],
                            z + air.space.gz(*p["pos"][:2]) + 6.0),
                           (q["pos"][0], q["pos"][1], q["pos"][2],
                            z + air.space.gz(*q["pos"][:2]) + 6.0)]
    # (the route ends where it began: a's pad, where the next cycle's dwell is)
    rt.pts.pop()
    rt.fixed.pop()
    return finish(rt), ""


def circuit(air: Air, did: str, nodes: list[tuple[str, float, float]], k: int,
            hint: int) -> dict | None:
    """A circuit round three avenue or highway nodes of a district: legs on the layers of their
    headings, the change of layer along the start of each leg (`ramp_m`)."""
    A = P.AIR
    lo, hi = A["lane_triangle_m"]
    # (a small district's circuits as large as it allows: sides from a third of its span)
    xs = [n[1] for n in nodes]
    ys = [n[2] for n in nodes]
    span = math.hypot(max(xs) - min(xs), max(ys) - min(ys)) if nodes else 0.0
    lo = min(lo, 0.33 * span)
    order = sorted(nodes, key=lambda n: _u("circuit", did, k, n[0]))
    for a in order[:12]:
        bs = [n for n in order if lo <= math.dist(a[1:], n[1:]) <= hi]
        for b in bs[:6]:
            cs = [n for n in order if n is not a and n is not b and
                  lo <= math.dist(a[1:], n[1:]) <= hi and lo <= math.dist(b[1:], n[1:]) <= hi]
            for c in cs[:4]:
                tri = [a, b, c]
                # (counterclockwise, no corner under 25 degrees)
                ar = (b[1] - a[1]) * (c[2] - a[2]) - (b[2] - a[2]) * (c[1] - a[1])
                if ar < 0:
                    tri = [a, c, b]
                ang_ok = True
                for q in range(3):
                    p0, p1, p2 = tri[q - 1], tri[q], tri[(q + 1) % 3]
                    v1 = (p0[1] - p1[1], p0[2] - p1[2])
                    v2 = (p2[1] - p1[1], p2[2] - p1[2])
                    ca = (v1[0] * v2[0] + v1[1] * v2[1]) / (math.hypot(*v1) * math.hypot(*v2))
                    if math.degrees(math.acos(max(-1.0, min(1.0, ca)))) < 25.0:
                        ang_ok = False
                if not ang_ok:
                    continue
                legs = []
                for q in range(3):
                    p, r = tri[q], tri[(q + 1) % 3]
                    h = _heading(p[1:], r[1:])
                    got = None
                    for z in air.layer("car", h, 0.0, hint)[:3]:
                        pts = air.leg("car", (p[1], p[2], 0.0), (r[1], r[2], 0.0), z, True)
                        if pts is not None:
                            got = (pts, z)
                            break
                    if got is None:
                        break
                    legs.append(got)
                if len(legs) < 3:
                    continue
                rt = Route(f"air.lane.{tri[0][0]}", "car", did)
                rt.serves = [n[0] for n in tri]
                zprev = legs[-1][1]
                for pts, z in legs:
                    pts = resample(pts, 8.0)
                    run = 0.0
                    out = []
                    for q, (x, y) in enumerate(pts):
                        if q:
                            run += math.dist(pts[q - 1], (x, y))
                        f = min(1.0, run / max(1.0, min(A["ramp_m"], 0.4 * _plen(pts))))
                        zz = zprev + (z - zprev) * (f * f * (3 - 2 * f))
                        out.append((x, y, zz + air.space.gz(x, y)))
                    rt.add(out)
                    zprev = z
                rec = finish(rt)
                if rec is not None and _route_clear(air, rec, "car") is None:
                    return rec
    return None


def _plen(pts) -> float:
    return sum(math.dist(a[:2], b[:2]) for a, b in zip(pts, pts[1:]))


def orbit(air: Air, rid: str, kind: str, did, centers, radii, alts, k: int) -> dict | None:
    """An orbit (police, media): the first circle of the radii and heights clear at the
    kind's margin round any of the centers, clockwise or not by its draw."""
    sense = 1.0 if _u("sense", rid) < 0.5 else -1.0
    for cx, cy in centers:
        for r in radii:
            for z in alts:
                n = max(24, int(2 * math.pi * r / 12.0))
                a0 = 2 * math.pi * _u("phase", rid)
                pts = [(cx + r * math.cos(a0 + sense * 2 * math.pi * q / n),
                        cy + r * math.sin(a0 + sense * 2 * math.pi * q / n)) for q in range(n)]
                if not all(air.g4.inside(x, y) for x, y in pts):
                    continue
                if all(air.free_xyz(kind, x, y, z) for x, y in resample(pts + pts[:1], 6.0)):
                    rt = Route(rid, kind, did)
                    rt.add(_abs(air, pts, z))
                    rec = finish(rt)
                    # (LG8: the finished route read back as the check reads it, every 4 m:
                    # the circle tested every 6 m could graze a tower between two of its points,
                    # Nexus City's media flier at 280 m)
                    if rec is not None and _route_clear(air, rec, kind) is None:
                        return rec
    return None


def overflights(model: dict, n: int) -> list[dict]:
    """Aircraft crossing the map high over it: a straight line through the middle on a bearing
    drawn from the city's name, each next one the other way 700 m to its side, running on
    `aircraft_out_m` past the edge and turning round off the map."""
    A = P.AIR
    b = model["bounds"]
    cx, cy = (b[0] + b[2]) / 2.0, (b[1] + b[3]) / 2.0
    half = max(b[2] - b[0], b[3] - b[1]) / 2.0 + A["aircraft_out_m"]
    th0 = math.pi * _u("air", model.get("name"))
    out = []
    for k in range(n):
        th = th0 + (math.pi if k % 2 else 0.0)
        off = 700.0 * (k // 2 + 0.5) * (1 if k % 2 == 0 else -1)
        ux, uy = math.cos(th), math.sin(th)
        nx_, ny_ = -uy, ux
        R = V["aircraft"]["turn_m"]
        z = A["aircraft_m"][k % len(A["aircraft_m"])]
        z2 = A["aircraft_m"][(k + 1) % len(A["aircraft_m"])]
        p0 = (cx + nx_ * off - ux * half, cy + ny_ * off - uy * half)
        p1 = (cx + nx_ * off + ux * half, cy + ny_ * off + uy * half)
        rt = Route(f"air.aircraft.{k}", "aircraft")
        pts = [(p0[0], p0[1], z), (p1[0], p1[1], z)]
        # (round off the map: a half circle to the left, back on the far side, a half circle)
        c1 = (p1[0] + nx_ * R, p1[1] + ny_ * R)
        for q in range(1, 25):
            a = th - math.pi / 2 + math.pi * q / 24
            pts.append((c1[0] + R * math.cos(a), c1[1] + R * math.sin(a),
                        z + (z2 - z) * q / 24))
        q0 = (p0[0] + 2 * nx_ * R, p0[1] + 2 * ny_ * R)
        pts.append((q0[0], q0[1], z2))
        c0 = (p0[0] + nx_ * R, p0[1] + ny_ * R)
        for q in range(1, 24):
            a = th + math.pi / 2 + math.pi * q / 24
            pts.append((c0[0] + R * math.cos(a), c0[1] + R * math.sin(a),
                        z2 + (z - z2) * q / 24))
        rt.add(pts)
        rec = finish(rt)
        if rec:
            out.append(rec)
    return out


def shuttle(air: Air, pad: dict, model: dict) -> tuple[dict | None, str]:
    """A spaceport's shuttle: in from far out along its pad's flight cone at the shuttle's
    cruise, down to `shuttle_hover_m` over the pad, straight down onto it, a dwell, up and out
    the cone's way, round off the map."""
    A = P.AIR
    ms = next((m for m in model.get("megasites", []) if m["id"] == pad.get("megasite_id")), None)
    cone = _poly((ms or {}).get("flight_cone")) if ms else None
    x, y, z = pad["pos"]
    if cone is not None:
        c = cone.centroid
        h = _heading((x, y), (c.x, c.y))
    else:
        h = math.pi * 2 * _u("shuttle", pad["id"])
    ux, uy = math.cos(h), math.sin(h)
    nx_, ny_ = -uy, ux
    b = model["bounds"]
    far = max(b[2] - b[0], b[3] - b[1]) + A["aircraft_out_m"]
    hov = z + A["shuttle_hover_m"]
    if not air.column_free(x, y, z, hov + 10.0):
        return None, f"{pad['id']}: its column meets something"
    zc = A["shuttle_cruise_m"]
    lat = 400.0
    rt = Route(f"air.shuttle.{pad['id']}", "shuttle")
    rt.serves = [pad["id"]]
    rt.margin_ends = [(x, y, z, hov + 20.0)]
    rt.add([(x, y, z)])
    rt.stop(V["shuttle"]["dwell_s"], "launch", pad["id"])
    rt.add([(x, y, hov + 300.0), (x + ux * 1500 - nx_ * lat * 0.4, y + uy * 1500 - ny_ * lat * 0.4,
                                  zc), (x + ux * far - nx_ * lat, y + uy * far - ny_ * lat, zc)])
    R = lat
    cx, cy = x + ux * far, y + uy * far
    for q in range(1, 24):
        a = h - math.pi / 2 + math.pi * q / 24
        rt.add([(cx + R * math.cos(a), cy + R * math.sin(a), zc)])
    rt.add([(x + ux * far + nx_ * lat, y + uy * far + ny_ * lat, zc),
            (x + ux * 900 + nx_ * lat * 0.3, y + uy * 900 + ny_ * lat * 0.3, hov + 160.0),
            (x + ux * 250, y + uy * 250, hov), (x, y, hov)])
    return finish(rt), ""


def drone_roofs(model: dict, ground: Ground, lo: float, hi: float) -> list[dict]:
    """Roofs a drone can set down on: a building's top mass between `lo` and `hi` high, its
    point on its footprint 2.5 m clear of every roof item."""
    out = []
    for b in model.get("buildings", []):
        ms = [m for m in b.get("masses") or [] if m.get("footprint")]
        if not ms:
            continue
        top = max(ms, key=lambda m: float(m.get("z1_m") or 0.0))
        h = float(top.get("z1_m") or 0.0)
        if not (lo <= h <= hi):
            continue
        p = _poly(top["footprint"])
        if p is None or p.area < 60.0:
            continue
        c = p.buffer(-3.0).representative_point() if not p.buffer(-3.0).is_empty else None
        if c is None:
            continue
        if any(math.hypot(float(it["position"][0]) - c.x, float(it["position"][1]) - c.y) <
               2.5 + 0.5 * max(float(it["size"][0]), float(it["size"][1]))
               for it in b.get("roof_items") or []):
            continue
        base = float(b.get("base_m") or 0.0) if b.get("base_m") is not None else ground.one(c.x, c.y)
        out.append({"id": b["id"], "district_id": b.get("district_id"),
                    "pos": [_r(c.x, 2), _r(c.y, 2), _r(base + h, 2)]})
    out.sort(key=lambda r: r["id"])
    return out


def drone_route(air: Air, hub: dict, drop: dict, hint: int) -> dict | None:
    A = P.AIR
    rt = Route(f"air.drone.{hub['id']}.{drop['id']}", "drone", hub.get("district_id"))
    rt.serves = [hub["id"], drop["id"]]
    legs = []
    for p, q in ((hub, drop), (drop, hub)):
        h = _heading(p["pos"], q["pos"])
        need = max(p["pos"][2] - air.space.gz(*p["pos"][:2]),
                   q["pos"][2] - air.space.gz(*q["pos"][:2])) + 8.0
        got = None
        for z in air.layer("drone", h, need, hint)[:3]:
            zp = z + air.space.gz(*p["pos"][:2])
            zq = z + air.space.gz(*q["pos"][:2])
            if not (air.column_free(*p["pos"][:2], p["pos"][2], zp) and
                    air.column_free(*q["pos"][:2], q["pos"][2], zq)):
                continue
            pts = air.leg("drone", p["pos"], q["pos"], z, False)
            if pts is not None:
                got = (pts, z)
                break
        if got is None:
            return None
        legs.append(got)
    for (pts, z), p, q, code in zip(legs, (hub, drop), (drop, hub), ("drop", "drop")):
        rt.add([tuple(p["pos"])])
        rt.stop(V["drone"]["dwell_s"] * (2.0 if p is hub else 1.0), code, p["id"])
        rt.add(_abs(air, pts, z))
        rt.add([tuple(q["pos"])])
        rt.margin_ends += [(p["pos"][0], p["pos"][1], p["pos"][2],
                            z + air.space.gz(*p["pos"][:2]) + 6.0),
                           (q["pos"][0], q["pos"][1], q["pos"][2],
                            z + air.space.gz(*q["pos"][:2]) + 6.0)]
    rt.pts.pop()
    rt.fixed.pop()
    return finish(rt)


def _route_clear(air: Air, rec: dict, kind: str) -> str | None:
    """Where a flier's route meets an obstacle within its margin (read every 4 m; within a
    pad's or roof's column, at the drones' margin), else None."""
    pts = rec["points"]
    cols = rec.get("_columns") or []
    for a, b in zip(pts, pts[1:]):
        L = math.dist(a[:3], b[:3])
        n = max(1, int(math.ceil(L / 4.0)))
        for q in range(n + 1):
            t = q / n
            x, y, z = (a[i] + (b[i] - a[i]) * t for i in range(3))
            gz = air.space.gz(x, y)
            near = None
            for c in cols:
                if math.hypot(x - c[0], y - c[1]) < max(V[kind]["margin_m"], 10.0) + 2.0 and \
                        z <= c[3] + 8.0:
                    near = c
                    break
            if near is not None:
                if z <= near[2] + P.AIR["vmargin_m"] + air.space.slab:
                    continue
                if air.space.hit(x, y, z, 0.5):
                    return f"({x:.0f}, {y:.0f}, {z:.0f}) by its pad"
                continue
            if kind in ("aircraft", "shuttle") and z > air.space.top + 20.0:
                continue
            if not air.free_xyz(kind, x, y, z - gz, kind not in ("drone",)) and \
                    not (kind != "drone" and air.free_xyz(kind, x, y, z - gz, False)):
                return f"({x:.0f}, {y:.0f}, {z:.0f})"
    return None


# ---------------------------------------------------------------------------
# The water
# ---------------------------------------------------------------------------

def water_bodies(model: dict) -> list[dict]:
    """M16's water bodies (not the ornamental ones): id, kind, polygons, surface, depth, banks."""
    out = []
    lv = {w.get("water_id"): w for w in ((model.get("terrain") or {}).get("water_levels") or [])}

    def surf(e):
        s = (e.get("bed") or {}).get("surface_m")
        if s is not None:
            return float(s)
        return float((lv.get(e["id"]) or {}).get("level_m") or 0.0)
    for s in model.get("seas", []):
        polys = [_poly(p) for p in s.get("polygons") or []]
        out.append({"id": s["id"], "kind": "sea", "polys": [p for p in polys if p],
                    "surface": surf(s), "depth": float(s.get("depth_m") or 10.0), "ent": s})
    for coll, kind in (("rivers", "river"), ("channels", "channel")):
        for r in model.get(coll, []):
            p = _poly(r.get("polygon"))
            out.append({"id": r["id"], "kind": kind, "polys": [p] if p else [],
                        "surface": surf(r), "depth": float(r.get("depth_m") or 3.0),
                        "centerline": r.get("centerline"), "ent": r})
    for w in model.get("waterways", []):
        if w.get("ornamental"):
            continue
        p = _poly(w.get("polygon"))
        out.append({"id": w["id"], "kind": w.get("kind") or "canal", "polys": [p] if p else [],
                    "surface": surf(w), "depth": float(w.get("depth_m") or 1.5),
                    "centerline": w.get("centerline"), "ent": w})
    return out


def street_piers(build: Path | None) -> list[Polygon]:
    """AG7's bridge piers' footprints (the street manifest's notes), where the build has them."""
    if build is None:
        return []
    f = Path(build) / "assets" / "streets" / "manifest.json"
    if not f.is_file():
        return []
    import json
    try:
        man = json.loads(f.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    out = []
    for pc in (man.get("pieces") or {}).values() if isinstance(man.get("pieces"), dict) else \
            (man.get("pieces") or []):
        for ring in ((pc or {}).get("notes") or {}).get("piers") or []:
            if len(ring) >= 3:
                p = Polygon(ring)
                if p.is_valid and not p.is_empty:
                    out.append(p)
    return out


class WaterSpace:
    """The water on a 4 m raster: which body each cell is in, its surface, its depth (M16's
    bed rule, linear from a bank's toe), what keeps a hull off (banks' slopes, quays' bands,
    moored boats, columns and bridge piers standing in it)."""

    def __init__(self, model: dict, build: Path | None = None):
        W = P.WATER
        self.grid = g = Grid(model["bounds"], W["cell_m"])
        self.bodies = water_bodies(model)
        self.body = np.full((g.ny, g.nx), -1, dtype=np.int32)
        for k, b in enumerate(self.bodies):
            for p in b["polys"]:
                shapely.prepare(p)
                r = g.mask(p)
                if r is None:
                    continue
                j0, j1, i0, i1, m = r
                sub = self.body[j0:j1, i0:i1]
                sub[m & (sub < 0)] = k
        self.water = self.body >= 0
        kg = []
        banks_by = defaultdict(list)
        for bk in model.get("banks", []):
            if len(bk.get("line") or []) < 2:
                continue
            ln = LineString(bk["line"])
            banks_by[bk.get("water_id")].append((ln, float(bk.get("width_m") or 2.0),
                                                 float(bk.get("toe_m") or 1.0)))
            kg.append(ln.buffer(max(0.5, float(bk.get("width_m") or 2.0)), cap_style="flat"))
        for q in model.get("quays", []):
            if len(q.get("line") or []) >= 2:
                kg.append(LineString(q["line"]).buffer(float(q.get("width_m") or 4.0) / 2.0))
        self.moored = []
        for p in model.get("props", []):
            if p.get("type") != "prop.boat":
                continue
            x, y = float(p["position"][0]), float(p["position"][1])
            sc = p.get("scale") or [1.0, 1.0, 1.0]
            hull = _box(x, y, float(p.get("yaw_deg") or 0.0), 8.0 * float(sc[0]) + 0.6,
                        3.0 * float(sc[1]) + 0.6)
            self.moored.append(hull)
            kg.append(hull)
        for s in model.get("structures", []):
            if float(s.get("z0_m") or 0.0) > 0.5:
                continue
            p = _poly(s.get("footprint"))
            if p is not None and s.get("kind") in ("column", "pylon", "pier"):
                kg.append(p.buffer(0.5))
        for p in street_piers(build):
            kg.append(p.buffer(0.3))
        # (what keeps a hull off, as geometry: a kind's water is the water shrunk by its half
        # beam and margin less all this grown by as much, exactly, not by whole cells)
        self.keep_g = shapely.union_all(kg) if kg else Polygon()
        b = model["bounds"]
        self.mapbox = box(*b)
        polys = [p for bd in self.bodies for p in bd["polys"]]
        wg = shapely.union_all(polys) if polys else Polygon()
        self.water_g = wg.union(box(b[0] - 200, b[1] - 200, b[2] + 200, b[3] + 200)
                                .difference(self.mapbox))
        keep = np.zeros_like(self.water)
        g.paint(keep, self.keep_g)
        self.keep = keep
        self.nav = self.water & ~keep
        # (depth: by the nearest bank of the cell's own body, M16's rule made linear)
        self.depth = np.zeros((g.ny, g.nx))
        X, Y = np.meshgrid(g.xs, g.ys)
        for k, b in enumerate(self.bodies):
            cells = self.body == k
            if not cells.any():
                continue
            D = b["depth"]
            bed = b["ent"].get("bed") or {}
            bks = banks_by.get(b["id"]) or []
            if not bks:
                self.depth[cells] = D
                continue
            xs, ys = X[cells], Y[cells]
            tree = shapely.STRtree([q[0] for q in bks])
            pts = shapely.points(np.stack([xs, ys], axis=1))
            idx, dist = tree.query_nearest(pts, all_matches=False, return_distance=True)
            k_ = idx[1]
            w = np.array([q[1] for q in bks])[k_]
            toe = np.minimum(np.array([q[2] for q in bks])[k_], D)
            span = 4.0 if bed.get("profile") == "flat" else \
                np.maximum(1.0, float(bed.get("reach_m") or 60.0) - w)
            u = np.clip((dist - w) / span, 0.0, 1.0)
            self.depth[cells] = np.where(dist < w, 0.0, toe + (D - toe) * u)
        self.surf = np.zeros((g.ny, g.nx))
        for k, b in enumerate(self.bodies):
            self.surf[self.body == k] = b["surface"]
        self.cache = {}
        self.bridges = []
        for br in model.get("bridges", []):
            ln = br.get("line") or []
            if len(ln) >= 2 and br.get("water_class"):
                self.bridges.append((LineString([p[:2] for p in ln]).buffer(6.0),
                                     float(br.get("clearance_m") or 0.0), br["id"]))

    def navigable(self, kind: str) -> np.ndarray:
        if kind in self.cache:
            return self.cache[kind]
        k = V[kind]
        r = k["size"][1] / 2.0 + k["margin_m"]
        ng = self.water_g.buffer(-r, quad_segs=4)
        if not self.keep_g.is_empty:
            ng = ng.difference(self.keep_g.buffer(r, quad_segs=4))
        ng = ng.intersection(self.mapbox.buffer(-0.01))
        shapely.prepare(ng)
        m = np.zeros_like(self.water)
        self.grid.paint(m, ng)
        m &= self.water & (self.depth >= k["draft"] + 0.3)
        # (the cells too low under a bridge for its height over the water)
        for poly, clear, _ in self.bridges:
            if clear < k["size"][2] + P.WATER["bridge_pad_m"]:
                r_ = self.grid.mask(poly)
                if r_ is not None:
                    j0, j1, i0, i1, mm = r_
                    m[j0:j1, i0:i1][mm] = False
                    ng = ng.difference(poly)
        self.cache[kind] = m
        self.cache[("geom", kind)] = ng
        return m

    def near_water(self, kind: str, x: float, y: float, tol: float = 1.0) -> bool:
        """Whether a hull's middle at (x, y) is within `tol` of the kind's water (exactly: the
        raster's cells are 4 m)."""
        self.navigable(kind)
        return self.cache[("geom", kind)].distance(Point(x, y)) <= tol

    def cost(self, kind: str) -> np.ndarray:
        key = ("cost", kind)
        if key in self.cache:
            return self.cache[key]
        m = self.navigable(kind)
        lvl = np.zeros(m.shape)
        e = m
        for q in range(1, 6):
            e = erode(e, 1, True)
            lvl += e
        c = np.where(m, 1.0 + 1.5 * (1.0 - lvl / 5.0), np.inf)
        self.cache[key] = c
        return c

    def snap(self, kind: str, x: float, y: float, reach: float = 40.0):
        """The nearest cell middle the kind can be at, within `reach`."""
        m = self.navigable(kind)
        g = self.grid
        j, i = g.ij(x, y)
        r = int(math.ceil(reach / g.c))
        best = None
        for dj in range(-r, r + 1):
            for di in range(-r, r + 1):
                jj, ii = j + dj, i + di
                if 0 <= jj < g.ny and 0 <= ii < g.nx and m[jj, ii]:
                    d = dj * dj + di * di
                    if best is None or d < best[0]:
                        best = (d, jj, ii)
        if best is None:
            return None
        return g.xy(best[1], best[2])

    def ok_point(self, kind: str, x: float, y: float) -> bool:
        if not self.grid.inside(x, y):
            return True
        j, i = self.grid.ij(x, y)
        return bool(self.navigable(kind)[j, i])

    def z_at(self, x: float, y: float) -> float:
        if not self.grid.inside(x, y):
            return float(self.bodies[0]["surface"]) if self.bodies else 0.0
        j, i = self.grid.ij(x, y)
        return float(self.surf[j, i])

    def path(self, kind: str, a, b) -> list[tuple[float, float]] | None:
        c = self.cost(kind)
        g = self.grid
        cells = astar(c, g.ij(*a), g.ij(*b), pad=max(30, int(0.4 * math.dist(a, b) / g.c)),
                      limit=900000)
        if cells is None:
            return None
        pts = pull(g, c, cells, ends=(tuple(a), tuple(b)))
        r = max(V[kind]["turn_m"], 3.0) * 3.0

        def ok(arc):
            return all(self.ok_point(kind, x, y) for x, y in arc)
        return drop_close(fillet(pts, r, 3.0, ok))


def _water_route(ws: WaterSpace, rid: str, kind: str, waypoints, stops=None,
                 district=None) -> tuple[dict | None, str]:
    """An out and back route through `waypoints` (each a point the kind can be at): each way
    keeping right of the path's middle by the most of the kind's turn radius both ways fit,
    a turn round at each end; a kind with no turn radius (double-ended) runs back stern
    first. `stops` {waypoint index: (dwell, code, what)}."""
    legs = []
    for a, b in zip(waypoints, waypoints[1:]):
        p = ws.path(kind, a, b)
        if p is None:
            return None, f"no water for a {kind} from ({a[0]:.0f}, {a[1]:.0f}) to " \
                         f"({b[0]:.0f}, {b[1]:.0f})"
        legs.append(p)
    path = [legs[0][0]]
    wp_idx = [0]
    for lg in legs:
        path.extend(lg[1:])
        wp_idx.append(len(path) - 1)
    path = drop_close(path)
    # (indices of the waypoints in the dropped path)
    wp_idx = [min(range(len(path)), key=lambda q: math.dist(path[q], w)) for w in waypoints]
    rt = Route(rid, kind, district)
    stops = stops or {}
    d = V[kind]["turn_m"]
    if d > 0:
        dd = d
        while dd >= 0.5:
            out = offset(path, -dd)
            back = offset(path[::-1], -dd)
            turn_b = _half_turn(path[-1], _heading(path[-2], path[-1]), dd)
            turn_a = _half_turn(path[0], _heading(path[1], path[0]), dd)
            loop = out + turn_b + back + turn_a
            if all(ws.ok_point(kind, x, y) or ws.near_water(kind, x, y, 0.25)
                   for x, y in resample(loop + loop[:1], 2.0)):
                break
            dd /= 2.0
        else:
            d = 0.0
        if d > 0:
            n = len(path)
            for q, (x, y) in enumerate(out):
                rt.add([(x, y, ws.z_at(x, y))])
                for wi, w in enumerate(wp_idx):
                    if w == q and wi in stops and wi not in (0,):
                        rt.stop(*stops[wi])
            rt.add([(x, y, ws.z_at(x, y)) for x, y in turn_b])
            for q, (x, y) in enumerate(back):
                rt.add([(x, y, ws.z_at(x, y))])
                for wi, w in enumerate(wp_idx):
                    if n - 1 - q == w and wi in stops and wi != len(waypoints) - 1:
                        rt.stop(*stops[wi])
            rt.add([(x, y, ws.z_at(x, y)) for x, y in turn_a])
            if 0 in stops:
                rt.stops.insert(0, (0, *stops[0]))
            # (the end waypoint's stop, once: at the far turn's start)
            rec = finish(rt)
            return rec, "" if rec else "too short"
    # double-ended: there with the bow ahead, back stern first (each point's heading kept)
    yw = yaws([(x, y, 0.0) for x, y in path])
    for q, (x, y) in enumerate(path):
        rt.add([(x, y, ws.z_at(x, y))], yaw=yw[q])
        for wi, w in enumerate(wp_idx):
            if w == q and wi in stops and wi != 0:
                rt.stop(*stops[wi])
    for q in range(len(path) - 2, 0, -1):
        x, y = path[q]
        rt.add([(x, y, ws.z_at(x, y))], yaw=yw[q])
        for wi, w in enumerate(wp_idx):
            if w == q and wi in stops and wi not in (0, len(waypoints) - 1):
                rt.stop(*stops[wi])
    if 0 in stops:
        rt.stops.insert(0, (0, *stops[0]))
    rec = finish(rt)
    return rec, "" if rec else "too short"


def _half_turn(p, h: float, r: float, n: int = 10):
    """A half circle of radius r beyond point p (travelling on heading h) from its right side
    round to its left (the way back keeping right)."""
    cx, cy = p
    out = []
    for q in range(n + 1):
        a = h - math.pi / 2 + math.pi * q / n
        out.append((cx + r * math.cos(a), cy + r * math.sin(a)))
    return out


def piers(ws: WaterSpace, model: dict) -> tuple[list[dict], list[dict]]:
    """Piers (the ask `piers`, derived): a water taxi's at the middle of every quay (moved along
    it to where a taxi fits beside it), a ferry's at each end of a crossing of a river or
    channel where a walkway comes within `ferry_walk_m` of both shores; and what was left out."""
    W = P.WATER
    out, left = [], []
    walks = [w for w in model.get("walkways", []) if w.get("kind") in
             ("sidewalk", "promenade", "path", "pedestrian_street") and len(w.get("line") or []) >= 2]
    wtree = shapely.STRtree([LineString([p[:2] for p in w["line"]]) for w in walks]) if walks else None

    def walk_near(x, y, reach):
        if wtree is None:
            return None
        k, d = wtree.query_nearest(Point(x, y), return_distance=True, all_matches=False)
        if len(k) and float(d[0]) <= reach:
            return walks[int(k[0])]["id"]
        return None
    tk = V["taxi"]
    for q in sorted(model.get("quays", []), key=lambda q: q["id"]):
        ln = LineString([p[:2] for p in q["line"]])
        if ln.length < tk["size"][0] + 6.0:
            left.append({"id": q["id"], "why": "a quay shorter than a taxi's berth"})
            continue
        got = None
        # (from the quay's middle out along it every 8 m, the nearest place off its band a
        # taxi fits in: moored boats line most of a canal's quays)
        steps = int(ln.length / 16.0)
        base = float(q.get("width_m") or 4.0) / 2.0 + tk["size"][1] / 2.0 + tk["margin_m"] + 0.5
        for step in [0] + [v for k_ in range(1, steps + 1) for v in (k_, -k_)]:
            s = min(ln.length - 4.0, max(4.0, ln.length / 2.0 + step * 8.0))
            p = ln.interpolate(s)
            p2 = ln.interpolate(min(ln.length, s + 1.0))
            p1 = ln.interpolate(max(0.0, s - 1.0))
            h = _heading((p1.x, p1.y), (p2.x, p2.y))
            for off in (base, base + 1.5, base + 3.0):
                for sg in (1.0, -1.0):
                    x = p.x - math.sin(h) * off * sg
                    y = p.y + math.cos(h) * off * sg
                    if ws.grid.inside(x, y) and ws.ok_point("taxi", x, y):
                        got = (x, y, h)
                        break
                if got:
                    break
            if got:
                break
        if got is None:
            left.append({"id": q["id"], "why": "no water a taxi fits in beside it"})
            continue
        x, y, h = got
        near = next((o for o in out if math.dist(o["pos"][:2], (x, y)) < 30.0), None)
        if near is not None:
            left.append({"id": q["id"], "why": f"its pier would be {near['id']}'s (the quay "
                                               f"across the canal)"})
            continue
        j, i = ws.grid.ij(x, y)
        bid = ws.bodies[int(ws.body[j, i])]["id"] if ws.body[j, i] >= 0 else None
        out.append({"id": f"{q['id']}.pier", "kind": "taxi", "quay_id": q["id"], "bank_id": None,
                    "pos": [_r(x, 2), _r(y, 2), _r(ws.z_at(x, y), 2)],
                    "yaw_deg": _r(math.degrees(h) % 360.0, 2),
                    "berth_m": _r(tk["size"][0] + 4.0, 1),
                    "walkway_id": walk_near(p.x, p.y, 30.0), "water_id": bid,
                    "depth_m": _r(float(ws.depth[j, i]), 2)})
    # ferries: crossings of rivers and channels
    fk = V["ferry"]
    cross = []
    for b in ws.bodies:
        if b["kind"] not in ("river", "channel") or not b.get("centerline"):
            continue
        cl = LineString([p[:2] for p in b["centerline"]])
        s = W["ferry_spacing_m"] / 2.0
        while s < cl.length:
            c = cl.interpolate(s)
            c2 = cl.interpolate(min(cl.length, s + 2.0))
            c1 = cl.interpolate(max(0.0, s - 2.0))
            s += W["ferry_spacing_m"] / 3.0
            if not ws.grid.inside(c.x, c.y):
                continue
            h = _heading((c1.x, c1.y), (c2.x, c2.y))
            nx_, ny_ = -math.sin(h), math.cos(h)
            ends = []
            for sg in (1.0, -1.0):
                d = 0.0
                while d < 400.0:
                    x, y = c.x + nx_ * sg * d, c.y + ny_ * sg * d
                    if not ws.grid.inside(x, y):
                        break
                    j, i = ws.grid.ij(x, y)
                    if not ws.water[j, i]:
                        break
                    d += 2.0
                shore = (c.x + nx_ * sg * d, c.y + ny_ * sg * d)
                pier = None
                dd = d
                while dd > 0:
                    x, y = c.x + nx_ * sg * dd, c.y + ny_ * sg * dd
                    if ws.ok_point("ferry", x, y):
                        pier = (x, y)
                        break
                    dd -= 2.0
                wk = walk_near(*shore, W["ferry_walk_m"])
                ends.append((shore, pier, wk))
            (s0, p0, w0), (s1, p1_, w1) = ends
            if p0 is None or p1_ is None or w0 is None or w1 is None:
                continue
            if math.dist(p0, p1_) < W["ferry_min_m"]:
                continue
            cross.append((b["id"], s, p0, p1_, w0, w1, h))
    cross.sort(key=lambda c: _u("ferry", c[0], round(c[1])))
    keep = []
    for c in cross:
        if len(keep) >= W["ferry_max"]:
            break
        mid = ((c[2][0] + c[3][0]) / 2, (c[2][1] + c[3][1]) / 2)
        if any(math.dist(mid, ((k[2][0] + k[3][0]) / 2, (k[2][1] + k[3][1]) / 2)) <
               W["ferry_spacing_m"] for k in keep):
            continue
        keep.append(c)
    for bid, s, p0, p1_, w0, w1, h in keep:
        for p, w, sg in ((p0, w0, 1.0), (p1_, w1, -1.0)):
            j, i = ws.grid.ij(*p)
            yaw = math.degrees(h + sg * math.pi / 2.0 + math.pi) % 360.0
            out.append({"id": f"{bid}.pier.{_cell_id(*p)}", "kind": "ferry", "quay_id": None,
                        "bank_id": None, "pos": [_r(p[0], 2), _r(p[1], 2), _r(ws.z_at(*p), 2)],
                        "yaw_deg": _r(yaw, 2), "berth_m": _r(fk["size"][0] + 6.0, 1),
                        "walkway_id": w, "water_id": bid, "depth_m": _r(float(ws.depth[j, i]), 2),
                        "pair": None})
        out[-1]["pair"] = out[-2]["id"]
        out[-2]["pair"] = out[-1]["id"]
    out.sort(key=lambda p: p["id"])
    return out, left


def _edge_points(ws: WaterSpace, kind: str) -> list[tuple[float, float, float, float]]:
    """Where the kind's water meets the map's edge: (x, y, outward unit x, y), every 40 m."""
    m = ws.navigable(kind)
    g = ws.grid
    out = []
    step = max(1, int(40.0 / g.c))
    for i in range(0, g.nx, step):
        if m[0, i]:
            out.append((*g.xy(0, i), 0.0, -1.0))
        if m[g.ny - 1, i]:
            out.append((*g.xy(g.ny - 1, i), 0.0, 1.0))
    for j in range(0, g.ny, step):
        if m[j, 0]:
            out.append((*g.xy(j, 0), -1.0, 0.0))
        if m[j, g.nx - 1]:
            out.append((*g.xy(j, g.nx - 1), 1.0, 0.0))
    return out


def _water_ends(ws: WaterSpace, kind: str, line, reach: float):
    """A centerline's first and last points the kind can be at (within `reach` of a point of
    the line inside the map, from each end inward)."""
    pts = [p for p in resample([tuple(p[:2]) for p in line], 20.0)
           if ws.grid.inside(p[0], p[1])]
    a = b = None
    for p in pts:
        a = ws.snap(kind, p[0], p[1], reach)
        if a:
            break
    for p in reversed(pts):
        b = ws.snap(kind, p[0], p[1], reach)
        if b:
            break
    if a is None or b is None or math.dist(a, b) < 20.0:
        return None
    return a, b


def _longest_run(ws: WaterSpace, kind: str, line, reach: float):
    """Where a body is cut (a bridge's piers across a canal's channel): the longest stretch of
    its centerline a boat joins from one of its ends (points every 40 m, the farthest one a
    path reaches from each end), else None."""
    ln = LineString([p[:2] for p in line])
    pts = []
    s = 0.0
    while s <= ln.length:
        p = ln.interpolate(s)
        if ws.grid.inside(p.x, p.y):
            q = ws.snap(kind, p.x, p.y, reach)
            if q:
                pts.append((s, q))
        s += 40.0
    if len(pts) < 2:
        return None
    best = None
    for a, rng in ((pts[0], pts[:0:-1]), (pts[-1], pts[:-1])):
        for b in rng:
            if abs(b[0] - a[0]) < 2.0 * P.WATER["canal_min_m"] / 2.0 or \
                    (best and abs(b[0] - a[0]) <= best[0]):
                break
            if ws.path(kind, a[1], b[1]):
                best = (abs(b[0] - a[0]), a[1], b[1])
                break
    return (best[1], best[2]) if best else None


def ship_routes(ws: WaterSpace, model: dict) -> tuple[list[dict], list[dict]]:
    """Ships at the port: per berth (a megasite's `berth` lines, `WATER["berths"]` along each,
    and every harbor basin's middle) one coming in from past the map's edge on water deep and
    wide enough, lying at it, backing out (stern first: no turning basin yet); a berth no ship
    reaches has one lying at it. One more passes offshore between two far points of the map's
    edge on such water."""
    W = P.WATER
    k = V["ship"]
    berths = []
    for e in sorted(model.get("site_elements", []), key=lambda e: e["id"]):
        if e.get("kind") != "berth" or len(e.get("line") or []) < 2:
            continue
        ln = LineString([p[:2] for p in e["line"]])
        h = _heading(e["line"][0], e["line"][-1])
        for q in range(W["berths"]):
            s = ln.length * (q + 0.5) / W["berths"]
            p = ln.interpolate(s)
            for sg in (1.0, -1.0):
                off = k["size"][1] / 2.0 + 4.0
                x, y = p.x - math.sin(h) * off * sg, p.y + math.cos(h) * off * sg
                if ws.grid.inside(x, y):
                    j, i = ws.grid.ij(x, y)
                    if ws.water[j, i]:
                        berths.append((f"{e['id']}.{q}", (x, y), h))
                        break
    for w in model.get("waterways", []):
        if w.get("kind") == "basin" and len(w.get("centerline") or []) >= 2:
            ln = LineString([p[:2] for p in w["centerline"]])
            p = ln.interpolate(ln.length / 2.0)
            berths.append((f"{w['id']}.berth", (p.x, p.y), _heading(w["centerline"][0],
                                                                      w["centerline"][-1])))
    edges = _edge_points(ws, "ship")
    out, left = [], []
    for bid, bp, h in berths:
        rt = Route(f"water.ship.{bid}", "ship")
        rt.serves = [bid]
        snap = ws.snap("ship", *bp, 30.0)
        got = None
        if snap is not None and edges:
            for e in sorted(edges, key=lambda e: math.dist(e[:2], snap))[:6]:
                path = ws.path("ship", e[:2], snap)
                if path:
                    got = (e, path)
                    break
        if got is None:
            # (lying at its berth: a few meters along it and back over a long dwell)
            ux, uy = math.cos(h), math.sin(h)
            x, y = bp
            z = ws.z_at(x, y)
            yaw = math.degrees(h) % 360.0
            rt.add([(x - ux * 10, y - uy * 10, z)], yaw=yaw)
            rt.stop(3000.0, "berth", bid)
            rt.add([(x + ux * 10, y + uy * 10, z)], yaw=yaw)
            rt.stop(600.0, "berth", bid)
            rec = finish(rt)
            if rec:
                rec["moored"] = True
                out.append(rec)
            left.append({"id": bid, "why": "no water deep and wide enough for a ship reaches it "
                                           "from the map's edge: a ship lies at it"})
            continue
        e, path = got
        out_pt = (e[0] + e[2] * W["out_m"], e[1] + e[3] * W["out_m"])
        path = [out_pt] + path
        yw = yaws([(x, y, 0.0) for x, y in path])
        for q, (x, y) in enumerate(path):
            rt.add([(x, y, ws.z_at(x, y))], yaw=yw[q])
        rt.stop(k["dwell_s"], "berth", bid)
        for q in range(len(path) - 2, 0, -1):
            x, y = path[q]
            rt.add([(x, y, ws.z_at(x, y))], yaw=yw[q])
        rec = finish(rt)
        if rec:
            out.append(rec)
    # offshore: the two edge points farthest apart that a ship's water joins
    if edges:
        far = sorted(((math.dist(a[:2], b[:2]), a, b) for a in edges[::3] for b in edges[::3]),
                     key=lambda t: -t[0])
        for d, a, b in far[:8]:
            if d < 1500.0:
                break
            path = ws.path("ship", a[:2], b[:2])
            if not path:
                continue
            rt = Route("water.ship.offshore", "ship")
            pa = (a[0] + a[2] * W["out_m"], a[1] + a[3] * W["out_m"])
            pb = (b[0] + b[2] * W["out_m"], b[1] + b[3] * W["out_m"])
            z = ws.z_at(*a[:2])
            full = [pa] + path + [pb]
            # (back past the map: out from b, round and in to a, well beyond the edge)
            mx, my = (pa[0] + pb[0]) / 2.0, (pa[1] + pb[1]) / 2.0
            cx = sum(p[0] for p in path) / len(path)
            cy = sum(p[1] for p in path) / len(path)
            ox, oy = mx - cx, my - cy
            L = math.hypot(ox, oy) or 1.0
            back = (mx + ox / L * W["out_m"] * 3.0, my + oy / L * W["out_m"] * 3.0)
            full += [back]
            rt.add([(x, y, z) for x, y in full])
            rec = finish(rt)
            if rec:
                out.append(rec)
            break
    return out, left


def _district_of(polys, x: float, y: float) -> str | None:
    pt = Point(x, y)
    for did, p in polys:
        if p.covers(pt):
            return did
    best = None
    for did, p in polys:
        d = p.distance(pt)
        if best is None or d < best[0]:
            best = (d, did)
    return best[1] if best else None


def _pick(weights: dict, *salt) -> str | None:
    items = sorted((k, v) for k, v in weights.items() if v > 0)
    if not items:
        return None
    tot = sum(v for _, v in items)
    x = _u(*salt) * tot
    for k, v in items:
        x -= v
        if x < 0:
            return k
    return items[-1][0]


HOVER = ("kestrel_dart", "kestrel_meridian", "kestrel_atlas")
# (a flying car's underglow by its route: neon, read by night from afar)
CAR_GLOW = ("#21e6ff", "#ff2bd6", "#ffb21c", "#7dff3a", "#8a5bff", "#ff3b3b")
STANDIN_COLORS = {
    "drone": ["#f2f2f2", "#ff8a1c", "#ffd21c", "#1cc6ff"],
    "police": ["#1f3cff"], "media": ["#f4f4f4"], "aircraft": ["#e3e8ee"],
    "shuttle": ["#d8dade"],
    "boat": ["#c8402a", "#2a6fc8", "#e0c040", "#2aa070", "#f0f0f0", "#8a3ac8"],
    "taxi": ["#f2c200"], "ferry": ["#e8e8e8"],
    "ship": ["#a8322d", "#2d5aa8", "#2d8a5a", "#333a44"],
}


def _min_gap(rec: dict, n: int) -> float:
    """With n vehicles evenly round the route's cycle, the least distance along it between
    one and the one behind it (m; inf for one)."""
    if n < 2:
        return math.inf
    s = rec["samples"]
    dt = rec["sample_s"]
    R = rec["cycle_s"]
    L = rec["length_m"]
    H = R / n
    least = math.inf
    for j in range(0, len(s), 2):
        u = j * dt
        a = _at(s, dt, u % R)
        b = _at(s, dt, (u - H) % R)
        least = min(least, (a - b) % L)
    return least


def _at(samples, dt, u):
    j = u / dt
    k = int(math.floor(j))
    if k >= len(samples) - 1:
        return samples[-1]
    t = j - k
    return samples[k] + (samples[k + 1] - samples[k]) * t


def _fit(rec: dict, want: list[int]) -> list[int]:
    """The vehicles a band can run on a route: what is asked, fewer while two would come
    closer than the kind's spacing (a route's dwells bunch them)."""
    sp = V[rec["kind"]]["spacing_m"]
    out = []
    cache = {}
    for n in want:
        n = max(0, int(n))
        while n > 1:
            if n not in cache:
                cache[n] = _min_gap(rec, n)
            if cache[n] >= sp:
                break
            n -= 1
        out.append(n)
    return out


def airwater_plan(model: dict, filled: dict, build: Path | None = None,
                  obs=None) -> tuple[list[dict], list[dict], list[dict], dict]:
    """Every route of the city's air and water (records as `airwater.json` holds them), the
    pads, the piers, and what was left out with why."""
    A = P.AIR
    W = P.WATER
    ground = Ground(model)
    left = {"pads": [], "routes": [], "piers": [], "berths": []}
    polys = []
    for d in sorted(model.get("districts", []), key=lambda d: d["id"]):
        p = _poly(d.get("polygon"))
        if p is not None:
            polys.append((d["id"], p))
    fd = filled.get("districts") or {}
    akinds = (filled.get("air") or {}).get("kinds") or {}
    wkinds = (filled.get("water") or {}).get("kinds") or {}
    abusy = float(filled.get("air_busy", 1.0))
    wbusy = float(filled.get("water_busy", 1.0))

    def busy(did):
        return float((fd.get(did) or {}).get("busy", 1.0))
    routes = []
    pads = pads_of(model, ground)
    if any(akinds.get(k, 1.0) > 0 for k in AIRK):
        air = Air(model, ground, obs)
    # --- flying cars: pad pairs, then circuits by the districts' counts
    hover_all = {}
    for d, f in fd.items():
        for m, v in (f.get("fleet") or {}).items():
            if m in HOVER:
                hover_all[m] = hover_all.get(m, 0.0) + v

    def hover_model(did, salt):
        w = {m: v for m, v in ((fd.get(did) or {}).get("fleet") or {}).items() if m in HOVER}
        return _pick(w or hover_all or {HOVER[0]: 1.0}, "hover", salt) or HOVER[0]
    want_cars = {}
    for did, p in polys:
        area = p.area / 1e6
        w = float((fd.get(did) or {}).get("wealth", 0.5))
        want_cars[did] = [A["car_density"][b] * area * busy(did) * abusy * akinds.get("car", 1.0) *
                          (0.5 + w) for b in range(5)]
    have = defaultdict(lambda: [0.0] * 5)
    served = set()
    if akinds.get("car", 1.0) > 0:
        # (a pad something stands over, its building's crown mast on it, is left out)
        usable = []
        for p in pads:
            if p["kind"] == "launch_pad":
                continue
            top = p["pos"][2] + A["pad_over_m"] + 30.0
            if air.column_free(p["pos"][0], p["pos"][1], p["pos"][2], top):
                usable.append(p)
                continue
            what = air.over(p["pos"][0], p["pos"][1], p["pos"][2], top)
            left["pads"].append({"id": p["id"], "why": f"{what or 'something'} stands over it" +
                                 (" (its own building's crown: a citygen conflict)"
                                  if what == p.get("building_id") else "")})
        pairs = car_pairs(usable, 500.0, 2200.0)
        for q, (a, b) in enumerate(pairs[:A["routes_max"]["car"]]):
            rec, why = pad_route(air, a, b, int(2 * _u("hint", a["id"])) % 2)
            if rec is None:
                left["pads"].append({"id": a["id"], "why": why})
                left["pads"].append({"id": b["id"], "why": why})
                continue
            bad = _route_clear(air, rec, "car")
            if bad:
                left["pads"].append({"id": a["id"], "why": f"its flight meets something at {bad}"})
                continue
            did = a.get("district_id") or _district_of(polys, *a["pos"][:2])
            rec["district_id"] = did
            rec["model"] = hover_model(did, a["id"])
            rec["color"] = CAR_GLOW[int(_u("glow", rec["id"]) * len(CAR_GLOW)) % len(CAR_GLOW)]
            rec["counts"] = [1, 2, 2, 2, 1]
            served |= {a["id"], b["id"]}
            for bb in range(5):
                have[did][bb] += rec["counts"][bb]
            routes.append(rec)
        for p in pads:
            if p["kind"] != "launch_pad" and p["id"] not in served and \
                    not any(x["id"] == p["id"] for x in left["pads"]):
                left["pads"].append({"id": p["id"], "why": "no other pad to fly to within reach"})
        # circuits
        seg_nodes = defaultdict(set)
        for s in model.get("road_segments", []):
            if s.get("road_class") in ("avenue", "highway") and s.get("level", 0) == 0:
                seg_nodes[s.get("start")].add(s["id"])
                seg_nodes[s.get("end")].add(s["id"])
        nodes = [(n["id"], float(n["position"][0]), float(n["position"][1]))
                 for n in model.get("road_nodes", []) if n["id"] in seg_nodes]
        by_d = defaultdict(list)
        for n in nodes:
            by_d[_district_of(polys, n[1], n[2])].append(n)
        ncirc = 0
        for did, p in polys:
            need = [max(0.0, want_cars[did][b] - have[did][b]) for b in range(5)]
            k_need = int(math.ceil(max(need) / A["per_circuit"]))
            got = []
            tries = 0
            while len(got) < k_need and tries < k_need + 3 and \
                    ncirc < A["routes_max"]["car"] and len(by_d[did]) >= 3:
                rec = circuit(air, did, by_d[did], tries, int(4 * _u("ch", did, tries)) % 3)
                tries += 1
                if rec is None or any(r["id"] == rec["id"] for r in routes + got):
                    continue
                rec["model"] = hover_model(did, rec["id"])
                rec["color"] = CAR_GLOW[int(_u("glow", rec["id"]) * len(CAR_GLOW)) %
                                        len(CAR_GLOW)]
                got.append(rec)
                ncirc += 1
            for k, rec in enumerate(got):
                tot = [int(round(v)) for v in need]
                rec["counts"] = [tot[b] // len(got) + (1 if k < tot[b] % len(got) else 0)
                                 for b in range(5)]
                routes.append(rec)
            if k_need and not got:
                left["routes"].append({"id": f"air.lane.{did}", "why": "no circuit of three "
                                       "avenue or highway nodes clear on a layer"})
    # --- drones
    if akinds.get("drone", 1.0) > 0:
        hubs = drone_roofs(model, ground, *A["drone_hub_h_m"])
        drops = drone_roofs(model, ground, *A["drone_drop_h_m"])
        lo, hi = A["drone_reach_m"]
        nd = 0
        for did, p in polys:
            want = [A["drone_density"][b] * p.area / 1e6 * busy(did) * abusy *
                    akinds.get("drone", 1.0) for b in range(5)]
            k_need = int(math.ceil(max(want)))
            hs = sorted([h for h in hubs if h["district_id"] == did],
                        key=lambda h: _u("hub", h["id"]))
            got = 0
            for h in hs:
                if got >= k_need or nd >= A["routes_max"]["drone"]:
                    break
                ds = [d for d in drops if d["id"] != h["id"] and
                      lo <= math.dist(d["pos"][:2], h["pos"][:2]) <= hi]
                ds.sort(key=lambda d: _u("drop", h["id"], d["id"]))
                for d in ds[:2]:
                    rec = drone_route(air, h, d, int(3 * _u("dh", h["id"])) % 2)
                    if rec is None or _route_clear(air, rec, "drone"):
                        continue
                    rec["counts"] = [1 if got < round(want[b]) else 0 for b in range(5)]
                    rec["color"] = STANDIN_COLORS["drone"][int(_u("c", rec["id"]) * 4) % 4]
                    rec["model"] = "drone"
                    routes.append(rec)
                    got += 1
                    nd += 1
                    break
    # --- police and media
    if akinds.get("police", 1.0) > 0:
        zones = defaultdict(list)
        for z in model.get("zones", []):
            if z.get("kind") == "territory" and _poly(z.get("polygon")):
                zones[z.get("district_id")].append(_poly(z["polygon"]).representative_point())
        npol = 0
        for did, p in polys:
            dg = float((fd.get(did) or {}).get("danger", 0.3))
            n = int(round(A["police"]["base"] + A["police"]["danger"] * dg *
                          akinds.get("police", 1.0)))
            c0 = p.representative_point()
            centers = [(c0.x, c0.y)] + [(q.x, q.y) for q in zones.get(did, [])]
            for k in range(n):
                if npol >= A["routes_max"]["police"]:
                    break
                cs = centers[k % len(centers):] + centers[:k % len(centers)]
                rec = orbit(air, f"air.police.{did}.{k}", "police", did, cs, A["police_r_m"],
                            A["police_m"][k % 2::2] + A["police_m"], k)
                if rec is None:
                    left["routes"].append({"id": f"air.police.{did}.{k}",
                                           "why": "no orbit clear over the district"})
                    continue
                rec["counts"] = [1 if k < max(1, round(n * A["police"]["band"][b])) else 0
                                 for b in range(5)]
                rec["model"] = "kestrel_meridian" if "kestrel_meridian" in hover_all or \
                    not hover_all else sorted(hover_all)[0]
                rec["color"] = STANDIN_COLORS["police"][0]
                routes.append(rec)
                npol += 1
    if akinds.get("media", 1.0) > 0:
        tall = sorted(model.get("buildings", []), key=lambda b: (-float(b.get("height_m") or 0.0),
                                                                  b["id"]))
        cs = []
        for b in [b for b in tall if b.get("landmark")] + tall[:6]:
            p = _poly(b.get("footprint"))
            if p is not None:
                c = p.representative_point()
                cs.append((c.x, c.y, float(b.get("height_m") or 0.0)))
        for k in range(min(A["routes_max"]["media"], int(round(A["media"] * akinds.get("media", 1.0))))):
            if not cs:
                break
            x, y, hgt = cs[k % len(cs)]
            alts = [z for z in A["media_m"]]
            rec = orbit(air, f"air.media.{k}", "media", _district_of(polys, x, y),
                        [(x, y)] + [(c[0], c[1]) for c in cs if c[:2] != (x, y)][:3],
                        A["media_r_m"], alts, k)
            if rec is None:
                left["routes"].append({"id": f"air.media.{k}", "why": "no orbit clear"})
                continue
            rec["counts"] = [1, 1, 1, 1, 1]
            rec["model"] = "media"
            rec["color"] = STANDIN_COLORS["media"][0]
            routes.append(rec)
    # --- aircraft and shuttles
    if akinds.get("aircraft", 1.0) > 0:
        for rec in overflights(model, min(A["routes_max"]["aircraft"],
                                          int(round(A["aircraft"] * akinds.get("aircraft", 1.0))))):
            rec["counts"] = [1, 2, 2, 2, 2]
            rec["model"] = "aircraft"
            rec["color"] = STANDIN_COLORS["aircraft"][0]
            routes.append(rec)
    if akinds.get("shuttle", 1.0) > 0:
        for p in [p for p in pads if p["kind"] == "launch_pad"][:A["routes_max"]["shuttle"]]:
            rec, why = shuttle(air, p, model)
            if rec is None:
                left["pads"].append({"id": p["id"], "why": why})
                continue
            rec["counts"] = [1, 1, 1, 1, 1]
            rec["model"] = "shuttle"
            rec["color"] = STANDIN_COLORS["shuttle"][0]
            rec["district_id"] = _district_of(polys, *p["pos"][:2])
            routes.append(rec)
    # --- the water
    ws = WaterSpace(model, build)
    pier_rows, pleft = piers(ws, model)
    left["piers"] += pleft
    if wkinds.get("boat", 1.0) > 0:
        for b in ws.bodies:
            if not b.get("centerline") or b["kind"] in ("basin",):
                continue
            ends = _water_ends(ws, "boat", b["centerline"], 30.0 if b["kind"] == "canal" else 80.0)
            if ends is None:
                left["routes"].append({"id": f"water.boat.{b['id']}",
                                       "why": "no water a boat fits in at its ends"})
                continue
            did = _district_of(polys, *ends[0])
            rec, why = _water_route(ws, f"water.boat.{b['id']}", "boat", list(ends), district=did)
            if rec is None:
                # (cut by a bridge's piers: the longest stretch a boat joins from an end)
                run = _longest_run(ws, "boat", b["centerline"],
                                   30.0 if b["kind"] == "canal" else 80.0)
                if run is not None:
                    rec, why2 = _water_route(ws, f"water.boat.{b['id']}", "boat", list(run),
                                             district=did)
                    if rec is not None:
                        rec["cut"] = why
            if rec is None:
                left["routes"].append({"id": f"water.boat.{b['id']}", "why": why})
                continue
            if b["kind"] in ("river", "channel"):
                km = rec["length_m"] / 2000.0
                rec["counts"] = [max(1, int(round(W["boat_per_km"][q] * km * busy(did) * wbusy *
                                                  wkinds.get("boat", 1.0)))) for q in range(5)]
            else:
                if rec["length_m"] < 2.0 * W["canal_min_m"]:
                    left["routes"].append({"id": rec["id"], "why": "a canal too short"})
                    continue
                rec["counts"] = [1] * 5
            rec["water_id"] = b["id"]
            rec["model"] = "boat"
            rec["color"] = STANDIN_COLORS["boat"][int(_u("c", rec["id"]) * 6) % 6]
            routes.append(rec)
    if wkinds.get("taxi", 1.0) > 0:
        taxi = [p for p in pier_rows if p["kind"] == "taxi"]
        chain = []
        if taxi:
            rest = sorted(taxi, key=lambda p: _u("taxi", p["id"]))
            cur = rest.pop(0)
            chain.append(cur)
            while rest:
                rest.sort(key=lambda p: (math.dist(p["pos"][:2], cur["pos"][:2]), p["id"]))
                cur = rest.pop(0)
                chain.append(cur)
        tour = W["taxi_tour"]
        groups = [chain[q:q + tour] for q in range(0, len(chain), tour)]
        if groups and len(groups[-1]) == 1 and len(groups) > 1:
            last = groups.pop()
            groups[-1] += last
        for grp in groups:
            if len(grp) < 2:
                left["routes"].append({"id": f"water.taxi.{grp[0]['id']}", "why": "a lone pier"})
                continue
            wps = [tuple(p["pos"][:2]) for p in grp]
            stops = {q: (V["taxi"]["dwell_s"], "pier", p["id"]) for q, p in enumerate(grp)}
            did = _district_of(polys, *wps[0])
            rec, why = _water_route(ws, f"water.taxi.{grp[0]['id']}", "taxi", wps, stops, did)
            if rec is None and len(grp) > 2:
                rec, why = _water_route(ws, f"water.taxi.{grp[0]['id']}", "taxi", wps[:2],
                                        {0: stops[0], 1: stops[1]}, did)
            if rec is None:
                left["routes"].append({"id": f"water.taxi.{grp[0]['id']}", "why": why})
                continue
            rec["serves"] = [p["id"] for p in grp]
            rec["counts"] = list(W["taxi_band"])
            rec["model"] = "taxi"
            rec["color"] = STANDIN_COLORS["taxi"][0]
            routes.append(rec)
    if wkinds.get("ferry", 1.0) > 0:
        fer = {p["id"]: p for p in pier_rows if p["kind"] == "ferry"}
        for pid in sorted(fer):
            a = fer[pid]
            if a["pair"] is None or a["pair"] < pid:
                continue
            b = fer[a["pair"]]
            stops = {0: (V["ferry"]["dwell_s"], "pier", a["id"]),
                     1: (V["ferry"]["dwell_s"], "pier", b["id"])}
            did = _district_of(polys, *a["pos"][:2])
            rec, why = _water_route(ws, f"water.ferry.{a['id']}", "ferry",
                                    [tuple(a["pos"][:2]), tuple(b["pos"][:2])], stops, did)
            if rec is None:
                left["routes"].append({"id": f"water.ferry.{a['id']}", "why": why})
                continue
            rec["serves"] = [a["id"], b["id"]]
            rec["counts"] = [1] * 5
            rec["model"] = "ferry"
            rec["color"] = STANDIN_COLORS["ferry"][0]
            routes.append(rec)
    if wkinds.get("ship", 1.0) > 0:
        srecs, sleft = ship_routes(ws, model)
        left["berths"] += sleft
        for rec in srecs:
            rec["counts"] = [1] * 5
            rec["model"] = "ship"
            rec["color"] = STANDIN_COLORS["ship"][int(_u("c", rec["id"]) * 4) % 4]
            rec["district_id"] = _district_of(polys, *rec["points"][0][:2]) \
                if ws.grid.inside(*rec["points"][0][:2]) else None
            routes.append(rec)
    # (ids unique: a later route with an id taken gets .2, .3, ...)
    seen = defaultdict(int)
    for rec in routes:
        seen[rec["id"]] += 1
        if seen[rec["id"]] > 1:
            rec["id"] = f"{rec['id']}.{seen[rec['id']]}"
    for rec in routes:
        if rec.get("district_id") is None and rec["kind"] not in ("aircraft",):
            p0 = rec["points"][0]
            if ws.grid.inside(p0[0], p0[1]):
                rec["district_id"] = _district_of(polys, p0[0], p0[1])
        rec["counts"] = _fit(rec, rec["counts"])
        rec["vehicle_ids"] = [f"{rec['id']}.{k}" for k in range(max(rec["counts"]))]
    routes.sort(key=lambda r: (AW_ORDER[r["kind"]], r["id"]))
    for p in pads:
        p["served"] = p["id"] in served or any(p["id"] in r["serves"] for r in routes)
    ctx = {"air": air if any(akinds.get(k, 1.0) > 0 for k in AIRK) else None, "water": ws,
           "ground": ground}
    return routes, pads, pier_rows, {"left": left, "ctx": ctx}


AW_ORDER = {k: q for q, k in enumerate(P.AW_KINDS)}


def records(routes: list[dict]) -> list[dict]:
    """The records `airwater.json` holds (the profile's grids left out)."""
    return [{k: v for k, v in r.items() if not k.startswith("_")} for r in routes]


def plan_record(routes, pads, pier_rows, left, hour: int) -> dict:
    """The plan's `airwater` (without its hash): per kind its routes and vehicles by band;
    the pads and piers served; what was left out."""
    b = P.band_of(hour)
    kinds = {}
    for k in P.AW_KINDS:
        rs = [r for r in routes if r["kind"] == k]
        kinds[k] = {"routes": len(rs),
                    "vehicles_by_band": [sum(r["counts"][q] for r in rs) for q in range(5)],
                    "vehicles_at_hour": sum(r["counts"][b] for r in rs),
                    "length_m": _r(sum(r["length_m"] for r in rs), 1)}
    air = [sum(kinds[k]["vehicles_by_band"][q] for k in P.AIR_KINDS) for q in range(5)]
    water = [sum(kinds[k]["vehicles_by_band"][q] for k in P.WATER_KINDS) for q in range(5)]
    return {"hour": hour, "vehicles": {k: dict(v) for k, v in sorted(V.items())},
            "settings": {"air": dict(P.AIR), "water": dict(P.WATER)},
            "kinds": kinds,
            "totals": {"routes": len(routes), "air_by_band": air, "water_by_band": water,
                       "air_at_hour": air[b], "water_at_hour": water[b],
                       "pads": len(pads), "pads_served": sum(1 for p in pads if p.get("served")),
                       "piers": len(pier_rows),
                       "piers_served": sum(1 for p in pier_rows
                                           if any(p["id"] in r["serves"] for r in routes)),
                       "left_out": left}}


# ---------------------------------------------------------------------------
# Checks
# ---------------------------------------------------------------------------

def checks(routes: list[dict], pads: list[dict], pier_rows: list[dict], extra: dict) -> dict:
    out = {}
    ctx = extra["ctx"]
    air, ws = ctx["air"], ctx["water"]
    left = extra["left"]
    # air_lanes
    bad = []
    nair = 0
    for r in routes:
        if r["kind"] not in P.AIR_KINDS or air is None:
            continue
        nair += 1
        why = _route_clear(air, r, r["kind"])
        if why:
            bad.append(f"{r['id']}: meets an obstacle at {why}")
    layers = sorted({round(p[2]) for r in routes if r["kind"] == "car" for p in r["points"][1:-1:7]})
    out["air_lanes"] = {"ok": not bad, "detail": (
        f"{nair} flight routes clear of the masses, roof items, skybridges, sky tubes, transit "
        f"lines, structures and signs by their kind's margin (cars {V['car']['margin_m']:g} m, "
        f"drones {V['drone']['margin_m']:g} m), read every 4 m" if not bad else "; ".join(bad[:6]))}
    # air_pads
    bad = []
    for r in routes:
        for e in r["events"]:
            if EVENT_CODES[e[2]] in ("pad", "launch"):
                pid = e[3]
                pad = next((p for p in pads if p["id"] == pid), None)
                if pad is None:
                    bad.append(f"{r['id']}: lands at {pid}, no such pad")
                    continue
                if not any(math.dist(pt[:3], pad["pos"]) < 0.5 for pt in r["points"]):
                    bad.append(f"{r['id']}: never reaches {pid}")
    srv = sum(1 for p in pads if p.get("served"))
    out["air_pads"] = {"ok": not bad, "detail": (
        f"{srv} of {len(pads)} pads flown from and to, each landing on its pad" +
        (f"; left out: {', '.join(x['id'] + ' (' + x['why'] + ')' for x in left['pads'][:3])}"
         + (f" and {len(left['pads']) - 3} more" if len(left['pads']) > 3 else "")
         if left["pads"] else "") if not bad else "; ".join(bad[:6]))}
    # water_lanes
    bad = []
    nw = 0
    for r in routes:
        if r["kind"] not in P.WATER_KINDS:
            continue
        nw += 1
        pts = [p[:2] for p in r["points"]]
        for x, y in resample(pts, 2.0):
            if ws.grid.inside(x, y) and not ws.ok_point(r["kind"], x, y) and \
                    not ws.near_water(r["kind"], x, y):
                bad.append(f"{r['id']}: off its water at ({x:.0f}, {y:.0f})")
                break
        for p in r["points"]:
            if ws.grid.inside(p[0], p[1]) and abs(p[2] - ws.z_at(p[0], p[1])) > 0.01:
                bad.append(f"{r['id']}: not at the water's surface at ({p[0]:.0f}, {p[1]:.0f})")
                break
    out["water_lanes"] = {"ok": not bad, "detail": (
        f"{nw} boat routes on water their hulls clear by their margins (banks' slopes, quays, "
        f"moored boats, piers, columns), {V['boat']['draft']:g} to {V['ship']['draft']:g} m "
        f"of draft under them, under every bridge with room; {len(pier_rows)} piers derived" +
        (f"; left out: {', '.join(x['id'] for x in (left['routes'] + left['berths'])[:4])}"
         if [x for x in left["routes"] if x["id"].startswith("water")] or left["berths"]
         else "") if not bad else "; ".join(bad[:6]))}
    # airwater_timing
    bad = []
    for r in routes:
        k = V[r["kind"]]
        s, dt = r["samples"], r["sample_s"]
        vs = [(s[j + 1] - s[j]) / dt for j in range(len(s) - 1)]
        if min(vs, default=0.0) < -1e-6:
            bad.append(f"{r['id']}: runs backward")
        if max(vs, default=0.0) > k["cruise"] * 1.02 + 0.05:
            bad.append(f"{r['id']}: {max(vs):.1f} m/s over its {k['cruise']} m/s")
        over = max((v - lim for v, lim in zip(r["_v"], r["_lim"])), default=0.0)
        if over > 1e-6:
            bad.append(f"{r['id']}: {over:.2f} m/s over a turn's limit")
        if abs(s[-1] - r["length_m"]) > max(0.5, k["cruise"] * dt) or abs(s[0]) > 0.01:
            bad.append(f"{r['id']}: its cycle does not come round")
        if math.dist(r["points"][0][:3], r["points"][-1][:3]) > 0.02:
            bad.append(f"{r['id']}: not closed")
        for e in r["events"]:
            if e[1] - e[0] < 1.0:
                bad.append(f"{r['id']}: a dwell of {e[1] - e[0]:.1f} s")
        for b, n in enumerate(r["counts"]):
            if n > 1 and _min_gap(r, n) < k["spacing_m"] - 1e-6:
                bad.append(f"{r['id']} {P.BANDS[b]}: {n} vehicles closer than {k['spacing_m']} m")
    out["airwater_timing"] = {"ok": not bad, "detail": (
        f"{len(routes)} routes closed, within their kinds' speeds, turns, climbs, acceleration "
        f"and braking, dwells kept, vehicles on a route their kind's spacing apart"
        if not bad else "; ".join(bad[:6]))}
    # airwater_budget
    B = P.AW_BUDGET
    fl = [sum(r["counts"][b] for r in routes if r["kind"] in ("car", "police", "media",
                                                                "aircraft", "shuttle"))
          for b in range(5)]
    dr = [sum(r["counts"][b] for r in routes if r["kind"] == "drone") for b in range(5)]
    bo = [sum(r["counts"][b] for r in routes if r["kind"] in P.WATER_KINDS) for b in range(5)]
    ok = max(fl) <= B["fliers"] and max(dr) <= B["drones"] and max(bo) <= B["boats"]
    out["airwater_budget"] = {"ok": ok, "detail": (
        f"at most {max(fl)} fliers, {max(dr)} drones and {max(bo)} boats at once (budget "
        f"{B['fliers']}, {B['drones']}, {B['boats']})")}
    return out


# ---------------------------------------------------------------------------
# The preview
# ---------------------------------------------------------------------------

KIND_COLORS = {"car": "#28e0ff", "drone": "#ffd21c", "police": "#4d6bff", "media": "#ffffff",
               "aircraft": "#b8c0cc", "shuttle": "#ff8a1c", "boat": "#3ce07a", "taxi": "#f2c200",
               "ferry": "#ff4fd8", "ship": "#ff4a4a"}


def position(r: dict, u: float):
    """Where a route's vehicle is u seconds into its cycle (x, y, z)."""
    s = _at(r["samples"], r["sample_s"], u % r["cycle_s"])
    pts = r["points"]
    cum = [0.0]
    for a, b in zip(pts, pts[1:]):
        cum.append(cum[-1] + math.dist(a[:3], b[:3]))
    k = max(0, min(len(cum) - 2, bisect.bisect_right(cum, s) - 1))
    a, b = pts[k], pts[k + 1]
    seg = cum[k + 1] - cum[k]
    t = 0.0 if seg <= 0 else (s - cum[k]) / seg
    return tuple(a[i] + (b[i] - a[i]) * t for i in range(3))


def preview(model: dict, routes: list[dict], pads: list[dict], pier_rows: list[dict],
            hour: int, path: Path) -> str | None:
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        return None
    b = P.band_of(hour)
    fig = plt.figure(figsize=(18, 9.5), dpi=100)
    fig.patch.set_facecolor("#0c111a")
    bb = model.get("bounds") or [-1, -1, 1, 1]
    for col, which in enumerate(("air", "water")):
        ax = fig.add_axes([0.02 + col * 0.49, 0.04, 0.46, 0.88])
        ax.set_facecolor("#0c111a")
        for w in water_bodies(model):
            for p in w["polys"]:
                xs, ys = p.exterior.xy
                ax.fill(xs, ys, color="#13314a", lw=0)
        for d in model.get("districts", []):
            ring = (d.get("polygon") or {}).get("exterior") or []
            if ring:
                xs, ys = zip(*(ring + ring[:1]))
                ax.plot(xs, ys, color="#2c3443", lw=0.8)
        if which == "air":
            for bld in model.get("buildings", []):
                if float(bld.get("height_m") or 0.0) >= 60.0:
                    p = _poly(bld.get("footprint"))
                    if p is not None and p.geom_type == "Polygon":
                        xs, ys = p.exterior.xy
                        ax.fill(xs, ys, color="#39404e", lw=0)
        kinds = P.AIR_KINDS if which == "air" else P.WATER_KINDS
        for k in kinds:
            rs = [r for r in routes if r["kind"] == k]
            for r in rs:
                xs = [p[0] for p in r["points"]]
                ys = [p[1] for p in r["points"]]
                ax.plot(xs, ys, color=KIND_COLORS[k], lw=0.6 if k in ("car", "drone") else 1.1,
                        alpha=0.75)
            n = sum(r["counts"][b] for r in rs)
            ax.plot([], [], color=KIND_COLORS[k], lw=2, label=f"{k}: {len(rs)} routes, {n} at "
                                                              f"{hour}:00")
            for r in rs:
                nv = r["counts"][b]
                for q in range(nv):
                    x, y, _ = position(r, q * r["cycle_s"] / nv + 37.0)
                    ax.plot(x, y, "o", ms=3.5 if k != "drone" else 2.0, color="#ffffff",
                            mec=KIND_COLORS[k], mew=1.0)
        if which == "air":
            for p in pads:
                ax.plot(p["pos"][0], p["pos"][1], "s", ms=4,
                        color="#ff3cac" if p.get("served") else "#555555")
        else:
            for p in pier_rows:
                ax.plot(p["pos"][0], p["pos"][1], "^", ms=6,
                        color=KIND_COLORS["taxi" if p["kind"] == "taxi" else "ferry"],
                        mec="#000000", mew=0.5)
        ax.set_xlim(bb[0], bb[2])
        ax.set_ylim(bb[1], bb[3])
        ax.set_aspect("equal")
        ax.tick_params(colors="#9aa6bd")
        for sp in ax.spines.values():
            sp.set_color("#3a4253")
        ax.set_title(("air routes, pads (served pink) and fliers" if which == "air" else
                      "water routes, piers and boats") + f" at {hour}:00", color="#e6ecf7")
        ax.legend(facecolor="#141a26", labelcolor="#e6ecf7", edgecolor="#3a4253", fontsize=8,
                  loc="lower left")
    tmp = path.with_suffix(".tmp.png")
    fig.savefig(tmp, facecolor=fig.get_facecolor())
    plt.close(fig)
    data = tmp.read_bytes()
    tmp.unlink()
    if path.is_file() and path.read_bytes() == data:
        return None
    path.write_bytes(data)
    return str(path)
