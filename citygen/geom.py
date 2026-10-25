"""Geometry helpers shared by the generator stages (meters, x east, y north, origin center)."""

from __future__ import annotations

import math

import numpy as np
import shapely
from shapely.geometry import LineString, MultiLineString, MultiPolygon, Point, Polygon, box
from shapely.ops import unary_union

from . import dmath as M
from . import presets

GRID_M = 0.01  # output precision
# Tests set this (meters) to jitter every geometry entering a quantization barrier, to show that
# the barriers absorb last-bit differences between machines. Always 0 in a real build.
JITTER_M = 0.0
# M2 stages (streets, junctions, blocks) put every snapped polygon in canonical form (rings
# start at their lowest vertex, parts sorted; `shapely.normalize`): GEOS's snap-rounding can
# return the same rings starting at another vertex when its input differs in the last bits.
# Off for the M1 stages, whose output is unchanged.
CANONICAL = [False]


class canonical:
    """Context: snapped polygons in canonical form (see CANONICAL)."""

    def __enter__(self):
        self.prev = CANONICAL[0]
        CANONICAL[0] = True
        return self

    def __exit__(self, *exc):
        CANONICAL[0] = self.prev
        return False


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
    if len(out) == 1:
        return out
    a = areas(np.array(out, dtype=object))
    keys = [(-a[i],) + qbounds(p) for i, p in enumerate(out)]
    return [out[i] for i in sorted(range(len(out)), key=lambda i: keys[i])]


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
    out = polygonal(snap(g, grid))
    return shapely.normalize(out) if CANONICAL[0] and not out.is_empty else out


def snap(geom, grid: float = GRID_M):
    """Coordinates on the grid (made valid by GEOS), with a floating precision model.

    `shapely.set_precision` also attaches its grid to the geometry, and GEOS then runs every
    later overlay on it snap-rounded; WKB and pickling drop that, so the same coordinates
    would overlay differently in a worker process. Dropping it here keeps every geometry
    plain coordinates."""
    if CANONICAL[0]:
        return _round(geom, grid)
    return floating(shapely.set_precision(geom, grid))


def _round(geom, grid: float = GRID_M):
    """M2 snapping: every coordinate rounded on its own (no snap-rounding, whose hot-pixel
    tests on grid-aligned input can depend on the last bits), then repaired by make_valid
    and rounded again where the repair added vertices."""
    g = floating(shapely.set_precision(geom, grid, mode="pointwise"))
    dim = int(shapely.get_dimensions(geom))
    for k in range(5):
        if g.is_empty or g.is_valid:
            break
        if k == 4:  # rare: rounding keeps breaking the repair; snap-round instead
            return floating(shapely.set_precision(geom, grid))
        g = shapely.make_valid(g)
        if dim == 2:
            g = polygonal(g)
        elif dim == 1:
            # make_valid nests the lines in a collection (beside collapsed points): flatten
            ls = [p for q in shapely.get_parts(g) for p in shapely.get_parts(q)
                  if p.geom_type == "LineString"]
            g = MultiLineString(ls) if len(ls) > 1 else (ls[0] if ls else LineString())
        g = floating(shapely.set_precision(g, grid, mode="pointwise"))
    return g


def floating(geom):
    """The same coordinates with a floating precision model."""
    if geom is None or shapely.get_precision(geom) == 0:
        return geom
    return shapely.set_precision(geom, 0.0, mode="pointwise")


# ---------------------------------------------------------------------------
# Quantization barriers: every stage hands the next one coordinates on the 0.01 m grid, so
# last-bit differences between machines (libm, SIMD, fused multiply-add in GEOS) cannot reach
# a later decision.
# ---------------------------------------------------------------------------

def q(v: float) -> float:
    """A number on the output grid (0.01)."""
    return round(float(v), 2) + 0.0


def _jitter(geom):
    if not JITTER_M or geom is None or geom.is_empty or shapely.get_precision(geom) > 0:
        return geom  # (a geometry that carries the grid precision is exact grid output)

    # Only inexact values move (machine noise cannot change a value computed exactly from
    # grid inputs, such as a midpoint), by a function of the point itself (rings stay closed).
    def move(c):
        exact = np.abs(c * 1000.0 - np.rint(c * 1000.0)) < 1e-6
        h = np.mod(c[:, :1] * 12.9898 + c[:, 1:2] * 78.233, 1.0)
        d = JITTER_M * (2.0 * np.hstack([h, np.mod(h * 7.0, 1.0)]) - 1.0)
        return np.where(exact, c, c + d)

    return shapely.transform(geom, move)


