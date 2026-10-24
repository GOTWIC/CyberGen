"""Stage 2, districts: real polygons on the landmasses, plus the channels that separate them.

1. Ideal positions: a force solve over the land for every district not on an island (edge and
   center targets, direction relations, adjacency, coast, along_river, spreading by size).
2. Landmass assignment: each district lives on one landmass (so it is never in pieces). A local
   search (single moves and swaps) minimizes a cost of area mismatch per landmass, distance from
   the ideal position, placement violations and land left without a district.
3. Partition: districts sharing a landmass split it with a power diagram (weighted Voronoi)
   of domain-warped positions, so boundaries are curved and irregular, and some districts are
   concave. Weights are iterated on a raster until every cell holds its area share; Lloyd
   steps keep cells compact; boundaries are smooth iso-lines; stray pieces go to a neighbor.
4. Separation: shared land boundaries become meandering canal-scale channels (`separation`,
   25 to 80 m, widest where they open onto the sea) where the spec asks for water: every one
   for `water_required` (or `separated_by: water`); for `water_preferred` a budget: boundaries
   that run from water to water (near water first) until `water.boundary_water_share` of the
   district-to-district boundary is on water, water-to-map-edge ones only as a fallback.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import contourpy
import numpy as np
import shapely
from shapely.geometry import LineString, MultiLineString, Point, Polygon
from shapely.ops import nearest_points, unary_union

from . import geom as G
from . import hydro as H
from . import presets
from . import relations as R
from .defaults import derive_seed
from .spec import CitySpec

PREFERRED_MAX_LEN_M = 2400.0
WATER_KINDS = ("water", "river", "channel", "canal", "sea")


@dataclass
class Layout:
    polygons: dict[str, object] = field(default_factory=dict)
    landmass_of: dict[str, int | None] = field(default_factory=dict)
    seeds: dict[str, tuple[float, float]] = field(default_factory=dict)
    assignment_cost: float = 0.0
    shares: dict[str, float] = field(default_factory=dict)
    share_source: dict[str, str] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)
    separation: dict = field(default_factory=dict)


def resolve(spec: CitySpec, ref: str) -> tuple[str, str] | None:
    for d in spec.districts:
        if d.name == ref or any(p.name == ref for p in d.places) or \
                any(m.name == ref for m in d.megasites or []):
            return ("district", d.name)
    if any(i.name == ref for i in spec.water.islands):
        return ("island", ref)
    return None


def water_of(h: H.Hydro, kind_or_name: str):
    """Water geometry a `separated_by` / `along_river` value refers to."""
    if kind_or_name == "sea":
        return h.sea
    if kind_or_name in ("river",):
        return unary_union([b.polygon for b in h.bodies if b.kind in ("river", "delta_branch")])
    if kind_or_name == "channel":
        return unary_union([b.polygon for b in h.bodies
                            if b.kind in ("sea_channel", "delta_branch", "separation")])
    if kind_or_name == "canal":
        return unary_union([b.polygon for b in h.bodies if b.kind == "separation"])
    if kind_or_name == "water":
        return h.water
    bodies = h.by_name(kind_or_name)
    return unary_union([b.polygon for b in bodies]) if bodies else Polygon()


def island_landmass(h: H.Hydro, name: str) -> int | None:
    isl = next((i for i in h.islands if i.name == name), None)
    if isl is None or isl.polygon is None:
        return None
    for k, lm in enumerate(h.landmasses):
        if lm is isl.polygon:
            return k
    best = max(range(len(h.landmasses)),
               key=lambda k: h.landmasses[k].intersection(isl.polygon).area, default=None)
    return best


def effective_shares(spec: CitySpec, explicit: set[str], h: H.Hydro,
                     assign: dict[str, int], sources: dict | None = None) -> dict[str, float]:
    """Area shares the build aims for, as fractions of the land that holds districts.

    Shares the spec states are kept. A district without a stated share that has an island to
    itself gets the island's area; the other unstated shares split what is left by archetype
    weight (the same weights fill-defaults uses).
    """
    areas = [lm.area for lm in h.landmasses]
    used = sorted({k for k in assign.values() if k is not None})
    total = sum(areas[k] for k in used) or 1.0
    shares = {d.name: d.area_share for d in spec.districts}
    out = {n: shares[n] for n in shares if n in explicit}
    by_lm: dict[int, list[str]] = {}
    for n, k in assign.items():
        if k is not None:
            by_lm.setdefault(k, []).append(n)
    island_lms = {island_landmass(h, i.name) for i in h.islands}
    for k, names in by_lm.items():
        if k in island_lms and len(names) == 1 and names[0] not in explicit and \
                spec.district(names[0]).placement.on_island:
            out[names[0]] = areas[k] / total
            if sources is not None:
                sources[names[0]] = "island"
    rest = [d for d in spec.districts if d.name not in out]
    left = max(0.0, 1.0 - sum(out.values()))
    weight = sum(presets.ARCHETYPES[d.archetype].area_weight for d in rest)
    for d in rest:
        out[d.name] = left * presets.ARCHETYPES[d.archetype].area_weight / weight if weight \
            else 0.0
    if sources is not None:
        for n in out:
            sources.setdefault(n, "spec" if n in explicit else "archetype weight")
    return out


# ---------------------------------------------------------------------------
# 1. Ideal positions
# ---------------------------------------------------------------------------

def ideal_positions(spec: CitySpec, h: H.Hydro, pool, total: float) -> dict[str, np.ndarray]:
    rng = np.random.default_rng(derive_seed(spec.seed, "districts.ideal"))
    canvas = h.canvas
    radius = {d.name: math.sqrt(max(d.area_share * total, 1.0) / math.pi) for d in spec.districts}
    pts: dict[str, np.ndarray] = {}
    fixed: set[str] = set()
    targets: dict[str, np.ndarray] = {}
    isl_pos = {i.name: np.array(i.polygon.representative_point().coords[0])
               for i in h.islands if i.polygon is not None}
    for d in spec.districts:
        pl = d.placement
        if pl.on_island and pl.on_island in isl_pos:
            pts[d.name] = isl_pos[pl.on_island].copy()
            fixed.add(d.name)
            continue
        if pl.edge == "center":
            targets[d.name] = np.array(R.city_center(h.land))
        elif pl.edge:
            ux, uy = presets.DIRECTION_VECTORS[pl.edge]
            r = R.land_reach(h.land, canvas, pl.edge)
            targets[d.name] = np.array([ux, uy]) * r * 0.65
        minx, miny, maxx, maxy = canvas.bounds
        start = targets.get(d.name, np.array([rng.uniform(minx, maxx) * 0.4,
                                              rng.uniform(miny, maxy) * 0.4]))
        pts[d.name] = start.astype(float)
    coast = h.coastline
    rivers = {r.name: unary_union([b.centerline for b in h.by_name(r.name)])
              for r in spec.water.rivers}

    def pos(ref: str):
        hit = resolve(spec, ref)
        if hit is None:
            return None, None
        if hit[0] == "island":
            return isl_pos.get(hit[1]), None
        return pts[hit[1]], hit[1]

    inner_pool = {}
    steps = 300
    for it in range(steps):
        k = 0.5 * (1 - it / steps) + 0.05
        moves = {n: np.zeros(2) for n in pts}
        for d in spec.districts:
            a = d.name
            pl = d.placement
            for direction, ref in pl.relations():
                pb, b = pos(ref)
                if pb is None or b == a:
                    continue
                u = np.array(presets.DIRECTION_VECTORS[direction])
                margin = 0.75 * (radius[a] + radius.get(b, radius[a]))
                rel = pts[a] - pb
                along = float(rel @ u)
                viol = margin - along
                if viol > 0:
                    moves[a] += u * viol * 0.5
                    if b in moves:
                        moves[b] -= u * viol * 0.5
                # keep inside the angular sector: damp the sideways part
                side = rel - along * u
                lim = max(along, 0) * math.tan(math.radians(R.DIRECTION_TOL_DEG - 15))
                sn = float(np.linalg.norm(side))
                if sn > lim and sn > 1e-6:
                    moves[a] -= side / sn * (sn - lim) * 0.3
            for ref in pl.adjacent_to:
                pb, b = pos(ref)
                if pb is None or b == a:
                    continue
                gap = np.linalg.norm(pts[a] - pb) - (radius[a] + radius.get(b, radius[a]))
                if gap > 0:
                    dvec = (pb - pts[a]) / (np.linalg.norm(pb - pts[a]) + 1e-9)
                    moves[a] += dvec * gap * 0.3
            if a in targets:
                moves[a] += (targets[a] - pts[a]) * 0.25
            if pl.coast is not None and coast is not None and not coast.is_empty:
                p = Point(*pts[a])
                q = np.array(nearest_points(coast, p)[0].coords[0])
                dist = np.linalg.norm(pts[a] - q)
                if pl.coast and dist > 0.7 * radius[a]:
                    moves[a] += (q - pts[a]) * (1 - 0.7 * radius[a] / dist) * 0.4
                elif pl.coast is False and dist < 1.5 * radius[a]:
                    moves[a] += (pts[a] - q) / (dist + 1e-9) * (1.5 * radius[a] - dist) * 0.4
            for key in {pl.along_river, pl.separated_by} & set(rivers):
                if rivers[key].is_empty:
                    continue
                q = np.array(nearest_points(rivers[key], Point(*pts[a]))[0].coords[0])
                dist = np.linalg.norm(q - pts[a])
                if dist > 0.6 * radius[a]:
                    moves[a] += (q - pts[a]) * (1 - 0.6 * radius[a] / dist) * 0.3
        names = list(pts)
        for i, a in enumerate(names):
            for b in names[i + 1:]:
                dvec = pts[a] - pts[b]
                dist = np.linalg.norm(dvec) + 1e-9
                want = 0.9 * (radius[a] + radius[b])
                if dist < want:
                    push = dvec / dist * (want - dist) * 0.25
                    moves[a] += push
                    moves[b] -= push
        for n in names:
            if n in fixed:
                continue
            pts[n] = pts[n] + moves[n] * k
            p = Point(*pts[n])
            if not pool.is_empty and not pool.contains(p):
                if n not in inner_pool:
                    inner = pool.buffer(-0.3 * radius[n])
                    inner_pool[n] = inner if not inner.is_empty else pool
                pts[n] = np.array(nearest_points(inner_pool[n], p)[0].coords[0])
    return pts


# ---------------------------------------------------------------------------
# 2. Landmass assignment
# ---------------------------------------------------------------------------

@dataclass
class _Ctx:
    spec: CitySpec
    h: H.Hydro
    ideal: dict[str, np.ndarray]
    fixed: dict[str, int]
    pool: list[int]
    touch_sea: list[bool]
    touch: dict[str, list[bool]]
    radius: dict[str, float]
    centroid: list[np.ndarray]
    explicit: set[str]
    rivers: dict = field(default_factory=dict)
    cache: dict = field(default_factory=dict)
    local: dict = field(default_factory=dict)
    reaches: dict = field(default_factory=dict)

    def reach(self, edge: str) -> float | None:
        if edge == "center":
            return None
        if edge not in self.reaches:
            self.reaches[edge] = R.land_reach(self.h.land, self.h.canvas, edge)
        return self.reaches[edge]


def local_ideal(ctx: _Ctx, n: str, k: int) -> np.ndarray:
    """Best point for district `n` on landmass `k` for its own placement rules (the other
    districts at their ideal positions); the ideal position itself when it lies there."""
    key = (n, k)
    if key in ctx.local:
        return ctx.local[key]
    lm = ctx.h.landmasses[k]
    p0 = Point(*ctx.ideal[n])
    if lm.buffer(-20).contains(p0):
        ctx.local[key] = ctx.ideal[n]
        return ctx.ideal[n]
    minx, miny, maxx, maxy = lm.bounds
    step = max(maxx - minx, maxy - miny) / 10
    xs, ys = np.meshgrid(np.arange(minx + step / 2, maxx, step),
                         np.arange(miny + step / 2, maxy, step))
    xs, ys = xs.ravel(), ys.ravel()
    inner = lm.buffer(-min(step / 3, 80))
    ok = shapely.contains_xy(inner if not inner.is_empty else lm, xs, ys)
    cands = [np.array(nearest_points(lm, p0)[0].coords[0])] + \
        [np.array([x, y]) for x, y in zip(xs[ok], ys[ok])]
    d = ctx.spec.district(n)
    pl = d.placement
    r = ctx.radius[n]
    coast = ctx.h.coastline

    def cost(p):
        c = 0.3 * float(np.linalg.norm(p - ctx.ideal[n])) / r
        for direction, ref in pl.relations():
            hit = resolve(ctx.spec, ref)
            if hit is None or hit[1] == n:
                continue
            if hit[0] == "district":
                pb = ctx.ideal[hit[1]]
            else:
                isl = next((i for i in ctx.h.islands if i.name == hit[1]), None)
                if isl is None or isl.polygon is None:
                    continue
                pb = np.array(isl.polygon.centroid.coords[0])
            c += 4.0 * R.direction_excess(p, pb, direction)
        if pl.edge:
            c += 3.0 * R.edge_score(tuple(p), ctx.h.canvas, pl.edge, ctx.reach(pl.edge),
                                    R.city_center(ctx.h.land))
        if pl.coast is True and coast is not None and not coast.is_empty:
            c += max(0.0, coast.distance(Point(*p)) / r - 0.7)
        for key in (pl.along_river, pl.separated_by):
            if key and key in ctx.rivers:
                c += max(0.0, ctx.rivers[key].distance(Point(*p)) / r - 0.6)
        return c

    best = min(cands, key=lambda p: (cost(p), p[0], p[1]))
    ctx.local[key] = best
    return best


def _positions(ctx: _Ctx, assign: dict[str, int]) -> dict[str, np.ndarray]:
    """Expected centroid of every district: its landmass centroid when alone there, else the
    centroid of its Voronoi cell (seeds at the ideal positions) within the landmass."""
    by_lm: dict[int, list[str]] = {}
    for n, k in assign.items():
        by_lm.setdefault(k, []).append(n)
    out = {}
    for k, names in by_lm.items():
        if len(names) == 1:
            out[names[0]] = ctx.centroid[k]
            continue
        key = (k, tuple(sorted(names)))
        if key not in ctx.cache:
            lm = ctx.h.landmasses[k]
            seeds = np.array([local_ideal(ctx, n, k) for n in key[1]], dtype=float)
            for i in range(len(seeds)):
                for j in range(i):
                    if np.linalg.norm(seeds[i] - seeds[j]) < 1.0:
                        seeds[i] += np.array([5.0 * (i + 1), -3.0 * (i + 1)])
            minx, miny, maxx, maxy = lm.bounds
            pad = max(maxx - minx, maxy - miny)
            cells = power_cells(seeds, np.zeros(len(seeds)),
                                (minx - pad, miny - pad, maxx + pad, maxy + pad))
            pos = {}
            for n, cell, sd in zip(key[1], cells, seeds):
                part = cell.intersection(lm)
                pos[n] = np.array(part.centroid.coords[0]) if not part.is_empty else sd
            ctx.cache[key] = pos
        out.update(ctx.cache[key])
    return out


def _add(parts: dict | None, key: str, value: float) -> float:
    if parts is not None:
        parts[key] = parts.get(key, 0.0) + value
    return value


def assignment_cost(ctx: _Ctx, assign: dict[str, int], parts: dict | None = None) -> float:
    spec, h = ctx.spec, ctx.h
    by_lm: dict[int, list[str]] = {}
    for n, k in assign.items():
        by_lm.setdefault(k, []).append(n)
    areas = [lm.area for lm in h.landmasses]
    total = sum(areas[k] for k in by_lm) or 1.0
    shares = effective_shares(spec, ctx.explicit, h, assign)
    cost = 0.0
    for k, names in by_lm.items():
        want = sum(shares[n] for n in names) * total
        cost += _add(parts, "area", 25.0 * math.log(max(areas[k], 1.0) / max(want, 1.0)) ** 2)
    mean_t = total / max(len(assign), 1)
    for k in ctx.pool:
        if k not in by_lm:
            cost += _add(parts, "empty_land", 4.0 * areas[k] / mean_t)
    pos = _positions(ctx, assign)
    for d in spec.districts:
        n = d.name
        if n not in assign:
            continue
        k = assign[n]
        pl = d.placement
        lm = h.landmasses[k]
        if n not in ctx.fixed:
            cost += _add(parts, "distance", 0.5 * lm.distance(Point(*ctx.ideal[n])) / ctx.radius[n])
        for direction, ref in pl.relations():
            hit = resolve(spec, ref)
            if hit is None or hit[1] == n:
                continue
            if hit[0] == "district" and hit[1] in pos:
                pb = pos[hit[1]]
            else:
                isl = next((i for i in h.islands if i.name == hit[1]), None)
                if isl is None or isl.polygon is None:
                    continue
                pb = np.array(isl.polygon.centroid.coords[0])
            ex = R.direction_excess(pos[n], pb, direction)
            cost += _add(parts, "relation", (1.0 + 6.0 * ex) if ex > 0 else 0.0)
        if pl.edge:
            cost += _add(parts, "edge", 3.0 * R.edge_score(tuple(pos[n]), h.canvas, pl.edge,
                                                           ctx.reach(pl.edge),
                                                           R.city_center(h.land)))
        if pl.coast is True and not ctx.touch_sea[k]:
            cost += _add(parts, "coast", 3.0)
        if pl.coast is False and ctx.touch_sea[k] and len(by_lm[k]) == 1:
            cost += _add(parts, "inland", 1.0)
        for key in (pl.along_river, pl.separated_by):
            if key and key in ctx.touch and not ctx.touch[key][k]:
                cost += _add(parts, "water_touch", 3.0)
    return cost


def assign_landmasses(spec: CitySpec, h: H.Hydro, ideal: dict[str, np.ndarray],
                      fixed: dict[str, int], pool: list[int], total: float,
                      explicit: set[str]) -> tuple[dict, float, _Ctx]:
    coastal = h.coastal
    touch_sea = [R.touches(lm, coastal, 5.0) for lm in h.landmasses]
    keys = {d.placement.along_river for d in spec.districts if d.placement.along_river}
    keys |= {d.placement.separated_by for d in spec.districts
             if d.placement.separated_by and (d.placement.separated_by in WATER_KINDS
                                              or h.by_name(d.placement.separated_by))}
    touch = {}
    for key in sorted(keys):
        wgeom = water_of(h, key)
        touch[key] = [R.touches(lm, wgeom, 5.0) for lm in h.landmasses]
    radius = {d.name: math.sqrt(max(d.area_share * total, 1.0) / math.pi) for d in spec.districts}
    ctx = _Ctx(spec, h, ideal, fixed, pool, touch_sea, touch, radius,
               [np.array(lm.centroid.coords[0]) for lm in h.landmasses], explicit,
               {r.name: unary_union([b.centerline for b in h.by_name(r.name)])
                for r in spec.water.rivers})
    assign = dict(fixed)
    movable = [d.name for d in spec.districts if d.name not in fixed]
    if not pool:
        return assign, assignment_cost(ctx, assign), ctx
    for n in movable:
        p = Point(*ideal[n])
        assign[n] = min(pool, key=lambda k: (h.landmasses[k].distance(p), k))
    best = assignment_cost(ctx, assign)
    for _ in range(80):
        improved = None
        for n in movable:
            for k in pool:
                if k == assign[n]:
                    continue
                trial = dict(assign)
                trial[n] = k
                c = assignment_cost(ctx, trial)
                if c < best - 1e-9 and (improved is None or c < improved[0]):
                    improved = (c, trial)
        for i, a in enumerate(movable):
            for b in movable[i + 1:]:
                if assign[a] == assign[b]:
                    continue
                trial = dict(assign)
                trial[a], trial[b] = assign[b], assign[a]
                c = assignment_cost(ctx, trial)
                if c < best - 1e-9 and (improved is None or c < improved[0]):
                    improved = (c, trial)
        if improved is None:
            break
        best, assign = improved
    return assign, best, ctx


# ---------------------------------------------------------------------------
# 3. Power diagram per landmass
# ---------------------------------------------------------------------------

def _clip(pts: list[tuple[float, float]], a: float, b: float, c: float):
    out = []
    n = len(pts)
    for i in range(n):
        px, py = pts[i]
        qx, qy = pts[(i + 1) % n]
        fp = a * px + b * py - c
        fq = a * qx + b * qy - c
        if fp <= 0:
            out.append((px, py))
        if (fp <= 0) != (fq <= 0):
            t = fp / (fp - fq)
            out.append((px + t * (qx - px), py + t * (qy - py)))
    return out


def power_cells(seeds: np.ndarray, weights: np.ndarray, bounds) -> list[Polygon]:
    minx, miny, maxx, maxy = bounds
    box_pts = [(minx, miny), (maxx, miny), (maxx, maxy), (minx, maxy)]
    cells = []
    sq = (seeds ** 2).sum(axis=1)
    for i in range(len(seeds)):
        pts = box_pts
        for j in range(len(seeds)):
            if i == j:
                continue
            a, b = 2 * (seeds[j] - seeds[i])
            c = sq[j] - sq[i] - weights[j] + weights[i]
            pts = _clip(pts, float(a), float(b), float(c))
            if len(pts) < 3:
                break
        cells.append(Polygon(pts) if len(pts) >= 3 else Polygon())
    return cells


def _shared_len(a, b) -> float:
    if a.is_empty or b.is_empty:
        return 0.0
    return a.boundary.intersection(b.buffer(0.5)).length


def fix_pieces(polys: dict[str, object]) -> dict[str, object]:
    """Keep each district's largest part; give other parts to the neighbor they touch most."""
    main = {n: (G.parts(p)[0] if G.parts(p) else Polygon()) for n, p in polys.items()}
    extra = []
    for n, p in polys.items():
        extra += [(n, q) for q in G.parts(p)[1:]]
    for n, q in extra:
        cands = [(_shared_len(q, main[m]), m) for m in sorted(main) if m != n]
        cands = [c for c in cands if c[0] > 1.0]
        if not cands:
            continue
        _, m = max(cands)
        main[m] = G.clean(unary_union([main[m], q]))
    return main


