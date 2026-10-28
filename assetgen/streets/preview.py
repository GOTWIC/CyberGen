"""`preview_streets.png`: the street packs drawn from above, straight from their glTF files
(a check that the packs hold what the report says), the whole city at a glance and close
insets: every triangle filled with its slot's color, lower ones first.
"""

from __future__ import annotations

import json
import struct
from pathlib import Path

import numpy as np

_CT = {5126: np.float32, 5125: np.uint32, 5123: np.uint16, 5121: np.uint8, 5122: np.int16,
       5120: np.int8}
_NC = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4}


def read_glb(path: Path):
    """[(node name, material name, rgba, triangles (n, 3, 3) in citygen's frame, meters)]."""
    data = Path(path).read_bytes()
    if len(data) < 20:
        return []
    jl, = struct.unpack_from("<I", data, 12)
    doc = json.loads(data[20:20 + jl].decode("utf-8"))
    off = 20 + jl
    bl, = struct.unpack_from("<I", data, off)
    binary = data[off + 8:off + 8 + bl]

    def acc(i):
        a = doc["accessors"][i]
        v = doc["bufferViews"][a["bufferView"]]
        dt = _CT[a["componentType"]]
        n = _NC[a["type"]]
        stride = v.get("byteStride")
        start = v.get("byteOffset", 0) + a.get("byteOffset", 0)
        if stride and stride != np.dtype(dt).itemsize * n:
            raw = np.frombuffer(binary, dtype=np.uint8, count=stride * a["count"],
                                offset=start).reshape(a["count"], stride)
            arr = raw[:, :np.dtype(dt).itemsize * n].copy().view(dt).reshape(a["count"], n)
        else:
            arr = np.frombuffer(binary, dtype=dt, count=a["count"] * n,
                                offset=start).reshape(a["count"], n)
        return arr
    mats = doc.get("materials", [])
    out = []
    for nd in doc.get("nodes", []):
        if "mesh" not in nd:
            continue
        t = nd.get("translation", [0.0, 0.0, 0.0])
        for pr in doc["meshes"][nd["mesh"]]["primitives"]:
            pos = acc(pr["attributes"]["POSITION"]).astype(np.float64)
            pos = pos + np.array(t)
            P = np.stack([pos[:, 0], -pos[:, 2], pos[:, 1]], axis=1)
            idx = acc(pr["indices"]).reshape(-1, 3).astype(np.int64)
            m = mats[pr["material"]] if mats else {"name": "?", "pbrMetallicRoughness": {}}
            col = m.get("pbrMetallicRoughness", {}).get("baseColorFactor", [0.5, 0.5, 0.5, 1])
            out.append((nd["name"], m.get("name", "?"), col, P[idx]))
    return out


def render(streets_dir: Path, out_png: Path, insets=None, title: str = "") -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.collections import PolyCollection

    tris, cols, zs = [], [], []

    def add(T, col):
        tris.append(T[:, :, :2])
        zs.append(T[:, :, 2].max(axis=1))
        cols.append(np.repeat(np.array([col], dtype=np.float64), len(T), axis=0))
    for f in sorted(Path(streets_dir).glob("t*.glb")):
        for _, name, col, T in read_glb(f):
            if name.startswith("glass"):
                col = [col[0], col[1], col[2], 0.35]
            add(T, col)
    # instanced parts (containers) where the contribution places them
    con = Path(streets_dir).parent / "unreal_contribution.streets.json"
    parts = Path(streets_dir) / "parts.glb"
    if con.is_file() and parts.is_file():
        protos: dict = {}
        for node, _, col, T in read_glb(parts):
            protos.setdefault(node, []).append((col, T))
        for e in json.loads(con.read_text(encoding="utf-8"))["entries"]:
            for p in e.get("parts", []):
                px, py, pz = e["pivot"]
                for col, T in protos.get(p["node"], []):
                    for x, y, z, yaw in p["xforms"]:
                        a = np.radians(yaw)
                        c, s_ = np.cos(a), np.sin(a)
                        X = T[:, :, 0] * c - T[:, :, 1] * s_ + px + x
                        Y = T[:, :, 0] * s_ + T[:, :, 1] * c + py + y
                        add(np.stack([X, Y, T[:, :, 2] + pz + z], axis=2), col)
    if not tris:
        return
    T = np.concatenate(tris)
    Z = np.concatenate(zs)
    Cc = np.concatenate(cols)
    order = np.argsort(Z, kind="stable")
    T, Cc = T[order], Cc[order]
    insets = insets or []
    n = 1 + len(insets)
    fig = plt.figure(figsize=(8 * min(n, 3), 8 * ((n + 2) // 3)), dpi=110)
    boxes = [None] + list(insets)
    for k, box in enumerate(boxes):
        ax = fig.add_subplot((n + 2) // 3, min(n, 3), k + 1)
        ax.set_facecolor("#1c2128")
        if box is None:
            sel = slice(None)
            x0, y0 = T[:, :, 0].min(), T[:, :, 1].min()
            x1, y1 = T[:, :, 0].max(), T[:, :, 1].max()
            ax.set_title(title or "streets", fontsize=10)
        else:
            cx_, cy_, r = box
            x0, x1, y0, y1 = cx_ - r, cx_ + r, cy_ - r, cy_ + r
            m = ((T[:, :, 0].max(axis=1) >= x0) & (T[:, :, 0].min(axis=1) <= x1) &
                 (T[:, :, 1].max(axis=1) >= y0) & (T[:, :, 1].min(axis=1) <= y1))
            sel = m
            ax.set_title(f"{2 * r:.0f} m around ({cx_:.0f}, {cy_:.0f})", fontsize=9)
        pc = PolyCollection(T[sel], facecolors=Cc[sel], edgecolors="none",
                            linewidths=0, antialiased=box is not None)
        ax.add_collection(pc)
        ax.set_xlim(x0, x1)
        ax.set_ylim(y0, y1)
        ax.set_aspect("equal")
        ax.tick_params(labelsize=6)
    fig.tight_layout()
    out_png.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_png)
    plt.close(fig)
