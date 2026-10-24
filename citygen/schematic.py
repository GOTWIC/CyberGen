"""2D debug schematic of a filled spec (`citygen spec render`).

A quick, deterministic picture of what the spec asks for: coast form, rivers and delta branches,
islands, a rough district layout solved from the placement constraints, highway pattern,
transit routes by mode, megasites, landmarks and named places, with a legend. It is a review
aid for the spec session, not the M1 generator: shapes are coarse and nothing here is reused
by generation.
"""

from __future__ import annotations

import heapq
import math
from dataclasses import dataclass, field

import matplotlib

matplotlib.use("Agg")
import matplotlib.patheffects as pe  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from matplotlib.lines import Line2D  # noqa: E402
from matplotlib.patches import Patch  # noqa: E402
from shapely import affinity, contains_xy  # noqa: E402
from shapely.geometry import LineString, Point, Polygon, box  # noqa: E402
from shapely.ops import nearest_points, unary_union  # noqa: E402

from . import presets  # noqa: E402
from .defaults import derive_seed  # noqa: E402
from .geom import edge_point  # noqa: E402
from .spec import EXIT_RE, CitySpec  # noqa: E402

ARCHETYPE_COLORS = {
    "corporate_core": "#4f7cff",
    "megablock_residential": "#9b6bff",
    "midtown_mixed": "#ffb347",
    "entertainment_market": "#ff4fc3",
    "old_town": "#e8833a",
    "industrial_port": "#d94848",
    "residential_heights": "#6cc46c",
    "research_campus": "#c7d4e8",
    "transit_hub": "#e8e8e8",
    "spaceport": "#62d6e8",
}
SEA = "#0a1a2e"
RIVER = "#1d5a85"
LAND = "#262b38"
BG = "#05080f"
INK = "#f2f4f8"
MUTED = "#8a93a6"
HIGHWAY = "#d9d9d9"

MEGASITE_MARKERS = {
    "spaceport": "*", "skyport": "v", "transit_nexus": "H", "freight_terminal": "s",
    "stadium": "o", "arcology": "^", "temple_complex": "P", "central_park": "o",
    "grand_plaza": "D", "attraction": "p",
}
MODE_LABELS = {
    "metro": "metro (underground)", "elevated_rail": "elevated rail", "monorail": "monorail",
    "maglev": "maglev", "sky_tube": "sky tube",
}

HALO = [pe.withStroke(linewidth=3, foreground=BG)]


@dataclass
class Layout:
    canvas: Polygon
    sea: object
    water: object
    land: object
    rivers: list[tuple[str, LineString, list[LineString], object]] = field(default_factory=list)
    islands: dict[str, Polygon] = field(default_factory=dict)
    districts: dict[str, object] = field(default_factory=dict)
    seeds: dict[str, tuple[float, float]] = field(default_factory=dict)
    anchors: dict[str, tuple[float, float]] = field(default_factory=dict)
    exits: dict[str, tuple[float, float]] = field(default_factory=dict)
    frame: tuple[float, float, float, float] = (1, 0, 0, 1)  # sea direction u and perp v
    ext: float = 1.0


# ---------------------------------------------------------------------------
# Geometry helpers
# ---------------------------------------------------------------------------

def _parts(geom) -> list[Polygon]:
    if geom.is_empty:
        return []
    if isinstance(geom, Polygon):
        return [geom]
    return [g for g in getattr(geom, "geoms", []) if isinstance(g, Polygon)]


def _edge_point(canvas: Polygon, direction: str, offset: float = 0.0) -> tuple[float, float]:
    """Where a ray from the center in `direction` meets the canvas edge, slid by `offset`."""
    ux, uy = presets.DIRECTION_VECTORS[direction]
    minx, miny, maxx, maxy = canvas.bounds
    far = 4 * max(maxx - minx, maxy - miny)
    hit = LineString([(0, 0), (ux * far, uy * far)]).intersection(canvas.exterior)
    p = hit if isinstance(hit, Point) else list(hit.geoms)[0]
    x, y = p.x - uy * offset, p.y + ux * offset
    return (min(max(x, minx), maxx), min(max(y, miny), maxy))


def _wavy_halfplane(t: float, big: float, amp: float, rng: np.random.Generator) -> Polygon:
    """{a > t + noise(b)} in the canonical frame (a toward the sea, b along the coast)."""
    phases = rng.uniform(0, 2 * math.pi, 3)
    bs = np.linspace(-big, big, 240)
    a = t + amp * (np.sin(bs / big * 7 + phases[0]) * 0.6 + np.sin(bs / big * 17 + phases[1]) * 0.3
                   + np.sin(bs / big * 31 + phases[2]) * 0.1)
    pts = list(zip(a, bs)) + [(big * 3, big), (big * 3, -big)]
    return Polygon(pts)


def _blob(center: tuple[float, float], r: float, rng: np.random.Generator, n: int = 48) -> Polygon:
    ph = rng.uniform(0, 2 * math.pi, 3)
    pts = []
    for k in range(n):
        th = 2 * math.pi * k / n
        rr = r * (1 + 0.12 * math.sin(3 * th + ph[0]) + 0.07 * math.sin(5 * th + ph[1])
                  + 0.04 * math.sin(9 * th + ph[2]))
        pts.append((center[0] + rr * math.cos(th), center[1] + rr * math.sin(th)))
    return Polygon(pts)