def make_warp(seed: int, radius: float):
    """Smooth domain warp p -> p + V(p) (V: 2D fractal noise, amplitude about a quarter of a
    district radius). Districts are power cells of the warped position, so their boundaries
    are the preimages of straight power-diagram edges: curved, irregular, sometimes concave,
    and still an exact partition (every point gets exactly one district)."""
    rng = np.random.default_rng(derive_seed(seed, "districts.warp"))
    lam = 1.6 * radius
    nx = G.noise2d(rng, lam, octaves=3, persistence=0.38)
    ny = G.noise2d(rng, lam, octaves=3, persistence=0.38)
    amp = min(max(0.42 * radius, 130.0), 320.0)

    def warp(x, y):
        return x + amp * nx(x, y), y + amp * ny(x, y)

    warp.key = ("warp", seed, round(radius, 6))
    return warp


_GRIDS: dict = {}


def _grid(lm: Polygon, res: float, warp):
    key = (lm.wkb, round(res, 6), getattr(warp, "key", id(warp)))
    if key not in _GRIDS:
        if len(_GRIDS) > 64:
            _GRIDS.clear()
        _GRIDS[key] = _grid_build(lm, res, warp)
    return _GRIDS[key]


def _grid_build(lm: Polygon, res: float, warp):
    minx, miny, maxx, maxy = lm.bounds
    pad = 3 * res
    xs = np.arange(minx - pad, maxx + pad + res, res)
    ys = np.arange(miny - pad, maxy + pad + res, res)
    gx, gy = np.meshgrid(xs, ys)
    inside = shapely.contains_xy(lm, gx.ravel(), gy.ravel()).reshape(gx.shape)
    wx, wy = warp(gx, gy)
    return xs, ys, inside, wx, wy