def qpoint(p) -> tuple[float, float]:
    x, y = (p.x, p.y) if hasattr(p, "x") else (p[0], p[1])
    if JITTER_M:
        if abs(x * 1000.0 - round(x * 1000.0)) >= 1e-6:
            x += JITTER_M * 0.37
        if abs(y * 1000.0 - round(y * 1000.0)) >= 1e-6:
            y -= JITTER_M * 0.61
    return (q(x), q(y))


def qline(line, dedupe: bool = True):
    """LineString with coordinates on the grid (repeated points dropped unless `dedupe` is
    False, which keeps one vertex per input vertex)."""
    if line is None or line.is_empty:
        return line
    line = _jitter(line)
    pts = []
    for x, y in np.asarray(line.coords)[:, :2]:
        p = (q(x), q(y))
        if not dedupe or not pts or p != pts[-1]:
            pts.append(p)
    return LineString(pts) if len(pts) > 1 else LineString()


def qpoly(geom):
    """Polygonal geometry snapped to the grid (valid, polygonal)."""
    if geom is None or geom.is_empty:
        return geom
    return clean(_jitter(geom))


def opening(geom, half_width: float):
    """Morphological opening: removes necks and strips narrower than 2 * half_width
    (grid output)."""
    if geom.is_empty or half_width <= 0:
        return geom
    inner = qpoly(geom.buffer(-half_width, join_style="mitre", mitre_limit=3))
    if inner.is_empty:
        return Polygon()
    outer = qpoly(inner.buffer(half_width, join_style="mitre", mitre_limit=3))
    # Remove only what the opening really removes: where the outer outline runs along the
    # original one it differs by grid steps, and those hairline slivers (thinner than 0.1 m)
    # are not removed, so the kept outline is exactly the original one.
    if CANONICAL[0]:  # M2: an exact width, not an inner buffer, decides what a hairline is
        removed = [p for p in parts(diff(geom, outer)) if _strip_width(p) > 0.1]
    else:
        removed = [p for p in parts(diff(geom, outer))
                   if not p.buffer(-0.05, join_style="mitre").is_empty]
    return diff(geom, union(removed)) if removed else polygonal(geom)


def _strip_width(p) -> float:
    """Width of a strip with the exact area and perimeter of p (a long w x L rectangle gives
    about w)."""
    A = area1(p)
    half = length1(p.exterior) / 2.0
    disc = half * half - 4.0 * A
    return math.sqrt(A) if disc < 0 else (half - math.sqrt(disc)) / 2.0


def drop_small(geom, min_area: float):
    return polygonal(MultiPolygon([p for p in parts(geom) if area(p) >= min_area]))


# ---------------------------------------------------------------------------
# Exact measures and grid-snapped operations. GEOS computes areas, lengths, distances and new
# vertices in floating point, and a compiler may fuse a * b + c into one rounding (ARM does,
# x86 baseline builds do not), so the same input gives slightly different bits on different
# machines. Decisions only look at these: areas and lengths computed exactly from the
# 0.01 m grid coordinates (integer arithmetic, `math.fsum`), distances rounded to 1e-6 m, and
# GEOS outputs snapped to the grid right away.
# ---------------------------------------------------------------------------

_SCALE = 100.0  # grid units per meter
DIST_DIGITS = 6


def _icoords(coords) -> np.ndarray:
    """Coordinates as integer grid units (exact)."""
    return np.rint(np.asarray(coords, dtype=np.float64)[:, :2] * _SCALE).astype(np.int64)


def area(geom) -> float:
    """Area of the grid-snapped vertices, exact (integer shoelace on grid units)."""
    if geom is None or geom.is_empty:
        return 0.0
    if geom.geom_type == "Polygon":
        return float(areas(np.array([geom], dtype=object))[0])
    parts_ = shapely.get_parts(geom)
    if any(p.geom_type in ("MultiPolygon", "GeometryCollection") for p in parts_):
        return math.fsum([area(p) for p in parts_])
    polys = parts_[shapely.get_type_id(parts_) == 3]
    return math.fsum(areas(polys)) if len(polys) else 0.0


