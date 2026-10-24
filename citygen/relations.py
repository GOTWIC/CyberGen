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

from . import presets

DIRECTION_TOL_DEG = 67.5
TOUCH_M = 30.0
ADJACENT_M = 300.0


def direction_ok(a: tuple[float, float], b: tuple[float, float], direction: str) -> bool:
    dx, dy = a[0] - b[0], a[1] - b[1]
    d = math.hypot(dx, dy)
    if d < 1e-6:
        return False
    ux, uy = presets.DIRECTION_VECTORS[direction]
    return (dx * ux + dy * uy) / d >= math.cos(math.radians(DIRECTION_TOL_DEG)) - 1e-9


def direction_excess(a, b, direction: str) -> float:
    """How far (radians) the relation is outside its tolerance; 0 when satisfied."""
    dx, dy = a[0] - b[0], a[1] - b[1]
    if math.hypot(dx, dy) < 1e-6:
        return math.pi / 2
    ux, uy = presets.DIRECTION_VECTORS[direction]
    ang = abs(math.atan2(ux * dy - uy * dx, ux * dx + uy * dy))
    return max(0.0, ang - math.radians(DIRECTION_TOL_DEG))


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
        return math.hypot(c.x - cx, c.y - cy) <= 0.25 * w or poly.contains(Point(cx, cy))
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
        return max(0.0, math.hypot(pos[0] - center[0], pos[1] - center[1]) / (0.25 * w) - 0.7)
    ux, uy = presets.DIRECTION_VECTORS[edge]
    r = reach_m or reach(canvas, edge)
    proj = pos[0] * ux + pos[1] * uy
    return max(0.0, 0.45 - proj / r)


def touches(a, b, tol: float = TOUCH_M) -> bool:
    if a is None or b is None or a.is_empty or b.is_empty:
        return False
    return a.distance(b) <= tol