def _power(wx, wy, s, w) -> np.ndarray:
    return (wx[..., None] - s[:, 0]) ** 2 + (wy[..., None] - s[:, 1]) ** 2 - w


def partition(lm: Polygon, names: list[str], seeds: dict[str, np.ndarray],
              targets: dict[str, float], warp=None, fine: bool = True) -> dict[str, object]:
    """Split a landmass into districts of the target areas: a power diagram (weighted
    Voronoi) of the warped positions. Weights are iterated on a coarse raster until every
    cell holds its share; Lloyd steps (seed to centroid, anchored to the placement seed) keep
    cells compact. The final boundaries are iso-lines of the power differences on a finer
    raster (linear interpolation, so they are smooth, not stepped). Detached bits of a cell go
    to a neighbor, so the areas are measured on the final polygons and the raster targets
    corrected for up to three rounds."""
    if len(names) == 1:
        return {names[0]: lm}
    warp = warp or (lambda x, y: (x, y))
    n = len(names)
    s = np.array([seeds[k] for k in names], dtype=float)
    for i in range(n):  # separate coincident seeds
        for j in range(i):
            if np.linalg.norm(s[i] - s[j]) < 1.0:
                s[i] += np.array([3.0 * (i + 1), -2.0 * (i + 1)])
    s0 = s.copy()
    t = np.array([targets[k] for k in names], dtype=float)
    t *= lm.area / t.sum()
    goal = t.copy()
    w = np.zeros(n)
    res = min(max(math.sqrt(lm.area) / 90.0, 10.0), 24.0)
    _, _, inside, wx, wy = _grid(lm, res, warp)
    wxi, wyi = wx[inside], wy[inside]
    step = min(max(math.sqrt(lm.area) / 180.0, 5.0), 12.0) if fine else res
    best = None
    for rnd in range(3 if fine else 1):
        eta, prev = 0.8, None
        for it in range(120):
            lab = np.argmin(_power(wxi, wyi, s, w), axis=-1)
            area = np.bincount(lab, minlength=n) * res * res
            err = t - area
            rel = float(np.max(np.abs(err) / t))
            if it > 24 and rel < 0.006:
                break
            if prev is not None:
                eta = min(eta * 1.15, 1.5) if rel < prev else eta * 0.5
            prev = rel
            w += eta * err
            w -= w.mean()
            if rnd == 0 and it < 24 and it % 2 == 0:
                cnt = np.maximum(np.bincount(lab, minlength=n), 1)
                c = np.column_stack([np.bincount(lab, wxi, n) / cnt,
                                     np.bincount(lab, wyi, n) / cnt])
                has = np.bincount(lab, minlength=n) > 0
                s[has] += 0.3 * (c[has] - s[has]) + 0.25 * (s0[has] - s[has])
        out = _cells(lm, names, s, w, step, warp)
        got = np.array([out[k].area for k in names])
        err = float(np.max(np.abs(got - goal) / goal))
        if best is None or err < best[0]:
            best = (err, out, s.copy())
        if err < 0.02:
            break
        t = t * np.clip(goal / np.maximum(got, 1.0), 0.7, 1.4)
        t *= lm.area / t.sum()
    _, out, s = best
    for k in names:
        seeds[k] = s[names.index(k)]
    return out


