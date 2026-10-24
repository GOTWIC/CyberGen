"""Placement predicates shared by the district solver and the checks (scope section 9).

- `<direction>_of`: the angle between (centroid A - centroid B) and the direction is at most
  67.5 degrees (the direction's own sector plus one neighbor on each side).
- `edge`: measured against the land's reach in that direction (the map edge on a land side,
  the outermost shore on a sea side). The centroid lies at least 20% of the way out, and the
  district touches that map edge, reaches 85% of the way, or has its centroid half way out.
  `center`: the centroid is within a quarter of the shorter map side of the city center (the
  centroid of the land, which sits off the map center when the sea takes one side).
- `coast`: true = touches the sea or a sea channel (within 30 m); false = stays more than 30 m
  from both.
- `on_island`: at least 95% of the district lies on the island.
- `along_river`, `separated_by` (water kinds or a river name): touches that water.
- `adjacent_to`: within 300 m (a river between them still counts: bridges join them).
"""

from __future__ import annotations

import math

from shapely.geometry import LineString, Point, Polygon

from . import dmath as M
from . import presets

DIRECTION_TOL_DEG = 67.5
TOUCH_M = 30.0
ADJACENT_M = 300.0


def direction_ok(a: tuple[float, float], b: tuple[float, float], direction: str) -> bool:
    dx, dy = a[0] - b[0], a[1] - b[1]
    d = M.hypot(dx, dy)
    if d < 1e-6:
        return False
    ux, uy = presets.DIRECTION_VECTORS[direction]
    return (dx * ux + dy * uy) / d >= M.cos(M.radians(DIRECTION_TOL_DEG)) - 1e-9


def direction_excess(a, b, direction: str) -> float:
    """How far (radians) the relation is outside its tolerance; 0 when satisfied."""
    dx, dy = a[0] - b[0], a[1] - b[1]
    if M.hypot(dx, dy) < 1e-6:
        return math.pi / 2
    ux, uy = presets.DIRECTION_VECTORS[direction]
    ang = abs(M.atan2(ux * dy - uy * dx, ux * dx + uy * dy))
    return max(0.0, ang - M.radians(DIRECTION_TOL_DEG))


def reach(canvas: Polygon, direction: str) -> float:
    ux, uy = presets.DIRECTION_VECTORS[direction]
    _, _, maxx, maxy = canvas.bounds
    tx = maxx / abs(ux) if abs(ux) > 1e-9 else math.inf
    ty = maxy / abs(uy) if abs(uy) > 1e-9 else math.inf
    return min(tx, ty)


def edge_side(canvas: Polygon, direction: str) -> LineString:
    """The map boundary on that side (two half sides for a diagonal)."""
    minx, miny, maxx, maxy = canvas.bounds
    sides = {
        "north": [(minx, maxy), (maxx, maxy)], "south": [(minx, miny), (maxx, miny)],
        "east": [(maxx, miny), (maxx, maxy)], "west": [(minx, miny), (minx, maxy)],
    }
    if direction in sides:
        return LineString(sides[direction])
    first, second = direction.split("_")
    cx = maxx if second == "east" else minx
    cy = maxy if first == "north" else miny
    return LineString([(0.0, cy), (cx, cy), (cx, 0.0)])


def land_reach(land, canvas: Polygon, direction: str) -> float:
    """How far the land extends from the center toward `direction` (capped by the map)."""
    if land is None or land.is_empty:
        return reach(canvas, direction)
    ux, uy = presets.DIRECTION_VECTORS[direction]
    pts = [c for g in getattr(land, "geoms", [land]) for c in g.exterior.coords]
    return max(min(max(x * ux + y * uy for x, y in pts), reach(canvas, direction)), 1.0)


def city_center(land) -> tuple[float, float]:
    if land is None or land.is_empty:
        return (0.0, 0.0)
    c = land.centroid
    return (c.x, c.y)


def edge_ok(poly, canvas: Polygon, edge: str, land=None) -> bool:
    c = poly.centroid
    if edge == "center":
        w = min(canvas.bounds[2] - canvas.bounds[0], canvas.bounds[3] - canvas.bounds[1])
        cx, cy = city_center(land)
        return M.hypot(c.x - cx, c.y - cy) <= 0.25 * w or poly.contains(Point(cx, cy))
    ux, uy = presets.DIRECTION_VECTORS[edge]
    r = land_reach(land, canvas, edge)
    proj = c.x * ux + c.y * uy
    if proj < 0.2 * r:
        return False
    far = max(x * ux + y * uy for x, y in poly.exterior.coords)
    return proj >= 0.5 * r or far >= 0.85 * r or \
        poly.distance(edge_side(canvas, edge)) <= TOUCH_M