def areas(polys) -> np.ndarray:
    """Exact areas (see `area`) of an array of Polygons, in one pass."""
    rings, owner = shapely.get_rings(polys, return_index=True)
    coords, ridx = shapely.get_coordinates(rings, return_index=True)
    c = np.rint(coords * _SCALE).astype(np.int64)
    cross = c[:-1, 0] * c[1:, 1] - c[1:, 0] * c[:-1, 1]
    cross = np.where(ridx[:-1] == ridx[1:], cross, 0)  # no term across two rings
    starts = np.searchsorted(ridx[:-1], np.arange(len(rings)))
    per_ring = np.abs(np.add.reduceat(np.append(cross, 0), starts))
    exterior = np.r_[True, owner[1:] != owner[:-1]]
    signed = np.where(exterior, per_ring, -per_ring)
    out = np.zeros(len(polys), dtype=np.int64)
    np.add.at(out, owner, signed)
    return out / (2 * _SCALE * _SCALE)


def _path_length(coords) -> list[float]:
    c = _icoords(coords)
    if len(c) < 2:
        return []
    d = np.diff(c, axis=0)
    return list(np.sqrt((d[:, 0] * d[:, 0] + d[:, 1] * d[:, 1]).astype(np.float64)))


def length(geom) -> float:
    """Length of a line (perimeter of a polygon) on its grid-snapped vertices: exact squared
    segment lengths, correctly rounded square roots, `math.fsum`."""
    if geom is None or geom.is_empty:
        return 0.0
    segs: list[float] = []
    for p in shapely.get_parts(geom):
        if p.geom_type == "Polygon":
            for r in [p.exterior, *p.interiors]:
                segs += _path_length(r.coords)
        elif p.geom_type in ("LineString", "LinearRing"):
            segs += _path_length(p.coords)
        elif hasattr(p, "geoms"):
            segs.append(length(p) * _SCALE)
    return math.fsum(segs) / _SCALE


def qbounds(geom) -> tuple[float, float, float, float]:
    return tuple(q(v) for v in geom.bounds)


def dist(a, b) -> float:
    """Distance rounded to 1e-6 m (thresholds and ties see the same value everywhere)."""
    return round(float(a.distance(b)), DIST_DIGITS)


def dists(geom, pts) -> np.ndarray:
    return np.round(shapely.distance(geom, pts), DIST_DIGITS)


def within(geom, pts, d: float) -> np.ndarray:
    """distance(geom, pts) <= d, decided with a 1e-6 m margin (so a distance that is exactly
    d, common on the grid, counts on every machine); prepared, so fast."""
    shapely.prepare(geom)
    return shapely.dwithin(geom, pts, d + 10.0 ** -DIST_DIGITS)


def centroid(geom) -> tuple[float, float]:
    c = geom.centroid
    return qpoint(c)


def nearest(geom, p) -> tuple[float, float]:
    """Point of `geom` nearest to `p`, on the grid."""
    from shapely.ops import nearest_points

    return qpoint(nearest_points(geom, p if hasattr(p, "geom_type") else Point(*p))[0])


def apart(a, b, pad: float = 0.0) -> bool:
    """True when the bounding boxes of a and b are more than `pad` apart (a cheap reject)."""
    ax0, ay0, ax1, ay1 = a.bounds
    bx0, by0, bx1, by1 = b.bounds
    return ax1 + pad < bx0 or bx1 + pad < ax0 or ay1 + pad < by0 or by1 + pad < ay0


# Overlays run in floating point on grid inputs (GEOS decides the topology with exact
# predicates, so only the new vertices can carry machine noise) and are snapped to the grid at
# once. Snap-rounded overlays (`grid_size`) would be as deterministic, but leave zigzags of
# 0.01 m steps where two boundaries nearly coincide.

def _fixed(out):
    """M2: output of a fixed-precision (grid_size) overlay, valid and on the grid already."""
    out = polygonal(floating(out))
    return shapely.normalize(out) if not out.is_empty else out