def _cells(lm: Polygon, names: list[str], s, w, step: float, warp) -> dict[str, object]:
    xs, ys, _, wx, wy = _grid(lm, step, warp)
    pw = _power(wx, wy, s, w)
    out: dict[str, object] = {}
    used = Polygon()
    for i, k in enumerate(names):
        others = np.delete(pw, i, axis=-1).min(axis=-1)
        polys = _filled(xs, ys, others - pw[..., i])
        cell = G.polygonal(polys.intersection(lm))
        if not used.is_empty:
            cell = G.polygonal(cell.difference(used))
        out[k] = cell
        used = used.union(cell)
    gaps = G.polygonal(lm.difference(used))
    for gp in G.parts(gaps):
        if gp.area < 0.5:
            continue
        m = max(names, key=lambda k: (_shared_len(gp, out[k]), -out[k].distance(gp)))
        out[m] = G.polygonal(unary_union([out[m], gp]))
    simple = shapely.coverage_simplify(np.array([out[k] for k in names], dtype=object), 0.5)
    return fix_pieces({k: G.clean(v) for k, v in zip(names, simple)})


def _filled(xs, ys, z) -> object:
    """Region z > 0 as a shapely (Multi)Polygon."""
    gen = contourpy.contour_generator(xs, ys, z, fill_type=contourpy.FillType.OuterOffset)
    pts_list, offs_list = gen.filled(0.0, np.inf)
    polys = []
    for pts, offs in zip(pts_list, offs_list):
        rings = [pts[offs[i]:offs[i + 1]] for i in range(len(offs) - 1)]
        rings = [r for r in rings if len(r) >= 4]
        if rings:
            polys.append(shapely.make_valid(Polygon(rings[0], rings[1:])))
    return G.polygonal(unary_union(polys)) if polys else Polygon()


