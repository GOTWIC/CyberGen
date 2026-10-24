"""Geometry helpers shared by the generator stages (meters, x east, y north, origin center)."""

from __future__ import annotations

import math

import numpy as np
import shapely
from shapely.geometry import LineString, MultiPolygon, Point, Polygon, box
from shapely.ops import unary_union

from . import presets

GRID_M = 0.01  # output precision


def canvas_for(size_km: tuple[float, float]) -> Polygon:
    w, h = size_km[0] * 1000.0, size_km[1] * 1000.0
    return box(-w / 2, -h / 2, w / 2, h / 2)


def parts(geom) -> list[Polygon]:
    """Polygon parts of any geometry, largest first (ties broken by position)."""
    if geom is None or geom.is_empty:
        return []
    if isinstance(geom, Polygon):
        return [geom]
    out = [g for g in getattr(geom, "geoms", []) if isinstance(g, Polygon) and not g.is_empty]
    nested = [p for g in getattr(geom, "geoms", []) if not isinstance(g, Polygon)
              for p in parts(g)]
    out += nested
    return sorted(out, key=lambda p: (-round(p.area, 3), round(p.centroid.x, 3),
                                      round(p.centroid.y, 3)))


def polygonal(geom):
    """Only the polygonal part of a geometry, as a (Multi)Polygon."""
    ps = parts(geom)
    if not ps:
        return Polygon()
    return ps[0] if len(ps) == 1 else MultiPolygon(ps)


def clean(geom, grid: float = GRID_M):
    """Valid polygonal geometry snapped to the output grid."""
    g = shapely.make_valid(geom) if not geom.is_valid else geom
    g = polygonal(g)
    if g.is_empty:
        return g
    return polygonal(shapely.set_precision(g, grid))


def opening(geom, half_width: float):
    """Morphological opening: removes necks and strips narrower than 2 * half_width."""
    if geom.is_empty or half_width <= 0:
        return geom
    return polygonal(geom.buffer(-half_width, join_style="mitre", mitre_limit=3)
                     .buffer(half_width, join_style="mitre", mitre_limit=3).intersection(geom))


def drop_small(geom, min_area: float):
    return polygonal(MultiPolygon([p for p in parts(geom) if p.area >= min_area]))


def frame(direction: str) -> tuple[float, float, float, float]:
    """(ux, uy, vx, vy): u points toward `direction`, v is u turned 90 degrees left."""
    ux, uy = presets.DIRECTION_VECTORS[direction]
    return ux, uy, -uy, ux


def edge_point(canvas: Polygon, direction: str, at: float | None = None) -> tuple[float, float]:
    """Point on the map edge named `direction`.

    `at` runs 0 to 1: west to east on the north and south edges, south to north on the east and
    west edges. A diagonal edge runs from the middle of its first-named side (0) through the
    corner (0.5) to the middle of its second side (1). Default 0.5.
    """
    minx, miny, maxx, maxy = canvas.bounds
    at = 0.5 if at is None else min(max(at, 0.0), 1.0)
    mx, my = (minx + maxx) / 2, (miny + maxy) / 2
    sides = {
        "north": ((minx, maxy), (maxx, maxy)), "south": ((minx, miny), (maxx, miny)),
        "east": ((maxx, miny), (maxx, maxy)), "west": ((minx, miny), (minx, maxy)),
    }
    if direction in sides:
        (ax, ay), (bx, by) = sides[direction]
        return (ax + (bx - ax) * at, ay + (by - ay) * at)
    first, second = direction.split("_")
    corner = (maxx if second == "east" else minx, maxy if first == "north" else miny)
    p0 = (mx, corner[1])  # middle of the first-named (north/south) side
    p1 = (corner[0], my)  # middle of the second (east/west) side
    path = LineString([p0, corner, p1])
    q = path.interpolate(at, normalized=True)
    return (q.x, q.y)


def edge_tangent_inward(canvas: Polygon, p: tuple[float, float]) -> tuple[float, float]:
    """Unit vector pointing into the map from an edge point."""
    minx, miny, maxx, maxy = canvas.bounds
    x, y = p
    dx = (1.0 if abs(x - minx) < 1 else -1.0 if abs(x - maxx) < 1 else 0.0)
    dy = (1.0 if abs(y - miny) < 1 else -1.0 if abs(y - maxy) < 1 else 0.0)
    n = math.hypot(dx, dy) or 1.0
    return (dx / n, dy / n)


# ---------------------------------------------------------------------------
# Noise and curves
# ---------------------------------------------------------------------------