def inter(a, b):
    """Polygonal intersection on the grid."""
    if a.is_empty or b.is_empty or apart(a, b):
        return Polygon()
    if CANONICAL[0]:
        return _fixed(shapely.intersection(a, b, grid_size=GRID_M))
    return clean(polygonal(shapely.intersection(a, b)))


def diff(a, b):
    if a.is_empty:
        return Polygon()
    if b.is_empty or apart(a, b):
        return clean(a)
    if CANONICAL[0]:
        return _fixed(shapely.difference(a, b, grid_size=GRID_M))
    return clean(polygonal(shapely.difference(a, b)))


def union(geoms):
    geoms = [g for g in geoms if g is not None and not g.is_empty]
    if not geoms:
        return Polygon()
    if CANONICAL[0]:
        return _fixed(_union_fixed(geoms))
    return clean(polygonal(shapely.union_all(geoms)))


def _zorder(ix: int, iy: int) -> int:
    """Morton (Z-order) code of two non-negative integers."""
    z = 0
    for b in range(max(ix.bit_length(), iy.bit_length())):
        z |= ((ix >> b) & 1) << (2 * b) | ((iy >> b) & 1) << (2 * b + 1)
    return z


def _union_fixed(geoms):
    """Snap-rounded union of many geometries in an order fixed here.

    Snap rounding is not associative, so the result depends on the order in which the
    pieces are merged. `union_all` merges them in the order of its STRtree, which packs
    the pieces after a `std::sort` of their envelopes: equal keys come out in an order
    that differs between C++ standard libraries (libc++ on macOS, libstdc++ on Linux).
    Here the pieces are sorted by the Z-order of their bounding box centers in grid units
    (exact integers; input order breaks ties) and merged pairwise, level by level, with
    binary snap-rounded unions, whose result does not depend on any such order. Only the
    polygonal parts count (the caller keeps only those)."""
    polys = [polygonal(g) for g in geoms]
    polys = [g for g in polys if not g.is_empty]
    if not polys:
        return Polygon()
    geoms = polys
    if len(geoms) == 1:
        return shapely.union(geoms[0], geoms[0], grid_size=GRID_M)
    b = np.rint(shapely.bounds(np.array(geoms, dtype=object)) * _SCALE).astype(np.int64)
    cx = (b[:, 0] + b[:, 2]).tolist()
    cy = (b[:, 1] + b[:, 3]).tolist()
    x0, y0 = min(cx), min(cy)
    order = sorted(range(len(geoms)), key=lambda i: (_zorder(cx[i] - x0, cy[i] - y0), i))
    arr = np.empty(len(geoms), dtype=object)
    arr[:] = [geoms[i] for i in order]
    while len(arr) > 1:
        n = len(arr) // 2 * 2
        u = shapely.union(arr[0:n:2], arr[1:n:2], grid_size=GRID_M)
        for i in np.nonzero(shapely.get_type_id(u) > 6)[0].tolist():
            u[i] = polygonal(u[i])  # a collection with collapsed linework
        arr = np.concatenate([u, arr[n:]])
    return arr[0]


def line_union(lines):
    lines = [g for g in lines if g is not None and not g.is_empty]
    if not lines:
        return LineString()
    out = floating(shapely.union_all(lines, grid_size=GRID_M))
    # M2: parts in canonical order (GEOS's own order can follow its std::sort ties)
    return shapely.normalize(out) if CANONICAL[0] else out


def along(line, ds) -> np.ndarray:
    """Points at distances `ds` along a line (grid-snapped vertices), on the grid. Segment
    lengths are exact square roots; positions use separate elementwise operations."""
    c = _icoords(line.coords)
    d = np.diff(c, axis=0)
    seg = np.sqrt((d[:, 0] * d[:, 0] + d[:, 1] * d[:, 1]).astype(np.float64)) / _SCALE
    cum = np.concatenate([[0.0], np.cumsum(seg)])
    ds = np.clip(np.asarray(ds, dtype=np.float64), 0.0, cum[-1])
    i = np.clip(np.searchsorted(cum, ds, side="right") - 1, 0, max(len(seg) - 1, 0))
    if not len(seg):
        return np.repeat(c[:1] / _SCALE, len(ds), axis=0)
    f = (ds - cum[i]) / np.where(seg[i] > 0, seg[i], 1.0)
    a = c[i] / _SCALE
    b = c[i + 1] / _SCALE
    x = a[:, 0] + f * (b[:, 0] - a[:, 0])
    y = a[:, 1] + f * (b[:, 1] - a[:, 1])
    return np.column_stack([np.rint(x * _SCALE) / _SCALE, np.rint(y * _SCALE) / _SCALE])