# ---------------------------------------------------------------------------
# 4. Separation channels
# ---------------------------------------------------------------------------

def _pair_mode(spec: CitySpec, a: str, b: str) -> str:
    da, db = spec.district(a), spec.district(b)

    def mode(d):
        if d.placement.separated_by in ("water", "canal", "channel"):
            return "water_required"
        return d.water_separation or spec.water.district_separation

    ma, mb = mode(da), mode(db)
    if "water_required" in (ma, mb):
        return "water_required"
    if ma == "none" and mb == "none":
        return "none"
    if "none" in (ma, mb):
        return "none"
    return "water_preferred"


def _lines(g) -> list[LineString]:
    g = shapely.line_merge(g) if not g.is_empty and not isinstance(g, LineString) else g
    if g.is_empty:
        return []
    if isinstance(g, LineString):
        return [g]
    out = []
    for x in getattr(g, "geoms", []):
        if isinstance(x, LineString):
            out.append(x)
        elif isinstance(x, MultiLineString):
            out += list(x.geoms)
    return out


def _fits(a: str | None, b: str | None, edge_ok: bool = False) -> bool:
    """A preferred channel runs from water to water. Reaching the map edge is never a reason
    to cut one: a boundary from water to the edge is only a fallback when the water-to-water
    ones cannot reach the budget, and one between two map edges never is."""
    if edge_ok:
        return {a, b} <= {"water", "edge"} and "water" in (a, b)
    return a == "water" and b == "water"