def _sea_canonical(form: str, k: float, ext: float, half_b: float, big: float,
                   rng_seed: int, extra_islands: int = 5) -> object:
    """Sea in the canonical frame; `k` in [0, 1] grows the sea (solved for the sea share).

    Straight, delta and archipelago coasts move the shoreline inland with `k`; a peninsula keeps
    a mainland band behind its neck and narrows with `k`; bays and crescents keep a thin strip of
    open sea and grow the bay itself, so land stays on both flanks of the bay.
    """
    rng = np.random.default_rng(rng_seed)
    amp = 0.035 * ext
    if form in ("bay", "crescent"):
        t = 0.8 * ext
        base = _wavy_halfplane(t, big, amp, rng)
        if form == "bay":
            bay = affinity.scale(Point(t, 0).buffer(1), 1.6 * ext * k, 1.1 * half_b * k)
        else:
            bay = Point(t + 0.3 * ext * k, 0).buffer(1.3 * half_b * k)
        return base.union(bay)
    if form == "peninsula":
        # Mainland band behind a fixed neck; `k` narrows the peninsula.
        neck = -0.45 * ext
        w = max(0.08, 0.6 * (1 - k)) * half_b
        tip = 0.8 * ext
        pen = Polygon([(neck - ext, -w * 1.15), (tip, -w * 0.8), (tip, w * 0.8),
                       (neck - ext, w * 1.15)]).union(Point(tip, 0).buffer(w * 0.8))
        return _wavy_halfplane(neck, big, amp, rng).difference(pen)
    t = ext * (1 - 2 * k)
    base = _wavy_halfplane(t, big, amp, rng)
    span = max(ext - t, 0.05 * ext)
    if form == "delta":
        lobe = affinity.scale(Point(t, 0).buffer(1), 0.45 * span, 0.4 * half_b)
        return base.difference(lobe)
    if form == "archipelago":
        isl = []
        for _ in range(extra_islands):
            a = rng.uniform(t + 0.2 * span, t + 0.85 * span)
            b = rng.uniform(-0.75 * half_b, 0.75 * half_b)
            isl.append(_blob((a, b), rng.uniform(0.07, 0.12) * half_b, rng))
        return base.difference(unary_union(isl)) if isl else base
    return base  # straight


def build_sea(spec: CitySpec, canvas: Polygon) -> tuple[object, tuple, float]:
    coast = spec.water.coast
    ux, uy = presets.DIRECTION_VECTORS[coast.side]
    vx, vy = -uy, ux
    corners = list(canvas.exterior.coords)[:4]
    ext = max(x * ux + y * uy for x, y in corners)
    half_b = max(abs(x * vx + y * vy) for x, y in corners)
    big = 4 * max(ext, half_b)
    seed = derive_seed(spec.seed, "schematic.coast")
    target = coast.sea_share * canvas.area
    # Archipelagos get filler islands only where the spec names few islands of its own.
    extra = max(0, 5 - 2 * len(spec.water.islands))

    def sea_for(k: float):
        g = _sea_canonical(coast.form, k, ext, half_b, big, seed, extra)
        g = affinity.affine_transform(g, [ux, vx, uy, vy, 0, 0])
        return g.intersection(canvas)

    lo, hi = 0.0, 1.0
    for _ in range(24):  # bisection so the sea share matches the spec
        mid = (lo + hi) / 2
        if sea_for(mid).area < target:
            lo = mid
        else:
            hi = mid
    return sea_for((lo + hi) / 2), (ux, uy, vx, vy), ext


# ---------------------------------------------------------------------------
# Water
# ---------------------------------------------------------------------------

def _meander(a: tuple, b: tuple, amount: float, rng: np.random.Generator) -> LineString:
    ax, ay = a
    bx, by = b
    length = math.hypot(bx - ax, by - ay) or 1.0
    nx, ny = -(by - ay) / length, (bx - ax) / length
    ts = np.linspace(0, 1, 80)
    ph = rng.uniform(0, 2 * math.pi, 3)
    wav = (np.sin(ts * 2 * math.pi * 1.5 + ph[0]) + 0.5 * np.sin(ts * 2 * math.pi * 3.5 + ph[1])
           + 0.25 * np.sin(ts * 2 * math.pi * 6 + ph[2]))
    off = amount * 0.06 * length * wav * np.sin(math.pi * ts)
    xs = ax + (bx - ax) * ts + nx * off
    ys = ay + (by - ay) * ts + ny * off
    return LineString(list(zip(xs, ys)))


def _coastline(sea, canvas: Polygon):
    return sea.boundary.difference(canvas.exterior.buffer(1.0))


def _first_sea_hit(start: tuple, aim: tuple, sea, coast_line) -> tuple[float, float]:
    """Where the straight path from `start` toward `aim` first reaches the sea, a little past
    the shore; the nearest shore point if it never does."""
    seg = LineString([start, aim])
    hit = seg.intersection(sea)
    if hit.is_empty:
        return nearest_points(coast_line, Point(aim))[0].coords[0]
    d = seg.project(nearest_points(hit, Point(start))[0])
    return seg.interpolate(d + 0.04 * seg.length).coords[0]


def _order_rivers(rivers):
    names = {r.name for r in rivers}
    done: list = []
    pending = list(rivers)
    while pending:
        for r in list(pending):
            if r.to not in names or r.to in {d.name for d in done}:
                done.append(r)
                pending.remove(r)
                break
        else:  # cycle (validation forbids it); keep order
            done += pending
            break
    return done


