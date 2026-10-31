"""A plan region as a triangle mesh on a square lattice (the water surfaces and the beds).

The lattice's cells fully inside the region are two triangles each on the lattice's points;
the cells the region's edge crosses are clipped to it (GEOS) and their pieces triangulated
exactly on integer millimeters (`assetgen.triangulate`, every vertex kept, so neighbors meet
without T-junctions). Vertices are shared by their millimeter position, so the mesh is one
watertight sheet: a height or an offset given per vertex (a wave) moves both sides of every
edge alike. Triangles are counterclockwise seen from above.
"""

from __future__ import annotations

import math

import numpy as np
import shapely

from ..triangulate import TriangulationError, triangulate


def _lattice(x0: float, x1: float, c: float) -> np.ndarray:
    n = max(1, int(math.ceil((x1 - x0) / c - 1e-9)))
    v = x0 + np.arange(n + 1, dtype=np.float64) * c
    v[-1] = x1
    return v


def mesh(region, box, cell: float) -> tuple[np.ndarray, np.ndarray]:
    """(vertices as (n, 2) integer millimeters in the world frame, triangles (m, 3)) of the
    region (a polygon or multipolygon, inside `box` = (x0, y0, x1, y1))."""
    if region is None or region.is_empty:
        return np.zeros((0, 2), dtype=np.int64), np.zeros((0, 3), dtype=np.int64)
    x0, y0, x1, y1 = box
    # (on the millimeter grid first: the clipped pieces are then valid as they are rounded,
    # with no sliver that rounds to a fold)
    region = shapely.set_precision(region, 0.001)
    if region.is_empty:
        return np.zeros((0, 2), dtype=np.int64), np.zeros((0, 3), dtype=np.int64)
    gx = _lattice(x0, x1, cell)
    gy = _lattice(y0, y1, cell)
    nx, ny = len(gx) - 1, len(gy) - 1
    I, J = np.meshgrid(np.arange(nx), np.arange(ny))
    I, J = I.ravel(), J.ravel()
    cells = shapely.box(gx[I], gy[J], gx[I + 1], gy[J + 1])
    keys: dict[tuple[int, int], int] = {}
    verts: list[tuple[int, int]] = []

    def vid(k: tuple[int, int]) -> int:
        v = keys.get(k)
        if v is None:
            v = keys[k] = len(verts)
            verts.append(k)
        return v

    mx = np.rint(gx * 1000.0).astype(np.int64)
    my = np.rint(gy * 1000.0).astype(np.int64)
    tris: list[tuple[int, int, int]] = []
    for face in [region]:
        shapely.prepare(face)
        hit = shapely.intersects(face, cells)
        full = hit & shapely.covers(face, cells)
        edge = hit & ~full
        for i, j in zip(I[full].tolist(), J[full].tolist()):
            a = vid((int(mx[i]), int(my[j])))
            b = vid((int(mx[i + 1]), int(my[j])))
            c = vid((int(mx[i + 1]), int(my[j + 1])))
            d = vid((int(mx[i]), int(my[j + 1])))
            tris.append((a, b, c))
            tris.append((a, c, d))
        if edge.any():
            for g in shapely.intersection(cells[edge], face, grid_size=0.001).tolist():
                for p in _polys(g):
                    _piece(p, vid, tris)
    if not tris:
        return np.zeros((0, 2), dtype=np.int64), np.zeros((0, 3), dtype=np.int64)
    return np.array(verts, dtype=np.int64), np.array(tris, dtype=np.int64)


def _polys(g) -> list:
    if g is None or g.is_empty:
        return []
    t = g.geom_type
    if t == "Polygon":
        return [g]
    if t in ("MultiPolygon", "GeometryCollection"):
        return [p for x in g.geoms for p in _polys(x)]
    return []


def _ring_mm(coords) -> list[tuple[int, int]]:
    out = []
    for x, y in coords:
        k = (int(round(x * 1000.0)), int(round(y * 1000.0)))
        if not out or out[-1] != k:
            out.append(k)
    if len(out) > 1 and out[0] == out[-1]:
        out.pop()
    return out


SPLIT_DEPTH = 4


def _piece(p, vid, tris, depth: int = 0) -> None:
    """A clipped cell piece, triangulated exactly; a piece the ear clipper cannot take whole
    (a hole touching its outline at a point, a pinched spike: the same directed edge twice)
    is split in halves, across its longer side, and each half taken again."""
    outer = _ring_mm(p.exterior.coords)
    holes = [_ring_mm(r.coords) for r in p.interiors]
    holes = [h for h in holes if len(h) >= 3]
    if len(outer) < 3:
        return
    try:
        t = triangulate(outer, holes, keep_straight=True)
    except TriangulationError:
        t = None
    allp = outer + [q for h in holes for q in h]
    keep, seen, bad = [], set(), t is None
    for a, b, c in t or ():
        pa, pb, pc = allp[a], allp[b], allp[c]
        if (pb[0] - pa[0]) * (pc[1] - pa[1]) - (pb[1] - pa[1]) * (pc[0] - pa[0]) <= 0:
            continue
        for e in ((pa, pb), (pb, pc), (pc, pa)):
            if e in seen:
                bad = True
            seen.add(e)
        keep.append((pa, pb, pc))
    if bad and depth < SPLIT_DEPTH:
        x0, y0, x1, y1 = p.bounds
        if x1 - x0 >= y1 - y0:
            xm = round((x0 + x1) / 2.0, 3)
            halves = [(x0, y0, xm, y1), (xm, y0, x1, y1)]
        else:
            ym = round((y0 + y1) / 2.0, 3)
            halves = [(x0, y0, x1, ym), (x0, ym, x1, y1)]
        for h in halves:
            for q in _polys(shapely.intersection(p, shapely.box(*h), grid_size=0.001)):
                _piece(q, vid, tris, depth + 1)
        return
    for pa, pb, pc in keep:
        tris.append((vid(pa), vid(pb), vid(pc)))


def normals(pos_mm: np.ndarray, tri: np.ndarray) -> np.ndarray:
    """Vertex normals: the sum of the triangles' integer cross products at each vertex."""
    p = pos_mm.astype(np.float64)
    a, b, c = p[tri[:, 0]], p[tri[:, 1]], p[tri[:, 2]]
    cr = np.cross(b - a, c - a)
    acc = np.zeros_like(p)
    for k in range(3):
        np.add.at(acc, tri[:, k], cr)
    L = np.sqrt((acc * acc).sum(axis=1))
    out = np.zeros_like(p)
    ok = L > 0
    out[ok] = acc[ok] / L[ok, None]
    out[~ok] = (0.0, 0.0, 1.0)
    return out