def _near_water(line: LineString, water, reach: float = 220.0) -> float:
    """Share of a boundary (its ends aside) that runs within `reach` meters of water."""
    if line.length < 200.0:
        return 0.0
    ds = np.arange(80.0, line.length - 80.0, 20.0)
    if not len(ds):
        return 0.0
    pts = shapely.points([line.interpolate(d).coords[0] for d in ds])
    return float(np.mean(shapely.distance(water, pts) <= reach))


def separation_lines(spec: CitySpec, h: H.Hydro, lay: Layout) -> list[tuple[str, str, LineString]]:
    """Shared land boundaries that become channels.

    water_required: every boundary. water_preferred: a budget. Chains of one to three
    boundaries that run from water to water are candidates; the ones that already run near
    water (then the shorter ones) are cut first, until the share of district-to-district
    boundary on water reaches `water.boundary_water_share`."""
    canvas = h.canvas
    edges = []  # (a, b, line, mode, landmass)
    by_lm: dict[int, list[str]] = {}
    for n, k in lay.landmass_of.items():
        if k is not None:
            by_lm.setdefault(k, []).append(n)
    order = [d.name for d in spec.districts]
    for k in sorted(by_lm):
        names = sorted(by_lm[k], key=order.index)
        for i, a in enumerate(names):
            for b in names[i + 1:]:
                pa, pb = lay.polygons[a], lay.polygons[b]
                shared = pa.boundary.intersection(pb.buffer(0.5))
                for line in _lines(shared):
                    if line.length < 5.0:
                        continue
                    edges.append((a, b, line, _pair_mode(spec, a, b), k))
    wet, dry = R.boundary_water_split(lay.polygons, h.water, canvas)
    target = spec.water.boundary_water_share
    lay.separation = {"target": target, "before": round(wet / (wet + dry), 4)
                      if wet + dry else 1.0, "preferred_chains": 0}
    if not edges:
        return []

    nodes: list[tuple[float, float]] = []

    def key(p) -> int:
        """Endpoints within 6 m are one node (boundaries meet at triple points)."""
        for i, q in enumerate(nodes):
            if math.hypot(p[0] - q[0], p[1] - q[1]) <= 6.0:
                return i
        nodes.append((p[0], p[1]))
        return len(nodes) - 1

    def label(p, k) -> str:
        pt = Point(p)
        lm = h.landmasses[k]
        if lm.exterior.distance(pt) > 3.0 and all(r.distance(pt) > 3.0 for r in lm.interiors):
            return "interior"
        return "edge" if canvas.exterior.distance(pt) <= 3.0 else "water"

    labels: dict[int, str] = {}
    for a, b, line, mode, k in edges:
        for p in (line.coords[0], line.coords[-1]):
            lab = label(p, k)
            kk = key(p)
            if labels.get(kk) != "water":
                labels[kk] = lab if kk not in labels or lab != "interior" else labels[kk]
    chosen = [False] * len(edges)

    def take(idx: list[int]) -> None:
        nonlocal wet, dry
        for i in idx:
            chosen[i] = True
            wet += 2 * edges[i][2].length
            dry -= 2 * edges[i][2].length
            for p in (edges[i][2].coords[0], edges[i][2].coords[-1]):
                labels[key(p)] = "water"

    take([i for i, e in enumerate(edges) if e[3] == "water_required"])
    near = {i: _near_water(e[2], h.water) for i, e in enumerate(edges)}

    def share(w, d) -> float:
        return w / (w + d) if w + d > 0 else 1.0

    edge_ok = False
    while share(wet, dry) < target:
        pref = [i for i, e in enumerate(edges) if not chosen[i] and e[3] == "water_preferred"]
        ends = {i: (key(edges[i][2].coords[0]), key(edges[i][2].coords[-1])) for i in pref}
        cands: list[list[int]] = [[i] for i in pref]
        for x, i in enumerate(pref):  # chains of two and three boundaries
            for j in pref[x + 1:]:
                if len(set(ends[i]) & set(ends[j])) == 1:
                    cands.append([i, j])
                    for m in pref:
                        if m not in (i, j) and len(set(ends[m]) & (set(ends[i]) ^ set(ends[j]))) == 1 \
                                and not set(ends[m]) & (set(ends[i]) & set(ends[j])):
                            cands.append(sorted([i, j, m]))
        scored = []
        seen = set()
        for c in cands:
            if tuple(c) in seen:
                continue
            seen.add(tuple(c))
            deg: dict[int, int] = {}
            for i in c:
                for e in ends[i]:
                    deg[e] = deg.get(e, 0) + 1
            outer = sorted(e for e, v in deg.items() if v == 1)
            if len(outer) != 2 or any(v > 2 for v in deg.values()):
                continue
            if not _fits(labels.get(outer[0]), labels.get(outer[1]), edge_ok):
                continue
            length = sum(edges[i][2].length for i in c)
            if length > PREFERRED_MAX_LEN_M:
                continue
            nr = sum(near[i] * edges[i][2].length for i in c) / length
            scored.append((-(nr - 0.3 * length / 1000.0), length, c))
        scored.sort()
        before = abs(share(wet, dry) - target)
        pick = None
        for _, length, c in scored:
            after = share(wet + 2 * length, dry - 2 * length)
            if abs(after - target) < before:
                pick = c
                break
        if pick is None:
            if edge_ok:
                break
            edge_ok = True
            continue
        take(pick)
        lay.separation["preferred_chains"] += 1
    lay.separation["planned"] = round(share(wet, dry), 4)
    return [(e[0], e[1], e[2]) for i, e in enumerate(edges) if chosen[i]]


