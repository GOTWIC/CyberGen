"""A mesh buffer for shells: vertices on integer millimeters per material slot, each tagged
with the face plane it lies on (its flat normal and UV0 frame), triangles tagged with the
closed part they belong to (for the mesh check).

Faces are welded on their plane by the generators themselves (a facade's grid shares its
vertices across bays, a cap's triangles share its ring), never across planes, as flat
shading needs. UV0 is meters along the plane's axes (world-scale tiling, scope 5.2); UV1
(0 to 1 over a pane) and COLOR_0 (window id in alpha) exist only on the glass slots.
"""

from __future__ import annotations

import numpy as np

from ..gltf import Primitive
from . import systems as SY

KEY_OFF = 1 << 20          # vertex keys: 21 bits per axis, +-1048 m around the origin


class Buf:
    def __init__(self):
        self.planes: list[tuple] = []
        self.slots: dict[str, dict] = {}
        self.part = -1

    def new_part(self) -> int:
        self.part += 1
        return self.part

    def plane(self, n, o, uax, vax, u0: float = 0.0, v0: float = 0.0) -> int:
        """A face plane: unit normal n, origin o (mm), UV axes (unit), UV0 at the origin."""
        self.planes.append((n[0], n[1], n[2], o[0], o[1], o[2], uax[0], uax[1], uax[2],
                            vax[0], vax[1], vax[2], u0, v0))
        return len(self.planes) - 1

    def slot(self, name: str) -> dict:
        s = self.slots.get(name)
        if s is None:
            s = {"x": [], "y": [], "z": [], "pl": [], "tri": [], "part": [], "uv1": [],
                 "win": []}
            self.slots[name] = s
        return s

    def add(self, slot: str, plane: int, pts, tris, uv1=None, win: int = 0) -> None:
        """Vertices `pts` ((x, y, z) mm) on `plane` and triangles as local index triples
        (flat list), in the current part."""
        s = self.slot(slot)
        base = len(s["x"])
        for p in pts:
            s["x"].append(p[0])
            s["y"].append(p[1])
            s["z"].append(p[2])
        s["pl"].extend([plane] * len(pts))
        if slot in SY.GLASS_SLOTS:
            s["uv1"].extend(uv1 if uv1 is not None else [(0.0, 0.0)] * len(pts))
            s["win"].extend([win] * len(pts))
        s["tri"].extend(base + i for i in tris)
        s["part"].extend([self.part] * (len(tris) // 3))

    def quad(self, slot: str, plane: int, a, b, c, d, uv1=None, win: int = 0) -> None:
        self.add(slot, plane, (a, b, c, d), (0, 1, 2, 0, 2, 3), uv1, win)

    @property
    def triangles(self) -> int:
        return sum(len(s["tri"]) // 3 for s in self.slots.values())

    # -- out -----------------------------------------------------------------------------

    def arrays(self) -> dict[str, dict]:
        """Per slot (sorted by name): positions (n, 3) int64 mm, plane ids, triangles (m, 3),
        the part of each triangle, UV1 and window ids (glass)."""
        out = {}
        for name in sorted(self.slots):
            s = self.slots[name]
            if not s["tri"]:
                continue
            pos = np.stack([np.array(s["x"], dtype=np.int64), np.array(s["y"], dtype=np.int64),
                            np.array(s["z"], dtype=np.int64)], axis=1)
            out[name] = {"pos": pos, "pl": np.array(s["pl"], dtype=np.int64),
                         "tri": np.array(s["tri"], dtype=np.int64).reshape(-1, 3),
                         "part": np.array(s["part"], dtype=np.int64),
                         "uv1": np.array(s["uv1"], dtype=np.float64).reshape(-1, 2)
                         if s["uv1"] else None,
                         "win": np.array(s["win"], dtype=np.int64) if s["win"] else None}
        return out

    def primitives(self, arrs: dict, materials: dict[str, int]) -> list[Primitive]:
        P = np.array(self.planes, dtype=np.float64).reshape(-1, 14)
        prims = []
        for name, a in arrs.items():
            pl = P[a["pl"]]
            pos = a["pos"].astype(np.float64)
            d = [pos[:, k] - pl[:, 3 + k] for k in range(3)]
            # UV0: meters along the plane's axes, three products added in a fixed order
            uu = (d[0] * pl[:, 6] + d[1] * pl[:, 7]) + d[2] * pl[:, 8]
            vv = (d[0] * pl[:, 9] + d[1] * pl[:, 10]) + d[2] * pl[:, 11]
            uv0 = np.stack([pl[:, 12] + uu / 1000.0, pl[:, 13] + vv / 1000.0], axis=1)
            glass = name in SY.GLASS_SLOTS
            colors = None
            if glass:
                w = a["win"]
                colors = np.stack([np.full(len(w), 255), np.full(len(w), 255),
                                   np.full(len(w), 255), w & 255], axis=1).astype(np.uint8)
            prims.append(Primitive(material=materials[name], positions=a["pos"],
                                   indices=a["tri"].reshape(-1), normals=pl[:, 0:3],
                                   uv0=uv0, uv1=a["uv1"] if glass else None, colors=colors))
        return prims


def vertex_keys(pos: np.ndarray) -> np.ndarray:
    """One int64 per position (21 bits per axis)."""
    p = pos + KEY_OFF
    if p.size and (p.min() < 0 or p.max() >= (1 << 21)):
        raise ValueError("a vertex is more than 1048 m from its building's origin")
    return (p[:, 0] << 42) | (p[:, 1] << 21) | p[:, 2]


def check(arrs: dict) -> dict:
    """The mesh check (scope section 9) on a shell: no degenerate or duplicate triangles,
    and every part closed and consistently wound (each directed edge once, its reverse once),
    so no crack anywhere along the shell; UVs present on every vertex."""
    tris, parts = [], []
    deg = 0
    for a in arrs.values():
        pos, t = a["pos"], a["tri"]
        p0, p1, p2 = pos[t[:, 0]], pos[t[:, 1]], pos[t[:, 2]]
        e1, e2 = p1 - p0, p2 - p0
        cx = e1[:, 1] * e2[:, 2] - e1[:, 2] * e2[:, 1]
        cy = e1[:, 2] * e2[:, 0] - e1[:, 0] * e2[:, 2]
        cz = e1[:, 0] * e2[:, 1] - e1[:, 1] * e2[:, 0]
        deg += int(((cx == 0) & (cy == 0) & (cz == 0)).sum())
        k = vertex_keys(pos)
        tris.append(k[t])
        parts.append(a["part"])
    if not tris:
        return {"triangles": 0, "degenerate": 0, "duplicate": 0, "open_edges": 0,
                "bad_edges": 0, "parts": 0}
    T = np.concatenate(tris)
    Pt = np.concatenate(parts)
    srt = np.sort(T, axis=1)
    dup = len(srt) - len(np.unique(np.concatenate([Pt[:, None], srt], axis=1), axis=0))
    # directed edges (part, from, to)
    E = np.concatenate([np.stack([Pt, T[:, 0], T[:, 1]], axis=1),
                        np.stack([Pt, T[:, 1], T[:, 2]], axis=1),
                        np.stack([Pt, T[:, 2], T[:, 0]], axis=1)])
    Eu, cnt = np.unique(E, axis=0, return_counts=True)
    bad = int((cnt > 1).sum())             # the same directed edge twice: not a 2-manifold
    R = Eu[:, [0, 2, 1]]
    # every directed edge must have its reverse
    idx = np.lexsort((Eu[:, 2], Eu[:, 1], Eu[:, 0]))
    S = Eu[idx]
    pos = np.searchsorted(_rows(S), _rows(R))
    pos = np.minimum(pos, len(S) - 1)
    found = (S[pos] == R).all(axis=1)
    return {"triangles": int(len(T)), "degenerate": deg, "duplicate": int(dup),
            "open_edges": int((~found).sum()), "bad_edges": bad,
            "parts": int(len(np.unique(Pt)))}


def _rows(a: np.ndarray) -> np.ndarray:
    """Rows of three int64 as one sortable structured key."""
    a = np.ascontiguousarray(a)
    return a.view([("a", np.int64), ("b", np.int64), ("c", np.int64)]).reshape(-1)
