"""A plan index of triangles (AG14's fit checks): every triangle filed under the grid cells
its plan box covers, so a point finds the triangles over or under it.

`Surfaces` keeps triangles that face up (a floor, a roof, a road, the ground): for a point
it gives the height of the highest surface under a given height. Every computation is
plain numpy arithmetic in float64 on the triangles as read; nothing is written back into an
asset, so the checks' figures may differ in the last digit from machine to machine but the
assets do not.
"""

from __future__ import annotations

import numpy as np

CELL_M = 2.0
CHUNK = 2_000_000           # (point, triangle) pairs per batch


class TriIndex:
    def __init__(self, tris: np.ndarray, owner: np.ndarray | None = None,
                 cell: float = CELL_M):
        """tris (n, 3, 3); owner (n,) an integer per triangle (which piece it is of)."""
        self.cell = cell
        self.t = np.asarray(tris, dtype=np.float64).reshape(-1, 3, 3)
        n = len(self.t)
        self.owner = np.zeros(n, dtype=np.int64) if owner is None else \
            np.asarray(owner, dtype=np.int64)
        if not n:
            self.keys = np.zeros(0, dtype=np.int64)
            self.ids = np.zeros(0, dtype=np.int64)
            return
        lo = self.t[:, :, :2].min(axis=1)
        hi = self.t[:, :, :2].max(axis=1)
        i0 = np.floor(lo / cell).astype(np.int64)
        i1 = np.floor(hi / cell).astype(np.int64)
        nx = i1[:, 0] - i0[:, 0] + 1
        ny = i1[:, 1] - i0[:, 1] + 1
        cnt = nx * ny
        tid = np.repeat(np.arange(n), cnt)
        k = np.arange(cnt.sum()) - np.repeat(np.cumsum(cnt) - cnt, cnt)
        cx = i0[tid, 0] + k % nx[tid]
        cy = i0[tid, 1] + k // nx[tid]
        key = _key(cx, cy)
        o = np.argsort(key, kind="stable")
        self.keys = key[o]
        self.ids = tid[o]
        # plane of each triangle: z = a x + b y + c (vertical ones get nan)
        p0, p1, p2 = self.t[:, 0], self.t[:, 1], self.t[:, 2]
        e1, e2 = p1 - p0, p2 - p0
        nrm = np.cross(e1, e2)
        self.nz = nrm[:, 2]
        self.area = 0.5 * np.linalg.norm(nrm, axis=1)

    def candidates(self, xy: np.ndarray):
        """(point index, triangle index) pairs: the triangles filed in each point's cell."""
        if not len(self.ids) or not len(xy):
            return np.zeros(0, dtype=np.int64), np.zeros(0, dtype=np.int64)
        c = np.floor(xy / self.cell).astype(np.int64)
        key = _key(c[:, 0], c[:, 1])
        a = np.searchsorted(self.keys, key, "left")
        b = np.searchsorted(self.keys, key, "right")
        cnt = b - a
        pid = np.repeat(np.arange(len(xy)), cnt)
        k = np.arange(cnt.sum()) - np.repeat(np.cumsum(cnt) - cnt, cnt)
        tid = self.ids[np.repeat(a, cnt) + k]
        return pid, tid

    def heights(self, xy: np.ndarray, pid: np.ndarray, tid: np.ndarray, eps: float = 1e-7):
        """For each pair whose triangle contains the point in plan, the triangle's height
        there; (mask of the pairs that do, heights)."""
        P = xy[pid]
        T = self.t[tid]
        a, b, c = T[:, 0, :2], T[:, 1, :2], T[:, 2, :2]
        v0, v1, v2 = b - a, c - a, P - a
        den = v0[:, 0] * v1[:, 1] - v1[:, 0] * v0[:, 1]
        ok = np.abs(den) > 1e-12
        den = np.where(ok, den, 1.0)
        u = (v2[:, 0] * v1[:, 1] - v1[:, 0] * v2[:, 1]) / den
        v = (v0[:, 0] * v2[:, 1] - v2[:, 0] * v0[:, 1]) / den
        inside = ok & (u >= -eps) & (v >= -eps) & (u + v <= 1.0 + eps)
        z = T[:, 0, 2] + u * (T[:, 1, 2] - T[:, 0, 2]) + v * (T[:, 2, 2] - T[:, 0, 2])
        return inside, z


def _key(cx, cy):
    return (cx.astype(np.int64) + (1 << 20)) * (1 << 21) + (cy.astype(np.int64) + (1 << 20))


class Surfaces(TriIndex):
    """Up-facing triangles (normal's z over `min_nz` of its length)."""

    def __init__(self, tris: np.ndarray, owner: np.ndarray | None = None,
                 min_nz: float = 0.2, cell: float = CELL_M):
        tris = np.asarray(tris, dtype=np.float64).reshape(-1, 3, 3)
        if len(tris):
            e1 = tris[:, 1] - tris[:, 0]
            e2 = tris[:, 2] - tris[:, 0]
            n = np.cross(e1, e2)
            L = np.linalg.norm(n, axis=1)
            up = (L > 1e-9) & (n[:, 2] > min_nz * np.maximum(L, 1e-12))
            tris = tris[up]
            owner = None if owner is None else np.asarray(owner)[up]
        super().__init__(tris, owner, cell)

    def under(self, pts: np.ndarray, reach, exclude: np.ndarray | None = None,
              floor=None) -> np.ndarray:
        """For each point (x, y, z): the highest surface at its plan position no higher than
        z + reach (a number, or one per point; nan where none); `exclude` (per point) an
        owner whose triangles do not count; `floor` the ground under each point (a number, or one per point: the
        blockout's land, which stays in the level under every asset)."""
        pts = np.asarray(pts, dtype=np.float64).reshape(-1, 3)
        out = np.full(len(pts), -np.inf)
        R = np.broadcast_to(np.asarray(reach, dtype=np.float64), (len(pts),))
        if len(pts):
            step = max(1, CHUNK // 64)
            for s in range(0, len(pts), step):
                P = pts[s:s + step]
                pid, tid = self.candidates(P[:, :2])
                if len(pid):
                    inside, z = self.heights(P[:, :2], pid, tid)
                    keep = inside & (z <= P[pid, 2] + R[s:s + step][pid])
                    if exclude is not None:
                        keep &= self.owner[tid] != exclude[s:s + step][pid]
                    if keep.any():
                        np.maximum.at(out[s:s + step], pid[keep], z[keep])
        if floor is not None:
            ok = pts[:, 2] + R >= floor
            out = np.where(ok, np.maximum(out, floor), out)
        out[np.isinf(out)] = np.nan
        return out