def _end_kind(h: H.Hydro, p: Point) -> str:
    if not h.sea.is_empty and h.sea.distance(p) <= 6.0:
        return "sea"
    if any(b.kind != "separation" and b.polygon.distance(p) <= 6.0 for b in h.bodies):
        return "river"
    return "inner"


END_WIDTH_M = {"sea": (48.0, 80.0), "river": (36.0, 55.0), "inner": (25.0, 32.0)}


def add_separation_channels(spec: CitySpec, h: H.Hydro, lay: Layout) -> list[H.WaterBody]:
    """Separation channels along the chosen boundaries: a meander around the boundary (a
    sine-generated curve on it) and a width from about 25 m at an inland end to up to 80 m
    where it opens onto the sea (the longer the channel, the wider its mouth)."""
    lines = separation_lines(spec, h, lay)
    bodies = []
    for k, (a, b, line) in enumerate(lines, start=1):
        rng = np.random.default_rng(derive_seed(spec.seed, "districts.separation", k))
        p0, p1 = Point(line.coords[0]), Point(line.coords[-1])
        kinds = [_end_kind(h, p0), _end_kind(h, p1)]
        frac = min(line.length / 1500.0, 1.0)
        w0, w1 = (lo + (hi - lo) * frac * rng.uniform(0.7, 1.0)
                  for lo, hi in (END_WIDTH_M[x] for x in kinds))
        if line.length > 300.0:
            course = G.course(line.coords[0], line.coords[-1], rng,
                              wavelength=float(rng.uniform(240.0, 340.0)), omega=0.35,
                              base=np.asarray(line.coords), ramp=(0.18, 0.18))
        else:
            course = line
        course = LineString(G.line_coords(course))
        mid = max(min(w0, w1) * 0.85, END_WIDTH_M["inner"][0])

        def wfn(ts, w0=w0, w1=w1, mid=mid):
            ts = np.asarray(ts, dtype=float)
            return mid + (w0 - mid) * G.smoothstep(1 - 2 * ts) + (w1 - mid) * G.smoothstep(2 * ts - 1)

        poly = G.polygonal(G.variable_buffer(course, wfn).intersection(h.canvas))
        others = [x for x in h.bodies if x.polygon.distance(poly) < 1.0]
        into = others[0].id if others else ("sea" if poly.distance(h.sea) < 1.0 else None)
        bodies.append(H.WaterBody(f"sep{k:02d}", "separation", None, course,
                                  H._widths_at(course, wfn), poly, "river", into,
                                  attrs={"separates": [a, b], "ends": kinds}))
    return bodies


# ---------------------------------------------------------------------------
# Driver
# ---------------------------------------------------------------------------