def line_inter(line, poly):
    """Linework of `line` inside `poly`, on the grid (vertices rounded, so the lines follow
    the input vertices without grid zigzags)."""
    if line.is_empty or poly.is_empty or apart(line, poly):
        return LineString()
    out = shapely.intersection(line, poly)
    lines = [qline(g) for g in shapely.get_parts(out)
             if g.geom_type in ("LineString", "LinearRing")]
    lines = [g for g in lines if not g.is_empty]
    if not lines:
        return LineString()
    return lines[0] if len(lines) == 1 else MultiLineString(lines)


def coverage_simplify(polys: list, tolerance: float) -> list:
    """`shapely.coverage_simplify` run on integer grid-unit coordinates, where its triangle
    areas are exact, so its choices are the same on every machine."""
    arr = np.array([shapely.transform(p, lambda c: np.rint(c * _SCALE)) for p in polys],
                   dtype=object)
    out = shapely.coverage_simplify(arr, tolerance * _SCALE)
    return [shapely.transform(p, lambda c: c / _SCALE) for p in out]


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
    n = M.hypot(dx, dy) or 1.0
    return (dx / n, dy / n)


# ---------------------------------------------------------------------------
# Noise and curves
# ---------------------------------------------------------------------------

def noise1d(rng: np.random.Generator, wavelength: float, octaves: int = 3,
            persistence: float = 0.45):
    """Smooth fractal 1D value noise f(t) in about [-1, 1] (t in meters or any unit)."""
    tables = []
    for o in range(octaves):
        amp = math.prod([persistence] * o)
        tables.append((wavelength / (2 ** o), amp, rng.uniform(-1, 1, 4096),
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


def noise2d(rng: np.random.Generator, wavelength: float, octaves: int = 2,
            persistence: float = 0.4):
    """Smooth fractal 2D value noise f(x, y) in about [-1, 1] (x, y in meters)."""
    tables = []
    for o in range(octaves):
        amp = math.prod([persistence] * o)
        tables.append((wavelength / (2 ** o), amp, rng.uniform(-1, 1, (256, 256)),
                       rng.uniform(0, 256, 2)))
    norm = sum(a for _, a, _, _ in tables)

    def f(x, y):
        x = np.asarray(x, dtype=float)
        y = np.asarray(y, dtype=float)
        out = np.zeros(np.broadcast(x, y).shape)
        for lam, amp, tab, off in tables:
            u, v = x / lam + off[0], y / lam + off[1]
            i, j = np.floor(u).astype(int), np.floor(v).astype(int)
            fu, fv = u - i, v - j
            wu, wv = fu * fu * (3 - 2 * fu), fv * fv * (3 - 2 * fv)
            i0, j0, i1, j1 = i % 256, j % 256, (i + 1) % 256, (j + 1) % 256
            a = tab[i0, j0] + (tab[i1, j0] - tab[i0, j0]) * wu
            b = tab[i0, j1] + (tab[i1, j1] - tab[i0, j1]) * wu
            out += amp * (a + (b - a) * wv)
        return out / norm

    return f


def smoothstep(x):
    x = np.clip(np.asarray(x, dtype=float), 0.0, 1.0)
    return x * x * (3 - 2 * x)


def bezier(p0, p1, p2, p3, n: int = 200) -> np.ndarray:
    t = np.linspace(0, 1, n)[:, None]
    p0, p1, p2, p3 = (np.asarray(p, dtype=float) for p in (p0, p1, p2, p3))
    u = 1 - t
    return u * u * u * p0 + 3 * u * u * t * p1 + 3 * u * t * t * p2 + t * t * t * p3


def course(a, b, rng: np.random.Generator, *, wavelength: float, omega: float,
           base: np.ndarray | None = None, bulge: float = 0.0, step: float = 10.0,
           ramp: tuple[float, float] = (0.08, 0.08), scale: float = 1.0) -> LineString:
    """Meandering path from a to b as a sine-generated curve (Langbein and Leopold 1966).

    The heading is theta(s) = base(s) + omega(s) sin(phi(s)): `base` is the heading of an
    optional curved base path (points from a to b; default the straight chord), `omega` the
    peak deflection in radians (varied along the path by slow noise between 45% and 100%),
    and phi a phase with noisy wavelength, so bends differ in size and spacing. The heading is
    integrated and the result is fitted to a and b by a similarity transform. Below about 2
    radians a sine-generated curve never crosses itself. `ramp` fades the meander in and out
    over those fractions of the length; `bulge` bows the whole path sideways (fraction of the
    chord, + = left); `scale` multiplies omega (used to damp a path back onto the map).
    """
    a, b = np.asarray(a, dtype=float), np.asarray(b, dtype=float)
    chord = float(M.hypot(*(b - a))) or 1.0
    ang0 = M.atan2(b[1] - a[1], b[0] - a[0])
    if base is None:
        base = np.array([a, b])
    base = np.asarray(base, dtype=float)
    seg = M.hypot(*np.diff(base, axis=0).T)
    cum = np.concatenate([[0.0], np.cumsum(seg)])
    blen = float(cum[-1]) or chord
    head = np.unwrap(M.atan2(*np.diff(base, axis=0).T[::-1]))
    mids = (cum[:-1] + cum[1:]) / 2 / blen
    n_amp = noise1d(rng, 1.7 * wavelength, octaves=2)
    n_ph = noise1d(rng, 1.3 * wavelength, octaves=2)
    ph0 = rng.uniform(0, 2 * math.pi)
    length = blen
    pts = None
    for _ in range(2):  # second pass: the step that gives the wavelength in final meters
        n = max(int(length / step), 16)
        s = (np.arange(n) + 0.5) / n
        sm = s * length
        th_base = np.interp(s, mids, head) if len(head) > 1 else np.full(n, head[0])
        om = omega * scale * (0.45 + 0.55 * (0.5 + 0.5 * np.clip(1.8 * n_amp(sm), -1, 1)))
        om = om * smoothstep(s / max(ramp[0], 1e-6)) * smoothstep((1 - s) / max(ramp[1], 1e-6))
        th = th_base + om * M.sin(2 * math.pi * sm / wavelength + ph0 + 4.5 * n_ph(sm))
        th = th + math.pi * bulge * M.cos(math.pi * s) * 1.2
        d = np.column_stack([M.cos(th), M.sin(th)]) * (length / n)
        pts = np.vstack([[0.0, 0.0], np.cumsum(d, axis=0)])
        span = float(M.hypot(*pts[-1])) or 1.0
        length = length * chord / span
    span_ang = M.atan2(pts[-1][1], pts[-1][0])
    k = chord / (float(M.hypot(*pts[-1])) or 1.0)
    rot = ang0 - span_ang
    c, sn = M.cos(rot), M.sin(rot)
    out = np.column_stack([pts[:, 0] * c - pts[:, 1] * sn, pts[:, 0] * sn + pts[:, 1] * c]) * k
    out = out + a
    out[-1] = b
    return LineString(out)


def resample(line: LineString, step: float) -> np.ndarray:
    n = max(2, int(math.ceil(line.length / step)) + 1)
    ds = np.linspace(0, line.length, n)
    return np.array([line.interpolate(d).coords[0] for d in ds])


def wiggle_path(a: tuple[float, float], b: tuple[float, float], offset_fn,
                step: float = 20.0) -> LineString:
    """Path from a to b displaced sideways by offset_fn(t) (t = 0..1, meters, + = left)."""
    ax, ay = a
    bx, by = b
    length = M.hypot(bx - ax, by - ay) or 1.0
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
    norm = M.hypot(d[:, 0], d[:, 1])
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
    rr = (1 + 0.10 * M.sin(2 * th + ph[0]) + 0.08 * M.sin(3 * th + ph[1])
          + 0.05 * M.sin(5 * th + ph[2]) + 0.025 * M.sin(8 * th + ph[3]))
    xs, ys = rr * M.cos(th) * elong, rr * M.sin(th) / elong
    ca, sa = M.cos(angle), M.sin(angle)
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


# ---------------------------------------------------------------------------
# Fast exact measures for one geometry (the same arithmetic as `area` and `length`, without
# the array machinery; the street, junction and block stages call them very often)
# ---------------------------------------------------------------------------

def area1(poly) -> float:
    """Exact area of a Polygon on its grid-snapped vertices (equal to `area`)."""
    if poly is None or poly.is_empty:
        return 0.0
    if poly.geom_type != "Polygon":
        return math.fsum(area1(p) for p in shapely.get_parts(poly)
                         if p.geom_type == "Polygon")
    tot = 0
    for k, ring in enumerate([poly.exterior, *poly.interiors]):
        c = np.rint(shapely.get_coordinates(ring) * _SCALE).astype(np.int64)
        cr = abs(int((c[:-1, 0] * c[1:, 1] - c[1:, 0] * c[:-1, 1]).sum()))
        tot += cr if k == 0 else -cr
    return tot / (2 * _SCALE * _SCALE)


def length1(geom) -> float:
    """Exact length of the linework of a geometry on grid-rounded vertices (equal to
    `length` for lines; polygons count their rings, points nothing)."""
    if geom is None or geom.is_empty:
        return 0.0
    if geom.geom_type in ("LineString", "LinearRing"):
        c = np.rint(shapely.get_coordinates(geom) * _SCALE).astype(np.int64)
        d = np.diff(c, axis=0)
        seg = np.sqrt((d[:, 0] * d[:, 0] + d[:, 1] * d[:, 1]).astype(np.float64))
        return math.fsum(seg.tolist()) / _SCALE
    parts = shapely.get_parts(geom)
    lines = []
    for p in parts:
        t = p.geom_type
        if t in ("LineString", "LinearRing"):
            lines.append(p)
        elif t == "Polygon":
            lines += [p.exterior, *p.interiors]
        elif t in ("MultiLineString", "MultiPolygon", "GeometryCollection"):
            lines += [x for x in shapely.get_parts(p) if x.geom_type == "LineString"]
    if not lines:
        return 0.0
    coords, idx = shapely.get_coordinates(np.array(lines, dtype=object), return_index=True)
    c = np.rint(coords * _SCALE).astype(np.int64)
    same = idx[1:] == idx[:-1]
    d = np.diff(c, axis=0)[same]
    seg = np.sqrt((d[:, 0] * d[:, 0] + d[:, 1] * d[:, 1]).astype(np.float64))
    return math.fsum(seg.tolist()) / _SCALE


def snap_many(geoms):
    """Array of geometries snapped to the grid (floating precision model), in one call."""
    arr = np.asarray(geoms, dtype=object)
    if CANONICAL[0]:
        out = shapely.set_precision(arr, GRID_M, mode="pointwise")
        out = shapely.set_precision(out, 0.0, mode="pointwise")
        bad = ~shapely.is_valid(out)
        for i in np.nonzero(bad)[0].tolist():
            out[i] = _round(out[i])
        return out
    arr = shapely.set_precision(arr, GRID_M)
    return shapely.set_precision(arr, 0.0, mode="pointwise")


def from_model_polys(polys) -> list:
    """Shapely polygons of many model polygons at once (rings built in one vectorized call;
    polygons with holes one by one)."""
    out = [None] * len(polys)
    flat, idx, which = [], [], []
    k = 0
    for i, d in enumerate(polys):
        if d is None:
            continue
        holes = d.holes if hasattr(d, "holes") else d.get("holes", [])
        if holes:
            out[i] = from_model_poly(d)
            continue
        ext = d.exterior if hasattr(d, "exterior") else d["exterior"]
        flat.extend(ext)
        idx.extend([k] * len(ext))
        which.append(i)
        k += 1
    if which:
        rings = shapely.linearrings(np.asarray(flat, dtype=np.float64),
                                    indices=np.asarray(idx, dtype=np.int64))
        ps = shapely.polygons(rings)
        for i, p in zip(which, ps):
            out[i] = p
    return out