def edge_score(pos: tuple[float, float], canvas: Polygon, edge: str,
               reach_m: float | None = None,
               center: tuple[float, float] = (0.0, 0.0)) -> float:
    """0 when a point is well inside the edge zone, growing outside (for the solver)."""
    if edge == "center":
        w = min(canvas.bounds[2] - canvas.bounds[0], canvas.bounds[3] - canvas.bounds[1])
        return max(0.0, M.hypot(pos[0] - center[0], pos[1] - center[1]) / (0.25 * w) - 0.7)
    ux, uy = presets.DIRECTION_VECTORS[edge]
    r = reach_m or reach(canvas, edge)
    proj = pos[0] * ux + pos[1] * uy
    return max(0.0, 0.45 - proj / r)


def touches(a, b, tol: float = TOUCH_M) -> bool:
    if a is None or b is None or a.is_empty or b.is_empty:
        return False
    return a.distance(b) <= tol


def boundary_samples(polys: dict, water, canvas: Polygon, reach: float = 250.0,
                     step: float = 10.0) -> list[tuple]:
    """Samples along every district outline (map edges aside), one list per ring:
    (xy array, sample length, kind array) with kind 1 = dry boundary (another district within
    2 m, shared land), 2 = wet boundary (the nearest other district within `reach` across
    water), 0 = neither (open coast, map edge)."""
    import numpy as np
    import shapely

    names = [n for n in sorted(polys) if not polys[n].is_empty]
    edge = canvas.exterior
    out = []
    for n in names:
        others = [polys[m] for m in names if m != n]
        if not others:
            continue
        geom = polys[n]
        rings = [r for p in getattr(geom, "geoms", [geom]) for r in [p.exterior, *p.interiors]]
        for ring in rings:
            line = LineString(ring.coords)
            k = max(int(line.length / step), 1)
            seg = line.length / k
            xy = np.array([line.interpolate((i + 0.5) * seg).coords[0] for i in range(k)])
            pts = shapely.points(xy)
            d = np.min([shapely.distance(o, pts) for o in others], axis=0)
            keep = shapely.distance(edge, pts) > 1.0
            kind = np.zeros(k, dtype=int)
            kind[keep & (d <= 2.0)] = 1
            kind[keep & (d > 2.0) & (d <= reach) & (shapely.distance(water, pts) <= 3.0)] = 2
            out.append((xy, seg, kind))
    return out


def boundary_water_split(polys: dict, water, canvas: Polygon, reach: float = 250.0,
                         step: float = 10.0) -> tuple[float, float]:
    """(wet, dry) length of the boundaries between neighboring districts (see
    `boundary_samples`). Each boundary is seen from both sides, so wet / (wet + dry) is the
    share of the district-to-district boundary that runs along water."""
    wet = dry = 0.0
    for _, seg, kind in boundary_samples(polys, water, canvas, reach, step):
        dry += float((kind == 1).sum()) * seg
        wet += float((kind == 2).sum()) * seg
    return wet, dry


def boundary_curvature(samples, window: float = 400.0, kinds=(1, 2)) -> float | None:
    """Mean arc length / chord over windows of `window` meters of district-to-district
    boundary (1.0 = ruler straight). None when no boundary run is that long."""
    import numpy as np

    ratios = []
    for xy, seg, kind in samples:
        ok = np.isin(kind, kinds)
        n = len(ok)
        w = max(int(round(window / seg)), 2)
        if n < w:
            continue
        # rotate so a run does not wrap around the ring start
        start = int(np.argmin(ok)) if not ok.all() else 0
        ok, pts = np.roll(ok, -start), np.roll(xy, -start, axis=0)
        i = 0
        while i + w <= n:
            if ok[i:i + w].all():
                chord = float(M.hypot(*(pts[i + w - 1] - pts[i])))
                ratios.append((w - 1) * seg / max(chord, 1e-6))
                i += max(w // 4, 1)
            else:
                i += 1
    return float(np.mean(ratios)) if ratios else None
