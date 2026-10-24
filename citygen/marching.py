"""Filled marching squares: the region z > 0 of a raster as polygons on the 0.01 m grid.

Replaces contourpy, whose compiled interpolation rounds differently on different machines
(a compiler may fuse x0 + t * (x1 - x0) into one operation on ARM). Here every crossing point
is computed with separate elementwise numpy operations (t = z0 / (z0 - z1), then x0 + t * dx),
which IEEE 754 rounds the same everywhere, and the vertex is snapped to the grid at once.
Each crossing point belongs to one raster edge and is computed once, so the boundary between
two regions whose fields are negatives of each other has the same vertices on both sides.

Saddle cells (two opposite corners inside) are joined when the cell center (mean of the four
corners) is inside. Rings run counterclockwise around the region (holes clockwise); the
region is their even-odd combination.
"""

from __future__ import annotations

import numpy as np
import shapely
from shapely.geometry import Polygon

from . import geom as G

# Edges of a cell in counterclockwise order: bottom, right, top, left.
# Corners: 0 bottom left, 1 bottom right, 2 top right, 3 top left.


def _axis(v: np.ndarray) -> np.ndarray:
    """Coordinates with one extra step on each side."""
    lo = v[0] - (v[1] - v[0])
    hi = v[-1] + (v[-1] - v[-2])
    return np.concatenate([[lo], v, [hi]])


def rings(xs: np.ndarray, ys: np.ndarray, z: np.ndarray) -> list[np.ndarray]:
    """Closed rings (first point repeated) around z > 0, on the grid, counterclockwise around
    the region. xs: column coordinates, ys: row coordinates (both increasing), z[row, col]."""
    z = np.asarray(z, dtype=np.float64)
    ny, nx = z.shape
    zp = np.full((ny + 2, nx + 2), -1.0)
    zp[1:-1, 1:-1] = z  # a negative border closes every ring
    xp, yp = _axis(np.asarray(xs, dtype=np.float64)), _axis(np.asarray(ys, dtype=np.float64))
    NY, NX = zp.shape
    inside = zp > 0.0
    if not inside.any():
        return []
    n_h = NY * (NX - 1)

    # Crossing points on horizontal edges (row j, columns i and i + 1).
    za, zb = zp[:, :-1], zp[:, 1:]
    hmask = inside[:, :-1] != inside[:, 1:]
    jh, ih = np.nonzero(hmask)
    a, b = za[jh, ih], zb[jh, ih]
    t = a / (a - b)
    x0, x1 = xp[ih], xp[ih + 1]
    hx = x0 + t * (x1 - x0)
    hy = yp[jh]
    # Crossing points on vertical edges (column i, rows j and j + 1).
    za, zb = zp[:-1, :], zp[1:, :]
    vmask = inside[:-1, :] != inside[1:, :]
    jv, iv = np.nonzero(vmask)
    a, b = za[jv, iv], zb[jv, iv]
    t = a / (a - b)
    y0, y1 = yp[jv], yp[jv + 1]
    vy = y0 + t * (y1 - y0)
    vx = xp[iv]

    n_ids = n_h + (NY - 1) * NX
    px = np.zeros(n_ids)
    py = np.zeros(n_ids)
    hid = jh * (NX - 1) + ih
    vid = n_h + jv * NX + iv
    px[hid], py[hid] = hx, hy
    px[vid], py[vid] = vx, vy
    px = np.rint(px * 100.0) / 100.0
    py = np.rint(py * 100.0) / 100.0

    # Cells: corner flags and the ids of their four edges (counterclockwise).
    c0, c1 = inside[:-1, :-1], inside[:-1, 1:]
    c2, c3 = inside[1:, 1:], inside[1:, :-1]
    case = c0 * 1 + c1 * 2 + c2 * 4 + c3 * 8
    jc, ic = np.nonzero((case != 0) & (case != 15))
    case = case[jc, ic]
    e_bottom = jc * (NX - 1) + ic
    e_right = n_h + jc * NX + ic + 1
    e_top = (jc + 1) * (NX - 1) + ic
    e_left = n_h + jc * NX + ic
    edges = np.stack([e_bottom, e_right, e_top, e_left], axis=1)
    corners = np.stack([c0[jc, ic], c1[jc, ic], c2[jc, ic], c3[jc, ic]], axis=1)
    # Edge k runs from corner k to corner k + 1 (counterclockwise). The ring leaves a cell
    # through an edge going from inside to outside and enters through one going outside to
    # inside, so each segment runs from an in-out edge to an out-in edge.
    start = corners & ~np.roll(corners, -1, axis=1)
    end = ~corners & np.roll(corners, -1, axis=1)
    nxt = np.full(n_ids, -1, dtype=np.int64)
    saddle = (case == 5) | (case == 10)
    plain = ~saddle
    si = np.argmax(start[plain], axis=1)
    ei = np.argmax(end[plain], axis=1)
    rows = np.nonzero(plain)[0]
    nxt[edges[rows, si]] = edges[rows, ei]
    if saddle.any():
        rows = np.nonzero(saddle)[0]
        zc = ((zp[jc[rows], ic[rows]] + zp[jc[rows], ic[rows] + 1])
              + (zp[jc[rows] + 1, ic[rows] + 1] + zp[jc[rows] + 1, ic[rows]])) * 0.25
        joined = zc > 0.0
        for r, cs, jn in zip(rows, case[rows], joined):
            e = edges[r]
            if cs == 5:  # corners 0 and 2 inside
                pairs = ((0, 1), (2, 3)) if jn else ((0, 3), (2, 1))
            else:  # corners 1 and 3 inside
                pairs = ((1, 2), (3, 0)) if jn else ((1, 0), (3, 2))
            for s, f in pairs:
                nxt[e[s]] = e[f]

    out = []
    todo = np.nonzero(nxt >= 0)[0]
    seen = bytearray(n_ids)
    nl = nxt.tolist()
    xl, yl = px.tolist(), py.tolist()
    for s in todo.tolist():
        if seen[s]:
            continue
        ring = []
        k = s
        while not seen[k]:
            seen[k] = True
            p = (xl[k], yl[k])
            if not ring or ring[-1] != p:
                ring.append(p)
            k = nl[k]
        if len(ring) > 1 and ring[0] == ring[-1]:
            ring.pop()
        if len(ring) >= 3:
            ring.append(ring[0])
            out.append(np.array(ring))
    return out


def filled(xs: np.ndarray, ys: np.ndarray, z: np.ndarray):
    """Region z > 0 as a (Multi)Polygon on the grid."""
    shells = []
    for r in rings(xs, ys, z):
        poly = Polygon(r)
        if G.area(poly) <= 0.0:
            continue
        if not poly.is_valid:
            poly = G.polygonal(shapely.make_valid(poly))
        shells.append(poly)
    if not shells:
        return Polygon()
    # Rings never cross (they may touch after snapping): the region is their even-odd
    # combination, which handles holes and islands in holes alike.
    shells.sort(key=lambda p: (-G.area(p),) + G.qbounds(p))
    region = shells[0]
    for p in shells[1:]:
        region = shapely.symmetric_difference(region, p, grid_size=G.GRID_M)
    return G.polygonal(G.snap(region))