def noise1d(rng: np.random.Generator, wavelength: float, octaves: int = 3,
            persistence: float = 0.45):
    """Smooth fractal 1D value noise f(t) in about [-1, 1] (t in meters or any unit)."""
    tables = []
    for o in range(octaves):
        tables.append((wavelength / (2 ** o), persistence ** o, rng.uniform(-1, 1, 4096),
                       rng.uniform(0, 4096)))
    norm = sum(a for _, a, _, _ in tables)

    def f(t):
        t = np.asarray(t, dtype=float)
        out = np.zeros_like(t)
        for lam, amp, tab, off in tables:
            x = t / lam + off
            i = np.floor(x).astype(int)
            fr = x - i
            w = fr * fr * (3 - 2 * fr)  # smoothstep
            a = tab[i % 4096]
            b = tab[(i + 1) % 4096]
            out += amp * (a + (b - a) * w)
        return out / norm

    return f


def resample(line: LineString, step: float) -> np.ndarray:
    n = max(2, int(math.ceil(line.length / step)) + 1)
    ds = np.linspace(0, line.length, n)
    return np.array([line.interpolate(d).coords[0] for d in ds])


def wiggle_path(a: tuple[float, float], b: tuple[float, float], offset_fn,
                step: float = 20.0) -> LineString:
    """Path from a to b displaced sideways by offset_fn(t) (t = 0..1, meters, + = left)."""
    ax, ay = a
    bx, by = b
    length = math.hypot(bx - ax, by - ay) or 1.0
    nx, ny = -(by - ay) / length, (bx - ax) / length
    n = max(8, int(length / step))
    ts = np.linspace(0, 1, n + 1)
    off = offset_fn(ts)
    xs = ax + (bx - ax) * ts + nx * off
    ys = ay + (by - ay) * ts + ny * off
    return LineString(list(zip(xs, ys)))


def variable_buffer(line: LineString, widths_fn, step: float = 12.0) -> Polygon:
    """Polygon around `line` whose full width at fraction t is widths_fn(t)."""
    pts = resample(line, step)
    if len(pts) < 2:
        return Polygon()
    ts = np.linspace(0, 1, len(pts))
    w = np.asarray(widths_fn(ts), dtype=float) / 2
    d = np.gradient(pts, axis=0)
    norm = np.hypot(d[:, 0], d[:, 1])
    norm[norm == 0] = 1
    nx, ny = -d[:, 1] / norm, d[:, 0] / norm
    left = np.column_stack([pts[:, 0] + nx * w, pts[:, 1] + ny * w])
    right = np.column_stack([pts[:, 0] - nx * w, pts[:, 1] - ny * w])
    ring = np.vstack([left, right[::-1]])
    poly = shapely.make_valid(Polygon(ring))
    caps = [Point(pts[0]).buffer(w[0], 16), Point(pts[-1]).buffer(w[-1], 16)]
    return polygonal(unary_union([polygonal(poly), *caps]))


def blob(center: tuple[float, float], area: float, rng: np.random.Generator,
         elong: float = 1.0, angle: float = 0.0, n: int = 72) -> Polygon:
    """Smooth noisy island-like shape with exactly `area` square meters."""
    ph = rng.uniform(0, 2 * math.pi, 4)
    th = np.linspace(0, 2 * math.pi, n, endpoint=False)
    rr = (1 + 0.10 * np.sin(2 * th + ph[0]) + 0.08 * np.sin(3 * th + ph[1])
          + 0.05 * np.sin(5 * th + ph[2]) + 0.025 * np.sin(8 * th + ph[3]))
    xs, ys = rr * np.cos(th) * elong, rr * np.sin(th) / elong
    ca, sa = math.cos(angle), math.sin(angle)
    pts = np.column_stack([xs * ca - ys * sa, xs * sa + ys * ca])
    unit = Polygon(pts)
    k = math.sqrt(area / unit.area)
    return Polygon(pts * k + np.asarray(center))


# ---------------------------------------------------------------------------
# Model conversion
# ---------------------------------------------------------------------------

def _ring(coords) -> list[tuple[float, float]]:
    pts = [(round(x, 2) + 0.0, round(y, 2) + 0.0) for x, y in coords]
    if len(pts) > 1 and pts[0] == pts[-1]:
        pts = pts[:-1]
    return pts


def oriented(p: Polygon) -> Polygon:
    return shapely.geometry.polygon.orient(p, 1.0)


def to_model_polys(geom) -> list[dict]:
    """Polygon parts as model dicts (exterior counterclockwise, holes clockwise)."""
    out = []
    for p in parts(geom):
        p = oriented(p)
        out.append({"exterior": _ring(p.exterior.coords),
                    "holes": [_ring(r.coords) for r in p.interiors]})
    return out


def to_model_poly(geom) -> dict:
    ps = to_model_polys(geom)
    return ps[0]


def from_model_poly(d) -> Polygon:
    ext = d.exterior if hasattr(d, "exterior") else d["exterior"]
    holes = d.holes if hasattr(d, "holes") else d.get("holes", [])
    return Polygon(ext, holes)


def line_coords(line) -> list[tuple[float, float]]:
    return [(round(x, 2) + 0.0, round(y, 2) + 0.0) for x, y in line.coords]