def build_water(spec: CitySpec, lay: Layout) -> None:
    canvas, sea = lay.canvas, lay.sea
    ux, uy, vx, vy = lay.frame
    coast_line = _coastline(sea, canvas)
    water_parts = [sea]
    branch_water: list = []
    by_name: dict[str, LineString] = {}
    rivers = spec.water.rivers
    same_side: dict[str, list[str]] = {}
    for r in rivers:
        same_side.setdefault(r.from_, []).append(r.name)
    edge_len = max(canvas.bounds[2] - canvas.bounds[0], canvas.bounds[3] - canvas.bounds[1])
    for r in _order_rivers(rivers):
        rng = np.random.default_rng(derive_seed(spec.seed, "schematic.river", r.name))
        group = same_side[r.from_]
        k = group.index(r.name)
        start = _edge_point(canvas, r.from_, (k - (len(group) - 1) / 2) * 0.28 * edge_len)
        if r.from_at is not None:
            start = edge_point(canvas, r.from_, r.from_at)
        if r.to in by_name:
            end = by_name[r.to].interpolate(0.55, normalized=True).coords[0]
        elif r.to in presets.DIRECTIONS:
            end = _edge_point(canvas, r.to) if r.to_at is None else \
                edge_point(canvas, r.to, r.to_at)
        elif coast_line.is_empty:
            end = _edge_point(canvas, presets.opposite(r.from_))
        else:
            if r.to_at is not None:
                aim = edge_point(canvas, spec.water.coast.side, r.to_at)
            elif r.to == "bay":
                aim = (ux * lay.ext * 0.8, uy * lay.ext * 0.8)
            else:
                aim = (start[0] + ux * 2 * lay.ext, start[1] + uy * 2 * lay.ext)
            end = _first_sea_hit(start, aim, sea, coast_line)
        line = _meander(start, end, r.meander, rng)
        width = sum(r.width_m) / 2
        branches = []
        if r.delta_branches and not coast_line.is_empty:
            # Split past the middle (where mid_river islands sit) and fan out along the coast.
            split = line.interpolate(0.7, normalized=True).coords[0]
            for j in range(r.delta_branches):
                side = 1 if j % 2 == 0 else -1
                spread = (j // 2 + 1) * 0.3 * lay.ext * side
                aim = Point(end[0] + vx * spread, end[1] + vy * spread)
                tgt = nearest_points(coast_line, aim)[0].coords[0]
                tgt = (tgt[0] + ux * 0.04 * lay.ext, tgt[1] + uy * 0.04 * lay.ext)
                branches.append(_meander(split, tgt, r.meander * 0.6, rng))
        poly = line.buffer(width / 2)
        for b in branches:
            branch_water.append(b.buffer(width * 0.3))
            poly = poly.union(branch_water[-1])
        by_name[r.name] = line
        lay.rivers.append((r.name, line, branches, poly))
        water_parts.append(poly)

    water = unary_union(water_parts).intersection(canvas)
    land = canvas.difference(water)
    for isl in spec.water.islands:
        rng = np.random.default_rng(derive_seed(spec.seed, "schematic.island", isl.name))
        r = math.sqrt(isl.area_km2 * 1e6 / math.pi)
        taken = unary_union([p.buffer(0.05 * lay.ext + 0.3 * r) for p in lay.islands.values()])
        poly = _place_island(isl, r, lay, by_name, sea.difference(taken), rng)
        if poly is None:
            continue
        if isl.setting in ("mid_river", "delta"):
            ring_w = 0.7 * sum(next(x for x in rivers if x.name == isl.river).width_m) / 2
            water = water.union(poly.buffer(ring_w)).intersection(canvas)
        water = water.difference(poly)
        lay.islands[isl.name] = poly
    # Delta branches cut through islands at the mouth: islands lie between the channels.
    branches = unary_union(branch_water) if branch_water else None
    if branches is not None:
        water = water.union(branches).intersection(canvas)
        lay.islands = {n: max(_parts(p.difference(branches)), key=lambda g: g.area)
                       for n, p in lay.islands.items() if not p.difference(branches).is_empty}
    lay.water = water
    lay.land = canvas.difference(water)


def _place_island(isl, r, lay: Layout, rivers: dict, sea, rng) -> Polygon | None:
    if isl.setting in ("mid_river", "delta") and isl.river in rivers:
        line = rivers[isl.river]
        at = 0.9 if isl.setting == "delta" else 0.5
        if isl.position != "center" and isl.setting == "mid_river":
            dx, dy = presets.DIRECTION_VECTORS[isl.position]
            aim = Point(dx * lay.ext * 0.5, dy * lay.ext * 0.5)
            at = line.project(nearest_points(line, aim)[0], normalized=True)
            at = min(max(at, 0.15), 0.85)
        c = line.interpolate(at, normalized=True).coords[0]
        return _blob(c, r, rng)
    gap = 0.03 * lay.ext if isl.setting == "nearshore" else 0.08 * lay.ext
    # The map edge is not a shore: islands may sit near it, so only real coasts keep the gap.
    beyond = lay.canvas.buffer(4 * lay.ext, join_style="mitre").difference(lay.canvas)
    inner = sea.union(beyond).buffer(-(r + gap)).intersection(lay.canvas.buffer(-1.05 * r))
    if inner.is_empty:
        inner = sea.buffer(-r * 0.6)
        if inner.is_empty:
            return None
    if isl.position == "center":
        aim = Point(lay.frame[0] * lay.ext, lay.frame[1] * lay.ext)
    else:
        dx, dy = presets.DIRECTION_VECTORS[isl.position]
        aim = Point(dx * lay.ext * (0.45 if isl.setting == "nearshore" else 0.7),
                    dy * lay.ext * (0.45 if isl.setting == "nearshore" else 0.7))
    c = nearest_points(inner, aim)[0].coords[0]
    return _blob(c, r, rng).intersection(lay.canvas)


# ---------------------------------------------------------------------------
# Districts: seeds from the placement constraints, then a weighted raster partition
# ---------------------------------------------------------------------------

def _resolve(spec: CitySpec, ref: str) -> str | None:
    """Name of the district a reference lives in (or the island name)."""
    for d in spec.districts:
        if d.name == ref or any(p.name == ref for p in d.places) or \
                any(m.name == ref for m in d.megasites):
            return d.name
    return None


def solve_seeds(spec: CitySpec, lay: Layout) -> None:
    rng = np.random.default_rng(derive_seed(spec.seed, "schematic.seeds"))
    mainland = lay.land
    for poly in lay.islands.values():
        mainland = mainland.difference(poly.buffer(1.0))
    land_area = max(lay.land.area, 1.0)
    radius = {d.name: math.sqrt(d.area_share * land_area / math.pi) for d in spec.districts}
    coast = _coastline(lay.sea, lay.canvas)
    pts: dict[str, np.ndarray] = {}
    fixed: set[str] = set()
    targets: dict[str, np.ndarray] = {}
    minx, miny, maxx, maxy = lay.canvas.bounds
    for d in spec.districts:
        pl = d.placement
        if pl.on_island and pl.on_island in lay.islands:
            c = lay.islands[pl.on_island].representative_point()
            pts[d.name] = np.array([c.x, c.y])
            fixed.add(d.name)
            continue
        if pl.edge == "center":
            targets[d.name] = np.array([0.0, 0.0])
        elif pl.edge:
            ex, ey = _edge_point(lay.canvas, pl.edge)
            targets[d.name] = np.array([ex, ey]) * 0.62
        pts[d.name] = targets.get(d.name, np.array(
            [rng.uniform(minx, maxx) * 0.5, rng.uniform(miny, maxy) * 0.5]))

    islands_c = {n: np.array(p.representative_point().coords[0]) for n, p in lay.islands.items()}

    def pos(ref: str) -> np.ndarray | None:
        name = _resolve(spec, ref)
        if name:
            return pts[name]
        return islands_c.get(ref)

    rivers = {name: line for name, line, _, _ in lay.rivers}
    steps = 400
    for it in range(steps):
        k = 0.5 * (1 - it / steps) + 0.05
        moves = {n: np.zeros(2) for n in pts}
        for d in spec.districts:
            a = d.name
            pl = d.placement
            for direction, ref in pl.relations():
                b = _resolve(spec, ref)
                pb = pos(ref)
                if pb is None or b == a:
                    continue
                u = np.array(presets.DIRECTION_VECTORS[direction])
                margin = 0.7 * (radius[a] + radius.get(b, radius[a]))
                viol = margin - float((pts[a] - pb) @ u)
                if viol > 0:
                    moves[a] += u * viol * 0.5
                    if b in moves:
                        moves[b] -= u * viol * 0.5
            for ref in pl.adjacent_to:
                pb = pos(ref)
                b = _resolve(spec, ref)
                if pb is None or b == a:
                    continue
                gap = np.linalg.norm(pts[a] - pb) - (radius[a] + radius.get(b, radius[a]))
                if gap > 0:
                    dvec = (pb - pts[a]) / (np.linalg.norm(pb - pts[a]) + 1e-9)
                    moves[a] += dvec * gap * 0.3
            if a in targets:
                moves[a] += (targets[a] - pts[a]) * 0.3
            if pl.coast is not None and not coast.is_empty:
                p = Point(*pts[a])
                q = np.array(nearest_points(coast, p)[0].coords[0])
                dist = np.linalg.norm(pts[a] - q)
                if pl.coast and dist > 0.8 * radius[a]:
                    moves[a] += (q - pts[a]) * (1 - 0.8 * radius[a] / dist) * 0.4
                elif pl.coast is False and dist < 1.6 * radius[a]:
                    moves[a] += (pts[a] - q) / (dist + 1e-9) * (1.6 * radius[a] - dist) * 0.4
            if pl.along_river in rivers:
                q = np.array(nearest_points(rivers[pl.along_river], Point(*pts[a]))[0].coords[0])
                moves[a] += (q - pts[a]) * 0.2
        names = list(pts)
        for i, a in enumerate(names):  # spread districts apart
            for b in names[i + 1:]:
                dvec = pts[a] - pts[b]
                dist = np.linalg.norm(dvec) + 1e-9
                want = 0.85 * (radius[a] + radius[b])
                if dist < want:
                    push = dvec / dist * (want - dist) * 0.25
                    moves[a] += push
                    moves[b] -= push
        for n in names:
            if n in fixed:
                continue
            pts[n] = pts[n] + moves[n] * k
            p = Point(*pts[n])
            if not mainland.contains(p) and not mainland.is_empty:
                inner = mainland.buffer(-0.3 * radius[n])
                ref = inner if not inner.is_empty else mainland
                pts[n] = np.array(nearest_points(ref, p)[0].coords[0])
    lay.seeds = {n: (float(p[0]), float(p[1])) for n, p in pts.items()}


def partition(spec: CitySpec, lay: Layout) -> None:
    """Grow every district from its seed over a land raster until it holds its area share.

    Growth only steps between neighboring land cells, so rivers and channels become district
    boundaries on their own and every district stays in one piece. Districts on islands only
    grow on their island; mainland districts never take island cells.
    """
    minx, miny, maxx, maxy = lay.canvas.bounds
    n_cells = 110
    cell = max(maxx - minx, maxy - miny) / n_cells
    nx, ny = int(math.ceil((maxx - minx) / cell)), int(math.ceil((maxy - miny) / cell))
    xs = minx + cell / 2 + cell * np.arange(nx)
    ys = miny + cell / 2 + cell * np.arange(ny)
    gx, gy = np.meshgrid(xs, ys)  # [row = y, col = x]
    on_land = contains_xy(lay.land, gx, gy)
    region = np.full(gx.shape, "", dtype=object)
    for name, poly in lay.islands.items():
        region[contains_xy(poly, gx, gy) & on_land] = name

    names = [d.name for d in spec.districts]
    allowed = [d.placement.on_island if d.placement.on_island in lay.islands else ""
               for d in spec.districts]
    target = np.zeros(len(names))
    for reg in set(allowed):
        idx = [i for i, r in enumerate(allowed) if r == reg]
        cells = int(np.sum(on_land & (region == reg)))
        tot = sum(spec.districts[i].area_share for i in idx) or 1.0
        for i in idx:
            target[i] = cells * spec.districts[i].area_share / tot

    owner = np.full(gx.shape, -1)
    counts = np.zeros(len(names))
    heap: list[tuple[float, int, int, int]] = []

    def expand(i: int, r: int, c: int) -> None:
        sx, sy = lay.seeds[names[i]]
        for dr, dc in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            rr, cc = r + dr, c + dc
            if 0 <= rr < ny and 0 <= cc < nx and owner[rr, cc] < 0 and on_land[rr, cc] \
                    and region[rr, cc] == allowed[i]:
                d = math.hypot(gx[rr, cc] - sx, gy[rr, cc] - sy)
                heapq.heappush(heap, (d, i, rr, cc))

    for i, n in enumerate(names):
        sx, sy = lay.seeds[n]
        ok = on_land & (region == allowed[i]) & (owner < 0)
        if not ok.any():
            continue
        d2 = (gx - sx) ** 2 + (gy - sy) ** 2
        d2[~ok] = np.inf
        r, c = np.unravel_index(np.argmin(d2), d2.shape)
        lay.seeds[n] = (float(gx[r, c]), float(gy[r, c]))
        owner[r, c] = i
        counts[i] = 1

    for capped in (True, False):
        # First pass grows each district up to its share; the second hands land left over
        # (cut off behind full districts) to a neighbor, without caps.
        heap.clear()
        for r, c in zip(*np.nonzero(owner >= 0)):
            expand(int(owner[r, c]), int(r), int(c))
        while heap:
            _, i, r, c = heapq.heappop(heap)
            if owner[r, c] >= 0 or (capped and counts[i] >= target[i]):
                continue
            owner[r, c] = i
            counts[i] += 1
            expand(i, r, c)

    half = cell / 2
    for i, n in enumerate(names):
        sel = owner == i
        if not sel.any():
            continue
        cells = [box(x - half, y - half, x + half, y + half) for x, y in zip(gx[sel], gy[sel])]
        poly = unary_union(cells).buffer(cell * 0.6).buffer(-cell * 0.6)
        lay.districts[n] = poly.simplify(cell * 0.5).intersection(lay.land)


def build_anchors(spec: CitySpec, lay: Layout) -> None:
    for d in spec.districts:
        poly = lay.districts.get(d.name)
        if poly is None or poly.is_empty:
            c = lay.seeds[d.name]
        else:
            p = Point(lay.seeds[d.name])
            c = (p if poly.contains(p) else poly.representative_point()).coords[0]
        lay.anchors[d.name] = c
        r = math.sqrt(max(poly.area if poly is not None else 0, 1.0) / math.pi)
        others = [*d.places, *d.megasites, *d.landmarks]
        for k, item in enumerate(others):
            name = item.name
            if getattr(item, "position", None) not in (None, "center", "waterfront") or \
                    getattr(item, "edge", None) not in (None, "center"):
                direction = getattr(item, "position", None) or getattr(item, "edge", None)
                dx, dy = presets.DIRECTION_VECTORS[direction]
                rr = 0.55 * r
            else:
                ang = math.radians(90 + 360 * (k + 0.5) / max(len(others), 1))
                dx, dy = math.cos(ang), math.sin(ang)
                rr = 0.45 * r
            q = Point(c[0] + dx * rr, c[1] + dy * rr)
            if poly is not None and not poly.is_empty and not poly.contains(q):
                q = nearest_points(poly.buffer(-0.1 * r) if not poly.buffer(-0.1 * r).is_empty
                                   else poly, q)[0]
            if name:
                lay.anchors.setdefault(name, (q.x, q.y))
    for name, poly in lay.islands.items():
        lay.anchors.setdefault(name, poly.representative_point().coords[0])
    for direction in presets.DIRECTIONS:
        lay.exits[f"{direction}_exit"] = _edge_point(lay.canvas, direction)


def build_layout(spec: CitySpec) -> Layout:
    w, h = spec.size_km[0] * 1000, spec.size_km[1] * 1000
    canvas = box(-w / 2, -h / 2, w / 2, h / 2)
    sea, frame, ext = build_sea(spec, canvas)
    lay = Layout(canvas=canvas, sea=sea, water=sea, land=canvas.difference(sea), frame=frame,
                 ext=ext)
    build_water(spec, lay)
    solve_seeds(spec, lay)
    partition(spec, lay)
    build_anchors(spec, lay)
    return lay


# ---------------------------------------------------------------------------
# Drawing
# ---------------------------------------------------------------------------

def _draw_geom(ax, geom, face, edge="none", lw=0.0, alpha=1.0, z=1, ls="-") -> None:
    from matplotlib.patches import PathPatch
    from matplotlib.path import Path as MPath

    for poly in _parts(geom):
        verts, codes = [], []
        for ring in [poly.exterior, *poly.interiors]:
            coords = list(ring.coords)
            verts += coords
            codes += [MPath.MOVETO] + [MPath.LINETO] * (len(coords) - 2) + [MPath.CLOSEPOLY]
        ax.add_patch(PathPatch(MPath(verts, codes), facecolor=face, edgecolor=edge, lw=lw,
                               alpha=alpha, zorder=z, linestyle=ls))


def _point(lay: Layout, ref: str) -> tuple[float, float] | None:
    if EXIT_RE.match(ref):
        return lay.exits[ref]
    return lay.anchors.get(ref)


def _offset_path(pts: list[tuple[float, float]], off: float) -> list[tuple[float, float]]:
    if off == 0 or len(pts) < 2:
        return pts
    line = LineString(pts)
    try:
        shifted = line.offset_curve(off, join_style="mitre", mitre_limit=2.0)
        if shifted.geom_type == "LineString" and len(shifted.coords) >= 2:
            return list(shifted.coords)
    except Exception:  # noqa: BLE001 (degenerate offset)
        pass
    return pts


def draw_highways(ax, spec: CitySpec, lay: Layout) -> None:
    hw = spec.highways
    ux, uy, vx, vy = lay.frame
    r = 0.3 * min(lay.canvas.bounds[2], lay.canvas.bounds[3])
    lines = []
    center = (0.0, 0.0)
    if hw.pattern in ("ring", "ring_plus_spine"):
        lines.append(Point(center).buffer(r).exterior)
    if hw.pattern in ("spine", "ring_plus_spine"):
        far = 3 * lay.ext
        lines.append(LineString([(-ux * far, -uy * far), (ux * far, uy * far)]))
    if hw.pattern == "grid":
        for s in (-0.35, 0.35):
            lines.append(LineString([(-3 * lay.ext, s * lay.ext * 2), (3 * lay.ext, s * lay.ext * 2)]))
            lines.append(LineString([(s * lay.ext * 2, -3 * lay.ext), (s * lay.ext * 2, 3 * lay.ext)]))
    if hw.pattern == "radial":
        for d in presets.DIRECTIONS[::2]:
            lines.append(LineString([center, _edge_point(lay.canvas, d)]))
    if hw.pattern == "coastal":
        coast = _coastline(lay.sea, lay.canvas)
        if not coast.is_empty:
            lines.append(affinity.translate(coast, -ux * 0.12 * lay.ext, -uy * 0.12 * lay.ext))
    if hw.pattern != "none":
        for e in hw.exits or []:
            ex, ey = _edge_point(lay.canvas, e)
            start = (ex * 0.25, ey * 0.25) if hw.pattern in ("spine", "coastal", "grid") else \
                (ex / math.hypot(ex, ey) * r, ey / math.hypot(ex, ey) * r)
            lines.append(LineString([start, (ex, ey)]))
            ax.annotate(f"{e} exit", (ex, ey), color=HIGHWAY, fontsize=7, ha="center",
                        va="center", path_effects=HALO, zorder=9)
    for line in lines:
        clipped = line.intersection(lay.land.buffer(0.01 * lay.ext))
        for seg in getattr(clipped, "geoms", [clipped]):
            if seg.is_empty or seg.geom_type != "LineString":
                continue
            xs, ys = seg.xy
            ax.plot(xs, ys, color=HIGHWAY, lw=2.2, alpha=0.55, zorder=4, solid_capstyle="round")
    for h in hw.named:
        pts = [p for p in (_point(lay, ref) for ref in h.route) if p]
        if len(pts) >= 2:
            xs, ys = zip(*pts)
            ax.plot(xs, ys, color=HIGHWAY, lw=2.6, alpha=0.8, zorder=4)
            mx, my = LineString(pts).interpolate(0.5, normalized=True).coords[0]
            ax.text(mx, my, h.name, color=HIGHWAY, fontsize=7, style="italic", zorder=9,
                    path_effects=HALO, ha="center")


def draw_transit(ax, spec: CitySpec, lay: Layout) -> None:
    scale = max(lay.canvas.bounds[2], lay.canvas.bounds[3])
    for k, line in enumerate(spec.transit.lines):
        pts = [p for p in (_point(lay, ref) for ref in line.route) if p]
        if len(pts) < 2:
            continue
        off = (k - (len(spec.transit.lines) - 1) / 2) * 0.012 * scale
        path = _offset_path(pts, off)
        xs, ys = zip(*path)
        c = line.color
        if line.mode == "metro":
            ax.plot(xs, ys, color=c, lw=2.0, ls=(0, (5, 3)), zorder=6)
        elif line.mode == "elevated_rail":
            ax.plot(xs, ys, color=c, lw=3.0, zorder=6)
            ax.plot(xs, ys, color=BG, lw=1.0, ls=(0, (1, 3)), zorder=6)
        elif line.mode == "monorail":
            ax.plot(xs, ys, color=c, lw=2.6, ls=(0, (1, 1.5)), zorder=6)
        elif line.mode == "maglev":
            ax.plot(xs, ys, color=c, lw=3.6, zorder=6, solid_capstyle="round")
        else:  # sky_tube
            ax.plot(xs, ys, color=c, lw=6, alpha=0.45, zorder=7, solid_capstyle="round")
            ax.plot(xs, ys, color="white", lw=1.0, zorder=7)
        sx, sy = zip(*pts)
        ax.scatter(sx, sy, s=26, facecolor=BG, edgecolor=c, lw=1.6, zorder=8)
        lx, ly = LineString(path).interpolate(0.18 + 0.1 * (k % 3), normalized=True).coords[0]
        ax.text(lx, ly, line.name, color=c, fontsize=7.5, fontweight="bold", zorder=11,
                path_effects=HALO, ha="center", va="bottom")


def draw_bridges(ax, spec: CitySpec, lay: Layout) -> None:
    for b in spec.water.bridges.named:
        a, c = (_point(lay, r) for r in b.connects)
        if not a or not c:
            continue
        seg = LineString([a, c])
        crossing = seg.intersection(lay.water)
        mid = crossing.centroid if not crossing.is_empty else seg.interpolate(0.5, normalized=True)
        ax.plot([a[0], c[0]], [a[1], c[1]], color="#f5e6a8", lw=1.0, ls=":", alpha=0.8, zorder=5)
        ax.scatter([mid.x], [mid.y], marker="$═$", s=160, color="#f5e6a8", zorder=10)
        ax.text(mid.x, mid.y, "  " + b.name, color="#f5e6a8", fontsize=7, zorder=11,
                path_effects=HALO, va="top")


def draw_labels(ax, spec: CitySpec, lay: Layout) -> None:
    for d in spec.districts:
        x, y = lay.anchors[d.name]
        ax.text(x, y, d.name.upper(), color=INK, fontsize=9, fontweight="bold", ha="center",
                va="center", zorder=12, path_effects=[pe.withStroke(linewidth=3.5, foreground=BG)])
        ax.text(x, y, f"\n\n{d.archetype} {d.area_share:.0%}", color=MUTED, fontsize=6.5,
                ha="center", va="center", zorder=12, path_effects=HALO)
        for p in d.places:
            px, py = lay.anchors[p.name]
            water = p.kind in ("canal", "creek", "marina", "pier", "docks", "waterfront", "beach")
            green = p.kind in ("park", "garden")
            col = "#7fd6ff" if water else "#8be38b" if green else "#ffe27a"
            ax.scatter([px], [py], marker="d", s=22, color=col, zorder=10, edgecolor=BG, lw=0.5)
            ax.text(px, py, " " + p.name, color=col, fontsize=6.5, zorder=11, path_effects=HALO,
                    va="center")
        for lm in d.landmarks:
            px, py = lay.anchors[lm.name]
            ax.scatter([px], [py], marker="^", s=70, color="#ffffff", zorder=10, edgecolor=BG)
            ax.text(px, py, f" {lm.name} ({lm.height_m:g} m)", color=INK, fontsize=6.5,
                    zorder=11, path_effects=HALO, va="bottom")
        for m in d.megasites:
            px, py = lay.anchors[m.name]
            rr = math.sqrt(m.area_km2 * 1e6 / math.pi)
            _draw_geom(ax, Point(px, py).buffer(rr), face="none", edge="#ffffff", lw=0.8,
                       alpha=0.7, z=9, ls="--")
            ax.scatter([px], [py], marker=MEGASITE_MARKERS[m.kind], s=110, color="#ffffff",
                       zorder=10, edgecolor=BG, lw=0.6)
            label = f"[{m.kind}]" if m.name == d.name else f"{m.name}\n[{m.kind}]"
            ax.text(px, py - rr * 0.15, label, color="#ffffff", fontsize=6.5,
                    ha="center", va="top", zorder=11, path_effects=HALO)
    for name, poly in lay.islands.items():
        if any(d.placement.on_island == name for d in spec.districts if d.name == name):
            continue
        c = poly.representative_point()
        ax.text(c.x, c.y - 0.05 * lay.ext, name, color="#bcd7e8", fontsize=7, style="italic",
                ha="center", va="top", zorder=11, path_effects=HALO)
    for name, line, _, _ in lay.rivers:
        x, y = line.interpolate(0.35, normalized=True).coords[0]
        ax.text(x, y, name, color="#8cc8f0", fontsize=7.5, style="italic", zorder=11,
                path_effects=HALO, ha="center")
    coast = spec.water.coast
    if coast.name:
        pt = _open_water_point(lay)
        ax.text(pt.x, pt.y, coast.name.upper(), color="#5f8fb8", fontsize=10, ha="center",
                zorder=3, style="italic")


def _open_water_point(lay: Layout) -> Point:
    """A point in open sea, far from land and toward the sea side, for the sea label."""
    ux, uy = lay.frame[0], lay.frame[1]
    minx, miny, maxx, maxy = lay.canvas.bounds
    best, best_score = lay.sea.representative_point(), -math.inf
    land = lay.land.boundary
    for x in np.linspace(minx, maxx, 24)[1:-1]:
        for y in np.linspace(miny, maxy, 24)[1:-1]:
            p = Point(x, y)
            near_scale_bar = x < minx + 0.4 * (maxx - minx) and y < miny + 0.1 * (maxy - miny)
            if near_scale_bar or not lay.water.contains(p):
                continue
            score = min(land.distance(p), 0.25 * lay.ext) + 0.1 * (x * ux + y * uy)
            if score > best_score:
                best, best_score = p, score
    return best


def draw_legend(lax, spec: CitySpec) -> None:
    lax.axis("off")
    handles = [Patch(facecolor=SEA, edgecolor="#5f8fb8", label=f"sea ({spec.water.coast.form}, "
                     f"{spec.water.coast.side})"),
               Patch(facecolor=RIVER, label="rivers, delta branches"),
               Patch(facecolor=LAND, edgecolor="#bcd7e8", ls="--", label="island / unassigned land"),
               Line2D([], [], color=HIGHWAY, lw=2.2, alpha=0.6,
                      label=f"highways ({spec.highways.pattern})")]
    for arch in dict.fromkeys(d.archetype for d in spec.districts):
        handles.append(Patch(facecolor=ARCHETYPE_COLORS[arch], alpha=0.6, label=arch))
    styles = {"metro": dict(ls=(0, (5, 3)), lw=2), "elevated_rail": dict(lw=3),
              "monorail": dict(ls=(0, (1, 1.5)), lw=2.6), "maglev": dict(lw=3.6),
              "sky_tube": dict(lw=5, alpha=0.6)}
    for line in spec.transit.lines:
        handles.append(Line2D([], [], color=line.color, **styles[line.mode],
                              label=f"{line.name}: {MODE_LABELS[line.mode]}, "
                                    f"{line.altitude_m[0]:g} to {line.altitude_m[1]:g} m"))
    kinds = list(dict.fromkeys(m.kind for d in spec.districts for m in d.megasites))
    for kind in kinds:
        handles.append(Line2D([], [], marker=MEGASITE_MARKERS[kind], color="white", ls="none",
                              markersize=8, label=f"megasite: {kind} (dashed = area)"))
    handles += [
        Line2D([], [], marker="^", color="white", ls="none", markersize=7, label="landmark"),
        Line2D([], [], marker="d", color="#ffe27a", ls="none", markersize=6, label="named place"),
        Line2D([], [], marker="$═$", color="#f5e6a8", ls="none", markersize=9,
               label="named bridge"),
        Line2D([], [], marker="o", color=BG, markeredgecolor="#cccccc", ls="none", markersize=6,
               label="transit stop"),
    ]
    lax.legend(handles=handles, loc="upper left", fontsize=7.5, frameon=False,
                     labelcolor=INK, borderaxespad=0)
    rows = [f"{'district':<22}{'share':>6}  {'height m':>9}"]
    for d in spec.districts:
        rows.append(f"{d.name[:21]:<22}{d.area_share:>6.0%}  {d.height_m[0]:>4g}-{d.height_m[1]:<4g}")
    lax.text(0.0, 0.0, "\n".join(rows), family="monospace", fontsize=7, color=MUTED,
             va="bottom", transform=lax.transAxes)


def render(spec: CitySpec, out: str, dpi: int = 110) -> Layout:
    lay = build_layout(spec)
    fig = plt.figure(figsize=(15, 10.5), facecolor=BG)
    ax = fig.add_axes([0.02, 0.04, 0.66, 0.86])
    lax = fig.add_axes([0.70, 0.04, 0.29, 0.86])
    ax.set_facecolor(BG)
    _draw_geom(ax, lay.canvas, SEA, z=0)
    _draw_geom(ax, lay.land, LAND, z=1)
    for d in spec.districts:
        poly = lay.districts.get(d.name)
        if poly is not None:
            _draw_geom(ax, poly, ARCHETYPE_COLORS[d.archetype], edge="white", lw=0.8,
                       alpha=0.55, z=2)
    _draw_geom(ax, lay.water.difference(lay.sea), RIVER, z=3)
    for poly in lay.islands.values():
        _draw_geom(ax, poly, "none", edge="#bcd7e8", lw=0.8, z=3, ls="--")
    draw_highways(ax, spec, lay)
    draw_bridges(ax, spec, lay)
    draw_transit(ax, spec, lay)
    draw_labels(ax, spec, lay)

    minx, miny, maxx, maxy = lay.canvas.bounds
    ax.set_xlim(minx, maxx)
    ax.set_ylim(miny, maxy)
    ax.set_aspect("equal")
    ax.set_xticks([])
    ax.set_yticks([])
    for s in ax.spines.values():
        s.set_color("#33415c")
    # Scale bar (1 km) and north arrow.
    sx, sy = minx + 0.04 * (maxx - minx), miny + 0.04 * (maxy - miny)
    ax.plot([sx, sx + 1000], [sy, sy], color=INK, lw=3, zorder=13)
    ax.text(sx + 500, sy + 0.012 * (maxy - miny), "1 km", color=INK, fontsize=8, ha="center",
            zorder=13, path_effects=HALO)
    nx, ny = minx + 0.05 * (maxx - minx), maxy - 0.1 * (maxy - miny)
    ax.annotate("N", xy=(nx, ny + 0.06 * (maxy - miny)), xytext=(nx, ny), color=INK,
                ha="center", fontsize=10, fontweight="bold", zorder=13,
                arrowprops=dict(arrowstyle="-|>", color=INK, lw=1.5))
    fig.text(0.02, 0.965, f"{spec.name}: spec schematic", color=INK, fontsize=16,
             fontweight="bold", va="center")
    fig.text(0.02, 0.928,
             f"seed {spec.seed}, {spec.size_km[0]:g} x {spec.size_km[1]:g} km, "
             f"{len(spec.districts)} districts, coast {spec.water.coast.form} to the "
             f"{spec.water.coast.side}. Rough placement solved from the spec constraints; "
             "not the generated layout.", color=MUTED, fontsize=9, va="center")
    draw_legend(lax, spec)
    fig.savefig(out, dpi=dpi, facecolor=BG)
    plt.close(fig)
    return lay