def layout_districts(spec: CitySpec, h: H.Hydro, explicit: set[str]) -> Layout:
    lay = Layout()
    fixed: dict[str, int] = {}
    for d in spec.districts:
        if d.placement.on_island:
            k = island_landmass(h, d.placement.on_island)
            if k is not None:
                fixed[d.name] = k
            else:
                lay.notes.append(f"district '{d.name}': island '{d.placement.on_island}' "
                                 "was not built")
    claimed = set(fixed.values())
    fillers = {island_landmass(h, i.name) for i in h.islands if i.filler}
    pool = [k for k in range(len(h.landmasses)) if k not in claimed and k not in fillers]
    pool_geom = unary_union([h.landmasses[k] for k in pool]) if pool else Polygon()
    total = sum(lm.area for k, lm in enumerate(h.landmasses) if k not in fillers)
    ideal = ideal_positions(spec, h, pool_geom, total)
    if not pool and any(d.name not in fixed for d in spec.districts):
        lay.notes.append("no mainland left for districts that are not on islands")
    assign, cost, ctx = assign_landmasses(spec, h, ideal, fixed, pool, total, explicit)
    lay.assignment_cost = cost
    lay.shares = effective_shares(spec, explicit, h, assign, lay.share_source)
    lay.landmass_of = {d.name: assign.get(d.name) for d in spec.districts}
    by_lm: dict[int, list[str]] = {}
    for d in spec.districts:
        k = assign.get(d.name)
        if k is not None:
            by_lm.setdefault(k, []).append(d.name)
    seeds = {n: ideal[n].copy() for n in ideal}
    warp = make_warp(spec.seed, math.sqrt(total / max(len(spec.districts), 1) / math.pi))
    for k, names in sorted(by_lm.items()):
        lm = h.landmasses[k]
        if len(names) > 1:
            for n in names:
                seeds[n] = local_ideal(ctx, n, k).copy()
        for n in names:
            p = Point(*seeds[n])
            if not lm.contains(p):
                inner = lm.buffer(-30)
                seeds[n] = np.array(nearest_points(inner if not inner.is_empty else lm, p)[0]
                                    .coords[0])
        targets = {n: lay.shares[n] for n in names}
        part = partition(lm, names, seeds, targets, warp)
        part = _repair_relations(spec, lm, names, seeds, targets, part, warp)
        lay.polygons.update(part)
    lay.seeds = {n: (float(p[0]), float(p[1])) for n, p in seeds.items()}
    return lay


def _relation_failures(spec: CitySpec, polys: dict[str, object], names: list[str]) -> int:
    bad = 0
    for n in names:
        for direction, ref in spec.district(n).placement.relations():
            hit = resolve(spec, ref)
            if hit and hit[0] == "district" and hit[1] in names and hit[1] != n:
                if polys[n].is_empty or polys[hit[1]].is_empty:
                    bad += 10
                    continue
                a, b = polys[n].centroid, polys[hit[1]].centroid
                if not R.direction_ok((a.x, a.y), (b.x, b.y), direction):
                    bad += 1
    return bad


def _failing(spec: CitySpec, polys: dict[str, object], names: list[str]) -> set[str]:
    out = set()
    for n in names:
        for direction, ref in spec.district(n).placement.relations():
            hit = resolve(spec, ref)
            if hit and hit[0] == "district" and hit[1] in names and hit[1] != n:
                a, b = polys[n], polys[hit[1]]
                if a.is_empty or b.is_empty or not R.direction_ok(
                        (a.centroid.x, a.centroid.y), (b.centroid.x, b.centroid.y), direction):
                    out |= {n, hit[1]}
    return out


def _repair_relations(spec, lm, names, seeds, targets, part, warp=None):
    """Swap seeds of districts whose relation to a district on the same landmass fails."""
    if len(names) < 2:
        return part
    for _ in range(2):
        bad_set = _failing(spec, part, names)
        bad = _relation_failures(spec, part, names)
        if bad == 0:
            break
        best = None
        for i, a in enumerate(names):
            for b in names[i + 1:]:
                if a not in bad_set and b not in bad_set:
                    continue
                trial_seeds = dict(seeds)
                trial_seeds[a], trial_seeds[b] = seeds[b].copy(), seeds[a].copy()
                trial = partition(lm, names, trial_seeds, targets, warp, fine=False)
                f = _relation_failures(spec, trial, names)
                if f < bad and (best is None or f < best[0]):
                    best = (f, trial, trial_seeds)
        if best is None:
            break
        _, _, new_seeds = best
        seeds.update(new_seeds)
        part = partition(lm, names, seeds, targets, warp)
    return part


def _hand_over_tips(polys: dict[str, object]) -> dict[str, object]:
    """Thin tips (where a district boundary meets the shore at a shallow angle) go to the
    neighbor on the other side of the boundary, whose corner there is wide."""
    out = dict(polys)
    for n in sorted(polys):
        p = out[n]
        removed = p.difference(G.opening(p, H.MIN_LAND_WIDTH_M / 2))
        for tip in G.parts(removed):
            if tip.area < 20.0:
                continue
            cands = [(_shared_len(tip, out[m]), m) for m in sorted(out) if m != n]
            cands = [c for c in cands if c[0] > 5.0]
            if not cands:
                continue
            _, m = max(cands)
            out[n] = G.polygonal(out[n].difference(tip))
            out[m] = G.clean(unary_union([out[m], tip]))
    return out


def finalize(spec: CitySpec, h: H.Hydro, lay: Layout) -> None:
    """Add separation channels, rebuild the land, and clip districts to it."""
    seps = add_separation_channels(spec, h, lay)
    if seps:
        h.bodies += seps
        H.rebuild_land(h)
    land = h.land
    polys = {n: G.polygonal(p.intersection(land)) for n, p in lay.polygons.items()}
    # A district must not straddle landmasses: keep its largest part, hand the rest over.
    polys = fix_pieces(polys)
    polys = _hand_over_tips(polys)
    # Snapping to the output grid can make neighbors overlap by a hair; the earlier district
    # in spec order keeps the overlap.
    used = Polygon()
    for d in spec.districts:
        p = polys.get(d.name)
        if p is None or p.is_empty:
            continue
        p = G.clean(p)
        if not used.is_empty and p.intersects(used):
            p = G.clean(G.polygonal(p.difference(used)))
        polys[d.name] = p
        used = used.union(p)
    lay.polygons = {n: p for n, p in polys.items() if not p.is_empty}
    lay.landmass_of = {}
    for n, p in lay.polygons.items():
        k = max(range(len(h.landmasses)),
                key=lambda i: h.landmasses[i].intersection(p).area, default=None)
        lay.landmass_of[n] = k
